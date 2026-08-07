"""backfill reservation_rooms for active reservations (Phase 1, Release 1)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-09 22:05:00.000000

Inserts one is_primary=True row into reservation_rooms for every ACTIVE
reservation (Reserved, Confirmed, CheckedIn, Overbooked, Blocked) that
has a non-NULL room_id. Closed historical rows (CheckedOut, Cancelled,
NoShow) are NOT backfilled — they are never read by occupancy or
conflict-detection hot paths, and the Reservation.all_room_ids() helper
already falls back to [room_id] for any reservation lacking a bridge
entry.

This migration produces ZERO behavioural change at deploy time:
    - get_occupied_count() reads the bridge → returns the same number
      as the prior count() formula (each active row has exactly one
      bridge entry, one room).
    - rooms_held_in_window() reads bridge + Reservation.room_id and
      deduplicates → same set of held rooms as before.
    - Existing single-room flows do not touch the bridge.

Idempotent (ON CONFLICT DO NOTHING). Re-running creates zero rows.

Audit trail:
    The migration logs a one-line summary to pms.log on completion
    ("backfilled N rows"). Per-row audit_logs entries are intentionally
    not written from the migration — there is no operator user context
    at alembic-upgrade time. Per-row logging via log_group_room_link()
    activates for application-driven creations in Release 2/3.
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


_ACTIVE_STATUSES = ('Reserved', 'Confirmed', 'CheckedIn', 'Overbooked', 'Blocked')


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return name in set(insp.get_table_names())
    except Exception:
        return False


def upgrade():
    """Backfill bridge entries for active reservations. Idempotent."""
    if not _table_exists('reservation_rooms') or not _table_exists('reservations'):
        # Bridge table or reservations table missing — nothing to do.
        return

    bind = op.get_bind()

    # SQLite ≥ 3.24 and PostgreSQL both support ON CONFLICT DO NOTHING.
    # Backfill is bounded: at Sukoon Pearl Inn, active rows are ~50–100
    # at peak. Closed historical rows are intentionally skipped because
    # they are not read by any hot path and the fallback in
    # Reservation.all_room_ids() covers them.
    statuses_placeholder = ','.join(f"'{s}'" for s in _ACTIVE_STATUSES)
    result = bind.execute(sa.text(f"""
        INSERT INTO reservation_rooms
            (reservation_id, room_id, is_primary, created_at)
        SELECT id, room_id, 1, created_at
          FROM reservations
         WHERE room_id IS NOT NULL
           AND status IN ({statuses_placeholder})
        ON CONFLICT (reservation_id, room_id) DO NOTHING
    """))

    # Result.rowcount reflects how many rows were actually inserted
    # (excluding ON CONFLICT skips). Log for operational traceability.
    inserted = getattr(result, 'rowcount', None)
    if inserted is None:
        inserted = '?'
    logging.getLogger('alembic.runtime.migration').info(
        'reservation_rooms backfill: %s row(s) inserted for active reservations',
        inserted,
    )


def downgrade():
    """Remove only the primary-room rows inserted by this migration.

    A reservation that gained additional non-primary rows after the
    backfill (i.e. became a real multi-room reservation in a later
    release) keeps those rows. We delete only the is_primary=1 mirrors
    that this migration could have created.

    OPERATIONAL NOTE: per docs/RELEASE.md, downgrades on Group Stay
    migrations are not run in production. Use a pre-upgrade DB restore
    for rollback. This implementation exists for staging.
    """
    if not _table_exists('reservation_rooms'):
        return

    bind = op.get_bind()
    statuses_placeholder = ','.join(f"'{s}'" for s in _ACTIVE_STATUSES)
    bind.execute(sa.text(f"""
        DELETE FROM reservation_rooms
         WHERE is_primary = 1
           AND reservation_id IN (
               SELECT id FROM reservations
                WHERE status IN ({statuses_placeholder})
           )
    """))
