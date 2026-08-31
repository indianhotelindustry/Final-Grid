"""
Evidence for historical replay runs.

Same contract as D1 and D2: a machine-readable ``result.json`` a release
gate can read, and a ``report.txt`` an engineer actually reads, both
deterministic given the same inputs.

The report leads with the controls — read-only, clock, ledger stability,
order independence — before any figure. A number produced by a harness
whose guarantees were not established is not evidence, and putting the
numbers first invites people to read them as though it were.
"""
from __future__ import annotations

from dataclasses import asdict

from verification.golden.report import write_pack  # one implementation only
from verification.replay import reconcile as rec

W = 100

__all__ = ['write_pack', 'render_replay', 'render_comparison',
           'replay_payload', 'comparison_payload']


def _controls(run) -> list:
    L: list[str] = []
    add = L.append
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

    proven = sum(1 for d in run.dates if d.freeze_proven)
    add(f'  frozen clock    : proven on {proven}/{len(run.dates)} dates '
        f'(each date re-installs and re-proves the freeze)')

    add('  ledger stable   : ' +
        ('VERIFIED — the primary record is byte-identical before and after '
         'the application ran'
         if run.ledger_stable else
         f'*** {len(run.ledger_instability)} figures MOVED — the replay '
         f'itself wrote to the copy ***'))

    if run.order_proof_run:
        mismatches = sum(len(d.order_mismatch) for d in run.dates)
        add('  order independent: ' +
            ('VERIFIED — replaying the dates in reverse produced identical '
             'figures'
             if mismatches == 0 else
             f'*** {mismatches} figures depend on the order the dates were '
             f'replayed in ***'))
    else:
        add('  order independent: NOT RUN — requested with --fast. The risk '
            'that state leaked between dates was not measured.')
    add('')
    return L


def render_replay(run) -> str:
    L: list[str] = []
    add = L.append
    counts = run.counts

    add('=' * W)
    add('FINALGRID — HISTORICAL REPLAY')
    add('Production Verification Framework, Wave 0 Deliverable 3')
    add('=' * W)
    add(f'Started           : {run.started_at}')
    add(f'Duration          : {run.duration_seconds:.1f}s')
    add(f'Application       : v{run.app_version}')
    add(f'PVF               : v{run.pvf_version}')
    add(f'Business date     : {run.business_date}')
    add(f'History replayed  : {run.first_activity} .. {run.business_date}')
    add('')
    L.extend(_controls(run))

    add('-' * W)
    add('COVERAGE')
    add('-' * W)
    add(f'  Dates replayed        : {counts["dates"]}  '
        f'({counts["traded"]} with primary records, '
        f'{run.gaps_filled} with none — replayed anyway)')
    add(f'  Closed (night audit)  : {counts["closed"]}')
    add(f'  With frozen snapshot  : {counts["with_snapshot"]}')
    add(f'  Reconciliations       : {counts["reconciled"]} reconciled, '
        f'{counts["unreconciled"]} UNRECONCILED, '
        f'{counts["not_comparable"]} not comparable, '
        f'{counts["no_activity"]} on days with no activity')
    add(f'  As-at drift           : {counts["asat_drift"]} figures move '
        f'when a closed day is asked about today')
    add(f'  History drift         : {counts["history_drift"]} figures differ '
        f'from what was frozen at close')
    add(f'  Engine probe errors   : {counts["engine_errors"]}')
    add('')
    add(f'  OVERALL VERDICT       : {run.overall}')
    add(f'  Blocking findings     : {len(run.blocking)}')
    add('')

    if counts['closed'] == 0:
        add('  NOTE: no date in this dataset has a completed night audit, so')
        add('  the comparison against what the system froze at close time was')
        add('  not exercised. That half of the framework is unverified by')
        add('  this run — absence of a closed day is not evidence that')
        add('  closed days reconcile (Principle 10).')
        add('')

    # -- the findings ----------------------------------------------------
    unreconciled = [(d, r) for d in run.dates for r in d.unreconciled]
    if unreconciled:
        add('=' * W)
        add(f'UNRECONCILED — the application disagrees with the primary '
            f'record ({len(unreconciled)})')
        add('=' * W)
        add('Each line is one declared reconciliation that did not hold. The')
        add('ledger side is summed from the transactional rows for that date')
        add('by this package, with no application code involved.')
        add('')
        for d, r in unreconciled:
            add(f'{d.date}  [{r.rule_id}]  {r.engine_path}')
            add(f'      engine : {r.engine_value}')
            add(f'      ledger : {r.ledger_value}   ({r.ledger_expr})')
            add(f'      delta  : {r.delta}   over {r.population} row(s)')
        add('')

    drifted = [d for d in run.dates if d.asat_drift]
    if drifted:
        add('=' * W)
        add('AS-AT DRIFT — a past day answers differently depending on when '
            'it is asked')
        add('=' * W)
        add('The same date, the same data, two clocks: once frozen to the')
        add('date itself, once frozen to the current business date. A figure')
        add('that moves is a present-tense query inside a historical report.')
        add('')
        for d in drifted:
            state = 'CLOSED' if d.is_closed else 'open'
            add(f'{d.date} ({state}) — {len(d.asat_drift)} figures')
            for item in d.asat_drift[:40]:
                add(f'      {item["path"]}')
                add(f'          asked on the date : {item["asked_on_the_date"]}')
                add(f'          asked today       : {item["asked_today"]}')
            if len(d.asat_drift) > 40:
                add(f'      ... {len(d.asat_drift) - 40} more '
                    f'(see result.json — nothing is omitted there)')
        add('')

    history = [d for d in run.dates if d.history_drift]
    if history:
        add('=' * W)
        add('HISTORY DRIFT — today\'s code disagrees with what was frozen at '
            'close')
        add('=' * W)
        add('These dates were closed and the figures reported. Recomputing')
        add('them now gives a different answer. Either the data moved after')
        add('the close, or the code changed what the day means.')
        add('')
        for d in history:
            add(f'{d.date} ({d.audit_status or "no status"}) — '
                f'{len(d.history_drift)} figures')
            for item in d.history_drift:
                add(f'      {item["path"]}')
                add(f'          frozen at close : {item["frozen_at_close"]}')
                add(f'          recomputed now  : {item["recomputed_today"]}')
        add('')

    integrity_failures = [d for d in run.dates if not d.snapshot_intact]
    if integrity_failures:
        add('=' * W)
        add('SNAPSHOT INTEGRITY FAILURES')
        add('=' * W)
        for d in integrity_failures:
            add(f'{d.date}')
            add(f'      stored hash  : {d.snapshot_integrity.get("stored_hash")}')
            add(f'      current hash : {d.snapshot_integrity.get("current_hash")}')
        add('')

    errored = [d for d in run.dates if d.engine_errors]
    if errored:
        add('=' * W)
        add('ENGINE PROBE ERRORS')
        add('=' * W)
        for d in errored:
            add(f'{d.date}')
            for probe, message in sorted(d.engine_errors.items()):
                add(f'      {probe}: {message}')
        add('')

    if run.ledger_instability:
        add('=' * W)
        add('LEDGER INSTABILITY — the primary record moved during the run')
        add('=' * W)
        for item in run.ledger_instability[:60]:
            add(f'  {item["date"]}  {item["path"]}: '
                f'{item["before"]} -> {item["after"]}')
        add('')

    mtd_failed = [c for c in run.mtd_checks
                  if c['status'] == rec.Status.UNRECONCILED]
    if mtd_failed:
        add('=' * W)
        add('MONTH-TO-DATE (RC20) — the running total does not equal the days')
        add('=' * W)
        for check in mtd_failed:
            add(f'  {check["date"]}  engine {check["engine"]}  vs  '
                f'sum of days {check["ledger"]}')
        add('')

    # -- per-date table --------------------------------------------------
    add('=' * W)
    add('DATES')
    add('=' * W)
    add(f'{"DATE":<12}{"STATE":<9}{"PAY":>5}{"CHG":>5}{"TAX":>5}{"NGT":>5}  '
        f'{"LEDGER":>7}{"ENGINE":>7}{"RECON":>7}{"UNREC":>6}{"DRIFT":>6}'
        f'{"ms":>7}')
    add('-' * W)
    quiet_dates: list = []
    for d in run.dates:
        interesting = (d.traded or d.is_closed or d.is_business_date
                       or d.unreconciled or d.asat_drift or d.history_drift
                       or d.engine_errors or d.order_mismatch)
        if not interesting:
            quiet_dates.append(d.date)
            continue
        state = ('TODAY' if d.is_business_date
                 else 'CLOSED' if d.is_closed else 'open')
        counted = d.row_counts
        reconciled = sum(1 for r in d.reconciliations
                         if r.status == rec.Status.RECONCILED)
        add(f'{d.date:<12}{state:<9}'
            f'{counted.get("payments", 0):>5}{counted.get("charges", 0):>5}'
            f'{counted.get("tax_lines", 0):>5}{counted.get("night_rates", 0):>5}  '
            f'{len(d.ledger):>7}{len(d.engine):>7}{reconciled:>7}'
            f'{len(d.unreconciled):>6}{len(d.asat_drift):>6}'
            f'{d.duration_ms:>7}')
    if quiet_dates:
        add('')
        add(f'  {len(quiet_dates)} further dates were replayed and carry no '
            f'primary record and no finding:')
        add(f'      {quiet_dates[0]} .. {quiet_dates[-1]}')
        add('  They are present in full in result.json. They are summarised')
        add('  here rather than omitted, because a day that later acquires a')
        add('  back-dated posting must be visible as a change against the')
        add('  stored replay.')
    add('')

    # -- declared gaps ---------------------------------------------------
    add('=' * W)
    add('NOT REPLAYABLE — engine entry points with no historical form')
    add('=' * W)
    add('These publish a figure for "now" and cannot answer for a past date.')
    add('Any report showing one of them under a historical heading is showing')
    add('today\'s number.')
    for item in run.not_replayable:
        add(f'  {item["entry_point"]}')
        add(f'      {item["reason"]}')
    add('')

    add('=' * W)
    add('AS-AT COMPARISON EXCLUSIONS')
    add('=' * W)
    if not run.asat_exclusions:
        add('  None.')
    for item in run.asat_exclusions:
        hits = sum(d.asat_exclusion_hits.get(item['path'], 0)
                   for d in run.dates)
        add(f'  {item["path"]}   (matched on {hits} date(s))')
        add(f'      {item["why"]}')
    add('')

    if run.timeline_excluded or run.timeline_window_notes:
        add('=' * W)
        add('REPLAY WINDOW')
        add('=' * W)
        for item in run.timeline_window_notes:
            add(f'  INCLUDED  {item["date"]}')
            add(f'      {item["reason"]}')
        for item in run.timeline_excluded:
            add(f'  EXCLUDED  {item["date"]}')
            add(f'      {item["reason"]}')
        add('')

    if run.date_insensitive:
        add('=' * W)
        add(f'DATE-INSENSITIVE ENGINE FIGURES ({len(run.date_insensitive)})')
        add('=' * W)
        add(f'Held the same value on all {counts["dates"]} replayed dates. A')
        add('date-scoped figure that never moves is either genuinely constant')
        add('or not date-scoped at all — a present-tense number published')
        add('under a historical heading. Informational: the framework states')
        add('the fact, the judgement is an engineering one.')
        for item in run.date_insensitive[:80]:
            add(f'  {item["path"]:<64} = {item["value"]}')
        if len(run.date_insensitive) > 80:
            add(f'  ... {len(run.date_insensitive) - 80} more '
                f'(see result.json)')
        add('')

    uncovered = sorted({path for d in run.dates for path in d.unreconciled_paths})
    add('=' * W)
    add(f'ENGINE FIGURES NOT COVERED BY A DECLARED RECONCILIATION '
        f'({len(uncovered)})')
    add('=' * W)
    add('The framework\'s own coverage gap. These figures are captured and')
    add('compared between runs, but nothing checks them against the primary')
    add('record. Listed in full so the declared mapping cannot quietly stop')
    add('keeping up with the application.')
    for path in uncovered[:120]:
        add(f'  {path}')
    if len(uncovered) > 120:
        add(f'  ... {len(uncovered) - 120} more (see result.json)')
    add('')

    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def render_comparison(result, run) -> str:
    L: list[str] = []
    add = L.append
    add('=' * W)
    add('FINALGRID — HISTORICAL REPLAY VERIFICATION')
    add('Production Verification Framework, Wave 0 Deliverable 3')
    add('=' * W)
    add(f'Stored replay     : {result.tag}')
    add(f'Stored captured   : {result.stored_captured_at} '
        f'(app v{result.stored_app_version})')
    add(f'Current run       : {run.started_at} (app v{run.app_version})')
    add(f'Business date     : {result.stored_business_date} -> '
        f'{result.current_business_date}')
    add(f'Read-only         : '
        f'{"VERIFIED" if run.read_only_verified else "NOT VERIFIED"}')
    add('')
    add(f'Dates compared    : {result.dates_compared}')
    add(f'Dates clean       : {result.dates_clean}')
    add(f'Differences       : {len(result.differences)}')
    add(f'Blocking          : {len(result.blocking)}')
    add('')
    add(f'VERDICT           : {result.verdict}')
    add('')

    if result.by_kind:
        add('-' * W)
        add('DIFFERENCES BY KIND')
        add('-' * W)
        for kind, n in sorted(result.by_kind.items()):
            add(f'  {kind:<28} {n:>5}')
        add('')

    if result.differences:
        add('=' * W)
        add('DIFFERENCES')
        add('=' * W)
        add('Severity follows the state of the day: a closed day may not move')
        add('at all, an open past day may move but is reported, and the')
        add('current business date is expected to move.')
        current_date = None
        shown = 0
        for d in result.differences:
            if shown >= 400:
                add(f'  ... {len(result.differences) - shown} more '
                    f'(see result.json — nothing is omitted there)')
                break
            if d.date != current_date:
                current_date = d.date
                add('')
                add(f'{d.date}   [{d.day_state}]')
            line = f'    [{d.severity:<5}] {d.kind:<26}'
            if d.key:
                line += f' {d.key}'
            add(line)
            if d.stored or d.current:
                add(f'            stored : {d.stored}')
                add(f'            current: {d.current}'
                    + (f'   (delta {d.delta})' if d.delta else ''))
            shown += 1
        add('')
    else:
        add('  No differences. Every replayed date reconstructs exactly as it')
        add('  did when the stored replay was taken.')
        add('')

    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def replay_payload(run) -> dict:
    payload = asdict(run)
    payload['counts'] = run.counts
    payload['overall'] = run.overall
    payload['blocking'] = run.blocking
    return payload


def comparison_payload(result, run) -> dict:
    return {
        'tag': result.tag,
        'verdict': result.verdict,
        'stored_captured_at': result.stored_captured_at,
        'stored_app_version': result.stored_app_version,
        'current_app_version': run.app_version,
        'stored_business_date': result.stored_business_date,
        'current_business_date': result.current_business_date,
        'read_only_verified': run.read_only_verified,
        'dates_compared': result.dates_compared,
        'dates_clean': result.dates_clean,
        'difference_count': len(result.differences),
        'blocking_count': len(result.blocking),
        'by_kind': result.by_kind,
        'differences': [asdict(d) for d in result.differences],
    }
