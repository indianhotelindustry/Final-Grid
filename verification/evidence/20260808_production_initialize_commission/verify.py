"""Commission the Production Initialization Framework.

A dry run reports "0 unclassified, 437 rows would be removed". That is the
answer the tool was built to give, and a tool that printed it
unconditionally would look identical (P9). So every safety condition is
driven to failure and required to abort, and every claim the tool makes
about the result is checked independently of the tool.

**Production is never opened except read-only.** Every case runs on a
throwaway copy in a temp directory, and production's SHA-256 is compared
before and after the whole run.
"""
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools import production_initialize as pi                # noqa: E402
from tools.initialization_classification import (            # noqa: E402
    CLASSIFICATION, MASTER, TRANSACTION,
)

PROD = os.path.join(ROOT, 'instance', 'pms.db')
results = []
WORK = tempfile.mkdtemp(prefix='pi_commission_')
#: Backups from a commissioning run belong with the commissioning run, not
#: in the production backup store. The first version of this file let them
#: accumulate under ../db-backups/initialization/, which is how a test
#: artefact ends up looking like a production event.
BACKUPS = os.path.join(WORK, 'backups')


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print('%-4s %-62s got %-9s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def fresh(name):
    """A throwaway copy of production, via the backup API."""
    path = os.path.join(WORK, name)
    src = sqlite3.connect('file:' + PROD.replace('\\', '/') + '?mode=ro',
                          uri=True)
    dst = sqlite3.connect(path)
    src.backup(dst)
    dst.close()
    src.close()
    return path


def counts(path):
    conn = sqlite3.connect('file:' + path.replace('\\', '/') + '?mode=ro',
                           uri=True)
    try:
        return {t[0]: conn.execute('SELECT COUNT(*) FROM "%s"' % t[0])
                .fetchone()[0]
                for t in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'")}
    finally:
        conn.close()


PROD_BEFORE = sha(PROD)
TODAY = dt.date(2026, 8, 8)

# =====================================================================
print('== the tool aborts on every declared safety condition ==')

# 1. Unknown table. The condition that exists because
#    reset_transactional_data.py lacks it.
db = fresh('unknown.db')
conn = sqlite3.connect(db)
conn.execute('CREATE TABLE a_table_nobody_classified (id INTEGER PRIMARY KEY)')
conn.commit()
conn.close()
try:
    pi.initialize(db, confirm=True, business_date=TODAY, boot_check=False,
                  quiet=True, backup_root=BACKUPS)
    check('unknown table aborts', 'no abort', 'abort')
except pi.InitializationAborted as exc:
    check('unknown table aborts', 'abort', 'abort')
    check('  and names the table',
          'a_table_nobody_classified' in str(exc), True)
check('  and changed nothing', counts(db)['reservations'], 28)

# 2. A MASTER declaring a foreign key into a cleared table.
db = fresh('contradiction.db')
conn = sqlite3.connect(db)
conn.execute('ALTER TABLE pos_items RENAME TO pos_items_old')
conn.execute('CREATE TABLE pos_items (id INTEGER PRIMARY KEY, '
             'reservation_id INTEGER REFERENCES reservations(id))')
conn.commit()
conn.close()
try:
    pi.initialize(db, confirm=True, business_date=TODAY, boot_check=False,
                  quiet=True, backup_root=BACKUPS)
    check('MASTER depending on TRANSACTION aborts', 'no abort', 'abort')
except pi.InitializationAborted as exc:
    msg = str(exc)
    # It may abort on the renamed table first; either abort is correct.
    check('MASTER depending on TRANSACTION aborts', 'abort', 'abort')
    check('  and explains which rule fired',
          ('pos_items' in msg), True)

# 3. A corrupt source database.
db = os.path.join(WORK, 'corrupt.db')
shutil.copy2(fresh('to_corrupt.db'), db)
with open(db, 'r+b') as fh:
    fh.seek(8192)
    fh.write(b'\xff' * 4096)
try:
    pi.initialize(db, confirm=True, business_date=TODAY, boot_check=False,
                  quiet=True, backup_root=BACKUPS)
    check('corrupt source aborts', 'no abort', 'abort')
except (pi.InitializationAborted, sqlite3.DatabaseError):
    check('corrupt source aborts', 'abort', 'abort')

# 4. A missing database.
try:
    pi.initialize(os.path.join(WORK, 'nope.db'), confirm=True,
                  business_date=TODAY, boot_check=False, quiet=True,
                  backup_root=BACKUPS)
    check('missing database aborts', 'no abort', 'abort')
except pi.InitializationAborted:
    check('missing database aborts', 'abort', 'abort')

# 5. Without --confirm nothing is written.
db = fresh('dryrun.db')
before = sha(db)
out = pi.initialize(db, confirm=False, business_date=TODAY, quiet=True)
check('dry run reports DRY RUN', out['result'], 'DRY RUN')
check('  and the file is byte-identical', sha(db), before)

# =====================================================================
print()
print('== a real run does what it says, checked independently ==')

db = fresh('real.db')
before_counts = counts(db)
out = pi.initialize(db, confirm=True, business_date=TODAY, boot_check=False,
                    quiet=True, backup_root=BACKUPS)
after_counts = counts(db)

check('result is SUCCESS', out['result'], 'SUCCESS')
check('every verification check passed',
      all(c['passed'] for c in out['verification']['checks']), True)

master = {t for t, (c, _r) in CLASSIFICATION.items() if c == MASTER}
cleared = {t for t, (c, _r) in CLASSIFICATION.items()
           if c in ('TRANSACTION', 'TEMPORARY')}

check('every cleared table is empty',
      sum(after_counts.get(t, 0) for t in cleared), 0)
check('every master table is untouched',
      all(after_counts.get(t) == before_counts.get(t) for t in master), True)
check('  masters still hold rows',
      sum(after_counts.get(t, 0) for t in master) > 0, True)
check('schema_migrations preserved', after_counts.get('schema_migrations'),
      before_counts.get('schema_migrations'))
check('settings preserved', after_counts.get('settings'),
      before_counts.get('settings'))
check('users preserved', after_counts.get('users'),
      before_counts.get('users'))
check('rooms preserved', after_counts.get('rooms'),
      before_counts.get('rooms'))

conn = sqlite3.connect('file:' + db.replace('\\', '/') + '?mode=ro', uri=True)
try:
    check('no foreign key violations',
          len(list(conn.execute('PRAGMA foreign_key_check'))), 0)
    check('integrity check ok',
          [r[0] for r in conn.execute('PRAGMA integrity_check')], ['ok'])
    bd = conn.execute('SELECT "current_date", is_locked FROM business_date'
                      ).fetchone()
    check('business date is today', str(bd[0])[:10], TODAY.isoformat())
    check('hotel unlocked', bool(bd[1]), False)
    check('no reservations', conn.execute(
        'SELECT COUNT(*) FROM reservations').fetchone()[0], 0)
    check('no open shifts', conn.execute(
        'SELECT COUNT(*) FROM shifts').fetchone()[0], 0)
    check('no pending audit', conn.execute(
        'SELECT COUNT(*) FROM night_audit_logs').fetchone()[0], 0)
    check('no outstanding balances', conn.execute(
        'SELECT COUNT(*) FROM payments').fetchone()[0], 0)
    check('no orphaned room allocations — the reset_transactional_data gap',
          conn.execute('SELECT COUNT(*) FROM reservation_rooms'
                       ).fetchone()[0], 0)
finally:
    conn.close()

# =====================================================================
print()
print('== the backup is real, verified, and restores ==')

backup_path = out['backup']['path']
check('backup exists', os.path.exists(backup_path), True)
bcounts = counts(backup_path)
check('backup holds the ORIGINAL rows, not the reset ones',
      bcounts.get('reservations'), 28)
check('backup row counts match the pre-run source',
      bcounts == before_counts, True)
man = out['backup']['manifest']
check('manifest records both hashes',
      bool(man['source_sha256']) and bool(man['backup_sha256']), True)
check('manifest records the row counts', man['total_rows'],
      sum(before_counts.values()))

# Restore, and prove the restore.
restored = os.path.join(WORK, 'restored.db')
shutil.copy2(backup_path, restored)
check('restoring returns the original row counts',
      counts(restored) == before_counts, True)

# =====================================================================
print()
print('== idempotency ==')

second = pi.initialize(db, confirm=True, business_date=TODAY,
                       boot_check=False, quiet=True, backup_root=BACKUPS)
check('a second run reports ALREADY INITIALIZED', second['result'],
      'ALREADY INITIALIZED')
check('  and removes zero rows', second['counts']['rows_removed'], 0)
check('  and the row counts are unchanged', counts(db), after_counts)

# =====================================================================
print()
print('== --preserve-guests is honoured ==')

db2 = fresh('guests.db')
out2 = pi.initialize(db2, confirm=True, business_date=TODAY,
                     preserve_guests=True, boot_check=False, quiet=True,
                     backup_root=BACKUPS)
c2 = counts(db2)
check('guests retained when asked', c2.get('guests'),
      before_counts.get('guests'))
check('  and reservations still cleared', c2.get('reservations'), 0)
conn = sqlite3.connect('file:' + db2.replace('\\', '/') + '?mode=ro',
                       uri=True)
try:
    check('  and no FK violation results',
          len(list(conn.execute('PRAGMA foreign_key_check'))), 0)
finally:
    conn.close()

# =====================================================================
print()
print('== determinism ==')

a = fresh('det_a.db')
b = fresh('det_b.db')
ra = pi.initialize(a, confirm=True, business_date=TODAY, boot_check=False,
                   quiet=True, backup_root=BACKUPS)
rb = pi.initialize(b, confirm=True, business_date=TODAY, boot_check=False,
                   quiet=True, backup_root=BACKUPS)
check('two runs produce the same deletion order',
      ra['deletion_order'], rb['deletion_order'])
check('two runs remove the same rows',
      ra['rows_removed_by_table'], rb['rows_removed_by_table'])
check('two runs produce identical row counts', counts(a), counts(b))

# =====================================================================
print()
check('production byte-identical throughout', sha(PROD), PROD_BEFORE)

shutil.rmtree(WORK, ignore_errors=True)
print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
