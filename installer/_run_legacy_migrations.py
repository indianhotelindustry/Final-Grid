"""Run legacy custom migrations explicitly — patch_apply Phase 3 (v2.2.13).

The legacy migration system in app/__init__.py:_run_pending_migrations() is
a custom registry of (version, description, sql) tuples tracked in the
``schema_migrations`` table. It runs at app boot today; the v2.2.13
deployment governance overhaul requires it to also be invoked EXPLICITLY
from patch_apply.bat with errorlevel checking BEFORE the alembic stage.

Why an explicit pre-step
------------------------
Alembic owns schema from c4d5e6f7a8b9 onward. The legacy registry handled
schema additions before alembic was authoritative. On SQLite many legacy
migrations are PostgreSQL-only (DO $$ ... END $$) and are skipped by the
runner; on PostgreSQL they fire. Either way, the runner is idempotent
(tracks applied versions in schema_migrations).

The reason we still invoke it explicitly is governance: the user-approved
Phase 3 pipeline lists it as step 1 with its own errorlevel gate, so
operators can distinguish legacy-migration failures from alembic failures
in patch.log.

Invocation
----------
    venv\\Scripts\\python.exe installer\\_run_legacy_migrations.py

This boots the Flask app via create_app() — which internally calls
_run_pending_migrations(). If any legacy migration fails, create_app()
raises and this script exits non-zero.

Exit codes:
  0  legacy migrations applied (or no-op on already-applied state)
  1  Flask app failed to import / boot
  2  legacy migration runner raised an exception
"""
import logging
import os
import sys
import traceback


def main():
    # Make the app package importable from the installer/ directory.
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _APP_ROOT   = os.path.dirname(_SCRIPT_DIR)
    if _APP_ROOT not in sys.path:
        sys.path.insert(0, _APP_ROOT)

    os.environ.setdefault('FLASK_ENV', 'production')
    # Quiet the noisy security-mode WARNING-level banner during patch context.
    logging.disable(logging.WARNING)

    try:
        from app import create_app
    except Exception:
        print('FAIL: cannot import Flask app', file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        # create_app() invokes _run_pending_migrations() internally
        # (app/__init__.py around line 486). If any legacy migration raises,
        # this boot fails and we exit non-zero.
        app = create_app()
    except Exception:
        print('FAIL: legacy migration runner raised', file=sys.stderr)
        traceback.print_exc()
        return 2

    # Use the app context once to confirm DB connectivity post-legacy-migration.
    try:
        with app.app_context():
            from app.models import db
            db.session.execute(db.text('SELECT 1')).scalar()
    except Exception:
        print('FAIL: post-legacy-migration DB ping failed', file=sys.stderr)
        traceback.print_exc()
        return 2

    print('OK: legacy migration runner completed (or no pending entries)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
