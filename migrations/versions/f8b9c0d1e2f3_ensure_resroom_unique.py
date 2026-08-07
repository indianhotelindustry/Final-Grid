"""ensure reservation_rooms (reservation_id, room_id) uniqueness — mid-RC fix for v2.2.13

Revision ID: f8b9c0d1e2f3
Revises: e6f7a8b9c0d1
Create Date: 2026-05-13 22:30:00.000000

Why this migration exists
-------------------------
v2.2.10 introduced ``migrations/versions/d5e6f7a8b9c0_add_reservation_rooms_bridge.py``
which declared a UNIQUE constraint on ``reservation_rooms(reservation_id, room_id)``
via ``sa.UniqueConstraint(name='uq_resroom_reservation_room')``. Boxes where the
alembic chain actually ran (build box, fresh installs) have the constraint;
ON CONFLICT (reservation_id, room_id) works correctly on them.

But on boxes where v2.2.10's patch_apply.bat heredoc bug silently no-opped
flask_migrate.upgrade() — including the production staging box that recovered
via the v2.2.11 manual ``flask db stamp e6f7a8b9c0d1`` workaround — the
``reservation_rooms`` table was created instead by ``db.create_all()`` at app
boot. Depending on the model class state at the time of first auto-creation,
the UniqueConstraint may NOT have been emitted. Those boxes have the bridge
table WITHOUT the constraint.

When the v2.2.13 RC ran ``f7a8b9c0d1e2_backfill_post_r1_orphans.py`` on staging,
SQLite correctly rejected the ON CONFLICT clause with:

    sqlite3.OperationalError: ON CONFLICT clause does not match any
    PRIMARY KEY or UNIQUE constraint

The governance pipeline aborted cleanly. No corruption.

What this migration does
------------------------
Step 1 — DUPLICATE DETECTION (fail-loud).
    Query for any existing (reservation_id, room_id) duplicates. If found,
    raise RuntimeError with the full violation list. Operators must dedupe
    manually — automatic dedupe would be a financial-audit-grade decision
    we refuse to make.

Step 2 — DEFENSIVE INDEX CREATION.
    CREATE UNIQUE INDEX IF NOT EXISTS idx_resroom_unique ON
    reservation_rooms(reservation_id, room_id). Idempotent. Provides the
    uniqueness invariant that ON CONFLICT needs, REGARDLESS of whether the
    table was created via alembic (constraint present) or via create_all()
    (constraint may be missing).

What this migration does NOT do
-------------------------------
- No data mutation. Pure schema invariant repair.
- Does NOT drop or modify ``uq_resroom_reservation_room`` (the existing
  constraint from d5e6f7a8b9c0). Both can coexist.
- Does NOT dedupe. Refuses to proceed if duplicates exist.

Companion edit
--------------
``f7a8b9c0d1e2_backfill_post_r1_orphans.py`` has its ``down_revision`` updated
from 'e6f7a8b9c0d1' to 'f8b9c0d1e2f3', so this migration runs immediately
before the backfill it unblocks.
"""
import logging

from alembic import op
import sqlalchemy as sa


revision = 'f8b9c0d1e2f3'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return name in set(insp.get_table_names())
    except Exception:
        return False


def upgrade():
    """Ensure (reservation_id, room_id) uniqueness on reservation_rooms.

    Fail-loud if duplicates already exist. Otherwise create a unique index
    idempotently (no-op on boxes where the constraint already exists).
    """
    log = logging.getLogger('alembic.runtime.migration')

    if not _table_exists('reservation_rooms'):
        # No bridge table yet — nothing to enforce. Downstream migrations
        # create it. This branch should only fire on extremely fresh boxes.
        log.info('reservation_rooms table absent; nothing to enforce')
        return

    bind = op.get_bind()

    # ── Step 1: duplicate detection (fail-loud) ──────────────────────
    duplicates = bind.execute(sa.text("""
        SELECT reservation_id, room_id, COUNT(*) AS cnt
          FROM reservation_rooms
         GROUP BY reservation_id, room_id
        HAVING COUNT(*) > 1
         ORDER BY reservation_id, room_id
    """)).fetchall()

    if duplicates:
        # Build a human-readable violation report and fail-loud.
        # We do NOT dedupe — that's an audit-grade decision for the operator.
        lines = ['Pre-existing duplicate (reservation_id, room_id) rows '
                 'detected in reservation_rooms.',
                 'Cannot enforce UNIQUE invariant safely. Operator must '
                 'dedupe manually before re-running this migration.',
                 '',
                 'Violations:']
        for row in duplicates:
            lines.append('  reservation_id={0} room_id={1} count={2}'.format(
                row[0], row[1], row[2]))
        lines.append('')
        lines.append('Recovery options (operator chooses one, by audit policy):')
        lines.append('  A. Keep is_primary=True row, drop the rest:')
        lines.append('       DELETE FROM reservation_rooms')
        lines.append('        WHERE id NOT IN (')
        lines.append('            SELECT MIN(id) FROM reservation_rooms')
        lines.append('             GROUP BY reservation_id, room_id')
        lines.append('             HAVING COUNT(*) > 1')
        lines.append('               AND SUM(CASE WHEN is_primary=1 THEN 1 ELSE 0 END) > 0')
        lines.append('        )')
        lines.append('        AND (reservation_id, room_id) IN (')
        lines.append('            SELECT reservation_id, room_id FROM reservation_rooms')
        lines.append('             GROUP BY reservation_id, room_id')
        lines.append('             HAVING COUNT(*) > 1')
        lines.append('        );')
        lines.append('')
        lines.append('  B. Keep the oldest row by created_at, drop the rest:')
        lines.append('       DELETE FROM reservation_rooms')
        lines.append('        WHERE id NOT IN (')
        lines.append('            SELECT MIN(id) FROM reservation_rooms')
        lines.append('             GROUP BY reservation_id, room_id')
        lines.append('        );')
        lines.append('')
        lines.append('After deduping, re-run:')
        lines.append('  venv\\Scripts\\python.exe -m alembic -c migrations\\alembic.ini upgrade head')
        msg = '\n'.join(lines)
        log.error(msg)
        raise RuntimeError(msg)

    # ── Step 2: defensive unique-index creation (idempotent) ─────────
    # CREATE UNIQUE INDEX IF NOT EXISTS makes this a no-op on boxes where
    # the index already exists (build box, fresh installs). On boxes where
    # the bridge table was created via db.create_all() without the
    # UniqueConstraint, this is the load-bearing repair.
    bind.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_resroom_unique '
        'ON reservation_rooms(reservation_id, room_id)'
    ))

    log.info(
        'reservation_rooms uniqueness verified: 0 duplicates, '
        'idx_resroom_unique present'
    )


def downgrade():
    """Drop the defensive unique index.

    The ``uq_resroom_reservation_room`` constraint from d5e6f7a8b9c0 is
    untouched. Per docs/RELEASE.md, downgrades on Group Stay migrations
    are not run in production; this implementation exists for staging.
    """
    bind = op.get_bind()
    bind.execute(sa.text('DROP INDEX IF EXISTS idx_resroom_unique'))
