"""
Evaluation — running every layer against a dataset and comparing the
result with what the dataset declared.

The integration point that made this cheap
------------------------------------------
D1, D2, D3 and D4 each already accept ``--db``, and D5 wrapped all four
as uniform probes in order to sweep them concurrently. That wrapper is
exactly what a dataset evaluation needs, so this module reuses
``verification.faults.detectors`` rather than building a second way to
run the same four things. One consequence worth stating: a change to how
a layer is probed lands in D5 and D6 together, and cannot drift between
them.

What is compared, per charter element
-------------------------------------
=====================  ==========================================
element 3 financial    plain SQL over the dataset (``financials``)
element 4 invariants   D4 status per invariant id
element 5 replay       D3 reconciliation status, and ledger stability
element 6 parity       D1 verdict per quantity
element 7 faults       D5 detection when injected into THIS dataset
=====================  ==========================================

Element 7 is the one that finds things nothing else can. A fault that is
detected on production data and missed on a dataset has found a
population the framework is blind on — and populations are precisely what
D6 exists to create. The three-way relationship matters: D5 asks whether
the framework sees a defect, D6 asks whether it still sees it when the
data looks different.

Not-run is not agreement
------------------------
A layer that could not be probed yields ``NOT_RUN`` for every expectation
that depends on it, never ``MET``. This is the same rule D1 applies with
``NOT_IMPLEMENTED`` and for the same reason (P10): silence is not
evidence.
"""
from __future__ import annotations

import os
import time

from verification.datasets import financials
from verification.datasets.model import (
    DatasetResult, ExpectationOutcome, Layer, Status,
)
from verification.faults import detectors
from verification.faults.model import Layer as FaultLayer

#: Dataset layer -> D5 probe layer. D5_FAULTS has no probe of its own: it
#: is exercised by injecting faults and re-probing.
PROBE_FOR = {
    Layer.D1_PARITY: FaultLayer.D1_PARITY,
    Layer.D2_GOLDEN: FaultLayer.D2_GOLDEN,
    Layer.D3_REPLAY: FaultLayer.D3_REPLAY,
    Layer.D4_INVARIANTS: FaultLayer.D4_INVARIANTS,
}

#: The reserved replay expectation key: did the ledger stay self-consistent
#: across the whole dataset?
LEDGER_STABLE = 'ledger_stable'


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

def _observe_invariants(raw: dict) -> dict:
    return {iid: (entry or {}).get('status', '')
            for iid, entry in (raw.get('invariants') or {}).items()}


def _observe_invariant_populations(raw: dict) -> dict:
    return {iid: (entry or {}).get('population', 0)
            for iid, entry in (raw.get('invariants') or {}).items()}


def _observe_parity(raw: dict) -> dict:
    return {qid: (entry or {}).get('verdict', '')
            for qid, entry in (raw or {}).items()}


def _observe_replay(raw: dict) -> dict:
    """Reconciliation id -> a single status for the whole dataset.

    A reconciliation is evaluated per business date. A dataset's
    declaration is about the dataset as a whole, so the per-date statuses
    are collapsed: if every date agrees, that status; if they differ, the
    worst one, because a reconciliation that failed on one day of the
    narrative has failed.
    """
    order = ['ERROR', 'FAIL', 'BLOCK', 'WARN', 'INFO', 'PASS', 'OK']
    per_rule: dict = {}
    for _date, entry in sorted((raw.get('dates') or {}).items()):
        for rule_id, status in (entry.get('reconciliations') or {}).items():
            per_rule.setdefault(rule_id, []).append(str(status))
    out = {}
    for rule_id, statuses in per_rule.items():
        unique = set(statuses)
        if len(unique) == 1:
            out[rule_id] = statuses[0]
            continue
        for candidate in order:
            if candidate in unique:
                out[rule_id] = candidate
                break
        else:
            out[rule_id] = sorted(unique)[0]
    out[LEDGER_STABLE] = str(raw.get('ledger_stable'))
    return out


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _compare(element: str, target: str, expected: str,
             observed_map: dict, ran: bool,
             not_run_note: str = '') -> ExpectationOutcome:
    outcome = ExpectationOutcome(element=element, target=target,
                                 expected=str(expected))
    if not ran:
        outcome.status = Status.NOT_RUN
        outcome.detail = not_run_note or 'the layer could not be probed'
        return outcome
    if target not in observed_map:
        outcome.status = Status.UNKNOWN_TARGET
        outcome.detail = (f'{target} was not reported by the layer at all, so '
                          f'the expectation names something that does not '
                          f'exist on this dataset')
        return outcome
    outcome.observed = str(observed_map[target])
    outcome.status = (Status.MET if outcome.observed == str(expected)
                      else Status.UNMET)
    return outcome


# ---------------------------------------------------------------------------
# Fault expectations — charter element 7
# ---------------------------------------------------------------------------

def _evaluate_faults(d, db_path: str, baseline_signals: dict,
                     outcomes: list) -> None:
    """Inject each declared fault into a copy of the dataset.

    Only the layers a fault declares are swept, rather than all four.
    D5's own run already establishes the blast radius on production data;
    what D6 asks is narrower and cheaper — *does the declared detector
    still fire on this population?*
    """
    import shutil

    from verification.faults import injection, pipeline, registry as faultreg
    from verification.faults.model import Detection

    for fault_id, expected in d.expectations.faults.items():
        outcome = ExpectationOutcome(element='faults', target=fault_id,
                                     expected=str(expected))
        seeded = ''
        try:
            fault = faultreg.get(fault_id)
            layers = tuple(l for l in fault.expected_detection
                           if l in baseline_signals)
            if not layers:
                outcome.status = Status.NOT_RUN
                outcome.detail = ('none of the layers this fault declares '
                                  'could be probed on this dataset')
                outcomes.append(outcome)
                continue

            seeded = db_path + f'.fault_{fault_id}.db'
            shutil.copy2(db_path, seeded)
            inj, env_overlay, patch = injection.prepare(
                fault, seeded, os.path.dirname(seeded))
            probes = detectors.sweep(seeded, layers, env_overlay, patch,
                                     slot=f'_ds{fault_id}', parallel=True)
            classified = [pipeline.classify(fault, layer, probes.get(layer),
                                            baseline_signals.get(layer, {}))
                          for layer in layers]
            detected = any(o.detection == Detection.ATTRIBUTED
                           for o in classified)
            outcome.observed = 'DETECTED' if detected else 'MISSED'
            outcome.status = (Status.MET
                              if outcome.observed == str(expected)
                              else Status.UNMET)
            outcome.detail = '; '.join(f'{o.layer}={o.detection}'
                                       for o in classified)
            if not inj.verified:
                outcome.status = Status.ERROR
                outcome.detail = ('the fault was not actually injected into '
                                  'this dataset, so the result says nothing')
        except Exception as exc:                             # noqa: BLE001
            outcome.status = Status.ERROR
            outcome.detail = f'{type(exc).__name__}: {exc}'
        finally:
            if seeded and os.path.exists(seeded):
                try:
                    os.remove(seeded)
                except OSError:
                    pass
        outcomes.append(outcome)


# ---------------------------------------------------------------------------
# The evaluation
# ---------------------------------------------------------------------------

def evaluate(d, materialisation, layers: tuple = (),
             include_faults: bool = True,
             parallel: bool = True) -> DatasetResult:
    """Run the declared layers against a materialised dataset."""
    started = time.perf_counter()
    result = DatasetResult(dataset_id=d.dataset_id, version=d.version,
                           title=d.title, materialisation=materialisation,
                           commissioning_status=d.commissioning_status,
                           certification_status=d.certification_status)
    if not materialisation.ok:
        result.error = materialisation.error or 'the dataset did not build'
        return result

    db_path = materialisation.db_path

    # -- element 3: financial, measured straight from the books ----------
    observed_financial = financials.measure(
        db_path, tuple(d.expectations.financial))
    for name, expected in sorted(d.expectations.financial.items()):
        result.outcomes.append(
            _compare('financial', name, expected, observed_financial, True))

    # -- probe the layers the dataset declares ---------------------------
    declared = d.expectations.declared_layers()
    wanted = tuple(layers) if layers else declared
    probe_layers = tuple(PROBE_FOR[l] for l in wanted if l in PROBE_FOR)
    probes = (detectors.sweep(db_path, probe_layers, slot='_ds',
                              parallel=parallel)
              if probe_layers else {})
    result.layers_run = tuple(l for l in wanted if l in PROBE_FOR)

    def probe_for(layer):
        return probes.get(PROBE_FOR.get(layer, ''), None)

    # -- element 4: invariants -------------------------------------------
    inv_probe = probe_for(Layer.D4_INVARIANTS)
    inv_ran = bool(inv_probe and inv_probe.ran)
    observed_invariants = (_observe_invariants(inv_probe.raw)
                           if inv_ran else {})
    populations = (_observe_invariant_populations(inv_probe.raw)
                   if inv_ran else {})
    for invariant_id, expected in sorted(d.expectations.invariants.items()):
        result.outcomes.append(
            _compare('invariants', invariant_id, expected,
                     observed_invariants, inv_ran,
                     'the invariant engine could not be run on this dataset'))

    # The activation question, which is why this deliverable exists.
    for invariant_id in d.activates_invariants:
        status = observed_invariants.get(invariant_id, '')
        if not inv_ran:
            result.still_vacuous.append(invariant_id)
        elif status == 'VACUOUS' or populations.get(invariant_id, 0) == 0:
            result.still_vacuous.append(invariant_id)
        else:
            result.activated_invariants.append(invariant_id)

    # -- element 5: replay -----------------------------------------------
    replay_probe = probe_for(Layer.D3_REPLAY)
    replay_ran = bool(replay_probe and replay_probe.ran)
    observed_replay = _observe_replay(replay_probe.raw) if replay_ran else {}
    for rule_id, expected in sorted(d.expectations.replay.items()):
        result.outcomes.append(
            _compare('replay', rule_id, expected, observed_replay, replay_ran,
                     'the replay engine could not be run on this dataset'))

    # -- D2: which golden-master surfaces resolve -------------------------
    #
    # The capture is keyed by surface, and a surface that resolved is a key
    # in it. A surface whose resolver found no entity is simply absent —
    # which is why the observation is membership rather than a status
    # field, and why UNRESOLVED is a declarable expectation rather than an
    # omission.
    golden_probe = probe_for(Layer.D2_GOLDEN)
    golden_ran = bool(golden_probe and golden_probe.ran)
    captured = set(golden_probe.raw or {}) if golden_ran else set()
    observed_golden = {surface: ('RESOLVED' if surface in captured
                                 else 'UNRESOLVED')
                       for surface in d.expectations.golden}
    for surface, expected in sorted(d.expectations.golden.items()):
        result.outcomes.append(
            _compare('golden', surface, expected, observed_golden, golden_ran,
                     'the golden master framework could not be run on this '
                     'dataset'))

    # -- element 6: parity -----------------------------------------------
    parity_probe = probe_for(Layer.D1_PARITY)
    parity_ran = bool(parity_probe and parity_probe.ran)
    observed_parity = _observe_parity(parity_probe.raw) if parity_ran else {}
    for quantity_id, expected in sorted(d.expectations.parity.items()):
        result.outcomes.append(
            _compare('parity', quantity_id, expected, observed_parity,
                     parity_ran,
                     'the parity harness could not be run on this dataset'))

    # -- element 7: faults ------------------------------------------------
    if include_faults and d.expectations.faults:
        baseline_signals = {layer: probe.signal
                            for layer, probe in probes.items() if probe.ran}
        # Faults declaring a layer this evaluation did not probe need that
        # layer's baseline; sweep the remainder once rather than per fault.
        needed = set()
        from verification.faults import registry as faultreg
        for fault_id in d.expectations.faults:
            try:
                needed |= set(faultreg.get(fault_id).expected_detection)
            except KeyError:
                continue
        extra = tuple(l for l in sorted(needed) if l not in baseline_signals)
        if extra:
            for layer, probe in detectors.sweep(db_path, extra, slot='_dsb',
                                                parallel=parallel).items():
                if probe.ran:
                    baseline_signals[layer] = probe.signal
        _evaluate_faults(d, db_path, baseline_signals, result.outcomes)

    for layer, probe in probes.items():
        if not probe.ran:
            result.error = (result.error or
                            f'{layer} probe failed: '
                            f'{(probe.error or "").splitlines()[0][:120]}')

    result.duration_seconds = round(time.perf_counter() - started, 2)
    return result
