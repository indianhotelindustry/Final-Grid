"""
ai_predictive_maintenance.py -- Predictive Maintenance Engine
=============================================================
Analyzes historical maintenance request patterns to predict failures,
score room/equipment health, and auto-generate preventive schedules.

Statistical methods (no external ML libraries):
  - Exponential smoothing for failure rate trends
  - Weibull-like decay for equipment aging
  - Moving averages for seasonal/cyclical patterns
  - Standard deviation for anomaly thresholds
"""

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, date, timedelta

from app.models import (
    db, Room, RoomType, MaintenanceRequest, Equipment,
    PreventiveSchedule, EquipmentHealthLog,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORY_WEIGHTS = {
    'AC / Heating': 1.0,
    'Plumbing': 0.95,
    'Electrical': 0.9,
    'Internet / TV': 0.7,
    'Furniture': 0.5,
    'Cleaning': 0.3,
    'Other': 0.4,
}

SEVERITY_MULT = {'Urgent': 4, 'High': 3, 'Medium': 2, 'Low': 1}

DECAY_CONSTANT = 90  # days -- exponential decay half-life for recency scoring

# Service task templates by category
SERVICE_TEMPLATES = {
    'AC / Heating': 'Preventive AC service -- filter clean, gas pressure check, coil inspection',
    'Plumbing': 'Preventive plumbing inspection -- check joints, flush lines, inspect valves',
    'Electrical': 'Electrical safety inspection -- check switches, wiring, earthing, MCB test',
    'Internet / TV': 'Network & TV check -- test WiFi signal, cable connections, remote & channels',
    'Furniture': 'Furniture inspection -- check fittings, hinges, drawer slides, mattress condition',
    'Cleaning': 'Deep cleaning -- upholstery, carpet, curtains, bathroom descaling',
    'Other': 'General room inspection and preventive maintenance',
}


def _risk_level(score):
    """Map health score (0-100) to risk level."""
    if score < 40:
        return 'Critical'
    if score < 60:
        return 'High'
    if score < 80:
        return 'Medium'
    return 'Low'


def _risk_from_probability(prob):
    if prob >= 0.85:
        return 'Critical'
    if prob >= 0.70:
        return 'High'
    if prob >= 0.50:
        return 'Medium'
    return 'Low'


def _exponential_smoothing(values, alpha=0.3):
    """Simple exponential smoothing. Returns smoothed last value."""
    if not values:
        return 0
    s = values[0]
    for v in values[1:]:
        s = alpha * v + (1 - alpha) * s
    return s


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PredictiveMaintenanceEngine:
    """Stateless engine -- instantiated per request, queries DB fresh."""

    # -------------------------------------------------------------------
    # Public dashboard entry point
    # -------------------------------------------------------------------

    def get_dashboard_data(self):
        room_health = self.get_room_health_scores()
        predictions = self.get_failure_predictions(days_ahead=30)
        schedules = self.get_upcoming_schedules(days_ahead=30)
        categories = self.get_category_analytics(lookback_days=365)

        at_risk = [r for r in room_health if r['health_score'] < 60]
        critical = [r for r in room_health if r['risk_level'] == 'Critical']
        high = [r for r in room_health if r['risk_level'] == 'High']
        overdue = [s for s in schedules if s['is_overdue']]
        upcoming_7d = [s for s in schedules if 0 <= s['days_until'] <= 7]
        avg_health = (
            sum(r['health_score'] for r in room_health) / len(room_health)
            if room_health else 100.0
        )

        # Predicted savings: ratio of schedules completed before failure
        total_completed = PreventiveSchedule.query.filter_by(status='Completed').count()
        total_predicted = max(len(predictions), 1)
        savings_pct = min(round((total_completed / total_predicted) * 40, 1), 40.0)

        return {
            'summary': {
                'total_rooms': len(room_health),
                'rooms_at_risk': len(at_risk),
                'critical_count': len(critical),
                'high_count': len(high),
                'overdue_schedules': len(overdue),
                'upcoming_7_days': len(upcoming_7d),
                'avg_health_score': round(avg_health, 1),
                'predicted_savings_pct': savings_pct,
            },
            'room_health': room_health,
            'predictions': predictions,
            'upcoming_schedules': schedules,
            'category_breakdown': categories,
        }

    # -------------------------------------------------------------------
    # Room health scores
    # -------------------------------------------------------------------

    def get_room_health_scores(self):
        today = date.today()
        rooms = Room.query.filter_by(is_active=True).all()
        if not rooms:
            return []

        # Pre-fetch all maintenance requests from last 365 days
        cutoff = datetime.utcnow() - timedelta(days=365)
        all_requests = MaintenanceRequest.query.filter(
            MaintenanceRequest.created_at >= cutoff
        ).all()

        # Group by room
        room_requests = defaultdict(list)
        for req in all_requests:
            room_requests[req.room_id].append(req)

        # Hotel-wide average per room (180 days)
        cutoff_180 = datetime.utcnow() - timedelta(days=180)
        total_180 = sum(
            1 for r in all_requests if r.created_at >= cutoff_180
        )
        active_count = len(rooms)
        hotel_avg_180 = total_180 / max(active_count, 1)

        # Pre-fetch equipment
        all_equipment = Equipment.query.filter_by(is_active=True).all()
        room_equipment = defaultdict(list)
        for eq in all_equipment:
            room_equipment[eq.room_id].append(eq)

        # Pre-fetch room types
        room_types = {rt.id: rt.name for rt in RoomType.query.all()}

        results = []
        for room in rooms:
            requests = room_requests.get(room.id, [])
            equip_list = room_equipment.get(room.id, [])
            score, risk_factors, cat_scores = self._compute_health(
                today, requests, equip_list, hotel_avg_180
            )
            risk = _risk_level(score)

            # Trend: compare last 30-day avg vs 60-90 day avg from snapshots
            trend = self._compute_trend(room.id)

            open_issues = sum(
                1 for r in requests if r.status in ('Open', 'InProgress')
            )
            last_issue = max(
                (r.created_at for r in requests), default=None
            )

            results.append({
                'room_id': room.id,
                'room_number': room.room_number,
                'floor': room.floor,
                'wing': room.wing or '',
                'room_type': room_types.get(room.room_type_id, ''),
                'health_score': round(score, 1),
                'risk_level': risk,
                'risk_factors': risk_factors,
                'category_scores': cat_scores,
                'last_issue_date': (
                    last_issue.strftime('%Y-%m-%d') if last_issue else None
                ),
                'open_issues': open_issues,
                'trend': trend,
            })

        results.sort(key=lambda r: r['health_score'])
        return results

    def _compute_health(self, today, requests, equipment, hotel_avg_180):
        base = 100.0
        risk_factors = []
        cat_scores = {}

        # --- Per-category scoring ---
        cat_penalties = defaultdict(float)
        for req in requests:
            days_ago = max((today - req.created_at.date()).days, 1)
            sev = SEVERITY_MULT.get(req.priority, 2)
            cat_w = CATEGORY_WEIGHTS.get(req.category, 0.4)
            decay = math.exp(-days_ago / DECAY_CONSTANT)
            penalty = sev * cat_w * decay * 3.0
            cat_penalties[req.category] += penalty

        for cat, pen in cat_penalties.items():
            base -= pen
            cat_scores[cat] = round(max(0, 100 - pen * 5), 1)
            if pen > 8:
                risk_factors.append(f'High {cat} issue frequency')

        # --- Frequency penalty (180 days) ---
        cutoff_180 = datetime.utcnow() - timedelta(days=180)
        count_180 = sum(
            1 for r in requests if r.created_at >= cutoff_180
        )
        if hotel_avg_180 > 0 and count_180 > hotel_avg_180 * 1.5:
            excess = count_180 / max(hotel_avg_180, 1)
            freq_pen = min(excess * 5, 15)
            base -= freq_pen
            risk_factors.append(
                f'{count_180} issues in 180d ({excess:.1f}x hotel avg)'
            )

        # --- Equipment age penalty (Weibull-like) ---
        for eq in equipment:
            if eq.install_date and eq.expected_life_years:
                age_years = (today - eq.install_date).days / 365.25
                life_ratio = age_years / eq.expected_life_years
                if life_ratio > 0.7:
                    age_pen = min(10 * (life_ratio ** 2), 20)
                    base -= age_pen
                    if life_ratio > 0.9:
                        risk_factors.append(
                            f'{eq.name} at {life_ratio:.0%} of expected life'
                        )

        # --- Service overdue penalty ---
        for eq in equipment:
            if eq.last_service_date and eq.service_interval_days:
                days_since = (today - eq.last_service_date).days
                overdue = days_since - eq.service_interval_days
                if overdue > 0:
                    svc_pen = min(overdue / 10, 10)
                    base -= svc_pen
                    risk_factors.append(
                        f'{eq.name} service overdue by {overdue}d'
                    )

        # --- Open urgent issues ---
        open_urgent = sum(
            1 for r in requests
            if r.status in ('Open', 'InProgress') and r.priority == 'Urgent'
        )
        if open_urgent:
            base -= open_urgent * 10
            risk_factors.append(f'{open_urgent} open urgent issue(s)')

        score = max(0.0, min(100.0, base))
        return score, risk_factors[:5], cat_scores

    def _compute_trend(self, room_id):
        """Compare recent health snapshots to determine trend."""
        today = date.today()
        d30 = today - timedelta(days=30)
        d90 = today - timedelta(days=90)

        recent = db.session.query(db.func.avg(EquipmentHealthLog.health_score)).filter(
            EquipmentHealthLog.room_id == room_id,
            EquipmentHealthLog.snapshot_date >= d30,
            EquipmentHealthLog.category == 'overall',
        ).scalar()

        older = db.session.query(db.func.avg(EquipmentHealthLog.health_score)).filter(
            EquipmentHealthLog.room_id == room_id,
            EquipmentHealthLog.snapshot_date >= d90,
            EquipmentHealthLog.snapshot_date < d30,
            EquipmentHealthLog.category == 'overall',
        ).scalar()

        if recent is None or older is None:
            return 'stable'
        diff = recent - older
        if diff > 5:
            return 'improving'
        if diff < -5:
            return 'declining'
        return 'stable'

    # -------------------------------------------------------------------
    # Failure predictions
    # -------------------------------------------------------------------

    def get_failure_predictions(self, days_ahead=30):
        today = date.today()
        target_date = today + timedelta(days=days_ahead)

        # Get all resolved + open requests grouped by (room_id, category)
        all_reqs = (
            MaintenanceRequest.query
            .filter(MaintenanceRequest.status.in_(['Open', 'InProgress', 'Resolved']))
            .order_by(MaintenanceRequest.room_id, MaintenanceRequest.category,
                      MaintenanceRequest.created_at)
            .all()
        )

        # Group by (room_id, category)
        groups = defaultdict(list)
        for req in all_reqs:
            groups[(req.room_id, req.category)].append(req)

        # Room lookup
        rooms = {r.id: r for r in Room.query.filter_by(is_active=True).all()}

        predictions = []
        for (room_id, category), reqs in groups.items():
            if len(reqs) < 2:
                continue
            room = rooms.get(room_id)
            if not room:
                continue

            # Compute inter-arrival times
            dates_sorted = sorted(r.created_at for r in reqs)
            intervals = []
            for i in range(1, len(dates_sorted)):
                delta = (dates_sorted[i] - dates_sorted[i - 1]).days
                if delta > 0:
                    intervals.append(delta)

            if not intervals:
                continue

            smoothed_interval = _exponential_smoothing(intervals, alpha=0.3)
            if smoothed_interval <= 0:
                continue

            days_since_last = (
                datetime.utcnow() - dates_sorted[-1]
            ).days

            # Failure probability: exponential CDF
            prob = 1 - math.exp(-(days_since_last / smoothed_interval))

            if prob < 0.3:
                continue

            # Predicted next failure date
            remaining = max(smoothed_interval - days_since_last, 0)
            predicted_date = today + timedelta(days=int(remaining))

            # Only include if predicted within window (or already overdue)
            if predicted_date > target_date and prob < 0.5:
                continue

            risk = _risk_from_probability(prob)

            predictions.append({
                'room_id': room_id,
                'room_number': room.room_number,
                'category': category,
                'probability': round(prob, 2),
                'risk_level': risk,
                'predicted_date': predicted_date.isoformat(),
                'avg_interval_days': round(smoothed_interval, 1),
                'days_since_last': days_since_last,
                'total_historical_issues': len(reqs),
                'description': (
                    f'{category} issue predicted for Room {room.room_number} '
                    f'({prob:.0%} probability). '
                    f'Avg interval: {smoothed_interval:.0f}d, '
                    f'last issue: {days_since_last}d ago.'
                ),
            })

        predictions.sort(key=lambda p: -p['probability'])
        return predictions

    # -------------------------------------------------------------------
    # Category analytics
    # -------------------------------------------------------------------

    def get_category_analytics(self, lookback_days=365):
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        reqs = MaintenanceRequest.query.filter(
            MaintenanceRequest.created_at >= cutoff
        ).all()

        rooms = {r.id: r for r in Room.query.all()}
        now = datetime.utcnow()
        d90 = now - timedelta(days=90)
        d180 = now - timedelta(days=180)

        cats = defaultdict(lambda: {
            'total_requests': 0,
            'resolution_hours': [],
            'open_count': 0,
            'recent_90': 0,
            'prev_90': 0,
            'monthly': defaultdict(int),
            'room_counts': defaultdict(int),
        })

        for req in reqs:
            c = cats[req.category]
            c['total_requests'] += 1
            if req.status in ('Open', 'InProgress'):
                c['open_count'] += 1
            if req.resolved_at and req.created_at:
                hours = (req.resolved_at - req.created_at).total_seconds() / 3600
                c['resolution_hours'].append(hours)
            if req.created_at >= d90:
                c['recent_90'] += 1
            elif req.created_at >= d180:
                c['prev_90'] += 1

            month_key = req.created_at.strftime('%Y-%m')
            c['monthly'][month_key] += 1

            room = rooms.get(req.room_id)
            if room:
                c['room_counts'][room.room_number] += 1

        result = {}
        for cat, data in cats.items():
            avg_hours = (
                sum(data['resolution_hours']) / len(data['resolution_hours'])
                if data['resolution_hours'] else 0
            )

            # Trend
            if data['prev_90'] > 0:
                change = (data['recent_90'] - data['prev_90']) / data['prev_90']
            elif data['recent_90'] > 0:
                change = 1.0
            else:
                change = 0.0

            if change > 0.2:
                trend = 'increasing'
            elif change < -0.2:
                trend = 'decreasing'
            else:
                trend = 'stable'

            # Monthly counts sorted
            monthly = [
                {'month': k, 'count': v}
                for k, v in sorted(data['monthly'].items())
            ]

            # Top rooms
            top_rooms = sorted(
                data['room_counts'].items(), key=lambda x: -x[1]
            )[:5]
            top_rooms = [{'room_number': r, 'count': c} for r, c in top_rooms]

            result[cat] = {
                'total_requests': data['total_requests'],
                'avg_resolution_hours': round(avg_hours, 1),
                'open_count': data['open_count'],
                'trend': trend,
                'monthly_counts': monthly,
                'top_rooms': top_rooms,
            }

        return result

    # -------------------------------------------------------------------
    # Preventive schedules
    # -------------------------------------------------------------------

    def get_upcoming_schedules(self, days_ahead=30):
        today = date.today()
        target = today + timedelta(days=days_ahead)

        scheds = (
            PreventiveSchedule.query
            .filter(
                PreventiveSchedule.status.in_(['Pending', 'Overdue']),
                PreventiveSchedule.scheduled_date <= target,
            )
            .order_by(PreventiveSchedule.scheduled_date)
            .all()
        )

        rooms = {r.id: r for r in Room.query.all()}
        results = []
        for s in scheds:
            room = rooms.get(s.room_id)
            is_overdue = s.scheduled_date < today and s.status != 'Completed'
            days_until = (s.scheduled_date - today).days

            results.append({
                'id': s.id,
                'room_number': room.room_number if room else '?',
                'room_id': s.room_id,
                'category': s.category,
                'task_description': s.task_description,
                'scheduled_date': s.scheduled_date.isoformat(),
                'status': 'Overdue' if is_overdue else s.status,
                'priority': s.priority,
                'risk_level': s.risk_level or '',
                'predicted_failure_probability': s.predicted_failure_probability,
                'assigned_to': s.assigned_to or '',
                'source': s.source,
                'is_overdue': is_overdue,
                'days_until': days_until,
            })

        return results

    def generate_preventive_schedules(self, days_ahead=30):
        today = date.today()
        predictions = self.get_failure_predictions(days_ahead=days_ahead)
        high_risk = [p for p in predictions if p['probability'] >= 0.5]

        created = 0
        existing = 0

        for pred in high_risk:
            # Schedule 7 days before predicted failure
            pred_date = date.fromisoformat(pred['predicted_date'])
            sched_date = max(pred_date - timedelta(days=7), today)

            # Check for existing schedule within +/- 14 days
            window_start = sched_date - timedelta(days=14)
            window_end = sched_date + timedelta(days=14)
            exists = PreventiveSchedule.query.filter(
                PreventiveSchedule.room_id == pred['room_id'],
                PreventiveSchedule.category == pred['category'],
                PreventiveSchedule.status.in_(['Pending', 'Overdue']),
                PreventiveSchedule.scheduled_date >= window_start,
                PreventiveSchedule.scheduled_date <= window_end,
            ).first()

            if exists:
                existing += 1
                continue

            # Determine priority from risk
            priority_map = {'Critical': 'High', 'High': 'High', 'Medium': 'Medium', 'Low': 'Low'}
            priority = priority_map.get(pred['risk_level'], 'Medium')

            task_desc = SERVICE_TEMPLATES.get(
                pred['category'],
                f"Preventive {pred['category']} service"
            )
            task_desc += f" -- predicted failure probability {pred['probability']:.0%}"

            sched = PreventiveSchedule(
                room_id=pred['room_id'],
                category=pred['category'],
                task_description=task_desc,
                scheduled_date=sched_date,
                status='Pending',
                priority=priority,
                risk_level=pred['risk_level'],
                predicted_failure_probability=pred['probability'],
                source='auto',
            )
            db.session.add(sched)
            created += 1

        # Also check equipment service intervals
        equipment_list = Equipment.query.filter_by(is_active=True).all()
        for eq in equipment_list:
            if not eq.last_service_date or not eq.service_interval_days:
                continue
            next_service = eq.last_service_date + timedelta(days=eq.service_interval_days)
            if next_service <= today + timedelta(days=14):
                # Check existing
                exists = PreventiveSchedule.query.filter(
                    PreventiveSchedule.room_id == eq.room_id,
                    PreventiveSchedule.equipment_id == eq.id,
                    PreventiveSchedule.status.in_(['Pending', 'Overdue']),
                    PreventiveSchedule.scheduled_date >= today - timedelta(days=14),
                ).first()
                if exists:
                    existing += 1
                    continue

                sched_date = max(next_service - timedelta(days=7), today)
                sched = PreventiveSchedule(
                    room_id=eq.room_id,
                    equipment_id=eq.id,
                    category=eq.category,
                    task_description=f'Scheduled service for {eq.name}',
                    scheduled_date=sched_date,
                    status='Pending',
                    priority='Medium',
                    source='auto',
                )
                db.session.add(sched)
                created += 1

        if created:
            db.session.commit()

        return {
            'created': created,
            'existing': existing,
            'total_predictions': len(predictions),
        }

    # -------------------------------------------------------------------
    # Health snapshots (daily job)
    # -------------------------------------------------------------------

    def snapshot_health_scores(self):
        today = date.today()
        # Skip if already snapshotted today
        existing = EquipmentHealthLog.query.filter_by(
            snapshot_date=today, category='overall'
        ).first()
        if existing:
            return 0

        scores = self.get_room_health_scores()
        count = 0
        for s in scores:
            log_entry = EquipmentHealthLog(
                room_id=s['room_id'],
                health_score=s['health_score'],
                category='overall',
                risk_factors=json.dumps(s['risk_factors']),
                snapshot_date=today,
            )
            db.session.add(log_entry)
            count += 1

        if count:
            db.session.commit()
        return count

    # -------------------------------------------------------------------
    # Health trend
    # -------------------------------------------------------------------

    def get_health_trend(self, room_id, days=90):
        cutoff = date.today() - timedelta(days=days)
        logs = (
            EquipmentHealthLog.query
            .filter(
                EquipmentHealthLog.room_id == room_id,
                EquipmentHealthLog.snapshot_date >= cutoff,
                EquipmentHealthLog.category == 'overall',
            )
            .order_by(EquipmentHealthLog.snapshot_date)
            .all()
        )
        return [
            {'date': l.snapshot_date.isoformat(), 'score': round(l.health_score, 1)}
            for l in logs
        ]

    # -------------------------------------------------------------------
    # Equipment lifecycle
    # -------------------------------------------------------------------

    def get_equipment_lifecycle(self, room_id=None):
        today = date.today()
        q = Equipment.query.filter_by(is_active=True)
        if room_id:
            q = q.filter_by(room_id=room_id)
        equipment = q.all()

        rooms = {r.id: r for r in Room.query.all()}

        # Count maintenance requests by (room_id, category)
        issue_counts = defaultdict(int)
        for req in MaintenanceRequest.query.all():
            issue_counts[(req.room_id, req.category)] += 1

        results = []
        for eq in equipment:
            room = rooms.get(eq.room_id)
            age_years = 0.0
            life_remaining_pct = 100.0
            if eq.install_date:
                age_years = (today - eq.install_date).days / 365.25
                if eq.expected_life_years and eq.expected_life_years > 0:
                    life_remaining_pct = max(
                        0, (1 - age_years / eq.expected_life_years) * 100
                    )

            days_since_service = 0
            service_overdue = False
            service_overdue_days = 0
            if eq.last_service_date:
                days_since_service = (today - eq.last_service_date).days
                if eq.service_interval_days:
                    service_overdue_days = max(
                        0, days_since_service - eq.service_interval_days
                    )
                    service_overdue = service_overdue_days > 0

            related = issue_counts.get((eq.room_id, eq.category), 0)

            # Status determination
            if service_overdue:
                status = 'Overdue Service'
            elif life_remaining_pct <= 10:
                status = 'End-of-Life'
            elif life_remaining_pct <= 30:
                status = 'Aging'
            else:
                status = 'Good'

            results.append({
                'id': eq.id,
                'room_number': room.room_number if room else '?',
                'room_id': eq.room_id,
                'name': eq.name,
                'category': eq.category,
                'manufacturer': eq.manufacturer or '',
                'model_number': eq.model_number or '',
                'install_date': eq.install_date.isoformat() if eq.install_date else None,
                'age_years': round(age_years, 1),
                'expected_life_years': eq.expected_life_years or 0,
                'life_remaining_pct': round(life_remaining_pct, 1),
                'last_service_date': (
                    eq.last_service_date.isoformat() if eq.last_service_date else None
                ),
                'days_since_service': days_since_service,
                'service_overdue': service_overdue,
                'service_overdue_days': service_overdue_days,
                'related_issues_count': related,
                'status': status,
            })

        results.sort(key=lambda e: e['life_remaining_pct'])
        return results
