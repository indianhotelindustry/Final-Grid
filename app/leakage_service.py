"""
Leakage Service — Commercial Revenue Leakage Computation
=========================================================
Computes the difference between what *should* have been charged
(standard tariff) and what *was* charged (actual rate + discounts).

This module deals exclusively with **rate leakage** and **discount
leakage**.  It does NOT include unpaid balances, credits, or refunds.

Usage::

    from app.leakage_service import compute_reservation_leakage

    result = compute_reservation_leakage(reservation)
    # result['total_leakage']  →  Decimal amount lost
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Optional

from app.financial import money, ZERO

_Q2 = Decimal('0.01')


def compute_reservation_leakage(reservation) -> dict:
    """
    Compute commercial leakage for a single reservation.

    Parameters
    ----------
    reservation : Reservation
        Must have ``standard_tariff``, ``rate_per_night``,
        ``arrival_date``, ``departure_date``, ``discount_amount``.

    Returns
    -------
    dict with keys:
        reservation_id      : int
        guest_name          : str
        room_number         : str
        arrival_date        : date
        departure_date      : date
        nights              : int
        standard_tariff     : Decimal   per-night standard rate
        actual_rate         : Decimal   per-night charged rate
        standard_revenue    : Decimal   standard_tariff × nights
        actual_revenue      : Decimal   actual_rate × nights
        rate_leakage        : Decimal   max(0, standard - actual)
        discount_amount     : Decimal   discount applied at checkout
        total_leakage       : Decimal   rate_leakage + discount_amount
        leakage_pct         : Decimal   total_leakage / standard_revenue × 100
        pricing_mode        : str | None
        adjustment_type     : str | None   ('LEAKAGE', 'UPSELL', or None)
        has_leakage         : bool
    """
    import logging as _lk_logging
    _lk_log = _lk_logging.getLogger('app.leakage')

    nights = max((reservation.departure_date - reservation.arrival_date).days, 1)

    # ── Phase C.4: per-night leakage from nightly rows when available ──
    _src = 'legacy_aggregate'
    std_revenue = None
    actual_revenue = None
    rate_leakage = None
    discount = None

    try:
        from app.nightly_rate_service import validate_nightly_rows
        validation = validate_nightly_rows(reservation)
        if validation['rows']:
            blocking = [w for w in validation['warnings']
                        if w.startswith(('MISSING_DATES', 'DUPLICATE_DATES'))]
            if blocking:
                _src = 'validation_fallback'
                _lk_log.warning(
                    'compute_reservation_leakage: res=%d validation_fallback: %s',
                    reservation.id, '; '.join(blocking))
            else:
                rows = validation['rows']
                std_revenue = sum(money(r.standard_rate) for r in rows)
                actual_revenue = sum(money(r.final_rate) for r in rows)
                # Per-night leakage: max(0, standard - final) summed across nights.
                # An upsell night (final > standard) contributes 0 leakage.
                rate_leakage = sum(
                    max(ZERO, money(r.standard_rate) - money(r.final_rate))
                    for r in rows)
                # Discount leakage = sum of nightly discount_amount (already
                # baked into final_rate, tracked separately for reporting).
                discount = sum(money(r.discount_amount) for r in rows)
                _src = 'nightly_rows'
    except Exception as _err:
        _lk_log.warning(
            'compute_reservation_leakage: res=%d nightly lookup failed (%s), '
            'using legacy', reservation.id, _err)

    # Legacy aggregate fallback
    if std_revenue is None:
        std_tariff = money(reservation.standard_tariff
                           if reservation.standard_tariff is not None
                           else reservation.rate_per_night)
        actual_rate = money(reservation.rate_per_night)
        std_revenue = (std_tariff * nights).quantize(_Q2, rounding=ROUND_HALF_UP)
        actual_revenue = (actual_rate * nights).quantize(_Q2, rounding=ROUND_HALF_UP)
        rate_leakage = max(ZERO, std_revenue - actual_revenue)
        discount = money(reservation.discount_amount)

    std_revenue = std_revenue.quantize(_Q2, rounding=ROUND_HALF_UP)
    actual_revenue = actual_revenue.quantize(_Q2, rounding=ROUND_HALF_UP)
    rate_leakage = rate_leakage.quantize(_Q2, rounding=ROUND_HALF_UP)
    discount = discount.quantize(_Q2, rounding=ROUND_HALF_UP)

    # Derive per-night averages for backward compatibility in return dict
    std_tariff = (std_revenue / nights).quantize(_Q2, rounding=ROUND_HALF_UP) if nights > 0 else ZERO
    actual_rate = (actual_revenue / nights).quantize(_Q2, rounding=ROUND_HALF_UP) if nights > 0 else ZERO

    total_leak = (rate_leakage + discount).quantize(_Q2, rounding=ROUND_HALF_UP)
    _lk_log.debug('compute_reservation_leakage: res=%d source=%s std=%s actual=%s rate_leak=%s disc=%s',
                  reservation.id, _src, std_revenue, actual_revenue, rate_leakage, discount)

    leakage_pct = ZERO
    if std_revenue > ZERO:
        leakage_pct = (total_leak * 100 / std_revenue).quantize(_Q2, rounding=ROUND_HALF_UP)

    # ── Actionable status ──────────────────────────────────────────
    adj_type = getattr(reservation, 'adjustment_type', None)
    disc_auth = getattr(reservation, 'discount_authorized_by', None)

    if total_leak == ZERO:
        status = 'OK'
    elif adj_type == 'UPSELL':
        status = 'OK'
    elif discount > ZERO and not (disc_auth and disc_auth.strip()):
        status = 'UNAUTHORIZED'
    elif discount > ZERO:
        status = 'APPROVED'
    elif rate_leakage > ZERO:
        status = 'UNDERPRICED'
    else:
        status = 'REVIEW'

    guest = reservation.guest
    room  = reservation.room

    return {
        'reservation_id':   reservation.id,
        'invoice_number':   reservation.invoice_number,
        'guest_name':       guest.name if guest else '—',
        'room_number':      room.room_number if room else '—',
        'arrival_date':     reservation.arrival_date,
        'departure_date':   reservation.departure_date,
        'nights':           nights,
        'standard_tariff':  std_tariff,
        'actual_rate':      actual_rate,
        'standard_revenue': std_revenue,
        'actual_revenue':   actual_revenue,
        'rate_leakage':     rate_leakage,
        'discount_amount':  discount,
        'total_leakage':    total_leak,
        'leakage_pct':      leakage_pct,
        'pricing_mode':     getattr(reservation, 'pricing_mode', None),
        'adjustment_type':  adj_type,
        'has_leakage':      total_leak > ZERO,
        'status':           status,
        'discount_reason':  getattr(reservation, 'discount_reason', None),
        'discount_authorized_by': disc_auth,
        'source':           _src,
    }


def compute_leakage_for_date_range(
    start_date: date,
    end_date: date,
    *,
    only_leakage: bool = False,
    status_filter: Optional[list[str]] = None,
) -> list[dict]:
    """
    Compute leakage for all reservations whose **checkout** falls within
    [start_date, end_date].

    Parameters
    ----------
    start_date, end_date : date
        Inclusive date range on ``checked_out_at``.
    only_leakage : bool
        If True, exclude reservations with zero leakage.
    status_filter : list[str], optional
        Reservation statuses to include.  Defaults to
        ``['CheckedOut', 'CheckedIn']``.

    Returns
    -------
    list[dict]
        Each element is a :func:`compute_reservation_leakage` result dict.
        Sorted by ``total_leakage`` descending.
    """
    from sqlalchemy import func
    from app.models import db, Reservation

    statuses = status_filter or ['CheckedOut', 'CheckedIn']

    q = (Reservation.query
         .filter(Reservation.status.in_(statuses))
         .options(
             db.joinedload(Reservation.guest),
             db.joinedload(Reservation.room),
         ))

    # Date filter: use checked_out_at for CheckedOut, arrival_date for CheckedIn
    q = q.filter(
        db.or_(
            db.and_(
                Reservation.status == 'CheckedOut',
                func.date(Reservation.checked_out_at) >= start_date,
                func.date(Reservation.checked_out_at) <= end_date,
            ),
            db.and_(
                Reservation.status == 'CheckedIn',
                Reservation.arrival_date >= start_date,
                Reservation.arrival_date <= end_date,
            ),
        )
    )

    results = []
    for res in q.all():
        rec = compute_reservation_leakage(res)
        if only_leakage and not rec['has_leakage']:
            continue
        results.append(rec)

    results.sort(key=lambda r: r['total_leakage'], reverse=True)
    return results


def compute_leakage_summary(records: list[dict]) -> dict:
    """
    Aggregate a list of leakage records into a summary.

    Parameters
    ----------
    records : list[dict]
        Output from :func:`compute_leakage_for_date_range`.

    Returns
    -------
    dict with keys:
        total_reservations  : int
        leakage_count       : int     reservations with leakage > 0
        total_standard      : Decimal
        total_actual        : Decimal
        total_rate_leakage  : Decimal
        total_discount      : Decimal
        total_leakage       : Decimal
        avg_leakage_pct     : Decimal
    """
    total_std   = ZERO
    total_act   = ZERO
    total_rate  = ZERO
    total_disc  = ZERO
    total_leak  = ZERO
    leak_count  = 0

    for r in records:
        total_std  += r['standard_revenue']
        total_act  += r['actual_revenue']
        total_rate += r['rate_leakage']
        total_disc += r['discount_amount']
        total_leak += r['total_leakage']
        if r['has_leakage']:
            leak_count += 1

    avg_pct = ZERO
    if total_std > ZERO:
        avg_pct = (total_leak * 100 / total_std).quantize(_Q2, rounding=ROUND_HALF_UP)

    return {
        'total_reservations': len(records),
        'leakage_count':      leak_count,
        'total_standard':     total_std,
        'total_actual':       total_act,
        'total_rate_leakage': total_rate,
        'total_discount':     total_disc,
        'total_leakage':      total_leak,
        'avg_leakage_pct':    avg_pct,
    }
