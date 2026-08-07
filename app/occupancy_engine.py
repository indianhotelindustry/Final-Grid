"""Canonical Occupancy Engine — Sukoon PMS (KPI Phase 1, Step 2).

THE single source of occupancy truth. Every KPI surface (Dashboard,
Night Audit, Room Revenue Report, KPI Command Center, MIS) must consume
occupancy numbers from this module and from nowhere else.

------------------------------------------------------------------------
WHY THIS MODULE EXISTS
------------------------------------------------------------------------
The KPI Truth Audit (docs/v2.2.19_kpi_truth_audit.md) found 27 distinct
occupancy code paths producing six semantic flavours, four denominators,
and three bridge-awareness behaviours. They could not agree. A live
Pearl Inn probe (2026-05-15) isolated the root cause:

    ROOM STATUS DRIFT — 12 rooms flagged Room.status='Occupied'
    while only 1 live CheckedIn reservation existed. 11 stale
    'Occupied' flags had no backing reservation.

Conclusion: ``Room.status`` is NOT a trustworthy occupancy source.

------------------------------------------------------------------------
THE CANONICAL CONTRACT
------------------------------------------------------------------------
1. Occupancy is reservation-driven. The authoritative signal is
   ``Reservation.status == 'CheckedIn'`` with a valid room linkage.

2. "Valid room linkage" = the CheckedIn reservation points at a room
   either through the legacy ``Reservation.room_id`` column OR through
   the ``reservation_rooms`` bridge (Group Stay Phase 1). A reservation
   with NEITHER has no recoverable room and is surfaced as an anomaly,
   never silently counted.

3. ``occupied_rooms`` counts DISTINCT PHYSICAL ROOM IDs. It is never a
   reservation-row count, never a room-night count, never a bridge-row
   count. The room_id and bridge room sets are combined by SET UNION so
   a room claimed by both paths is counted exactly once.

4. ``Room.status`` is demoted to derived/display state. This module
   never reads it for occupancy. A separate reconciliation path (not in
   this module) detects and repairs stale 'Occupied' flags.

5. ``occupied_room_nights`` is a SEPARATE metric — distinct (room,
   night) pairs over a window. It is NOT interchangeable with
   occupancy and lives behind its own function name.

This module performs NO writes. It reads operational truth correctly.
No folio mutation, no settlement rewriting, no Room.status repair.
"""
from __future__ import annotations

import logging
import os
from datetime import date as _date, timedelta as _timedelta

from app.models import db, Room, Reservation, ReservationRoom

logger = logging.getLogger(__name__)

# The one status that means "a guest is physically in this room right now".
# CheckedOut/Reserved/Confirmed/Cancelled/NoShow are NOT current occupancy.
OCCUPANCY_STATUS = 'CheckedIn'

# Statuses that mean a room is genuinely unavailable to sell. Used to
# trim the sellable denominator. Mirrors the audit's sellable definition.
_UNAVAILABLE_ROOM_STATUSES = ('Maintenance', 'Out of Order', 'OutOfOrder')

# Statuses under which a reservation is considered to have physically
# occupied a room on a past night (for the room-nights metric only).
# CheckedOut is included because a guest who has since departed still
# occupied the room on the nights of their completed stay.
_ROOM_NIGHT_STATUSES = ('CheckedIn', 'CheckedOut')


# ─────────────────────────────────────────────────────────────────────
# Business date
# ─────────────────────────────────────────────────────────────────────

def _business_date() -> _date:
    """Resolve the current business date. Lazy import to avoid coupling."""
    try:
        from app.services import get_business_date
        bd = get_business_date()
        if isinstance(bd, _date):
            return bd
    except Exception:
        pass
    return _date.today()


# ─────────────────────────────────────────────────────────────────────
# CANONICAL OCCUPANCY — distinct physical rooms with a CheckedIn guest
# ─────────────────────────────────────────────────────────────────────

def occupied_rooms_set() -> set[int]:
    """Set of distinct physical room IDs occupied right now.

    A room is occupied iff at least one ``status='CheckedIn'``
    reservation is linked to it, by EITHER:
      - ``Reservation.room_id`` (legacy single-room pointer), OR
      - a ``reservation_rooms`` bridge row (Group Stay Phase 1+).

    The two sources are combined by Python set union, so a room reached
    by both paths is present exactly once. No double counting.

    ``Room.status`` is deliberately NOT consulted.
    """
    rooms: set[int] = set()

    # Path 1 — legacy room_id pointer on CheckedIn reservations.
    for (rid,) in (
        db.session.query(Reservation.room_id)
        .filter(Reservation.status == OCCUPANCY_STATUS,
                Reservation.room_id.isnot(None))
    ):
        rooms.add(rid)

    # Path 2 — reservation_rooms bridge for CheckedIn reservations.
    for (rid,) in (
        db.session.query(ReservationRoom.room_id)
        .join(Reservation, Reservation.id == ReservationRoom.reservation_id)
        .filter(Reservation.status == OCCUPANCY_STATUS,
                ReservationRoom.room_id.isnot(None))
    ):
        rooms.add(rid)

    return rooms


def occupied_rooms() -> int:
    """THE canonical occupancy count: distinct physical rooms occupied now.

    Never exceeds the physical room inventory. Immune to Room.status
    drift. Immune to duplicate CheckedIn rows (set union dedupes).
    """
    return len(occupied_rooms_set())


def count_distinct_rooms(reservations) -> int:
    """Distinct physical room count for an ALREADY-LOADED list of
    reservation objects, via ``room_id`` UNION the ``reservation_rooms``
    bridge.

    For date-scoped callers (e.g. Night Audit) that have already
    filtered a specific reservation set and must NOT re-query globally.
    The caller owns the date scoping; this function only does the
    room_id ∪ bridge dedupe so the count is distinct-rooms, never a
    reservation-row count.

    Reads ``reservation.room_links`` (the bridge backref). Callers that
    iterate many reservations should ``subqueryload(Reservation.room_links)``
    to avoid an N+1 query.
    """
    rooms: set[int] = set()
    for r in reservations:
        rid = getattr(r, 'room_id', None)
        if rid is not None:
            rooms.add(rid)
        for link in (getattr(r, 'room_links', None) or []):
            if link.room_id is not None:
                rooms.add(link.room_id)
    return len(rooms)


def checked_in_without_room() -> list[int]:
    """Reservation IDs that are CheckedIn but have NO valid room linkage.

    These reservations carry neither a ``room_id`` nor a bridge row.
    They cannot be attributed to a physical room and are therefore NOT
    counted in ``occupied_rooms()``. Surfaced here as an anomaly so the
    operator can repair the linkage. Diagnostic only — no mutation.
    """
    linked_ids: set[int] = set()

    for (res_id,) in (
        db.session.query(Reservation.id)
        .filter(Reservation.status == OCCUPANCY_STATUS,
                Reservation.room_id.isnot(None))
    ):
        linked_ids.add(res_id)

    for (res_id,) in (
        db.session.query(ReservationRoom.reservation_id)
        .join(Reservation, Reservation.id == ReservationRoom.reservation_id)
        .filter(Reservation.status == OCCUPANCY_STATUS)
    ):
        linked_ids.add(res_id)

    orphan_ids = [
        res_id for (res_id,) in
        db.session.query(Reservation.id)
        .filter(Reservation.status == OCCUPANCY_STATUS)
        if res_id not in linked_ids
    ]
    return sorted(orphan_ids)


# ─────────────────────────────────────────────────────────────────────
# SELLABLE DENOMINATOR
# ─────────────────────────────────────────────────────────────────────

def sellable_rooms() -> int:
    """Rooms that could be sold tonight: the occupancy denominator.

    active AND sellable AND NOT out_of_order AND status not in
    {Maintenance, Out of Order}. An occupied room IS sellable inventory
    (it is sold, but it still belongs in the denominator).

    Belt-and-suspenders: both the ``is_out_of_order`` boolean AND the
    ``status`` text are checked, because the live probe proved the two
    can drift apart.
    """
    q = Room.query.filter(
        Room.is_active.is_(True),
        Room.is_sellable.is_(True),
        Room.is_out_of_order.is_(False),
        Room.status.notin_(_UNAVAILABLE_ROOM_STATUSES),
    )
    return q.count()


def total_rooms() -> int:
    """All rooms incl. maintenance / OOO. Inventory display ONLY —
    never an occupancy denominator."""
    return Room.query.count()


# ─────────────────────────────────────────────────────────────────────
# OCCUPANCY PERCENT + SNAPSHOT
# ─────────────────────────────────────────────────────────────────────

def occupancy_pct() -> float:
    """occupied_rooms / sellable_rooms as a percentage, 1 decimal place.

    Returns 0.0 when there is no sellable inventory. When occupied
    exceeds sellable (an operator OOO-ed a room with a guest still in
    it) the raw ratio can exceed 100% — that is a genuine anomaly and
    is reported as-is; callers should consult ``occupancy_snapshot()``'s
    ``anomaly`` flag rather than silently clamping.
    """
    occ = occupied_rooms()
    sell = sellable_rooms()
    if sell <= 0:
        return 0.0
    return round(occ / sell * 100, 1)


def occupancy_snapshot() -> dict:
    """One-call canonical occupancy payload for every KPI surface.

    Keys:
      occupied   - distinct physical rooms occupied now (int)
      sellable   - sellable-room denominator (int)
      total      - all rooms incl. OOO/maintenance (int)
      pct        - occupancy percentage, 1dp (float)
      anomaly    - True if occupied > sellable (impossible-by-physics;
                   indicates an occupied room was marked OOO/maintenance)
      orphan_checked_in - count of CheckedIn reservations with no room
                   linkage (excluded from `occupied`)
    """
    occ = occupied_rooms()
    sell = sellable_rooms()
    tot = total_rooms()
    orphans = checked_in_without_room()
    pct = round(occ / sell * 100, 1) if sell > 0 else 0.0
    return {
        'occupied': occ,
        'sellable': sell,
        'total': tot,
        'pct': pct,
        'anomaly': occ > sell,
        'orphan_checked_in': len(orphans),
    }


# ─────────────────────────────────────────────────────────────────────
# OCCUPIED ROOM-NIGHTS — a SEPARATE metric, not occupancy
# ─────────────────────────────────────────────────────────────────────

def occupied_room_nights(from_date: _date, to_date: _date) -> int:
    """Distinct (room, night) pairs sold across [from_date, to_date].

    This is NOT occupancy. It is a period volume metric for revenue and
    statistical reports (e.g. Room Revenue Report). A 3-night stay in
    one room contributes 3 room-nights; it contributes 1 to
    ``occupied_rooms()``.

    A reservation contributes night ``d`` iff
        arrival_date <= d < departure_date
        AND status in (CheckedIn, CheckedOut)
    Room linkage is room_id UNION bridge. The (room, night) pairs are
    deduplicated, so two reservations colliding on the same room+night
    (a data-integrity bug) count once, never twice.
    """
    if from_date > to_date:
        return 0

    pairs: set[tuple[int, _date]] = set()

    # Pull candidate reservations overlapping the window once.
    candidates = (
        Reservation.query
        .filter(Reservation.status.in_(_ROOM_NIGHT_STATUSES),
                Reservation.arrival_date <= to_date,
                Reservation.departure_date > from_date)
        .all()
    )
    if not candidates:
        return 0

    cand_ids = [r.id for r in candidates]

    # Bridge rooms for those reservations, keyed by reservation_id.
    bridge_by_res: dict[int, list[int]] = {}
    for res_id, room_id in (
        db.session.query(ReservationRoom.reservation_id, ReservationRoom.room_id)
        .filter(ReservationRoom.reservation_id.in_(cand_ids))
    ):
        bridge_by_res.setdefault(res_id, []).append(room_id)

    for r in candidates:
        room_ids = set(bridge_by_res.get(r.id, []))
        if r.room_id is not None:
            room_ids.add(r.room_id)
        if not room_ids:
            continue
        # Clamp the stay into the window. A night d is a stay night for
        # d in [arrival, departure).
        night = max(r.arrival_date, from_date)
        last = min(r.departure_date - _timedelta(days=1), to_date)
        while night <= last:
            for rid in room_ids:
                pairs.add((rid, night))
            night += _timedelta(days=1)

    return len(pairs)


# ─────────────────────────────────────────────────────────────────────
# ROOM-STATUS DRIFT DETECTOR (read-only; feeds reconciliation path)
# ─────────────────────────────────────────────────────────────────────

def stale_occupied_rooms() -> list[int]:
    """Room IDs marked Room.status='Occupied' with NO CheckedIn reservation.

    These are the residue of checkouts/no-shows/cancellations that did
    not reset the room flag — the root cause the Pearl Inn probe found.
    This function only DETECTS. Repair belongs to a separate
    reconciliation path (deliberately not in this module).
    """
    occ_now = occupied_rooms_set()
    flagged = {
        rid for (rid,) in
        db.session.query(Room.id).filter(Room.status == 'Occupied')
    }
    return sorted(flagged - occ_now)


def occupied_rooms_not_flagged() -> list[int]:
    """The inverse drift: rooms with a CheckedIn guest whose
    Room.status is NOT 'Occupied'. Also reconciliation input."""
    occ_now = occupied_rooms_set()
    flagged = {
        rid for (rid,) in
        db.session.query(Room.id).filter(Room.status == 'Occupied')
    }
    return sorted(occ_now - flagged)


# ─────────────────────────────────────────────────────────────────────
# DIAGNOSTIC TELEMETRY (Step 5 wiring consumes this)
# ─────────────────────────────────────────────────────────────────────

def occupancy_debug_record() -> dict:
    """Full diagnostic payload — what occupancy_engine_debug.log records.

    Includes the canonical numbers, the distinct room-id set, the
    denominator composition, the drift sets, and the orphan list.
    Pure read; safe to call any time.
    """
    occ_set = occupied_rooms_set()
    sell = sellable_rooms()
    tot = total_rooms()
    stale = stale_occupied_rooms()
    unflagged = occupied_rooms_not_flagged()
    orphans = checked_in_without_room()
    return {
        'business_date': _business_date().isoformat(),
        'occupied_rooms': len(occ_set),
        'occupied_room_ids': sorted(occ_set),
        'sellable_rooms': sell,
        'total_rooms': tot,
        'occupancy_pct': round(len(occ_set) / sell * 100, 1) if sell > 0 else 0.0,
        'anomaly_over_100': len(occ_set) > sell,
        'stale_occupied_room_ids': stale,
        'stale_occupied_count': len(stale),
        'occupied_but_unflagged_room_ids': unflagged,
        'orphan_checked_in_reservation_ids': orphans,
    }


def log_occupancy_debug(path: str = 'logs/occupancy_engine_debug.log') -> dict:
    """Append one occupancy_debug_record() line to the debug log.

    Temporary validation telemetry (KPI Phase 1, Step 5). One JSON
    object per line, append-only. Returns the record it wrote.
    Never raises — telemetry failure must not break a request.
    """
    import json
    from datetime import datetime
    rec = occupancy_debug_record()
    rec['ts'] = datetime.now().isoformat(timespec='seconds')
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, separators=(',', ':')) + '\n')
    except Exception as exc:
        logger.warning('occupancy_engine_debug.log write failed: %s', exc)
    return rec
