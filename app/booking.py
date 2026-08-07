"""
Public Booking Engine — no login required.
Accessible at /book  (publicly via Cloudflare Tunnel)
"""

import random
import string
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from app.models import db, Room, RoomType, Guest, Reservation, Payment, PaymentMode, Settings
from app import limiter
from app.validators import (
    clean_phone, validate_phone, validate_email, validate_name,
    validate_fields, validate_date_range, validate_not_past,
    validate_positive_int, validate_text_length,
)

booking_bp = Blueprint('booking', __name__, url_prefix='/book')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_reference():
    """Generate a unique 10-char booking reference like SCW-AB12CD."""
    import secrets
    alphabet = string.ascii_uppercase + string.digits
    chars = ''.join(secrets.choice(alphabet) for _ in range(6))
    return 'SCW-' + chars


def _count_available(room_type_id: int, arrival: date, departure: date) -> int:
    """How many rooms of a type are free for the given date range."""
    total = Room.query.filter_by(room_type_id=room_type_id, is_active=True).count()
    booked = Reservation.query.filter(
        Reservation.room_type_id == room_type_id,
        Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn', 'Overbooked']),
        Reservation.arrival_date < departure,
        Reservation.departure_date > arrival,
    ).count()
    return max(0, total - booked)


def _hotel_name():
    s = Settings.query.filter_by(key='hotel_name').first()
    from flask import current_app
    return s.value if s else current_app.config.get('HOTEL_NAME', 'Sukoon City View')


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@booking_bp.route('/', methods=['GET'])
def index():
    """Public booking landing page."""
    room_types = RoomType.query.all()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    hotel_name = _hotel_name()
    return render_template(
        'booking/index.html',
        room_types=room_types,
        today=today,
        tomorrow=tomorrow,
        hotel_name=hotel_name,
    )


@booking_bp.route('/check-availability', methods=['POST'])
@limiter.limit('30 per minute')
def check_availability():
    """AJAX endpoint — returns available room types for given dates."""
    try:
        arrival_str = request.form.get('arrival_date') or request.json.get('arrival_date')
        departure_str = request.form.get('departure_date') or request.json.get('departure_date')
        arrival = datetime.strptime(arrival_str, '%Y-%m-%d').date()
        departure = datetime.strptime(departure_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid dates'}), 400

    if arrival < date.today():
        return jsonify({'success': False, 'error': 'Arrival date cannot be in the past'}), 400
    if departure <= arrival:
        return jsonify({'success': False, 'error': 'Departure must be after arrival'}), 400
    if (departure - arrival).days > 30:
        return jsonify({'success': False, 'error': 'Maximum stay is 30 nights'}), 400

    nights = (departure - arrival).days
    room_types = RoomType.query.all()
    results = []

    from app.rates import get_average_rate, get_stay_rates
    for rt in room_types:
        avail = _count_available(rt.id, arrival, departure)
        nightly_rates = get_stay_rates(rt.id, arrival, departure)
        avg_rate = round(sum(nightly_rates) / len(nightly_rates), 2) if nightly_rates else 0.0
        total = round(sum(nightly_rates), 2)
        results.append({
            'id': rt.id,
            'name': rt.name,
            'description': rt.description or '',
            'rate_per_night': avg_rate,
            'total': total,
            'nights': nights,
            'available': avail,
        })

    return jsonify({'success': True, 'results': results, 'nights': nights})


@booking_bp.route('/create', methods=['POST'])
@limiter.limit('10 per minute; 50 per hour')
def create_booking():
    """Create a reservation from the public booking form."""
    try:
        arrival = datetime.strptime(request.form['arrival_date'], '%Y-%m-%d').date()
        departure = datetime.strptime(request.form['departure_date'], '%Y-%m-%d').date()
        room_type_id = int(request.form['room_type_id'])
        adults = int(request.form.get('adults', 1))
        children = int(request.form.get('children', 0))
        special_requests = request.form.get('special_requests', '').strip()

        guest_first_name = request.form.get('guest_first_name', '').strip()
        guest_last_name  = request.form.get('guest_last_name', '').strip()
        guest_name = (f'{guest_first_name} {guest_last_name}'.strip()
                      or request.form.get('guest_name', '').strip())
        guest_phone = request.form.get('guest_phone', '').strip()
        guest_email = request.form.get('guest_email', '').strip()

        booking_errs = validate_fields(
            validate_name(guest_name, 'Name'),
            validate_phone(guest_phone, 'Mobile number'),
            validate_email(guest_email),
            validate_not_past(arrival, 'Arrival date'),
            validate_date_range(arrival, departure, 'Arrival', 'Departure'),
            validate_positive_int(adults, 'Adults', min_val=1, max_val=10),
            validate_positive_int(children, 'Children', min_val=0, max_val=10),
            validate_text_length(special_requests, 'Special requests', max_len=500),
        )
        if booking_errs:
            for e in booking_errs:
                flash(e, 'danger')
            return redirect(url_for('booking.index'))

        guest_phone = clean_phone(guest_phone)

        room_type = RoomType.query.get_or_404(room_type_id)
        available = _count_available(room_type_id, arrival, departure)

        if available < 1:
            flash(f'Sorry, no {room_type.name} rooms are available for the selected dates. Please choose different dates or room type.', 'warning')
            return redirect(url_for('booking.index'))

        # Find or create guest
        guest = Guest.query.filter_by(phone=guest_phone).first()
        if not guest:
            guest = Guest(
                name=guest_name,
                phone=guest_phone,
                email=guest_email or None,
            )
            if guest_first_name:
                guest.first_name = guest_first_name
                guest.last_name = guest_last_name
            db.session.add(guest)
            db.session.flush()
        else:
            if not guest.email and guest_email:
                guest.email = guest_email

        # Generate unique booking reference
        ref = _generate_reference()
        while Reservation.query.filter_by(booking_reference=ref).first():
            ref = _generate_reference()

        # Use rate plan if available, else base rate — average across all nights
        from app.rates import get_average_rate
        applicable_rate = get_average_rate(room_type_id, arrival, departure)

        nights = (departure - arrival).days
        reservation = Reservation(
            booking_reference=ref,
            guest_id=guest.id,
            room_type_id=room_type_id,
            arrival_date=arrival,
            departure_date=departure,
            adults=adults,
            children=children,
            rate_per_night=applicable_rate,
            advance_payment=0,
            status='Confirmed',
            source='Website',
            special_requests=special_requests,
        )
        db.session.add(reservation)
        db.session.commit()

        # Fire WhatsApp + email notifications (non-blocking)
        try:
            from app.notifications import notify_booking_confirmed
            notify_booking_confirmed(reservation, app=current_app._get_current_object())
        except Exception:
            pass  # Never let notification failure break the booking

        return redirect(url_for('booking.confirmation', ref=ref))

    except KeyError as e:
        flash(f'Missing field: {e}', 'danger')
        return redirect(url_for('booking.index'))
    except Exception as e:
        db.session.rollback()
        flash('Something went wrong. Please try again.', 'danger')
        return redirect(url_for('booking.index'))


@booking_bp.route('/confirmation/<ref>')
def confirmation(ref):
    """Show booking confirmation page (public, no login)."""
    reservation = Reservation.query.filter_by(booking_reference=ref).first_or_404()
    nights = (reservation.departure_date - reservation.arrival_date).days
    total = float(reservation.rate_per_night) * nights
    hotel_name = _hotel_name()
    return render_template(
        'booking/confirmation.html',
        reservation=reservation,
        nights=nights,
        total=total,
        hotel_name=hotel_name,
    )


# ---------------------------------------------------------------------------
# Public availability API (used by channel manager to query live inventory)
# ---------------------------------------------------------------------------

@booking_bp.route('/api/availability')
@limiter.limit('20 per minute')
def availability_api():
    """
    Public availability API for channel managers.
    GET /book/api/availability?from=YYYY-MM-DD&to=YYYY-MM-DD
    Returns room-type inventory for each day in the range.
    """
    try:
        from_str = request.args.get('from')
        to_str = request.args.get('to')
        from_date = datetime.strptime(from_str, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'error': 'from and to parameters required (YYYY-MM-DD)'}), 400

    if (to_date - from_date).days > 90:
        return jsonify({'error': 'Range cannot exceed 90 days'}), 400

    room_types = RoomType.query.all()
    result = {'from': from_str, 'to': to_str, 'room_types': []}

    from app.rates import get_applicable_rate
    for rt in room_types:
        days = []
        d = from_date
        while d < to_date:
            avail = _count_available(rt.id, d, d + timedelta(days=1))
            rate = get_applicable_rate(rt.id, d, d + timedelta(days=1))
            days.append({'date': d.isoformat(), 'available': avail, 'rate': rate})
            d += timedelta(days=1)
        result['room_types'].append({
            'id': rt.id,
            'name': rt.name,
            'days': days,
        })

    return jsonify(result)


@booking_bp.route('/api/rates')
@limiter.limit('20 per minute')
def rates_api():
    """
    Public rates API for channel managers.
    GET /book/api/rates?date=YYYY-MM-DD  (optional — defaults to today)
    Returns current applicable rates per room type.
    """
    from app.rates import get_applicable_rate
    from datetime import date as date_type
    date_str = request.args.get('date')
    try:
        check_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date_type.today()
    except ValueError:
        check_date = date_type.today()

    room_types = RoomType.query.all()
    return jsonify([
        {
            'id': rt.id,
            'name': rt.name,
            'base_rate': float(rt.base_rate),
            'applicable_rate': get_applicable_rate(rt.id, check_date, check_date),
            'description': rt.description,
        }
        for rt in room_types
    ])
