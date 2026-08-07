"""add hot-path indexes for reservations, payments, extra_charges, folios

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-20 12:00:00.000000

Adds the indexes identified by the Week 2 data-integrity audit. These
columns are filtered or joined on nearly every report/dashboard query, so
a missing index forces a full table scan. All indexes are ``IF NOT EXISTS``
aware via ``op.create_index`` + a pre-check so that the migration is
idempotent on any install that may have already created them manually.

No data is modified; this migration is safe to apply online.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


# (index_name, table, columns)
_INDEXES = [
    # Reservation date ranges — used by availability, night audit,
    # occupancy reports, dashboard arrivals/departures.
    ('idx_reservation_arrival_date',   'reservations', ['arrival_date']),
    ('idx_reservation_departure_date', 'reservations', ['departure_date']),
    ('idx_reservation_status',         'reservations', ['status']),

    # Payment date filters — used by night audit, payment report,
    # GST report, collection report.
    ('idx_payment_payment_date',       'payments', ['payment_date']),
    ('idx_payment_is_voided',          'payments', ['is_voided']),
    ('idx_payment_folio_id',           'payments', ['folio_id']),

    # ExtraCharge — used by folio total, night audit room-rent posting,
    # GST breakdown.
    ('idx_extra_charge_charge_date',   'extra_charges', ['charge_date']),
    ('idx_extra_charge_folio_id',      'extra_charges', ['folio_id']),
    ('idx_extra_charge_charge_type',   'extra_charges', ['charge_type']),

    # Folio — used by split-billing list on every reservation view.
    ('idx_folio_reservation_id',       'folios', ['reservation_id']),

    # NightAuditLog status filter (lookup for last closed / reopened).
    ('idx_night_audit_status',         'night_audit_logs', ['status']),
]


# Partial UNIQUE index for idempotent payment inserts. Separate from the
# list above because it requires a WHERE clause and is UNIQUE; we emit it
# via raw SQL to avoid dialect-specific op.create_index quirks.
_IDEM_INDEX_NAME = 'ux_payment_idem_ref'
_IDEM_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_payment_idem_ref "
    "ON payments(reference_number) "
    "WHERE reference_number LIKE 'idem:%'"
)


def _existing_indexes(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix['name'] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


def upgrade():
    """Create missing hot-path indexes. Idempotent — skips any that already exist."""
    # Group indexes per table so we only inspect each table once.
    by_table: dict = {}
    for name, table, cols in _INDEXES:
        by_table.setdefault(table, []).append((name, cols))

    for table, entries in by_table.items():
        # Skip tables that don't exist yet (partial migration chain)
        bind = op.get_bind()
        insp = sa.inspect(bind)
        try:
            if table not in set(insp.get_table_names()):
                continue
        except Exception:
            continue
        existing = _existing_indexes(table)
        for name, cols in entries:
            if name in existing:
                continue
            op.create_index(name, table, cols)

    # Partial UNIQUE index on payment idempotency keys. Both SQLite (>=3.8)
    # and PostgreSQL accept the WHERE-clause syntax. IF NOT EXISTS makes it
    # safe to re-run.
    try:
        op.execute(sa.text(_IDEM_INDEX_SQL))
    except Exception:
        # Some SQLAlchemy versions don't accept sa.text() in op.execute;
        # fall back to raw string.
        op.execute(_IDEM_INDEX_SQL)


def downgrade():
    """Drop the indexes added by this migration. Idempotent on missing."""
    # Drop the partial UNIQUE index first — it is ENGINE-level, not per-table.
    try:
        op.execute(sa.text(f'DROP INDEX IF EXISTS {_IDEM_INDEX_NAME}'))
    except Exception:
        op.execute(f'DROP INDEX IF EXISTS {_IDEM_INDEX_NAME}')

    by_table: dict = {}
    for name, table, cols in _INDEXES:
        by_table.setdefault(table, []).append(name)

    for table, names in by_table.items():
        existing = _existing_indexes(table)
        for name in names:
            if name in existing:
                op.drop_index(name, table_name=table)
