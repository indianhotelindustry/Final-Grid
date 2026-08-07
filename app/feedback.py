"""
Guest Feedback blueprint.
Routes:
  /feedback/submit/<token>   — public, guest fills form via WhatsApp link
  /feedback/complete         — public, thank-you page
  /feedback/dashboard        — staff, view all feedback + stats
  /feedback/send/<res_id>    — staff POST, generate token + send WhatsApp link
"""
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from app.models import db, GuestFeedback, Reservation, Guest
from app import csrf

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')


# ---------------------------------------------------------------------------
# Public: guest submits feedback via token link
# ---------------------------------------------------------------------------

@feedback_bp.route('/submit/<token>', methods=['GET', 'POST'])
@csrf.exempt  # Public guest form authenticated by unique token — no session available
def submit(token):
    feedback = GuestFeedback.query.filter_by(token=token).first_or_404()

    if feedback.submitted_at and feedback.rating:
        return render_template('feedback/complete.html', already_done=True)

    reservation = feedback.reservation
    guest = reservation.guest

    if request.method == 'POST':
        rating = request.form.get('rating', type=int)
        if not rating or rating < 1 or rating > 5:
            flash('Please select a rating.', 'danger')
            return redirect(url_for('feedback.submit', token=token))

        feedback.rating = rating
        feedback.cleanliness = request.form.get('cleanliness', type=int)
        feedback.service = request.form.get('service', type=int)
        feedback.food = request.form.get('food', type=int)
        feedback.value = request.form.get('value', type=int)
        feedback.comment = request.form.get('comment', '').strip()[:1000]
        feedback.would_recommend = request.form.get('would_recommend') == '1'
        feedback.negative_flag = rating <= 2
        feedback.submitted_at = datetime.utcnow()
        feedback.ip_address = request.remote_addr
        feedback.source = 'whatsapp_link'
        db.session.commit()

        # If rating >= 4, push Google review link (non-blocking)
        if rating >= 4:
            _push_google_review(feedback, reservation)

        return redirect(url_for('feedback.complete'))

    return render_template('feedback/form.html', feedback=feedback,
                           reservation=reservation, guest=guest)


@feedback_bp.route('/complete')
def complete():
    return render_template('feedback/complete.html', already_done=False)


# ---------------------------------------------------------------------------
# Staff: send feedback link
# ---------------------------------------------------------------------------

@feedback_bp.route('/send/<int:reservation_id>', methods=['POST'])
@login_required
def send_link(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status != 'CheckedOut':
        flash('Feedback links can only be sent after checkout.', 'warning')
        return redirect(request.referrer or url_for('main.reservations'))

    # Idempotent: reuse existing record if already created
    existing = GuestFeedback.query.filter_by(reservation_id=reservation_id).first()
    if existing and existing.rating:
        flash('Guest has already submitted feedback.', 'info')
        return redirect(url_for('feedback.dashboard'))

    if not existing:
        token = secrets.token_urlsafe(32)
        fb = GuestFeedback(
            reservation_id=reservation_id,
            rating=0,           # 0 = not yet submitted
            token=token,
            source='whatsapp_link',
        )
        db.session.add(fb)
        db.session.commit()
    else:
        token = existing.token

    link = url_for('feedback.submit', token=token, _external=True)

    # Send via WhatsApp (non-blocking)
    try:
        from flask import current_app
        from app.notifications import _send_whatsapp
        guest = reservation.guest
        msg = (
            f"Dear {guest.name.split()[0]},\n\n"
            f"Thank you for staying at {current_app.config['HOTEL_NAME']}! "
            f"We'd love your feedback (takes 30 seconds):\n{link}\n\n"
            f"Your review helps us serve you better. 🙏"
        )
        _send_whatsapp(guest.phone, msg, app=current_app._get_current_object())
        flash(f'Feedback link sent to {guest.phone} via WhatsApp.', 'success')
    except Exception as e:
        flash(f'Feedback record created but WhatsApp failed: {e}. Link: {link}', 'warning')

    return redirect(url_for('feedback.dashboard'))


# ---------------------------------------------------------------------------
# Staff: feedback dashboard
# ---------------------------------------------------------------------------

@feedback_bp.route('/dashboard')
@login_required
def dashboard():
    from sqlalchemy import func

    feedbacks = (GuestFeedback.query
                 .filter(GuestFeedback.rating > 0)
                 .order_by(GuestFeedback.submitted_at.desc())
                 .all())

    total = len(feedbacks)
    avg_rating = round(sum(f.rating for f in feedbacks) / total, 1) if total else 0
    negative = sum(1 for f in feedbacks if f.negative_flag)
    promoters = sum(1 for f in feedbacks if f.rating >= 4)
    nps = round((promoters - negative) / total * 100) if total else 0

    dist = {i: sum(1 for f in feedbacks if f.rating == i) for i in range(1, 6)}

    return render_template('feedback/dashboard.html',
                           feedbacks=feedbacks,
                           total=total,
                           avg_rating=avg_rating,
                           negative=negative,
                           promoters=promoters,
                           nps=nps,
                           dist=dist)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _push_google_review(feedback, reservation):
    """Send Google review link to happy guests (rating >= 4). Non-blocking."""
    try:
        from flask import current_app
        from app.models import Settings
        from app.notifications import _send_whatsapp

        with current_app.app_context():
            setting = Settings.query.filter_by(key='google_review_url').first()
            if not setting or not setting.value:
                return
            guest = reservation.guest
            msg = (
                f"Hi {guest.name.split()[0]}, glad you enjoyed your stay! 😊\n"
                f"Would you mind leaving us a quick Google review?\n{setting.value}\n"
                f"It means a lot to us. Thank you!"
            )
            _send_whatsapp(guest.phone, msg, app=current_app._get_current_object())
            feedback.google_review_pushed = True
            db.session.commit()
    except Exception:
        pass
