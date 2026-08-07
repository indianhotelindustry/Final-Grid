"""
revenue_guard.py — Pre-save revenue validation and leakage detection.
Called from routes before db.session.commit().
Raises ValueError on hard policy violations (e.g., discount needs manager approval).
All alert firing is non-fatal (delegates to AlertService).
"""
import logging
from datetime import date as date_type, datetime, timedelta
from decimal import Decimal

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setting(key: str, default):
    try:
        from app.models import Settings
        row = Settings.query.filter_by(key=key).first()
        if row is None:
            return default
        val = row.value
        if isinstance(default, float):
            return float(val)
        if isinstance(default, int):
            return int(val)
        return val
    except Exception:
        return default


def _to_dec(val, fallback=Decimal('0')):
    if val is None:
        return fallback
    try:
        return Decimal(str(val))
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Expected tariff computation
# ---------------------------------------------------------------------------

def compute_expected_tariff(room_type: str, checkin_date, rate_per_night):
    """
    Returns the expected tariff as MAX of three signals:
      1. standard_tariff from RoomType
      2. 7-day rolling average for same room_type
      3. highest-priority active RatePlan tariff for the date

    Falls back to rate_per_night if all signals are unavailable.
    """
    signals = []

    # Signal 1: standard_tariff from RoomType
    try:
        from app.models import RoomType
        rt = RoomType.query.filter_by(name=room_type).first()
        if rt and rt.base_rate:
            signals.append(_to_dec(rt.base_rate))
    except Exception as exc:
        log.debug('compute_expected_tariff signal1 failed: %s', exc)

    # Signal 2: 7-day rolling average for same room_type
    try:
        from app.models import Reservation, db
        from sqlalchemy import func
        seven_ago = (
            checkin_date - timedelta(days=7)
            if isinstance(checkin_date, date_type)
            else datetime.utcnow().date() - timedelta(days=7)
        )
        avg_row = (
            db.session.query(func.avg(Reservation.rate_per_night))
            .join(Reservation.room)
            .filter(
                Reservation.arrival_date >= seven_ago,
                Reservation.status.in_(['checked_in', 'checked_out']),
            )
            .first()
        )
        # Attempt join via room relationship then filter by room_type name
        # Fallback: filter by room_type string if column exists
        from app.models import Room
        avg_row = (
            db.session.query(func.avg(Reservation.rate_per_night))
            .join(Room, Reservation.room_id == Room.id)
            .join(RoomType, Room.room_type_id == RoomType.id)
            .filter(
                RoomType.name == room_type,
                Reservation.arrival_date >= seven_ago,
                Reservation.status.in_(['checked_in', 'checked_out']),
            )
            .scalar()
        )
        if avg_row:
            signals.append(_to_dec(avg_row))
    except Exception as exc:
        log.debug('compute_expected_tariff signal2 failed: %s', exc)

    # Signal 3: active RatePlan for this room_type and date
    try:
        from app.models import RatePlan
        if isinstance(checkin_date, str):
            from datetime import date as dt
            checkin_date = dt.fromisoformat(checkin_date)
        target = checkin_date if isinstance(checkin_date, date_type) else checkin_date.date()
        plan = (
            RatePlan.query
            .filter(
                RatePlan.room_type == room_type,
                RatePlan.start_date <= target,
                RatePlan.end_date >= target,
                RatePlan.is_active == True,
            )
            .order_by(RatePlan.priority.desc())
            .first()
        )
        if plan and plan.rate:
            signals.append(_to_dec(plan.rate))
    except Exception as exc:
        log.debug('compute_expected_tariff signal3 failed: %s', exc)

    if not signals:
        return _to_dec(rate_per_night)

    return max(signals)


# ---------------------------------------------------------------------------
# Leakage application
# ---------------------------------------------------------------------------

def apply_leakage_with_expected(reservation, user_id: int,
                                 reason: str = '', room_no=None):
    """
    Compute expected_tariff for the reservation and store it.
    If actual rate_per_night < expected_tariff, record a leakage_reason
    and fire a non-fatal alert.
    Modifies reservation in place (does NOT commit).
    """
    try:
        room_type = None
        try:
            if reservation.room and reservation.room.room_type:
                room_type = reservation.room.room_type.name
        except Exception:
            pass

        if not room_type:
            return  # Cannot compute without room_type

        expected = compute_expected_tariff(
            room_type=room_type,
            # v2.2.17 — Reservation has no `checkin_date`; the stay date is
            # `arrival_date`. The wrong name raised AttributeError on every
            # check-in (caught non-fatally) so leakage classification never
            # ran. Corrected to the real model field.
            checkin_date=reservation.arrival_date,
            rate_per_night=reservation.rate_per_night,
        )
        reservation.expected_tariff = expected

        actual = _to_dec(reservation.rate_per_night)
        nights = reservation.num_nights or 1
        leakage_per_night = expected - actual

        if leakage_per_night > Decimal('0'):
            total_leakage = leakage_per_night * nights
            lreason = reason or 'Rate below expected tariff'
            reservation.leakage_reason = lreason

            fire_leakage_alert_if_needed(
                user_id=user_id,
                leakage_amount=float(total_leakage),
                reservation_id=getattr(reservation, 'id', None),
                room_no=room_no,
                reason=lreason,
            )
    except Exception as exc:
        log.error('apply_leakage_with_expected failed (non-fatal): %s', exc)


def fire_leakage_alert_if_needed(user_id: int, leakage_amount: float,
                                  reservation_id=None, room_no=None,
                                  reason: str = ''):
    """Thin wrapper — delegates to AlertService.check_leakage (non-fatal)."""
    try:
        from app.alert_service import AlertService
        AlertService.check_leakage(
            user_id=user_id,
            leakage_amount=leakage_amount,
            reservation_id=reservation_id,
            room_no=room_no,
            reason=reason,
        )
    except Exception as exc:
        log.error('fire_leakage_alert_if_needed failed (non-fatal): %s', exc)


# ---------------------------------------------------------------------------
# Discount validation
# ---------------------------------------------------------------------------

def validate_discount(user, discount_amount: float):
    """
    Raise ValueError if:
      - discount_amount > MAX_DISCOUNT_WITHOUT_APPROVAL AND user is not Admin/Manager.
    Returns True if OK.
    """
    if discount_amount is None or float(discount_amount) <= 0:
        return True

    max_without_approval = _setting('MAX_DISCOUNT_WITHOUT_APPROVAL', 1000)
    if float(discount_amount) > float(max_without_approval):
        if not user.has_role('Admin', 'Manager'):
            raise ValueError(
                f"Discount of ₹{discount_amount:.2f} exceeds the allowed limit of "
                f"₹{max_without_approval}. Manager approval required."
            )
    return True


def validate_and_apply_discount(reservation, user, discount_amount: float,
                                  discount_type: str = None,
                                  discount_reason: str = None):
    """
    Full discount pipeline:
      1. Validate amount (raises ValueError if over threshold without manager)
      2. Apply discount fields to reservation (no commit)
      3. Fire discount alerts (non-fatal)

    discount_type: 'percentage' | 'fixed'
    Returns effective discount amount applied.
    """
    if discount_amount is None or float(discount_amount) < 0:
        discount_amount = 0.0

    # Hard validation — may raise
    validate_discount(user, float(discount_amount))

    disc_dec = _to_dec(discount_amount)

    if disc_dec > 0:
        rate    = _to_dec(reservation.rate_per_night)
        nights  = reservation.num_nights or 1
        base    = rate * nights

        if discount_type == 'percentage':
            effective = base * disc_dec / Decimal('100')
        else:
            effective = disc_dec

        net_total = base - effective
        if net_total < 0:
            raise ValueError("Discount cannot exceed total bill amount.")

        reservation.discount_amount     = float(effective)
        reservation.discount_percentage = (
            float(disc_dec) if discount_type == 'percentage' else
            float(effective / base * 100) if base > 0 else 0
        )
        reservation.discount_reason      = discount_reason or ''
        reservation.discount_given_by    = user.username
        reservation.net_total            = float(net_total)

        # Fire alert (non-fatal)
        try:
            from app.alert_service import AlertService
            AlertService.check_discount(
                user_id=user.id,
                discount_amount=float(effective),
                reservation_id=getattr(reservation, 'id', None),
                room_no=getattr(reservation.room, 'room_number', None),
            )
        except Exception as exc:
            log.error('Discount alert failed (non-fatal): %s', exc)

        return float(effective)
    else:
        # Clear discount
        reservation.discount_amount     = None
        reservation.discount_percentage = None
        reservation.discount_reason      = None
        reservation.discount_given_by    = None
        rate    = _to_dec(reservation.rate_per_night)
        nights  = reservation.num_nights or 1
        reservation.net_total = float(rate * nights)
        return 0.0
