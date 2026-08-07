"""
Class A — Business faults.

Things a hotel can genuinely do wrong. Every fault here is legal SQL and
plausible data: a front-desk clerk picking the wrong settlement head, a
room moved without releasing the old one, a guest allowed to leave with a
balance nobody recorded a reason for.

They are the most important class, because they are the ones that happen.
A framework that catches a corrupted foreign key but not a walk-in
settled to an OTA is protecting the database rather than the business.
"""
from __future__ import annotations

from verification.faults.model import (
    Category, Commissioning, Layer, Method, Mode, Severity, TargetLayer,
)
from verification.faults.registry import fault

MODES = (Mode.SINGLE_FAULT, Mode.BATCH, Mode.COMMISSIONING,
         Mode.RELEASE_VERIFICATION, Mode.CONTINUOUS_VERIFICATION)

REPEATABLE = ('Deterministic SQL against a private copy of a fixed '
              'baseline. Re-running produces the same rows and the same '
              'detection.')
DETERMINISTIC = ('No clock, no randomness, no ordering dependence: every '
                 'statement is bounded by an explicit MIN/MAX subquery.')
CLEANUP = ('The private copy is deleted and its absence verified; the '
           'pristine baseline and production are SHA-256 re-verified '
           'after every injection.')


@fault(
    fault_id='FLT-A01',
    title='Walk-in reservation settled through an OTA receivable head',
    category=Category.BUSINESS,
    purpose=(
        'The commonest revenue-recognition error a front desk can make. '
        'An OTA head says a travel agent owes the money; for a guest who '
        'walked in there is no agent, so the cash is either in the drawer '
        'and missing from the cash figure, or it was never taken.'),
    business_rule_challenged=(
        'No payment through an ota_receivable mode belongs to a walk-in '
        'reservation.'),
    injection_method=Method.SQL,
    target_objects=('payments', 'payment_modes', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-C01', 'INV-C05'),
    expected_quantities=('P10',),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The day ledger moves money from the direct bucket to the OTA '
        'bucket; the engine follows, so the reconciliations hold and the '
        'movement shows as a changed ledger rather than a broken rule.'),
    expected_parity_behaviour=(
        'P10 (payments by mode and purpose) changes composition while the '
        'gross total is unchanged — the signature of a misclassification '
        'rather than a loss.'),
    expected_certification_impact=(
        'Certification-blocking: revenue is recognised against a '
        'counterparty that does not exist.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-C01 names the payment, the reservation, its source and the '
        'OTA head, and totals the exposure.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with a direct payment',
    payload=(
        "UPDATE payments SET payment_mode_id = "
        "  (SELECT id FROM payment_modes WHERE category='ota_receivable' "
        "    ORDER BY id LIMIT 1) "
        "WHERE id = (SELECT MIN(p.id) FROM payments p "
        "            JOIN payment_modes m ON m.id = p.payment_mode_id "
        "            WHERE m.category = 'direct_payment')",
    ),
    affected_reports=('reports.ota_reconciliation', 'reports.flash'),
    root_cause_candidates=(
        'The desk UI offers every payment mode regardless of booking source',
        'A booking imported from an OTA whose source was overwritten',
        'Training: OTA heads used as a catch-all for card settlements'),
    principles=('P5', 'P11', 'P14'),
    modes=MODES,
)
def _a01():
    pass


@fault(
    fault_id='FLT-A02',
    title='Corporate booking with no company account behind it',
    category=Category.BUSINESS,
    purpose=(
        'A stay billed to a company is credit extended to that company. '
        'If no company is named on any folio there is nobody to invoice, '
        'and the balance is uncollectable from the moment it is created.'),
    business_rule_challenged=(
        'Every reservation billed corporate has a folio carrying an '
        'existing company.'),
    injection_method=Method.SQL,
    target_objects=('reservations', 'folios', 'companies'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-C06',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected. Booking type carries no money of its own, so no '
        'ledger figure moves — which is precisely why an invariant is '
        'needed for it.'),
    expected_parity_behaviour=(
        'None expected. No parity quantity reads booking_type.'),
    expected_certification_impact=(
        'Certification-blocking: an uncollectable receivable is carried '
        'as an asset.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-C06 names the reservation, its booking type, and the absence '
        'of a company-bearing folio.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE reservations SET booking_type = 'Corporate' "
        "WHERE id = (SELECT MIN(id) FROM reservations)",
    ),
    affected_reports=('reports.ar_aging', 'reports.company_ledger'),
    root_cause_candidates=(
        'Billing responsibility set on the reservation but never '
        'propagated to a folio',
        'The company record was created after the booking and never linked',
        'A company deleted while its folios survived'),
    principles=('P1', 'P5', 'P14'),
    modes=MODES,
)
def _a02():
    pass


@fault(
    fault_id='FLT-A03',
    title='Duplicate payment posted for the same settlement',
    category=Category.BUSINESS,
    purpose=(
        'A double-submitted card settlement or a re-keyed cash receipt. '
        'The day banks more than it took, the guest appears overpaid, and '
        'nothing in the record says the two rows are the same event.'),
    business_rule_challenged=(
        'A settlement is recorded once. There is currently no invariant '
        'that says so, and this fault exists to establish whether the '
        'framework can see it anyway.'),
    injection_method=Method.SQL,
    target_objects=('payments',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D3_REPLAY, Layer.D1_PARITY,
                        Layer.D4_INVARIANTS),
    #: INV-A06 fires because the duplicate drives the guest overpaid with
    #: no overpayment record. That is detection by consequence, not by
    #: cause, and the completion report says so.
    expected_invariants=('INV-A06',),
    expected_quantities=('P09', 'P10'),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The day ledger and the engine both rise by the duplicated '
        'amount, so every reconciliation still holds. The day simply '
        'reports more money than it took — detectable as movement, not as '
        'a broken rule.'),
    expected_parity_behaviour=(
        'P09 and P10 both rise. No parity quantity can distinguish a '
        'duplicate from a genuine second payment.'),
    expected_certification_impact=(
        'Certification-blocking: the cash figure is overstated and the '
        'guest is owed a refund nobody has recorded.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-A06 names the reservation and the amount overpaid. No layer '
        'names the duplication itself.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with a payment',
    payload=(
        "INSERT INTO payments "
        "(reservation_id, folio_id, payment_mode_id, amount, payment_date, "
        " created_at, reference_number, is_voided, is_correction, "
        " is_reversal, payment_purpose) "
        "SELECT p.reservation_id, p.folio_id, p.payment_mode_id, p.amount, "
        "  p.payment_date, p.created_at, p.reference_number, 0, 0, 0, "
        "  p.payment_purpose FROM payments p ORDER BY p.id LIMIT 1",
    ),
    affected_reports=('reports.flash', 'main.dashboard',
                      'reports.payment_collection'),
    root_cause_candidates=(
        'A double-submitted form with no idempotency key',
        'A card terminal retried after a timeout',
        'Manual re-keying of a receipt already entered'),
    principles=('P1', 'P5', 'P11'),
    modes=MODES,
)
def _a03():
    pass


@fault(
    fault_id='FLT-A04',
    title='A sold room night has no priced rate row',
    category=Category.BUSINESS,
    purpose=(
        'The nightly rate rows are what room revenue is earned from. A '
        'night the guest stayed with no priced row is revenue the hotel '
        'never records, and there is no screen on which its absence '
        'shows.'),
    business_rule_challenged=(
        'Every night of a stay carries a priced nightly rate row. No '
        'invariant currently asserts this; the fault establishes whether '
        'anything notices.'),
    injection_method=Method.SQL,
    target_objects=('reservation_night_rates', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D3_REPLAY,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The ledger night_rates total falls. Nothing else moves, because '
        'the accrual engines read the reservation tariff rather than the '
        'nightly rows — which is itself the finding.'),
    expected_parity_behaviour=(
        'None declared. P03 reads get_room_revenue, which falls back to '
        'the flat tariff when nightly rows are absent, so the loss is '
        'invisible to it.'),
    expected_certification_impact=(
        'Certification-blocking if confirmed: room revenue would be '
        'understated with no audit trail.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'The D3 ledger shows night_rates.rows and night_rates.final '
        'falling for the affected date.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with a priced room night',
    payload=(
        "DELETE FROM reservation_night_rates "
        "WHERE id = (SELECT MIN(id) FROM reservation_night_rates)",
    ),
    affected_reports=('reports.revenue', 'night audit revenue summary'),
    root_cause_candidates=(
        'A stay extended without regenerating nightly rows',
        'A failed pricing run that partially committed',
        'A manual delete during a rate correction'),
    principles=('P1', 'P10', 'P14'),
    modes=MODES,
)
def _a04():
    pass


@fault(
    fault_id='FLT-A05',
    title='GST applied at the wrong rate',
    category=Category.BUSINESS,
    purpose=(
        'A tax line whose rate no longer matches the amount it carries. '
        'The return is filed from the stored lines, so an unnoticed rate '
        'error is filed too.'),
    business_rule_challenged=(
        'Every stored tax line equals its own taxable base times its own '
        'rate.'),
    injection_method=Method.SQL,
    target_objects=('tax_lines',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-A05',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected: the rate column moves, the amount does not, so no '
        'ledger total changes. A fault that money-based checks cannot '
        'see.'),
    expected_parity_behaviour=(
        'None expected. P07 totals tax by component, which the rate '
        'change leaves alone.'),
    expected_certification_impact=(
        'Certification-blocking: a GST return would be filed from a line '
        'that does not follow from its own base.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-A05 names the line, its base, its rate, the stored amount '
        'and the recomputed amount.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with tax lines',
    payload=(
        "UPDATE tax_lines SET tax_rate = tax_rate + 6.0 "
        "WHERE id = (SELECT MIN(id) FROM tax_lines)",
    ),
    affected_reports=('billing.gst_report', 'billing.gstr_export',
                      'main.invoice'),
    root_cause_candidates=(
        'A rate change applied to the rate column without recomputing',
        'A slab reclassification applied retrospectively',
        'Manual correction of one column only'),
    principles=('P1', 'P11'),
    modes=MODES,
)
def _a05():
    pass


@fault(
    fault_id='FLT-A06',
    title='Payment posted through a settlement head that does not exist',
    category=Category.BUSINESS,
    purpose=(
        'The known hole D3 found and D4 confirmed. The night audit treats '
        'a missing payment mode as direct cash; kpi_helpers drops the row '
        'entirely. The same rupees appear on one report and not the '
        'other, and no schema constraint prevents it.'),
    business_rule_challenged=(
        'Every payment references an existing payment mode whose category '
        'the system understands.'),
    injection_method=Method.SQL,
    target_objects=('payments', 'payment_modes'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-D03', 'INV-A04'),
    expected_quantities=('P10',),
    expected_reconciliations=('RC11',),
    expected_replay_behaviour=(
        'RC11 breaks: the night audit counts the orphan as direct cash '
        'while the ledger counts it as neither, so the two part company '
        'by exactly the orphan amount.'),
    expected_parity_behaviour=(
        'P10 loses the row from its by-mode breakdown.'),
    expected_certification_impact=(
        'Release-blocking: two canonical engines disagree about the same '
        'money.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-D03 names the payment and the missing mode id; INV-A04 names '
        'the date and the unclassified amount; RC11 gives the delta.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with a direct payment',
    payload=(
        "UPDATE payments SET payment_mode_id = 999999 "
        "WHERE id = (SELECT MIN(p.id) FROM payments p "
        "            JOIN payment_modes m ON m.id = p.payment_mode_id "
        "            WHERE p.is_voided = 0 AND m.category='direct_payment')",
    ),
    affected_reports=('reports.flash', 'main.dashboard',
                      'night audit payment summary'),
    root_cause_candidates=(
        'A payment mode deleted rather than deactivated',
        'Foreign keys are not enforced on this database',
        'A data import referencing a mode that was never created'),
    principles=('P1', 'P3', 'P5', 'P14'),
    modes=MODES,
)
def _a06():
    pass


@fault(
    fault_id='FLT-A07',
    title='Guest overpaid with no overpayment record',
    category=Category.BUSINESS,
    purpose=(
        'Money held above what a guest owes is a liability. Until it is '
        'recorded it looks like income, inflates the day, and nobody '
        'knows to refund it.'),
    business_rule_challenged=(
        'Every reservation whose settlement balance is negative has an '
        'overpayment record.'),
    injection_method=Method.SQL,
    target_objects=('payments', 'overpayment_logs', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-A06',),
    expected_quantities=('P09', 'P12'),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The day ledger and the engine both rise by the overpayment, so '
        'reconciliations hold; the day reports more cash than it owed.'),
    expected_parity_behaviour=(
        'P09 rises and P12 (outstanding per reservation) goes negative.'),
    expected_certification_impact=(
        'Certification-blocking: an unrecorded liability.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-A06 names the reservation and the amount overpaid.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with a payment',
    payload=(
        "INSERT INTO payments "
        "(reservation_id, folio_id, payment_mode_id, amount, payment_date, "
        " created_at, is_voided, is_correction, is_reversal, payment_purpose) "
        "SELECT p.reservation_id, p.folio_id, p.payment_mode_id, 40000.00, "
        "  p.payment_date, p.created_at, 0, 0, 0, 'settlement' "
        "FROM payments p ORDER BY p.id LIMIT 1",
    ),
    affected_reports=('reports.refund_report', 'main.reservation_folio'),
    root_cause_candidates=(
        'Overpayment detected only at checkout, and this arrived after',
        'A payment posted against the wrong reservation',
        'A refund reversed without reversing the original'),
    principles=('P1', 'P5', 'P10'),
    modes=MODES,
)
def _a07():
    pass


@fault(
    fault_id='FLT-A08',
    title='Room move recorded without releasing the old room',
    category=Category.BUSINESS,
    purpose=(
        'Two guests recorded in one room on one night. Either a move was '
        'half-recorded, or the night was sold twice — and if it was sold '
        'twice, occupancy, ADR and RevPAR are all overstated.'),
    business_rule_challenged=(
        'At most one reservation occupies a room on a night.'),
    injection_method=Method.SQL,
    target_objects=('reservations', 'rooms'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-C04',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The ledger occupancy count for the affected night changes; the '
        'engine follows.'),
    expected_parity_behaviour=(
        'None declared. P19 counts distinct rooms, which a double '
        'allocation leaves unchanged — the reason an invariant is needed.'),
    expected_certification_impact=(
        'Certification-blocking: occupancy and rate metrics overstated.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-C04 names the room, the night and both reservations.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any night with an occupied room',
    payload=(
        "UPDATE reservations SET room_id = "
        "  (SELECT room_id FROM reservations WHERE room_id IS NOT NULL "
        "    ORDER BY id LIMIT 1), "
        "  arrival_date = (SELECT arrival_date FROM reservations "
        "                   WHERE room_id IS NOT NULL ORDER BY id LIMIT 1), "
        "  departure_date = (SELECT departure_date FROM reservations "
        "                     WHERE room_id IS NOT NULL ORDER BY id LIMIT 1) "
        "WHERE id = (SELECT MAX(id) FROM reservations)",
    ),
    affected_reports=('reports.room_status_report', 'main.dashboard',
                      'night audit occupancy'),
    root_cause_candidates=(
        'A room move that assigned the new room without releasing the old',
        'An allocation route with no availability check',
        'A group booking defaulted to one room'),
    principles=('P5', 'P11'),
    modes=MODES,
)
def _a08():
    pass


@fault(
    fault_id='FLT-A09',
    title='Guest checked out with an unexplained balance',
    category=Category.BUSINESS,
    purpose=(
        'Letting a guest leave owing money is a decision — credit, a '
        'company account, a write-off — and it must leave a trace. An '
        'unexplained balance on a departed guest is money the hotel has '
        'stopped being able to collect and has not decided to lose.'),
    business_rule_challenged=(
        'A checked-out reservation is settled, or carries a recorded '
        'credit arrangement.'),
    injection_method=Method.SQL,
    target_objects=('extra_charges', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-C02',),
    expected_quantities=('P02', 'P12'),
    expected_reconciliations=('RC07',),
    expected_replay_behaviour=(
        'The charge lands on a date inside the replay window, so the '
        'ledger extras total and the accrual engine both move together.'),
    expected_parity_behaviour=(
        'P02 (charge census) and P12 (outstanding) both move.'),
    expected_certification_impact=(
        'Certification-blocking: an unrecoverable receivable with no '
        'authorisation behind it.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-C02 names the reservation, its checkout time and the '
        'outstanding amount.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any date with a checked-out reservation',
    payload=(
        "INSERT INTO extra_charges "
        "(reservation_id, folio_id, description, amount, charge_date, "
        " created_at, charge_type, charge_category, is_correction, "
        " is_reversal) "
        "SELECT id, NULL, 'FIP unpaid charge', 6500.00, departure_date, "
        "  checked_out_at, 'food', 'Restaurant', 0, 0 "
        "FROM reservations WHERE status = 'CheckedOut' "
        "  AND COALESCE(credit_amount, 0) = 0 ORDER BY id LIMIT 1",
    ),
    affected_reports=('reports.ar_aging', 'main.reservation_folio'),
    root_cause_candidates=(
        'A checkout route that warns about a balance but does not block',
        'Charges posted after the guest departed',
        'A credit arrangement agreed verbally and never recorded'),
    principles=('P5', 'P11'),
    modes=MODES,
)
def _a09():
    pass


@fault(
    fault_id='FLT-A10',
    title='Duplicate reservation for the same stay',
    category=Category.BUSINESS,
    purpose=(
        'The same booking entered twice. Occupancy and forecast are '
        'overstated, the room is blocked against itself, and if only one '
        'is settled the other becomes a phantom receivable.'),
    business_rule_challenged=(
        'A booking reference identifies one reservation. No invariant '
        'currently asserts this; the fault establishes what notices.'),
    injection_method=Method.SQL,
    target_objects=('reservations',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D1_PARITY),
    #: Detected by consequence: the duplicate occupies the same room on
    #: the same nights, so the room-night clash invariant fires. Nothing
    #: names the duplication itself.
    expected_invariants=('INV-C04',),
    expected_quantities=('P01',),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'Occupancy and accrual room revenue rise for the duplicated '
        'nights; the ledger and the engine move together.'),
    expected_parity_behaviour='P01 (reservation census) rises by one.',
    expected_certification_impact=(
        'Certification-blocking: occupancy and accrual revenue overstated.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-C04 names the room night and both reservation ids. The '
        'duplicated booking reference itself goes unreported.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    #: The column list carries the five NOT NULL money columns
    #: (``credit_*`` and ``cancellation_*``) as well as the descriptive
    #: ones. They have no default, so omitting them raises IntegrityError
    #: and the fault is never injected at all — which is exactly what
    #: commissioning caught the first time this declaration was run.
    payload=(
        "INSERT INTO reservations "
        "(booking_reference, guest_id, room_id, room_type_id, arrival_date, "
        " departure_date, adults, children, status, rate_per_night, "
        " advance_payment, source, booking_type, created_at, "
        " noshow_exempt, tariff_modified_manually, checkout_initiated, "
        " credit_amount, credit_settled_amount, "
        " cancellation_amount_refunded, cancellation_amount_forfeited, "
        " cancellation_amount_credit_voucher) "
        "SELECT booking_reference, guest_id, room_id, room_type_id, "
        "  arrival_date, departure_date, adults, children, status, "
        "  rate_per_night, advance_payment, source, booking_type, "
        "  created_at, noshow_exempt, tariff_modified_manually, "
        "  checkout_initiated, credit_amount, credit_settled_amount, "
        "  cancellation_amount_refunded, cancellation_amount_forfeited, "
        "  cancellation_amount_credit_voucher "
        "FROM reservations ORDER BY id LIMIT 1",
    ),
    affected_reports=('reports.room_status_report', 'reports.revenue',
                      'main.dashboard'),
    root_cause_candidates=(
        'A double-submitted booking form with no uniqueness constraint',
        'An OTA import run twice',
        'A manual re-entry after a perceived failure'),
    principles=('P1', 'P5', 'P11'),
    modes=MODES,
)
def _a10():
    pass
