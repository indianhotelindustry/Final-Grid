"""
The LEDGER account — a reconstruction of a business date from the primary
record alone.

Why this exists
---------------
Every other account of a day's trading is produced by application code.
If that code changes, they all move together and agree with each other
just as convincingly as before. An account that is *independent of the
code under test* is the only thing that can tell you which of them moved.

So this module reads the transactional rows with plain ``sqlite3`` and
sums them in ``Decimal``. It contains no financial policy: it does not
decide what revenue is, which payments count as cash, or how tax should
be apportioned. It states what is in the books, sliced the few ways the
application's own filters slice it, so that an engine figure can be
compared against the aggregate it is *supposed* to equal.

Where a slice mirrors an application filter, the filter is named in the
docstring of the aggregate. That is deliberate: it makes the mirroring
reviewable. A reviewer can check that ``payments.direct.non_voided``
really is the same population as ``kpi_helpers.get_cash_revenue``, and if
the application's filter later changes, the declared reconciliation in
``reconcile.py`` fails and says so — which is the point.

Determinism
-----------
Amounts are summed as ``Decimal(str(value))`` rather than by SQL ``SUM``.
SQLite stores these NUMERIC columns as REAL, and ``SUM`` over REAL
accumulates in binary floating point, so the total depends on row order.
A ledger whose total changed when a row was inserted elsewhere would make
every comparison unstable, and the instability would look exactly like a
financial regression.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal


def _dec(value) -> Decimal:
    """Decimal from a database value. NULL is zero; anything non-numeric
    raises, because a silent zero would let a broken read look like a
    balanced book."""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _fmt(value: Decimal) -> str:
    """Canonical string form. Normalised so ``0E-8`` and ``0.00`` cannot
    both appear for the same figure and be read as a difference."""
    q = value.quantize(Decimal('0.000001'))
    text = format(q.normalize(), 'f')
    return '0' if text in ('-0', '0E+0', '') else text


class _Acc:
    """Accumulator that keeps figures and their populations together."""

    def __init__(self) -> None:
        self.figures: dict[str, str] = {}

    def money(self, path: str, value: Decimal) -> None:
        self.figures[path] = _fmt(value)

    def count(self, path: str, value: int) -> None:
        self.figures[path] = str(int(value))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------

def _payments(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Payment rows dated to *day*.

    Slices mirror the filters the application uses:

    ``direct``      ``PaymentMode.category = 'direct_payment'`` — the
                    population behind ``kpi_helpers.get_cash_revenue``.
    ``ota``         ``PaymentMode.category = 'ota_receivable'`` — the
                    population behind ``get_ota_receivable_posted``.
    ``non_voided``  ``Payment.is_voided = 0``, which every cash helper
                    applies.

    Both the voided and the gross figures are recorded even though no
    application helper uses them. A void that appears on a closed day is
    a movement in history whether or not any report shows it, and a
    ledger that only recorded what the reports look at could not detect
    a report that stopped looking.
    """
    if not _table_exists(conn, 'payments'):
        return
    rows = conn.execute(
        'SELECT p.amount, p.is_voided, p.is_correction, p.is_reversal, '
        '       p.payment_purpose, m.category AS mode_category, '
        '       m.name AS mode_name '
        'FROM payments p '
        'LEFT JOIN payment_modes m ON m.id = p.payment_mode_id '
        'WHERE p.payment_date = ? ORDER BY p.id', (day,)).fetchall()

    gross = Decimal('0')
    voided = Decimal('0')
    non_voided = Decimal('0')
    direct = Decimal('0')
    ota = Decimal('0')
    unmoded = Decimal('0')
    corrections = Decimal('0')
    reversals = Decimal('0')
    by_purpose: dict[str, Decimal] = {}
    by_mode: dict[str, Decimal] = {}
    n_voided = 0
    n_direct = 0
    n_ota = 0

    for r in rows:
        amount = _dec(r['amount'])
        gross += amount
        if r['is_voided']:
            voided += amount
            n_voided += 1
            continue
        non_voided += amount
        category = r['mode_category']
        if category == 'direct_payment':
            direct += amount
            n_direct += 1
        elif category == 'ota_receivable':
            ota += amount
            n_ota += 1
        else:
            # A payment whose mode has no category, or no mode at all,
            # is counted nowhere by the application's cash helpers. It is
            # recorded here so that money which falls between the two
            # filters is visible instead of vanishing.
            unmoded += amount
        if r['is_correction']:
            corrections += amount
        if r['is_reversal']:
            reversals += amount
        purpose = r['payment_purpose'] or 'UNSPECIFIED'
        by_purpose[purpose] = by_purpose.get(purpose, Decimal('0')) + amount
        mode = r['mode_name'] or 'NO_MODE'
        by_mode[mode] = by_mode.get(mode, Decimal('0')) + amount

    acc.count('payments.rows', len(rows))
    acc.money('payments.gross', gross)
    acc.money('payments.voided', voided)
    acc.count('payments.voided_rows', n_voided)
    acc.money('payments.non_voided', non_voided)
    acc.money('payments.direct.non_voided', direct)
    acc.count('payments.direct.rows', n_direct)
    acc.money('payments.ota.non_voided', ota)
    acc.count('payments.ota.rows', n_ota)
    acc.money('payments.uncategorised.non_voided', unmoded)
    acc.money('payments.corrections', corrections)
    acc.money('payments.reversals', reversals)
    for purpose in sorted(by_purpose):
        acc.money(f'payments.by_purpose.{purpose}', by_purpose[purpose])
    for mode in sorted(by_mode):
        acc.money(f'payments.by_mode.{mode}', by_mode[mode])


def _charges(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Extra-charge rows dated to *day*.

    ``non_room_rent`` mirrors the filter in
    ``kpi_helpers.get_accrual_extras`` and in ``NightAuditService``:
    ``charge_type IS NULL OR charge_type <> 'room_rent'``. Room rent
    posted by the night audit is excluded there because room revenue is
    accounted for from the reservation tariff instead; recording both
    slices here means a change to that exclusion is visible rather than
    absorbed.
    """
    if not _table_exists(conn, 'extra_charges'):
        return
    rows = conn.execute(
        'SELECT amount, charge_type, charge_category, is_correction, '
        '       is_reversal '
        'FROM extra_charges WHERE charge_date = ? ORDER BY id',
        (day,)).fetchall()

    gross = Decimal('0')
    room_rent = Decimal('0')
    non_room_rent = Decimal('0')
    corrections = Decimal('0')
    reversals = Decimal('0')
    by_category: dict[str, Decimal] = {}

    for r in rows:
        amount = _dec(r['amount'])
        gross += amount
        if (r['charge_type'] or '') == 'room_rent':
            room_rent += amount
        else:
            non_room_rent += amount
        if r['is_correction']:
            corrections += amount
        if r['is_reversal']:
            reversals += amount
        category = r['charge_category'] or r['charge_type'] or 'UNCLASSIFIED'
        by_category[category] = by_category.get(category, Decimal('0')) + amount

    acc.count('charges.rows', len(rows))
    acc.money('charges.gross', gross)
    acc.money('charges.room_rent', room_rent)
    acc.money('charges.non_room_rent', non_room_rent)
    acc.money('charges.corrections', corrections)
    acc.money('charges.reversals', reversals)
    for category in sorted(by_category):
        acc.money(f'charges.by_category.{category}', by_category[category])


def _tax(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Stored tax lines dated to *day*, by component.

    Taxable base is summed over DISTINCT charge sources as well as raw.
    A GST regime raises several component lines (CGST and SGST) against
    one taxable amount, so the raw sum of ``taxable_amount`` double
    counts; both are recorded because the application has historically
    used each of them in different places (Phase 2, P06).
    """
    if not _table_exists(conn, 'tax_lines'):
        return
    rows = conn.execute(
        'SELECT taxable_amount, tax_amount, tax_type, charge_source_type, '
        '       charge_source_id, is_exempted '
        'FROM tax_lines WHERE charge_date = ? ORDER BY id', (day,)).fetchall()

    total = Decimal('0')
    raw_base = Decimal('0')
    by_type: dict[str, Decimal] = {}
    distinct_base: dict[tuple, Decimal] = {}
    exempted = 0

    for r in rows:
        tax_amount = _dec(r['tax_amount'])
        base = _dec(r['taxable_amount'])
        total += tax_amount
        raw_base += base
        tax_type = (r['tax_type'] or 'UNKNOWN').upper()
        by_type[tax_type] = by_type.get(tax_type, Decimal('0')) + tax_amount
        key = (str(r['charge_source_type']), str(r['charge_source_id']))
        distinct_base[key] = base
        if r['is_exempted']:
            exempted += 1

    acc.count('tax.rows', len(rows))
    acc.money('tax.total', total)
    acc.money('tax.taxable_base_raw', raw_base)
    acc.money('tax.taxable_base_deduplicated',
              sum(distinct_base.values(), Decimal('0')))
    acc.count('tax.exempt_rows', exempted)
    for tax_type in sorted(by_type):
        acc.money(f'tax.by_type.{tax_type}', by_type[tax_type])


def _night_rates(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Priced room nights whose stay date is *day*.

    ``reservation_night_rates`` is the per-night pricing record: the
    closest thing in the schema to an immutable statement of what a room
    was sold for on a given night, and therefore the natural reference
    for accrual room revenue.
    """
    if not _table_exists(conn, 'reservation_night_rates'):
        return
    rows = conn.execute(
        'SELECT final_rate, resolved_rate, standard_rate, discount_amount, '
        '       is_posted, is_locked '
        'FROM reservation_night_rates WHERE stay_date = ? ORDER BY id',
        (day,)).fetchall()

    final = Decimal('0')
    resolved = Decimal('0')
    standard = Decimal('0')
    discount = Decimal('0')
    posted = 0
    locked = 0
    for r in rows:
        final += _dec(r['final_rate'])
        resolved += _dec(r['resolved_rate'])
        standard += _dec(r['standard_rate'])
        discount += _dec(r['discount_amount'])
        posted += 1 if r['is_posted'] else 0
        locked += 1 if r['is_locked'] else 0

    acc.count('night_rates.rows', len(rows))
    acc.money('night_rates.final', final)
    acc.money('night_rates.resolved', resolved)
    acc.money('night_rates.standard', standard)
    acc.money('night_rates.discount', discount)
    acc.count('night_rates.posted_rows', posted)
    acc.count('night_rates.locked_rows', locked)


def _occupancy(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Occupancy derived from reservation date spans, not room status.

    In-house is ``arrival_date <= day < departure_date`` with status in
    ``CheckedIn`` or ``CheckedOut`` — the same span the application uses
    in ``get_accrual_room_revenue`` and ``NightAuditService``.

    Room *status* is deliberately not used. ``Room.status`` is a
    present-tense field: it says what a room is like now, not what it was
    like on 27 May. Any figure derived from it is unreplayable by
    construction, and one purpose of this ledger is to make that visible.
    """
    if not _table_exists(conn, 'reservations'):
        return
    inhouse = conn.execute(
        "SELECT COUNT(*) AS n, "
        "       COUNT(DISTINCT room_id) AS rooms, "
        "       COALESCE(SUM(rate_per_night), 0) AS tariff "
        "FROM reservations "
        "WHERE status IN ('CheckedIn','CheckedOut') "
        "  AND arrival_date <= ? AND departure_date > ?",
        (day, day)).fetchone()
    tariff_rows = conn.execute(
        "SELECT rate_per_night FROM reservations "
        "WHERE status IN ('CheckedIn','CheckedOut') "
        "  AND arrival_date <= ? AND departure_date > ? ORDER BY id",
        (day, day)).fetchall()

    acc.count('occupancy.inhouse_reservations', inhouse['n'])
    acc.count('occupancy.inhouse_distinct_rooms', inhouse['rooms'] or 0)
    acc.money('occupancy.inhouse_tariff_sum',
              sum((_dec(r['rate_per_night']) for r in tariff_rows),
                  Decimal('0')))

    arrivals = conn.execute(
        'SELECT COUNT(*) FROM reservations WHERE arrival_date = ?',
        (day,)).fetchone()[0]
    arrivals_done = conn.execute(
        "SELECT COUNT(*) FROM reservations WHERE arrival_date = ? "
        "AND status IN ('CheckedIn','CheckedOut')", (day,)).fetchone()[0]
    departures = conn.execute(
        'SELECT COUNT(*) FROM reservations WHERE departure_date = ?',
        (day,)).fetchone()[0]
    departures_done = conn.execute(
        "SELECT COUNT(*) FROM reservations WHERE departure_date = ? "
        "AND status = 'CheckedOut'", (day,)).fetchone()[0]

    acc.count('movement.arrivals_expected', arrivals)
    acc.count('movement.arrivals_completed', arrivals_done)
    acc.count('movement.departures_expected', departures)
    acc.count('movement.departures_completed', departures_done)


def _discounts(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Checkout discounts attributed to *day*.

    Mirrors ``kpi_helpers.get_cash_discount``: reservations with status
    ``CheckedOut`` whose ``checked_out_at`` falls on the date. That
    helper feeds both the cash-net and the accrual-net figures, so a day
    with no checkouts and a day whose checkouts carry no discount are
    indistinguishable in the engine output — the row count recorded here
    is what tells them apart.
    """
    if not _table_exists(conn, 'reservations'):
        return
    rows = conn.execute(
        "SELECT discount_amount FROM reservations "
        "WHERE status = 'CheckedOut' AND DATE(checked_out_at) = ? "
        "ORDER BY id", (day,)).fetchall()
    acc.count('discounts.checkout_rows', len(rows))
    acc.money('discounts.checkout_total',
              sum((_dec(r['discount_amount']) for r in rows), Decimal('0')))


def _credit_notes(conn: sqlite3.Connection, day: str, acc: _Acc) -> None:
    """Credit notes issued on *day*."""
    if not _table_exists(conn, 'credit_notes'):
        return
    rows = conn.execute(
        'SELECT total_amount, taxable_amount FROM credit_notes '
        'WHERE DATE(issued_at) = ? ORDER BY id', (day,)).fetchall()
    acc.count('credit_notes.rows', len(rows))
    acc.money('credit_notes.total',
              sum((_dec(r['total_amount']) for r in rows), Decimal('0')))
    acc.money('credit_notes.taxable',
              sum((_dec(r['taxable_amount']) for r in rows), Decimal('0')))


BUILDERS = (_payments, _charges, _tax, _night_rates, _occupancy,
            _discounts, _credit_notes)


def build(db_path: str, day: str) -> dict:
    """Return the ledger for one business date as ``{path: value}``."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro'.replace('\\', '/'),
                           uri=True)
    conn.row_factory = sqlite3.Row
    try:
        acc = _Acc()
        for builder in BUILDERS:
            builder(conn, day, acc)
        return dict(sorted(acc.figures.items()))
    finally:
        conn.close()


def build_all(db_path: str, days: list) -> dict:
    """Ledgers for many dates: ``{date: {path: value}}``."""
    return {day: build(db_path, day) for day in days}
