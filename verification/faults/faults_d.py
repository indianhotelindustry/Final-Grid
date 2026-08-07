"""
Class D — Operational faults.

Nothing about the money is wrong; the environment is. The clock has
drifted, a frozen snapshot has been edited, the configuration the figures
were produced under is not the configuration they are being read under.

This class is where the framework's blind spots cluster, and that is the
most useful thing about it. Three faults here are registered as
**uncovered**: no layer of the current framework can see them. They are
not quietly omitted, because a taxonomy that lists only the faults the
framework happens to catch is a taxonomy that flatters it. Each names the
deliverable that will close the gap.
"""
from __future__ import annotations

from verification.faults.model import (
    Category, Commissioning, Layer, Method, Mode, Severity, TargetLayer,
)
from verification.faults.registry import fault

MODES = (Mode.SINGLE_FAULT, Mode.BATCH, Mode.COMMISSIONING,
         Mode.RELEASE_VERIFICATION, Mode.CONTINUOUS_VERIFICATION)

REPEATABLE = ('Deterministic: the same environment or the same rows, '
              'every run.')
DETERMINISTIC = ('No randomness and no ordering dependence; where a clock '
                 'is involved it is set to an explicit instant.')
CLEANUP = ('The private database copy is deleted and verified; '
           'environment overlays exist only inside the probe subprocess; '
           'file faults are applied to a copy in the arena, never to the '
           'original.')


@fault(
    fault_id='FLT-D01',
    title='Clock drift: a run executes one day out',
    category=Category.OPERATIONAL,
    purpose=(
        'A verification run whose clock is wrong measures a day the hotel '
        'did not trade, and every figure it produces is internally '
        'consistent. Nothing about the data is wrong; the run is.'),
    business_rule_challenged=(
        'A verification run states, and can prove, the instant it ran at.'),
    injection_method=Method.CLOCK_SHIFT,
    target_objects=('the frozen clock',),
    target_layer=TargetLayer.CLOCK,
    expected_detection=(Layer.D2_GOLDEN,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected. D3 derives its own clock per replayed date and '
        'does not honour the override, so it is immune by construction — '
        'worth stating, because "immune" and "blind" look identical in a '
        'result table.'),
    expected_parity_behaviour=(
        'None expected: D1 does not freeze the clock at all, which is why '
        'its date-scoped quantities take explicit date arguments.'),
    expected_certification_impact=(
        'Release-blocking if undetected: it would mean masters can silently '
        'be captured for the wrong day.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'Every clock-sensitive surface moves; D2 attributes the movement '
        'surface by surface.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(1,),
    affected_reports=('main.dashboard', 'reports.flash'),
    root_cause_candidates=(
        'A scheduled run crossing midnight',
        'A server clock out of sync with the business date',
        'A manual override left set from a previous investigation'),
    principles=('P8', 'P11'),
    modes=MODES,
)
def _d01():
    pass


@fault(
    fault_id='FLT-D02',
    title='A frozen night-audit snapshot has been edited',
    category=Category.OPERATIONAL,
    purpose=(
        'The snapshot is the hotel\'s own frozen statement about a day, '
        'and its hash exists so that a manual edit cannot rewrite '
        'history. This fault is the tamper the control claims to detect.'),
    business_rule_challenged=(
        'Every frozen snapshot matches its stored hash.'),
    injection_method=Method.SQL,
    target_objects=('night_audit_logs',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY),
    expected_invariants=('INV-B02',),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The snapshot integrity verdict for the date flips to false.'),
    expected_parity_behaviour=(
        'None declared: Q15 compares stored column totals, which the edit '
        'leaves alone.'),
    expected_certification_impact=(
        'Release-blocking: the record of a closed day cannot be vouched '
        'for.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B02 gives the stored and recomputed hashes for the date.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='v2.2 and later',
    applicable_business_dates='every date with a snapshot',
    payload=(
        "UPDATE night_audit_logs SET snapshot_json = snapshot_json || ' ' "
        "WHERE snapshot_json IS NOT NULL AND snapshot_hash IS NOT NULL",
    ),
    affected_reports=('night audit', 'reports.night_audit_history'),
    root_cause_candidates=(
        'A manual UPDATE against night_audit_logs',
        'A serialisation change without re-hashing',
        'A restore that mixed rows from two versions'),
    principles=('P2', 'P7', 'P11', 'P12'),
    modes=MODES,
)
def _d02():
    pass


@fault(
    fault_id='FLT-D03',
    title='The stored close total for an audited day has been rewritten',
    category=Category.OPERATIONAL,
    purpose=(
        'Not the snapshot but the columns beside it: the figures the '
        'system itself reports as the day\'s close. Changing them makes '
        'the audit disagree with its own recomputation.'),
    business_rule_challenged=(
        'A closed day recomputes the figures it reported.'),
    injection_method=Method.SQL,
    target_objects=('night_audit_logs',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY,
                        Layer.D1_PARITY),
    expected_invariants=('INV-B03',),
    expected_quantities=('Q15',),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'History drift between the recomputed collected total and the '
        'stored close.'),
    expected_parity_behaviour=(
        'Q15 diverges on total_revenue.'),
    expected_certification_impact=(
        'Release-blocking: the reported day and the computed day '
        'disagree.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B03 names the date and field with both values; Q15 '
        'attributes the divergence to the stored column.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every closed date',
    payload=(
        "UPDATE night_audit_logs SET total_revenue = total_revenue + 999.00 "
        "WHERE audit_date = (SELECT MIN(audit_date) FROM night_audit_logs)",
    ),
    affected_reports=('night audit', 'reports.daily_reconciliation'),
    root_cause_candidates=(
        'A manual correction applied to the log rather than the data',
        'A reopen-and-partially-rerun cycle',
        'A migration that recalculated stored aggregates'),
    principles=('P2', 'P4', 'P7', 'P12'),
    modes=MODES,
)
def _d03():
    pass


@fault(
    fault_id='FLT-D04',
    title='A database backup file is corrupt',
    category=Category.OPERATIONAL,
    purpose=(
        'A backup that cannot be restored is not a backup. The hotel '
        'believes it has a recovery position it does not have, and finds '
        'out on the day it matters.'),
    business_rule_challenged=(
        'Every recorded backup is restorable and matches what it claims '
        'to contain.'),
    injection_method=Method.FILE,
    target_objects=('backups/', 'backup_logs'),
    target_layer=TargetLayer.ARTEFACT,
    expected_detection=(),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour='None. No layer reads backup files.',
    expected_parity_behaviour='None.',
    expected_certification_impact=(
        'Would be release-blocking. Currently invisible, which is the '
        'finding.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'None produced by any layer. The backup_logs table records a '
        'filename, a size and a status, and no checksum — so even a '
        'byte-for-byte comparison has nothing to compare against.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.UNCOVERED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=('backups', 'flip'),
    affected_reports=('backup history',),
    root_cause_candidates=(
        'Storage corruption between backup and restore',
        'A truncated write when the disk filled',
        'A backup taken while the database was mid-write'),
    principles=('P11', 'P13'),
    modes=MODES,
    uncovered_reason=(
        'No verification layer reads backup artefacts, and backup_logs '
        'stores no checksum — the schema records filename, size and '
        'status only. There is nothing to compare a restored file '
        'against, so corruption is undetectable by construction rather '
        'than by omission.'),
    covered_by_deliverable=(
        'D9 — Backup Restore Verification. It will need a checksum '
        'column, or an out-of-band manifest, before it can detect this at '
        'all.'),
)
def _d04():
    pass


@fault(
    fault_id='FLT-D05',
    title='A restored database does not match what was backed up',
    category=Category.OPERATIONAL,
    purpose=(
        'Restoration is the one recovery control that is never exercised '
        'until it is needed. A restore that silently loses the last day '
        'of trading is indistinguishable from a successful one.'),
    business_rule_challenged=(
        'A restore reproduces the state that was backed up, exactly.'),
    injection_method=Method.SQL,
    target_objects=('the restored database',),
    target_layer=TargetLayer.ARTEFACT,
    expected_detection=(),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None. The framework has no notion of a backup to compare a '
        'restore against.'),
    expected_parity_behaviour='None.',
    expected_certification_impact=(
        'Would be release-blocking. Currently invisible.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'None. A restored database is simply a database; nothing records '
        'what it was supposed to contain.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.UNCOVERED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "DELETE FROM payments WHERE payment_date = "
        "  (SELECT MAX(payment_date) FROM payments)",
    ),
    affected_reports=('every report',),
    root_cause_candidates=(
        'A restore from an older backup than intended',
        'A partial restore that stopped at a table boundary',
        'A restore into a schema newer than the dump'),
    principles=('P11', 'P13'),
    modes=MODES,
    uncovered_reason=(
        'Detecting this requires comparing a restored database against a '
        'recorded pre-backup fingerprint. Nothing in the framework holds '
        'one, so the deletion is simply the new truth and every layer '
        'reconciles against it perfectly.'),
    covered_by_deliverable=(
        'D9 — Backup Restore Verification, which must fingerprint before '
        'backup and re-verify after restore for this to be detectable.'),
)
def _d05():
    pass


@fault(
    fault_id='FLT-D06',
    title='Hotel state code changed, flipping the GST regime',
    category=Category.OPERATIONAL,
    purpose=(
        'A configuration value that silently changes how tax is computed. '
        'The stored lines stay intrastate CGST and SGST while every fresh '
        'computation becomes interstate IGST, and the two coexist without '
        'complaint.'),
    business_rule_challenged=(
        'The configuration the figures were produced under is the '
        'configuration they are read under.'),
    injection_method=Method.SQL,
    target_objects=('settings.hotel_state_code',),
    target_layer=TargetLayer.CONFIGURATION,
    expected_detection=(Layer.D2_GOLDEN,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None declared: the replay reconciliations read stored tax lines '
        'rather than recomputing GST.'),
    expected_parity_behaviour=(
        'None declared: Q07 totals the stored components, which the '
        'setting does not touch.'),
    expected_certification_impact=(
        'Certification-blocking: invoices would be issued under the wrong '
        'GST regime.'),
    expected_severity=Severity.HIGH,
    expected_evidence=(
        'Every rendered surface that computes GST moves; D2 attributes it '
        'surface by surface.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE settings SET value = '07' WHERE key = 'hotel_state_code'",
    ),
    affected_reports=('main.invoice', 'billing.gst_report'),
    root_cause_candidates=(
        'A settings edit made without re-issuing affected invoices',
        'A multi-property deployment sharing one settings table',
        'A restore of settings from a different property'),
    principles=('P1', 'P11'),
    modes=MODES,
)
def _d06():
    pass


@fault(
    fault_id='FLT-D07',
    title='A run executes under a different process environment',
    category=Category.OPERATIONAL,
    purpose=(
        'Two runs of the same code over the same data under different '
        'environments can produce different figures, and nothing in the '
        'evidence records which environment produced which.'),
    business_rule_challenged=(
        'Evidence states the environment it was produced under.'),
    injection_method=Method.ENV,
    target_objects=('FLASK_ENV',),
    target_layer=TargetLayer.ENVIRONMENT,
    expected_detection=(),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None. The replay records the application version and the frozen '
        'clock, and nothing else about the process.'),
    expected_parity_behaviour=(
        'None. The parity evidence pack records app and PVF versions '
        'only.'),
    expected_certification_impact=(
        'Certification-blocking if undetected: a certificate that cannot '
        'name the environment it certifies is a certificate about '
        'nothing in particular.'),
    expected_severity=Severity.MEDIUM,
    expected_evidence=(
        'None. This fault is registered to record that the evidence model '
        'has no environment fingerprint, not to demonstrate a detection.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.UNCOVERED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=('FLASK_ENV', 'development'),
    affected_reports=('every evidence pack',),
    root_cause_candidates=(
        'A run executed from a developer machine',
        'A container image with different defaults',
        'An environment variable set for debugging and left set'),
    principles=('P6', 'P11', 'P13'),
    modes=MODES,
    uncovered_reason=(
        'No layer fingerprints the process environment, so a run under a '
        'different environment is indistinguishable in the evidence. The '
        'gap is in the evidence model rather than in any control.'),
    covered_by_deliverable=(
        'D7 — Certification Engine, which must record an environment '
        'fingerprint in every certificate for this to be visible.'),
)
def _d07():
    pass


@fault(
    fault_id='FLT-D08',
    title='An invoice presentation flag was changed after issue',
    category=Category.OPERATIONAL,
    purpose=(
        'A flag that changes what a document shows without changing what '
        'it says. A reissued invoice no longer matches the one the guest '
        'holds, and no financial total moved to signal it.'),
    business_rule_challenged=(
        'A document reissued today renders as it rendered when issued.'),
    injection_method=Method.SQL,
    target_objects=('settings.invoice_show_gst_breakdown',),
    target_layer=TargetLayer.CONFIGURATION,
    expected_detection=(Layer.D2_GOLDEN,),
    expected_invariants=(),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'None expected: no figure changes, only what is rendered.'),
    expected_parity_behaviour=(
        'None expected, for the same reason. This fault exists precisely '
        'to show that the golden master layer covers something the '
        'numeric layers cannot.'),
    expected_certification_impact=(
        'Operational: no money is misstated, but a reissued document '
        'differs from the original.'),
    expected_severity=Severity.MEDIUM,
    expected_evidence=(
        'D2 reports a body-hash change on the invoice surfaces with no '
        'accompanying figure change — the signature of a '
        'presentation-only difference.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE settings SET value = 'false' "
        "WHERE key = 'invoice_show_gst_breakdown'",
    ),
    affected_reports=('main.invoice',),
    root_cause_candidates=(
        'A settings change made for one guest and left in place',
        'A template toggle flipped during an unrelated change',
        'A settings restore from a different configuration'),
    principles=('P11', 'P12'),
    modes=MODES,
)
def _d08():
    pass


@fault(
    fault_id='FLT-D09',
    title='The business date has been rolled backwards',
    category=Category.OPERATIONAL,
    purpose=(
        'A restore, or a manual correction, that moves the business date '
        'into the past. Trading that has already happened is now dated in '
        'the future, and a closed night audit is dated after the day the '
        'hotel believes it is on.'),
    business_rule_challenged=(
        'The business date is at or after every closed audit and every '
        'dated financial row.'),
    injection_method=Method.SQL,
    target_objects=('business_date',),
    target_layer=TargetLayer.CONFIGURATION,
    expected_detection=(Layer.D4_INVARIANTS,),
    expected_invariants=('INV-B04', 'INV-B05'),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The replay window shortens to end at the rolled-back date, so '
        'the most recent trading days fall out of scope entirely — a '
        'silent loss of coverage that the window note is the only record '
        'of.'),
    expected_parity_behaviour=(
        'None declared: the parity quantities take the business date as '
        'given.'),
    expected_certification_impact=(
        'Release-blocking: the temporal basis is behind the data.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B04 names the rows dated beyond the business date; INV-B05 '
        'names the audit dated after it.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='all',
    payload=(
        "UPDATE business_date "
        "SET \"current_date\" = DATE(\"current_date\", '-5 day')",
    ),
    affected_reports=('every date-scoped report', 'night audit'),
    root_cause_candidates=(
        'A restore from a backup taken days earlier',
        'A manual correction to unblock a stuck night audit',
        'A test reset run against the live database'),
    principles=('P7', 'P8', 'P12'),
    modes=MODES,
)
def _d09():
    pass


@fault(
    fault_id='FLT-D10',
    title='A completed night audit has been reopened and left open',
    category=Category.OPERATIONAL,
    purpose=(
        'Reopening a closed day is a legitimate operation; leaving it '
        'open is not. The period stops being append-only, its figures can '
        'move again, and every control that keys on "closed" quietly '
        'stops applying to it.'),
    business_rule_challenged=(
        'A day that was closed stays closed, or is closed again.'),
    injection_method=Method.SQL,
    target_objects=('night_audit_logs',),
    target_layer=TargetLayer.DATA,
    expected_detection=(Layer.D4_INVARIANTS, Layer.D3_REPLAY),
    expected_invariants=('INV-B01', 'INV-B03'),
    expected_quantities=(),
    expected_reconciliations=(),
    expected_replay_behaviour=(
        'The date stops being reported as closed, so severity in a '
        'release comparison drops from BLOCK to WARN for that day — the '
        'control does not fire, it becomes inapplicable, which is the '
        'more dangerous failure.'),
    expected_parity_behaviour=(
        'None declared: Q15 iterates audit logs regardless of status.'),
    expected_certification_impact=(
        'Release-blocking: a reported period has been un-reported.'),
    expected_severity=Severity.CRITICAL,
    expected_evidence=(
        'INV-B01 and INV-B03 both lose the date from their population — '
        'the population count is the evidence, and it is why population '
        'is recorded on every invariant result.'),
    cleanup_strategy=CLEANUP,
    repeatability=REPEATABLE,
    determinism=DETERMINISTIC,
    commissioning_status=Commissioning.COMMISSIONED,
    applicable_releases='all',
    applicable_business_dates='every closed date',
    payload=(
        "UPDATE night_audit_logs SET status = 'Reopened' "
        "WHERE audit_date = (SELECT MIN(audit_date) FROM night_audit_logs)",
    ),
    affected_reports=('night audit', 'reports.night_audit_history'),
    root_cause_candidates=(
        'A reopen for a correction that was never re-run',
        'A crash between reopen and re-close',
        'A status column edited directly'),
    principles=('P2', 'P7', 'P12'),
    modes=MODES,
)
def _d10():
    pass
