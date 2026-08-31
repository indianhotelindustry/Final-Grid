"""
GST Service — FinalGrid (India)
==============================
GST slabs as per CGST (Rate) Notification No. 03/2022 (effective 18 Jul 2022):

  All room tariffs                  → 12% GST  (6% CGST + 6% SGST  OR  12% IGST)
  Declared tariff > ₹7,500/night   → 18% GST  (9% CGST + 9% SGST  OR  18% IGST)

Note: The earlier Nil (0%) slab for tariff ≤ ₹1,000 was REMOVED effective 18 Jul 2022.

Rate selection priority:
  1. Room type's ``gst_rate`` field (if set and > 0)  →  room_type_override
  2. Fallback slab based on per-night tariff           →  slab_fallback

IGST applies when billing party's state ≠ hotel's state (interstate supply).

Tax lines are IMMUTABLE once stored — historical invoices remain accurate
even if GST rates or settings change later.

SAC Codes used:
  Room accommodation  : 996311
  Restaurant / F&B    : 996331  (5% without ITC — no separate liquor SAC here)
  Laundry             : 998523
  Telephone / Internet: 998432
  Other hotel services: 996319
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from datetime import date, timedelta
from typing import NamedTuple

from app.models import ExtraCharge, Reservation, Settings, TaxLine, db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TWO   = Decimal('0.01')
THREE = Decimal('0.001')

# ---------------------------------------------------------------------------
# Configurable GST policy slabs
# ---------------------------------------------------------------------------
# hotel_gst_policy setting selects which slab table to use.
# Room-type-level gst_rate always overrides the slab.

_GST_POLICIES = {
    'standard_12_18': {
        'label': 'Standard 12%/18% (post Jul 2022)',
        'slabs': [
            (Decimal('7500'), Decimal('12')),
            (Decimal('Inf'),  Decimal('18')),
        ],
    },
    'new_5_18': {
        'label': 'Budget 0%/5%/18% (pre Jul 2022 / special zones)',
        'slabs': [
            (Decimal('1000'), Decimal('0')),
            (Decimal('7500'), Decimal('5')),
            (Decimal('Inf'),  Decimal('18')),
        ],
    },
}

# Default policy when not configured
_DEFAULT_POLICY = 'standard_12_18'


def get_gst_policy() -> str:
    """Return the active hotel GST policy key from Settings."""
    val = _setting('hotel_gst_policy', _DEFAULT_POLICY).strip()
    if val not in _GST_POLICIES:
        return _DEFAULT_POLICY
    return val


def get_gst_policy_slabs(policy: str | None = None) -> list:
    """Return the slab list for the given (or active) policy."""
    key = policy or get_gst_policy()
    return _GST_POLICIES.get(key, _GST_POLICIES[_DEFAULT_POLICY])['slabs']


def get_all_gst_policies() -> dict:
    """Return all available policies with labels (for admin UI)."""
    return {k: v['label'] for k, v in _GST_POLICIES.items()}

# Default GST rate per POS / extra-charge category
_CATEGORY_RATES: dict[str, Decimal] = {
    'Restaurant':   Decimal('5'),
    'Room Service': Decimal('5'),
    'Bar':          Decimal('18'),
    'Laundry':      Decimal('18'),
    'Minibar':      Decimal('18'),
    'Telephone':    Decimal('18'),
    'Other':        Decimal('18'),
}

_CATEGORY_SAC: dict[str, str] = {
    'Restaurant':   '996331',
    'Room Service': '996331',
    'Bar':          '996331',
    'Laundry':      '998523',
    'Minibar':      '996319',
    'Telephone':    '998432',
    'Other':        '996319',
}

ROOM_SAC = '996311'


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _setting(key: str, default: str = '') -> str:
    row = Settings.query.filter_by(key=key).first()
    return (row.value or default) if row else default


def get_hotel_state_code() -> str:
    return _setting('hotel_state_code', '07').strip()


def get_hotel_gstin() -> str:
    return _setting('hotel_gstin', '').strip()


def get_hotel_address() -> str:
    return _setting('hotel_address', '').strip()


def is_interstate(billing_state_code: str | None) -> bool:
    """True → IGST applies; False → CGST+SGST applies."""
    if not billing_state_code:
        return False
    return billing_state_code.strip() != get_hotel_state_code()


# ---------------------------------------------------------------------------
# Rate lookups
# ---------------------------------------------------------------------------

def get_room_gst_rate(tariff: Decimal, room_type=None) -> Decimal:
    """
    Total GST% for a given nightly room tariff.

    Priority:
      1. ``room_type.gst_rate`` if explicitly set (> 0) and not gst_exempted
      2. 0% if ``room_type.gst_exempted`` is True
      3. Fallback slab based on tariff amount

    Returns the rate as a Decimal (e.g. ``Decimal('12')``).
    """
    rate, _source, _reason = get_room_gst_rate_detailed(tariff, room_type)
    return rate


def get_room_gst_rate_detailed(tariff: Decimal, room_type=None):
    """
    Like :func:`get_room_gst_rate` but also returns source, reason, and policy.

    Returns:
        (rate: Decimal, source: str, reason: str)

    *source* is one of:
      - ``'room_type_override'`` — room type's explicit gst_rate
      - ``'room_type_exempt'``  — room type is GST-exempted
      - ``'policy'``            — tariff-based slab from hotel_gst_policy
    """
    import logging
    _log = logging.getLogger('app.gst')

    # 1. Room type explicit exemption
    if room_type is not None:
        if getattr(room_type, 'gst_exempted', False):
            _log.info('GST rate=0%% source=room_type_exempt room_type=%s',
                      getattr(room_type, 'name', '?'))
            return Decimal('0'), 'room_type_exempt', \
                f'Room type "{room_type.name}" is GST-exempted'

    # 2. Room type explicit rate (> 0)
    if room_type is not None:
        rt_rate = getattr(room_type, 'gst_rate', None)
        if rt_rate is not None:
            rt_rate_d = Decimal(str(rt_rate))
            if rt_rate_d > 0:
                _log.info('GST rate=%s%% source=room_type_override room_type=%s',
                          rt_rate_d, getattr(room_type, 'name', '?'))
                return rt_rate_d, 'room_type_override', \
                    f'Room type "{room_type.name}" gst_rate={rt_rate_d}%'

    # 3. Policy-based slab fallback
    policy_key = get_gst_policy()
    slabs = get_gst_policy_slabs(policy_key)
    for upper, rate in slabs:
        if tariff <= upper:
            reason = (f'Policy "{policy_key}": tariff {tariff}/night '
                      f'<= {upper} slab -> {rate}% GST')
            _log.info('GST rate=%s%% source=policy policy=%s tariff=%s',
                      rate, policy_key, tariff)
            return rate, 'policy', reason

    _log.info('GST rate=18%% source=policy policy=%s tariff=%s (above all slabs)',
              policy_key, tariff)
    return Decimal('18'), 'policy', \
        f'Policy "{policy_key}": tariff {tariff}/night above all slabs -> 18% GST'


def get_category_gst_rate(category: str) -> Decimal:
    """
    Total GST% for a POS / extra-charge category.
    Category rate can be overridden in Settings: key = 'gst_rate_<category_slug>'.
    """
    slug = category.lower().replace(' ', '_').replace('/', '_')
    override = _setting(f'gst_rate_{slug}')
    if override:
        try:
            return Decimal(override)
        except Exception:
            pass
    return _CATEGORY_RATES.get(category, Decimal('18'))


# ---------------------------------------------------------------------------
# Core computation (pure — no DB writes)
# ---------------------------------------------------------------------------

class TaxBreakdown(NamedTuple):
    taxable_amount: Decimal
    cgst_rate:      Decimal
    cgst_amount:    Decimal
    sgst_rate:      Decimal
    sgst_amount:    Decimal
    igst_rate:      Decimal
    igst_amount:    Decimal
    total_tax:      Decimal
    total_with_tax: Decimal
    is_interstate:  bool
    is_exempted:    bool


def compute_tax(
    taxable_amount: Decimal,
    gst_rate: Decimal,
    interstate: bool = False,
) -> TaxBreakdown:
    """
    Compute CGST+SGST (intrastate) or IGST (interstate).
    gst_rate is the TOTAL GST% (e.g. 12 → 6% CGST + 6% SGST).
    """
    amt = Decimal(str(taxable_amount)).quantize(TWO, rounding=ROUND_HALF_UP)

    if gst_rate == 0:
        return TaxBreakdown(
            taxable_amount=amt,
            cgst_rate=Decimal('0'), cgst_amount=Decimal('0'),
            sgst_rate=Decimal('0'), sgst_amount=Decimal('0'),
            igst_rate=Decimal('0'), igst_amount=Decimal('0'),
            total_tax=Decimal('0'),
            total_with_tax=amt,
            is_interstate=interstate,
            is_exempted=True,
        )

    if interstate:
        igst_rate = gst_rate
        igst_amt  = (amt * igst_rate / 100).quantize(TWO, rounding=ROUND_HALF_UP)
        return TaxBreakdown(
            taxable_amount=amt,
            cgst_rate=Decimal('0'), cgst_amount=Decimal('0'),
            sgst_rate=Decimal('0'), sgst_amount=Decimal('0'),
            igst_rate=igst_rate, igst_amount=igst_amt,
            total_tax=igst_amt,
            total_with_tax=(amt + igst_amt).quantize(TWO),
            is_interstate=True,
            is_exempted=False,
        )
    else:
        half = (gst_rate / 2).quantize(THREE)
        cgst = (amt * half / 100).quantize(TWO, rounding=ROUND_HALF_UP)
        sgst = (amt * half / 100).quantize(TWO, rounding=ROUND_HALF_UP)
        total = cgst + sgst
        return TaxBreakdown(
            taxable_amount=amt,
            cgst_rate=half, cgst_amount=cgst,
            sgst_rate=half, sgst_amount=sgst,
            igst_rate=Decimal('0'), igst_amount=Decimal('0'),
            total_tax=total,
            total_with_tax=(amt + total).quantize(TWO),
            is_interstate=False,
            is_exempted=False,
        )


# ---------------------------------------------------------------------------
# TaxLine builders — do NOT commit, caller commits
# ---------------------------------------------------------------------------

def _build_tax_lines(
    reservation_id: int,
    source_type: str,
    source_id: str,
    charge_date: date,
    taxable_amount: Decimal,
    gst_rate: Decimal,
    interstate: bool,
    sac_code: str = '',
) -> list[TaxLine]:
    """
    Build 1–2 TaxLine objects for a single charge amount.
    Returns unsaved ORM objects.
    """
    bd = compute_tax(taxable_amount, gst_rate, interstate)
    kwargs_base = dict(
        reservation_id=reservation_id,
        charge_source_type=source_type,
        charge_source_id=source_id,
        charge_date=charge_date,
        taxable_amount=bd.taxable_amount,
        is_interstate=interstate,
        is_exempted=bd.is_exempted,
        sac_code=sac_code,
    )

    if bd.is_exempted:
        return [TaxLine(tax_type='EXEMPT', tax_rate=Decimal('0'),
                        tax_amount=Decimal('0'), **kwargs_base)]

    if interstate:
        return [TaxLine(tax_type='IGST', tax_rate=bd.igst_rate,
                        tax_amount=bd.igst_amount, **kwargs_base)]

    return [
        TaxLine(tax_type='CGST', tax_rate=bd.cgst_rate,
                tax_amount=bd.cgst_amount, **kwargs_base),
        TaxLine(tax_type='SGST', tax_rate=bd.sgst_rate,
                tax_amount=bd.sgst_amount, **kwargs_base),
    ]


def _already_has_tax(reservation_id: int, source_type: str, source_id: str) -> bool:
    return TaxLine.query.filter_by(
        reservation_id=reservation_id,
        charge_source_type=source_type,
        charge_source_id=source_id,
    ).first() is not None


def generate_room_tax_lines(reservation: Reservation) -> list[TaxLine]:
    """
    Generate TaxLine records for all room nights not yet covered.
    Does NOT commit.

    **Phase C.1:** Uses ReservationNightRate rows when available for
    per-night pricing truth.  Falls back to legacy ``rate_per_night``
    average when no nightly rows exist or validation fails.

    GST rate priority: room_type.gst_rate (if set) > policy slab.
    """
    import logging
    _log = logging.getLogger('app.gst')

    interstate = is_interstate(reservation.billing_state_code)
    room_type  = reservation.room_type

    # ── Try nightly rows (Phase C.1) ────────────────────────────────
    nightly_map = None  # date → final_rate
    _source_label = 'legacy_average_fallback'

    try:
        from app.models import ReservationNightRate
        from app.nightly_rate_service import validate_nightly_rows
        validation = validate_nightly_rows(reservation)

        if validation['rows']:
            # Check for blocking failures only — warnings are acceptable
            blocking = [w for w in validation['warnings']
                        if w.startswith(('MISSING_DATES', 'DUPLICATE_DATES'))]
            if blocking:
                _log.warning(
                    'generate_room_tax_lines: res=%d using validation_fallback '
                    'due to: %s', reservation.id, '; '.join(blocking))
                _source_label = 'validation_fallback'
            else:
                nightly_map = {r.stay_date: Decimal(str(r.final_rate))
                               for r in validation['rows']}
                _source_label = 'nightly_rows'
    except Exception as _nr_err:
        _log.warning(
            'generate_room_tax_lines: res=%d nightly row lookup failed (%s), '
            'using legacy fallback', reservation.id, _nr_err)

    # ── Generate tax lines per night ────────────────────────────────
    legacy_tariff = Decimal(str(reservation.rate_per_night))
    lines: list[TaxLine] = []
    current = reservation.arrival_date

    while current < reservation.departure_date:
        sid = f'night_{current.isoformat()}'
        if not _already_has_tax(reservation.id, 'room_night', sid):
            # Determine taxable amount for this night
            if nightly_map and current in nightly_map:
                tariff = nightly_map[current]
            else:
                tariff = legacy_tariff

            gst_rate, _gs, _gr = get_room_gst_rate_detailed(tariff, room_type)

            new = _build_tax_lines(
                reservation_id=reservation.id,
                source_type='room_night',
                source_id=sid,
                charge_date=current,
                taxable_amount=tariff,
                gst_rate=gst_rate,
                interstate=interstate,
                sac_code=ROOM_SAC,
            )
            for tl in new:
                db.session.add(tl)
            lines.extend(new)
        current += timedelta(days=1)

    _log.info(
        'generate_room_tax_lines: res=%d source=%s nights=%d lines=%d',
        reservation.id, _source_label,
        (reservation.departure_date - reservation.arrival_date).days,
        len(lines))

    return lines


_CICO_CHARGE_TYPES = {'early_checkin', 'late_checkout'}

# Charge types that follow the *room* GST rate (not the category default).
# Includes early-checkin / late-checkout (sold as accommodation services)
# AND 'room_upsell' — the corrective row posted when the front desk
# converts an above-tariff overpayment into upsell revenue. For upsells,
# the GST rate must match the room's rate so the new bill grand_total
# ties out to what the guest actually paid.
_ROOM_GST_RATE_CHARGE_TYPES = _CICO_CHARGE_TYPES | {'room_upsell'}

# Charge types created by the overpayment-resolution flow that move guest
# funds between buckets WITHOUT representing a new taxable supply. They
# clear a negative balance (the guest paid > bill) by reclassifying the
# excess as a tip or non-room income line — neither is a service we
# rendered, so neither attracts GST. Kept as a constant so the GST engine
# (compute_stay_gst, generate_extra_charge_tax_lines) and any future
# reporting code use the same set.
_NON_TAXABLE_ADJUSTMENT_CHARGE_TYPES = {'tip', 'other_income'}


def compute_stay_gst(reservation) -> Decimal:
    """Fast, side-effect-free GST total for a reservation.

    Calculates what the GST WOULD be if we generated tax lines right now,
    using the same rate-resolution rules as generate_room_tax_lines /
    generate_extra_charge_tax_lines — but WITHOUT writing any TaxLine
    rows or committing anything. Safe to call from hot paths
    (calculate_stay_amount, checkout, reports).

    Inclusive vs exclusive is a quoting convention only: room_type.base_rate
    (and therefore reservation.rate_per_night) is ALWAYS stored pre-tax, so
    GST is consistently computed on top of the pre-tax room_charges. For
    inclusive-priced rooms, `grand_total = pre-tax × (1 + rate%)` recovers
    the original sticker price the guest was quoted.

    Excludes night-audit room_rent ExtraCharges from the extras loop
    (they are the room, not real extras). Matches the single-source fix.
    """
    from app.services import is_room_rent_charge, get_room_revenue

    room_type = getattr(reservation, 'room_type', None)
    tariff = Decimal(str(getattr(reservation, 'rate_per_night', 0) or 0))

    # Room GST — flat rate on total room revenue for the stay.
    room_rate = get_room_gst_rate(tariff, room_type)
    room_revenue = Decimal(str(get_room_revenue(reservation)))
    room_gst = (room_revenue * room_rate / Decimal('100')).quantize(TWO)

    # Extras GST — category-based (CICO gets the room rate).
    extras_gst = Decimal('0')
    for ec in (getattr(reservation, 'extra_charges', None) or []):
        if is_room_rent_charge(ec):
            continue
        ct = getattr(ec, 'charge_type', None)
        # Overpayment-resolution rows (tip / other_income) are funds
        # reclassification, not a taxable supply — skip GST entirely.
        if ct in _NON_TAXABLE_ADJUSTMENT_CHARGE_TYPES:
            continue
        amount = Decimal(str(ec.amount or 0))
        if ct in _ROOM_GST_RATE_CHARGE_TYPES:
            rate = room_rate
        else:
            category = getattr(ec, 'charge_category', None) \
                       or (ec.description or '').split('—')[0].split('-')[0].strip()
            rate = get_category_gst_rate(category)
        extras_gst += (amount * rate / Decimal('100')).quantize(TWO)

    return (room_gst + extras_gst).quantize(TWO)


def generate_extra_charge_tax_lines(
    extra_charge: ExtraCharge,
    reservation: Reservation,
) -> list[TaxLine]:
    """Generate TaxLine for one ExtraCharge. Does NOT commit."""
    sid = str(extra_charge.id)
    if _already_has_tax(reservation.id, 'extra_charge', sid):
        return []

    # Skip night-audit room_rent rows. Room-night GST is produced
    # once by generate_room_tax_lines (sourced from ReservationNightRate
    # or rate_per_night). Creating tax lines on the derived room_rent
    # ExtraCharge would double the GST on the invoice.
    ct = getattr(extra_charge, 'charge_type', None)
    if ct == 'room_rent':
        return []

    # Tip / Other Income overpayment-resolution rows are funds
    # reclassification, not a taxable supply (no service rendered).
    # Skip TaxLine generation; matches compute_stay_gst's exemption.
    if ct in _NON_TAXABLE_ADJUSTMENT_CHARGE_TYPES:
        return []

    # Room-rate charges (CICO + room_upsell) are treated as accommodation
    # services and therefore follow the room's GST rate, not a fixed category rate.
    # CICO = early_checkin / late_checkout sold as accommodation;
    # room_upsell = corrective row when front desk converts an above-tariff
    # overpayment into recognised upsell revenue.
    if ct in _ROOM_GST_RATE_CHARGE_TYPES:
        tariff     = Decimal(str(reservation.rate_per_night or 0))
        rate       = get_room_gst_rate(tariff, reservation.room_type)
        sac        = ROOM_SAC
        interstate = is_interstate(reservation.billing_state_code)
        lines = _build_tax_lines(
            reservation_id=reservation.id,
            source_type='extra_charge',
            source_id=sid,
            charge_date=extra_charge.charge_date,
            taxable_amount=Decimal(str(extra_charge.amount)),
            gst_rate=rate,
            interstate=interstate,
            sac_code=sac,
        )
        for tl in lines:
            db.session.add(tl)
        return lines

    # Use explicit charge_category if set; fall back to description inference for legacy data
    category = getattr(extra_charge, 'charge_category', None)
    if not category:
        category = extra_charge.description.split('—')[0].split('-')[0].strip()
    rate      = get_category_gst_rate(category)
    sac       = _CATEGORY_SAC.get(category, '996319')
    interstate = is_interstate(reservation.billing_state_code)

    lines = _build_tax_lines(
        reservation_id=reservation.id,
        source_type='extra_charge',
        source_id=sid,
        charge_date=extra_charge.charge_date,
        taxable_amount=Decimal(str(extra_charge.amount)),
        gst_rate=rate,
        interstate=interstate,
        sac_code=sac,
    )
    for tl in lines:
        db.session.add(tl)
    return lines


def ensure_all_tax_lines(reservation: Reservation) -> None:
    """
    Idempotent: generate all missing tax lines for a reservation.
    Covers room nights + extra charges. Commits at the end.

    Room-night GST is produced exclusively by generate_room_tax_lines
    (which reads ReservationNightRate / rate_per_night). The night audit
    also posts one ExtraCharge per night with charge_type='room_rent',
    but those rows are a DERIVED ledger artefact and must not be taxed
    a second time — generate_extra_charge_tax_lines skips them.
    """
    generate_room_tax_lines(reservation)
    for ec in reservation.extra_charges:
        if (getattr(ec, 'charge_type', None) or '') == 'room_rent':
            continue   # defence in depth — generator also skips these
        generate_extra_charge_tax_lines(ec, reservation)
    db.session.commit()


# ---------------------------------------------------------------------------
# Folio GST summary — used by invoice route and GST report
# ---------------------------------------------------------------------------

class FolioGSTSummary(NamedTuple):
    taxable_amount: Decimal   # total pre-tax charges
    cgst:           Decimal
    sgst:           Decimal
    igst:           Decimal
    total_tax:      Decimal
    grand_total:    Decimal   # taxable + tax
    lines:          list      # all TaxLine objects for this reservation


def _ids_of_room_rent_extras(reservation_id: int) -> set[str]:
    """IDs of ExtraCharges with charge_type='room_rent' for this reservation.

    Used to filter legacy TaxLine rows that were created for room_rent
    ExtraCharges BEFORE the fix. We never delete those rows (data safety);
    we just stop counting them in aggregation.
    """
    try:
        rows = (db.session.query(ExtraCharge.id)
                .filter(ExtraCharge.reservation_id == reservation_id,
                        ExtraCharge.charge_type == 'room_rent').all())
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def get_folio_gst_summary(reservation: Reservation) -> FolioGSTSummary:
    """
    Ensure tax lines exist, then aggregate them into invoice-ready totals.
    This is the main entry point for the invoice route.
    """
    ensure_all_tax_lines(reservation)

    tls = TaxLine.query.filter_by(reservation_id=reservation.id).all()

    # Filter out legacy TaxLines that were created for room_rent ExtraCharges
    # (before this fix). Room-night GST is produced by generate_room_tax_lines
    # with source_type='room_night' — those are the only TaxLines we keep for
    # room revenue; any tax line pointing at a room_rent ExtraCharge is a
    # duplicate and must be excluded from totals.
    room_rent_ec_ids = _ids_of_room_rent_extras(reservation.id)

    def _is_room_rent_duplicate(tl) -> bool:
        return (tl.charge_source_type == 'extra_charge'
                and str(tl.charge_source_id) in room_rent_ec_ids)

    tls = [tl for tl in tls if not _is_room_rent_duplicate(tl)]

    # Taxable amount: counted once per unique source (avoid double-counting CGST+SGST pair)
    seen: set[tuple] = set()
    taxable = Decimal('0')
    for tl in tls:
        key = (tl.charge_source_type, tl.charge_source_id)
        if key not in seen:
            taxable += Decimal(str(tl.taxable_amount))
            seen.add(key)

    cgst = sum((Decimal(str(tl.tax_amount)) for tl in tls if tl.tax_type == 'CGST'), Decimal('0'))
    sgst = sum((Decimal(str(tl.tax_amount)) for tl in tls if tl.tax_type == 'SGST'), Decimal('0'))
    igst = sum((Decimal(str(tl.tax_amount)) for tl in tls if tl.tax_type == 'IGST'), Decimal('0'))
    total_tax = cgst + sgst + igst

    return FolioGSTSummary(
        taxable_amount=taxable.quantize(TWO),
        cgst=cgst.quantize(TWO),
        sgst=sgst.quantize(TWO),
        igst=igst.quantize(TWO),
        total_tax=total_tax.quantize(TWO),
        grand_total=(taxable + total_tax).quantize(TWO),
        lines=tls,
    )


# ---------------------------------------------------------------------------
# GST Report aggregation
# ---------------------------------------------------------------------------

def get_gst_report(from_date: date, to_date: date) -> dict:
    """
    Aggregate TaxLine records across all reservations for a date range.
    Returns data for the GST summary report.
    """
    rows = (
        TaxLine.query
        .filter(
            TaxLine.charge_date >= from_date,
            TaxLine.charge_date <= to_date,
        )
        .order_by(TaxLine.charge_date, TaxLine.reservation_id)
        .all()
    )

    # Exclude legacy TaxLines that were created for room_rent ExtraCharges
    # before the single-source-of-truth fix. Room-night GST lives on the
    # room_night source; the extra_charge source for room_rent is a
    # duplicate and must be filtered out of the report totals.
    legacy_room_rent_ec_ids = {
        str(r[0]) for r in db.session.query(ExtraCharge.id)
                             .filter(ExtraCharge.charge_type == 'room_rent').all()
    } if rows else set()

    def _is_room_rent_duplicate(tl) -> bool:
        return (tl.charge_source_type == 'extra_charge'
                and str(tl.charge_source_id) in legacy_room_rent_ec_ids)

    rows = [tl for tl in rows if not _is_room_rent_duplicate(tl)]

    # Per-rate bucket: {(gst_rate_pair, source_type): {taxable, cgst, sgst, igst, count}}
    seen_sources: set[tuple] = set()
    total_taxable = Decimal('0')
    cgst_total    = Decimal('0')
    sgst_total    = Decimal('0')
    igst_total    = Decimal('0')

    # Group by reservation + source for deduplication
    for tl in rows:
        key = (tl.reservation_id, tl.charge_source_type, tl.charge_source_id)
        if key not in seen_sources:
            total_taxable += Decimal(str(tl.taxable_amount))
            seen_sources.add(key)
        if tl.tax_type == 'CGST':
            cgst_total += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'SGST':
            sgst_total += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'IGST':
            igst_total += Decimal(str(tl.tax_amount))

    total_tax = cgst_total + sgst_total + igst_total

    # Rate-wise breakdown for GSTR-1 style summary
    from collections import defaultdict
    rate_groups: dict[str, dict] = defaultdict(lambda: {
        'taxable': Decimal('0'), 'cgst': Decimal('0'),
        'sgst': Decimal('0'), 'igst': Decimal('0'),
    })
    # Build a lookup: (reservation_id, source_type, source_id) -> rate_key for CGST lines
    cgst_rate_key_map: dict[tuple, str] = {}
    for tl in rows:
        if tl.tax_type == 'CGST':
            rate_key = f'{float(tl.tax_rate * 2):.0f}%'
            src_key = (tl.reservation_id, tl.charge_source_type, tl.charge_source_id)
            cgst_rate_key_map[src_key] = rate_key

    seen_for_rate: set[tuple] = set()
    for tl in rows:
        src_key = (tl.reservation_id, tl.charge_source_type, tl.charge_source_id)
        if tl.tax_type == 'CGST':
            rate_key = f'{float(tl.tax_rate * 2):.0f}%'
            if src_key not in seen_for_rate:
                rate_groups[rate_key]['taxable'] += Decimal(str(tl.taxable_amount))
                seen_for_rate.add(src_key)
            rate_groups[rate_key]['cgst'] += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'IGST':
            rate_key = f'{float(tl.tax_rate):.0f}% (IGST)'
            if src_key not in seen_for_rate:
                rate_groups[rate_key]['taxable'] += Decimal(str(tl.taxable_amount))
                seen_for_rate.add(src_key)
            rate_groups[rate_key]['igst'] += Decimal(str(tl.tax_amount))
        elif tl.tax_type == 'SGST':
            rate_key = cgst_rate_key_map.get(src_key)
            if rate_key:
                rate_groups[rate_key]['sgst'] += Decimal(str(tl.tax_amount))

    return {
        'rows': rows,
        'total_taxable': total_taxable.quantize(TWO),
        'cgst_total':    cgst_total.quantize(TWO),
        'sgst_total':    sgst_total.quantize(TWO),
        'igst_total':    igst_total.quantize(TWO),
        'total_tax':     total_tax.quantize(TWO),
        'grand_total':   (total_taxable + total_tax).quantize(TWO),
        'rate_groups':   dict(rate_groups),
        'from_date':     from_date,
        'to_date':       to_date,
    }
