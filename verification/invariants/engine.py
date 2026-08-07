"""
The execution pipeline.

A run is:

  1. copy production through the SQLite backup API and fingerprint the
     original (``verification.dbcopy``, unchanged since D1);
  2. freeze the clock — to the scope's business date when there is one,
     otherwise to the dataset's current business date (D2's proven
     freeze, unchanged);
  3. build the Flask application bound to the copy, then start metering,
     so application boot writes are not counted against the invariants;
  4. evaluate every registered invariant, each in isolation, each metered
     independently;
  5. evaluate the registry a second time — and a third in reverse
     declaration order — to prove the results are repeatable and do not
     depend on evaluation order;
  6. re-verify that production is byte-identical.

Isolation between invariants
----------------------------
Each invariant gets its own metering window and its own exception
boundary. One that raises becomes an ERROR result for itself and nothing
else: a partial run with a visible hole is useful, a crashed run is not.

Determinism and order independence
----------------------------------
Both are requirements of the charter and both are *measured*, not
asserted. The second pass proves repeatability; the reverse pass proves
that no invariant left state behind that changed another's answer. They
are cheap because invariants are reads, and they are the difference
between "the engine agreed with itself" and "the engine is deterministic".

Zero writes
-----------
``db_writes`` is counted on both the raw connection and the SQLAlchemy
engine. A single write anywhere in the run fails it outright, regardless
of what the invariants reported — a verification engine that modified the
system it was verifying would invalidate its own findings.
"""
from __future__ import annotations

import datetime as _dt
import os
import time
import tracemalloc
from dataclasses import dataclass, field

from verification.config import PRODUCTION_DB, PROJECT_ROOT
from verification.dbcopy import (
    CopyHandle, assert_production_untouched, make_copy, sqlalchemy_url,
)
from verification.golden.capture import FREEZE_TIME
from verification.golden.freeze import install_proven
from verification.invariants import registry
from verification.invariants.context import Context, Scope
from verification.invariants.model import (
    Blocking, Commissioning, Confidence, Evidence, InvariantResult, Metering,
    Mode, SEVERITY_RANK, Severity, Status,
)

INVARIANT_DIR = os.path.join(PROJECT_ROOT, 'verification', 'invariant_sets')

#: Violations listed per invariant. The COUNT is always exact; only the
#: listing is capped, and a capped listing downgrades confidence to
#: TRUNCATED so a reader can never mistake the cap for completeness.
MAX_VIOLATIONS_LISTED = 200


@dataclass
class EngineRun:
    started_at: str
    finished_at: str = ''
    duration_seconds: float = 0.0
    app_version: str = ''
    pvf_version: str = ''
    mode: str = ''
    scope: str = ''
    business_date: str = ''
    frozen_at: str = ''
    freeze_proven: bool = False
    source_db: str = ''
    source_hash_before: str = ''
    source_hash_after: str = ''
    read_only_verified: bool = False
    copy_method: str = ''

    results: list = field(default_factory=list)
    repeatability_mismatches: list = field(default_factory=list)
    order_mismatches: list = field(default_factory=list)
    determinism_proven: bool = False
    order_independence_proven: bool = False
    total_writes: int = 0
    registry_size: int = 0
    commissioning_gaps: list = field(default_factory=list)
    unbacked_commissioning_claims: list = field(default_factory=list)
    commissioning_evidence_pack: str = ''

    # -- aggregates -------------------------------------------------------

    @property
    def counts(self) -> dict:
        out = {'registered': self.registry_size, 'evaluated': len(self.results)}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        out['violations'] = sum(r.violation_count for r in self.results)
        out['uncommissioned'] = sum(1 for r in self.results
                                    if not r.counts_as_evidence)
        return out

    @property
    def violated(self) -> list:
        return [r for r in self.results if r.status == Status.VIOLATED]

    @property
    def release_blocking(self) -> list:
        return [r for r in self.violated
                if r.blocking == Blocking.RELEASE and r.counts_as_evidence]

    @property
    def certification_blocking(self) -> list:
        return [r for r in self.violated
                if r.blocking in (Blocking.RELEASE, Blocking.CERTIFICATION)
                and r.counts_as_evidence]

    @property
    def write_free(self) -> bool:
        return self.total_writes == 0

    @property
    def overall(self) -> str:
        """The engine's verdict.

        ``UNVERIFIED`` outranks everything else: if the read-only
        guarantee, determinism, order independence or the zero-write
        requirement was not established, the findings are not evidence
        and reporting PASS or FAIL over them would be a category error.
        """
        if not (self.read_only_verified and self.write_free
                and self.determinism_proven
                and self.order_independence_proven):
            return 'UNVERIFIED'
        if self.unbacked_commissioning_claims:
            # An invariant claiming to be commissioned without evidence
            # makes every green result it produced unreliable, so the run
            # cannot report on the system until the claim is resolved.
            return 'UNVERIFIED'
        if any(r.status == Status.ERROR for r in self.results):
            return 'ERROR'
        if self.release_blocking:
            return 'FAIL'
        if any(r.status in (Status.VACUOUS, Status.NOT_APPLICABLE)
               for r in self.results) or self.commissioning_gaps:
            return 'INCOMPLETE'
        if self.violated:
            return 'FAIL'
        return 'PASS'


# ---------------------------------------------------------------------------
# Evaluation of one invariant
# ---------------------------------------------------------------------------

def evaluate_one(inv, ctx: Context) -> InvariantResult:
    """Evaluate a single invariant, metered and isolated."""
    result = InvariantResult(
        invariant_id=inv.invariant_id, title=inv.title, category=inv.category,
        severity=inv.severity, blocking=inv.blocking, mode=ctx.scope.mode,
        scope=ctx.scope.label, status=Status.NOT_APPLICABLE,
        commissioning_status=inv.commissioning_status)

    if not inv.supports(ctx.scope.mode):
        result.evidence = Evidence(
            expected_result='not evaluated in this mode',
            observed_result=(f'{inv.invariant_id} declares modes '
                             f'{", ".join(inv.modes)}'),
            confidence=Confidence.NONE,
            timestamp=_utcnow(), business_date=ctx.business_date,
            replay_context=dict(ctx.scope.replay_context))
        return result

    ctx.reset_metering()
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        status, population, violations, extras = inv.fn(ctx)
    except Exception as exc:                             # noqa: BLE001
        import traceback
        result.status = Status.ERROR
        result.error = f'{type(exc).__name__}: {exc}'
        result.evidence = Evidence(
            expected_result=inv.business_rule,
            observed_result='evaluation raised',
            root_cause_candidates=list(inv.likely_root_causes),
            confidence=Confidence.NONE, timestamp=_utcnow(),
            business_date=ctx.business_date,
            replay_context=dict(ctx.scope.replay_context))
        result.evidence.inputs = {'traceback': traceback.format_exc(limit=6)}
        _finish_metering(result, ctx, t0)
        return result

    duration = time.perf_counter() - t0
    _finish_metering(result, ctx, t0, duration)

    result.status = status
    result.population = population
    result.violation_count = len(violations)
    result.violations = violations[:MAX_VIOLATIONS_LISTED]

    confidence = Confidence.PROVEN
    if population == 0:
        confidence = Confidence.NONE
    elif len(violations) > MAX_VIOLATIONS_LISTED:
        confidence = Confidence.TRUNCATED
    if extras.get('confidence'):
        confidence = extras['confidence']

    result.evidence = Evidence(
        inputs=extras.get('inputs', {}),
        expected_result=extras.get('expected', inv.business_rule),
        observed_result=extras.get('observed', ''),
        variance=extras.get('variance', ''),
        confidence=confidence,
        evidence_files=extras.get('evidence_files', []),
        affected_objects=sorted({f'{v.object_type}:{v.object_id}'
                                 for v in result.violations}),
        root_cause_candidates=(list(inv.likely_root_causes)
                               if status == Status.VIOLATED else []),
        timestamp=_utcnow(),
        business_date=ctx.business_date,
        replay_context=dict(ctx.scope.replay_context),
    )
    return result


def _finish_metering(result: InvariantResult, ctx: Context, t0: float,
                     duration: float | None = None) -> None:
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = duration if duration is not None else (time.perf_counter() - t0)
    result.metering = Metering(
        duration_ms=int(elapsed * 1000),
        db_reads=ctx.metering.db_reads,
        db_writes=ctx.metering.db_writes,
        memory_peak_kb=int(peak / 1024),
        rows_examined=ctx.metering.rows_examined,
    )


def _utcnow() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _build_app(handle: CopyHandle):
    os.environ['DATABASE_URL'] = sqlalchemy_url(handle)
    os.environ.setdefault('FLASK_ENV', 'production')
    from app import create_app
    return create_app()


def _app_version() -> str:
    try:
        from app import APP_VERSION
        return APP_VERSION
    except Exception:                                    # noqa: BLE001
        return 'unknown'


def _comparable(results: list) -> dict:
    """The part of a result that must be identical between passes.

    Timings, memory and read counts legitimately vary; the finding must
    not. Comparing the whole result would make the determinism control
    fire on noise, and a control that cries wolf is switched off.
    """
    return {
        r.invariant_id: {
            'status': r.status,
            'population': r.population,
            'violations': r.violation_count,
            'objects': tuple(r.evidence.affected_objects),
            'observed': r.evidence.observed_result,
        } for r in results
    }


def run(source: str = PRODUCTION_DB,
        mode: str = Mode.ENTIRE_DATABASE,
        business_date: str = '',
        reservation_id: int = 0,
        dataset: str = '',
        ids: list | None = None,
        prove_determinism: bool = True,
        quiet: bool = False) -> EngineRun:
    """Evaluate the invariant registry against a disposable copy."""
    from verification import __version__ as PVF_VERSION
    from verification.replay.timeline import read_business_date

    started = _utcnow()
    t0 = time.perf_counter()

    handle = make_copy(name='pvf_invariants.db', source=source)
    dataset_business_date = read_business_date(handle.copy_path)
    scope_date = business_date or (
        dataset_business_date.isoformat()
        if mode in (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT,
                    Mode.HISTORICAL_REPLAY) else '')

    scope = Scope(mode=mode, business_date=scope_date,
                  reservation_id=reservation_id, dataset=dataset)

    # The clock is frozen to the date under evaluation when there is one,
    # so that an invariant asking a canonical engine about a past day is
    # answered as of that day rather than as of the run.
    freeze_date = (_dt.date.fromisoformat(scope_date) if scope_date
                   else dataset_business_date)
    instant = _dt.datetime.combine(freeze_date, FREEZE_TIME)

    if not quiet:
        print(f'[inv] working copy : {handle.copy_path} ({handle.method})')
        print(f'[inv] source sha256: {handle.source_hash_before}')
        print(f'[inv] mode         : {scope.label}')
        print(f'[inv] clock frozen : {instant.isoformat()}')

    invariants = registry.select(ids=ids)
    run_result = EngineRun(
        started_at=started, pvf_version=PVF_VERSION, mode=mode,
        scope=scope.label, business_date=scope_date or
        dataset_business_date.isoformat(),
        frozen_at=instant.isoformat(),
        source_db=handle.source_path,
        source_hash_before=handle.source_hash_before,
        copy_method=handle.method,
        registry_size=len(invariants),
        commissioning_gaps=registry.commissioning_gaps(),
    )
    (run_result.unbacked_commissioning_claims,
     run_result.commissioning_evidence_pack) =         registry.unbacked_commissioning_claims()

    freeze, proof = install_proven(instant)
    ctx = None
    try:
        app = _build_app(handle)
        freeze.rebind_loaded_modules()
        proof = freeze.prove()
        run_result.freeze_proven = bool(proof.get('proven'))
        run_result.app_version = _app_version()

        with app.app_context():
            ctx = Context(handle.copy_path, app=app, scope=scope,
                          business_date=run_result.business_date)
            ctx.install_sqlalchemy_meter()

            if not quiet:
                print(f'[inv] invariants   : {len(invariants)} registered')

            results = [evaluate_one(inv, ctx) for inv in invariants]
            run_result.results = results

            if prove_determinism:
                second = [evaluate_one(inv, ctx) for inv in invariants]
                first_map, second_map = _comparable(results), _comparable(second)
                run_result.repeatability_mismatches = sorted(
                    key for key in set(first_map) | set(second_map)
                    if first_map.get(key) != second_map.get(key))
                run_result.determinism_proven = (
                    not run_result.repeatability_mismatches)

                reversed_results = [evaluate_one(inv, ctx)
                                    for inv in reversed(invariants)]
                reversed_map = _comparable(reversed_results)
                run_result.order_mismatches = sorted(
                    key for key in set(first_map) | set(reversed_map)
                    if first_map.get(key) != reversed_map.get(key))
                run_result.order_independence_proven = (
                    not run_result.order_mismatches)
            else:
                run_result.determinism_proven = False
                run_result.order_independence_proven = False

            run_result.total_writes = sum(
                r.metering.db_writes for r in run_result.results)
            run_result.total_writes += ctx.metering.db_writes
    finally:
        if ctx is not None:
            ctx.close()
        freeze.uninstall()

    run_result.source_hash_after = assert_production_untouched(handle)
    run_result.read_only_verified = (
        run_result.source_hash_after == run_result.source_hash_before)
    run_result.finished_at = _utcnow()
    run_result.duration_seconds = round(time.perf_counter() - t0, 2)
    return run_result


# ---------------------------------------------------------------------------
# In-process evaluation against an already-prepared database
# ---------------------------------------------------------------------------

def evaluate_database(db_path: str, mode: str = Mode.ENTIRE_DATABASE,
                      business_date: str = '',
                      ids: list | None = None) -> list:
    """Evaluate the registry against *db_path* directly.

    Used by commissioning, which runs each seeded database in its own
    process. The database is treated as already disposable — no further
    copy is taken — so that a seeded fault is measured exactly as it was
    injected.
    """
    from verification.replay.timeline import read_business_date

    dataset_business_date = read_business_date(db_path)
    scope_date = business_date or (
        dataset_business_date.isoformat()
        if mode in (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT,
                    Mode.HISTORICAL_REPLAY) else '')
    scope = Scope(mode=mode, business_date=scope_date)

    freeze_date = (_dt.date.fromisoformat(scope_date) if scope_date
                   else dataset_business_date)
    instant = _dt.datetime.combine(freeze_date, FREEZE_TIME)

    os.environ['DATABASE_URL'] = 'sqlite:///' + db_path.replace('\\', '/')
    os.environ.setdefault('FLASK_ENV', 'production')

    freeze, _proof = install_proven(instant)
    ctx = None
    try:
        from app import create_app
        app = create_app()
        freeze.rebind_loaded_modules()
        with app.app_context():
            ctx = Context(db_path, app=app, scope=scope,
                          business_date=scope.business_date or
                          dataset_business_date.isoformat())
            ctx.install_sqlalchemy_meter()
            return [evaluate_one(inv, ctx)
                    for inv in registry.select(ids=ids)]
    finally:
        if ctx is not None:
            ctx.close()
        freeze.uninstall()
