"""
AI Insights Service — Module 7
================================
Explains WHY things happened today and suggests concrete next actions,
based on the same KPIs and alerts the dashboard already shows.

Pipeline
--------
1. ``gather_context(business_date)``
   Pulls KPIs from ``app.kpi_helpers``, alerts from ``app.alert_service``,
   plus a small set of operational counts (overdue checkouts, dirty rooms,
   pending arrivals, OTA receivable, yesterday comparison) and packs them
   into a structured dict.

2. ``generate_insights(context)``
   Sends that context to **Gemini** (``google-genai`` SDK) with a prompt
   that produces a JSON object with three keys: ``summary``, ``issues``,
   ``actions``. If the API key is missing, the SDK is not installed, the
   network is down, or the call fails for any reason, falls back to a
   deterministic ``_heuristic_insights(context)`` so the dashboard never
   breaks for an offline hotel.

3. ``get_insights(business_date, force_refresh=False)``
   Memoised entry point. Caches the last good result per business_date
   in process for ``CACHE_TTL_SECONDS`` so the dashboard doesn't pay the
   Gemini latency on every page load.

The output is intentionally schema-stable so the front-end JS can render
the same shape regardless of whether Gemini or the heuristic produced it.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

# Cache TTL — short enough that managers see fresh insights as the day
# progresses, long enough that opening the dashboard repeatedly does not
# hammer the Gemini API.
CACHE_TTL_SECONDS = 15 * 60

# Default Gemini model. Flash is the cost/latency sweet spot for short
# JSON-only responses.
DEFAULT_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')


# ──────────────────────────────────────────────────────────────────────
# In-process cache (per-process, restart-clears)
# ──────────────────────────────────────────────────────────────────────

_cache_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}
# Shape: { '<isodate>': { 'expires_at': datetime, 'value': dict } }


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if datetime.utcnow() >= entry['expires_at']:
            _cache.pop(key, None)
            return None
        return entry['value']


def _cache_put(key: str, value: dict) -> None:
    with _cache_lock:
        _cache[key] = {
            'expires_at': datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS),
            'value': value,
        }


def _cache_clear(key: str | None = None) -> None:
    with _cache_lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


# ──────────────────────────────────────────────────────────────────────
# Context gathering — KPIs + alerts + operational counts
# ──────────────────────────────────────────────────────────────────────

def gather_context(business_date: date | None = None,
                   mode: str = 'frontdesk') -> dict[str, Any]:
    """Build the structured input dict that gets fed to Gemini.

    ``mode='frontdesk'`` (default) — operational view: today's KPIs,
    alerts, operational counts, and a yesterday comparison. This is
    what the dashboard panel consumes.

    ``mode='ceo'`` — strategic view: same front-desk core PLUS the
    full CEO KPI pack (funnel, channel mix, pipeline, receivable
    aging, audit health). Used by the /ceo dashboard insights panel.

    All values are plain Python (str/int/float/list/dict) so the dict is
    JSON-serialisable for both the LLM prompt and any test assertions.
    """
    from app.kpi_helpers import get_dashboard_kpis
    from app.alert_service import AlertService
    from app.models import Reservation, Room, Settings

    if business_date is None:
        from app.services import get_business_date
        business_date = get_business_date()

    # ── KPIs (today) ─────────────────────────────────────────────────
    try:
        kpis = get_dashboard_kpis(business_date)
    except Exception as exc:
        log.exception('gather_context: get_dashboard_kpis failed: %s', exc)
        kpis = {}

    # ── KPIs (yesterday, for comparison) ─────────────────────────────
    yesterday = business_date - timedelta(days=1)
    try:
        kpis_yday = get_dashboard_kpis(yesterday)
    except Exception:
        kpis_yday = {}

    # ── Operational counts ───────────────────────────────────────────
    try:
        overdue_count = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.departure_date < business_date,
        ).count()
    except Exception:
        overdue_count = 0

    try:
        pending_arrivals = Reservation.query.filter(
            Reservation.status.in_(['Reserved', 'Confirmed']),
            Reservation.arrival_date == business_date,
        ).count()
    except Exception:
        pending_arrivals = 0

    try:
        dirty_rooms = Room.query.filter_by(
            is_active=True, status='Dirty',
        ).count()
    except Exception:
        dirty_rooms = 0

    try:
        ooo_rooms = Room.query.filter_by(
            is_active=True, is_out_of_order=True,
        ).count()
    except Exception:
        ooo_rooms = 0

    # ── Active alerts ────────────────────────────────────────────────
    try:
        alerts = AlertService.get_live_alerts(limit=20, unresolved_only=True)
        alert_counts = AlertService.get_alert_counts()
    except Exception:
        alerts = []
        alert_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'total': 0}

    # ── Hotel identity (so the LLM can address the user) ─────────────
    hotel_name = 'the hotel'
    try:
        row = Settings.query.filter_by(key='hotel_name').first()
        if row and row.value:
            hotel_name = row.value
    except Exception:
        pass

    # ── Comparison deltas (yesterday → today) ────────────────────────
    def _delta(a: float, b: float) -> float:
        try:
            return round(float(a) - float(b), 2)
        except Exception:
            return 0.0

    comparison = {
        'occupancy_pct_delta': _delta(
            kpis.get('occupancy_pct', 0), kpis_yday.get('occupancy_pct', 0)),
        'adr_delta': _delta(
            kpis.get('adr', 0), kpis_yday.get('adr', 0)),
        'revpar_delta': _delta(
            kpis.get('revpar', 0), kpis_yday.get('revpar', 0)),
        'cash_collected_delta': _delta(
            kpis.get('cash_collected', 0), kpis_yday.get('cash_collected', 0)),
        'accrual_gross_delta': _delta(
            kpis.get('accrual_gross', 0), kpis_yday.get('accrual_gross', 0)),
    }

    ctx: dict[str, Any] = {
        'business_date': business_date.isoformat(),
        'hotel_name': hotel_name,
        'mode': mode,
        'kpis': kpis,
        'kpis_yesterday': kpis_yday,
        'comparison': comparison,
        'operations': {
            'overdue_checkouts': overdue_count,
            'pending_arrivals': pending_arrivals,
            'dirty_rooms': dirty_rooms,
            'out_of_order_rooms': ooo_rooms,
        },
        'alerts': alerts,
        'alert_counts': alert_counts,
    }

    # ── CEO mode: enrich with the full CEO KPI pack ──
    # Wrapped so a CEO-helper failure can never break front-desk insights.
    if mode == 'ceo':
        try:
            from app.ceo_kpis import get_ceo_kpi_pack
            ctx['ceo'] = get_ceo_kpi_pack(business_date)
        except Exception as exc:
            log.warning('gather_context(mode=ceo) failed: %s', exc)
            ctx['ceo'] = {}

    return ctx


# ──────────────────────────────────────────────────────────────────────
# Heuristic fallback — used when Gemini is unavailable
# ──────────────────────────────────────────────────────────────────────

def _heuristic_insights_ceo(context: dict) -> dict:
    """Owner-flavored heuristic. Reads context['ceo'] (the kpi pack)."""
    kpis = context.get('kpis') or {}
    ceo = context.get('ceo') or {}
    funnel = ceo.get('funnel') or {}
    pipeline = ceo.get('pipeline') or {}
    aging = ceo.get('receivable_aging') or {}
    audit = ceo.get('audit_health') or {}
    channel_mix = (ceo.get('channel_mix') or {}).get('today') or []

    occ = float(kpis.get('occupancy_pct') or 0)
    accr = float(kpis.get('accrual_gross') or 0)
    bookings = int(funnel.get('bookings_received') or 0)
    arrivals = int(funnel.get('arrivals_expected') or 0)
    checked_in = int(funnel.get('checked_in') or 0)
    no_shows = int(funnel.get('no_shows') or 0)
    conversion = float(funnel.get('conversion_pct') or 0)
    outstanding = float(aging.get('total_outstanding') or 0)
    pipe_bookings = int(pipeline.get('total_bookings') or 0)
    pipe_revenue = float(pipeline.get('total_projected_revenue') or 0)
    days_behind = int(audit.get('days_behind') or 0)

    aging_by_label = {b.get('label'): float(b.get('total') or 0)
                      for b in (aging.get('buckets') or [])}
    aged_30_plus = aging_by_label.get('30+ days', 0)

    # ── Summary ──
    summary = (
        f"Today: {bookings} OTA booking{'s' if bookings != 1 else ''} received, "
        f"{checked_in}/{arrivals} arrivals checked in, "
        f"\u20b9{accr:,.0f} earned at {occ:.0f}% occupancy. "
        f"OTA receivable on the books: \u20b9{outstanding:,.0f}. "
        f"Forward 30-day pipeline: {pipe_bookings} bookings worth "
        f"\u20b9{pipe_revenue:,.0f}."
    )

    # ── Issues ──
    issues: list[dict] = []

    if outstanding > 0 and aged_30_plus / max(outstanding, 1) >= 0.30:
        issues.append({
            'title': f"\u20b9{aged_30_plus:,.0f} of OTA receivables is 30+ days old",
            'reason': "More than a third of outstanding OTA money is sitting "
                      "in the 30+ bucket — channel reconciliation is lagging.",
        })

    if arrivals > 0 and conversion < 70:
        issues.append({
            'title': f"OTA conversion only {conversion:.0f}% today",
            'reason': f"{arrivals - checked_in} expected OTA arrivals haven't "
                      "been processed yet — risk of no-shows or unbilled stays.",
        })

    if no_shows >= 2:
        issues.append({
            'title': f"{no_shows} OTA no-shows today",
            'reason': "No-show fees on prepaid OTA bookings are not auto-settled "
                      "— manual reconciliation required to recover revenue.",
        })

    if days_behind >= 1:
        issues.append({
            'title': f"Night audit is {days_behind} day(s) behind",
            'reason': "Until the audit catches up, accrual revenue, OTA "
                      "receivables and tax reports are stale.",
        })

    if channel_mix:
        top = channel_mix[0]
        top_pct = (float(top.get('revenue_accrued') or 0)
                   / max(sum(float(r.get('revenue_accrued') or 0)
                             for r in channel_mix), 1)) * 100
        if top_pct >= 70 and len(channel_mix) >= 2:
            issues.append({
                'title': f"{top.get('source')} is {top_pct:.0f}% of today's OTA revenue",
                'reason': "Single-channel concentration is a payout-cycle and "
                          "policy-change risk — diversify the channel mix.",
            })

    if pipe_bookings == 0:
        issues.append({
            'title': "Empty 30-day OTA pipeline",
            'reason': "There are no confirmed OTA bookings in the next month — "
                      "marketing or rate competitiveness needs attention.",
        })

    # ── Actions ──
    actions: list[str] = []
    if aged_30_plus > 0:
        actions.append(
            f"Reconcile the \u20b9{aged_30_plus:,.0f} of 30+ day OTA receivables "
            "this week — pull the latest payout files from each channel manager.")
    if arrivals - checked_in > 0:
        actions.append(
            f"Tell front desk to confirm the {arrivals - checked_in} pending OTA "
            "arrivals over WhatsApp before the no-show cut-off.")
    if no_shows >= 1:
        actions.append(
            "Open each no-show in the OTA dashboard and decide whether to "
            "claim the no-show fee or release the inventory.")
    if days_behind >= 1:
        actions.append(
            "Have the manager run night audit tonight to clear the backlog.")
    if pipe_bookings < 5 and pipe_revenue < 50000:
        actions.append(
            "Push the next 14 days on Booking.com and MMT — open a 5-10% "
            "promo or check that rates are not sold out.")

    if not issues and not actions:
        actions = ["Hold strategy — funnel, pipeline and receivables look healthy."]

    return {
        'summary': summary,
        'issues': issues,
        'actions': actions,
        'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'source': 'heuristic',
        'model': None,
    }


def _heuristic_insights(context: dict) -> dict:
    """Rule-based insights, derived directly from the context dict.

    Used when no GEMINI_API_KEY is configured, the SDK is not installed,
    or the API call fails. Designed so an offline hotel still gets a
    useful — if less colourful — version of the insights panel.

    Dispatches to ``_heuristic_insights_ceo`` when ``mode='ceo'``.
    """
    if (context.get('mode') or 'frontdesk') == 'ceo':
        return _heuristic_insights_ceo(context)

    kpis = context.get('kpis') or {}
    cmp_ = context.get('comparison') or {}
    ops = context.get('operations') or {}
    alerts = context.get('alerts') or []

    occ = float(kpis.get('occupancy_pct') or 0)
    adr = float(kpis.get('adr') or 0)
    revpar = float(kpis.get('revpar') or 0)
    cash = float(kpis.get('cash_collected') or 0)
    accr = float(kpis.get('accrual_gross') or 0)

    occ_delta = float(cmp_.get('occupancy_pct_delta') or 0)
    rev_delta = float(cmp_.get('accrual_gross_delta') or 0)

    # ── Summary ──
    if occ >= 80:
        occ_phrase = f"Occupancy is strong at {occ:.0f}%"
    elif occ >= 50:
        occ_phrase = f"Occupancy is moderate at {occ:.0f}%"
    else:
        occ_phrase = f"Occupancy is low at {occ:.0f}%"

    direction = "up" if rev_delta > 0 else ("down" if rev_delta < 0 else "flat")
    summary = (
        f"{occ_phrase}. ADR is ₹{adr:,.0f} and RevPAR is ₹{revpar:,.0f}. "
        f"Today's earned revenue is ₹{accr:,.0f} ({direction} ₹{abs(rev_delta):,.0f} vs yesterday). "
        f"Cash collected so far: ₹{cash:,.0f}."
    )

    # ── Issues ──
    issues: list[dict] = []

    if ops.get('overdue_checkouts', 0) > 0:
        n = ops['overdue_checkouts']
        issues.append({
            'title': f"{n} overdue check-out{'s' if n > 1 else ''}",
            'reason': "These rooms are still showing the old guest, "
                      "blocking new arrivals from being assigned.",
        })

    if ops.get('pending_arrivals', 0) > 0:
        n = ops['pending_arrivals']
        issues.append({
            'title': f"{n} pending check-in{'s' if n > 1 else ''}",
            'reason': "Reserved guests for today have not been checked in yet, "
                      "which delays room readiness reports and skews occupancy KPIs.",
        })

    if ops.get('dirty_rooms', 0) >= 5:
        issues.append({
            'title': f"{ops['dirty_rooms']} dirty rooms in inventory",
            'reason': "Housekeeping has not yet released these rooms back "
                      "for sale, reducing the number of rooms available to OTAs.",
        })

    if rev_delta < 0 and abs(rev_delta) >= max(1000.0, accr * 0.10):
        issues.append({
            'title': f"Revenue is ₹{abs(rev_delta):,.0f} below yesterday",
            'reason': "Earned room revenue dropped meaningfully compared to "
                      "the previous business day.",
        })

    if occ_delta <= -10:
        issues.append({
            'title': f"Occupancy dropped {abs(occ_delta):.0f} points vs yesterday",
            'reason': "A double-digit drop usually signals weak walk-ins or a "
                      "block of departures that wasn't backfilled by OTAs.",
        })

    high_alerts = [a for a in alerts if a.get('severity') == 'HIGH']
    if high_alerts:
        issues.append({
            'title': f"{len(high_alerts)} high-severity revenue alert"
                     f"{'s' if len(high_alerts) > 1 else ''}",
            'reason': high_alerts[0].get('message') or
                      "Revenue guard flagged unusual activity.",
        })

    # ── Actions ──
    actions: list[str] = []
    if ops.get('overdue_checkouts', 0) > 0:
        actions.append("Call each overdue guest to confirm departure or extend, "
                       "and have housekeeping ready those rooms.")
    if ops.get('pending_arrivals', 0) > 0:
        actions.append("Confirm pending arrivals over the phone or WhatsApp; "
                       "release no-shows after the cut-off.")
    if ops.get('dirty_rooms', 0) >= 5:
        actions.append("Push housekeeping to clear dirty rooms before peak "
                       "OTA booking hours (5–9 PM).")
    if occ < 60:
        actions.append("Open lower-tier OTA rates and check walk-in pricing — "
                       "the hotel has spare inventory to fill.")
    if high_alerts:
        actions.append("Open Revenue Alerts and resolve the high-severity items "
                       "before night audit.")

    if not issues and not actions:
        issues = []  # explicit
        actions = ["Hold the current rate strategy — KPIs look healthy."]

    return {
        'summary': summary,
        'issues': issues,
        'actions': actions,
        'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'source': 'heuristic',
        'model': None,
    }


# ──────────────────────────────────────────────────────────────────────
# Gemini call
# ──────────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """You are a hotel revenue analyst for {hotel_name}.
Analyse today's data ({business_date}) and produce a brief, business-focused insight report.

TODAY'S KPIs:
- Occupancy: {occupancy_pct}% ({occupied}/{sellable} sellable rooms)
- ADR: \u20b9{adr}
- RevPAR: \u20b9{revpar}
- Cash collected: \u20b9{cash_collected}
- Earned revenue (accrual): \u20b9{accrual_gross}
- OTA receivable: \u20b9{ota_receivable}

VS YESTERDAY:
- Occupancy delta: {occupancy_pct_delta} pts
- ADR delta: \u20b9{adr_delta}
- RevPAR delta: \u20b9{revpar_delta}
- Earned revenue delta: \u20b9{accrual_gross_delta}

OPERATIONS TODAY:
- Overdue check-outs: {overdue_checkouts}
- Pending check-ins: {pending_arrivals}
- Dirty rooms: {dirty_rooms}
- Out-of-order rooms: {out_of_order_rooms}

ACTIVE ALERTS ({alert_total}, {alert_high} high-severity):
{alert_block}

Produce a JSON object with EXACTLY these keys:
- "summary": 2-3 sentences in plain business English describing how the hotel
  is performing today. Mention the headline numbers. No jargon.
- "issues": array of 1-4 objects, each {{"title": "<short>", "reason": "<one sentence why>"}}.
  Each issue must be a real problem visible in the data above. If everything looks
  fine, return an empty array.
- "actions": array of 1-4 strings. Each is a concrete next step the front-office
  manager should take TODAY. Avoid vague advice like "monitor" or "review" \u2014
  say what to actually do.

Rules:
- Use simple language a non-technical hotelier understands.
- Use \u20b9 for currency. Round to whole rupees.
- Ground every statement in the numbers above. Do NOT invent metrics.
- Return ONLY the raw JSON object, no markdown, no backticks, no prose outside it.
"""


CEO_PROMPT_TEMPLATE = """You are reporting to the OWNER of {hotel_name}.
Produce a brief, ownership-level insight report for {business_date}.

TODAY'S CORE KPIs:
- Occupancy: {occupancy_pct}% ({occupied}/{sellable} sellable rooms)
- ADR: \u20b9{adr}
- RevPAR: \u20b9{revpar}
- Earned revenue: \u20b9{accrual_gross}

OTA FUNNEL TODAY:
- Bookings received: {ota_bookings_today}
- Arrivals expected: {ota_arrivals_today}
- Checked in: {ota_checkin_today}
- No-shows: {ota_noshows_today}
- Conversion: {ota_conversion_pct}%

OTA CHANNEL MIX (today):
{channel_mix_block}

OTA PIPELINE (next 30 days):
- Bookings on the books: {pipeline_bookings}
- Projected revenue: \u20b9{pipeline_revenue}

OTA RECEIVABLES:
- Total outstanding: \u20b9{ota_outstanding}
- 0-7 days bucket:   \u20b9{aging_0_7}
- 8-15 days bucket:  \u20b9{aging_8_15}
- 16-30 days bucket: \u20b9{aging_16_30}
- 30+ days bucket:   \u20b9{aging_30_plus}

NIGHT AUDIT HEALTH:
- Last completed audit: {last_audit_date} ({last_audit_status})
- Days behind: {audit_days_behind}

Produce a JSON object with EXACTLY these keys:
- "summary": 2-3 sentences in plain ownership English. Focus on the
  business story for today: where money came in, where it is stuck,
  and whether tomorrow's pipeline is healthy. Mention the headline
  numbers.
- "issues": array of 1-4 objects {{"title": "<short>", "reason": "<one sentence>"}}.
  Each issue must be a real problem visible above. Lean toward
  receivables aging, channel concentration risk, audit lag, and
  pipeline gaps. If everything looks fine, return an empty array.
- "actions": array of 1-4 strings. Each is a concrete strategic action
  the owner should take or instruct staff to take this week. Avoid
  vague advice like "monitor" or "review" \u2014 say what to actually do.

Rules:
- Use simple language a non-technical owner understands.
- Use \u20b9 for currency. Round to whole rupees.
- Ground every statement in the numbers above. Do NOT invent metrics.
- Return ONLY the raw JSON object, no markdown, no backticks, no prose outside it.
"""


def _format_alert_block(alerts: list) -> str:
    if not alerts:
        return '- (none)'
    return '\n'.join(
        f"- [{a.get('severity', '?')}] {a.get('alert_type', '?')}: "
        f"{a.get('message', '')}"
        for a in alerts[:5]
    )


def _format_channel_mix_block(rows: list) -> str:
    if not rows:
        return '- (no OTA bookings today)'
    lines = []
    for r in rows[:6]:
        lines.append(
            f"- {r.get('source', '?')}: {r.get('bookings', 0)} bookings, "
            f"{r.get('room_nights', 0)} room nights, "
            f"\u20b9{float(r.get('revenue_accrued', 0)):,.0f} accrued "
            f"(ADR \u20b9{float(r.get('adr', 0)):,.0f})"
        )
    return '\n'.join(lines)


def _build_prompt_ceo(context: dict) -> str:
    """CEO-flavored prompt — pulls from context['ceo'] (kpi pack)."""
    kpis = context.get('kpis') or {}
    ceo = context.get('ceo') or {}
    funnel = ceo.get('funnel') or {}
    pipeline = ceo.get('pipeline') or {}
    aging = ceo.get('receivable_aging') or {}
    audit = ceo.get('audit_health') or {}
    channel_mix = (ceo.get('channel_mix') or {}).get('today') or []

    aging_by_label = {b.get('label'): float(b.get('total') or 0)
                      for b in (aging.get('buckets') or [])}

    return CEO_PROMPT_TEMPLATE.format(
        hotel_name=context.get('hotel_name', 'the hotel'),
        business_date=context.get('business_date', ''),
        occupancy_pct=kpis.get('occupancy_pct', 0),
        occupied=kpis.get('occupied', 0),
        sellable=kpis.get('sellable', 0),
        adr=f"{float(kpis.get('adr') or 0):,.0f}",
        revpar=f"{float(kpis.get('revpar') or 0):,.0f}",
        accrual_gross=f"{float(kpis.get('accrual_gross') or 0):,.0f}",
        ota_bookings_today=funnel.get('bookings_received', 0),
        ota_arrivals_today=funnel.get('arrivals_expected', 0),
        ota_checkin_today=funnel.get('checked_in', 0),
        ota_noshows_today=funnel.get('no_shows', 0),
        ota_conversion_pct=funnel.get('conversion_pct', 0),
        channel_mix_block=_format_channel_mix_block(channel_mix),
        pipeline_bookings=pipeline.get('total_bookings', 0),
        pipeline_revenue=f"{float(pipeline.get('total_projected_revenue') or 0):,.0f}",
        ota_outstanding=f"{float(aging.get('total_outstanding') or 0):,.0f}",
        aging_0_7=f"{aging_by_label.get('0-7 days', 0):,.0f}",
        aging_8_15=f"{aging_by_label.get('8-15 days', 0):,.0f}",
        aging_16_30=f"{aging_by_label.get('16-30 days', 0):,.0f}",
        aging_30_plus=f"{aging_by_label.get('30+ days', 0):,.0f}",
        last_audit_date=audit.get('last_completed_audit_date') or '(none)',
        last_audit_status=audit.get('last_audit_status') or 'unknown',
        audit_days_behind=audit.get('days_behind', 0),
    )


def _build_prompt(context: dict) -> str:
    if (context.get('mode') or 'frontdesk') == 'ceo':
        return _build_prompt_ceo(context)

    kpis = context.get('kpis') or {}
    cmp_ = context.get('comparison') or {}
    ops = context.get('operations') or {}
    alerts = context.get('alerts') or []
    counts = context.get('alert_counts') or {}

    alert_block = _format_alert_block(alerts)

    return PROMPT_TEMPLATE.format(
        hotel_name=context.get('hotel_name', 'the hotel'),
        business_date=context.get('business_date', ''),
        occupancy_pct=kpis.get('occupancy_pct', 0),
        occupied=kpis.get('occupied', 0),
        sellable=kpis.get('sellable', 0),
        adr=f"{float(kpis.get('adr') or 0):,.0f}",
        revpar=f"{float(kpis.get('revpar') or 0):,.0f}",
        cash_collected=f"{float(kpis.get('cash_collected') or 0):,.0f}",
        accrual_gross=f"{float(kpis.get('accrual_gross') or 0):,.0f}",
        ota_receivable=f"{float(kpis.get('ota_receivable') or 0):,.0f}",
        occupancy_pct_delta=cmp_.get('occupancy_pct_delta', 0),
        adr_delta=f"{float(cmp_.get('adr_delta') or 0):,.0f}",
        revpar_delta=f"{float(cmp_.get('revpar_delta') or 0):,.0f}",
        accrual_gross_delta=f"{float(cmp_.get('accrual_gross_delta') or 0):,.0f}",
        overdue_checkouts=ops.get('overdue_checkouts', 0),
        pending_arrivals=ops.get('pending_arrivals', 0),
        dirty_rooms=ops.get('dirty_rooms', 0),
        out_of_order_rooms=ops.get('out_of_order_rooms', 0),
        alert_total=counts.get('total', 0),
        alert_high=counts.get('HIGH', 0),
        alert_block=alert_block,
    )


def _parse_gemini_json(raw: str) -> dict:
    """Tolerantly parse the model's response into our schema.

    Models occasionally wrap JSON in ```json ... ``` despite instructions.
    Strip such fences before parsing.
    """
    text = (raw or '').strip()
    if text.startswith('```'):
        # Drop leading ```json or ```
        text = text.split('\n', 1)[1] if '\n' in text else text[3:]
    if text.endswith('```'):
        text = text.rsplit('```', 1)[0]
    text = text.strip()
    return json.loads(text)


def _call_gemini(prompt: str, model: str = DEFAULT_MODEL) -> dict | None:
    """Call Gemini and return parsed JSON. Returns None on any failure.

    Imports the SDK lazily so the package being absent doesn't break
    module import for offline deployments that never set GEMINI_API_KEY.
    """
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None

    try:
        # New unified Google GenAI SDK
        from google import genai
        from google.genai import types as genai_types
    except Exception as exc:
        log.warning('AI insights: google-genai SDK not installed (%s); '
                    'falling back to heuristic', exc)
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.4,
                max_output_tokens=1024,
            ),
        )
        raw = getattr(response, 'text', None) or ''
        if not raw:
            log.warning('AI insights: empty Gemini response')
            return None
        return _parse_gemini_json(raw)
    except Exception as exc:
        log.warning('AI insights: Gemini call failed (%s); falling back to '
                    'heuristic', exc)
        return None


def _normalise(parsed: dict, model: str) -> dict:
    """Coerce a Gemini response into the canonical insights schema."""
    summary = str(parsed.get('summary') or '').strip()
    raw_issues = parsed.get('issues') or []
    raw_actions = parsed.get('actions') or []

    issues: list[dict] = []
    for item in raw_issues[:6]:
        if isinstance(item, dict):
            t = str(item.get('title') or '').strip()
            r = str(item.get('reason') or '').strip()
            if t:
                issues.append({'title': t, 'reason': r})
        elif isinstance(item, str) and item.strip():
            issues.append({'title': item.strip(), 'reason': ''})

    actions: list[str] = []
    for item in raw_actions[:6]:
        if isinstance(item, str) and item.strip():
            actions.append(item.strip())
        elif isinstance(item, dict):
            txt = item.get('action') or item.get('text') or item.get('title')
            if isinstance(txt, str) and txt.strip():
                actions.append(txt.strip())

    return {
        'summary': summary or '(no summary returned)',
        'issues': issues,
        'actions': actions,
        'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'source': 'gemini',
        'model': model,
    }


def generate_insights(context: dict, model: str = DEFAULT_MODEL) -> dict:
    """Produce an insights dict for *context*.

    Tries Gemini first; on any failure (no key, no SDK, network down,
    bad JSON), falls back to ``_heuristic_insights`` so the caller
    always gets a valid, well-shaped result. The mode is read from
    ``context['mode']`` so the dispatcher can pick the right prompt
    and heuristic.
    """
    prompt = _build_prompt(context)
    parsed = _call_gemini(prompt, model=model)
    if parsed is None:
        return _heuristic_insights(context)
    try:
        return _normalise(parsed, model)
    except Exception as exc:
        log.warning('AI insights: failed to normalise Gemini response (%s); '
                    'falling back to heuristic', exc)
        return _heuristic_insights(context)


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────

def _cache_key(business_date: date, mode: str) -> str:
    return f'{mode}:{business_date.isoformat()}'


def get_insights(business_date: date | None = None,
                 force_refresh: bool = False,
                 mode: str = 'frontdesk') -> dict:
    """Cached, end-to-end entry point used by the API route.

    The cache key includes ``mode`` so the front-desk and CEO views
    do not collide. Returns a dict with: ``summary``, ``issues``,
    ``actions``, ``generated_at``, ``source`` ('gemini' | 'heuristic'),
    ``model``, ``mode``, and a ``kpi_snapshot`` block the dashboard
    can render alongside.
    """
    if business_date is None:
        from app.services import get_business_date
        business_date = get_business_date()
    if mode not in ('frontdesk', 'ceo'):
        mode = 'frontdesk'

    key = _cache_key(business_date, mode)
    if not force_refresh:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    context = gather_context(business_date, mode=mode)
    insights = generate_insights(context)
    insights['mode'] = mode

    # Attach a small KPI snapshot the dashboard can show without making
    # a second round-trip. We deliberately do NOT include the full alerts
    # array — the dashboard already renders alerts elsewhere.
    kpis = context.get('kpis') or {}
    snapshot = {
        'business_date': context['business_date'],
        'hotel_name': context['hotel_name'],
        'occupancy_pct': kpis.get('occupancy_pct', 0),
        'adr': kpis.get('adr', 0),
        'revpar': kpis.get('revpar', 0),
        'cash_collected': kpis.get('cash_collected', 0),
        'accrual_gross': kpis.get('accrual_gross', 0),
        'alert_total': (context.get('alert_counts') or {}).get('total', 0),
    }
    if mode == 'ceo':
        ceo = context.get('ceo') or {}
        snapshot['ceo_headline'] = ceo.get('headline') or {}
    insights['kpi_snapshot'] = snapshot

    _cache_put(key, insights)
    return insights


def clear_cache(business_date: date | None = None,
                mode: str | None = None) -> None:
    """Used by the force-refresh endpoint and by tests.

    - ``clear_cache()``                — clear everything
    - ``clear_cache(date)``            — clear both modes for that date
    - ``clear_cache(date, 'ceo')``     — clear just the CEO cache for that date
    """
    if business_date is None:
        _cache_clear()
        return
    if mode is None:
        _cache_clear(_cache_key(business_date, 'frontdesk'))
        _cache_clear(_cache_key(business_date, 'ceo'))
    else:
        _cache_clear(_cache_key(business_date, mode))
