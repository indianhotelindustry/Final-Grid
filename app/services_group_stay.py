"""Canonical helpers for the reservation_rooms bridge (Group Stay Phase 1, R2A).

Every write that touches reservation-to-room assignment MUST go through one of
these helpers. Direct mutation of ``Reservation.room_id`` without a matching
bridge mutation is the bug class R2A exists to eliminate.

Three invariants the helpers preserve:

  1. **Bridge authoritative.** For any reservation with an assigned room, the
     bridge contains exactly one ``is_primary=True`` row whose ``room_id`` ==
     ``Reservation.room_id``. Single-room reservations have exactly one row.
     Multi-room reservations have N rows; one primary, N-1 secondary.

  2. **Same-transaction write.** Bridge mutation and ``Reservation.room_id``
     mutation happen inside the caller's transaction. The caller controls the
     commit. Helpers DO NOT commit.

  3. **Audit on every link mutation.** Each INSERT / DELETE / primary-flip
     records an ``AuditLog`` row via ``log_group_room_link``. The bridge is
     the historical record of which rooms a reservation used.

Bridge rows are *append-mostly*. Status transitions (checkout, cancel,
no-show) do NOT delete bridge rows — the bridge is the long-term room-stay
audit. Deletions only happen on explicit "remove from group" (R2C+) or on
single-room rotation via ``swap_room_in_bridge``.

This module is the only writer of ``reservation_rooms`` after R2A deploys.
The Alembic backfill migration is the only other writer historically; from
R2A onward, every application-driven bridge mutation comes through here.

See docs/RELEASE.md for the full Phase 1 design.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from flask import request
from sqlalchemy.exc import IntegrityError

from app.models import (
    AuditLog,
    Reservation,
    ReservationRoom,
    Room,
    db,
    log_group_room_link,
)

logger = logging.getLogger(__name__)


_ACTION_CREATED  = 'GROUP_ROOM_LINK_CREATED'
_ACTION_REMOVED  = 'GROUP_ROOM_LINK_REMOVED'
_ACTION_PRIMARY  = 'GROUP_ROOM_LINK_PRIMARY_CHANGED'


def _resolve_actor(user_id: Optional[int]) -> int:
    """Resolve the actor user id for audit purposes.

    Falls back to ``current_user.id`` from Flask-Login if available, else 0.
    R2A backfill paths (no operator context) pass 0 explicitly.
    """
    if user_id is not None:
        return user_id
    try:
        from flask_login import current_user
        if current_user and getattr(current_user, 'is_authenticated', False):
            return int(current_user.id)
    except Exception:
        pass
    return 0


def _resolve_ip(ip_address: Optional[str]) -> Optional[str]:
    """Resolve the request IP for audit purposes."""
    if ip_address is not None:
        return ip_address
    try:
        if request:
            return request.remote_addr
    except Exception:
        pass
    return None


def link_reservation_to_room(
    reservation: Reservation,
    room: Room,
    *,
    is_primary: bool = False,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> bool:
    """INSERT a bridge row linking ``reservation`` to ``room``.

    Idempotent: if the bridge row already exists (UNIQUE constraint on
    ``(reservation_id, room_id)``), no INSERT is performed and no audit row
    is written. Returns True iff a new row was inserted.

    If ``is_primary=True``:
      - the caller asserts there is no OTHER ``is_primary=True`` row for this
        reservation (partial unique index ``idx_resroom_primary`` enforces
        this at COMMIT time).
      - ``Reservation.room_id`` is set to ``room.id``.

    Does NOT commit. Caller controls the transaction.
    """
    existing = ReservationRoom.query.filter_by(
        reservation_id=reservation.id, room_id=room.id
    ).first()
    if existing is not None:
        # Idempotent no-op. If caller asked for is_primary=True and the
        # existing row is non-primary, that's a coherence bug — surface it.
        if is_primary and not existing.is_primary:
            logger.warning(
                'link_reservation_to_room: bridge row exists with is_primary=False '
                'but caller requested is_primary=True (reservation=%s room=%s). '
                'Use set_primary_room() to promote.',
                reservation.id, room.id,
            )
        return False

    bridge = ReservationRoom(
        reservation_id=reservation.id,
        room_id=room.id,
        is_primary=bool(is_primary),
    )
    db.session.add(bridge)
    if is_primary:
        reservation.room_id = room.id

    log_group_room_link(
        reservation_id=reservation.id,
        room_id=room.id,
        action=_ACTION_CREATED,
        actor_user_id=_resolve_actor(user_id),
        is_primary=bool(is_primary),
        ip_address=_resolve_ip(ip_address),
    )
    return True


def unlink_reservation_room(
    reservation: Reservation,
    room: Room,
    *,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> bool:
    """DELETE the bridge row linking ``reservation`` to ``room``.

    Idempotent: missing bridge row is a no-op, returns False.
    Returns True iff a row was deleted.

    Refuses to delete a ``is_primary=True`` row unless it is the LAST bridge
    row of the reservation (the reservation is being completely unlinked).
    The caller must promote a secondary to primary first via
    ``set_primary_room`` for partial-removal cases.

    Does NOT commit. Caller controls the transaction.
    """
    bridge = ReservationRoom.query.filter_by(
        reservation_id=reservation.id, room_id=room.id
    ).first()
    if bridge is None:
        return False

    if bridge.is_primary:
        sibling_count = ReservationRoom.query.filter(
            ReservationRoom.reservation_id == reservation.id,
            ReservationRoom.room_id != room.id,
        ).count()
        if sibling_count > 0:
            raise ValueError(
                f'Cannot unlink primary room {room.id} from reservation '
                f'{reservation.id} while {sibling_count} other room(s) remain. '
                f'Promote a secondary to primary first.'
            )

    db.session.delete(bridge)
    log_group_room_link(
        reservation_id=reservation.id,
        room_id=room.id,
        action=_ACTION_REMOVED,
        actor_user_id=_resolve_actor(user_id),
        is_primary=bool(bridge.is_primary),
        ip_address=_resolve_ip(ip_address),
    )
    return True


def set_primary_room(
    reservation: Reservation,
    room_id: int,
    *,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> bool:
    """Designate ``room_id`` as the primary room of ``reservation``.

    Requires a bridge row for ``room_id`` to already exist. Flips the
    ``is_primary`` flag: clears every existing primary first (within the
    reservation), then sets the target row's flag to True. Also syncs
    ``Reservation.room_id``.

    Idempotent: if the target is already primary, returns False without
    writing an audit row.

    Returns True iff the primary was changed.

    Does NOT commit. Caller controls the transaction.
    """
    target = ReservationRoom.query.filter_by(
        reservation_id=reservation.id, room_id=room_id
    ).first()
    if target is None:
        raise ValueError(
            f'Cannot set primary: no bridge row for reservation '
            f'{reservation.id} room {room_id}. Call link_reservation_to_room first.'
        )
    if target.is_primary and reservation.room_id == room_id:
        return False

    # Clear every existing primary, then set the target. Order matters —
    # the partial unique index on (reservation_id) WHERE is_primary=1 means
    # we cannot have two primaries at COMMIT time. SQLite enforces the
    # constraint per-statement during flush, so we must flush the clears
    # before promoting the target.
    siblings = ReservationRoom.query.filter(
        ReservationRoom.reservation_id == reservation.id,
        ReservationRoom.is_primary.is_(True),
        ReservationRoom.id != target.id,
    ).all()
    if siblings:
        for s in siblings:
            s.is_primary = False
        db.session.flush()
    target.is_primary = True
    reservation.room_id = room_id

    log_group_room_link(
        reservation_id=reservation.id,
        room_id=room_id,
        action=_ACTION_PRIMARY,
        actor_user_id=_resolve_actor(user_id),
        is_primary=True,
        ip_address=_resolve_ip(ip_address),
    )
    return True


def sync_primary_pointer(reservation: Reservation) -> bool:
    """Ensure ``Reservation.room_id`` matches the bridge's is_primary row.

    Idempotent. Returns True iff a change was made. Useful after bulk bridge
    operations to re-establish the invariant before commit.

    Behaviour:
      - If exactly one ``is_primary=True`` row exists: set
        ``Reservation.room_id = row.room_id`` (no-op if already matches).
      - If zero ``is_primary=True`` rows but at least one bridge row exists:
        does nothing (caller error — the reservation is in an inconsistent
        state and should call ``set_primary_room`` explicitly).
      - If no bridge rows exist: does nothing.

    Does NOT commit.
    """
    primary = ReservationRoom.query.filter_by(
        reservation_id=reservation.id, is_primary=True
    ).first()
    if primary is None:
        return False
    if reservation.room_id == primary.room_id:
        return False
    reservation.room_id = primary.room_id
    return True


def swap_room_in_bridge(
    reservation: Reservation,
    old_room_id: Optional[int],
    new_room_id: int,
    *,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Replace ``old_room_id`` with ``new_room_id`` in the bridge.

    Used by the single-room rotation paths (``/room-change``,
    ``/api/reservation/move``). Preserves the primary-status of the old row
    on the new row — i.e. swapping the primary room keeps the new row
    flagged primary.

    If ``old_room_id`` has no bridge row (legacy orphan), the helper inserts
    the new row as primary (no DELETE needed). This is the back-compat path
    for pre-R2A reservations whose primary was never bridged.

    If ``new_room_id`` already has a bridge row (rare race), this is an
    error — caller has logically inconsistent state.

    Always syncs ``Reservation.room_id = new_room_id``.

    Does NOT commit. Caller controls the transaction.
    """
    if new_room_id is None:
        raise ValueError('swap_room_in_bridge requires new_room_id')

    new_room = db.session.get(Room, new_room_id)
    if new_room is None:
        raise ValueError(f'swap_room_in_bridge: new_room_id {new_room_id} not found')

    # Detect existing target row — error if already linked.
    if ReservationRoom.query.filter_by(
        reservation_id=reservation.id, room_id=new_room_id
    ).first() is not None:
        raise ValueError(
            f'swap_room_in_bridge: reservation {reservation.id} already linked '
            f'to room {new_room_id}. Use set_primary_room to designate.'
        )

    was_primary = True  # default for orphan-promotion path
    if old_room_id is not None:
        old_bridge = ReservationRoom.query.filter_by(
            reservation_id=reservation.id, room_id=old_room_id
        ).first()
        if old_bridge is not None:
            was_primary = bool(old_bridge.is_primary)
            db.session.delete(old_bridge)
            # Flush the DELETE before the INSERT below so the partial
            # unique index idx_resroom_primary doesn't see two primary rows
            # transiently inside the same flush cycle (SQLite enforces
            # constraints per-statement).
            if was_primary:
                db.session.flush()
            log_group_room_link(
                reservation_id=reservation.id,
                room_id=old_room_id,
                action=_ACTION_REMOVED,
                actor_user_id=_resolve_actor(user_id),
                is_primary=was_primary,
                ip_address=_resolve_ip(ip_address),
            )
        # else: orphan — no DELETE, new row simply becomes the (first) primary

    db.session.add(ReservationRoom(
        reservation_id=reservation.id,
        room_id=new_room_id,
        is_primary=was_primary,
    ))
    if was_primary:
        reservation.room_id = new_room_id
    log_group_room_link(
        reservation_id=reservation.id,
        room_id=new_room_id,
        action=_ACTION_CREATED,
        actor_user_id=_resolve_actor(user_id),
        is_primary=was_primary,
        ip_address=_resolve_ip(ip_address),
    )


def mirror_room_to_bridge(
    reservation: Reservation,
    *,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> bool:
    """Convenience: ensure a bridge row exists for ``reservation.room_id``.

    Workhorse for write-site instrumentation. Call after any code that sets
    ``Reservation.room_id`` (check-in, walk-in, block-room, batch-checkin).
    If no bridge row exists for the current primary, inserts one with
    ``is_primary=True`` and writes an audit row.

    Idempotent — re-running is a no-op.

    Returns True iff a bridge row was inserted.
    """
    if not reservation.room_id:
        return False
    room = db.session.get(Room, reservation.room_id)
    if room is None:
        logger.warning(
            'mirror_room_to_bridge: reservation %s.room_id=%s but Room row missing',
            reservation.id, reservation.room_id,
        )
        return False
    return link_reservation_to_room(
        reservation, room,
        is_primary=True,
        user_id=user_id,
        ip_address=ip_address,
    )


def count_post_r2a_orphans() -> int:
    """Count reservations with a non-NULL primary room that have NO bridge row.

    The R2A acceptance metric: must return 0 on production data after R2A
    deploys + the backfill migration runs. Used by tests/parity validation.
    """
    return (
        Reservation.query
        .filter(
            Reservation.room_id.isnot(None),
            Reservation.status.in_(
                ('Reserved', 'Confirmed', 'CheckedIn', 'Overbooked', 'Blocked')
            ),
            ~db.session.query(ReservationRoom.id)
                .filter(ReservationRoom.reservation_id == Reservation.id)
                .exists(),
        )
        .count()
    )
