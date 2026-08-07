"""
AI Dynamic Pricing Engine
=========================
Rule-based revenue management engine that recommends optimal room rates
using statistical analysis of historical data, occupancy projections,
day-of-week patterns, seasonal trends, and booking pace.

No heavy ML dependencies -- uses only Python stdlib + SQLAlchemy.

Usage:
    from app.ai_pricing import ai_pricing_bp, DynamicPricingEngine
    app.register_blueprint(ai_pricing_bp)

API Endpoints (require Admin or Manager role):
    GET /ai/pricing/recommendations?days=30   -- JSON rate recommendations
    GET /ai/pricing/dashboard                 -- full dashboard page
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from app.models import db, Reservation, Room, RoomType, Settings

logger = logging.getLogger(__name__)

ai_pricing_bp = Blueprint('ai_pricing', __name__, url_prefix='/ai/pricing')


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

_SETTINGS_DEFAULTS: Dict[str, Any] = {
    'pricing_enabled': 'true',
    'pricing_dow_multipliers': json.dumps({
        '0': 0.90, '1': 0.90, '2': 0.90, '3': 0.90,   # Mon-Thu
        '4': 1.05,                                        # Fri
        '5': 1.15,                                        # Sat
        '6': 0.95,                                        # Sun
    }),
    'pricing_max_increase_pct': '40',
    'pricing_max_decrease_pct': '20',
    'pricing_auto_apply': 'false',
}


def _get_setting(key: str) -> str:
    """Read a setting from the Settings table, falling back to built-in default."""
    row = Settings.query.filter_by(key=key).first()
    if row and row.value is not None:
        return row.value
    return _SETTINGS_DEFAULTS.get(key, '')


def _get_setting_bool(key: str) -> bool:
    return _get_setting(key).lower() in ('true', '1', 'yes')


def _get_setting_float(key: str) -> float:
    try:
        return float(_get_setting(key))
    except (ValueError, TypeError):
        return float(_SETTINGS_DEFAULTS.get(key, '0'))


def _get_dow_multipliers() -> Dict[str, float]:
    """Return day-of-week multipliers as {weekday_str: multiplier}."""
    raw = _get_setting('pricing_dow_multipliers')
    try:
        data = json.loads(raw)
        return {str(k): float(v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return json.loads(_SETTINGS_DEFAULTS['pricing_dow_multipliers'])


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------

def _get_sellable_rooms_by_type(room_type_id: Optional[int] = None) -> Dict[int, int]:
    """Return {room_type_id: count} of sellable rooms."""
    q = Room.query.filter_by(is_active=True, is_sellable=True, is_out_of_order=False)
    if room_type_id:
        q = q.filter_by(room_type_id=room_type_id)
    rows = (
        q.with_entities(Room.room_type_id, func.count(Room.id))
        .group_by(Room.room_type_id)
        .all()
    )
    return {rt_id: cnt for rt_id, cnt in rows}


def _get_total_sellable_count() -> int:
    return Room.query.filter_by(
        is_active=True, is_sellable=True, is_out_of_order=False
    ).count()


def _count_reservations_for_date(target_date: date,
                                  room_type_id: Optional[int] = None,
                                  statuses: Optional[Tuple[str, ...]] = None) -> int:
    """Count on-the-books reservations overlapping *target_date*."""
    if statuses is None:
        statuses = ('Reserved', 'Confirmed', 'CheckedIn')
    q = Reservation.query.filter(
        Reservation.status.in_(statuses),
        Reservation.arrival_date <= target_date,
        Reservation.departure_date > target_date,
    )
    if room_type_id:
        q = q.filter_by(room_type_id=room_type_id)
    return q.count()


# ---------------------------------------------------------------------------
# Dynamic Pricing Engine
# ---------------------------------------------------------------------------

class DynamicPricingEngine:
    """Rule-based dynamic pricing with statistical heuristics."""

    def __init__(self, app=None):
        self.app = app

    # ------------------------------------------------------------------
    # Public: recommended rate
    # ------------------------------------------------------------------

    def get_recommended_rate(self, room_type_id: int, target_date: date) -> Dict[str, Any]:
        """
        Return AI-recommended rate for a room type on a specific date.

        Returns dict with:
            base_rate, recommended_rate, factors dict, confidence, capped
        """
        room_type = db.session.get(RoomType, room_type_id)
        if not room_type:
            return {'error': f'Room type {room_type_id} not found'}

        base_rate = float(room_type.base_rate)
        if base_rate <= 0:
            return {
                'base_rate': base_rate,
                'recommended_rate': base_rate,
                'factors': {},
                'confidence': 0,
                'capped': False,
            }

        # Compute individual factors
        occ_mult = self.get_occupancy_multiplier(target_date)
        dow_mult = self.get_dow_multiplier(target_date)
        seasonal = self.get_seasonal_factor(target_date)
        pace = self.get_pace_factor(room_type_id, target_date)

        # Combine factors multiplicatively
        combined = occ_mult * dow_mult * seasonal * pace
        raw_rate = round(base_rate * combined, 2)

        # Apply caps from settings
        max_up = _get_setting_float('pricing_max_increase_pct') / 100.0
        max_down = _get_setting_float('pricing_max_decrease_pct') / 100.0
        floor_rate = round(base_rate * (1 - max_down), 2)
        ceil_rate = round(base_rate * (1 + max_up), 2)

        capped = False
        recommended = raw_rate
        if recommended > ceil_rate:
            recommended = ceil_rate
            capped = True
        elif recommended < floor_rate:
            recommended = floor_rate
            capped = True

        # Confidence score: higher when we have more historical data
        confidence = self._compute_confidence(room_type_id, target_date)

        return {
            'base_rate': base_rate,
            'recommended_rate': recommended,
            'raw_rate': raw_rate,
            'combined_multiplier': round(combined, 4),
            'factors': {
                'occupancy': round(occ_mult, 4),
                'dow': round(dow_mult, 4),
                'seasonal': round(seasonal, 4),
                'pace': round(pace, 4),
            },
            'confidence': confidence,
            'capped': capped,
        }

    # ------------------------------------------------------------------
    # Factor 1: Occupancy-based multiplier
    # ------------------------------------------------------------------

    def get_occupancy_multiplier(self, target_date: date) -> float:
        """
        Rate multiplier based on projected occupancy for *target_date*.

        Tiers:
            0-40%  -> 0.85  (discount to stimulate demand)
            40-60% -> 0.95
            60-75% -> 1.00  (base)
            75-85% -> 1.10
            85-95% -> 1.25
            95%+   -> 1.40  (premium)
        """
        total_sellable = _get_total_sellable_count()
        if total_sellable == 0:
            return 1.0

        booked = _count_reservations_for_date(target_date)
        occ_pct = (booked / total_sellable) * 100

        if occ_pct >= 95:
            return 1.40
        elif occ_pct >= 85:
            # Linear interpolation between 1.25 and 1.40
            return round(1.25 + (occ_pct - 85) / 10 * 0.15, 4)
        elif occ_pct >= 75:
            return round(1.10 + (occ_pct - 75) / 10 * 0.15, 4)
        elif occ_pct >= 60:
            return round(1.00 + (occ_pct - 60) / 15 * 0.10, 4)
        elif occ_pct >= 40:
            return round(0.95 + (occ_pct - 40) / 20 * 0.05, 4)
        else:
            return 0.85

    # ------------------------------------------------------------------
    # Factor 2: Day-of-week multiplier
    # ------------------------------------------------------------------

    def get_dow_multiplier(self, target_date: date) -> float:
        """Day-of-week rate adjustment from configurable settings."""
        multipliers = _get_dow_multipliers()
        weekday = str(target_date.weekday())  # 0=Mon ... 6=Sun
        return multipliers.get(weekday, 1.0)

    # ------------------------------------------------------------------
    # Factor 3: Seasonal factor from historical occupancy
    # ------------------------------------------------------------------

    def get_seasonal_factor(self, target_date: date) -> float:
        """
        Detect high/low season from historical occupancy patterns.

        Looks at the same month in previous years (up to 3 years back).
        - Avg occupancy > 75% -> high season  (1.10)
        - Avg occupancy < 40% -> low season   (0.85)
        - Otherwise           -> normal        (1.00)

        Interpolates between boundaries for smoother transitions.
        """
        month = target_date.month
        total_sellable = _get_total_sellable_count()
        if total_sellable == 0:
            return 1.0

        # Gather historical data for the same month across prior years
        today = date.today()
        historical_counts = []

        for years_back in range(1, 4):
            year = today.year - years_back
            if year < 2000:
                continue
            try:
                month_start = date(year, month, 1)
                if month == 12:
                    month_end = date(year + 1, 1, 1)
                else:
                    month_end = date(year, month + 1, 1)
            except ValueError:
                continue

            # Count distinct reservation-nights in this historical month
            nights_booked = Reservation.query.filter(
                Reservation.status.in_(('CheckedIn', 'CheckedOut', 'Reserved', 'Confirmed')),
                Reservation.arrival_date < month_end,
                Reservation.departure_date > month_start,
            ).count()

            # Approximate occupancy: reservations / (sellable rooms * days in month)
            days_in_month = (month_end - month_start).days
            room_nights = total_sellable * days_in_month
            if room_nights > 0:
                historical_counts.append(nights_booked / room_nights * 100)

        if not historical_counts:
            return 1.0

        avg_occ = sum(historical_counts) / len(historical_counts)

        if avg_occ >= 75:
            # High season: scale 1.05 to 1.15 linearly from 75% to 100%
            factor = 1.05 + min((avg_occ - 75) / 25, 1.0) * 0.10
            return round(factor, 4)
        elif avg_occ <= 40:
            # Low season: scale 0.85 to 0.92 linearly from 0% to 40%
            factor = 0.85 + (avg_occ / 40) * 0.07
            return round(factor, 4)
        else:
            # Normal: slight gradient 0.95 to 1.05 between 40% and 75%
            factor = 0.95 + (avg_occ - 40) / 35 * 0.10
            return round(factor, 4)

    # ------------------------------------------------------------------
    # Factor 4: Booking pace factor
    # ------------------------------------------------------------------

    def get_pace_factor(self, room_type_id: int, target_date: date) -> float:
        """
        Compare current booking pace vs historical for same lead time.

        - Ahead of pace  -> 1.05 to 1.15 (can charge more)
        - On pace        -> 1.00
        - Behind pace    -> 0.90 to 0.95 (stimulate demand)
        """
        today = date.today()
        lead_time = (target_date - today).days
        if lead_time < 0:
            return 1.0

        # Current bookings on the books for target_date
        current_count = _count_reservations_for_date(target_date, room_type_id)

        # Historical average: for each of the last 3 years, look at the same
        # target day-of-year with the same lead time window
        historical_counts = []
        for years_back in range(1, 4):
            try:
                hist_target = target_date.replace(year=target_date.year - years_back)
                hist_snapshot = hist_target - timedelta(days=lead_time)
            except ValueError:
                # Feb 29 edge case
                continue

            # How many reservations existed for hist_target that were created
            # before the snapshot date (approximates bookings at same lead time)?
            count = Reservation.query.filter(
                Reservation.room_type_id == room_type_id,
                Reservation.status.in_(('Reserved', 'Confirmed', 'CheckedIn', 'CheckedOut')),
                Reservation.arrival_date <= hist_target,
                Reservation.departure_date > hist_target,
                Reservation.created_at <= datetime.combine(hist_snapshot, datetime.max.time()),
            ).count()
            historical_counts.append(count)

        if not historical_counts or max(historical_counts) == 0:
            # No historical data -- neutral factor
            return 1.0

        avg_historical = sum(historical_counts) / len(historical_counts)
        if avg_historical == 0:
            # If historically zero bookings but we have some now, modest premium
            return 1.05 if current_count > 0 else 1.0

        # Pace ratio
        ratio = current_count / avg_historical

        if ratio >= 1.5:
            return 1.15
        elif ratio >= 1.2:
            # Interpolate 1.05 to 1.15
            return round(1.05 + (ratio - 1.2) / 0.3 * 0.10, 4)
        elif ratio >= 0.8:
            # On pace (0.8 to 1.2) -> slight adjustment
            return round(1.0 + (ratio - 1.0) * 0.25, 4)
        elif ratio >= 0.5:
            # Behind pace
            return round(0.95 - (0.8 - ratio) / 0.3 * 0.05, 4)
        else:
            return 0.90

    # ------------------------------------------------------------------
    # Confidence score
    # ------------------------------------------------------------------

    def _compute_confidence(self, room_type_id: int, target_date: date) -> int:
        """
        Confidence score 0-100 based on data availability.

        Factors:
         - Historical data availability (3 years max, 30 pts each for 2 years)
         - Lead time reasonableness (longer lead = less certain, up to 20 pts)
         - Current occupancy signal strength (20 pts)
        """
        score = 0
        today = date.today()
        lead_time = (target_date - today).days

        # Check historical data availability (up to 60 pts)
        for years_back in range(1, 4):
            try:
                hist_date = target_date.replace(year=target_date.year - years_back)
            except ValueError:
                continue
            hist_start = date(hist_date.year, hist_date.month, 1)
            if hist_date.month == 12:
                hist_end = date(hist_date.year + 1, 1, 1)
            else:
                hist_end = date(hist_date.year, hist_date.month + 1, 1)

            count = Reservation.query.filter(
                Reservation.arrival_date < hist_end,
                Reservation.departure_date > hist_start,
            ).count()
            if count > 0:
                score += 20  # 20 pts per year with data

        # Lead time factor (up to 20 pts -- closer dates are more predictable)
        if 0 <= lead_time <= 7:
            score += 20
        elif lead_time <= 14:
            score += 15
        elif lead_time <= 30:
            score += 10
        else:
            score += 5

        # Current signal strength (up to 20 pts)
        current_booked = _count_reservations_for_date(target_date, room_type_id)
        sellable = _get_sellable_rooms_by_type(room_type_id).get(room_type_id, 0)
        if sellable > 0 and current_booked > 0:
            fill_pct = current_booked / sellable
            score += min(int(fill_pct * 20), 20)

        return min(score, 100)

    # ------------------------------------------------------------------
    # Bulk recommendations
    # ------------------------------------------------------------------

    def generate_rate_recommendations(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Generate rate recommendations for next N days for all room types."""
        if not _get_setting_bool('pricing_enabled'):
            return []

        room_types = RoomType.query.filter_by(is_active=True).all()
        today = date.today()
        recommendations = []

        for day_offset in range(days_ahead):
            target = today + timedelta(days=day_offset)
            for rt in room_types:
                rec = self.get_recommended_rate(rt.id, target)
                if 'error' in rec:
                    continue

                change_pct = 0.0
                if rec['base_rate'] > 0:
                    change_pct = round(
                        (rec['recommended_rate'] - rec['base_rate']) / rec['base_rate'] * 100, 1
                    )

                recommendations.append({
                    'date': target.isoformat(),
                    'date_display': target.strftime('%a, %d %b'),
                    'room_type_id': rt.id,
                    'room_type_name': rt.name,
                    'base_rate': rec['base_rate'],
                    'recommended_rate': rec['recommended_rate'],
                    'change_pct': change_pct,
                    'factors': rec['factors'],
                    'confidence': rec['confidence'],
                    'capped': rec['capped'],
                })

        return recommendations

    # ------------------------------------------------------------------
    # Dashboard data
    # ------------------------------------------------------------------

    def get_pricing_dashboard_data(self, days_ahead: int = 30) -> Dict[str, Any]:
        """Get data for the pricing dashboard including recommendations and charts."""
        recommendations = self.generate_rate_recommendations(days_ahead)

        if not recommendations:
            return {
                'enabled': _get_setting_bool('pricing_enabled'),
                'recommendations': [],
                'summary': {
                    'avg_change_pct': 0,
                    'rooms_increase': 0,
                    'rooms_decrease': 0,
                    'rooms_unchanged': 0,
                    'max_increase': 0,
                    'max_decrease': 0,
                    'total_recommendations': 0,
                },
                'chart_data': {'labels': [], 'datasets': []},
                'settings': self._get_settings_dict(),
            }

        # Summary statistics
        changes = [r['change_pct'] for r in recommendations]
        avg_change = round(sum(changes) / len(changes), 1) if changes else 0
        rooms_increase = sum(1 for c in changes if c > 0.5)
        rooms_decrease = sum(1 for c in changes if c < -0.5)
        rooms_unchanged = len(changes) - rooms_increase - rooms_decrease

        # Chart data: group by date, one dataset per room type
        room_types = sorted(set(r['room_type_name'] for r in recommendations))
        dates = sorted(set(r['date'] for r in recommendations))
        date_labels = []
        for d in dates:
            dt = date.fromisoformat(d)
            date_labels.append(dt.strftime('%d %b'))

        # Color palette for chart lines
        colors = [
            '#0d6efd', '#198754', '#dc3545', '#ffc107', '#6610f2',
            '#fd7e14', '#20c997', '#d63384', '#0dcaf0', '#6c757d',
        ]

        datasets_base = []
        datasets_rec = []
        for idx, rt_name in enumerate(room_types):
            color = colors[idx % len(colors)]
            base_vals = []
            rec_vals = []
            for d in dates:
                match = next(
                    (r for r in recommendations
                     if r['date'] == d and r['room_type_name'] == rt_name),
                    None
                )
                base_vals.append(match['base_rate'] if match else None)
                rec_vals.append(match['recommended_rate'] if match else None)

            datasets_base.append({
                'label': f'{rt_name} (Base)',
                'data': base_vals,
                'borderColor': color,
                'borderDash': [5, 5],
                'fill': False,
                'tension': 0.3,
                'pointRadius': 1,
            })
            datasets_rec.append({
                'label': f'{rt_name} (AI)',
                'data': rec_vals,
                'borderColor': color,
                'fill': False,
                'tension': 0.3,
                'borderWidth': 2,
                'pointRadius': 2,
            })

        chart_data = {
            'labels': date_labels,
            'datasets': datasets_base + datasets_rec,
        }

        return {
            'enabled': _get_setting_bool('pricing_enabled'),
            'recommendations': recommendations,
            'summary': {
                'avg_change_pct': avg_change,
                'rooms_increase': rooms_increase,
                'rooms_decrease': rooms_decrease,
                'rooms_unchanged': rooms_unchanged,
                'max_increase': round(max(changes), 1) if changes else 0,
                'max_decrease': round(min(changes), 1) if changes else 0,
                'total_recommendations': len(recommendations),
            },
            'chart_data': chart_data,
            'settings': self._get_settings_dict(),
        }

    def _get_settings_dict(self) -> Dict[str, Any]:
        return {
            'pricing_enabled': _get_setting_bool('pricing_enabled'),
            'pricing_max_increase_pct': _get_setting_float('pricing_max_increase_pct'),
            'pricing_max_decrease_pct': _get_setting_float('pricing_max_decrease_pct'),
            'pricing_auto_apply': _get_setting_bool('pricing_auto_apply'),
            'pricing_dow_multipliers': _get_dow_multipliers(),
        }


# ---------------------------------------------------------------------------
# Singleton engine (initialised on first request within app context)
# ---------------------------------------------------------------------------

_engine: Optional[DynamicPricingEngine] = None


def get_engine() -> DynamicPricingEngine:
    global _engine
    if _engine is None:
        _engine = DynamicPricingEngine()
    return _engine


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------

def _require_manager():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access restricted to Admin and Manager.', 'danger')
        return redirect(url_for('main.dashboard'))
    return None


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@ai_pricing_bp.before_request
@login_required
def guard():
    pass


@ai_pricing_bp.route('/recommendations')
def recommendations_api():
    """GET /ai/pricing/recommendations?days=30 -- JSON rate recommendations."""
    denied = _require_manager()
    if denied:
        return denied

    days = request.args.get('days', 30, type=int)
    days = max(1, min(days, 90))  # clamp to 1-90

    engine = get_engine()
    recs = engine.generate_rate_recommendations(days_ahead=days)
    return jsonify({
        'success': True,
        'days': days,
        'count': len(recs),
        'recommendations': recs,
    })


@ai_pricing_bp.route('/dashboard')
def dashboard():
    """GET /ai/pricing/dashboard -- full pricing dashboard page."""
    denied = _require_manager()
    if denied:
        return denied

    days = request.args.get('days', 30, type=int)
    days = max(1, min(days, 90))

    engine = get_engine()
    data = engine.get_pricing_dashboard_data(days_ahead=days)

    return render_template(
        'ai/pricing_dashboard.html',
        data=data,
        days=days,
        chart_data_json=json.dumps(data['chart_data']),
    )


@ai_pricing_bp.route('/rate/<int:room_type_id>/<target_date>')
def single_rate(room_type_id, target_date):
    """GET /ai/pricing/rate/<room_type_id>/<YYYY-MM-DD> -- single rate recommendation."""
    denied = _require_manager()
    if denied:
        return denied

    try:
        td = date.fromisoformat(target_date)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    engine = get_engine()
    result = engine.get_recommended_rate(room_type_id, td)

    if 'error' in result:
        return jsonify({'success': False, 'error': result['error']}), 404

    return jsonify({
        'success': True,
        'room_type_id': room_type_id,
        'date': target_date,
        **result,
    })


@ai_pricing_bp.route('/settings', methods=['GET'])
def get_settings():
    """GET /ai/pricing/settings -- current pricing settings as JSON."""
    denied = _require_manager()
    if denied:
        return denied

    engine = get_engine()
    return jsonify({
        'success': True,
        'settings': engine._get_settings_dict(),
    })


@ai_pricing_bp.route('/settings', methods=['POST'])
def update_settings():
    """POST /ai/pricing/settings -- update pricing settings."""
    denied = _require_manager()
    if denied:
        return denied

    payload = request.get_json(silent=True) or {}
    updated = []

    for key in _SETTINGS_DEFAULTS:
        if key in payload:
            val = payload[key]
            # Serialize dicts/lists to JSON strings
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            elif isinstance(val, bool):
                val = 'true' if val else 'false'
            else:
                val = str(val)

            row = Settings.query.filter_by(key=key).first()
            if row:
                row.value = val
            else:
                row = Settings(key=key, value=val, description=f'AI Pricing: {key}')
                db.session.add(row)
            updated.append(key)

    if updated:
        db.session.commit()

    return jsonify({'success': True, 'updated': updated})
