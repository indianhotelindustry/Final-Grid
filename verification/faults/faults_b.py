"""
Class B — Data faults.

The record itself is malformed. A dangling reference, a missing row, a
date outside the period it claims. These are the faults a schema is
supposed to prevent and this one does not: ``PRAGMA foreign_keys`` is 0
on this database, so every referential constraint it declares is
advisory.

They are cheap to inject and unglamorous to read, and they decide whether
anything else can be trusted. A reconciliation performed over rows whose
parents have vanished is arithmetic on rubble.
"""
from __future__ import annotations

from verification.faults.model import (
    Category, Commissioning, Layer, Method, Mode, Severity, TargetLayer,
)
from verification.faults.registry import fault

MODES = (Mode.SINGLE_FAULT, Mode.BATCH, Mode.COMMISSIONING,
         Mode.RELEASE_VERIFICATION, Mode.CONTINUOUS_VERIFICATION)

REPEATABLE = ('Deterministic SQL against a private copy of a fixed '
              'baseline; the same rows every time.')
DETERMINISTIC = ('Bounded by explicit MIN/MAX subqueries — no ordering '
                 'dependence, no clock, no randomness.')
CLEANUP = ('The private copy is deleted and its absence verified; the '
           'baseline and production are SHA-256 re-verified after every '
           'injection.')


@fault(
    fault_id='FLT-B01',
    title='Payment referencing a reservation that does not exist',
    category=Category.DATA,
    purpose=(
        'Money without a story. The payment still appears in the day\'s '
        'totals but cannot be billed, refunded, explained to a guest or '
        'attributed to a stay.'),
    business_rule_challenged=(
        'Every financial event belongs to a reservation that exists.'),
    injection_method=Method.SQL,
    target_objects=('payments', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-C03',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected. The payment keeps its date and amount, so every '
        'date-scoped total is unchanged — the orphaning is invisible to '
        'money-based checks, which is why a referential invariant exists.'),
    expected_parity_behaviour=(
        'None expected: the payment census is unchanged.'),
    expected_certification_impact=(
        'Release-blocking: a financial row with no provenance.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-C03 names the table, the row and the reservation id it '
        'claims.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE payments SET reservation_id = 987654 "
        "WHERE id = (SELECT MIN(id) FROM payments)",
    ),
    affected_reports=('every financial report', 'night audit'),
    root_cause_candidates=(
        'A reservation deleted without cascading its financial rows',
        'Foreign keys not enforced on this database',
        'An import that wrote children before parents'),
    principles=('P1', 'P5', 'P14'),
    modes=MODES,
)
def _b01():
    pass


@fault(
    fault_id='FLT-B02',
    title='Payment posted with no folio',
    category=Category.DATA,
    purpose=(
        'A folio is the unit a bill is issued against. A payment that '
        'belongs to none still moves the hotel\'s money but cannot be '
        'attributed, split or reconciled downstream.'),
    business_rule_challenged=(
        'Every payment and charge carries a folio_id (Financial '
        'Constitution, Article V section 3).'),
    injection_method=Method.SQL,
    target_objects=('payments', 'folios'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-A02',),
    expected_quantities=('Q09', 'Q14'),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The ledger gains the payment; the engine follows. The unrouted '
        'state itself does not move any total, so only the invariant '
        'names it.'),
    expected_parity_behaviour=(
        'Q09 rises and Q14 (folio partition integrity) records another '
        'unrouted row.'),
    expected_certification_impact=(
        'Certification-blocking: unattributable money.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-A02 names the row and totals the unrouted money.'),
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
        "SELECT p.reservation_id, NULL, p.payment_mode_id, 137.00, "
        "  p.payment_date, p.created_at, 0, 0, 0, 'settlement' "
        "FROM payments p ORDER BY p.id LIMIT 1",
    ),
    affected_reports=('main.reservation_folio', 'billing.gst_report'),
    root_cause_candidates=(
        'A posting path that writes a payment before a folio exists',
        'Folio creation conditional on the check-in route',
        'Legacy rows never backfilled'),
    principles=('P1', 'P5', 'P14'),
    modes=MODES,
)
def _b02():
    pass


@fault(
    fault_id='FLT-B03',
    title='A ledger row that a closed day counted has been deleted',
    category=Category.DATA,
    purpose=(
        'The most direct attack on a closed period. A payment the night '
        'audit counted is gone; the day no longer computes what it '
        'reported, and no screen says so.'),
    business_rule_challenged=(
        'Recomputing a closed day reproduces the figures it reported.'),
    injection_method=Method.SQL,
    target_objects=('payments', 'night_audit_logs'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-B03',),
    expected_quantities=('Q09', 'Q15'),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'History drift: the recomputed collected total for the closed '
        'date no longer equals the frozen snapshot.'),
    expected_parity_behaviour=(
        'Q15 (night audit stored vs recomputed) diverges further.'),
    expected_certification_impact=(
        'Release-blocking: a reported period has changed.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B03 names the date and the field, with the frozen and the '
        'recomputed value.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='any closed date',
    payload=(
        "DELETE FROM payments WHERE id = "
        "  (SELECT MIN(p.id) FROM payments p "
        "   JOIN payment_modes m ON m.id = p.payment_mode_id "
        "   WHERE m.category = 'direct_payment' AND p.is_voided = 0 "
        "     AND p.payment_date = (SELECT MIN(audit_date) "
        "                           FROM night_audit_logs))",
    ),
    affected_reports=('night audit', 'reports.daily_reconciliation'),
    root_cause_candidates=(
        'A hard delete where a void was intended',
        'A purge script with too wide a date range',
        'A restore from a backup taken before the payment'),
    principles=('P2', 'P7', 'P12'),
    modes=MODES,
)
def _b03():
    pass


@fault(
    fault_id='FLT-B04',
    title='Two reservations sharing one invoice number',
    category=Category.DATA,
    purpose=(
        'An invoice number is the reference a guest quotes and a tax '
        'authority indexes. Two stays under one number cannot both be '
        'produced on demand, and the GST return has two supplies where it '
        'should have one row each.'),
    business_rule_challenged=(
        'An invoice number identifies one stay. No invariant currently '
        'asserts this; the fault establishes what notices.'),
    injection_method=Method.SQL,
    target_objects=('reservations',),
    target_layer=TargetLayer.DATA,
    expected_detection=(),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None. No figure moves; the invoice number is an identifier, not '
        'an amount.'),
    expected_parity_behaviour='None. No parity quantity reads it.',
    expected_certification_impact=(
        'Would be certification-blocking if detected. It is not detected, '
        'which is the finding.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'None produced by any layer. Registered so the gap is tracked '
        'rather than forgotten.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.UNCOVERED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE reservations SET invoice_number = "
        "  (SELECT invoice_number FROM reservations "
        "    WHERE invoice_number IS NOT NULL ORDER BY id LIMIT 1) "
        "WHERE id = (SELECT MAX(id) FROM reservations "
        "            WHERE invoice_number IS NOT NULL)",
    ),
    affected_reports=('main.invoice', 'billing.gstr_export'),
    root_cause_candidates=(
        'The invoice counter in settings read without a lock',
        'A re-issued invoice reusing the original number',
        'A restore that rolled the counter backwards'),
    principles=('P1', 'P14'),
    modes=MODES,
    uncovered_reason=(
        'No invariant asserts invoice-number uniqueness, and no monetary '
        'total moves, so every layer is silent by construction. Injecting '
        'it would produce a guaranteed MISS that says nothing the '
        'declaration does not already say.'),
    covered_by_deliverable=(
        'D4 — add an invariant asserting invoice_number uniqueness among '
        'finalised invoices. Registered here so the gap is tracked.'),
)
def _b04():
    pass


@fault(
    fault_id='FLT-B05',
    title='Folio referencing a reservation that does not exist',
    category=Category.DATA,
    purpose=(
        'A bill for no stay. It cannot be issued, chased or explained, '
        'but its charges and payments still appear in the hotel\'s '
        'totals.'),
    business_rule_challenged='Every folio references an existing reservation.',
    injection_method=Method.SQL,
    target_objects=('folios', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-D01',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected: no money moves.'),
    expected_parity_behaviour=(
        'None declared. Q14 counts unrouted rows rather than orphan '
        'folios.'),
    expected_certification_impact=(
        'Release-blocking: a financial container with no provenance.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence='INV-D01 names the folio and the id it claims.',
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE folios SET reservation_id = 876543 "
        "WHERE id = (SELECT MIN(id) FROM folios)",
    ),
    affected_reports=('main.reservation_folio', 'reports.ar_aging'),
    root_cause_candidates=(
        'A reservation deleted without cascading its folios',
        'Foreign keys not enforced'),
    principles=('P1', 'P5', 'P14'),
    modes=MODES,
)
def _b05():
    pass


@fault(
    fault_id='FLT-B06',
    title='Tax line pointing at a room night that never happened',
    category=Category.DATA,
    purpose=(
        'A GST line must be traceable to the supply that gave rise to it. '
        'One that is not cannot be defended in an assessment and cannot '
        'be reversed if the underlying charge is cancelled.'),
    business_rule_challenged=(
        'Every tax line resolves to the charge it was raised on.'),
    injection_method=Method.SQL,
    target_objects=('tax_lines', 'reservation_night_rates'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-D04',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected: the amount is unchanged, only its provenance.'),
    expected_parity_behaviour='None expected: Q07 totals are unchanged.',
    expected_certification_impact=(
        'Certification-blocking: an indefensible tax line.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-D04 names the line, the stay date it claims and the tax at '
        'stake.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE tax_lines SET charge_source_id = 'night_1999-01-01' "
        "WHERE id = (SELECT MIN(id) FROM tax_lines "
        "            WHERE charge_source_type = 'room_night')",
    ),
    affected_reports=('billing.gst_report', 'billing.gstr_export'),
    root_cause_candidates=(
        'A tax line written before its charge was committed',
        'A stay date changed without regenerating tax',
        'A new charge source type the tax writer does not handle'),
    principles=('P1', 'P5', 'P14'),
    modes=MODES,
)
def _b06():
    pass


@fault(
    fault_id='FLT-B07',
    title='Money dated beyond the business date',
    category=Category.DATA,
    purpose=(
        'A payment dated into the future is money the hotel has not taken '
        'yet, sitting in a period that has not started. It disappears '
        'from today and reappears on a day nobody is watching.'),
    business_rule_challenged=(
        'No financial row is dated later than the business date.'),
    injection_method=Method.SQL,
    target_objects=('payments', 'business_date'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D1_PARITY),
    expected_invariants=('INV-B04',),
    expected_quantities=('Q09',),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected: the replay window ends at the business date, so a '
        'future-dated row falls outside it entirely — which is exactly '
        'how a figure hides from a historical review.'),
    expected_parity_behaviour='Q09 (payments total) rises.',
    expected_certification_impact=(
        'Release-blocking: the temporal basis is broken.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B04 names the row, its date and the business date.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "INSERT INTO payments "
        "(reservation_id, folio_id, payment_mode_id, amount, payment_date, "
        " created_at, is_voided, is_correction, is_reversal, payment_purpose) "
        "SELECT p.reservation_id, p.folio_id, p.payment_mode_id, 250.00, "
        "  DATE((SELECT \"current_date\" FROM business_date ORDER BY id "
        "        LIMIT 1), '+45 day'), p.created_at, 0, 0, 0, 'settlement' "
        "FROM payments p ORDER BY p.id LIMIT 1",
    ),
    affected_reports=('reports.flash', 'main.dashboard'),
    root_cause_candidates=(
        'A posting route using the wall clock rather than the business '
        'date',
        'A date field defaulted from an uncontrolled input',
        'An advance deposit booked to the stay date rather than today'),
    principles=('P8', 'P11'),
    modes=MODES,
)
def _b07():
    pass


@fault(
    fault_id='FLT-B08',
    title='Priced room night outside the stay it belongs to',
    category=Category.DATA,
    purpose=(
        'Room revenue attributed to a night the guest was not present. '
        'The total is unchanged, so nothing that reads totals will '
        'notice; only the night it lands on is wrong.'),
    business_rule_challenged=(
        'Every priced night satisfies arrival <= stay_date < departure.'),
    injection_method=Method.SQL,
    target_objects=('reservation_night_rates', 'reservations'),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY),
    expected_invariants=('INV-D06',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The ledger night_rates total falls on the original date. The '
        'night moves ninety days out, beyond the replay window, so it '
        'does not reappear anywhere.'),
    expected_parity_behaviour=(
        'None declared: Q04 reads the reservation tariff, not the nightly '
        'rows.'),
    expected_certification_impact=(
        'Release-blocking: revenue attributed to an unsold night.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'INV-D06 names the row, the stay window and the date it claims.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE reservation_night_rates "
        "SET stay_date = DATE(stay_date, '+90 day') "
        "WHERE id = (SELECT MIN(id) FROM reservation_night_rates)",
    ),
    affected_reports=('reports.revenue', 'night audit revenue summary'),
    root_cause_candidates=(
        'A stay shortened or extended without regenerating nightly rows',
        'A date-shift correction applied to the reservation only'),
    principles=('P1', 'P5', 'P8', 'P14'),
    modes=MODES,
)
def _b08():
    pass


@fault(
    fault_id='FLT-B09',
    title='Reversal flagged with no original transaction',
    category=Category.DATA,
    purpose=(
        'A reversal with no original is indistinguishable from a negative '
        'transaction invented from nothing. It is the classic shape of a '
        'concealed adjustment, and the signing logic treats it as real.'),
    business_rule_challenged=(
        'Every correction or reversal references the transaction it '
        'corrects.'),
    injection_method=Method.SQL,
    target_objects=('payments',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-D02',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The night audit signs reversal amounts negative, so the '
        'collected total for the day falls while the ledger, which does '
        'not sign, holds — a genuine divergence between two views.'),
    expected_parity_behaviour=(
        'None declared. Q09 compares signed against raw payments, so it '
        'may move; the declaration stays with the invariant that names '
        'the cause.'),
    expected_certification_impact=(
        'Release-blocking: an unauditable adjustment.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-D02 names the row, the flag set and the missing pointer.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE payments SET is_reversal = 1 "
        "WHERE id = (SELECT MIN(id) FROM payments)",
    ),
    affected_reports=('reports.revenue', 'night audit payment summary'),
    root_cause_candidates=(
        'A correction UI that sets the flag but not the link',
        'The original deleted after the correction was raised',
        'A bulk adjustment written straight to the database'),
    principles=('P1', 'P5', 'P11', 'P14'),
    modes=MODES,
)
def _b09():
    pass


@fault(
    fault_id='FLT-B10',
    title='A second business date row',
    category=Category.DATA,
    purpose=(
        'The business date is the single temporal basis the whole system '
        'agrees on. Two of them means different parts of the system are '
        'trading on different days, and which one answers depends on row '
        'order.'),
    business_rule_challenged='Exactly one business date row exists.',
    injection_method=Method.SQL,
    target_objects=('business_date',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-B04',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected: the replay reads the lowest-id row, which is '
        'unchanged. The ambiguity is invisible until something reads the '
        'other one.'),
    expected_parity_behaviour='None expected for the same reason.',
    expected_certification_impact=(
        'Release-blocking: the temporal basis is ambiguous.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B04 reports the row count and every date present.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "INSERT INTO business_date (\"current_date\", is_locked, updated_at) "
        "SELECT DATE(\"current_date\", '+1 day'), 0, updated_at "
        "FROM business_date ORDER BY id LIMIT 1",
    ),
    affected_reports=('every date-scoped report', 'night audit'),
    root_cause_candidates=(
        'A migration that inserted rather than updated',
        'A reset script run against a live database',
        'A night audit that advanced the date without committing'),
    principles=('P8', 'P11'),
    modes=MODES,
)
def _b10():
    pass
