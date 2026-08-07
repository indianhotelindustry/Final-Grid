"""
Group Reservation Module Blueprint
====================================
Manage group blocks for weddings, corporate events, and tour groups.

Routes:
  GET  /groups/              — List all group blocks
  GET  /groups/new           — Form to create a new group block
  POST /groups/new           — Create a group block (generates unique group_code)
  GET  /groups/<id>          — View group detail with rooming list
  POST /groups/<id>/add-room — Add a reservation to the group
  POST /groups/<id>/batch-checkin — Check in all confirmed reservations
  POST /groups/<id>/update-status — Update group block status
"""

import secrets
import string
from datetime import datetime, date
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.auth import role_required
from app.models import (
    db, GroupBlock, Reservation, Guest, Room, RoomType, Company, PaymentMode,
)
from app.validators import (
    validate_fields, validate_phone_optional, validate_email,
    validate_name, validate_phone, validate_positive_int,
    validate_non_negative_float, validate_text_length,
)

groups_bp = Blueprint('groups', __name__, url_prefix='/groups',
                      template_folder='templates/groups')


def _generate_group_code():
    """Generate a unique 8-char group code like GRP-XXXX."""
    charset = string.ascii_uppercase + string.digits
    for _ in range(100):  # avoid infinite loop
        code = 'GRP-' + ''.join(secrets.choice(charset) for _ in range(4))
        if not GroupBlock.query.filter_by(group_code=code).first():
            return code
    # Fallback: use timestamp suffix
    return 'GRP-' + secrets.token_hex(3).upper()[:4]


# ---------------------------------------------------------------------------
# Before-request guard: Admin or Manager only
# ---------------------------------------------------------------------------
@groups_bp.before_request
@login_required
def _require_login():
    pass


# ---------------------------------------------------------------------------
# GET /groups/ — List all group blocks
# ---------------------------------------------------------------------------
@groups_bp.route('/')
@role_required('Admin', 'Manager')
def index():
    status_filter = request.args.get('status', '')
    query = GroupBlock.query.order_by(GroupBlock.arrival_date.desc())
    if status_filter:
        query = query.filter(GroupBlock.status == status_filter)
    groups = query.all()

    # Calculate picked-up rooms for each group
    for g in groups:
        g.picked_up = Reservation.query.filter(
            Reservation.group_block_id == g.id,
            Reservation.status.notin_(['Cancelled'])
        ).count()

    return render_template('groups/index.html', groups=groups,
                           status_filter=status_filter)


# ---------------------------------------------------------------------------
# GET/POST /groups/new — Create a new group block
# ---------------------------------------------------------------------------
@groups_bp.route('/new', methods=['GET', 'POST'])
@role_required('Admin', 'Manager')
def new_group():
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    room_types = RoomType.query.filter_by(is_active=True).order_by(RoomType.name).all()

    # Build rooms-by-type lookup for JS (only Vacant rooms)
    rooms_by_type = {}
    vacant_rooms = Room.query.filter_by(status='Vacant', is_active=True).order_by(Room.room_number).all()
    for rm in vacant_rooms:
        rooms_by_type.setdefault(str(rm.room_type_id), []).append({
            'id': rm.id,
            'room_number': rm.room_number,
            'floor': rm.floor,
        })

    if request.method == 'POST':
        group_name = request.form.get('group_name', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        contact_email = request.form.get('contact_email', '').strip()

        try:
            arrival = datetime.strptime(request.form.get('arrival_date', ''), '%Y-%m-%d').date()
            departure = datetime.strptime(request.form.get('departure_date', ''), '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid arrival or departure date.', 'danger')
            return render_template('groups/new.html', companies=companies,
                                   room_types=room_types, rooms_by_type=rooms_by_type)

        group_rate_str = request.form.get('group_rate', '').strip()

        # Room allocation rows from form
        room_type_ids = request.form.getlist('room_type_id[]')
        room_ids = request.form.getlist('room_id[]')
        adults_list = request.form.getlist('adults[]')
        children_list = request.form.getlist('children[]')

        # Filter out empty rows
        room_rows = []
        for i, rt_id in enumerate(room_type_ids):
            if rt_id:
                room_rows.append({
                    'room_type_id': int(rt_id),
                    'room_id': int(room_ids[i]) if i < len(room_ids) and room_ids[i] else None,
                    'adults': int(adults_list[i]) if i < len(adults_list) and adults_list[i] else 1,
                    'children': int(children_list[i]) if i < len(children_list) and children_list[i] else 0,
                })

        total_rooms = len(room_rows) if room_rows else 1

        grp_errs = validate_fields(
            validate_name(group_name, 'Group name', max_len=200),
            validate_phone_optional(contact_phone, 'Contact phone'),
            validate_email(contact_email),
            validate_non_negative_float(group_rate_str, 'Group rate') if group_rate_str else None,
            validate_text_length(request.form.get('notes', ''), 'Notes', max_len=1000),
            validate_text_length(request.form.get('billing_instructions', ''), 'Billing instructions', max_len=1000),
        )
        if departure <= arrival:
            grp_errs.append('Departure date must be after arrival date.')
        if not room_rows:
            grp_errs.append('At least one room must be allocated.')
        if grp_errs:
            for e in grp_errs:
                flash(e, 'danger')
            return render_template('groups/new.html', companies=companies,
                                   room_types=room_types, rooms_by_type=rooms_by_type)

        # Check for duplicate room assignments
        assigned_room_ids = [r['room_id'] for r in room_rows if r['room_id']]
        if len(assigned_room_ids) != len(set(assigned_room_ids)):
            flash('Duplicate room numbers selected. Each room can only be assigned once.', 'danger')
            return render_template('groups/new.html', companies=companies,
                                   room_types=room_types, rooms_by_type=rooms_by_type)

        group_rate = Decimal(group_rate_str) if group_rate_str else None
        company_id = request.form.get('company_id', type=int) or None

        block = GroupBlock(
            group_name=group_name,
            group_code=_generate_group_code(),
            contact_name=request.form.get('contact_name', '').strip() or None,
            contact_phone=request.form.get('contact_phone', '').strip() or None,
            contact_email=request.form.get('contact_email', '').strip() or None,
            company_id=company_id,
            arrival_date=arrival,
            departure_date=departure,
            total_rooms=total_rooms,
            group_rate=group_rate,
            status='Tentative',
            billing_instructions=request.form.get('billing_instructions', '').strip() or None,
            notes=request.form.get('notes', '').strip() or None,
            created_by_user_id=current_user.id,
        )
        db.session.add(block)
        db.session.flush()

        # Create a reservation for each room row
        from app.rates import resolve_rate_for_reservation
        reservations_created = 0
        for row in room_rows:
            rt = RoomType.query.get(row['room_type_id'])
            if not rt:
                continue
            _resolved = resolve_rate_for_reservation(
                row['room_type_id'], arrival, departure,
                group_rate=float(group_rate) if group_rate else None)
            rate = _resolved.rate_per_night
            res = Reservation(
                room_type_id=row['room_type_id'],
                room_id=row['room_id'],
                arrival_date=arrival,
                departure_date=departure,
                adults=row['adults'],
                children=row['children'],
                rate_per_night=rate,
                status='Confirmed',
                source='Walk-in',
                group_block_id=block.id,
            )
            db.session.add(res)
            db.session.flush()
            from app.nightly_rate_service import safe_sync_nightly_rates
            safe_sync_nightly_rates(res, reason='new_booking')

            # R2A: bridge-write invariant — mirror primary room into
            # reservation_rooms when this group row was assigned a room
            # at creation time. Idempotent.
            if res.room_id:
                from app.services_group_stay import mirror_room_to_bridge
                mirror_room_to_bridge(res)

            reservations_created += 1

        db.session.commit()
        flash(f'Group block "{block.group_name}" created with {reservations_created} room(s) '
              f'(code: {block.group_code}).', 'success')
        return redirect(url_for('groups.detail', group_id=block.id))

    return render_template('groups/new.html', companies=companies,
                           room_types=room_types, rooms_by_type=rooms_by_type)


# ---------------------------------------------------------------------------
# GET /groups/<id> — View group detail with rooming list
# ---------------------------------------------------------------------------
@groups_bp.route('/<int:group_id>')
@role_required('Admin', 'Manager')
def detail(group_id):
    block = GroupBlock.query.get_or_404(group_id)
    reservations = Reservation.query.filter_by(group_block_id=block.id).all()
    room_types = RoomType.query.filter_by(is_active=True).all()
    picked_up = sum(1 for r in reservations if r.status != 'Cancelled')
    remaining = max(0, block.total_rooms - picked_up)

    return render_template('groups/detail.html', block=block,
                           reservations=reservations, room_types=room_types,
                           picked_up=picked_up, remaining=remaining)


# ---------------------------------------------------------------------------
# POST /groups/<id>/add-room — Add a reservation to the group
# ---------------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/add-room', methods=['POST'])
@role_required('Admin', 'Manager')
def add_room(group_id):
    block = GroupBlock.query.get_or_404(group_id)

    if block.status == 'Cancelled':
        flash('Cannot add rooms to a cancelled group block.', 'danger')
        return redirect(url_for('groups.detail', group_id=block.id))

    # Resolve or create guest — accept structured first/last name with legacy fallback
    guest_first_name = request.form.get('guest_first_name', '').strip()
    guest_last_name  = request.form.get('guest_last_name', '').strip()
    guest_name = (f'{guest_first_name} {guest_last_name}'.strip()
                  or request.form.get('guest_name', '').strip())
    guest_phone = request.form.get('guest_phone', '').strip()
    add_errs = validate_fields(
        validate_name(guest_name, 'Guest name'),
        validate_phone(guest_phone, 'Guest phone'),
    )
    if add_errs:
        for e in add_errs:
            flash(e, 'danger')
        return redirect(url_for('groups.detail', group_id=block.id))

    from app.validators import clean_phone
    guest_phone = clean_phone(guest_phone)
    guest = Guest.query.filter_by(phone=guest_phone).first()
    if not guest:
        guest = Guest(name=guest_name, phone=guest_phone)
        if guest_first_name:
            guest.first_name = guest_first_name
            guest.last_name = guest_last_name
        db.session.add(guest)
        db.session.flush()

    room_type_id = request.form.get('room_type_id', type=int)
    if not room_type_id:
        flash('Room type is required.', 'danger')
        return redirect(url_for('groups.detail', group_id=block.id))

    room_type = RoomType.query.get(room_type_id)
    if not room_type:
        flash('Invalid room type.', 'danger')
        return redirect(url_for('groups.detail', group_id=block.id))

    # Use group rate if set, otherwise use central rate resolver
    from app.rates import resolve_rate_for_reservation
    _resolved = resolve_rate_for_reservation(
        room_type_id, block.arrival_date, block.departure_date,
        group_rate=float(block.group_rate) if block.group_rate else None)
    rate = _resolved.rate_per_night

    reservation = Reservation(
        guest_id=guest.id,
        room_type_id=room_type_id,
        arrival_date=block.arrival_date,
        departure_date=block.departure_date,
        adults=request.form.get('adults', 1, type=int),
        children=request.form.get('children', 0, type=int),
        rate_per_night=rate,
        status='Confirmed',
        source='Walk-in',
        group_block_id=block.id,
        special_requests=request.form.get('special_requests', '').strip() or None,
    )
    db.session.add(reservation)
    db.session.flush()
    from app.nightly_rate_service import safe_sync_nightly_rates
    safe_sync_nightly_rates(reservation, reason='new_booking')
    db.session.commit()
    flash(f'Reservation added for {guest.name} in group "{block.group_name}".', 'success')
    return redirect(url_for('groups.detail', group_id=block.id))


# ---------------------------------------------------------------------------
# POST /groups/<id>/batch-checkin — Check in all confirmed reservations
# ---------------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/batch-checkin', methods=['POST'])
@role_required('Admin', 'Manager')
def batch_checkin(group_id):
    block = GroupBlock.query.get_or_404(group_id)
    confirmed = Reservation.query.filter_by(
        group_block_id=block.id, status='Confirmed'
    ).all()

    if not confirmed:
        flash('No confirmed reservations to check in.', 'warning')
        return redirect(url_for('groups.detail', group_id=block.id))

    checked_in_count = 0
    skipped = []

    for res in confirmed:
        # Try to assign a vacant room of the requested type (row-locked to prevent races)
        room = (db.session.query(Room)
                .with_for_update()
                .filter_by(
                    room_type_id=res.room_type_id,
                    status='Vacant',
                    is_active=True,
                    is_sellable=True,
                    is_out_of_order=False
                ).first())

        if not room:
            skipped.append(res.guest.name if res.guest else f'Reservation #{res.id}')
            continue

        res.room_id = room.id
        res.status = 'CheckedIn'
        res.checked_in_at = datetime.utcnow()
        res.checkin_by = current_user.username
        room.status = 'Occupied'

        # R2A: bridge-write invariant — mirror primary room.
        from app.services_group_stay import mirror_room_to_bridge
        mirror_room_to_bridge(res)

        checked_in_count += 1

    # Update group status if all rooms are checked in
    if block.status != 'Completed':
        block.status = 'Confirmed'

    db.session.commit()

    if checked_in_count:
        flash(f'Batch check-in complete: {checked_in_count} guest(s) checked in.', 'success')
    if skipped:
        flash(f'Skipped (no vacant rooms available): {", ".join(skipped)}', 'warning')

    return redirect(url_for('groups.detail', group_id=block.id))


# ---------------------------------------------------------------------------
# POST /groups/<id>/update-status — Update group block status
# ---------------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/update-status', methods=['POST'])
@role_required('Admin', 'Manager')
def update_status(group_id):
    block = GroupBlock.query.get_or_404(group_id)
    new_status = request.form.get('status', '').strip()
    if new_status not in ('Tentative', 'Confirmed', 'Cancelled', 'Completed'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('groups.detail', group_id=block.id))
    block.status = new_status
    db.session.commit()
    flash(f'Group status updated to {new_status}.', 'success')
    return redirect(url_for('groups.detail', group_id=block.id))
