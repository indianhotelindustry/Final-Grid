"""
POS Room Posting Blueprint
===========================
Allows staff to post food, beverage, laundry, and other charges
directly to a guest's room folio (ExtraCharge on the Reservation).

Routes:
  GET  /pos/                        — POS dashboard (search occupied rooms)
  POST /pos/post                    — Post a charge to a room
  GET  /pos/items                   — Manage POS item catalog
  POST /pos/items/create            — Add a new catalog item
  POST /pos/items/<id>/toggle       — Activate / deactivate item
  POST /pos/items/<id>/delete       — Remove item from catalog
  GET  /pos/api/room-charges/<res_id> — AJAX: get all charges for a reservation
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, Room, Reservation, Guest, RoomType, ExtraCharge, POSItem, PaymentMode
from app.services import get_business_date

pos_bp = Blueprint('pos', __name__, url_prefix='/pos')


@pos_bp.before_request
@login_required
def guard():
    pass


def _deny():
    """Only Admin, Manager, FrontDesk can post charges."""
    if not current_user.has_role('Admin', 'Manager', 'FrontDesk'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))
    return None


# ---------------------------------------------------------------------------
# POS Dashboard
# ---------------------------------------------------------------------------

@pos_bp.route('/')
def index():
    denied = _deny()
    if denied:
        return denied

    # Show all currently checked-in reservations
    occupied = Reservation.query.filter_by(status='CheckedIn')\
        .order_by(Reservation.arrival_date).all()

    # POS items grouped by category
    items = POSItem.query.filter_by(is_active=True)\
        .order_by(POSItem.category, POSItem.name).all()

    categories = {}
    for item in items:
        categories.setdefault(item.category, []).append(item)

    return render_template(
        'pos/index.html',
        occupied=occupied,
        categories=categories,
        business_date=get_business_date(),
    )


# ---------------------------------------------------------------------------
# Post a charge
# ---------------------------------------------------------------------------

@pos_bp.route('/post', methods=['POST'])
def post_charge():
    denied = _deny()
    if denied:
        return denied

    reservation_id = request.form.get('reservation_id', type=int)
    description = request.form.get('description', '').strip()
    amount = request.form.get('amount', type=float)
    pos_item_id = request.form.get('pos_item_id', type=int)

    # If a catalog item was selected, use its values
    if pos_item_id:
        item = db.session.get(POSItem, pos_item_id)
        if item:
            if not description:
                description = item.name
            if not amount:
                amount = float(item.price)

    if not reservation_id or not description or not amount or amount <= 0:
        flash('Room, description and amount are required.', 'danger')
        return redirect(url_for('pos.index'))

    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status != 'CheckedIn':
        flash('Can only post charges to a currently checked-in guest.', 'warning')
        return redirect(url_for('pos.index'))

    # Prefix with POS to distinguish from manual charges
    if pos_item_id and not description.startswith('POS:'):
        description = f'POS: {description}'

    # Determine GST category from catalog item or default to 'Other'
    _category = item.category if pos_item_id and item else 'Other'

    charge = ExtraCharge(
        reservation_id=reservation_id,
        description=description,
        amount=amount,
        charge_date=get_business_date(),
        charge_category=_category,
    )
    db.session.add(charge)
    db.session.commit()

    # Audit log
    try:
        from app.models import AuditLog
        log = AuditLog(
            staff_user_id=current_user.id,
            entity_type='ExtraCharge',
            entity_id=charge.id,
            action='pos_charge',
            before_state={},
            after_state={'reservation_id': reservation_id, 'description': description, 'amount': amount},
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

    guest_name = reservation.guest.name if reservation.guest else 'Guest'
    room_num = reservation.room.room_number if reservation.room else reservation.room_type.name
    flash(f'Charge ₹{amount:,.0f} — "{description}" posted to Room {room_num} ({guest_name}).', 'success')

    # Return AJAX-friendly response if requested
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'charge_id': charge.id, 'amount': amount, 'description': description})

    return redirect(url_for('pos.index'))


# ---------------------------------------------------------------------------
# Room charges AJAX API
# ---------------------------------------------------------------------------

@pos_bp.route('/api/room-charges/<int:reservation_id>')
def room_charges_api(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    # Exclude night-audit room_rent rows — the POS UI shows add-on charges
    # only; room revenue is handled elsewhere. Listing room_rent here
    # confuses staff into thinking they need to collect it twice.
    from sqlalchemy import or_ as _or_pos
    charges = ExtraCharge.query.filter_by(reservation_id=reservation_id)\
        .filter(_or_pos(ExtraCharge.charge_type.is_(None),
                        ExtraCharge.charge_type != 'room_rent'))\
        .order_by(ExtraCharge.charge_date.desc(), ExtraCharge.id.desc()).all()
    return jsonify({
        'guest': reservation.guest.name if reservation.guest else '',
        'room': reservation.room.room_number if reservation.room else reservation.room_type.name,
        'charges': [
            {'id': c.id, 'description': c.description,
             'amount': float(c.amount),
             'date': c.charge_date.isoformat() if c.charge_date else ''}
            for c in charges
        ],
        'total': sum(float(c.amount) for c in charges),
    })


# ---------------------------------------------------------------------------
# POS Catalog Management
# ---------------------------------------------------------------------------

@pos_bp.route('/items')
def items():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Only Admin and Manager can manage POS items.', 'danger')
        return redirect(url_for('pos.index'))

    all_items = POSItem.query.order_by(POSItem.category, POSItem.name).all()
    return render_template('pos/items.html', items=all_items)


@pos_bp.route('/items/create', methods=['POST'])
def create_item():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('pos.index'))

    try:
        item = POSItem(
            name=request.form['name'].strip(),
            category=request.form.get('category', 'Restaurant'),
            price=float(request.form['price']),
        )
        db.session.add(item)
        db.session.commit()
        flash(f'POS item "{item.name}" added.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('pos.items'))


@pos_bp.route('/items/<int:item_id>/toggle', methods=['POST'])
def toggle_item(item_id):
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('pos.index'))
    item = POSItem.query.get_or_404(item_id)
    item.is_active = not item.is_active
    db.session.commit()
    flash(f'Item "{item.name}" {"activated" if item.is_active else "deactivated"}.', 'success')
    return redirect(url_for('pos.items'))


@pos_bp.route('/items/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('pos.index'))
    item = POSItem.query.get_or_404(item_id)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{name}" deleted.', 'success')
    return redirect(url_for('pos.items'))
