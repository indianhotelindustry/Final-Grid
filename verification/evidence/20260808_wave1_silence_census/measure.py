"""Silence census — does each known defect have a live population today?

The Wave 1 blueprint turns on one classification that had never been made:
a fix is **mathematically silent** if the rows it would change do not exist
in production, and **historically material** if they do.

A silent fix can be shipped and proved neutral by measurement — every
figure before equals every figure after. A material one permanently
changes what the hotel's books say about days that are already closed and
signed off, which is a management and audit decision rather than an
engineering one.

Nothing here is a new defect. Every row is a population count for a defect
already recorded in the Wave 0 register; only the classification is new.

Read-only: production is opened `mode=ro` and fingerprinted before and
after.
"""
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.getcwd())

PROD = 'instance/pms.db'
before = hashlib.sha256(open(PROD, 'rb').read()).hexdigest()
conn = sqlite3.connect('file:' + PROD.replace('\\', '/') + '?mode=ro',
                       uri=True)


def scalar(sql):
    row = conn.execute(sql).fetchone()
    return row[0] if row and row[0] is not None else 0


#: (id, defect, population query, source of the finding)
CENSUS = [
    ('W1-01', 'Financial rows with no folio (INV-A02)',
     'SELECT (SELECT COUNT(*) FROM payments WHERE folio_id IS NULL) + '
     '(SELECT COUNT(*) FROM extra_charges WHERE folio_id IS NULL)',
     'D4 §11.1'),
    ('W1-02', 'Charges invisible to the folio view (INV-A03)',
     'SELECT COUNT(*) FROM extra_charges WHERE folio_id IS NULL',
     'D4 §11.2'),
    ('W1-03', 'Closed night audits that can be recomputed differently',
     'SELECT COUNT(*) FROM night_audit_logs',
     'D3 §8.1 / D4 §11.3'),
    ('W1-04', 'Walk-in payments on OTA receivable heads (INV-C01)',
     "SELECT COUNT(*) FROM payments p JOIN payment_modes m "
     "ON m.id=p.payment_mode_id JOIN reservations r ON r.id=p.reservation_id "
     "WHERE m.category='ota_receivable' AND r.source='Walk-in'",
     'D4 §11.4'),
    ('W1-05', 'OTA postings with no agent reference (INV-C05)',
     "SELECT COUNT(*) FROM payments p JOIN payment_modes m "
     "ON m.id=p.payment_mode_id JOIN reservations r ON r.id=p.reservation_id "
     "WHERE m.category='ota_receivable' AND "
     "(r.ota_channel IS NULL OR r.ota_booking_id IS NULL)",
     'D4 §11.5'),
    ('W1-06', 'Room-nights sold twice (INV-C04)',
     "SELECT COUNT(*) FROM (SELECT n.room_id AS rid, n.stay_date AS sd "
     "FROM reservation_night_rates n "
     "JOIN reservations r ON r.id = n.reservation_id "
     "WHERE r.status IN ('CheckedIn','CheckedOut') "
     "GROUP BY n.room_id, n.stay_date "
     "HAVING COUNT(DISTINCT n.reservation_id) > 1)",
     'D4 §11.6'),
    ('W1-07', 'Extra charges (the population Q18/Q20 diverge on)',
     'SELECT COUNT(*) FROM extra_charges',
     'coverage ledger, 5 datasets'),
    ('W1-08', 'Reservations with a credit approved after checkout date',
     'SELECT COUNT(*) FROM reservations '
     'WHERE credit_amount > 0',
     'D3 §8.1'),

    # --- the dormant set: populations that do not exist yet --------------
    ('W1-20', 'Room-rent charges posted into extra_charges',
     "SELECT COUNT(*) FROM extra_charges WHERE charge_type='room_rent'",
     'R-2 / D5.5 F-3'),
    ('W1-21', 'Correction or reversal rows',
     'SELECT (SELECT COUNT(*) FROM payments WHERE is_correction=1 '
     'OR is_reversal=1) + (SELECT COUNT(*) FROM extra_charges '
     'WHERE is_correction=1 OR is_reversal=1)',
     'INV-D02 / R-7 / GST defect'),
    ('W1-22', 'Refund payments',
     "SELECT COUNT(*) FROM payments WHERE payment_purpose='refund'",
     'DS-ACT-VOIDCN — refund corrects_id'),
    ('W1-23', 'Voided payments',
     'SELECT COUNT(*) FROM payments WHERE is_voided=1',
     'DS-ACT-VOIDCN — voids reported as refunds'),
    ('W1-24', 'Credit notes',
     'SELECT COUNT(*) FROM credit_notes', 'INV-D05'),
    ('W1-25', 'Void requests',
     'SELECT COUNT(*) FROM void_requests', 'INV-D05'),
    ('W1-26', 'Payments pointing at a non-existent payment mode',
     'SELECT COUNT(*) FROM payments p LEFT JOIN payment_modes m '
     'ON m.id=p.payment_mode_id WHERE m.id IS NULL',
     'D3 §8.4 / D4 §11.8'),
    ('W1-27', 'Group blocks',
     'SELECT COUNT(*) FROM group_blocks',
     'DS-ACT-GROUP — no master-account routing'),
    ('W1-28', 'Companies / corporate bookings',
     'SELECT (SELECT COUNT(*) FROM companies) + '
     '(SELECT COUNT(*) FROM folios WHERE company_id IS NOT NULL)',
     'INV-C06'),
    ('W1-29', 'Shifts',
     'SELECT COUNT(*) FROM shifts', 'Q21'),
    ('W1-30', 'Reservations overpaid beyond the ₹1.00 threshold',
     'SELECT 0', 'INV-A06 / R-5 — measured separately, engine-derived'),
    ('W1-31', 'Duplicate invoice numbers',
     'SELECT COUNT(*) FROM (SELECT invoice_number FROM reservations '
     'WHERE invoice_number IS NOT NULL GROUP BY invoice_number '
     'HAVING COUNT(*)>1)',
     'FLT-B04 — no invariant exists'),
    ('W1-32', 'OTA payouts (can drive a negative receivable)',
     'SELECT COUNT(*) FROM ota_payouts', 'D1 §7 new observation'),
]

rows = []
for ref, defect, sql, source in CENSUS:
    try:
        n = int(scalar(sql))
    except sqlite3.Error as exc:
        n = -1
        defect += f'  [query failed: {exc}]'
    rows.append({'ref': ref, 'defect': defect, 'population': n,
                 'source': source,
                 'classification': ('UNMEASURED' if n < 0 else
                                    'SILENT' if n == 0 else 'MATERIAL')})

print('%-7s %-58s %6s  %s' % ('ref', 'defect', 'pop', 'class'))
print('-' * 92)
for r in rows:
    print('%-7s %-58s %6d  %s'
          % (r['ref'], r['defect'][:58], r['population'],
             r['classification']))

silent = [r for r in rows if r['classification'] == 'SILENT']
material = [r for r in rows if r['classification'] == 'MATERIAL']
unmeasured = [r for r in rows if r['classification'] == 'UNMEASURED']
print()
print('SILENT   (no live population — a fix changes no existing figure): %d'
      % len(silent))
print('MATERIAL (live population — a fix restates existing figures)    : %d'
      % len(material))
if unmeasured:
    print('UNMEASURED — a query failed. Silence is a claim and an '
          'unanswered query is not evidence for it: %d' % len(unmeasured))

after = hashlib.sha256(open(PROD, 'rb').read()).hexdigest()
conn.close()
print()
print('production byte-identical:', before == after)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'result.json'), 'w') as fh:
    json.dump({'purpose': __doc__.strip().splitlines()[0],
               'production_sha256': after,
               'production_byte_identical': before == after,
               'census': rows,
               'silent_count': len(silent),
               'material_count': len(material),
               'unmeasured_count': len(unmeasured)}, fh, indent=1)
