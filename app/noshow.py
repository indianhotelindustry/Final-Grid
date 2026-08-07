"""
No-Show Blueprint  (/noshow/*)
===============================
Routes for:
  - Pending no-show review (Manager/Admin before night audit)
  - Manager exemption / un-exemption
  - Manual no-show posting
  - No-show report (Admin/Manager/Accountant)

Role access:
  - Pending review + exemption + manual post: Manager, Admin
  - Report: Admin, Manager, Accountant
"""
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import NoShowLog, Reservation, db
from app.services import get_business_date
from app import noshow_service, limiter

noshow_bp = Blueprint('noshow', __name__, url_prefix='/noshow')


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def _manager_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role not in ('Admin', 'Manager'):
            flash('Manager or Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


def _report_access_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role not in ('Admin', 'Manager', 'Accountant'):
            flash('Access denied.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Pending no-shows (today's expected arrivals that haven't checked in)
# ---------------------------------------------------------------------------

@noshow_bp.route('/pending')
@_manager_required
def pending():
    business_date = get_business_date()
    candidates = noshow_service.get_pending_noshows(business_date)
    return render_template(
        'noshow/pending.html',
        candidates=candidates,
        business_date=business_date,
    )


# ---------------------------------------------------------------------------
# Exemption management
# ---------------------------------------------------------------------------

@noshow_bp.route('/exempt/<int:reservation_id>', methods=['POST'])
@_manager_required
@limiter.limit('30 per minute')
def exempt(reservation_id):
    note = request.form.get('note', '').strip()
    ok, msg = noshow_service.exempt_reservation(reservation_id, current_user.id, note)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('noshow.pending'))


@noshow_bp.route('/unexempt/<int:reservation_id>', methods=['POST'])
@_manager_required
@limiter.limit('30 per minute')
def unexempt(reservation_id):
    ok, msg = noshow_service.remove_exemption(reservation_id, current_user.id)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('noshow.pending'))


# ---------------------------------------------------------------------------
# Manual no-show posting
# ---------------------------------------------------------------------------

@noshow_bp.route('/manual/<int:reservation_id>', methods=['POST'])
@_manager_required
@limiter.limit('20 per minute; 60 per hour')
def manual_post(reservation_id):
    note = request.form.get('note', '').strip()
    result = noshow_service.manual_noshow(reservation_id, current_user.id, note)
    flash(result.message, 'success' if result.success else 'danger')
    # Redirect back to the reservation list
    return redirect(url_for('main.reservations'))


# ---------------------------------------------------------------------------
# No-show report
# ---------------------------------------------------------------------------

@noshow_bp.route('/report')
@_report_access_required
def report():
    from datetime import date

    from_str = request.args.get('from_date', '')
    to_str = request.args.get('to_date', '')

    try:
        from_date = date.fromisoformat(from_str) if from_str else date.today().replace(day=1)
        to_date = date.fromisoformat(to_str) if to_str else date.today()
    except ValueError:
        from_date = date.today().replace(day=1)
        to_date = date.today()

    logs = (
        NoShowLog.query
        .join(Reservation)
        .filter(
            NoShowLog.audit_date >= from_date,
            NoShowLog.audit_date <= to_date,
        )
        .order_by(NoShowLog.audit_date.desc(), NoShowLog.posted_at.desc())
        .all()
    )

    total_count  = len(logs)
    ota_count    = sum(1 for l in logs if l.is_ota)
    direct_count = total_count - ota_count
    total_fees   = sum(float(l.fee_amount or 0) for l in logs)
    fee_applied_count = sum(1 for l in logs if l.fee_applied)

    return render_template(
        'noshow/report.html',
        logs=logs,
        from_date=from_date,
        to_date=to_date,
        total_count=total_count,
        ota_count=ota_count,
        direct_count=direct_count,
        total_fees=total_fees,
        fee_applied_count=fee_applied_count,
    )
