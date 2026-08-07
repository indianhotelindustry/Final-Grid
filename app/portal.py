"""
Guest Self-Service Portal — Digital Pre-Check-In
=================================================
No login required. Accessible via a one-time token link sent to guest.

Flow:
  Staff clicks "Send Pre-check-in" on a reservation
    → Token generated (48-hour expiry)
    → WhatsApp notification sent to guest with the link
    → Guest opens link on their phone
    → Fills in personal details, uploads ID photo, signs
    → Submission saved to DB
    → Front desk sees "Pre-check-in Complete" badge on the reservation
    → Actual check-in at hotel is fast — data is pre-filled

Public routes (no login):
  GET  /portal/<token>           — Pre-check-in form
  POST /portal/<token>/submit    — Submit the form
  GET  /portal/<token>/complete  — Thank-you / success page

Staff routes (login required):
  POST /portal/send/<reservation_id>         — Generate token + send WA
  GET  /portal/submissions                   — View all submissions
  GET  /portal/submissions/<reservation_id>  — View one submission
"""

import os
import secrets
import base64
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, abort, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import (db, Reservation, Guest, Room, RoomType,
                        PreCheckinToken, PreCheckinSubmission)
from app.services import get_business_date


# ── Upload validation ───────────────────────────────────────────────────────
# Allowed file types for guest ID documents. Each entry maps an extension to
# the set of magic-byte signatures that mark the first bytes of a valid file
# of that type. This is an inclusive allowlist — anything not listed is
# rejected outright. We never rename a bad upload: the caller must decide.
_ID_UPLOAD_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_ID_UPLOAD_RULES = {
    'jpg':  (b'\xff\xd8\xff',),                      # JPEG SOI
    'jpeg': (b'\xff\xd8\xff',),
    'png':  (b'\x89PNG\r\n\x1a\n',),                  # PNG header
    'pdf':  (b'%PDF-',),                              # PDF signature
}


def _sniff_ext(data: bytes) -> str | None:
    """Return the canonical extension for `data` based on its magic bytes,
    or None if the content does not match any allowed type."""
    if not data:
        return None
    for ext, signatures in _ID_UPLOAD_RULES.items():
        for sig in signatures:
            if data.startswith(sig):
                # Normalise 'jpeg' down to 'jpg' for consistent storage.
                return 'jpg' if ext == 'jpeg' else ext
    return None


def _validate_upload(data: bytes, claimed_ext: str | None) -> tuple[str | None, str | None]:
    """Validate an uploaded file's bytes. Returns (canonical_ext, error).

    - Enforces size limit
    - Requires the magic bytes to match one of the allowed types
    - If a filename extension was claimed, it MUST agree with the sniffed
      type; we never silently rewrite an incorrect extension.
    """
    if not data:
        return None, 'The uploaded file is empty.'
    if len(data) > _ID_UPLOAD_MAX_BYTES:
        mb = _ID_UPLOAD_MAX_BYTES // (1024 * 1024)
        return None, f'File is larger than the {mb} MB limit.'
    sniffed = _sniff_ext(data)
    if sniffed is None:
        return None, (
            'File type is not allowed. '
            'Please upload a JPG, PNG, or PDF.'
        )
    if claimed_ext:
        claimed = claimed_ext.lower().lstrip('.')
        # Accept jpg/jpeg as interchangeable; everything else must match.
        claimed_norm = 'jpg' if claimed == 'jpeg' else claimed
        if claimed_norm != sniffed:
            return None, (
                f'File content ({sniffed.upper()}) does not match its '
                f'name extension (.{claimed}). Upload rejected.'
            )
    return sniffed, None

portal_bp = Blueprint('portal', __name__, url_prefix='/portal')

TOKEN_TTL_HOURS = 48   # token lifespan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hotel_name():
    return current_app.config.get('HOTEL_NAME', 'Hotel')


def _portal_url(token: str) -> str:
    """Build the full public URL for the pre-check-in form."""
    base = os.getenv('PUBLIC_BASE_URL', 'http://localhost:5000')
    return f"{base.rstrip('/')}/portal/{token}"


def _generate_token(reservation_id: int) -> PreCheckinToken:
    """Create (or replace) a pre-check-in token for the reservation."""
    # Invalidate any old unused tokens for this reservation
    old = PreCheckinToken.query.filter_by(
        reservation_id=reservation_id, is_used=False
    ).all()
    for t in old:
        db.session.delete(t)

    token_str = secrets.token_urlsafe(40)
    token = PreCheckinToken(
        token=token_str,
        reservation_id=reservation_id,
        expires_at=datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS),
    )
    db.session.add(token)
    db.session.flush()
    return token


def _get_valid_token(token_str: str) -> PreCheckinToken:
    """Return a valid, unexpired, unused token or abort 404/410."""
    t = PreCheckinToken.query.filter_by(token=token_str).first()
    if not t:
        abort(404)
    if t.is_used:
        abort(410)   # Gone — already submitted
    if t.expires_at < datetime.utcnow():
        abort(410)   # Expired
    return t


def _private_upload_dir(folder: str) -> str:
    """Returns path to private (non-web-accessible) upload directory."""
    return os.path.join(current_app.root_path, 'private_uploads', folder)


def _save_upload(file_data: str, folder: str, prefix: str) -> tuple[str | None, str | None]:
    """Save a base64 data-URI image to private storage.

    Returns (relative_path, error). On success error is None; on rejection
    relative_path is None and error is a human-readable reason. The content
    is validated by magic-byte sniffing, not by the data-URI header (which
    is attacker-controlled in a guest-submitted payload).
    """
    if not file_data or ',' not in file_data:
        return None, None  # nothing uploaded — not an error
    try:
        _header, encoded = file_data.split(',', 1)
        raw = base64.b64decode(encoded, validate=False)
    except Exception:
        return None, 'Uploaded file is not valid base64 data.'
    ext, err = _validate_upload(raw, claimed_ext=None)
    if err:
        return None, err
    filename = f'{prefix}_{secrets.token_hex(8)}.{ext}'
    upload_dir = _private_upload_dir(folder)
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, filename), 'wb') as f:
        f.write(raw)
    return f'{folder}/{filename}', None


# ---------------------------------------------------------------------------
# Public: Pre-Check-In Form
# ---------------------------------------------------------------------------

@portal_bp.route('/<token_str>')
def form(token_str):
    t = _get_valid_token(token_str)
    r = t.reservation

    # Already submitted? Show the complete page.
    if hasattr(r, 'precheckin_submission') and r.precheckin_submission:
        return redirect(url_for('portal.complete', token_str=token_str))

    hotel_name = _hotel_name()
    nights = (r.departure_date - r.arrival_date).days
    return render_template(
        'portal/form.html',
        token=token_str,
        reservation=r,
        nights=nights,
        hotel_name=hotel_name,
    )


@portal_bp.route('/<token_str>/submit', methods=['POST'])
def submit(token_str):
    t = _get_valid_token(token_str)
    r = t.reservation

    if hasattr(r, 'precheckin_submission') and r.precheckin_submission:
        return redirect(url_for('portal.complete', token_str=token_str))

    # --- Parse form ---
    full_name = request.form.get('full_name', '').strip()
    dob_str = request.form.get('date_of_birth', '').strip()
    nationality = request.form.get('nationality', '').strip()
    address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    id_type = request.form.get('id_type', '').strip()
    id_number = request.form.get('id_number', '').strip()
    eta = request.form.get('estimated_arrival_time', '').strip()
    special_requests = request.form.get('special_requests', '').strip()
    terms = request.form.get('terms_accepted') == 'on'

    if not full_name or not id_type or not id_number or not terms:
        flash('Name, ID document details and terms acceptance are required.', 'danger')
        return redirect(url_for('portal.form', token_str=token_str))

    # Parse DOB
    dob = None
    if dob_str:
        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # Save uploaded ID photo (base64 data-URI from webcam/file)
    id_photo_path, id_err = _save_upload(
        request.form.get('id_photo_data', ''),
        'precheckin', f'id_{r.id}'
    )
    if id_err:
        flash(id_err, 'danger')
        return redirect(url_for('portal.form', token_str=token_str))

    # Fallback: traditional file upload. Validated the same way — we never
    # silently rewrite an extension, and we reject anything whose content
    # does not match an allowed type (JPG / PNG / PDF).
    if not id_photo_path and 'id_photo_file' in request.files:
        f = request.files['id_photo_file']
        if f and f.filename:
            # secure_filename strips path separators and nulls.
            safe_name = secure_filename(f.filename) or ''
            claimed = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else ''
            raw = f.read(_ID_UPLOAD_MAX_BYTES + 1)
            ext, err = _validate_upload(raw, claimed_ext=claimed)
            if err:
                flash(err, 'danger')
                return redirect(url_for('portal.form', token_str=token_str))
            filename = f'id_{r.id}_{secrets.token_hex(6)}.{ext}'
            upload_dir = _private_upload_dir('precheckin')
            os.makedirs(upload_dir, exist_ok=True)
            with open(os.path.join(upload_dir, filename), 'wb') as out:
                out.write(raw)
            id_photo_path = f'precheckin/{filename}'

    # Save signature (always a data-URI from the signature pad)
    signature_path, sig_err = _save_upload(
        request.form.get('signature_data', ''),
        'precheckin', f'sig_{r.id}'
    )
    if sig_err:
        flash(sig_err, 'danger')
        return redirect(url_for('portal.form', token_str=token_str))

    # Update the Guest record with the verified details
    guest = r.guest
    if guest:
        guest.name = full_name
        guest.address = address
        guest.id_proof_type = id_type
        guest.id_proof_number = id_number

    # Create submission
    submission = PreCheckinSubmission(
        reservation_id=r.id,
        token_id=t.id,
        full_name=full_name,
        date_of_birth=dob,
        nationality=nationality,
        address=address,
        city=city,
        id_type=id_type,
        id_number=id_number,
        id_photo_path=id_photo_path,
        estimated_arrival_time=eta or None,
        special_requests=special_requests or None,
        signature_path=signature_path,
        terms_accepted=terms,
        ip_address=request.remote_addr,
    )
    db.session.add(submission)

    # Mark token used
    t.is_used = True
    db.session.commit()

    return redirect(url_for('portal.complete', token_str=token_str))


@portal_bp.route('/<token_str>/complete')
def complete(token_str):
    t = PreCheckinToken.query.filter_by(token=token_str).first_or_404()
    r = t.reservation
    hotel_name = _hotel_name()
    submission = r.precheckin_submission if hasattr(r, 'precheckin_submission') else None
    return render_template(
        'portal/complete.html',
        reservation=r,
        hotel_name=hotel_name,
        submission=submission,
    )


# ---------------------------------------------------------------------------
# Staff: Send Pre-Check-In Link
# ---------------------------------------------------------------------------

@portal_bp.route('/send/<int:reservation_id>', methods=['POST'])
@login_required
def send_link(reservation_id):
    r = Reservation.query.get_or_404(reservation_id)

    if r.status not in ('Reserved', 'Confirmed'):
        flash('Pre-check-in can only be sent for Reserved or Confirmed bookings.', 'warning')
        return redirect(url_for('main.reservations'))

    if not r.guest or not r.guest.phone:
        flash('Guest phone number is required to send pre-check-in link.', 'danger')
        return redirect(url_for('main.reservations'))

    # Generate token
    token = _generate_token(reservation_id)
    db.session.commit()

    link = _portal_url(token.token)

    # Send WhatsApp notification
    try:
        from app.notifications import _send_whatsapp, _log_notification, _hotel_name as hn
        message = (
            f"🏨 *Pre-Check-In — {hn()}*\n\n"
            f"Dear {r.guest.name},\n\n"
            f"Save time at the front desk! Complete your pre-check-in online before arrival:\n\n"
            f"🔗 {link}\n\n"
            f"✅ Takes less than 2 minutes on your phone.\n"
            f"📋 Ref: {r.booking_reference or r.id} | "
            f"Check-in: {r.arrival_date.strftime('%d %b %Y')}\n\n"
            f"This link expires in {TOKEN_TTL_HOURS} hours."
        )
        ok, err = _send_whatsapp(r.guest.phone, message)
        _log_notification(
            current_app._get_current_object(),
            'whatsapp', r.guest.phone, 'precheckin_link', r.id,
            'sent' if ok else 'failed', err if not ok else ''
        )
        if ok:
            flash(f'Pre-check-in link sent to {r.guest.phone} via WhatsApp.', 'success')
        else:
            flash(f'WhatsApp send failed: {err}. Link: {link}', 'warning')
    except Exception as e:
        flash(f'Notification error: {e}. Link for manual sharing: {link}', 'warning')

    return redirect(url_for('main.reservations'))


# ---------------------------------------------------------------------------
# Staff: View All Submissions
# ---------------------------------------------------------------------------

@portal_bp.route('/submissions')
@login_required
def submissions():
    if not current_user.has_role('Admin', 'Manager', 'FrontDesk'):
        abort(403)
    all_subs = PreCheckinSubmission.query\
        .order_by(PreCheckinSubmission.submitted_at.desc()).all()
    return render_template('portal/submissions.html', submissions=all_subs)


@portal_bp.route('/submissions/<int:reservation_id>')
@login_required
def view_submission(reservation_id):
    if not current_user.has_role('Admin', 'Manager', 'FrontDesk'):
        abort(403)
    r = Reservation.query.get_or_404(reservation_id)
    sub = r.precheckin_submission if hasattr(r, 'precheckin_submission') else None
    if not sub:
        flash('No pre-check-in submission for this reservation.', 'info')
        return redirect(url_for('portal.submissions'))
    return render_template('portal/view_submission.html', reservation=r, sub=sub)
