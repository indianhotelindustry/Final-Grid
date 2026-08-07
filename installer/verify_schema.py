"""Schema verification gate — Sukoon PMS deployment governance (v2.2.13 Phase 2).

This script is part of the **release-governance contract**. Installer success
is impossible without verify_schema PASS. patch_apply.bat must invoke this
after migrations and abort the wizard on any non-zero exit.

What changed from the v2.2.10 `migrations/verify_schema.py`
----------------------------------------------------------
The old script only required ``alembic_version`` to be present and non-empty.
That accepted any version string — including stale ones from a partial or
botched stamp. v2.2.13 raises the bar:

  - The DB's ``alembic_version.version_num`` MUST equal the expected head
    declared in ``installer/expected_alembic_head.txt``. This is the pin
    that ties a particular installer build to a particular migration head;
    a mismatch means the installer's bundled migrations did not actually
    advance the DB to the expected state.

  - REQUIRED_TABLES is the **release contract** for which tables the
    current code reads in critical request-path / night-audit flows.
    Initial v2.2.13 list (per Phase 2 approval):
        users, reservations, rooms, reservation_rooms
    Plus alembic_version (intrinsic to the contract). Future releases
    append release-contract tables here when new schema dependencies
    become operationally meaningful.

Companion files
---------------
  - ``installer/expected_alembic_head.txt`` — single-line file containing
    the expected head revision id. Bumped each release by the release
    packaging step (Phase 6).

Usage
-----
    python installer/verify_schema.py [path/to/pms.db]

Defaults to ``instance/pms.db`` if no path given (CWD-relative).
The expected head is read from ``installer/expected_alembic_head.txt``
relative to this script's directory (script-relative, not CWD-relative,
so it works from any cwd as long as the installer/ tree is intact).

Exit codes (patch_apply.bat dispatches on these)
------------------------------------------------
  0  schema verified ok; alembic_version matches expected head;
     every required table is present.
  4  required table missing  (or DB file not found)
  5  alembic_version table missing / row missing / version_num blank
  6  alembic_version mismatch with expected head (the load-bearing new check)
  7  expected_alembic_head.txt missing / unreadable / empty

Any non-zero code is a hard release-gate failure.
"""
import os
import sqlite3
import sys


# Required minimum table set — the release-governance contract.
# Rule: only tables the current production code reads from in critical
# (request-path or night-audit) flows. Decorative / optional tables stay
# out of this contract. Append carefully; once a table is in here, every
# subsequent release must keep it present or this gate hard-fails.
REQUIRED_TABLES = {
    # Alembic management — intrinsic to the contract
    'alembic_version',
    # Phase 2 v2.2.13 initial baseline (per user approval):
    'users',
    'reservations',
    'rooms',
    'reservation_rooms',
}


def _read_expected_head():
    """Read the expected alembic head from installer/expected_alembic_head.txt.

    Returns (head_string_or_None, error_message_or_None). Script-relative so
    it works regardless of cwd.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    head_file = os.path.join(here, 'expected_alembic_head.txt')
    if not os.path.exists(head_file):
        return None, f'expected_alembic_head.txt not found at {head_file}'
    try:
        with open(head_file, 'r', encoding='utf-8') as f:
            head = f.read().strip()
    except OSError as e:
        return None, f'cannot read expected_alembic_head.txt: {e}'
    if not head:
        return None, 'expected_alembic_head.txt is empty'
    return head, None


def main(db_path):
    # --- 0. Expected head pin ---------------------------------------------
    expected_head, head_err = _read_expected_head()
    if head_err:
        print(f'FAIL: {head_err}', file=sys.stderr)
        return 7

    # --- 1. DB file present -----------------------------------------------
    if not os.path.exists(db_path):
        print(f'FAIL: DB not found: {db_path}', file=sys.stderr)
        return 4

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # --- 2. REQUIRED_TABLES all present -------------------------------
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        present = {r[0] for r in cur.fetchall()}
        missing = REQUIRED_TABLES - present
        if missing:
            print('FAIL: required tables missing:', sorted(missing),
                  file=sys.stderr)
            print('     present tables ({}):'.format(len(present)),
                  sorted(present), file=sys.stderr)
            return 4

        # --- 3. alembic_version populated ---------------------------------
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

        # --- 4. version_num matches expected head -------------------------
        # This is the v2.2.13 load-bearing check. A version that doesn't
        # match the head bundled with this installer means the migrations
        # did not advance the DB to the expected state.
        if version != expected_head:
            print('FAIL: alembic_version mismatch', file=sys.stderr)
            print(f'     expected head : {expected_head}', file=sys.stderr)
            print(f'     DB version_num: {version}', file=sys.stderr)
            print('     The migrations bundled with this installer did not '
                  'advance the DB to the expected state.', file=sys.stderr)
            return 6

        # --- All checks passed --------------------------------------------
        print('OK: schema verified.')
        print(f'    alembic head    = {version}')
        print(f'    expected head   = {expected_head}')
        print(f'    required tables = {len(REQUIRED_TABLES)} present '
              f'({sorted(REQUIRED_TABLES)})')
        return 0

    finally:
        conn.close()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'instance/pms.db'
    sys.exit(main(db))
