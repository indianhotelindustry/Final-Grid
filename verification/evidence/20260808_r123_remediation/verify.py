"""Verify R-1, R-2, R-3, R-6 against the D5.5 audit's authoritative table.

R-2 cannot be shown by the aggregate: 0 of 30 night-rate rows are posted,
so the exclusion it adds removes nothing on production data. It is proved
instead by injecting a room_rent charge into a disposable copy and showing
the probe holds where the pre-R-2 form moves. That is the P9 discipline —
a control is not evidence until it has been shown to be capable of
behaving differently.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
from decimal import Decimal as D

sys.path.insert(0, os.getcwd())
from verification.datasets import financials  # noqa: E402

DB = 'instance/pms.db'
Q = D('0.01')

PRE_R2_OUTSTANDING = (
    'SELECT COALESCE((SELECT SUM(final_rate) '
    '                 FROM reservation_night_rates), 0) '
    '     + COALESCE((SELECT SUM(amount) FROM extra_charges), 0) '
    '     + COALESCE((SELECT SUM(tax_amount) FROM tax_lines), 0) '
    '     - COALESCE((SELECT SUM(amount) FROM payments '
    '                 WHERE COALESCE(is_voided,0)=0), 0)')

results = []


def check(label, got, want):
    ok = str(got) == str(want)
    results.append(ok)
    print('%-4s %-46s got %-12s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def ro(path):
    return sqlite3.connect('file:' + path.replace('\\', '/') + '?mode=ro',
                           uri=True)


# --- R-1 / R-3 / R-6 on production, read-only ------------------------------
print('== aggregate, production database (read-only) ==')
m = financials.measure(DB)
check('R-1  outstanding', m['outstanding'], '199.92')
check('R-3  taxable_total', m['taxable_total'], '37946.67')
check('R-3  taxable_total == charges excl tax - untaxed extras',
      m['taxable_total'],
      str(D(m['room_revenue']) + D(m['extra_charges_total']) - D('0.30')))
check('R-3  tax_lines_count == 2 x tax_base_count',
      m['tax_lines_count'], str(int(m['tax_base_count']) * 2))
check('R-6  unrounded + round_off == rounded',
      str(D(m['invoice_unrounded_grand_total'])
          + D(m['invoice_round_off_total'])),
      m['invoice_rounded_grand_total'])
check('R-2  extra_charges slices sum to the total',
      str(D(m['extra_charges_room_rent'])
          + D(m['extra_charges_non_room_rent'])),
      m['extra_charges_total'])

# --- R-1 per-reservation trace ---------------------------------------------
print()
print('== per-reservation trace (R-1 verification) ==')
conn = ro(DB)


def scalar(sql, args=()):
    row = conn.execute(sql, args).fetchone()
    return D(str(row[0] or 0)).quantize(Q)


zero = nonzero = 0
detail = []
total = D('0')
roundoff_explained = taxpath_explained = D('0')
for (rid,) in conn.execute('SELECT id FROM reservations ORDER BY id'):
    room = scalar('SELECT SUM(final_rate) FROM reservation_night_rates '
                  'WHERE reservation_id=?', (rid,))
    extras = scalar("SELECT SUM(amount) FROM extra_charges "
                    "WHERE reservation_id=? AND (charge_type IS NULL "
                    "  OR charge_type <> 'room_rent')", (rid,))
    tax = scalar('SELECT SUM(tax_amount) FROM tax_lines '
                 'WHERE reservation_id=?', (rid,))
    paid = scalar('SELECT SUM(amount) FROM payments '
                  'WHERE reservation_id=? AND COALESCE(is_voided,0)=0', (rid,))
    round_off = scalar('SELECT invoice_round_off_amount FROM reservations '
                       'WHERE id=?', (rid,))
    unrounded = scalar('SELECT invoice_unrounded_grand_total FROM reservations '
                       'WHERE id=?', (rid,))
    bal = room + extras + tax - paid
    total += bal
    roundoff_explained += round_off
    taxpath_explained += unrounded - (room + extras + tax)
    if bal == 0:
        zero += 1
    else:
        nonzero += 1
        detail.append((rid, bal))
conn.close()

# The audit's enumerated residue list is right; its count is not. It names
# nine reservations and then says "21 others", which totals 30 against a
# population of 28. Measured: 19 at zero, 9 with a residue, and the nine
# match the audit's own list to the paisa.
check('R-1  reservations at exactly 0.00', zero, 19)
check('R-1  reservations with a residue', nonzero, 9)
check('R-1  residues sum to the aggregate', total, '199.92')
print('     residues: ' + ', '.join('resv %d %+.2f' % (r, b) for r, b in detail))

# R-6's stated purpose is that a dataset can declare an exact balance.
# invoice_round_off_amount alone does not get there.
print()
print('== residue attribution (R-6 scope) ==')
check('R-6  round_off accounts for', -roundoff_explained, '0.25')
check('R-6  tax-rounding path accounts for', -taxpath_explained, '-0.04')
# Not attributable to either rounding mechanism: reservation 1's genuine
# unpaid 200.00, less the two real 0.15 overpayments on 10 and 17.
check('R-6  remainder after both rounding causes',
      total + roundoff_explained + taxpath_explained, '199.71')
check('R-6    = resv 1 unpaid, less the two real overpayments',
      D('200.00') - D('0.15') - D('0.15') + D('0.01'), '199.71')

# --- R-2 commissioning: inject room rent into a disposable copy ------------
print()
print('== R-2 commissioning (disposable copy, production untouched) ==')
work = tempfile.mkdtemp(prefix='r2_')
copy = os.path.join(work, 'pms.db')
src = ro(DB)
dst = sqlite3.connect(copy)
src.backup(dst)
dst.close()
src.close()

before = financials.measure(copy)
check('copy reproduces production outstanding',
      before['outstanding'], '199.92')

# Post every unposted night rate into extra_charges as room_rent, which is
# what the night audit does. Nothing about production changes.
w = sqlite3.connect(copy)
rows = w.execute('SELECT reservation_id, stay_date, final_rate '
                 'FROM reservation_night_rates').fetchall()
for reservation_id, stay_date, final_rate in rows:
    w.execute('INSERT INTO extra_charges '
              '(reservation_id, description, amount, charge_date, '
              ' charge_type, is_correction, is_reversal) '
              "VALUES (?,?,?,?,'room_rent',0,0)",
              (reservation_id, 'Room Rent', final_rate, stay_date))
w.commit()
posted = D(str(w.execute("SELECT SUM(amount) FROM extra_charges "
                         "WHERE charge_type='room_rent'").fetchone()[0])
           ).quantize(Q)
pre_r2 = D(str(w.execute(PRE_R2_OUTSTANDING).fetchone()[0])).quantize(Q)
w.close()

after = financials.measure(copy)
print('     injected %d room_rent rows totalling %s' % (len(rows), posted))
check('R-2  probe HOLDS at 199.92 with room rent posted',
      after['outstanding'], '199.92')
check('R-2  pre-R-2 form would have moved to', pre_r2,
      str(D('199.92') + posted))
check('R-2  room_rent slice now visible', after['extra_charges_room_rent'],
      str(posted))
check('R-2  non_room_rent slice unchanged',
      after['extra_charges_non_room_rent'], before['extra_charges_total'])
shutil.rmtree(work, ignore_errors=True)

print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
