"""Pearl Inn topology classification gate — pure stdlib, READ-ONLY diagnostic.

Approved by the KPI Phase 1 gate (2026-05-15, revised spec). Runs the three
approved diagnostic queries against ``instance/pms.db`` and prints raw
classification evidence.

ZERO mutation risk:
  - the database is opened in SQLite read-only mode (URI ``mode=ro``)
  - only SELECT statements are issued
  - no UPDATE / DELETE / INSERT / ALTER / DROP / COMMIT anywhere

This script DELIBERATELY emits NO automatic CLEAN/POLLUTED verdict. It
produces only the raw counts. Classification is a human analytical step
performed on the returned evidence — keeping the production-truth
determination explicit and reviewable.

Usage at Pearl Inn:
    cd "C:\\path\\to\\FinalGrid"
    venv\\Scripts\\python.exe installer\\topology_classify.py

Then paste the entire stdout block back to engineering for classification.
"""
from __future__ import annotations
import datetime
import os
import sqlite3
import sys


# --- The three approved gating queries (verbatim) ---------------------

QUERY_1 = """
SELECT
  CASE
    WHEN g.name LIKE 'Test Guest %'
      OR g.name LIKE 'Test X%'
      OR g.name LIKE 'Bridge Test %'
      OR g.name LIKE 'Recon Test %'
      OR g.first_name IN ('Test','Bridge','Recon')
    THEN 'TEST_FIXTURE'
    ELSE 'REAL'
  END AS data_class,
  r.status,
  COUNT(*) AS cnt
FROM reservations r
JOIN guests g ON g.id = r.guest_id
GROUP BY 1, 2
ORDER BY 1, 2;
"""

QUERY_2 = """
SELECT
  CASE
    WHEN room_number LIKE 'T%'
      OR room_number LIKE 'B%'
      OR room_number LIKE 'X%'
      OR room_number LIKE 'K%'
      OR room_number LIKE 'OT%'
    THEN 'TEST_FIXTURE'
    ELSE 'REAL'
  END AS class,
  COUNT(*) AS cnt
FROM rooms
GROUP BY 1
ORDER BY 1;
"""

QUERY_3 = """
SELECT COUNT(DISTINCT r.room_id) AS occupied_rooms_now
FROM reservations r
JOIN guests g ON g.id = r.guest_id
WHERE r.status = 'CheckedIn'
  AND NOT (
    g.name LIKE 'Test%'
    OR g.name LIKE 'Bridge%'
    OR g.name LIKE 'Recon%'
    OR g.first_name IN ('Test','Bridge','Recon')
  );
"""


def main(db_path: str) -> int:
    print('=' * 72)
    print('PEARL INN TOPOLOGY CLASSIFICATION — READ-ONLY DIAGNOSTIC')
    print('Run at:', datetime.datetime.now().isoformat(timespec='seconds'))
    print('DB path:', db_path)
    print('=' * 72)

    if not os.path.exists(db_path):
        print()
        print('FAIL: database not found at', db_path)
        print('Confirm the current directory is the FinalGrid install root')
        print('(the folder that contains the "instance" sub-folder).')
        return 9

    # Open READ-ONLY. The mode=ro URI guarantees the connection cannot
    # write, even if a stray statement tried to. immutable=0 so SQLite
    # still honours any concurrent writers' journal.
    uri = 'file:' + os.path.abspath(db_path).replace('\\', '/') + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()

    test_res = 0
    real_res = 0
    test_rooms = 0
    real_rooms = 0
    occupied_now = 0

    # === QUERY 1 ===
    print()
    print('=== QUERY 1 — RESERVATIONS BY CLASS × STATUS ===')
    print()
    cur.execute(QUERY_1)
    rows = cur.fetchall()
    if rows:
        print('  {:<14}{:<16}{:>10}'.format('data_class', 'status', 'cnt'))
        print('  {:<14}{:<16}{:>10}'.format('-' * 12, '-' * 14, '-' * 8))
        for data_class, status, cnt in rows:
            print('  {:<14}{:<16}{:>10}'.format(
                data_class, status if status is not None else '(null)', cnt))
            if data_class == 'TEST_FIXTURE':
                test_res += cnt
            else:
                real_res += cnt
    else:
        print('  (no reservations found)')

    # === QUERY 2 ===
    print()
    print('=== QUERY 2 — ROOMS BY CLASS ===')
    print()
    cur.execute(QUERY_2)
    rows = cur.fetchall()
    if rows:
        print('  {:<14}{:>10}'.format('class', 'cnt'))
        print('  {:<14}{:>10}'.format('-' * 12, '-' * 8))
        for cls, cnt in rows:
            print('  {:<14}{:>10}'.format(cls, cnt))
            if cls == 'TEST_FIXTURE':
                test_rooms += cnt
            else:
                real_rooms += cnt
    else:
        print('  (no rooms found)')

    # === QUERY 3 ===
    print()
    print('=== QUERY 3 — DISTINCT REAL OCCUPIED ROOMS ===')
    print()
    cur.execute(QUERY_3)
    occupied_now = cur.fetchone()[0] or 0
    print('  occupied_rooms_now :', occupied_now)
    print('  (compare against the manager\'s physical occupancy count)')

    conn.close()

    # === RAW SUMMARY ===
    print()
    print('=== RAW SUMMARY ===')
    print()
    print('  TEST_FIXTURE reservations :', test_res)
    print('  REAL reservations         :', real_res)
    print('  TEST_FIXTURE rooms        :', test_rooms)
    print('  REAL rooms                :', real_rooms)
    print('  occupied_rooms_now        :', occupied_now)
    print()
    print('  No verdict is emitted by this script. Classification is a')
    print('  human analytical step performed on the evidence above.')
    print()
    print('=' * 72)
    print('To return: copy this entire block (from the first === bar) and')
    print('paste it back to engineering. Read-only — nothing was modified.')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'instance/pms.db'
    try:
        sys.exit(main(db))
    except Exception as e:
        print('UNEXPECTED ERROR in topology classifier:', repr(e), file=sys.stderr)
        sys.exit(2)
