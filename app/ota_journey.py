"""
OTA Reservation Journey — Phase A
===================================
Single source of truth for "where is this reservation in its lifecycle"
across the OTA → Reservation → Night Audit → Settlement flow.

Designed to be called from:
- A detail page (Phase C) that renders one reservation's full story
- The CEO dashboard (Phase B) when drilling down from a funnel row
- Tests and reports that need a structured view instead of reaching
  into routes.py / services.py / ota_settlement_service.py each time.

Public API
----------
    build_journey(reservation_id) -> dict
    is_ota_reservation(reservation) -> bool
    derive_stage(reservation, money) -> str

The returned ``journey`` dict has this shape::

    {
        'reservation_id', 'is_ota', 'booking_reference',
        'ota_source', 'ota_booking_id', 'ota_payment_status',
        'guest':       {'id', 'name', 'phone', 'email'},
        'room_type':   str,
        'room_number': str | None,
        'dates':       {'arrival', 'departure', 'nights'},
        'money': {
            'rate_per_night', 'room_revenue_accrued', 'extras_posted',
            'discount', 'gross_total',
            'direct_payments_collected', 'ota_receivable_posted',
            'total_settled', 'outstanding',
        },
        'current_status',  # raw DB status
        'current_stage',   # derived high-level stage
        'has_outstanding', # bool
        'timeline':  [ {'step', 'at', 'by', 'detail', 'amount'}, ... ]
    }

All monetary values are floats (rupees). All timestamps in the
timeline are ISO-8601 strings in UTC where available (DB-stored).
The service never raises for missing related rows — it degrades to
placeholder strings so the calling UI stays stable.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.models import (
    db, Reservation, Guest, Room, RoomType,
    Payment, PaymentMode, ExtraCharge,
    AuditLog, WebhookLog,
)

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Predicates
# ──────────────────────────────────────────────────────────────────────

def is_ota_reservation(reservation: Reservation | None) -> bool:
    """True when this reservation originated from an OTA channel.

    We treat ``source == 'OTA'`` as authoritative. A reservation with an
    ``ota_booking_id`` but ``source != 'OTA'`` is unusual enough that we
    log it and still return True — the CEO view should not lose it.
    """
    if reservation is None:
        return False
    if reservation.source == 'OTA':
        return True
    if (reservation.ota_booking_id or '').strip():
        log.info(
            'ota_journey: reservation %s has ota_booking_id but source=%s',
            reservation.id, reservation.source)
        return True
    return False


# ──────────────────────────────────────────────────────────────────────
# Money breakdown
# ──────────────────────────────────────────────────────────────────────

def _f(v: Any, default: float = 0.0) -> float:
    """Coerce Decimal/str/None to float, tolerating garbage."""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _compute_money(reservation: Reservation) -> dict[str, float]:
    """Build the money block: all numbers attached to this reservation.

    Breaks out direct payments from OTA receivable postings so the
    journey view can show "settled to OTA" vs "paid in cash" separately.
    """
    rate = _f(reservation.rate_per_night)

    # Room revenue accrued = rate × nights of stay to date (or full stay
    # if checked out). Before check-in this is just the booked amount.
    nights = max(0, (reservation.departure_date - reservation.arrival_date).days)
    if reservation.checked_out_at:
        earned_nights = nights
    elif reservation.checked_in_at:
        today = date.today()
        earned_nights = max(
            0,
            (min(reservation.departure_date, today) - reservation.arrival_date).days,
        )
    else:
        earned_nights = 0
    room_revenue_accrued = round(rate * earned_nights, 2)

    # Extras posted to this reservation (POS, minibar, laundry, etc.)
    extras = 0.0
    room_rent_posted = 0.0
    try:
        rows = (ExtraCharge.query
                .filter_by(reservation_id=reservation.id)
                .all())
        for r in rows:
            amt = _f(r.amount)
            if (r.charge_type or '').lower() == 'room_rent':
                room_rent_posted += amt
            else:
                extras += amt
    except Exception as exc:
        log.warning('ota_journey: extras lookup failed for res %s: %s',
                    reservation.id, exc)

    # If room rent has been posted by night audit, prefer the posted sum
    # over the derived "rate × nights" figure — it is the authoritative
    # accrual that payments are reconciled against.
    if room_rent_posted > 0:
        room_revenue_accrued = round(room_rent_posted, 2)

    discount = _f(reservation.discount_amount)
    gross_total = round(room_revenue_accrued + extras - discount, 2)

    # Payments: split direct vs ota_receivable, ignore voided
    direct = 0.0
    ota_recv = 0.0
    try:
        rows = (db.session.query(Payment, PaymentMode)
                .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
                .filter(Payment.reservation_id == reservation.id,
                        Payment.is_voided == False)
                .all())
        for p, pm in rows:
            amt = _f(p.amount)
            if (pm.category or '') == 'ota_receivable':
                ota_recv += amt
            else:
                direct += amt
    except Exception as exc:
        log.warning('ota_journey: payments lookup failed for res %s: %s',
                    reservation.id, exc)

    total_settled = round(direct + ota_recv, 2)
    outstanding = round(gross_total - total_settled, 2)

    return {
        'rate_per_night': round(rate, 2),
        'room_revenue_accrued': room_revenue_accrued,
        'extras_posted': round(extras, 2),
        'discount': round(discount, 2),
        'gross_total': gross_total,
        'direct_payments_collected': round(direct, 2),
        'ota_receivable_posted': round(ota_recv, 2),
        'total_settled': total_settled,
        'outstanding': outstanding,
    }


# ──────────────────────────────────────────────────────────────────────
# Stage derivation
# ──────────────────────────────────────────────────────────────────────

# Canonical, high-level stages the UI renders as a horizontal progress
# bar. Multiple raw DB statuses can map to the same stage, and the
# "awaiting_settlement" stage is derived from money, not status.
STAGE_BOOKED             = 'booked'
STAGE_CONFIRMED          = 'confirmed'
STAGE_IN_HOUSE           = 'in_house'
STAGE_CHECKED_OUT        = 'checked_out'
STAGE_AWAITING_SETTLEMENT = 'awaiting_settlement'
STAGE_SETTLED            = 'settled'
STAGE_CANCELLED          = 'cancelled'
STAGE_NO_SHOW            = 'no_show'
STAGE_BLOCKED            = 'blocked'

_STATUS_TO_STAGE = {
    'Reserved':   STAGE_BOOKED,
    'Confirmed':  STAGE_CONFIRMED,
    'CheckedIn':  STAGE_IN_HOUSE,
    'CheckedOut': STAGE_CHECKED_OUT,
    'Cancelled':  STAGE_CANCELLED,
    'NoShow':     STAGE_NO_SHOW,
    'Blocked':    STAGE_BLOCKED,
    'Overbooked': STAGE_CONFIRMED,
}


def derive_stage(reservation: Reservation, money: dict) -> str:
    """Canonical pipeline stage for this reservation.

    CheckedOut + outstanding > 0 → awaiting_settlement
    CheckedOut + outstanding ≤ 0 → settled
    Everything else follows the status → stage map.
    """
    base = _STATUS_TO_STAGE.get(reservation.status, STAGE_BOOKED)
    if base == STAGE_CHECKED_OUT:
        return (STAGE_SETTLED if money.get('outstanding', 0) <= 0
                else STAGE_AWAITING_SETTLEMENT)
    return base


# ──────────────────────────────────────────────────────────────────────
# Timeline assembly
# ──────────────────────────────────────────────────────────────────────

def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        return str(value)
    except Exception:
        return None


def _build_timeline(reservation: Reservation) -> list[dict]:
    """Merge every event touching this reservation into one sorted list.

    Sources (in rough chronological order):
    - webhook_logs (inbound channel manager events)
    - reservation.created_at              → booked
    - reservation.checked_in_at           → checked_in
    - extra_charges (room_rent)           → room_charge_posted
    - extra_charges (other)               → extra_charge_posted
    - payments (non-voided, split direct/ota) → payment_received
    - reservation.discount_at             → discount_applied
    - reservation.checked_out_at          → checked_out
    - audit_logs (entity=Reservation)     → status_change
    """
    events: list[dict] = []

    def _add(step: str, at, by: str | None, detail: str,
             amount: float | None = None):
        events.append({
            'step': step,
            'at': _iso(at),
            'by': by,
            'detail': detail,
            'amount': amount,
        })

    # ── Webhook events ────────────────────────────────────────────────
    try:
        hooks = (WebhookLog.query
                 .filter_by(reservation_id=reservation.id)
                 .order_by(WebhookLog.created_at.asc())
                 .all() if hasattr(WebhookLog, 'created_at')
                 else WebhookLog.query
                      .filter_by(reservation_id=reservation.id).all())
    except Exception:
        hooks = []
    for h in hooks:
        _add(
            step='webhook_received',
            at=getattr(h, 'created_at', None) or getattr(h, 'received_at', None),
            by=f'webhook:{h.source}' if getattr(h, 'source', None) else 'webhook',
            detail=f'{h.event_type}: {h.status}',
        )

    # ── Booking created ──
    _add(
        step='booked',
        at=reservation.created_at,
        by=(reservation.source or 'Walk-in'),
        detail=(f'Reservation {reservation.booking_reference or reservation.id} '
                f'created ({reservation.source})'),
    )

    # ── Check-in ──
    if reservation.checked_in_at:
        _add(
            step='checked_in',
            at=reservation.checked_in_at,
            by=reservation.checkin_by,
            detail=(f'Checked in to room '
                    f'{reservation.room.room_number if reservation.room else "?"}'),
        )

    # ── Room-rent postings (one per night, from night audit) ──
    try:
        rent_rows = (ExtraCharge.query
                     .filter_by(reservation_id=reservation.id,
                                charge_type='room_rent')
                     .order_by(ExtraCharge.charge_date.asc())
                     .all())
    except Exception:
        rent_rows = []
    for r in rent_rows:
        _add(
            step='room_charge_posted',
            at=r.charge_date,
            by='night_audit',
            detail=f'Room rent — {r.charge_date.strftime("%d %b")}',
            amount=_f(r.amount),
        )

    # ── Other extras ──
    try:
        extras_rows = (ExtraCharge.query
                       .filter(ExtraCharge.reservation_id == reservation.id,
                               ExtraCharge.charge_type != 'room_rent')
                       .order_by(ExtraCharge.charge_date.asc())
                       .all())
    except Exception:
        extras_rows = []
    for r in extras_rows:
        _add(
            step='extra_charge_posted',
            at=r.charge_date,
            by=(r.charge_category or 'POS'),
            detail=(r.description or r.charge_type or 'Extra'),
            amount=_f(r.amount),
        )

    # ── Discount ──
    if (reservation.discount_amount or 0) and _f(reservation.discount_amount) > 0:
        _add(
            step='discount_applied',
            at=reservation.discount_at or reservation.checked_out_at,
            by=(reservation.discount_given_by
                or reservation.discount_authorized_by),
            detail=(reservation.discount_reason
                    or 'Discount applied at checkout'),
            amount=_f(reservation.discount_amount),
        )

    # ── Payments (direct + OTA receivable) ──
    try:
        pay_rows = (db.session.query(Payment, PaymentMode)
                    .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
                    .filter(Payment.reservation_id == reservation.id,
                            Payment.is_voided == False)
                    .order_by(Payment.created_at.asc())
                    .all())
    except Exception:
        pay_rows = []
    for p, pm in pay_rows:
        is_ota = (pm.category or '') == 'ota_receivable'
        _add(
            step=('ota_receivable_posted' if is_ota else 'payment_received'),
            at=p.created_at or p.payment_date,
            by=pm.name,
            detail=(f'Settled to {pm.name} ({pm.code})' if is_ota
                    else f'Payment via {pm.name}'),
            amount=_f(p.amount),
        )

    # ── Check-out ──
    if reservation.checked_out_at:
        _add(
            step='checked_out',
            at=reservation.checked_out_at,
            by=reservation.checkout_by,
            detail='Guest checked out',
        )

    # ── Status changes from audit log ──
    try:
        logs = (AuditLog.query
                .filter_by(entity_type='Reservation', entity_id=reservation.id)
                .order_by(AuditLog.timestamp.asc())
                .all())
    except Exception:
        logs = []
    for a in logs:
        if a.action in ('created', 'edited'):
            # Already represented by booked/checked_in/etc.
            continue
        _add(
            step=f'status_{a.action}',
            at=a.timestamp,
            by=(a.staff_user.username if a.staff_user else None),
            detail=f'{a.action} by {a.staff_user.username if a.staff_user else "system"}',
        )

    # Sort: events with at-None sink to the end in original order (stable)
    def _key(e):
        at = e.get('at')
        return (0, at) if at else (1, '')
    events.sort(key=_key)
    return events


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────

def build_journey(reservation_id: int) -> dict | None:
    """Return the full journey dict for one reservation, or None if
    the reservation does not exist.

    Never raises for missing related rows — degrades to '?' / None.
    """
    res = db.session.get(Reservation, reservation_id)
    if res is None:
        return None

    guest = res.guest
    room = res.room
    rt = res.room_type

    money = _compute_money(res)
    stage = derive_stage(res, money)
    nights = max(0, (res.departure_date - res.arrival_date).days)

    # Resolve OTA channel name — reuse the existing ota.py inference so
    # the journey, OTA dashboard, and CEO views agree on the source.
    ota_source_name: str | None = None
    if is_ota_reservation(res):
        try:
            from app.ota import _infer_ota_source
            ota_source_name = _infer_ota_source(res)
        except Exception:
            ota_source_name = 'Other OTA'

    return {
        'reservation_id': res.id,
        'is_ota': is_ota_reservation(res),
        'booking_reference': res.booking_reference,
        'ota_source': ota_source_name,
        'ota_booking_id': res.ota_booking_id,
        'ota_payment_status': res.ota_payment_status,
        'guest': {
            'id': guest.id if guest else None,
            'name': (guest.name if guest else None) or '(no guest)',
            'phone': guest.phone if guest else None,
            'email': guest.email if guest else None,
        },
        'room_type': rt.name if rt else None,
        'room_number': room.room_number if room else None,
        'dates': {
            'arrival': res.arrival_date.isoformat(),
            'departure': res.departure_date.isoformat(),
            'nights': nights,
        },
        'money': money,
        'current_status': res.status,
        'current_stage': stage,
        'has_outstanding': money['outstanding'] > 0.01,
        'timeline': _build_timeline(res),
    }
