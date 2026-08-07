"""add reservation_rooms bridge table (Group Stay Phase 1, Release 1)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-09 22:00:00.000000

Phase 1 of Group Stay Management — multi-room shared reservations.

This migration is purely additive: a new bridge table that allows one
Reservation to optionally span 1..N rooms. Existing single-room
behaviour is unaffected. The bridge table is invisible to all existing
code paths until Release 1's helper layer (Reservation.all_room_ids,
occupancy formula, conflict-detection helper) starts reading it.

Schema:
    reservation_rooms(
        id PK,
        reservation_id FK → reservations,
        room_id        FK → rooms,
        is_primary     BOOLEAN — exactly one per reservation,
        created_at     DATETIME
    )

Invariants enforced at DB level:
    - UNIQUE(reservation_id, room_id) — a room cannot be linked twice.
    - Partial UNIQUE on (reservation_id) WHERE is_primary=1 — at most
      one primary room per reservation.

No data is modified by this migration. Backfill of existing active
reservations happens in the next revision (e6f7a8b9c0d1).

Safe to apply online; safe to re-run (idempotent on table/index exist).
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


_TABLE_NAME = 'reservation_rooms'
_PARTIAL_PRIMARY_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_resroom_primary "
    "ON reservation_rooms(reservation_id) "
    "WHERE is_primary = 1"
)


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return name in set(insp.get_table_names())
    except Exception:
        return False


def _existing_indexes(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix['name'] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


def upgrade():
    """Create reservation_rooms table + indexes. Idempotent."""
    if not _table_exists(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('reservation_id', sa.Integer,
                      sa.ForeignKey('reservations.id'), nullable=False),
            sa.Column('room_id', sa.Integer,
                      sa.ForeignKey('rooms.id'), nullable=False),
            sa.Column('is_primary', sa.Boolean, nullable=False,
                      server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime, nullable=False,
                      server_default=sa.func.current_timestamp()),
            sa.UniqueConstraint('reservation_id', 'room_id',
                                name='uq_resroom_reservation_room'),
        )

    existing = _existing_indexes(_TABLE_NAME)
    if 'idx_resroom_res' not in existing:
        op.create_index('idx_resroom_res', _TABLE_NAME, ['reservation_id'])
    if 'idx_resroom_room' not in existing:
        op.create_index('idx_resroom_room', _TABLE_NAME, ['room_id'])

    # Partial unique index — emitted via raw SQL because op.create_index's
    # sqlite_where support varies across SQLAlchemy versions. IF NOT EXISTS
    # makes it safe to re-run. SQLite >= 3.8 supports partial indexes.
    try:
        op.execute(sa.text(_PARTIAL_PRIMARY_INDEX_SQL))
    except Exception:
        op.execute(_PARTIAL_PRIMARY_INDEX_SQL)


def downgrade():
    """Drop the bridge table and its indexes.

    OPERATIONAL NOTE: per docs/RELEASE.md, this downgrade is intentionally
    NOT run in production. Bridge data, once populated, would be orphaned
    by a downgrade. Restore from a pre-upgrade backup if rolling back a
    release that included this migration. The function is implemented for
    completeness (and for use on staging / disposable environments).
    """
    try:
        op.execute(sa.text('DROP INDEX IF EXISTS idx_resroom_primary'))
    except Exception:
        op.execute('DROP INDEX IF EXISTS idx_resroom_primary')

    if _table_exists(_TABLE_NAME):
        existing = _existing_indexes(_TABLE_NAME)
        if 'idx_resroom_room' in existing:
            op.drop_index('idx_resroom_room', table_name=_TABLE_NAME)
        if 'idx_resroom_res' in existing:
            op.drop_index('idx_resroom_res', table_name=_TABLE_NAME)
        op.drop_table(_TABLE_NAME)
