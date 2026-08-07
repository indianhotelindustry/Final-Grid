import logging
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User, Shift, AuditLog
from datetime import datetime
from app import limiter
from app import shift_service

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# ---------------------------------------------------------------------------
# Role permission map — what each role can access
# ---------------------------------------------------------------------------
ROLE_LABELS = {
    'Admin': 'Administrator',
    'Manager': 'Manager',
    'FrontDesk': 'Front Desk',
    'Housekeeping': 'Housekeeping',
    'Accountant': 'Accountant',
}

ALL_ROLES = list(ROLE_LABELS.keys())


# ---------------------------------------------------------------------------
# Decorator helpers
# ---------------------------------------------------------------------------

def role_required(*roles):
    """Restrict a route to users with specific role(s)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.url))
            if current_user.role not in roles:
                flash('You do not have permission to access that page.', 'danger')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    return role_required('Admin')(f)


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 30 per hour', methods=['POST'])
def login():
    # If no admin exists, redirect to first-time setup wizard
    if not User.query.filter_by(role='Admin').first():
        return redirect(url_for('main.setup_wizard'))
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username).first()

        # Account lockout check (5 failed attempts = 15 min lockout)
        MAX_FAILED = 5
        LOCKOUT_MINUTES = 15
        if user and user.locked_until and user.locked_until > datetime.utcnow():
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
            flash(f'Account temporarily locked. Try again in {remaining} minute(s).', 'danger')
            return render_template('auth/login.html')

        if user and user.is_active and user.check_password(password):
            # Reset failed attempts on successful login
            user.failed_login_count = 0
            user.locked_until = None
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            # Audit: successful login
            db.session.add(AuditLog(
                entity_type='Auth', entity_id=user.id, action='login_success',
                before_state=None,
                after_state={'username': user.username, 'role': user.role},
                staff_user_id=user.id,
                ip_address=request.remote_addr,
            ))
            db.session.commit()

            next_page = request.args.get('next')
            # Prevent open redirect — only allow relative paths
            if next_page and (next_page.startswith('http') or next_page.startswith('//')):
                next_page = None
            return redirect(next_page or url_for('main.dashboard'))
        else:
            # Increment failed login counter and lock if threshold exceeded
            if user:
                from datetime import timedelta
                user.failed_login_count = (user.failed_login_count or 0) + 1
                if user.failed_login_count >= MAX_FAILED:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                    logger.warning('Account %s locked after %d failed attempts', username, user.failed_login_count)
                # Audit: failed login attempt
                db.session.add(AuditLog(
                    entity_type='Auth', entity_id=user.id, action='login_failed',
                    before_state=None,
                    after_state={'username': username, 'attempt': user.failed_login_count,
                                 'reason': 'wrong_password' if user.is_active else 'account_inactive'},
                    staff_user_id=user.id,
                    ip_address=request.remote_addr,
                ))
                db.session.commit()
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    # Auto-close any open shift for this user
    open_shift = Shift.query.filter_by(user_id=current_user.id, status='Open').first()
    if open_shift:
        open_shift.status = 'Closed'
        open_shift.end_time = datetime.utcnow()
        db.session.commit()

    # Audit: logout
    db.session.add(AuditLog(
        entity_type='Auth', entity_id=current_user.id, action='logout',
        before_state=None,
        after_state={'username': current_user.username},
        staff_user_id=current_user.id,
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')
        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
        elif new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for('main.dashboard'))

    return render_template('auth/change_password.html')


# ---------------------------------------------------------------------------
# Shift Management
# ---------------------------------------------------------------------------

@auth_bp.route('/shift/start', methods=['POST'])
@login_required
def start_shift():
    # Close any stale open shift first
    stale = Shift.query.filter_by(user_id=current_user.id, status='Open').first()
    if stale:
        stale.status = 'Closed'
        stale.end_time = datetime.utcnow()

    shift_type = request.form.get('shift_type', 'Morning')
    opening_cash = float(request.form.get('opening_cash', 0) or 0)

    shift = Shift(
        user_id=current_user.id,
        shift_type=shift_type,
        opening_cash=opening_cash,
        status='Open',
        start_time=datetime.utcnow(),
    )
    db.session.add(shift)
    db.session.commit()
    flash(f'{shift_type} shift started. Opening cash: ₹{opening_cash:,.0f}', 'success')
    return redirect(request.referrer or url_for('main.dashboard'))


@auth_bp.route('/shift/close', methods=['GET', 'POST'])
@login_required
def close_shift():
    """
    GET  — Show the reconciliation form for the current user's open shift.
    POST — Submit declared cash + notes; auto-approve or route to Manager.
    """
    from app.models import ShiftAdjustment

    shift = Shift.query.filter_by(user_id=current_user.id, status='Open').first()
    if not shift:
        flash('No open shift to close.', 'warning')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        declared_cash = request.form.get('declared_cash', '0')
        close_notes = request.form.get('close_notes', '').strip()
        result = shift_service.close_shift(
            shift=shift,
            declared_cash_str=declared_cash,
            close_notes=close_notes,
            user_id=current_user.id,
            ip_address=request.remote_addr,
        )
        flash(result.message, 'success' if result.success else 'danger')
        if result.success:
            return redirect(url_for('auth.shift_handover', shift_id=shift.id))
        return redirect(url_for('auth.close_shift'))

    # GET — build context for the reconciliation form
    expected = shift_service.calculate_expected_cash(shift)
    payment_summary = shift_service.get_payment_mode_summary(shift)
    cash_breakdown = shift_service.get_cash_breakdown(shift)
    adjustments = ShiftAdjustment.query.filter_by(shift_id=shift.id).order_by(ShiftAdjustment.created_at).all()
    threshold = shift_service._get_variance_threshold()

    return render_template(
        'auth/shift_close.html',
        shift=shift,
        expected_cash=expected,
        payment_summary=payment_summary,
        cash_breakdown=cash_breakdown,
        adjustments=adjustments,
        threshold=threshold,
    )


@auth_bp.route('/shift/adjustment', methods=['POST'])
@login_required
def shift_adjustment():
    """Add a cash adjustment to the current user's open shift."""
    shift = Shift.query.filter_by(user_id=current_user.id, status='Open').first()
    if not shift:
        flash('No open shift found.', 'warning')
        return redirect(url_for('main.dashboard'))

    ok, msg = shift_service.add_adjustment(
        shift=shift,
        adjustment_type=request.form.get('adjustment_type', ''),
        amount_str=request.form.get('amount', '0'),
        description=request.form.get('description', ''),
        user_id=current_user.id,
    )
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('auth.close_shift'))


@auth_bp.route('/shift/<int:shift_id>/handover')
@login_required
def shift_handover(shift_id):
    """Printable handover / shift summary report."""
    from app.models import ShiftAdjustment
    shift = db.session.get(Shift, shift_id)
    if not shift:
        flash('Shift not found.', 'danger')
        return redirect(url_for('main.dashboard'))

    # Only the shift owner or Manager/Admin can view
    if shift.user_id != current_user.id and current_user.role not in ('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    adjustments = ShiftAdjustment.query.filter_by(shift_id=shift_id).order_by(ShiftAdjustment.created_at).all()
    return render_template('auth/shift_handover.html', shift=shift, adjustments=adjustments)


@auth_bp.route('/shifts/pending-approvals')
@login_required
def shift_pending_approvals():
    """Manager/Admin: list of shifts awaiting approval."""
    if current_user.role not in ('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))
    pending = shift_service.get_pending_shift_closes()
    return render_template('auth/shift_pending_approvals.html', pending=pending)


@auth_bp.route('/shift/<int:shift_id>/approve', methods=['POST'])
@login_required
def approve_shift(shift_id):
    """Manager/Admin: approve a pending shift close."""
    if current_user.role not in ('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    shift = db.session.get(Shift, shift_id)
    if not shift:
        flash('Shift not found.', 'danger')
        return redirect(url_for('auth.shift_pending_approvals'))

    ok, msg = shift_service.approve_shift_close(
        shift=shift,
        approver_id=current_user.id,
        ip_address=request.remote_addr,
    )
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('auth.shift_pending_approvals'))


# ---------------------------------------------------------------------------
# User Management (Admin only)
# ---------------------------------------------------------------------------

@auth_bp.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.role, User.full_name).all()
    return render_template('auth/users.html', users=all_users, roles=ALL_ROLES, role_labels=ROLE_LABELS)


@auth_bp.route('/users/new', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip().lower()
    full_name = request.form.get('full_name', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'FrontDesk')

    if not username or not full_name or not password:
        flash('All fields are required.', 'danger')
        return redirect(url_for('auth.users'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'danger')
        return redirect(url_for('auth.users'))

    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('auth.users'))

    if role not in ALL_ROLES:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('auth.users'))

    user = User(username=username, full_name=full_name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'User "{full_name}" created successfully.', 'success')
    return redirect(url_for('auth.users'))


@auth_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    # Prevent demoting the last admin
    if user.role == 'Admin' and request.form.get('role') != 'Admin':
        admin_count = User.query.filter_by(role='Admin', is_active=True).count()
        if admin_count <= 1:
            flash('Cannot change role: at least one Admin must remain.', 'danger')
            return redirect(url_for('auth.users'))

    user.full_name = request.form.get('full_name', user.full_name).strip()
    new_role = request.form.get('role', user.role)
    if new_role in ALL_ROLES:
        user.role = new_role
    user.is_active = request.form.get('is_active') == 'on'

    new_password = request.form.get('new_password', '').strip()
    if new_password:
        if len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return redirect(url_for('auth.users'))
        user.set_password(new_password)

    db.session.commit()
    flash(f'User "{user.full_name}" updated.', 'success')
    return redirect(url_for('auth.users'))


@auth_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('auth.users'))

    if user.is_active and user.role == 'Admin':
        admin_count = User.query.filter_by(role='Admin', is_active=True).count()
        if admin_count <= 1:
            flash('Cannot deactivate: at least one active Admin must remain.', 'danger')
            return redirect(url_for('auth.users'))

    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User "{user.full_name}" {status}.', 'success')
    return redirect(url_for('auth.users'))


# ---------------------------------------------------------------------------
# Shift history (Manager/Admin)
# ---------------------------------------------------------------------------

@auth_bp.route('/shifts')
@login_required
def shifts():
    if not current_user.has_role('Admin', 'Manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))
    all_shifts = (
        Shift.query
        .join(User)
        .order_by(Shift.start_time.desc())
        .limit(100)
        .all()
    )
    return render_template('auth/shifts.html', shifts=all_shifts)
