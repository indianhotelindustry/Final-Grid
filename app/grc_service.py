"""
GRC Service — Guest Registration Card + Form C PDF generation
=============================================================
"""
import io
import os
import re
import logging
from datetime import datetime
from flask import current_app, render_template

from app.models import (db, Reservation, Guest, CheckInRecord, GuestIDDocument,
                         ReservationPassenger, PreCheckinSubmission,
                         ForeignNationalInfo, Settings)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

_SAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9\-]')


def _sanitize_filename_part(value: str) -> str:
    """Make *value* safe for a Windows/Linux/macOS filename component.

    Strips whitespace, converts internal spaces to hyphens, and drops every
    character outside ``[A-Za-z0-9-]``. Returns '' if nothing survives.
    """
    if not value:
        return ''
    cleaned = value.strip().replace(' ', '-')
    return _SAFE_FILENAME_RE.sub('', cleaned)


def _extract_room_number(room_number) -> str:
    """Pull the numeric part out of a room code (e.g. ``'D205'`` → ``'205'``).

    Preserves the original (sanitised) string when no digits are present, so
    codes like ``'SUITE'`` still appear in the filename instead of being
    reduced to empty.
    """
    s = str(room_number or '').strip()
    if not s:
        return '0'
    digits = ''.join(ch for ch in s if ch.isdigit())
    return digits or _SAFE_FILENAME_RE.sub('', s) or '0'


def build_grc_filename(reservation) -> str:
    """Compose the GRC download filename.

    Format: ``Room#<RoomNumber>-<FirstName>-<LastName>.pdf``.
    Falls back gracefully when the last name is missing (``Room#201-Anjali.pdf``)
    or when neither first nor last name is set (``Room#201-Guest.pdf``).
    If no room is assigned (e.g. cancelled bookings) the booking reference is
    used instead so the filename still identifies the stay.
    """
    # Room segment
    room = getattr(reservation, 'room', None)
    if room and getattr(room, 'room_number', None):
        room_part = _extract_room_number(room.room_number)
    else:
        ref = (reservation.booking_reference or f'RES{reservation.id}').strip()
        room_part = _sanitize_filename_part(ref) or str(reservation.id)

    # Guest name segment
    guest = getattr(reservation, 'guest', None)
    first = _sanitize_filename_part(getattr(guest, 'first_name', '') or '')
    last  = _sanitize_filename_part(getattr(guest, 'last_name', '') or '')
    if first and last:
        guest_part = f'{first}-{last}'
    elif first:
        guest_part = first
    elif last:
        guest_part = last
    else:
        guest_part = 'Guest'

    return f'Room#{room_part}-{guest_part}.pdf'


def is_foreign_national(guest):
    """Check if guest is a foreign national (country is not India)."""
    if not guest:
        return False
    country = (guest.country or '').strip()
    return country != '' and country.lower() != 'india'


def _get_setting(key, default=''):
    s = Settings.query.filter_by(key=key).first()
    return s.value if s and s.value else default


def _abs_path(relative_path, private=False):
    """Convert a stored relative path to an absolute file:// URI for xhtml2pdf."""
    if not relative_path:
        return None
    if private:
        full = os.path.join(current_app.root_path, 'private_uploads', relative_path)
    else:
        full = os.path.join(current_app.root_path, 'static', relative_path)
    if os.path.exists(full):
        return full.replace('\\', '/')
    return None


def _get_hotel_info():
    """Gather hotel branding info from Settings."""
    keys = ['hotel_name', 'hotel_address', 'hotel_contact', 'hotel_gstin',
            'hotel_email', 'hotel_cin', 'hotel_state_code', 'invoice_logo_filename']
    rows = Settings.query.filter(Settings.key.in_(keys)).all()
    info = {r.key: r.value for r in rows}

    logo_path = None
    logo_fn = info.get('invoice_logo_filename', '')
    if logo_fn:
        lp = os.path.join(current_app.static_folder, 'uploads', logo_fn)
        if os.path.exists(lp):
            logo_path = lp.replace('\\', '/')
    info['logo_path'] = logo_path
    return info


def _gather_grc_context(reservation_id):
    """Gather all data needed for GRC PDF."""
    reservation = Reservation.query.get(reservation_id)
    if not reservation:
        return None

    guest = reservation.guest
    checkin = reservation.checkin_record
    passengers = ReservationPassenger.query.filter_by(
        reservation_id=reservation_id
    ).all()

    # ID documents
    id_doc = GuestIDDocument.query.filter_by(guest_id=guest.id).order_by(
        GuestIDDocument.created_at.desc()
    ).first() if guest else None

    # Foreign national info
    foreign_info = ForeignNationalInfo.query.filter_by(
        guest_id=guest.id
    ).first() if guest and is_foreign_national(guest) else None

    # Image paths
    guest_photo = _abs_path(checkin.guest_photo_path) if checkin and checkin.guest_photo_path else None
    signature = _abs_path(checkin.signature_path) if checkin and checkin.signature_path else None
    id_front = _abs_path(id_doc.front_image_path, private=True) if id_doc and id_doc.front_image_path else None
    id_back = _abs_path(id_doc.back_image_path, private=True) if id_doc and id_doc.back_image_path else None

    hotel = _get_hotel_info()
    nights = (reservation.departure_date - reservation.arrival_date).days if reservation.departure_date and reservation.arrival_date else 0

    # ── Source / OTA channel display ────────────────────────────────────
    # Resolve authoritative channel name ('MakeMyTrip', 'Goibibo', etc.)
    # via _infer_ota_source so GRC, dashboard, reports and KPIs all agree.
    ota_channel_display = None
    source_display = reservation.source or '—'
    if (reservation.source or '').strip() == 'OTA':
        try:
            from app.ota import _infer_ota_source
            ota_channel_display = _infer_ota_source(reservation)
        except Exception:
            ota_channel_display = reservation.ota_channel or None

    # ── Payment totals (advance / paid / balance) ───────────────────────
    try:
        from app.services import calculate_stay_amount
        stay_amount = calculate_stay_amount(reservation)
    except Exception:
        stay_amount = {'paid': 0.0, 'balance': 0.0, 'total': 0.0}

    # ── Mode of payment summary ─────────────────────────────────────────
    # Rules:
    #   * OTA paid_at_ota  → "{Channel} Paid" (e.g. "MMT Paid")
    #   * Walk-in / Direct → "Walk-in" with actual mode in brackets if paid
    #   * Otherwise        → pay_at_hotel: list distinct modes used, else "Pay at Hotel"
    payment_mode_summary = '—'
    src = (reservation.source or '').strip()
    ota_pay_status = (reservation.ota_payment_status or '').strip()

    # Collect distinct payment mode names from non-voided payments.
    paid_mode_names = []
    seen_modes = set()
    for p in (reservation.payments or []):
        if p.is_voided:
            continue
        pm = getattr(p, 'payment_mode', None)
        name = getattr(pm, 'name', None) if pm else None
        if name and name not in seen_modes:
            seen_modes.add(name)
            paid_mode_names.append(name)

    if src == 'OTA' and ota_pay_status == 'paid_at_ota':
        # Prefer the OTA receivable head actually booked; fall back to a
        # generic label from the channel name.
        ota_paid_name = next(
            (n for n in paid_mode_names if 'Paid' in n), None)
        if ota_paid_name:
            payment_mode_summary = ota_paid_name
        elif ota_channel_display:
            short_map = {
                'MakeMyTrip': 'MMT Paid', 'Goibibo': 'Goibibo Paid',
                'Booking.com': 'Booking.com Paid', 'Agoda': 'Agoda Paid',
                'Expedia': 'Expedia Paid', 'Airbnb': 'Airbnb Paid',
                'Yatra': 'Yatra Paid', 'EaseMyTrip': 'EaseMyTrip Paid',
            }
            payment_mode_summary = short_map.get(
                ota_channel_display, f'{ota_channel_display} Paid')
    elif src == 'Walk-in':
        if paid_mode_names:
            payment_mode_summary = 'Walk-in · ' + ' + '.join(paid_mode_names)
        else:
            payment_mode_summary = 'Walk-in'
    else:
        # Calling / Website / Agent / OTA pay_at_hotel — show collected modes
        # if any; else indicate settlement happens at hotel.
        if paid_mode_names:
            payment_mode_summary = ' + '.join(paid_mode_names)
        elif src == 'OTA':
            payment_mode_summary = 'Pay at Hotel'
        else:
            payment_mode_summary = src or '—'

    return {
        'reservation': reservation,
        'guest': guest,
        'checkin': checkin,
        'passengers': passengers,
        'id_doc': id_doc,
        'foreign_info': foreign_info,
        'is_foreign': is_foreign_national(guest),
        'guest_photo': guest_photo,
        'signature': signature,
        'id_front': id_front,
        'id_back': id_back,
        'hotel': hotel,
        'nights': nights,
        'generated_at': datetime.utcnow(),
        'source_display': source_display,
        'ota_channel_display': ota_channel_display,
        'stay_amount': stay_amount,
        'payment_mode_summary': payment_mode_summary,
    }


def generate_grc_pdf(reservation_id):
    """Generate Guest Registration Card as PDF. Returns BytesIO or None."""
    ctx = _gather_grc_context(reservation_id)
    if not ctx:
        return None

    html = render_template('grc_pdf.html', **ctx)

    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.error('xhtml2pdf not installed')
        return None

    buf = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buf)
    if pisa_status.err:
        logger.error('GRC PDF generation failed for reservation %s', reservation_id)
        return None

    # Update checkin record
    checkin = ctx['checkin']
    if checkin:
        checkin.grc_generated_at = datetime.utcnow()
        db.session.commit()

    buf.seek(0)
    return buf


def generate_form_c_pdf(reservation_id):
    """Generate FRRO Form C as PDF for foreign nationals. Returns BytesIO or None."""
    ctx = _gather_grc_context(reservation_id)
    if not ctx or not ctx['is_foreign']:
        return None

    html = render_template('form_c_pdf.html', **ctx)

    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.error('xhtml2pdf not installed')
        return None

    buf = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buf)
    if pisa_status.err:
        logger.error('Form C PDF generation failed for reservation %s', reservation_id)
        return None

    buf.seek(0)
    return buf


def prefill_from_precheckin(reservation_id):
    """Return pre-fill dict from PreCheckinSubmission if available."""
    sub = PreCheckinSubmission.query.filter_by(reservation_id=reservation_id).first()
    if not sub:
        return {}
    return {
        'full_name': sub.full_name,
        'date_of_birth': sub.date_of_birth,
        'nationality': sub.nationality,
        'id_type': sub.id_type,
        'id_number': sub.id_number,
        'address': sub.address,
        'city': sub.city,
        'special_requests': sub.special_requests,
        'has_portal_signature': bool(sub.signature_path),
        'portal_signature_path': sub.signature_path,
    }
