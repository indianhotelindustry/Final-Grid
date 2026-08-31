"""
PVF command-line entry point.

    python -m verification run                 cross-implementation parity run
    python -m verification baseline --tag X    capture a baseline
    python -m verification compare  --tag X    diff against a baseline
    python -m verification selfcheck           read-only guarantee only

Exit codes are meaningful so the pipeline can gate on them:
    0  PASS
    1  FAIL       — a blocking divergence
    2  INCOMPLETE — quantities not implemented or vacuous
    3  ERROR      — a measurement raised
    4  UNVERIFIED — read-only guarantee not established
"""
from __future__ import annotations

import argparse
import json
import sys

from verification.config import Mode
from verification.evidence import render_report

EXIT = {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2, 'ERROR': 3, 'UNVERIFIED': 4}



def _maybe_apply_fip_patch() -> str:
    """Install a D5 engine patch if one was requested by environment.

    One hook, honoured by every internal probe entry point, so a Class C
    fault does not need four separate plumbings. Reads
    ``PVF_FIP_PATCH``; absent in every normal run. The wrapper lives and
    dies inside the probe subprocess and no file under ``app/`` is
    touched.
    """
    import os
    spec = os.environ.get('PVF_FIP_PATCH', '')
    if not spec:
        return ''
    from verification.faults.injection import apply_patch
    apply_patch(spec)
    return spec


def _cmd_run(args) -> int:
    from verification.runner import run
    result, evidence_dir = run(mode=Mode.CROSS_IMPLEMENTATION, tag=args.tag)
    print()
    print(render_report(result))
    print(f'[pvf] evidence pack: {evidence_dir}')
    return EXIT.get(result.overall, 3)


def _cmd_baseline(args) -> int:
    from verification.runner import run
    result, evidence_dir = run(mode=Mode.BASELINE, tag=args.tag)
    print()
    print(render_report(result))
    print(f'[pvf] evidence pack: {evidence_dir}')
    print(f'[pvf] baseline captured: {args.tag}')
    return EXIT.get(result.overall, 3)


def _cmd_compare(args) -> int:
    from verification.runner import run, compare_to_baseline
    result, evidence_dir = run(mode=Mode.COMPARE, tag=args.tag)
    diff = compare_to_baseline(result, args.tag)
    print()
    print(render_report(result))
    print('=' * 100)
    print(f'BASELINE COMPARISON — {diff["baseline_name"]} '
          f'(captured {diff["baseline_captured_at"]}, '
          f'app v{diff["baseline_app_version"]} -> v{diff["current_app_version"]})')
    print('=' * 100)
    if not diff['changes']:
        print('  No change against baseline.')
    else:
        for c in diff['changes']:
            print(f'  [{c["kind"]:<15}] {c["quantity"]}  '
                  f'{c.get("implementation", "")}')
            if 'baseline' in c:
                print(f'      baseline: {c["baseline"]}')
                print(f'      now:      {c.get("now")}')
    print()
    print(f'[pvf] evidence pack: {evidence_dir}')
    with open(f'{evidence_dir}/baseline_diff.json', 'w', encoding='utf-8') as fh:
        json.dump(diff, fh, indent=2, sort_keys=True)
        fh.write('\n')
    if diff['changes'] and result.overall == 'PASS':
        return 1
    return EXIT.get(result.overall, 3)


def _cmd_measure(args) -> int:
    """Internal: measure an ALREADY-PREPARED database and emit JSON.

    Used by the commissioning harness, which runs each seeded fault in a
    separate process so that one measurement can never contaminate the
    next through module-level application state.
    """
    import os
    _maybe_apply_fip_patch()
    os.environ['DATABASE_URL'] = 'sqlite:///' + args.db.replace('\\', '/')
    os.environ.setdefault('FLASK_ENV', 'production')

    from app import create_app
    from verification.quantities import Context, measure_all

    app = create_app()
    with app.app_context():
        ctx = Context(app)
        results = measure_all(ctx)
        ctx.db.session.rollback()

    print('---PVF-JSON---')
    print(json.dumps(
        {q.quantity_id: {
            'verdict': q.verdict,
            'divergences': len(q.divergences),
            # Implementation VALUES are required so commissioning can
            # detect a fault in a quantity that was already diverging:
            # there, the verdict and the divergence count both hold
            # steady while the underlying figures move.
            'implementations': {k: str(v)
                                for k, v in sorted(q.implementations.items())},
        } for q in results},
        sort_keys=True))
    return 0


def _cmd_commission(args) -> int:
    from verification.commission import commission
    return commission(verbose=not args.quiet)


def _cmd_gm_capture(args) -> int:
    """Capture golden masters for every catalogued surface."""
    from verification.golden.capture import run_capture, write_masters
    from verification.golden import report as gmreport

    run = run_capture(quiet=args.quiet)
    text = gmreport.render_capture(run)
    print()
    print(text)
    evidence = gmreport.write_pack(gmreport.capture_payload(run), text,
                                   f'gm_capture_{args.tag}', run.started_at)
    print(f'[gm] evidence pack: {evidence}')
    if args.dry_run:
        print('[gm] dry run — masters NOT written')
    else:
        out = write_masters(run, args.tag)
        print(f'[gm] masters written: {out}')
    if not run.read_only_verified:
        return 4
    return 0


def _cmd_gm_verify(args) -> int:
    """Re-capture and diff against a stored master set."""
    from verification.golden.capture import run_capture, read_masters
    from verification.golden.compare import compare
    from verification.golden import report as gmreport

    index, masters = read_masters(args.tag)
    run = run_capture(quiet=args.quiet)
    result = compare(run.surfaces, masters, index, args.tag)
    text = gmreport.render_comparison(result, run)
    print()
    print(text)
    evidence = gmreport.write_pack(gmreport.comparison_payload(result, run),
                                   text, f'gm_verify_{args.tag}',
                                   run.started_at)
    print(f'[gm] evidence pack: {evidence}')
    if not run.read_only_verified:
        return 4
    return {'PASS': 0, 'FAIL': 1, 'WARN': 2}[result.verdict]


def _cmd_gm_commission(args) -> int:
    from verification.golden.commission import commission
    return commission(verbose=not args.quiet)


def _cmd_gm_capture_json(args) -> int:
    """Internal: capture and dump a comparable digest as JSON.

    Used by golden master commissioning, which runs each seeded fault in
    a separate process so that module-level application state, and the
    clock patch, can never leak between measurements.
    """
    import os
    _maybe_apply_fip_patch()
    from verification.golden.capture import run_capture
    from dataclasses import asdict

    run = run_capture(source=args.db, quiet=True)
    print('---GM-JSON---')
    print(json.dumps({
        s.surface_id: {
            'status': s.status,
            'anon_status': s.anon_status,
            'body_sha256': s.body_sha256,
            'figures': s.figures,
            'templates': s.templates,
        } for s in run.surfaces}, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# D3 — historical replay
# ---------------------------------------------------------------------------

def _replay_window(args):
    import datetime as _dt
    frm = _dt.date.fromisoformat(args.from_date) if args.from_date else None
    to = _dt.date.fromisoformat(args.to_date) if args.to_date else None
    return frm, to


def _cmd_replay(args) -> int:
    """Replay every historical business date and reconcile it."""
    from verification.replay.replay import run_replay, write_ledgers
    from verification.replay import report as rpreport

    frm, to = _replay_window(args)
    run = run_replay(from_date=frm, to_date=to,
                     prove_order=not args.fast, quiet=args.quiet)
    text = rpreport.render_replay(run)
    print()
    print(text)
    evidence = rpreport.write_pack(rpreport.replay_payload(run), text,
                                   f'replay_{args.tag}', run.started_at)
    print(f'[replay] evidence pack: {evidence}')
    if args.dry_run:
        print('[replay] dry run — stored replay NOT written')
    else:
        out = write_ledgers(run, args.tag)
        print(f'[replay] stored replay written: {out}')
    if not run.read_only_verified:
        return 4
    return EXIT.get(run.overall, 3)


def _cmd_replay_verify(args) -> int:
    """Re-replay history and diff against a stored replay."""
    from verification.replay.replay import run_replay, read_ledgers
    from verification.replay.compare import compare
    from verification.replay import report as rpreport

    index, stored = read_ledgers(args.tag)
    frm, to = _replay_window(args)
    run = run_replay(from_date=frm, to_date=to,
                     prove_order=not args.fast, quiet=args.quiet)
    result = compare(run, stored, index, args.tag)
    text = rpreport.render_comparison(result, run)
    print()
    print(text)
    evidence = rpreport.write_pack(
        rpreport.comparison_payload(result, run), text,
        f'replay_verify_{args.tag}', run.started_at)
    print(f'[replay] evidence pack: {evidence}')
    if not run.read_only_verified:
        return 4
    return {'PASS': 0, 'FAIL': 1, 'WARN': 2}[result.verdict]


def _cmd_replay_commission(args) -> int:
    from verification.replay.commission import commission
    return commission(verbose=not args.quiet)


def _cmd_replay_json(args) -> int:
    """Internal: replay an ALREADY-PREPARED database and emit a digest.

    Used by replay commissioning, which runs every seeded fault in its
    own process so that the clock patch and the Flask application cannot
    leak state between measurements.
    """
    _maybe_apply_fip_patch()
    from verification.replay.replay import run_replay

    run = run_replay(source=args.db, prove_order=False, quiet=True)
    print('---REPLAY-JSON---')
    print(json.dumps({
        'business_date': run.business_date,
        'overall': run.overall,
        'blocking': run.blocking,
        'ledger_stable': run.ledger_stable,
        'dates': {
            d.date: {
                'ledger': d.ledger,
                'engine': d.engine,
                'recorded': d.recorded,
                'is_closed': d.is_closed,
                'snapshot_matches': bool(
                    d.snapshot_integrity.get('matches', True)),
                'reconciliations': {r.rule_id: r.status
                                    for r in d.reconciliations},
                'history_drift': [x['path'] for x in d.history_drift],
                'asat_drift': [x['path'] for x in d.asat_drift],
            } for d in run.dates},
    }, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# D4 — financial invariant engine
# ---------------------------------------------------------------------------

def _cmd_inv_registry(args) -> int:
    """Print the registry and its matrices. Touches no database."""
    from verification.invariants import report as invreport

    text = invreport.render_registry()
    print(text)
    if args.tag:
        evidence = invreport.write_pack(
            invreport.registry_payload(), text, f'inv_registry_{args.tag}',
            __import__('datetime').datetime.utcnow()
            .replace(microsecond=0).isoformat())
        print(f'[inv] evidence pack: {evidence}')
    return 0


def _cmd_inv_run(args) -> int:
    """Evaluate the invariant registry."""
    from verification.invariants.engine import run as inv_run
    from verification.invariants import report as invreport

    run = inv_run(mode=args.mode, business_date=args.date,
                  reservation_id=args.reservation,
                  ids=args.id or None,
                  prove_determinism=not args.fast, quiet=args.quiet)
    text = invreport.render_run(run)
    print()
    print(text)
    evidence = invreport.write_pack(invreport.run_payload(run), text,
                                    f'inv_run_{args.tag}', run.started_at)
    print(f'[inv] evidence pack: {evidence}')
    if not run.read_only_verified:
        return 4
    return EXIT.get(run.overall, 3)


def _cmd_inv_history(args) -> int:
    """Replay every date-capable invariant across the dataset's history."""
    import datetime as _dt

    from verification.invariants.history import run_history
    from verification.invariants import report as invreport

    frm = _dt.date.fromisoformat(args.from_date) if args.from_date else None
    to = _dt.date.fromisoformat(args.to_date) if args.to_date else None
    run = run_history(ids=args.id or None, from_date=frm, to_date=to,
                      quiet=args.quiet)
    text = invreport.render_history(run)
    print()
    print(text)
    evidence = invreport.write_pack(invreport.history_payload(run), text,
                                    f'inv_history_{args.tag}', run.started_at)
    print(f'[inv] evidence pack: {evidence}')
    if not run.read_only_verified:
        return 4
    return {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2}.get(run.verdict, 3)


def _cmd_inv_commission(args) -> int:
    from verification.invariants.commission import commission
    return commission(ids=args.id or None, verbose=not args.quiet)


def _apply_engine_patch(spec: str) -> None:
    """Perturb a canonical engine's return value, in THIS process only.

    Used by commissioning to inject a fault into an invariant that no
    data mutation can break — one that checks a canonical engine's own
    outputs against each other. The wrapper is installed on the imported
    module object inside a throwaway subprocess; no file under ``app/``
    is touched and nothing survives the process.
    """
    import importlib

    target, key, delta = spec.split('|')
    module_name, attribute = target.rsplit('.', 1)
    module = importlib.import_module(module_name)
    original = getattr(module, attribute)
    shift = float(delta)

    def patched(*a, **kw):
        result = original(*a, **kw)
        if isinstance(result, dict) and key in result:
            result = dict(result)
            try:
                result[key] = float(result[key]) + shift
            except (TypeError, ValueError):
                pass
        return result

    patched.__name__ = getattr(original, '__name__', attribute)
    setattr(module, attribute, patched)


def _cmd_inv_json(args) -> int:
    """Internal: evaluate an ALREADY-PREPARED database and emit a digest.

    Used by invariant commissioning, which runs every seeded fault in its
    own process so that the clock patch, the Flask application and any
    engine patch cannot leak between measurements.
    """
    from dataclasses import asdict

    if args.patch:
        # Imported before the engine builds the app so that any module
        # binding the target picks up the wrapper.
        _apply_engine_patch(args.patch)
    _maybe_apply_fip_patch()

    from verification.invariants.engine import evaluate_database
    from verification.invariants import registry as invregistry

    invariants = invregistry.select()
    first = evaluate_database(args.db)
    second = evaluate_database(args.db)
    reverse_ids = [i.invariant_id for i in reversed(invariants)]
    reversed_run = evaluate_database(args.db, ids=reverse_ids)

    def digest(results):
        return {r.invariant_id: {
            'status': r.status,
            'population': r.population,
            'violations': r.violation_count,
            'affected_objects': list(r.evidence.affected_objects),
            'evidence': asdict(r.evidence),
            'writes': r.metering.db_writes,
        } for r in results}

    d1, d2, d3 = digest(first), digest(second), digest(reversed_run)

    def mismatches(a, b):
        keys = ('status', 'population', 'violations', 'affected_objects')
        return sorted(k for k in set(a) | set(b)
                      if any(a.get(k, {}).get(f) != b.get(k, {}).get(f)
                             for f in keys))

    print('---INV-JSON---')
    print(json.dumps({
        'invariants': d1,
        'repeatability_mismatches': mismatches(d1, d2),
        'order_mismatches': mismatches(d1, d3),
        'total_writes': sum(r.metering.db_writes for r in first),
    }, sort_keys=True, default=str))
    return 0


def _cmd_ds_registry(args) -> int:
    """Print the dataset registry. Touches no database."""
    from verification.datasets import report as dsreport

    text = dsreport.render_registry()
    print(text)
    if args.tag:
        import datetime as _dt
        started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
        pack = dsreport.write_pack(dsreport.registry_payload(), text,
                                   f'ds_registry_{args.tag}', started)
        print(f'[ds] evidence pack: {pack}')
    return 0


def _cmd_ds_build(args) -> int:
    """Materialise one dataset and report what it produced."""
    from verification.datasets import builder, registry

    # registry.get raises KeyError for an unknown id rather than returning
    # None. An unknown id is a usage error, not a crash.
    try:
        d = registry.get(args.id)
    except KeyError:
        known = [x.key for x in registry.all_datasets()]
        print(f'unknown dataset {args.id!r}. '
              f'Registered: {", ".join(known) if known else "none"}')
        return 3

    m = builder.build(d)
    print(f'dataset          : {d.key}')
    print(f'database         : {m.db_path}')
    print(f'rows removed     : {m.rows_removed}')
    print(f'rows inserted    : {m.rows_inserted}')
    print(f'tables touched   : {len(m.tables_touched)}')
    print(f'business date    : {m.business_date}')
    print(f'content hash     : {m.content_hash}')
    print(f'production intact: {m.production_unchanged}')
    if m.error:
        print(f'ERROR            : {m.error}')
    if not args.keep:
        builder.discard(m)
        print('copy discarded.')
    if m.error:
        return 3
    return 0 if m.production_unchanged else 4


def _cmd_ds_run(args) -> int:
    """Evaluate every dataset against its own declaration."""
    from verification.datasets import builder, evaluate, registry

    datasets = registry.select(ids=args.id) if args.id \
        else registry.all_datasets()
    if not datasets:
        print('No dataset is registered, so nothing was evaluated.')
        print()
        print('The verdict is INCOMPLETE, never PASS: a platform that has')
        print('measured nothing has demonstrated nothing, and reporting that')
        print('as a pass would be silence presented as evidence (P10).')
        return 2

    failed = 0
    for d in datasets:
        if not args.quiet:
            print(f'[ds] evaluating {d.key} …')
        m = builder.build(d)
        try:
            result = evaluate.evaluate(d, m)
            print(f'  {d.key:<28} {result.verdict:<12} '
                  f'met={len(result.met)} unmet={len(result.unmet)} '
                  f'not_run={len(result.not_run)}')
            if result.verdict != 'PASS':
                failed += 1
        finally:
            builder.discard(m)
    return 1 if failed else 0


def _cmd_ds_coverage(args) -> int:
    """Measure what a dataset adds, loses and changes against production.

    Exit 0 when coverage moved exactly as the dataset declared, 1 when it
    did not. An undeclared loss is a failure and not a warning: a dataset
    that quietly stops covering something while still reporting PASS on
    every expectation it declared is the specific failure this ledger was
    built after.
    """
    import datetime as _dt

    from verification.config import PRODUCTION_DB
    from verification.datasets import builder, coverage, registry
    from verification.datasets import report as dsreport
    from verification.dbcopy import make_copy, production_fingerprint

    started_at = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    d = registry.get(args.id)

    before, _size = production_fingerprint(PRODUCTION_DB)

    # Production is measured through a copy, never the live file: the
    # golden-master capture drives the application, and pointing that at
    # production to establish a baseline would put the thing being
    # protected in the path of the measurement.
    print(f'[cov] measuring production baseline ...')
    handle = make_copy(name='coverage_baseline.db', source=PRODUCTION_DB)
    baseline = coverage.measure(handle.copy_path, 'production')

    print(f'[cov] building and measuring {d.key} ...')
    materialisation = builder.build(d, slot='_coverage')
    if not materialisation.ok:
        print(f'[cov] ERROR: {materialisation.error}')
        return 3
    try:
        snapshot = coverage.measure(materialisation.db_path, d.key)
    finally:
        builder.discard(materialisation)

    delta = coverage.compare(baseline, snapshot, d.coverage_expectation,
                             d.expectations.invariants,
                             d.expectations.parity)
    text = coverage.render(delta)
    print()
    print(text)

    after, _size = production_fingerprint(PRODUCTION_DB)
    if after != before:
        print('[cov] PRODUCTION CHANGED during measurement. Result void.')
        return 4

    if args.tag:
        payload = {'started_at': started_at,
                   'dataset': d.key,
                   'content_hash': materialisation.content_hash,
                   'production_sha256': after,
                   'production_unchanged': True,
                   'baseline': baseline.as_dict(),
                   'snapshot': snapshot.as_dict(),
                   'declared': {k: list(v) for k, v in
                                d.coverage_expectation.items()},
                   'ledger': delta.as_dict()}
        pack = dsreport.write_pack(payload, text, f'ds_coverage_{args.tag}',
                                   started_at)
        print(f'[cov] evidence pack: {pack}')

    return 0 if delta.clean else 1


def _cmd_ds_commission(args) -> int:
    """Prove every dataset can be made to fail."""
    from verification.datasets import commission
    from verification.datasets import report as dsreport

    run = commission.run(ids=args.id or None, quiet=args.quiet)
    text = dsreport.render_commission(run)
    print()
    print(text)
    if args.tag:
        pack = dsreport.write_pack(commission.payload(run), text,
                                   f'ds_commission_{args.tag}',
                                   run.started_at)
        print(f'[ds] evidence pack: {pack}')
    return run.exit_code


def _cmd_fault_registry(args) -> int:
    """Print the fault taxonomy. No database is touched."""
    from verification.faults import report as fipreport

    text = fipreport.render_registry()
    print(text)
    if args.tag:
        import datetime as _dt
        started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
        pack = fipreport.write_pack(fipreport.registry_payload(), text,
                                    f'fip_registry_{args.tag}', started)
        print(f'[fip] evidence pack: {pack}')
    return 0


def _cmd_fault_run(args) -> int:
    """Challenge the verification framework with the fault registry."""
    from verification.faults import pipeline
    from verification.faults import report as fipreport
    from verification.faults.model import ALL_LAYERS

    layers = tuple(args.layer) if args.layer else ALL_LAYERS
    unknown = [l for l in layers if l not in ALL_LAYERS]
    if unknown:
        print(f'unknown layer(s): {", ".join(unknown)}; '
              f'known: {", ".join(ALL_LAYERS)}')
        return 3

    run = pipeline.run(mode=args.mode, ids=args.id or None,
                       category=args.category or None, layers=layers,
                       parallel=not args.serial, quiet=args.quiet)
    text = fipreport.render_run(run)
    print()
    print(text)
    pack = fipreport.write_pack(fipreport.run_payload(run), text,
                                f'fip_run_{args.tag}', run.started_at)
    print(f'[fip] evidence pack: {pack}')
    if not run.isolation_verified:
        return 4
    return EXIT.get(run.overall, 3)


def _cmd_fault_commission(args) -> int:
    from verification.faults.commission import commission
    return commission(ids=args.id or None, verbose=not args.quiet)


def _cmd_selfcheck(args) -> int:
    """Prove the read-only guarantee without running measurements."""
    from verification.dbcopy import (make_copy, assert_production_untouched,
                                     production_fingerprint)
    from verification.config import PRODUCTION_DB

    before, size = production_fingerprint(PRODUCTION_DB)
    print(f'production : {PRODUCTION_DB}')
    print(f'size       : {size:,} bytes')
    print(f'sha256     : {before}')
    handle = make_copy(name='pvf_selfcheck.db')
    print(f'copy       : {handle.copy_path} via {handle.method}')
    after = assert_production_untouched(handle)
    ok = after == before
    print(f'sha256 now : {after}')
    print(f'VERDICT    : {"READ-ONLY VERIFIED" if ok else "*** PRODUCTION MODIFIED ***"}')
    return 0 if ok else 4


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog='python -m verification',
        description='FinalGrid — Financial Parity Harness (PVF D1)')
    sub = p.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('run', help='cross-implementation parity run')
    r.add_argument('--tag', default='')
    r.set_defaults(fn=_cmd_run)

    b = sub.add_parser('baseline', help='capture a baseline for later comparison')
    b.add_argument('--tag', required=True)
    b.set_defaults(fn=_cmd_baseline)

    c = sub.add_parser('compare', help='diff a run against a stored baseline')
    c.add_argument('--tag', required=True)
    c.set_defaults(fn=_cmd_compare)

    s = sub.add_parser('selfcheck', help='prove the read-only guarantee only')
    s.set_defaults(fn=_cmd_selfcheck)

    k = sub.add_parser('commission',
                       help='seeded-fault commissioning (Principle 9)')
    k.add_argument('--quiet', action='store_true')
    k.set_defaults(fn=_cmd_commission)

    m = sub.add_parser('_measure', help=argparse.SUPPRESS)
    m.add_argument('--db', required=True)
    m.set_defaults(fn=_cmd_measure)

    # -- D2: golden master ------------------------------------------------
    gc = sub.add_parser('gm-capture',
                        help='capture golden masters for every surface')
    gc.add_argument('--tag', default='production')
    gc.add_argument('--quiet', action='store_true')
    gc.add_argument('--dry-run', action='store_true',
                    help='capture and report without writing masters')
    gc.set_defaults(fn=_cmd_gm_capture)

    gv = sub.add_parser('gm-verify',
                        help='re-capture and diff against stored masters')
    gv.add_argument('--tag', default='production')
    gv.add_argument('--quiet', action='store_true')
    gv.set_defaults(fn=_cmd_gm_verify)

    gk = sub.add_parser('gm-commission',
                        help='seeded-fault commissioning of the golden master')
    gk.add_argument('--quiet', action='store_true')
    gk.set_defaults(fn=_cmd_gm_commission)

    gj = sub.add_parser('_gm_capture_json', help=argparse.SUPPRESS)
    gj.add_argument('--db', required=True)
    gj.set_defaults(fn=_cmd_gm_capture_json)

    # -- D3: historical replay --------------------------------------------
    rp = sub.add_parser('replay',
                        help='replay and reconcile every historical date')
    rp.add_argument('--tag', default='production')
    rp.add_argument('--from', dest='from_date', default='',
                    help='earliest date to replay (ISO)')
    rp.add_argument('--to', dest='to_date', default='',
                    help='latest date to replay (ISO)')
    rp.add_argument('--fast', action='store_true',
                    help='skip the reverse-order pass (the order-independence '
                         'proof); reported as not run')
    rp.add_argument('--dry-run', action='store_true',
                    help='replay and report without writing the stored replay')
    rp.add_argument('--quiet', action='store_true')
    rp.set_defaults(fn=_cmd_replay)

    rv = sub.add_parser('replay-verify',
                        help='re-replay history and diff against a stored replay')
    rv.add_argument('--tag', default='production')
    rv.add_argument('--from', dest='from_date', default='')
    rv.add_argument('--to', dest='to_date', default='')
    rv.add_argument('--fast', action='store_true')
    rv.add_argument('--quiet', action='store_true')
    rv.set_defaults(fn=_cmd_replay_verify)

    rk = sub.add_parser('replay-commission',
                        help='seeded-fault commissioning of historical replay')
    rk.add_argument('--quiet', action='store_true')
    rk.set_defaults(fn=_cmd_replay_commission)

    rj = sub.add_parser('_replay_json', help=argparse.SUPPRESS)
    rj.add_argument('--db', required=True)
    rj.set_defaults(fn=_cmd_replay_json)

    # -- D4: financial invariant engine ------------------------------------
    ir = sub.add_parser('inv-registry',
                        help='print the invariant registry and its matrices')
    ir.add_argument('--tag', default='',
                    help='also write an evidence pack under this tag')
    ir.set_defaults(fn=_cmd_inv_registry)

    iv = sub.add_parser('inv-run', help='evaluate the invariant registry')
    iv.add_argument('--mode', default='ENTIRE_DATABASE',
                    help='validation mode (see inv-registry mode matrix)')
    iv.add_argument('--date', default='',
                    help='business date, for date-scoped modes')
    iv.add_argument('--reservation', type=int, default=0,
                    help='reservation id, for SINGLE_RESERVATION mode')
    iv.add_argument('--id', action='append',
                    help='evaluate only these invariants (repeatable)')
    iv.add_argument('--tag', default='production')
    iv.add_argument('--fast', action='store_true',
                    help='skip the repeatability and reverse-order passes; '
                         'the run is then reported as UNVERIFIED')
    iv.add_argument('--quiet', action='store_true')
    iv.set_defaults(fn=_cmd_inv_run)

    ih = sub.add_parser('inv-history',
                        help='replay every date-capable invariant across history')
    ih.add_argument('--id', action='append')
    ih.add_argument('--from', dest='from_date', default='')
    ih.add_argument('--to', dest='to_date', default='')
    ih.add_argument('--tag', default='production')
    ih.add_argument('--quiet', action='store_true')
    ih.set_defaults(fn=_cmd_inv_history)

    ik = sub.add_parser('inv-commission',
                        help='commission every invariant (eight elements each)')
    ik.add_argument('--id', action='append')
    ik.add_argument('--quiet', action='store_true')
    ik.set_defaults(fn=_cmd_inv_commission)

    ij = sub.add_parser('_inv_json', help=argparse.SUPPRESS)
    ij.add_argument('--db', required=True)
    ij.add_argument('--patch', default='')
    ij.set_defaults(fn=_cmd_inv_json)

    # -- D5: fault injection platform --------------------------------------
    fr = sub.add_parser('fault-registry',
                        help='print the fault taxonomy and its matrices')
    fr.add_argument('--tag', default='',
                    help='also write an evidence pack under this tag')
    fr.set_defaults(fn=_cmd_fault_registry)

    fn_ = sub.add_parser(
        'fault-run',
        help='inject every fault and sweep the verification framework')
    fn_.add_argument('--id', action='append',
                     help='challenge only these faults (repeatable)')
    fn_.add_argument('--category', default='',
                     help='A-BUSINESS, B-DATA, C-ENGINE or D-OPERATIONAL')
    fn_.add_argument('--layer', action='append',
                     help='sweep only these layers (repeatable). A layer '
                          'skipped for cost is a layer that reported nothing')
    fn_.add_argument('--mode', default='BATCH')
    fn_.add_argument('--serial', action='store_true',
                     help='run probes one at a time instead of concurrently')
    fn_.add_argument('--tag', default='production')
    fn_.add_argument('--quiet', action='store_true')
    fn_.set_defaults(fn=_cmd_fault_run)

    fk = sub.add_parser(
        'fault-commission',
        help='commission every fault (nine elements) and self-verify the '
             'platform')
    fk.add_argument('--id', action='append')
    fk.add_argument('--quiet', action='store_true')
    fk.set_defaults(fn=_cmd_fault_commission)

    # -- D6: regression dataset platform -----------------------------------
    dr = sub.add_parser('ds-registry',
                        help='print the dataset registry and its matrices')
    dr.add_argument('--tag', default='',
                    help='also write an evidence pack under this tag')
    dr.set_defaults(fn=_cmd_ds_registry)

    db_ = sub.add_parser('ds-build',
                         help='materialise a dataset into its own database')
    db_.add_argument('--id', required=True,
                     help='dataset id, or id@version')
    db_.add_argument('--keep', action='store_true',
                     help='do not discard the built copy')
    db_.set_defaults(fn=_cmd_ds_build)

    dn = sub.add_parser('ds-run',
                        help='evaluate every dataset against its declaration')
    dn.add_argument('--id', action='append',
                    help='evaluate only these datasets (repeatable)')
    dn.add_argument('--tag', default='production')
    dn.add_argument('--quiet', action='store_true')
    dn.set_defaults(fn=_cmd_ds_run)

    dk = sub.add_parser(
        'ds-commission',
        help='commission every dataset (six elements): prove it discriminates')
    dk.add_argument('--id', action='append')
    dk.add_argument('--tag', default='')
    dk.add_argument('--quiet', action='store_true')
    dk.set_defaults(fn=_cmd_ds_commission)

    dv = sub.add_parser(
        'ds-coverage',
        help='what a dataset adds, loses and changes against production')
    dv.add_argument('--id', required=True)
    dv.add_argument('--tag', default='')
    dv.set_defaults(fn=_cmd_ds_coverage)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
