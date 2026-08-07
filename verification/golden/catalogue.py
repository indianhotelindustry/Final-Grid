"""
The surface catalogue — what the golden master covers, and what it does not.

Discovery is automatic (every GET rule in the application's URL map) but
inclusion is governed:

  * every surface is classified into a category, and the category fixes
    the blocking severity;
  * every exclusion is declared here with a reason and is printed on
    every run, so "not covered" is always visible;
  * a surface that appears in the URL map and matches no classification
    rule is reported as UNCLASSIFIED and captured at WARN. New routes
    therefore show up as an explicit gap rather than quietly escaping
    verification.

Parameterised surfaces (an invoice, a folio, a night audit snapshot) are
the ones that carry the most financial weight, so they are included with
entity ids resolved deterministically from the data — always the lowest
id matching a stated rule, never a random sample.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from verification.config import Severity


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class Category:
    #: Renders money, or a figure a money decision is taken on. A change
    #: here blocks a release until it is explained.
    FINANCIAL = 'FINANCIAL'

    #: Operational state — rooms, housekeeping, guests, users. Wrong
    #: output disrupts the hotel but does not misstate the accounts.
    OPERATIONAL = 'OPERATIONAL'

    #: Advisory / derived / forecast surfaces. Recorded for drift, never
    #: blocking, because the underlying models are estimative by design.
    ADVISORY = 'ADVISORY'

    #: Public surfaces (booking engine, health probes).
    PUBLIC = 'PUBLIC'

    #: Matched no rule. Captured, reported, and treated as WARN so that a
    #: newly added route cannot escape verification unnoticed.
    UNCLASSIFIED = 'UNCLASSIFIED'


CATEGORY_SEVERITY = {
    Category.FINANCIAL: Severity.BLOCK,
    Category.OPERATIONAL: Severity.WARN,
    Category.ADVISORY: Severity.INFO,
    Category.PUBLIC: Severity.INFO,
    Category.UNCLASSIFIED: Severity.WARN,
}


# ---------------------------------------------------------------------------
# Classification rules — first match wins, evaluated in order
# ---------------------------------------------------------------------------

#: (regex on the URL rule, category). Ordered: the specific before the
#: general, because ``/reports/`` would otherwise swallow everything
#: under it.
CLASSIFICATION: list[tuple[str, str]] = [
    # -- advisory / AI must precede the generic /api/ rule --------------
    (r'^/ai/', Category.ADVISORY),
    (r'^/api/ai/', Category.ADVISORY),
    (r'^/api/ceo/kpi-pack', Category.ADVISORY),

    # -- public --------------------------------------------------------
    (r'^/book/', Category.PUBLIC),
    (r'^/health$', Category.PUBLIC),
    (r'^/api/health$', Category.PUBLIC),
    (r'^/feedback/(submit|complete)', Category.PUBLIC),

    # -- financial -----------------------------------------------------
    (r'^/reports/', Category.FINANCIAL),
    (r'^/billing/', Category.FINANCIAL),
    (r'^/invoice', Category.FINANCIAL),
    (r'^/advance-receipt/', Category.FINANCIAL),
    (r'^/folio/', Category.FINANCIAL),
    (r'^/api/invoice-detail/', Category.FINANCIAL),
    (r'^/api/reservation/\d+/folios', Category.FINANCIAL),
    (r'^/credit/', Category.FINANCIAL),
    (r'^/night-audit', Category.FINANCIAL),
    (r'^/dashboard', Category.FINANCIAL),
    (r'^/api/dashboard/', Category.FINANCIAL),
    (r'^/api/analytics/data', Category.FINANCIAL),
    (r'^/ceo$', Category.FINANCIAL),
    (r'^/ota/', Category.FINANCIAL),
    (r'^/pos/', Category.FINANCIAL),
    (r'^/noshow/report', Category.FINANCIAL),
    (r'^/guest/\d+$', Category.FINANCIAL),          # guest folio
    (r'^/checkout/', Category.FINANCIAL),
    (r'^/api/checkin/company/', Category.FINANCIAL),
    (r'^/loyalty/(transactions|milestones|config)', Category.FINANCIAL),
    (r'^/api/voucher/', Category.FINANCIAL),

    # -- operational ---------------------------------------------------
    (r'^/reservations', Category.OPERATIONAL),
    (r'^/reservation/', Category.OPERATIONAL),
    (r'^/api/reservation/', Category.OPERATIONAL),
    (r'^/rooms?', Category.OPERATIONAL),
    (r'^/room-grid', Category.OPERATIONAL),
    (r'^/api/rooms?/', Category.OPERATIONAL),
    (r'^/housekeeping', Category.OPERATIONAL),
    (r'^/hk$', Category.OPERATIONAL),
    (r'^/maintenance/', Category.OPERATIONAL),
    (r'^/guests', Category.OPERATIONAL),
    (r'^/guest-database', Category.OPERATIONAL),
    (r'^/guest/\d+/history', Category.OPERATIONAL),
    (r'^/api/guests/', Category.OPERATIONAL),
    (r'^/api/search-guests', Category.OPERATIONAL),
    (r'^/groups', Category.OPERATIONAL),
    (r'^/grc/', Category.OPERATIONAL),
    (r'^/noshow/', Category.OPERATIONAL),
    (r'^/loyalty/', Category.OPERATIONAL),
    (r'^/rates/', Category.OPERATIONAL),
    (r'^/portal/', Category.OPERATIONAL),
    (r'^/feedback/', Category.OPERATIONAL),
    (r'^/auth/', Category.OPERATIONAL),
    (r'^/masters$', Category.OPERATIONAL),
    (r'^/setup$', Category.OPERATIONAL),
    (r'^/checkin/', Category.OPERATIONAL),
    (r'^/backup/$', Category.OPERATIONAL),
    (r'^/admin/', Category.OPERATIONAL),
    (r'^/owner/', Category.OPERATIONAL),
    (r'^/webhook/logs', Category.OPERATIONAL),
    (r'^/api/alerts/', Category.OPERATIONAL),
    (r'^/api/companies', Category.OPERATIONAL),
    (r'^/api/staff/', Category.OPERATIONAL),
    (r'^/api/cico/', Category.OPERATIONAL),
    (r'^/api/tab/', Category.OPERATIONAL),
    (r'^/$', Category.OPERATIONAL),
]


# ---------------------------------------------------------------------------
# Declared exclusions — printed on every run
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Exclusion:
    pattern: str
    reason: str


EXCLUSIONS: list[Exclusion] = [
    Exclusion(r'^/static/', 'Static assets. Not application output.'),
    Exclusion(r'^/admin/update',
              'Updater. Reaches the network and can stage a release; '
              'exercising it from a verification harness is unsafe.'),
    Exclusion(r'^/admin/reset-transactional-data',
              'Destructive by design. Never exercised by the harness, '
              'even against a copy, so that a path confusion bug can '
              'never destroy data.'),
    Exclusion(r'^/backup/download',
              'Streams a file; content is the backup, not application '
              'output. Covered instead by D9 (Backup Restore '
              'Verification).'),
    Exclusion(r'^/private-uploads/',
              'Serves uploaded guest documents. Excluded so that guest '
              'identity documents are never written into an evidence '
              'pack.'),
    Exclusion(r'^/webhook/ping',
              'Liveness probe for an external channel manager.'),
    Exclusion(r'^/auth/shift/close',
              'GET handler with a side effect (closes the open shift). '
              'Excluded to keep capture free of state change; shift '
              'closure figures are covered by Q21 and by '
              '/reports/shift-reconciliation.'),
    Exclusion(r'^/feedback/submit/',
              'Requires a single-use guest token. Deferred to D6 '
              '(Regression Dataset Framework), which can mint one.'),
    Exclusion(r'^/portal/[^/]+$',
              'Requires a pre-check-in token. Deferred to D6.'),
    Exclusion(r'^/portal/[^/]+/complete',
              'Requires a pre-check-in token. Deferred to D6.'),
    Exclusion(r'^/book/confirmation/',
              'Requires a booking reference issued by the public engine. '
              'Deferred to D6.'),
]


def excluded_reason(path: str) -> str:
    for ex in EXCLUSIONS:
        if re.search(ex.pattern, path):
            return ex.reason
    return ''


def classify(path: str) -> str:
    for pattern, category in CLASSIFICATION:
        if re.search(pattern, path):
            return category
    return Category.UNCLASSIFIED


# ---------------------------------------------------------------------------
# Surfaces
# ---------------------------------------------------------------------------

@dataclass
class Surface:
    """One capturable URL."""
    surface_id: str
    url: str
    endpoint: str
    category: str
    severity: str
    origin: str                     # 'discovered' | 'declared'
    note: str = ''
    params: dict = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_')


def _make(endpoint: str, url: str, origin: str, note: str = '',
          params: dict | None = None) -> Surface:
    category = classify(url.split('?')[0])
    qs = url.split('?')[1] if '?' in url else ''
    sid = endpoint if not qs else f'{endpoint}__{_slug(qs)}'
    return Surface(surface_id=sid, url=url, endpoint=endpoint,
                   category=category, severity=CATEGORY_SEVERITY[category],
                   origin=origin, note=note, params=params or {})


# ---------------------------------------------------------------------------
# Declared parameterised surfaces
# ---------------------------------------------------------------------------
#
# Each entry names a resolver that picks an entity DETERMINISTICALLY —
# always the lowest id satisfying the stated rule. A random or "latest"
# pick would make the master depend on data insertion order.

def _resolvers() -> dict:
    """Resolve pinned entity ids from the working copy.

    Returns ``{name: (id or None, rule_text)}``. A resolver that finds
    nothing yields ``None`` and the surface is reported as
    UNRESOLVED — stated explicitly, never skipped silently.
    """
    from app.models import Reservation, Guest, NightAuditLog, Room, Company

    def first_id(query, rule):
        row = query.first()
        return (row.id if row else None), rule

    out = {}
    out['checked_out_reservation'] = first_id(
        Reservation.query.filter_by(status='CheckedOut')
                         .order_by(Reservation.id),
        'lowest reservation id with status CheckedOut')
    out['inhouse_reservation'] = first_id(
        Reservation.query.filter_by(status='CheckedIn')
                         .order_by(Reservation.id),
        'lowest reservation id with status CheckedIn')
    out['any_reservation'] = first_id(
        Reservation.query.order_by(Reservation.id),
        'lowest reservation id')
    out['any_guest'] = first_id(
        Guest.query.order_by(Guest.id), 'lowest guest id')
    out['night_audit_log'] = first_id(
        NightAuditLog.query.order_by(NightAuditLog.id),
        'lowest night audit log id')
    out['any_room'] = first_id(
        Room.query.order_by(Room.id), 'lowest room id')
    out['any_company'] = first_id(
        Company.query.order_by(Company.id), 'lowest company id')

    from app.models import Payment, GroupBlock
    out['any_payment'] = first_id(
        Payment.query.order_by(Payment.id), 'lowest payment id')
    out['any_group'] = first_id(
        GroupBlock.query.order_by(GroupBlock.id), 'lowest group block id')
    return out


#: (endpoint, url template, resolver name, note)
DECLARED_PARAMETERISED: list[tuple[str, str, str, str]] = [
    ('main.invoice', '/invoice/{id}', 'checked_out_reservation',
     'Tax invoice — the document the guest is charged on.'),
    ('main.invoice_detail_api', '/api/invoice-detail/{id}',
     'checked_out_reservation', 'Invoice figures as consumed by the UI.'),
    ('main.reservation_folio', '/folio/{id}', 'checked_out_reservation',
     'Folio ledger for a settled stay.'),
    ('main.reservation_folio', '/folio/{id}', 'inhouse_reservation',
     'Folio ledger for an open stay — the unsettled case.'),
    ('folio.list_folios', '/api/reservation/{id}/folios',
     'checked_out_reservation', 'Split-billing sub-ledger.'),
    ('main.get_reservation', '/api/reservation/{id}', 'any_reservation',
     'Reservation as served to the UI.'),
    ('main.checkout', '/checkout/{id}', 'inhouse_reservation',
     'Checkout screen — settlement figures before they are posted.'),
    ('main.advance_receipt', '/advance-receipt/{id}', 'any_reservation',
     'Advance receipt document.'),
    ('main.guest_folio', '/guest/{id}', 'any_guest',
     'Guest-level folio.'),
    ('main.guest_history', '/guest/{id}/history', 'any_guest',
     'Guest stay history.'),
    ('reports.night_audit_snapshot', '/reports/night-audit/{id}',
     'night_audit_log',
     'A closed night audit as stored — the immutable financial record.'),
    ('pos.room_charges_api', '/pos/api/room-charges/{id}',
     'inhouse_reservation', 'POS charges posted to a room.'),
    ('main.get_room_tariff', '/api/room/{id}/tariff', 'any_room',
     'Tariff lookup used when a rate is applied.'),
    ('main.get_company_credit', '/api/checkin/company/{id}', 'any_company',
     'Corporate credit limit check.'),
    ('grc.preview', '/grc/{id}/preview', 'any_reservation',
     'Guest registration card.'),
    ('main.nightly_rate_inspector', '/reservations/{id}/nightly-rates',
     'any_reservation', 'Per-night rate breakdown.'),
    ('billing.void_history', '/billing/void/history/{id}', 'any_reservation',
     'Void and reversal history for a stay.'),
    ('groups.detail', '/groups/{id}', 'any_group',
     'Group block — its rooms and its shared billing.'),
    ('loyalty.api_balance', '/loyalty/api/balance/{id}', 'any_guest',
     'Loyalty point balance, redeemable against a bill.'),
    ('main.company_detail', '/api/companies/{id}', 'any_company',
     'Corporate account as served to the UI.'),
    ('billing.void_eligible', '/billing/void/eligible/{id}', 'any_payment',
     'Whether a payment may still be voided — the gate on reversals.'),
    ('main.edit_reservation', '/reservation/{id}/edit', 'any_reservation',
     'Reservation edit screen, where tariffs are changed.'),
    ('portal.view_submission', '/portal/submissions/{id}', 'any_reservation',
     'Pre-check-in submission for a stay.'),
]


#: Parameterised surfaces whose path parameter is an enumerated NAME
#: rather than an entity id. Listed explicitly because guessing them
#: from the URL map is impossible — the valid values live in ``if``
#: statements inside the handler.
DECLARED_NAMED_PARAMS: list[tuple[str, str, str]] = [
    ('main.load_dashboard_tab', '/api/dashboard/analytics',
     'Dashboard analytics tab shell.'),
    ('main.load_dashboard_tab', '/api/dashboard/command-center',
     'KPI command centre tab shell — targets, variance, forecast.'),
    ('main.load_tab', '/api/tab/overview',
     'Dashboard overview tab, refreshed by AJAX. Its figures must match '
     'the initial dashboard render.'),
    ('main.load_tab', '/api/tab/booking', 'Booking tab.'),
    ('main.load_tab', '/api/tab/reservations', 'Reservations tab.'),
]


#: Surfaces worth capturing more than once because their output depends
#: on a query argument that a user routinely changes. The date is pinned
#: to the business date so the master does not depend on the wall clock.
DECLARED_QUERY_VARIANTS: list[tuple[str, str, str]] = [
    ('reports.flash_report', '/reports/flash?date={business_date}',
     'Flash report for the current business date.'),
    ('reports.daily_reconciliation',
     '/reports/daily-reconciliation?date={business_date}',
     'Daily reconciliation for the current business date.'),
    ('reports.payment_collection',
     '/reports/payments?start_date={month_start}&end_date={business_date}',
     'Payment collection, month to date.'),
    ('reports.revenue',
     '/reports/revenue?start_date={month_start}&end_date={business_date}',
     'Revenue report, month to date.'),
    ('reports.front_office_mis',
     '/reports/front-office-mis?from_date={month_start}&to_date={business_date}',
     'Front office MIS, month to date.'),
    ('reports.occupancy',
     '/reports/occupancy?start_date={month_start}&end_date={business_date}',
     'Occupancy, month to date.'),
]


def build(app, business_date) -> tuple[list[Surface], list[dict]]:
    """Build the full catalogue against a live application.

    Returns ``(surfaces, gaps)`` where *gaps* records every URL that was
    discovered but not captured, with the reason. Nothing is dropped
    without an entry there.
    """
    from datetime import date as _date

    surfaces: list[Surface] = []
    gaps: list[dict] = []
    seen_urls: set[str] = set()

    # -- 1. discovered, parameterless ----------------------------------
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        path = str(rule)
        methods = rule.methods - {'HEAD', 'OPTIONS'}
        if 'GET' not in methods:
            gaps.append({'url': path, 'endpoint': rule.endpoint,
                         'reason': 'not a GET surface'})
            continue
        reason = excluded_reason(path)
        if reason:
            gaps.append({'url': path, 'endpoint': rule.endpoint,
                         'reason': reason})
            continue
        if '<' in path:
            # Handled by the declared lists below; recorded here so an
            # unhandled parameterised route stays visible.
            declared = (any(d[0] == rule.endpoint for d in DECLARED_PARAMETERISED)
                        or any(d[0] == rule.endpoint
                               for d in DECLARED_NAMED_PARAMS))
            if not declared:
                gaps.append({
                    'url': path, 'endpoint': rule.endpoint,
                    'reason': 'parameterised and not declared in '
                              'DECLARED_PARAMETERISED'})
            continue
        s = _make(rule.endpoint, path, 'discovered')
        surfaces.append(s)
        seen_urls.add(path)

    # -- 2. declared parameterised -------------------------------------
    resolved = _resolvers()
    for endpoint, template, resolver, note in DECLARED_PARAMETERISED:
        entity_id, rule_text = resolved.get(resolver, (None, resolver))
        if entity_id is None:
            gaps.append({'url': template, 'endpoint': endpoint,
                         'reason': f'UNRESOLVED — no entity matches: {rule_text}'})
            continue
        url = template.format(id=entity_id)
        s = _make(endpoint, url, 'declared', note,
                  {'resolver': resolver, 'rule': rule_text, 'id': entity_id})
        s.surface_id = f'{endpoint}__{resolver}'
        surfaces.append(s)

    # -- 2b. declared named-parameter surfaces -------------------------
    for endpoint, url, note in DECLARED_NAMED_PARAMS:
        s = _make(endpoint, url, 'declared', note)
        s.surface_id = f'{endpoint}__{_slug(url.rsplit("/", 1)[-1])}'
        surfaces.append(s)

    # -- 3. declared query variants ------------------------------------
    month_start = business_date.replace(day=1)
    subst = {'business_date': business_date.isoformat(),
             'month_start': month_start.isoformat()}
    for endpoint, template, note in DECLARED_QUERY_VARIANTS:
        url = template.format(**subst)
        s = _make(endpoint, url, 'declared', note, dict(subst))
        surfaces.append(s)

    surfaces.sort(key=lambda s: s.surface_id)
    gaps.sort(key=lambda g: (g['url'], g['endpoint']))
    return surfaces, gaps
