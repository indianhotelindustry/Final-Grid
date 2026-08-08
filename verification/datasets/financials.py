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

# ---------------------------------------------------------------------------
# Signing corrections and reversals — R-7
# ---------------------------------------------------------------------------
#
# ``payments`` carries ``CHECK amount > 0`` and ``extra_charges`` carries
# ``CHECK amount >= 0``, so a reversal cannot be stored as a negative
# number. The application's answer, documented on both models and
# implemented in ``services.signed_extra_charge_amount``, is to store the
# reversal POSITIVE and require every caller to flip the sign:
#
#     REVERSAL     is_correction=1, is_reversal=1, amount = the original
#     REPLACEMENT  is_correction=1, is_reversal=0, amount = the corrected
#
# A probe that sums ``amount`` unsigned therefore ADDS the reversed money
# where the business meaning is to remove it, and is wrong by twice the
# reversed amount on every correction.
#
# Measured before the fix, injecting one 500.00 charge correction and one
# 1,000.00 payment correction into a copy of production:
#
#     extra_charges_total   1,929.85 against a truth of   929.85
#     payments_net         42,244.29 against a truth of 40,244.29
#     outstanding          -1,200.08 against a truth of  -200.08
#
# Production has zero correction rows, so this has never shown up — the
# same way R-2's double count was invisible while zero night rates were
# posted. ``DS-ACT-CORRECTION`` is the first thing that will produce this
# shape, which is exactly why the probes had to be fixed before it declared
# anything against them.
SIGNED_AMOUNT = ('SUM(CASE WHEN COALESCE(is_reversal,0)=1 '
                 'THEN -amount ELSE amount END)')
SIGNED_PAYMENTS = f'SELECT {SIGNED_AMOUNT} FROM payments'
SIGNED_CHARGES = f'SELECT {SIGNED_AMOUNT} FROM extra_charges'
NOT_ROOM_RENT = "charge_type IS NULL OR charge_type <> 'room_rent'"


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
    #: Net of voids AND of reversals. A reversal row carries the ORIGINAL
    #: amount as a POSITIVE number — the ``CHECK amount > 0`` constraint
    #: forbids anything else — and the application's rule is that "callers
    #: that compute paid totals must SUBTRACT this row's amount"
    #: (``services.post_payment_correction``). Summing it unsigned counts
    #: the reversed money twice: once as collected and once as collected
    #: again, when it should net to nothing.
    'payments_net': ('money', SIGNED_PAYMENTS +
                     ' WHERE COALESCE(is_voided,0)=0'),
    'payments_corrections': ('money',
                             'SELECT SUM(amount) FROM payments '
                             'WHERE COALESCE(is_correction,0)=1'),
    'payments_reversals': ('money',
                           'SELECT SUM(amount) FROM payments '
                           'WHERE COALESCE(is_reversal,0)=1'),

    # -- charges ----------------------------------------------------------
    'extra_charges_total': ('money',
                            'SELECT SUM(amount) FROM extra_charges'),
    #: The two slices of ``extra_charges_total``, split on the exclusion
    #: ``outstanding`` applies. Recorded separately for the reason
    #: ``replay/ledger.py`` records them separately: a change to the
    #: exclusion is then visible rather than absorbed. Room rent posted by
    #: the night audit is excluded from the balance because room revenue is
    #: already counted from the reservation tariff.
    'extra_charges_room_rent': ('money',
                                'SELECT SUM(amount) FROM extra_charges '
                                "WHERE charge_type = 'room_rent'"),
    'extra_charges_non_room_rent': ('money',
                                    'SELECT SUM(amount) FROM extra_charges '
                                    'WHERE charge_type IS NULL '
                                    "   OR charge_type <> 'room_rent'"),
    'extra_charges_reversals': ('money',
                                'SELECT SUM(amount) FROM extra_charges '
                                'WHERE COALESCE(is_reversal,0)=1'),
    #: The signed figures. ``extra_charges_total`` above stays an unsigned
    #: gross on purpose — it answers "how much was raised", and a reversal
    #: pair really did raise both rows. These answer "what is owed", which
    #: is the question the balance is built from, and the two must not be
    #: collapsed into one probe that silently means whichever the reader
    #: assumed.
    'extra_charges_net': ('money', SIGNED_CHARGES),
    'extra_charges_non_room_rent_net': ('money',
                                        f'{SIGNED_CHARGES} '
                                        f'WHERE {NOT_ROOM_RENT}'),
    'room_revenue': ('money',
                     'SELECT SUM(final_rate) FROM reservation_night_rates'),
    'room_discount': ('money',
                      'SELECT SUM(discount_amount) '
                      'FROM reservation_night_rates'),

    # -- tax --------------------------------------------------------------
    #: ``tax_amount`` is summed plainly: Indian GST splits into CGST and
    #: SGST and each row carries its own half, so the rows add up.
    'tax_total': ('money', 'SELECT SUM(tax_amount) FROM tax_lines'),

    #: ``taxable_amount`` is the opposite. ``tax_lines`` holds one row per
    #: tax component and **every component repeats the full taxable base**,
    #: so summing the column counts each base once per component. The base
    #: is therefore taken once per charge.
    #:
    #: The grouping includes ``reservation_id``, which is not optional:
    #: ``charge_source_id`` is a label like ``night_2026-05-27`` and is
    #: unique only within a reservation. Grouping without it collapses the
    #: same stay-night across every reservation that has one — measured on
    #: the production database, 33 real bases collapse to 5.
    #:
    #: ``DISTINCT`` rather than ``MAX``: if two components ever disagreed
    #: about the base, this figure moves. A ``MAX`` would silently pick one
    #: and report a clean number over an inconsistency (P9 — a measurement
    #: that cannot move is not a measurement).
    'taxable_total': ('money',
                      'SELECT SUM(taxable_amount) FROM '
                      '(SELECT DISTINCT reservation_id, charge_source_type, '
                      '        charge_source_id, taxable_amount '
                      ' FROM tax_lines)'),
    'tax_lines_count': ('count', 'SELECT COUNT(*) FROM tax_lines'),
    #: One per taxed charge. ``tax_lines_count`` divided by this is the
    #: component count; if that ratio moves off 2 on a domestic dataset,
    #: the shape of the tax table has changed and ``taxable_total`` should
    #: be re-read before it is trusted.
    'tax_base_count': ('count',
                       'SELECT COUNT(*) FROM '
                       '(SELECT DISTINCT reservation_id, charge_source_type, '
                       '        charge_source_id FROM tax_lines)'),

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

    # -- the invoice ------------------------------------------------------
    #: What the guest was actually billed, as opposed to what the component
    #: rows add up to. The two are not the same figure and a dataset that
    #: wants to declare an exact per-reservation balance needs both.
    #:
    #: ``unrounded + round_off = rounded`` holds exactly, per reservation,
    #: on all 28 production rows. What does *not* hold is
    #: ``unrounded == room + extras + tax``: the invoice rounds tax over the
    #: whole bill while ``tax_lines`` rounds it per component, and the two
    #: paths differ by up to a paisa per reservation. Both slices are
    #: recorded so the difference is a measured quantity rather than an
    #: unexplained residue.
    'invoice_unrounded_grand_total': ('money',
                                      'SELECT SUM(invoice_unrounded_grand_total) '
                                      'FROM reservations'),
    'invoice_round_off_total': ('money',
                                'SELECT SUM(invoice_round_off_amount) '
                                'FROM reservations'),
    'invoice_rounded_grand_total': ('money',
                                    'SELECT SUM(invoice_rounded_grand_total) '
                                    'FROM reservations'),
    'invoice_round_off_rows': ('count',
                               'SELECT COUNT(*) FROM reservations '
                               'WHERE COALESCE(invoice_round_off_amount,0) <> 0'),

    # -- the balance ------------------------------------------------------
    #: Charges the hotel raised, less what it collected. The single figure
    #: a manager would recognise, and the one most likely to move when
    #: anything at all is wrong.
    #:
    #: Tax is part of the charge. Guests settle tax-inclusive totals, so a
    #: balance that omits tax subtracts money against a charge it never
    #: counted and reports the whole book as overpaid by exactly the tax.
    #:
    #: Room rent is counted once, from ``reservation_night_rates``. When the
    #: night audit posts it into ``extra_charges`` the same revenue appears
    #: in both tables, so the ``extra_charges`` term excludes it — the same
    #: exclusion ``kpi_helpers.get_accrual_extras`` and ``NightAuditService``
    #: apply, mirrored in ``replay/ledger.py``. On the current database
    #: ``0 of 30`` night-rate rows are posted and the exclusion removes
    #: nothing; it is here so that the first night audit to post room rent
    #: does not silently double the balance.
    #: Everything the hotel is owed, before anything it collected. Exposed
    #: as its own probe so the balance is decomposable: when `outstanding`
    #: moves, this says whether the charges or the collections moved.
    'charges_net': ('money',
                    'SELECT COALESCE((SELECT SUM(final_rate) '
                    '                 FROM reservation_night_rates), 0) '
                    f'     + COALESCE(({SIGNED_CHARGES} '
                    f'                 WHERE {NOT_ROOM_RENT}), 0) '
                    '     + COALESCE((SELECT SUM(tax_amount) '
                    '                 FROM tax_lines), 0)'),

    'outstanding': ('money',
                    'SELECT COALESCE((SELECT SUM(final_rate) '
                    '                 FROM reservation_night_rates), 0) '
                    f'     + COALESCE(({SIGNED_CHARGES} '
                    f'                 WHERE {NOT_ROOM_RENT}), 0) '
                    '     + COALESCE((SELECT SUM(tax_amount) '
                    '                 FROM tax_lines), 0) '
                    f'     - COALESCE(({SIGNED_PAYMENTS} '
                    '                 WHERE COALESCE(is_voided,0)=0), 0)'),

    # -- R-8: what is actually still collectable --------------------------
    #: ``outstanding`` less credit notes.
    #:
    #: ``outstanding`` answers "charges raised, less collections", and that
    #: is the right question for it: a charge that was raised WAS raised,
    #: and the folio says so. A credit note does not remove the charge —
    #: it is a separate instrument that writes off what will not be
    #: collected, which is why it lives in its own table rather than as a
    #: reversal row.
    #:
    #: The consequence, found by ``DS-ACT-VOIDCN``: after a credit note is
    #: issued, ``outstanding`` reports money the hotel has already agreed
    #: it will never see. On that dataset it reads 236.00 while the true
    #: receivable is 0.00.
    #:
    #: This is added as a SEPARATE quantity rather than folded into
    #: ``outstanding``, because the two answer different questions and a
    #: single probe meaning whichever the reader assumed is the defect R-7
    #: was careful to avoid. Note it was also not treated as blocking:
    #: unlike R-1, R-2, R-3 and R-7 this was a MISSING quantity rather
    #: than a WRONG one, so no baseline was ever declared against an error.
    'net_receivable': ('money',
                       'SELECT COALESCE((SELECT SUM(final_rate) '
                       '                 FROM reservation_night_rates), 0) '
                       f'     + COALESCE(({SIGNED_CHARGES} '
                       f'                 WHERE {NOT_ROOM_RENT}), 0) '
                       '     + COALESCE((SELECT SUM(tax_amount) '
                       '                 FROM tax_lines), 0) '
                       f'     - COALESCE(({SIGNED_PAYMENTS} '
                       '                 WHERE COALESCE(is_voided,0)=0), 0) '
                       '     - COALESCE((SELECT SUM(total_amount) '
                       '                 FROM credit_notes), 0)'),
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
