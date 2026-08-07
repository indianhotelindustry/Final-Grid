"""
Payment Void / Reversal Service
================================
Business rules:
  1. Original Payment record is NEVER deleted — only marked is_voided=True.
  2. Void window: payment must be within void_window_hours of posting AND
     the business date must not have advanced past the payment date (not settled).
  3. FrontDesk:  can REQUEST a void → creates VoidRequest (status=Pending).
  4. Manager:    can REQUEST and APPROVE in one step (direct void)
                 within the standard void window.
  5. Admin:      same as Manager + extended window (admin_void_window_hours).
  6. Reversal (post-settlement): handled by the Refund module — out of scope here.
  7. Mandatory: reason for every void/request.
  8. AuditLog entry on every state change.
  9. Folio balance recalculates automatically (computed from non-voided payments).
 10. Cannot void an already-voided payment.
 11. Cannot void a payment that has an approved pending VoidRequest (already done).

Settings keys:
  void_window_hours       — default 2  (for Manager)
  admin_void_window_hours — default 24 (for Admin)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple

from app.models import AuditLog, Payment, Settings, User, VoidRequest, db

logger = logging.getLogger(__name__)


def _lock_payment_for_void(payment_id: int) -> Payment | None:
    """Fetch a Payment row with a pessimistic row lock.

    Returns None if the payment does not exist. The lock is released when
    the caller's transaction commits or rolls back — so callers MUST do
    exactly one of those before returning.

    Why: void is a multi-step check-then-update flow. Two concurrent
    ``direct_void`` / ``approve_void`` calls for the same payment must not
    both pass the ``is_voided == False`` check. Locking the row at read
    time serialises those flows at the database level.
    """
    return (db.session.query(Payment)
            .with_for_update(of=Payment)
            .filter_by(id=payment_id)
            .first())


def _lock_void_request(void_request_id: int) -> VoidRequest | None:
    """Lock a VoidRequest row so two approvers cannot both decide it."""
    return (db.session.query(VoidRequest)
            .with_for_update(of=VoidRequest)
            .filter_by(id=void_request_id)
            .first())


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class VoidResult(NamedTuple):
    success: bool
    message: str
    void_request: object = None   # VoidRequest | None


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _get_window_hours(user: User) -> int:
    if user.role == 'Admin':
        s = Settings.query.filter_by(key='admin_void_window_hours').first()
        return int(s.value) if s and s.value else 24
    s = Settings.query.filter_by(key='void_window_hours').first()
    return int(s.value) if s and s.value else 2


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _within_window(payment: Payment, user: User) -> tuple[bool, str]:
    """Check if payment is still within the void time window."""
    window_hours = _get_window_hours(user)
    age = datetime.utcnow() - payment.created_at
    if age > timedelta(hours=window_hours):
        hours_ago = age.total_seconds() / 3600
        return False, (
            f'Payment was posted {hours_ago:.1f}h ago — '
            f'void window is {window_hours}h. Use Refund for post-settlement reversals.'
        )
    return True, ''


def _is_settled(payment: Payment) -> bool:
    """
    A payment is 'settled' if the night audit for its payment_date has been
    Completed or Warning-completed.  A mere business-date advance is NOT enough —
    the audit must have actually run and locked the date.  This prevents false
    'settled' blocks when the audit is Reopened or still Pending.
    """
    from app.models import NightAuditLog
    log = NightAuditLog.query.filter(
        NightAuditLog.audit_date == payment.payment_date,
        NightAuditLog.status.in_(['Completed', 'Warning'])
    ).first()
    return log is not None


def validate_void_eligibility(
    payment: Payment,
    user: User,
    check_window: bool = True,
) -> tuple[bool, str]:
    """Return (ok, error_msg). Validates before any void or request."""
    if payment.is_voided:
        return False, 'This payment has already been voided.'

    # Check for existing pending request
    pending = VoidRequest.query.filter_by(
        payment_id=payment.id, status='Pending'
    ).first()
    if pending:
        return False, 'A void request for this payment is already pending approval.'

    if _is_settled(payment):
        return False, (
            'Payment date has been settled by night audit. '
            'Use the Refund module for post-settlement reversals.'
        )

    if check_window:
        ok, msg = _within_window(payment, user)
        if not ok:
            return False, msg

    return True, ''


# ---------------------------------------------------------------------------
# FrontDesk: create a void request
# ---------------------------------------------------------------------------

def request_void(
    payment_id: int,
    user: User,
    reason: str,
    ip_address: str = '',
) -> VoidResult:
    """
    FrontDesk (and Manager/Admin) create a pending void request.
    Manager/Admin can then approve immediately via approve_void().
    """
    if not reason.strip():
        return VoidResult(False, 'Void reason is mandatory.')

    try:
        payment = _lock_payment_for_void(payment_id)
        if not payment:
            db.session.rollback()
            return VoidResult(False, 'Payment not found.')

        ok, msg = validate_void_eligibility(payment, user)
        if not ok:
            db.session.rollback()
            return VoidResult(False, msg)

        vr = VoidRequest(
            payment_id=payment_id,
            requested_by_user_id=user.id,
            reason=reason.strip(),
            status='Pending',
        )
        db.session.add(vr)

        db.session.add(AuditLog(
            entity_type='Payment',
            entity_id=payment_id,
            action='void_requested',
            before_state={'is_voided': False, 'amount': float(payment.amount)},
            after_state={'void_request_status': 'Pending', 'reason': reason.strip()},
            staff_user_id=user.id,
            ip_address=ip_address,
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('request_void failed payment_id=%s user_id=%s: %s',
                     payment_id, getattr(user, 'id', None), e, exc_info=True)
        return VoidResult(False, 'Could not submit void request. Please try again.')
    return VoidResult(True, 'Void request submitted for Manager/Admin approval.', vr)


# ---------------------------------------------------------------------------
# Manager / Admin: approve a pending request → executes the void
# ---------------------------------------------------------------------------

def approve_void(
    void_request_id: int,
    approver: User,
    ip_address: str = '',
) -> VoidResult:
    """Approve a pending VoidRequest and immediately void the payment.

    Locks both the VoidRequest and its Payment row to prevent:
      - two approvers deciding the same request simultaneously
      - concurrent direct_void slipping in between the re-validation and
        the ``is_voided = True`` write
    """
    if approver.role not in ('Admin', 'Manager'):
        return VoidResult(False, 'Only Manager or Admin can approve void requests.')

    try:
        # Lock order: VoidRequest first (identifier used to enter this flow),
        # then its Payment. Keep the order consistent across call-sites.
        vr = _lock_void_request(void_request_id)
        if not vr:
            db.session.rollback()
            return VoidResult(False, 'Void request not found.')
        if vr.status != 'Pending':
            db.session.rollback()
            return VoidResult(False, f'Request is already {vr.status}.')

        payment = _lock_payment_for_void(vr.payment_id)
        if not payment:
            db.session.rollback()
            return VoidResult(False, 'Associated payment not found.')

        # Re-validate at approval time (payment may have been settled since request)
        ok, msg = validate_void_eligibility(payment, approver, check_window=False)
        if not ok:
            vr.status = 'Rejected'
            vr.decided_by_user_id = approver.id
            vr.decided_at = datetime.utcnow()
            vr.rejection_reason = f'Auto-rejected at approval: {msg}'
            db.session.commit()
            return VoidResult(False, f'Cannot void: {msg}')

        _execute_void(payment, approver, vr.reason, ip_address)

        vr.status = 'Approved'
        vr.decided_by_user_id = approver.id
        vr.decided_at = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('approve_void failed vr_id=%s approver_id=%s: %s',
                     void_request_id, getattr(approver, 'id', None), e,
                     exc_info=True)
        return VoidResult(False, 'Could not approve void. Please try again.')

    return VoidResult(
        True,
        f'Payment of ₹{float(payment.amount):,.2f} voided successfully.',
        vr,
    )


def reject_void(
    void_request_id: int,
    approver: User,
    rejection_reason: str,
    ip_address: str = '',
) -> VoidResult:
    """Reject a pending VoidRequest."""
    if approver.role not in ('Admin', 'Manager'):
        return VoidResult(False, 'Only Manager or Admin can reject void requests.')

    try:
        vr = _lock_void_request(void_request_id)
        if not vr or vr.status != 'Pending':
            db.session.rollback()
            return VoidResult(False, 'Void request not found or already decided.')

        vr.status = 'Rejected'
        vr.decided_by_user_id = approver.id
        vr.decided_at = datetime.utcnow()
        vr.rejection_reason = rejection_reason.strip() or 'No reason given.'

        db.session.add(AuditLog(
            entity_type='Payment',
            entity_id=vr.payment_id,
            action='void_rejected',
            before_state={'void_request_status': 'Pending'},
            after_state={'void_request_status': 'Rejected', 'reason': vr.rejection_reason},
            staff_user_id=approver.id,
            ip_address=ip_address,
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('reject_void failed vr_id=%s approver_id=%s: %s',
                     void_request_id, getattr(approver, 'id', None), e,
                     exc_info=True)
        return VoidResult(False, 'Could not reject void. Please try again.')
    return VoidResult(True, 'Void request rejected.', vr)


# ---------------------------------------------------------------------------
# Manager / Admin: direct single-step void (no prior request needed)
# ---------------------------------------------------------------------------

def direct_void(
    payment_id: int,
    user: User,
    reason: str,
    ip_address: str = '',
) -> VoidResult:
    """
    Manager/Admin void a payment in one step without prior FrontDesk request.
    Creates a VoidRequest record marked Approved for audit completeness.
    """
    if user.role not in ('Admin', 'Manager'):
        return VoidResult(False, 'Only Manager or Admin can void payments directly.')

    if not reason.strip():
        return VoidResult(False, 'Void reason is mandatory.')

    try:
        # Pessimistic lock on the Payment row — two concurrent direct_void
        # calls for the same payment will serialise, and the second one
        # will see is_voided=True and be rejected by validate_void_eligibility.
        payment = _lock_payment_for_void(payment_id)
        if not payment:
            db.session.rollback()
            return VoidResult(False, 'Payment not found.')

        ok, msg = validate_void_eligibility(payment, user)
        if not ok:
            db.session.rollback()
            return VoidResult(False, msg)

        _execute_void(payment, user, reason, ip_address)

        # Record a completed VoidRequest for auditability
        vr = VoidRequest(
            payment_id=payment_id,
            requested_by_user_id=user.id,
            reason=reason.strip(),
            status='Approved',
            decided_by_user_id=user.id,
            decided_at=datetime.utcnow(),
        )
        db.session.add(vr)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('direct_void failed payment_id=%s user_id=%s: %s',
                     payment_id, getattr(user, 'id', None), e, exc_info=True)
        return VoidResult(False, 'Could not void payment. Please try again.')

    return VoidResult(
        True,
        f'Payment of ₹{float(payment.amount):,.2f} voided successfully.',
        vr,
    )


# ---------------------------------------------------------------------------
# Internal: execute the actual void
# ---------------------------------------------------------------------------

def _execute_void(
    payment: Payment,
    user: User,
    reason: str,
    ip_address: str,
) -> None:
    """Mark payment as voided. Does NOT commit — caller commits."""
    before = {'is_voided': False, 'amount': float(payment.amount)}
    payment.is_voided        = True
    payment.voided_at        = datetime.utcnow()
    payment.voided_by_user_id = user.id
    payment.void_reason      = reason

    db.session.add(AuditLog(
        entity_type='Payment',
        entity_id=payment.id,
        action='voided',
        before_state=before,
        after_state={
            'is_voided':    True,
            'void_reason':  reason,
            'voided_by':    user.username,
            'reservation_id': payment.reservation_id,
        },
        staff_user_id=user.id,
        ip_address=ip_address,
    ))


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_pending_void_requests():
    """All Pending void requests with payment and reservation info loaded."""
    return (
        VoidRequest.query
        .filter_by(status='Pending')
        .order_by(VoidRequest.requested_at.asc())
        .all()
    )


def can_request_void(user: User) -> bool:
    return user.role in ('Admin', 'Manager', 'FrontDesk')


def can_approve_void(user: User) -> bool:
    return user.role in ('Admin', 'Manager')
