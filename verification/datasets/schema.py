"""
The table classification, and why a dataset is built on the real schema.

Two ways to build a regression dataset
--------------------------------------
**Synthesise a schema and fill it.** Fast, self-contained, and wrong. The
synthetic schema drifts from production the first time a migration lands,
and from then on the datasets exercise constraints the real database does
not have and miss the ones it does. D5 proved how much that matters:
FLT-A10 was never injected because the real ``reservations`` table has
five NOT NULL money columns a hand-written statement did not know about.
A synthetic schema would have accepted it and the fault would have
reported a clean pass over a row that could never exist.

**Strip a copy of production and rebuild the transactional layer.** The
schema is real by construction — it *is* the production schema, migrated
exactly as production is — and the master data (rooms, room types,
payment modes, settings, tax policy) is the hotel's own configuration
rather than an invented approximation. Only the transactional story is
replaced.

The second is what this module supports, and the classification below is
the whole of it.

Relationship to ``reset_transactional_data.py``
-----------------------------------------------
The application ships an admin utility with the same classification. It
is **deliberately not imported.** That script is production tooling with
its own safety interlocks, backups and confirmation prompts, and the
verification package may not depend on production code — the measuring
instrument must not become part of the thing it measures. The lists are
therefore restated here, and ``verify_classification()`` proves the
restatement still covers every table the live schema actually has, so the
duplication cannot rot silently.
"""
from __future__ import annotations

import sqlite3

#: Master and configuration tables. Preserved verbatim, because a
#: dataset built on invented room types and invented tax policy is not
#: measuring this hotel.
PRESERVED_TABLES = (
    'schema_migrations',
    'users',
    'settings',
    'business_date',
    'room_types',
    'rooms',
    'payment_modes',
    'companies',
    'rate_plans',
    'pos_items',
    'equipment',
    'loyalty_config',
    'loyalty_milestones',
)

#: Transactional tables, in FK-safe delete order: children before
#: parents. A dataset replaces all of these. Restated from the admin
#: utility rather than imported; ``verify_classification`` keeps the two
#: honest about the live schema.
TRANSACTIONAL_TABLES_IN_DELETE_ORDER = (
    'loyalty_redemptions',
    'loyalty_transactions',
    'cico_charge_logs',
    'credit_notes',
    'overpayment_logs',
    'void_requests',
    # The four the admin utility does not classify. See
    # UNCLASSIFIED_BY_ADMIN_RESET below — this is a production finding,
    # not a difference of opinion about where they belong.
    'credit_voucher_redemptions',   # -> credit_vouchers, payments
    'credit_vouchers',              # -> reservations, guests
    'ota_payouts',                  # -> users only
    'staff_performance_daily',
    'revenue_alerts',
    'backup_logs',
    'guest_feedback',
    'tax_lines',
    'no_show_logs',
    'foreign_national_info',
    'guest_id_documents',
    'precheckin_submissions',
    'precheckin_tokens',
    'equipment_health_logs',
    'preventive_schedules',
    'maintenance_requests',
    'notification_queue',
    'notification_logs',
    'webhook_logs',
    'audit_logs',
    'checkin_records',
    'night_audit_reopen_logs',
    'night_audit_logs',
    'payments',
    'extra_charges',
    'reservation_night_rates',
    'folios',
    'reservation_passengers',
    'reservation_rooms',            # -> reservations, rooms. See below.
    'reservations',
    'group_blocks',
    'shift_adjustments',
    'shifts',
)

#: ``guests`` is neither. The admin utility preserves guest profiles by
#: default for CRM reasons; a regression dataset must own its guests
#: outright, because a narrative about "the guest who overpaid" cannot
#: reference a guest the dataset did not create. It is stripped last,
#: after every table that references it.
GUEST_TABLES = ('guests',)


#: Tables the live schema has that the shipped admin utility
#: ``reset_transactional_data.py`` classifies as neither preserved nor
#: transactional, and which it therefore does not delete. It has no
#: dynamic catch-all, so these simply survive a reset.
#:
#: This is a **production finding**, recorded here because this module is
#: where it was found and where it would otherwise be silently papered
#: over by classifying the tables correctly and saying nothing.
#:
#: ``reservation_rooms`` is the one that matters. It holds 28 rows on the
#: current production database, every one a child of a reservation the
#: reset deletes. After a reset the hotel would carry orphaned
#: room-allocation rows pointing at reservations that no longer exist.
#: The other three are empty today, so the exposure is latent rather than
#: current.
#:
#: Per the Wave 0 standing instruction this is reported and NOT fixed:
#: ``reset_transactional_data.py`` is production tooling and no
#: verification deliverable may change it. It belongs on the Wave 1
#: triage list.
UNCLASSIFIED_BY_ADMIN_RESET = (
    'reservation_rooms',
    'credit_vouchers',
    'credit_voucher_redemptions',
    'ota_payouts',
)


class ClassificationDrift(RuntimeError):
    """The live schema has a table this module does not classify.

    Raised rather than ignored. An unclassified table is one a dataset
    would neither preserve nor strip, so its production rows would leak
    into every dataset — and the dataset would look clean while carrying
    someone else's data.
    """


def live_tables(db_path: str) -> tuple:
    conn = sqlite3.connect('file:' + db_path.replace('\\', '/') + '?mode=ro',
                           uri=True)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    finally:
        conn.close()
    return tuple(r[0] for r in rows)


def verify_classification(db_path: str) -> tuple:
    """Return ``(unclassified, missing)`` for the live schema.

    ``unclassified`` — tables the database has and this module does not
    place. Every one is a leak.
    ``missing`` — tables this module names and the database does not
    have. Harmless but reported, because a stale name means the
    classification is drifting.
    """
    known = set(PRESERVED_TABLES) | set(
        TRANSACTIONAL_TABLES_IN_DELETE_ORDER) | set(GUEST_TABLES)
    live = set(live_tables(db_path))
    return tuple(sorted(live - known)), tuple(sorted(known - live))


def assert_classified(db_path: str) -> None:
    unclassified, _missing = verify_classification(db_path)
    if unclassified:
        raise ClassificationDrift(
            f'The live schema has {len(unclassified)} table(s) this module '
            f'does not classify: {", ".join(unclassified)}.\n'
            f'A dataset would neither preserve nor strip them, so their '
            f'production rows would leak into every dataset while the '
            f'dataset appeared clean. Classify them in '
            f'verification/datasets/schema.py before building anything.')


def strip_order() -> tuple:
    """Delete order for building a dataset: transactional, then guests."""
    return TRANSACTIONAL_TABLES_IN_DELETE_ORDER + GUEST_TABLES


def table_columns(conn: sqlite3.Connection, table: str) -> tuple:
    return tuple(r[1] for r in conn.execute(f'PRAGMA table_info("{table}")'))


def required_columns(conn: sqlite3.Connection, table: str) -> tuple:
    """NOT NULL columns with no default and no primary key.

    A declared row that omits one of these cannot be inserted. Returned
    so the builder can say which column is missing and in which table,
    rather than surfacing an opaque IntegrityError — the failure mode D5
    hit with FLT-A10.
    """
    return tuple(r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')
                 if r[3] and r[4] is None and not r[5])
