"""
Shared Financial Constants & Helpers
=====================================
One place for all monetary conversion, rounding, and threshold logic.

Usage::

    from app.financial import money, round2, SETTLEMENT_TOLERANCE, ZERO
"""
from decimal import Decimal, ROUND_HALF_UP

# ── Constants ────────────────────────────────────────────────────────────────

#: Amounts at or below this threshold are treated as zero for settlement
#: status, balance checks, and folio reconciliation.
SETTLEMENT_TOLERANCE = Decimal('0.01')

#: Convenient zero constant to avoid repeated Decimal('0') construction.
ZERO = Decimal('0')

#: Two-decimal quantizer for ROUND_HALF_UP.
_Q2 = Decimal('0.01')


# ── Conversion helpers ───────────────────────────────────────────────────────

def money(val) -> Decimal:
    """
    Convert *val* to a ``Decimal`` rounded to 2 decimal places.

    Accepts ``Decimal``, ``float``, ``int``, ``str``, or ``None``.
    ``None`` and empty strings convert to ``Decimal('0.00')``.

    >>> money(123.456)
    Decimal('123.46')
    >>> money(None)
    Decimal('0.00')
    >>> money('2500.5')
    Decimal('2500.50')
    """
    if val is None or val == '':
        return ZERO.quantize(_Q2)
    if isinstance(val, Decimal):
        return val.quantize(_Q2, rounding=ROUND_HALF_UP)
    return Decimal(str(val)).quantize(_Q2, rounding=ROUND_HALF_UP)


def round2(val) -> float:
    """
    Convert *val* to a ``float`` rounded to exactly 2 decimal places.

    Use this **only** at serialization boundaries (JSON responses, template
    context) where Decimal is not supported.  Keep intermediate calculations
    in ``Decimal`` via :func:`money`.

    >>> round2(Decimal('123.456'))
    123.46
    >>> round2(None)
    0.0
    """
    return float(money(val))


def is_settled(balance) -> bool:
    """Return True if *balance* is within settlement tolerance of zero."""
    return money(balance) <= SETTLEMENT_TOLERANCE


def is_zero(amount) -> bool:
    """Return True if *amount* is effectively zero."""
    return abs(money(amount)) <= SETTLEMENT_TOLERANCE


# ═══════════════════════════════════════════════════════════════════════════
# Centralized Pricing Engine — the SINGLE place for check-in pricing math.
# Every route / service that computes tariffs must call this function.
# ═══════════════════════════════════════════════════════════════════════════

#: Tolerance for rounding assertions (rate_per_night * nights vs charged_total).
#: Must accommodate worst-case division remainders (e.g., ₹100/7 = 14.29 × 7 = 100.03).
#: Formula: max remainder = (nights - 1) × 0.005 rounded up.  For 30 nights ≈ 0.15.
_ROUNDING_TOLERANCE = Decimal('0.50')


class PricingError(ValueError):
    """Raised when pricing inputs are invalid and cannot be normalized."""
    pass


class PricingResult:
    """Immutable result from :func:`compute_pricing_from_mode`."""
    __slots__ = (
        'pricing_mode', 'nights',
        'standard_rate', 'standard_total',
        'rate_per_night', 'charged_total',
        'adjustment_amount', 'adjustment_type',
        'discount_amount', 'discount_reason',
        'discount_authorized_by', 'discount_given_by',
        'warnings',
    )

    def __init__(self, **kw):
        for k, v in kw.items():
            object.__setattr__(self, k, v)
        object.__setattr__(self, 'warnings', kw.get('warnings', []))

    def as_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def compute_pricing_from_mode(
    *,
    pricing_mode: str,
    standard_rate,
    nights: int,
    entered_per_night=None,
    entered_stay_total=None,
    discount_amount=None,
    discount_reason: str = '',
    discount_authorized_by: str = '',
    discount_given_by: str = '',
) -> PricingResult:
    """
    Server-authoritative pricing computation.

    Parameters
    ----------
    pricing_mode : str
        One of ``'standard'``, ``'per_night'``, ``'total_stay'``,
        ``'discount_on_total'``.
    standard_rate : numeric
        Room-type base rate per night (excl. GST).
    nights : int
        Number of nights (must be >= 1).
    entered_per_night : numeric, optional
        Raw user-entered per-night rate (for ``per_night`` mode).
    entered_stay_total : numeric, optional
        Raw user-entered total stay amount (for ``total_stay`` mode).
    discount_amount : numeric, optional
        Discount off standard total (for ``discount_on_total`` mode).
    discount_reason, discount_authorized_by, discount_given_by : str
        Audit fields for discount mode.

    Returns
    -------
    PricingResult
        All computed pricing values, ready to persist.

    Raises
    ------
    PricingError
        If mandatory inputs are missing or invalid.
    """
    import logging
    _log = logging.getLogger('app.pricing')
    warnings = []

    # ── Normalize inputs via Decimal ────────────────────────────────
    std_rate = money(standard_rate)
    if std_rate < ZERO:
        raise PricingError('Standard rate cannot be negative.')

    if nights is None or nights < 1:
        _log.warning('Nights was %r, normalizing to 1', nights)
        nights = 1
        warnings.append('Nights normalized to 1.')

    std_total = money(std_rate * nights)
    pricing_mode = (pricing_mode or 'standard').strip().lower()
    disc_amt = ZERO

    # ── Mode dispatch ───────────────────────────────────────────────
    if pricing_mode == 'per_night':
        pn = money(entered_per_night)
        if pn <= ZERO:
            raise PricingError(
                'Per-night rate must be > 0. '
                'Received: %s' % entered_per_night
            )
        rate = pn
        charged = money(rate * nights)

    elif pricing_mode == 'total_stay':
        total_raw = money(entered_stay_total)
        if total_raw <= ZERO:
            raise PricingError(
                'Total stay amount must be > 0. '
                'Received: %s' % entered_stay_total
            )
        charged = total_raw
        # Derive per-night rate; distribute rounding remainder to last night
        rate = money(charged / nights)

        # ── Consistency assertion: rate * nights must reconcile ──
        reconstructed = money(rate * nights)
        remainder = charged - reconstructed
        if abs(remainder) > _ROUNDING_TOLERANCE:
            _log.error(
                'PRICING INTEGRITY FAIL: mode=total_stay charged=%s '
                'rate=%s nights=%d reconstructed=%s remainder=%s',
                charged, rate, nights, reconstructed, remainder
            )
            raise PricingError(
                'Rounding inconsistency: the entered total and computed rate '
                'diverge beyond acceptable limits (off by %s).' % remainder
            )
        if remainder != ZERO:
            # Normal rounding gap — log for traceability, distribute at
            # invoice time via distribute_nightly_charges().
            _log.info(
                'PRICING ROUNDING: %s / %d nights = %s/night '
                '(remainder %s will be distributed to final night)',
                charged, nights, rate, remainder
            )

    elif pricing_mode == 'discount_on_total':
        disc_raw = money(discount_amount)
        if disc_raw < ZERO:
            raise PricingError('Discount amount cannot be negative.')
        if disc_raw > std_total:
            disc_raw = std_total
            warnings.append('Discount capped at standard total ₹%s.' % std_total)
        disc_amt = disc_raw
        charged = money(std_total - disc_amt)
        rate = money(charged / nights) if nights > 0 else ZERO

        # Validation: require reason and authorization
        if disc_amt > ZERO:
            if not (discount_reason or '').strip():
                raise PricingError('Discount reason is required when discount > 0.')
            if not (discount_authorized_by or '').strip():
                raise PricingError('Authorized-by is required when discount > 0.')

    else:
        # standard — no modification
        pricing_mode = 'standard'
        rate = std_rate
        charged = std_total

    # ── Final consistency assertion (all modes) ─────────────────────
    expected_total = money(rate * nights)
    diff = abs(charged - expected_total)
    if diff > _ROUNDING_TOLERANCE:
        _log.error(
            'PRICING CONSISTENCY FAIL: mode=%s rate=%s nights=%d '
            'charged=%s expected=%s diff=%s',
            pricing_mode, rate, nights, charged, expected_total, diff
        )
        # Normalize: trust charged_total, recompute rate
        rate = money(charged / nights)
        warnings.append(
            'Rate normalized from consistency check: ₹%s/night.' % rate
        )

    # ── Adjustment ──────────────────────────────────────────────────
    adj = money(charged - std_total)
    if adj < -SETTLEMENT_TOLERANCE:
        adj_type = 'LEAKAGE'
    elif adj > SETTLEMENT_TOLERANCE:
        adj_type = 'UPSELL'
    else:
        adj_type = None

    _log.info(
        'PRICING OK [mode=%s] std_rate=%s nights=%d std_total=%s '
        'rate_per_night=%s charged_total=%s adj=%s(%s)%s',
        pricing_mode, std_rate, nights, std_total,
        rate, charged, adj, adj_type or 'NONE',
        ' WARNINGS: ' + '; '.join(warnings) if warnings else ''
    )

    return PricingResult(
        pricing_mode=pricing_mode,
        nights=nights,
        standard_rate=round2(std_rate),
        standard_total=round2(std_total),
        rate_per_night=round2(rate),
        charged_total=round2(charged),
        adjustment_amount=round2(adj),
        adjustment_type=adj_type,
        discount_amount=round2(disc_amt),
        discount_reason=(discount_reason or '').strip() or None,
        discount_authorized_by=(discount_authorized_by or '').strip() or None,
        discount_given_by=(discount_given_by or '').strip() or None,
        warnings=warnings,
    )


def distribute_nightly_charges(charged_total, nights: int) -> list:
    """
    Split *charged_total* into *nights* nightly amounts that sum exactly.

    Uses banker's distribution: equal amounts with remainder added to the
    last night, ensuring the sum always reconciles.

    >>> distribute_nightly_charges(1000, 3)
    [333.33, 333.33, 333.34]
    >>> sum(distribute_nightly_charges(1000, 3))
    1000.0
    """
    total = money(charged_total)
    base = money(total / nights)
    amounts = [round2(base)] * nights
    remainder = round2(total - money(sum(Decimal(str(a)) for a in amounts)))
    if remainder != 0:
        amounts[-1] = round(amounts[-1] + remainder, 2)
    return amounts
