"""
No-Show Service
===============
Business logic for marking reservations as NoShow, applying no-show fees,
and managing manager overrides/exemptions.

Rules:
- NoShow is distinct from Cancelled (no guest/hotel communication).
- Night audit calls process_all_noshows() at EOD.
- Manager/Admin can call manual_noshow() before audit runs.
- Manager/Admin can exempt a reservation so audit skips it (late-arrival extension).
- OTA bookings are flagged but fee is withheld by default (channel manager handles billing).
- No-show fee is recorded as an ExtraCharge on the folio.
- Every action creates an AuditLog entry.
- All service functions that are called from night audit do NOT commit — caller commits.
- Standalone user-action functions (manual_noshow, exempt_reservation, etc.) DO commit.
"""
from __future__ import annotations
from typing import NamedTuple
from datetime import date

from app.models import db, Reservation, Room, NoShowLog, ExtraCharge, AuditLog, Settings


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class NoShowResult(NamedTuple):
    success: bool
    message: str
    no_show_log: object = None  # NoShowLog | None


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _get_noshow_config() -> dict:
    """Read no-show policy settings from the Settings table."""
    def _s(key: str, default: str) -> str:
        row = Settings.query.filter_by(key=key).first()
        return (row.value or default) if row else default

    return {
        'fee_enabled':       _s('noshow_fee_enabled', 'false').lower() == 'true',
        'fee_mode':          _s('noshow_fee_mode', 'fixed'),      # fixed | percent
        'fee_amount':        float(_s('noshow_fee_amount', '0') or '0'),
        'ota_auto_process':  _s('noshow_ota_auto_process', 'false').lower() == 'true',
    }


def _calculate_fee(reservation: Reservation, config: dict) -> float:
    """Return the no-show fee for a reservation based on current policy."""
    if not config['fee_enabled']:
        return 0.0
    if config['fee_mode'] == 'percent':
        return round(float(reservation.rate_per_night) * config['fee_amount'] / 100, 2)
    return round(float(config['fee_amount']), 2)


# ---------------------------------------------------------------------------
# Core processing (no commit — caller commits)
# ---------------------------------------------------------------------------

def get_pending_noshows(business_date: date) -> list[Reservation]:
    """
    Return reservations that are candidates for no-show posting:
    - Status in Reserved/Confirmed
    - Arrival date <= business_date (due today or overdue)
    - Not exempt
    """
    return (
        Reservation.query
        .filter(
            Reservation.status.in_(['Reserved', 'Confirmed']),
            Reservation.arrival_date <= business_date,
            Reservation.noshow_exempt == False,  # noqa: E712
        )
        .order_by(Reservation.arrival_date, Reservation.id)
        .all()
    )


def process_reservation_noshow(
    reservation: Reservation,
    business_date: date,
    config: dict,
    posted_by_user_id: int | None = None,
) -> NoShowResult:
    """
    Mark a single reservation as NoShow.
    - Updates reservation.status → 'NoShow'
    - Releases room (sets to Vacant if it was Reserved/Dirty and not Occupied)
    - Creates ExtraCharge for fee (if applicable)
    - Creates NoShowLog record
    - Creates AuditLog entry
    Does NOT commit — caller must commit.
    """
    # Pessimistic lock: prevent concurrent status changes on this reservation
    reservation = (db.session.query(Reservation)
                   .with_for_update()
                   .filter_by(id=reservation.id)
                   .first())
    if not reservation:
        db.session.rollback()
        return NoShowResult(reservation_id=0, status='skipped',
                            fee_amount=0, fee_applied=False, note='Reservation not found')

    is_ota = bool(reservation.ota_booking_id)
    old_status = reservation.status

    # OTA: flag but withhold automatic fee unless ota_auto_process is enabled
    if is_ota and not config.get('ota_auto_process', False):
        fee_amount = 0.0
        fee_applied = False
        fee_note = 'OTA booking — no-show fee withheld; manual handling required.'
    else:
        fee_amount = _calculate_fee(reservation, config)
        fee_applied = fee_amount > 0
        fee_note = None

    # --- State transitions ---
    reservation.status = 'NoShow'
    reservation.noshow_exempt = False  # clear any lingering exemption flag

    # Release room inventory: room was assigned but never occupied.
    # Only release if no OTHER active (CheckedIn) reservation is using this room.
    if reservation.room_id:
        room = db.session.query(Room).with_for_update().filter_by(id=reservation.room_id).first()
        if room and room.status != 'Occupied':
            # Verify no other CheckedIn reservation holds this room
            other_checkin = Reservation.query.filter(
                Reservation.room_id == reservation.room_id,
                Reservation.status == 'CheckedIn',
                Reservation.id != reservation.id,
            ).first()
            if not other_checkin:
                room.status = 'Vacant'

    # --- No-show fee as ExtraCharge ---
    if fee_applied:
        from app.services import resolve_billing_folio_id
        db.session.add(ExtraCharge(
            reservation_id=reservation.id,
            folio_id=resolve_billing_folio_id(                        # R-1
                reservation, user_id=posted_by_user_id),
            description=f'No-Show Fee ({config["fee_mode"]})',
            amount=fee_amount,
            charge_date=business_date,
        ))

    # --- NoShowLog (immutable record) ---
    log = NoShowLog(
        reservation_id=reservation.id,
        audit_date=business_date,
        fee_applied=fee_applied,
        fee_amount=fee_amount,
        is_ota=is_ota,
        ota_booking_id=reservation.ota_booking_id,
        posted_by_user_id=posted_by_user_id,   # None = automated night audit
        notes=fee_note,
    )
    db.session.add(log)

    # --- AuditLog ---
    db.session.add(AuditLog(
        entity_type='Reservation',
        entity_id=reservation.id,
        action='noshow_posted',
        before_state={'status': old_status},
        after_state={
            'status': 'NoShow',
            'fee_applied': fee_applied,
            'fee_amount': fee_amount,
            'is_ota': is_ota,
            'audit_date': str(business_date),
            'posted_by': posted_by_user_id or 'night_audit',
        },
        staff_user_id=posted_by_user_id or 0,  # 0 = system/night audit
    ))

    return NoShowResult(success=True, message='No-show posted successfully.', no_show_log=log)


def process_all_noshows(
    business_date: date,
    posted_by_user_id: int | None = None,
) -> tuple[int, int]:
    """
    Process all pending no-shows for business_date.
    Called by run_night_audit() — does NOT commit.
    Returns (total_count, ota_count).
    """
    config = _get_noshow_config()
    candidates = get_pending_noshows(business_date)
    total = 0
    ota = 0
    for reservation in candidates:
        result = process_reservation_noshow(reservation, business_date, config, posted_by_user_id)
        if result.success:
            total += 1
            if result.no_show_log and result.no_show_log.is_ota:
                ota += 1
    return total, ota


# ---------------------------------------------------------------------------
# Manager override — standalone (commits)
# ---------------------------------------------------------------------------

def exempt_reservation(reservation_id: int, user_id: int, note: str = '') -> tuple[bool, str]:
    """
    Mark a reservation as exempt so tonight's night audit skips it.
    Use case: guest called to say they are arriving late.
    """
    reservation = db.session.get(Reservation, reservation_id)
    if not reservation:
        return False, 'Reservation not found.'
    if reservation.status not in ('Reserved', 'Confirmed'):
        return False, f'Cannot exempt: reservation status is {reservation.status}.'
    if reservation.noshow_exempt:
        return False, 'Reservation is already exempt.'

    reservation.noshow_exempt = True
    db.session.add(AuditLog(
        entity_type='Reservation',
        entity_id=reservation_id,
        action='noshow_exempt_set',
        before_state={'noshow_exempt': False},
        after_state={'noshow_exempt': True, 'note': note},
        staff_user_id=user_id,
    ))
    db.session.commit()
    return True, 'Reservation exempted from tonight\'s no-show processing.'


def remove_exemption(reservation_id: int, user_id: int) -> tuple[bool, str]:
    """Remove a manager-set no-show exemption."""
    reservation = db.session.get(Reservation, reservation_id)
    if not reservation:
        return False, 'Reservation not found.'
    if not reservation.noshow_exempt:
        return False, 'Reservation is not currently exempt.'

    reservation.noshow_exempt = False
    db.session.add(AuditLog(
        entity_type='Reservation',
        entity_id=reservation_id,
        action='noshow_exempt_removed',
        before_state={'noshow_exempt': True},
        after_state={'noshow_exempt': False},
        staff_user_id=user_id,
    ))
    db.session.commit()
    return True, 'No-show exemption removed.'


def manual_noshow(
    reservation_id: int,
    user_id: int,
    note: str = '',
) -> NoShowResult:
    """
    Manually mark a reservation as NoShow before night audit runs.
    Only allowed for Manager/Admin — route layer enforces role check.
    """
    reservation = db.session.get(Reservation, reservation_id)
    if not reservation:
        return NoShowResult(False, 'Reservation not found.')
    if reservation.status not in ('Reserved', 'Confirmed'):
        return NoShowResult(False, f'Cannot post no-show: status is {reservation.status}.')

    from app.services import get_business_date
    business_date = get_business_date()

    if reservation.arrival_date > business_date:
        return NoShowResult(False, 'Arrival date is in the future — cannot mark as no-show yet.')

    config = _get_noshow_config()
    try:
        result = process_reservation_noshow(reservation, business_date, config, posted_by_user_id=user_id)
        if result.success and result.no_show_log:
            result.no_show_log.override_by_user_id = user_id
            result.no_show_log.override_note = note or 'Manual no-show posted by staff.'
        db.session.commit()
        return result
    except Exception as exc:
        db.session.rollback()
        return NoShowResult(False, f'Failed to post no-show: {exc}')
