"""
KPI Command Center — Phase 3 (real calculations).

Public entry: ``build_command_center_payload(filters, business_date)``.

Core definitions used throughout (locked here so every metric stays consistent):
    * **Accrual room revenue (range)** — Σ (rate_per_night × nights-in-range)
      for reservations with ``status ∈ {CheckedIn, CheckedOut}`` overlapping
      the window. Nights-in-range = ``min(departure, to+1) − max(arrival, from)``.
    * **Accrual extras (range)** — Σ ``ExtraCharge.amount`` where
      ``charge_date`` falls inside the window.
    * **Rooms sold (range)** — total occupied room-nights across the same set
      of reservations used for accrual revenue.
    * **Rooms available (range)** — sellable, in-order inventory × days in range.
    * **Occupancy %** — rooms_sold / rooms_available × 100.
    * **ADR** — room_revenue / rooms_sold  (0 if no sold rooms).
    * **RevPAR** — room_revenue / rooms_available  (0 if no available rooms).
    * **ALOS** — avg (departure − arrival).days over CheckedOut stays whose
      ``DATE(checked_out_at)`` falls in the window.
    * **Outstanding due (cash)** — Σ calculate_stay_amount(r)['balance'] for
      every in-house reservation (status=CheckedIn) with balance > 0. This is
      a point-in-time snapshot, not range-based.
    * **OTA receivable (range, cash)** — Σ non-voided payments posted to
      ``PaymentMode.category='ota_receivable'`` within the window.

Data-source priority (per date, checked during aggregation):
    1. ``NightAuditLog`` row with ``status='Completed'`` — its
       ``accrual_revenue`` / ``occupancy_count`` win.
    2. Otherwise live aggregation from reservations / extra_charges / payments.

This resolves the cash vs. accrual ambiguity the project flagged earlier:
headline revenue cards use **accrual**; collection/due cards use **cash**.
Each revenue card also carries a ``tag`` (``Accrual`` / ``Cash``) so the UI
can never be mistaken.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Iterable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased

from app.date_ranges import (
    resolve_range, ResolvedRange, month_window,
    comparison_range, ComparisonWindow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Governance metrics — feed the alert engine's _detect_governance_alerts.
# ---------------------------------------------------------------------------
def _build_governance_block(ctx: dict) -> dict:
    """Aggregate the three signals the governance alerts care about.

    Returns a dict with::
        credit_outstanding_total : ₹ open individual-credit receivable
        credit_outstanding_count : number of open receivables
        overdue_30_count         : count of receivables aged > 30 days
        overdue_30_amount        : ₹ in 30+ bucket
        overrides_24h_count      : count of audit_lock_override AuditLog rows
                                   in the trailing 24 hours
    """
    from app.models import Reservation, AuditLog
    from datetime import datetime as _dt, timedelta as _td

    today = ctx.get('business_date') or date.today()

    out = {
        'credit_outstanding_total': 0.0,
        'credit_outstanding_count': 0,
        'overdue_30_count':         0,
        'overdue_30_amount':        0.0,
        'overrides_24h_count':      0,
    }

    # Open Individual Credit receivables
    try:
        rows = (Reservation.query
                .filter(Reservation.credit_amount > 0)
                .all())
        for r in rows:
            original  = float(r.credit_amount or 0)
            settled   = float(r.credit_settled_amount or 0)
            remaining = max(0.0, round(original - settled, 2))
            if remaining <= 0.005:
                continue
            out['credit_outstanding_total'] += remaining
            out['credit_outstanding_count'] += 1
            approved_at = r.credit_approved_at
            approved_d = approved_at.date() if approved_at else r.departure_date
            if approved_d is not None and (today - approved_d).days > 30:
                out['overdue_30_count']  += 1
                out['overdue_30_amount'] += remaining
    except Exception:
        logger.exception('governance: credit aggregation failed')

    # Audit-lock overrides in trailing 24h
    try:
        cutoff = _dt.utcnow() - _td(hours=24)
        out['overrides_24h_count'] = int(
            AuditLog.query
            .filter(AuditLog.action == 'audit_lock_override',
                    AuditLog.timestamp >= cutoff)
            .count() or 0
        )
    except Exception:
        logger.exception('governance: override count failed')

    return out

# ---------------------------------------------------------------------------
# Phase-1 metric envelopes (unchanged shape — callers depend on this)
# ---------------------------------------------------------------------------

def _metric(value: float = 0,
            display: str = '—',
            sub: str = '',
            tag: str = '',
            currency: str = '') -> dict:
    return {'value': value, 'display': display, 'sub': sub,
            'tag': tag, 'currency': currency}


def _money(value: float = 0, display: str = '—',
           sub: str = '', tag: str = '') -> dict:
    return _metric(value=value, display=display, sub=sub, tag=tag, currency='INR')


def _variance(value: float = 0, display: str = '—',
              direction: str = 'flat', currency: str = '') -> dict:
    return {'value': value, 'display': display,
            'direction': direction, 'currency': currency}


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_inr(amount) -> str:
    """₹-prefixed integer with thousand-separators (comma). Negative safe."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0
    sign = '-' if n < 0 else ''
    return f'{sign}₹{abs(n):,.0f}'


def _fmt_pct(value, decimals: int = 1) -> str:
    try:
        return f'{float(value or 0):.{decimals}f}%'
    except (TypeError, ValueError):
        return '0.0%'


def _fmt_nights(value) -> str:
    try:
        return f'{float(value or 0):.1f} nights'
    except (TypeError, ValueError):
        return '0.0 nights'


def _fmt_count(value) -> str:
    try:
        return f'{int(value or 0):,}'
    except (TypeError, ValueError):
        return '0'


def _fmt_inr_short(amount) -> str:
    """Indian short-form ₹: 12,34,567 → ₹12.35L, 1.5Cr etc. Used in subtext
    where space matters. Falls back to full precision for small amounts."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0
    a = abs(n)
    sign = '-' if n < 0 else ''
    if a >= 1_00_00_000:
        return f'{sign}₹{a / 1_00_00_000:.2f}Cr'
    if a >= 1_00_000:
        return f'{sign}₹{a / 1_00_000:.2f}L'
    return f'{sign}₹{a:,.0f}'


# ---------------------------------------------------------------------------
# Phase 4 — Target engine
# ---------------------------------------------------------------------------

# Canonical Settings keys (match existing usage elsewhere in the app).
_TARGET_KEY_REVENUE   = 'monthly_revenue_target'
_TARGET_KEY_OCCUPANCY = 'monthly_occupancy_target'
_TARGET_KEY_ADR       = 'monthly_adr_target'
_TARGET_KEY_REVPAR    = 'monthly_revpar_target'


def _read_number_setting(key: str, default: float = 0.0) -> float:
    """Read a Settings row and coerce to float. Never raises."""
    from app.models import Settings
    try:
        row = Settings.query.filter_by(key=key).first()
        if row and row.value is not None and str(row.value).strip() != '':
            return float(str(row.value).strip())
    except Exception:
        pass
    return float(default)


def get_monthly_targets(business_date: date, property_id: Optional[str] = None) -> dict:
    """Pull monthly-target Settings rows.

    property_id is accepted for forward-compat but ignored for now — the app's
    Settings are global. When property-scoped targets land, extend this helper
    without touching the callers.
    """
    return {
        'revenue':   _read_number_setting(_TARGET_KEY_REVENUE,   0.0),
        'occupancy': _read_number_setting(_TARGET_KEY_OCCUPANCY, 0.0),
        'adr':       _read_number_setting(_TARGET_KEY_ADR,       0.0),
        'revpar':    _read_number_setting(_TARGET_KEY_REVPAR,    0.0),
    }


def _compute_target_frame(monthly_target: float, business_date: date) -> dict:
    """Expand a monthly revenue target into the set of derived numbers the
    UI and debug need. All divisions are zero-safe; every field is always
    present so callers never branch on missing keys.

    Semantics (locked):
      daily_target          = monthly_target / days_in_month
      pro_rated_mtd_target  = monthly_target * days_elapsed / days_in_month
      remaining_target      = max(0, monthly_target - mtd_actual)   (caller fills)
      remaining_days        = max(0, days_in_month - days_elapsed)
      required_run_rate     = remaining_target / remaining_days (0 when denom=0)
      mtd_vs_full_pct       = mtd_actual / monthly_target * 100
      mtd_variance_vs_prorated = mtd_actual - pro_rated_mtd_target
    """
    target = float(monthly_target or 0)
    days_in_month = _days_in_month(business_date.year, business_date.month)
    days_elapsed  = business_date.day
    remaining_days = max(0, days_in_month - days_elapsed)
    daily_target  = (target / days_in_month) if days_in_month > 0 else 0.0
    pro_rated     = (target * days_elapsed / days_in_month) if days_in_month > 0 else 0.0
    return {
        'monthly_target':        target,
        'days_in_month':         days_in_month,
        'days_elapsed':          days_elapsed,
        'remaining_days':        remaining_days,
        'daily_target':          daily_target,
        'pro_rated_mtd_target':  pro_rated,
    }


def _required_run_rate(monthly_target: float, mtd_actual: float,
                       remaining_days: int) -> float:
    """How much per day do we need from now to end-of-month to hit target?

    Returns 0 when already over target or when there are no days left —
    avoids showing "₹12L/day" on 31 Mar.
    """
    remaining = float(monthly_target or 0) - float(mtd_actual or 0)
    if remaining <= 0 or remaining_days <= 0:
        return 0.0
    return remaining / remaining_days


def _variance_direction(variance: float) -> str:
    if variance > 0:
        return 'up'
    if variance < 0:
        return 'down'
    return 'flat'


def _safe_progress_pct(actual: float, target: float) -> float:
    """Clamped 0–999. Above 999 is conceptually ``∞`` — callers should treat
    the value as "way over target" rather than try to render it literally.
    The frontend further caps bar width to 100% in its CSS; this clamp keeps
    the JSON payload bounded so downstream consumers (logs, exports, future
    reports) aren't surprised by 7-digit percentages."""
    if not target or target <= 0:
        return 0.0
    raw = float(actual or 0) / float(target) * 100
    if raw < 0:
        return 0.0
    return round(min(raw, 999.0), 1)


# ---------------------------------------------------------------------------
# Phase 5 — Comparison engine
# ---------------------------------------------------------------------------

def _compute_delta(current: float, previous: float,
                   formatter=None, pct_unit: str = '%') -> dict:
    """Standard delta envelope.

    current/previous → delta (absolute), pct (percentage change), direction.

    Zero-previous rule: ``previous == 0`` returns ``pct = None`` so the UI
    can render "New" / "—" instead of a misleading ``0%`` (which would
    make an infinite-growth jump look flat). ``direction`` still reports
    ``up`` / ``flat`` honestly based on the absolute delta.
    """
    cur  = float(current or 0)
    prev = float(previous or 0)
    delta = cur - prev
    if prev == 0:
        pct = None                       # explicit "undefined growth"
    else:
        raw = (delta / prev) * 100
        pct = round(max(-999.0, min(999.0, raw)), 1)
    fmt = formatter or _fmt_inr
    direction = 'up' if delta > 0 else ('down' if delta < 0 else 'flat')
    return {
        'value':     round(delta, 2),
        'display':   fmt(delta),
        'pct':       pct,                # may be None
        'direction': direction,
    }


def _delta_phrase(delta: dict, metric_label: str, unit: str = '₹') -> str:
    """Human-readable phrase: 'Up ₹45,000 vs previous'  /  'Down 12% vs previous'.
    Keeps sub-text concise — meeting-safe wording."""
    if delta['direction'] == 'flat':
        return f'{metric_label} unchanged'
    word = 'Up' if delta['direction'] == 'up' else 'Down'
    return f'{word} {delta["display"].lstrip("-")} vs previous'


def build_comparison(ctx: dict) -> dict:
    """Phase 5 — period-over-period block.

    Produces a ``comparison`` dict with current / previous / delta sub-blocks.
    Both windows use the same source filter and the same KPI helpers as the
    main dashboard so the headline number and "vs previous" number can never
    drift on definition.

    Skipped entirely (empty dict) when no valid current range is resolvable
    (error path). The composer detects this and surfaces ``comparison: {}``
    rather than None so the frontend always has a key to read.
    """
    df: Optional[date] = ctx.get('date_from')
    dt: Optional[date] = ctx.get('date_to')
    if not df or not dt:
        return {'type': 'none', 'current': {}, 'previous': {}, 'delta': {}}

    bd:      date = ctx['business_date']
    preset:  str  = ctx.get('preset') or 'custom'
    source:  str  = ctx.get('filters', {}).get('source') or 'ALL'

    cw: ComparisonWindow = comparison_range(preset, bd, df, dt)
    if cw.error or not cw.previous_from or not cw.previous_to:
        return {'type': cw.comparison_type, 'current': {}, 'previous': {}, 'delta': {}}

    cur_snap  = _snapshot(df, dt, source)
    prev_snap = _snapshot(cw.previous_from, cw.previous_to, source)
    cur_alos  = _alos(df, dt, source)
    prev_alos = _alos(cw.previous_from, cw.previous_to, source)

    def _pp_fmt(v):   # percentage points — occupancy delta
        try: return f'{float(v or 0):+.1f}pt'
        except Exception: return '0.0pt'
    def _cnt_fmt(v):
        try: return f'{int(v or 0):+,}'
        except Exception: return '0'
    def _nights_fmt(v):
        try: return f'{float(v or 0):+.1f}'
        except Exception: return '0.0'

    current_block = {
        'sales':     _money(value=cur_snap['total_revenue'],  display=_fmt_inr(cur_snap['total_revenue'])),
        'occupancy': _metric(value=cur_snap['occupancy_pct'], display=_fmt_pct(cur_snap['occupancy_pct'])),
        'adr':       _money(value=cur_snap['adr'],            display=_fmt_inr(cur_snap['adr'])),
        'revpar':    _money(value=cur_snap['revpar'],         display=_fmt_inr(cur_snap['revpar'])),
        'alos':      _metric(value=cur_alos,                  display=_fmt_nights(cur_alos)),
    }
    previous_block = {
        'sales':     _money(value=prev_snap['total_revenue'],  display=_fmt_inr(prev_snap['total_revenue'])),
        'occupancy': _metric(value=prev_snap['occupancy_pct'], display=_fmt_pct(prev_snap['occupancy_pct'])),
        'adr':       _money(value=prev_snap['adr'],            display=_fmt_inr(prev_snap['adr'])),
        'revpar':    _money(value=prev_snap['revpar'],         display=_fmt_inr(prev_snap['revpar'])),
        'alos':      _metric(value=prev_alos,                  display=_fmt_nights(prev_alos)),
    }
    delta_block = {
        'sales':     _compute_delta(cur_snap['total_revenue'],  prev_snap['total_revenue']),
        'occupancy': _compute_delta(cur_snap['occupancy_pct'],  prev_snap['occupancy_pct'], formatter=_pp_fmt),
        'adr':       _compute_delta(cur_snap['adr'],            prev_snap['adr']),
        'revpar':    _compute_delta(cur_snap['revpar'],         prev_snap['revpar']),
        'alos':      _compute_delta(cur_alos,                   prev_alos, formatter=_nights_fmt),
    }
    return {
        'type':               cw.comparison_type,
        'current_range':      {'from': df.isoformat(), 'to': dt.isoformat()},
        'previous_range':     {'from': cw.previous_from.isoformat(),
                               'to':   cw.previous_to.isoformat()},
        'current':            current_block,
        'previous':           previous_block,
        'delta':              delta_block,
    }


# ---------------------------------------------------------------------------
# Source filter — canonical keys → Reservation filter chain
# ---------------------------------------------------------------------------

def apply_source_filter(query, source_key: str):
    """Narrow a ``Reservation`` query by canonical source key.

    CORPORATE is special: not a source value in the schema — it's derived via
    CheckInRecord.billing_responsibility or a non-empty Guest.company. The
    helper outer-joins the necessary tables on the fly.
    """
    from app.models import Reservation, CheckInRecord, Guest
    if source_key in (None, '', 'ALL'):
        return query
    if source_key == 'OTA':
        return query.filter(Reservation.source == 'OTA')
    if source_key == 'AGENT':
        return query.filter(Reservation.source == 'Agent')
    if source_key == 'WALKIN':
        return query.filter(Reservation.source == 'Walk-in')
    if source_key == 'DIRECT':
        return query.filter(Reservation.source.in_(('Website', 'Calling')))
    if source_key == 'CORPORATE':
        # Priority rule:
        #   PRIMARY   — CheckInRecord.billing_responsibility = 'Company'
        #   SECONDARY — no CheckInRecord yet (Reserved/Confirmed before CI)
        #               AND guest.company is populated.
        # Rationale: a guest whose profile says "Acme Corp" but who checks in
        # with billing_responsibility='Guest' is explicitly a personal stay
        # — treating them as Corporate would over-count. The fallback only
        # catches upcoming bookings that haven't been checked in yet.
        ci = aliased(CheckInRecord)
        return (query
                .outerjoin(ci, ci.reservation_id == Reservation.id)
                .outerjoin(Guest, Guest.id == Reservation.guest_id)
                .filter(or_(
                    ci.billing_responsibility == 'Company',
                    and_(ci.id.is_(None),
                         Guest.company.isnot(None),
                         Guest.company != ''),
                ))
                .distinct())
    return query


# ---------------------------------------------------------------------------
# Inventory & business-date helpers
# ---------------------------------------------------------------------------

def _sellable_rooms_count() -> int:
    """Rooms that can actually be occupied tonight: active + sellable + not OOO.

    Delegates to the canonical occupancy_engine so the KPI Command Center
    shares the exact sellable denominator used by every other surface
    (the engine also screens Room.status, catching boolean/status drift).
    """
    from app.occupancy_engine import sellable_rooms
    return sellable_rooms()


def _days_in_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _overlap_nights(arr: date, dep: date, df: date, dt: date) -> int:
    """Nights of stay [arr, dep) that fall inside window [df, dt] (dt inclusive)."""
    if not arr or not dep:
        return 0
    start = max(arr, df)
    end   = min(dep, dt + timedelta(days=1))
    return max(0, (end - start).days)


# ---------------------------------------------------------------------------
# Night-audit resolver — cache per-request so repeated calls don't re-hit DB
# ---------------------------------------------------------------------------

def _audit_rows(date_from: date, date_to: date) -> dict:
    """Return {date → NightAuditLog} for completed rows in the window."""
    from app.models import NightAuditLog, db
    rows = (db.session.query(NightAuditLog)
            .filter(NightAuditLog.audit_date >= date_from,
                    NightAuditLog.audit_date <= date_to,
                    NightAuditLog.status == 'Completed')
            .all())
    return {r.audit_date: r for r in rows}


def _audit_coverage(audit_map: dict, date_from: date, date_to: date) -> str:
    """Classify audit coverage over a window: ``audit`` / ``mixed`` / ``live``.

    Used only for metadata reporting. Live aggregation still runs beneath —
    audits are preferred per-day where available (and never make the numbers
    contradict live code, because both are rate × nights accrual).
    """
    n_days = (date_to - date_from).days + 1
    n_audit = sum(1 for i in range(n_days)
                  if (date_from + timedelta(days=i)) in audit_map)
    if n_audit == 0:
        return 'live'
    if n_audit == n_days:
        return 'audit'
    return 'mixed'


# ---------------------------------------------------------------------------
# Core stay aggregator — one pass, returns revenue + rooms_sold + ALOS inputs
# ---------------------------------------------------------------------------

def _stay_aggregate(date_from: date, date_to: date, source_key: str) -> dict:
    """Walk reservations overlapping the window; bucket revenue + rooms_sold.

    Uses accrual (rate × nights-in-range). Single query scoped by source filter.

    Audit override rule: a ``NightAuditLog`` row's ``accrual_revenue`` is the
    full-day total across every source, so it can only substitute for the live
    per-day sum when the request is unfiltered (``source=ALL``). With a source
    filter active we always use live per-source aggregation to avoid leaking
    other sources' revenue into the filtered result.
    """
    from app.models import Reservation, db

    unfiltered = source_key in (None, '', 'ALL')
    audit_map  = _audit_rows(date_from, date_to) if unfiltered else {}

    q = (db.session.query(Reservation.arrival_date,
                          Reservation.departure_date,
                          Reservation.rate_per_night)
         .filter(Reservation.status.in_(('CheckedIn', 'CheckedOut')),
                 Reservation.arrival_date <= date_to,
                 Reservation.departure_date > date_from))
    q = apply_source_filter(q, source_key)
    stays = q.all()

    # Per-day accrual from live data; audit overrides where it exists and
    # the request is unfiltered.
    n_days = (date_to - date_from).days + 1
    live_rev = {date_from + timedelta(days=i): Decimal('0') for i in range(n_days)}
    rooms_sold_by_day = {d: 0 for d in live_rev}

    for arr, dep, rate in stays:
        if arr is None or dep is None:
            continue
        r = Decimal(rate or 0)
        # Bucket nights day-by-day so the audit-per-date override (when
        # applicable) can replace the live sum cleanly for that one day.
        day = max(arr, date_from)
        end = min(dep, date_to + timedelta(days=1))
        while day < end:
            if day in live_rev:
                live_rev[day] += r
                rooms_sold_by_day[day] += 1
            day += timedelta(days=1)

    total_rev = Decimal('0')
    for d in live_rev:
        aud = audit_map.get(d)
        if aud and (aud.accrual_revenue is not None) and Decimal(aud.accrual_revenue) > 0:
            total_rev += Decimal(aud.accrual_revenue)
        else:
            total_rev += live_rev[d]

    # rooms_sold is a room-NIGHTS metric. When the request is unfiltered
    # the canonical engine owns it (distinct room+night pairs, bridge-aware,
    # deduped). With a source filter active the engine — which has no
    # source filter — cannot scope it, so the per-source live count stands.
    if unfiltered:
        from app.occupancy_engine import occupied_room_nights as _engine_room_nights
        rooms_sold = _engine_room_nights(date_from, date_to)
    else:
        rooms_sold = sum(rooms_sold_by_day.values())
    sellable   = _sellable_rooms_count()
    rooms_avail = sellable * n_days
    return {
        'room_revenue':   float(total_rev),
        'rooms_sold':     rooms_sold,
        'rooms_avail':    rooms_avail,
        'n_days':         n_days,
        'sellable_rooms': sellable,
        'audit_coverage': _audit_coverage(audit_map, date_from, date_to) if unfiltered else 'live',
    }


# ---------------------------------------------------------------------------
# Other per-metric helpers
# ---------------------------------------------------------------------------

def _extras_accrual(date_from: date, date_to: date, source_key: str) -> float:
    """Σ ExtraCharge.amount over the window — excluding night-audit
    room_rent rows, which are already counted as room revenue via
    ReservationNightRate / rate_per_night. Without this filter the
    "Extras" KPI would double-count room revenue.
    """
    from app.models import ExtraCharge, Reservation, db
    q = (db.session.query(func.coalesce(func.sum(ExtraCharge.amount), 0))
         .filter(ExtraCharge.charge_date >= date_from,
                 ExtraCharge.charge_date <= date_to,
                 or_(ExtraCharge.charge_type.is_(None),
                     ExtraCharge.charge_type != 'room_rent')))
    if source_key and source_key not in ('ALL', '', None):
        sub = db.session.query(Reservation.id)
        sub = apply_source_filter(sub, source_key)
        q = q.filter(ExtraCharge.reservation_id.in_(sub))
    return float(q.scalar() or 0)


def _ota_receivable_cash(date_from: date, date_to: date, source_key: str) -> float:
    """Σ non-voided OTA-receivable payments in the window."""
    from app.models import Payment, PaymentMode, Reservation, db
    q = (db.session.query(func.coalesce(func.sum(Payment.amount), 0))
         .join(PaymentMode, PaymentMode.id == Payment.payment_mode_id)
         .filter(Payment.is_voided == False,                    # noqa: E712
                 Payment.payment_date >= date_from,
                 Payment.payment_date <= date_to,
                 PaymentMode.category == 'ota_receivable'))
    if source_key and source_key not in ('ALL', '', None):
        sub = db.session.query(Reservation.id)
        sub = apply_source_filter(sub, source_key)
        q = q.filter(Payment.reservation_id.in_(sub))
    return float(q.scalar() or 0)


def _outstanding_due_cash() -> float:
    """Σ positive balance over current in-house reservations (point-in-time)."""
    from app.models import Reservation
    from app.services import calculate_stay_amount
    total = 0.0
    for r in Reservation.query.filter(Reservation.status == 'CheckedIn').all():
        try:
            bal = float(calculate_stay_amount(r).get('balance') or 0)
        except Exception:
            bal = 0.0
        if bal > 0:
            total += bal
    return total


def _alos(date_from: date, date_to: date, source_key: str) -> float:
    """Avg nights over CheckedOut stays whose ``checked_out_at`` date is in range."""
    from app.models import Reservation, db
    q = (db.session.query(Reservation.arrival_date,
                          Reservation.departure_date,
                          Reservation.checked_out_at)
         .filter(Reservation.status == 'CheckedOut',
                 Reservation.checked_out_at.isnot(None)))
    q = apply_source_filter(q, source_key)
    total_nights = 0
    total_stays  = 0
    for arr, dep, co_at in q.all():
        co_date = co_at.date() if isinstance(co_at, datetime) else co_at
        if not co_date or co_date < date_from or co_date > date_to:
            continue
        if not arr or not dep:
            continue
        nights = (dep - arr).days
        if nights <= 0:
            continue
        total_nights += nights
        total_stays  += 1
    if total_stays == 0:
        return 0.0
    return round(total_nights / total_stays, 1)


# ---------------------------------------------------------------------------
# Per-scope snapshot (today / mtd / last_month / range)
# ---------------------------------------------------------------------------

def _snapshot(date_from: date, date_to: date, source_key: str) -> dict:
    """Full KPI block for a window. Used by both summary + quick-answers."""
    stay = _stay_aggregate(date_from, date_to, source_key)
    extras = _extras_accrual(date_from, date_to, source_key)
    room_rev = float(stay['room_revenue'])
    rooms_sold = stay['rooms_sold']
    rooms_avail = stay['rooms_avail']
    occ_pct = (rooms_sold / rooms_avail * 100) if rooms_avail > 0 else 0.0
    adr     = (room_rev / rooms_sold)          if rooms_sold  > 0 else 0.0
    revpar  = (room_rev / rooms_avail)         if rooms_avail > 0 else 0.0
    return {
        'room_revenue':    room_rev,
        'extras_revenue':  extras,
        'total_revenue':   room_rev + extras,
        'rooms_sold':      rooms_sold,
        'rooms_avail':     rooms_avail,
        'sellable_rooms':  stay['sellable_rooms'],
        'n_days':          stay['n_days'],
        'occupancy_pct':   occ_pct,
        'adr':             adr,
        'revpar':          revpar,
        'audit_coverage':  stay['audit_coverage'],
    }


# ---------------------------------------------------------------------------
# Monthly trend (6-month continuous) — one query, Python bucket
# ---------------------------------------------------------------------------

def _monthly_trend_continuous(business_date: date, mode: str, source_key: str,
                              monthly_target: float = 0.0) -> dict:
    """Monthly series: sales, occupancy, ADR, RevPAR, **target**, **variance**.

    ``target`` is the same configured monthly goal broadcast across every
    bucket (we don't store historical targets yet). ``variance`` = sales −
    target, per month, so the frontend can overlay target lines cheaply.
    """
    months = month_window(mode or '6m', business_date)
    labels, sales, occ, adr, revpar, variance = [], [], [], [], [], []
    target_arr = []
    for y, m in months:
        mfrom = date(y, m, 1)
        mto   = date(y, m, _days_in_month(y, m))
        # Never look beyond business_date — current month is naturally MTD.
        if mto > business_date:
            mto = business_date
        snap = _snapshot(mfrom, mto, source_key)
        labels.append(mfrom.strftime('%b %y'))
        sales.append(round(snap['room_revenue'], 0))
        occ.append(round(snap['occupancy_pct'], 1))
        adr.append(round(snap['adr'], 0))
        revpar.append(round(snap['revpar'], 0))
        target_arr.append(round(float(monthly_target), 0))
        variance.append(round(snap['room_revenue'] - float(monthly_target), 0))
    return {
        'mode':        mode or '6m',
        'labels':      labels,
        'sales':       sales,
        'occupancy':   occ,
        'adr':         adr,
        'revpar':      revpar,
        'target':      target_arr,
        'variance':    variance,
        'target_note': 'Using current monthly target (historical targets not stored)',
    }


def _monthly_trend_compare(business_date: date, source_key: str,
                           monthly_target: float = 0.0) -> dict:
    """Two-month side-by-side: last full month vs current (MTD).

    Caller displays these in a compact compare view. Labels are short-form
    month names; ALOS is included here even though the continuous trend
    doesn't bother with it (compare is richer by design).
    """
    last_month_first, last_month_last = (
        business_date.replace(day=1) - timedelta(days=1),
        business_date.replace(day=1) - timedelta(days=1),
    )
    last_first = last_month_first.replace(day=1)
    # Current month MTD window
    cur_first  = business_date.replace(day=1)
    cur_last   = business_date

    labels, sales, occ, adr, revpar, alos_arr, target_arr = [], [], [], [], [], [], []
    for mfrom, mto in ((last_first, last_month_last), (cur_first, cur_last)):
        snap = _snapshot(mfrom, mto, source_key)
        labels.append(mfrom.strftime('%b %y'))
        sales.append(round(snap['room_revenue'], 0))
        occ.append(round(snap['occupancy_pct'], 1))
        adr.append(round(snap['adr'], 0))
        revpar.append(round(snap['revpar'], 0))
        alos_arr.append(_alos(mfrom, mto, source_key))
        target_arr.append(round(float(monthly_target), 0))

    return {
        'labels':      labels,
        'sales':       sales,
        'occupancy':   occ,
        'adr':         adr,
        'revpar':      revpar,
        'alos':        alos_arr,
        'target':      target_arr,
        'target_note': 'Using current monthly target (historical targets not stored)',
        'note':        'Last full month vs current MTD',
    }


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

def build_data_quality(ctx: dict) -> dict:
    df: Optional[date] = ctx.get('date_from')
    dt: Optional[date] = ctx.get('date_to')
    if not df or not dt:
        return {'has_night_audit_data': False, 'data_source': 'live'}
    coverage = ctx.get('audit_coverage') or 'live'
    return {
        'has_night_audit_data': coverage in ('audit', 'mixed'),
        'data_source':          coverage,
    }


# ---------------------------------------------------------------------------
# Section builders — replace Phase-2 placeholders with real values
# ---------------------------------------------------------------------------

def build_quick_answers(ctx: dict) -> dict:
    """Nine cards of Section B.

    All target-driven cards now pull real values from the target engine
    (``get_monthly_targets`` + ``_compute_target_frame``) and fall back
    gracefully when a target isn't configured.
    """
    business_date: date = ctx['business_date']
    source = ctx.get('filters', {}).get('source') or 'ALL'
    property_id = ctx.get('filters', {}).get('property_id')

    today_snap = _snapshot(business_date, business_date, source)
    mtd_from   = business_date.replace(day=1)
    mtd_snap   = _snapshot(mtd_from, business_date, source)

    targets = get_monthly_targets(business_date, property_id)
    frame   = _compute_target_frame(targets['revenue'], business_date)
    mtd_actual    = mtd_snap['total_revenue']
    days_in_month = frame['days_in_month']
    days_elapsed  = frame['days_elapsed']
    remaining_days = frame['remaining_days']
    monthly_target = frame['monthly_target']
    pro_rated = frame['pro_rated_mtd_target']
    daily_target = frame['daily_target']

    surplus_deficit = mtd_actual - pro_rated
    required = _required_run_rate(monthly_target, mtd_actual, remaining_days)

    # Forecast (Phase 3 logic with early-month guard) + Phase 4 target compare.
    if days_elapsed < 3:
        forecast = mtd_actual
        forecast_sub_core = f'MTD ({days_elapsed}/{days_in_month}) — too early to project'
    elif days_elapsed > 0:
        forecast = mtd_actual / days_elapsed * days_in_month
        forecast_sub_core = f'Projected from MTD pace ({days_elapsed}/{days_in_month} days)'
    else:
        forecast = 0.0
        forecast_sub_core = '—'

    if monthly_target > 0:
        gap = forecast - monthly_target
        if gap > 0:
            gap_phrase = f'Forecast exceeds target by {_fmt_inr_short(abs(gap))}'
        elif gap < 0:
            gap_phrase = f'Forecast short by {_fmt_inr_short(abs(gap))}'
        else:
            gap_phrase = 'Forecast meets target exactly'
        forecast_sub = f'{forecast_sub_core} · {gap_phrase}'
    else:
        forecast_sub = forecast_sub_core

    # Surplus/Deficit sub reads like an operator instruction.
    if monthly_target <= 0:
        sd_sub = 'Set a monthly revenue target in Settings'
    elif surplus_deficit > 0:
        sd_sub = f'Ahead of pace by {_fmt_inr_short(abs(surplus_deficit))}'
    elif surplus_deficit < 0:
        sd_sub = f'Behind pace by {_fmt_inr_short(abs(surplus_deficit))}'
    else:
        sd_sub = 'On pace exactly'

    # Required run-rate sub: spell out the window.
    if monthly_target <= 0:
        rr_sub = 'Set a monthly revenue target in Settings'
    elif required <= 0 and remaining_days > 0:
        rr_sub = f'Target already achieved (₹0/day needed over {remaining_days} days)'
    elif remaining_days <= 0:
        rr_sub = 'End of month — no days remaining'
    else:
        rr_sub = f'Needed over next {remaining_days} day{"s" if remaining_days != 1 else ""}'

    # Occupancy target comparison (percentage points).
    occ_target = float(targets['occupancy'] or 0)
    def _occ_sub(occ_pct):
        if occ_target <= 0:
            return None
        diff = occ_pct - occ_target
        label = 'above' if diff > 0 else ('below' if diff < 0 else 'at')
        return f'Target {_fmt_pct(occ_target, 0)} · {abs(diff):.1f}pt {label}'

    occ_today_sub = _occ_sub(today_snap['occupancy_pct']) \
                    or f"{today_snap['rooms_sold']} / {today_snap['sellable_rooms']} rooms"
    occ_mtd_sub = _occ_sub(mtd_snap['occupancy_pct']) \
                    or f"{mtd_snap['rooms_sold']} / {mtd_snap['rooms_avail']} room-nights"

    # ── Phase 5: include "vs previous" sub when the composer passed a
    #    yesterday snapshot for today and a last-month-same-range snapshot
    #    for MTD. Always additive — never replaces target subtext.
    yesterday_snap = ctx.get('yesterday_snap')
    lm_same_range_snap = ctx.get('last_month_same_range_snap')

    today_sub_parts = [
        f"Room {_fmt_inr(today_snap['room_revenue'])} + Extras {_fmt_inr(today_snap['extras_revenue'])}"
    ]
    if yesterday_snap is not None:
        d = _compute_delta(today_snap['total_revenue'], yesterday_snap['total_revenue'])
        if d['direction'] != 'flat':
            word = 'Up' if d['direction'] == 'up' else 'Down'
            today_sub_parts.append(
                f'{word} {_fmt_inr_short(abs(d["value"]))} vs yesterday')

    mtd_sub_core = (f'{days_elapsed} of {days_in_month} days · '
                    f'vs full target {_safe_progress_pct(mtd_actual, monthly_target)}%'
                    if monthly_target > 0
                    else f'{days_elapsed} day{"s" if days_elapsed != 1 else ""} elapsed of {days_in_month}')
    if lm_same_range_snap is not None:
        d = _compute_delta(mtd_actual, lm_same_range_snap['total_revenue'])
        if d['direction'] == 'flat':
            mtd_sub_compare = 'same as last month'
        else:
            word = 'up' if d['direction'] == 'up' else 'down'
            mtd_sub_compare = f'{word} {_fmt_inr_short(abs(d["value"]))} vs last month'
        mtd_sub = f'{mtd_sub_core} · {mtd_sub_compare}'
    else:
        mtd_sub = mtd_sub_core

    return {
        'today_sales': _money(
            value=today_snap['total_revenue'],
            display=_fmt_inr(today_snap['total_revenue']),
            sub=' · '.join(today_sub_parts),
        ),
        'mtd_sales': _money(
            value=mtd_actual,
            display=_fmt_inr(mtd_actual),
            sub=mtd_sub,
        ),
        'occupancy_today': _metric(
            value=today_snap['occupancy_pct'],
            display=_fmt_pct(today_snap['occupancy_pct']),
            sub=occ_today_sub,
        ),
        'occupancy_mtd': _metric(
            value=mtd_snap['occupancy_pct'],
            display=_fmt_pct(mtd_snap['occupancy_pct']),
            sub=occ_mtd_sub,
        ),
        'today_target': _money(
            value=daily_target,
            display=_fmt_inr(daily_target),
            sub=('Daily target from monthly goal'
                 if monthly_target > 0 else 'No monthly target configured'),
        ),
        'mtd_target': _money(
            value=pro_rated,
            display=_fmt_inr(pro_rated),
            sub=(f'Pro-rated for {days_elapsed}/{days_in_month} days · '
                 f'full target {_fmt_inr_short(monthly_target)}'
                 if monthly_target > 0 else 'No monthly target configured'),
        ),
        'surplus_deficit': _money(
            value=surplus_deficit,
            display=_fmt_inr(surplus_deficit),
            sub=sd_sub,
        ),
        'required_run_rate': _money(
            value=required,
            display=_fmt_inr(required),
            sub=rr_sub,
        ),
        'forecast_month_end': _money(
            value=forecast,
            display=_fmt_inr(forecast),
            sub=forecast_sub,
        ),
    }


def build_summary_cards(ctx: dict) -> dict:
    """Six cards of Section C — scoped to the user-selected range (metadata)."""
    df: date = ctx['date_from']
    dt: date = ctx['date_to']
    source = ctx.get('filters', {}).get('source') or 'ALL'
    snap = _snapshot(df, dt, source)
    outstanding = _outstanding_due_cash()
    return {
        'adr':     _money(value=snap['adr'],     display=_fmt_inr(snap['adr']),
                          sub='Avg room rate (range)'),
        'revpar':  _money(value=snap['revpar'],  display=_fmt_inr(snap['revpar']),
                          sub='Per available room'),
        'alos':    _metric(value=_alos(df, dt, source),
                           display=_fmt_nights(_alos(df, dt, source)),
                           sub='Checked-out stays in range'),
        'rooms_sold':      _metric(value=snap['rooms_sold'],
                                   display=_fmt_count(snap['rooms_sold']),
                                   sub='Room-nights sold'),
        'rooms_available': _metric(value=snap['rooms_avail'],
                                   display=_fmt_count(snap['rooms_avail']),
                                   sub=f"{snap['sellable_rooms']} rooms × {snap['n_days']} days"),
        'outstanding_due': _money(value=outstanding,
                                   display=_fmt_inr(outstanding),
                                   sub='In-house balances (live)', tag='Cash'),
    }


def build_sales_vs_target(ctx: dict) -> dict:
    """Section D — per-scope {actual, target, variance, progress_pct}.

    MTD scope additionally carries:
      - ``full_month_target``           — the unscaled monthly goal.
      - ``full_month_progress_pct``     — MTD actual / monthly target × 100.

    ``today.target`` is the daily target (monthly / days-in-month).
    ``mtd.target`` is the pro-rated MTD target (on-pace view).
    ``last_month.target`` is 0 (no historical target archive yet — see
    known-limitations in the Phase-4 deliverable).
    """
    business_date: date = ctx['business_date']
    source = ctx.get('filters', {}).get('source') or 'ALL'
    property_id = ctx.get('filters', {}).get('property_id')

    today_snap = _snapshot(business_date, business_date, source)
    mtd_from   = business_date.replace(day=1)
    mtd_snap   = _snapshot(mtd_from, business_date, source)
    lm_from, lm_to = _last_month_window(business_date)
    lm_snap   = _snapshot(lm_from, lm_to, source)

    targets = get_monthly_targets(business_date, property_id)
    frame   = _compute_target_frame(targets['revenue'], business_date)
    monthly_target = frame['monthly_target']
    daily_target   = frame['daily_target']
    pro_rated      = frame['pro_rated_mtd_target']

    def _scope(actual_value: float, target_value: float, sub_hint: str) -> dict:
        variance = float(actual_value or 0) - float(target_value or 0)
        return {
            'actual': _money(value=actual_value, display=_fmt_inr(actual_value),
                             sub='Accrual', tag='Accrual'),
            'target': _money(value=target_value, display=_fmt_inr(target_value),
                             sub=sub_hint, tag='Target'),
            'variance': _variance(value=variance, display=_fmt_inr(variance),
                                  direction=_variance_direction(variance),
                                  currency='INR'),
            'progress_pct': _safe_progress_pct(actual_value, target_value),
        }

    today_sub = ('Daily target from monthly goal'
                 if monthly_target > 0 else 'No monthly target configured')
    mtd_sub = (f'Pro-rated for {frame["days_elapsed"]}/{frame["days_in_month"]} days'
               if monthly_target > 0 else 'No monthly target configured')
    # Deliberately avoid rendering "₹0" as if it were a real configured target —
    # users shouldn't think the property's last-month goal was zero.
    lm_sub = 'Historical target not available'

    mtd_scope = _scope(mtd_snap['total_revenue'], pro_rated, mtd_sub)
    # Dual-view: expose the un-prorated target + full-month achievement %
    # so strategic users can read both "on pace?" and "how close to goal?".
    mtd_scope['full_month_target'] = _money(
        value=monthly_target, display=_fmt_inr(monthly_target),
        sub='Configured monthly revenue goal',
        tag='Target')
    mtd_scope['full_month_progress_pct'] = _safe_progress_pct(
        mtd_snap['total_revenue'], monthly_target)

    # Phase 5 additive sub: "vs last month: +₹1.2L · vs last year: -₹80K".
    # Written only when the composer supplied the comparison snapshots so
    # this builder stays usable in tests with ctx lacking them.
    lm_snap_same  = ctx.get('last_month_same_range_snap')
    ly_snap_same  = ctx.get('last_year_same_range_snap')
    compare_bits = []
    if lm_snap_same is not None:
        d = _compute_delta(mtd_snap['total_revenue'], lm_snap_same['total_revenue'])
        sign = '+' if d['direction'] == 'up' else ('-' if d['direction'] == 'down' else '±')
        compare_bits.append(f'vs last month: {sign}{_fmt_inr_short(abs(d["value"]))}')
    if ly_snap_same is not None:
        d = _compute_delta(mtd_snap['total_revenue'], ly_snap_same['total_revenue'])
        sign = '+' if d['direction'] == 'up' else ('-' if d['direction'] == 'down' else '±')
        compare_bits.append(f'vs last year: {sign}{_fmt_inr_short(abs(d["value"]))}')
    if compare_bits:
        # Attach to the MTD target sub (spec: "use subtext, do not redesign structure").
        mtd_scope['target']['sub'] = (mtd_scope['target']['sub'] or '') + ' · ' + ' · '.join(compare_bits)

    return {
        'today':      _scope(today_snap['total_revenue'], daily_target, today_sub),
        'mtd':        mtd_scope,
        'last_month': _scope(lm_snap['total_revenue'], 0.0, lm_sub),
    }


def _last_month_window(business_date: date):
    first_this = business_date.replace(day=1)
    last_prev  = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, last_prev


def build_monthly_trend(ctx: dict) -> dict:
    """Section E — continuous trend + two-month compare (Phase 5)."""
    business_date: date = ctx['business_date']
    source = ctx.get('filters', {}).get('source') or 'ALL'
    mode = ctx.get('trend_mode') or '6m'
    property_id = ctx.get('filters', {}).get('property_id')
    monthly_target = get_monthly_targets(business_date, property_id)['revenue']

    cont    = _monthly_trend_continuous(business_date, mode, source, monthly_target)
    compare = _monthly_trend_compare(business_date, source, monthly_target)
    return {
        'trend_continuous': cont,
        'trend_compare':    compare,
    }


def build_range_revenue(ctx: dict) -> dict:
    """Section F — metrics scoped to the user-selected range."""
    df: date = ctx['date_from']
    dt: date = ctx['date_to']
    source = ctx.get('filters', {}).get('source') or 'ALL'
    snap = _snapshot(df, dt, source)
    ota_recv = _ota_receivable_cash(df, dt, source)
    return {
        'occupancy_range': _metric(value=snap['occupancy_pct'],
                                   display=_fmt_pct(snap['occupancy_pct']),
                                   sub=f"{snap['rooms_sold']} / {snap['rooms_avail']} room-nights"),
        'room_revenue':    _money(value=snap['room_revenue'],
                                   display=_fmt_inr(snap['room_revenue']),
                                   sub='Rate × nights (range)', tag='Accrual'),
        'extras_revenue':  _money(value=snap['extras_revenue'],
                                   display=_fmt_inr(snap['extras_revenue']),
                                   sub='F&B / Laundry / Minibar etc.', tag='Accrual'),
        'ota_receivable':  _money(value=ota_recv,
                                   display=_fmt_inr(ota_recv),
                                   sub='Posted to OTA heads (range)', tag='Cash'),
    }


def build_metadata(ctx: dict,
                   error: bool = False,
                   message: Optional[str] = None) -> dict:
    bd:        Optional[date] = ctx.get('business_date')
    date_from: Optional[date] = ctx.get('date_from')
    date_to:   Optional[date] = ctx.get('date_to')
    return {
        'error':         error,
        'message':       message,
        'business_date': bd.isoformat() if bd else None,
        'date_from':     date_from.isoformat() if date_from else None,
        'date_to':       date_to.isoformat() if date_to else None,
        'preset':        ctx.get('preset'),
        'generated_at':  datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'phase':         '3-kpi-engine',
        'data_quality':  build_data_quality(ctx),
    }


# ---------------------------------------------------------------------------
# Top-level composer
# ---------------------------------------------------------------------------

_MAX_RANGE_DAYS = 365


def build_command_center_payload(filters: dict,
                                 business_date: date) -> dict:
    """Compose the full Command Center JSON. Never raises."""
    # Resolve date range. Error path returns early with empty-state banner.
    rr: ResolvedRange = resolve_range(
        filters.get('preset') or 'today',
        business_date,
        filters.get('date_from'),
        filters.get('date_to'),
    )
    ctx: dict = {
        'filters':       filters,
        'business_date': business_date,
        'date_from':     rr.date_from,
        'date_to':       rr.date_to,
        'preset':        rr.preset,
        'trend_mode':    filters.get('trend_mode') or '6m',
    }
    filters_echo = {
        'property_id': filters.get('property_id'),
        'preset':      rr.preset,
        'date_from':   rr.date_from.isoformat() if rr.date_from else None,
        'date_to':     rr.date_to.isoformat()   if rr.date_to   else None,
        'compare':     bool(filters.get('compare')),
        'source':      filters.get('source') or 'ALL',
        'trend_mode':  ctx['trend_mode'],
    }

    # Hard guard — clamp pathologically long ranges before we start scanning.
    if rr.date_from and rr.date_to:
        span = (rr.date_to - rr.date_from).days + 1
        if span > _MAX_RANGE_DAYS:
            msg = f'Range too long ({span} days). Maximum supported is {_MAX_RANGE_DAYS} days.'
            return _error_payload(ctx, filters_echo, msg)

    if rr.error:
        return _error_payload(ctx, filters_echo, rr.error)

    try:
        # Pre-compute stay aggregate once for the range so builders can read
        # its audit coverage into metadata without re-hitting the DB.
        source = filters.get('source') or 'ALL'
        range_snap = _snapshot(rr.date_from, rr.date_to, source) if rr.date_from else None
        if range_snap:
            ctx['audit_coverage'] = range_snap['audit_coverage']

        # ── Phase 5 — comparison gating ────────────────────────────────
        # Per the refinement: comparison is opt-in via the `compare` filter.
        # When compare=False we still include the JSON key (empty block) so
        # the frontend can always read payload.comparison, but we skip the
        # extra snapshots and leave subs target-only.
        compare_on = bool(filters.get('compare'))
        if compare_on:
            y_date = business_date - timedelta(days=1)
            ctx['yesterday_snap'] = _snapshot(y_date, y_date, source)

            mtd_first = business_date.replace(day=1)
            mtd_day   = business_date.day
            lm_cw     = comparison_range('mtd', business_date, mtd_first, business_date)
            if lm_cw.previous_from and lm_cw.previous_to:
                ctx['last_month_same_range_snap'] = _snapshot(
                    lm_cw.previous_from, lm_cw.previous_to, source)
            # Same-month-last-year (same partial day-range)
            ly_year = business_date.year - 1
            try:
                ly_first = business_date.replace(year=ly_year, day=1)
                ly_to_day = min(mtd_day, _days_in_month(ly_year, business_date.month))
                ly_to    = date(ly_year, business_date.month, ly_to_day)
                ctx['last_year_same_range_snap'] = _snapshot(ly_first, ly_to, source)
            except Exception:
                pass  # non-critical; sub just skipped

        body = {
            'quick_answers':   build_quick_answers(ctx),
            'summary_cards':   build_summary_cards(ctx),
            'sales_vs_target': build_sales_vs_target(ctx),
            'monthly_trend':   build_monthly_trend(ctx),
            'range_revenue':   build_range_revenue(ctx),
            'comparison':      (build_comparison(ctx) if compare_on
                                else {'type':     'disabled',
                                      'current':  {}, 'previous': {}, 'delta': {},
                                      'note':     'Toggle Compare in filters to enable'}),
        }

        # ── Governance section — credit exposure / overdue / overrides ──
        # Computed BEFORE the alert engine so the governance detector can
        # read it from body. Wrapped defensively — failure here must never
        # break the payload.
        try:
            body['governance'] = _build_governance_block(ctx)
        except Exception:
            logger.exception('governance block build failed')
            body['governance'] = {
                'credit_outstanding_total': 0.0,
                'credit_outstanding_count': 0,
                'overdue_30_count':         0,
                'overdue_30_amount':        0.0,
                'overrides_24h_count':      0,
            }

        # ── Phase 7 — Alert + Root-Cause Engine ─────────────────────────
        # Runs AFTER the KPI body is built so detectors read already-computed
        # sections instead of re-querying. Engine never raises — on any
        # internal failure it returns an empty alerts block so the payload
        # still ships.
        try:
            from app.alert_engine import build_alerts, empty_alerts_block
            body.update(build_alerts(ctx, body))
        except Exception:
            logger.exception('alert engine failed')
            body.update(empty_alerts_block())
    except Exception as exc:
        logger.exception('build_command_center_payload failed during aggregation')
        return _error_payload(ctx, filters_echo, f'Aggregation error: {exc}')

    # Debug payload — surfaces only when caller passed debug=True.
    # calculation_summary makes occupancy-%-looks-wrong bugs diagnosable at a
    # glance: if rooms_sold/rooms_available looks absurd for the range, the
    # root cause is right there in the response.
    debug_block = None
    if filters.get('debug'):
        calc_summary = None
        if range_snap:
            calc_summary = {
                'rooms_sold':      range_snap['rooms_sold'],
                'rooms_available': range_snap['rooms_avail'],
                'days_count':      range_snap['n_days'],
                'sellable_rooms':  range_snap['sellable_rooms'],
                'room_revenue':    range_snap['room_revenue'],
                'extras_revenue':  range_snap['extras_revenue'],
                'occupancy_pct':   round(range_snap['occupancy_pct'], 2),
                'adr':             round(range_snap['adr'], 2),
                'revpar':          round(range_snap['revpar'], 2),
            }
        # Target diagnostics — recompute against MTD so any mismatch between
        # UI cards and raw numbers is spotted in one round-trip.
        try:
            _targets  = get_monthly_targets(business_date, filters.get('property_id'))
            _frame    = _compute_target_frame(_targets['revenue'], business_date)
            _mtd_snap = _snapshot(business_date.replace(day=1), business_date, source)
            _mtd_actual = _mtd_snap['total_revenue']
            target_debug = {
                'monthly_revenue_target':   _frame['monthly_target'],
                'monthly_occupancy_target': _targets['occupancy'],
                'days_in_month':            _frame['days_in_month'],
                'days_elapsed':             _frame['days_elapsed'],
                'remaining_days':           _frame['remaining_days'],
                'daily_target':             _frame['daily_target'],
                'pro_rated_mtd_target':     _frame['pro_rated_mtd_target'],
                'mtd_actual':               _mtd_actual,
                'remaining_target':         max(0.0, _frame['monthly_target'] - _mtd_actual),
                'required_run_rate':        _required_run_rate(
                    _frame['monthly_target'], _mtd_actual, _frame['remaining_days']),
                'mtd_vs_full_pct':          _safe_progress_pct(
                    _mtd_actual, _frame['monthly_target']),
                'mtd_variance_vs_prorated': _mtd_actual - _frame['pro_rated_mtd_target'],
            }
        except Exception as exc:  # never crash the debug path
            logger.warning('target_debug failed: %s', exc)
            target_debug = {'error': str(exc)}

        # Comparison diagnostics — echoes the chosen comparison window and
        # the raw deltas so "vs last month" disputes are resolvable in one GET.
        comparison_debug = {}
        try:
            comp_block = body.get('comparison') or {}
            comp_current  = comp_block.get('current_range') or {}
            comp_previous = comp_block.get('previous_range') or {}
            comp_delta    = comp_block.get('delta') or {}
            comparison_debug = {
                'comparison_type': comp_block.get('type'),
                'current_range':   f"{comp_current.get('from')} → {comp_current.get('to')}",
                'previous_range':  f"{comp_previous.get('from')} → {comp_previous.get('to')}",
                'sales_delta':     comp_delta.get('sales'),
                'adr_delta':       comp_delta.get('adr'),
                'occupancy_delta': comp_delta.get('occupancy'),
            }
        except Exception as exc:
            comparison_debug = {'error': str(exc)}

        debug_block = {
            'range_days':          range_snap['n_days'] if range_snap else None,
            'audit_coverage':      range_snap['audit_coverage'] if range_snap else None,
            'sellable_rooms':      range_snap['sellable_rooms'] if range_snap else None,
            'source_filter':       source,
            'calculation_summary': calc_summary,
            'target_debug':        target_debug,
            'comparison_debug':    comparison_debug,
            'note':                ('Phase 5 comparison engine active. Audit rows still override '
                                    'daily accrual only when source=ALL.'),
        }

    return {
        'success':  True,
        'metadata': build_metadata(ctx),
        'filters':  filters_echo,
        **body,
        'empty_state': {'is_empty': False, 'message': ''},
        **({'debug': debug_block} if debug_block else {}),
    }


def _error_payload(ctx: dict, filters_echo: dict, message: str) -> dict:
    """Structured failure — keeps every section key present so the UI doesn't crash."""
    # Zero-valued payload (same shape as success) so downstream JS never hits undefined.
    ctx_with_zero_coverage = {**ctx, 'audit_coverage': 'live'}
    zero_ctx = ctx_with_zero_coverage
    try:
        zero_body = {
            'quick_answers':   _zero_quick_answers(),
            'summary_cards':   _zero_summary_cards(),
            'sales_vs_target': _zero_sales_vs_target(),
            'monthly_trend':   {'trend_continuous': {'mode': ctx.get('trend_mode') or '6m',
                                                     'labels': [], 'sales': [],
                                                     'occupancy': [], 'adr': [], 'revpar': [],
                                                     'target': [], 'variance': []},
                                'trend_compare':    {'labels': [], 'sales': [],
                                                     'occupancy': [], 'adr': [], 'revpar': [],
                                                     'alos': [], 'target': [],
                                                     'note': 'Error path'}},
            'range_revenue':   _zero_range_revenue(),
            'comparison':      {'type': 'none', 'current': {}, 'previous': {}, 'delta': {}},
            # Phase 7 — alert block in the error path too, so the frontend
            # can always read payload.alerts / alerts_summary / root_cause_summary.
            'alerts':              [],
            'alerts_summary':      {'red_count': 0, 'amber_count': 0,
                                    'persistent_count': 0, 'top_alert_title': None},
            'root_cause_summary':  [],
        }
    except Exception:
        zero_body = {'quick_answers': {}, 'summary_cards': {},
                     'sales_vs_target': {}, 'monthly_trend': {}, 'range_revenue': {},
                     'alerts': [], 'alerts_summary': {'red_count': 0, 'amber_count': 0,
                                                      'persistent_count': 0,
                                                      'top_alert_title': None},
                     'root_cause_summary': []}
    return {
        'success':  False,
        'metadata': build_metadata(zero_ctx, error=True, message=message),
        'filters':  filters_echo,
        **zero_body,
        'empty_state': {'is_empty': True, 'message': message},
    }


# Empty-scaffold builders — used only in the error path so the frontend has
# every key it expects even when we never got to real aggregation.
def _zero_quick_answers():
    return {k: _money(display=_fmt_inr(0), sub='—')
            for k in ('today_sales', 'mtd_sales', 'today_target', 'mtd_target',
                      'surplus_deficit', 'required_run_rate', 'forecast_month_end')
           } | {
            'occupancy_today': _metric(display=_fmt_pct(0), sub='—'),
            'occupancy_mtd':   _metric(display=_fmt_pct(0), sub='—'),
           }


def _zero_summary_cards():
    return {
        'adr':             _money(display=_fmt_inr(0), sub='—'),
        'revpar':          _money(display=_fmt_inr(0), sub='—'),
        'alos':            _metric(display=_fmt_nights(0), sub='—'),
        'rooms_sold':      _metric(display=_fmt_count(0), sub='—'),
        'rooms_available': _metric(display=_fmt_count(0), sub='—'),
        'outstanding_due': _money(display=_fmt_inr(0), sub='—', tag='Cash'),
    }


def _zero_sales_vs_target():
    def _zero_scope(with_full_month=False):
        scope = {
            'actual':   _money(display=_fmt_inr(0), sub='—', tag='Accrual'),
            'target':   _money(display=_fmt_inr(0), sub='—', tag='Target'),
            'variance': _variance(display=_fmt_inr(0), currency='INR'),
            'progress_pct': 0,
        }
        if with_full_month:
            scope['full_month_target'] = _money(display=_fmt_inr(0), sub='—', tag='Target')
            scope['full_month_progress_pct'] = 0
        return scope
    return {
        'today':      _zero_scope(),
        'mtd':        _zero_scope(with_full_month=True),
        'last_month': _zero_scope(),
    }


def _zero_range_revenue():
    return {
        'occupancy_range': _metric(display=_fmt_pct(0), sub='—'),
        'room_revenue':    _money(display=_fmt_inr(0), sub='—', tag='Accrual'),
        'extras_revenue':  _money(display=_fmt_inr(0), sub='—', tag='Accrual'),
        'ota_receivable':  _money(display=_fmt_inr(0), sub='—', tag='Cash'),
    }
