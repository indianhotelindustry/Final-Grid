"""
The coverage ledger — what a dataset adds, loses and changes.

Why this exists
---------------
``DS-ACT-INHOUSE`` was declared to resolve three golden-master surfaces
that production leaves UNRESOLVED. It did. It also **un-resolved four
others**, and nobody would have known: a dataset replaces the
transactional layer rather than adding to it (``builder.strip``), so
coverage over a dataset is never automatically a superset of coverage over
production. The loss was found by capturing masters by hand and counting.

Doing that by hand once is diligence. Relying on it is not a control. So
the three questions a dataset must answer become measurements:

===================  ======================================================
Coverage Added       what this dataset can exercise that production cannot
Coverage Lost        what production exercises that this dataset cannot
Coverage Changed     what both exercise, but differently — an invariant
                     that holds on production and is violated here, or
                     whose population moved
===================  ======================================================

And the fourth question, which is the one that actually catches mistakes:

    **Expected vs Unexpected.** A dataset declares the movement it intends.
    Movement it did not declare is reported separately, because an
    unexpected loss is how a dataset quietly stops covering something while
    still reporting PASS on everything it declared.

What is measured
----------------
Three layers.

**D1 parity quantities.** The verdict per quantity. A quantity is covered
when it actually compared something: ``VACUOUS`` agreed over an empty
population and ``NOT_IMPLEMENTED`` was never measured at all, so neither
counts (P10). ``DS-ACT-VOIDCN`` lifting ``Q11`` from VACUOUS to DIVERGED
is a coverage gain, and it is the movement that showed why D1 belonged
here: half that dataset's justification was a claim this ledger could not
check, and it had to be measured by hand.

**D2 surfaces.** Which golden-master surfaces resolve. A surface whose
resolver finds no entity is captured as UNRESOLVED and is not evidence of
anything.

**D4 invariants.** Status and population per invariant. Population is the
part that matters: an invariant holding over 28 reservations and one
holding over 0 are both ``HOLDS`` and only one of them proves anything
(P10). A drop to zero is a coverage loss even though nothing failed.

**D3 replay is not measured, and that is not a temporary gap.** Its unit
is a business date rather than an entity, and a dataset declares exactly
one date against production's 28. A delta over it would report a
catastrophic loss on every dataset ever written, which is noise dressed as
a finding. Stated rather than approximated — an approximated ledger is
worse than none, because it reads as complete.

Cost
----
A full measurement captures 158-odd surfaces through the application and
evaluates the whole invariant registry, twice. It is minutes, not seconds,
which is why this is its own command rather than part of ``ds-run``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

from verification.config import PROJECT_ROOT

#: Declaration keys a dataset may use in ``coverage_expectation``. Anything
#: else is refused at registration rather than silently ignored, because a
#: misspelled key would read as "expected nothing" and turn every real
#: movement into an unexpected one.
EXPECTATION_KEYS = (
    'surfaces_added', 'surfaces_lost',
    'invariants_activated', 'invariants_deactivated',
    'quantities_activated', 'quantities_deactivated',
)

#: D1 verdicts that mean the quantity measured nothing. A quantity that is
#: VACUOUS agreed over an empty population, and one that is
#: NOT_IMPLEMENTED was never measured at all; neither is coverage (P10).
#: Every other verdict — AGREED, SINGLE_SOURCE, DIVERGED, ERROR — means
#: something was actually compared.
UNCOVERED_VERDICTS = ('VACUOUS', 'NOT_IMPLEMENTED', '')


class CoverageError(RuntimeError):
    """A coverage measurement could not be taken. Never swallowed."""


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _probe(command: str, db_path: str, marker: str) -> dict:
    proc = subprocess.run(
        [sys.executable, '-m', 'verification', command,
         '--db', os.path.abspath(db_path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if marker not in proc.stdout:
        raise CoverageError(
            f'{command} produced no result for {db_path}.\n'
            f'stdout tail: {proc.stdout[-1200:]}\n'
            f'stderr tail: {proc.stderr[-1200:]}')
    return json.loads(proc.stdout.split(marker, 1)[1].strip())


#: A date embedded in a surface key, e.g. ``date_2026_06_15``.
_DATE_IN_KEY = re.compile(r'\d{4}_\d{2}_\d{2}')


def _normalise_dates(key: str) -> str:
    """Replace dates in a surface key with a placeholder.

    Report surfaces are pinned to the business date, so
    ``reports.flash_report__date_2026_05_28`` on production and
    ``reports.flash_report__date_2026_06_15`` on a dataset are the same
    surface at two dates, not one gained and one lost. Compared literally
    they produce six spurious additions and six spurious losses on every
    dataset — noise that would bury the real movement and train everyone
    to skim the ledger.

    Normalising the date and nothing else keeps the failure visible: a
    dataset on which the flash report does not resolve at all is still
    reported as a loss, because the normalised key is simply absent.
    """
    return _DATE_IN_KEY.sub('YYYY_MM_DD', key)


@dataclass
class Snapshot:
    """What one database can exercise."""
    label: str = ''
    #: Endpoints whose parameterised surface resolved to an entity.
    surfaces: set = field(default_factory=set)
    #: invariant id -> (status, population)
    invariants: dict = field(default_factory=dict)
    #: quantity id -> verdict
    quantities: dict = field(default_factory=dict)

    @property
    def populated_invariants(self) -> set:
        """Invariants with something in scope.

        A population of zero is VACUOUS however green the status looks, so
        it is not counted as covered.
        """
        return {iid for iid, (_status, population) in self.invariants.items()
                if population}

    @property
    def measured_quantities(self) -> set:
        """Quantities that actually compared something.

        The D1 equivalent of ``populated_invariants``: agreement over an
        empty population proves nothing, so VACUOUS and NOT_IMPLEMENTED
        are not coverage.
        """
        return {qid for qid, verdict in self.quantities.items()
                if verdict not in UNCOVERED_VERDICTS}

    def as_dict(self) -> dict:
        return {'label': self.label,
                'surfaces': sorted(self.surfaces),
                'surface_count': len(self.surfaces),
                'invariants': {k: {'status': v[0], 'population': v[1]}
                               for k, v in sorted(self.invariants.items())},
                'populated_invariant_count': len(self.populated_invariants),
                'quantities': dict(sorted(self.quantities.items())),
                'measured_quantity_count': len(self.measured_quantities)}


def measure(db_path: str, label: str = '') -> Snapshot:
    """Measure what *db_path* can exercise.

    Surfaces are keyed as captured — ``endpoint__resolver`` for a
    parameterised surface, the bare endpoint otherwise — and NOT collapsed
    to the endpoint. The first version of this module collapsed them, and
    got the answer wrong on the first dataset it was pointed at:
    ``main.reservation_folio`` has both a ``checked_out_reservation`` and
    an ``inhouse_reservation`` variant, so an endpoint-level set showed it
    as covered before and after and reported no gain, when in fact a
    variant that had never resolved began resolving.

    Collapsing also hides the dangerous direction: an endpoint keeps one
    working variant while another silently stops resolving, and the ledger
    reports no loss.

    Dates in the key are normalised — see ``_normalise_dates``.
    """
    captured = _probe('_gm_capture_json', db_path, '---GM-JSON---')
    surfaces = {_normalise_dates(key) for key in captured}

    evaluated = _probe('_inv_json', db_path, '---INV-JSON---')
    invariants = {
        iid: (str((entry or {}).get('status', '')),
              int((entry or {}).get('population', 0) or 0))
        for iid, entry in (evaluated.get('invariants') or {}).items()}

    measured = _probe('_measure', db_path, '---PVF-JSON---')
    quantities = {qid: str((entry or {}).get('verdict', ''))
                  for qid, entry in (measured or {}).items()}

    return Snapshot(label=label, surfaces=surfaces, invariants=invariants,
                    quantities=quantities)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@dataclass
class Delta:
    """The ledger for one dataset against a baseline."""
    baseline_label: str = ''
    dataset_label: str = ''

    surfaces_added: list = field(default_factory=list)
    surfaces_lost: list = field(default_factory=list)
    invariants_activated: list = field(default_factory=list)
    invariants_deactivated: list = field(default_factory=list)
    #: Covered by both, but the status or population moved.
    invariants_changed: list = field(default_factory=list)
    quantities_activated: list = field(default_factory=list)
    quantities_deactivated: list = field(default_factory=list)
    #: Measured by both, but the verdict moved.
    quantities_changed: list = field(default_factory=list)

    unexpected: list = field(default_factory=list)
    expected_but_absent: list = field(default_factory=list)

    @property
    def added_count(self) -> int:
        return (len(self.surfaces_added) + len(self.invariants_activated)
                + len(self.quantities_activated))

    @property
    def lost_count(self) -> int:
        return (len(self.surfaces_lost) + len(self.invariants_deactivated)
                + len(self.quantities_deactivated))

    @property
    def clean(self) -> bool:
        """Did coverage move exactly as the dataset said it would?

        ``expected_but_absent`` counts. A dataset that declared it would
        resolve a surface and did not has made a claim the ledger cannot
        support, which is the same class of error as an undeclared loss.
        """
        return not self.unexpected and not self.expected_but_absent

    def as_dict(self) -> dict:
        return {
            'baseline': self.baseline_label,
            'dataset': self.dataset_label,
            'coverage_added': {
                'surfaces': self.surfaces_added,
                'invariants': self.invariants_activated,
                'quantities': self.quantities_activated},
            'coverage_lost': {
                'surfaces': self.surfaces_lost,
                'invariants': self.invariants_deactivated,
                'quantities': self.quantities_deactivated},
            'coverage_changed': {
                'invariants': self.invariants_changed,
                'quantities': self.quantities_changed},
            'unexpected_movement': self.unexpected,
            'declared_but_not_observed': self.expected_but_absent,
            'verdict': 'AS_DECLARED' if self.clean else 'UNDECLARED_MOVEMENT',
        }


def compare(baseline: Snapshot, dataset: Snapshot,
            expectation: dict | None = None,
            declared_statuses: dict | None = None,
            declared_verdicts: dict | None = None) -> Delta:
    """Build the ledger, and classify every movement against *expectation*.

    ``declared_statuses`` is the dataset's ``expectations.invariants`` and
    ``declared_verdicts`` its ``expectations.parity``. Both are consulted
    rather than duplicated: a dataset that already says ``INV-A02: HOLDS``
    has declared the change from production's VIOLATED, and making it say
    so a second time in ``coverage_expectation`` would be two declarations
    of one intent that can drift apart.
    """
    delta = Delta(baseline_label=baseline.label,
                  dataset_label=dataset.label)

    delta.surfaces_added = sorted(dataset.surfaces - baseline.surfaces)
    delta.surfaces_lost = sorted(baseline.surfaces - dataset.surfaces)

    base_populated = baseline.populated_invariants
    ds_populated = dataset.populated_invariants
    delta.invariants_activated = sorted(ds_populated - base_populated)
    delta.invariants_deactivated = sorted(base_populated - ds_populated)

    for iid in sorted(base_populated & ds_populated):
        was_status, was_population = baseline.invariants[iid]
        now_status, now_population = dataset.invariants[iid]
        if was_status != now_status or was_population != now_population:
            delta.invariants_changed.append({
                'invariant': iid,
                'was': f'{was_status} over {was_population}',
                'now': f'{now_status} over {now_population}',
                'status_moved': was_status != now_status})

    base_measured = baseline.measured_quantities
    ds_measured = dataset.measured_quantities
    delta.quantities_activated = sorted(ds_measured - base_measured)
    delta.quantities_deactivated = sorted(base_measured - ds_measured)
    for qid in sorted(base_measured & ds_measured):
        if baseline.quantities[qid] != dataset.quantities[qid]:
            delta.quantities_changed.append({
                'quantity': qid,
                'was': baseline.quantities[qid],
                'now': dataset.quantities[qid]})

    expectation = expectation or {}
    declared = {key: set(expectation.get(key) or ()) for key in
                EXPECTATION_KEYS}
    observed = {
        'surfaces_added': set(delta.surfaces_added),
        'surfaces_lost': set(delta.surfaces_lost),
        'invariants_activated': set(delta.invariants_activated),
        'invariants_deactivated': set(delta.invariants_deactivated),
        'quantities_activated': set(delta.quantities_activated),
        'quantities_deactivated': set(delta.quantities_deactivated),
    }

    for key in EXPECTATION_KEYS:
        for item in sorted(observed[key] - declared[key]):
            delta.unexpected.append({'movement': key, 'target': item})
        for item in sorted(declared[key] - observed[key]):
            delta.expected_but_absent.append({'movement': key,
                                              'target': item})

    # A status change on a jointly-covered invariant is never silently
    # accepted: a rule that holds on production and is VIOLATED on a
    # dataset is either a defect the dataset was built to expose — in which
    # case expectations.invariants already declares it — or a surprise.
    declared_statuses = declared_statuses or {}
    for change in delta.invariants_changed:
        if not change['status_moved']:
            continue
        invariant_id = change['invariant']
        now_status = dataset.invariants[invariant_id][0]
        if declared_statuses.get(invariant_id) == now_status:
            continue                      # the dataset said so already
        delta.unexpected.append({'movement': 'invariant_status_changed',
                                 'target': invariant_id,
                                 'detail': f'{change["was"]} -> '
                                           f'{change["now"]}'})

    # The same rule for D1, for the same reason. A quantity that agrees on
    # production and diverges on a dataset has found something the
    # production population could not show — Q09 is exactly that — and it
    # is not allowed to pass unremarked.
    declared_verdicts = declared_verdicts or {}
    for change in delta.quantities_changed:
        quantity_id = change['quantity']
        if declared_verdicts.get(quantity_id) == change['now']:
            continue
        delta.unexpected.append({'movement': 'quantity_verdict_changed',
                                 'target': quantity_id,
                                 'detail': f'{change["was"]} -> '
                                           f'{change["now"]}'})
    return delta


def render(delta: Delta) -> str:
    """The ledger, as a human reads it."""
    out = []
    add = out.append
    add('=' * 78)
    add(f'COVERAGE LEDGER — {delta.dataset_label}')
    add(f'baseline: {delta.baseline_label}')
    add('=' * 78)

    add('')
    add(f'COVERAGE ADDED ({delta.added_count})')
    for name in delta.surfaces_added:
        add(f'  + surface    {name}')
    for name in delta.invariants_activated:
        add(f'  + invariant  {name}')
    for name in delta.quantities_activated:
        add(f'  + quantity   {name}')
    if not delta.added_count:
        add('  (none)')

    add('')
    add(f'COVERAGE LOST ({delta.lost_count})')
    for name in delta.surfaces_lost:
        add(f'  - surface    {name}')
    for name in delta.invariants_deactivated:
        add(f'  - invariant  {name}  (population fell to zero)')
    for name in delta.quantities_deactivated:
        add(f'  - quantity   {name}  (nothing left to compare)')
    if not delta.lost_count:
        add('  (none)')

    changed = len(delta.invariants_changed) + len(delta.quantities_changed)
    add('')
    add(f'COVERAGE CHANGED ({changed})')
    for change in delta.invariants_changed:
        marker = '!' if change['status_moved'] else ' '
        add(f'  {marker} {change["invariant"]:<10} {change["was"]} -> '
            f'{change["now"]}')
    for change in delta.quantities_changed:
        add(f'  ! {change["quantity"]:<10} {change["was"]} -> '
            f'{change["now"]}')
    if not changed:
        add('  (none)')

    add('')
    add('EXPECTED vs UNEXPECTED')
    if delta.clean:
        add('  every movement was declared, and every declared movement '
            'happened')
    for item in delta.unexpected:
        detail = f'  ({item["detail"]})' if item.get('detail') else ''
        add(f'  UNEXPECTED           {item["movement"]:<28} '
            f'{item["target"]}{detail}')
    for item in delta.expected_but_absent:
        add(f'  DECLARED, NOT SEEN   {item["movement"]:<28} '
            f'{item["target"]}')

    add('')
    add(f'VERDICT: {delta.as_dict()["verdict"]}')
    add('')
    add('Measured: D1 parity quantities, D2 golden-master surfaces,')
    add('D4 invariants. Not measured: D3 replay — its unit is a business')
    add('date rather than an entity, and a dataset declares one date, so a')
    add('delta over it would compare a single day against 28 and read as a')
    add('catastrophic loss on every dataset.')
    add('=' * 78)
    return '\n'.join(out)
