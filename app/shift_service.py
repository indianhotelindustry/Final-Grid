"""
Shift Closing & Cash Reconciliation Service
============================================
Business logic for shift close workflow:
  - Calculate expected cash (opening + cash payments - voids +/- adjustments)
  - Build payment mode summary snapshot
  - Auto-approve if variance within threshold; else require Manager approval
  - Audit log on every state change
"""
from decimal import Decimal
from datetime import datetime
from typing import NamedTuple


class ShiftCloseResult(NamedTuple):
    success: bool
    message: str
    variance: Decimal
    approval_required: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_cash_mode_id():
    """Return the id of the 'Cash' payment mode, or None if not found."""
    from app.models import PaymentMode
    mode = PaymentMode.query.filter(PaymentMode.name.ilike('cash')).first()
    return mode.id if mode else None


def _get_variance_threshold() -> Decimal:
    """Return configurable variance threshold (default ₹50)."""
    from app.models import Settings
    s = Settings.query.filter_by(key='shift_variance_threshold').first()
    try:
        return Decimal(s.value) if s else Decimal('50')
    except Exception:
        return Decimal('50')


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------

def calculate_expected_cash(shift) -> Decimal:
    """
    Expected cash in drawer =
        opening_cash
        + SUM(Cash payments received this shift, not voided)
        - SUM(Cash payments voided during this shift)
        + SUM(float_add adjustments)
        - SUM(payout + float_remove + petty_cash adjustments)
    """
    from app.models import Payment, ShiftAdjustment, db
    from sqlalchemy import func

    opening = Decimal(str(shift.opening_cash or 0))
    cash_mode_id = _get_cash_mode_id()

    if cash_mode_id is not None:
        end_time = shift.end_time or datetime.utcnow()
        received = db.session.query(func.sum(Payment.amount)).filter(
            Payment.payment_mode_id == cash_mode_id,
            Payment.is_voided == False,
            Payment.created_at >= shift.start_time,
            Payment.created_at <= end_time,
        ).scalar() or Decimal('0')

        voided = db.session.query(func.sum(Payment.amount)).filter(
            Payment.payment_mode_id == cash_mode_id,
            Payment.is_voided == True,
            Payment.voided_at >= shift.start_time,
            Payment.voided_at <= end_time,
        ).scalar() or Decimal('0')
    else:
        received = Decimal('0')
        voided = Decimal('0')

    # Adjustments for this shift
    adjs = ShiftAdjustment.query.filter_by(shift_id=shift.id).all()
    adj_net = Decimal('0')
    for adj in adjs:
        amt = Decimal(str(adj.amount))
        if adj.adjustment_type == 'float_add':
            adj_net += amt
        else:  # payout, float_remove, petty_cash
            adj_net -= amt

    return opening + Decimal(str(received)) - Decimal(str(voided)) + adj_net


def get_payment_mode_summary(shift) -> dict:
    """
    Return {mode_name: float_total} for ALL non-voided payments during this shift.
    Also returns cash received / voided breakdown for the reconciliation display.
    """
    from app.models import Payment, PaymentMode, db
    from sqlalchemy import func

    rows = (
        db.session.query(PaymentMode.name, func.sum(Payment.amount))
        .join(Payment, Payment.payment_mode_id == PaymentMode.id)
        .filter(
            Payment.is_voided == False,
            Payment.created_at >= shift.start_time,
        )
        .group_by(PaymentMode.name)
        .all()
    )
    return {name: float(total) for name, total in rows}


def get_cash_breakdown(shift) -> dict:
    """Return cash-specific breakdown for the close form display."""
    from app.models import Payment, db
    from sqlalchemy import func

    cash_mode_id = _get_cash_mode_id()
    if cash_mode_id is None:
        return {'received': 0.0, 'voided': 0.0}

    received = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_mode_id == cash_mode_id,
        Payment.is_voided == False,
        Payment.created_at >= shift.start_time,
    ).scalar() or Decimal('0')

    voided = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_mode_id == cash_mode_id,
        Payment.is_voided == True,
        Payment.voided_at >= shift.start_time,
    ).scalar() or Decimal('0')

    return {
        'received': float(received),
        'voided': float(voided),
    }


# ---------------------------------------------------------------------------
# Close workflow
# ---------------------------------------------------------------------------

def close_shift(shift, declared_cash_str, close_notes, user_id, ip_address='') -> ShiftCloseResult:
    """
    Close an open shift with reconciliation.
    Auto-approves if |variance| <= threshold, else sets PendingApproval.
    Commits on success.
    """
    from app.models import AuditLog, db

    if shift.status != 'Open':
        return ShiftCloseResult(False, 'This shift is not open.', Decimal('0'), False)

    try:
        declared = Decimal(str(declared_cash_str or 0))
    except Exception:
        return ShiftCloseResult(False, 'Invalid declared cash amount.', Decimal('0'), False)

    expected = calculate_expected_cash(shift)
    variance = declared - expected
    threshold = _get_variance_threshold()
    payment_summary = get_payment_mode_summary(shift)

    shift.expected_cash = expected
    shift.declared_closing_cash = declared
    shift.closing_cash = declared          # keep legacy column in sync
    shift.variance = variance
    shift.close_notes = close_notes
    shift.payment_summary = payment_summary
    shift.closed_by_user_id = user_id
    shift.end_time = datetime.utcnow()

    if abs(variance) <= threshold:
        shift.status = 'Closed'
        shift.approval_status = 'auto_approved'
        approval_required = False
        msg = (
            f'Shift closed successfully. '
            f'Variance ₹{variance:+.2f} is within the ₹{threshold} threshold.'
        )
    else:
        shift.status = 'PendingApproval'
        shift.approval_status = 'pending_approval'
        approval_required = True
        msg = (
            f'Shift submitted for Manager approval. '
            f'Variance ₹{variance:+.2f} exceeds threshold of ₹{threshold}.'
        )

    log = AuditLog(
        entity_type='Shift',
        entity_id=shift.id,
        action='close_shift',
        before_state={'status': 'Open'},
        after_state={
            'status': shift.status,
            'expected_cash': float(expected),
            'declared_cash': float(declared),
            'variance': float(variance),
        },
        staff_user_id=user_id,
        ip_address=ip_address,
    )
    db.session.add(log)
    db.session.commit()

    return ShiftCloseResult(True, msg, variance, approval_required)


def approve_shift_close(shift, approver_id, ip_address='') -> tuple:
    """Manager/Admin approves a PendingApproval shift. Commits."""
    from app.models import AuditLog, db

    if shift.status != 'PendingApproval':
        return False, 'Shift is not pending approval.'

    shift.status = 'Closed'
    shift.approval_status = 'approved'
    shift.approved_by_user_id = approver_id
    shift.approved_at = datetime.utcnow()

    log = AuditLog(
        entity_type='Shift',
        entity_id=shift.id,
        action='approve_shift_close',
        before_state={'status': 'PendingApproval'},
        after_state={'status': 'Closed', 'approved_by_user_id': approver_id},
        staff_user_id=approver_id,
        ip_address=ip_address,
    )
    db.session.add(log)
    db.session.commit()
    return True, 'Shift close approved.'


def add_adjustment(shift, adjustment_type, amount_str, description, user_id) -> tuple:
    """Add a cash adjustment to an open shift. Commits."""
    from app.models import ShiftAdjustment, db

    if shift.status != 'Open':
        return False, 'Cannot add adjustments to a closed shift.'

    valid_types = ('payout', 'float_add', 'float_remove', 'petty_cash')
    if adjustment_type not in valid_types:
        return False, 'Invalid adjustment type.'

    try:
        amount = Decimal(str(amount_str or 0))
        if amount <= 0:
            return False, 'Amount must be greater than zero.'
    except Exception:
        return False, 'Invalid amount.'

    if not description or not description.strip():
        return False, 'Description is required.'

    adj = ShiftAdjustment(
        shift_id=shift.id,
        adjustment_type=adjustment_type,
        amount=amount,
        description=description.strip(),
        created_by_user_id=user_id,
    )
    db.session.add(adj)
    db.session.commit()
    return True, 'Adjustment recorded.'


def get_pending_shift_closes():
    """Return all shifts awaiting Manager approval."""
    from app.models import Shift
    return (
        Shift.query
        .filter_by(status='PendingApproval')
        .order_by(Shift.end_time.desc())
        .all()
    )
