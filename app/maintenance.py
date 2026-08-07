"""
Maintenance Module Blueprint
==============================
Track room maintenance issues, assign staff, and monitor resolution.

Routes:
  GET  /maintenance/              — List all open requests + summary
  POST /maintenance/create        — Report a new issue
  POST /maintenance/<id>/update   — Update status / assign / add notes
  POST /maintenance/<id>/resolve  — Mark resolved
  GET  /maintenance/history       — View resolved requests (last 90 days)

When a room has an Urgent open issue, it is automatically set to
'Maintenance' status (blocked from new check-ins).
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, Room, MaintenanceRequest
from app.services import get_business_date

maintenance_bp = Blueprint('maintenance', __name__, url_prefix='/maintenance')

CATEGORIES = ['Plumbing', 'Electrical', 'AC / Heating', 'Furniture', 'Cleaning', 'Internet / TV', 'Other']
PRIORITIES = ['Low', 'Medium', 'High', 'Urgent']


@maintenance_bp.before_request
@login_required
def guard():
    pass


def _block_room_if_urgent(room):
    """Set room to Maintenance if it has any Urgent open request."""
    urgent = MaintenanceRequest.query.filter(
        MaintenanceRequest.room_id == room.id,
        MaintenanceRequest.status.in_(['Open', 'InProgress']),
        MaintenanceRequest.priority == 'Urgent',
    ).first()
    if urgent and room.status not in ('Occupied', 'Maintenance'):
        room.status = 'Maintenance'
        db.session.flush()


# ---------------------------------------------------------------------------
# Main list view
# ---------------------------------------------------------------------------

@maintenance_bp.route('/')
def index():
    status_filter = request.args.get('status', 'open')
    priority_filter = request.args.get('priority', '')

    q = MaintenanceRequest.query

    if status_filter == 'open':
        q = q.filter(MaintenanceRequest.status.in_(['Open', 'InProgress']))
    elif status_filter == 'resolved':
        q = q.filter(MaintenanceRequest.status == 'Resolved')
    # 'all' shows everything

    if priority_filter:
        q = q.filter(MaintenanceRequest.priority == priority_filter)

    requests_list = q.order_by(
        db.case(
            (MaintenanceRequest.priority == 'Urgent', 1),
            (MaintenanceRequest.priority == 'High', 2),
            (MaintenanceRequest.priority == 'Medium', 3),
            else_=4
        ),
        MaintenanceRequest.created_at.desc()
    ).all()

    # Summary counts
    open_count = MaintenanceRequest.query.filter(MaintenanceRequest.status.in_(['Open', 'InProgress'])).count()
    urgent_count = MaintenanceRequest.query.filter(
        MaintenanceRequest.status.in_(['Open', 'InProgress']),
        MaintenanceRequest.priority == 'Urgent'
    ).count()
    resolved_today = MaintenanceRequest.query.filter(
        MaintenanceRequest.status == 'Resolved',
        MaintenanceRequest.resolved_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()

    rooms = Room.query.order_by(Room.room_number).all()

    return render_template(
        'maintenance/index.html',
        requests_list=requests_list,
        rooms=rooms,
        categories=CATEGORIES,
        priorities=PRIORITIES,
        open_count=open_count,
        urgent_count=urgent_count,
        resolved_today=resolved_today,
        status_filter=status_filter,
        priority_filter=priority_filter,
    )


# ---------------------------------------------------------------------------
# Create a request
# ---------------------------------------------------------------------------

@maintenance_bp.route('/create', methods=['POST'])
def create():
    room_id = request.form.get('room_id', type=int)
    category = request.form.get('category', 'Other')
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'Medium')

    if not room_id or not description:
        flash('Room and description are required.', 'danger')
        return redirect(url_for('maintenance.index'))

    try:
        req = MaintenanceRequest(
            room_id=room_id,
            category=category,
            description=description,
            priority=priority,
            status='Open',
            reported_by=current_user.full_name or current_user.username,
        )
        db.session.add(req)

        # Auto-block room if urgent — lock room to prevent concurrent status changes
        if priority == 'Urgent':
            room = db.session.query(Room).with_for_update().filter_by(id=room_id).first()
            if room and room.status not in ('Occupied',):
                room.status = 'Maintenance'

        db.session.commit()
        room_obj = db.session.get(Room, room_id)
        flash(f'{priority} maintenance request created for Room {room_obj.room_number}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to create maintenance request: {str(e)}', 'danger')
    return redirect(url_for('maintenance.index'))


# ---------------------------------------------------------------------------
# Update a request (assign / change priority / add notes)
# ---------------------------------------------------------------------------

@maintenance_bp.route('/<int:req_id>/update', methods=['POST'])
def update(req_id):
    req = MaintenanceRequest.query.get_or_404(req_id)

    new_status = request.form.get('status')
    assigned_to = request.form.get('assigned_to', '').strip()
    notes = request.form.get('notes', '').strip()
    priority = request.form.get('priority')

    if new_status:
        req.status = new_status
    if assigned_to:
        req.assigned_to = assigned_to
    if notes:
        req.notes = (req.notes or '') + f'\n[{datetime.utcnow().strftime("%d %b %H:%M")}] {notes}'.strip()
    if priority:
        req.priority = priority

    db.session.commit()
    flash('Maintenance request updated.', 'success')
    return redirect(url_for('maintenance.index'))


# ---------------------------------------------------------------------------
# Resolve a request
# ---------------------------------------------------------------------------

@maintenance_bp.route('/<int:req_id>/resolve', methods=['POST'])
def resolve(req_id):
    req = MaintenanceRequest.query.get_or_404(req_id)
    resolution_note = request.form.get('resolution_note', '').strip()

    try:
        req.status = 'Resolved'
        req.resolved_at = datetime.utcnow()
        if resolution_note:
            req.notes = ((req.notes or '') + f'\n✅ Resolved: {resolution_note}').strip()

        # Release room from Maintenance status if no more open urgent issues
        # Lock room to prevent concurrent status changes
        room = db.session.query(Room).with_for_update().filter_by(id=req.room_id).first()
        other_urgent = MaintenanceRequest.query.filter(
            MaintenanceRequest.room_id == room.id,
            MaintenanceRequest.id != req_id,
            MaintenanceRequest.status.in_(['Open', 'InProgress']),
            MaintenanceRequest.priority == 'Urgent',
        ).first()

        if not other_urgent and room.status == 'Maintenance':
            room.status = 'Vacant'

        db.session.commit()
        flash(f'Maintenance request #{req_id} resolved. Room {room.room_number} released.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to resolve maintenance request: {str(e)}', 'danger')
    return redirect(url_for('maintenance.index'))
