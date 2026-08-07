"""
Loyalty Program Engine
======================
3-tier loyalty system (Silver → Gold → Platinum) with points earning,
milestone bonuses, and redemptions (billing discounts, flexible check-in/out).

Blueprint: /loyalty
"""
import math
import logging
from datetime import datetime, date
from decimal import Decimal
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import func
from app.auth import role_required
from app.models import (db, Guest, Reservation, Payment, LoyaltyConfig,
                         LoyaltyMilestone, LoyaltyTransaction, LoyaltyRedemption)

logger = logging.getLogger(__name__)

loyalty_bp = Blueprint('loyalty', __name__, url_prefix='/loyalty',
                        template_folder='templates/loyalty')

VIP_MAP = {'Silver': 'V3', 'Gold': 'V4', 'Platinum': 'V5'}
DIRECT_SOURCES = {'Walk-in', 'Calling', 'Website'}

# ═════════════════════════════════════════════════════════════════════════════
# SERVICE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def get_loyalty_balance(guest_id):
    """Return current points balance (sum of all transactions)."""
    val = db.session.query(
        func.coalesce(func.sum(LoyaltyTransaction.points), 0)
    ).filter_by(guest_id=guest_id).scalar()
    return int(val)


def get_tier_config(tier_name):
    """Return LoyaltyConfig row for a tier, or None."""
    return LoyaltyConfig.query.filter_by(tier_name=tier_name, is_active=True).first()


def get_all_tiers():
    """Return all active tiers ordered by tier_order."""
    return LoyaltyConfig.query.filter_by(is_active=True).order_by(LoyaltyConfig.tier_order).all()


def get_guest_tier(guest_id):
    """Determine tier based on current points balance."""
    balance = get_loyalty_balance(guest_id)
    tiers = LoyaltyConfig.query.filter_by(is_active=True).order_by(
        LoyaltyConfig.min_points.desc()
    ).all()
    for t in tiers:
        if balance >= t.min_points:
            return t.tier_name
    return 'Silver'


def evaluate_tier_change(guest):
    """Re-evaluate tier and update Guest record if changed."""
    new_tier = get_guest_tier(guest.id)
    if guest.loyalty_tier != new_tier:
        guest.loyalty_tier = new_tier
        guest.vip_level = VIP_MAP.get(new_tier, 'V3')
        logger.info('Guest %s tier changed to %s', guest.id, new_tier)


def generate_loyalty_number(guest):
    """Generate a loyalty number if guest doesn't have one."""
    if not guest.loyalty_number:
        guest.loyalty_number = f'LYL-{guest.id:06d}'
        guest.loyalty_tier = guest.loyalty_tier or 'Silver'
        guest.vip_level = VIP_MAP.get(guest.loyalty_tier, 'V3')
    return guest.loyalty_number


def _add_transaction(guest_id, reservation_id, txn_type, points, description,
                     reference_amount=None, user_id=None):
    """Insert a ledger entry."""
    guest = db.session.get(Guest, guest_id)
    txn = LoyaltyTransaction(
        guest_id=guest_id,
        reservation_id=reservation_id,
        txn_type=txn_type,
        points=points,
        description=description,
        reference_amount=reference_amount,
        tier_at_time=guest.loyalty_tier if guest else None,
        created_by_user_id=user_id,
    )
    db.session.add(txn)
    return txn


def award_checkout_points(reservation, user_id=None):
    """
    Award loyalty points on checkout. Called within the checkout transaction.
    Earning methods:
      1. Per-night stayed
      2. Per-rupee spent
      3. Direct booking bonus (% extra if not OTA)
      4. Milestone bonuses
    """
    guest = reservation.guest
    if not guest or not guest.loyalty_number:
        return

    tier_cfg = get_tier_config(guest.loyalty_tier or 'Silver')
    if not tier_cfg:
        return

    nights = max(1, (reservation.departure_date - reservation.arrival_date).days)
    total_paid = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.reservation_id == reservation.id,
        Payment.is_voided == False  # noqa: E712
    ).scalar()
    total_paid = float(total_paid)

    earned = 0

    # 1. Per-night points
    night_pts = nights * tier_cfg.earn_per_night
    if night_pts > 0:
        _add_transaction(guest.id, reservation.id, 'earn_night', night_pts,
                         f'{nights} night(s) × {tier_cfg.earn_per_night} pts',
                         user_id=user_id)
        earned += night_pts

    # 2. Per-rupee points
    spend_pts = int(total_paid / 100) * tier_cfg.earn_per_100_rupees
    if spend_pts > 0:
        _add_transaction(guest.id, reservation.id, 'earn_spend', spend_pts,
                         f'₹{total_paid:,.0f} spent × {tier_cfg.earn_per_100_rupees}/₹100',
                         reference_amount=Decimal(str(total_paid)),
                         user_id=user_id)
        earned += spend_pts

    # 3. Direct booking bonus
    base_pts = night_pts + spend_pts
    if reservation.source in DIRECT_SOURCES and tier_cfg.direct_booking_bonus_pct > 0:
        bonus = int(base_pts * tier_cfg.direct_booking_bonus_pct / 100)
        if bonus > 0:
            _add_transaction(guest.id, reservation.id, 'earn_direct', bonus,
                             f'{tier_cfg.direct_booking_bonus_pct}% direct booking bonus',
                             user_id=user_id)
            earned += bonus

    # 4. Milestone bonuses
    stay_count = (guest.total_stays or 0) + 1  # +1 because checkout increments after
    milestones = LoyaltyMilestone.query.filter_by(is_active=True).all()
    for ms in milestones:
        if ms.trigger_type == 'stays':
            if ms.is_recurring:
                if stay_count > 0 and stay_count % ms.trigger_value == 0:
                    _award_milestone(guest, reservation, ms, user_id)
            else:
                if stay_count == ms.trigger_value:
                    _award_milestone(guest, reservation, ms, user_id)
        elif ms.trigger_type == 'spend':
            lifetime_spend = _get_lifetime_spend(guest.id)
            if lifetime_spend >= ms.trigger_value:
                existing = LoyaltyTransaction.query.filter_by(
                    guest_id=guest.id, txn_type='earn_bonus',
                    description=ms.name
                ).first()
                if not existing or ms.is_recurring:
                    _add_transaction(guest.id, reservation.id, 'earn_bonus',
                                     ms.bonus_points, ms.name, user_id=user_id)

    # Re-evaluate tier
    evaluate_tier_change(guest)

    logger.info('Loyalty: Guest %s earned %d pts on reservation %s',
                guest.id, earned, reservation.id)


def _award_milestone(guest, reservation, ms, user_id):
    """Award a milestone bonus."""
    _add_transaction(guest.id, reservation.id, 'earn_bonus',
                     ms.bonus_points, ms.name, user_id=user_id)


def _get_lifetime_spend(guest_id):
    """Total non-voided payments across all reservations."""
    val = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).join(Reservation, Payment.reservation_id == Reservation.id).filter(
        Reservation.guest_id == guest_id,
        Payment.is_voided == False  # noqa: E712
    ).scalar()
    return float(val)


def apply_discount_redemption(guest_id, reservation_id, points_to_redeem, user_id=None):
    """Redeem points for billing discount. Returns (success, message, rupee_value)."""
    balance = get_loyalty_balance(guest_id)
    if points_to_redeem <= 0:
        return False, 'Points must be positive', 0
    if points_to_redeem > balance:
        return False, f'Insufficient balance ({balance} available)', 0

    guest = db.session.get(Guest, guest_id)
    tier_cfg = get_tier_config(guest.loyalty_tier or 'Silver')
    if not tier_cfg:
        return False, 'Tier config not found', 0

    rupee_value = round(float(points_to_redeem) * float(tier_cfg.redemption_value), 2)

    txn = _add_transaction(guest_id, reservation_id, 'redeem_discount',
                           -points_to_redeem,
                           f'Redeemed {points_to_redeem} pts for ₹{rupee_value:,.2f} discount',
                           reference_amount=Decimal(str(rupee_value)),
                           user_id=user_id)
    db.session.flush()

    redemption = LoyaltyRedemption(
        guest_id=guest_id,
        reservation_id=reservation_id,
        redemption_type='discount',
        points_used=points_to_redeem,
        rupee_value=Decimal(str(rupee_value)),
        transaction_id=txn.id,
        applied_by_user_id=user_id,
    )
    db.session.add(redemption)

    # Apply discount to reservation
    reservation = db.session.get(Reservation, reservation_id)
    if reservation:
        reservation.discount_amount = float(reservation.discount_amount or 0) + rupee_value
        reservation.discount_reason = (reservation.discount_reason or '') + f' Loyalty:{points_to_redeem}pts'

    evaluate_tier_change(guest)
    return True, f'₹{rupee_value:,.2f} discount applied', rupee_value


def apply_perk_redemption(guest_id, reservation_id, perk_type, user_id=None):
    """Redeem points for late checkout or early checkin. Returns (success, message)."""
    guest = db.session.get(Guest, guest_id)
    tier_cfg = get_tier_config(guest.loyalty_tier or 'Silver')
    if not tier_cfg:
        return False, 'Tier config not found'

    if perk_type == 'late_checkout':
        cost = tier_cfg.late_checkout_points
        txn_type = 'redeem_late_co'
        desc = f'Late checkout ({cost} pts)'
    elif perk_type == 'early_checkin':
        cost = tier_cfg.early_checkin_points
        txn_type = 'redeem_early_ci'
        desc = f'Early check-in ({cost} pts)'
    else:
        return False, 'Invalid perk type'

    balance = get_loyalty_balance(guest_id)
    if balance < cost:
        return False, f'Insufficient points ({balance} available, need {cost})'

    txn = _add_transaction(guest_id, reservation_id, txn_type, -cost, desc,
                           user_id=user_id)
    db.session.flush()

    redemption = LoyaltyRedemption(
        guest_id=guest_id,
        reservation_id=reservation_id,
        redemption_type=perk_type,
        points_used=cost,
        transaction_id=txn.id,
        applied_by_user_id=user_id,
    )
    db.session.add(redemption)
    evaluate_tier_change(guest)
    return True, f'{desc} approved'


def get_program_stats():
    """Dashboard summary stats."""
    enrolled = Guest.query.filter(Guest.loyalty_number.isnot(None)).count()
    tier_dist = db.session.query(
        Guest.loyalty_tier, func.count(Guest.id)
    ).filter(Guest.loyalty_number.isnot(None)).group_by(Guest.loyalty_tier).all()
    tier_counts = {t: c for t, c in tier_dist}

    month_start = date.today().replace(day=1)
    pts_issued = db.session.query(
        func.coalesce(func.sum(LoyaltyTransaction.points), 0)
    ).filter(
        LoyaltyTransaction.points > 0,
        LoyaltyTransaction.created_at >= datetime.combine(month_start, datetime.min.time())
    ).scalar()
    pts_redeemed = db.session.query(
        func.coalesce(func.sum(func.abs(LoyaltyTransaction.points)), 0)
    ).filter(
        LoyaltyTransaction.points < 0,
        LoyaltyTransaction.created_at >= datetime.combine(month_start, datetime.min.time())
    ).scalar()

    return {
        'enrolled': enrolled,
        'silver': tier_counts.get('Silver', 0),
        'gold': tier_counts.get('Gold', 0),
        'platinum': tier_counts.get('Platinum', 0),
        'points_issued_mtd': int(pts_issued),
        'points_redeemed_mtd': int(pts_redeemed),
    }


# ═════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@loyalty_bp.before_request
@login_required
def _require_login():
    pass


# ── Dashboard ─────────────────────────────────────────────────────────────

@loyalty_bp.route('/')
@role_required('Admin', 'Manager')
def dashboard():
    stats = get_program_stats()
    tiers = get_all_tiers()
    recent_txns = LoyaltyTransaction.query.order_by(
        LoyaltyTransaction.created_at.desc()
    ).limit(20).all()
    top_members = db.session.query(
        Guest,
        func.coalesce(func.sum(LoyaltyTransaction.points), 0).label('balance')
    ).join(LoyaltyTransaction, Guest.id == LoyaltyTransaction.guest_id).filter(
        Guest.loyalty_number.isnot(None)
    ).group_by(Guest.id).order_by(
        func.sum(LoyaltyTransaction.points).desc()
    ).limit(10).all()
    return render_template('loyalty/dashboard.html', stats=stats, tiers=tiers,
                           recent_txns=recent_txns, top_members=top_members)


# ── Config ────────────────────────────────────────────────────────────────

@loyalty_bp.route('/config', methods=['GET', 'POST'])
@role_required('Admin')
def config():
    tiers = get_all_tiers()
    if request.method == 'POST':
        for t in tiers:
            prefix = f't{t.id}_'
            t.earn_per_night = request.form.get(prefix + 'earn_per_night', t.earn_per_night, type=int)
            t.earn_per_100_rupees = request.form.get(prefix + 'earn_per_100_rupees', t.earn_per_100_rupees, type=int)
            t.direct_booking_bonus_pct = request.form.get(prefix + 'direct_bonus', t.direct_booking_bonus_pct, type=int)
            t.min_points = request.form.get(prefix + 'min_points', t.min_points, type=int)
            t.redemption_value = request.form.get(prefix + 'redemption_value', t.redemption_value, type=float)
            t.late_checkout_points = request.form.get(prefix + 'late_co', t.late_checkout_points, type=int)
            t.early_checkin_points = request.form.get(prefix + 'early_ci', t.early_checkin_points, type=int)
            t.color_hex = request.form.get(prefix + 'color', t.color_hex)
        db.session.commit()
        flash('Loyalty config updated.', 'success')
        return redirect(url_for('loyalty.config'))
    return render_template('loyalty/config.html', tiers=tiers)


# ── Milestones ────────────────────────────────────────────────────────────

@loyalty_bp.route('/milestones', methods=['GET', 'POST'])
@role_required('Admin')
def milestones():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            ms = LoyaltyMilestone(
                name=request.form.get('name', '').strip(),
                trigger_type=request.form.get('trigger_type', 'stays'),
                trigger_value=request.form.get('trigger_value', 0, type=int),
                bonus_points=request.form.get('bonus_points', 100, type=int),
                is_recurring=request.form.get('is_recurring') == '1',
            )
            db.session.add(ms)
            db.session.commit()
            flash(f'Milestone "{ms.name}" added.', 'success')
        elif action == 'delete':
            ms_id = request.form.get('milestone_id', type=int)
            ms = db.session.get(LoyaltyMilestone, ms_id)
            if ms:
                db.session.delete(ms)
                db.session.commit()
                flash('Milestone deleted.', 'success')
        elif action == 'toggle':
            ms_id = request.form.get('milestone_id', type=int)
            ms = db.session.get(LoyaltyMilestone, ms_id)
            if ms:
                ms.is_active = not ms.is_active
                db.session.commit()
        return redirect(url_for('loyalty.milestones'))
    all_ms = LoyaltyMilestone.query.order_by(LoyaltyMilestone.trigger_value).all()
    return render_template('loyalty/milestones.html', milestones=all_ms)


# ── Members ───────────────────────────────────────────────────────────────

@loyalty_bp.route('/members')
@role_required('Admin', 'Manager', 'FrontDesk')
def members():
    q = request.args.get('q', '').strip()
    tier_filter = request.args.get('tier', '')
    query = Guest.query.filter(Guest.loyalty_number.isnot(None))
    if q:
        query = query.filter(
            db.or_(Guest.name.ilike(f'%{q}%'), Guest.phone.ilike(f'%{q}%'),
                   Guest.loyalty_number.ilike(f'%{q}%'))
        )
    if tier_filter:
        query = query.filter_by(loyalty_tier=tier_filter)
    guests = query.order_by(Guest.name).all()
    # Get balances
    balances = {}
    if guests:
        guest_ids = [g.id for g in guests]
        rows = db.session.query(
            LoyaltyTransaction.guest_id,
            func.sum(LoyaltyTransaction.points)
        ).filter(LoyaltyTransaction.guest_id.in_(guest_ids)).group_by(
            LoyaltyTransaction.guest_id
        ).all()
        balances = {r[0]: int(r[1]) for r in rows}
    tiers = get_all_tiers()
    return render_template('loyalty/members.html', guests=guests, balances=balances,
                           tiers=tiers, q=q, tier_filter=tier_filter)


# ── Member Detail ─────────────────────────────────────────────────────────

@loyalty_bp.route('/member/<int:guest_id>')
@role_required('Admin', 'Manager', 'FrontDesk')
def member_detail(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    balance = get_loyalty_balance(guest_id)
    tier = guest.loyalty_tier or 'Silver'
    tier_cfg = get_tier_config(tier)
    all_tiers = get_all_tiers()
    # Progress to next tier
    next_tier = None
    pts_to_next = 0
    for t in all_tiers:
        if t.min_points > balance:
            next_tier = t
            pts_to_next = t.min_points - balance
            break
    transactions = LoyaltyTransaction.query.filter_by(guest_id=guest_id).order_by(
        LoyaltyTransaction.created_at.desc()
    ).limit(100).all()
    redemptions = LoyaltyRedemption.query.filter_by(guest_id=guest_id).order_by(
        LoyaltyRedemption.created_at.desc()
    ).limit(50).all()
    return render_template('loyalty/member_detail.html', guest=guest, balance=balance,
                           tier=tier, tier_cfg=tier_cfg, next_tier=next_tier,
                           pts_to_next=pts_to_next, transactions=transactions,
                           redemptions=redemptions)


# ── Manual Adjust ─────────────────────────────────────────────────────────

@loyalty_bp.route('/member/<int:guest_id>/adjust', methods=['POST'])
@role_required('Admin', 'Manager')
def adjust_points(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    points = request.form.get('points', 0, type=int)
    reason = request.form.get('reason', '').strip()
    if not points or not reason:
        flash('Points and reason are required.', 'danger')
        return redirect(url_for('loyalty.member_detail', guest_id=guest_id))
    _add_transaction(guest_id, None, 'adjust', points,
                     f'Manual adjustment: {reason}',
                     user_id=current_user.id)
    evaluate_tier_change(guest)
    db.session.commit()
    flash(f'{"+" if points > 0 else ""}{points} points adjusted.', 'success')
    return redirect(url_for('loyalty.member_detail', guest_id=guest_id))


# ── Enroll ────────────────────────────────────────────────────────────────

@loyalty_bp.route('/enroll/<int:guest_id>', methods=['POST'])
@role_required('Admin', 'Manager', 'FrontDesk')
def enroll(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    if guest.loyalty_number:
        flash(f'{guest.name} is already enrolled ({guest.loyalty_number}).', 'info')
    else:
        generate_loyalty_number(guest)
        db.session.commit()
        flash(f'{guest.name} enrolled — {guest.loyalty_number}', 'success')
    return redirect(request.referrer or url_for('loyalty.members'))


# ── Transactions Log ──────────────────────────────────────────────────────

@loyalty_bp.route('/transactions')
@role_required('Admin', 'Manager')
def transactions():
    page = request.args.get('page', 1, type=int)
    txn_type = request.args.get('type', '')
    query = LoyaltyTransaction.query
    if txn_type:
        query = query.filter_by(txn_type=txn_type)
    txns = query.order_by(LoyaltyTransaction.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('loyalty/transactions.html', txns=txns, txn_type=txn_type)


# ═════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS (JSON)
# ═════════════════════════════════════════════════════════════════════════════

@loyalty_bp.route('/api/balance/<int:guest_id>')
def api_balance(guest_id):
    guest = db.session.get(Guest, guest_id)
    if not guest or not guest.loyalty_number:
        return jsonify({'enrolled': False, 'balance': 0, 'tier': None})
    balance = get_loyalty_balance(guest_id)
    tier_cfg = get_tier_config(guest.loyalty_tier or 'Silver')
    return jsonify({
        'enrolled': True,
        'loyalty_number': guest.loyalty_number,
        'balance': balance,
        'tier': guest.loyalty_tier,
        'color': tier_cfg.color_hex if tier_cfg else '#6c757d',
        'redemption_value': float(tier_cfg.redemption_value) if tier_cfg else 0,
        'max_discount': round(balance * float(tier_cfg.redemption_value), 2) if tier_cfg else 0,
    })


@loyalty_bp.route('/api/available-perks/<int:guest_id>')
def api_available_perks(guest_id):
    guest = db.session.get(Guest, guest_id)
    if not guest or not guest.loyalty_number:
        return jsonify({'enrolled': False})
    balance = get_loyalty_balance(guest_id)
    tier_cfg = get_tier_config(guest.loyalty_tier or 'Silver')
    if not tier_cfg:
        return jsonify({'enrolled': True, 'balance': balance, 'perks': []})
    perks = []
    if balance >= tier_cfg.late_checkout_points:
        perks.append({'type': 'late_checkout', 'cost': tier_cfg.late_checkout_points,
                      'label': 'Late Checkout'})
    if balance >= tier_cfg.early_checkin_points:
        perks.append({'type': 'early_checkin', 'cost': tier_cfg.early_checkin_points,
                      'label': 'Early Check-in'})
    max_discount = round(balance * float(tier_cfg.redemption_value), 2)
    return jsonify({
        'enrolled': True,
        'balance': balance,
        'tier': guest.loyalty_tier,
        'max_discount': max_discount,
        'redemption_value': float(tier_cfg.redemption_value),
        'perks': perks,
    })


@loyalty_bp.route('/api/redeem', methods=['POST'])
@role_required('Admin', 'Manager', 'FrontDesk')
def api_redeem():
    data = request.get_json() or {}
    guest_id = data.get('guest_id', 0)
    reservation_id = data.get('reservation_id', 0)
    rtype = data.get('type', '')  # 'discount', 'late_checkout', 'early_checkin'
    points = data.get('points', 0)

    if not guest_id or not reservation_id:
        return jsonify({'success': False, 'error': 'Missing guest_id or reservation_id'}), 400

    if rtype == 'discount':
        if not points or points <= 0:
            return jsonify({'success': False, 'error': 'Points must be positive'}), 400
        ok, msg, rupee_val = apply_discount_redemption(
            guest_id, reservation_id, points, user_id=current_user.id)
        if ok:
            db.session.commit()
        return jsonify({'success': ok, 'message': msg, 'rupee_value': rupee_val})
    elif rtype in ('late_checkout', 'early_checkin'):
        ok, msg = apply_perk_redemption(
            guest_id, reservation_id, rtype, user_id=current_user.id)
        if ok:
            db.session.commit()
        return jsonify({'success': ok, 'message': msg})
    else:
        return jsonify({'success': False, 'error': 'Invalid redemption type'}), 400
