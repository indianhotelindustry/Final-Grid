"""
The dataset registry — registration, validation, versioning, taxonomy.

Extension point
---------------
A new dataset is one ``@dataset(...)`` declaration in a ``datasets_*``
module. No builder change, no evaluator change, no comparison table edit.

Versioning — charter element 1
------------------------------
A dataset is identified by ``dataset_id@version``, and both are part of
its identity. The same id at two versions is two datasets that coexist,
because a regression dataset's whole value is that a result obtained
last release can be compared with one obtained today — and that is
impossible if the dataset was edited underneath the comparison.

So editing a dataset in place is an error the registry cannot detect, and
the content hash is what makes it detectable anyway: a certificate names
the hash it was issued against, and a dataset whose content has moved
reports ``STALE`` rather than ``CERTIFIED``. The version is the
declaration; the hash is the proof.

Why registration validates
--------------------------
The same reason as D4 and D5, with one addition specific to data. A
fixture directory decays because nothing forces a fixture to say what it
proves. Registration therefore refuses:

* a duplicate ``id@version``;
* an unknown purpose, origin or mode;
* an empty narrative, or a timeline with no events;
* **an expectation set that declares nothing** — a dataset that asserts
  no outcome is a fixture, and this registry does not hold fixtures;
* an expectation naming an invariant, quantity or fault that does not
  exist in D4, D1 or D5;
* **an ``activates_invariants`` entry that is not also declared in
  ``expectations.invariants``** — claiming to lift an invariant out of
  VACUOUS without saying what it should then report is claiming the half
  of the job that cannot be checked;
* a missing perturbation, or a perturbation that declares nothing it
  should break. A dataset that cannot be shown to discriminate is
  decoration (P9);
* a provenance that claims real guest data with no disclosure statement.
"""
from __future__ import annotations

from verification.datasets.model import (
    ALL_MODES, ALL_ORIGINS, ALL_PURPOSES, Commissioning, Dataset,
)


class RegistrationError(ValueError):
    """A dataset declaration is not usable. Raised at import time."""


_REGISTRY: dict = {}

REQUIRED_TEXT_FIELDS = ('title', 'business_narrative', 'business_date',
                        'applicable_releases')


def _known_invariant_ids() -> set:
    from verification.invariants import registry as invreg
    return {i.invariant_id for i in invreg.all_invariants()}


def _known_quantity_ids() -> set:
    """The D1 parity quantities.

    ``quantities.REGISTRY`` is a list of tuples populated by the
    ``@quantity`` decorator at import; the id is the first element.
    """
    from verification import quantities
    return {entry[0] for entry in quantities.REGISTRY}


def _known_fault_ids() -> set:
    from verification.faults import registry as faultreg
    return {f.fault_id for f in faultreg.all_faults()}


def _validate(d: Dataset) -> None:
    if d.key in _REGISTRY:
        raise RegistrationError(
            f'Duplicate dataset {d.key!r}. Two datasets sharing an id and '
            f'version would make every certificate ambiguous.')
    if d.purpose not in ALL_PURPOSES:
        raise RegistrationError(f'{d.key}: unknown purpose {d.purpose!r}')
    if d.provenance.origin not in ALL_ORIGINS:
        raise RegistrationError(
            f'{d.key}: unknown origin {d.provenance.origin!r}')
    if not d.modes:
        raise RegistrationError(
            f'{d.key}: declares no execution modes, so nothing would run it')
    for mode in d.modes:
        if mode not in ALL_MODES:
            raise RegistrationError(f'{d.key}: unknown mode {mode!r}')
    for name in REQUIRED_TEXT_FIELDS:
        if not (getattr(d, name) or '').strip():
            raise RegistrationError(f'{d.key}: {name} is empty')
    if not d.timeline:
        raise RegistrationError(
            f'{d.key}: has no timeline. A dataset whose events nobody wrote '
            f'down is a fixture, and its expectations cannot be traced to '
            f'anything that happened.')
    if not d.principles:
        raise RegistrationError(
            f'{d.key}: names no constitutional principle')
    if not d.provenance.author or not d.provenance.derivation:
        raise RegistrationError(
            f'{d.key}: provenance must state an author and a derivation')
    if d.provenance.contains_real_guest_data and not d.provenance.disclosure:
        raise RegistrationError(
            f'{d.key}: declares real guest data and no disclosure statement. '
            f'A dataset carrying a real guest with no stated handling rule '
            f'is a data-protection incident waiting to be copied into a '
            f'ticket.')

    if d.not_materialisable_reason:
        if not d.covered_by_deliverable:
            raise RegistrationError(
                f'{d.key}: is declared not materialisable but names no '
                f'deliverable that will make it buildable, so the gap would '
                f'never be tracked.')
        return                      # the checks below assume a real build

    if not d.rows:
        raise RegistrationError(
            f'{d.key}: declares no rows and is not marked unbuildable. It '
            f'would materialise as an empty hotel while claiming a '
            f'narrative.')
    if not d.expectations.total():
        raise RegistrationError(
            f'{d.key}: declares no expectation of any kind. A dataset that '
            f'asserts no outcome cannot fail, and a control that cannot '
            f'fail is not a control (P9).')
    if not d.perturbation:
        raise RegistrationError(
            f'{d.key}: declares no perturbation. Without one the dataset '
            f'can never be shown to discriminate — its expectations might '
            f'hold whatever the system does.')
    if not d.perturbation_breaks:
        raise RegistrationError(
            f'{d.key}: declares a perturbation but names nothing it should '
            f'break, so commissioning could not tell a discriminating '
            f'dataset from an inert one.')

    from verification.datasets import financials
    unknown_financial = financials.unknown_probes(d.expectations.financial)
    if unknown_financial:
        raise RegistrationError(
            f'{d.key}: declares financial expectation(s) with no probe to '
            f'measure them: {", ".join(unknown_financial)}. Known probes: '
            f'{", ".join(sorted(financials.PROBES))}')

    known_invariants = _known_invariant_ids()
    for invariant_id in d.expectations.invariants:
        if invariant_id not in known_invariants:
            raise RegistrationError(
                f'{d.key}: expects {invariant_id}, which is not in the D4 '
                f'registry.')
    for invariant_id in d.activates_invariants:
        if invariant_id not in known_invariants:
            raise RegistrationError(
                f'{d.key}: claims to activate {invariant_id}, which is not '
                f'in the D4 registry.')
        if invariant_id not in d.expectations.invariants:
            raise RegistrationError(
                f'{d.key}: claims to activate {invariant_id} but declares no '
                f'expected outcome for it. Lifting an invariant out of '
                f'VACUOUS without saying what it should then report is '
                f'claiming the half of the job that cannot be checked.')

    known_faults = _known_fault_ids()
    for fault_id in d.expectations.faults:
        if fault_id not in known_faults:
            raise RegistrationError(
                f'{d.key}: expects fault {fault_id}, which is not in the D5 '
                f'registry.')

    for surface, state in d.expectations.golden.items():
        if state not in ('RESOLVED', 'UNRESOLVED'):
            raise RegistrationError(
                f'{d.key}: golden expectation for {surface} is {state!r}. A '
                f'surface either resolved to an entity or it did not, so the '
                f'only declarable states are RESOLVED and UNRESOLVED.')

    known_quantities = _known_quantity_ids()
    if known_quantities:
        for quantity_id in d.expectations.parity:
            if quantity_id not in known_quantities:
                raise RegistrationError(
                    f'{d.key}: expects quantity {quantity_id}, which is not '
                    f'in the D1 registry.')

    # A misspelled coverage key would read as "expected nothing" and turn
    # every real movement into an unexpected one, which is the failure mode
    # that makes a ledger noisy enough to be ignored.
    from verification.datasets.coverage import EXPECTATION_KEYS
    unknown_coverage = sorted(set(d.coverage_expectation) -
                              set(EXPECTATION_KEYS))
    if unknown_coverage:
        raise RegistrationError(
            f'{d.key}: coverage_expectation has unknown key(s): '
            f'{", ".join(unknown_coverage)}. Known: '
            f'{", ".join(EXPECTATION_KEYS)}')

    known_invariants_for_coverage = _known_invariant_ids()
    for key in ('invariants_activated', 'invariants_deactivated'):
        for invariant_id in d.coverage_expectation.get(key) or ():
            if invariant_id not in known_invariants_for_coverage:
                raise RegistrationError(
                    f'{d.key}: coverage_expectation.{key} names '
                    f'{invariant_id}, which is not in the D4 registry.')

    known_quantities_for_coverage = _known_quantity_ids()
    if known_quantities_for_coverage:
        for key in ('quantities_activated', 'quantities_deactivated'):
            for quantity_id in d.coverage_expectation.get(key) or ():
                if quantity_id not in known_quantities_for_coverage:
                    raise RegistrationError(
                        f'{d.key}: coverage_expectation.{key} names '
                        f'{quantity_id}, which is not in the D1 registry.')

    declared = set(d.perturbation_breaks)
    targets = (set(d.expectations.financial) | set(d.expectations.invariants)
               | set(d.expectations.replay) | set(d.expectations.parity)
               | set(d.expectations.faults))
    unknown = sorted(declared - targets)
    if unknown:
        raise RegistrationError(
            f'{d.key}: the perturbation claims to break {", ".join(unknown)}, '
            f'which this dataset does not declare an expectation for. It '
            f'would appear to discriminate while breaking nothing anyone '
            f'is measuring.')


def dataset(**declaration):
    """Declare and register a dataset."""
    def deco(fn=None):
        d = Dataset(**declaration)
        _validate(d)
        _REGISTRY[d.key] = d
        return fn
    return deco


def register(d: Dataset) -> Dataset:
    _validate(d)
    _REGISTRY[d.key] = d
    return d


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def load_all() -> None:
    from verification.datasets import (datasets_core,      # noqa: F401
                                       datasets_activation)


def all_datasets() -> list:
    load_all()
    return list(_REGISTRY.values())


def get(key: str):
    """Fetch by ``id@version``, or by id alone for the latest version."""
    load_all()
    if key in _REGISTRY:
        return _REGISTRY[key]
    versions = sorted((d for d in _REGISTRY.values()
                       if d.dataset_id == key),
                      key=lambda d: _version_key(d.version))
    if versions:
        return versions[-1]
    raise KeyError(
        f'No dataset {key!r}. Registered: {", ".join(sorted(_REGISTRY))}')


def _version_key(version: str) -> tuple:
    parts = []
    for piece in str(version).split('.'):
        parts.append(int(piece) if piece.isdigit() else 0)
    return tuple(parts)


def select(ids: list | None = None, purpose: str | None = None,
           mode: str | None = None, origin: str | None = None,
           include_unbuildable: bool = True) -> list:
    out = all_datasets()
    if ids:
        wanted = set(ids)
        out = [d for d in out if d.key in wanted or d.dataset_id in wanted]
    if purpose:
        out = [d for d in out if d.purpose == purpose]
    if origin:
        out = [d for d in out if d.provenance.origin == origin]
    if mode:
        out = [d for d in out if mode in d.modes]
    if not include_unbuildable:
        out = [d for d in out if not d.not_materialisable_reason]
    return out


def latest_versions() -> list:
    """One dataset per id — the highest version of each."""
    by_id: dict = {}
    for d in all_datasets():
        current = by_id.get(d.dataset_id)
        if current is None or _version_key(d.version) > _version_key(
                current.version):
            by_id[d.dataset_id] = d
    return [by_id[k] for k in sorted(by_id)]


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

def purpose_matrix() -> dict:
    out: dict = {}
    for d in all_datasets():
        out.setdefault(d.purpose, []).append(d.key)
    return out


def origin_matrix() -> dict:
    out: dict = {}
    for d in all_datasets():
        out.setdefault(d.provenance.origin, []).append(d.key)
    return out


def version_matrix() -> dict:
    """{dataset id: [versions, oldest first]}."""
    out: dict = {}
    for d in all_datasets():
        out.setdefault(d.dataset_id, []).append(d.version)
    return {k: sorted(v, key=_version_key) for k, v in out.items()}


def invariant_activation_matrix() -> dict:
    """{invariant id: [datasets that claim to give it a population]}.

    Read the other way round this is the answer to the question D6 was
    commissioned to answer: which invariants are still VACUOUS with no
    dataset proposed for them?
    """
    from verification.invariants import registry as invreg

    out: dict = {i.invariant_id: [] for i in invreg.all_invariants()}
    for d in all_datasets():
        for invariant_id in d.activates_invariants:
            out[invariant_id].append(d.key)
    return out


def unactivated_invariants() -> list:
    """Invariants no dataset claims to activate."""
    return sorted(k for k, v in invariant_activation_matrix().items() if not v)


def unbuildable_datasets() -> list:
    return [{'key': d.key, 'title': d.title,
             'reason': d.not_materialisable_reason,
             'covered_by': d.covered_by_deliverable}
            for d in all_datasets() if d.not_materialisable_reason]


def commissioning_gaps() -> list:
    return [{'key': d.key, 'status': d.commissioning_status,
             'reason': (d.not_materialisable_reason
                        or 'declared but not yet commissioned')}
            for d in all_datasets()
            if d.commissioning_status != Commissioning.COMMISSIONED]


def datasets_without_coverage_ledger() -> tuple:
    """Datasets with no passing coverage ledger behind them.

    The coverage ledger is a **mandatory verification artefact** for every
    regression dataset, and this is what makes that a check rather than a
    convention. It was made mandatory after the ledger twice found coverage
    movement that careful reading of a narrative had not: four surfaces
    silently un-resolved by ``DS-ACT-INHOUSE``, and ``INV-D02`` silently
    activated by ``DS-ACT-VOIDCN`` on a dataset whose every expectation
    passed.

    A dataset can be COMMISSIONED — its expectations hold, its perturbation
    discriminates — and still be quietly covering less than production did.
    Commissioning asks whether the declared outcomes are right; only the
    ledger asks what the dataset can exercise at all.

    Returns ``(findings, evidence_pack_path)``. Pack naming follows the
    same rule as ``unbacked_commissioning_claims`` — ``ds-coverage`` writes
    ``{timestamp}_ds_coverage_{tag}`` and only when ``--tag`` is given, so
    the match is containment, not suffix. That is not a guess: the suffix
    form was the defect this registry shipped with, found on the first
    dataset to declare COMMISSIONED.
    """
    import json
    import os

    from verification.config import EVIDENCE_DIR

    datasets = all_datasets()
    if not datasets:
        return [], ''
    packs = (sorted(name for name in os.listdir(EVIDENCE_DIR)
                    if '_ds_coverage' in name)
             if os.path.isdir(EVIDENCE_DIR) else [])
    if not packs:
        return ([{'key': d.key,
                  'reason': 'no coverage ledger exists on this machine'}
                 for d in datasets], '')

    # Every retained pack is read, newest first, and the most recent one
    # naming a dataset decides it. A ledger is per-dataset — unlike
    # commissioning, which runs the whole registry at once — so "the latest
    # pack" would condemn every dataset but the one measured last.
    verdicts: dict = {}
    for name in reversed(packs):
        try:
            with open(os.path.join(EVIDENCE_DIR, name, 'result.json'),
                      encoding='utf-8') as fh:
                payload = json.load(fh)
        except Exception:                                    # noqa: BLE001
            continue
        key = payload.get('dataset')
        if key and key not in verdicts:
            verdicts[key] = ((payload.get('ledger') or {}).get('verdict', ''),
                             name)

    findings = []
    for d in datasets:
        verdict, pack = verdicts.get(d.key, ('', ''))
        if not verdict:
            findings.append({'key': d.key,
                             'reason': 'no coverage ledger has been run for '
                                       'this dataset'})
        elif verdict != 'AS_DECLARED':
            findings.append({'key': d.key,
                             'reason': f'its most recent coverage ledger '
                                       f'({pack}) reported {verdict}'})
    return findings, (os.path.join(EVIDENCE_DIR, packs[-1]) if packs else '')


def unbacked_commissioning_claims() -> tuple:
    """Datasets claiming COMMISSIONED that the evidence does not support.

    The same cross-check D4 and D5 apply, for the same reason: a status
    declared in code is a gate somebody can walk through without doing
    the work.

    Pack naming, and why the match is a containment rather than a suffix
    -------------------------------------------------------------------
    ``ds-commission`` writes its pack as ``{timestamp}_ds_commission_{tag}``
    and only writes one when ``--tag`` is given, so a commissioning pack
    always carries a trailing tag. This function originally matched
    ``name.endswith('_ds_commission')``, which no such name can satisfy —
    the cross-check could never find evidence and every ``COMMISSIONED``
    declaration would be reported as unbacked forever.

    Step 1 could not have found that: with an empty registry there are no
    claimants and the function returns before it looks. It surfaced on
    ``DS-ACT-INHOUSE``, the first dataset to declare ``COMMISSIONED``.

    The timestamp prefix is fixed-width, so a plain sort still puts the
    most recent pack last.
    """
    import json
    import os

    from verification.config import EVIDENCE_DIR

    claimants = [d for d in all_datasets()
                 if d.commissioning_status == Commissioning.COMMISSIONED]
    if not claimants:
        return [], ''
    packs = (sorted(name for name in os.listdir(EVIDENCE_DIR)
                    if '_ds_commission' in name)
             if os.path.isdir(EVIDENCE_DIR) else [])
    if not packs:
        return ([{'key': d.key,
                  'reason': 'no commissioning evidence exists on this machine'}
                 for d in claimants], '')
    pack = os.path.join(EVIDENCE_DIR, packs[-1])
    try:
        with open(os.path.join(pack, 'result.json'), encoding='utf-8') as fh:
            payload = json.load(fh)
    except Exception as exc:                                 # noqa: BLE001
        return ([{'key': '*',
                  'reason': f'commissioning evidence unreadable: {exc}'}],
                pack)
    passed = {o['key'] for o in payload.get('outcomes', [])
              if o.get('checks') and all(o['checks'].values())}
    findings = [{'key': d.key,
                 'reason': (f'declares COMMISSIONED, but the most recent '
                            f'commissioning run ({packs[-1]}) did not pass '
                            f'it')}
                for d in claimants if d.key not in passed]
    return findings, pack
