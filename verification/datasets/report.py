"""
Reports and evidence packs for D6.

``write_pack`` is imported from D2 rather than reimplemented, for the same
reason D5 imports it: one implementation of the evidence pack format means
one thing to change when Phase 2.6 §10 export is automated.

The registry report is written to be useful when it is **empty**. A report
that only makes sense once there is data cannot tell you whether the
platform works before you have any.
"""
from __future__ import annotations

from verification.golden.report import write_pack  # one implementation only
from verification.datasets import registry
from verification.datasets.model import (
    ALL_ORIGINS, ALL_PURPOSES, Commissioning,
)

W = 100

__all__ = ['write_pack', 'render_registry', 'registry_payload',
           'render_commission', 'commission_payload']


def _matrix(add, title, matrix, vocabulary):
    add('-' * W)
    add(title)
    add('-' * W)
    if not matrix:
        for term in vocabulary:
            add(f'  {term:<28} 0')
        return
    for term in vocabulary:
        entries = matrix.get(term, [])
        add(f'  {term:<28} {len(entries):>3}  '
            f'{", ".join(entries) if entries else ""}'.rstrip())


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def render_registry() -> str:
    L: list[str] = []
    add = L.append
    datasets = registry.all_datasets()

    add('=' * W)
    add('DSBC FRONTLINE — REGRESSION DATASET REGISTRY')
    add('Production Verification Framework, Wave 0 Deliverable 6')
    add('=' * W)
    add(f'Registered datasets : {len(datasets)}')
    add('')

    if not datasets:
        add('-' * W)
        add('EMPTY REGISTRY')
        add('-' * W)
        add('No dataset is declared. This is the expected state after D6')
        add('Step 1, which wires the platform and deliberately introduces no')
        add('business knowledge.')
        add('')
        add('The platform is nonetheless proved to work: this report ran, the')
        add('registry resolved, and the commissioning gate is reachable. What')
        add('it has not been shown to do is discriminate, because nothing has')
        add('been declared for it to discriminate on.')
        add('')
        add('An empty registry is reported INCOMPLETE by ds-run and')
        add('ds-commission, never PASS. A platform with no datasets has')
        add('demonstrated nothing, and reporting that as a pass would be')
        add('silence presented as evidence (P10).')
        add('')
        add('Declarations belong in:')
        add('  datasets_core.py        baseline narratives — an ordinary hotel')
        add('  datasets_activation.py  datasets that activate a silent control')
        add('')

    _matrix(add, 'PURPOSE MATRIX', registry.purpose_matrix(), ALL_PURPOSES)
    add('')
    _matrix(add, 'ORIGIN MATRIX', registry.origin_matrix(), ALL_ORIGINS)
    add('')

    add('-' * W)
    add('INVARIANT ACTIVATION — the reason this deliverable exists')
    add('-' * W)
    activation = registry.invariant_activation_matrix()
    unactivated = registry.unactivated_invariants()
    activated = {k: v for k, v in activation.items() if v}
    add(f'  Invariants with an activating dataset : {len(activated)} '
        f'of {len(activation)}')
    for invariant_id in sorted(activated):
        add(f'    {invariant_id:<12} activated by '
            f'{", ".join(activated[invariant_id])}')
    add('')
    add(f'  Invariants with no activating dataset : {len(unactivated)}')
    if unactivated:
        add('  ' + ', '.join(sorted(unactivated)))
        add('')
        add('  These are reported so the gap is tracked. An invariant with no')
        add('  dataset behind it is exercised only by whatever production')
        add('  happens to contain, which for a VACUOUS invariant is nothing.')
    add('')

    add('-' * W)
    add('COMMISSIONING')
    add('-' * W)
    gaps = registry.commissioning_gaps()
    # Returns (findings, evidence_pack). The pack is reported too, because
    # "no unbacked claims" means something different when it was decided
    # against no evidence at all.
    unbacked, evidence_pack = registry.unbacked_commissioning_claims()
    unbuildable = registry.unbuildable_datasets()

    add(f'  Datasets not commissioned    : {len(gaps)}')
    for gap in sorted(gaps, key=lambda g: g['key']):
        add(f'    {gap["key"]:<24} {gap["status"]:<20} {gap["reason"]}')

    add(f'  Unbacked COMMISSIONED claims : {len(unbacked)}')
    for claim in sorted(unbacked, key=lambda c: c['key']):
        add(f'    {claim["key"]:<24} {claim["reason"]}')
    if unbacked:
        add('    A claim this run could not back is counted as a failure, not')
        add('    as a pass. It would otherwise be trusted on every later run.')
    add(f'  Checked against              : '
        f'{evidence_pack or "no commissioning evidence pack"}')

    add(f'  Declared not materialisable  : {len(unbuildable)}')
    for item in sorted(unbuildable, key=lambda u: u['key']):
        add(f'    {item["key"]:<24} {item["reason"]} '
            f'(tracked against {item["covered_by"]})')
    add('')

    add('-' * W)
    add('COVERAGE LEDGER — mandatory for every dataset')
    add('-' * W)
    no_ledger, _pack = registry.datasets_without_coverage_ledger()
    add(f'  Datasets without a passing ledger : {len(no_ledger)}')
    for item in sorted(no_ledger, key=lambda i: i['key']):
        add(f'    {item["key"]:<24} {item["reason"]}')
    if no_ledger:
        add('')
        add('    A dataset can be COMMISSIONED and still cover less than')
        add('    production did. Commissioning asks whether the declared')
        add('    outcomes are right; only the ledger asks what the dataset')
        add('    can exercise at all. Twice now it has found movement that')
        add('    careful reading of a narrative did not.')
    add('')

    add('=' * W)
    add('END OF REGISTRY')
    add('=' * W)
    return '\n'.join(L) + '\n'


def registry_payload() -> dict:
    datasets = registry.all_datasets()
    unbacked, evidence_pack = registry.unbacked_commissioning_claims()
    return {
        'registered': len(datasets),
        'datasets': [d.as_dict() for d in datasets],
        'purpose_matrix': registry.purpose_matrix(),
        'origin_matrix': registry.origin_matrix(),
        'version_matrix': registry.version_matrix(),
        'invariant_activation_matrix': registry.invariant_activation_matrix(),
        'unactivated_invariants': registry.unactivated_invariants(),
        'unbuildable_datasets': registry.unbuildable_datasets(),
        'commissioning_gaps': registry.commissioning_gaps(),
        'unbacked_commissioning_claims': unbacked,
        'commissioning_evidence_pack': evidence_pack,
        'datasets_without_coverage_ledger':
            registry.datasets_without_coverage_ledger()[0],
    }


# ---------------------------------------------------------------------------
# Commissioning
# ---------------------------------------------------------------------------

def render_commission(run) -> str:
    L: list[str] = []
    add = L.append

    add('=' * W)
    add('DSBC FRONTLINE — REGRESSION DATASET COMMISSIONING')
    add('Production Verification Framework, Wave 0 Deliverable 6')
    add('=' * W)
    add(f'Started            : {run.started_at}')
    add(f'Duration           : {run.duration_seconds:.1f}s')
    add(f'Registered         : {run.registered}')
    add(f'Commissioned       : {len(run.commissioned)}')
    add(f'Not commissioned   : {len(run.not_commissioned)}')
    add(f'Unbacked claims    : {len(run.unbacked_claims)}')
    add(f'OVERALL VERDICT    : {run.verdict}')
    add('')

    if not run.results:
        add('-' * W)
        add('NOTHING TO COMMISSION')
        add('-' * W)
        add('No dataset is registered, so the gate ran against nothing.')
        add('')
        add('The verdict is INCOMPLETE rather than PASS. Under P9 a control')
        add('that has not been shown to fail is not a control, and a gate')
        add('that has never been given anything to reject has not been shown')
        add('to reject anything.')
        add('')
        add('This is the expected and correct state after D6 Step 1.')
        add('')
        add('=' * W)
        add('END OF REPORT')
        add('=' * W)
        return '\n'.join(L) + '\n'

    add('-' * W)
    add('THE SIX ELEMENTS')
    add('-' * W)
    add('  BUILD          the dataset materialises on the real schema')
    add('  POSITIVE       every declared expectation holds on the clean build')
    add('  PERTURBATION   the perturbation actually changes rows')
    add('  DISCRIMINATION every declared target breaks when it is applied')
    add('  ACTIVATION     every activation claim lifts its invariant out of')
    add('                 VACUOUS')
    add('  ISOLATION      production is byte-identical throughout')
    add('')

    for r in run.results:
        add('-' * W)
        flag = '' if r.status == Commissioning.COMMISSIONED else '   ** GAP **'
        add(f'{r.key}  [{r.status}]{flag}')
        add('-' * W)
        add(f'  {r.title}')
        if r.content_hash:
            add(f'  content hash : {r.content_hash[:16]}')
        if r.error:
            add(f'  ERROR        : {r.error}')
        if not r.claim_is_backed:
            add('  UNBACKED CLAIM: the declaration says COMMISSIONED and this')
            add('                  run could not demonstrate it.')
        for e in r.elements:
            mark = 'PASS' if e.passed else ('SKIP' if e.skipped else 'FAIL')
            add(f'  [{mark}] {e.element:<15} {e.detail}')
        add('')

    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def commission_payload(run) -> dict:
    from verification.datasets import commission
    return commission.payload(run)
