"""
Alert + Root-Cause Engine — Phase 7
====================================

Deterministic (no ML / no LLM) diagnostic layer over the KPI Command Center
payload. Given the already-computed ``ctx`` + ``body`` from
``kpi_command_center.build_command_center_payload``, returns three extra
sections that answer:

    * What is wrong?        → ``alerts``           (list of structured issues)
    * How urgent is it?     → severity ``red`` / ``amber`` / ``green``
    * Why is it wrong?      → ``root_cause_summary`` (short prose)
    * What should we do?    → ``suggested_actions`` on each alert

Design rules
------------
1. **Never raise.** The alert engine is a decorator on top of the payload —
   if a rule blows up, the payload still ships with alerts=[] for that rule.
2. **No heavy queries.** Detectors consume the KPI ``body`` that was just
   computed. Two small helpers (channel mix, cancellation rate) do a single
   extra query each and are individually wrapped in try/except so schema
   drift never breaks the payload.
3. **Deterministic rules only.** No ML, no LLM, no probability. A rule
   either fires or it doesn't based on numeric comparisons.
4. **Thresholds are constants.** Centralised in ``ALERT_THRESHOLDS`` so a
   future phase can move them into Settings without touching call-sites.
5. **Skip cleanly when data is missing.** A rule whose inputs are not
   available just doesn't contribute an alert — no "N/A" noise.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from flask import current_app
from sqlalchemy import func

from app.models import PaymentMode, Reservation, db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds — centralised so ops can tune without hunting through logic
# ---------------------------------------------------------------------------

ALERT_THRESHOLDS = {
    # Revenue gap vs target (percent; negative = behind). Red = urgent.
    'revenue_red_pct':                 -15,
    'revenue_amber_pct':                -5,
    # Occupancy gap vs target (percentage points, NOT %).
    'occupancy_gap_red_pts':           -10,
    'occupancy_gap_amber_pts':          -5,
    # ADR/RevPAR period-over-period movement.
    'adr_drop_red_pct':                -10,
    'adr_drop_amber_pct':               -5,
    'revpar_drop_red_pct':             -10,
    'revpar_drop_amber_pct':            -5,
    # Channel mix — share expressed as 0-100.
    'ota_dependency_red_pct':           60,
    'ota_dependency_amber_pct':         45,
    'direct_share_low_red_pct':         10,   # direct share below this = red
    'direct_share_low_amber_pct':       20,
    # Collections.
    'outstanding_due_red':          100000,   # ₹ — in-house balance
    'outstanding_due_amber':         50000,
    'ota_receivable_red':           200000,   # ₹ — posted OTA receivable in range
    'ota_receivable_amber':         100000,
    # Behaviour.
    'cancellation_rate_red_pct':        15,
    'cancellation_rate_amber_pct':       8,
    # Room-type mix.
    'premium_idle_red_pct':             25,   # premium occupancy below this = red
    'premium_idle_amber_pct':           45,
    # Forecast miss (% of full monthly target).
    'forecast_miss_red_pct':           -15,
    'forecast_miss_amber_pct':          -5,
    # Run-rate vs today's pace — "unrealistic" threshold.
    'run_rate_unrealistic_ratio':     1.5,
    # Governance — Individual Credit exposure (₹, current open receivable).
    'credit_exposure_red':           150000,
    'credit_exposure_amber':          50000,
    # Governance — Overdue (>30d) receivable count.
    'overdue_credit_red_count':            3,
    'overdue_credit_amber_count':          1,
    # Governance — Admin audit-lock overrides in trailing 24h.
    'override_24h_red_count':              5,
    'override_24h_amber_count':            2,
}


# ---------------------------------------------------------------------------
# Owner mapping — who should act on each alert code
# ---------------------------------------------------------------------------

OWNER_MAP = {
    # Revenue / occupancy / pricing → Manager
    'FORECAST_BELOW_TARGET':        'Manager',
    'MTD_REVENUE_BELOW_PACE':       'Manager',
    'TODAY_SALES_BELOW_TARGET':     'Manager',
    'OCCUPANCY_BELOW_TARGET':       'Manager',
    'ADR_BELOW_TARGET':             'Manager',
    'REVPAR_BELOW_TARGET':          'Manager',
    # Channels → Sales / Manager
    'HIGH_OTA_DEPENDENCY':          'Sales / Manager',
    'DIRECT_SHARE_TOO_LOW':         'Sales / Manager',
    # Collections → Accountant
    'OUTSTANDING_DUE_HIGH':         'Accountant',
    'OTA_RECEIVABLE_HIGH':          'Accountant',
    # Room mix → Front Office / Manager
    'PREMIUM_ROOM_UNDERSOLD':       'Front Office / Manager',
    # Behaviour → Manager
    'CANCELLATION_RATE_HIGH':       'Manager',
    'DISCOUNT_LEAKAGE_HIGH':        'Manager',
    # Run-rate — same urgency family as MTD/forecast
    'RUN_RATE_UNREALISTIC':         'Manager',
    # Governance / Receivable health → Accountant + Manager
    'HIGH_CREDIT_EXPOSURE':         'Accountant / Manager',
    'OVERDUE_CREDIT_RISK':          'Accountant / Manager',
    'FREQUENT_ADMIN_OVERRIDES':     'Admin',
}


# ---------------------------------------------------------------------------
# Priority — lower rank = acted on first
# ---------------------------------------------------------------------------

PRIORITY_RANK = {
    'FORECAST_BELOW_TARGET':        1,
    'RUN_RATE_UNREALISTIC':         2,
    'MTD_REVENUE_BELOW_PACE':       3,
    'TODAY_SALES_BELOW_TARGET':     4,
    'OCCUPANCY_BELOW_TARGET':       5,
    'ADR_BELOW_TARGET':             6,
    'REVPAR_BELOW_TARGET':          7,
    'HIGH_OTA_DEPENDENCY':          8,
    'DIRECT_SHARE_TOO_LOW':         9,
    'OUTSTANDING_DUE_HIGH':        10,
    'OTA_RECEIVABLE_HIGH':         11,
    'PREMIUM_ROOM_UNDERSOLD':      12,
    'CANCELLATION_RATE_HIGH':      13,
    'DISCOUNT_LEAKAGE_HIGH':       14,
    # Governance — sit just below collections in priority
    'OVERDUE_CREDIT_RISK':         15,
    'HIGH_CREDIT_EXPOSURE':        16,
    'FREQUENT_ADMIN_OVERRIDES':    17,
}

# Within the same severity, red beats amber beats green.
_SEVERITY_RANK = {'red': 0, 'amber': 1, 'green': 2}


# ---------------------------------------------------------------------------
# Alert memory store — JSON file in instance/ (single-property PMS)
# ---------------------------------------------------------------------------
# Purpose: track first-seen / last-seen per alert code so the UI can show
# "(3 days)" next to persistent issues and suppress repeated noise.
#
# Shape (versioned for forward compat):
#   {
#     "version": 1,
#     "alerts": {
#       "MTD_REVENUE_BELOW_PACE": {
#         "first_seen": "2026-04-18",
#         "last_seen":  "2026-04-20",
#         "days_active": 3
#       },
#       ...
#     }
#   }
#
# Notes:
#   - File-based (not DB) so no migration is required. Matches the project's
#     pattern of single-property SQLite installs.
#   - Swap-in-place design: if a future phase wants a DB-backed store,
#     `AlertMemory` is the single point to replace.
#   - Every I/O call is wrapped in try/except — file corruption must never
#     break the payload.

_ALERT_MEMORY_FILENAME = 'alert_memory.json'
# A code is "persistent" once it has been seen on N+ distinct days.
PERSISTENT_DAYS_THRESHOLD = 3
# Purge entries not seen in this many days to keep the file small.
_MEMORY_STALE_DAYS = 14


class AlertMemory:
    """Read-modify-write wrapper around ``instance/alert_memory.json``.

    Intended lifecycle: build one instance per payload request, ``load()``,
    ``mark(code, today)`` for every fired alert, then ``save()`` once at
    the end. The file is small (dozens of entries max) and all operations
    are O(n) over the map.
    """

    def __init__(self):
        self._data: dict = {'version': 1, 'alerts': {}}
        self._path: Optional[str] = None
        self._dirty = False

    @staticmethod
    def _resolve_path() -> Optional[str]:
        try:
            root = current_app.root_path
        except RuntimeError:
            return None
        # instance/ lives one level up from app/
        instance_dir = os.path.join(root, '..', 'instance')
        try:
            os.makedirs(instance_dir, exist_ok=True)
        except OSError:
            return None
        return os.path.realpath(os.path.join(instance_dir, _ALERT_MEMORY_FILENAME))

    def load(self) -> 'AlertMemory':
        self._path = self._resolve_path()
        if not self._path or not os.path.isfile(self._path):
            return self
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if isinstance(raw, dict) and isinstance(raw.get('alerts'), dict):
                # Keep only entries with valid shape.
                clean = {}
                for code, entry in raw['alerts'].items():
                    if not isinstance(entry, dict):
                        continue
                    if not entry.get('first_seen') or not entry.get('last_seen'):
                        continue
                    clean[str(code)] = {
                        'first_seen':  str(entry['first_seen']),
                        'last_seen':   str(entry['last_seen']),
                        'days_active': int(entry.get('days_active') or 1),
                    }
                self._data = {'version': 1, 'alerts': clean}
        except Exception as exc:
            logger.warning('alert memory load failed (starting fresh): %s', exc)
            self._data = {'version': 1, 'alerts': {}}
        return self

    def _count_days(self, first_seen: str, today: date) -> int:
        """Days from first_seen up to today inclusive. We use calendar days
        (not firing count) so a gap-day doesn't inflate the counter."""
        try:
            fd = date.fromisoformat(first_seen)
        except ValueError:
            return 1
        return max(1, (today - fd).days + 1)

    def mark(self, code: str, today: date) -> dict:
        """Record a sighting of ``code`` for ``today`` and return the
        memory entry (creating it if new)."""
        iso = today.isoformat()
        entry = self._data['alerts'].get(code)
        if not entry:
            entry = {'first_seen': iso, 'last_seen': iso, 'days_active': 1}
        else:
            # Preserve first_seen; refresh last_seen; recompute days_active
            # so a returning alert after a gap has accurate age.
            entry['last_seen']   = iso
            entry['days_active'] = self._count_days(entry['first_seen'], today)
        self._data['alerts'][code] = entry
        self._dirty = True
        return entry

    def purge_stale(self, today: date) -> None:
        """Drop entries whose last_seen is older than _MEMORY_STALE_DAYS.
        Called when saving so the file doesn't grow indefinitely."""
        alerts = self._data.get('alerts') or {}
        cutoff = today - timedelta(days=_MEMORY_STALE_DAYS)
        removed = []
        for code, entry in list(alerts.items()):
            try:
                if date.fromisoformat(entry['last_seen']) < cutoff:
                    removed.append(code)
                    alerts.pop(code, None)
            except ValueError:
                alerts.pop(code, None)
                removed.append(code)
        if removed:
            self._dirty = True

    def save(self) -> None:
        if not self._dirty or not self._path:
            return
        try:
            tmp = self._path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning('alert memory save failed: %s', exc)


# ---------------------------------------------------------------------------
# Light helpers (defensive; never raise to the payload composer)
# ---------------------------------------------------------------------------

def _fmt_inr(n) -> str:
    """Short ₹-formatter — mirrors kpi_command_center._fmt_inr for display."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return '—'
    if abs(n) >= 10_000_000:
        return f'₹{n / 10_000_000:.2f} cr'
    if abs(n) >= 100_000:
        return f'₹{n / 100_000:.2f} lakh'
    return f'₹{n:,.0f}'


def _pct(v, d=1) -> str:
    try:
        return f'{float(v):.{d}f}%'
    except (TypeError, ValueError):
        return '—'


def _severity_from_revenue_gap(pct: float) -> str:
    """Classify a revenue gap percentage against red/amber thresholds."""
    if pct <= ALERT_THRESHOLDS['revenue_red_pct']:
        return 'red'
    if pct <= ALERT_THRESHOLDS['revenue_amber_pct']:
        return 'amber'
    return 'green'


def _severity_from_pts_gap(pts: float) -> str:
    if pts <= ALERT_THRESHOLDS['occupancy_gap_red_pts']:
        return 'red'
    if pts <= ALERT_THRESHOLDS['occupancy_gap_amber_pts']:
        return 'amber'
    return 'green'


def _severity_from_drop_pct(pct: float, red_key: str, amber_key: str) -> str:
    if pct <= ALERT_THRESHOLDS[red_key]:
        return 'red'
    if pct <= ALERT_THRESHOLDS[amber_key]:
        return 'amber'
    return 'green'


def _alert(
    code: str,
    title: str,
    severity: str,
    metric: str,
    current_value: Optional[float],
    target_value: Optional[float],
    variance_value: Optional[float],
    variance_pct: Optional[float],
    reason: str,
    root_cause: Iterable[dict] = (),
    suggested_actions: Iterable[str] = (),
    scope_note: Optional[str] = None,
) -> dict:
    """Build the structured alert envelope.

    Phase-7-refinement additions (backward-compatible — all optional):

    * ``root_cause`` now accepts a list of either strings OR dicts
      ``{text, confidence}`` where ``confidence ∈ {primary, secondary,
      possible}``. Legacy string entries are wrapped into
      ``{text: ..., confidence: 'secondary'}`` so no caller breaks.
    * ``scope_note``   — free-form string rendered by the UI as a grey
      badge on the card (e.g. "Based on MTD performance" for channel
      alerts, so users on a 7-day filter aren't confused).
    * ``days_active``  — set by ``build_alerts`` from the alert memory;
      0 for a brand-new alert, N for one active N calendar days.
    * ``is_persistent`` — True when days_active ≥
      ``PERSISTENT_DAYS_THRESHOLD``. The UI uses this to fold repeated
      noise into a quieter summary tail.
    """
    rc_out = []
    for item in (root_cause or []):
        if isinstance(item, dict):
            rc_out.append({
                'text':       str(item.get('text') or ''),
                'confidence': str(item.get('confidence') or 'secondary'),
            })
        else:
            rc_out.append({'text': str(item), 'confidence': 'secondary'})
    return {
        'code':              code,
        'title':             title,
        'severity':          severity,
        'metric':            metric,
        'current_value':     current_value,
        'target_value':      target_value,
        'variance_value':    variance_value,
        'variance_pct':      variance_pct,
        'reason':            reason,
        'root_cause':        rc_out,
        'suggested_actions': list(suggested_actions),
        'owner_role':        OWNER_MAP.get(code, 'Manager'),
        'priority_rank':     PRIORITY_RANK.get(code, 99),
        # Memory-driven fields — populated by build_alerts, not the detector.
        'days_active':   0,
        'is_persistent': False,
        'first_seen':    None,
        # Scope hint for the UI (e.g. "Based on MTD performance").
        'scope_note':    scope_note,
    }


# ---------------------------------------------------------------------------
# Small additional queries (all defensive; None on any failure)
# ---------------------------------------------------------------------------

def _channel_mix_mtd(business_date: date) -> Optional[dict]:
    """Rooms-sold share by source for MTD. Returns a dict of shares (0-100)
    or None if the query fails. Used for HIGH_OTA_DEPENDENCY and
    DIRECT_SHARE_TOO_LOW rules.

    Shares are computed on CheckedIn/CheckedOut reservations whose
    arrival_date falls inside the MTD window — same set used by the
    headline occupancy snapshot so the numbers reconcile with the UI."""
    try:
        month_start = business_date.replace(day=1)
        rows = (db.session.query(
                    Reservation.source, func.count(Reservation.id))
                .filter(Reservation.status.in_(('CheckedIn', 'CheckedOut')),
                        Reservation.arrival_date >= month_start,
                        Reservation.arrival_date <= business_date)
                .group_by(Reservation.source).all())
        total = sum(r[1] for r in rows) or 0
        if total <= 0:
            return None
        counts = {str(src or 'Walk-in'): int(cnt) for src, cnt in rows}
        # Canonical buckets (keep aligned with filter options).
        def _pctOf(key):
            return round(counts.get(key, 0) / total * 100, 1)
        return {
            'total_rooms': total,
            'ota_pct':     _pctOf('OTA'),
            'walkin_pct':  _pctOf('Walk-in'),
            'calling_pct': _pctOf('Calling'),
            'website_pct': _pctOf('Website'),
            'agent_pct':   _pctOf('Agent'),
            # Direct = walk-in + calling + website (excludes OTA / agent).
            'direct_pct':  _pctOf('Walk-in') + _pctOf('Calling') + _pctOf('Website'),
        }
    except Exception as exc:
        logger.warning('_channel_mix_mtd failed: %s', exc)
        return None


def _cancellation_rate_mtd(business_date: date) -> Optional[dict]:
    """Cancelled + NoShow share of all reservations whose arrival falls in
    MTD. Percent is over the SUM of active+cancelled (i.e. what the team
    booked, not what stayed) so a 10% rate reads correctly."""
    try:
        month_start = business_date.replace(day=1)
        rows = (db.session.query(
                    Reservation.status, func.count(Reservation.id))
                .filter(Reservation.arrival_date >= month_start,
                        Reservation.arrival_date <= business_date)
                .group_by(Reservation.status).all())
        counts = {str(s or ''): int(c) for s, c in rows}
        total = sum(counts.values()) or 0
        if total <= 0:
            return None
        cancelled = counts.get('Cancelled', 0)
        noshow    = counts.get('NoShow', 0)
        return {
            'total_bookings': total,
            'cancelled':       cancelled,
            'noshow':          noshow,
            'cancel_pct':      round(cancelled / total * 100, 1),
            'noshow_pct':      round(noshow / total * 100, 1),
        }
    except Exception as exc:
        logger.warning('_cancellation_rate_mtd failed: %s', exc)
        return None


def _premium_room_utilization(business_date: date) -> Optional[dict]:
    """Rough 'premium rooms sold' vs 'base rooms sold' split by base_rate
    tercile. Uses the live Reservation / Room tables — one query.

    Returns {premium_pct, base_pct, premium_sold, base_sold} or None.
    'Premium' = room_types in the top third by base_rate.
    """
    try:
        from app.models import RoomType
        rt_rows = (db.session.query(RoomType.id, RoomType.name, RoomType.base_rate)
                   .filter(RoomType.base_rate > 0)
                   .order_by(RoomType.base_rate.desc()).all())
        if not rt_rows:
            return None
        # Top third by base_rate = "premium"; remaining = "base".
        premium_count = max(1, len(rt_rows) // 3)
        premium_ids = {r[0] for r in rt_rows[:premium_count]}
        month_start = business_date.replace(day=1)
        sold_rows = (db.session.query(
                         Reservation.room_type_id, func.count(Reservation.id))
                     .filter(Reservation.status.in_(('CheckedIn', 'CheckedOut')),
                             Reservation.arrival_date >= month_start,
                             Reservation.arrival_date <= business_date)
                     .group_by(Reservation.room_type_id).all())
        sold = {int(rt_id): int(c) for rt_id, c in sold_rows if rt_id is not None}
        premium_sold = sum(sold.get(rt_id, 0) for rt_id in premium_ids)
        base_sold    = sum(c for rt_id, c in sold.items() if rt_id not in premium_ids)
        total_sold = premium_sold + base_sold
        if total_sold <= 0:
            return None
        return {
            'premium_ids':  sorted(premium_ids),
            'premium_sold': premium_sold,
            'base_sold':    base_sold,
            'premium_pct':  round(premium_sold / total_sold * 100, 1),
            'base_pct':     round(base_sold    / total_sold * 100, 1),
        }
    except Exception as exc:
        logger.warning('_premium_room_utilization failed: %s', exc)
        return None


def _discount_leakage_mtd(business_date: date) -> Optional[dict]:
    """Sum of discount_amount on MTD reservations / total accrual room rev,
    expressed as a percent. Returns None on failure or no bookings."""
    try:
        month_start = business_date.replace(day=1)
        agg = (db.session.query(
                    func.coalesce(func.sum(Reservation.discount_amount), 0),
                    func.coalesce(func.sum(Reservation.rate_per_night), 0),
                    func.count(Reservation.id))
               .filter(Reservation.status.in_(('CheckedIn', 'CheckedOut')),
                       Reservation.arrival_date >= month_start,
                       Reservation.arrival_date <= business_date)
               .one())
        discount_total = float(agg[0] or 0)
        rate_total = float(agg[1] or 0)
        n = int(agg[2] or 0)
        if n <= 0 or rate_total <= 0:
            return None
        leak_pct = (discount_total / rate_total) * 100
        return {
            'discount_total': discount_total,
            'reservations':   n,
            'leakage_pct':    round(leak_pct, 1),
        }
    except Exception as exc:
        logger.warning('_discount_leakage_mtd failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Detectors — one family per function. Each returns a list of alert dicts.
# Every detector is wrapped in try/except by build_alerts so a bug in one
# family can never erase the whole alerts block.
# ---------------------------------------------------------------------------

def _detect_revenue_alerts(ctx: dict, body: dict) -> list:
    """Forecast miss / MTD below pace / today below target."""
    out = []
    qa  = body.get('quick_answers') or {}
    svt = body.get('sales_vs_target') or {}
    mtd_target_metric = qa.get('mtd_target') or {}
    mtd_sales_metric  = qa.get('mtd_sales')  or {}
    forecast_metric   = qa.get('forecast_month_end') or {}
    today_sales       = qa.get('today_sales')  or {}
    today_target      = qa.get('today_target') or {}
    run_rate_metric   = qa.get('required_run_rate') or {}

    # Full monthly target — reconstruct from daily_target × days_in_month by
    # reading the sales_vs_target mtd.full_month_target if present (set by
    # build_sales_vs_target for the MTD scope). Fall back to 0.
    mtd_scope = svt.get('mtd') or {}
    # build_sales_vs_target emits full_month_target as a metric envelope
    # ({value, display, sub}), not a bare number — the same shape every
    # quick_answers entry above is read through. Unwrapping it is what this
    # line always meant to do; without it float() received the dict and the
    # whole detector died before emitting a single alert.
    full_monthly_target = float((mtd_scope.get('full_month_target') or {}).get('value') or 0)

    # ── MTD_REVENUE_BELOW_PACE ─────────────────────────────────────────
    # Use sales_vs_target.mtd.progress_pct which is actual / pro-rated × 100.
    # Progress of 85% (15pt behind) is the red-amber boundary here.
    mtd_progress = mtd_scope.get('progress_pct')
    if mtd_progress is not None and float(mtd_target_metric.get('value') or 0) > 0:
        # progress_pct is already current/target*100 — gap is progress-100.
        gap_pct = float(mtd_progress) - 100
        severity = _severity_from_revenue_gap(gap_pct)
        if severity != 'green':
            actual = float(mtd_sales_metric.get('value') or 0)
            target = float(mtd_target_metric.get('value') or 0)
            variance = actual - target
            shortfall = target - actual
            out.append(_alert(
                code='MTD_REVENUE_BELOW_PACE',
                title='MTD sales below pace',
                severity=severity,
                metric='sales',
                current_value=actual,
                target_value=target,
                variance_value=variance,
                variance_pct=round(gap_pct, 1),
                reason=(f'MTD sales are {abs(round(gap_pct, 1))}% below the '
                        f'pro-rated target ({_fmt_inr(actual)} vs {_fmt_inr(target)}).'),
                root_cause=[],      # filled by build_root_cause_summary via ctx
                suggested_actions=[
                    f'Close the {_fmt_inr(shortfall)} gap over the remaining days — '
                    'brief front desk on walk-in upsell priorities.',
                    'Review OTA rate parity — small ADR uplift on high-demand days beats a discount-led push.',
                    'Pull the last 7 cancellations — if OTA-heavy, tighten non-refundable mix.',
                ],
            ))

    # ── TODAY_SALES_BELOW_TARGET ──────────────────────────────────────
    today_actual = float(today_sales.get('value') or 0)
    today_tgt    = float(today_target.get('value') or 0)
    if today_tgt > 0:
        gap_pct = ((today_actual - today_tgt) / today_tgt) * 100
        severity = _severity_from_revenue_gap(gap_pct)
        if severity != 'green':
            today_gap = today_tgt - today_actual
            out.append(_alert(
                code='TODAY_SALES_BELOW_TARGET',
                title="Today's sales below daily target",
                severity=severity,
                metric='sales',
                current_value=today_actual,
                target_value=today_tgt,
                variance_value=today_actual - today_tgt,
                variance_pct=round(gap_pct, 1),
                reason=(f"Today's sales are {abs(round(gap_pct, 1))}% below "
                        f'the daily target ({_fmt_inr(today_actual)} vs {_fmt_inr(today_tgt)}).'),
                root_cause=[],
                suggested_actions=[
                    f'Close the {_fmt_inr(today_gap)} gap today — check in all expected arrivals.',
                    'Walk the arrivals list — offer a paid upgrade for any premium room sitting empty.',
                    'Short-window tactical offer if vacant rooms remain at 4 PM.',
                ],
            ))

    # ── FORECAST_BELOW_TARGET ─────────────────────────────────────────
    forecast_val = float(forecast_metric.get('value') or 0)
    if full_monthly_target > 0 and forecast_val > 0:
        gap_pct = ((forecast_val - full_monthly_target) / full_monthly_target) * 100
        severity = _severity_from_drop_pct(
            gap_pct, 'forecast_miss_red_pct', 'forecast_miss_amber_pct')
        if severity != 'green':
            short_by = full_monthly_target - forecast_val
            out.append(_alert(
                code='FORECAST_BELOW_TARGET',
                title=f'Forecast likely to miss target by {_fmt_inr(short_by)}',
                severity=severity,
                metric='sales',
                current_value=forecast_val,
                target_value=full_monthly_target,
                variance_value=-short_by,
                variance_pct=round(gap_pct, 1),
                reason=('At the current pace, month-end sales will fall '
                        f'{abs(round(gap_pct, 1))}% below target '
                        f'({_fmt_inr(forecast_val)} vs {_fmt_inr(full_monthly_target)}).'),
                root_cause=[],
                suggested_actions=[
                    f'Tactical push needed to cover {_fmt_inr(short_by)} — align ownership before Friday.',
                    'Lift ARR 5-8% on high-demand days before cutting rates on soft days.',
                    'Audit room-type performance — premium inventory is usually the easiest lever.',
                ],
            ))

    # ── RUN_RATE_UNREALISTIC ──────────────────────────────────────────
    rr_val = float(run_rate_metric.get('value') or 0)
    if rr_val > 0 and today_actual > 0:
        ratio = rr_val / today_actual
        if ratio >= ALERT_THRESHOLDS['run_rate_unrealistic_ratio']:
            severity = 'red' if ratio >= 2.0 else 'amber'
            out.append(_alert(
                code='RUN_RATE_UNREALISTIC',
                title=f"Required run rate is {ratio:.1f}× today's pace",
                severity=severity,
                metric='sales',
                current_value=today_actual,
                target_value=rr_val,
                variance_value=rr_val - today_actual,
                variance_pct=round((ratio - 1) * 100, 1),
                reason=('The daily run-rate needed to hit target is '
                        f"{ratio:.1f}× today's run-rate — the gap cannot be "
                        f'closed without a step-change.'),
                root_cause=[],
                suggested_actions=[
                    f'Escalate: target requires {_fmt_inr(rr_val)} per day vs current {_fmt_inr(today_actual)}.',
                    'Recalibrate the monthly target with ownership OR commit to a tactical push.',
                    'Reallocate corporate hold to open market if inventory is held back.',
                ],
            ))

    return out


def _detect_occupancy_alerts(ctx: dict, body: dict) -> list:
    """Occupancy gap vs configured target (today + MTD)."""
    out = []
    qa = body.get('quick_answers') or {}

    # Extract MTD occupancy actual + target from sub-text heuristics — the
    # target was embedded into the metric sub by build_quick_answers, but
    # the numeric target is more reliable via get_monthly_targets.
    try:
        from app.kpi_command_center import get_monthly_targets
        targets = get_monthly_targets(
            ctx['business_date'], (ctx.get('filters') or {}).get('property_id'))
        occ_target = float(targets.get('occupancy') or 0)
    except Exception:
        occ_target = 0.0

    occ_today_metric = qa.get('occupancy_today') or {}
    occ_mtd_metric   = qa.get('occupancy_mtd')   or {}
    occ_today = float(occ_today_metric.get('value') or 0)
    occ_mtd   = float(occ_mtd_metric.get('value') or 0)

    if occ_target > 0:
        # MTD occupancy carries more weight than today's single data point.
        gap_mtd = occ_mtd - occ_target
        severity = _severity_from_pts_gap(gap_mtd)
        if severity != 'green':
            out.append(_alert(
                code='OCCUPANCY_BELOW_TARGET',
                title='Occupancy below target',
                severity=severity,
                metric='occupancy',
                current_value=occ_mtd,
                target_value=occ_target,
                variance_value=gap_mtd,
                variance_pct=round(gap_mtd, 1),    # pts, shown as % in UI
                reason=(f'MTD occupancy is {_pct(occ_mtd)} vs the {_pct(occ_target, 0)} '
                        f'target — {abs(round(gap_mtd, 1))} points short.'),
                root_cause=[],
                suggested_actions=[
                    'Check rate competitiveness — OTA and direct.',
                    'Offer short-stay packages for weekdays.',
                    'Walk in-house list — extensions often fill tomorrow.',
                ],
            ))

    return out


def _detect_pricing_alerts(ctx: dict, body: dict) -> list:
    """ADR / RevPAR movement vs the comparison period."""
    out = []
    cmp_block = body.get('comparison') or {}
    delta = cmp_block.get('delta') or {}
    adr_delta = delta.get('adr')    or {}
    revpar_delta = delta.get('revpar') or {}

    adr_pct = adr_delta.get('pct')
    if adr_pct is not None:
        severity = _severity_from_drop_pct(
            float(adr_pct), 'adr_drop_red_pct', 'adr_drop_amber_pct')
        if severity != 'green':
            cur = (cmp_block.get('current')  or {}).get('adr', {})
            prv = (cmp_block.get('previous') or {}).get('adr', {})
            cur_v = float(cur.get('value') or 0)
            prv_v = float(prv.get('value') or 0)
            drop  = prv_v - cur_v
            out.append(_alert(
                code='ADR_BELOW_TARGET',
                title='ADR weaker than previous period',
                severity=severity,
                metric='adr',
                current_value=cur_v,
                target_value=prv_v,
                variance_value=float(adr_delta.get('value') or 0),
                variance_pct=round(float(adr_pct), 1),
                reason=(f"Average daily rate dropped {abs(round(float(adr_pct), 1))}% "
                        'vs the comparison period.'),
                root_cause=[],
                suggested_actions=[
                    f'ADR is {_fmt_inr(cur_v)} vs {_fmt_inr(prv_v)} — pull discount audit for the period.',
                    f'Recover {_fmt_inr(drop)} / room by tightening OTA promos and overrides.',
                    'Lift walk-in rate ₹200-500 on next 3 high-occupancy days before dropping it on soft ones.',
                ],
            ))

    revpar_pct = revpar_delta.get('pct')
    if revpar_pct is not None:
        severity = _severity_from_drop_pct(
            float(revpar_pct), 'revpar_drop_red_pct', 'revpar_drop_amber_pct')
        if severity != 'green':
            cur = (cmp_block.get('current')  or {}).get('revpar', {})
            prv = (cmp_block.get('previous') or {}).get('revpar', {})
            cur_v = float(cur.get('value') or 0)
            prv_v = float(prv.get('value') or 0)
            # Decide whether occupancy or ADR is the bigger driver — this
            # lets the action text point to the actual lever.
            occ_delta = (cmp_block.get('delta') or {}).get('occupancy') or {}
            occ_pct_move = float(occ_delta.get('pct') or 0)
            adr_pct_move = float(adr_pct or 0)
            if abs(occ_pct_move) > abs(adr_pct_move):
                driver = 'occupancy'
                primary_action = 'Refresh OTA promos and re-check room-availability blocks — occupancy is the bigger driver.'
            else:
                driver = 'ADR'
                primary_action = 'Tighten discount authorisations — ADR is the bigger driver of the RevPAR drop.'
            out.append(_alert(
                code='REVPAR_BELOW_TARGET',
                title='RevPAR weaker than previous period',
                severity=severity,
                metric='revpar',
                current_value=cur_v,
                target_value=prv_v,
                variance_value=float(revpar_delta.get('value') or 0),
                variance_pct=round(float(revpar_pct), 1),
                reason=(f'RevPAR at {_fmt_inr(cur_v)} is '
                        f'{abs(round(float(revpar_pct), 1))}% below the comparison period '
                        f'— {driver} is the primary driver.'),
                root_cause=[],
                suggested_actions=[
                    primary_action,
                    f'Target RevPAR: {_fmt_inr(prv_v)} — close {_fmt_inr(prv_v - cur_v)} per available room.',
                    'Review room-type pricing for the upcoming week with revenue manager.',
                ],
            ))

    return out


def _detect_channel_alerts(ctx: dict, body: dict) -> list:
    """Channel-mix dependency — OTA too high, direct too low."""
    out = []
    mix = _channel_mix_mtd(ctx['business_date'])
    if not mix:
        return out

    ota = float(mix.get('ota_pct') or 0)
    direct = float(mix.get('direct_pct') or 0)

    # Channel mix is computed over MTD regardless of the user-selected
    # filter (strategic KPI, reads cleanest monthly). Flag that in the UI.
    scope = 'Based on MTD performance'

    if ota >= ALERT_THRESHOLDS['ota_dependency_red_pct']:
        severity = 'red'
    elif ota >= ALERT_THRESHOLDS['ota_dependency_amber_pct']:
        severity = 'amber'
    else:
        severity = 'green'
    if severity != 'green':
        ota_amber = ALERT_THRESHOLDS['ota_dependency_amber_pct']
        out.append(_alert(
            code='HIGH_OTA_DEPENDENCY',
            title=f'OTA share high at {_pct(ota, 0)}',
            severity=severity,
            metric='channel_mix',
            current_value=ota,
            target_value=ota_amber,
            variance_value=ota - ota_amber,
            variance_pct=round(ota - ota_amber, 1),
            reason=(f'{_pct(ota, 0)} of MTD bookings come from OTA — '
                    'commissions eat into ADR and dilute margin.'),
            root_cause=[],
            suggested_actions=[
                f'Reduce OTA allocation next 3 days — target below {_pct(ota_amber, 0)} share.',
                (f'Direct share is only {_pct(direct, 0)} — push the WhatsApp '
                 'pre-check-in link and promote repeat-guest discount.'),
                'Re-check parity — OTA can be undercutting the direct-channel rate without the team noticing.',
            ],
            scope_note=scope,
        ))

    if direct <= ALERT_THRESHOLDS['direct_share_low_red_pct']:
        severity = 'red'
    elif direct <= ALERT_THRESHOLDS['direct_share_low_amber_pct']:
        severity = 'amber'
    else:
        severity = 'green'
    if severity != 'green':
        direct_target = ALERT_THRESHOLDS['direct_share_low_amber_pct']
        out.append(_alert(
            code='DIRECT_SHARE_TOO_LOW',
            title=f'Direct share only {_pct(direct, 0)}',
            severity=severity,
            metric='channel_mix',
            current_value=direct,
            target_value=direct_target,
            variance_value=direct - direct_target,
            variance_pct=round(direct - direct_target, 1),
            reason=(f'Only {_pct(direct, 0)} of MTD bookings are direct '
                    '(walk-in / calling / website).'),
            root_cause=[],
            suggested_actions=[
                f'Grow direct by {_pct(max(0, direct_target - direct), 0)} — incentivise walk-in conversions.',
                (f'OTA share is {_pct(ota, 0)}; each direct booking saves 15-20% '
                 'commission — push the pre-check-in link aggressively.'),
                'Run a targeted WhatsApp campaign to repeat guests this week.',
            ],
            scope_note=scope,
        ))

    return out


def _detect_collection_alerts(ctx: dict, body: dict) -> list:
    """Outstanding due / OTA receivable thresholds."""
    out = []
    summary = body.get('summary_cards') or {}
    rr      = body.get('range_revenue') or {}

    due = float((summary.get('outstanding_due') or {}).get('value') or 0)
    if due >= ALERT_THRESHOLDS['outstanding_due_red']:
        severity = 'red'
    elif due >= ALERT_THRESHOLDS['outstanding_due_amber']:
        severity = 'amber'
    else:
        severity = 'green'
    if severity != 'green':
        due_amber = ALERT_THRESHOLDS['outstanding_due_amber']
        out.append(_alert(
            code='OUTSTANDING_DUE_HIGH',
            title=f'In-house dues at {_fmt_inr(due)}',
            severity=severity,
            metric='outstanding_due',
            current_value=due,
            target_value=due_amber,
            variance_value=due - due_amber,
            variance_pct=None,
            reason=(f'Sum of in-house guest balances has reached {_fmt_inr(due)} — '
                    'a cash-flow gap if not collected.'),
            root_cause=[],
            suggested_actions=[
                f'Collect {_fmt_inr(due - due_amber)} over threshold — front desk to walk in-house dues by room.',
                'Accountant to pull invoice-register aging and flag any > 24h balances.',
                'Check corporate credit — likely a limit is exceeded and needs top-up or payment.',
            ],
            scope_note='In-house balances (live)',
        ))

    recv = float((rr.get('ota_receivable') or {}).get('value') or 0)
    if recv >= ALERT_THRESHOLDS['ota_receivable_red']:
        severity = 'red'
    elif recv >= ALERT_THRESHOLDS['ota_receivable_amber']:
        severity = 'amber'
    else:
        severity = 'green'
    if severity != 'green':
        recv_amber = ALERT_THRESHOLDS['ota_receivable_amber']
        out.append(_alert(
            code='OTA_RECEIVABLE_HIGH',
            title=f'OTA receivable at {_fmt_inr(recv)}',
            severity=severity,
            metric='ota_receivable',
            current_value=recv,
            target_value=recv_amber,
            variance_value=recv - recv_amber,
            variance_pct=None,
            reason=(f'{_fmt_inr(recv)} is posted to OTA heads for the range '
                    'but not yet settled to the hotel account.'),
            root_cause=[],
            suggested_actions=[
                f'Reconcile {_fmt_inr(recv)} against next-cycle OTA payouts — match by booking-ref.',
                'Identify the slowest-paying OTA and escalate to its account manager.',
                'Flag any receivable older than the channel\'s standard payout cycle.',
            ],
            scope_note='Selected range · Cash basis',
        ))

    return out


def _detect_room_type_alerts(ctx: dict, body: dict) -> list:
    """Premium rooms unsold while base inventory fills."""
    out = []
    util = _premium_room_utilization(ctx['business_date'])
    if not util:
        return out
    prem = float(util.get('premium_pct') or 0)
    # Low premium share = premium rooms under-performing.
    if prem <= ALERT_THRESHOLDS['premium_idle_red_pct']:
        severity = 'red'
    elif prem <= ALERT_THRESHOLDS['premium_idle_amber_pct']:
        severity = 'amber'
    else:
        severity = 'green'
    if severity != 'green':
        amber_tgt = ALERT_THRESHOLDS['premium_idle_amber_pct']
        gap = amber_tgt - prem
        out.append(_alert(
            code='PREMIUM_ROOM_UNDERSOLD',
            title=f'Premium rooms only {_pct(prem, 0)} of sales',
            severity=severity,
            metric='room_type_mix',
            current_value=prem,
            target_value=amber_tgt,
            variance_value=prem - amber_tgt,
            variance_pct=round(prem - amber_tgt, 1),
            reason=('Premium room categories account for only '
                    f'{_pct(prem, 0)} of MTD bookings — revenue is concentrated '
                    'in the base inventory.'),
            root_cause=[],
            suggested_actions=[
                (f'Offer upgrade or bundle premium rooms — currently {util.get("premium_sold", 0)} sold '
                 f'vs {util.get("base_sold", 0)} base rooms.'),
                f'Target premium mix ≥ {_pct(amber_tgt, 0)} — shift {_pct(max(0, gap), 0)} more bookings up-category.',
                'Review premium rate parity — it may be priced out of market vs base + extras.',
            ],
            scope_note='Based on MTD performance',
        ))
    return out


def _detect_behaviour_alerts(ctx: dict, body: dict) -> list:
    """Cancellation rate + discount leakage."""
    out = []
    cancel = _cancellation_rate_mtd(ctx['business_date'])
    if cancel:
        rate = float(cancel.get('cancel_pct') or 0)
        if rate >= ALERT_THRESHOLDS['cancellation_rate_red_pct']:
            severity = 'red'
        elif rate >= ALERT_THRESHOLDS['cancellation_rate_amber_pct']:
            severity = 'amber'
        else:
            severity = 'green'
        if severity != 'green':
            amber_tgt = ALERT_THRESHOLDS['cancellation_rate_amber_pct']
            excess_n = cancel['cancelled'] - int(cancel['total_bookings'] * amber_tgt / 100)
            out.append(_alert(
                code='CANCELLATION_RATE_HIGH',
                title=f'Cancellation rate at {_pct(rate, 0)}',
                severity=severity,
                metric='cancellations',
                current_value=rate,
                target_value=amber_tgt,
                variance_value=rate - amber_tgt,
                variance_pct=round(rate - amber_tgt, 1),
                reason=(f'{cancel["cancelled"]} of {cancel["total_bookings"]} MTD '
                        f'bookings ({_pct(rate, 0)}) were cancelled.'),
                root_cause=[],
                suggested_actions=[
                    (f'Sample the last {max(10, min(20, cancel["cancelled"]))} cancellations — '
                     'look for the common channel / rate plan / lead-time.'),
                    f'Target ≤ {_pct(amber_tgt, 0)} — {excess_n} cancellations above threshold this month.',
                    'Convert high-risk bookings to non-refundable rates if OTA cancellations dominate.',
                ],
                scope_note='Based on MTD performance',
            ))

    leak = _discount_leakage_mtd(ctx['business_date'])
    if leak:
        leak_pct = float(leak.get('leakage_pct') or 0)
        if leak_pct >= 12:
            severity = 'red'
        elif leak_pct >= 6:
            severity = 'amber'
        else:
            severity = 'green'
        if severity != 'green':
            avg_per_res = leak['discount_total'] / max(1, leak['reservations'])
            out.append(_alert(
                code='DISCOUNT_LEAKAGE_HIGH',
                title=f'Discount leakage at {_pct(leak_pct, 0)} of room rate',
                severity=severity,
                metric='discount',
                current_value=leak_pct,
                target_value=6.0,
                variance_value=leak_pct - 6.0,
                variance_pct=round(leak_pct - 6.0, 1),
                reason=(f'{_fmt_inr(leak["discount_total"])} of discounts posted '
                        f'across {leak["reservations"]} MTD reservations '
                        f'({_pct(leak_pct, 0)} of room rate).'),
                root_cause=[],
                suggested_actions=[
                    (f'Average discount is {_fmt_inr(avg_per_res)} per reservation — '
                     'pull the audit log and identify the top 5 authorisers.'),
                    f'Tighten per-reservation cap to ≤ 6% — current MTD is {_pct(leak_pct, 0)}.',
                    'Require Manager override for any discount > ₹500 (set in Settings).',
                ],
                scope_note='Based on MTD performance',
            ))

    return out


# ---------------------------------------------------------------------------
# Governance — Individual Credit exposure, overdue receivables, audit-lock
# overrides. These signals do NOT depend on revenue/occupancy context, so
# the detector reads its own queries and never crashes the rest of the
# build_alerts pipeline (wrapped in try/except up the stack).
# ---------------------------------------------------------------------------
def _detect_governance_alerts(ctx: dict, body: dict) -> list:
    out = []
    governance = (body.get('governance') or {}) if isinstance(body, dict) else {}

    # ── HIGH_CREDIT_EXPOSURE ──────────────────────────────────────────
    credit_total = float(governance.get('credit_outstanding_total') or 0)
    if credit_total >= ALERT_THRESHOLDS['credit_exposure_red']:
        sev = 'red'
    elif credit_total >= ALERT_THRESHOLDS['credit_exposure_amber']:
        sev = 'amber'
    else:
        sev = 'green'
    if sev != 'green':
        amber_tgt = ALERT_THRESHOLDS['credit_exposure_amber']
        out.append(_alert(
            code='HIGH_CREDIT_EXPOSURE',
            title=f'Open individual-credit receivable at {_fmt_inr(credit_total)}',
            severity=sev,
            metric='credit_exposure',
            current_value=credit_total,
            target_value=amber_tgt,
            variance_value=credit_total - amber_tgt,
            variance_pct=None,
            reason=(f'{_fmt_inr(credit_total)} is owed by '
                    f'{int(governance.get("credit_outstanding_count") or 0)} '
                    f'guest(s) checked out on Individual Credit. Receivable is '
                    f'NOT revenue — cash flow is at risk until cleared.'),
            root_cause=[
                {'text': 'Front desk approving credit checkouts above the safe threshold.',
                 'confidence': 'secondary'},
                {'text': 'Guest receivables are not being followed up daily.',
                 'confidence': 'possible'},
            ],
            suggested_actions=[
                'Pull Credit Ledger and route the top 5 receivables to the cashier for follow-up.',
                f'Trim exposure below {_fmt_inr(amber_tgt)} — currently '
                f'{_fmt_inr(credit_total - amber_tgt)} above amber threshold.',
                'Tighten Manager-approval rule for any new individual-credit checkout.',
            ],
            scope_note='Receivable (live)',
        ))

    # ── OVERDUE_CREDIT_RISK ───────────────────────────────────────────
    overdue_count  = int(governance.get('overdue_30_count')  or 0)
    overdue_amount = float(governance.get('overdue_30_amount') or 0)
    if overdue_count >= ALERT_THRESHOLDS['overdue_credit_red_count']:
        sev = 'red'
    elif overdue_count >= ALERT_THRESHOLDS['overdue_credit_amber_count']:
        sev = 'amber'
    else:
        sev = 'green'
    if sev != 'green':
        out.append(_alert(
            code='OVERDUE_CREDIT_RISK',
            title=f'{overdue_count} receivable(s) overdue 30+ days',
            severity=sev,
            metric='overdue_30',
            current_value=overdue_count,
            target_value=0,
            variance_value=overdue_count,
            variance_pct=None,
            reason=(f'{overdue_count} individual-credit receivable(s) totalling '
                    f'{_fmt_inr(overdue_amount)} have been open for more than 30 days. '
                    f'Aging this old materially raises the write-off probability.'),
            root_cause=[
                {'text': 'No one is owning the recovery follow-up on these specific folios.',
                 'confidence': 'primary'},
                {'text': 'Guest contact details may be stale — phone / email outdated.',
                 'confidence': 'secondary'},
            ],
            suggested_actions=[
                'Open Credit Aging report → 30+ bucket → assign each row to a recovery owner.',
                'Call/SMS each overdue guest with a soft-collection script.',
                'Flag rows for write-off review if 60+ days with zero contact.',
            ],
            scope_note='Receivable Aging (live)',
        ))

    # ── FREQUENT_ADMIN_OVERRIDES ──────────────────────────────────────
    overrides_24h = int(governance.get('overrides_24h_count') or 0)
    if overrides_24h >= ALERT_THRESHOLDS['override_24h_red_count']:
        sev = 'red'
    elif overrides_24h >= ALERT_THRESHOLDS['override_24h_amber_count']:
        sev = 'amber'
    else:
        sev = 'green'
    if sev != 'green':
        amber_tgt = ALERT_THRESHOLDS['override_24h_amber_count']
        out.append(_alert(
            code='FREQUENT_ADMIN_OVERRIDES',
            title=f'{overrides_24h} Admin override(s) in last 24h',
            severity=sev,
            metric='audit_lock_override',
            current_value=overrides_24h,
            target_value=amber_tgt,
            variance_value=overrides_24h - amber_tgt,
            variance_pct=None,
            reason=(f'Admin used the audit-lock override {overrides_24h} time(s) in the '
                    f'last 24 hours. Each override edits financial data inside a closed '
                    f'Night Audit date — a pattern of frequent overrides erodes the '
                    f'integrity guarantee the lock provides.'),
            root_cause=[
                {'text': 'Front desk is missing the void / payment window before night audit closes.',
                 'confidence': 'primary'},
                {'text': 'Same Admin user is repeatedly correcting the same staff\'s mistakes.',
                 'confidence': 'secondary'},
            ],
            suggested_actions=[
                'Pull the AuditLog where action=\'audit_lock_override\' for the last 24h '
                'and review each reason.',
                'If overrides cluster around one user, run a refresher on the void window.',
                'Consider widening the void window in Settings if overrides are legitimate.',
            ],
            scope_note='Trailing 24h',
        ))

    return out


# ---------------------------------------------------------------------------
# Root-cause narrative — runs AFTER all detectors so it can read their codes
# ---------------------------------------------------------------------------

def build_root_cause_summary(alerts: list, ctx: dict, body: dict) -> list:
    """Short human-readable diagnosis with confidence tags.

    Returns a list of ``{text, confidence}`` dicts where:
      * ``primary``   — the rule is a direct match on multiple firing alerts
                        (e.g. MTD below pace AND occupancy below target).
      * ``secondary`` — a single firing alert points at the cause.
      * ``possible`` — plausible but weaker signal (fewer inputs).

    Capped at 4 lines for readability. Confidence helps the UI render
    the most certain diagnosis first (bold), keep noise muted.
    """
    codes = {a['code'] for a in alerts}
    lines: list = []

    def _add(text: str, confidence: str) -> None:
        lines.append({'text': text, 'confidence': confidence})

    # PRIMARY — two or more firing alerts align on the same diagnosis.
    if ({'MTD_REVENUE_BELOW_PACE', 'OCCUPANCY_BELOW_TARGET'} <= codes):
        _add('Revenue is behind pace mainly due to low occupancy.', 'primary')
    if ('HIGH_OTA_DEPENDENCY' in codes and 'ADR_BELOW_TARGET' in codes):
        _add('ADR pressure is coming from OTA-heavy mix — direct share needs a push.', 'primary')
    if ('MTD_REVENUE_BELOW_PACE' in codes and 'ADR_BELOW_TARGET' in codes
            and 'OCCUPANCY_BELOW_TARGET' not in codes):
        _add('Occupancy is healthy but ADR is weak — discounting is eating revenue.', 'primary')

    # SECONDARY — one firing alert carries a clear narrative.
    if 'RUN_RATE_UNREALISTIC' in codes:
        _add('Required run-rate far exceeds current pace — the monthly target '
             'may need a tactical push or a recalibration.', 'secondary')
    if 'PREMIUM_ROOM_UNDERSOLD' in codes:
        _add('Premium rooms are underperforming — revenue is concentrated in base inventory.', 'secondary')
    if 'OUTSTANDING_DUE_HIGH' in codes and 'MTD_REVENUE_BELOW_PACE' not in codes:
        _add('Sales are on pace, but collections are lagging billed revenue.', 'secondary')

    # POSSIBLE — weaker signals; shown only if nothing stronger fired, or
    # as supporting context.
    if 'OTA_RECEIVABLE_HIGH' in codes:
        _add('OTA receivable is high — follow up on the next settlement cycle.', 'possible')
    if 'CANCELLATION_RATE_HIGH' in codes:
        _add('Cancellation rate is elevated — review policy and OTA cancellation behaviour.', 'possible')
    if 'FORECAST_BELOW_TARGET' in codes and not lines:
        _add('At the current pace, month-end will fall short of the revenue target.', 'possible')

    # Cap at 4 so the box stays skimmable. Ordering is preserved from the
    # rule evaluation above which already goes primary → secondary → possible.
    lines = lines[:4]

    # Populate root_cause hints back onto each top-urgency alert so the
    # UI can show per-alert context without rerunning the narrative rules.
    if lines:
        top_n = lines[:3]
        for a in alerts:
            if a['code'] in (
                'FORECAST_BELOW_TARGET', 'MTD_REVENUE_BELOW_PACE',
                'TODAY_SALES_BELOW_TARGET', 'RUN_RATE_UNREALISTIC',
            ):
                # Carry over the {text, confidence} shape so the card can
                # style the primary cause distinctly.
                a['root_cause'] = [{'text': l['text'],
                                    'confidence': l['confidence']}
                                   for l in top_n]

    return lines


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_DETECTORS = (
    ('revenue',    _detect_revenue_alerts),
    ('occupancy',  _detect_occupancy_alerts),
    ('pricing',    _detect_pricing_alerts),
    ('channel',    _detect_channel_alerts),
    ('collection', _detect_collection_alerts),
    ('room_type',  _detect_room_type_alerts),
    ('behaviour',  _detect_behaviour_alerts),
    ('governance', _detect_governance_alerts),
)


def _sort_alerts(alerts: list) -> list:
    """Sort by (severity red<amber<green, priority rank asc, code asc)."""
    return sorted(
        alerts,
        key=lambda a: (
            _SEVERITY_RANK.get(a.get('severity'), 99),
            a.get('priority_rank', 99),
            a.get('code', ''),
        ),
    )


# ---------------------------------------------------------------------------
# Deduplication — codes in each group describe overlapping problems; when
# the stronger (key) alert is present, the weaker (value) alerts get
# downgraded to amber (if they were red) or suppressed entirely to keep
# the panel focused. This prevents alert fatigue.
# ---------------------------------------------------------------------------

_DEDUP_DOWNGRADE = {
    # Forecast covers the same narrative as MTD pace and today's gap;
    # keep forecast prominent, quieten its symptoms.
    'FORECAST_BELOW_TARGET': ('MTD_REVENUE_BELOW_PACE', 'TODAY_SALES_BELOW_TARGET'),
    # Run-rate subsumes MTD pace when both fire.
    'RUN_RATE_UNREALISTIC':  ('MTD_REVENUE_BELOW_PACE',),
    # RevPAR usually moves together with ADR. If both fire, leave RevPAR
    # as the composite and downgrade ADR (RevPAR = ADR × occupancy, so
    # the RevPAR card already tells the pricing story at a higher level).
    'REVPAR_BELOW_TARGET':   ('ADR_BELOW_TARGET',),
}


def _deduplicate(alerts: list) -> list:
    """Apply the dedup table: if a key alert is present, each value alert
    in its tuple gets downgraded (red → amber). We DOWNGRADE rather than
    remove because the weaker alert still carries contextual actions that
    the manager might want — they just shouldn't scream at the same
    severity as the headline.
    """
    present = {a['code'] for a in alerts}
    to_downgrade = set()
    for key_code, weaker_codes in _DEDUP_DOWNGRADE.items():
        if key_code in present:
            to_downgrade.update(weaker_codes)
    # Touch only codes that are both present AND in the downgrade set.
    # Mutate in-place and mark the card so the UI can style it quietly.
    for a in alerts:
        if a['code'] in to_downgrade and a.get('severity') == 'red':
            a['severity'] = 'amber'
            a['is_duplicate_of'] = next(
                (k for k, v in _DEDUP_DOWNGRADE.items()
                 if a['code'] in v and k in present),
                None,
            )
    return alerts


def _apply_memory(alerts: list, today: date) -> AlertMemory:
    """Record today's firings in the alert-memory store and annotate each
    alert with ``first_seen`` / ``days_active`` / ``is_persistent``.

    Returns the memory handle so callers can decide what to persist.
    """
    mem = AlertMemory().load()
    for a in alerts:
        entry = mem.mark(a['code'], today)
        a['first_seen']    = entry['first_seen']
        a['days_active']   = entry['days_active']
        a['is_persistent'] = entry['days_active'] >= PERSISTENT_DAYS_THRESHOLD
        # Append "(N days)" to the title if persistent — helps the manager
        # register that this isn't a new problem.
        if a['is_persistent']:
            days = entry['days_active']
            a['title'] = f'{a["title"]} · {days} day{"s" if days != 1 else ""}'
    return mem


def build_alerts(ctx: dict, body: dict) -> dict:
    """Main entry: returns ``alerts``, ``alerts_summary`` and
    ``root_cause_summary`` — merge-able into the Command Center payload.

    Phase-7 refinement additions:
      * memory-backed ``days_active`` + ``is_persistent`` per alert
      * deduplication across overlapping families (forecast > mtd, etc.)
      * confidence-weighted root-cause summary
      * ``persistent_count`` in alerts_summary so the UI can surface a
        "persistent issues" badge without re-counting.
    """
    all_alerts: list = []
    for family, fn in _DETECTORS:
        try:
            all_alerts.extend(fn(ctx, body) or [])
        except Exception:
            logger.exception('alert detector %s failed', family)

    # Deduplicate BEFORE sort so downgraded alerts land in the amber tier.
    all_alerts = _deduplicate(all_alerts)
    all_alerts = _sort_alerts(all_alerts)

    # Memory: first_seen / days_active / is_persistent. Memory is only
    # persisted when we have a valid business_date in ctx — error-path
    # calls never touch the file.
    mem = None
    try:
        today = ctx.get('business_date')
        if isinstance(today, date):
            mem = _apply_memory(all_alerts, today)
            mem.purge_stale(today)
            mem.save()
    except Exception:
        logger.exception('alert memory update failed')

    # Root-cause summary reads the final alert list (post-dedup) so it
    # won't describe a cause that no longer has a red signal.
    try:
        summary_lines = build_root_cause_summary(all_alerts, ctx, body)
    except Exception:
        logger.exception('root-cause summary failed')
        summary_lines = []

    red_count       = sum(1 for a in all_alerts if a['severity'] == 'red')
    amber_count     = sum(1 for a in all_alerts if a['severity'] == 'amber')
    persistent_count = sum(1 for a in all_alerts if a.get('is_persistent'))
    top_alert_title = all_alerts[0]['title'] if all_alerts else None

    return {
        'alerts': all_alerts,
        'alerts_summary': {
            'red_count':        red_count,
            'amber_count':      amber_count,
            'persistent_count': persistent_count,
            'top_alert_title':  top_alert_title,
        },
        'root_cause_summary': summary_lines,
    }


def empty_alerts_block() -> dict:
    """Shape returned on the error payload — keeps the UI safe."""
    return {
        'alerts': [],
        'alerts_summary': {'red_count': 0, 'amber_count': 0,
                           'persistent_count': 0, 'top_alert_title': None},
        'root_cause_summary': [],
    }
