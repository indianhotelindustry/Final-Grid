"""
Channel Manager Webhook Endpoints
Receives inbound booking events from OTAs via channel managers (Staah, Wubook, etc.)

Authentication: X-API-Key header must match WEBHOOK_API_KEY in .env / Settings table.

All calls are logged to webhook_logs table for audit and debugging.
"""

import os
import hmac
import hashlib
import logging
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)
from app.models import db, Guest, Reservation, RoomType, Room, Payment, PaymentMode, WebhookLog, Settings, AuditLog


def _webhook_resolve_rate(room_type_id, arrival, departure):
    """Resolve rate via central resolver for webhook fallback paths."""
    from app.rates import resolve_rate_for_reservation
    return resolve_rate_for_reservation(room_type_id, arrival, departure).rate_per_night

webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Return the webhook API key (env var takes priority over DB setting)."""
    key = os.getenv('WEBHOOK_API_KEY')
    if not key:
        s = Settings.query.filter_by(key='webhook_api_key').first()
        key = s.value if s else None
    return key or ''


def _verify_hmac_signature(body: bytes, key: str) -> bool:
    """Verify optional HMAC-SHA256 signature in X-Signature-SHA256 header.
    Format expected: 'sha256=<hex_digest>' (same as GitHub/Shopify webhooks).
    Returns True if header absent (optional) or if signature matches.
    """
    sig_header = request.headers.get('X-Signature-SHA256', '')
    if not sig_header:
        return True  # HMAC is optional; only X-API-Key is required
    expected = 'sha256=' + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig_header, expected)


def require_api_key(f):
    """Decorator — validates X-API-Key header and optional HMAC-SHA256 signature."""
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get('X-API-Key', '')
        expected = _get_api_key()
        if not expected:
            return jsonify({'error': 'Webhook API key not configured on server'}), 503
        if not hmac.compare_digest(provided.encode(), expected.encode()):
            return jsonify({'error': 'Unauthorized'}), 401
        # If channel manager sends HMAC signature, verify it too
        if not _verify_hmac_signature(request.get_data(), expected):
            return jsonify({'error': 'Invalid HMAC signature'}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(source, event_type, payload, status='received', error=None, reservation_id=None):
    try:
        log = WebhookLog(
            source=source,
            event_type=event_type,
            raw_payload=payload,
            status=status,
            error_message=error,
            reservation_id=reservation_id,
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.flush()
        return log
    except Exception:
        return None


def _generate_ref():
    import secrets, string
    alphabet = string.ascii_uppercase + string.digits
    chars = ''.join(secrets.choice(alphabet) for _ in range(6))
    return 'OTA-' + chars


# ---------------------------------------------------------------------------
# Generic Booking Webhook (JSON)
# Works with any channel manager configured to POST JSON bookings.
#
# Expected payload:
# {
#   "event": "new_booking" | "cancel_booking" | "modify_booking",
#   "source": "staah" | "wubook" | "booking.com" | ...,
#   "ota_booking_id": "ABC123",
#   "room_type_name": "Standard",
#   "arrival_date": "2026-03-15",
#   "departure_date": "2026-03-17",
#   "adults": 2,
#   "children": 0,
#   "rate_per_night": 1500.00,
#   "guest": {
#     "name": "John Doe",
#     "phone": "9999999999",
#     "email": "john@example.com"
#   },
#   "special_requests": "..."
# }
# ---------------------------------------------------------------------------

@webhook_bp.route('/booking', methods=['POST'])
@require_api_key
def handle_booking():
    payload = request.get_json(silent=True) or {}
    event = payload.get('event', 'new_booking')
    source = payload.get('source', 'ota')

    log = _log(source, event, payload)

    if event == 'new_booking':
        return _handle_new_booking(payload, log)
    elif event == 'cancel_booking':
        return _handle_cancel(payload, log)
    elif event == 'modify_booking':
        return _handle_modify(payload, log)
    else:
        if log:
            log.status = 'failed'
            log.error_message = f'Unknown event type: {event}'
            db.session.commit()
        return jsonify({'error': f'Unknown event: {event}'}), 400


def _handle_new_booking(payload, log):
    try:
        ota_id = payload.get('ota_booking_id', '')
        room_type_name = payload.get('room_type_name', '')
        arrival = datetime.strptime(payload['arrival_date'], '%Y-%m-%d').date()
        departure = datetime.strptime(payload['departure_date'], '%Y-%m-%d').date()
        adults = int(payload.get('adults', 1))
        children = int(payload.get('children', 0))
        rate = float(payload.get('rate_per_night', 0))
        special_requests = payload.get('special_requests', '')

        guest_data = payload.get('guest', {})
        g_first = guest_data.get('first_name', '').strip()
        g_last = guest_data.get('last_name', '').strip()
        # Fallback: split legacy single 'name' field
        if not g_first:
            _raw = guest_data.get('name', 'OTA Guest').strip()
            _parts = _raw.split(None, 1) if _raw else ['OTA Guest']
            g_first = _parts[0]
            g_last = _parts[1] if len(_parts) > 1 else g_last
        g_name = f'{g_first} {g_last}'.strip()
        g_phone = guest_data.get('phone', f'ota_{ota_id}')
        g_email = guest_data.get('email', '')

        # Prevent duplicate OTA bookings
        existing = Reservation.query.filter_by(ota_booking_id=ota_id).first() if ota_id else None
        if existing:
            if log:
                log.status = 'skipped'
                log.reservation_id = existing.id
                db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Booking already exists',
                'reservation_id': existing.id,
                'booking_reference': existing.booking_reference,
            })

        # Find room type
        room_type = RoomType.query.filter(
            RoomType.name.ilike(f'%{room_type_name}%')
        ).first()
        if not room_type:
            room_type = RoomType.query.first()  # fallback to first available

        if not room_type:
            raise ValueError('No room types configured')

        # Find or create guest — always store structured names
        guest = Guest.query.filter_by(phone=g_phone).first()
        if not guest:
            guest = Guest(
                name=g_name, first_name=g_first, last_name=g_last,
                phone=g_phone, email=g_email or None,
            )
            db.session.add(guest)
            db.session.flush()
        else:
            # Backfill structured names if missing
            if not guest.first_name:
                Guest.set_name(guest, g_first, g_last)

        # Generate unique booking reference
        ref = _generate_ref()
        while Reservation.query.filter_by(booking_reference=ref).first():
            ref = _generate_ref()

        # OTA webhook bookings default to paid_at_ota unless payload says otherwise
        _payment_mode = (payload.get('payment_mode') or '').strip().lower()
        _pay_at_hotel = _payment_mode in ('pay_at_hotel', 'pah', 'payathotel', 'direct')
        _ota_pmt_status = 'pay_at_hotel' if _pay_at_hotel else 'paid_at_ota'

        # Authoritative OTA channel name. Channel managers send this
        # under several different keys; accept the most common ones in
        # priority order. None of them is the legacy ``source`` field
        # at line 130 — that one carries the event source ('ota') for
        # logging, not the channel.
        _ota_channel = (
            payload.get('ota_channel')
            or payload.get('channel')
            or payload.get('ota_source')
            or ''
        ).strip() or None

        reservation = Reservation(
            booking_reference=ref,
            guest_id=guest.id,
            room_type_id=room_type.id,
            arrival_date=arrival,
            departure_date=departure,
            adults=adults,
            children=children,
            rate_per_night=rate if rate > 0 else _webhook_resolve_rate(
                room_type.id, arrival, departure),
            advance_payment=0,
            status='Confirmed',
            source='OTA',
            ota_channel=_ota_channel,
            ota_payment_status=_ota_pmt_status,
            ota_booking_id=ota_id,
            special_requests=special_requests,
        )

        # Webhook didn't carry a channel field — fall back to inference
        # from the booking ID prefix so the row still gets a stored value
        # at creation time. (Inference will return 'Other OTA' if it
        # can't pattern-match — that's fine for legacy/unknown sources.)
        if not reservation.ota_channel:
            from app.ota import _infer_ota_source
            reservation.ota_channel = _infer_ota_source(reservation)
        db.session.add(reservation)
        db.session.flush()

        if log:
            log.status = 'processed'
            log.reservation_id = reservation.id

        db.session.commit()

        # Front-desk WhatsApp alert for new OTA booking (non-blocking)
        try:
            from app.notifications import notify_ota_booking
            notify_ota_booking(reservation, app=current_app._get_current_object())
        except Exception:
            pass

        return jsonify({
            'success': True,
            'reservation_id': reservation.id,
            'booking_reference': ref,
            'message': f'Booking created for {g_name}',
        }), 201

    except KeyError as e:
        db.session.rollback()
        if log:
            log.status = 'failed'
            log.error_message = f'Missing field: {e}'
            db.session.commit()
        return jsonify({'error': f'Missing required field: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        if log:
            log.status = 'failed'
            log.error_message = str(e)
            db.session.commit()
        logger.error('Webhook handler error: %s', e, exc_info=True)
        return jsonify({'error': 'Internal processing error'}), 500


def _handle_cancel(payload, log):
    try:
        ota_id = payload.get('ota_booking_id', '')
        ref = payload.get('booking_reference', '')

        reservation = None
        if ota_id:
            reservation = Reservation.query.filter_by(ota_booking_id=ota_id).first()
        if not reservation and ref:
            reservation = Reservation.query.filter_by(booking_reference=ref).first()

        if not reservation:
            if log:
                log.status = 'failed'
                log.error_message = 'Booking not found'
                db.session.commit()
            return jsonify({'error': 'Booking not found'}), 404

        if reservation.status in ('CheckedIn', 'CheckedOut'):
            if log:
                log.status = 'failed'
                log.error_message = f'Cannot cancel — status is {reservation.status}'
                db.session.commit()
            return jsonify({'error': f'Cannot cancel booking in status: {reservation.status}'}), 409

        reservation.status = 'Cancelled'
        if log:
            log.status = 'processed'
            log.reservation_id = reservation.id
        db.session.commit()

        # Guest cancellation WhatsApp + email (non-blocking)
        try:
            from app.notifications import notify_booking_cancelled
            notify_booking_cancelled(reservation, app=current_app._get_current_object())
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Booking cancelled'})

    except Exception as e:
        db.session.rollback()
        if log:
            log.status = 'failed'
            log.error_message = str(e)
            db.session.commit()
        logger.error('Webhook handler error: %s', e, exc_info=True)
        return jsonify({'error': 'Internal processing error'}), 500


def _write_audit(entity_type, entity_id, action, before_state, after_state):
    """Write an entry to the AuditLog table. Never raises -- audit failures are non-fatal."""
    try:
        log_entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
            staff_user_id=0,  # webhook / system action
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(log_entry)
        db.session.flush()
    except Exception as _exc:
        logger.error(
            'AuditLog write FAILED | entity=%s id=%s action=%s | %s',
            entity_type, entity_id, action, _exc, exc_info=True,
        )


def _handle_modify(payload, log):
    try:
        ota_id = payload.get('ota_booking_id', '')
        ref = payload.get('booking_reference', '')

        reservation = None
        if ota_id:
            reservation = Reservation.query.filter_by(ota_booking_id=ota_id).first()
        if not reservation and ref:
            reservation = Reservation.query.filter_by(booking_reference=ref).first()

        if not reservation:
            if log:
                log.status = 'failed'
                log.error_message = 'Booking not found'
                db.session.commit()
            return jsonify({'error': 'Booking not found'}), 404

        if reservation.status in ('CheckedIn', 'CheckedOut'):
            if log:
                log.status = 'failed'
                log.error_message = f'Cannot modify — reservation is {reservation.status}'
                db.session.commit()
            return jsonify({
                'error': f'Cannot modify a {reservation.status} reservation. Contact front desk.'
            }), 409

        # --- Parse incoming values, falling back to existing reservation data ---
        new_arrival = (
            datetime.strptime(payload['arrival_date'], '%Y-%m-%d').date()
            if 'arrival_date' in payload else reservation.arrival_date
        )
        new_departure = (
            datetime.strptime(payload['departure_date'], '%Y-%m-%d').date()
            if 'departure_date' in payload else reservation.departure_date
        )
        new_adults = int(payload['adults']) if 'adults' in payload else reservation.adults
        new_rate = float(payload['rate_per_night']) if 'rate_per_night' in payload else reservation.rate_per_night

        # --- Business validations ---
        errors = []

        if 'arrival_date' in payload and new_arrival < date.today():
            errors.append('arrival_date cannot be in the past')

        if 'departure_date' in payload and new_departure <= new_arrival:
            errors.append('departure_date must be after arrival_date')

        if 'rate_per_night' in payload and new_rate < 0:
            errors.append('rate_per_night must be >= 0')

        if 'adults' in payload and new_adults < 1:
            errors.append('adults must be >= 1')

        if errors:
            error_msg = '; '.join(errors)
            if log:
                log.status = 'failed'
                log.error_message = f'Validation failed: {error_msg}'
                db.session.commit()
            return jsonify({'error': error_msg}), 400

        # --- Capture before-state for audit ---
        before_state = {
            'arrival_date': str(reservation.arrival_date),
            'departure_date': str(reservation.departure_date),
            'adults': reservation.adults,
            'children': reservation.children,
            'rate_per_night': float(reservation.rate_per_night),
            'special_requests': reservation.special_requests,
        }

        # --- Apply changes ---
        if 'arrival_date' in payload:
            reservation.arrival_date = new_arrival
        if 'departure_date' in payload:
            reservation.departure_date = new_departure
        if 'adults' in payload:
            reservation.adults = new_adults
        if 'children' in payload:
            reservation.children = int(payload['children'])
        if 'rate_per_night' in payload:
            reservation.rate_per_night = new_rate
        if 'special_requests' in payload:
            reservation.special_requests = payload['special_requests']

        # --- Capture after-state and write audit log ---
        after_state = {
            'arrival_date': str(reservation.arrival_date),
            'departure_date': str(reservation.departure_date),
            'adults': reservation.adults,
            'children': reservation.children,
            'rate_per_night': float(reservation.rate_per_night),
            'special_requests': reservation.special_requests,
        }
        _write_audit('Reservation', reservation.id, 'webhook_modify', before_state, after_state)

        if log:
            log.status = 'processed'
            log.reservation_id = reservation.id
        db.session.commit()

        return jsonify({'success': True, 'message': 'Booking modified'})

    except Exception as e:
        db.session.rollback()
        if log:
            log.status = 'failed'
            log.error_message = str(e)
            db.session.commit()
        logger.error('Webhook handler error: %s', e, exc_info=True)
        return jsonify({'error': 'Internal processing error'}), 500


# ---------------------------------------------------------------------------
# Webhook log viewer (staff use — requires login via main app)
# ---------------------------------------------------------------------------

@webhook_bp.route('/logs')
def webhook_logs():
    """View recent webhook logs — protected by session (redirects to login if not logged in)."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))
    if not current_user.has_role('Admin', 'Manager'):
        from flask import abort
        abort(403)
    logs = WebhookLog.query.order_by(WebhookLog.received_at.desc()).limit(100).all()
    from flask import render_template
    return render_template('webhook/logs.html', logs=logs)


# ---------------------------------------------------------------------------
# Health check (public — for channel manager connectivity test)
# ---------------------------------------------------------------------------

@webhook_bp.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'service': 'Sukoon PMS Webhook', 'timestamp': datetime.utcnow().isoformat()})
