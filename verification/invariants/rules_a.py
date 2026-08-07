"""
Class A — Accounting invariants.

The books must add up. Every invariant here answers a question an auditor
would ask about a set of figures: does the balance equal the charges less
the payments, does the sum of the parts equal the whole, does the tax
line agree with the base it was raised on.

Where an invariant compares the **canonical engine** against the
**primary record**, the primary record is read directly with SQL. Asking
the application whether it agrees with itself would let a defect in the
application conceal itself, and every rule in this file exists because
that concealment is exactly what happened somewhere.
"""
from __future__ import annotations

from decimal import Decimal

from verification.invariants.helpers import (
    EPSILON, dec, differs, money, row_violation, scope_clause, summarise,
    verdict,
)
from verification.invariants.model import (
    Blocking, Category, Commissioning, Mode, Severity, Status,
)
from verification.invariants.registry import invariant

WHOLE_DB = (Mode.ENTIRE_DATABASE, Mode.RELEASE_VERIFICATION,
            Mode.REGRESSION_DATASET, Mode.CONTINUOUS_MONITORING)
DATED = (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT, Mode.HISTORICAL_REPLAY)


# ---------------------------------------------------------------------------
# INV-A01 — the settlement identity
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-A01',
    title='Settlement identity: grand total - payments - company credit = balance',
    category=Category.ACCOUNTING,
    business_purpose=(
        'The balance shown on a folio is what the hotel tells a guest they '
        'owe. If it is not the arithmetic consequence of the charges and '
        'the payments, then either the guest is being asked for the wrong '
        'money or the hotel is writing off revenue it never decided to '
        'write off.'),
    business_rule=(
        'For every reservation, calculate_stay_amount must satisfy '
        'balance = grand_total - paid - company_credit, and '
        'settlement_balance = rounded_grand_total - paid - company_credit.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('reservations', 'extra_charges', 'payments',
                  'reservation_night_rates', 'tax_lines'),
    canonical_engine='app.services.calculate_stay_amount',
    validation_method=(
        'Call the canonical engine for every reservation in scope and check '
        'its own outputs against each other. This is an internal-consistency '
        'check of the engine, deliberately separate from INV-A04 which '
        'checks the engine against the primary record.'),
    evidence_produced=(
        'Per reservation: grand_total, paid, company_credit, reported '
        'balance, computed balance, variance.'),
    failure_message=(
        'The settlement identity does not hold. A folio balance is not the '
        'arithmetic consequence of its own charges and payments.'),
    likely_root_causes=(
        'A rounding step applied to one side of the identity but not the '
        'other',
        'company_credit subtracted twice, or not at all, on one path',
        'GST added to grand_total after balance was computed',
        'A caller mutating the returned dict'),
    suggested_investigation=(
        'Re-run calculate_stay_amount for the reported reservation and print '
        'every key it returns',
        'Compare grand_total against total + gst_amount',
        'Check whether round2 is applied before or after the subtraction'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + (Mode.SINGLE_RESERVATION,),
    principles=('P1', 'P11'),
    affected_reports=('main.reservation_folio', 'main.invoice',
                      'reports.ar_aging', 'night audit folio control'),
    negative_patch=('app.services.calculate_stay_amount', 'balance', 1000.0),
    negative_patch_reason=(
        'The identity is computed inside one function from values it derives '
        'itself, so no mutation of the DATA can break it: every input moves '
        'both sides together. The only thing that can break it is the code, '
        'and Wave 0 forbids changing that. So the fault is injected at the '
        'engine boundary instead — the returned balance is moved by 1,000 '
        'inside the commissioning subprocess only — which is precisely the '
        'shape of the regression this invariant exists to catch.'),
)
def _a01(ctx):
    from app.models import Reservation
    from app.services import calculate_stay_amount

    ctx.require_app('INV-A01')
    query = Reservation.query
    if ctx.reservation_id:
        query = query.filter(Reservation.id == ctx.reservation_id)
    reservations = query.order_by(Reservation.id).all()

    violations = []
    for r in reservations:
        amounts = calculate_stay_amount(r)
        grand = dec(amounts['grand_total'])
        paid = dec(amounts['paid'])
        credit = dec(amounts.get('company_credit', 0))
        reported = dec(amounts['balance'])
        computed = grand - paid - credit
        if differs(reported, computed):
            violations.append(row_violation(
                'reservation', r.id,
                expected=f'balance = {money(computed)}',
                observed=f'balance = {money(reported)}',
                amount=abs(reported - computed),
                variance=money(reported - computed),
                grand_total=money(grand), paid=money(paid),
                company_credit=money(credit)))
            continue

        rounded = dec(amounts['rounded_grand_total'])
        settlement = dec(amounts['settlement_balance'])
        expected_settlement = rounded - paid - credit
        if differs(settlement, expected_settlement):
            violations.append(row_violation(
                'reservation', r.id,
                expected=f'settlement_balance = {money(expected_settlement)}',
                observed=f'settlement_balance = {money(settlement)}',
                amount=abs(settlement - expected_settlement),
                variance=money(settlement - expected_settlement)))

    population = len(reservations)
    return (verdict(population, violations), population, violations,
            {'expected': 'balance = grand_total - paid - company_credit',
             'observed': summarise('settlement identity', population,
                                   violations),
             'inputs': {'reservations': population}})


# ---------------------------------------------------------------------------
# INV-A02 — folio partition
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-A02',
    title='Every financial row belongs to a folio',
    category=Category.ACCOUNTING,
    business_purpose=(
        'A folio is the unit a bill is issued against and the unit a '
        'company or an OTA is invoiced on. A payment or a charge that '
        'belongs to no folio still moves the hotel\'s money, but it cannot '
        'be attributed to anything, cannot appear on a split bill, and '
        'cannot be reconciled by anyone downstream.'),
    business_rule=(
        'Every payments row and every extra_charges row carries a non-null '
        'folio_id (Financial Constitution, Article V §3).'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('payments', 'extra_charges', 'folios'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Count rows with folio_id IS NULL, and total the money they carry '
        'so the finding has a size and not merely a count.'),
    evidence_produced=(
        'Count and rupee total of unrouted payments and charges, with the '
        'first of each listed by id.'),
    failure_message=(
        'Financial rows exist that belong to no folio. The money is real '
        'and its attribution is not.'),
    likely_root_causes=(
        'Posting paths that write a payment before a folio exists',
        'A folio-creation step that runs only on the check-in route',
        'Legacy rows predating the folio model, never backfilled'),
    suggested_investigation=(
        'Group the unrouted rows by created_at to see whether they are '
        'legacy or still being produced today',
        'Trace the posting path for the most recent unrouted row',
        'Check whether folio creation is conditional on booking_type'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P1', 'P5'),
    affected_reports=('main.reservation_folio', 'billing.gst_report',
                      'reports.daily_reconciliation', 'night audit folio control'),
    negative_seed=(
        "INSERT INTO payments "
        "(reservation_id, folio_id, payment_mode_id, amount, payment_date, "
        " created_at, is_voided, is_correction, is_reversal, payment_purpose) "
        "SELECT p.reservation_id, NULL, p.payment_mode_id, 191.00, "
        "  p.payment_date, p.created_at, 0, 0, 0, 'settlement' "
        "FROM payments p ORDER BY p.id LIMIT 1",
    ),
    negative_seed_reason=(
        'Posting a payment with no folio is exactly the state the rule '
        'forbids. The seed ADDS an unrouted row rather than detaching an '
        'existing one, because on this dataset every payment is already '
        'unrouted — the first version of this seed set folio_id = NULL '
        'where it was NOT NULL, matched nothing, and was correctly '
        'reported as a broken seed. Detection is therefore by the '
        'violation count rising, not by the status changing.'),
)
def _a02(ctx):
    date_clause, params = scope_clause(ctx, 'payment_date')
    payments = ctx.sql(
        f'SELECT id, amount, payment_date FROM payments '
        f'WHERE folio_id IS NULL{date_clause} ORDER BY id', params)
    charge_clause, charge_params = scope_clause(ctx, 'charge_date')
    charges = ctx.sql(
        f'SELECT id, amount, charge_date FROM extra_charges '
        f'WHERE folio_id IS NULL{charge_clause} ORDER BY id', charge_params)

    total_payments = ctx.count(
        f'SELECT COUNT(*) FROM payments WHERE 1=1{date_clause}', params)
    total_charges = ctx.count(
        f'SELECT COUNT(*) FROM extra_charges WHERE 1=1{charge_clause}',
        charge_params)

    violations = []
    for row in payments:
        violations.append(row_violation(
            'payment', row['id'], expected='folio_id set',
            observed='folio_id NULL', amount=dec(row['amount']),
            date=str(row['payment_date'])))
    for row in charges:
        violations.append(row_violation(
            'extra_charge', row['id'], expected='folio_id set',
            observed='folio_id NULL', amount=dec(row['amount']),
            date=str(row['charge_date'])))

    population = total_payments + total_charges
    unrouted_money = (sum((dec(r['amount']) for r in payments), Decimal('0'))
                      + sum((dec(r['amount']) for r in charges), Decimal('0')))
    return (verdict(population, violations), population, violations,
            {'expected': 'every payment and charge carries a folio_id',
             'observed': (f'{len(payments)}/{total_payments} payments and '
                          f'{len(charges)}/{total_charges} charges are '
                          f'unrouted, carrying {money(unrouted_money)}'),
             'variance': money(unrouted_money),
             'inputs': {'payments_in_scope': total_payments,
                        'charges_in_scope': total_charges}})


# ---------------------------------------------------------------------------
# INV-A03 — partition completeness
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-A03',
    title='Charges summed over folios equal charges summed over reservations',
    category=Category.ACCOUNTING,
    business_purpose=(
        'The same money must total the same whichever way it is sliced. If '
        'the folio view and the reservation view of the same charges differ, '
        'then at least one report in the system is showing a number that '
        'does not exist.'),
    business_rule=(
        'Σ extra_charges grouped by folio = Σ extra_charges grouped by '
        'reservation, over the same population.'),
    severity=Severity.HIGH,
    blocking=Blocking.RELEASE,
    data_sources=('extra_charges', 'folios', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Total the charge rows twice, once joined through folios and once '
        'through reservations, and compare. A row reachable by neither '
        'route is reported separately, because it would otherwise cancel '
        'out of both totals and leave them agreeing.'),
    evidence_produced='Both totals, their variance, and any orphan rows.',
    failure_message=(
        'The folio and reservation views of the same charges disagree.'),
    likely_root_causes=(
        'A charge whose folio belongs to a different reservation',
        'Charges with folio_id NULL falling out of the folio view',
        'A folio whose reservation_id was repointed'),
    suggested_investigation=(
        'List charges whose folio.reservation_id differs from their own '
        'reservation_id',
        'Check INV-A02 first — unrouted rows are the usual cause'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5'),
    affected_reports=('main.reservation_folio', 'reports.revenue',
                      'night audit folio control'),
    negative_seed=(
        "INSERT INTO folios (reservation_id, folio_letter, label, is_closed) "
        "SELECT (SELECT MAX(id) FROM reservations), 'Z', 'SEEDED', 0",
        "INSERT INTO extra_charges "
        "(reservation_id, folio_id, description, amount, charge_date, "
        " charge_type, charge_category, is_correction, is_reversal) "
        "SELECT (SELECT MIN(id) FROM reservations), "
        "  (SELECT MAX(id) FROM folios), 'SEEDED cross-routed charge', "
        "  613.00, r.arrival_date, 'food', 'Restaurant', 0, 0 "
        "FROM reservations r ORDER BY r.id LIMIT 1",
    ),
    negative_seed_reason=(
        'A charge whose folio belongs to a DIFFERENT reservation makes the '
        'two views of the same money disagree. The seed adds such a row '
        'rather than re-routing an existing one: on this dataset every '
        'charge is already unrouted, so re-routing one would merely swap '
        'it from one violation category to another and leave the count '
        'unchanged — the first version of this seed did exactly that and '
        'was correctly reported as undetected.'),
)
def _a03(ctx):
    rows = ctx.sql(
        'SELECT c.id, c.amount, c.reservation_id AS own_res, '
        '       f.reservation_id AS folio_res '
        'FROM extra_charges c LEFT JOIN folios f ON f.id = c.folio_id '
        'ORDER BY c.id')
    by_reservation = Decimal('0')
    by_folio = Decimal('0')
    violations = []
    for row in rows:
        amount = dec(row['amount'])
        by_reservation += amount
        if row['folio_res'] is None:
            # Unrouted, or routed to a folio that no longer exists. Either
            # way the folio view cannot see it; reported here rather than
            # allowed to cancel out of both sides.
            violations.append(row_violation(
                'extra_charge', row['id'],
                expected='reachable through a folio',
                observed='folio missing or unset', amount=amount))
            continue
        by_folio += amount
        if int(row['folio_res']) != int(row['own_res']):
            violations.append(row_violation(
                'extra_charge', row['id'],
                expected=f'folio belongs to reservation {row["own_res"]}',
                observed=f'folio belongs to reservation {row["folio_res"]}',
                amount=amount))

    if differs(by_reservation, by_folio) and not violations:
        violations.append(row_violation(
            'population', 'all charges',
            expected=f'folio view = {money(by_reservation)}',
            observed=f'folio view = {money(by_folio)}',
            amount=abs(by_reservation - by_folio),
            variance=money(by_folio - by_reservation)))

    population = len(rows)
    return (verdict(population, violations), population, violations,
            {'expected': 'both views total the same money',
             'observed': (f'reservation view {money(by_reservation)}, '
                          f'folio view {money(by_folio)}'),
             'variance': money(by_folio - by_reservation),
             'inputs': {'charge_rows': population}})


# ---------------------------------------------------------------------------
# INV-A04 — daily collections reconcile to the primary record
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-A04',
    title='Daily collections equal the direct payments recorded for the day',
    category=Category.ACCOUNTING,
    business_purpose=(
        'The day\'s cash figure is what the hotel banks against, what the '
        'shift is balanced against, and what the owner reads first. It must '
        'be the sum of the payment rows for that date and nothing else.'),
    business_rule=(
        'kpi_helpers.get_cash_revenue(d) = Σ payments on d that are not '
        'voided and whose mode category is direct_payment, AND no '
        'non-voided payment on d falls outside the direct/OTA '
        'classification.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('payments', 'payment_modes'),
    canonical_engine='app.kpi_helpers.get_cash_revenue',
    validation_method=(
        'Call the canonical engine for the date in scope and compare it '
        'against the same population summed in Decimal straight from the '
        'table. The ledger side additionally LEFT-joins the payment mode '
        'and totals anything that lands in neither the direct nor the OTA '
        'bucket.\n'
        '        That second half is not decoration. The first version of '
        'this invariant summed the ledger with the same INNER JOIN the '
        'engine uses, which made it tautological: a payment whose mode '
        'row is missing was dropped by both sides, they agreed, and the '
        'money vanished from the report unnoticed. Commissioning found '
        'that — the seeded fault was not detected — and the rule was '
        'widened rather than the seed weakened.'),
    evidence_produced=(
        'Engine figure, ledger figure, variance, row count and the ids of '
        'the payments in the population.'),
    failure_message=(
        'The day\'s collected cash does not equal the payments recorded '
        'for that day.'),
    likely_root_causes=(
        'The engine\'s join dropping rows whose payment mode is missing',
        'A filter on is_voided applied on one side only',
        'Float accumulation in SQL SUM over a REAL column',
        'A second definition of "cash" introduced by a report'),
    suggested_investigation=(
        'List the payments for the date with their mode and category',
        'Compare against INV-D03 — an orphan payment mode is the known '
        'route to this failure',
        'Re-run D3 replay for the date and read reconciliation RC01'),
    applicable_releases='all',
    applicable_business_dates='every date with payment activity',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=DATED + (Mode.ENTIRE_DATABASE, Mode.RELEASE_VERIFICATION,
                   Mode.CONTINUOUS_MONITORING),
    principles=('P1', 'P3', 'P8'),
    affected_reports=('reports.flash', 'main.dashboard',
                      'reports.front_office_mis', 'reports.payment_collection'),
    negative_seed=(
        "UPDATE payments SET payment_mode_id = 999999 "
        "WHERE id = (SELECT MIN(p.id) FROM payments p "
        "            JOIN payment_modes m ON m.id = p.payment_mode_id "
        "            WHERE p.is_voided = 0 AND m.category='direct_payment')",
    ),
    negative_seed_reason=(
        'An orphan payment mode is dropped by the engine\'s inner join but '
        'still sits in the table, so the engine and the primary record part '
        'company. This is the live gap D3 recorded; foreign keys are not '
        'enforced on this database, so the state is reachable.'),
)
def _a04(ctx):
    from app.kpi_helpers import get_cash_revenue
    import datetime as _dt

    ctx.require_app('INV-A04')
    dates = ([ctx.date] if ctx.date else
             [str(r[0]) for r in ctx.sql(
                 'SELECT DISTINCT payment_date FROM payments '
                 'WHERE payment_date IS NOT NULL ORDER BY payment_date')])

    KNOWN = ('direct_payment', 'ota_receivable')
    violations = []
    population = 0
    unclassified_total = Decimal('0')
    for day in dates:
        # LEFT JOIN, deliberately: an INNER JOIN here would mirror the
        # engine's own filter and make the comparison tautological.
        rows = ctx.sql(
            'SELECT p.id, p.amount, m.category '
            'FROM payments p '
            'LEFT JOIN payment_modes m ON m.id = p.payment_mode_id '
            'WHERE p.payment_date = ? AND p.is_voided = 0 ORDER BY p.id',
            (day,))
        direct = Decimal('0')
        unclassified = Decimal('0')
        direct_ids = []
        unclassified_ids = []
        for row in rows:
            amount = dec(row['amount'])
            category = row['category']
            if category == 'direct_payment':
                direct += amount
                direct_ids.append(int(row['id']))
            elif category not in KNOWN:
                unclassified += amount
                unclassified_ids.append(int(row['id']))
        population += len(rows)
        unclassified_total += unclassified

        engine = dec(get_cash_revenue(_dt.date.fromisoformat(day)))
        if differs(engine, direct):
            violations.append(row_violation(
                'business_date', day,
                expected=f'{money(direct)} from {len(direct_ids)} direct '
                         f'payment row(s)',
                observed=f'engine reports {money(engine)}',
                amount=abs(engine - direct),
                variance=money(engine - direct),
                payment_ids=direct_ids[:50]))
        if unclassified:
            violations.append(row_violation(
                'business_date', day,
                expected='every non-voided payment classified as direct or OTA',
                observed=(f'{len(unclassified_ids)} payment(s) carrying '
                          f'{money(unclassified)} belong to neither bucket, '
                          f'so no cash figure counts them'),
                amount=unclassified, payment_ids=unclassified_ids[:50]))

    return (verdict(population, violations), population, violations,
            {'expected': 'engine cash = Σ direct non-voided payments, and '
                         'nothing falls outside the classification',
             'observed': summarise('daily collections', population, violations),
             'variance': money(unclassified_total),
             'inputs': {'dates_examined': len(dates),
                        'payment_rows': population,
                        'unclassified_money': money(unclassified_total)}})


# ---------------------------------------------------------------------------
# INV-A05 — tax lines agree with their own base
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-A05',
    title='Every stored tax line equals its taxable base times its rate',
    category=Category.ACCOUNTING,
    business_purpose=(
        'Stored tax lines are what a GST return is filed from. A line whose '
        'amount does not follow from its own base and rate is a filing '
        'error waiting to be made, and it is invisible on any screen that '
        'shows only the total.'),
    business_rule=(
        'For every tax_lines row that is not exempt: '
        '|tax_amount - taxable_amount x tax_rate / 100| <= 0.01.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.CERTIFICATION,
    data_sources=('tax_lines',),
    canonical_engine='none — the stored line is checked against itself',
    validation_method=(
        'Recompute each line from its own stored base and rate. This is '
        'deliberately not a comparison against gst_service: that service '
        'writes (it calls ensure_all_tax_lines, which commits), and an '
        'invariant may not write.'),
    evidence_produced=(
        'Per line: base, rate, stored amount, recomputed amount, variance.'),
    failure_message=(
        'A stored tax line does not equal its own base times its own rate.'),
    likely_root_causes=(
        'A rate change applied to the rate column without recomputing the '
        'amount',
        'Rounding applied per invoice rather than per line',
        'A manual correction to one column only'),
    suggested_investigation=(
        'Group the failing lines by tax_rate and by charge_date to see '
        'whether they cluster around a rate change',
        'Compare against the invoice totals stored on the reservation'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P1', 'P11'),
    affected_reports=('billing.gst_report', 'main.invoice',
                      'billing.gstr_export'),
    negative_seed=(
        "UPDATE tax_lines SET tax_amount = tax_amount + 100.00 "
        "WHERE id = (SELECT MIN(id) FROM tax_lines)",
    ),
    negative_seed_reason=(
        'Moving a stored tax amount away from its base breaks the '
        'relationship the rule asserts, without touching anything else.'),
)
def _a05(ctx):
    date_clause, params = scope_clause(ctx, 'charge_date')
    rows = ctx.sql(
        f'SELECT id, reservation_id, taxable_amount, tax_rate, tax_amount, '
        f'       tax_type, is_exempted, charge_date '
        f'FROM tax_lines WHERE 1=1{date_clause} ORDER BY id', params)

    violations = []
    examined = 0
    for row in rows:
        if row['is_exempted']:
            continue
        examined += 1
        base = dec(row['taxable_amount'])
        rate = dec(row['tax_rate'])
        stored = dec(row['tax_amount'])
        expected = (base * rate / Decimal('100')).quantize(Decimal('0.01'))
        if abs(stored - expected) > Decimal('0.01'):
            violations.append(row_violation(
                'tax_line', row['id'],
                expected=f'{money(expected)} = {money(base)} x {rate}%',
                observed=money(stored), amount=abs(stored - expected),
                variance=money(stored - expected),
                tax_type=str(row['tax_type']),
                reservation_id=row['reservation_id'],
                charge_date=str(row['charge_date'])))

    return (verdict(examined, violations), examined, violations,
            {'expected': 'tax_amount = taxable_amount x rate / 100 (±0.01)',
             'observed': summarise('tax lines', examined, violations),
             'inputs': {'rows_in_scope': len(rows), 'non_exempt': examined}})


# ---------------------------------------------------------------------------
# INV-A06 — overpayment must be recorded
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-A06',
    title='A guest who has paid more than they owe has an overpayment record',
    category=Category.ACCOUNTING,
    business_purpose=(
        'Money held above what a guest owes is a liability, not revenue. '
        'Until it is recorded as an overpayment it looks like income, '
        'inflates the day\'s collections, and nobody knows to refund it.'),
    business_rule=(
        'For every reservation whose settlement_balance is negative by more '
        'than one rupee, an overpayment_logs row exists.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('reservations', 'payments', 'overpayment_logs'),
    canonical_engine='app.services.calculate_stay_amount',
    validation_method=(
        'Compute the settlement balance through the canonical engine, take '
        'the reservations that are negative, and require each to appear in '
        'overpayment_logs.'),
    evidence_produced=(
        'Per reservation: settlement balance, amount overpaid, whether an '
        'overpayment record exists.'),
    failure_message=(
        'A reservation is overpaid with no overpayment record. The hotel is '
        'holding money it has not acknowledged owing.'),
    likely_root_causes=(
        'An overpayment path that logs only when detected at checkout',
        'A payment posted after checkout, bypassing the detection',
        'Rounding: an invoice rounded down while payment matched the '
        'unrounded total'),
    suggested_investigation=(
        'Compare each finding\'s magnitude against 1.00 — sub-rupee cases '
        'are the rounding path, larger ones are not',
        'Check the created_at of the last payment against checked_out_at'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + (Mode.SINGLE_RESERVATION,),
    principles=('P1', 'P5', 'P10'),
    affected_reports=('reports.refund_report', 'main.reservation_folio',
                      'night audit folio control'),
    negative_seed=(
        "INSERT INTO payments "
        "(reservation_id, folio_id, payment_mode_id, amount, payment_date, "
        " is_voided, is_correction, is_reversal, payment_purpose) "
        "SELECT p.reservation_id, p.folio_id, p.payment_mode_id, 50000.00, "
        "  p.payment_date, 0, 0, 0, 'settlement' "
        "FROM payments p ORDER BY p.id LIMIT 1",
    ),
    negative_seed_reason=(
        'A 50,000 payment against one reservation drives its settlement '
        'balance far negative with no overpayment record, which is exactly '
        'the unacknowledged liability the rule forbids.'),
)
def _a06(ctx):
    from app.models import Reservation
    from app.services import calculate_stay_amount

    ctx.require_app('INV-A06')
    query = Reservation.query
    if ctx.reservation_id:
        query = query.filter(Reservation.id == ctx.reservation_id)
    reservations = query.order_by(Reservation.id).all()

    logged = {int(r[0]) for r in ctx.sql(
        'SELECT DISTINCT reservation_id FROM overpayment_logs '
        'WHERE reservation_id IS NOT NULL')} if ctx.table_exists(
        'overpayment_logs') else set()

    violations = []
    overpaid = 0
    for r in reservations:
        balance = dec(calculate_stay_amount(r)['settlement_balance'])
        if balance >= Decimal('-1.00'):
            continue
        overpaid += 1
        if r.id not in logged:
            violations.append(row_violation(
                'reservation', r.id,
                expected='an overpayment_logs row',
                observed='none', amount=abs(balance),
                variance=money(balance)))

    return (verdict(overpaid, violations), overpaid, violations,
            {'expected': 'every overpaid reservation is logged',
             'observed': summarise('overpaid reservations', overpaid,
                                   violations),
             'inputs': {'reservations_examined': len(reservations),
                        'overpaid': overpaid,
                        'overpayment_log_rows': len(logged)}})
