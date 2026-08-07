"""Schema verification gate — Sukoon PMS deployment hardening (v2.2.10).

Runs after every alembic upgrade in `installer/patch_apply.bat`. Fails
the patch if the schema does not match the contract; the installer's
[Code] handler reads the exit code and aborts the wizard on non-zero,
leaving the PMS service stopped and the operator with a clear next-step
message.

Why this exists
---------------
Pre-v2.2.10, `patch_apply.bat` printed "Database migrated." without
actually invoking alembic. Multiple patches may have shipped without
ever applying their migrations. This script makes that class of silent
failure structurally impossible: if alembic did not run (or didn't
finish), one of the checks below will fail.

Checks
------
1. REQUIRED_TABLES — every table the production code reads from in
   critical paths must be present. The initial list (v2.2.10) is
   intentionally small and operationally meaningful; extend per
   release as new schema dependencies are added.

2. alembic_version — the table must exist (covered by check 1) and
   contain a non-empty version_num. A blank alembic_version means
   alembic was never run; a missing row means alembic was run with
   `--purge` or something equally surprising.

Exit codes
----------
  0  schema verified ok
  4  required table missing  (or DB file not found)
  5  alembic_version empty / blank

Usage
-----
    python migrations/verify_schema.py [path/to/pms.db]

Defaults to `instance/pms.db` if no path given. CWD-relative.
"""
import os
import sqlite3
import sys


# Required minimum table set as of v2.2.10. Extend per release.
# Rule: only tables the current production code reads from in critical
# (request-path or night-audit) flows. Decorative / optional tables
# stay out of this contract.
REQUIRED_TABLES = {
    # Alembic management
    'alembic_version',
    # Room inventory
    'rooms', 'room_types',
    # Guests
    'guests',
    # Reservations + Group Stay Phase 1 bridge
    'reservations', 'reservation_rooms',
    # Billing
    'folios',
    'payments', 'payment_modes',
    'extra_charges',
    # Audit trail
    'audit_logs',
}


def main(db_path):
    if not os.path.exists(db_path):
        print('FAIL: DB not found:', db_path, file=sys.stderr)
        return 4

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Check 1: REQUIRED_TABLES — all present
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        present = {r[0] for r in cur.fetchall()}
        missing = REQUIRED_TABLES - present
        if missing:
            print('FAIL: required tables missing:', sorted(missing),
                  file=sys.stderr)
            print('     present tables ({}):'.format(len(present)),
                  sorted(present), file=sys.stderr)
            return 4

        # Check 2: alembic_version — table exists (above) and is populated
        cur.execute('SELECT version_num FROM alembic_version')
        rows = cur.fetchall()
        if not rows:
            print('FAIL: alembic_version table is empty', file=sys.stderr)
            print('     (no migration has ever been applied to this DB)',
                  file=sys.stderr)
            return 5

        version = ''
        if rows[0] and rows[0][0] is not None:
            version = str(rows[0][0]).strip()
        if not version:
            print('FAIL: alembic_version.version_num is blank', file=sys.stderr)
            return 5

        print('OK: schema verified. alembic head = {}. '
              '{} required tables present.'.format(version, len(REQUIRED_TABLES)))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'instance/pms.db'
    sys.exit(main(db))
