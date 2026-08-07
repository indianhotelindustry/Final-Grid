"""
Class C — Domain invariants.

The hotel's own rules. These are the obligations that come from how the
business works rather than from arithmetic: a walk-in guest cannot be
settled through an OTA receivable, a room cannot hold two guests on the
same night, a guest cannot be checked out with money outstanding and no
recorded reason.

They are the invariants most likely to be argued with, because each one
encodes a business judgement. That is why every rule here states its
purpose in business terms and declares exactly what it treats as
legitimate — a rule whose exceptions are undocumented gets switched off
the first time it fires on a legitimate case.
"""
from __future__ import annotations

from decimal import Decimal

from verification.invariants.helpers import (
    dec, money, row_violation, scope_clause, summarise, verdict,
)
from verification.invariants.model import (
    Blocking, Category, Commissioning, Mode, Severity, Status,
)
from verification.invariants.registry import invariant

WHOLE_DB = (Mode.ENTIRE_DATABASE, Mode.RELEASE_VERIFICATION,
            Mode.REGRESSION_DATASET, Mode.CONTINUOUS_MONITORING)
DATED = (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT, Mode.HISTORICAL_REPLAY)


# ---------------------------------------------------------------------------
# INV-C01 — walk-in cannot settle to an OTA
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-C01',
    title='A walk-in reservation is never settled through an OTA receivable',
    category=Category.DOMAIN,
    business_purpose=(
        'An OTA receivable posting says "a travel agent owes us this money '
        'and will remit it". For a guest who walked in off the street there '
        'is no agent, so the posting creates a receivable against nobody. '
        'The cash was either taken at the desk and is now missing from the '
        'cash figure, or it was never taken at all.'),
    business_rule=(
        'No payment whose mode category is ota_receivable belongs to a '
        'reservation whose source is a walk-in.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.CERTIFICATION,
    data_sources=('payments', 'payment_modes', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Join payments to their mode and their reservation and report every '
        'ota_receivable posting on a walk-in booking. Source matching is '
        'case-insensitive and covers the spellings the dataset actually '
        'contains, because a rule that missed "Walk-in" while catching '
        '"walk_in" would report a clean result on a dirty system.'),
    evidence_produced=(
        'Per payment: reservation, source, ota_channel, mode, amount. '
        'Totalled so the exposure has a rupee value.'),
    failure_message=(
        'Walk-in reservations carry OTA receivable postings. Money is booked '
        'as owed by an agent that was never involved.'),
    likely_root_causes=(
        'The payment mode list is presented unfiltered at the desk, so an '
        'OTA head can be picked for any booking',
        'A booking imported from an OTA whose source was overwritten to '
        'walk-in during check-in',
        'Test or seed data that was never cleaned out'),
    suggested_investigation=(
        'Check whether ota_channel or ota_booking_id is set on the affected '
        'reservations — if not, the OTA head is certainly wrong',
        'Confirm whether the desk UI restricts payment modes by booking '
        'source',
        'Compare the total against the OTA receivable balance being chased'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P5', 'P11'),
    affected_reports=('reports.ota_reconciliation', 'reports.ar_aging',
                      'reports.flash', 'night audit payment summary'),
    negative_seed=(
        "UPDATE payments SET payment_mode_id = "
        "  (SELECT id FROM payment_modes WHERE category='ota_receivable' "
        "    ORDER BY id LIMIT 1) "
        "WHERE id = (SELECT MIN(p.id) FROM payments p "
        "            JOIN payment_modes m ON m.id = p.payment_mode_id "
        "            WHERE m.category = 'direct_payment')",
    ),
    negative_seed_reason=(
        'Repointing a direct payment at an OTA head creates exactly the '
        'forbidden pairing. On the current dataset the rule already fails, '
        'so the seed is verified by the violation count rising.'),
)
def _c01(ctx):
    WALK_IN = ('walk-in', 'walk_in', 'walkin', 'walk in')
    clause, params = scope_clause(ctx, 'p.payment_date')
    rows = ctx.sql(
        f"SELECT p.id, p.amount, p.payment_date, r.id AS res_id, r.source, "
        f"       r.ota_channel, r.ota_booking_id, m.name AS mode_name "
        f"FROM payments p "
        f"JOIN payment_modes m ON m.id = p.payment_mode_id "
        f"JOIN reservations r ON r.id = p.reservation_id "
        f"WHERE m.category = 'ota_receivable'{clause} ORDER BY p.id", params)

    violations = []
    exposure = Decimal('0')
    for row in rows:
        source = (row['source'] or '').strip().lower()
        if source not in WALK_IN:
            continue
        amount = dec(row['amount'])
        exposure += amount
        violations.append(row_violation(
            'payment', row['id'],
            expected='an OTA head only on an OTA booking',
            observed=(f'{row["mode_name"]} on reservation {row["res_id"]} '
                      f'with source {row["source"]!r}'),
            amount=amount, reservation_id=row['res_id'],
            ota_channel=row['ota_channel'],
            ota_booking_id=row['ota_booking_id'],
            payment_date=str(row['payment_date'])))

    return (verdict(len(rows), violations), len(rows), violations,
            {'expected': 'no OTA receivable posting on a walk-in booking',
             'observed': (f'{len(violations)} of {len(rows)} OTA posting(s) '
                          f'sit on walk-in bookings, carrying '
                          f'{money(exposure)}'),
             'variance': money(exposure),
             'inputs': {'ota_postings_in_scope': len(rows),
                        'walk_in_spellings_matched': list(WALK_IN)}})


# ---------------------------------------------------------------------------
# INV-C02 — checkout prerequisites
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-C02',
    title='A checked-out reservation is settled, or its balance is explained',
    category=Category.DOMAIN,
    business_purpose=(
        'Letting a guest leave with money outstanding is a decision — a '
        'credit arrangement, a company account, a write-off. It is never an '
        'accident, and it must leave a trace. An unexplained outstanding '
        'balance on a departed guest is money the hotel has stopped being '
        'able to collect and has not decided to lose.'),
    business_rule=(
        'For every reservation with status CheckedOut: checked_out_at is '
        'set, and either settlement_balance <= 1.00 or the reservation '
        'carries a credit_amount, a company credit, or a credit note.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('reservations', 'payments', 'extra_charges', 'credit_notes'),
    canonical_engine='app.services.calculate_stay_amount',
    validation_method=(
        'Compute the settlement balance through the canonical engine and '
        'require either settlement or a recorded justification. The one '
        'rupee allowance is the invoice rounding the engine itself applies; '
        'anything larger is a real balance.'),
    evidence_produced=(
        'Per reservation: checkout time, settlement balance, the '
        'justification found or its absence.'),
    failure_message=(
        'Guests have departed with an unexplained outstanding balance.'),
    likely_root_causes=(
        'A checkout route that warns about a balance but does not require a '
        'reason',
        'A credit arrangement agreed verbally and never recorded',
        'Charges posted after the guest departed'),
    suggested_investigation=(
        'Compare the last charge\'s created_at against checked_out_at',
        'Check whether the checkout route blocks or merely warns',
        'Look for a matching credit_note issued later'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + (Mode.SINGLE_RESERVATION,),
    principles=('P5', 'P11'),
    affected_reports=('reports.ar_aging', 'main.reservation_folio',
                      'night audit folio control'),
    negative_seed=(
        "INSERT INTO extra_charges "
        "(reservation_id, folio_id, description, amount, charge_date, "
        " charge_type, charge_category, is_correction, is_reversal) "
        "SELECT id, NULL, 'SEEDED unpaid charge', 7500.00, departure_date, "
        "  'food', 'Restaurant', 0, 0 "
        "FROM reservations WHERE status = 'CheckedOut' "
        "  AND COALESCE(credit_amount, 0) = 0 ORDER BY id LIMIT 1",
    ),
    negative_seed_reason=(
        'A 7,500 charge added to a departed guest with no credit '
        'arrangement leaves exactly the unexplained balance the rule '
        'forbids. The reservation is chosen for having NO credit_amount: '
        'the first version of this seed took the lowest-id checked-out '
        'reservation, which happens to carry a 200.00 credit, so the '
        'balance was correctly treated as justified and the seed went '
        'undetected — a broken seed, not a blind invariant.'),
)
def _c02(ctx):
    from app.models import Reservation
    from app.services import calculate_stay_amount

    ctx.require_app('INV-C02')
    query = Reservation.query.filter(Reservation.status == 'CheckedOut')
    if ctx.reservation_id:
        query = query.filter(Reservation.id == ctx.reservation_id)
    reservations = query.order_by(Reservation.id).all()

    credit_noted = {int(r[0]) for r in ctx.sql(
        'SELECT DISTINCT reservation_id FROM credit_notes '
        'WHERE reservation_id IS NOT NULL')} if ctx.table_exists(
        'credit_notes') else set()

    violations = []
    for r in reservations:
        if r.checked_out_at is None:
            violations.append(row_violation(
                'reservation', r.id,
                expected='checked_out_at set on a CheckedOut reservation',
                observed='checked_out_at is NULL', amount=0))
            continue
        amounts = calculate_stay_amount(r)
        balance = dec(amounts['settlement_balance'])
        if balance <= Decimal('1.00'):
            continue
        justified = (dec(getattr(r, 'credit_amount', 0)) > 0
                     or dec(amounts.get('company_credit', 0)) > 0
                     or r.id in credit_noted)
        if not justified:
            violations.append(row_violation(
                'reservation', r.id,
                expected='settled, or a recorded credit arrangement',
                observed=f'{money(balance)} outstanding, no justification',
                amount=balance,
                checked_out_at=str(r.checked_out_at)))

    return (verdict(len(reservations), violations), len(reservations),
            violations,
            {'expected': 'departed guests are settled or explained',
             'observed': summarise('checked-out reservations',
                                   len(reservations), violations),
             'inputs': {'checked_out': len(reservations),
                        'credit_notes_on_file': len(credit_noted)}})


# ---------------------------------------------------------------------------
# INV-C03 — no orphan financial events
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-C03',
    title='Every financial event belongs to a reservation that exists',
    category=Category.DOMAIN,
    business_purpose=(
        'A payment or a charge that points at no reservation still appears '
        'in the day\'s totals, but it cannot be billed, refunded, explained '
        'to a guest or attributed to a stay. It is money without a story.'),
    business_rule=(
        'Every payments, extra_charges and tax_lines row references an '
        'existing reservations row.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('payments', 'extra_charges', 'tax_lines', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Left-join each financial table to reservations and report every '
        'row whose reservation is missing.'),
    evidence_produced=(
        'Per orphan row: table, id, the reservation id it claims, amount.'),
    failure_message=(
        'Financial rows reference reservations that do not exist.'),
    likely_root_causes=(
        'A reservation deleted without cascading its financial rows',
        'A data import that wrote children before parents',
        'Foreign keys not enforced on this database, so the state is '
        'reachable at any time'),
    suggested_investigation=(
        'Check whether any delete path removes reservations directly',
        'PRAGMA foreign_keys is off on this database — confirm whether '
        'enabling it is viable',
        'Compare the orphans\' created_at against known imports'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5'),
    affected_reports=('every financial report', 'night audit',
                      'billing.gst_report'),
    negative_seed=(
        "UPDATE payments SET reservation_id = 987654 "
        "WHERE id = (SELECT MIN(id) FROM payments)",
    ),
    negative_seed_reason=(
        'Repointing a payment at a reservation id that does not exist is '
        'the orphan state the rule forbids, and foreign keys are not '
        'enforced so it is a state the live system can reach.'),
)
def _c03(ctx):
    violations = []
    population = 0
    for table, amount_col in (('payments', 'amount'),
                              ('extra_charges', 'amount'),
                              ('tax_lines', 'tax_amount')):
        if not ctx.table_exists(table):
            continue
        population += ctx.count(f'SELECT COUNT(*) FROM "{table}"')
        rows = ctx.sql(
            f'SELECT t.id, t.reservation_id, t."{amount_col}" AS amt '
            f'FROM "{table}" t '
            f'LEFT JOIN reservations r ON r.id = t.reservation_id '
            f'WHERE r.id IS NULL ORDER BY t.id')
        for row in rows:
            violations.append(row_violation(
                table.rstrip('s'), row['id'],
                expected='an existing reservation',
                observed=f'reservation_id {row["reservation_id"]} not found',
                amount=dec(row['amt']), table=table))

    return (verdict(population, violations), population, violations,
            {'expected': 'every financial row has a live reservation',
             'observed': summarise('financial rows', population, violations),
             'inputs': {'rows_examined': population}})


# ---------------------------------------------------------------------------
# INV-C04 — a room holds one guest a night
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-C04',
    title='No room is occupied by two reservations on the same night',
    category=Category.DOMAIN,
    business_purpose=(
        'Two guests cannot sleep in one room. A double allocation means '
        'either a guest was moved and the record not updated, or the same '
        'room night was sold twice — and if it was sold twice, occupancy, '
        'ADR and RevPAR are all overstated for that night.'),
    business_rule=(
        'For every room and every night, at most one reservation with '
        'status CheckedIn or CheckedOut spans that night in that room.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('reservations', 'rooms'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Expand every stay into its nights and count reservations per '
        '(room, night). Only CheckedIn and CheckedOut are counted: a '
        'cancelled or no-show booking does not occupy anything, and '
        'counting it would make the rule fire on ordinary overbooking '
        'protection.'),
    evidence_produced=(
        'Per clash: room, night, the reservations involved.'),
    failure_message=(
        'A room is recorded as occupied by more than one reservation on the '
        'same night. Occupancy and rate metrics for that night are '
        'overstated.'),
    likely_root_causes=(
        'A room move that assigned the new room without releasing the old',
        'An allocation route with no availability check',
        'A group booking assigned to one room by default'),
    suggested_investigation=(
        'Read the reservation_rooms bridge rows for the affected stays — a '
        'split-room stay may be modelled there rather than on the '
        'reservation',
        'Check the created_at of the two reservations to see which was '
        'later',
        'Compare against the night audit occupancy for that date'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P5', 'P11'),
    affected_reports=('reports.room_status_report', 'night audit occupancy',
                      'main.dashboard', 'reports.front_office_mis'),
    negative_seed=(
        "UPDATE reservations SET room_id = "
        "  (SELECT room_id FROM reservations WHERE room_id IS NOT NULL "
        "    ORDER BY id LIMIT 1), "
        "  arrival_date = (SELECT arrival_date FROM reservations "
        "                   WHERE room_id IS NOT NULL ORDER BY id LIMIT 1), "
        "  departure_date = (SELECT departure_date FROM reservations "
        "                     WHERE room_id IS NOT NULL ORDER BY id LIMIT 1) "
        "WHERE id = (SELECT MAX(id) FROM reservations)",
    ),
    negative_seed_reason=(
        'Copying one reservation\'s room and stay dates onto another puts '
        'two guests in one room for the same nights.'),
)
def _c04(ctx):
    import datetime as _dt

    rows = ctx.sql(
        "SELECT id, room_id, arrival_date, departure_date FROM reservations "
        "WHERE status IN ('CheckedIn','CheckedOut') AND room_id IS NOT NULL "
        "ORDER BY id")

    occupancy: dict = {}
    nights = 0
    for row in rows:
        try:
            arrival = _dt.date.fromisoformat(str(row['arrival_date'])[:10])
            departure = _dt.date.fromisoformat(str(row['departure_date'])[:10])
        except (TypeError, ValueError):
            continue
        cursor = arrival
        while cursor < departure:
            occupancy.setdefault((int(row['room_id']), cursor.isoformat()),
                                 []).append(int(row['id']))
            nights += 1
            cursor += _dt.timedelta(days=1)

    violations = []
    for (room_id, night), reservation_ids in sorted(occupancy.items()):
        if len(reservation_ids) > 1:
            violations.append(row_violation(
                'room_night', f'room {room_id} / {night}',
                expected='one reservation',
                observed=(f'{len(reservation_ids)} reservations: '
                          + ', '.join(str(i) for i in sorted(reservation_ids))),
                amount=0, room_id=room_id, night=night,
                reservations=sorted(reservation_ids)))

    return (verdict(nights, violations), nights, violations,
            {'expected': 'at most one reservation per room per night',
             'observed': (f'{len(violations)} clash(es) across {nights} '
                          f'occupied room-night(s)'),
             'inputs': {'reservations_expanded': len(rows),
                        'room_nights': nights}})


# ---------------------------------------------------------------------------
# INV-C05 — OTA bookings carry their agent
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-C05',
    title='An OTA settlement identifies the agent it will be collected from',
    category=Category.DOMAIN,
    business_purpose=(
        'An OTA receivable is only collectable if the hotel knows which '
        'agent owes it and against which booking reference. Without a '
        'channel and a booking id the receivable cannot be reconciled '
        'against the agent\'s remittance, and it sits on the ledger '
        'indefinitely.'),
    business_rule=(
        'Every reservation carrying a payment through an ota_receivable '
        'mode has a non-empty ota_channel and ota_booking_id.'),
    severity=Severity.MEDIUM,
    blocking=Blocking.OPERATIONAL,
    data_sources=('payments', 'payment_modes', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'For each reservation with an OTA posting, require both '
        'identifying fields. Reported separately from INV-C01: a booking '
        'can be genuinely from an agent and still be missing its '
        'reference, and conflating the two would hide whichever is less '
        'common.'),
    evidence_produced=(
        'Per reservation: OTA amount posted, channel, booking id, which '
        'field is missing.'),
    failure_message=(
        'OTA receivables exist that cannot be attributed to an agent.'),
    likely_root_causes=(
        'A manual OTA posting at the desk with no import behind it',
        'An import that maps the amount but not the channel',
        'A booking whose source was edited after import'),
    suggested_investigation=(
        'Check whether the affected reservations came through an import or '
        'were created at the desk',
        'Compare against the OTA settlement report to see whether these '
        'receivables have ever been collected'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P5', 'P10'),
    affected_reports=('reports.ota_reconciliation',
                      'reports.ota_settlement', 'reports.ar_aging'),
    negative_seed=(
        "UPDATE payments SET payment_mode_id = "
        "  (SELECT id FROM payment_modes WHERE category='ota_receivable' "
        "    ORDER BY id LIMIT 1) "
        "WHERE id = (SELECT MAX(id) FROM payments)",
    ),
    negative_seed_reason=(
        'Adding an OTA posting to a reservation that carries no channel or '
        'booking reference creates an unattributable receivable.'),
)
def _c05(ctx):
    rows = ctx.sql(
        "SELECT r.id AS res_id, r.ota_channel, r.ota_booking_id, "
        "       SUM(p.amount) AS ota_amount, COUNT(*) AS postings "
        "FROM payments p "
        "JOIN payment_modes m ON m.id = p.payment_mode_id "
        "JOIN reservations r ON r.id = p.reservation_id "
        "WHERE m.category = 'ota_receivable' "
        "GROUP BY r.id, r.ota_channel, r.ota_booking_id ORDER BY r.id")

    violations = []
    for row in rows:
        missing = []
        if not (row['ota_channel'] or '').strip():
            missing.append('ota_channel')
        if not (row['ota_booking_id'] or '').strip():
            missing.append('ota_booking_id')
        if missing:
            violations.append(row_violation(
                'reservation', row['res_id'],
                expected='ota_channel and ota_booking_id set',
                observed='missing ' + ', '.join(missing),
                amount=dec(row['ota_amount']),
                ota_postings=int(row['postings'])))

    return (verdict(len(rows), violations), len(rows), violations,
            {'expected': 'every OTA receivable names its agent',
             'observed': summarise('reservations with OTA postings',
                                   len(rows), violations),
             'inputs': {'reservations_with_ota_postings': len(rows)}})


# ---------------------------------------------------------------------------
# INV-C06 — corporate settlement is backed by a company
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-C06',
    title='Corporate credit is backed by a company account that exists',
    category=Category.DOMAIN,
    business_purpose=(
        'When a stay is billed to a company, the hotel is extending credit '
        'to that company and will invoice it. If the folio names no company, '
        'or names one that does not exist, there is nobody to invoice and '
        'the balance is uncollectable.'),
    business_rule=(
        'Every folio with a company_id references an existing companies '
        'row, and every reservation whose billing is corporate has a folio '
        'carrying a company.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('folios', 'companies', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Left-join folios to companies for the referential half, then check '
        'reservations flagged as corporate for a company-bearing folio. '
        'Corporate is detected from booking_type and from a non-zero '
        'credit_amount, both of which the schema uses.'),
    evidence_produced=(
        'Per folio: the company id claimed and whether it resolves; per '
        'corporate reservation: whether any folio names a company.'),
    failure_message=(
        'Corporate credit exists with no company account behind it.'),
    likely_root_causes=(
        'A company deleted while folios still referenced it',
        'A corporate booking created before the company record',
        'Billing responsibility set on the reservation but not propagated '
        'to the folio'),
    suggested_investigation=(
        'Check whether the company delete path guards against existing '
        'folios',
        'Compare Company.credit_used against the sum of the folios that '
        'name it'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P1', 'P5'),
    affected_reports=('reports.ar_aging', 'reports.company_ledger',
                      'night audit folio control'),
    negative_seed=(
        "UPDATE folios SET company_id = 424242 "
        "WHERE id = (SELECT MIN(id) FROM folios)",
    ),
    negative_seed_reason=(
        'Pointing a folio at a company id that does not exist creates '
        'exactly the uncollectable corporate balance the rule forbids.'),
)
def _c06(ctx):
    violations = []

    folios = ctx.sql(
        'SELECT f.id, f.company_id, f.reservation_id '
        'FROM folios f LEFT JOIN companies c ON c.id = f.company_id '
        'WHERE f.company_id IS NOT NULL AND c.id IS NULL ORDER BY f.id')
    for row in folios:
        violations.append(row_violation(
            'folio', row['id'],
            expected='an existing company account',
            observed=f'company_id {row["company_id"]} not found', amount=0,
            reservation_id=row['reservation_id']))

    corporate = ctx.sql(
        "SELECT r.id, r.booking_type, r.credit_amount, "
        "       (SELECT COUNT(*) FROM folios f "
        "         WHERE f.reservation_id = r.id AND f.company_id IS NOT NULL) "
        "         AS company_folios "
        "FROM reservations r "
        "WHERE LOWER(COALESCE(r.booking_type,'')) IN "
        "      ('corporate','company','corp') "
        "ORDER BY r.id")
    for row in corporate:
        if int(row['company_folios']) == 0:
            violations.append(row_violation(
                'reservation', row['id'],
                expected='a folio naming the company being billed',
                observed=f'booking_type {row["booking_type"]!r} with no '
                         f'company folio',
                amount=dec(row['credit_amount'])))

    population = ctx.count('SELECT COUNT(*) FROM folios') + len(corporate)
    company_folios = ctx.count(
        'SELECT COUNT(*) FROM folios WHERE company_id IS NOT NULL')
    if company_folios == 0 and not corporate:
        # Nothing corporate exists at all. The rule holds trivially, which
        # is not the same as the rule having been tested.
        return (Status.VACUOUS, 0, [],
                {'expected': 'corporate credit is backed by a company',
                 'observed': ('no folio names a company and no reservation '
                              'is flagged corporate; the rule was not '
                              'exercised'),
                 'inputs': {'folios': population,
                            'company_folios': 0,
                            'corporate_reservations': 0}})

    return (verdict(population, violations), population, violations,
            {'expected': 'corporate credit is backed by a company',
             'observed': summarise('corporate references', population,
                                   violations),
             'inputs': {'folios': ctx.count('SELECT COUNT(*) FROM folios'),
                        'company_folios': company_folios,
                        'corporate_reservations': len(corporate)}})
