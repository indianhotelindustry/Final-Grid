"""
Evidence, matrices and gap reporting for the fault injection platform.

Three audiences, three documents from the same run:

* ``result.json`` — machine-readable, what a release gate reads;
* ``report.txt`` — what an engineer reads;
* the **gap report** — the part that matters. For every fault a declared
  layer failed to attribute: what the fault was, which layer should have
  seen it, what it stayed silent about, and which reports would be wrong
  in production while the framework said nothing.

The reporting bias is deliberate and opposite to every other deliverable's.
D1 to D4 lead with what passed. D5 leads with what was **missed**, because
a fault injection platform that reports "38 of 40 detected" as a success
has buried its only genuinely valuable output on the second page.

The registry matrices print without touching a database, so the coverage
of the taxonomy can be reviewed independently of any particular run — and
so the question *which invariant does no fault challenge?* can be asked
without waiting twenty minutes for an answer.
"""
from __future__ import annotations

from dataclasses import asdict

from verification.golden.report import write_pack  # one implementation only
from verification.faults import registry
from verification.faults.model import (
    ALL_CATEGORIES, ALL_LAYERS, Detection, LAYER_COST_MS, SEVERITY_RANK,
    Severity,
)

W = 100

__all__ = ['write_pack', 'render_registry', 'render_run', 'render_gaps',
           'registry_payload', 'run_payload']


def _wrap(text: str, width: int = 88) -> list:
    words, lines, current = (text or '').split(), [], ''
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f'{current} {word}'.strip()
    if current:
        lines.append(current)
    return lines or ['']


# ---------------------------------------------------------------------------
# Registry documentation — no database required
# ---------------------------------------------------------------------------

def render_registry() -> str:
    L: list[str] = []
    add = L.append
    faults = registry.all_faults()
    severities = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
                  Severity.LOW]

    add('=' * W)
    add('FINALGRID — FAULT REGISTRY')
    add('Production Verification Framework, Wave 0 Deliverable 5')
    add('=' * W)
    add(f'Registered faults : {len(faults)}')
    add('')

    add('-' * W)
    add('CATEGORY MATRIX')
    add('-' * W)
    matrix = registry.category_matrix()
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
    add('LAYER MATRIX — how hard each verification layer has been challenged')
    add('-' * W)
    add('Read downwards this is coverage. Read as a comparison between rows')
    add('it is a statement about the PLATFORM, not about the layers: a layer')
    add('few faults point at is one this platform has barely tested.')
    add('')
    lmatrix = registry.layer_matrix()
    for layer in ALL_LAYERS:
        ids = sorted(lmatrix.get(layer, []))
        add(f'  {layer:<16} {len(ids):>3} fault(s)   '
            f'~{LAYER_COST_MS[layer] / 1000:.1f}s per probe')
        for line in _wrap(', '.join(ids) or '(none — this layer is never '
                                            'challenged by any fault)', 78):
            add(f'        {line}')
    add('')

    add('-' * W)
    add('METHOD MATRIX — where in the stack the defect is introduced')
    add('-' * W)
    mmatrix = registry.method_matrix()
    for method, ids in sorted(mmatrix.items()):
        add(f'  {method:<16} {len(ids):>3}  '
            + ', '.join(sorted(ids)[:14])
            + (' ...' if len(ids) > 14 else ''))
    add('')

    add('-' * W)
    add('INVARIANT CHALLENGE COVERAGE')
    add('-' * W)
    add('Which D4 invariants does an independently-declared fault make fire?')
    add('An invariant with no fault pointed at it is not unverified — it was')
    add('commissioned by its own negative seed. It is *singly* verified: its')
    add('only proof of failability is the one its own author wrote.')
    add('')
    coverage = registry.invariant_coverage()
    challenged = {k: v for k, v in coverage.items() if v}
    unchallenged = sorted(k for k, v in coverage.items() if not v)
    add(f'  challenged by a D5 fault   : {len(challenged)}/{len(coverage)}')
    for invariant_id in sorted(challenged):
        add(f'      {invariant_id:<12} {", ".join(sorted(challenged[invariant_id]))}')
    add('')
    add(f'  singly verified (own seed only) : {len(unchallenged)}')
    for line in _wrap(', '.join(unchallenged) or '(none)', 84):
        add(f'      {line}')
    add('')

    uncovered = registry.uncovered_faults()
    add('-' * W)
    add('UNCOVERED FAULTS — registered so the gap is tracked, not forgotten')
    add('-' * W)
    if not uncovered:
        add('  (none — every registered fault is expected to be detected by '
            'at least one layer)')
    for entry in uncovered:
        add(f'  {entry["fault_id"]:<12} {entry["title"]}')
        for line in _wrap(entry['reason'], 80):
            add(f'        {line}')
        add(f'        will be covered by: {entry["covered_by"]}')
    add('')

    gaps = registry.commissioning_gaps()
    add('-' * W)
    add('COMMISSIONING STATUS')
    add('-' * W)
    add(f'  declared COMMISSIONED     : {len(faults) - len(gaps)}')
    add(f'  not commissioned          : {len(gaps)}')
    for entry in gaps:
        add(f'      {entry["fault_id"]:<12} {entry["status"]:<18} '
            f'{entry["reason"][:52]}')
    add('')
    add('=' * W)
    return '\n'.join(L)


def registry_payload() -> dict:
    return {
        'faults': [f.as_dict() for f in registry.all_faults()],
        'category_matrix': registry.category_matrix(),
        'layer_matrix': registry.layer_matrix(),
        'method_matrix': registry.method_matrix(),
        'invariant_coverage': registry.invariant_coverage(),
        'uncovered': registry.uncovered_faults(),
        'commissioning_gaps': registry.commissioning_gaps(),
    }


# ---------------------------------------------------------------------------
# A platform run
# ---------------------------------------------------------------------------

_FLAG = {
    Detection.ATTRIBUTED: 'ATTR',
    Detection.UNATTRIBUTED: 'UNAT',
    Detection.MISSED: 'MISS',
    Detection.UNEXPECTED: 'unex',
    Detection.CORRECTLY_SILENT: ' -- ',
    Detection.NOT_RUN: ' ?  ',
    Detection.ERROR: 'ERR ',
}


def render_run(run) -> str:
    L: list[str] = []
    add = L.append
    counts = run.counts

    add('=' * W)
    add('FINALGRID — FAULT INJECTION PLATFORM RUN')
    add('Production Verification Framework, Wave 0 Deliverable 5')
    add('=' * W)
    add(f'Started         : {run.started_at}')
    add(f'Duration        : {run.duration_seconds:.1f}s')
    add(f'PVF             : v{run.pvf_version}')
    add(f'Mode            : {run.mode}')
    add(f'Layers swept    : {", ".join(run.layers_swept)} '
        f'({"parallel" if run.parallel else "serial"})')
    add(f'VERDICT         : {run.overall}')
    add('')

    add('-' * W)
    add('ISOLATION — verified, not asserted')
    add('-' * W)
    add(f'Production      : {run.production_db}')
    add(f'  sha256 before : {run.production_hash_before}')
    add(f'  sha256 after  : {run.production_hash_after}')
    add(f'  unchanged     : {run.cleanup.get("production_unchanged")}')
    add(f'Baseline sha256 : {run.baseline_hash}')
    add(f'  unchanged     : {run.cleanup.get("baseline_unchanged")}')
    add(f'Copies removed  : {run.cleanup.get("copies_removed")}')
    left = run.cleanup.get('copies_left_behind') or []
    add(f'Copies remaining: {len(left)}'
        + (f'  *** {", ".join(left[:4])} ***' if left else ''))
    add(f'Isolation       : {"VERIFIED" if run.isolation_verified else "*** NOT VERIFIED ***"}')
    add('')

    add('-' * W)
    add('SUMMARY')
    add('-' * W)
    add(f'  registered              : {counts["registered"]}')
    add(f'  challenged              : {counts["challenged"]}')
    add(f'  detected                : {counts["detected"]}')
    add(f'  MISSED                  : {counts["missed"]}')
    add(f'  errors                  : {counts["errors"]}')
    add(f'  uncovered (not injected): {counts["uncovered"]}')
    add('')
    add('  attributions per layer:')
    for layer in ALL_LAYERS:
        add(f'      {layer:<16} {counts.get(layer, 0):>3}')
    add('')

    add('-' * W)
    add('DETECTION MATRIX')
    add('-' * W)
    add('ATTR = attributed at the declared target      MISS = expected, silent')
    add('UNAT = moved, but not where declared          unex = undeclared layer moved')
    add(' --  = correctly silent (this is what makes attribution possible)')
    add('')
    add(f'{"FAULT":<11}{"SEV":<10}' + ''.join(f'{l.split("_")[0]:>7}'
                                              for l in run.layers_swept)
        + '   TITLE')
    for result in run.results:
        cells = {o.layer: _FLAG.get(o.detection, '?') for o in result.layers}
        add(f'{result.fault_id:<11}{result.severity:<10}'
            + ''.join(f'{cells.get(l, "  . "):>7}' for l in run.layers_swept)
            + f'   {result.title[:44]}')
    add('')

    add(render_gaps(run))

    add('-' * W)
    add('BLAST RADIUS — undeclared layers that moved')
    add('-' * W)
    add('Recorded, never counted as success. A platform in which every layer')
    add('moves for every fault can attribute nothing.')
    add('')
    noisy = [(r.fault_id, r.blast_radius) for r in run.results
             if r.blast_radius]
    if not noisy:
        add('  (none — every undeclared layer stayed correctly silent)')
    for fault_id, layers in noisy:
        add(f'  {fault_id:<12} {", ".join(layers)}')
    add('')

    errors = [r for r in run.results if r.error]
    if errors:
        add('-' * W)
        add('ERRORS — a fault that could not be exercised proves nothing')
        add('-' * W)
        for result in errors:
            add(f'  {result.fault_id:<12} {result.error[:80]}')
        add('')

    if run.uncovered:
        add('-' * W)
        add('UNCOVERED — no layer of the current framework can detect these')
        add('-' * W)
        for entry in run.uncovered:
            add(f'  {entry["fault_id"]:<12} {entry["title"]}')
            for line in _wrap(entry['reason'], 80):
                add(f'        {line}')
            add(f'        tracked against: {entry["covered_by"]}')
        add('')

    if run.unbacked_claims:
        add('-' * W)
        add('UNBACKED COMMISSIONING CLAIMS')
        add('-' * W)
        add('A fault declaring COMMISSIONED that the evidence does not '
            'support. A status')
        add('declared in code is a gate somebody can walk through without '
            'doing the work.')
        add('')
        for entry in run.unbacked_claims:
            add(f'  {entry["fault_id"]:<12} {entry["reason"]}')
        add('')

    add('=' * W)
    add(f'VERDICT: {run.overall}')
    if run.overall == 'FAIL':
        add('At least one fault went undetected by every layer that declared '
            'it would see it.')
    elif run.overall == 'INCOMPLETE':
        add('Every challenged fault was detected, but coverage is not '
            'complete: see the gap')
        add('report and the uncovered list above.')
    elif run.overall == 'UNVERIFIED':
        add('Isolation or commissioning evidence could not be established. '
            'No result in this')
        add('run may be relied upon, whatever the detection matrix says.')
    add('=' * W)
    return '\n'.join(L)


def render_gaps(run) -> str:
    """The findings. Printed before the passes, on purpose."""
    L: list[str] = []
    add = L.append
    add('-' * W)
    add('VERIFICATION GAPS — the output of this deliverable')
    add('-' * W)

    if not run.gaps:
        add('  (none — every declared layer attributed every fault it was '
            'expected to see)')
        add('')
        return '\n'.join(L)

    add('Each entry is a defect this framework would NOT catch in production,')
    add('or would notice without being able to say what happened.')
    add('')
    for result in sorted(run.gaps,
                         key=lambda r: SEVERITY_RANK.get(r.severity, 9)):
        add(f'  [{result.severity}] {result.fault_id}  {result.title}')
        for outcome in result.layers:
            if not outcome.expected or outcome.detection == Detection.ATTRIBUTED:
                continue
            add(f'      {outcome.layer:<16} {outcome.detection}')
            if outcome.missing_targets:
                for line in _wrap('did not move: '
                                  + ', '.join(outcome.missing_targets), 74):
                    add(f'          {line}')
            if outcome.signal_moved:
                add(f'          moved elsewhere: '
                    f'{", ".join(outcome.moved_keys[:6])}'
                    + (' ...' if len(outcome.moved_keys) > 6 else ''))
            if outcome.error:
                add(f'          error: {outcome.error.splitlines()[0][:66]}')
        detected = result.evidence.detected_by
        add(f'      caught anyway by: '
            + (', '.join(detected) if detected else
               'NOTHING — this defect is invisible to the framework'))
        for line in _wrap('reports affected in production: '
                          + (', '.join(result.evidence.affected_reports[:6])
                             or 'not established by this run'), 74):
            add(f'      {line}')
        for line in _wrap('where to look: '
                          + ', '.join(result.evidence.root_cause_candidates),
                          74):
            add(f'      {line}')
        add('')
    return '\n'.join(L)


def run_payload(run) -> dict:
    return {
        'started_at': run.started_at,
        'finished_at': run.finished_at,
        'duration_seconds': run.duration_seconds,
        'pvf_version': run.pvf_version,
        'mode': run.mode,
        'layers_swept': list(run.layers_swept),
        'parallel': run.parallel,
        'verdict': run.overall,
        'counts': run.counts,
        'isolation': {
            'production_db': run.production_db,
            'production_hash_before': run.production_hash_before,
            'production_hash_after': run.production_hash_after,
            'baseline_hash': run.baseline_hash,
            'verified': run.isolation_verified,
            'cleanup': run.cleanup,
        },
        'results': [asdict(r) | {'detected': r.detected,
                                 'gaps': r.gaps,
                                 'blast_radius': r.blast_radius}
                    for r in run.results],
        'gaps': [r.fault_id for r in run.gaps],
        'undetected': [r.fault_id for r in run.undetected],
        'uncovered': run.uncovered,
        'commissioning_gaps': run.commissioning_gaps,
        'unbacked_claims': run.unbacked_claims,
        'commissioning_evidence_pack': run.commissioning_evidence_pack,
    }
