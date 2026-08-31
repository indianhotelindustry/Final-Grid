"""Occupancy topology probe — pure stdlib, READ-ONLY diagnostic.

KPI Phase 1, Step 2 prerequisite (2026-05-15).

The Pearl Inn classification gate found CLEAN topology BUT a critical anomaly:
12 real CheckedIn reservations exist while COUNT(DISTINCT room_id) = 0 — i.e.
every CheckedIn reservation has Reservation.room_id IS NULL.

This probe answers the single gating question for the canonical occupancy
engine: WHERE does the active-room assignment actually live for a checked-in
guest on Pearl Inn?

  - in Reservation.room_id  (legacy column)?
  - in the reservation_rooms bridge?
  - in Room.status = 'Occupied' only?
  - nowhere (assignment lost)?

ZERO mutation risk:
  - database opened in SQLite read-only mode (URI mode=ro)
  - only SELECT statements
  - no UPDATE / DELETE / INSERT / ALTER / DROP / COMMIT

Emits NO verdict. Raw evidence only. Classification is a human step.

Usage at Pearl Inn:
    cd "C:\\path\\to\\FinalGrid"
    venv\\Scripts\\python.exe installer\\occupancy_topology_probe.py

Then paste the entire stdout block back to engineering.
"""
from __future__ import annotations
import datetime
import os
import sqlite3
import sys


_TEST_GUEST_FILTER = """NOT (
    g.name LIKE 'Test%'
    OR g.name LIKE 'Bridge%'
    OR g.name LIKE 'Recon%'
    OR g.first_name IN ('Test','Bridge','Recon')
)"""


def main(db_path: str) -> int:
    print('=' * 72)
    print('OCCUPANCY TOPOLOGY PROBE — READ-ONLY DIAGNOSTIC')
    print('Run at:', datetime.datetime.now().isoformat(timespec='seconds'))
    print('DB path:', db_path)
    print('=' * 72)

    if not os.path.exists(db_path):
        print()
        print('FAIL: database not found at', db_path)
        return 9

    uri = 'file:' + os.path.abspath(db_path).replace('\\', '/') + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # === SECTION 1 — every real CheckedIn reservation, with room linkage ===
    print()
    print('=== SECTION 1 — REAL CheckedIn reservations: where the room lives ===')
    print()
    cur.execute(f"""
        SELECT r.id, r.room_id, r.arrival_date, r.departure_date,
               r.checked_in_at, r.created_at, r.status
          FROM reservations r
          JOIN guests g ON g.id = r.guest_id
         WHERE r.status = 'CheckedIn'
           AND {_TEST_GUEST_FILTER}
         ORDER BY r.id
    """)
    ci_rows = cur.fetchall()

    has_room_id = 0
    has_bridge = 0
    has_neither = 0
    has_both = 0

    if not ci_rows:
        print('  (no real CheckedIn reservations)')
    else:
        hdr = '  {:>6} {:>9} {:>22} {:>22} {:>14}'.format(
            'res_id', 'room_id', 'checked_in_at', 'created_at', 'bridge_rooms')
        print(hdr)
        print('  ' + '-' * 78)
        for r in ci_rows:
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT room_id, is_primary FROM reservation_rooms "
                "WHERE reservation_id = ? ORDER BY room_id", (r['id'],))
            bridge = cur2.fetchall()
            bridge_str = ','.join(
                f"{b['room_id']}{'*' if b['is_primary'] else ''}" for b in bridge
            ) or '(none)'
            rid_str = str(r['room_id']) if r['room_id'] is not None else 'NULL'
            print('  {:>6} {:>9} {:>22} {:>22} {:>14}'.format(
                r['id'], rid_str,
                str(r['checked_in_at'])[:22] if r['checked_in_at'] else '(null)',
                str(r['created_at'])[:22] if r['created_at'] else '(null)',
                bridge_str))
            _rid = r['room_id'] is not None
            _br = len(bridge) > 0
            if _rid and _br:
                has_both += 1
            elif _rid:
                has_room_id += 1
            elif _br:
                has_bridge += 1
            else:
                has_neither += 1
    print()
    print(f'  CheckedIn reservations total          : {len(ci_rows)}')
    print(f'    with room_id AND bridge row         : {has_both}')
    print(f'    with room_id only (no bridge)       : {has_room_id}')
    print(f'    with bridge row only (room_id NULL) : {has_bridge}')
    print(f'    with NEITHER (room assignment lost) : {has_neither}')

    # === SECTION 2 — Room.status='Occupied' cross-check ===
    print()
    print('=== SECTION 2 — Rooms with status=Occupied vs CheckedIn linkage ===')
    print()
    cur.execute("SELECT COUNT(*) FROM rooms WHERE status = 'Occupied'")
    occ_rooms = cur.fetchone()[0]
    print(f'  Rooms with status=Occupied            : {occ_rooms}')

    # Occupied rooms that NO CheckedIn reservation points to (via room_id)
    cur.execute(f"""
        SELECT COUNT(*) FROM rooms rm
         WHERE rm.status = 'Occupied'
           AND rm.id NOT IN (
               SELECT r.room_id FROM reservations r
                JOIN guests g ON g.id = r.guest_id
               WHERE r.status='CheckedIn' AND r.room_id IS NOT NULL
                 AND {_TEST_GUEST_FILTER}
           )
    """)
    occ_no_ci_via_roomid = cur.fetchone()[0]
    print(f'  Occupied rooms NOT linked via room_id : {occ_no_ci_via_roomid}')

    # Occupied rooms that NO CheckedIn reservation points to (via bridge)
    cur.execute(f"""
        SELECT COUNT(*) FROM rooms rm
         WHERE rm.status = 'Occupied'
           AND rm.id NOT IN (
               SELECT rr.room_id FROM reservation_rooms rr
                JOIN reservations r ON r.id = rr.reservation_id
                JOIN guests g ON g.id = r.guest_id
               WHERE r.status='CheckedIn'
                 AND {_TEST_GUEST_FILTER}
           )
    """)
    occ_no_ci_via_bridge = cur.fetchone()[0]
    print(f'  Occupied rooms NOT linked via bridge  : {occ_no_ci_via_bridge}')

    # === SECTION 3 — bridge population for CheckedIn reservations ===
    print()
    print('=== SECTION 3 — reservation_rooms bridge population ===')
    print()
    cur.execute("SELECT COUNT(*) FROM reservation_rooms")
    print(f'  Total reservation_rooms rows          : {cur.fetchone()[0]}')
    cur.execute(f"""
        SELECT COUNT(DISTINCT rr.reservation_id)
          FROM reservation_rooms rr
          JOIN reservations r ON r.id = rr.reservation_id
          JOIN guests g ON g.id = r.guest_id
         WHERE r.status='CheckedIn' AND {_TEST_GUEST_FILTER}
    """)
    print(f'  CheckedIn reservations with bridge row: {cur.fetchone()[0]}')
    cur.execute(f"""
        SELECT COUNT(DISTINCT rr.room_id)
          FROM reservation_rooms rr
          JOIN reservations r ON r.id = rr.reservation_id
          JOIN guests g ON g.id = r.guest_id
         WHERE r.status='CheckedIn' AND {_TEST_GUEST_FILTER}
    """)
    print(f'  Distinct rooms via bridge (CheckedIn) : {cur.fetchone()[0]}')

    # === SECTION 4 — code-version hint: how were CheckedIn rows created ===
    print()
    print('=== SECTION 4 — CheckedIn reservation source + age spread ===')
    print()
    cur.execute(f"""
        SELECT COALESCE(r.source,'(null)') AS src, COUNT(*) AS cnt,
               MIN(r.checked_in_at) AS earliest, MAX(r.checked_in_at) AS latest
          FROM reservations r
          JOIN guests g ON g.id = r.guest_id
         WHERE r.status='CheckedIn' AND {_TEST_GUEST_FILTER}
         GROUP BY 1 ORDER BY cnt DESC
    """)
    for r in cur.fetchall():
        print(f"  source={r['src']:<14} count={r['cnt']:<4} "
              f"checked_in {str(r['earliest'])[:19]} .. {str(r['latest'])[:19]}")

    conn.close()
    print()
    print('=' * 72)
    print('Read-only — nothing was modified. Paste this entire block back.')
    print('=' * 72)
    return 0


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'instance/pms.db'
    try:
        sys.exit(main(db))
    except Exception as e:
        print('UNEXPECTED ERROR in occupancy topology probe:', repr(e), file=sys.stderr)
        sys.exit(2)
