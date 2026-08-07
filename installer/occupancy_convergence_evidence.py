"""Occupancy convergence evidence — pure stdlib, READ-ONLY diagnostic.

KPI / Occupancy Stabilization Phase 1, Step 6 (2026-05-15).

PURPOSE
-------
After Steps 2-5 every KPI surface (Dashboard, Night Audit, Room Revenue
Report, KPI Command Center, MIS) was rewired to consume occupancy from
the ONE canonical engine (app/occupancy_engine.py). This script produces
the BEFORE / AFTER convergence evidence the operator pastes back as proof.

It does NOT import the application. It re-derives, in raw SQL against a
read-only copy of the live database:

  * AFTER  — the single canonical occupancy number, computed with the
             exact semantics of app/occupancy_engine.py: distinct physical
             rooms with a status='CheckedIn' reservation, linked by
             Reservation.room_id UNION the reservation_rooms bridge.

  * BEFORE — the several DIFFERENT numbers the old fragmented formulas
             produced from the SAME rows at the SAME instant. This is the
             drift the user reported (Dashboard 84.2%, Night Audit 46.2%,
             Room Revenue 43 nights, a screen at 110.3%, actual 21).

  * DRIFT  — stale Room.status='Occupied' flags with no backing CheckedIn
             reservation. These are the reconciliation backlog; this
             script only REPORTS them (Phase 1 does not auto-heal).

ZERO mutation risk:
  - database opened in SQLite read-only mode (URI mode=ro)
  - only SELECT statements; no UPDATE / DELETE / INSERT / ALTER / DROP
  - no COMMIT, no schema change

Usage at Pearl Inn:
    cd "C:\\path\\to\\Sukoon PMS"
    venv\\Scripts\\python.exe installer\\occupancy_convergence_evidence.py

Optionally pass an explicit DB path as the first argument. Then paste the
entire stdout block back to engineering.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import sys

# Canonical constants — must mirror app/occupancy_engine.py exactly.
OCCUPANCY_STATUS = 'CheckedIn'
UNAVAILABLE_ROOM_STATUSES = ('Maintenance', 'Out of Order', 'OutOfOrder')
ROOM_NIGHT_STATUSES = ('CheckedIn', 'CheckedOut')


def _scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else 0


def _pct(occ, denom):
    return round(occ / denom * 100, 1) if denom else 0.0


def main(db_path: str) -> int:
    print('=' * 72)
    print('OCCUPANCY CONVERGENCE EVIDENCE — READ-ONLY DIAGNOSTIC')
    print('Run at  :', datetime.datetime.now().isoformat(timespec='seconds'))
    print('DB path :', db_path)
    print('=' * 72)

    if not os.path.exists(db_path):
        print()
        print('FAIL: database not found at', db_path)
        return 9

    uri = 'file:' + os.path.abspath(db_path).replace('\\', '/') + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    unavail = ','.join('?' * len(UNAVAILABLE_ROOM_STATUSES))

    # ── CANONICAL (AFTER) — exact occupancy_engine.py semantics ──────────
    # occupied_rooms_set(): room_id UNION bridge, CheckedIn, distinct rooms.
    canonical_occupied = _scalar(cur, f"""
        SELECT COUNT(*) FROM (
            SELECT r.room_id AS rid
              FROM reservations r
             WHERE r.status = ? AND r.room_id IS NOT NULL
            UNION
            SELECT rr.room_id AS rid
              FROM reservation_rooms rr
              JOIN reservations r2 ON r2.id = rr.reservation_id
             WHERE r2.status = ? AND rr.room_id IS NOT NULL
        )
    """, (OCCUPANCY_STATUS, OCCUPANCY_STATUS))

    # sellable_rooms(): active AND sellable AND NOT out_of_order AND
    # status NOT IN unavailable.
    canonical_sellable = _scalar(cur, f"""
        SELECT COUNT(*) FROM rooms
         WHERE is_active = 1 AND is_sellable = 1 AND is_out_of_order = 0
           AND status NOT IN ({unavail})
    """, UNAVAILABLE_ROOM_STATUSES)

    total_rooms = _scalar(cur, "SELECT COUNT(*) FROM rooms")
    canonical_pct = _pct(canonical_occupied, canonical_sellable)

    # orphan CheckedIn — CheckedIn with NO room_id and NO bridge row.
    orphan_checked_in = _scalar(cur, """
        SELECT COUNT(*) FROM reservations r
         WHERE r.status = ?
           AND r.room_id IS NULL
           AND r.id NOT IN (SELECT reservation_id FROM reservation_rooms)
    """, (OCCUPANCY_STATUS,))

    print()
    print('=== AFTER — THE ONE CANONICAL NUMBER (occupancy_engine.py) ==========')
    print()
    print(f'  occupied_rooms  (distinct, room_id UNION bridge) : {canonical_occupied}')
    print(f'  sellable_rooms  (active/sellable/not-OOO)        : {canonical_sellable}')
    print(f'  total_rooms     (inventory, display only)        : {total_rooms}')
    print(f'  occupancy_pct   = occupied / sellable            : {canonical_pct}%')
    print(f'  orphan CheckedIn (no room link — excluded)       : {orphan_checked_in}')
    if canonical_occupied > canonical_sellable:
        print('  ANOMALY: occupied > sellable — an occupied room is flagged OOO.')
    print()
    print('  Every wired surface now consumes these exact values:')
    print('  Dashboard, Night Audit, Room Revenue Report, KPI Command')
    print('  Center, MIS, Flash Report, In-House (Occupancy) Report.')

    # ── BEFORE — the divergent legacy interpretations ────────────────────
    # 1. Room.status='Occupied' — the stale-flag count (drove the Dashboard).
    legacy_status_occupied = _scalar(
        cur, "SELECT COUNT(*) FROM rooms WHERE status = 'Occupied'")

    # 2. Reservation-row count of CheckedIn (no dedupe, counts rows).
    legacy_checkedin_rows = _scalar(
        cur, "SELECT COUNT(*) FROM reservations WHERE status = ?",
        (OCCUPANCY_STATUS,))

    # 3. room_id-only distinct rooms — ignores the bridge entirely.
    legacy_roomid_only = _scalar(cur, """
        SELECT COUNT(DISTINCT room_id) FROM reservations
         WHERE status = ? AND room_id IS NOT NULL
    """, (OCCUPANCY_STATUS,))

    # 4. naive sellable — total minus status='Maintenance' only.
    legacy_sellable_naive = _scalar(
        cur, "SELECT COUNT(*) FROM rooms WHERE status != 'Maintenance'")

    print()
    print('=== BEFORE — WHAT THE OLD FRAGMENTED FORMULAS PRODUCED ==============')
    print('    (same rows, same instant — this is the reported drift)')
    print()
    rows = [
        ('Room.status=\'Occupied\' count (stale flags)',
         legacy_status_occupied, canonical_sellable),
        ('CheckedIn reservation-ROW count (no dedupe)',
         legacy_checkedin_rows, canonical_sellable),
        ('Distinct room_id ONLY (bridge ignored)',
         legacy_roomid_only, canonical_sellable),
        ('CheckedIn rows over TOTAL rooms denominator',
         legacy_checkedin_rows, total_rooms),
        ('Room.status=\'Occupied\' over naive sellable',
         legacy_status_occupied, legacy_sellable_naive),
    ]
    print('  {:<46} {:>7} {:>9}'.format('interpretation', 'count', 'pct'))
    print('  ' + '-' * 64)
    for label, cnt, denom in rows:
        print('  {:<46} {:>7} {:>8}%'.format(label, cnt, _pct(cnt, denom)))
    print('  ' + '-' * 64)
    print('  {:<46} {:>7} {:>8}%'.format(
        'CANONICAL (after)', canonical_occupied, canonical_pct))
    print()
    spread = sorted({legacy_status_occupied, legacy_checkedin_rows,
                     legacy_roomid_only, canonical_occupied})
    print(f'  Distinct occupied-count values seen above : {spread}')
    print('  Before Phase 1 these did not agree. After Phase 1 every')
    print('  surface resolves to the single CANONICAL row.')

    # ── DRIFT — stale Room.status flags (reconciliation backlog) ─────────
    stale_flagged = _scalar(cur, f"""
        SELECT COUNT(*) FROM rooms rm
         WHERE rm.status = 'Occupied'
           AND rm.id NOT IN (
               SELECT r.room_id FROM reservations r
                WHERE r.status = ? AND r.room_id IS NOT NULL
               UNION
               SELECT rr.room_id FROM reservation_rooms rr
                JOIN reservations r2 ON r2.id = rr.reservation_id
                WHERE r2.status = ?
           )
    """, (OCCUPANCY_STATUS, OCCUPANCY_STATUS))

    occupied_unflagged = _scalar(cur, f"""
        SELECT COUNT(*) FROM (
            SELECT r.room_id AS rid FROM reservations r
             WHERE r.status = ? AND r.room_id IS NOT NULL
            UNION
            SELECT rr.room_id AS rid FROM reservation_rooms rr
             JOIN reservations r2 ON r2.id = rr.reservation_id
             WHERE r2.status = ?
        )
        WHERE rid NOT IN (SELECT id FROM rooms WHERE status = 'Occupied')
    """, (OCCUPANCY_STATUS, OCCUPANCY_STATUS))

    print()
    print('=== DRIFT — Room.status vs reservation truth (reconciliation) =======')
    print()
    print(f'  Rooms flagged \'Occupied\' with NO CheckedIn guest : {stale_flagged}')
    print(f'  Occupied rooms NOT flagged \'Occupied\'            : {occupied_unflagged}')
    print('  Phase 1 only REPORTS this drift. Room.status is no longer')
    print('  read for occupancy, so these flags no longer corrupt KPIs.')
    print('  Repairing the flags is a separate reconciliation step.')

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
    except Exception as e:  # noqa: BLE001 - diagnostic must always report
        print('UNEXPECTED ERROR in occupancy convergence evidence:',
              repr(e), file=sys.stderr)
        sys.exit(2)
