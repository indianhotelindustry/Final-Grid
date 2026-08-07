"""
Rate & Inventory Management Blueprint
======================================
Handles seasonal / promotional / weekend rate plans.

Routes (all require Admin or Manager role):
  GET  /rates/                 — list all rate plans
  POST /rates/create           — create a new rate plan
  POST /rates/<id>/edit        — update an existing plan
  POST /rates/<id>/toggle      — activate / deactivate
  POST /rates/<id>/delete      — delete a plan

Public helpers (imported by booking.py and rates API):
  get_applicable_rate(room_type_id, arrival, departure) -> float   (single-night, arrival day only)
  get_stay_rates(room_type_id, arrival, departure) -> List[float]  (per-night rates for entire stay)
  get_average_rate(room_type_id, arrival, departure) -> float      (average nightly rate for display)
"""

from datetime import date, timedelta
from typing import List
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, RatePlan, RoomType
from app.validators import (
    validate_fields, validate_name, validate_positive_float,
    validate_positive_int, validate_date_range, validate_enum,
    validate_text_length, parse_date_optional,
)

rates_bp = Blueprint('rates', __name__, url_prefix='/rates')


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------
def _require_manager():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access restricted to Admin and Manager.', 'danger')
        return redirect(url_for('main.dashboard'))
    return None


# ---------------------------------------------------------------------------
# Rate calculation engine (shared with booking engine + API)
# ---------------------------------------------------------------------------

def _rate_for_night(room_type_id: int, night_date: date,
                    base: float, plans: list) -> float:
    """
    Return the rate for a single night given pre-fetched base rate and plans.

    Checks the *night_date*'s weekday (not just the arrival day) so that
    weekend/weekday plans apply correctly across multi-night stays.
    """
    weekday = str(night_date.weekday())  # 0=Mon … 6=Sun

    for plan in plans:
        # Date range check
        if plan.start_date and plan.end_date:
            if not (plan.start_date <= night_date < plan.end_date):
                continue
        elif plan.start_date and night_date < plan.start_date:
            continue
        elif plan.end_date and night_date >= plan.end_date:
            continue

        # Days-of-week check
        if plan.days_of_week:
            allowed_days = [d.strip() for d in plan.days_of_week.split(',')]
            if weekday not in allowed_days:
                continue

        # This plan matches — apply it
        amount = float(plan.rate_amount)
        if plan.rate_mode == 'fixed':
            return amount
        elif plan.rate_mode == 'percent_up':
            return round(base * (1 + amount / 100), 2)
        elif plan.rate_mode == 'percent_down':
            return round(base * (1 - amount / 100), 2)

    return base


def _rate_for_night_detailed(room_type_id: int, night_date: date,
                              base: float, plans: list) -> tuple:
    """Like _rate_for_night but returns (rate, plan_name_or_None)."""
    weekday = str(night_date.weekday())
    for plan in plans:
        if plan.start_date and plan.end_date:
            if not (plan.start_date <= night_date < plan.end_date):
                continue
        elif plan.start_date and night_date < plan.start_date:
            continue
        elif plan.end_date and night_date >= plan.end_date:
            continue
        if plan.days_of_week:
            allowed_days = [d.strip() for d in plan.days_of_week.split(',')]
            if weekday not in allowed_days:
                continue
        amount = float(plan.rate_amount)
        if plan.rate_mode == 'fixed':
            return amount, plan.name
        elif plan.rate_mode == 'percent_up':
            return round(base * (1 + amount / 100), 2), plan.name
        elif plan.rate_mode == 'percent_down':
            return round(base * (1 - amount / 100), 2), plan.name
    return base, None


def get_stay_rates_detailed(room_type_id: int, arrival: date, departure: date) -> list:
    """Return list of (date, rate, plan_name_or_None) for every night."""
    base, plans = _fetch_plans_and_base(room_type_id)
    result = []
    current = arrival
    while current < departure:
        rate, plan_name = _rate_for_night_detailed(room_type_id, current, base, plans)
        result.append((current, rate, plan_name))
        current += timedelta(days=1)
    return result


def _fetch_plans_and_base(room_type_id: int):
    """Load room type base rate and active rate plans (sorted by priority desc).

    Returns (base_rate, plans_list) or (0.0, []) when room type not found.
    """
    room_type = db.session.get(RoomType, room_type_id)
    if not room_type:
        return 0.0, []

    base = float(room_type.base_rate)

    plans = RatePlan.query.filter(
        RatePlan.is_active == True,
        db.or_(
            RatePlan.room_type_id == room_type_id,
            RatePlan.room_type_id == None,
        )
    ).order_by(RatePlan.priority.desc()).all()

    return base, plans


def get_applicable_rate(room_type_id: int, arrival: date, departure: date) -> float:
    """
    Return the best applicable rate (per night) for the given room type and
    the *arrival* date.  Kept for backward compatibility — callers that need
    per-night granularity across a full stay should use ``get_stay_rates()``
    or ``get_average_rate()`` instead.

    Logic:
    1. Collect all active rate plans for this room type (or global plans where room_type_id IS NULL).
    2. Filter to plans whose date range covers the arrival AND whose days_of_week matches arrival.
    3. Pick the plan with the highest priority.
    4. Apply rate_mode (fixed / percent_up / percent_down) against the room type base_rate.
    5. If no plan matches, return room type base_rate.
    """
    base, plans = _fetch_plans_and_base(room_type_id)
    if base == 0.0 and not plans:
        return 0.0
    return _rate_for_night(room_type_id, arrival, base, plans)


def get_stay_rates(room_type_id: int, arrival: date, departure: date) -> List[float]:
    """
    Return a list of per-night rates for every night from *arrival* up to
    (but not including) *departure*.

    Each night is independently matched against rate plans so that
    weekday/weekend and seasonal boundaries are respected.
    """
    base, plans = _fetch_plans_and_base(room_type_id)
    if base == 0.0 and not plans:
        nights = max((departure - arrival).days, 0)
        return [0.0] * nights

    rates: List[float] = []
    current = arrival
    while current < departure:
        rates.append(_rate_for_night(room_type_id, current, base, plans))
        current += timedelta(days=1)
    return rates


def get_average_rate(room_type_id: int, arrival: date, departure: date) -> float:
    """
    Return the average nightly rate across all nights of the stay.

    Useful for display on the booking engine and for storing as
    ``rate_per_night`` on a reservation.
    """
    rates = get_stay_rates(room_type_id, arrival, departure)
    if not rates:
        return 0.0
    return round(sum(rates) / len(rates), 2)


# ---------------------------------------------------------------------------
# Central Rate Resolver — ALL reservation creation paths should use this
# ---------------------------------------------------------------------------

class RateResolution:
    """Result of :func:`resolve_rate_for_reservation`."""
    __slots__ = ('rate_per_night', 'source', 'applied_plan_name',
                 'used_fallback', 'nightly_rates', 'base_rate')

    def __init__(self, **kw):
        for s in self.__slots__:
            object.__setattr__(self, s, kw.get(s))

    def as_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def resolve_rate_for_reservation(
    room_type_id: int,
    arrival_date: date,
    departure_date: date,
    *,
    override_rate: float | None = None,
    group_rate: float | None = None,
) -> RateResolution:
    """
    Single entry point for determining ``rate_per_night`` on a reservation.

    Every reservation creation flow should call this instead of reading
    ``room_type.base_rate`` directly.

    Priority:
      1. ``override_rate`` — staff manually entered a rate → use as-is
      2. ``group_rate``    — negotiated group block rate   → use as-is
      3. Rate plan match   — ``get_average_rate()`` across stay nights
      4. ``base_rate``     — final fallback (no plan matched)

    Returns a :class:`RateResolution` with the resolved rate, source label,
    applied plan name (if any), fallback flag, nightly breakdown, and base rate.
    """
    import logging
    _log = logging.getLogger('app.rates')

    room_type = db.session.get(RoomType, room_type_id)
    base = float(room_type.base_rate) if room_type else 0.0

    # 1. Manual override — staff entered a specific rate
    if override_rate is not None and override_rate > 0:
        _log.info('resolve_rate: override_rate=%.2f for rt=%d', override_rate, room_type_id)
        return RateResolution(
            rate_per_night=override_rate,
            source='manual_override',
            applied_plan_name=None,
            used_fallback=False,
            nightly_rates=None,
            base_rate=base,
        )

    # 2. Group rate — negotiated block-level rate
    if group_rate is not None and group_rate > 0:
        _log.info('resolve_rate: group_rate=%.2f for rt=%d', group_rate, room_type_id)
        return RateResolution(
            rate_per_night=group_rate,
            source='group_rate',
            applied_plan_name=None,
            used_fallback=False,
            nightly_rates=None,
            base_rate=base,
        )

    # 3. Rate plan resolution — per-night then average
    nightly = get_stay_rates(room_type_id, arrival_date, departure_date)
    avg = round(sum(nightly) / len(nightly), 2) if nightly else base

    # Did a rate plan actually change anything, or did every night fall back?
    plan_applied = any(r != base for r in nightly)

    if plan_applied:
        # Find which plan(s) matched for logging
        _, plans = _fetch_plans_and_base(room_type_id)
        plan_name = plans[0].name if plans else None
        _log.info('resolve_rate: rate_plan avg=%.2f nightly=%s for rt=%d plan=%s',
                  avg, nightly, room_type_id, plan_name)
        return RateResolution(
            rate_per_night=avg,
            source='rate_plan',
            applied_plan_name=plan_name,
            used_fallback=False,
            nightly_rates=nightly,
            base_rate=base,
        )

    # 4. No plan matched — base_rate fallback
    _log.info('resolve_rate: base_rate fallback=%.2f for rt=%d', base, room_type_id)
    return RateResolution(
        rate_per_night=base,
        source='base_rate',
        applied_plan_name=None,
        used_fallback=True,
        nightly_rates=nightly,
        base_rate=base,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@rates_bp.before_request
@login_required
def guard():
    pass


@rates_bp.route('/')
def index():
    denied = _require_manager()
    if denied:
        return denied

    plans = RatePlan.query.order_by(RatePlan.priority.desc(), RatePlan.name).all()
    room_types = RoomType.query.all()
    return render_template('rates/index.html', plans=plans, room_types=room_types)


@rates_bp.route('/create', methods=['POST'])
def create():
    denied = _require_manager()
    if denied:
        return denied

    _VALID_PLAN_TYPES = {'Seasonal', 'Promotional', 'Weekend', 'Weekday', 'Event', 'Corporate'}
    _VALID_RATE_MODES = {'fixed', 'percent_up', 'percent_down'}

    try:
        start_str = request.form.get('start_date')
        end_str = request.form.get('end_date')
        room_type_id = request.form.get('room_type_id') or None
        days_of_week = ','.join(request.form.getlist('days_of_week')) or None

        start_dt, start_err = parse_date_optional(start_str, 'Start date')
        end_dt, end_err = parse_date_optional(end_str, 'End date')

        rate_errs = validate_fields(
            validate_name(request.form.get('name', ''), 'Plan name', max_len=100),
            validate_enum(request.form.get('plan_type', ''), _VALID_PLAN_TYPES, 'Plan type'),
            validate_positive_float(request.form.get('rate_amount', ''), 'Rate amount'),
            validate_enum(request.form.get('rate_mode', ''), _VALID_RATE_MODES, 'Rate mode'),
            validate_positive_int(request.form.get('priority', 10), 'Priority', min_val=1, max_val=100),
            validate_text_length(request.form.get('notes', ''), 'Notes', max_len=500),
            start_err,
            end_err,
            validate_date_range(start_dt, end_dt, 'Start date', 'End date') if start_dt and end_dt else None,
        )
        if rate_errs:
            for e in rate_errs:
                flash(e, 'danger')
            return redirect(url_for('rates.index'))

        plan = RatePlan(
            name=request.form['name'].strip(),
            plan_type=request.form.get('plan_type', 'Seasonal'),
            room_type_id=int(room_type_id) if room_type_id else None,
            rate_amount=float(request.form['rate_amount']),
            rate_mode=request.form.get('rate_mode', 'fixed'),
            start_date=start_dt,
            end_date=end_dt,
            days_of_week=days_of_week,
            priority=int(request.form.get('priority', 10)),
            notes=request.form.get('notes', '').strip(),
            is_active=True,
        )
        db.session.add(plan)
        db.session.commit()
        flash(f'Rate plan "{plan.name}" created.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating rate plan: {e}', 'danger')

    return redirect(url_for('rates.index'))


@rates_bp.route('/<int:plan_id>/edit', methods=['POST'])
def edit(plan_id):
    denied = _require_manager()
    if denied:
        return denied

    _VALID_PLAN_TYPES = {'Seasonal', 'Promotional', 'Weekend', 'Weekday', 'Event', 'Corporate'}
    _VALID_RATE_MODES = {'fixed', 'percent_up', 'percent_down'}

    plan = RatePlan.query.get_or_404(plan_id)
    try:
        start_str = request.form.get('start_date')
        end_str = request.form.get('end_date')
        room_type_id = request.form.get('room_type_id') or None
        days_of_week = ','.join(request.form.getlist('days_of_week')) or None

        start_dt, start_err = parse_date_optional(start_str, 'Start date')
        end_dt, end_err = parse_date_optional(end_str, 'End date')

        rate_errs = validate_fields(
            validate_name(request.form.get('name', ''), 'Plan name', max_len=100),
            validate_enum(request.form.get('plan_type', ''), _VALID_PLAN_TYPES, 'Plan type'),
            validate_positive_float(request.form.get('rate_amount', ''), 'Rate amount'),
            validate_enum(request.form.get('rate_mode', ''), _VALID_RATE_MODES, 'Rate mode'),
            validate_positive_int(request.form.get('priority', 10), 'Priority', min_val=1, max_val=100),
            validate_text_length(request.form.get('notes', ''), 'Notes', max_len=500),
            start_err,
            end_err,
            validate_date_range(start_dt, end_dt, 'Start date', 'End date') if start_dt and end_dt else None,
        )
        if rate_errs:
            for e in rate_errs:
                flash(e, 'danger')
            return redirect(url_for('rates.index'))

        plan.name = request.form['name'].strip()
        plan.plan_type = request.form.get('plan_type', 'Seasonal')
        plan.room_type_id = int(room_type_id) if room_type_id else None
        plan.rate_amount = float(request.form['rate_amount'])
        plan.rate_mode = request.form.get('rate_mode', 'fixed')
        plan.start_date = start_dt
        plan.end_date = end_dt
        plan.days_of_week = days_of_week
        plan.priority = int(request.form.get('priority', 10))
        plan.notes = request.form.get('notes', '').strip()

        db.session.commit()
        flash(f'Rate plan "{plan.name}" updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating rate plan: {e}', 'danger')

    return redirect(url_for('rates.index'))


@rates_bp.route('/<int:plan_id>/toggle', methods=['POST'])
def toggle(plan_id):
    denied = _require_manager()
    if denied:
        return denied

    plan = RatePlan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    state = 'activated' if plan.is_active else 'deactivated'
    flash(f'Rate plan "{plan.name}" {state}.', 'success')
    return redirect(url_for('rates.index'))


@rates_bp.route('/<int:plan_id>/delete', methods=['POST'])
def delete(plan_id):
    denied = _require_manager()
    if denied:
        return denied

    plan = RatePlan.query.get_or_404(plan_id)
    name = plan.name
    db.session.delete(plan)
    db.session.commit()
    flash(f'Rate plan "{name}" deleted.', 'success')
    return redirect(url_for('rates.index'))


# ---------------------------------------------------------------------------
# Notification log viewer
# ---------------------------------------------------------------------------

@rates_bp.route('/notification-logs')
def notification_logs():
    denied = _require_manager()
    if denied:
        return denied

    from app.models import NotificationLog
    logs = NotificationLog.query.order_by(NotificationLog.sent_at.desc()).limit(200).all()
    return render_template('rates/notification_logs.html', logs=logs)
