"""backfill reservation_rooms for post-Release-1 orphans (Group Stay R2A)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-13 17:30:00.000000

Companion to e6f7a8b9c0d1 — the Release 1 backfill populated bridge rows for
every active reservation at that point. Between v2.2.10 deploy and v2.3.0
(R2A) deploy, application code created reservations without maintaining the
bridge (see R2A write-site instrumentation). This migration catches any
orphan that slipped through.

Same query, same idempotency (ON CONFLICT DO NOTHING). Same status filter:
active reservations only.

R2A's application code now maintains the bridge invariant, so this is the
LAST backfill required for the post-v2.2.10 → R2A transition window.
Subsequent reservation creates land in the bridge at write time.

Acceptance contract: after this migration runs, the count of reservations
with a non-NULL primary room and ACTIVE status that have NO bridge row
MUST be 0. The R2A test suite asserts this.
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
# down_revision was 'e6f7a8b9c0d1' pre-v2.2.13-mid-RC. The ON CONFLICT clause
# in the upgrade body below requires a UNIQUE constraint/index on
# (reservation_id, room_id). On boxes where d5e6f7a8b9c0 ran via alembic the
# constraint exists; on boxes where reservation_rooms was created via
# db.create_all() (v2.2.10 patch_apply.bat heredoc bug aftermath) the
# constraint may be missing. The new revision f8b9c0d1e2f3 inserts a
# defensive unique-index creation step BEFORE this backfill, guaranteeing
# ON CONFLICT works on every box.
down_revision = 'f8b9c0d1e2f3'
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
    """Catch any reservation that gained a room_id post-v2.2.10 without a bridge row.

    Idempotent. INSERT ON CONFLICT DO NOTHING — Release 1 backfilled rows
    are preserved untouched.
    """
    if not _table_exists('reservation_rooms') or not _table_exists('reservations'):
        return

    bind = op.get_bind()
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

    inserted = getattr(result, 'rowcount', None)
    if inserted is None:
        inserted = '?'

    # Sanity assertion: post-migration, the orphan count must be zero.
    remaining = bind.execute(sa.text(f"""
        SELECT COUNT(*)
          FROM reservations r
         WHERE r.room_id IS NOT NULL
           AND r.status IN ({statuses_placeholder})
           AND NOT EXISTS (
               SELECT 1 FROM reservation_rooms rr
                WHERE rr.reservation_id = r.id
           )
    """)).scalar() or 0

    log = logging.getLogger('alembic.runtime.migration')
    log.info(
        'R2A orphan backfill: %s row(s) inserted; orphan_count_after=%s',
        inserted, remaining,
    )
    if remaining > 0:
        # Fail-loud: a non-zero remainder means an active reservation has a
        # room_id but the INSERT couldn't satisfy it — likely a phantom Room
        # FK or some other inconsistency. R2A's deploy gate is "remainder == 0".
        raise RuntimeError(
            f'R2A backfill incomplete: {remaining} active reservation(s) with '
            f'room_id still have no reservation_rooms row. Manual inspection '
            f'required. Migration aborted.'
        )


def downgrade():
    """Remove R2A-era is_primary=1 rows for active reservations.

    Symmetric with e6f7a8b9c0d1 downgrade. Per docs/RELEASE.md, downgrades on
    Group Stay migrations are not run in production — exists for staging.
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
