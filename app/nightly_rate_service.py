"""
Nightly Rate Service — Phase B (Write-Only)
=============================================
Write-only service for creating and synchronizing ``ReservationNightRate``
rows.  Does NOT modify any existing read paths (invoice, night audit,
leakage engine, calculate_stay_amount).  Those remain on
``reservation.rate_per_night`` until Phase C.

Public API:

    sync_reservation_nightly_rates(reservation, reason, ...)
        Creates/updates nightly rows and synchronizes reservation summary.

    recalculate_reservation_rate_summary(reservation)
        Re-derives reservation.rate_per_night / adjustment_amount /
        discount_amount from existing nightly rows.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.financial import money, ZERO
from app.models import db, ReservationNightRate, Reservation

_log = logging.getLogger('app.nightly_rates')
_Q2 = Decimal('0.01')


# ---------------------------------------------------------------------------
# Discount distribution
# ---------------------------------------------------------------------------

def distribute_discount_proportionally(
    nightly_pre_discount: list[Decimal],
    total_discount: Decimal,
) -> list[Decimal]:
    """
    Distribute *total_discount* across nights proportionally to their
    pre-discount values.  Guarantees exact reconciliation via remainder
    on the last night.

    Parameters
    ----------
    nightly_pre_discount : list[Decimal]
        Pre-discount rate for each night (e.g., [2000, 3000, 3000]).
    total_discount : Decimal
        Total discount to allocate.

    Returns
    -------
    list[Decimal]
        Per-night discount amounts that sum exactly to *total_discount*.

    >>> distribute_discount_proportionally(
    ...     [Decimal('2000'), Decimal('3000'), Decimal('3000')],
    ...     Decimal('400'))
    [Decimal('100.00'), Decimal('150.00'), Decimal('150.00')]
    """
    if total_discount <= ZERO or not nightly_pre_discount:
        return [ZERO] * len(nightly_pre_discount)

    total_pre = sum(nightly_pre_discount)
    if total_pre <= ZERO:
        # Uniform split when all pre-discount values are zero
        per_night = (total_discount / len(nightly_pre_discount)).quantize(_Q2, rounding=ROUND_HALF_UP)
        alloc = [per_night] * len(nightly_pre_discount)
        # Fix remainder
        diff = total_discount - sum(alloc)
        alloc[-1] += diff
        return alloc

    alloc = []
    running = ZERO
    for i, pre in enumerate(nightly_pre_discount):
        if i == len(nightly_pre_discount) - 1:
            # Last night gets remainder for exact reconciliation
            alloc.append(total_discount - running)
        else:
            share = (pre * total_discount / total_pre).quantize(_Q2, rounding=ROUND_HALF_UP)
            alloc.append(share)
            running += share

    return alloc


# ---------------------------------------------------------------------------
# Core sync function
# ---------------------------------------------------------------------------

def sync_reservation_nightly_rates(
    reservation: Reservation,
    *,
    reason: str = 'new_booking',
    nightly_detailed: list | None = None,
    override_final_total: float | None = None,
    discount_total: float | None = None,
    pricing_mode: str | None = None,
    manual_override: bool = False,
    user_id: int | None = None,
) -> int:
    """
    Create or update nightly rate rows for a reservation and synchronize
    the reservation summary fields.

    Parameters
    ----------
    reservation : Reservation
        Must be flushed (have an id) and have arrival/departure set.
    reason : str
        Write reason for audit logging.  One of ``new_booking``,
        ``checkin_override``, ``edit``, ``room_change``, ``extension``.
    nightly_detailed : list, optional
        Output of ``get_stay_rates_detailed()`` — list of
        ``(date, rate, plan_name)`` tuples.  If None, the resolver
        is called internally.
    override_final_total : float, optional
        If set (e.g., total_stay pricing mode), the final_rates are
        proportionally scaled so their sum equals this total.
    discount_total : float, optional
        Reservation-level discount to distribute across nights.
    pricing_mode : str, optional
        Pricing mode used (standard/per_night/total_stay/discount_on_total).
    manual_override : bool
        True if staff manually overrode the tariff.
    user_id : int, optional
        Staff user ID for audit trail.

    Returns
    -------
    int
        Number of nightly rows created or updated.
    """
    if not reservation.id:
        raise ValueError('Reservation must be flushed before syncing nightly rates.')

    arrival = reservation.arrival_date
    departure = reservation.departure_date
    nights = max((departure - arrival).days, 1)
    room_type_id = reservation.room_type_id
    room_id = reservation.room_id

    # Get base rate
    from app.models import RoomType
    rt = db.session.get(RoomType, room_type_id) if room_type_id else None
    base_rate = money(rt.base_rate) if rt else ZERO

    # Get per-night detailed rates if not provided
    if nightly_detailed is None:
        from app.rates import get_stay_rates_detailed
        nightly_detailed = get_stay_rates_detailed(room_type_id, arrival, departure)

    # Build raw nightly data
    raw_nights = []
    current = arrival
    idx = 0
    while current < departure:
        if idx < len(nightly_detailed):
            d, resolved, plan_name = nightly_detailed[idx]
        else:
            d, resolved, plan_name = current, float(base_rate), None
        raw_nights.append({
            'date': current,
            'standard_rate': money(base_rate),
            'resolved_rate': money(resolved),
            'plan_name': plan_name,
            'rate_source': 'rate_plan' if plan_name else 'base_rate',
        })
        current += timedelta(days=1)
        idx += 1

    # Determine final rates
    _pm = pricing_mode or getattr(reservation, 'pricing_mode', 'standard') or 'standard'
    _disc = money(discount_total if discount_total is not None
                  else getattr(reservation, 'discount_amount', 0))

    if override_final_total is not None:
        # Total-stay or per-night override: scale resolved rates proportionally
        target = money(override_final_total)
        resolved_sum = sum(n['resolved_rate'] for n in raw_nights)
        if resolved_sum > ZERO:
            for n in raw_nights:
                n['final_pre_discount'] = (n['resolved_rate'] * target / resolved_sum).quantize(_Q2, ROUND_HALF_UP)
        else:
            per = (target / len(raw_nights)).quantize(_Q2, ROUND_HALF_UP)
            for n in raw_nights:
                n['final_pre_discount'] = per
        # Fix rounding to hit target exactly
        actual_sum = sum(n['final_pre_discount'] for n in raw_nights)
        if actual_sum != target:
            raw_nights[-1]['final_pre_discount'] += (target - actual_sum)
    elif manual_override and _pm == 'per_night':
        rate_pn = money(reservation.rate_per_night)
        for n in raw_nights:
            n['final_pre_discount'] = rate_pn
    else:
        for n in raw_nights:
            n['final_pre_discount'] = n['resolved_rate']

    # Override source if manual
    if manual_override:
        for n in raw_nights:
            n['rate_source'] = 'manual_override'

    # Distribute discount
    pre_disc_values = [n['final_pre_discount'] for n in raw_nights]
    disc_alloc = distribute_discount_proportionally(pre_disc_values, _disc)

    for i, n in enumerate(raw_nights):
        n['discount'] = disc_alloc[i]
        n['final_rate'] = (n['final_pre_discount'] - disc_alloc[i]).quantize(_Q2, ROUND_HALF_UP)

    # Get tax rate for each night
    from app.gst_service import get_room_gst_rate
    for n in raw_nights:
        n['tax_rate'] = get_room_gst_rate(n['final_rate'], rt)

    # Load existing rows, index by date
    existing = {r.stay_date: r for r in
                ReservationNightRate.query.filter_by(reservation_id=reservation.id).all()}

    created = 0
    skipped_locked = 0

    for n in raw_nights:
        d = n['date']
        row = existing.get(d)

        if row and (row.is_posted or row.is_locked):
            skipped_locked += 1
            continue

        if row:
            # Update existing unlocked row
            row.standard_rate = n['standard_rate']
            row.resolved_rate = n['resolved_rate']
            row.final_rate = n['final_rate']
            row.discount_amount = n['discount']
            row.rate_source = n['rate_source']
            row.rate_plan_name = n['plan_name']
            row.pricing_mode = _pm
            row.manual_override = manual_override
            row.tax_rate = n['tax_rate']
            row.room_type_id = room_type_id
            row.room_id = room_id
        else:
            # Create new row
            row = ReservationNightRate(
                reservation_id=reservation.id,
                stay_date=d,
                room_type_id=room_type_id,
                room_id=room_id,
                standard_rate=n['standard_rate'],
                resolved_rate=n['resolved_rate'],
                final_rate=n['final_rate'],
                discount_amount=n['discount'],
                rate_source=n['rate_source'],
                rate_plan_name=n['plan_name'],
                pricing_mode=_pm,
                manual_override=manual_override,
                tax_rate=n['tax_rate'],
            )
            db.session.add(row)
            created += 1

    # Sync reservation summary fields from the rows we just built
    _all_rows_for_summary = []
    for n in raw_nights:
        _all_rows_for_summary.append(type('_NR', (), {
            'standard_rate': n['standard_rate'],
            'final_rate': n['final_rate'],
            'discount_amount': n['discount'],
        })())
    recalculate_reservation_rate_summary(reservation, rows_override=_all_rows_for_summary)

    _log.info(
        'NIGHTLY_SYNC res=%d reason=%s nights=%d created=%d skipped_locked=%d '
        'mode=%s override=%s',
        reservation.id, reason, nights, created, skipped_locked,
        _pm, manual_override
    )

    return created


def recalculate_reservation_rate_summary(reservation: Reservation, rows_override=None):
    """
    Re-derive reservation summary fields from nightly rows.

    Updates:
    - ``rate_per_night`` = AVG(final_rate)
    - ``adjustment_amount`` = SUM(standard_rate) - SUM(final_rate)
    - ``discount_amount`` = SUM(nightly discount_amount)

    Only acts if nightly rows exist.  If no rows, leaves reservation unchanged.

    Parameters
    ----------
    rows_override : list, optional
        If provided, use these row-like objects instead of querying the DB.
        Used internally by sync to avoid re-querying rows just created.
    """
    rows = rows_override if rows_override is not None else \
        ReservationNightRate.query.filter_by(reservation_id=reservation.id).all()
    if not rows:
        return

    n = len(rows)
    sum_final = sum(money(r.final_rate) for r in rows)
    sum_std = sum(money(r.standard_rate) for r in rows)
    sum_disc = sum(money(r.discount_amount) for r in rows)

    avg_rate = (sum_final / n).quantize(_Q2, rounding=ROUND_HALF_UP)

    reservation.rate_per_night = avg_rate
    reservation.adjustment_amount = float((sum_std - sum_final).quantize(_Q2, rounding=ROUND_HALF_UP))
    reservation.discount_amount = float(sum_disc.quantize(_Q2, rounding=ROUND_HALF_UP))

    # Keep standard_tariff as first night's standard (or existing if already set)
    if reservation.standard_tariff is None and rows:
        reservation.standard_tariff = float(rows[0].standard_rate)

    # Adjustment type
    adj = sum_std - sum_final
    if adj > _Q2:
        reservation.adjustment_type = 'LEAKAGE'
    elif adj < -_Q2:
        reservation.adjustment_type = 'UPSELL'
    else:
        reservation.adjustment_type = None


def safe_sync_nightly_rates(reservation, **kwargs):
    """
    Non-blocking wrapper for ``sync_reservation_nightly_rates``.

    Call this from any write path.  If nightly row creation fails for
    any reason, the failure is logged but does NOT block the primary
    reservation flow.  Phase B is additive — existing behavior must
    never break because of nightly rows.
    """
    try:
        return sync_reservation_nightly_rates(reservation, **kwargs)
    except Exception as exc:
        _log.warning(
            'NIGHTLY_SYNC_FAIL res=%s reason=%s error=%s',
            getattr(reservation, 'id', '?'), kwargs.get('reason', '?'), exc,
            exc_info=True
        )
        return 0


# ---------------------------------------------------------------------------
# Validation / inspection helpers
# ---------------------------------------------------------------------------

def validate_nightly_rows(reservation) -> dict:
    """
    Validate nightly row continuity and consistency for a reservation.

    Returns a dict with:
        rows       : list of ReservationNightRate objects
        nights     : expected night count from dates
        warnings   : list of warning strings
        summary    : dict with totals and comparison to reservation fields
    """
    arrival = reservation.arrival_date
    departure = reservation.departure_date
    expected_nights = max((departure - arrival).days, 1)

    rows = ReservationNightRate.query.filter_by(
        reservation_id=reservation.id
    ).order_by(ReservationNightRate.stay_date).all()

    warnings = []

    # Check: any rows at all?
    if not rows:
        warnings.append('NO_ROWS: No nightly rate rows exist for this reservation.')
        return {
            'rows': [],
            'nights': expected_nights,
            'warnings': warnings,
            'summary': None,
        }

    # Check count
    if len(rows) != expected_nights:
        warnings.append(
            f'COUNT_MISMATCH: Expected {expected_nights} rows, found {len(rows)}.')

    # Check for gaps and duplicates
    expected_dates = set()
    d = arrival
    while d < departure:
        expected_dates.add(d)
        d += timedelta(days=1)

    actual_dates = [r.stay_date for r in rows]
    actual_set = set(actual_dates)

    missing = expected_dates - actual_set
    if missing:
        warnings.append(
            f'MISSING_DATES: {sorted(missing)}')

    if len(actual_dates) != len(actual_set):
        dupes = [d for d in actual_dates if actual_dates.count(d) > 1]
        warnings.append(
            f'DUPLICATE_DATES: {sorted(set(dupes))}')

    extra = actual_set - expected_dates
    if extra:
        warnings.append(
            f'EXTRA_DATES: Rows outside stay range: {sorted(extra)}')

    # Summary totals
    sum_std = sum(money(r.standard_rate) for r in rows)
    sum_final = sum(money(r.final_rate) for r in rows)
    sum_disc = sum(money(r.discount_amount) for r in rows)
    avg_final = (sum_final / len(rows)).quantize(_Q2, rounding=ROUND_HALF_UP) if rows else ZERO

    # Compare to reservation summary
    res_rpn = money(reservation.rate_per_night)
    res_disc = money(reservation.discount_amount)
    res_adj = money(reservation.adjustment_amount) if reservation.adjustment_amount else ZERO

    rpn_diff = abs(avg_final - res_rpn)
    if rpn_diff > Decimal('0.02'):
        warnings.append(
            f'RATE_MISMATCH: AVG(final_rate)={avg_final} vs '
            f'reservation.rate_per_night={res_rpn} (diff={rpn_diff})')

    expected_total = res_rpn * expected_nights
    if abs(sum_final - expected_total) > Decimal('1.00'):
        warnings.append(
            f'TOTAL_MISMATCH: SUM(final_rate)={sum_final} vs '
            f'rate_per_night*nights={expected_total}')

    return {
        'rows': rows,
        'nights': expected_nights,
        'warnings': warnings,
        'summary': {
            'total_standard': float(sum_std),
            'total_final': float(sum_final),
            'total_discount': float(sum_disc),
            'avg_final': float(avg_final),
            'res_rate_per_night': float(res_rpn),
            'res_discount': float(res_disc),
            'res_adjustment': float(res_adj),
            'row_count': len(rows),
            'expected_nights': expected_nights,
        },
    }
