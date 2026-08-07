"""
The financial probes — charter element 3.

A dataset declares what the money should come to. This module is how that
declaration is measured, and the design decision in it is which side of
the system does the measuring.

The books, not the application
------------------------------
Every probe here is plain SQL against the primary record. Not one goes
through a canonical engine, an ORM model or a report. That is deliberate
and it is the same reasoning D3 applies to its LEDGER account: a dataset
that declared "collections are Rs 12,000" and then asked the application
what collections were would agree with itself no matter how wrong the
application had become. The declaration must be checkable against the
rows, or it checks nothing.

The other direction — does the application agree with the books? — is
already covered, twice. D1 compares implementations against each other
and D3 reconciles the engine against the ledger. Those layers run against
the dataset too, and their expectations are declared separately. Keeping
the financial declaration on the SQL side means the two questions stay
independent instead of collapsing into one.

Money as strings
----------------
Every probe returns a string of a ``Decimal`` quantised to two places.
Floats are never used, never compared and never stored: a declaration of
``'12000.00'`` must mean exactly twelve thousand rupees, and
``0.1 + 0.2`` is the reason financial systems have a rule about this.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation

TWO_PLACES = Decimal('0.01')


def money(value) -> str:
    """Normalise any numeric to a two-place decimal string."""
    if value is None:
        value = 0
    try:
        return str(Decimal(str(value)).quantize(TWO_PLACES))
    except (InvalidOperation, ValueError):
        return str(Decimal('0').quantize(TWO_PLACES))


def _scalar(conn: sqlite3.Connection, query: str) -> str:
    try:
        row = conn.execute(query).fetchone()
    except sqlite3.Error:
        return money(0)
    return money(row[0] if row and row[0] is not None else 0)


def _count(conn: sqlite3.Connection, query: str) -> str:
    try:
        row = conn.execute(query).fetchone()
    except sqlite3.Error:
        return '0'
    return str(int(row[0] or 0))


#: probe name -> (kind, SQL). ``kind`` is 'money' or 'count'; the two are
#: formatted differently because "3 reservations" quantised to two places
#: reads as a currency amount and invites exactly the wrong reading.
PROBES = {
    # -- populations ------------------------------------------------------
    'reservations_count': ('count', 'SELECT COUNT(*) FROM reservations'),
    'guests_count': ('count', 'SELECT COUNT(*) FROM guests'),
    'folios_count': ('count', 'SELECT COUNT(*) FROM folios'),
    'payments_count': ('count', 'SELECT COUNT(*) FROM payments'),

    # -- collections ------------------------------------------------------
    'payments_gross': ('money',
                       'SELECT SUM(amount) FROM payments'),
    'payments_voided': ('money',
                        'SELECT SUM(amount) FROM payments WHERE is_voided=1'),
    'payments_net': ('money',
                     'SELECT SUM(amount) FROM payments '
                     'WHERE COALESCE(is_voided,0)=0'),
    'payments_corrections': ('money',
                             'SELECT SUM(amount) FROM payments '
                             'WHERE COALESCE(is_correction,0)=1'),
    'payments_reversals': ('money',
                           'SELECT SUM(amount) FROM payments '
                           'WHERE COALESCE(is_reversal,0)=1'),

    # -- charges ----------------------------------------------------------
    'extra_charges_total': ('money',
                            'SELECT SUM(amount) FROM extra_charges'),
    'extra_charges_reversals': ('money',
                                'SELECT SUM(amount) FROM extra_charges '
                                'WHERE COALESCE(is_reversal,0)=1'),
    'room_revenue': ('money',
                     'SELECT SUM(final_rate) FROM reservation_night_rates'),
    'room_discount': ('money',
                      'SELECT SUM(discount_amount) '
                      'FROM reservation_night_rates'),

    # -- tax --------------------------------------------------------------
    'tax_total': ('money', 'SELECT SUM(tax_amount) FROM tax_lines'),
    'taxable_total': ('money', 'SELECT SUM(taxable_amount) FROM tax_lines'),

    # -- adjustments — the populations D4 found VACUOUS -------------------
    'overpayment_total': ('money',
                          'SELECT SUM(overpaid_amount) FROM overpayment_logs'),
    'overpayment_count': ('count', 'SELECT COUNT(*) FROM overpayment_logs'),
    'credit_note_total': ('money',
                          'SELECT SUM(total_amount) FROM credit_notes'),
    'credit_note_count': ('count', 'SELECT COUNT(*) FROM credit_notes'),
    'void_request_count': ('count', 'SELECT COUNT(*) FROM void_requests'),
    'corporate_credit_used': ('money',
                              'SELECT SUM(credit_used) FROM companies'),
    'corporate_bookings': ('count',
                           'SELECT COUNT(*) FROM folios '
                           'WHERE company_id IS NOT NULL'),

    # -- the balance ------------------------------------------------------
    #: Charges the hotel raised, less what it collected. The single figure
    #: a manager would recognise, and the one most likely to move when
    #: anything at all is wrong.
    'outstanding': ('money',
                    'SELECT COALESCE((SELECT SUM(final_rate) '
                    '                 FROM reservation_night_rates), 0) '
                    '     + COALESCE((SELECT SUM(amount) '
                    '                 FROM extra_charges), 0) '
                    '     - COALESCE((SELECT SUM(amount) FROM payments '
                    '                 WHERE COALESCE(is_voided,0)=0), 0)'),
}


def measure(db_path: str, names: tuple = ()) -> dict:
    """Measure the named probes (or all of them) against a dataset."""
    conn = sqlite3.connect('file:' + db_path.replace('\\', '/') + '?mode=ro',
                           uri=True)
    try:
        wanted = names or tuple(PROBES)
        out = {}
        for name in wanted:
            if name not in PROBES:
                continue
            kind, query = PROBES[name]
            out[name] = (_count(conn, query) if kind == 'count'
                         else _scalar(conn, query))
        return out
    finally:
        conn.close()


def unknown_probes(names) -> list:
    return sorted(n for n in names if n not in PROBES)
