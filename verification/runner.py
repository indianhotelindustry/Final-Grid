"""
Parity harness orchestration.

Responsibilities, in order:
  1. Take a disposable copy of production and fingerprint the original.
  2. Build a Flask application bound to the COPY (never production).
  3. Measure all 22 quantities.
  4. Re-verify production is byte-identical.
  5. Emit an evidence pack.

Step 4 is not a formality. It is the positive evidence required by
Principle 11 — the harness proves it did no harm rather than merely
asserting it.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import time

from verification import __version__ as PVF_VERSION
from verification.config import (
    BASELINE_DIR, Mode, PRODUCTION_DB, Verdict,
)
from verification.dbcopy import (
    CopyHandle, assert_production_untouched, make_copy, sqlalchemy_url,
)
from verification.evidence import RunResult, write_pack


def _utcnow() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat()


def _build_app(handle: CopyHandle):
    """Create a Flask app bound to the working copy.

    ``create_app()`` writes — migrations, the SQLite column fixer and
    ``init_data()`` seeding all commit. That is precisely why it is
    pointed at the copy and never at production.
    """
    # Ensure the project root is importable when run as a script.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    os.environ['DATABASE_URL'] = sqlalchemy_url(handle)
    os.environ.setdefault('FLASK_ENV', 'production')

    from app import create_app
    return create_app()


def run(mode: str = Mode.CROSS_IMPLEMENTATION,
        source: str = PRODUCTION_DB,
        tag: str = '',
        quiet: bool = False) -> tuple[RunResult, str]:
    """Execute a parity run. Returns ``(result, evidence_dir)``."""
    started = _utcnow()
    t0 = time.perf_counter()

    handle = make_copy(source=source)
    if not quiet:
        print(f'[pvf] working copy: {handle.copy_path} ({handle.method})')
        print(f'[pvf] source sha256: {handle.source_hash_before}')

    app = _build_app(handle)

    from verification.quantities import Context, measure_all

    with app.app_context():
        ctx = Context(app)
        if not quiet:
            print(f'[pvf] measuring 22 quantities over '
                  f'{len(ctx.reservations)} reservations, '
                  f'{len(ctx.activity_dates)} activity dates...')
        results = measure_all(ctx)
        # Nothing in this package writes, but roll back explicitly so an
        # accidental future write can never be committed by the harness.
        ctx.db.session.rollback()

    hash_after = assert_production_untouched(handle)

    result = RunResult(
        mode=mode,
        started_at=started,
        finished_at=_utcnow(),
        duration_seconds=round(time.perf_counter() - t0, 2),
        app_version=_app_version(),
        pvf_version=PVF_VERSION,
        source_db=handle.source_path,
        source_hash_before=handle.source_hash_before,
        source_hash_after=hash_after,
        source_size_bytes=handle.source_size,
        copy_method=handle.method,
        read_only_verified=(hash_after == handle.source_hash_before),
        quantities=results,
    )

    evidence_dir = write_pack(result, tag=tag or mode.replace('-', '_'))

    if mode == Mode.BASELINE:
        _write_baseline(result, tag or 'default')

    return result, evidence_dir


def _app_version() -> str:
    try:
        from app import APP_VERSION
        return APP_VERSION
    except Exception:
        return 'unknown'


# ---------------------------------------------------------------------------
# Baseline / compare
# ---------------------------------------------------------------------------

def _baseline_path(name: str) -> str:
    return os.path.join(BASELINE_DIR, f'{name}.json')


def _baseline_payload(result: RunResult) -> dict:
    """Only the comparable surface: quantity -> implementation -> value.

    Deliberately excludes timings and hashes, which legitimately differ
    between runs and would make every comparison noisy.
    """
    return {
        'app_version': result.app_version,
        'pvf_version': result.pvf_version,
        'captured_at': result.started_at,
        'quantities': {
            q.quantity_id: {
                'label': q.label,
                'verdict': q.verdict,
                'implementations': {k: str(v)
                                    for k, v in sorted(q.implementations.items())},
            }
            for q in sorted(result.quantities, key=lambda x: x.quantity_id)
        },
    }


def _write_baseline(result: RunResult, name: str) -> str:
    os.makedirs(BASELINE_DIR, exist_ok=True)
    path = _baseline_path(name)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(_baseline_payload(result), fh, indent=2, sort_keys=True)
        fh.write('\n')
    return path


def compare_to_baseline(result: RunResult, name: str) -> dict:
    """Diff a run against a stored baseline.

    Reports movement in BOTH directions: a value that changed when it was
    expected to hold, and a value that held when it was expected to move.
    The second case is the one teams forget, and it means the change under
    test did not take effect.
    """
    path = _baseline_path(name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f'No baseline named {name!r}. Capture one first:\n'
            f'    python -m verification baseline --tag {name}')

    with open(path, encoding='utf-8') as fh:
        base = json.load(fh)

    current = _baseline_payload(result)
    changes: list[dict] = []
    for qid, cur in current['quantities'].items():
        old = base['quantities'].get(qid)
        if old is None:
            changes.append({'quantity': qid, 'kind': 'ADDED',
                            'label': cur['label']})
            continue
        for impl, val in cur['implementations'].items():
            prev = old['implementations'].get(impl)
            if prev is None:
                changes.append({'quantity': qid, 'kind': 'IMPL_ADDED',
                                'implementation': impl, 'now': val})
            elif prev != val:
                changes.append({'quantity': qid, 'kind': 'VALUE_CHANGED',
                                'implementation': impl,
                                'baseline': prev, 'now': val})
        for impl in old['implementations']:
            if impl not in cur['implementations']:
                changes.append({'quantity': qid, 'kind': 'IMPL_REMOVED',
                                'implementation': impl,
                                'baseline': old['implementations'][impl]})
        if old['verdict'] != cur['verdict']:
            changes.append({'quantity': qid, 'kind': 'VERDICT_CHANGED',
                            'baseline': old['verdict'], 'now': cur['verdict']})
    for qid, old in base['quantities'].items():
        if qid not in current['quantities']:
            changes.append({'quantity': qid, 'kind': 'REMOVED',
                            'label': old['label']})

    return {
        'baseline_name': name,
        'baseline_captured_at': base.get('captured_at'),
        'baseline_app_version': base.get('app_version'),
        'current_app_version': current['app_version'],
        'change_count': len(changes),
        'changes': sorted(changes, key=lambda c: (c['quantity'], c['kind'])),
    }
