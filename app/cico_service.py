"""
CICO Rule Engine — Check-In / Check-Out Time-Based Charge Calculator
=====================================================================
Computes early check-in and late check-out charges based on configurable
time slabs stored in the Settings table.

Charge flow:
  1. compute_early_checkin() / compute_late_checkout() → returns amount + label
  2. post_charge() → writes ExtraCharge row (idempotent)
  3. calculate_stay_amount() picks it up automatically (no changes needed there)

All charge amounts are based on rate_per_night × percentage.
"""

import json
from datetime import time as dtime
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# Settings keys
# ---------------------------------------------------------------------------
KEY_EARLY_ENABLED  = 'cico_early_enabled'
KEY_LATE_ENABLED   = 'cico_late_enabled'
KEY_EARLY_SLABS    = 'cico_early_slabs'
KEY_LATE_SLABS     = 'cico_late_slabs'
KEY_STD_CHECKIN    = 'cico_standard_checkin'
KEY_STD_CHECKOUT   = 'cico_standard_checkout'
KEY_ALLOW_WAIVE    = 'cico_allow_waive'
KEY_AUTO_POST      = 'cico_auto_post'

# ---------------------------------------------------------------------------
# Default slab definitions (used when no DB config exists)
# Each slab: {'from_hm': 'HH:MM', 'to_hm': 'HH:MM', 'pct': int, 'label': str}
# pct=0 = grace period (no charge)
# ---------------------------------------------------------------------------
DEFAULT_EARLY_SLABS = [
    {'from_hm': '04:00', 'to_hm': '06:00', 'pct': 30,
     'label': '4:00 AM – 6:00 AM'},
    {'from_hm': '06:01', 'to_hm': '08:00', 'pct': 20,
     'label': '6:01 AM – 8:00 AM'},
    {'from_hm': '08:01', 'to_hm': '10:00', 'pct': 10,
     'label': '8:01 AM – 10:00 AM'},
    {'from_hm': '10:01', 'to_hm': '11:00', 'pct':  0,
     'label': '10:01 AM – 11:00 AM (Grace)'},
]

DEFAULT_LATE_SLABS = [
    {'from_hm': '11:00', 'to_hm': '11:59', 'pct':  0,
     'label': '11:00 AM – 11:59 AM (1 Hour Buffer)'},
    {'from_hm': '12:00', 'to_hm': '14:00', 'pct': 20,
     'label': '12:00 PM – 2:00 PM'},
    {'from_hm': '14:01', 'to_hm': '16:00', 'pct': 50,
     'label': '2:01 PM – 4:00 PM'},
    {'from_hm': '16:01', 'to_hm': '23:59', 'pct': 100,
     'label': 'After 4:00 PM (Full Tariff)'},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hm(hm_str):
    """Parse 'HH:MM' string to datetime.time. Returns None on failure."""
    try:
        h, m = hm_str.strip().split(':')
        return dtime(int(h), int(m))
    except Exception:
        return None


def _to_time(value):
    """Accept dtime, 'HH:MM' string, or datetime; return dtime or None."""
    if isinstance(value, dtime):
        return value
    if isinstance(value, str):
        return _parse_hm(value)
    # datetime object
    try:
        return value.time().replace(second=0, microsecond=0)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------

def get_cico_settings():
    """
    Load CI/CO rule settings from the DB Settings table.
    Returns a dict with all rule parameters, falling back to defaults.
    """
    from app.models import Settings

    def _get(key, default=''):
        row = Settings.query.filter_by(key=key).first()
        return row.value if (row and row.value is not None) else default

    early_enabled = _get(KEY_EARLY_ENABLED, '1') == '1'
    late_enabled  = _get(KEY_LATE_ENABLED,  '1') == '1'
    allow_waive   = _get(KEY_ALLOW_WAIVE,   '1') == '1'
    auto_post     = _get(KEY_AUTO_POST,      '1') == '1'
    std_ci        = _get(KEY_STD_CHECKIN,    '11:00')
    std_co        = _get(KEY_STD_CHECKOUT,   '11:00')

    try:
        raw = _get(KEY_EARLY_SLABS, '')
        early_slabs = json.loads(raw) if raw else DEFAULT_EARLY_SLABS
    except Exception:
        early_slabs = DEFAULT_EARLY_SLABS

    try:
        raw = _get(KEY_LATE_SLABS, '')
        late_slabs = json.loads(raw) if raw else DEFAULT_LATE_SLABS
    except Exception:
        late_slabs = DEFAULT_LATE_SLABS

    if not early_slabs:
        early_slabs = DEFAULT_EARLY_SLABS
    if not late_slabs:
        late_slabs = DEFAULT_LATE_SLABS

    return {
        'early_enabled': early_enabled,
        'late_enabled':  late_enabled,
        'allow_waive':   allow_waive,
        'auto_post':     auto_post,
        'std_checkin':   std_ci,
        'std_checkout':  std_co,
        'early_slabs':   early_slabs,
        'late_slabs':    late_slabs,
    }


def save_cico_settings(data):
    """
    Persist CICO settings to the Settings table.
    data keys: same as get_cico_settings() return keys.
    """
    from app.models import Settings, db

    def _set(key, value):
        row = Settings.query.filter_by(key=key).first()
        if row:
            row.value = str(value)
        else:
            db.session.add(Settings(key=key, value=str(value)))

    _set(KEY_EARLY_ENABLED, '1' if data.get('early_enabled') else '0')
    _set(KEY_LATE_ENABLED,  '1' if data.get('late_enabled')  else '0')
    _set(KEY_ALLOW_WAIVE,   '1' if data.get('allow_waive')   else '0')
    _set(KEY_AUTO_POST,     '1' if data.get('auto_post')     else '0')
    _set(KEY_STD_CHECKIN,   data.get('std_checkin',  '11:00'))
    _set(KEY_STD_CHECKOUT,  data.get('std_checkout', '11:00'))

    if 'early_slabs' in data:
        _set(KEY_EARLY_SLABS, json.dumps(data['early_slabs']))
    if 'late_slabs' in data:
        _set(KEY_LATE_SLABS, json.dumps(data['late_slabs']))


# ---------------------------------------------------------------------------
# Core computation functions
# ---------------------------------------------------------------------------

def compute_early_checkin(rate_per_night, actual_time, nights, rules=None):
    """
    Compute the early check-in surcharge.

    Args:
        rate_per_night : Decimal/float — nightly room rate
        actual_time    : datetime.time | 'HH:MM' string | datetime
        nights         : int — number of nights booked (must be >= 1)
        rules          : dict from get_cico_settings() (loaded lazily if None)

    Returns:
        dict:
            applicable  bool   — True if the actual time falls inside a slab
            amount      float  — charge amount (0 if grace or not applicable)
            pct         int    — percentage applied (0 for grace)
            slab_label  str    — human-readable slab description
            grace       bool   — True when pct == 0 (guest gets free early CI)
    """
    if rules is None:
        rules = get_cico_settings()

    _not_applicable = {'applicable': False, 'amount': 0.0,
                       'pct': 0, 'slab_label': '', 'grace': False}

    if not rules['early_enabled']:
        return _not_applicable

    # Business rule: only charge if booking covers at least 1 full night
    if nights < 1:
        return _not_applicable

    actual_t = _to_time(actual_time)
    if actual_t is None:
        return _not_applicable

    std_ci = _parse_hm(rules['std_checkin']) or dtime(11, 0)

    # Apply only when arriving BEFORE standard check-in time
    if actual_t >= std_ci:
        return _not_applicable

    for slab in rules['early_slabs']:
        slab_from = _parse_hm(slab.get('from_hm', ''))
        slab_to   = _parse_hm(slab.get('to_hm',   ''))
        if slab_from is None or slab_to is None:
            continue
        if slab_from <= actual_t <= slab_to:
            pct   = int(slab.get('pct', 0))
            label = slab.get('label', f"{slab['from_hm']} – {slab['to_hm']}")
            grace = (pct == 0)
            amount = 0.0
            if not grace:
                amount = float(
                    (Decimal(str(rate_per_night)) * Decimal(pct) / Decimal('100'))
                    .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                )
            return {
                'applicable': True,
                'amount':     amount,
                'pct':        pct,
                'slab_label': label,
                'grace':      grace,
            }

    return _not_applicable


def compute_late_checkout(rate_per_night, actual_time, nights, rules=None):
    """
    Compute the late check-out surcharge.

    Args:
        rate_per_night : Decimal/float — nightly room rate
        actual_time    : datetime.time | 'HH:MM' string | datetime
        nights         : int — number of nights stayed (must be >= 1)
        rules          : dict from get_cico_settings()

    Returns: same shape as compute_early_checkin()
    """
    if rules is None:
        rules = get_cico_settings()

    _not_applicable = {'applicable': False, 'amount': 0.0,
                       'pct': 0, 'slab_label': '', 'grace': False}

    if not rules['late_enabled']:
        return _not_applicable

    if nights < 1:
        return _not_applicable

    actual_t = _to_time(actual_time)
    if actual_t is None:
        return _not_applicable

    std_co = _parse_hm(rules['std_checkout']) or dtime(11, 0)

    # Apply only when departing AFTER standard check-out time
    if actual_t < std_co:
        return _not_applicable

    for slab in rules['late_slabs']:
        slab_from = _parse_hm(slab.get('from_hm', ''))
        slab_to   = _parse_hm(slab.get('to_hm',   ''))
        if slab_from is None or slab_to is None:
            continue
        if slab_from <= actual_t <= slab_to:
            pct   = int(slab.get('pct', 0))
            label = slab.get('label', f"{slab['from_hm']} – {slab['to_hm']}")
            grace = (pct == 0)
            amount = 0.0
            if not grace:
                amount = float(
                    (Decimal(str(rate_per_night)) * Decimal(pct) / Decimal('100'))
                    .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                )
            return {
                'applicable': True,
                'amount':     amount,
                'pct':        pct,
                'slab_label': label,
                'grace':      grace,
            }

    return _not_applicable


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------

def already_has_charge(reservation, charge_type):
    """
    Return True if a charge of this type was already posted to this reservation.
    Checks both the charge_type column (new) and description patterns (legacy).
    """
    for ec in reservation.extra_charges:
        # New-style tag
        ct = getattr(ec, 'charge_type', None)
        if ct == charge_type:
            return True
        # Legacy description match (for records created before migration)
        desc = (ec.description or '').lower()
        if charge_type == 'early_checkin' and 'early check' in desc:
            return True
        if charge_type == 'late_checkout' and 'late check' in desc:
            return True
    return False


# ---------------------------------------------------------------------------
# Charge posting
# ---------------------------------------------------------------------------

def post_charge(reservation, charge_type, amount, slab_label,
                user_id=None, charge_date=None, pct=0, actual_time_str=None):
    """
    Post an early check-in or late check-out charge as an ExtraCharge row.
    Idempotent — does nothing and returns None if the charge already exists.

    Args:
        reservation     : Reservation ORM object
        charge_type     : 'early_checkin' | 'late_checkout'
        amount          : float — charge amount (must be > 0)
        slab_label      : str  — e.g. "04:28 AM — 30%"
        user_id         : int  — staff user id for audit log
        charge_date     : date — defaults to business date
        pct             : int  — percentage applied (for CICOChargeLog)
        actual_time_str : str  — 'HH:MM' hotel local time (for CICOChargeLog)

    Returns:
        ExtraCharge object if posted, None if skipped.
    """
    from app.models import ExtraCharge, AuditLog, CICOChargeLog, db
    from app.services import get_business_date

    if amount <= 0:
        return None

    if already_has_charge(reservation, charge_type):
        return None

    prefix = ('Early Check-in' if charge_type == 'early_checkin'
              else 'Late Check-out')
    description = f'{prefix} — {slab_label}'

    ec = ExtraCharge(
        reservation_id=reservation.id,
        description=description,
        amount=amount,
        charge_date=charge_date or get_business_date(),
        charge_type=charge_type,
    )
    db.session.add(ec)
    db.session.flush()

    # Expire the cached extra_charges collection on the reservation object.
    # already_has_charge() above loaded and cached it as an empty list; after the
    # flush the new row is in the DB but that stale cache would cause any immediate
    # calculate_stay_amount() call to report Rs 0 for extra charges.  Expiring here
    # ensures the next access re-queries the DB and picks up the posted charge,
    # regardless of what the caller does (or forgets to do) afterward.
    try:
        db.session.expire(reservation, ['extra_charges'])
    except Exception:
        pass

    # Dedicated CICO audit log
    try:
        db.session.add(CICOChargeLog(
            reservation_id=reservation.id,
            charge_type=charge_type,
            slab_label=slab_label,
            pct_applied=pct,
            amount_calculated=amount,
            actual_time_str=actual_time_str,
            outcome='posted',
            waived=False,
            extra_charge_id=ec.id,
            staff_user_id=user_id,
        ))
    except Exception:
        pass

    # Generic audit trail (for existing audit log UI)
    try:
        db.session.add(AuditLog(
            entity_type='Reservation',
            entity_id=reservation.id,
            action=f'auto_{charge_type}_charge',
            before_state={},
            after_state={
                'charge_type': charge_type,
                'amount': amount,
                'slab': slab_label,
            },
            staff_user_id=user_id,
        ))
    except Exception:
        pass

    return ec


def log_waiver(reservation, charge_type, amount, slab_label, pct,
               actual_time_str, user_id, waive_reason):
    """
    Write a CICOChargeLog record for a waived CICO charge (no ExtraCharge posted).
    Call this after confirming waiver is authorised.
    """
    from app.models import CICOChargeLog, AuditLog, db

    try:
        db.session.add(CICOChargeLog(
            reservation_id=reservation.id,
            charge_type=charge_type,
            slab_label=slab_label,
            pct_applied=pct,
            amount_calculated=amount,
            actual_time_str=actual_time_str,
            outcome='waived',
            waived=True,
            waived_by_user_id=user_id,
            waive_reason=waive_reason,
            extra_charge_id=None,
            staff_user_id=user_id,
        ))
        db.session.add(AuditLog(
            entity_type='Reservation',
            entity_id=reservation.id,
            action=f'waive_{charge_type}',
            before_state={},
            after_state={
                'charge_type': charge_type,
                'amount_waived': amount,
                'reason': waive_reason,
            },
            staff_user_id=user_id,
        ))
    except Exception:
        pass
