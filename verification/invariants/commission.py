"""
Commissioning — proving that every invariant is capable of failing.

Constitutional basis: P9 (a control that cannot fail is not a control)
and P11 (silence is never evidence).

An invariant that has only ever reported HOLDS has not been shown to
detect anything. It might be comparing a number to itself; it might be
querying a table that is always empty; its filter might exclude the very
rows it was written for. Until a seeded fault has made it fail, its
green result means nothing, and the engine treats it that way — an
uncommissioned invariant's result is reported but excluded from every
verdict.

The eight elements, per invariant
---------------------------------
The charter requires all eight, and each is a separate check with its own
pass or fail:

1. **Positive case** — on the clean baseline, the invariant evaluates
   without error and its status is recorded. (Note that HOLDS is not
   required: several invariants legitimately fail on live production
   data, and demanding a green baseline would mean deleting the findings
   to commission the finder.)
2. **Negative case** — with the fault applied, the invariant must report
   a violation it did not report before.
3. **Fault injection** — the fault itself: SQL against a disposable copy,
   or a patch on a canonical engine's return value inside the
   commissioning subprocess only.
4. **Detection verification** — the *right* invariant fired. Blast radius
   is recorded: other invariants firing is informative, but only the
   declared one counts.
5. **Evidence verification** — the failure carries an observed result,
   attributed objects and root-cause candidates. A detection that cannot
   be investigated is half a control.
6. **Repeatability** — the same evaluation, twice in the same process,
   returns the same thing.
7. **Determinism** — two independent processes over the same seeded
   database return the same thing.
8. **Order independence** — evaluating the registry in reverse order
   returns the same thing, so no invariant is leaving state behind that
   changes another's answer.

Elements 1–5 are specific to the invariant under test. Elements 6–8 are
measured for the whole registry on every seeded database, which makes
them stronger rather than weaker: a leak between two invariants is
detected on whichever run happens to expose it.

Two fault-injection routes
--------------------------
Most invariants are broken by mutating data. A few are internal
consistency checks — they assert that a canonical engine's own outputs
agree with each other — and no data mutation can break those, because
every input moves both sides together. For them the fault is injected at
the engine boundary: the returned value is perturbed inside the
commissioning subprocess. Production code is never touched and the
wrapper dies with the process.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field

from verification.config import PROJECT_ROOT, PVF_WORK_DIR
from verification.dbcopy import make_copy
from verification.invariants import registry
from verification.invariants.model import Commissioning, Status


class SeedDidNotApply(RuntimeError):
    """A seed's SQL ran cleanly but changed no rows.

    Inherited from D2 and D3, where exactly this produced a false alarm:
    a statement about a broken seed read as a statement about a broken
    control. Rowcount is asserted so the two can never be confused.
    """


ELEMENTS = ('positive_case', 'negative_case', 'fault_injection',
            'detection', 'evidence', 'repeatability', 'determinism',
            'order_independence')


@dataclass
class Outcome:
    invariant_id: str
    title: str
    route: str = ''                  # data seed / engine patch / none
    checks: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    baseline_status: str = ''
    baseline_violations: int = 0
    seeded_status: str = ''
    seeded_violations: int = 0
    rows_changed: int = 0
    blast_radius: list = field(default_factory=list)
    not_seedable_reason: str = ''

    @property
    def commissioned(self) -> bool:
        return bool(self.checks) and all(self.checks.values())

    @property
    def failed_elements(self) -> list:
        return [name for name, ok in self.checks.items() if not ok]


# ---------------------------------------------------------------------------
# Subprocess digest
# ---------------------------------------------------------------------------

def _evaluate_in_subprocess(db_path: str, patch: str = '') -> dict:
    args = [sys.executable, '-m', 'verification', '_inv_json', '--db', db_path]
    if patch:
        args += ['--patch', patch]
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    proc = subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True,
                          text=True, env=env)
    if '---INV-JSON---' not in proc.stdout:
        raise RuntimeError(
            f'Invariant subprocess produced no result.\n'
            f'stdout tail: {proc.stdout[-1500:]}\n'
            f'stderr tail: {proc.stderr[-1500:]}')
    return json.loads(proc.stdout.split('---INV-JSON---', 1)[1].strip())


def _apply(db_path: str, statements: tuple) -> int:
    conn = sqlite3.connect(db_path)
    try:
        changed = 0
        for statement in statements:
            cur = conn.execute(statement)
            changed += max(cur.rowcount, 0)
        conn.commit()
    finally:
        conn.close()
    if changed == 0:
        raise SeedDidNotApply(
            'seed SQL affected 0 rows — the fault was never injected, so '
            '"not detected" would be a statement about the seed, not about '
            'the invariant')
    return changed


def _digest_of(digest: dict, invariant_id: str) -> dict:
    return digest['invariants'].get(invariant_id, {})


# ---------------------------------------------------------------------------
# One invariant
# ---------------------------------------------------------------------------

def _commission_one(inv, base_db: str, baseline: dict,
                    verbose: bool) -> Outcome:
    out = Outcome(invariant_id=inv.invariant_id, title=inv.title)
    base_entry = _digest_of(baseline, inv.invariant_id)
    out.baseline_status = base_entry.get('status', '')
    out.baseline_violations = int(base_entry.get('violations', 0))

    # -- 1. positive case --------------------------------------------------
    # A green baseline is deliberately NOT required. Several invariants
    # legitimately fail on live production data — that is the point of the
    # engine — and demanding HOLDS here would mean deleting findings in
    # order to commission the thing that found them. What is required is
    # that the invariant EVALUATED: a status, a population, and no error.
    out.checks['positive_case'] = (
        out.baseline_status not in ('', Status.ERROR))
    out.notes['positive_case'] = (
        f'baseline status {out.baseline_status or "missing"} over '
        f'{base_entry.get("population", 0)} row(s), '
        f'{out.baseline_violations} violation(s)')

    if inv.not_seedable_reason and not (inv.negative_seed or
                                        inv.negative_patch):
        out.route = 'none'
        out.not_seedable_reason = inv.not_seedable_reason
        for element in ELEMENTS[1:]:
            out.checks[element] = False
            out.notes[element] = 'not seedable — see reason'
        return out

    # -- 3. fault injection ------------------------------------------------
    seeded_db = os.path.join(PVF_WORK_DIR,
                             f'pvf_inv_{inv.invariant_id.replace("-", "_")}.db')
    if os.path.exists(seeded_db):
        os.remove(seeded_db)
    shutil.copy2(base_db, seeded_db)

    patch = ''
    try:
        if inv.negative_patch:
            out.route = 'engine patch'
            target, key, delta = inv.negative_patch
            patch = f'{target}|{key}|{delta}'
            out.checks['fault_injection'] = True
            out.notes['fault_injection'] = (
                f'{target} return value {key!r} moved by {delta} inside the '
                f'commissioning subprocess only')
        else:
            out.route = 'data seed'
            out.rows_changed = _apply(seeded_db, inv.negative_seed)
            out.checks['fault_injection'] = True
            out.notes['fault_injection'] = (
                f'{out.rows_changed} row(s) changed by the declared seed')
    except SeedDidNotApply as exc:
        out.checks['fault_injection'] = False
        out.notes['fault_injection'] = f'SEED BROKEN — {exc}'
        for element in ELEMENTS[1:]:
            out.checks.setdefault(element, False)
            out.notes.setdefault(element, 'not reached — the seed did not bite')
        return out
    except Exception as exc:                             # noqa: BLE001
        out.checks['fault_injection'] = False
        out.notes['fault_injection'] = f'{type(exc).__name__}: {exc}'
        for element in ELEMENTS[1:]:
            out.checks.setdefault(element, False)
            out.notes.setdefault(element, 'not reached')
        return out

    try:
        seeded = _evaluate_in_subprocess(seeded_db, patch)
        confirm = _evaluate_in_subprocess(seeded_db, patch)
    except Exception as exc:                             # noqa: BLE001
        for element in ('negative_case', 'detection', 'evidence',
                        'repeatability', 'determinism', 'order_independence'):
            out.checks[element] = False
            out.notes[element] = f'{type(exc).__name__}: {exc}'
        return out

    entry = _digest_of(seeded, inv.invariant_id)
    out.seeded_status = entry.get('status', '')
    out.seeded_violations = int(entry.get('violations', 0))

    # -- 2. negative case / 4. detection -----------------------------------
    # An invariant already failing on live data cannot prove itself by a
    # status change, because it was already VIOLATED. It proves itself by
    # the violation count RISING — the seeded instance is a new one.
    if out.baseline_status == Status.VIOLATED:
        detected = out.seeded_violations > out.baseline_violations
        how = (f'already violated on live data; violations '
               f'{out.baseline_violations} -> {out.seeded_violations}')
    else:
        detected = out.seeded_status == Status.VIOLATED
        how = f'status {out.baseline_status} -> {out.seeded_status}'
    out.checks['negative_case'] = detected
    out.notes['negative_case'] = how
    out.checks['detection'] = detected
    out.notes['detection'] = (
        'the declared invariant fired' if detected else
        'the declared invariant did NOT fire')

    # blast radius — informative, never a pass condition
    for other_id, other in sorted(seeded['invariants'].items()):
        if other_id == inv.invariant_id:
            continue
        before = _digest_of(baseline, other_id)
        if (other.get('status') != before.get('status')
                or other.get('violations') != before.get('violations')):
            out.blast_radius.append(
                f'{other_id}: {before.get("status")}/'
                f'{before.get("violations")} -> {other.get("status")}/'
                f'{other.get("violations")}')

    # -- 5. evidence -------------------------------------------------------
    evidence = entry.get('evidence') or {}
    missing = []
    if not (evidence.get('observed_result') or '').strip():
        missing.append('observed_result')
    if detected and not evidence.get('affected_objects'):
        missing.append('affected_objects')
    if detected and not evidence.get('root_cause_candidates'):
        missing.append('root_cause_candidates')
    if not (evidence.get('timestamp') or '').strip():
        missing.append('timestamp')
    out.checks['evidence'] = not missing
    out.notes['evidence'] = (
        'evidence complete' if not missing
        else 'missing: ' + ', '.join(missing))

    # -- 6. repeatability (within one process) -----------------------------
    repeat = seeded['repeatability_mismatches']
    out.checks['repeatability'] = inv.invariant_id not in repeat
    out.notes['repeatability'] = (
        'identical on re-evaluation in the same process' if
        inv.invariant_id not in repeat else
        'differed when evaluated twice in the same process')

    # -- 7. determinism (across processes) ---------------------------------
    left = _digest_of(seeded, inv.invariant_id)
    right = _digest_of(confirm, inv.invariant_id)
    comparable = ('status', 'population', 'violations', 'affected_objects')
    same = all(left.get(k) == right.get(k) for k in comparable)
    out.checks['determinism'] = same
    out.notes['determinism'] = (
        'two independent processes agreed' if same else
        'two independent processes disagreed: '
        + ', '.join(f'{k} {left.get(k)!r} vs {right.get(k)!r}'
                    for k in comparable if left.get(k) != right.get(k)))

    # -- 8. order independence ---------------------------------------------
    order = seeded['order_mismatches']
    out.checks['order_independence'] = inv.invariant_id not in order
    out.notes['order_independence'] = (
        'unchanged when the registry was evaluated in reverse order'
        if inv.invariant_id not in order else
        'depends on the order the registry was evaluated in')

    return out


# ---------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------

def commission(ids: list | None = None, verbose: bool = True) -> int:
    """Commission every invariant. Returns 0 only if all pass."""
    os.makedirs(PVF_WORK_DIR, exist_ok=True)
    invariants = registry.select(ids=ids)

    if verbose:
        print('=' * 100)
        print('PVF D4 — FINANCIAL INVARIANT ENGINE COMMISSIONING')
        print('Principle 9: a control must be capable of failing.')
        print('Principle 11: silence is never evidence.')
        print('=' * 100)

    base_handle = make_copy(name='pvf_inv_commission_base.db')
    if verbose:
        print(f'baseline copy : {base_handle.copy_path}')
        print('evaluating clean baseline (subprocess)...')
    baseline = _evaluate_in_subprocess(base_handle.copy_path)
    if verbose:
        print(f'baseline      : {len(baseline["invariants"])} invariants '
              f'evaluated')
        print()

    outcomes: list[Outcome] = []

    # -- registry-wide null control ---------------------------------------
    null_db = os.path.join(PVF_WORK_DIR, 'pvf_inv_seed_NULL.db')
    if os.path.exists(null_db):
        os.remove(null_db)
    shutil.copy2(base_handle.copy_path, null_db)
    null_digest = _evaluate_in_subprocess(null_db)
    spurious = []
    for invariant_id, entry in sorted(null_digest['invariants'].items()):
        before = _digest_of(baseline, invariant_id)
        if (entry.get('status') != before.get('status')
                or entry.get('violations') != before.get('violations')):
            spurious.append(
                f'{invariant_id}: {before.get("status")}/'
                f'{before.get("violations")} -> {entry.get("status")}/'
                f'{entry.get("violations")}')
    null_control = Outcome(
        invariant_id='NULL-CONTROL',
        title='Identical data must produce identical results',
        route='none')
    null_control.checks = {'determinism': not spurious}
    null_control.notes = {
        'determinism': ('no invariant moved on unmutated data' if not spurious
                        else f'{len(spurious)} moved: '
                             + '; '.join(spurious[:5]))}
    if verbose:
        print('[NULL CONTROL] same data, no fault')
        print(f'    {"PASS" if not spurious else "FAIL"} — '
              f'{len(spurious)} spurious movements')
        print()

    zero_writes = int(baseline.get('total_writes', -1)) == 0
    write_control = Outcome(
        invariant_id='WRITE-CONTROL',
        title='The engine performs zero database writes',
        route='none')
    write_control.checks = {'evidence': zero_writes}
    write_control.notes = {
        'evidence': (f'{baseline.get("total_writes")} write statement(s) '
                     f'counted across the whole registry')}
    if verbose:
        print('[WRITE CONTROL] the engine must never write')
        print(f'    {"PASS" if zero_writes else "FAIL"} — '
              f'{baseline.get("total_writes")} writes counted')
        print()

    if verbose:
        print('[PER-INVARIANT] eight elements each')
    for inv in invariants:
        outcome = _commission_one(inv, base_handle.copy_path, baseline,
                                  verbose)
        outcomes.append(outcome)
        if verbose:
            flag = 'PASS' if outcome.commissioned else 'FAIL'
            detail = (outcome.notes.get('negative_case', '')
                      if outcome.commissioned
                      else 'failed: ' + ', '.join(outcome.failed_elements))
            print(f'    {flag} {outcome.invariant_id:<10} '
                  f'[{outcome.route:<12}] {detail}')

    outcomes.extend([null_control, write_control])

    passed = sum(1 for o in outcomes if o.commissioned)
    total = len(outcomes)

    if verbose:
        print()
        print('=' * 100)
        print(f'COMMISSIONING RESULT: {passed}/{total} '
              f'{"PASS" if passed == total else "FAIL"}')
        print('=' * 100)
        for o in outcomes:
            print(f'  {"PASS" if o.commissioned else "FAIL"}  '
                  f'{o.invariant_id:<14} {o.title[:64]}')
            for element in ELEMENTS:
                if element in o.checks:
                    print(f'        {"ok  " if o.checks[element] else "FAIL"} '
                          f'{element:<20} {o.notes.get(element, "")}')
            if o.blast_radius:
                print(f'        blast radius ({len(o.blast_radius)}): '
                      + '; '.join(o.blast_radius[:4]))
            if o.not_seedable_reason:
                print(f'        not seedable: {o.not_seedable_reason}')
        print()
        if passed != total:
            print('The engine is NOT fully commissioned. Every invariant that '
                  'failed above is reported by the engine but excluded from '
                  'its verdicts: an invariant that has never been shown to '
                  'fail cannot be relied upon to have passed.')

    _write_evidence(outcomes, passed, total)
    return 0 if passed == total else 1


def commissioned_ids(outcomes: list) -> list:
    return [o.invariant_id for o in outcomes if o.commissioned]


def _write_evidence(outcomes: list, passed: int, total: int) -> str:
    import datetime as _dt
    from dataclasses import asdict

    from verification.golden.report import write_pack

    started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    payload = {
        'commissioned': passed == total,
        'passed': passed,
        'total': total,
        'elements': list(ELEMENTS),
        'outcomes': [asdict(o) for o in outcomes],
    }
    lines = ['=' * 100,
             'DSBC FRONTLINE — FINANCIAL INVARIANT ENGINE COMMISSIONING',
             'Wave 0 Deliverable 4 — Principle 9 / Principle 11',
             '=' * 100,
             f'Result: {passed}/{total} '
             f'{"COMMISSIONED" if passed == total else "NOT COMMISSIONED"}',
             '']
    for o in outcomes:
        lines.append(f'[{"PASS" if o.commissioned else "FAIL"}] '
                     f'{o.invariant_id}  ({o.route})')
        lines.append(f'    {o.title}')
        for element in ELEMENTS:
            if element in o.checks:
                lines.append(f'      {"ok  " if o.checks[element] else "FAIL"} '
                             f'{element:<20} {o.notes.get(element, "")}')
        if o.blast_radius:
            lines.append(f'      blast radius: '
                         + '; '.join(o.blast_radius[:8]))
        if o.not_seedable_reason:
            lines.append(f'      not seedable: {o.not_seedable_reason}')
        lines.append('')
    text = '\n'.join(lines) + '\n'
    return write_pack(payload, text, 'inv_commission', started)
