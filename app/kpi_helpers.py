"""
Centralized Hotel KPI Calculations
====================================
Single source of truth for occupancy, ADR, RevPAR, and daily revenue.

Two Revenue Models
------------------
**Cash Revenue** (collected)
    Sum of non-voided payments received on a business date.
    Use for cashier reconciliation, bank deposits, payment-mode breakdowns.

**Accrual Revenue** (earned)
    Room tariff × occupied nights + extra charges posted on the date,
    regardless of when the guest actually pays.
    Use for P&L reporting, management KPIs, night-audit snapshots.

Both models are computed side-by-side.  Every dict key and template
variable carries a ``cash_`` or ``accrual_`` prefix so there is never
any ambiguity about which revenue basis is being shown.

Other Rules
-----------
- **Occupancy** is always derived from ``Reservation.status == 'CheckedIn'``,
  never from ``Room.status == 'Occupied'``.
- **Sellable rooms** = active, sellable, not out-of-order rooms.
- **ADR (Average Daily Rate)** is rate-based: ``AVG(rate_per_night)``
  of checked-in reservations.  Never derived from payment totals.
- **RevPAR** = ``ADR × occupancy_pct / 100``.

Import this module wherever KPI numbers are needed instead of writing
inline queries.
"""
from __future__ import annotations

from datetime import date as _date

from sqlalchemy import func

from app.models import db, Room, Reservation, ReservationRoom, Payment, ExtraCharge, PaymentMode


# ═══════════════════════════════════════════════════════════════════════════
# Room inventory
# ═══════════════════════════════════════════════════════════════════════════

def get_sellable_room_count() -> int:
    """Rooms that could be sold tonight — the occupancy denominator.

    KPI Phase 1, Step 3: delegates to the canonical occupancy engine
    (app/occupancy_engine.py) so every KPI surface shares one
    denominator. The engine additionally excludes rooms whose status
    text is Maintenance/Out of Order, not only the is_out_of_order
    boolean — the two were proven to drift apart in production.
    """
    from app.occupancy_engine import sellable_rooms
    return sellable_rooms()


def get_total_room_count() -> int:
    """All rooms (including maintenance/OOO). Use for inventory display only."""
    return Room.query.count()


# ═══════════════════════════════════════════════════════════════════════════
# Occupancy — always from Reservation.status = 'CheckedIn'
# ═══════════════════════════════════════════════════════════════════════════

def get_occupied_count() -> int:
    """Number of rooms currently occupied (checked-in reservations).

    KPI Phase 1, Step 3: delegates to the canonical occupancy engine
    (app/occupancy_engine.py). The engine counts DISTINCT physical
    rooms via a true set-union of ``Reservation.room_id`` and the
    ``reservation_rooms`` bridge for CheckedIn reservations — a room
    reached by both paths is counted exactly once (the prior additive
    two-path formula could double-count it). ``Room.status`` is never
    consulted. This wrapper is retained so existing import sites keep
    working unchanged.
    """
    from app.occupancy_engine import occupied_rooms
    return occupied_rooms()


def get_occupancy(sellable: int | None = None) -> dict:
    """Occupancy snapshot: {occupied, sellable, total, pct}.

    KPI Phase 1, Step 3: delegates to app/occupancy_engine.py — the
    single source of occupancy truth. Every legacy caller of this
    helper therefore converges on the canonical numbers without code
    change. The ``sellable`` override parameter is preserved for
    backward compatibility; when supplied it is used only to recompute
    ``pct``.
    """
    from app.occupancy_engine import occupancy_snapshot
    snap = occupancy_snapshot()
    occupied = snap['occupied']
    if sellable is None:
        sellable = snap['sellable']
    total = snap['total']
    pct = round(occupied / sellable * 100, 1) if sellable and sellable > 0 else 0.0
    return {
        'occupied': occupied,
        'sellable': sellable,
        'total':    total,
        'pct':      pct,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ADR — always rate-based, never payment-based
# ═══════════════════════════════════════════════════════════════════════════

def get_adr() -> float:
    """Average Daily Rate = AVG(rate_per_night) of checked-in reservations."""
    avg = (db.session.query(func.avg(Reservation.rate_per_night))
           .filter(Reservation.status == 'CheckedIn')
           .scalar())
    return round(float(avg), 2) if avg else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# RevPAR — always ADR × occupancy / 100
# ═══════════════════════════════════════════════════════════════════════════

def get_revpar(adr: float | None = None, occ_pct: float | None = None) -> float:
    """Revenue Per Available Room = ADR × occupancy_pct / 100."""
    if adr is None:
        adr = get_adr()
    if occ_pct is None:
        occ_pct = get_occupancy()['pct']
    return round(adr * occ_pct / 100, 2)


# ═══════════════════════════════════════════════════════════════════════════
# CASH REVENUE — payment-based (collected), excludes voided
# ═══════════════════════════════════════════════════════════════════════════

def get_cash_revenue(business_date: _date) -> float:
    """Gross **direct** cash collected: sum of non-voided payments where
    the payment mode category is ``direct_payment`` (Cash, UPI, Card, etc.).

    OTA receivable postings are **excluded** — they represent money owed
    by the OTA, not cash in the hotel's hands.
    """
    total = (db.session.query(func.sum(Payment.amount))
             .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
             .filter(Payment.payment_date == business_date,
                     Payment.is_voided == False,
                     PaymentMode.category == 'direct_payment')
             .scalar())
    return round(float(total), 2) if total else 0.0


def get_ota_receivable_posted(business_date: _date) -> float:
    """OTA receivable postings for *business_date*: sum of non-voided payments
    where the payment mode category is ``ota_receivable``.

    This is NOT cash received — it is the amount the OTA owes the hotel.
    """
    total = (db.session.query(func.sum(Payment.amount))
             .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
             .filter(Payment.payment_date == business_date,
                     Payment.is_voided == False,
                     PaymentMode.category == 'ota_receivable')
             .scalar())
    return round(float(total), 2) if total else 0.0


# Backward-compatible alias
get_ota_revenue = get_ota_receivable_posted


def get_ota_receivable_mtd(business_date: _date) -> float:
    """OTA receivable postings month-to-date: first of current month through
    ``business_date`` inclusive. Same filter as :func:`get_ota_receivable_posted`,
    just a wider window. Used on the main dashboard alongside the Today card."""
    month_start = business_date.replace(day=1)
    total = (db.session.query(func.sum(Payment.amount))
             .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
             .filter(Payment.payment_date >= month_start,
                     Payment.payment_date <= business_date,
                     Payment.is_voided == False,
                     PaymentMode.category == 'ota_receivable')
             .scalar())
    return round(float(total), 2) if total else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# CASH-BASIS REVENUE AGGREGATIONS (v2.2.11 Phase 0)
# ═══════════════════════════════════════════════════════════════════════════
# These helpers extract the inline payment-table aggregations that previously
# lived in ``_build_dashboard_context`` and in two reports (``/reports/flash``,
# ``/reports/daily-profit-snapshot``). They all filter to
# ``PaymentMode.category='direct_payment'`` so the dashboard's MTD / payment-
# mode / revenue-by-source tiles reconcile correctly with the daily cash
# revenue tiles. OTA receivable postings are surfaced separately via the
# ``get_ota_receivable_*`` helpers — combining them was semantic double-
# counting before v2.2.11. See CHANGELOG entry for v2.2.11 for the rationale.

def get_monthly_revenue(start_date: _date, end_date: _date) -> float:
    """Cash-basis revenue between *start_date* and *end_date*, inclusive.

    Sum of non-voided ``Payment.amount`` rows whose ``payment_date`` falls
    in the closed interval [start_date, end_date], filtered to
    ``PaymentMode.category='direct_payment'``.

    For month-to-date: pass ``month_start`` and the current business date.
    For previous month: prefer the dedicated wrapper
    :func:`get_previous_month_revenue`.

    Excludes OTA receivable postings — those are surfaced separately
    through :func:`get_ota_receivable_mtd` and
    :func:`get_ota_receivable_posted`. Bundling them here previously caused
    semantic double-counting between the MTD Revenue tile and the OTA
    Receivable MTD tile.
    """
    total = (db.session.query(func.sum(Payment.amount))
             .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
             .filter(Payment.payment_date >= start_date,
                     Payment.payment_date <= end_date,
                     Payment.is_voided == False,
                     PaymentMode.category == 'direct_payment')
             .scalar())
    return round(float(total), 2) if total else 0.0


def get_previous_month_revenue(business_date: _date) -> float:
    """Cash-basis revenue for the calendar month immediately before
    *business_date*. Thin wrapper around :func:`get_monthly_revenue` with
    the previous-month date bounds computed."""
    from datetime import timedelta as _td
    month_start = business_date.replace(day=1)
    last_month_start = (month_start - _td(days=1)).replace(day=1)
    last_month_end = month_start - _td(days=1)
    return get_monthly_revenue(last_month_start, last_month_end)


def get_payment_by_mode(business_date: _date) -> dict:
    """Cash-basis payment totals on *business_date*, grouped by
    ``PaymentMode.name``.

    Returns ``dict[mode_name -> float]`` covering only non-voided payments
    in the ``direct_payment`` category. OTA receivable heads (``MMT Paid``,
    ``Booking.com Paid``, etc.) are intentionally excluded so a caller can
    safely sum the values without double-counting OTA receivables that
    are surfaced separately via :func:`get_ota_receivable_posted`.

    Used by:
      - Dashboard ``Cash In`` / ``UPI In`` / ``Cards In`` tiles
      - ``/reports/flash`` payment-mode breakdown
      - ``/reports/daily-profit-snapshot`` revenue-by-mode breakdown

    Example return: ``{'Cash': 12500.0, 'UPI': 8200.0, 'Card': 3000.0}``
    """
    rows = (db.session.query(PaymentMode.name, func.sum(Payment.amount))
            .join(Payment, Payment.payment_mode_id == PaymentMode.id)
            .filter(Payment.payment_date == business_date,
                    Payment.is_voided == False,
                    PaymentMode.category == 'direct_payment')
            .group_by(PaymentMode.name)
            .all())
    return {name: float(amt or 0) for name, amt in rows}


def get_revenue_by_source(business_date: _date) -> dict:
    """Cash-basis revenue on *business_date*, grouped by
    ``Reservation.source``.

    Returns ``dict[source -> float]`` covering only non-voided payments
    in the ``direct_payment`` category. An OTA prepaid booking whose
    payment was an OTA receivable posting does **not** contribute here —
    that money has not yet been collected in cash. To see total OTA
    activity for a date including unrealised receivables, combine this
    dict's ``OTA`` value with :func:`get_ota_receivable_posted`.

    Example return: ``{'OTA': 4200.0, 'Walk-in': 8500.0, 'Calling': 1300.0}``
    """
    rows = (db.session.query(Reservation.source, func.sum(Payment.amount))
            .join(Payment, Payment.reservation_id == Reservation.id)
            .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
            .filter(Payment.payment_date == business_date,
                    Payment.is_voided == False,
                    PaymentMode.category == 'direct_payment')
            .group_by(Reservation.source)
            .all())
    return {src: float(amt or 0) for src, amt in rows}


def get_revenue_on_date(target_date: _date) -> float:
    """Cash-basis revenue collected on *target_date*. Convenience wrapper
    that exposes the same single-date semantic as :func:`get_cash_revenue`
    (which is aliased to ``get_daily_revenue``). Provided so call sites
    that need a date-parameterised single-date helper read intuitively
    without having to remember the legacy ``get_cash_revenue`` name.

    Used by:
      - ``/reports/flash`` previous-day revenue
      - ``/reports/flash`` same-day-last-year revenue
    """
    return get_cash_revenue(target_date)


def get_total_revenue(business_date: _date) -> float:
    """Total business revenue for *business_date* (accrual basis).

    This is room revenue earned + extra charges posted, regardless of
    how they are paid (cash, UPI, card, OTA).  It does NOT come from
    the Payment table — it comes from reservations and charges.
    Use this for P&L / management KPIs.
    """
    room = get_accrual_room_revenue(business_date)
    extras = get_accrual_extras(business_date)
    return round(room + extras, 2)


def get_cash_discount(business_date: _date) -> float:
    """Discounts applied on checkouts completed on *business_date*."""
    total = (db.session.query(func.sum(Reservation.discount_amount))
             .filter(Reservation.status == 'CheckedOut',
                     func.date(Reservation.checked_out_at) == business_date)
             .scalar())
    return round(float(total), 2) if total else 0.0


def get_net_cash_revenue(business_date: _date) -> float:
    """Cash collected minus checkout discounts."""
    return round(get_cash_revenue(business_date) - get_cash_discount(business_date), 2)


def get_cash_summary(business_date: _date) -> dict:
    """
    Full cash-basis revenue breakdown.

    Keys: cash_collected, cash_discount, cash_net
    """
    collected = get_cash_revenue(business_date)
    discount = get_cash_discount(business_date)
    ota_receivable = get_ota_receivable_posted(business_date)
    return {
        'cash_collected':    collected,
        'cash_discount':     discount,
        'cash_net':          round(collected - discount, 2),
        'ota_receivable':    ota_receivable,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ACCRUAL REVENUE — rate × occupied nights (earned), not payment-based
# ═══════════════════════════════════════════════════════════════════════════

def get_accrual_room_revenue(business_date: _date) -> float:
    """
    SUM(rate_per_night) for every reservation in-house on *business_date*
    (arrival <= date < departure, status CheckedIn or CheckedOut).
    """
    total = (db.session.query(func.sum(Reservation.rate_per_night))
             .filter(
                 Reservation.status.in_(['CheckedIn', 'CheckedOut']),
                 Reservation.arrival_date <= business_date,
                 Reservation.departure_date > business_date,
             ).scalar())
    return round(float(total), 2) if total else 0.0


def get_accrual_extras(business_date: _date) -> float:
    """Extra charges (POS, laundry, minibar, etc.) posted on *business_date*.

    EXCLUDES night-audit room_rent rows — those are accounted for by
    get_accrual_room_revenue (rate × occupied nights). Without this
    filter the night audit summary and dashboard accrual KPIs would
    double-book room revenue into the extras bucket.
    """
    from sqlalchemy import or_
    total = (db.session.query(func.sum(ExtraCharge.amount))
             .filter(ExtraCharge.charge_date == business_date,
                     or_(ExtraCharge.charge_type.is_(None),
                         ExtraCharge.charge_type != 'room_rent'))
             .scalar())
    return round(float(total), 2) if total else 0.0


def get_accrual_summary(business_date: _date) -> dict:
    """
    Full accrual-basis revenue breakdown.

    Keys: accrual_room, accrual_extras, accrual_gross, accrual_discount,
          accrual_net
    """
    room = get_accrual_room_revenue(business_date)
    extras = get_accrual_extras(business_date)
    discount = get_cash_discount(business_date)   # same discount pool
    gross = round(room + extras, 2)
    return {
        'accrual_room':     room,
        'accrual_extras':   extras,
        'accrual_gross':    gross,
        'accrual_discount': discount,
        'accrual_net':      round(gross - discount, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Convenience — all dashboard KPIs in one call
# ═══════════════════════════════════════════════════════════════════════════

def get_dashboard_kpis(business_date: _date) -> dict:
    """
    All dashboard KPIs in a single dict.

    Every revenue key is prefixed ``cash_`` or ``accrual_`` so templates
    can display them side-by-side without ambiguity.
    """
    occ     = get_occupancy()
    adr     = get_adr()
    revpar  = get_revpar(adr=adr, occ_pct=occ['pct'])
    cash    = get_cash_summary(business_date)
    accrual = get_accrual_summary(business_date)
    return {
        # Occupancy
        'occupied':      occ['occupied'],
        'sellable':      occ['sellable'],
        'total_rooms':   occ['total'],
        'occupancy_pct': occ['pct'],
        # Rate KPIs
        'adr':    adr,
        'revpar': revpar,
        # Cash-basis (collected)
        **cash,
        # Accrual-basis (earned)
        **accrual,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Backward-compatible aliases (old names → new names)
# Remove these once all call-sites are migrated.
# ═══════════════════════════════════════════════════════════════════════════

get_daily_revenue  = get_cash_revenue
get_daily_discount = get_cash_discount
get_net_revenue    = get_net_cash_revenue
get_accrual_revenue = get_accrual_summary
