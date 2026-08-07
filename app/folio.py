"""
Folio Management Blueprint
===========================
Split-billing API endpoints for managing folios on a reservation.

Each reservation starts with a default Folio A (Guest).  Staff can create
additional folios (B=Company, C=Travel Agent, etc.) and transfer individual
charges or payments between them.
"""

import logging

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from app.models import db, Reservation, Folio, ExtraCharge, Payment, Company

logger = logging.getLogger(__name__)

folio_bp = Blueprint('folio', __name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _folio_to_dict(folio):
    """Serialize a Folio to a JSON-safe dict."""
    from app.services import calculate_folio_amount
    totals = calculate_folio_amount(folio)
    return {
        'id': folio.id,
        'reservation_id': folio.reservation_id,
        'folio_letter': folio.folio_letter,
        'label': folio.label,
        'company_id': folio.company_id,
        'company_name': folio.company.name if folio.company else None,
        'is_closed': folio.is_closed,
        'closed_at': folio.closed_at.isoformat() if folio.closed_at else None,
        'notes': folio.notes,
        'created_at': folio.created_at.isoformat() if folio.created_at else None,
        'totals': totals,
    }


def _next_folio_letter(reservation_id):
    """Return the next available folio letter (B, C, D, ...) for a reservation."""
    existing = (db.session.query(Folio.folio_letter)
                .filter_by(reservation_id=reservation_id)
                .order_by(Folio.folio_letter.desc())
                .first())
    if not existing:
        return 'A'
    last = existing[0]
    next_char = chr(ord(last) + 1)
    if next_char > 'Z':
        return None  # exhausted
    return next_char


# ── List folios for a reservation ────────────────────────────────────────────

@folio_bp.route('/api/reservation/<int:reservation_id>/folios', methods=['GET'])
@login_required
def list_folios(reservation_id):
    """GET /api/reservation/<id>/folios -- list all folios for a reservation."""
    reservation = db.session.get(Reservation, reservation_id)
    if not reservation:
        return jsonify({'error': 'Reservation not found'}), 404

    folios = (Folio.query
              .filter_by(reservation_id=reservation_id)
              .order_by(Folio.folio_letter)
              .all())
    return jsonify({
        'reservation_id': reservation_id,
        'folios': [_folio_to_dict(f) for f in folios],
    })


# ── Create a new folio ──────────────────────────────────────────────────────

@folio_bp.route('/api/reservation/<int:reservation_id>/folios', methods=['POST'])
@login_required
def create_folio(reservation_id):
    """POST /api/reservation/<id>/folios -- create a new folio (B, C, etc.)."""
    # Lock the reservation row so concurrent folio creations on the same
    # reservation cannot race into duplicate letters. Without the lock,
    # two POSTs arriving at the same time could both read "no Folio B"
    # and both insert "B", failing later on the unique constraint (or
    # worse, silently on SQLite which has no such constraint).
    reservation = (db.session.query(Reservation)
                   .with_for_update(of=Reservation)
                   .filter_by(id=reservation_id)
                   .first())
    if not reservation:
        return jsonify({'error': 'Reservation not found'}), 404

    data = request.get_json(silent=True) or {}
    label = (data.get('label') or 'Guest').strip()
    company_id = data.get('company_id')
    notes = (data.get('notes') or '').strip() or None

    # Validate company if provided
    if company_id:
        company = db.session.get(Company, company_id)
        if not company:
            db.session.rollback()
            return jsonify({'error': 'Company not found'}), 404

    # Determine next letter
    letter = data.get('folio_letter')
    if letter:
        letter = letter.strip().upper()
        if len(letter) != 1 or not letter.isalpha():
            db.session.rollback()
            return jsonify({'error': 'folio_letter must be a single letter A-Z'}), 400
        # Check uniqueness (safe under the row lock above).
        exists = Folio.query.filter_by(
            reservation_id=reservation_id, folio_letter=letter
        ).first()
        if exists:
            db.session.rollback()
            return jsonify({'error': f'Folio {letter} already exists for this reservation'}), 409
    else:
        letter = _next_folio_letter(reservation_id)
        if letter is None:
            db.session.rollback()
            return jsonify({'error': 'Maximum number of folios (A-Z) reached'}), 400

    try:
        folio = Folio(
            reservation_id=reservation_id,
            folio_letter=letter,
            label=label,
            company_id=company_id,
            notes=notes,
        )
        db.session.add(folio)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('Folio create failed for reservation_id=%d: %s',
                     reservation_id, e, exc_info=True)
        return jsonify({'error': 'Could not create folio. Please try again.'}), 500

    return jsonify(_folio_to_dict(folio)), 201


# ── Transfer a charge between folios ────────────────────────────────────────

@folio_bp.route('/api/folio/<int:folio_id>/transfer-charge', methods=['POST'])
@login_required
def transfer_charge(folio_id):
    """POST /api/folio/<id>/transfer-charge

    Body: {"charge_id": 123, "target_folio_id": 456}

    Moves an ExtraCharge from its current folio to the target folio.
    Both folios must belong to the same reservation.
    """
    data = request.get_json(silent=True) or {}
    charge_id = data.get('charge_id')
    if not charge_id:
        return jsonify({'error': 'charge_id is required'}), 400

    try:
        # Lock the charge row first (deterministic order: charge < folio),
        # then the target folio. Consistent locking order avoids deadlocks
        # when two concurrent transfers touch the same rows.
        charge = (db.session.query(ExtraCharge)
                  .with_for_update(of=ExtraCharge)
                  .filter_by(id=charge_id)
                  .first())
        if not charge:
            db.session.rollback()
            return jsonify({'error': 'Charge not found'}), 404

        target_folio = (db.session.query(Folio)
                        .with_for_update(of=Folio)
                        .filter_by(id=folio_id)
                        .first())
        if not target_folio:
            db.session.rollback()
            return jsonify({'error': 'Target folio not found'}), 404
        if target_folio.is_closed:
            db.session.rollback()
            return jsonify({'error': 'Target folio is closed'}), 400

        # Reject no-op transfers explicitly so the caller notices. Silently
        # accepting "transfer onto current folio" makes it impossible for
        # the UI to tell success-that-did-nothing apart from success-that-
        # moved-something, which hides bugs.
        if charge.folio_id == target_folio.id:
            db.session.rollback()
            return jsonify({
                'error': (f'Charge #{charge.id} is already on Folio '
                          f'{target_folio.folio_letter}. Nothing to transfer.')
            }), 400

        # Both must belong to the same reservation
        if charge.reservation_id != target_folio.reservation_id:
            db.session.rollback()
            return jsonify({'error': 'Charge and target folio belong to different reservations'}), 400

        # Check source folio is not closed (if charge is already on a folio).
        # Lock it too so a concurrent "close folio" cannot complete mid-transfer.
        if charge.folio_id:
            source_folio = (db.session.query(Folio)
                            .with_for_update(of=Folio)
                            .filter_by(id=charge.folio_id)
                            .first())
            if source_folio and source_folio.is_closed:
                db.session.rollback()
                return jsonify({'error': 'Source folio is closed'}), 400

        charge.folio_id = target_folio.id
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('Charge transfer failed charge_id=%s target_folio=%d: %s',
                     charge_id, folio_id, e, exc_info=True)
        return jsonify({'error': 'Could not transfer charge. Please try again.'}), 500

    return jsonify({
        'message': f'Charge #{charge.id} transferred to Folio {target_folio.folio_letter}',
        'charge_id': charge.id,
        'target_folio_id': target_folio.id,
        'target_folio_letter': target_folio.folio_letter,
    })


# ── Transfer a payment between folios ───────────────────────────────────────

@folio_bp.route('/api/folio/<int:folio_id>/transfer-payment', methods=['POST'])
@login_required
def transfer_payment(folio_id):
    """POST /api/folio/<id>/transfer-payment

    Body: {"payment_id": 123}

    Moves a Payment to the target folio.
    Both must belong to the same reservation.
    """
    data = request.get_json(silent=True) or {}
    payment_id = data.get('payment_id')
    if not payment_id:
        return jsonify({'error': 'payment_id is required'}), 400

    try:
        # Consistent locking order: payment < folio (matches transfer_charge).
        payment = (db.session.query(Payment)
                   .with_for_update(of=Payment)
                   .filter_by(id=payment_id)
                   .first())
        if not payment:
            db.session.rollback()
            return jsonify({'error': 'Payment not found'}), 404
        if payment.is_voided:
            db.session.rollback()
            return jsonify({'error': 'Cannot transfer a voided payment'}), 400

        target_folio = (db.session.query(Folio)
                        .with_for_update(of=Folio)
                        .filter_by(id=folio_id)
                        .first())
        if not target_folio:
            db.session.rollback()
            return jsonify({'error': 'Target folio not found'}), 404
        if target_folio.is_closed:
            db.session.rollback()
            return jsonify({'error': 'Target folio is closed'}), 400

        # Reject no-op transfers explicitly (see transfer_charge for
        # rationale) — silent success hides bugs.
        if payment.folio_id == target_folio.id:
            db.session.rollback()
            return jsonify({
                'error': (f'Payment #{payment.id} is already on Folio '
                          f'{target_folio.folio_letter}. Nothing to transfer.')
            }), 400

        if payment.reservation_id != target_folio.reservation_id:
            db.session.rollback()
            return jsonify({'error': 'Payment and target folio belong to different reservations'}), 400

        if payment.folio_id:
            source_folio = (db.session.query(Folio)
                            .with_for_update(of=Folio)
                            .filter_by(id=payment.folio_id)
                            .first())
            if source_folio and source_folio.is_closed:
                db.session.rollback()
                return jsonify({'error': 'Source folio is closed'}), 400

        payment.folio_id = target_folio.id
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('Payment transfer failed payment_id=%s target_folio=%d: %s',
                     payment_id, folio_id, e, exc_info=True)
        return jsonify({'error': 'Could not transfer payment. Please try again.'}), 500

    return jsonify({
        'message': f'Payment #{payment.id} transferred to Folio {target_folio.folio_letter}',
        'payment_id': payment.id,
        'target_folio_id': target_folio.id,
        'target_folio_letter': target_folio.folio_letter,
    })
