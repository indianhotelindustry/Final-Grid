"""
Reset Transactional Data — admin CLI utility.

PURPOSE
-------
Wipes all operational/transactional tables (reservations, payments, invoices,
check-ins, night audit logs, etc.) so the hotel can start fresh, while
PRESERVING all master configuration (users, rooms, room types, payment modes,
settings, GST policies, rate plans, POS items, loyalty config, equipment
masters, business_date, schema_migrations).

SAFETY
------
  1. Dry-run mode is the default — no data is touched unless explicit flags
     are passed.
  2. A full DB backup is taken BEFORE any delete. If backup fails, reset
     aborts.
  3. The user must type the exact phrase "RESET TRANSACTIONAL DATA" at the
     interactive confirmation prompt (or pass --i-understand-this-is-destructive
     on the command line for scripted use).
  4. Works for SQLite and PostgreSQL — sequences/identity counters are reset
     after delete so new records start clean.
  5. Schema, migrations, masters, and app startup are NOT affected.

USAGE
-----
    # 1. Dry-run (always safe — default):
    venv\\Scripts\\python reset_transactional_data.py
    venv\\Scripts\\python reset_transactional_data.py --dry-run

    # 2. Real reset (interactive confirmation):
    venv\\Scripts\\python reset_transactional_data.py --execute

    # 3. Scripted (skip interactive prompt — use with CAUTION):
    venv\\Scripts\\python reset_transactional_data.py --execute --i-understand-this-is-destructive

    # 4. Also wipe guest profiles (default: preserved for CRM):
    venv\\Scripts\\python reset_transactional_data.py --execute --reset-guests
"""
import argparse
import logging
import os
import sys

os.environ.setdefault('FLASK_ENV', 'production')

# NOTE: logging.disable() is deliberately NOT called at import time.
# app/admin_reset.py imports this module to reuse its table manifests, so an
# import-time logging.disable(WARNING) silenced every WARNING, INFO and DEBUG
# record in the whole application for the life of the process — including the
# night audit's snapshot-parse fallback warning. It is a CLI convenience and
# now applies only when this file is actually run as a script (see main()).


# ─── Table classification ──────────────────────────────────────────────────
#
# PRESERVED = master / configuration tables that MUST survive the reset.
# TRANSACTIONAL = operational tables that get cleared.
#
# The TRANSACTIONAL list is in FK-safe DELETE ORDER (children before parents).
# Violating this order will trigger FK constraint errors on PostgreSQL.
#
PRESERVED_TABLES = [
    'schema_migrations',    # migration tracking — NEVER touch
    'users',                # auth / roles
    'settings',             # app config
    'business_date',        # singleton business-date row
    'room_types',           # room category masters
    'rooms',                # physical room masters
    'payment_modes',        # settlement heads (direct + OTA receivable)
    'companies',            # corporate billing masters
    'rate_plans',           # pricing plan masters
    'pos_items',            # POS catalog
    'equipment',            # asset masters in rooms
    'loyalty_config',       # loyalty tier definitions
    'loyalty_milestones',   # loyalty bonus thresholds
]

# FK-safe delete order: children first. When adding a new operational table,
# place it ABOVE any table it references via FK.
TRANSACTIONAL_TABLES_IN_DELETE_ORDER = [
    # ── Loyalty operational data (children of guests + reservations) ─────
    'loyalty_redemptions',
    'loyalty_transactions',
    # ── Billing adjustments (reference payments / extra_charges) ─────────
    'cico_charge_logs',
    'credit_notes',
    'overpayment_logs',
    'void_requests',
    # ── Credit vouchers (redemptions reference vouchers + payments) ──────
    'credit_voucher_redemptions',
    'credit_vouchers',
    # ── OTA settlement payouts (references users only) ───────────────────
    'ota_payouts',
    # ── Reports / snapshots / alerts ─────────────────────────────────────
    'staff_performance_daily',
    'revenue_alerts',
    'backup_logs',
    'guest_feedback',
    'tax_lines',
    'no_show_logs',
    # ── Guest documents (references guests) ──────────────────────────────
    'foreign_national_info',
    'guest_id_documents',
    # ── Pre-check-in portal (references reservations) ────────────────────
    'precheckin_submissions',
    'precheckin_tokens',
    # ── Maintenance / equipment logs (references rooms + equipment) ──────
    'equipment_health_logs',
    'preventive_schedules',
    'maintenance_requests',
    # ── Notifications / webhooks (references reservations) ───────────────
    'notification_queue',
    'notification_logs',
    'webhook_logs',
    # ── Audit logs ───────────────────────────────────────────────────────
    'audit_logs',
    # ── Check-in records (references reservation, guest, room) ───────────
    'checkin_records',
    # ── Night audit (reopen logs reference night_audit_logs) ─────────────
    'night_audit_reopen_logs',
    'night_audit_logs',
    # ── Billing core (references reservations + folios) ──────────────────
    'payments',
    'extra_charges',
    'reservation_night_rates',
    'folios',
    # ── Reservation children + reservations ──────────────────────────────
    'reservation_passengers',
    'reservation_rooms',
    'reservations',
    # ── Group blocks (references companies) ──────────────────────────────
    'group_blocks',
    # ── Shifts (references users) ────────────────────────────────────────
    'shift_adjustments',
    'shifts',
]

# Guests are kept by default (CRM/loyalty value); pass --reset-guests to clear.
GUEST_TABLE = 'guests'


# ─── Helpers ───────────────────────────────────────────────────────────────
def _get_db_dialect(db):
    return db.engine.dialect.name  # 'sqlite' or 'postgresql'


def _row_count(db, table):
    try:
        result = db.session.execute(db.text(f'SELECT COUNT(*) FROM {table}'))
        return result.scalar() or 0
    except Exception:
        return 0


def _table_exists(db, table):
    try:
        db.session.execute(db.text(f'SELECT 1 FROM {table} LIMIT 1'))
        return True
    except Exception:
        db.session.rollback()
        return False


def _all_db_tables(db):
    """Return the set of real tables in the connected database."""
    if _get_db_dialect(db) == 'sqlite':
        sql = ("SELECT name FROM sqlite_master WHERE type='table' "
               "AND name NOT LIKE :pfx")
        params = {'pfx': 'sqlite_%'}
    else:
        sql = ("SELECT tablename FROM pg_tables "
               "WHERE schemaname = current_schema() AND tablename NOT LIKE :pfx")
        params = {'pfx': 'pg_%'}
    return {row[0] for row in db.session.execute(db.text(sql), params)}


def _find_unclassified(db):
    """Tables present in the DB but in NEITHER manifest.

    A non-empty result means the manifest has drifted behind a migration.
    That is not cosmetic: if an unlisted child table survives while its parent
    is deleted, the reset leaves orphan rows behind and corrupts the DB.
    """
    known = (set(PRESERVED_TABLES)
             | set(TRANSACTIONAL_TABLES_IN_DELETE_ORDER)
             | {GUEST_TABLE})
    return sorted(_all_db_tables(db) - known)


def _reset_identity(db, table):
    """Reset the autoincrement/identity counter for `table` so new inserts
    start at id=1. SQLite clears sqlite_sequence; PostgreSQL uses RESTART
    IDENTITY (applied via TRUNCATE path) or direct sequence reset."""
    dialect = _get_db_dialect(db)
    try:
        if dialect == 'sqlite':
            db.session.execute(db.text(
                "DELETE FROM sqlite_sequence WHERE name=:t"), {'t': table})
        elif dialect == 'postgresql':
            # Find the sequence attached to the primary-key column
            seq = db.session.execute(db.text(
                "SELECT pg_get_serial_sequence(:t, 'id')"
            ), {'t': table}).scalar()
            if seq:
                db.session.execute(db.text(
                    f'ALTER SEQUENCE {seq} RESTART WITH 1'))
    except Exception:
        db.session.rollback()


def _print_header(title):
    print()
    print('=' * 70)
    print(f'  {title}')
    print('=' * 70)


def _collect_report(db, include_guests):
    """Return a list of (table, classification, row_count, exists) tuples."""
    report = []
    for t in PRESERVED_TABLES:
        report.append((t, 'PRESERVED', _row_count(db, t), _table_exists(db, t)))
    for t in TRANSACTIONAL_TABLES_IN_DELETE_ORDER:
        report.append((t, 'CLEAR', _row_count(db, t), _table_exists(db, t)))
    guest_cls = 'CLEAR' if include_guests else 'PRESERVED (default)'
    report.append((GUEST_TABLE, guest_cls,
                   _row_count(db, GUEST_TABLE),
                   _table_exists(db, GUEST_TABLE)))
    return report


def _print_report(report):
    _print_header('TRANSACTIONAL DATA RESET — DRY RUN REPORT')
    # Group by classification
    preserved = [r for r in report if r[1].startswith('PRESERVED')]
    clear = [r for r in report if r[1] == 'CLEAR']

    print()
    print(f'  {"Table":<32} {"Rows":>10}   Action')
    print(f'  {"-"*32} {"-"*10}   {"-"*30}')
    total_preserved = 0
    for t, _, cnt, exists in preserved:
        note = '' if exists else '  (missing)'
        print(f'  {t:<32} {cnt:>10}   KEEP{note}')
        total_preserved += cnt
    print()
    total_cleared = 0
    for t, _, cnt, exists in clear:
        note = '' if exists else '  (missing)'
        print(f'  {t:<32} {cnt:>10}   DELETE{note}')
        total_cleared += cnt

    print()
    print(f'  Preserved rows : {total_preserved:>10}')
    print(f'  Rows to delete : {total_cleared:>10}')
    print(f'  Tables to clear: {len(clear):>10}')
    print()


def _run_backup(app, label_suffix='pre-reset'):
    """Take a full DB backup. Returns (ok, filename, msg)."""
    from app.backup_manager import run_backup
    import inspect
    kwargs = {'backup_type': 'pre-reset'}
    if 'label' in inspect.signature(run_backup).parameters:
        kwargs['label'] = label_suffix
    return run_backup(app, **kwargs)


# Public constant so the admin UI wrapper can render the exact phrase.
CONFIRMATION_PHRASE = 'RESET TRANSACTIONAL DATA'


def _confirm_interactive():
    """Require user to type the exact phrase at stdin."""
    phrase = CONFIRMATION_PHRASE
    print()
    print('  This will PERMANENTLY DELETE all transactional data listed above.')
    print('  Master/configuration tables will be preserved.')
    print()
    print(f'  To proceed, type exactly:  {phrase}')
    print('  (anything else will cancel)')
    print()
    try:
        entered = input('  > ').strip()
    except (KeyboardInterrupt, EOFError):
        print('\n  Cancelled.')
        return False
    if entered != phrase:
        print('  Phrase did not match. Cancelled.')
        return False
    return True


def _execute_delete(db, include_guests):
    """Run the DELETE statements in FK-safe order. Returns dict of
    {table: rows_deleted}."""
    deleted = {}
    tables_to_clear = list(TRANSACTIONAL_TABLES_IN_DELETE_ORDER)
    if include_guests:
        tables_to_clear.append(GUEST_TABLE)

    dialect = _get_db_dialect(db)
    print()
    print('  Deleting transactional rows...')

    # On SQLite, temporarily disable FK checks to allow the bulk wipe in one
    # transaction. On PostgreSQL the delete order itself is FK-safe.
    if dialect == 'sqlite':
        db.session.execute(db.text('PRAGMA foreign_keys = OFF'))

    try:
        for table in tables_to_clear:
            if not _table_exists(db, table):
                continue
            before = _row_count(db, table)
            db.session.execute(db.text(f'DELETE FROM {table}'))
            deleted[table] = before
            print(f'    {table:<32} {before:>8} rows deleted')

        db.session.commit()

        # Reset identity counters after successful commit
        for table in tables_to_clear:
            if _table_exists(db, table):
                _reset_identity(db, table)
        db.session.commit()

    finally:
        if dialect == 'sqlite':
            db.session.execute(db.text('PRAGMA foreign_keys = ON'))
            db.session.commit()

    return deleted


# ─── Main ──────────────────────────────────────────────────────────────────
def main(argv=None):
    # Quieten library chatter for the CLI run only. Scoped here rather than at
    # module import so that importing this module never reconfigures logging
    # for a host application.
    logging.disable(logging.WARNING)

    parser = argparse.ArgumentParser(
        description='Reset PMS transactional data while preserving masters.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument('--execute', action='store_true',
                        help='Actually perform the reset. Without this flag, runs in dry-run mode.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Explicit dry-run (same as default — no changes made).')
    parser.add_argument('--reset-guests', action='store_true',
                        help='Also clear the guests table (default: guests preserved for CRM/loyalty).')
    parser.add_argument('--i-understand-this-is-destructive', action='store_true',
                        help='Skip the interactive confirmation phrase. Use only in scripts.')
    parser.add_argument('--allow-schema-drift', action='store_true',
                        help='Proceed even if the DB has tables in neither manifest. '
                             'They are left untouched, which may leave orphan rows.')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip the mandatory backup. DANGEROUS — only use if you just took one manually.')
    args = parser.parse_args(argv)

    # Import late so the app context is ready
    from app import create_app
    from app.models import db
    app = create_app()

    with app.app_context():
        # ── Step 1: Report ──────────────────────────────────────────────
        report = _collect_report(db, include_guests=args.reset_guests)
        _print_report(report)

        # ── Step 1b: Schema-drift guard ─────────────────────────────────
        unclassified = _find_unclassified(db)
        if unclassified:
            print('  SCHEMA DRIFT — tables in neither manifest:')
            for t in unclassified:
                print(f'    {t:<32} {_row_count(db, t):>8} rows')
            print()
            if args.execute and not args.allow_schema_drift:
                print('  Reset ABORTED — no data touched.')
                print('  Classify these tables in reset_transactional_data.py,')
                print('  or pass --allow-schema-drift to leave them untouched.')
                print()
                return 4

        if not args.execute:
            print('  This was a DRY-RUN. No data was modified.')
            print('  To perform the reset, re-run with --execute')
            print()
            return 0

        # ── Step 2: Confirmation ────────────────────────────────────────
        if not args.i_understand_this_is_destructive:
            if not _confirm_interactive():
                return 1

        # ── Step 3: Backup ──────────────────────────────────────────────
        if not args.no_backup:
            _print_header('Taking mandatory pre-reset backup')
            ok, fname, msg = _run_backup(app)
            if not ok:
                print(f'  BACKUP FAILED: {msg}')
                print('  Reset ABORTED — no data touched.')
                return 2
            print(f'  Backup created: {fname}')
        else:
            print('  WARNING: --no-backup flag set. Skipping backup.')

        # ── Step 4: Delete ──────────────────────────────────────────────
        _print_header('Executing delete')
        try:
            deleted = _execute_delete(db, include_guests=args.reset_guests)
        except Exception as exc:
            db.session.rollback()
            print(f'  DELETE FAILED: {exc}')
            print('  Transaction rolled back — data is intact.')
            print('  If a backup was taken, it is still on disk.')
            return 3

        # ── Step 5: Summary ─────────────────────────────────────────────
        _print_header('RESET COMPLETE')
        total = sum(deleted.values())
        print(f'  Tables cleared : {len(deleted)}')
        print(f'  Rows deleted   : {total}')
        if not args.reset_guests:
            print(f'  Guests         : preserved ({_row_count(db, GUEST_TABLE)} profiles)')
        print('  Masters        : preserved (users, rooms, settings, payment modes, etc.)')
        print('  Schema         : untouched')
        print()
        print('  The PMS is now ready for a fresh start.')
        print('  Next: restart the server and verify dashboard shows 0 active reservations.')
        print()
        return 0


if __name__ == '__main__':
    sys.exit(main())
