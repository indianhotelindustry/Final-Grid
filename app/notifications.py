"""
Phase 3 — Notification Service
================================
Sends WhatsApp messages (via UltraMSG) and emails (via SMTP) for:
  - booking_confirmed   → guest gets WhatsApp + email; front desk gets WhatsApp alert
  - ota_booking         → front desk WhatsApp alert only (guest is notified by OTA)
  - booking_cancelled   → guest gets WhatsApp + email
  - booking_modified    → guest gets WhatsApp + email
  - checkin_welcome     → guest gets WhatsApp welcome
  - checkout_thanks     → guest gets WhatsApp thank-you

All notifications are fire-and-forget (background thread) so the booking
flow is NEVER blocked by a notification failure.

Configuration (set in .env):
  WHATSAPP_PROVIDER    = ultramsg          (only supported provider right now)
  ULTRAMSG_INSTANCE    = instance12345
  ULTRAMSG_TOKEN       = your_token_here
  FRONTDESK_WHATSAPP   = 919876543210      (number to alert for new bookings)
  SMTP_HOST            = smtp.gmail.com
  SMTP_PORT            = 587
  SMTP_USER            = you@gmail.com
  SMTP_PASS            = app_password_here
  SMTP_FROM            = Sukoon City View <you@gmail.com>
  HOTEL_NAME           = Sukoon City View
  HOTEL_PHONE          = 011-XXXXXXXX
"""

import os
import smtplib
import threading
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import current_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core send functions
# ---------------------------------------------------------------------------

def _send_whatsapp(phone: str, message: str, app=None) -> tuple[bool, str]:
    """
    Send a WhatsApp message via UltraMSG REST API.
    Returns (success, error_message).
    """
    import urllib.request
    import urllib.parse
    import json

    instance = os.getenv('ULTRAMSG_INSTANCE', '')
    token = os.getenv('ULTRAMSG_TOKEN', '')

    if not instance or not token:
        return False, 'ULTRAMSG_INSTANCE or ULTRAMSG_TOKEN not configured'

    # Normalise phone: strip spaces/dashes, ensure country code prefix
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('0'):
        phone = '91' + phone[1:]   # India: 0XXXXXXXXXX → 91XXXXXXXXXX
    if not phone.startswith('+'):
        phone = '+' + phone

    url = f'https://api.ultramsg.com/{instance}/messages/chat'
    payload = urllib.parse.urlencode({
        'token': token,
        'to': phone,
        'body': message,
        'priority': 1,
    }).encode()

    try:
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            if body.get('sent') == 'true' or body.get('id'):
                return True, ''
            return False, body.get('error', str(body))
    except Exception as e:
        return False, str(e)


def _send_email(to: str, subject: str, html_body: str) -> tuple[bool, str]:
    """
    Send an HTML email via SMTP.
    Returns (success, error_message).
    """
    host = os.getenv('SMTP_HOST', '')
    port = int(os.getenv('SMTP_PORT', 587))
    user = os.getenv('SMTP_USER', '')
    password = os.getenv('SMTP_PASS', '')
    from_addr = os.getenv('SMTP_FROM', user)
    hotel_name = os.getenv('HOTEL_NAME', 'Hotel')

    if not host or not user or not password:
        return False, 'SMTP not configured'

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to], msg.as_string())
        return True, ''
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Notification logger (writes to DB inside Flask app context)
# ---------------------------------------------------------------------------

def _log_notification(app, channel, recipient, message_type, reservation_id, status, error=''):
    """Persist a NotificationLog row. Must run inside the passed app context."""
    try:
        with app.app_context():
            from app.models import db, NotificationLog
            log = NotificationLog(
                channel=channel,
                recipient=recipient,
                message_type=message_type,
                reservation_id=reservation_id,
                status=status,
                error_message=error or None,
            )
            db.session.add(log)
            db.session.commit()
    except Exception as e:
        logger.error('Failed to write NotificationLog: %s', e)


# ---------------------------------------------------------------------------
# Background dispatcher — runs in a daemon thread so Flask isn't blocked
# ---------------------------------------------------------------------------

def _enqueue(app, channel, recipient, subject, body, msg_type, res_id, error):
    """Persist a failed notification to the retry queue."""
    try:
        with app.app_context():
            from app.models import db, NotificationQueue
            from datetime import datetime, timedelta
            item = NotificationQueue(
                channel=channel,
                recipient=recipient,
                subject=subject,
                body=body,
                message_type=msg_type,
                reservation_id=res_id,
                status='pending',
                attempts=1,
                next_retry_at=datetime.utcnow() + timedelta(minutes=5),
                error_message=error,
            )
            db.session.add(item)
            db.session.commit()
            logger.info('Queued %s notification to %s for retry', channel, recipient)
    except Exception as e:
        logger.error('Failed to enqueue notification: %s', e)


def _dispatch(app, jobs: list[dict]):
    """
    jobs = list of dicts:
      { 'channel': 'whatsapp'|'email', 'to': str, 'subject': str (email only),
        'message': str, 'message_type': str, 'reservation_id': int|None }
    Sends immediately; on failure queues the notification for automatic retry.
    """
    for job in jobs:
        channel = job['channel']
        to = job['to']
        msg_type = job.get('message_type', 'notification')
        res_id = job.get('reservation_id')

        if not to:
            continue

        if channel == 'whatsapp':
            ok, err = _send_whatsapp(to, job['message'])
        elif channel == 'email':
            ok, err = _send_email(to, job['subject'], job['message'])
        else:
            continue

        status = 'sent' if ok else 'failed'
        if not ok:
            logger.warning('Notification failed [%s → %s] %s: %s', channel, to, msg_type, err)
            _enqueue(app, channel, to, job.get('subject', ''),
                     job['message'], msg_type, res_id, err)

        _log_notification(app, channel, to, msg_type, res_id, status, err if not ok else '')


def _fire(app, jobs: list[dict]):
    """Start a daemon thread for the notification jobs."""
    t = threading.Thread(target=_dispatch, args=(app, jobs), daemon=True)
    t.start()


def flush_notification_queue(app):
    """Retry all pending queued notifications. Called by APScheduler every 5 min."""
    with app.app_context():
        from app.models import db, NotificationQueue
        from datetime import datetime, timedelta

        pending = (NotificationQueue.query
                   .filter_by(status='pending')
                   .filter(NotificationQueue.next_retry_at <= datetime.utcnow())
                   .filter(NotificationQueue.attempts < NotificationQueue.max_attempts)
                   .order_by(NotificationQueue.created_at)
                   .limit(50)
                   .all())

        if not pending:
            return

        sent_count = 0
        for item in pending:
            if item.channel == 'whatsapp':
                ok, err = _send_whatsapp(item.recipient, item.body)
            elif item.channel == 'email':
                ok, err = _send_email(item.recipient, item.subject, item.body)
            else:
                item.status = 'failed'
                db.session.commit()
                continue

            item.attempts += 1
            if ok:
                item.status = 'sent'
                item.error_message = None
                sent_count += 1
                _log_notification(app, item.channel, item.recipient,
                                  item.message_type, item.reservation_id, 'sent')
            else:
                backoff_minutes = min(5 * (2 ** item.attempts), 1440)  # max 24h
                item.next_retry_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
                item.error_message = err
                if item.attempts >= item.max_attempts:
                    item.status = 'failed'
                    _log_notification(app, item.channel, item.recipient,
                                      item.message_type, item.reservation_id,
                                      'failed', f'Max retries exceeded: {err}')

            db.session.commit()

        if sent_count:
            logger.info('Notification queue flush: %d/%d sent', sent_count, len(pending))


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _hotel_name():
    return os.getenv('HOTEL_NAME', 'Hotel')

def _hotel_phone():
    return os.getenv('HOTEL_PHONE', 'Front Desk')

def _frontdesk_wa():
    return os.getenv('FRONTDESK_WHATSAPP', '')


def _fmt_date(d):
    if hasattr(d, 'strftime'):
        return d.strftime('%d %b %Y')
    return str(d)


def _booking_confirmed_wa(r):
    nights = (r.departure_date - r.arrival_date).days
    total = float(r.rate_per_night) * nights
    return (
        f"✅ *Booking Confirmed — {_hotel_name()}*\n\n"
        f"Dear {r.guest.name},\n\n"
        f"Your booking is confirmed! Details below:\n\n"
        f"📋 *Ref:* {r.booking_reference or r.id}\n"
        f"🛏️ *Room:* {r.room_type.name}\n"
        f"📅 *Check-in:* {_fmt_date(r.arrival_date)}\n"
        f"📅 *Check-out:* {_fmt_date(r.departure_date)}\n"
        f"🌙 *Nights:* {nights}\n"
        f"👤 *Guests:* {r.adults} adult(s)"
        + (f", {r.children} child(ren)" if r.children else "") + "\n"
        f"💰 *Total:* ₹{total:,.0f} (pay at hotel)\n\n"
        f"Check-in from 12:00 PM. Please carry a valid photo ID.\n\n"
        f"For queries: {_hotel_phone()}\n"
        f"We look forward to welcoming you! 🙏"
    )


def _booking_confirmed_email(r):
    nights = (r.departure_date - r.arrival_date).days
    total = float(r.rate_per_night) * nights
    ref = r.booking_reference or str(r.id)
    hn = _hotel_name()
    return f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">
<div style="background:#0d6efd;color:#fff;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
  <h2 style="margin:0;">✅ Booking Confirmed</h2>
  <p style="margin:4px 0 0;">{hn}</p>
</div>
<div style="border:1px solid #dee2e6;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
  <p>Dear <strong>{r.guest.name}</strong>,</p>
  <p>Your booking at <strong>{hn}</strong> is confirmed. Here are your details:</p>
  <table style="width:100%;border-collapse:collapse;">
    <tr style="background:#f8f9fa;"><td style="padding:8px;font-weight:bold;">Booking Reference</td>
        <td style="padding:8px;font-size:1.2em;font-weight:bold;color:#0d6efd;">{ref}</td></tr>
    <tr><td style="padding:8px;font-weight:bold;">Room Type</td><td style="padding:8px;">{r.room_type.name}</td></tr>
    <tr style="background:#f8f9fa;"><td style="padding:8px;font-weight:bold;">Check-in</td>
        <td style="padding:8px;color:#198754;font-weight:bold;">{_fmt_date(r.arrival_date)} (from 12:00 PM)</td></tr>
    <tr><td style="padding:8px;font-weight:bold;">Check-out</td><td style="padding:8px;">{_fmt_date(r.departure_date)}</td></tr>
    <tr style="background:#f8f9fa;"><td style="padding:8px;font-weight:bold;">Nights</td><td style="padding:8px;">{nights}</td></tr>
    <tr><td style="padding:8px;font-weight:bold;">Guests</td>
        <td style="padding:8px;">{r.adults} adult(s){f', {r.children} child(ren)' if r.children else ''}</td></tr>
    <tr style="background:#f8f9fa;"><td style="padding:8px;font-weight:bold;">Total Amount</td>
        <td style="padding:8px;font-size:1.1em;font-weight:bold;color:#198754;">₹{total:,.0f}</td></tr>
    <tr><td style="padding:8px;font-weight:bold;">Payment</td><td style="padding:8px;">At hotel (Cash / UPI / Card)</td></tr>
  </table>
  {'<p style="color:#666;"><em>Special requests: ' + r.special_requests + '</em></p>' if r.special_requests else ''}
  <div style="background:#fff3cd;padding:12px;border-radius:6px;margin:16px 0;">
    <strong>📋 Important:</strong> Please present this reference number (<strong>{ref}</strong>) at the front desk.
    Carry a valid government-issued photo ID.
  </div>
  <p>For queries, call us at <strong>{_hotel_phone()}</strong></p>
  <p style="color:#888;font-size:0.85em;">This is an automated email. {hn}</p>
</div>
</body></html>"""


def _frontdesk_new_booking_wa(r, source='Website'):
    nights = (r.departure_date - r.arrival_date).days
    return (
        f"🔔 *New Booking — {source}*\n\n"
        f"📋 Ref: {r.booking_reference or r.id}\n"
        f"👤 Guest: {r.guest.name} | 📞 {r.guest.phone}\n"
        f"🛏️ Room: {r.room_type.name}\n"
        f"📅 {_fmt_date(r.arrival_date)} → {_fmt_date(r.departure_date)} ({nights}N)\n"
        f"💰 ₹{float(r.rate_per_night):,.0f}/night"
    )


def _cancellation_wa(r):
    return (
        f"❌ *Booking Cancelled — {_hotel_name()}*\n\n"
        f"Dear {r.guest.name},\n\n"
        f"Your booking has been cancelled.\n\n"
        f"📋 Ref: {r.booking_reference or r.id}\n"
        f"🛏️ Room: {r.room_type.name}\n"
        f"📅 {_fmt_date(r.arrival_date)} → {_fmt_date(r.departure_date)}\n\n"
        f"If this was a mistake or to rebook, please call {_hotel_phone()}."
    )


def _cancellation_email(r):
    hn = _hotel_name()
    return f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">
<div style="background:#dc3545;color:#fff;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
  <h2 style="margin:0;">❌ Booking Cancelled</h2>
  <p style="margin:4px 0 0;">{hn}</p>
</div>
<div style="border:1px solid #dee2e6;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
  <p>Dear <strong>{r.guest.name}</strong>,</p>
  <p>Your booking at <strong>{hn}</strong> has been cancelled.</p>
  <p><strong>Booking Reference:</strong> {r.booking_reference or r.id}<br>
     <strong>Room:</strong> {r.room_type.name}<br>
     <strong>Dates:</strong> {_fmt_date(r.arrival_date)} → {_fmt_date(r.departure_date)}</p>
  <p>If this was a mistake, please call <strong>{_hotel_phone()}</strong> to rebook.</p>
  <p style="color:#888;font-size:0.85em;">This is an automated email. {hn}</p>
</div>
</body></html>"""


def _modification_wa(r):
    nights = (r.departure_date - r.arrival_date).days
    return (
        f"✏️ *Booking Modified — {_hotel_name()}*\n\n"
        f"Dear {r.guest.name},\n\n"
        f"Your booking has been updated:\n\n"
        f"📋 Ref: {r.booking_reference or r.id}\n"
        f"🛏️ Room: {r.room_type.name}\n"
        f"📅 New Check-in: {_fmt_date(r.arrival_date)}\n"
        f"📅 New Check-out: {_fmt_date(r.departure_date)} ({nights}N)\n\n"
        f"For queries: {_hotel_phone()}"
    )


def _checkin_welcome_wa(r):
    return (
        f"🏨 *Welcome to {_hotel_name()}!*\n\n"
        f"Dear {r.guest.name},\n\n"
        f"Your check-in is complete. We hope you have a wonderful stay!\n\n"
        f"🛏️ Room: {r.room.room_number if r.room else r.room_type.name}\n"
        f"📅 Check-out: {_fmt_date(r.departure_date)}\n\n"
        f"If you need anything, please call the front desk: {_hotel_phone()} 🙏"
    )


def _checkout_thanks_wa(r, total_paid):
    return (
        f"🙏 *Thank You — {_hotel_name()}*\n\n"
        f"Dear {r.guest.name},\n\n"
        f"Thank you for staying with us! We hope to see you again soon.\n\n"
        f"📋 Ref: {r.booking_reference or r.id}\n"
        f"💰 Total Paid: ₹{total_paid:,.0f}\n\n"
        f"Please share your feedback — it means a lot to us!\n"
        f"We look forward to welcoming you back. 😊"
    )


# ---------------------------------------------------------------------------
# Public API — call these from routes / booking / webhook
# ---------------------------------------------------------------------------

def notify_booking_confirmed(reservation, app=None):
    """
    Trigger: new booking from website booking engine.
    Guest: WhatsApp + Email
    Front desk: WhatsApp alert
    """
    if app is None:
        app = current_app._get_current_object()

    jobs = []
    r = reservation
    guest_phone = r.guest.phone if r.guest else ''
    guest_email = r.guest.email if r.guest else ''
    fd_wa = _frontdesk_wa()

    if guest_phone:
        jobs.append({'channel': 'whatsapp', 'to': guest_phone,
                     'message': _booking_confirmed_wa(r),
                     'message_type': 'booking_confirmed', 'reservation_id': r.id})

    if guest_email:
        jobs.append({'channel': 'email', 'to': guest_email,
                     'subject': f'Booking Confirmed — {r.booking_reference or r.id} | {_hotel_name()}',
                     'message': _booking_confirmed_email(r),
                     'message_type': 'booking_confirmed', 'reservation_id': r.id})

    if fd_wa:
        jobs.append({'channel': 'whatsapp', 'to': fd_wa,
                     'message': _frontdesk_new_booking_wa(r, source='Website'),
                     'message_type': 'frontdesk_alert', 'reservation_id': r.id})

    _fire(app, jobs)


def notify_ota_booking(reservation, app=None):
    """
    Trigger: new booking from OTA/channel manager webhook.
    Guest is notified by OTA — only front desk alert here.
    """
    if app is None:
        app = current_app._get_current_object()

    fd_wa = _frontdesk_wa()
    if not fd_wa:
        return

    jobs = [{'channel': 'whatsapp', 'to': fd_wa,
              'message': _frontdesk_new_booking_wa(reservation, source='OTA'),
              'message_type': 'frontdesk_alert', 'reservation_id': reservation.id}]
    _fire(app, jobs)


def notify_booking_cancelled(reservation, app=None):
    """Trigger: booking cancelled (from staff UI or OTA webhook)."""
    if app is None:
        app = current_app._get_current_object()

    jobs = []
    r = reservation
    guest_phone = r.guest.phone if r.guest else ''
    guest_email = r.guest.email if r.guest else ''

    # Don't notify blocked/group dummy guests
    if guest_phone and not guest_phone.startswith(('bulk', 'blocked')):
        jobs.append({'channel': 'whatsapp', 'to': guest_phone,
                     'message': _cancellation_wa(r),
                     'message_type': 'booking_cancelled', 'reservation_id': r.id})
        if guest_email:
            jobs.append({'channel': 'email', 'to': guest_email,
                         'subject': f'Booking Cancelled — {r.booking_reference or r.id} | {_hotel_name()}',
                         'message': _cancellation_email(r),
                         'message_type': 'booking_cancelled', 'reservation_id': r.id})

    _fire(app, jobs)


def notify_booking_modified(reservation, app=None):
    """Trigger: booking dates/room changed."""
    if app is None:
        app = current_app._get_current_object()

    jobs = []
    r = reservation
    guest_phone = r.guest.phone if r.guest else ''

    if guest_phone and not guest_phone.startswith(('bulk', 'blocked')):
        jobs.append({'channel': 'whatsapp', 'to': guest_phone,
                     'message': _modification_wa(r),
                     'message_type': 'booking_modified', 'reservation_id': r.id})
        if r.guest.email:
            from email.mime.text import MIMEText
            jobs.append({'channel': 'email', 'to': r.guest.email,
                         'subject': f'Booking Updated — {r.booking_reference or r.id} | {_hotel_name()}',
                         'message': _modification_wa(r).replace('\n', '<br>'),
                         'message_type': 'booking_modified', 'reservation_id': r.id})

    _fire(app, jobs)


def notify_checkin_welcome(reservation, app=None):
    """Trigger: guest checked in at front desk."""
    if app is None:
        app = current_app._get_current_object()

    r = reservation
    guest_phone = r.guest.phone if r.guest else ''
    if guest_phone and not guest_phone.startswith(('bulk', 'blocked')):
        _fire(app, [{'channel': 'whatsapp', 'to': guest_phone,
                     'message': _checkin_welcome_wa(r),
                     'message_type': 'checkin_welcome', 'reservation_id': r.id}])


def notify_checkout_thanks(reservation, total_paid: float, app=None):
    """Trigger: guest checked out."""
    if app is None:
        app = current_app._get_current_object()

    r = reservation
    guest_phone = r.guest.phone if r.guest else ''
    if guest_phone and not guest_phone.startswith(('bulk', 'blocked')):
        _fire(app, [{'channel': 'whatsapp', 'to': guest_phone,
                     'message': _checkout_thanks_wa(r, total_paid),
                     'message_type': 'checkout_thanks', 'reservation_id': r.id}])
