"""Alembic stamp-gate check — FinalGrid patch_apply (v2.2.12).

Replaces the multi-line ``python -c "..."`` heredoc that was the smoking gun
of the v2.2.11 deployment incident. The heredoc pattern does not execute
under cmd.exe batch — cmd parses each line after the opening quote as a
separate command, silently no-opping the entire check.

This script is invoked as a SINGLE-LINE python call from patch_apply.bat:

    venv\\Scripts\\python.exe installer\\_alembic_stamp_check.py [path/to/pms.db]

Exit codes (patch_apply.bat dispatches on these):
  0  alembic_version table exists AND contains a non-empty version_num.
     The DB is already alembic-managed. No stamp needed.
  7  alembic_version is missing OR table exists but is empty/NULL.
     The DB needs to be stamped to ``c4d5e6f7a8b9`` (pre-Release-1 head)
     before any ``flask db upgrade`` invocation, otherwise alembic will
     replay the PostgreSQL-targeted base migration ``e2a21139b806`` and
     fail on ``drop_constraint('guest_feedback_token_key')``.
  9  Database file not found at the given path. Cannot proceed.
  Other  Unexpected exception. patch_apply.bat treats any non-(0,7,9)
     code as a hard failure (added in v2.2.12 dispatch guard).

This is one of TWO standalone scripts that replaced heredocs in v2.2.12;
the other is ``_alembic_upgrade.py``. See ``migrations/verify_schema.py``
for the original "single-file script invoked from .bat" pattern that
this one mirrors.
"""
import os
import sqlite3
import sys


def main(db_path):
    if not os.path.exists(db_path):
        print('FAIL: DB not found at', db_path, file=sys.stderr)
        return 9

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Does alembic_version even exist?
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type=? AND name=?",
            ('table', 'alembic_version'),
        )
        if not cur.fetchall():
            print('alembic_version table MISSING - will stamp to c4d5e6f7a8b9 '
                  '(pre-Release-1 head)')
            return 7

        # Table exists. Is it populated?
        cur.execute('SELECT version_num FROM alembic_version')
        rows = cur.fetchall()
        if not rows:
            print('alembic_version table EMPTY (no row) - will stamp to '
                  'c4d5e6f7a8b9')
            return 7

        version = rows[0][0]
        if version is None or not str(version).strip():
            print('alembic_version row exists but version_num is NULL/blank - '
                  'will stamp to c4d5e6f7a8b9')
            return 7

        print('alembic_version present:', version, '(no stamp needed)')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'instance/pms.db'
    try:
        sys.exit(main(db))
    except Exception as e:
        # Surface unexpected errors so patch_apply.bat's defensive guard
        # (introduced in v2.2.12) hard-fails instead of falling through.
        print('UNEXPECTED ERROR in stamp check:', repr(e), file=sys.stderr)
        sys.exit(1)
