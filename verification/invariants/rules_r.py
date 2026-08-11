"""
Class R — Reconciliation invariants.

One question: does a day's money add up when you compare like with like?

This module exists because W1-R9 found that it did not, and that nothing in
the verification framework noticed. `final_control` compared pre-tax revenue
against tax-inclusive cash, so every taxable day reported a gap exactly equal
to its own tax, and the night audit refused to close over a defect in its own
arithmetic. D1 compared the stored reconciliation against a recomputed one and
reported AGREED, because both sides computed the same wrong number.

The rule was corrected in code and then written down twice — in a blueprint
and in a docstring. Neither can fail. Under P11 a control that cannot fail is
not a control, so the rule is registered here as something that executes.
"""
from __future__ import annotations

from verification.invariants.helpers import row_violation, summarise, verdict
from verification.invariants.model import (
    Blocking, Category, Commissioning, Mode, Severity,
)
from verification.invariants.registry import invariant

WHOLE_DB = (Mode.ENTIRE_DATABASE, Mode.RELEASE_VERIFICATION,
            Mode.REGRESSION_DATASET, Mode.CONTINUOUS_MONITORING)
DATED = (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT, Mode.HISTORICAL_REPLAY)


# ---------------------------------------------------------------------------
# INV-R01 — gross reconciliation basis
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-R01',
    title='A day reconciles gross accrual against gross payments',
    category=Category.ACCOUNTING,
    business_purpose=(
        'Revenue is reported net of tax and cash is received gross of it. '
        'Comparing the two directly makes every taxable day appear short by '
        'its own tax, which blocks the night audit over an arithmetic fault '
        'rather than a financial one, and teaches operators to override a '
        'control that is wrong by construction. The purpose of this '
        'invariant is that the comparison stays like-for-like.'),
    business_rule=(
        'For every audited business day, the reconciliation difference '
        'reported by the application — gross accrual less cash less today\'s '
        'outstanding — is within the configured tolerance '
        '(app.night_audit_service.RECONCILIATION_TOLERANCE).'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('night_audit_logs', 'payments', 'extra_charges',
                  'reservations', 'tax_lines'),
    canonical_engine='app.night_audit_service.evaluate_reconciliation',
    validation_method=(
        'Recompute each audited date with the read-only NightAuditService and '
        'submit the result to the application\'s own reconciliation judge '
        'rather than re-implementing the comparison here. A second '
        'implementation would drift, and if the application\'s rule is wrong '
        'this is the run that should say so. The judge also classifies the '
        'failure: a residual equal to the day\'s tax is reported as '
        'LIKELY_GROSS_NET_REGRESSION rather than as a generic gap, because '
        'that residual is the signature of the W1-R9 defect and sends the '
        'investigation to the accounting basis instead of to the payments.'),
    evidence_produced=(
        'Per audited date: gross accrual, cash collected, today\'s '
        'outstanding, the reconciliation difference, the day\'s tax, the '
        'tolerance in force, and the diagnostic code.'),
    failure_message=(
        'A day does not reconcile when gross accrual is compared against '
        'gross payments. If the difference equals the day\'s tax, the '
        'accounting basis has regressed; otherwise money is genuinely '
        'unaccounted for.'),
    likely_root_causes=(
        'final_control compares accrual_net against cash instead of '
        'accrual_gross (the W1-R9 regression)',
        'A payment posted against the wrong business date',
        'A charge posted after the day was closed',
        'Tax lines regenerated at a different rate than the ones billed'),
    suggested_investigation=(
        'Read the diagnostic code before reading the amount',
        'Compare the difference against revenue_summary.tax_amount',
        'Check whether both operands in final_control are on the gross basis',
        'Read the _meta.recon_algorithm_version of the date\'s snapshot'),
    applicable_releases='v2.2.18 and later (W1-R9 onwards)',
    applicable_business_dates='every date carrying a night audit log',
    commissioning_status=Commissioning.NOT_COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P1', 'P2', 'P11'),
    affected_reports=('night audit', 'reports.night_audit', 'dashboard'),
    negative_seed=(
        # Removing cash without removing the charge drives collected below
        # gross accrual. See the KNOWN REACH note in _r01: under the current
        # max(0, ...) semantics this direction is invisible, which is why the
        # invariant ships NOT_COMMISSIONED.
        "UPDATE payments SET amount = amount / 2 "
        "WHERE is_voided = 0 AND id IN (SELECT id FROM payments LIMIT 1)",
    ),
    negative_seed_reason=(
        'Halving a settled payment breaks the equality the invariant asserts. '
        'It is declared so the commissioning run can demonstrate whether the '
        'control actually fires — and on the current reconciliation '
        'expression it does not, which is the finding rather than an '
        'oversight.'),
)
def _r01(ctx):
    """Assert the gross reconciliation basis for every audited date.

    KNOWN REACH, stated so nobody reads a green run as more than it is.
    ``today_outstanding`` is ``max(0, accrual_gross - payments)``, so the
    reconciliation expression collapses to identically zero whenever accrual
    is at least cash. This invariant therefore detects:

        over-collection and the gross/net regression   — yes
        a missing payment or an unposted charge        — NO

    The blind direction is a property of the expression under test, not of
    this rule, and it is why the invariant is registered NOT_COMMISSIONED:
    its declared negative seed does not make it fire. Commissioning is
    deliberately deferred until the max(0, ...) redesign lands, so the
    framework never records this as a proven control while it is half a
    control. A green INV-R01 today means "no gross/net regression and no
    over-collection", nothing wider.
    """
    from datetime import date as _date

    from app.models import NightAuditLog
    from app.night_audit_service import (
        NightAuditService, RECONCILIATION_TOLERANCE, evaluate_reconciliation,
        RECON_GROSS_NET,
    )

    ctx.require_app('INV-R01')

    logs = NightAuditLog.query.order_by(NightAuditLog.audit_date).all()
    if ctx.date:
        logs = [l for l in logs if l.audit_date.isoformat() == ctx.date]

    violations = []
    examined = 0
    gross_net_hits = 0

    for log in logs:
        svc = NightAuditService(log.audit_date)
        ctrl = svc.final_control()
        rev = svc.revenue_summary()
        v = evaluate_reconciliation(ctrl, rev)
        examined += 1
        if v['within_tolerance']:
            continue
        if v['code'] == RECON_GROSS_NET:
            gross_net_hits += 1
        violations.append(row_violation(
            'night_audit', log.audit_date.isoformat(),
            expected=(f'|gross accrual - cash - outstanding| <= '
                      f'{RECONCILIATION_TOLERANCE:.2f}'),
            observed=f'{v["code"]}: {v["abs_difference"]:.2f}',
            amount=v['abs_difference'],
            diagnostic=v['code'],
            tax_amount=v['tax_amount'],
            tolerance=v['tolerance'],
            accrual_gross=rev.get('accrual_gross'),
            cash_collected=ctrl.get('total_collected'),
            today_outstanding=ctrl.get('total_outstanding')))

    return (verdict(examined, violations), examined, violations,
            {'expected': (f'every audited date reconciles within '
                          f'Rs {RECONCILIATION_TOLERANCE:.2f} on the gross basis'),
             'observed': summarise('audited dates', examined, violations),
             'inputs': {'audit_logs': len(logs),
                        'tolerance': RECONCILIATION_TOLERANCE,
                        'gross_net_regressions': gross_net_hits}})
