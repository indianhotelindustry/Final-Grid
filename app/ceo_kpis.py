"""
CEO KPI Service — Phase A
===========================
Roll-up helpers that aggregate reservations, payments, and OTA
settlement data into the shape a CEO dashboard needs.

All functions in this module are READ-ONLY. They compose the existing
primitives in ``kpi_helpers``, ``ota_settlement_service``, and
``ota_journey`` — the goal is one coherent data source for Phase B's
CEO dashboard UI and for the night-audit snapshot extension.

Public API
----------
    get_ota_funnel(business_date)           -> dict
    get_ota_channel_mix(business_date, mtd) -> dict
    get_ota_pipeline(days_ahead=30)         -> dict
    get_ota_receivable_aging(as_of=None)    -> dict
    get_night_audit_health()                -> dict
    get_ceo_kpi_pack(business_date)         -> dict

Aging buckets (default)
-----------------------
    0-15 / 16-30 / 31-60 / 60+ days
    Tuned for channel-manager settlement cycles (Booking.com ~15 days,
    MMT/Goibibo ~30 days, others longer). Override with ``buckets=``.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from app.models import (
    db, Reservation, Payment, PaymentMode, BusinessDate, NightAuditLog,
)

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────────────────────────────

def _f(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def _safe_div(a: float, b: float) -> float:
    return round(a / b, 2) if b else 0.0


def _ota_source_of(reservation: Reservation) -> str:
    """Resolve the OTA channel name the same way ota.py / ota_journey do."""
    try:
        from app.ota import _infer_ota_source
        return _infer_ota_source(reservation)
    except Exception:
        return 'Other OTA'


# ──────────────────────────────────────────────────────────────────────
# 1. OTA Funnel — today
# ──────────────────────────────────────────────────────────────────────

def get_ota_funnel(business_date: date) -> dict:
    """Today's OTA conversion funnel: booked → arrivals → check-in → out.

    Numbers are deliberately discrete (not cumulative) so the UI can
    render a "conversion %" between consecutive stages. "Bookings
    received today" counts reservations created today regardless of
    arrival_date — that's what a manager means by "how many bookings
    did we get today?".
    """
    from sqlalchemy import and_

    day_start = datetime.combine(business_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    base_ota = Reservation.query.filter(Reservation.source == 'OTA')

    bookings_received = base_ota.filter(
        Reservation.created_at >= day_start,
        Reservation.created_at < day_end,
    ).count()

    arrivals_expected = base_ota.filter(
        Reservation.arrival_date == business_date,
        Reservation.status.in_(
            ['Reserved', 'Confirmed', 'CheckedIn', 'CheckedOut', 'NoShow']),
    ).count()

    checked_in = base_ota.filter(
        Reservation.arrival_date == business_date,
        Reservation.status.in_(['CheckedIn', 'CheckedOut']),
    ).count()

    checked_out = base_ota.filter(
        Reservation.checked_out_at >= day_start,
        Reservation.checked_out_at < day_end,
    ).count()

    no_shows = base_ota.filter(
        Reservation.arrival_date == business_date,
        Reservation.status == 'NoShow',
    ).count()

    cancellations = base_ota.filter(
        Reservation.status == 'Cancelled',
        Reservation.arrival_date == business_date,
    ).count()

    return {
        'business_date': business_date.isoformat(),
        'bookings_received': bookings_received,
        'arrivals_expected': arrivals_expected,
        'checked_in': checked_in,
        'checked_out': checked_out,
        'no_shows': no_shows,
        'cancellations': cancellations,
        'conversion_pct': _safe_div(checked_in * 100.0, arrivals_expected),
        'no_show_pct': _safe_div(no_shows * 100.0, arrivals_expected),
    }


# ──────────────────────────────────────────────────────────────────────
# 2. OTA Channel Mix — today + MTD
# ──────────────────────────────────────────────────────────────────────

def _channel_mix_rows(reservations: list[Reservation]) -> list[dict]:
    """Group a list of reservations by inferred OTA source.

    Revenue is accrual (rate × nights of THAT reservation's stay within
    the period), not cash. This matches how the night audit accrues.
    """
    groups: dict[str, dict] = defaultdict(lambda: {
        'bookings': 0,
        'room_nights': 0,
        'revenue_accrued': 0.0,
    })
    for r in reservations:
        src = _ota_source_of(r)
        g = groups[src]
        g['bookings'] += 1
        nights = max(0, (r.departure_date - r.arrival_date).days)
        g['room_nights'] += nights
        g['revenue_accrued'] += _f(r.rate_per_night) * nights

    rows = []
    for src, g in groups.items():
        rows.append({
            'source': src,
            'bookings': g['bookings'],
            'room_nights': g['room_nights'],
            'revenue_accrued': round(g['revenue_accrued'], 2),
            'adr': _safe_div(g['revenue_accrued'], g['room_nights']),
        })
    rows.sort(key=lambda x: x['revenue_accrued'], reverse=True)
    return rows


def get_ota_channel_mix(business_date: date,
                        mtd: bool = True) -> dict:
    """OTA bookings grouped by channel, for today and optionally MTD.

    - "today" = reservations created on business_date (whatever their
      arrival date is — this is how hotels describe "today's bookings").
    - "mtd" = reservations created since the first of the month through
      business_date.
    """
    day_start = datetime.combine(business_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    today_rows = (Reservation.query
                  .filter(Reservation.source == 'OTA',
                          Reservation.created_at >= day_start,
                          Reservation.created_at < day_end,
                          Reservation.status != 'Cancelled')
                  .all())

    result = {
        'business_date': business_date.isoformat(),
        'today': _channel_mix_rows(today_rows),
    }

    if mtd:
        mtd_start = datetime.combine(business_date.replace(day=1),
                                     datetime.min.time())
        mtd_rows = (Reservation.query
                    .filter(Reservation.source == 'OTA',
                            Reservation.created_at >= mtd_start,
                            Reservation.created_at < day_end,
                            Reservation.status != 'Cancelled')
                    .all())
        result['mtd_from'] = mtd_start.date().isoformat()
        result['mtd'] = _channel_mix_rows(mtd_rows)

    return result


# ──────────────────────────────────────────────────────────────────────
# 3. Forward Pipeline — OTA bookings arriving in the next N days
# ──────────────────────────────────────────────────────────────────────

def get_ota_pipeline(business_date: date,
                     days_ahead: int = 30) -> dict:
    """Confirmed OTA bookings arriving in the next ``days_ahead`` days.

    Rolls up by source AND by arrival date — the per-date roll-up gives
    the CEO dashboard a daily bar chart of the forward OTA book.
    """
    if days_ahead <= 0:
        days_ahead = 30
    start = business_date
    end = business_date + timedelta(days=days_ahead)

    rows = (Reservation.query
            .filter(Reservation.source == 'OTA',
                    Reservation.status.in_(['Reserved', 'Confirmed']),
                    Reservation.arrival_date >= start,
                    Reservation.arrival_date < end)
            .all())

    total_bookings = len(rows)
    total_nights = 0
    total_revenue = 0.0

    by_source: dict[str, dict] = defaultdict(lambda: {
        'bookings': 0, 'room_nights': 0, 'revenue': 0.0})
    by_date: dict[str, dict] = defaultdict(lambda: {
        'bookings': 0, 'room_nights': 0, 'revenue': 0.0})

    for r in rows:
        nights = max(0, (r.departure_date - r.arrival_date).days)
        revenue = _f(r.rate_per_night) * nights
        total_nights += nights
        total_revenue += revenue

        src = _ota_source_of(r)
        s = by_source[src]
        s['bookings'] += 1
        s['room_nights'] += nights
        s['revenue'] += revenue

        key = r.arrival_date.isoformat()
        d = by_date[key]
        d['bookings'] += 1
        d['room_nights'] += nights
        d['revenue'] += revenue

    by_source_list = [
        {'source': src,
         'bookings': v['bookings'],
         'room_nights': v['room_nights'],
         'revenue': round(v['revenue'], 2)}
        for src, v in by_source.items()
    ]
    by_source_list.sort(key=lambda x: x['revenue'], reverse=True)

    by_date_list = [
        {'date': day,
         'bookings': v['bookings'],
         'room_nights': v['room_nights'],
         'revenue': round(v['revenue'], 2)}
        for day, v in by_date.items()
    ]
    by_date_list.sort(key=lambda x: x['date'])

    return {
        'from': start.isoformat(),
        'to': end.isoformat(),
        'days_ahead': days_ahead,
        'total_bookings': total_bookings,
        'total_room_nights': total_nights,
        'total_projected_revenue': round(total_revenue, 2),
        'by_source': by_source_list,
        'by_arrival_date': by_date_list,
    }


# ──────────────────────────────────────────────────────────────────────
# 4. OTA Receivable Aging
# ──────────────────────────────────────────────────────────────────────

DEFAULT_AGING_BUCKETS = [
    ('0-7 days',   0,   7),
    ('8-15 days',  8,  15),
    ('16-30 days', 16, 30),
    ('30+ days',   31, None),
]


def get_ota_receivable_aging(as_of: date | None = None,
                             buckets: list[tuple] | None = None) -> dict:
    """Bucket OTA receivable postings by age on each settlement head.

    Phase 1 definition (same as ota_settlement_service.compute_ota_outstanding):
    every non-voided payment posted to an ``ota_receivable`` head is
    treated as outstanding. A true reconciliation against channel-
    manager payout files is Phase 2 work.

    Each bucket returns: label, min/max days, total amount, and a
    by_head breakdown so the dashboard can render channel × age matrix.
    """
    if as_of is None:
        as_of = date.today()
    if buckets is None:
        buckets = DEFAULT_AGING_BUCKETS

    rows = (db.session.query(Payment, PaymentMode)
            .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
            .filter(PaymentMode.category == 'ota_receivable',
                    Payment.is_voided == False)
            .all())

    # Initialise buckets
    bucket_state = []
    for label, lo, hi in buckets:
        bucket_state.append({
            'label': label,
            'min_days': lo,
            'max_days': hi,
            'total': 0.0,
            'count': 0,
            'by_head': defaultdict(lambda: {'amount': 0.0, 'count': 0, 'code': ''}),
        })

    total_outstanding = 0.0
    for p, pm in rows:
        amt = _f(p.amount)
        if amt <= 0:
            continue
        total_outstanding += amt
        pay_date = p.payment_date or (p.created_at.date()
                                      if p.created_at else as_of)
        age = max(0, (as_of - pay_date).days)

        for b in bucket_state:
            lo = b['min_days']
            hi = b['max_days']
            if age >= lo and (hi is None or age <= hi):
                b['total'] += amt
                b['count'] += 1
                slot = b['by_head'][pm.name]
                slot['amount'] += amt
                slot['count'] += 1
                slot['code'] = pm.code or ''
                break

    # Convert defaultdicts → plain dicts for JSON serialisation
    for b in bucket_state:
        b['by_head'] = {k: {'amount': round(v['amount'], 2),
                            'count': v['count'],
                            'code': v['code']}
                       for k, v in b['by_head'].items()}
        b['total'] = round(b['total'], 2)

    return {
        'as_of': as_of.isoformat(),
        'buckets': bucket_state,
        'total_outstanding': round(total_outstanding, 2),
    }


# ──────────────────────────────────────────────────────────────────────
# 5. Night Audit Health
# ──────────────────────────────────────────────────────────────────────

def get_night_audit_health() -> dict:
    """Expose the state of the night-audit subsystem for the CEO view.

    The business date and the latest audit log are the two data points
    a CEO needs to answer: "did last night's audit run?" and "are we
    running behind?".
    """
    bd_row = db.session.query(BusinessDate).first()
    current_bd = bd_row.current_date if bd_row else None
    is_locked = bool(bd_row.is_locked) if bd_row else False

    last_any = (NightAuditLog.query
                .order_by(NightAuditLog.audit_date.desc())
                .first())
    last_completed = (NightAuditLog.query
                      .filter_by(status='Completed')
                      .order_by(NightAuditLog.audit_date.desc())
                      .first())

    days_behind = 0
    if current_bd and last_completed:
        # current_bd is the date we're OPERATING on, so the most recent
        # audit is expected to be current_bd - 1.
        expected = current_bd - timedelta(days=1)
        days_behind = max(0, (expected - last_completed.audit_date).days)
    elif current_bd and not last_completed:
        days_behind = 1  # No completed audits ever — worst case.

    return {
        'current_business_date': _iso(current_bd),
        'business_date_locked': is_locked,
        'last_audit_date': _iso(last_any.audit_date) if last_any else None,
        'last_audit_status': last_any.status if last_any else None,
        'last_audit_run_at': _iso(last_any.run_at) if last_any else None,
        'last_completed_audit_date': (_iso(last_completed.audit_date)
                                      if last_completed else None),
        'days_behind': days_behind,
        'is_healthy': days_behind == 0 and last_completed is not None,
    }


# ──────────────────────────────────────────────────────────────────────
# 6. One-call CEO KPI pack
# ──────────────────────────────────────────────────────────────────────

def get_ceo_kpi_pack(business_date: date | None = None,
                     days_ahead: int = 30) -> dict:
    """Bundle every CEO-dashboard primitive into one call.

    The CEO dashboard (Phase B) and the night-audit snapshot extension
    both consume this — one call, one coherent view.
    """
    if business_date is None:
        from app.services import get_business_date
        business_date = get_business_date()

    try:
        funnel = get_ota_funnel(business_date)
    except Exception as exc:
        log.exception('get_ceo_kpi_pack: funnel failed: %s', exc)
        funnel = {}

    try:
        channel_mix = get_ota_channel_mix(business_date, mtd=True)
    except Exception as exc:
        log.exception('get_ceo_kpi_pack: channel_mix failed: %s', exc)
        channel_mix = {}

    try:
        pipeline = get_ota_pipeline(business_date, days_ahead=days_ahead)
    except Exception as exc:
        log.exception('get_ceo_kpi_pack: pipeline failed: %s', exc)
        pipeline = {}

    try:
        aging = get_ota_receivable_aging(as_of=business_date)
    except Exception as exc:
        log.exception('get_ceo_kpi_pack: aging failed: %s', exc)
        aging = {}

    try:
        audit_health = get_night_audit_health()
    except Exception as exc:
        log.exception('get_ceo_kpi_pack: audit_health failed: %s', exc)
        audit_health = {}

    # ── Phase 2: payout status (additive layer over receivables) ──
    try:
        from app.ota_reconciliation import get_payout_status_for_ceo
        payout_status = get_payout_status_for_ceo()
    except Exception as exc:
        log.exception('get_ceo_kpi_pack: payout_status failed: %s', exc)
        payout_status = {}

    # Top-level KPI strip the dashboard header can render cheaply.
    headline = {
        'ota_bookings_today': funnel.get('bookings_received', 0),
        'ota_arrivals_today': funnel.get('arrivals_expected', 0),
        'ota_checked_in_today': funnel.get('checked_in', 0),
        'ota_no_shows_today': funnel.get('no_shows', 0),
        'ota_pipeline_bookings_30d': pipeline.get('total_bookings', 0),
        'ota_pipeline_revenue_30d': pipeline.get('total_projected_revenue', 0),
        'ota_receivable_outstanding': aging.get('total_outstanding', 0),
        'audit_days_behind': audit_health.get('days_behind', 0),
    }

    return {
        'business_date': business_date.isoformat(),
        'headline': headline,
        'funnel': funnel,
        'channel_mix': channel_mix,
        'pipeline': pipeline,
        'receivable_aging': aging,
        'audit_health': audit_health,
        'payout_status': payout_status,
    }
