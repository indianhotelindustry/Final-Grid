"""
Evidence, matrices and failure reporting for the invariant engine.

Three audiences, three documents from the same run:

* ``result.json`` — machine-readable, what a release gate reads;
* ``report.txt`` — what an engineer reads, leading with the controls and
  then with the failures;
* the **failure report** — what an auditor or a hotel manager reads: for
  each violated invariant, what it means in business terms, what it costs
  in rupees, which objects are affected, which reports are wrong because
  of it, and where to start looking.

The registry, category, severity, mode and principle matrices are printed
without needing a database, so the constitution's coverage can be
reviewed independently of any particular run.
"""
from __future__ import annotations

from dataclasses import asdict

from verification.golden.report import write_pack  # one implementation only
from verification.invariants import registry
from verification.invariants.model import (
    ALL_CATEGORIES, ALL_MODES, Blocking, Commissioning, PRINCIPLES,
    SEVERITY_RANK, STRUCTURAL_ENFORCEMENT, Severity, Status,
)

W = 100

__all__ = ['write_pack', 'render_run', 'render_registry', 'render_history',
           'run_payload', 'history_payload', 'registry_payload']


# ---------------------------------------------------------------------------
# Registry documentation — no database required
# ---------------------------------------------------------------------------

def render_registry() -> str:
    L: list[str] = []
    add = L.append
    invariants = registry.all_invariants()

    add('=' * W)
    add('DSBC FRONTLINE — FINANCIAL INVARIANT REGISTRY')
    add('Production Verification Framework, Wave 0 Deliverable 4')
    add('=' * W)
    add(f'Registered invariants : {len(invariants)}')
    add('')

    add('-' * W)
    add('CATEGORY MATRIX')
    add('-' * W)
    matrix = registry.category_matrix()
    severities = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
                  Severity.LOW]
    add(f'{"CATEGORY":<18}' + ''.join(f'{s:>10}' for s in severities)
        + f'{"TOTAL":>8}')
    for category in ALL_CATEGORIES:
        row = matrix.get(category, {})
        total = sum(len(v) for v in row.values())
        add(f'{category:<18}'
            + ''.join(f'{len(row.get(s, [])):>10}' for s in severities)
            + f'{total:>8}')
    add('')

    add('-' * W)
    add('SEVERITY MATRIX — what a failure stops')
    add('-' * W)
    blockings = [Blocking.RELEASE, Blocking.CERTIFICATION,
                 Blocking.OPERATIONAL, Blocking.INFORMATIONAL]
    smatrix = registry.severity_matrix()
    add(f'{"SEVERITY":<12}' + ''.join(f'{b.split("_")[0]:>16}'
                                      for b in blockings))
    for severity in severities:
        row = smatrix.get(severity, {})
        add(f'{severity:<12}'
            + ''.join(f'{len(row.get(b, [])):>16}' for b in blockings))
    add('')

    add('-' * W)
    add('CONSTITUTIONAL COVERAGE — the Financial Constitution, P1 to P12')
    add('-' * W)
    add('Some principles are obligations of the SYSTEM and are enforced by')
    add('invariants. Others are obligations of the VERIFICATION FRAMEWORK')
    add('and are enforced structurally. Both are listed, with how, because')
    add('calling a structurally-enforced principle "uncovered" would be as')
    add('misleading as quietly counting it as covered.')
    add('')
    pmatrix = registry.principle_matrix()
    uncovered = []
    for principle, (name, kind) in PRINCIPLES.items():
        ids = sorted(pmatrix.get(principle, []))
        add(f'  {principle:<5} {name}')
        if ids:
            add(f'        enforced by {len(ids)} invariant(s): '
                f'{", ".join(ids)}')
        elif kind == 'structural':
            for line in _wrap(STRUCTURAL_ENFORCEMENT.get(principle, ''), 80):
                add(f'        structural: {line}')
        else:
            uncovered.append(principle)
            add('        *** NOT ENFORCED BY ANY INVARIANT ***')
    if uncovered:
        add('')
        add(f'  GAPS: {", ".join(uncovered)} have no invariant and no '
            f'structural enforcement.')
    add('')

    add('-' * W)
    add('MODE MATRIX — which invariants a given run exercises')
    add('-' * W)
    mmatrix = registry.mode_matrix()
    for mode in sorted(ALL_MODES):
        ids = sorted(mmatrix.get(mode, []))
        add(f'  {mode:<24} {len(ids):>2}  '
            + (', '.join(ids) if ids else
               '(no invariant declares this mode — a run in it would '
               'evaluate nothing)'))
    add('')

    gaps = registry.commissioning_gaps()
    add('-' * W)
    add(f'COMMISSIONING STATUS — {len(invariants) - len(gaps)}/'
        f'{len(invariants)} commissioned')
    add('-' * W)
    if not gaps:
        add('  Every invariant has been shown to be capable of failing.')
    for gap in gaps:
        add(f'  {gap["invariant_id"]:<10} {gap["status"]}')
        add(f'      {gap["reason"]}')
    add('')

    add('=' * W)
    add('THE REGISTER')
    add('=' * W)
    for inv in invariants:
        add('')
        add('-' * W)
        add(f'{inv.invariant_id}  {inv.title}')
        add('-' * W)
        add(f'  Category                : {inv.category}')
        add(f'  Severity / Blocking     : {inv.severity} / {inv.blocking}')
        add(f'  Principles              : {", ".join(inv.principles)}')
        add(f'  Commissioning           : {inv.commissioning_status}')
        add(f'  Modes                   : {", ".join(inv.modes)}')
        add(f'  Data sources            : {", ".join(inv.data_sources)}')
        add(f'  Canonical engine        : {inv.canonical_engine}')
        add(f'  Applicable releases     : {inv.applicable_releases}')
        add(f'  Applicable dates        : {inv.applicable_business_dates}')
        add('  Business purpose        :')
        for line in _wrap(inv.business_purpose):
            add(f'      {line}')
        add('  Business rule           :')
        for line in _wrap(inv.business_rule):
            add(f'      {line}')
        add('  Validation method       :')
        for line in _wrap(inv.validation_method):
            add(f'      {line}')
        add('  Evidence produced       :')
        for line in _wrap(inv.evidence_produced):
            add(f'      {line}')
        add('  Failure message         :')
        for line in _wrap(inv.failure_message):
            add(f'      {line}')
        add('  Likely root causes      :')
        for cause in inv.likely_root_causes:
            add(f'      - {cause}')
        add('  Suggested investigation :')
        for step in inv.suggested_investigation:
            add(f'      - {step}')
        add('  Reports affected        :')
        for report in inv.affected_reports:
            add(f'      - {report}')
        if inv.negative_seed:
            add('  Negative seed           :')
            for line in _wrap(inv.negative_seed_reason):
                add(f'      {line}')
        elif inv.negative_patch:
            add('  Negative patch          :')
            for line in _wrap(inv.negative_patch_reason):
                add(f'      {line}')
        else:
            add('  NOT SEEDABLE            :')
            for line in _wrap(inv.not_seedable_reason):
                add(f'      {line}')
    add('')
    add('=' * W)
    add('END OF REGISTRY')
    add('=' * W)
    return '\n'.join(L) + '\n'


def _wrap(text: str, width: int = 88) -> list:
    import textwrap
    return textwrap.wrap(' '.join((text or '').split()), width=width) or ['']


def registry_payload() -> dict:
    return {
        'invariants': [inv.as_dict() for inv in registry.all_invariants()],
        'category_matrix': registry.category_matrix(),
        'severity_matrix': registry.severity_matrix(),
        'principle_matrix': registry.principle_matrix(),
        'mode_matrix': registry.mode_matrix(),
        'commissioning_gaps': registry.commissioning_gaps(),
    }


# ---------------------------------------------------------------------------
# Run report
# ---------------------------------------------------------------------------

def render_run(run) -> str:
    L: list[str] = []
    add = L.append
    counts = run.counts

    add('=' * W)
    add('DSBC FRONTLINE — FINANCIAL INVARIANT ENGINE')
    add('Production Verification Framework, Wave 0 Deliverable 4')
    add('=' * W)
    add(f'Started           : {run.started_at}')
    add(f'Duration          : {run.duration_seconds:.1f}s')
    add(f'Application       : v{run.app_version}')
    add(f'PVF               : v{run.pvf_version}')
    add(f'Mode / scope      : {run.scope}')
    add(f'Business date     : {run.business_date}')
    add(f'Clock frozen at   : {run.frozen_at}')
    add('')

    add('-' * W)
    add('CONTROLS (Principle 11 — positive evidence, not silence)')
    add('-' * W)
    add(f'Source database   : {run.source_db}')
    add(f'Copy method       : {run.copy_method}')
    add(f'SHA-256 before    : {run.source_hash_before}')
    add(f'SHA-256 after     : {run.source_hash_after}')
    add('  read-only       : ' +
        ('VERIFIED — production byte-identical after run'
         if run.read_only_verified else
         '*** NOT VERIFIED — DO NOT TRUST THIS RUN ***'))
    add('  zero writes     : ' +
        (f'VERIFIED — {run.total_writes} write statements counted across '
         f'the whole registry' if run.write_free else
         f'*** {run.total_writes} WRITES DETECTED — the engine modified the '
         f'system it was verifying ***'))
    add('  frozen clock    : ' +
        ('proven' if run.freeze_proven else '*** NOT PROVEN ***'))
    add('  repeatable      : ' +
        ('VERIFIED — a second evaluation produced identical findings'
         if run.determinism_proven else
         f'*** {len(run.repeatability_mismatches)} invariant(s) differed on '
         f're-evaluation: {", ".join(run.repeatability_mismatches[:6])} ***'))
    add('  order independent: ' +
        ('VERIFIED — reverse-order evaluation produced identical findings'
         if run.order_independence_proven else
         f'*** {len(run.order_mismatches)} invariant(s) depend on evaluation '
         f'order: {", ".join(run.order_mismatches[:6])} ***'))
    add('  commissioning   : ' +
        (f'VERIFIED — every COMMISSIONED claim is backed by '
         f'{run.commissioning_evidence_pack.rsplit(chr(92), 1)[-1].rsplit("/", 1)[-1]}'
         if not run.unbacked_commissioning_claims else
         f'*** {len(run.unbacked_commissioning_claims)} invariant(s) claim '
         f'to be commissioned without evidence ***'))
    for claim in run.unbacked_commissioning_claims[:10]:
        add(f'      {claim["invariant_id"]}: {claim["reason"]}')
    add('')

    add('-' * W)
    add('SUMMARY')
    add('-' * W)
    add(f'  Registered        : {counts["registered"]}')
    for status in (Status.HOLDS, Status.VIOLATED, Status.VACUOUS,
                   Status.NOT_APPLICABLE, Status.ERROR):
        add(f'  {status:<18}: {counts.get(status, 0)}')
    add(f'  Violations found  : {counts["violations"]}')
    add(f'  Uncommissioned    : {counts["uncommissioned"]}  '
        f'(reported, but excluded from the verdict)')
    add('')
    add(f'  OVERALL VERDICT   : {run.overall}')
    add(f'  Release blocking  : {len(run.release_blocking)}')
    add(f'  Cert. blocking    : {len(run.certification_blocking)}')
    add('')

    # -- failure report --------------------------------------------------
    violated = sorted(run.violated,
                      key=lambda r: (SEVERITY_RANK.get(r.severity, 9),
                                     r.invariant_id))
    if violated:
        add('=' * W)
        add(f'FAILURE REPORT — {len(violated)} invariant(s) violated')
        add('=' * W)
        for result in violated:
            inv = registry.get(result.invariant_id)
            add('')
            add('-' * W)
            add(f'{result.invariant_id}  [{result.severity} / '
                f'{result.blocking}]  {result.title}')
            add('-' * W)
            add('  What it means:')
            for line in _wrap(inv.failure_message):
                add(f'      {line}')
            add('  Why it matters:')
            for line in _wrap(inv.business_purpose):
                add(f'      {line}')
            add(f'  Financial impact  : {result.financial_impact} '
                f'(sum of the amounts carried by the violating rows)')
            add(f'  Population        : {result.population}')
            add(f'  Violations        : {result.violation_count}'
                + ('' if result.violation_count == len(result.violations)
                   else f'  (first {len(result.violations)} listed)'))
            add(f'  Confidence        : {result.evidence.confidence}')
            add(f'  Observed          : {result.evidence.observed_result}')
            if result.evidence.variance:
                add(f'  Variance          : {result.evidence.variance}')
            add(f'  Constitutional    : {", ".join(inv.principles)}')
            add('  Reports affected  :')
            for report in inv.affected_reports:
                add(f'      - {report}')
            add('  Root cause candidates:')
            for cause in inv.likely_root_causes:
                add(f'      - {cause}')
            add('  Recommended investigation:')
            for step in inv.suggested_investigation:
                add(f'      - {step}')
            if not result.counts_as_evidence:
                add('  NOTE: this invariant is not yet commissioned. Its '
                    'finding is reported')
                add('        but excluded from the verdict — it has never '
                    'been shown to be')
                add('        capable of failing, so it cannot be relied on '
                    'to have passed.')
            add('  Affected objects:')
            for violation in result.violations[:25]:
                add(f'      {violation.object_type} {violation.object_id}')
                add(f'          expected {violation.expected}')
                add(f'          observed {violation.observed}'
                    + (f'   (amount {violation.amount})'
                       if violation.amount not in ('0', '') else ''))
            if result.violation_count > 25:
                add(f'      ... {result.violation_count - 25} more '
                    f'(see result.json)')
        add('')

    errored = [r for r in run.results if r.status == Status.ERROR]
    if errored:
        add('=' * W)
        add('ERRORS')
        add('=' * W)
        for result in errored:
            add(f'  {result.invariant_id}: {result.error}')
        add('')

    unproven = [r for r in run.results
                if r.status in (Status.VACUOUS, Status.NOT_APPLICABLE)]
    if unproven:
        add('=' * W)
        add('NOT PROVEN — evaluated but not exercised')
        add('=' * W)
        add('These invariants did not fail. They also did not pass: the')
        add('population was empty, or the mode does not apply. Under P10')
        add('absence of data is not evidence of correctness, and reporting')
        add('them as green would make the engine exactly the kind of control')
        add('that cannot fail.')
        for result in unproven:
            add(f'  [{result.status:<15}] {result.invariant_id}  '
                f'{result.title}')
            add(f'      {result.evidence.observed_result}')
        add('')

    # -- performance ------------------------------------------------------
    add('=' * W)
    add('PERFORMANCE AND SAFETY')
    add('=' * W)
    add(f'{"ID":<10}{"STATUS":<16}{"POP":>7}{"VIOL":>6}{"ms":>7}'
        f'{"reads":>8}{"writes":>8}{"rows":>8}{"peak KB":>9}  TITLE')
    add('-' * W)
    for result in run.results:
        m = result.metering
        add(f'{result.invariant_id:<10}{result.status:<16}'
            f'{result.population:>7}{result.violation_count:>6}'
            f'{m.duration_ms:>7}{m.db_reads:>8}{m.db_writes:>8}'
            f'{m.rows_examined:>8}{m.memory_peak_kb:>9}  {result.title[:34]}')
    add('-' * W)
    add(f'{"TOTAL":<10}{"":<16}{"":>7}'
        f'{sum(r.violation_count for r in run.results):>6}'
        f'{sum(r.metering.duration_ms for r in run.results):>7}'
        f'{sum(r.metering.db_reads for r in run.results):>8}'
        f'{run.total_writes:>8}'
        f'{sum(r.metering.rows_examined for r in run.results):>8}'
        f'{max([r.metering.memory_peak_kb for r in run.results] or [0]):>9}')
    add('')

    if run.commissioning_gaps:
        add('=' * W)
        add(f'COMMISSIONING GAPS ({len(run.commissioning_gaps)})')
        add('=' * W)
        add('An invariant that has never been shown to fail is not yet a')
        add('control. These are reported by the engine and excluded from its')
        add('verdict until commissioning demonstrates the failure.')
        for gap in run.commissioning_gaps:
            add(f'  {gap["invariant_id"]:<10} {gap["status"]}')
            add(f'      {gap["reason"]}')
        add('')

    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def run_payload(run) -> dict:
    payload = asdict(run)
    payload['counts'] = run.counts
    payload['overall'] = run.overall
    payload['release_blocking'] = [r.invariant_id for r in run.release_blocking]
    payload['certification_blocking'] = [
        r.invariant_id for r in run.certification_blocking]
    payload['financial_impact'] = {
        r.invariant_id: r.financial_impact for r in run.violated}
    return payload


# ---------------------------------------------------------------------------
# Historical replay report
# ---------------------------------------------------------------------------

def render_history(run) -> str:
    L: list[str] = []
    add = L.append
    add('=' * W)
    add('DSBC FRONTLINE — INVARIANT HISTORICAL REPLAY')
    add('Production Verification Framework, Wave 0 Deliverable 4')
    add('=' * W)
    add(f'Started           : {run.started_at}')
    add(f'Duration          : {run.duration_seconds:.1f}s')
    add(f'Application       : v{run.app_version}')
    add(f'Business date     : {run.business_date}')
    add(f'Dates replayed    : {run.dates_replayed}  '
        f'({run.first_date} .. {run.business_date})')
    add(f'Read-only         : '
        f'{"VERIFIED" if run.read_only_verified else "NOT VERIFIED"}')
    add(f'Zero writes       : '
        f'{"VERIFIED" if not run.total_writes else run.total_writes}')
    add('')
    add(f'VERDICT           : {run.verdict}')
    add('')

    add('-' * W)
    add('WHAT THIS CAN AND CANNOT ANSWER')
    add('-' * W)
    add('The database holds one state: the present one. There is no archive')
    add('of what it looked like on a past date, so "was this true then"')
    add('cannot mean "restore the database and evaluate". Each date is')
    add('instead evaluated twice against current data — once with the clock')
    add('frozen to that date, once with the clock frozen to today. A')
    add('difference between the two is clock-dependence inside a date-scoped')
    add('rule. Genuine historical state is available only where a night')
    add('audit froze a snapshot, and INV-B03 is the invariant that uses it.')
    add('')

    add('=' * W)
    add('EARLIEST DIVERGENCE')
    add('=' * W)
    add(f'{"ID":<10}{"SEVERITY":<10}{"EARLIEST FAIL":<16}{"POP":>6}'
        f'{"CLOCK-DEP":>11}{"TODAY":>8}  TITLE')
    add('-' * W)
    for history in run.invariants:
        add(f'{history.invariant_id:<10}{history.severity:<10}'
            f'{(history.earliest_divergence or "—"):<16}'
            f'{history.earliest_divergence_population:>6}'
            f'{len(history.clock_dependent_dates):>11}'
            f'{("holds" if history.holds_today else "no"):>8}  '
            f'{history.title[:34]}')
    add('')

    if run.clock_dependent:
        add('=' * W)
        add('CLOCK-DEPENDENT INVARIANTS')
        add('=' * W)
        add('These answered differently about the same past date depending on')
        add('when the question was asked. A date-scoped obligation whose')
        add('truth depends on the wall clock is not date-scoped.')
        for history in run.clock_dependent:
            add(f'  {history.invariant_id}  {history.title}')
            add(f'      {len(history.clock_dependent_dates)} date(s): '
                + ', '.join(history.clock_dependent_dates[:12]))
        add('')

    diverged = run.diverged
    if diverged:
        add('=' * W)
        add('PER-INVARIANT TIMELINES')
        add('=' * W)
        for history in diverged:
            add('')
            add(f'{history.invariant_id}  {history.title}')
            add(f'  earliest divergence: {history.earliest_divergence} '
                f'(population {history.earliest_divergence_population})')
            add(f'  {"DATE":<12}{"AS OF DATE":<16}{"AS OF TODAY":<16}'
                f'{"VIOL":>6}{"CLOSED":>8}')
            quiet = 0
            for outcome in history.dates:
                uneventful = (outcome.status_as_of_date in
                              (Status.HOLDS, Status.VACUOUS,
                               Status.NOT_APPLICABLE))
                if uneventful and not outcome.clock_dependent:
                    quiet += 1
                    continue
                add(f'  {outcome.date:<12}{outcome.status_as_of_date:<16}'
                    f'{outcome.status_as_of_today:<16}'
                    f'{outcome.violations_as_of_date:>6}'
                    f'{("yes" if outcome.is_closed else ""):>8}')
            if quiet:
                add(f'  ({quiet} further date(s) held, or had no rows to '
                    f'test — see result.json)')
        add('')

    if run.skipped:
        add('=' * W)
        add(f'NOT REPLAYED ({len(run.skipped)})')
        add('=' * W)
        add('These invariants declare no date-scoped mode, so they have no')
        add('historical form. Listed rather than dropped, so the coverage of')
        add('a historical run is never overstated.')
        for item in run.skipped:
            add(f'  {item["invariant_id"]}')
            add(f'      {item["reason"]}')
        add('')

    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def history_payload(run) -> dict:
    payload = asdict(run)
    payload['verdict'] = run.verdict
    payload['diverged'] = [h.invariant_id for h in run.diverged]
    payload['clock_dependent'] = [h.invariant_id for h in run.clock_dependent]
    return payload
