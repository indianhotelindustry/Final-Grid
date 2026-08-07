"""
Class C — Engine faults.

The data is correct and the code is wrong. These are the faults no data
mutation can express: "this function now double-counts" is not a state
any row can be in.

They are injected at the engine boundary — a wrapper installed on a
canonical callable inside one throwaway probe subprocess. No file under
``app/`` is touched, the wrapper dies with the process, and production
financial logic is never modified. That is the whole point of doing it
this way: Wave 0 forbids changing the code, and a platform that cannot
challenge the code would leave the most dangerous class of regression
completely unexercised.

Each fault names a *specific* canonical engine, because that is what
makes the result interpretable. "Revenue is wrong somewhere" tells you
nothing; "``get_cash_revenue`` doubles and RC01 catches it while P16 does
not" tells you exactly which control you have and which you do not.
"""
from __future__ import annotations

from verification.faults.model import (
    Category, Commissioning, Layer, Method, Mode, Severity, TargetLayer,
)
from verification.faults.registry import fault

MODES = (Mode.SINGLE_FAULT, Mode.BATCH, Mode.COMMISSIONING,
         Mode.RELEASE_VERIFICATION, Mode.INVARIANT_VALIDATION)

REPEATABLE = ('The wrapper is installed deterministically from a declared '
              'spec; the same call sequence produces the same perturbation '
              'every run.')
DETERMINISTIC = ('A pure arithmetic transform of the return value. No '
                 'clock, no randomness, no dependence on call order.')
CLEANUP = ('Nothing to clean: the wrapper exists only inside the probe '
           'subprocess and dies with it. No file under app/ is written, '
           'and the database copy is deleted and verified regardless.')


@fault(
    fault_id='FLT-C01',
    title='Cash revenue engine double-counts every collection',
    category=Category.ENGINE,
    purpose=(
        'The single most consequential engine regression available: the '
        'day\'s cash figure is what the hotel banks against and what the '
        'owner reads first. Doubling it is the shape of a join that '
        'fanned out after a schema change.'),
    business_rule_challenged=(
        'Daily collections equal the direct payments recorded for the day.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.kpi_helpers.get_cash_revenue',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY),
    expected_invariants=('INV-A04',),
    expected_quantities=(),
    expected_reconciliations=('RC01', 'RC02'),
    expected_replay_behaviour=(
        'RC01 and RC02 break on every date with a payment: the engine '
        'reports twice what the primary record holds.'),
    expected_parity_behaviour=(
        'None declared. P16 and P18 reach the helper through the '
        'get_daily_revenue alias, which is bound at import time and so is '
        'not covered by a wrapper on the canonical name — a real limit of '
        'this injection, stated rather than hidden.'),
    expected_certification_impact=(
        'Release-blocking: every cash figure in the system is wrong.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-A04 names the date, the ledger total and the engine total; '
        'RC01 gives the delta per date.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every date with a payment',
    payload=('app.kpi_helpers.get_cash_revenue', '', 'mul', 2.0),
    affected_reports=('reports.flash', 'main.dashboard',
                      'reports.payment_collection'),
    root_cause_candidates=(
        'A join that fans out after a schema change',
        'A UNION that stopped being a UNION ALL, or started being one',
        'A helper called twice and summed'),
    principles=('P1', 'P3'),
    modes=MODES,
)
def _c01():
    pass


@fault(
    fault_id='FLT-C02',
    title='Accrual extras counted twice',
    category=Category.ENGINE,
    purpose=(
        'Accrual revenue drives the P&L view management reads. Doubling '
        'the extras component overstates earned revenue without touching '
        'a single cash figure, so cash reconciliation stays clean.'),
    business_rule_challenged=(
        'Accrual extras equal the non-room-rent charges posted on the '
        'date.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.kpi_helpers.get_accrual_extras',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D3_REPLAY,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=('RC07', 'RC08', 'RC09'),
    expected_replay_behaviour=(
        'RC07 breaks directly; RC08 and RC09 break because they are built '
        'on it. Three reconciliations failing from one cause is the '
        'signature the report should show.'),
    expected_parity_behaviour=(
        'None declared: P05 reads the charge table rather than the '
        'helper.'),
    expected_certification_impact=(
        'Release-blocking: earned revenue overstated.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'RC07, RC08 and RC09 each give the engine value, the ledger '
        'expression and the delta.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every date with a charge',
    payload=('app.kpi_helpers.get_accrual_extras', '', 'mul', 2.0),
    affected_reports=('reports.flash', 'reports.revenue',
                      'night audit revenue summary'),
    root_cause_candidates=(
        'The room_rent exclusion filter dropped or inverted',
        'A charge summed at both folio and reservation level',
        'A correction row counted as an addition'),
    principles=('P1', 'P3'),
    modes=MODES,
)
def _c02():
    pass


@fault(
    fault_id='FLT-C03',
    title='Folio balance drifts by half a rupee',
    category=Category.ENGINE,
    purpose=(
        'A rounding step applied to one side of the settlement identity '
        'and not the other. Small enough that nobody queries it, '
        'systematic enough that it applies to every folio in the hotel.'),
    business_rule_challenged=(
        'balance = grand_total - paid - company_credit.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.services.calculate_stay_amount',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D1_PARITY),
    expected_invariants=('INV-A01',),
    expected_quantities=('P12',),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None declared: the replay reconciliations do not read the '
        'settlement identity.'),
    expected_parity_behaviour=(
        'P12 (outstanding per reservation) moves on every reservation.'),
    expected_certification_impact=(
        'Release-blocking: every guest is told the wrong balance.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-A01 names each reservation with the reported and the '
        'computed balance and the variance.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=('app.services.calculate_stay_amount', 'balance', 'add', 0.5),
    affected_reports=('main.reservation_folio', 'main.invoice',
                      'reports.ar_aging'),
    root_cause_candidates=(
        'A rounding step applied to one side of the identity only',
        'GST added to grand_total after balance was computed',
        'A caller mutating the returned dict'),
    principles=('P1', 'P11'),
    modes=MODES,
)
def _c03():
    pass


@fault(
    fault_id='FLT-C04',
    title='Cash engine ignores the date it is asked about',
    category=Category.ENGINE,
    purpose=(
        'The wrong-temporal-basis regression: a helper that takes a date '
        'and answers about something else. Every historical report then '
        'shows one constant, and it looks entirely plausible.'),
    business_rule_challenged=(
        'A date-parameterised engine answers about the date it was given.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.kpi_helpers.get_cash_revenue',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY),
    expected_invariants=('INV-A04',),
    expected_quantities=(),
    expected_reconciliations=('RC01', 'RC02', 'RC05', 'RC10', 'RC19'),
    expected_replay_behaviour=(
        'Every date returns the same constant, so RC01 breaks on every '
        'date including the ones with no activity — the distinctive '
        'signature of a date-blind engine, and different from RC01 '
        'breaking only where money moved.'),
    expected_parity_behaviour='None declared, for the reason given in FLT-C01.',
    expected_certification_impact=(
        'Release-blocking: every historical cash figure is fiction.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'RC01 failing on dates with zero payment rows is the tell: a '
        'correct engine returns zero there.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every replayed date',
    payload=('app.kpi_helpers.get_cash_revenue', '', 'set', 9999.0),
    affected_reports=('reports.flash', 'main.dashboard',
                      'reports.front_office_mis'),
    root_cause_candidates=(
        'A date argument accepted and never used',
        'A cached value keyed on nothing',
        'A helper refactored to read the business date internally'),
    principles=('P3', 'P8'),
    modes=MODES,
)
def _c04():
    pass


@fault(
    fault_id='FLT-C05',
    title='Night audit occupancy inflated by present-tense leakage',
    category=Category.ENGINE,
    purpose=(
        'The defect class D3 already found in the live system, injected '
        'deliberately so the framework\'s ability to catch it can be '
        'measured rather than assumed: an occupancy figure inside a '
        'date-scoped report that does not describe that date.'),
    business_rule_challenged=(
        'A closed day recomputes the occupancy it reported.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=(
        'app.night_audit_service.NightAuditService.occupancy_position',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-B03',),
    expected_quantities=('P15',),
    expected_reconciliations=('RC16',),
    expected_replay_behaviour=(
        'History drift on occupancy for the closed date, and RC16 breaks '
        'against the ledger\'s span-derived room count.'),
    expected_parity_behaviour=(
        'P15 (night audit stored vs recomputed) diverges on '
        'occupancy_count.'),
    expected_certification_impact=(
        'Release-blocking: a reported period no longer recomputes.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B03 gives the frozen and recomputed occupancy for the date; '
        'RC16 gives the engine and ledger counts.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every closed date',
    payload=('app.night_audit_service.NightAuditService.occupancy_position',
             'occupied', 'add', 5.0),
    affected_reports=('night audit occupancy', 'main.dashboard',
                      'reports.front_office_mis'),
    root_cause_candidates=(
        'Room.status read inside a date-scoped section',
        'A reservation filter keyed on current status rather than the '
        'stay span',
        'A cached occupancy snapshot reused across dates'),
    principles=('P2', 'P4', 'P8', 'P12'),
    modes=MODES,
)
def _c05():
    pass


@fault(
    fault_id='FLT-C06',
    title='Canonical room-revenue engine bypassed by a 10% inflation',
    category=Category.ENGINE,
    purpose=(
        'P1 says there is one canonical derivation. This fault moves the '
        'canonical one and leaves the two legacy definitions alone, which '
        'is exactly what a partial migration looks like.'),
    business_rule_challenged=(
        'Room revenue has one canonical derivation that every consumer '
        'uses.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.services.get_room_revenue',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D1_PARITY,),
    expected_invariants=(),
    expected_quantities=('P03', 'P04'),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None declared: the replay reconciliations read the reservation '
        'tariff and the nightly rows, not this helper. That the canonical '
        'engine can move without a single reconciliation noticing is '
        'itself worth knowing.'),
    expected_parity_behaviour=(
        'P03 is the three-definition quantity and is built to catch '
        'exactly this: the canonical definition parts company with the '
        'two legacy ones.'),
    expected_certification_impact=(
        'Release-blocking: room revenue has two answers.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'P03 reports the canonical, single-night and rate x nights '
        'definitions side by side with per-reservation attribution.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=('app.services.get_room_revenue', '', 'mul', 1.1),
    affected_reports=('reports.revenue', 'main.invoice',
                      'night audit revenue summary'),
    root_cause_candidates=(
        'A migration that updated the canonical helper and not its '
        'callers',
        'A rate-plan change applied in one derivation only',
        'A CASE A / CASE B branch that stopped agreeing'),
    principles=('P1', 'P3'),
    modes=MODES,
)
def _c06():
    pass


@fault(
    fault_id='FLT-C07',
    title='OTA receivable filter excludes everything',
    category=Category.ENGINE,
    purpose=(
        'A filter that stopped matching. The receivable disappears from '
        'every report while the payments sit in the table, so the hotel '
        'stops chasing money it is owed and nothing looks wrong.'),
    business_rule_challenged=(
        'OTA receivable postings equal the ota_receivable payments '
        'recorded for the date.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.kpi_helpers.get_ota_receivable_posted',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D3_REPLAY,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=('RC03',),
    expected_replay_behaviour=(
        'RC03 breaks on every date with an OTA posting: the engine '
        'reports zero where the ledger holds the money.'),
    expected_parity_behaviour=(
        'None declared: P22 reads the payment table directly.'),
    expected_certification_impact=(
        'Certification-blocking: a receivable vanishes from every report.'),
    expected_severity=Severity.HIGH,
    expected_evidence=('RC03 gives the engine zero against the ledger total.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every date with an OTA posting',
    payload=('app.kpi_helpers.get_ota_receivable_posted', '', 'mul', 0.0),
    affected_reports=('reports.ota_reconciliation', 'reports.ar_aging',
                      'main.dashboard'),
    root_cause_candidates=(
        'A category string renamed on one side only',
        'An inner join where an outer was needed',
        'A filter narrowed during an unrelated refactor'),
    principles=('P1', 'P3'),
    modes=MODES,
)
def _c07():
    pass


@fault(
    fault_id='FLT-C08',
    title='Accrual room revenue double-counts occupied nights',
    category=Category.ENGINE,
    purpose=(
        'The join-fan-out regression on the accrual side: every in-house '
        'reservation counted twice. Earned revenue doubles while cash '
        'stays correct, so the two bases stop reconciling.'),
    business_rule_challenged=(
        'Accrual room revenue equals the tariff sum over the reservations '
        'in house that night.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=('app.kpi_helpers.get_accrual_room_revenue',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D3_REPLAY,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=('RC06', 'RC08', 'RC09'),
    expected_replay_behaviour=(
        'RC06 breaks directly, RC08 and RC09 downstream. The pattern — '
        'one primary and two derived — is what distinguishes a fault in '
        'the base helper from a fault in the bundle.'),
    expected_parity_behaviour=(
        'None declared: P04 sums the tariff itself rather than through '
        'this helper.'),
    expected_certification_impact=(
        'Release-blocking: earned revenue doubled.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'RC06 gives the engine and ledger figures per date.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every date with an in-house reservation',
    payload=('app.kpi_helpers.get_accrual_room_revenue', '', 'mul', 2.0),
    affected_reports=('reports.revenue', 'night audit revenue summary',
                      'reports.front_office_mis'),
    root_cause_candidates=(
        'A join to reservation_rooms fanning out on multi-room stays',
        'The in-house span filter widened to include departures',
        'A subquery returning duplicates after an index change'),
    principles=('P1', 'P3'),
    modes=MODES,
)
def _c08():
    pass


@fault(
    fault_id='FLT-C09',
    title='Night audit reports tax twice',
    category=Category.ENGINE,
    purpose=(
        'GST duplicated in the audit report while the stored lines are '
        'untouched. The return is filed from the lines and the day is '
        'reconciled from the report, so the two disagree and only one of '
        'them is looked at daily.'),
    business_rule_challenged=(
        'The night audit\'s tax figure equals the stored tax lines for '
        'the date.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=(
        'app.night_audit_service.NightAuditService.revenue_summary',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D3_REPLAY, Layer.D4_INVARIANTS),
    expected_invariants=('INV-B03',),
    expected_quantities=(),
    expected_reconciliations=('RC14',),
    expected_replay_behaviour=(
        'RC14 breaks against the stored tax lines, and the closed date '
        'shows history drift on tax.'),
    expected_parity_behaviour=(
        'None declared: P07 reads the tax table directly.'),
    expected_certification_impact=(
        'Certification-blocking: the audit and the return disagree about '
        'tax.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'RC14 gives the engine and the ledger tax totals; INV-B03 gives '
        'the frozen and recomputed values.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every date with tax lines',
    payload=('app.night_audit_service.NightAuditService.revenue_summary',
             'tax_amount', 'mul', 2.0),
    affected_reports=('night audit revenue summary', 'billing.gst_report'),
    root_cause_candidates=(
        'Tax summed from both the line table and a recomputation',
        'CGST and SGST added to a total that already includes both',
        'A component loop that iterates twice'),
    principles=('P1', 'P4'),
    modes=MODES,
)
def _c09():
    pass


@fault(
    fault_id='FLT-C10',
    title='Night audit settlement total diverges from the payments it lists',
    category=Category.ENGINE,
    purpose=(
        'The audit\'s collected total is the figure the day is reconciled '
        'on. Moving it while leaving the payment list alone is the shape '
        'of a total computed independently of the rows beneath it.'),
    business_rule_challenged=(
        'The night audit\'s collected total equals the direct payments '
        'recorded for the date.'),
    injection_method=Method.ENGINE_PATCH,
    target_objects=(
        'app.night_audit_service.NightAuditService.payment_summary',),
    target_layer=TargetLayer.ENGINE,
    expected_detection=(Layer.D3_REPLAY, Layer.D4_INVARIANTS,
                        Layer.D1_PARITY),
    expected_invariants=('INV-B03',),
    expected_quantities=('P15',),
    expected_reconciliations=('RC11',),
    expected_replay_behaviour=(
        'RC11 breaks by exactly the injected amount, and the closed date '
        'shows history drift on collected cash.'),
    expected_parity_behaviour=(
        'P15 diverges on total_revenue between the stored close and the '
        'recomputation.'),
    expected_certification_impact=(
        'Release-blocking: the day cannot be reconciled.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'RC11 gives the delta; INV-B03 names the frozen and recomputed '
        'totals for the date.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every date with a payment',
    payload=('app.night_audit_service.NightAuditService.payment_summary',
             'total_collected', 'add', 500.0),
    affected_reports=('night audit payment summary',
                      'reports.daily_reconciliation'),
    root_cause_candidates=(
        'A total computed independently of the rows it summarises',
        'A purpose bucket added to the total twice',
        'A reversal signed the wrong way in one aggregation'),
    principles=('P1', 'P4', 'P11'),
    modes=MODES,
)
def _c10():
    pass
