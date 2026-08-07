"""
OTA Settlement Service — Phase 1
=================================
Helpers for routing OTA prepaid revenue to the correct receivable head
without hardcoding OTA names in business logic.

Key principles:
- OTA heads are stored in PaymentMode with ``category='ota_receivable'``
- OTA source → head mapping uses the head's ``code`` field, not name
- Room revenue for paid-at-OTA reservations settles to an ota_receivable head
- Extras can still be settled via direct_payment heads

Public API:
    is_ota_prepaid(reservation) -> bool
    suggest_ota_settlement_head(ota_source) -> PaymentMode | None
    get_ota_receivable_heads() -> list[PaymentMode]
    get_direct_payment_modes() -> list[PaymentMode]
    compute_ota_outstanding() -> dict
    compute_ota_settlements_today(business_date) -> dict
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from app.models import db, PaymentMode, Payment, Reservation
from app.financial import money, ZERO

_log = logging.getLogger('app.ota_settlement')


# ---------------------------------------------------------------------------
# OTA source → settlement head code mapping
# ---------------------------------------------------------------------------
# Matches OTA_SOURCES in ota.py; resolved to PaymentMode by code.
# Keys are lowercased for case-insensitive matching.
_OTA_SOURCE_TO_CODE = {
    'makemytrip':   'MMT_PAID',
    'mmt':          'MMT_PAID',
    'goibibo':      'GOIBIBO_PAID',
    'booking.com':  'BOOKING_PAID',
    'bookingcom':   'BOOKING_PAID',
    'booking':      'BOOKING_PAID',
    'agoda':        'AGODA_PAID',
    'expedia':      'EXPEDIA_PAID',
    'airbnb':       'AIRBNB_PAID',
    'yatra':        'YATRA_PAID',
    'easemytrip':   'EASEMYTRIP_PAID',
}

_DEFAULT_OTA_CODE = 'OTHER_OTA_PAID'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_ota_prepaid(reservation) -> bool:
    """True if this reservation was paid at OTA and room revenue should
    settle to an ota_receivable head."""
    if reservation is None:
        return False
    return (getattr(reservation, 'ota_payment_status', None) == 'paid_at_ota')


def suggest_ota_settlement_head(ota_source: Optional[str]) -> Optional[PaymentMode]:
    """
    Given an OTA source name (e.g. 'MakeMyTrip', 'Booking.com'), return
    the matching ``PaymentMode`` with category='ota_receivable'.

    Falls back to 'Other OTA Paid' if the source is unknown.
    Returns ``None`` if no ota_receivable head exists in Masters.
    """
    code = _resolve_code(ota_source)
    pm = PaymentMode.query.filter_by(code=code, is_active=True).first()
    if pm:
        return pm
    # Fallback: try the default "Other OTA Paid" head
    pm = PaymentMode.query.filter_by(code=_DEFAULT_OTA_CODE, is_active=True).first()
    if pm:
        _log.info('OTA head fallback: source=%s → %s', ota_source, pm.name)
        return pm
    # Last-resort: any ota_receivable head
    pm = PaymentMode.query.filter_by(category='ota_receivable', is_active=True).first()
    if pm:
        _log.warning('OTA head fallback: no code match for %s, using %s',
                     ota_source, pm.name)
    return pm


def _resolve_code(ota_source: Optional[str]) -> str:
    """Normalize an OTA source string to a settlement head code."""
    if not ota_source:
        return _DEFAULT_OTA_CODE
    key = str(ota_source).strip().lower()
    # Try exact match
    if key in _OTA_SOURCE_TO_CODE:
        return _OTA_SOURCE_TO_CODE[key]
    # Try substring match (handles "MakeMyTrip.com", "MMT India", etc.)
    for src, code in _OTA_SOURCE_TO_CODE.items():
        if src in key:
            return code
    return _DEFAULT_OTA_CODE


def get_ota_receivable_heads() -> list:
    """Return all active OTA receivable heads, ordered by name."""
    return (PaymentMode.query
            .filter_by(category='ota_receivable', is_active=True)
            .order_by(PaymentMode.name)
            .all())


def get_direct_payment_modes() -> list:
    """Return all active direct-payment modes, ordered by name."""
    return (PaymentMode.query
            .filter_by(category='direct_payment', is_active=True)
            .order_by(PaymentMode.name)
            .all())


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def compute_ota_settlements_today(business_date: date) -> dict:
    """
    Return OTA settlement totals for *business_date*, grouped by head.

    Returns:
        {
            'by_head': {head_name: {'amount': Decimal, 'count': int, 'code': str}, ...},
            'total_amount': Decimal,
            'total_count': int,
        }
    """
    from sqlalchemy import func as _sqlfunc

    rows = (db.session.query(Payment, PaymentMode)
            .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
            .filter(PaymentMode.category == 'ota_receivable',
                    Payment.is_voided == False,
                    Payment.payment_date == business_date)
            .all())

    by_head = {}
    total_amt = ZERO
    total_count = 0
    for p, pm in rows:
        amt = money(p.amount)
        slot = by_head.setdefault(pm.name, {
            'amount': ZERO, 'count': 0, 'code': pm.code or ''})
        slot['amount'] = slot['amount'] + amt
        slot['count'] += 1
        total_amt += amt
        total_count += 1

    return {
        'by_head': by_head,
        'total_amount': total_amt,
        'total_count': total_count,
    }


def compute_ota_outstanding() -> dict:
    """
    Return lifetime OTA receivable balances — sum of all non-voided
    payments posted to ota_receivable heads.

    Phase 1 definition: this is the *gross* outstanding balance.
    Reconciliation / payout matching is deferred to Phase 2.

    Returns:
        {
            'by_head': {head_name: {'amount': Decimal, 'count': int, 'code': str}, ...},
            'total_amount': Decimal,
            'total_count': int,
        }
    """
    rows = (db.session.query(Payment, PaymentMode)
            .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
            .filter(PaymentMode.category == 'ota_receivable',
                    Payment.is_voided == False)
            .all())

    by_head = {}
    total_amt = ZERO
    total_count = 0
    for p, pm in rows:
        amt = money(p.amount)
        slot = by_head.setdefault(pm.name, {
            'amount': ZERO, 'count': 0, 'code': pm.code or ''})
        slot['amount'] = slot['amount'] + amt
        slot['count'] += 1
        total_amt += amt
        total_count += 1

    return {
        'by_head': by_head,
        'total_amount': total_amt,
        'total_count': total_count,
    }


def split_payment_totals(payment_mode_totals: dict) -> dict:
    """
    Given a dict of {mode_name: amount}, split into direct vs OTA totals.

    Input:  {'Cash': 5000, 'UPI': 2000, 'MMT Paid': 3000}
    Output: {
        'direct_total': 7000,
        'ota_total': 3000,
        'direct_by_mode': {'Cash': 5000, 'UPI': 2000},
        'ota_by_head': {'MMT Paid': 3000},
    }
    """
    # Build name → category lookup once
    all_modes = PaymentMode.query.all()
    cat_by_name = {m.name: m.category for m in all_modes}

    direct_total = ZERO
    ota_total = ZERO
    direct_by_mode = {}
    ota_by_head = {}
    for mode_name, amt in payment_mode_totals.items():
        amt_d = money(amt)
        cat = cat_by_name.get(mode_name, 'direct_payment')
        if cat == 'ota_receivable':
            ota_total += amt_d
            ota_by_head[mode_name] = amt_d
        else:
            direct_total += amt_d
            direct_by_mode[mode_name] = amt_d

    return {
        'direct_total': direct_total,
        'ota_total': ota_total,
        'direct_by_mode': direct_by_mode,
        'ota_by_head': ota_by_head,
    }
