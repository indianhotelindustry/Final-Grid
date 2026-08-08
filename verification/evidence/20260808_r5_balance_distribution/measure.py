"""Measure the settlement-balance distribution, for the R-5 proposal.

Uses the framework's own copy-and-build path (``dbcopy.make_copy`` plus
``runner._build_app``) rather than hand-rolling one, so the read-only
guarantee is the same one every other layer relies on.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.getcwd())

from verification.config import PRODUCTION_DB              # noqa: E402
from verification.dbcopy import make_copy, production_fingerprint  # noqa: E402
from verification import runner                            # noqa: E402

before, _size = production_fingerprint(PRODUCTION_DB)

handle = make_copy(name='r5_balances.db', source=PRODUCTION_DB)
app = runner._build_app(handle)

with app.app_context():
    from app.models import Reservation
    from app.services import calculate_stay_amount
    rows = [(r.id, Decimal(str(calculate_stay_amount(r)['settlement_balance'])))
            for r in Reservation.query.order_by(Reservation.id).all()]

THRESHOLD = Decimal('-1.00')
credit = [(i, b) for i, b in rows if b < 0]
material = [x for x in credit if x[1] < THRESHOLD]
immaterial = [x for x in credit if THRESHOLD <= x[1] < 0]
owed = [(i, b) for i, b in rows if b > 0]


def total(items):
    return sum((b for _i, b in items), Decimal('0'))


print('reservations                                  : %d' % len(rows))
print('settled exactly (balance 0.00)                : %d'
      % len([1 for _i, b in rows if b == 0]))
print('owing money                                   : %d, totalling %s'
      % (len(owed), total(owed)))
print('in credit at all                              : %d, totalling %s'
      % (len(credit), total(credit)))
print('  overpaid by MORE than 1.00 (INV-A06 pop.)   : %d, totalling %s'
      % (len(material), total(material)))
print('  overpaid by 0.01 to 1.00 (unmeasured band)  : %d, totalling %s'
      % (len(immaterial), total(immaterial)))
print()
print('every reservation in credit:')
for i, b in credit:
    band = 'MEASURED' if b < THRESHOLD else 'unmeasured'
    print('   reservation %-3d %8s   %s' % (i, b, band))
print()
print('reservations owing money:')
for i, b in owed:
    print('   reservation %-3d %8s' % (i, b))

after, _size = production_fingerprint(PRODUCTION_DB)
print()
print('production byte-identical                     :', before == after)
