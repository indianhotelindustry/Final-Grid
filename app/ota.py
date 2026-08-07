"""
OTA Channel Integration  (/ota/*)
===================================
Provides a staff-facing dashboard to:
  - View OTA booking stats (source breakdown, revenue, no-shows)
  - Manage webhook API key and test connectivity
  - Manually create / cancel OTA reservations (for phone-in OTA bookings)
  - View and retry failed webhook calls
  - Configure per-source settings (commission %, default room type)

Routes:
  GET  /ota/                          — Dashboard
  GET  /ota/settings                  — Webhook & source settings
  POST /ota/settings                  — Save settings
  POST /ota/test-ping                 — Test webhook endpoint reachability
  GET  /ota/bookings                  — OTA reservation list with filters
  POST /ota/bookings/manual           — Manually create OTA reservation
  POST /ota/bookings/<id>/cancel      — Cancel OTA reservation
  POST /ota/webhook/retry/<log_id>    — Retry a failed webhook log entry
  GET  /ota/webhook/logs              — Alias for webhook logs (paginated)
"""

import logging
import secrets
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import func

from sqlalchemy.orm import joinedload
from app.models import (Guest, Payment, Reservation, RoomType, Settings,
                        WebhookLog, db)

logger = logging.getLogger(__name__)

ota_bp = Blueprint('ota', __name__, url_prefix='/ota')


def _ota_resolve_rate(room_type_id, arrival, departure):
    """Resolve rate via central resolver for OTA fallback paths."""
    from app.rates import resolve_rate_for_reservation
    return resolve_rate_for_reservation(room_type_id, arrival, departure).rate_per_night


OTA_SOURCES = ['Booking.com', 'MakeMyTrip', 'Goibibo', 'Agoda',
               'Expedia', 'Airbnb', 'Yatra', 'EaseMyTrip', 'Other OTA']


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def _manager_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role not in ('Admin', 'Manager'):
            flash('Manager or Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated



# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _get_setting(key: str, default: str = '') -> str:
    row = Settings.query.filter_by(key=key).first()
    return (row.value or default) if row else default


def _set_setting(key: str, value: str, desc: str = '') -> None:
    row = Settings.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Settings(key=key, value=value, description=desc))


# ===========================================================================
# OTA Revenue Intelligence — Phase A (S1: KPI strip)
# ===========================================================================
# Append-only enhancement. Gated by app.config['OTA_INTELLIGENCE_ENABLED'].
# Existing dashboard rendering is byte-identical when the flag is OFF.
#
# Design rules locked in for Phase A:
#   - Existing helpers ONLY. No new joins. No new abstractions.
#   - Each aggregate fails-safe to a sentinel (0 / 0.0) on any DB error so
#     the dashboard never breaks because of intelligence.
#   - Per-aggregate + total timing is logged at INFO; auto-promotes to
#     WARNING above thresholds so slow paths surface in log aggregation.
#   - 60-second module-level TTL cache keyed on business_date — single
#     Gunicorn worker, so a dict is the right size of solution.
# ---------------------------------------------------------------------------

# Slow-path thresholds (ms). Tuned for receptionist-perceived latency.
_OTA_INTEL_SLOW_MS_TOTAL = 200
_OTA_INTEL_SLOW_MS_AGG   = 80

# Cache TTL — short enough that staff see fresh numbers on most refreshes,
# long enough to absorb rapid F5 hammering during a busy front-desk minute.
_OTA_INTEL_CACHE_TTL_S = 60

# Module-level cache. Format: {(label, business_date_iso): (expires_at_unix, value)}.
# Bounded in practice to one entry per business_date; resets on process restart.
_INTEL_CACHE: dict = {}


def _intel_cache_get(key):
    entry = _INTEL_CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.time() >= expires_at:
        # Expired — drop and miss.
        _INTEL_CACHE.pop(key, None)
        return None
    return value


def _intel_cache_set(key, value, ttl_s=_OTA_INTEL_CACHE_TTL_S):
    _INTEL_CACHE[key] = (time.time() + ttl_s, value)


@contextmanager
def _timed(label, sink):
    """Lightweight per-aggregate timer. Adds ms into *sink[label]*.
    Overhead is sub-microsecond; safe to wrap every aggregate."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        sink[label] = (time.perf_counter() - t0) * 1000.0


# ── Aggregates ────────────────────────────────────────────────────────────
# Each helper is a single-table query that mirrors an existing canonical
# pattern. The reference is documented in a one-line comment at the top of
# each. No joins, no abstractions, no caching at this level — the
# orchestrator handles caching once for the whole context.

def _ota_revenue_today(business_date) -> float:
    """OTA Revenue Today — room revenue only.

    Mirrors the canonical accrual pattern in
    ``app.services.compute_live_today_charges`` (services.py:376) — sum of
    ``rate_per_night`` for in-house reservations on *business_date* — and
    narrows it to ``source='OTA'``. Extras are intentionally excluded: the
    existing OTA-dashboard MTD revenue line (ota.py:113-115) is also
    rate × nights, so this tile reconciles with that figure.
    """
    try:
        rows = (db.session.query(Reservation.rate_per_night)
                .filter(Reservation.source == 'OTA',
                        Reservation.status == 'CheckedIn',
                        Reservation.arrival_date <= business_date,
                        Reservation.departure_date > business_date)
                .all())
        return round(float(sum((r[0] or 0) for r in rows)), 2)
    except Exception:
        logger.exception('ota_intel: _ota_revenue_today failed')
        return 0.0


def _ota_bookings_today(business_date) -> int:
    """Count of OTA reservations *created* today (booking velocity)."""
    try:
        from app.services import get_business_day_utc_window
        start_utc, end_utc = get_business_day_utc_window(business_date)
        return (db.session.query(func.count(Reservation.id))
                .filter(Reservation.source == 'OTA',
                        Reservation.created_at >= start_utc,
                        Reservation.created_at <  end_utc)
                .scalar() or 0)
    except Exception:
        logger.exception('ota_intel: _ota_bookings_today failed')
        return 0


def _ota_arrivals_today(business_date) -> int:
    """OTA arrivals scheduled for today (front-desk load).
    Pattern mirrors the dashboard arrivals counter; narrowed to source=OTA."""
    try:
        return (db.session.query(func.count(Reservation.id))
                .filter(Reservation.source == 'OTA',
                        Reservation.arrival_date == business_date,
                        Reservation.status.in_(
                            ('Reserved', 'Confirmed', 'CheckedIn')))
                .scalar() or 0)
    except Exception:
        logger.exception('ota_intel: _ota_arrivals_today failed')
        return 0


def _ota_departures_today(business_date) -> int:
    """OTA departures scheduled for today.
    Same pattern as arrivals; status set covers in-progress and completed."""
    try:
        return (db.session.query(func.count(Reservation.id))
                .filter(Reservation.source == 'OTA',
                        Reservation.departure_date == business_date,
                        Reservation.status.in_(('CheckedIn', 'CheckedOut')))
                .scalar() or 0)
    except Exception:
        logger.exception('ota_intel: _ota_departures_today failed')
        return 0


def _ota_pending_collection() -> float:
    """Lifetime OTA receivable — calls the canonical
    ``compute_ota_outstanding`` (ota_settlement_service.py:166-203). This is
    the same number that drives reconciliation reports, so the tile and
    those reports cannot drift apart."""
    try:
        from app.ota_settlement_service import compute_ota_outstanding
        result = compute_ota_outstanding() or {}
        return float(result.get('total_amount') or 0.0)
    except Exception:
        logger.exception('ota_intel: _ota_pending_collection failed')
        return 0.0


def _ota_cancelled_today(business_date) -> int:
    """OTA bookings cancelled *today* (cancellation event happened today).

    Proxy: ``status='Cancelled'`` AND ``updated_at`` within today's UTC
    window. A dedicated ``cancelled_at`` column would be more precise but
    is intentionally deferred — flagged in the audit roadmap (Phase 7+).
    Acceptable proxy because cancelled rows are rarely edited afterwards."""
    try:
        from app.services import get_business_day_utc_window
        start_utc, end_utc = get_business_day_utc_window(business_date)
        return (db.session.query(func.count(Reservation.id))
                .filter(Reservation.source == 'OTA',
                        Reservation.status == 'Cancelled',
                        Reservation.updated_at >= start_utc,
                        Reservation.updated_at <  end_utc)
                .scalar() or 0)
    except Exception:
        logger.exception('ota_intel: _ota_cancelled_today failed')
        return 0


def _build_intelligence_context(business_date):
    """Compute the Phase A KPI-strip context, with cache + timing.

    Returns a dict on success; returns ``None`` on catastrophic failure so
    the template ``{% if intel %}`` block becomes a no-op and the existing
    dashboard renders unchanged. Never raises.
    """
    cache_key = ('ota_intel_kpi', business_date.isoformat())
    cached = _intel_cache_get(cache_key)
    if cached is not None:
        logger.info('ota_intel cache=HIT date=%s', business_date)
        return cached
    logger.info('ota_intel cache=MISS date=%s', business_date)

    timings: dict = {}
    ctx: dict = {}
    try:
        with _timed('revenue_today', timings):
            ctx['ota_revenue_today'] = _ota_revenue_today(business_date)
        with _timed('bookings_today', timings):
            ctx['ota_bookings_today'] = _ota_bookings_today(business_date)
        with _timed('arrivals_today', timings):
            ctx['ota_arrivals_today'] = _ota_arrivals_today(business_date)
        with _timed('departures_today', timings):
            ctx['ota_departures_today'] = _ota_departures_today(business_date)
        with _timed('pending_collection', timings):
            ctx['ota_pending_collection'] = _ota_pending_collection()
        with _timed('cancelled_today', timings):
            ctx['ota_cancelled_today'] = _ota_cancelled_today(business_date)
    except Exception:
        # Safety net: any unexpected error in orchestration must NOT break
        # the dashboard. Returning None makes the template gate a no-op.
        logger.exception('ota_intel: _build_intelligence_context failed')
        return None

    total_ms = sum(timings.values())
    breakdown = ' '.join(f'{k}={v:.0f}ms' for k, v in timings.items())
    slow = (total_ms > _OTA_INTEL_SLOW_MS_TOTAL
            or any(v > _OTA_INTEL_SLOW_MS_AGG for v in timings.values()))
    logger.log(
        logging.WARNING if slow else logging.INFO,
        'ota_intel built total=%.0fms %s', total_ms, breakdown,
    )

    _intel_cache_set(cache_key, ctx)
    return ctx


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@ota_bp.route('/')
@login_required
def dashboard():
    if not current_user.has_role('Admin', 'Manager', 'FrontDesk', 'Accountant'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    today = date.today()
    month_start = today.replace(day=1)

    # OTA reservations this month — eager-load guest to avoid N+1
    ota_res = (
        Reservation.query
        .filter(
            Reservation.source == 'OTA',
            Reservation.arrival_date >= month_start,
        )
        .options(joinedload(Reservation.guest), joinedload(Reservation.room_type))
        .all()
    )

    # Stats by OTA source (ota_booking_id prefix or source field)
    by_source: dict = {}
    total_ota_revenue = 0.0
    for r in ota_res:
        src = _infer_ota_source(r)
        by_source[src] = by_source.get(src, 0) + 1
        if r.status in ('CheckedIn', 'CheckedOut'):
            nights = (r.departure_date - r.arrival_date).days
            total_ota_revenue += float(r.rate_per_night) * nights

    # Booking status breakdown
    status_counts = {}
    for r in ota_res:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    # Recent webhook logs
    recent_logs = (
        WebhookLog.query
        .order_by(WebhookLog.received_at.desc())
        .limit(10)
        .all()
    )

    # Failed logs count (last 7 days)
    failed_count = WebhookLog.query.filter(
        WebhookLog.status == 'failed',
        WebhookLog.received_at >= datetime.utcnow() - timedelta(days=7),
    ).count()

    # MTD OTA revenue vs total revenue
    total_revenue = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_date >= month_start,
        Payment.is_voided == False,
    ).scalar() or 0.0

    ota_share = round(total_ota_revenue / float(total_revenue) * 100, 1) if total_revenue else 0.0

    # Webhook API key (masked)
    api_key = _get_setting('webhook_api_key', '')
    api_key_masked = (api_key[:6] + '••••••••' + api_key[-4:]) if len(api_key) > 10 else '(not set)'

    # Tunnel URL for webhook endpoint
    tunnel_url = _get_setting('cloudflare_tunnel_url', '')
    webhook_url = f"{tunnel_url.rstrip('/')}/webhook/booking" if tunnel_url else '/webhook/booking'

    room_types = RoomType.query.order_by(RoomType.name).all()

    # CI/CO defaults from Masters → used to prefill Quick Manual OTA Booking
    # form times. Falls back to 11:00 when unconfigured (cico_service default).
    from app.cico_service import get_cico_settings
    _cico = get_cico_settings()
    default_ci_time = _cico.get('std_ci', '11:00') or '11:00'
    default_co_time = _cico.get('std_co', '11:00') or '11:00'

    # OTA Revenue Intelligence (Phase A) — gated context. Returns None when
    # the flag is OFF or on any internal failure; the template's `{% if intel %}`
    # block becomes a no-op and the existing dashboard renders unchanged.
    intel = (_build_intelligence_context(today)
             if current_app.config.get('OTA_INTELLIGENCE_ENABLED')
             else None)

    return render_template(
        'ota/dashboard.html',
        today=today,
        month_start=month_start,
        ota_res=ota_res,
        by_source=by_source,
        status_counts=status_counts,
        total_ota_revenue=total_ota_revenue,
        total_revenue=float(total_revenue),
        ota_share=ota_share,
        recent_logs=recent_logs,
        failed_count=failed_count,
        api_key_masked=api_key_masked,
        webhook_url=webhook_url,
        room_types=room_types,
        ota_sources=OTA_SOURCES,
        default_ci_time=default_ci_time,
        default_co_time=default_co_time,
        intel=intel,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@ota_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('ota.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'regenerate_key':
            new_key = secrets.token_hex(24)
            _set_setting('webhook_api_key', new_key, 'API key for channel manager webhook calls')
            db.session.commit()
            flash(f'New API key generated: {new_key}', 'success')
            return redirect(url_for('ota.settings'))

        if action == 'save_tunnel':
            tunnel_url = request.form.get('tunnel_url', '').strip().rstrip('/')
            _set_setting('cloudflare_tunnel_url', tunnel_url, 'Cloudflare tunnel public URL')
            db.session.commit()
            flash('Tunnel URL saved.', 'success')
            return redirect(url_for('ota.settings'))

        if action == 'save_commission':
            for src in OTA_SOURCES:
                key = f'ota_commission_{src.lower().replace(".", "").replace(" ", "_")}'
                val = request.form.get(f'commission_{src}', '0').strip()
                try:
                    float(val)
                except ValueError:
                    val = '0'
                _set_setting(key, val, f'Commission % for {src}')
            db.session.commit()
            flash('Commission rates saved.', 'success')
            return redirect(url_for('ota.settings'))

    api_key = _get_setting('webhook_api_key', '')
    tunnel_url = _get_setting('cloudflare_tunnel_url', '')
    webhook_url = f"{tunnel_url.rstrip('/')}/webhook/booking" if tunnel_url else ''

    commissions = {}
    for src in OTA_SOURCES:
        key = f'ota_commission_{src.lower().replace(".", "").replace(" ", "_")}'
        commissions[src] = _get_setting(key, '0')

    return render_template(
        'ota/settings.html',
        api_key=api_key,
        tunnel_url=tunnel_url,
        webhook_url=webhook_url,
        commissions=commissions,
        ota_sources=OTA_SOURCES,
    )


# ---------------------------------------------------------------------------
# Test ping (AJAX)
# ---------------------------------------------------------------------------

@ota_bp.route('/test-ping', methods=['POST'])
@login_required
def test_ping():
    if not current_user.has_role('Admin', 'Manager'):
        return jsonify({'ok': False, 'message': 'Access denied'}), 403

    tunnel_url = _get_setting('cloudflare_tunnel_url', '').strip()
    if not tunnel_url:
        return jsonify({'ok': False, 'message': 'Tunnel URL not configured in OTA Settings.'})

    import urllib.request
    import urllib.error
    ping_url = f"{tunnel_url.rstrip('/')}/webhook/ping"
    try:
        with urllib.request.urlopen(ping_url, timeout=8) as resp:
            body = resp.read().decode()
            return jsonify({'ok': True, 'message': f'Reachable ✓  ({resp.status})', 'body': body})
    except urllib.error.HTTPError as e:
        return jsonify({'ok': False, 'message': f'HTTP {e.code}: {e.reason}'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


# ---------------------------------------------------------------------------
# OTA Bookings list
# ---------------------------------------------------------------------------

@ota_bp.route('/bookings')
@login_required
def bookings():
    if not current_user.has_role('Admin', 'Manager', 'FrontDesk', 'Accountant'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    status_filter = request.args.get('status', '')
    source_filter = request.args.get('source', '')
    from_str = request.args.get('from', (date.today() - timedelta(days=29)).isoformat())
    to_str = request.args.get('to', date.today().isoformat())

    try:
        from_date = date.fromisoformat(from_str)
        to_date = date.fromisoformat(to_str)
    except ValueError:
        from_date = date.today() - timedelta(days=29)
        to_date = date.today()

    q = Reservation.query.filter(
        Reservation.source == 'OTA',
        Reservation.arrival_date >= from_date,
        Reservation.arrival_date <= to_date,
    )
    if status_filter:
        q = q.filter(Reservation.status == status_filter)

    records = q.order_by(Reservation.arrival_date.desc()).all()

    # Filter by inferred source after query (ota_booking_id prefix)
    if source_filter:
        records = [r for r in records if _infer_ota_source(r) == source_filter]

    room_types = RoomType.query.order_by(RoomType.name).all()

    return render_template(
        'ota/bookings.html',
        records=records,
        from_date=from_date,
        to_date=to_date,
        status_filter=status_filter,
        source_filter=source_filter,
        ota_sources=OTA_SOURCES,
        room_types=room_types,
        today=date.today(),
    )


# ---------------------------------------------------------------------------
# Manual OTA booking creation
# ---------------------------------------------------------------------------

@ota_bp.route('/bookings/manual', methods=['POST'])
@login_required
def manual_booking():
    if not current_user.has_role('Admin', 'Manager', 'FrontDesk'):
        flash('Access denied.', 'danger')
        return redirect(url_for('ota.bookings'))

    try:
        ota_source = request.form.get('ota_source', 'Other OTA').strip()
        ota_booking_id = request.form.get('ota_booking_id', '').strip()
        # Structured name fields (first_name + last_name)
        guest_first_name = request.form.get('guest_first_name', '').strip()
        guest_last_name = request.form.get('guest_last_name', '').strip()
        # Fallback: accept legacy single-field guest_name for backward compat
        if not guest_first_name:
            _legacy = request.form.get('guest_name', '').strip()
            parts = _legacy.split(None, 1) if _legacy else []
            guest_first_name = parts[0] if parts else ''
            guest_last_name = parts[1] if len(parts) > 1 else guest_last_name
        guest_phone = request.form.get('guest_phone', '').strip()
        guest_email = request.form.get('guest_email', '').strip()
        room_type_id = int(request.form.get('room_type_id', 0))
        arrival_str = request.form.get('arrival_date', '')
        departure_str = request.form.get('departure_date', '')
        # Optional HH:MM times (prefilled from CI/CO Rules on the form; stored
        # on the reservation so GRC / reports / hourly logic can read them).
        checkin_time_str = request.form.get('checkin_time', '').strip()[:5] or None
        checkout_time_str = request.form.get('checkout_time', '').strip()[:5] or None
        adults = int(request.form.get('adults', 1))
        children = int(request.form.get('children', 0))
        rate = float(request.form.get('rate_per_night', 0))
        special_requests = request.form.get('special_requests', '').strip()
        # 'paid_at_ota' (default for OTA) or 'pay_at_hotel'
        ota_payment_status = request.form.get('ota_payment_status', 'paid_at_ota').strip()
        if ota_payment_status not in ('paid_at_ota', 'pay_at_hotel'):
            ota_payment_status = 'paid_at_ota'

        if not all([guest_first_name, guest_phone, arrival_str, departure_str, room_type_id]):
            flash('Guest first name, phone, dates, and room type are required.', 'danger')
            return redirect(url_for('ota.bookings'))

        arrival = date.fromisoformat(arrival_str)
        departure = date.fromisoformat(departure_str)
        if departure <= arrival:
            flash('Departure must be after arrival.', 'danger')
            return redirect(url_for('ota.bookings'))

        # Duplicate check
        if ota_booking_id:
            existing = Reservation.query.filter_by(ota_booking_id=ota_booking_id).first()
            if existing:
                flash(f'OTA booking ID {ota_booking_id} already exists (Ref: {existing.booking_reference}).', 'warning')
                return redirect(url_for('ota.bookings'))

        room_type = db.session.get(RoomType, room_type_id)
        if not room_type:
            flash('Invalid room type.', 'danger')
            return redirect(url_for('ota.bookings'))

        # Find or create guest — always store structured names
        guest = Guest.query.filter_by(phone=guest_phone).first()
        if not guest:
            guest = Guest(
                name=f'{guest_first_name} {guest_last_name}'.strip(),
                first_name=guest_first_name,
                last_name=guest_last_name,
                phone=guest_phone,
                email=guest_email or None,
            )
            db.session.add(guest)
            db.session.flush()
        else:
            # Update structured names if currently missing
            if not guest.first_name:
                Guest.set_name(guest, guest_first_name, guest_last_name)

        # Generate booking reference
        import string
        alphabet = string.ascii_uppercase + string.digits
        ref = 'OTA-' + ''.join(secrets.choice(alphabet) for _ in range(6))
        while Reservation.query.filter_by(booking_reference=ref).first():
            ref = 'OTA-' + ''.join(secrets.choice(alphabet) for _ in range(6))

        reservation = Reservation(
            booking_reference=ref,
            guest_id=guest.id,
            room_type_id=room_type.id,
            arrival_date=arrival,
            departure_date=departure,
            adults=adults,
            children=children,
            rate_per_night=rate if rate > 0 else _ota_resolve_rate(
                room_type.id, arrival, departure),
            advance_payment=0,
            status='Confirmed',
            source='OTA',
            # Authoritative channel from the form (was previously read
            # but never stored — Phase A flagged this gap).
            ota_channel=ota_source or None,
            ota_payment_status=ota_payment_status,
            ota_booking_id=ota_booking_id or None,
            special_requests=special_requests or None,
            checkin_time=checkin_time_str,
            checkout_time=checkout_time_str,
        )
        db.session.add(reservation)
        db.session.commit()

        flash(f'OTA booking created: {ref} for {guest_first_name} {guest_last_name}.'.rstrip(), 'success')
        return redirect(url_for('ota.bookings'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating booking: {e}', 'danger')
        return redirect(url_for('ota.bookings'))


# ---------------------------------------------------------------------------
# Cancel OTA reservation
# ---------------------------------------------------------------------------

@ota_bp.route('/bookings/<int:reservation_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(reservation_id):
    if not current_user.has_role('Admin', 'Manager'):
        flash('Manager or Admin access required.', 'danger')
        return redirect(url_for('ota.bookings'))

    reservation = db.session.get(Reservation, reservation_id)
    if not reservation or reservation.source != 'OTA':
        flash('OTA reservation not found.', 'danger')
        return redirect(url_for('ota.bookings'))

    if reservation.status in ('CheckedIn', 'CheckedOut'):
        flash(f'Cannot cancel a {reservation.status} reservation.', 'danger')
        return redirect(url_for('ota.bookings'))

    reservation.status = 'Cancelled'
    db.session.commit()
    flash(f'Reservation {reservation.booking_reference} cancelled.', 'success')
    return redirect(url_for('ota.bookings'))


# ---------------------------------------------------------------------------
# Webhook logs (paginated)
# ---------------------------------------------------------------------------

@ota_bp.route('/webhook/logs')
@login_required
def webhook_logs():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('ota.dashboard'))

    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    source_filter = request.args.get('source', '')

    q = WebhookLog.query
    if status_filter:
        q = q.filter(WebhookLog.status == status_filter)
    if source_filter:
        q = q.filter(WebhookLog.source.ilike(f'%{source_filter}%'))

    logs = q.order_by(WebhookLog.received_at.desc()).paginate(page=page, per_page=50, error_out=False)

    return render_template(
        'ota/webhook_logs.html',
        logs=logs,
        status_filter=status_filter,
        source_filter=source_filter,
    )


# ---------------------------------------------------------------------------
# Retry failed webhook log
# ---------------------------------------------------------------------------

@ota_bp.route('/webhook/retry/<int:log_id>', methods=['POST'])
@login_required
def retry_webhook(log_id):
    if not current_user.has_role('Admin', 'Manager'):
        return jsonify({'ok': False, 'message': 'Access denied'}), 403

    log = db.session.get(WebhookLog, log_id)
    if not log:
        return jsonify({'ok': False, 'message': 'Log entry not found'})

    if log.status == 'processed':
        return jsonify({'ok': False, 'message': 'Already processed'})

    # Re-run the booking handler with the stored payload
    payload = log.raw_payload or {}
    event = payload.get('event', 'new_booking')

    try:
        from app.webhook import _handle_new_booking, _handle_cancel, _handle_modify
        if event == 'new_booking':
            response = _handle_new_booking(payload, log)
        elif event == 'cancel_booking':
            response = _handle_cancel(payload, log)
        elif event == 'modify_booking':
            response = _handle_modify(payload, log)
        else:
            return jsonify({'ok': False, 'message': f'Unknown event: {event}'})

        # webhook handlers return a Flask Response (possibly a tuple (response, code))
        if isinstance(response, tuple):
            resp_obj, code = response
        else:
            resp_obj, code = response, response.status_code
        ok = code in (200, 201)
        return jsonify({'ok': ok, 'message': f'Retry completed (HTTP {code})'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _infer_ota_source(reservation: Reservation) -> str:
    """Resolve the OTA channel name for a reservation.

    **Authoritative path** (preferred): read ``reservation.ota_channel``,
    which is set at booking creation time by the webhook ingestion and
    the manual OTA booking form. This is the single source of truth —
    once a row has it, the dashboard, reports, CEO KPIs and journey view
    will all agree forever, even if the booking_reference is later
    edited or the inference rules change.

    **Inference fallback**: legacy rows (created before column 7.3.0) and
    any future row where the channel could not be captured at creation
    time fall back to prefix matching against ``ota_booking_id`` /
    ``booking_reference``. The fallback is intentionally lenient so the
    column 7.3.0 backfill in ``init_data`` can populate every legacy
    row deterministically on first startup after the upgrade.
    """
    stored = (getattr(reservation, 'ota_channel', None) or '').strip()
    if stored:
        return stored

    ota_id = (reservation.ota_booking_id or '').lower()
    ref = (reservation.booking_reference or '').lower()
    combined = ota_id + ref

    mapping = {
        'bdc': 'Booking.com', 'booking': 'Booking.com',
        'mmt': 'MakeMyTrip', 'makemytrip': 'MakeMyTrip',
        'goi': 'Goibibo', 'goibibo': 'Goibibo',
        'aga': 'Agoda', 'agoda': 'Agoda',
        'exp': 'Expedia', 'expedia': 'Expedia',
        'air': 'Airbnb', 'airbnb': 'Airbnb',
        'yat': 'Yatra', 'yatra': 'Yatra',
        'eas': 'EaseMyTrip', 'easemytrip': 'EaseMyTrip',
    }
    for prefix, name in mapping.items():
        if prefix in combined:
            return name
    return 'Other OTA'
