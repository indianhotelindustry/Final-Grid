"""
Class D — Referential invariants.

Every financial fact must have an origin. These are the least glamorous
invariants and the ones that decide whether the other three classes can
be trusted: a reconciliation over rows whose parents have vanished is
arithmetic performed on rubble.

Foreign keys are not enforced on this SQLite database (``PRAGMA
foreign_keys`` is 0). Every rule in this file therefore checks a
constraint the database is declaring but not applying, which is exactly
why they belong in the engine rather than in the schema.
"""
from __future__ import annotations

from verification.invariants.helpers import (
    dec, money, row_violation, summarise, verdict,
)
from verification.invariants.model import (
    Blocking, Category, Commissioning, Mode, Severity, Status,
)
from verification.invariants.registry import invariant

WHOLE_DB = (Mode.ENTIRE_DATABASE, Mode.RELEASE_VERIFICATION,
            Mode.REGRESSION_DATASET, Mode.CONTINUOUS_MONITORING)


def _dangling(ctx, child_table: str, child_key: str, parent_table: str,
              amount_col: str = '') -> list:
    """Rows whose declared parent does not exist."""
    amount_select = f', c."{amount_col}" AS amt' if amount_col else ''
    return ctx.sql(
        f'SELECT c.id, c."{child_key}" AS parent_id{amount_select} '
        f'FROM "{child_table}" c '
        f'LEFT JOIN "{parent_table}" p ON p.id = c."{child_key}" '
        f'WHERE c."{child_key}" IS NOT NULL AND p.id IS NULL '
        f'ORDER BY c.id')


# ---------------------------------------------------------------------------
# INV-D01 — every folio has a reservation
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-D01',
    title='Every folio references a reservation that exists',
    category=Category.REFERENTIAL,
    business_purpose=(
        'A folio is a bill. A bill for no stay cannot be issued, chased or '
        'explained, but its charges and payments still appear in the '
        'hotel\'s totals.'),
    business_rule='Every folios row references an existing reservations row.',
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('folios', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method='Left-join folios to reservations and report the misses.',
    evidence_produced='Per orphan folio: id and the reservation id claimed.',
    failure_message='Folios exist for reservations that do not.',
    likely_root_causes=(
        'A reservation deleted without cascading its folios',
        'Foreign keys not enforced, so nothing at the database level '
        'prevents it'),
    suggested_investigation=(
        'Check every delete path that touches reservations',
        'Total the charges and payments routed to the orphan folios'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5', 'P14'),
    affected_reports=('main.reservation_folio', 'reports.ar_aging'),
    negative_seed=(
        "UPDATE folios SET reservation_id = 876543 "
        "WHERE id = (SELECT MIN(id) FROM folios)",
    ),
    negative_seed_reason=(
        'Repointing a folio at a reservation id that does not exist is the '
        'dangling reference the rule forbids.'),
)
def _d01(ctx):
    rows = _dangling(ctx, 'folios', 'reservation_id', 'reservations')
    violations = [row_violation(
        'folio', r['id'], expected='an existing reservation',
        observed=f'reservation_id {r["parent_id"]} not found', amount=0)
        for r in rows]
    population = ctx.count('SELECT COUNT(*) FROM folios')
    return (verdict(population, violations), population, violations,
            {'expected': 'every folio has a reservation',
             'observed': summarise('folios', population, violations),
             'inputs': {'folios': population}})


# ---------------------------------------------------------------------------
# INV-D02 — every correction references its original
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-D02',
    title='Every correction and reversal references the transaction it corrects',
    category=Category.REFERENTIAL,
    business_purpose=(
        'A correction is only auditable if you can see what it corrected. '
        'A reversal with no original is indistinguishable from a new '
        'negative transaction invented from nothing, and it is the '
        'classic shape of a concealed adjustment.'),
    business_rule=(
        'Every payments or extra_charges row flagged is_correction or '
        'is_reversal carries a corrects_id, and that id resolves to a row '
        'in the same table.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('payments', 'extra_charges'),
    canonical_engine='app.services.signed_extra_charge_amount',
    validation_method=(
        'Check the flag and the pointer together. A row flagged as a '
        'correction with no pointer is reported, and so is a pointer that '
        'does not resolve — they are different failures and each is named.'),
    evidence_produced=(
        'Per row: which flag is set, the corrects_id, whether it resolves, '
        'the amount involved.'),
    failure_message=(
        'A correction or reversal exists with no traceable original.'),
    likely_root_causes=(
        'A correction UI that sets the flag but not the link',
        'The original deleted after the correction was raised',
        'A bulk adjustment written directly to the database'),
    suggested_investigation=(
        'Read correction_reason on the affected rows',
        'Check whether the correction path is transactional',
        'Confirm signed_extra_charge_amount treats these rows as intended'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5', 'P14', 'P11'),
    affected_reports=('reports.revenue', 'billing.gst_report',
                      'night audit payment summary'),
    negative_seed=(
        "UPDATE payments SET is_reversal = 1 "
        "WHERE id = (SELECT MIN(id) FROM payments)",
    ),
    negative_seed_reason=(
        'Flagging a payment as a reversal without giving it a corrects_id '
        'creates a negative-signed entry with no original — the '
        'unauditable adjustment the rule forbids.'),
)
def _d02(ctx):
    violations = []
    population = 0
    for table in ('payments', 'extra_charges'):
        if not ctx.table_exists(table):
            continue
        rows = ctx.sql(
            f'SELECT c.id, c.amount, c.is_correction, c.is_reversal, '
            f'       c.corrects_id, p.id AS original '
            f'FROM "{table}" c LEFT JOIN "{table}" p ON p.id = c.corrects_id '
            f'WHERE c.is_correction = 1 OR c.is_reversal = 1 ORDER BY c.id')
        population += len(rows)
        for row in rows:
            flags = []
            if row['is_correction']:
                flags.append('is_correction')
            if row['is_reversal']:
                flags.append('is_reversal')
            label = '+'.join(flags)
            if row['corrects_id'] is None:
                violations.append(row_violation(
                    table.rstrip('s'), row['id'],
                    expected=f'{label} row carries a corrects_id',
                    observed='corrects_id is NULL', amount=dec(row['amount']),
                    table=table))
            elif row['original'] is None:
                violations.append(row_violation(
                    table.rstrip('s'), row['id'],
                    expected=f'corrects_id {row["corrects_id"]} resolves',
                    observed='the referenced original does not exist',
                    amount=dec(row['amount']), table=table))

    if population == 0:
        return (Status.VACUOUS, 0, [],
                {'expected': 'every correction points at its original',
                 'observed': ('no correction or reversal rows exist, so the '
                              'rule was not exercised. The signing logic in '
                              'signed_extra_charge_amount is therefore also '
                              'untested by live data'),
                 'inputs': {'correction_rows': 0}})

    return (verdict(population, violations), population, violations,
            {'expected': 'every correction points at its original',
             'observed': summarise('correction rows', population, violations),
             'inputs': {'correction_rows': population}})


# ---------------------------------------------------------------------------
# INV-D03 — every payment has a payment mode
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-D03',
    title='Every payment references a payment mode that exists',
    category=Category.REFERENTIAL,
    business_purpose=(
        'The payment mode decides whether money is cash in the drawer or a '
        'receivable from an agent. A payment whose mode is missing is '
        'counted as direct cash by the night audit and dropped entirely by '
        'the dashboard helpers, so the same rupees appear on one report and '
        'not the other.'),
    business_rule=(
        'Every payments row references an existing payment_modes row, and '
        'that row\'s category is one of direct_payment or ota_receivable.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('payments', 'payment_modes'),
    canonical_engine=(
        'app.kpi_helpers.get_cash_revenue and '
        'app.night_audit_service.NightAuditService.payment_summary'),
    validation_method=(
        'Left-join payments to payment_modes and report the misses, then '
        'check the category of every mode in use against the two the '
        'system understands.'),
    evidence_produced=(
        'Per orphan payment: the mode id claimed and the amount, plus any '
        'mode whose category is outside the known set.'),
    failure_message=(
        'A payment references a payment mode that does not exist, or a '
        'mode carries an unrecognised category. The money will be counted '
        'differently by different reports.'),
    likely_root_causes=(
        'A payment mode deactivated by deletion rather than is_active=0',
        'A category value introduced without updating the consuming code',
        'Foreign keys not enforced, so nothing prevents the dangling id'),
    suggested_investigation=(
        'Compare get_cash_revenue against the night audit total_collected '
        'for the affected date — they will differ by exactly the orphan '
        'amount',
        'Check that mode deactivation uses is_active rather than DELETE'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P3', 'P5', 'P14'),
    affected_reports=('reports.flash', 'main.dashboard',
                      'night audit payment summary',
                      'reports.payment_collection'),
    negative_seed=(
        "UPDATE payments SET payment_mode_id = 999999 "
        "WHERE id = (SELECT MIN(id) FROM payments)",
    ),
    negative_seed_reason=(
        'This is the exact live gap D3 found: an orphan mode is treated as '
        'direct cash by one engine and dropped by another, so the same '
        'money is counted twice differently.'),
)
def _d03(ctx):
    KNOWN = {'direct_payment', 'ota_receivable'}
    rows = _dangling(ctx, 'payments', 'payment_mode_id', 'payment_modes',
                     'amount')
    violations = [row_violation(
        'payment', r['id'], expected='an existing payment mode',
        observed=f'payment_mode_id {r["parent_id"]} not found',
        amount=dec(r['amt'])) for r in rows]

    categories = ctx.sql(
        'SELECT m.id, m.name, m.category, COUNT(p.id) AS uses '
        'FROM payment_modes m LEFT JOIN payments p '
        '  ON p.payment_mode_id = m.id '
        'GROUP BY m.id, m.name, m.category ORDER BY m.id')
    for row in categories:
        if (row['category'] or '') not in KNOWN:
            violations.append(row_violation(
                'payment_mode', row['id'],
                expected=f'category in {sorted(KNOWN)}',
                observed=f'category {row["category"]!r} on '
                         f'{row["name"]!r}', amount=0,
                payments_using_it=int(row['uses'])))

    population = ctx.count('SELECT COUNT(*) FROM payments')
    return (verdict(population, violations), population, violations,
            {'expected': 'every payment has a mode with a known category',
             'observed': summarise('payments', population, violations),
             'inputs': {'payments': population,
                        'payment_modes': len(categories),
                        'known_categories': sorted(KNOWN)}})


# ---------------------------------------------------------------------------
# INV-D04 — every tax line has a resolvable charge source
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-D04',
    title='Every tax line names the charge it was raised on',
    category=Category.REFERENTIAL,
    business_purpose=(
        'A GST line must be traceable to the supply that gave rise to it. '
        'A tax line whose source cannot be identified cannot be defended in '
        'an assessment, and it cannot be reversed if the underlying charge '
        'is cancelled.'),
    business_rule=(
        'Every tax_lines row carries a charge_source_type and a '
        'charge_source_id, and where the source type is a known table the '
        'id resolves.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('tax_lines', 'extra_charges', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Require both source fields, then resolve the id against the table '
        'the type names. Source types the engine does not recognise are '
        'reported as unresolvable rather than assumed valid, so a new '
        'source type cannot slip in unnoticed.'),
    evidence_produced=(
        'Per tax line: source type, source id, whether it resolves, the tax '
        'amount at stake.'),
    failure_message=(
        'Tax lines exist whose originating charge cannot be identified.'),
    likely_root_causes=(
        'A tax line written before its charge was committed',
        'A new charge source type added without updating the tax writer',
        'The originating charge deleted, leaving the tax line behind'),
    suggested_investigation=(
        'Group the failures by charge_source_type to see whether one type '
        'accounts for all of them',
        'Compare against INV-A05 — a line with no source may also have no '
        'valid base'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5', 'P14'),
    affected_reports=('billing.gst_report', 'billing.gstr_export',
                      'main.invoice'),
    negative_seed=(
        "UPDATE tax_lines SET charge_source_id = 'night_1999-01-01' "
        "WHERE id = (SELECT MIN(id) FROM tax_lines "
        "            WHERE charge_source_type = 'room_night')",
    ),
    negative_seed_reason=(
        'Pointing a room-night tax line at a night the guest never stayed '
        'makes it untraceable to any supply. The seed does not set the '
        'column to NULL: charge_source_id is NOT NULL, and the first '
        'version of this seed raised an IntegrityError, which the suite '
        'correctly reported as a broken seed rather than a blind '
        'invariant.'),
)
def _d04(ctx):
    #: How each source type is resolved. The room-night form is not a row
    #: id: ``gst_service`` writes the composite key ``night_<stay_date>``
    #: against the reservation, so resolving it means looking for a priced
    #: night of that stay on that date rather than a primary key.
    #:
    #: The first version of this invariant knew only about integer ids and
    #: reported all sixty room-night lines as unresolvable — a false
    #: positive in the invariant, not a defect in the data. The resolvers
    #: are declared explicitly so a source type the engine does not
    #: understand is reported as exactly that.
    ID_RESOLVERS = {
        'extra_charge': 'extra_charges',
        'extra_charges': 'extra_charges',
        'charge': 'extra_charges',
        'reservation': 'reservations',
        'stay': 'reservations',
    }
    NIGHT_PREFIX = 'night_'

    rows = ctx.sql(
        'SELECT id, reservation_id, charge_source_type, charge_source_id, '
        '       tax_amount FROM tax_lines ORDER BY id')
    violations = []
    unresolvable_types: dict = {}
    for row in rows:
        source_type = (row['charge_source_type'] or '').strip().lower()
        source_id = row['charge_source_id']
        if not source_type or source_id in (None, ''):
            violations.append(row_violation(
                'tax_line', row['id'],
                expected='charge_source_type and charge_source_id set',
                observed=f'type {row["charge_source_type"]!r}, '
                         f'id {source_id!r}',
                amount=dec(row['tax_amount'])))
            continue

        if source_type in ('room_night', 'room_rent', 'room'):
            text = str(source_id)
            stay_date = (text[len(NIGHT_PREFIX):]
                         if text.startswith(NIGHT_PREFIX) else text)
            resolved = ctx.count(
                'SELECT COUNT(*) FROM reservation_night_rates '
                'WHERE reservation_id = ? AND stay_date = ?',
                (row['reservation_id'], stay_date))
            if not resolved:
                violations.append(row_violation(
                    'tax_line', row['id'],
                    expected=f'a priced night of reservation '
                             f'{row["reservation_id"]} on {stay_date}',
                    observed='no such room night exists',
                    amount=dec(row['tax_amount'])))
            continue

        table = ID_RESOLVERS.get(source_type)
        if table is None:
            unresolvable_types[source_type] = \
                unresolvable_types.get(source_type, 0) + 1
            violations.append(row_violation(
                'tax_line', row['id'],
                expected=f'a source type this engine can resolve '
                         f'{sorted(set(ID_RESOLVERS)) + ["room_night"]}',
                observed=f'source type {source_type!r}',
                amount=dec(row['tax_amount'])))
            continue
        try:
            resolved = ctx.count(
                f'SELECT COUNT(*) FROM "{table}" WHERE id = ?',
                (int(str(source_id)),))
        except (TypeError, ValueError):
            resolved = 0
        if not resolved:
            violations.append(row_violation(
                'tax_line', row['id'],
                expected=f'{table} row {source_id}',
                observed='the referenced charge does not exist',
                amount=dec(row['tax_amount'])))

    return (verdict(len(rows), violations), len(rows), violations,
            {'expected': 'every tax line resolves to its charge',
             'observed': summarise('tax lines', len(rows), violations),
             'inputs': {'tax_lines': len(rows),
                        'unresolvable_source_types': unresolvable_types}})


# ---------------------------------------------------------------------------
# INV-D05 — every void request references a payment
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-D05',
    title='Every void request and credit note references what it cancels',
    category=Category.REFERENTIAL,
    business_purpose=(
        'A void and a credit note both remove money that was previously '
        'recognised. Each is only auditable if the thing it removed can '
        'still be identified — otherwise the reduction stands with nothing '
        'behind it.'),
    business_rule=(
        'Every void_requests row references an existing payment, and every '
        'credit_notes row references an existing reservation.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('void_requests', 'payments', 'credit_notes', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Left-join each cancellation record to what it claims to cancel. '
        'Both tables are checked in one invariant because they are the same '
        'obligation — a reduction must name what it reduced — and splitting '
        'them would make the constitutional coverage read as broader than '
        'it is.'),
    evidence_produced=(
        'Per orphan: the record, what it claims to reference, the amount.'),
    failure_message=(
        'A void or credit note exists with nothing behind it.'),
    likely_root_causes=(
        'A payment hard-deleted instead of voided',
        'A credit note raised against a reservation later removed',
        'A void request left behind after its payment was purged'),
    suggested_investigation=(
        'Check whether any path deletes payments rather than voiding them',
        'Total the credit notes with no reservation — that is revenue '
        'reduced against nothing'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5', 'P14', 'P11'),
    affected_reports=('reports.refund_report', 'billing.gst_report',
                      'reports.revenue'),
    negative_seed=(
        "INSERT INTO void_requests "
        "(payment_id, requested_by_user_id, requested_at, reason, status) "
        "VALUES (555444, 1, '2026-01-01 00:00:00', 'SEEDED', 'Pending')",
    ),
    negative_seed_reason=(
        'A void request against a payment that does not exist is a '
        'reduction with nothing behind it.'),
)
def _d05(ctx):
    violations = []
    population = 0

    if ctx.table_exists('void_requests'):
        population += ctx.count('SELECT COUNT(*) FROM void_requests')
        for row in _dangling(ctx, 'void_requests', 'payment_id', 'payments'):
            violations.append(row_violation(
                'void_request', row['id'],
                expected='an existing payment',
                observed=f'payment_id {row["parent_id"]} not found',
                amount=0))

    if ctx.table_exists('credit_notes'):
        population += ctx.count('SELECT COUNT(*) FROM credit_notes')
        rows = ctx.sql(
            'SELECT c.id, c.reservation_id, c.total_amount '
            'FROM credit_notes c '
            'LEFT JOIN reservations r ON r.id = c.reservation_id '
            'WHERE r.id IS NULL ORDER BY c.id')
        for row in rows:
            violations.append(row_violation(
                'credit_note', row['id'],
                expected='an existing reservation',
                observed=f'reservation_id {row["reservation_id"]} not found',
                amount=dec(row['total_amount'])))

    if population == 0:
        return (Status.VACUOUS, 0, [],
                {'expected': 'every cancellation names what it cancelled',
                 'observed': ('no void requests and no credit notes exist, '
                              'so the rule was not exercised'),
                 'inputs': {'void_requests': 0, 'credit_notes': 0}})

    return (verdict(population, violations), population, violations,
            {'expected': 'every cancellation names what it cancelled',
             'observed': summarise('cancellation records', population,
                                   violations),
             'inputs': {'records': population}})


# ---------------------------------------------------------------------------
# INV-D06 — every nightly rate belongs to its stay
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-D06',
    title='Every priced room night belongs to a stay that covers that night',
    category=Category.REFERENTIAL,
    business_purpose=(
        'The nightly rate rows are what room revenue is earned from. A row '
        'whose reservation does not exist, or whose stay date falls outside '
        'the stay it belongs to, contributes revenue to a night the hotel '
        'did not sell.'),
    business_rule=(
        'Every reservation_night_rates row references an existing '
        'reservation, and its stay_date satisfies '
        'arrival_date <= stay_date < departure_date.'),
    severity=Severity.HIGH,
    blocking=Blocking.RELEASE,
    data_sources=('reservation_night_rates', 'reservations'),
    canonical_engine='app.services.get_room_revenue',
    validation_method=(
        'Join each nightly row to its reservation and bound its stay date '
        'by the stay window.'),
    evidence_produced=(
        'Per row: reservation, stay window, stay date, rate at stake.'),
    failure_message=(
        'Priced room nights exist outside the stay they belong to.'),
    likely_root_causes=(
        'A stay shortened or extended without regenerating the nightly rows',
        'A date-shift correction applied to the reservation only',
        'Nightly rows generated before the dates were finalised'),
    suggested_investigation=(
        'Compare the nightly rows\' created_at against the reservation\'s '
        'updated dates',
        'Check whether the date-change path regenerates nightly rows',
        'Total the out-of-window rates — that is revenue attributed to '
        'nights that were not sold'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5', 'P14', 'P8'),
    affected_reports=('reports.revenue', 'night audit revenue summary',
                      'reports.front_office_mis'),
    negative_seed=(
        "UPDATE reservation_night_rates "
        "SET stay_date = DATE(stay_date, '+90 day') "
        "WHERE id = (SELECT MIN(id) FROM reservation_night_rates)",
    ),
    negative_seed_reason=(
        'Moving one priced night ninety days out of its stay attributes '
        'room revenue to a night the guest was not present.'),
)
def _d06(ctx):
    import datetime as _dt

    if not ctx.table_exists('reservation_night_rates'):
        return (Status.NOT_APPLICABLE, 0, [],
                {'expected': 'nightly rows lie inside their stay',
                 'observed': 'reservation_night_rates does not exist in this '
                             'schema version',
                 'inputs': {}})

    rows = ctx.sql(
        'SELECT n.id, n.reservation_id, n.stay_date, n.final_rate, '
        '       r.arrival_date, r.departure_date '
        'FROM reservation_night_rates n '
        'LEFT JOIN reservations r ON r.id = n.reservation_id ORDER BY n.id')

    violations = []
    for row in rows:
        if row['arrival_date'] is None:
            violations.append(row_violation(
                'night_rate', row['id'],
                expected='an existing reservation',
                observed=f'reservation_id {row["reservation_id"]} not found',
                amount=dec(row['final_rate'])))
            continue
        try:
            stay = _dt.date.fromisoformat(str(row['stay_date'])[:10])
            arrival = _dt.date.fromisoformat(str(row['arrival_date'])[:10])
            departure = _dt.date.fromisoformat(str(row['departure_date'])[:10])
        except (TypeError, ValueError):
            violations.append(row_violation(
                'night_rate', row['id'],
                expected='readable stay and night dates',
                observed=f'stay_date {row["stay_date"]!r}',
                amount=dec(row['final_rate'])))
            continue
        if not (arrival <= stay < departure):
            violations.append(row_violation(
                'night_rate', row['id'],
                expected=f'a night in [{arrival}, {departure})',
                observed=f'stay_date {stay}', amount=dec(row['final_rate']),
                reservation_id=row['reservation_id']))

    return (verdict(len(rows), violations), len(rows), violations,
            {'expected': 'every priced night lies inside its stay',
             'observed': summarise('nightly rate rows', len(rows), violations),
             'inputs': {'night_rate_rows': len(rows)}})
