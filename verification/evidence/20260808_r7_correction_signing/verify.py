"""Commission R-7 — the probes must sign corrections and reversals.

Two things have to be true, and only together:

  NEUTRAL   on production, where no correction row exists, every probe
            reads exactly what it read before the change. Otherwise R-7
            has moved a figure nobody asked it to move.
  CORRECT   under an injected correction pair, the signed probes report
            the business truth and the pre-R-7 forms are shown to be
            wrong by twice the reversed amount.

The second half is the part that matters. A fix whose only evidence is
"nothing changed" is indistinguishable from no fix at all — the same
argument R-2 needed, and for the same reason: the population it corrects
is empty on production.
"""
import hashlib
import os
import sqlite3
import sys
import tempfile
from decimal import Decimal as D

sys.path.insert(0, os.getcwd())
from verification.datasets import financials                  # noqa: E402

PROD = 'instance/pms.db'
results = []

#: The probe definitions as they stood before R-7.
PRE_R7 = {
    'payments_net': 'SELECT SUM(amount) FROM payments '
                    'WHERE COALESCE(is_voided,0)=0',
    'outstanding': (
        'SELECT COALESCE((SELECT SUM(final_rate) '
        '                 FROM reservation_night_rates), 0) '
        '     + COALESCE((SELECT SUM(amount) FROM extra_charges '
        "                 WHERE charge_type IS NULL "
        "                    OR charge_type <> 'room_rent'), 0) "
        '     + COALESCE((SELECT SUM(tax_amount) FROM tax_lines), 0) '
        '     - COALESCE((SELECT SUM(amount) FROM payments '
        '                 WHERE COALESCE(is_voided,0)=0), 0)'),
}


def check(label, got, want):
    ok = str(got) == str(want)
    results.append(ok)
    print('%-4s %-52s got %-12s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def copy_production(name):
    path = os.path.join(tempfile.mkdtemp(prefix='r7_'), name)
    src = sqlite3.connect('file:' + PROD.replace('\\', '/') + '?mode=ro',
                          uri=True)
    dst = sqlite3.connect(path)
    src.backup(dst)
    dst.close()
    src.close()
    return path


def scalar(db_path, sql):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(sql).fetchone()
    finally:
        conn.close()
    return D(str(row[0] or 0)).quantize(D('0.01'))


before = hashlib.sha256(open(PROD, 'rb').read()).hexdigest()

# -- NEUTRAL --------------------------------------------------------------
print('== neutral on production: no correction rows exist ==')
live = financials.measure(PROD)
check('payments_net', live['payments_net'], '39644.29')
check('outstanding', live['outstanding'], '199.92')
check('extra_charges_net equals the gross', live['extra_charges_net'],
      live['extra_charges_total'])
check('charges_net', live['charges_net'], '39844.21')
check('charges_net - payments_net == outstanding',
      D(live['charges_net']) - D(live['payments_net']),
      D(live['outstanding']))
check('correction rows on production', live['payments_corrections'], '0.00')
check('reversal rows on production', live['payments_reversals'], '0.00')

# -- CORRECT --------------------------------------------------------------
print()
print('== correct under an injected correction pair ==')
db = copy_production('corrected.db')
conn = sqlite3.connect(db)
# A 500.00 charge raised in error, reversed, replaced with 200.00.
conn.execute(
    "INSERT INTO extra_charges (id, reservation_id, description, amount, "
    " charge_date, charge_type, is_correction, is_reversal, corrects_id, "
    " correction_reason) VALUES "
    " (901, 1, 'Laundry',           500.00, '2026-05-27', 'laundry', 0, 0, "
    "  NULL, NULL),"
    " (902, 1, 'Laundry reversal',  500.00, '2026-05-27', 'laundry', 1, 1, "
    "  901, 'wrong amount'),"
    " (903, 1, 'Laundry corrected', 200.00, '2026-05-27', 'laundry', 1, 0, "
    "  901, 'wrong amount')")
# A 1,000.00 payment taken in error, reversed, replaced with 600.00.
conn.execute(
    "INSERT INTO payments (id, reservation_id, folio_id, payment_mode_id, "
    " amount, payment_date, is_voided, is_correction, is_reversal, "
    " corrects_id, correction_reason, payment_purpose) VALUES "
    " (901, 1, 1, 1, 1000.00, '2026-05-27', 0, 0, 0, NULL, NULL, "
    "  'settlement'),"
    " (902, 1, 1, 1, 1000.00, '2026-05-27', 0, 1, 1, 901, 'wrong amount', "
    "  'settlement'),"
    " (903, 1, 1, 1,  600.00, '2026-05-27', 0, 1, 0, 901, 'wrong amount', "
    "  'settlement')")
conn.commit()
conn.close()

seeded = financials.measure(db)

# Truth: the reversal cancels the original, leaving the replacement.
want_charges_gross = D('729.85') + D('500.00') + D('500.00') + D('200.00')
want_charges_net = D('729.85') + D('200.00')
want_paid = D('39644.29') + D('600.00')
want_outstanding = D('199.92') + D('200.00') - D('600.00')

check('extra_charges_total stays an unsigned gross',
      seeded['extra_charges_total'], str(want_charges_gross))
check('extra_charges_net nets the reversal out',
      seeded['extra_charges_net'], str(want_charges_net))
check('payments_net nets the reversal out', seeded['payments_net'],
      str(want_paid))
check('outstanding', seeded['outstanding'], str(want_outstanding))
check('charges_net - payments_net == outstanding',
      D(seeded['charges_net']) - D(seeded['payments_net']),
      D(seeded['outstanding']))

# -- the pre-R-7 forms are shown to be wrong, not merely different --------
print()
print('== the pre-R-7 forms, on the same database ==')
old_paid = scalar(db, PRE_R7['payments_net'])
old_out = scalar(db, PRE_R7['outstanding'])
check('pre-R-7 payments_net overstates by 2x the reversal',
      old_paid - want_paid, D('2000.00'))
check('pre-R-7 outstanding is wrong by', old_out - want_outstanding,
      D('-1000.00'))
check('  and the probe now disagrees with it',
      D(seeded['payments_net']) != old_paid, True)

# -- descriptive probes still describe ------------------------------------
print()
print('== the unsigned slices remain available ==')
check('payments_reversals', seeded['payments_reversals'], '1000.00')
check('payments_corrections (reversal + replacement)',
      seeded['payments_corrections'], '1600.00')
check('extra_charges_reversals', seeded['extra_charges_reversals'], '500.00')

after = hashlib.sha256(open(PROD, 'rb').read()).hexdigest()
print()
check('production byte-identical throughout', before == after, True)
print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
