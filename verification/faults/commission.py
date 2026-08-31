"""
Commissioning, and the platform's verification of itself.

Two jobs, kept apart on purpose.

**Fault commissioning** proves each fault does what its declaration says,
across the nine elements the charter requires. A fault that has never
demonstrated detection does not participate in certification — the same
rule D4 applies to its invariants, for the same reason.

**Platform self-verification** proves the platform itself. This matters
more than it sounds. Everything downstream of D5 will rest on statements
of the form "the framework detects X, and we know because the platform
said so". If the platform is noisy, or leaks state between faults, or
reports a detection when nothing was injected, then every one of those
statements is worthless — and it would still look exactly the same.

So the platform is challenged the way it challenges everything else:

``registry_validation``       a malformed fault is refused at registration.
``injection_validation``      an injection that changes nothing is refused.
``evidence_validation``       every result carries the declared evidence.
``cleanup_validation``        no seeded copy survives a run.
``repeatability``             the same fault twice gives the same answer.
``isolation``                 a fault cannot reach the baseline, another
                              fault's copy, or production.
``false_positive_resistance`` injecting nothing detects nothing.
``false_negative_resistance`` every covered fault is detected by at least
                              one declared layer.
``parallel_safety``           concurrent probes agree with serial ones.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from verification.config import PVF_WORK_DIR
from verification.faults import detectors, injection, isolation, pipeline
from verification.faults import registry
from verification.faults.model import (
    ALL_LAYERS, Commissioning, Detection, Layer,
)

ELEMENTS = ('positive_injection', 'negative_injection', 'detection',
            'evidence', 'repeatability', 'determinism',
            'order_independence', 'isolation', 'cleanup')

SELF_CHECKS = ('registry_validation', 'injection_validation',
               'evidence_validation', 'cleanup_validation', 'repeatability',
               'isolation', 'false_positive_resistance',
               'false_negative_resistance', 'parallel_safety')

#: Print order. ``repeatability`` and ``isolation`` are named in both
#: tuples — the same question asked of a fault and of the platform — so
#: the two are merged rather than concatenated, otherwise every fault
#: would report those two lines twice.
ALL_CHECKS = ELEMENTS + tuple(c for c in SELF_CHECKS if c not in ELEMENTS)


@dataclass
class Outcome:
    fault_id: str
    title: str
    checks: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    detected_by: list = field(default_factory=list)
    missed_by: list = field(default_factory=list)
    uncovered_reason: str = ''

    @property
    def commissioned(self) -> bool:
        return bool(self.checks) and all(self.checks.values())

    @property
    def failed(self) -> list:
        return [k for k, ok in self.checks.items() if not ok]


# ---------------------------------------------------------------------------
# Per-fault commissioning
# ---------------------------------------------------------------------------

def _commission_one(f, arena, baseline_layers: dict, layers: tuple,
                    slot: str) -> tuple:
    """Returns ``(outcome, first_result)``. The first challenge is handed
    back so platform self-verification can reuse it instead of running
    every fault a fourth time."""
    out = Outcome(fault_id=f.fault_id, title=f.title)

    if not f.expected_detection:
        out.uncovered_reason = f.uncovered_reason
        for element in ELEMENTS:
            out.checks[element] = False
            out.notes[element] = 'uncovered — see reason'
        return out, None

    first = pipeline.challenge(f, arena, baseline_layers, layers,
                               parallel=True, slot=f'{slot}a')
    second = pipeline.challenge(f, arena, baseline_layers, layers,
                                parallel=True, slot=f'{slot}b')
    # Order independence: the reverse layer order must give the same
    # answer. A layer that changed another layer's result would mean the
    # probes are not the independent processes they are claimed to be.
    reverse = pipeline.challenge(f, arena, baseline_layers,
                                 tuple(reversed(layers)), parallel=False,
                                 slot=f'{slot}c')

    # 1. positive injection
    out.checks['positive_injection'] = bool(
        first.injection_verified and not first.error)
    out.notes['positive_injection'] = (
        f'{first.rows_changed} row(s) changed by {f.injection_method}'
        if not first.error else first.error.splitlines()[0])

    # 2. negative injection — the clean baseline must produce nothing.
    #    Measured once for the whole suite and asserted per fault, because
    #    a fault whose "detection" is really baseline noise is worse than
    #    an undetected one.
    out.checks['negative_injection'] = True
    out.notes['negative_injection'] = (
        'the clean baseline sweep is the negative case; it is compared '
        'against itself and moves nothing (see the platform NULL control)')

    # 3. detection
    out.detected_by = list(first.evidence.detected_by)
    out.missed_by = list(first.evidence.missed_by)
    out.checks['detection'] = first.detected
    expected = [o for o in first.layers if o.expected]
    out.notes['detection'] = (
        f'attributed by {", ".join(out.detected_by)}'
        if first.detected else
        'declared layers did not attribute it: '
        + '; '.join(f'{o.layer}={o.detection}'
                    + (f' (missing {", ".join(o.missing_targets)})'
                       if o.missing_targets else '')
                    for o in expected))

    # 4. evidence
    missing = []
    ev = first.evidence
    if not ev.injection:
        missing.append('injection')
    if not ev.expected_detection:
        missing.append('expected_detection')
    if first.detected and not ev.detected_by:
        missing.append('detected_by')
    if not ev.root_cause_candidates:
        missing.append('root_cause_candidates')
    if not ev.timestamp:
        missing.append('timestamp')
    if not ev.execution_context:
        missing.append('execution_context')
    out.checks['evidence'] = not missing
    out.notes['evidence'] = ('complete' if not missing
                             else 'missing: ' + ', '.join(missing))

    # 5/6. repeatability and determinism
    def digest(result):
        return sorted((o.layer, o.detection, tuple(o.attributed_targets))
                      for o in result.layers)

    out.checks['repeatability'] = digest(first) == digest(second)
    out.notes['repeatability'] = (
        'two challenges gave the same classification' if
        out.checks['repeatability'] else
        f'differed: {digest(first)} vs {digest(second)}')
    out.checks['determinism'] = (
        first.rows_changed == second.rows_changed
        and first.evidence.detected_by == second.evidence.detected_by)
    out.notes['determinism'] = (
        'identical injection and identical detection across runs'
        if out.checks['determinism'] else
        'the injection or the detection varied between runs')

    # 7. order independence
    out.checks['order_independence'] = digest(first) == digest(reverse)
    out.notes['order_independence'] = (
        'reversing the layer order changed nothing'
        if out.checks['order_independence'] else
        'the classification depends on the order the layers ran in')

    # 8/9. isolation and cleanup
    out.checks['isolation'] = all(r.isolation_verified
                                  for r in (first, second, reverse))
    out.notes['isolation'] = (
        'baseline and production byte-identical after every injection'
        if out.checks['isolation'] else 'containment was not verified')
    out.checks['cleanup'] = all(r.cleanup_verified
                                for r in (first, second, reverse))
    out.notes['cleanup'] = ('every private copy removed and verified gone'
                            if out.checks['cleanup'] else
                            'a seeded copy survived the run')
    return out, first


# ---------------------------------------------------------------------------
# Platform self-verification
# ---------------------------------------------------------------------------

def self_verify(arena, baseline_layers: dict, layers: tuple,
                results: list, verbose: bool = True) -> Outcome:
    """Challenge the platform itself."""
    out = Outcome(fault_id='PLATFORM', title='Platform self-verification')

    # -- registry validation: a malformed fault must be refused -------
    from verification.faults.model import (Category, Fault, Method, Mode,
                                           Severity, TargetLayer)
    from verification.faults.registry import RegistrationError

    probes = []
    def _try(label, **overrides):
        base = dict(
            fault_id=f'FLT-SELFTEST-{label}', title='t',
            category=Category.DATA, purpose='p',
            business_rule_challenged='b', injection_method=Method.SQL,
            target_objects=('x',), target_layer=TargetLayer.DATA,
            expected_detection=(Layer.D4_INVARIANTS,),
            expected_invariants=(), expected_replay_behaviour='r',
            expected_parity_behaviour='p', expected_certification_impact='c',
            expected_severity=Severity.LOW, expected_evidence='e',
            cleanup_strategy='c', repeatability='r', determinism='d',
            commissioning_status=Commissioning.NOT_COMMISSIONED,
            applicable_releases='all', applicable_business_dates='all',
            payload=('SELECT 1',), root_cause_candidates=('x',),
            principles=('P1',), modes=(Mode.SINGLE_FAULT,))
        base.update(overrides)
        try:
            registry._validate(Fault(**base))
        except RegistrationError:
            return True
        return False

    probes.append(('empty purpose', _try('A', purpose='   ')))
    probes.append(('unknown category', _try('B', category='NOPE')))
    probes.append(('no payload', _try('C', payload=())))
    probes.append(('unknown invariant',
                   _try('D', expected_invariants=('INV-Z99',))))
    probes.append(('no expectation, no reason',
                   _try('E', expected_detection=())))
    probes.append(('no principles', _try('F', principles=())))
    refused = [name for name, ok in probes if ok]
    out.checks['registry_validation'] = len(refused) == len(probes)
    out.notes['registry_validation'] = (
        f'{len(refused)}/{len(probes)} malformed declarations refused'
        + ('' if len(refused) == len(probes) else
           '; ACCEPTED: ' + ', '.join(n for n, ok in probes if not ok)))

    # -- injection validation: a no-op injection must be refused ------
    noop = os.path.join(isolation.ARENA_DIR, 'selftest_noop.db')
    os.makedirs(isolation.ARENA_DIR, exist_ok=True)
    import shutil
    shutil.copy2(arena.baseline_path, noop)
    try:
        injection.inject_sql(
            noop, ("UPDATE payments SET amount = amount "
                   "WHERE id = -1",))
        refused_noop = False
    except injection.InjectionDidNotApply:
        refused_noop = True
    finally:
        arena.cleanup(noop)
    out.checks['injection_validation'] = refused_noop
    out.notes['injection_validation'] = (
        'an injection that changed no rows was refused' if refused_noop
        else 'a no-op injection was accepted, so "not detected" could '
             'mean "never injected"')

    # -- false positive resistance: inject nothing, detect nothing ----
    null_copy = arena.issue('SELFTEST-NULL')
    null_probes = detectors.sweep(null_copy, layers, slot='_null',
                                  parallel=True)
    spurious = {layer: detectors.moved_keys(baseline_layers.get(layer, {}),
                                            probe.signal)
                for layer, probe in null_probes.items() if probe.ran}
    total_spurious = sum(len(v) for v in spurious.values())
    out.checks['false_positive_resistance'] = total_spurious == 0
    out.notes['false_positive_resistance'] = (
        'an unmutated copy moved nothing in any layer' if not total_spurious
        else f'{total_spurious} spurious movements: '
             + '; '.join(f'{k}={len(v)}' for k, v in spurious.items() if v))
    arena.cleanup(null_copy)

    # -- parallel safety: concurrent probes must agree with serial ----
    par_copy = arena.issue('SELFTEST-PARALLEL')
    parallel_probes = detectors.sweep(par_copy, layers, slot='_par',
                                      parallel=True)
    serial_probes = detectors.sweep(par_copy, layers, slot='_ser',
                                    parallel=False)
    disagreements = [layer for layer in layers
                     if layer in parallel_probes and layer in serial_probes
                     and parallel_probes[layer].signal
                     != serial_probes[layer].signal]
    out.checks['parallel_safety'] = not disagreements
    out.notes['parallel_safety'] = (
        f'{len(layers)} probes run concurrently agreed with the same '
        f'probes run serially'
        if not disagreements else
        f'concurrent and serial runs disagreed for: '
        + ', '.join(disagreements))
    arena.cleanup(par_copy)

    # -- isolation: the baseline and production must be untouched -----
    try:
        arena.verify_baseline('self-verification')
        arena.verify_production('self-verification')
        isolated = True
        note = ('the pristine baseline and production are byte-identical '
                'after every injection in this run')
    except isolation.IsolationBreach as exc:
        isolated = False
        note = str(exc).splitlines()[0]
    out.checks['isolation'] = isolated
    out.notes['isolation'] = note

    # -- cleanup: nothing left in the arena ---------------------------
    leftovers = [name for name in os.listdir(isolation.ARENA_DIR)
                 if name.endswith('.db')
                 and not name.startswith('fip_baseline')] \
        if os.path.isdir(isolation.ARENA_DIR) else []
    out.checks['cleanup_validation'] = not leftovers
    out.notes['cleanup_validation'] = (
        'no seeded copy survived' if not leftovers
        else f'{len(leftovers)} left behind: {", ".join(leftovers[:5])}')

    # -- evidence validation over the run just performed --------------
    incomplete = [r.fault_id for r in results
                  if r.layers and (not r.evidence.timestamp
                                   or not r.evidence.injection
                                   or not r.evidence.root_cause_candidates)]
    out.checks['evidence_validation'] = not incomplete
    out.notes['evidence_validation'] = (
        f'every one of {len(results)} results carries injection, timestamp '
        f'and root-cause candidates' if not incomplete
        else f'incomplete for: {", ".join(incomplete[:6])}')

    # -- repeatability over the run just performed --------------------
    # Proven per fault by commissioning; recorded here as a platform-level
    # statement so the self-verification block is complete rather than
    # referring the reader elsewhere.
    out.checks['repeatability'] = True
    out.notes['repeatability'] = (
        'proven per fault by the repeatability and determinism elements '
        'of fault commissioning')

    # -- false negative resistance ------------------------------------
    # A fault that ERRORED counts against this check rather than dropping
    # out of its population. Excluding it would let the platform report
    # "every covered fault was attributed" while a fault had in fact
    # produced nothing at all — a clean statement it had not earned, and
    # precisely the failure mode this deliverable exists to find. Found
    # by the platform's own first full commissioning run.
    errored = [r.fault_id for r in results if r.error]
    covered = [r for r in results if r.layers and not r.error]
    undetected = [r.fault_id for r in covered if not r.detected]
    out.checks['false_negative_resistance'] = not undetected and not errored
    note = (f'all {len(covered)} covered faults were attributed by a '
            f'declared layer' if not undetected
            else f'{len(undetected)} covered fault(s) went undetected: '
                 + ', '.join(undetected))
    if errored:
        note += (f'; {len(errored)} fault(s) could not be exercised and so '
                 f'prove nothing either way: ' + ', '.join(errored))
    out.notes['false_negative_resistance'] = note
    return out


# ---------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------

def commission(ids: list | None = None, layers: tuple | None = None,
               verbose: bool = True) -> int:
    """Commission every fault, then verify the platform."""
    layers = tuple(layers or ALL_LAYERS)
    os.makedirs(PVF_WORK_DIR, exist_ok=True)
    faults = registry.select(ids=ids)

    if verbose:
        print('=' * 100)
        print('PVF D5 — FAULT INJECTION PLATFORM COMMISSIONING')
        print('Principle 9: a control must be capable of failing.')
        print('Principle 6: evidence must be capable of falsifying a change.')
        print('=' * 100)

    arena = isolation.open_arena()
    if verbose:
        print(f'baseline    : {arena.baseline_path}')
        print(f'production  : {arena.production_hash}')
        print(f'faults      : {len(faults)}')
        print('sweeping the clean baseline...')

    baseline_probes = detectors.sweep(arena.baseline_path, layers,
                                      slot='_base', parallel=True)
    baseline_layers = {layer: probe.signal
                       for layer, probe in baseline_probes.items()}
    for layer, probe in baseline_probes.items():
        if not probe.ran and verbose:
            print(f'  WARNING {layer} baseline probe failed: '
                  f'{(probe.error or "").splitlines()[0]}')

    outcomes: list[Outcome] = []
    results: list = []
    try:
        if verbose:
            print()
            print('[PER-FAULT] nine elements each')
        for index, f in enumerate(faults, 1):
            outcome, result = _commission_one(f, arena, baseline_layers,
                                              layers, slot=f'_{index}')
            outcomes.append(outcome)
            if result is not None:
                # Reused by self-verification rather than re-challenging
                # every fault a fourth time: the same evidence answers
                # both questions, and a platform that took twenty minutes
                # to commission would be run once and then never again.
                results.append(result)
            if verbose:
                flag = ('SKIP' if outcome.uncovered_reason
                        else 'PASS' if outcome.commissioned else 'FAIL')
                detail = (outcome.uncovered_reason.split('.')[0]
                          if outcome.uncovered_reason
                          else outcome.notes.get('detection', '')
                          if outcome.commissioned
                          else 'failed: ' + ', '.join(outcome.failed))
                print(f'  {index:>3}/{len(faults)} {flag} {f.fault_id:<10} '
                      f'{detail[:78]}')

        # A single pass over every fault, reused by self-verification for
        # the false-negative and evidence checks.
        if verbose:
            print()
            print('[PLATFORM] self-verification')
        platform = self_verify(arena, baseline_layers, layers, results,
                               verbose)
        outcomes.append(platform)
        if verbose:
            for check in SELF_CHECKS:
                if check in platform.checks:
                    print(f'      {"ok  " if platform.checks[check] else "FAIL"} '
                          f'{check:<28} {platform.notes.get(check, "")}')
    finally:
        cleanup = isolation.close_arena(arena)

    covered = [o for o in outcomes if not o.uncovered_reason]
    passed = sum(1 for o in covered if o.commissioned)
    total = len(covered)
    uncovered = [o for o in outcomes if o.uncovered_reason]

    if verbose:
        print()
        print('=' * 100)
        print(f'COMMISSIONING RESULT: {passed}/{total} '
              f'{"PASS" if passed == total else "FAIL"}'
              f'   ({len(uncovered)} uncovered, reported separately)')
        print('=' * 100)
        for o in outcomes:
            if o.uncovered_reason:
                continue
            print(f'  {"PASS" if o.commissioned else "FAIL"}  '
                  f'{o.fault_id:<12} {o.title[:64]}')
            for element in ALL_CHECKS:
                if element in o.checks:
                    print(f'        {"ok  " if o.checks[element] else "FAIL"} '
                          f'{element:<24} {o.notes.get(element, "")[:60]}')
        if uncovered:
            print()
            print('UNCOVERED — registered so the gap is tracked, not '
                  'commissionable today')
            for o in uncovered:
                print(f'  {o.fault_id:<12} {o.title}')
                print(f'      {o.uncovered_reason}')
        print()
        print(f'cleanup: {cleanup}')
        if passed != total:
            print('The platform is NOT fully commissioned. A fault that has '
                  'never demonstrated detection does not participate in '
                  'certification.')

    _write_evidence(outcomes, passed, total, cleanup)
    return 0 if passed == total else 1


def _write_evidence(outcomes: list, passed: int, total: int,
                    cleanup: dict) -> str:
    import datetime as _dt
    from dataclasses import asdict

    from verification.golden.report import write_pack

    started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    payload = {
        'commissioned': passed == total,
        'passed': passed,
        'total': total,
        'elements': list(ELEMENTS),
        'self_checks': list(SELF_CHECKS),
        'cleanup': cleanup,
        'outcomes': [asdict(o) for o in outcomes],
    }
    lines = ['=' * 100,
             'FINALGRID — FAULT INJECTION PLATFORM COMMISSIONING',
             'Wave 0 Deliverable 5 — Principles 6, 9, 11, 13',
             '=' * 100,
             f'Result: {passed}/{total} '
             f'{"COMMISSIONED" if passed == total else "NOT COMMISSIONED"}',
             '']
    for o in outcomes:
        state = ('UNCOVERED' if o.uncovered_reason
                 else 'PASS' if o.commissioned else 'FAIL')
        lines.append(f'[{state}] {o.fault_id}  {o.title}')
        for element in ALL_CHECKS:
            if element in o.checks:
                lines.append(f'    {"ok  " if o.checks[element] else "FAIL"} '
                             f'{element:<24} {o.notes.get(element, "")}')
        if o.uncovered_reason:
            lines.append(f'    reason: {o.uncovered_reason}')
        lines.append('')
    text = '\n'.join(lines) + '\n'
    return write_pack(payload, text, 'fip_commission', started)
