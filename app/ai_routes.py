"""
AI Insights Blueprint -- Forecast, Demand Calendar, Anomaly Detection,
Sentiment & Predictive Maintenance
==================================================================================
Provides API endpoints and page routes for the AI Revenue Forecasting
engine, Demand Calendar heat-map, Payment Anomaly Detection,
Guest Sentiment Dashboard, and Predictive Maintenance.

Endpoints
---------
Pages (HTML):
    /ai/forecast                -- forecast dashboard
    /ai/demand-calendar         -- demand calendar view
    /ai/anomalies               -- payment anomaly detection dashboard
    /ai/sentiment               -- guest sentiment dashboard
    /ai/predictive-maintenance  -- predictive maintenance dashboard

API (JSON):
    GET  /api/ai/forecast?days=90            -- daily revenue forecast
    GET  /api/ai/forecast/monthly            -- monthly summary
    GET  /api/ai/demand-calendar?start=&end= -- calendar heat-map data
    GET  /api/ai/demand-spikes?days=90       -- demand spike detection
    GET  /api/ai/anomalies?days=30&category= -- anomaly scan results
    GET  /api/ai/anomalies/risk/<user_id>    -- per-user risk score
    GET  /api/ai/sentiment?days=90           -- sentiment dashboard data
    GET  /api/ai/predictive-maintenance      -- full dashboard data
    GET  /api/ai/predictive-maintenance/predictions?days=30
    GET  /api/ai/predictive-maintenance/health
    GET  /api/ai/predictive-maintenance/health/<room_id>
    GET  /api/ai/predictive-maintenance/schedules?days=30
    POST /api/ai/predictive-maintenance/schedules/generate
    GET  /api/ai/predictive-maintenance/categories?days=365
    GET  /api/ai/predictive-maintenance/equipment?room_id=
    POST /api/ai/predictive-maintenance/schedules/<id>/complete
    POST /api/ai/predictive-maintenance/schedules/<id>/skip
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.ai_forecast import RevenueForecastEngine, DemandCalendar
from app.services import get_business_date

log = logging.getLogger(__name__)

ai_bp = Blueprint('ai', __name__)


# =========================================================================
# Access guard -- Admin & Manager only
# =========================================================================

def _check_ai_access():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    if current_user.role not in ('Admin', 'Manager'):
        return jsonify({'error': 'Insufficient permissions'}), 403
    return None


# =========================================================================
# Page routes
# =========================================================================

@ai_bp.route('/ai/forecast')
@login_required
def forecast_dashboard():
    if current_user.role not in ('Admin', 'Manager'):
        from flask import abort
        abort(403)
    return render_template('ai/forecast_dashboard.html')


@ai_bp.route('/ai/demand-calendar')
@login_required
def demand_calendar_page():
    if current_user.role not in ('Admin', 'Manager'):
        from flask import abort
        abort(403)
    return render_template('ai/demand_calendar.html')


# =========================================================================
# API -- Revenue Forecast
# =========================================================================

@ai_bp.route('/api/ai/forecast')
@login_required
def api_forecast():
    err = _check_ai_access()
    if err:
        return err
    days = request.args.get('days', 90, type=int)
    days = max(1, min(days, 365))
    engine = RevenueForecastEngine()
    data = engine.forecast_revenue(days_ahead=days)
    return jsonify({'status': 'ok', 'days': days, 'forecast': data})


@ai_bp.route('/api/ai/forecast/monthly')
@login_required
def api_forecast_monthly():
    err = _check_ai_access()
    if err:
        return err
    months = request.args.get('months', 3, type=int)
    months = max(1, min(months, 12))
    engine = RevenueForecastEngine()
    data = engine.get_monthly_summary(months_ahead=months)
    return jsonify({'status': 'ok', 'months': months, 'summary': data})


# =========================================================================
# API -- Demand Calendar
# =========================================================================

@ai_bp.route('/api/ai/demand-calendar')
@login_required
def api_demand_calendar():
    err = _check_ai_access()
    if err:
        return err
    today = get_business_date()
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    try:
        start = date.fromisoformat(start_str) if start_str else today
        end = date.fromisoformat(end_str) if end_str else today + timedelta(days=60)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    # Cap range at 180 days
    if (end - start).days > 180:
        end = start + timedelta(days=180)

    cal = DemandCalendar()
    data = cal.get_calendar_data(start, end)
    return jsonify({'status': 'ok', 'start': start.isoformat(),
                    'end': end.isoformat(), 'calendar': data})


@ai_bp.route('/api/ai/demand-spikes')
@login_required
def api_demand_spikes():
    err = _check_ai_access()
    if err:
        return err
    days = request.args.get('days', 90, type=int)
    days = max(1, min(days, 365))
    cal = DemandCalendar()
    data = cal.detect_demand_spikes(days_ahead=days)
    return jsonify({'status': 'ok', 'days': days, **data})


# =========================================================================
# Page routes -- Anomaly Detection
# =========================================================================

@ai_bp.route('/ai/anomalies')
@login_required
def anomaly_dashboard():
    if current_user.role not in ('Admin', 'Manager'):
        from flask import abort
        abort(403)
    return render_template('ai/anomaly_dashboard.html')


# =========================================================================
# API -- Anomaly Detection
# =========================================================================

@ai_bp.route('/api/ai/anomalies')
@login_required
def api_anomalies():
    """JSON endpoint: run anomaly scan and return findings."""
    err = _check_ai_access()
    if err:
        return err

    from app.ai_anomaly import AnomalyDetector
    detector = AnomalyDetector()

    lookback = request.args.get('days', 30, type=int)
    lookback = max(1, min(lookback, 365))
    category = request.args.get('category')

    try:
        findings = detector.scan_all(lookback)
        if category:
            findings = [f for f in findings if f.get('category') == category]

        summary = {
            'total': len(findings),
            'critical': sum(1 for f in findings if f.get('severity') == 'CRITICAL'),
            'high': sum(1 for f in findings if f.get('severity') == 'HIGH'),
            'medium': sum(1 for f in findings if f.get('severity') == 'MEDIUM'),
            'low': sum(1 for f in findings if f.get('severity') == 'LOW'),
        }

        return jsonify({
            'status': 'ok',
            'lookback_days': lookback,
            'summary': summary,
            'findings': findings,
        })
    except Exception as e:
        log.error('Anomaly scan API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/anomalies/risk/<int:user_id>')
@login_required
def api_risk_score(user_id):
    """JSON endpoint: risk score for a specific staff member."""
    err = _check_ai_access()
    if err:
        return err

    from app.ai_anomaly import AnomalyDetector
    detector = AnomalyDetector()
    lookback = request.args.get('days', 30, type=int)

    try:
        result = detector.get_risk_score(user_id, lookback)
        return jsonify({'status': 'ok', **result})
    except Exception as e:
        log.error('Risk score API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


# =========================================================================
# Page routes -- Sentiment Dashboard
# =========================================================================

@ai_bp.route('/ai/sentiment')
@login_required
def sentiment_dashboard():
    if current_user.role not in ('Admin', 'Manager', 'FrontDesk'):
        from flask import abort
        abort(403)
    return render_template('ai/sentiment_dashboard.html')


# =========================================================================
# API -- Sentiment Dashboard
# =========================================================================

@ai_bp.route('/api/ai/sentiment')
@login_required
def api_sentiment():
    """JSON endpoint: sentiment dashboard data."""
    err = _check_ai_access()
    if err:
        return err

    from app.ai_sentiment import SentimentAnalyzer
    analyzer = SentimentAnalyzer()

    days = request.args.get('days', 90, type=int)
    days = max(1, min(days, 365))

    try:
        data = analyzer.get_dashboard_data(days)
        insights = analyzer.get_actionable_insights(days)

        return jsonify({
            'status': 'ok',
            'days': days,
            'dashboard': data,
            'insights': insights,
        })
    except Exception as e:
        log.error('Sentiment API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


# =========================================================================
# Page routes -- Predictive Maintenance
# =========================================================================

@ai_bp.route('/ai/predictive-maintenance')
@login_required
def predictive_maintenance_dashboard():
    if current_user.role not in ('Admin', 'Manager'):
        from flask import abort
        abort(403)
    return render_template('ai/predictive_maintenance_dashboard.html')


# =========================================================================
# API -- Predictive Maintenance
# =========================================================================

@ai_bp.route('/api/ai/predictive-maintenance')
@login_required
def api_predictive_maintenance():
    """Full dashboard data for predictive maintenance."""
    err = _check_ai_access()
    if err:
        return err
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        data = engine.get_dashboard_data()
        return jsonify({'status': 'ok', **data})
    except Exception as e:
        log.error('Predictive maintenance API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/predictions')
@login_required
def api_pm_predictions():
    err = _check_ai_access()
    if err:
        return err
    days = request.args.get('days', 30, type=int)
    days = max(1, min(days, 180))
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        data = engine.get_failure_predictions(days_ahead=days)
        return jsonify({'status': 'ok', 'days': days, 'predictions': data})
    except Exception as e:
        log.error('PM predictions API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/health')
@login_required
def api_pm_health():
    err = _check_ai_access()
    if err:
        return err
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        scores = engine.get_room_health_scores()
        floor_filter = request.args.get('floor', type=int)
        wing_filter = request.args.get('wing')
        if floor_filter is not None:
            scores = [s for s in scores if s['floor'] == floor_filter]
        if wing_filter:
            scores = [s for s in scores if s['wing'] == wing_filter]
        return jsonify({'status': 'ok', 'room_health': scores})
    except Exception as e:
        log.error('PM health API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/health/<int:room_id>')
@login_required
def api_pm_health_detail(room_id):
    err = _check_ai_access()
    if err:
        return err
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        scores = engine.get_room_health_scores()
        room_data = next((s for s in scores if s['room_id'] == room_id), None)
        trend_days = request.args.get('trend_days', 90, type=int)
        trend = engine.get_health_trend(room_id, days=trend_days)
        return jsonify({
            'status': 'ok',
            'room': room_data,
            'trend': trend,
        })
    except Exception as e:
        log.error('PM health detail API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/schedules')
@login_required
def api_pm_schedules():
    err = _check_ai_access()
    if err:
        return err
    days = request.args.get('days', 30, type=int)
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        data = engine.get_upcoming_schedules(days_ahead=days)
        return jsonify({'status': 'ok', 'schedules': data})
    except Exception as e:
        log.error('PM schedules API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/schedules/generate', methods=['POST'])
@login_required
def api_pm_generate_schedules():
    err = _check_ai_access()
    if err:
        return err
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        result = engine.generate_preventive_schedules(days_ahead=30)
        return jsonify({'status': 'ok', **result})
    except Exception as e:
        log.error('PM schedule generation failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/categories')
@login_required
def api_pm_categories():
    err = _check_ai_access()
    if err:
        return err
    days = request.args.get('days', 365, type=int)
    days = max(1, min(days, 730))
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        data = engine.get_category_analytics(lookback_days=days)
        return jsonify({'status': 'ok', 'categories': data})
    except Exception as e:
        log.error('PM categories API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/equipment')
@login_required
def api_pm_equipment():
    err = _check_ai_access()
    if err:
        return err
    room_id = request.args.get('room_id', type=int)
    try:
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        data = engine.get_equipment_lifecycle(room_id=room_id)
        return jsonify({'status': 'ok', 'equipment': data})
    except Exception as e:
        log.error('PM equipment API failed: %s', e)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@ai_bp.route('/api/ai/predictive-maintenance/schedules/<int:sched_id>/complete', methods=['POST'])
@login_required
def api_pm_complete_schedule(sched_id):
    err = _check_ai_access()
    if err:
        return err
    from app.models import db, PreventiveSchedule
    from datetime import datetime
    sched = PreventiveSchedule.query.get_or_404(sched_id)
    sched.status = 'Completed'
    sched.completed_at = datetime.utcnow()
    body = request.get_json(silent=True) or {}
    if body.get('notes'):
        sched.notes = body['notes']
    db.session.commit()
    return jsonify({'status': 'ok', 'id': sched_id})


@ai_bp.route('/api/ai/predictive-maintenance/schedules/<int:sched_id>/skip', methods=['POST'])
@login_required
def api_pm_skip_schedule(sched_id):
    err = _check_ai_access()
    if err:
        return err
    from app.models import db, PreventiveSchedule
    sched = PreventiveSchedule.query.get_or_404(sched_id)
    sched.status = 'Skipped'
    body = request.get_json(silent=True) or {}
    if body.get('notes'):
        sched.notes = body['notes']
    db.session.commit()
    return jsonify({'status': 'ok', 'id': sched_id})


# ---------------------------------------------------------------------------
# Voice Assistant
# ---------------------------------------------------------------------------

@ai_bp.route('/api/ai/voice', methods=['POST'])
@login_required
def voice_command():
    """Process a voice command and return structured response."""
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'speech': 'I didn\'t hear anything. Please try again.',
                        'action_type': 'error'}), 400

    from app.ai_voice import process_voice_command
    result = process_voice_command(text)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Module 7 — AI Insights (Gemini)
# ---------------------------------------------------------------------------
# Explains WHY today's KPIs/alerts look the way they do and proposes
# concrete next actions. Cached per business_date in app.ai_insights.

def _resolve_mode_with_gate():
    """Read ?mode= from request and enforce per-mode access.

    - mode='frontdesk' (default): Admin/Manager — same as the rest of /ai.
    - mode='ceo':                 App owner only.

    Returns ``(mode, error_response_or_None)``.
    """
    raw = (request.args.get('mode') or 'frontdesk').strip().lower()
    if raw not in ('frontdesk', 'ceo'):
        raw = 'frontdesk'

    if raw == 'ceo':
        if not current_user.is_authenticated:
            return raw, (jsonify({'error': 'Authentication required'}), 401)
        if not getattr(current_user, 'is_app_owner', False):
            return raw, (jsonify({'error': 'Owner access required'}), 403)
        return raw, None

    return raw, _check_ai_access()


@ai_bp.route('/api/ai/insights')
@login_required
def api_ai_insights():
    """Return cached or freshly-generated AI insights for today.

    ``?mode=frontdesk`` (default) — Admin/Manager only.
    ``?mode=ceo``                 — App owner only.

    Falls back to a deterministic heuristic when Gemini is unavailable,
    so this endpoint never 5xx's just because the hotel is offline.
    """
    mode, err = _resolve_mode_with_gate()
    if err:
        return err
    try:
        from app.ai_insights import get_insights
        data = get_insights(mode=mode)
        return jsonify({'status': 'ok', 'insights': data})
    except Exception as exc:
        log.exception('api_ai_insights failed: %s', exc)
        return jsonify({'status': 'error', 'error': str(exc)}), 500


@ai_bp.route('/api/ai/insights/refresh', methods=['POST'])
@login_required
def api_ai_insights_refresh():
    """Force a fresh generation, bypassing the in-process cache.

    Honours the same ``?mode=`` parameter as the GET endpoint, including
    the owner-only gate for ``mode=ceo``.
    """
    mode, err = _resolve_mode_with_gate()
    if err:
        return err
    try:
        from datetime import date as _date
        from app.ai_insights import get_insights, clear_cache
        # Clear only this mode's cache for today — leave the other mode
        # alone so refreshing CEO insights doesn't drop the front-desk
        # cache (and vice versa).
        clear_cache(_date.today(), mode=mode)
        data = get_insights(force_refresh=True, mode=mode)
        return jsonify({'status': 'ok', 'insights': data})
    except Exception as exc:
        log.exception('api_ai_insights_refresh failed: %s', exc)
        return jsonify({'status': 'error', 'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Phase B — CEO KPI pack endpoint
# ---------------------------------------------------------------------------
# Returns the bundled CEO dashboard data (funnel, channel mix, pipeline,
# receivable aging, audit health). Owner only.

@ai_bp.route('/api/ceo/kpi-pack')
@login_required
def api_ceo_kpi_pack():
    if not getattr(current_user, 'is_app_owner', False):
        from flask import abort
        abort(403)
    try:
        from app.ceo_kpis import get_ceo_kpi_pack
        data = get_ceo_kpi_pack()
        return jsonify({'status': 'ok', 'data': data})
    except Exception as exc:
        log.exception('api_ceo_kpi_pack failed: %s', exc)
        return jsonify({'status': 'error', 'error': str(exc)}), 500
