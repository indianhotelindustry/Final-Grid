"""
The discrimination gate.

Why a dataset must be commissioned
----------------------------------
Under P9 a control that cannot fail is not a control. A dataset whose
declared expectations hold no matter what the system does is not a
regression dataset; it is decoration that reports PASS forever and is
mistaken for evidence.

So every dataset is perturbed and required to break. The question is not
"do the expectations hold?" — that is the easy half, and a dataset asserting
``reservations_count = 0`` would satisfy it. The question is "do they stop
holding when the data stops being what the narrative says it is?"

The six elements
----------------
Each is pass or fail, each produces evidence, and a dataset failing any one
is ``NOT_COMMISSIONED``: reported in full, excluded from every verdict, and
excluded from certification. Same rule D4 applies to an uncommissioned
invariant and D5 to an uncommissioned fault.

``BUILD``            the dataset materialises on the real schema.
``POSITIVE``         every declared expectation is MET on the clean build.
                     A dataset whose expectations do not hold on its own
                     data is wrong before it is useful.
``PERTURBATION``     the perturbation actually changes rows. A zero-change
                     perturbation would show the expectations "surviving"
                     it and credit the dataset with a discrimination it
                     never demonstrated — the same refusal D5 applies to a
                     zero-change injection.
``DISCRIMINATION``   every target named in ``perturbation_breaks`` is UNMET
                     after the perturbation. This is the element the gate
                     exists for.
``ACTIVATION``       every invariant named in ``activates_invariants`` is
                     no longer VACUOUS on this dataset. A dataset that
                     claims to give a control a population and does not is
                     making the one claim nobody would check by hand.
``ISOLATION``        production is byte-identical throughout. Verified per
                     dataset rather than once per run, so a breach can be
                     attributed to the dataset that caused it.

What this module does not do
----------------------------
It does not repair a dataset that fails, and it does not weaken an
expectation to make one pass. A declaration that cannot discriminate is a
finding about the declaration.
"""
from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass, field

from verification.datasets import builder, evaluate, registry
from verification.datasets.model import Commissioning, Status

#: The six elements, in the order they are established. Order matters:
#: there is no point asking whether a perturbation discriminates if the
#: dataset never built.
ELEMENTS = ('BUILD', 'POSITIVE', 'PERTURBATION', 'DISCRIMINATION',
            'ACTIVATION', 'ISOLATION')


@dataclass
class ElementOutcome:
    """One commissioning element and the evidence for its verdict."""
    element: str
    passed: bool = False
    detail: str = ''
    #: Set when the element could not be reached because an earlier one
    #: failed. Never counted as a pass.
    skipped: bool = False


@dataclass
class DatasetCommissioning:
    """The commissioning record for one dataset."""
    dataset_id: str
    version: str
    title: str
    elements: list = field(default_factory=list)
    declared_status: str = Commissioning.NOT_COMMISSIONED
    content_hash: str = ''
    duration_seconds: float = 0.0
    error: str = ''

    @property
    def key(self) -> str:
        return f'{self.dataset_id}@{self.version}'

    @property
    def failed(self) -> list:
        return [e for e in self.elements if not e.passed and not e.skipped]

    @property
    def skipped(self) -> list:
        return [e for e in self.elements if e.skipped]

    @property
    def status(self) -> str:
        if self.error:
            return Commissioning.NOT_COMMISSIONED
        if self.failed or self.skipped:
            return Commissioning.NOT_COMMISSIONED
        return (Commissioning.COMMISSIONED if self.elements
                else Commissioning.NOT_COMMISSIONED)

    @property
    def claim_is_backed(self) -> bool:
        """Does a ``COMMISSIONED`` declaration match what was demonstrated?

        A declaration claiming COMMISSIONED that this run could not back is
        the dangerous case: it would be counted as evidence on every future
        run without anyone re-checking it.
        """
        if self.declared_status != Commissioning.COMMISSIONED:
            return True
        return self.status == Commissioning.COMMISSIONED


@dataclass
class CommissioningRun:
    started_at: str = ''
    duration_seconds: float = 0.0
    results: list = field(default_factory=list)
    registered: int = 0

    @property
    def commissioned(self) -> list:
        return [r for r in self.results
                if r.status == Commissioning.COMMISSIONED]

    @property
    def not_commissioned(self) -> list:
        return [r for r in self.results
                if r.status != Commissioning.COMMISSIONED]

    @property
    def unbacked_claims(self) -> list:
        return [r for r in self.results if not r.claim_is_backed]

    @property
    def verdict(self) -> str:
        """PASS, FAIL, INCOMPLETE or ERROR.

        An empty registry is INCOMPLETE, never PASS. Nothing was
        demonstrated, and reporting a platform with no datasets as passing
        would be silence presented as evidence — the one thing P10 forbids.
        """
        if any(r.error for r in self.results):
            return 'ERROR'
        if not self.results:
            return 'INCOMPLETE'
        if self.unbacked_claims or self.not_commissioned:
            return 'FAIL'
        return 'PASS'

    @property
    def exit_code(self) -> int:
        return {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2, 'ERROR': 3}[
            self.verdict]


def _unmet_targets(result) -> set:
    return {o.target for o in result.outcomes if o.status == Status.UNMET}


def _met_targets(result) -> set:
    return {o.target for o in result.outcomes if o.status == Status.MET}


def commission_one(d, quiet: bool = False) -> DatasetCommissioning:
    """Put one dataset through all six elements."""
    started = time.perf_counter()
    record = DatasetCommissioning(dataset_id=d.dataset_id, version=d.version,
                                  title=d.title,
                                  declared_status=d.commissioning_status)

    def outcome(element, passed, detail, skipped=False):
        record.elements.append(ElementOutcome(element, passed, detail,
                                              skipped))

    def skip_rest(from_index, reason):
        for element in ELEMENTS[from_index:]:
            outcome(element, False, reason, skipped=True)

    if d.not_materialisable_reason:
        outcome('BUILD', False,
                f'declared not materialisable: {d.not_materialisable_reason} '
                f'(tracked against {d.covered_by_deliverable})')
        skip_rest(1, 'the dataset does not build')
        record.duration_seconds = time.perf_counter() - started
        return record

    # -- 1. BUILD ---------------------------------------------------------
    clean = builder.build(d)
    if not clean.ok:
        outcome('BUILD', False, clean.error or 'the dataset did not build')
        skip_rest(1, 'the dataset did not build')
        record.duration_seconds = time.perf_counter() - started
        return record
    record.content_hash = clean.content_hash
    outcome('BUILD', True,
            f'{clean.rows_inserted} rows into {len(clean.tables_touched)} '
            f'tables, content hash {clean.content_hash[:12]}')

    try:
        # -- 2. POSITIVE --------------------------------------------------
        before = evaluate.evaluate(d, clean)
        unmet = [f'{o.element}/{o.target}' for o in before.outcomes
                 if o.status != Status.MET]
        if unmet:
            outcome('POSITIVE', False,
                    f'{len(unmet)} expectation(s) not met on the clean '
                    f'build: {", ".join(sorted(unmet)[:6])}')
            skip_rest(2, 'the expectations do not hold on the clean dataset')
            return record
        outcome('POSITIVE', True,
                f'all {len(before.outcomes)} declared expectation(s) met')

        # -- 5. ACTIVATION (measured on the clean build) ------------------
        # Evaluated here because activation is a property of the dataset as
        # declared, not of the perturbed copy. Reported in element order.
        activation_ok = not before.still_vacuous
        activation_detail = (
            f'{len(d.activates_invariants)} claim(s) verified'
            if activation_ok else
            'still VACUOUS after building: '
            + ', '.join(sorted(before.still_vacuous)))

        # -- 3. PERTURBATION ----------------------------------------------
        perturbed = builder.build(d, slot='_perturbed')
        if not perturbed.ok:
            outcome('PERTURBATION', False,
                    perturbed.error or 'the perturbation copy did not build')
            skip_rest(3, 'no perturbed copy to evaluate')
            return record
        try:
            changed = builder.perturb(perturbed.db_path, d.perturbation)
            if not changed:
                outcome('PERTURBATION', False,
                        'the perturbation changed no rows. A zero-change '
                        'perturbation cannot demonstrate discrimination.')
                skip_rest(3, 'the perturbation changed nothing')
                return record
            outcome('PERTURBATION', True,
                    f'{changed} row(s) changed by '
                    f'{len(d.perturbation)} statement(s)')

            # -- 4. DISCRIMINATION ----------------------------------------
            after = evaluate.evaluate(d, perturbed)
            broke = _unmet_targets(after)
            declared = set(d.perturbation_breaks)
            survived = sorted(declared - broke)
            if survived:
                outcome('DISCRIMINATION', False,
                        f'{len(survived)} declared target(s) survived the '
                        f'perturbation: {", ".join(survived)}. The dataset '
                        f'does not discriminate on them.')
            else:
                collateral = sorted(broke - declared)
                detail = (f'all {len(declared)} declared target(s) broke')
                if collateral:
                    detail += (f'; {len(collateral)} further target(s) also '
                               f'broke: {", ".join(collateral[:6])}')
                outcome('DISCRIMINATION', True, detail)

            # -- 5. ACTIVATION -------------------------------------------
            outcome('ACTIVATION', activation_ok, activation_detail)

            # -- 6. ISOLATION --------------------------------------------
            isolated = clean.production_unchanged and \
                perturbed.production_unchanged
            outcome('ISOLATION', isolated,
                    'production byte-identical across both builds'
                    if isolated else
                    'PRODUCTION CHANGED during commissioning. Every result '
                    'for this dataset is void.')
        finally:
            builder.discard(perturbed)
    except Exception as exc:                                    # noqa: BLE001
        record.error = f'{type(exc).__name__}: {exc}'
    finally:
        builder.discard(clean)
        record.duration_seconds = time.perf_counter() - started

    return record


def run(ids: list | None = None, quiet: bool = False) -> CommissioningRun:
    """Commission every selected dataset.

    With no datasets registered this returns an empty run whose verdict is
    INCOMPLETE, which is the correct answer for a platform that has been
    wired but not yet given anything to prove.
    """
    started_at = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    clock = time.perf_counter()

    datasets = registry.select(ids=ids) if ids else registry.all_datasets()
    result = CommissioningRun(started_at=started_at,
                              registered=len(registry.all_datasets()))

    for d in datasets:
        if not quiet:
            print(f'[ds] commissioning {d.key} …')
        result.results.append(commission_one(d, quiet=quiet))

    result.duration_seconds = time.perf_counter() - clock
    return result


def payload(run_result: CommissioningRun) -> dict:
    return {
        'started_at': run_result.started_at,
        'duration_seconds': run_result.duration_seconds,
        'registered': run_result.registered,
        'verdict': run_result.verdict,
        'elements': list(ELEMENTS),

        # ``registry.unbacked_commissioning_claims()`` reads this key and
        # expects ``{'key': ..., 'checks': {name: bool}}`` per entry. The
        # shape is its contract, not ours; emitting anything else would make
        # every COMMISSIONED declaration read as unbacked forever. A skipped
        # element is False here, which is correct — it was not demonstrated.
        'outcomes': [
            {
                'key': r.key,
                'checks': {e.element: bool(e.passed) for e in r.elements},
            }
            for r in run_result.results
        ],
        'results': [
            {
                'dataset': r.key,
                'title': r.title,
                'status': r.status,
                'declared_status': r.declared_status,
                'claim_is_backed': r.claim_is_backed,
                'content_hash': r.content_hash,
                'duration_seconds': r.duration_seconds,
                'error': r.error,
                'elements': [
                    {'element': e.element, 'passed': e.passed,
                     'skipped': e.skipped, 'detail': e.detail}
                    for e in r.elements
                ],
            }
            for r in run_result.results
        ],
    }
