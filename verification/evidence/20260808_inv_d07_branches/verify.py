"""Exercise every branch of INV-D07.

The declared negative seed covers one branch: a log row against a
reservation that is not overpaid and carries no resolution. Three others
decide the rule's answer and none of them is reached by that seed, so on
the evidence so far they are assertions rather than demonstrations (P9).

  1. live       reservation still overpaid beyond the threshold -> no
                violation, whatever the resolution says
  2. resolved   not overpaid, but a resolution is recorded      -> no
                violation                     (production: 2 rows)
  3. unexplained not overpaid, resolution empty                 -> VIOLATION
                                              (the declared seed)
  4. orphan     reservation does not exist                      -> VIOLATION

Each case is built on its own disposable copy. Production is never opened
except read-only, and is fingerprinted before and after.
"""
import hashlib
import json
import os
import subprocess
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.getcwd())

PROD = 'instance/pms.db'
results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print('%-4s %-56s got %-9s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def fingerprint():
    return hashlib.sha256(open(PROD, 'rb').read()).hexdigest()


def copy_of_production(name):
    path = os.path.join(tempfile.mkdtemp(prefix='d07_'), name)
    src = sqlite3.connect('file:' + PROD.replace('\\', '/') + '?mode=ro',
                          uri=True)
    dst = sqlite3.connect(path)
    src.backup(dst)
    dst.close()
    src.close()
    return path


def evaluate(db_path):
    """Run INV-D07 against *db_path* through the framework's own probe."""
    proc = subprocess.run(
        [sys.executable, '-m', 'verification', '_inv_json',
         '--db', os.path.abspath(db_path)],
        cwd=os.getcwd(), capture_output=True, text=True,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if '---INV-JSON---' not in proc.stdout:
        raise RuntimeError('no result:\n' + proc.stdout[-800:]
                           + '\n' + proc.stderr[-800:])
    payload = json.loads(proc.stdout.split('---INV-JSON---', 1)[1].strip())
    entry = (payload.get('invariants') or {}).get('INV-D07') or {}
    return entry.get('status', ''), entry.get('population', 0), entry


before = fingerprint()

# -- branch 2, as production stands ---------------------------------------
# Evaluated on an untouched copy rather than on the live file: the probe
# opens the database through the application, and pointing that at
# production to prove a read-only property would be assuming the thing
# being demonstrated.
print('== branch 2: resolved (unmodified copy of production) ==')
status, population, entry = evaluate(copy_of_production('pristine.db'))
check('production status', status, 'HOLDS')
check('  population is the log table, not the overpaid set', population, 2)

# -- branch 1: a live overpayment ------------------------------------------
print()
print('== branch 1: reservation still overpaid, resolution empty ==')
db = copy_of_production('live.db')
conn = sqlite3.connect(db)
# Overpay reservation 1 heavily, and give it a log row with NO resolution.
# If the rule ignored the balance it would fire on the empty resolution.
conn.execute("INSERT INTO payments (reservation_id, folio_id, "
             "payment_mode_id, amount, payment_date, is_voided, "
             "is_correction, is_reversal, payment_purpose) "
             "SELECT 1, NULL, 1, 50000.00, '2026-05-27', 0, 0, 0, "
             "'settlement'")
conn.execute("INSERT INTO overpayment_logs (reservation_id, guest_id, "
             "overpaid_amount, reason, resolution, created_at) "
             "VALUES (1, 1, 50000.00, 'seeded', '', "
             "'2026-01-01 00:00:00.000000')")
conn.commit()
conn.close()
status, population, entry = evaluate(db)
check('a live overpayment does not violate', status, 'HOLDS')
check('  population grew by the seeded row', population, 3)
check('  and it is counted as still overpaid',
      ((entry.get('evidence') or {}).get('inputs') or {}).get('still_overpaid'), 1)

# -- branch 4: an orphan ----------------------------------------------------
print()
print('== branch 4: log row whose reservation does not exist ==')
db = copy_of_production('orphan.db')
conn = sqlite3.connect(db)
conn.execute("INSERT INTO overpayment_logs (reservation_id, guest_id, "
             "overpaid_amount, reason, resolution, created_at) "
             "VALUES (99999, NULL, 250.00, 'seeded', 'income', "
             "'2026-01-01 00:00:00.000000')")
conn.commit()
conn.close()
status, population, entry = evaluate(db)
check('an orphan violates', status, 'VIOLATED')
check('  even though it carries a resolution',
      ((entry.get('evidence') or {}).get('inputs') or {}).get('orphaned_reservation'), 1)

# -- branch 3: the declared seed, re-run here for completeness -------------
print()
print('== branch 3: not overpaid, resolution empty (the declared seed) ==')
db = copy_of_production('unexplained.db')
conn = sqlite3.connect(db)
conn.execute("INSERT INTO overpayment_logs (reservation_id, guest_id, "
             "overpaid_amount, reason, resolution, created_at) "
             "SELECT r.id, r.guest_id, 500.00, 'seeded', '', "
             "'2026-01-01 00:00:00.000000' "
             "FROM reservations r ORDER BY r.id LIMIT 1")
conn.commit()
conn.close()
status, population, entry = evaluate(db)
check('an unexplained record violates', status, 'VIOLATED')

# -- the threshold is the boundary it claims to be -------------------------
print()
print('== the materiality boundary ==')
for amount, expected in ((0.50, 'VIOLATED'), (2.00, 'HOLDS')):
    db = copy_of_production('edge_%s.db' % amount)
    conn = sqlite3.connect(db)
    # Overpay reservation 1 by exactly `amount`, log it with no resolution.
    conn.execute("INSERT INTO payments (reservation_id, folio_id, "
                 "payment_mode_id, amount, payment_date, is_voided, "
                 "is_correction, is_reversal, payment_purpose) "
                 "VALUES (1, NULL, 1, ?, '2026-05-27', 0, 0, 0, "
                 "'settlement')", (200.00 + amount,))
    conn.execute("INSERT INTO overpayment_logs (reservation_id, guest_id, "
                 "overpaid_amount, reason, resolution, created_at) "
                 "VALUES (1, 1, ?, 'seeded', '', "
                 "'2026-01-01 00:00:00.000000')", (amount,))
    conn.commit()
    conn.close()
    status, _pop, _e = evaluate(db)
    check('overpaid by %.2f (threshold 1.00)' % amount, status, expected)

after = fingerprint()
print()
check('production byte-identical throughout', before == after, True)
print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
