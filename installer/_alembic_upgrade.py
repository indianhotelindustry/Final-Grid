"""Alembic upgrade runner — Sukoon PMS patch_apply (v2.2.12).

Replaces the multi-line ``python -c "..."`` heredoc that previously called
``flask_migrate.upgrade()``. The heredoc did not execute under cmd.exe
batch (see the v2.2.11 incident analysis); migrations silently never ran,
and the cmd-misinterpreted exit code happened to be non-zero, which masked
the bug as a "MIGRATION FAILED" log line.

Invoked from patch_apply.bat as:

    venv\\Scripts\\python.exe installer\\_alembic_upgrade.py

Exit codes:
  0  upgrade completed successfully
  1  unexpected import or app-context error (rare; means create_app failed)
  2  alembic upgrade itself failed — see traceback above

patch_apply.bat treats any non-zero code as a CRITICAL migration failure
and aborts the wizard (PMS service NOT restarted).

Companion script: ``_alembic_stamp_check.py``.
"""
import logging
import os
import sys
import traceback


def main():
    # When invoked as `venv\Scripts\python.exe installer\_alembic_upgrade.py`
    # from the app root, sys.path[0] is the installer/ subdirectory, so
    # `import app` fails. Prepend the app root (parent of this script).
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _APP_ROOT   = os.path.dirname(_SCRIPT_DIR)
    if _APP_ROOT not in sys.path:
        sys.path.insert(0, _APP_ROOT)

    os.environ.setdefault('FLASK_ENV', 'production')
    # The Flask app's own logging may print noisy WARNING-level lines when
    # the security mode banner emits. Quiet it during patch context.
    logging.disable(logging.WARNING)

    try:
        from app import create_app
        from flask_migrate import upgrade as alembic_upgrade
    except Exception:
        print('FAIL: cannot import Flask app / flask_migrate', file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        app = create_app()
        with app.app_context():
            alembic_upgrade()
        print('OK: alembic upgrade head completed')
        return 0
    except Exception:
        print('FAIL: alembic upgrade head failed', file=sys.stderr)
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    sys.exit(main())
