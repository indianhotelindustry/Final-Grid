"""
The execution pipeline and the result classifier.

One challenge, start to finish:

  1. **Arena** — take a pristine baseline from production and fingerprint
     both (``isolation``).
  2. **Baseline sweep** — run every layer against the clean baseline,
     once per platform run. This is what "moved" is measured against, and
     it is why a layer that already reports FAIL on production data can
     still detect a new fault.
  3. **Issue** — a private copy of the baseline for this fault.
  4. **Inject** — realise the fault, and refuse a zero-change injection.
  5. **Sweep** — run every layer against the seeded copy, in parallel.
  6. **Classify** — per layer: did the signal move, and did it move where
     the fault declared it would?
  7. **Collect** — the evidence the charter requires.
  8. **Clean** — delete the copy, verify it is gone, verify the baseline
     and production are byte-identical.

Why every layer is swept, not only the declared ones
----------------------------------------------------
Sweeping only the layers a fault expects would make the platform
incapable of its most useful output. Two of the four questions it exists
to answer — *can it distinguish unrelated failures?* and *which layer
missed this?* — require running the layers that are expected to stay
silent. A framework where every layer moves for every fault has detected
nothing; it has proved it is sensitive to change.

The classifier's five outcomes
------------------------------
``ATTRIBUTED``        expected, moved, and moved where the fault said.
``UNATTRIBUTED``      expected, moved, but not at the declared target.
                      The layer felt a disturbance; it did not identify
                      a defect.
``MISSED``            expected, silent. **The finding.**
``UNEXPECTED``        not expected, moved. Blast radius, recorded.
``CORRECTLY_SILENT``  not expected, silent. A real result: this is what
                      makes attribution possible at all.
"""
from __future__ import annotations

import datetime as _dt
import time
import tracemalloc
from dataclasses import dataclass, field

from verification.config import PRODUCTION_DB
from verification.faults import detectors, injection, isolation, registry
from verification.faults.model import (
    ALL_LAYERS, Commissioning, Detection, FaultEvidence, FaultResult, Layer,
    LAYER_COST_MS, Metering, Mode, SEVERITY_RANK,
)


def _utcnow() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat()


@dataclass
class PlatformRun:
    started_at: str
    finished_at: str = ''
    duration_seconds: float = 0.0
    pvf_version: str = ''
    mode: str = ''
    layers_swept: tuple = ()
    parallel: bool = True

    production_db: str = ''
    production_hash_before: str = ''
    production_hash_after: str = ''
    baseline_hash: str = ''
    isolation_verified: bool = False
    cleanup: dict = field(default_factory=dict)

    baseline_layers: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    registry_size: int = 0
    uncovered: list = field(default_factory=list)
    commissioning_gaps: list = field(default_factory=list)
    unbacked_claims: list = field(default_factory=list)
    commissioning_evidence_pack: str = ''
    total_writes: int = 0

    # -- aggregates -------------------------------------------------------

    @property
    def counts(self) -> dict:
        out = {'registered': self.registry_size,
               'challenged': len(self.results),
               'detected': 0, 'missed': 0, 'errors': 0,
               'uncovered': len(self.uncovered)}
        for r in self.results:
            if r.error:
                out['errors'] += 1
            elif not r.layers:
                # Uncovered: never injected, because nothing in the current
                # framework could see it. Counted under 'uncovered' only.
                # Counting it as MISSED as well would read as "the
                # framework failed to detect this", when what happened is
                # that it was never asked — misleading in exactly the
                # direction this deliverable must not be.
                continue
            elif r.detected:
                out['detected'] += 1
            else:
                out['missed'] += 1
        for layer in ALL_LAYERS:
            out[layer] = sum(
                1 for r in self.results for o in r.layers
                if o.layer == layer and o.detection == Detection.ATTRIBUTED)
        return out

    @property
    def gaps(self) -> list:
        """Faults an expected layer failed to attribute. The output."""
        return [r for r in self.results if r.gaps and not r.error]

    @property
    def undetected(self) -> list:
        return [r for r in self.results
                if not r.detected and not r.error and r.layers]

    @property
    def overall(self) -> str:
        if not self.isolation_verified or self.total_writes:
            return 'UNVERIFIED'
        if self.unbacked_claims:
            return 'UNVERIFIED'
        if any(r.error for r in self.results):
            return 'ERROR'
        if self.undetected:
            return 'FAIL'
        if self.gaps or self.uncovered or self.commissioning_gaps:
            return 'INCOMPLETE'
        return 'PASS'


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _attribution_targets(f, layer: str) -> list:
    """The signal keys this fault says the layer should move."""
    if layer == Layer.D4_INVARIANTS:
        return list(f.expected_invariants)
    if layer == Layer.D1_PARITY:
        return list(f.expected_quantities)
    if layer == Layer.D3_REPLAY:
        return [f'rc:{r}' for r in f.expected_reconciliations]
    if layer == Layer.D2_GOLDEN:
        return list(f.affected_reports)
    return []


def _matches(layer: str, target: str, moved: list) -> bool:
    if layer == Layer.D2_GOLDEN:
        # Surface ids are endpoint-shaped; a declared report is a prefix.
        return any(key.startswith(target) for key in moved)
    return target in moved


def classify(f, layer: str, probe, baseline_signal: dict):
    """One layer's outcome for one fault."""
    from verification.faults.model import LayerOutcome

    outcome = LayerOutcome(layer=layer, expected=f.expects(layer))
    if probe is None:
        outcome.detection = Detection.NOT_RUN
        return outcome
    outcome.ran = probe.ran
    outcome.duration_ms = probe.duration_ms
    if not probe.ran:
        outcome.error = probe.error
        outcome.detection = Detection.ERROR
        return outcome

    moved = detectors.moved_keys(baseline_signal, probe.signal)
    outcome.moved_keys = moved[:60]
    outcome.signal_moved = bool(moved)

    targets = _attribution_targets(f, layer)
    hit = [t for t in targets if _matches(layer, t, moved)]
    outcome.attributed_targets = hit
    outcome.missing_targets = [t for t in targets if t not in hit]

    if outcome.expected:
        if not moved:
            outcome.detection = Detection.MISSED
        elif targets and not hit:
            outcome.detection = Detection.UNATTRIBUTED
        else:
            # No declared target means the fault only claims the layer
            # should notice. Movement is then attribution.
            outcome.detection = Detection.ATTRIBUTED
    else:
        outcome.detection = (Detection.UNEXPECTED if moved
                             else Detection.CORRECTLY_SILENT)
    return outcome


# ---------------------------------------------------------------------------
# One challenge
# ---------------------------------------------------------------------------

def challenge(f, arena, baseline_layers: dict, layers: tuple,
              parallel: bool = True, slot: str = '',
              quiet: bool = True) -> FaultResult:
    """Inject one fault and sweep the framework."""
    result = FaultResult(
        fault_id=f.fault_id, title=f.title, category=f.category,
        severity=f.expected_severity, method=f.injection_method,
        commissioning_status=f.commissioning_status)

    if not f.expected_detection:
        # Registered so the taxonomy is complete, but nothing in the
        # current framework can see it. Injecting would produce a
        # guaranteed MISS that says nothing new.
        result.evidence = FaultEvidence(
            injection={'skipped': f.uncovered_reason},
            expected_detection=[], actual_detection=[],
            certification_impact=f.expected_certification_impact,
            root_cause_candidates=list(f.root_cause_candidates),
            timestamp=_utcnow())
        result.error = ''
        return result

    tracemalloc.start()
    t0 = time.perf_counter()
    db_path = ''
    try:
        db_path = arena.issue(f.fault_id)
        inj, env_overlay, patch = injection.prepare(
            f, db_path, isolation.ARENA_DIR)
        result.rows_changed = inj.rows_changed
        result.injection_verified = inj.verified

        # The baseline must be untouched by the injection: the fault goes
        # into its private copy or nowhere.
        arena.verify_baseline(f.fault_id)

        probes = detectors.sweep(db_path, layers, env_overlay, patch,
                                 slot=slot, parallel=parallel)
        result.layers = [
            classify(f, layer, probes.get(layer),
                     baseline_layers.get(layer, {}))
            for layer in layers]

        detection_time = min(
            (o.duration_ms for o in result.layers
             if o.detection == Detection.ATTRIBUTED), default=0)

        result.evidence = FaultEvidence(
            injection={'method': inj.method, 'rows_changed': inj.rows_changed,
                       **inj.detail},
            expected_detection=list(f.expected_detection),
            actual_detection=[o.layer for o in result.layers
                              if o.signal_moved],
            detection_time_ms=detection_time,
            detected_by=[o.layer for o in result.layers
                         if o.detection == Detection.ATTRIBUTED],
            missed_by=[o.layer for o in result.layers
                       if o.detection in (Detection.MISSED,
                                          Detection.UNATTRIBUTED)],
            affected_invariants=[k for o in result.layers
                                 if o.layer == Layer.D4_INVARIANTS
                                 for k in o.moved_keys],
            affected_reports=[k for o in result.layers
                              if o.layer == Layer.D2_GOLDEN
                              for k in o.moved_keys][:40],
            affected_replays=[k for o in result.layers
                              if o.layer == Layer.D3_REPLAY
                              for k in o.moved_keys],
            affected_parity_checks=[k for o in result.layers
                                    if o.layer == Layer.D1_PARITY
                                    for k in o.moved_keys],
            certification_impact=f.expected_certification_impact,
            root_cause_candidates=list(f.root_cause_candidates),
            execution_context={'layers': list(layers), 'parallel': parallel,
                               'patch': patch, 'env': env_overlay},
            business_date='', replay_context={}, timestamp=_utcnow())

        # Isolation and cleanup, verified rather than assumed.
        arena.verify_baseline(f.fault_id)
        arena.verify_production(f.fault_id)
        result.isolation_verified = True
    except Exception as exc:                             # noqa: BLE001
        result.error = f'{type(exc).__name__}: {exc}'
        result.evidence = FaultEvidence(
            injection={'error': result.error},
            expected_detection=list(f.expected_detection),
            root_cause_candidates=list(f.root_cause_candidates),
            timestamp=_utcnow())
    finally:
        if db_path:
            result.cleanup_verified = arena.cleanup(db_path)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.metering = Metering(
            duration_ms=int((time.perf_counter() - t0) * 1000),
            memory_peak_kb=int(peak / 1024),
            layers_run=sum(1 for o in result.layers if o.ran))
    return result


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run(source: str = PRODUCTION_DB,
        mode: str = Mode.BATCH,
        ids: list | None = None,
        category: str | None = None,
        layers: tuple | None = None,
        parallel: bool = True,
        quiet: bool = False) -> PlatformRun:
    """Challenge the framework with every selected fault."""
    from verification import __version__ as PVF_VERSION

    started = _utcnow()
    t0 = time.perf_counter()
    layers = tuple(layers or ALL_LAYERS)

    faults = registry.select(ids=ids, category=category)
    run_result = PlatformRun(
        started_at=started, pvf_version=PVF_VERSION, mode=mode,
        layers_swept=layers, parallel=parallel,
        registry_size=len(faults),
        uncovered=registry.uncovered_faults(),
        commissioning_gaps=registry.commissioning_gaps())
    (run_result.unbacked_claims,
     run_result.commissioning_evidence_pack) = \
        registry.unbacked_commissioning_claims()

    arena = isolation.open_arena(source)
    run_result.production_db = arena.production_path
    run_result.production_hash_before = arena.production_hash
    run_result.baseline_hash = arena.baseline_hash

    if not quiet:
        print(f'[fip] baseline    : {arena.baseline_path}')
        print(f'[fip] production  : {arena.production_hash}')
        print(f'[fip] layers      : {", ".join(layers)}  '
              f'(~{sum(LAYER_COST_MS[l] for l in layers) / 1000:.0f}s '
              f'serial, {max(LAYER_COST_MS[l] for l in layers) / 1000:.0f}s '
              f'parallel)')
        print(f'[fip] faults      : {len(faults)}')
        print('[fip] sweeping the clean baseline...')

    baseline_probes = detectors.sweep(arena.baseline_path, layers,
                                      slot='_base', parallel=parallel)
    for layer, probe in baseline_probes.items():
        run_result.baseline_layers[layer] = probe.signal
        if not probe.ran and not quiet:
            print(f'[fip]   WARNING {layer} baseline probe failed: '
                  f'{probe.error.splitlines()[0] if probe.error else ""}')

    try:
        for index, f in enumerate(faults, 1):
            result = challenge(f, arena, run_result.baseline_layers, layers,
                               parallel=parallel, slot=f'_{index}',
                               quiet=quiet)
            run_result.results.append(result)
            if not quiet:
                flag = ('SKIP' if not f.expected_detection
                        else 'ERR ' if result.error
                        else 'PASS' if result.detected else 'MISS')
                detail = (result.error.splitlines()[0] if result.error
                          else ', '.join(result.evidence.detected_by)
                          or 'no layer attributed it')
                print(f'[fip] {index:>3}/{len(faults)} {flag} '
                      f'{f.fault_id:<10} {detail}')
    finally:
        run_result.cleanup = isolation.close_arena(arena)
        run_result.production_hash_after = run_result.cleanup.get(
            'production_sha256', '')
        run_result.isolation_verified = bool(
            run_result.cleanup.get('production_unchanged')
            and run_result.cleanup.get('baseline_unchanged')
            and not run_result.cleanup.get('copies_left_behind'))

    run_result.finished_at = _utcnow()
    run_result.duration_seconds = round(time.perf_counter() - t0, 2)
    return run_result
