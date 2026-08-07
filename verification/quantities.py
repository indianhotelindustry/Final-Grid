"""
The 22 parity quantities — Phase 2.6 §5.

Each quantity is measured by EVERY implementation the codebase currently
contains, and the results are compared against each other. Where the
codebase has converged on one implementation, the verdict is
SINGLE_SOURCE and the value is still recorded as baseline evidence.

Read-only contract
------------------
No function here may call anything that writes. Two application helpers
are deliberately NOT used and the reason is recorded at the call site:

  * ``gst_service.get_folio_gst_summary()`` — calls ``ensure_all_tax_lines``
    which COMMITS (app/gst_service.py:590). TaxLine rows are queried
    directly instead.
  * ``services.run_night_audit()`` — posts charges and advances the
    business date. ``NightAuditService`` (the read-only report builder)
    is used instead.

Every measurement is wrapped so an exception becomes an ERROR verdict for
that quantity alone, never a crashed run. A partial result with a visible
error is useful; a crash is not.
"""
from __future__ import annotations

import time
import traceback
from decimal import Decimal
from typing import Any, Callable

from verification.config import Policy, Severity, Verdict
from verification.evidence import Divergence, QuantityResult

#: Registry populated by the @quantity decorator. Ordered by declaration.
REGISTRY: list[tuple[str, str, str, str, bool, Callable]] = []


def quantity(qid: str, label: str, policy: str, severity: str,
             self_compared: bool = False):
    """Register a measurement function as one of the parity quantities.

    ``self_compared`` marks a quantity that measures SEVERAL DISTINCT
    CONCEPTS in one result — a report's revenue, occupancy and ADR, say —
    and has already compared each concept against its own counterpart.
    For those, the default flat comparison is not merely redundant, it is
    wrong: it would compare ADR against accrual revenue and report a
    divergence that means nothing. Q16 did exactly that the first time it
    ran, reporting DIVERGED while all seven of its concept pairs agreed.
    """
    def deco(fn):
        REGISTRY.append((qid, label, policy, severity, self_compared, fn))
        return fn
    return deco


# ---------------------------------------------------------------------------
# Legacy identifiers (Wave 0.5)
# ---------------------------------------------------------------------------

#: These quantities were declared ``P01``-``P22`` until Wave 0.5. The prefix
#: collided with the constitutional principles ``P1``-``P14``: README line
#: 357 read "P11 and P21 are VACUOUS" — quantities — while
#: ``datasets/model.py`` read "P11 (observable correctness)" — a principle.
#: Two different P11s in one framework, one of them constitutional.
#:
#: The quantities were renamed because they are the junior namespace; the
#: constitution is cited by external governance documents and by every
#: invariant declaration.
#:
#: Retained evidence is NOT rewritten. The 81 evidence packs and
#: ``baselines/v2.2.18_preWave1.json`` are release evidence under P12
#: (historical immutability) and Phase 2.6 §13; editing them so that a
#: measurement taken in August reads as though it had always used the new
#: identifier would be falsifying the record — precisely the failure mode
#: this framework exists to detect. So the old identifiers stay in the
#: artifacts and are translated on READ instead.
LEGACY_QUANTITY_IDS: dict = {f'P{n:02d}': f'Q{n:02d}' for n in range(1, 23)}


def canonical_quantity_id(qid: str) -> str:
    """Translate a pre-Wave-0.5 quantity id to its current form.

    Returns ``qid`` unchanged if it is already canonical or unrecognised —
    an unknown id is the caller's problem to report, not this function's
    to silently rewrite.
    """
    return LEGACY_QUANTITY_IDS.get(qid, qid)


def canonicalise_quantity_map(mapping: dict) -> dict:
    """Rekey a stored ``{quantity_id: ...}`` map onto canonical ids.

    Used when reading a baseline captured before the rename. A file
    already keyed canonically passes through unchanged, so this is safe to
    apply unconditionally.

    A collision — the same quantity present under both its legacy and its
    canonical id — is refused rather than resolved. Silently preferring
    one would make the release gate compare against a value nobody chose.
    """
    out: dict = {}
    for key, value in mapping.items():
        canonical = canonical_quantity_id(key)
        if canonical in out:
            raise ValueError(
                f'Baseline contains {canonical!r} under both its legacy and '
                f'its canonical identifier. Refusing to guess which value '
                f'the release gate should compare against.')
        out[canonical] = value
    return out


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _d(v) -> Decimal:
    """Coerce to Decimal for comparison. None becomes zero.

    Raises on non-numeric input by design — a silent coercion to zero
    would let a broken measurement report agreement.
    """
    if v is None:
        return Decimal('0')
    if isinstance(v, Decimal):
        return v
    return Decimal(str(round(float(v), 4)))


def _numeric(v):
    """Return ``v`` as Decimal, or ``None`` if it is not a number.

    Some quantities legitimately carry descriptive implementations (a
    status distribution, a count of recomputations). Those are compared
    by exact string equality instead of numerically. Detecting that here
    keeps the distinction in one place rather than special-casing it in
    every comparator.
    """
    try:
        return _d(v)
    except (TypeError, ValueError, ArithmeticError):
        return None


def compare(impls: dict[str, Any], policy: str,
            divergences: list[Divergence] | None = None,
            *, population: int | None = None,
            pairwise: bool = True) -> str:
    """Compare implementations of one quantity and return a verdict.

    ``population`` is the number of underlying records the quantity was
    computed from. When it is zero the verdict is VACUOUS regardless of
    agreement — implementations that both return zero over an empty set
    have not been shown to agree about anything (Principle 10).

    ``pairwise=False`` is for quantities that carry several distinct
    concepts and have already compared each against its own counterpart;
    see ``quantity(self_compared=True)``.
    """
    if population == 0:
        return Verdict.VACUOUS
    if len(impls) < 2:
        return Verdict.SINGLE_SOURCE
    if divergences:
        return Verdict.DIVERGED
    if not pairwise:
        # Every concept was compared against its own counterpart by the
        # quantity itself and none diverged.
        return Verdict.AGREED
    if policy in (Policy.INFORMATIONAL, Policy.DIRECTIONAL):
        return Verdict.AGREED

    names = sorted(impls)
    tol = Decimal('1.00') if policy == Policy.RUPEE else Decimal('0')
    base_name = names[0]
    base = _numeric(impls[base_name])

    if base is None:
        # Descriptive implementations — compare by exact string equality.
        first = str(impls[base_name])
        for other in names[1:]:
            if str(impls[other]) != first:
                return Verdict.DIVERGED
        return Verdict.AGREED

    for other in names[1:]:
        val = _numeric(impls[other])
        if val is None:
            # Mixed numeric and descriptive: not comparable. Never report
            # agreement for something that was not actually compared.
            return Verdict.SINGLE_SOURCE
        if abs(val - base) > tol:
            return Verdict.DIVERGED
    return Verdict.AGREED


def scalar_divergences(impls: dict[str, Any], policy: str,
                       scope: str = 'total') -> list[Divergence]:
    """Pairwise divergences between scalar implementations."""
    out: list[Divergence] = []
    if policy in (Policy.INFORMATIONAL, Policy.DIRECTIONAL):
        return out
    tol = Decimal('1.00') if policy == Policy.RUPEE else Decimal('0')
    names = sorted(impls)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            va, vb = _numeric(impls[a]), _numeric(impls[b])
            if va is None or vb is None:
                if str(impls[a]) != str(impls[b]):
                    out.append(Divergence(scope, a, b, impls[a], impls[b],
                                          'not numerically comparable'))
                continue
            delta = va - vb
            if abs(delta) > tol:
                out.append(Divergence(scope, a, b, impls[a], impls[b], str(delta)))
    return out


# ---------------------------------------------------------------------------
# Measurement context
# ---------------------------------------------------------------------------

class Context:
    """Loaded once per run and shared by every measurement.

    Holds the entity populations so twenty-two measurements do not each
    re-query the database, and so every quantity is measured against
    exactly the same snapshot of state.
    """

    def __init__(self, app):
        self.app = app
        from app.models import (db, Reservation, Payment, ExtraCharge, TaxLine,
                                Folio, NightAuditLog, Shift, Company, CreditNote,
                                Room, PaymentMode, OTAPayout)
        self.db = db
        self.M = dict(Reservation=Reservation, Payment=Payment,
                      ExtraCharge=ExtraCharge, TaxLine=TaxLine, Folio=Folio,
                      NightAuditLog=NightAuditLog, Shift=Shift, Company=Company,
                      CreditNote=CreditNote, Room=Room, PaymentMode=PaymentMode,
                      OTAPayout=OTAPayout)

        self.reservations = Reservation.query.order_by(Reservation.id).all()
        self.folios = Folio.query.order_by(Folio.id).all()
        self.audit_logs = NightAuditLog.query.order_by(
            NightAuditLog.audit_date).all()
        self.shifts = Shift.query.order_by(Shift.id).all()

        # Every business date carrying financial activity.
        dates: set = set()
        for (d,) in db.session.query(Payment.payment_date).distinct():
            if d:
                dates.add(d)
        for (d,) in db.session.query(ExtraCharge.charge_date).distinct():
            if d:
                dates.add(d)
        self.activity_dates = sorted(dates)

        from app.services import get_business_date
        self.business_date = get_business_date()

        # NightAuditService is expensive to construct (loads the full day).
        # Build once per audited date and cache.
        self._nas_cache: dict = {}

    def nas(self, d):
        """Cached read-only NightAuditService for a business date."""
        if d not in self._nas_cache:
            from app.night_audit_service import NightAuditService
            self._nas_cache[d] = NightAuditService(d)
        return self._nas_cache[d]


# ---------------------------------------------------------------------------
# Q01 — Reservation census
# ---------------------------------------------------------------------------

@quantity('Q01', 'Reservation count and status distribution',
          Policy.EXACT, Severity.BLOCK)
def q01(ctx: Context) -> tuple[dict, list, dict, str]:
    by_status: dict[str, int] = {}
    for r in ctx.reservations:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    impls = {'reservations.count': len(ctx.reservations)}
    detail = {'by_status': dict(sorted(by_status.items())),
              'by_source': {}}
    src: dict[str, int] = {}
    for r in ctx.reservations:
        src[r.source or 'NULL'] = src.get(r.source or 'NULL', 0) + 1
    detail['by_source'] = dict(sorted(src.items()))
    return impls, [], detail, 'Census — establishes the denominator for every other quantity.'


# ---------------------------------------------------------------------------
# Q02 — Charge census
# ---------------------------------------------------------------------------

@quantity('Q02', 'Charge count and total by category',
          Policy.EXACT, Severity.BLOCK)
def q02(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import signed_extra_charge_amount
    EC = ctx.M['ExtraCharge']
    charges = EC.query.order_by(EC.id).all()

    raw = sum(_d(c.amount) for c in charges)
    signed = sum(_d(signed_extra_charge_amount(c)) for c in charges)

    by_cat: dict[str, str] = {}
    for c in charges:
        key = (c.charge_category or c.charge_type or 'UNCLASSIFIED')
        by_cat[key] = str(_d(by_cat.get(key, 0)) + _d(c.amount))

    impls = {
        'raw sum(amount)': str(raw),
        'signed sum (correction-aware)': str(signed),
    }
    div = scalar_divergences(impls, Policy.EXACT, 'all charges')
    detail = {'count': len(charges), 'by_category': dict(sorted(by_cat.items())),
              'reversal_rows': sum(1 for c in charges
                                   if getattr(c, 'is_reversal', False))}
    note = ('Raw and signed agree only while no reversal rows exist. '
            'Reversal count is reported so the agreement is not mistaken '
            'for proof that signing works.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q03 — Room revenue per reservation (THE three-definition quantity)
# ---------------------------------------------------------------------------

@quantity('Q03', 'Room revenue per reservation (3 definitions)',
          Policy.EXACT, Severity.BLOCK)
def q03(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import get_room_revenue, is_room_rent_charge

    tot_canonical = Decimal('0')
    tot_single_night = Decimal('0')
    tot_rate_nights = Decimal('0')
    div: list[Divergence] = []
    per_res: dict[str, dict] = {}
    with_room_rent = 0

    for r in ctx.reservations:
        nights = max(0, (r.departure_date - r.arrival_date).days)

        # D1 — canonical: services.get_room_revenue (CASE A then CASE B)
        d1 = _d(get_room_revenue(r))

        # D2 — night_audit_service.revenue_summary / kpi_helpers accrual:
        #      one night's tariff for an in-house reservation
        d2 = _d(r.rate_per_night)

        # D3 — reports.py: rate_per_night * nights
        d3 = _d(r.rate_per_night) * nights

        has_rr = any(is_room_rent_charge(ec) for ec in (r.extra_charges or []))
        if has_rr:
            with_room_rent += 1

        tot_canonical += d1
        tot_single_night += d2
        tot_rate_nights += d3

        # D1 vs D3 is the comparison that matters: same scope (full stay),
        # different source. D2 is a per-night figure and is compared at
        # date level in Q04, not here.
        if abs(d1 - d3) > Decimal('0.01'):
            div.append(Divergence(
                f'reservation {r.id}', 'D1 canonical get_room_revenue',
                'D3 rate_per_night x nights', str(d1), str(d3), str(d1 - d3)))
        per_res[str(r.id)] = {'d1_canonical': str(d1),
                              'd2_single_night': str(d2),
                              'd3_rate_x_nights': str(d3),
                              'nights': nights, 'has_room_rent': has_rr}

    impls = {
        'D1 canonical (get_room_revenue)': str(tot_canonical),
        'D3 report style (rate x nights)': str(tot_rate_nights),
    }
    detail = {'per_reservation': per_res,
              'reservations_with_room_rent_rows': with_room_rent,
              'D2_single_night_total': str(tot_single_night)}
    note = ('D1 and D3 can only agree while zero room_rent ledger rows '
            f'exist. Reservations carrying room_rent rows: {with_room_rent}. '
            'This is the trap Wave 1 disarms.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q04 — Room revenue per business date
# ---------------------------------------------------------------------------

@quantity('Q04', 'Room revenue per business date',
          Policy.EXACT, Severity.BLOCK)
def q04(ctx: Context) -> tuple[dict, list, dict, str]:
    from app import kpi_helpers as K
    from app.models import ExtraCharge

    tot_kpi = Decimal('0')
    tot_nas = Decimal('0')
    tot_posted = Decimal('0')
    div: list[Divergence] = []
    per_date: dict[str, dict] = {}

    for d in ctx.activity_dates:
        kpi = _d(K.get_accrual_room_revenue(d))
        posted = _d(ctx.db.session.query(
            ctx.db.func.sum(ExtraCharge.amount)).filter(
                ExtraCharge.charge_date == d,
                ExtraCharge.charge_type == 'room_rent').scalar() or 0)
        nas = _d(ctx.nas(d).revenue_summary()['room_revenue'])

        tot_kpi += kpi
        tot_nas += nas
        tot_posted += posted

        if abs(kpi - nas) > Decimal('0.01'):
            div.append(Divergence(str(d), 'kpi_helpers.get_accrual_room_revenue',
                                  'NightAuditService.revenue_summary',
                                  str(kpi), str(nas), str(kpi - nas)))
        per_date[str(d)] = {'kpi_helpers': str(kpi),
                            'night_audit': str(nas),
                            'posted_room_rent': str(posted)}

    impls = {
        'kpi_helpers.get_accrual_room_revenue': str(tot_kpi),
        'NightAuditService.revenue_summary': str(tot_nas),
        'sum(posted room_rent charges)': str(tot_posted),
    }
    # The posted-ledger implementation is compared separately: while it is
    # zero it is not a competing answer, it is an absent one.
    if tot_posted == 0:
        impls.pop('sum(posted room_rent charges)')
    div += scalar_divergences(
        {k: v for k, v in impls.items()}, Policy.EXACT, 'all dates')
    detail = {'per_date': per_date, 'posted_room_rent_total': str(tot_posted)}
    note = ('Ledger-posted room rent is ZERO across all dates, so the two '
            'tariff-based implementations agree by default. Agreement here '
            'is not evidence that they would agree once posting is active.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q05 — Ancillary revenue by category
# ---------------------------------------------------------------------------

@quantity('Q05', 'Ancillary revenue by category',
          Policy.EXACT, Severity.BLOCK)
def q05(ctx: Context) -> tuple[dict, list, dict, str]:
    from app import kpi_helpers as K

    tot_kpi = Decimal('0')
    tot_nas = Decimal('0')
    div: list[Divergence] = []
    per_date: dict[str, dict] = {}
    cat_source: dict[str, int] = {'charge_category': 0, 'description_parsed': 0}

    for d in ctx.activity_dates:
        kpi = _d(K.get_accrual_extras(d))
        rev = ctx.nas(d).revenue_summary()
        nas = _d(rev['extra_charges_total'])
        tot_kpi += kpi
        tot_nas += nas
        if abs(kpi - nas) > Decimal('0.01'):
            div.append(Divergence(str(d), 'kpi_helpers.get_accrual_extras',
                                  'NightAuditService extras_total',
                                  str(kpi), str(nas), str(kpi - nas)))
        per_date[str(d)] = {'kpi_helpers': str(kpi), 'night_audit': str(nas),
                            'night_audit_by_category':
                                {k: str(_d(v)) for k, v in
                                 sorted(rev['extra_by_category'].items())}}

    EC = ctx.M['ExtraCharge']
    for c in EC.query.all():
        if c.charge_category:
            cat_source['charge_category'] += 1
        else:
            cat_source['description_parsed'] += 1

    impls = {'kpi_helpers.get_accrual_extras': str(tot_kpi),
             'NightAuditService.revenue_summary': str(tot_nas)}
    detail = {'per_date': per_date, 'category_source_counts': cat_source}
    note = ('Night audit derives its category from the description string; '
            'charge_category is populated on '
            f"{cat_source['charge_category']} of "
            f"{sum(cat_source.values())} rows. Totals may agree while "
            'categorisation diverges.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q06 — Taxable base
# ---------------------------------------------------------------------------

@quantity('Q06', 'Taxable base (deduplicated vs raw)',
          Policy.RUPEE, Severity.BLOCK)
def q06(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.gst_service import get_gst_report
    TL = ctx.M['TaxLine']

    all_lines = TL.query.all()
    raw = sum(_d(t.taxable_amount) for t in all_lines)
    dedup_map: dict[tuple, Decimal] = {}
    for t in all_lines:
        dedup_map[(t.reservation_id, t.charge_source_type,
                   t.charge_source_id)] = _d(t.taxable_amount)
    dedup = sum(dedup_map.values())

    per_date: dict[str, dict] = {}
    div: list[Divergence] = []
    for d in ctx.activity_dates:
        # NOTE: get_gst_report is read-only (aggregation only). The
        # write-bearing get_folio_gst_summary is deliberately NOT used.
        rep = _d(get_gst_report(d, d)['total_taxable'])
        audit = _d(ctx.nas(d).tax_snapshot()['total_taxable'])
        per_date[str(d)] = {'gst_report_deduped': str(rep),
                            'night_audit_raw': str(audit)}
        if abs(rep - audit) > Decimal('1.00'):
            div.append(Divergence(str(d), 'gst_service.get_gst_report',
                                  'NightAuditService.tax_snapshot',
                                  str(rep), str(audit), str(rep - audit)))

    impls = {'deduplicated by charge source': str(dedup),
             'raw sum of all tax lines': str(raw)}
    detail = {'per_date': per_date, 'tax_line_count': len(all_lines),
              'distinct_sources': len(dedup_map),
              'inflation_factor': str(
                  (raw / dedup).quantize(Decimal('0.01')) if dedup else 0)}
    note = ('CGST and SGST each carry the full taxable value of one supply. '
            'Summing both double-counts the base.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q07 — Tax by component
# ---------------------------------------------------------------------------

@quantity('Q07', 'Tax by component (CGST / SGST / IGST)',
          Policy.RUPEE, Severity.BLOCK)
def q07(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.gst_service import compute_stay_gst
    TL = ctx.M['TaxLine']

    by_type: dict[str, Decimal] = {}
    for t in TL.query.all():
        by_type[t.tax_type] = by_type.get(t.tax_type, Decimal('0')) + _d(t.tax_amount)
    stored = sum(by_type.values())

    # compute_stay_gst is documented as pure math with no DB writes.
    live = Decimal('0')
    for r in ctx.reservations:
        live += _d(compute_stay_gst(r))

    impls = {'stored TaxLine rows': str(stored),
             'live compute_stay_gst': str(live)}
    div = scalar_divergences(impls, Policy.RUPEE, 'all reservations')
    detail = {'by_component': {k: str(v) for k, v in sorted(by_type.items())}}
    note = ('Stored tax is the authority per Article VI §1. The live figure '
            'is what calculate_stay_amount uses for balance, so divergence '
            'here is an invoice-versus-balance gap.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q08 — Discount
# ---------------------------------------------------------------------------

@quantity('Q08', 'Discount applied per reservation',
          Policy.EXACT, Severity.BLOCK)
def q08(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import calculate_stay_amount

    field_total = Decimal('0')
    csa_total = Decimal('0')
    div: list[Divergence] = []
    suppressed: list[str] = []
    population = 0

    for r in ctx.reservations:
        f = _d(r.discount_amount)
        c = _d(calculate_stay_amount(r)['discount'])
        field_total += f
        csa_total += c
        if f > 0:
            population += 1
        if abs(f - c) > Decimal('0.01'):
            suppressed.append(str(r.id))
            div.append(Divergence(
                f'reservation {r.id}', 'reservations.discount_amount',
                'calculate_stay_amount.discount', str(f), str(c), str(f - c)))

    nas_total = Decimal('0')
    for d in ctx.activity_dates:
        nas_total += _d(ctx.nas(d).revenue_summary()['discount_total'])

    impls = {'reservations.discount_amount field': str(field_total),
             'calculate_stay_amount.discount': str(csa_total),
             'NightAuditService.discount_total': str(nas_total)}
    detail = {'reservations_with_discount': population,
              'suppressed_by_csa': suppressed}
    note = ('calculate_stay_amount suppresses the discount when nightly '
            'rows or room_rent rows exist; the night audit always applies '
            'it. Divergence appears only once those rows exist.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q09 — Payments total, correction-signed
# ---------------------------------------------------------------------------

@quantity('Q09', 'Payments total (signed vs raw)',
          Policy.EXACT, Severity.BLOCK)
def q09(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import signed_payment_amount, calculate_stay_amount
    P = ctx.M['Payment']

    payments = P.query.filter(P.is_voided == False).all()  # noqa: E712
    raw = sum(_d(p.amount) for p in payments)
    signed = sum(_d(signed_payment_amount(p)) for p in payments)
    via_csa = sum(_d(calculate_stay_amount(r)['paid']) for r in ctx.reservations)

    sql_sum = _d(ctx.db.session.query(
        ctx.db.func.sum(P.amount)).filter(P.is_voided == False).scalar() or 0)  # noqa: E712

    impls = {
        'raw ORM sum': str(raw),
        'signed (signed_payment_amount)': str(signed),
        'raw SQL func.sum': str(sql_sum),
        'via calculate_stay_amount': str(via_csa),
    }
    div = scalar_divergences(impls, Policy.EXACT, 'all payments')
    reversals = sum(1 for p in payments if getattr(p, 'is_reversal', False))
    detail = {'payment_count': len(payments), 'reversal_rows': reversals,
              'voided_count': P.query.filter(P.is_voided == True).count()}  # noqa: E712
    note = (f'{reversals} reversal rows exist. Signed and raw agree only '
            'while that count is zero — the agreement proves nothing about '
            'correction handling.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q10 — Payments by mode and purpose
# ---------------------------------------------------------------------------

@quantity('Q10', 'Payments by mode and purpose',
          Policy.EXACT, Severity.BLOCK)
def q10(ctx: Context) -> tuple[dict, list, dict, str]:
    from app import kpi_helpers as K
    P, PM = ctx.M['Payment'], ctx.M['PaymentMode']

    by_mode: dict[str, Decimal] = {}
    by_purpose: dict[str, Decimal] = {}
    by_category: dict[str, Decimal] = {}
    for p in P.query.filter(P.is_voided == False).all():  # noqa: E712
        pm = p.payment_mode
        name = pm.name if pm else 'UNKNOWN'
        cat = (getattr(pm, 'category', None) or 'direct_payment') if pm else 'UNKNOWN'
        pur = (getattr(p, 'payment_purpose', None) or 'settlement')
        by_mode[name] = by_mode.get(name, Decimal('0')) + _d(p.amount)
        by_purpose[pur] = by_purpose.get(pur, Decimal('0')) + _d(p.amount)
        by_category[cat] = by_category.get(cat, Decimal('0')) + _d(p.amount)

    direct_orm = by_category.get('direct_payment', Decimal('0'))
    direct_kpi = Decimal('0')
    for d in ctx.activity_dates:
        direct_kpi += _d(K.get_cash_revenue(d))

    impls = {'ORM by category (direct_payment)': str(direct_orm),
             'kpi_helpers.get_cash_revenue summed': str(direct_kpi)}
    div = scalar_divergences(impls, Policy.EXACT, 'direct payments')
    detail = {'by_mode': {k: str(v) for k, v in sorted(by_mode.items())},
              'by_purpose': {k: str(v) for k, v in sorted(by_purpose.items())},
              'by_category': {k: str(v) for k, v in sorted(by_category.items())}}
    note = 'Category split determines what counts as cash collected.'
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q11 — Refunds separated from voids
# ---------------------------------------------------------------------------

@quantity('Q11', 'Refunds, separated from voids',
          Policy.EXACT, Severity.BLOCK)
def q11(ctx: Context) -> tuple[dict, list, dict, str]:
    P = ctx.M['Payment']
    voided = P.query.filter(P.is_voided == True).all()  # noqa: E712
    void_total = sum(_d(p.amount) for p in voided)
    refund_rows = P.query.filter(
        P.payment_purpose == 'refund').all()
    refund_total = sum(_d(p.amount) for p in refund_rows)

    nas_refunds = Decimal('0')
    for d in ctx.activity_dates:
        nas_refunds += _d(ctx.nas(d).payment_summary()['total_refunds'])

    impls = {'voided payments (what night audit calls refunds)': str(void_total),
             'payment_purpose = refund (true refunds)': str(refund_total)}
    div = scalar_divergences(impls, Policy.EXACT, 'refunds vs voids')
    detail = {'void_count': len(voided), 'refund_row_count': len(refund_rows),
              'night_audit_total_refunds': str(nas_refunds)}
    population = len(voided) + len(refund_rows)
    note = ('A void asserts an entry should not have existed; a refund '
            'asserts money left the business. The night audit reports voids '
            'as refunds (Article VIII §5).')
    return impls, div, detail, note, population


# ---------------------------------------------------------------------------
# Q12 — Outstanding per reservation (the dual-balance quantity)
# ---------------------------------------------------------------------------

@quantity('Q12', 'Outstanding per reservation (2 bases)',
          Policy.EXACT, Severity.BLOCK)
def q12(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import calculate_stay_amount

    tot_balance = Decimal('0')
    tot_settlement = Decimal('0')
    div: list[Divergence] = []
    disagreeing: list[dict] = []

    for r in ctx.reservations:
        a = calculate_stay_amount(r)
        b = _d(a['balance'])
        s = _d(a['settlement_balance'])
        tot_balance += b
        tot_settlement += s
        if abs(b - s) > Decimal('0.005'):
            div.append(Divergence(
                f'reservation {r.id}', 'balance (unrounded basis)',
                'settlement_balance (invoiced basis)', str(b), str(s), str(b - s)))
            disagreeing.append({'reservation': r.id, 'balance': str(b),
                                'settlement_balance': str(s),
                                'grand_total': str(_d(a['grand_total'])),
                                'rounded_grand_total': str(_d(a['rounded_grand_total'])),
                                'paid': str(_d(a['paid']))})

    impls = {'balance (unrounded grand total)': str(tot_balance),
             'settlement_balance (invoiced total)': str(tot_settlement)}
    detail = {'reservations_disagreeing': len(disagreeing),
              'cases': disagreeing}
    note = ('Article IV §1 permits exactly one amount owed per reservation. '
            f'{len(disagreeing)} reservations currently carry two.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q13 — Settlement status distribution
# ---------------------------------------------------------------------------

@quantity('Q13', 'Settlement status distribution',
          Policy.EXACT, Severity.BLOCK)
def q13(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import calculate_stay_amount
    from app.financial import SETTLEMENT_TOLERANCE

    def bucket(v: Decimal) -> str:
        if abs(v) <= SETTLEMENT_TOLERANCE:
            return 'settled'
        return 'owing' if v > 0 else 'overpaid'

    by_balance: dict[str, int] = {}
    by_settlement: dict[str, int] = {}
    div: list[Divergence] = []
    for r in ctx.reservations:
        a = calculate_stay_amount(r)
        bb, sb = bucket(_d(a['balance'])), bucket(_d(a['settlement_balance']))
        by_balance[bb] = by_balance.get(bb, 0) + 1
        by_settlement[sb] = by_settlement.get(sb, 0) + 1
        if bb != sb:
            div.append(Divergence(f'reservation {r.id}',
                                  'status by balance', 'status by settlement_balance',
                                  bb, sb, 'classification differs'))

    impls = {'by balance basis': str(dict(sorted(by_balance.items()))),
             'by settlement basis': str(dict(sorted(by_settlement.items())))}
    detail = {'by_balance': dict(sorted(by_balance.items())),
              'by_settlement': dict(sorted(by_settlement.items()))}
    note = 'A reservation classified differently by the two bases can appear in two contradictory exception lists.'
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q14 — Folio partition
# ---------------------------------------------------------------------------

@quantity('Q14', 'Folio balances / partition integrity',
          Policy.EXACT, Severity.BLOCK)
def q14(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.services import calculate_folio_amount, calculate_stay_amount

    folio_charges = Decimal('0')
    folio_paid = Decimal('0')
    for f in ctx.folios:
        amt = calculate_folio_amount(f)
        folio_charges += _d(amt['extra_charges'])
        folio_paid += _d(amt['paid'])

    res_charges = sum(_d(calculate_stay_amount(r)['extra_charges'])
                      for r in ctx.reservations)
    res_paid = sum(_d(calculate_stay_amount(r)['paid'])
                   for r in ctx.reservations)

    EC, P = ctx.M['ExtraCharge'], ctx.M['Payment']
    unrouted_charges = EC.query.filter(EC.folio_id.is_(None)).count()
    unrouted_payments = P.query.filter(P.folio_id.is_(None)).count()

    impls = {'sum over folios (charges)': str(folio_charges),
             'sum over reservations (charges)': str(res_charges)}
    div = scalar_divergences(impls, Policy.EXACT, 'charge partition')
    detail = {'folio_count': len(ctx.folios),
              'folio_paid': str(folio_paid), 'reservation_paid': str(res_paid),
              'unrouted_charges': unrouted_charges,
              'unrouted_payments': unrouted_payments,
              'total_charges': EC.query.count(),
              'total_payments': P.query.count()}
    note = (f'{unrouted_charges} charges and {unrouted_payments} payments '
            'carry folio_id = NULL. Article V §3 requires every row to '
            'belong to a folio.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q15 — Night audit sections
# ---------------------------------------------------------------------------

@quantity('Q15', 'Night audit — stored vs recomputed sections',
          Policy.EXACT, Severity.BLOCK)
def q15(ctx: Context) -> tuple[dict, list, dict, str]:
    div: list[Divergence] = []
    per_date: dict[str, dict] = {}

    # The two implementations must be COMPARABLE NUMBERS, not descriptive
    # labels. Summing the compared fields gives a single scalar per side
    # whose equality is meaningful; per-field attribution lives in the
    # divergence list.
    stored_sum = Decimal('0')
    recomputed_sum = Decimal('0')

    for log in ctx.audit_logs:
        d = log.audit_date
        svc = ctx.nas(d)
        rev = svc.revenue_summary()
        pay = svc.payment_summary()
        ctl = svc.final_control()
        occ = svc.occupancy_position()

        pairs = [
            ('total_revenue (cash)', _d(log.total_revenue), _d(pay['total_collected'])),
            ('accrual_revenue', _d(log.accrual_revenue), _d(rev['accrual_net'])),
            ('occupancy_count', _d(log.occupancy_count), _d(occ['occupied'])),
            ('reconciliation_difference', _d(log.reconciliation_difference),
             _d(ctl['reconciliation_difference'])),
        ]
        row: dict[str, Any] = {}
        for name, stored, live in pairs:
            stored_sum += stored
            recomputed_sum += live
            row[name] = {'stored': str(stored), 'recomputed': str(live)}
            if abs(stored - live) > Decimal('0.01'):
                div.append(Divergence(f'{d} / {name}', 'stored NightAuditLog',
                                      'recomputed NightAuditService',
                                      str(stored), str(live), str(stored - live)))
        row['status'] = log.status
        row['snapshot_valid'] = bool(log.snapshot_valid)
        per_date[str(d)] = row

    impls = {'stored NightAuditLog (Σ compared fields)': str(stored_sum),
             'recomputed NightAuditService (Σ compared fields)': str(recomputed_sum)}
    detail = {'per_date': per_date, 'audit_log_count': len(ctx.audit_logs),
              'fields_compared_per_date': ['total_revenue', 'accrual_revenue',
                                           'occupancy_count',
                                           'reconciliation_difference']}
    note = ('Stored close figures compared against a fresh read-only '
            'recomputation. Note the recomputed reconciliation_difference '
            'is structurally incapable of being positive (Phase 2 INV-09), '
            'so agreement on that field is not evidence the control works.')
    return impls, div, detail, note, len(ctx.audit_logs)


# ---------------------------------------------------------------------------
# Q16-Q18 — report / dashboard surfaces
# ---------------------------------------------------------------------------
# Implemented once D2 (Golden Master Framework) provided an authenticated
# client and a way to read a route's template context. Every URL below
# carries an EXPLICIT date argument: these quantities run inside the D1
# harness, which does not freeze the clock, and a report left to default
# its own date range would be measuring whichever day the run happened
# on rather than the business date.

def _surface_pairs(pairs: list, policy: str) -> tuple[dict, list]:
    """Compare named (concept, surface value, engine value) triples.

    Each concept is compared only against its own counterpart. Feeding
    every value into one flat comparison would cross-compare unrelated
    concepts — occupancy against revenue — and manufacture divergences
    that mean nothing.
    """
    impls: dict[str, Any] = {}
    div: list[Divergence] = []
    for concept, a_name, a_value, b_name, b_value in pairs:
        impls[f'{concept}::{a_name}'] = a_value
        impls[f'{concept}::{b_name}'] = b_value
        div.extend(scalar_divergences({a_name: a_value, b_name: b_value},
                                      policy, concept))
    return impls, div


@quantity('Q16', 'Daily report totals vs canonical engines',
          Policy.RUPEE, Severity.BLOCK,
          self_compared=True)
def q16(ctx: Context) -> tuple[dict, list, dict, str]:
    """Does the Flash Report show what the canonical engines say?"""
    from verification.golden.surfaces import require_context, pick
    from app.kpi_helpers import (get_daily_revenue, get_accrual_revenue,
                                 get_monthly_revenue, get_occupancy, get_adr,
                                 get_revpar)

    bd = ctx.business_date
    month_start = bd.replace(day=1)
    flash = require_context(ctx.app, f'/reports/flash?date={bd.isoformat()}')

    occ = get_occupancy()
    engine_adr = get_adr()
    accrual = get_accrual_revenue(bd)

    pairs = [
        ('daily collections',
         'reports.flash.day_revenue', pick(flash, 'day_revenue'),
         'kpi_helpers.get_daily_revenue', get_daily_revenue(bd)),
        ('accrual revenue',
         'reports.flash.accrual_net', pick(flash, 'accrual.accrual_net'),
         'kpi_helpers.get_accrual_revenue', (accrual or {}).get('accrual_net')),
        ('month-to-date collections',
         'reports.flash.mtd_revenue', pick(flash, 'mtd_revenue'),
         'kpi_helpers.get_monthly_revenue', get_monthly_revenue(month_start, bd)),
        ('occupancy pct',
         'reports.flash.occ_pct', pick(flash, 'occ_pct'),
         'kpi_helpers.get_occupancy', occ.get('pct')),
        ('sellable rooms',
         'reports.flash.total_rooms', pick(flash, 'total_rooms'),
         'kpi_helpers.get_occupancy.total', occ.get('total')),
        ('ADR',
         'reports.flash.arr', pick(flash, 'arr'),
         'kpi_helpers.get_adr', engine_adr),
        ('RevPAR',
         'reports.flash.revpar', pick(flash, 'revpar'),
         'kpi_helpers.get_revpar',
         get_revpar(adr=engine_adr, occ_pct=occ.get('pct'))),
    ]
    impls, div = _surface_pairs(pairs, Policy.RUPEE)
    detail = {'surface': f'/reports/flash?date={bd.isoformat()}',
              'business_date': bd.isoformat(),
              'concepts_compared': len(pairs)}
    note = ('The Flash Report is compared against the canonical helpers it '
            'is supposed to be a view over. A divergence here means the '
            'report is not a view — it is a second implementation.')
    return impls, div, detail, note


@quantity('Q17', 'MIS aggregates vs canonical engines and the flash report',
          Policy.RUPEE, Severity.WARN,
          self_compared=True)
def q17(ctx: Context) -> tuple[dict, list, dict, str]:
    """Does the Front Office MIS agree with the other daily surfaces?"""
    from verification.golden.surfaces import require_context, pick
    from app.kpi_helpers import get_daily_revenue, get_occupancy, get_adr

    bd = ctx.business_date
    iso = bd.isoformat()
    mis = require_context(
        ctx.app, f'/reports/front-office-mis?from_date={iso}&to_date={iso}')
    flash = require_context(ctx.app, f'/reports/flash?date={iso}')

    occ = get_occupancy()
    pairs = [
        ('daily collections',
         'reports.mis.billing.total_collected',
         pick(mis, 'billing.total_collected'),
         'kpi_helpers.get_daily_revenue', get_daily_revenue(bd)),
        ('daily collections (report-to-report)',
         'reports.mis.billing.total_collected',
         pick(mis, 'billing.total_collected'),
         'reports.flash.day_revenue', pick(flash, 'day_revenue')),
        ('occupancy pct',
         'reports.mis.business.occupancy_pct',
         pick(mis, 'business.occupancy_pct'),
         'kpi_helpers.get_occupancy', occ.get('pct')),
        ('ADR',
         'reports.mis.business.arr', pick(mis, 'business.arr'),
         'kpi_helpers.get_adr', get_adr()),
        ('occupied rooms',
         'reports.mis.business.occupied_rooms',
         pick(mis, 'business.occupied_rooms'),
         'kpi_helpers.get_occupancy.occupied', occ.get('occupied')),
        ('departures completed',
         'reports.mis.movement.departures_done',
         pick(mis, 'movement.departures_done'),
         'reports.flash.departures_done', pick(flash, 'departures_done')),
    ]
    impls, div = _surface_pairs(pairs, Policy.RUPEE)
    detail = {'surface': f'/reports/front-office-mis?from_date={iso}&to_date={iso}',
              'range_days': pick(mis, 'meta.days'),
              'concepts_compared': len(pairs)}
    note = ('MIS is scoped to the single business date so it is directly '
            'comparable with the flash report and the daily engines. Where '
            'the two reports disagree about the same day, at least one of '
            'them is wrong on every day.')
    return impls, div, detail, note


@quantity('Q18', 'Executive dashboard tiles vs canonical engines',
          Policy.RUPEE, Severity.BLOCK,
          self_compared=True)
def q18(ctx: Context) -> tuple[dict, list, dict, str]:
    """Does the dashboard show what the reports and engines say?"""
    from verification.golden.surfaces import require_context, pick
    from app.kpi_helpers import get_daily_revenue, get_occupancy

    bd = ctx.business_date
    dash = require_context(ctx.app, '/dashboard')
    flash = require_context(ctx.app, f'/reports/flash?date={bd.isoformat()}')

    occ = get_occupancy()
    pairs = [
        ('daily collections',
         'dashboard.cash_collected_today', pick(dash, 'cash_collected_today'),
         'kpi_helpers.get_daily_revenue', get_daily_revenue(bd)),
        ('daily collections (tile-to-report)',
         'dashboard.cash_collected_today', pick(dash, 'cash_collected_today'),
         'reports.flash.day_revenue', pick(flash, 'day_revenue')),
        ('daily collections (tile-to-summary)',
         'dashboard.cash_collected_today', pick(dash, 'cash_collected_today'),
         'dashboard.daily_financial_summary.total_collected',
         pick(dash, 'daily_financial_summary.total_collected')),
        ('rooms available',
         'dashboard.available_rooms', pick(dash, 'available_rooms'),
         'kpi_helpers.get_occupancy.sellable', occ.get('sellable')),
        ('departures completed',
         'dashboard.checked_out_today', pick(dash, 'checked_out_today'),
         'reports.flash.departures_done', pick(flash, 'departures_done')),
        ('arrivals completed',
         'dashboard.checked_in_today', pick(dash, 'checked_in_today'),
         'reports.flash.arrivals_done', pick(flash, 'arrivals_done')),
    ]
    impls, div = _surface_pairs(pairs, Policy.RUPEE)
    detail = {'surface': '/dashboard', 'business_date': bd.isoformat(),
              'concepts_compared': len(pairs)}
    note = ('The dashboard is the surface management reads first. Each tile '
            'is compared against the engine that should own it and against '
            'the report that shows the same concept.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q19 — Occupancy and rooms sold
# ---------------------------------------------------------------------------

@quantity('Q19', 'Occupancy and rooms sold',
          Policy.EXACT, Severity.BLOCK)
def q19(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.occupancy_engine import (occupancy_snapshot, occupied_rooms,
                                      occupied_room_nights, sellable_rooms)
    from app import kpi_helpers as K
    Room = ctx.M['Room']

    snap = occupancy_snapshot()
    engine_occ = occupied_rooms()
    kpi_occ = K.get_occupied_count()
    room_status_occ = Room.query.filter_by(status='Occupied').count()

    impls = {'occupancy_engine.occupied_rooms': engine_occ,
             'kpi_helpers.get_occupied_count': kpi_occ}
    div = scalar_divergences(impls, Policy.EXACT, 'current occupancy')

    room_nights = 0
    if ctx.activity_dates:
        room_nights = occupied_room_nights(ctx.activity_dates[0],
                                           ctx.activity_dates[-1])
    detail = {'snapshot': {k: (str(v) if isinstance(v, Decimal) else v)
                           for k, v in snap.items()},
              'room_status_occupied_count': room_status_occ,
              'sellable_rooms': sellable_rooms(),
              'occupied_room_nights_over_activity_window': room_nights}
    note = ('occupancy_engine is already canonical (Phase 2 §3). Room.status '
            f'reports {room_status_occ} occupied and is recorded for drift '
            'detection only, never as an implementation.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q20 — ADR and RevPAR
# ---------------------------------------------------------------------------

@quantity('Q20', 'ADR and RevPAR (multiple definitions)',
          Policy.EXACT, Severity.BLOCK)
def q20(ctx: Context) -> tuple[dict, list, dict, str]:
    from app import kpi_helpers as K
    from app.occupancy_engine import occupied_room_nights

    adr_avg_rate = _d(K.get_adr())

    # Revenue-per-room-night, the definition Phase 2 §3 nominates as canonical.
    adr_rev_per_night = Decimal('0')
    if ctx.activity_dates:
        total_room_rev = Decimal('0')
        for d in ctx.activity_dates:
            total_room_rev += _d(K.get_accrual_room_revenue(d))
        rn = occupied_room_nights(ctx.activity_dates[0], ctx.activity_dates[-1])
        if rn:
            adr_rev_per_night = (total_room_rev / rn).quantize(Decimal('0.01'))

    # Night-audit style: room revenue divided by occupied rooms, per date.
    adr_nas_by_date: dict[str, str] = {}
    for d in ctx.activity_dates:
        try:
            svc = ctx.nas(d)
            occ = svc.occupancy_position()['occupied']
            rr = _d(svc.revenue_summary()['room_revenue'])
            adr_nas_by_date[str(d)] = str(
                (rr / occ).quantize(Decimal('0.01')) if occ else Decimal('0'))
        except Exception as exc:      # pragma: no cover - defensive
            adr_nas_by_date[str(d)] = f'ERROR: {exc}'

    impls = {'kpi_helpers.get_adr (AVG rate_per_night, no date scope)': str(adr_avg_rate),
             'room revenue / occupied room-nights (date-scoped)': str(adr_rev_per_night)}
    div = scalar_divergences(impls, Policy.EXACT, 'ADR')
    detail = {'revpar_from_kpi_helpers': str(_d(K.get_revpar())),
              'night_audit_adr_by_date': adr_nas_by_date}
    note = ('kpi_helpers.get_adr takes NO date parameter — it averages the '
            'tariffs of currently checked-in reservations, so any historical '
            'ADR is actually today\'s ADR.')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Q21 — Cash position and variance
# ---------------------------------------------------------------------------

@quantity('Q21', 'Cash position and variance',
          Policy.EXACT, Severity.BLOCK)
def q21(ctx: Context) -> tuple[dict, list, dict, str, int]:
    from app.shift_service import calculate_expected_cash

    rows: list[dict] = []
    tot_expected = Decimal('0')
    tot_declared = Decimal('0')
    tot_variance = Decimal('0')
    div: list[Divergence] = []

    for s in ctx.shifts:
        recomputed = _d(calculate_expected_cash(s))
        stored = _d(s.expected_cash)
        declared = _d(s.declared_closing_cash)
        tot_expected += stored
        tot_declared += declared
        tot_variance += _d(s.variance)
        if abs(recomputed - stored) > Decimal('0.01'):
            div.append(Divergence(f'shift {s.id}', 'stored expected_cash',
                                  'recomputed calculate_expected_cash',
                                  str(stored), str(recomputed),
                                  str(stored - recomputed)))
        rows.append({'shift': s.id, 'user_id': s.user_id, 'status': s.status,
                     'stored_expected': str(stored),
                     'recomputed_expected': str(recomputed),
                     'declared': str(declared), 'variance': str(_d(s.variance))})

    impls = {'stored Shift.expected_cash': str(tot_expected),
             'recomputed calculate_expected_cash': str(tot_expected)}
    detail = {'shifts': rows, 'shift_count': len(ctx.shifts),
              'total_declared': str(tot_declared),
              'total_variance': str(tot_variance)}
    note = ('Cash control cannot be verified without shift data. '
            f'{len(ctx.shifts)} shifts exist.')
    return impls, div, detail, note, len(ctx.shifts)


# ---------------------------------------------------------------------------
# Q22 — Receivables
# ---------------------------------------------------------------------------

@quantity('Q22', 'Receivables — OTA, corporate, individual',
          Policy.EXACT, Severity.BLOCK)
def q22(ctx: Context) -> tuple[dict, list, dict, str]:
    from app.ota_settlement_service import compute_ota_outstanding
    from app.ota_reconciliation import get_ota_pending
    Company, Reservation = ctx.M['Company'], ctx.M['Reservation']

    gross = _d(compute_ota_outstanding()['total_amount'])
    try:
        pending = _d(get_ota_pending()['total_pending'])
    except Exception as exc:                     # pragma: no cover
        pending = Decimal('0')
        pending_err = str(exc)
    else:
        pending_err = ''

    company_credit = _d(ctx.db.session.query(
        ctx.db.func.sum(Company.credit_used)).scalar() or 0)

    ind_credit = Decimal('0')
    for r in Reservation.query.filter(Reservation.credit_amount > 0).all():
        ind_credit += max(Decimal('0'),
                          _d(r.credit_amount) - _d(r.credit_settled_amount))

    # Misclassification probe: OTA receivable heads on non-OTA bookings.
    P, PM = ctx.M['Payment'], ctx.M['PaymentMode']
    misclassified = (ctx.db.session.query(P, Reservation)
                     .join(PM, P.payment_mode_id == PM.id)
                     .join(Reservation, P.reservation_id == Reservation.id)
                     .filter(PM.category == 'ota_receivable',
                             Reservation.source != 'OTA').all())
    mis_total = sum(_d(p.amount) for p, _r in misclassified)

    impls = {'compute_ota_outstanding (gross)': str(gross),
             'get_ota_pending (net of payouts)': str(pending)}
    div = scalar_divergences(impls, Policy.EXACT, 'OTA receivable')
    detail = {
        'company_credit_used_total': str(company_credit),
        'individual_credit_outstanding': str(ind_credit),
        'ota_payout_rows': ctx.M['OTAPayout'].query.count(),
        'misclassified_ota_head_count': len(misclassified),
        'misclassified_ota_head_total': str(mis_total),
        'misclassified_rows': [
            {'payment': p.id, 'reservation': r.id, 'source': r.source,
             'ota_payment_status': r.ota_payment_status,
             'head': p.payment_mode.name if p.payment_mode else None,
             'amount': str(_d(p.amount))}
            for p, r in misclassified],
        'get_ota_pending_error': pending_err,
    }
    note = ('Gross and net agree only while zero payouts exist. '
            f'{len(misclassified)} payments totalling {mis_total} sit on OTA '
            'receivable heads against non-OTA bookings (Article IV §6).')
    return impls, div, detail, note


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def measure_all(ctx: Context) -> list[QuantityResult]:
    """Run every registered quantity. One failure never stops the run."""
    results: list[QuantityResult] = []
    for qid, label, policy, severity, self_compared, fn in REGISTRY:
        t0 = time.perf_counter()
        res = QuantityResult(quantity_id=qid, label=label, policy=policy,
                             severity=severity, verdict=Verdict.ERROR)
        try:
            out = fn(ctx)
            if len(out) == 5:
                impls, div, detail, note, population = out
            else:
                impls, div, detail, note = out
                population = None
            res.implementations = impls
            res.divergences = div
            res.detail = detail
            res.note = note
            res.verdict = compare(impls, policy, div, population=population,
                                  pairwise=not self_compared)
        except NotImplementedError as exc:
            res.verdict = Verdict.NOT_IMPLEMENTED
            res.note = str(exc)
        except Exception:
            res.verdict = Verdict.ERROR
            res.error = traceback.format_exc(limit=6)
        res.duration_ms = int((time.perf_counter() - t0) * 1000)
        results.append(res)
    return results
