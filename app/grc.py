"""
GRC Blueprint — Guest Registration Card + Form C routes
========================================================
"""
from datetime import datetime, date
from flask import Blueprint, flash, redirect, url_for, jsonify, request, send_file, render_template
from flask_login import login_required, current_user
from app.auth import role_required
from app.models import db, Reservation, Guest, ForeignNationalInfo
from app.grc_service import (generate_grc_pdf, generate_form_c_pdf,
                              is_foreign_national, _gather_grc_context,
                              build_grc_filename)
from app.validators import validate_fields, validate_text_length, parse_date_optional

grc_bp = Blueprint('grc', __name__, url_prefix='/grc')


@grc_bp.before_request
@login_required
def _require_login():
    pass


@grc_bp.route('/<int:reservation_id>/pdf')
@role_required('Admin', 'Manager', 'FrontDesk')
def download_pdf(reservation_id):
    """Download GRC as PDF."""
    reservation = Reservation.query.get_or_404(reservation_id)
    buf = generate_grc_pdf(reservation_id)
    if not buf:
        flash('Could not generate GRC PDF.', 'danger')
        return redirect(request.referrer or url_for('main.index'))
    return send_file(buf, download_name=build_grc_filename(reservation),
                     as_attachment=True, mimetype='application/pdf')


@grc_bp.route('/<int:reservation_id>/form-c')
@role_required('Admin', 'Manager', 'FrontDesk')
def download_form_c(reservation_id):
    """Download FRRO Form C as PDF (foreign nationals only)."""
    reservation = Reservation.query.get_or_404(reservation_id)
    if not is_foreign_national(reservation.guest):
        flash('Form C is only for foreign nationals.', 'warning')
        return redirect(request.referrer or url_for('main.index'))
    buf = generate_form_c_pdf(reservation_id)
    if not buf:
        flash('Could not generate Form C PDF.', 'danger')
        return redirect(request.referrer or url_for('main.index'))
    ref = reservation.booking_reference or str(reservation_id)
    return send_file(buf, download_name=f'FormC-{ref}.pdf',
                     as_attachment=True, mimetype='application/pdf')


@grc_bp.route('/<int:reservation_id>/preview')
@role_required('Admin', 'Manager', 'FrontDesk')
def preview(reservation_id):
    """Preview GRC in the browser on an A4-sized, print-friendly page.

    The PDF renderer reads images from filesystem paths; the browser cannot.
    Convert the shared context's file-system paths into authenticated web URLs
    (``main.serve_private_upload`` for ID docs, static uploads for photo +
    signature) before rendering the HTML preview. The PDF path continues to
    use ``grc_pdf.html`` with the original paths intact — don't touch that.
    """
    from app.models import CheckInRecord, GuestIDDocument
    ctx = _gather_grc_context(reservation_id)
    if not ctx:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('main.index'))

    # Resolve web URLs for images directly from the stored DB paths so the
    # preview does not depend on the filesystem existence check used for PDF.
    reservation = ctx['reservation']
    checkin = ctx.get('checkin')
    id_doc = ctx.get('id_doc')

    def _static_url(rel):
        return url_for('static', filename=rel) if rel else None

    def _private_url(rel):
        return url_for('main.serve_private_upload', filepath=rel) if rel else None

    ctx['guest_photo_url'] = _static_url(checkin.guest_photo_path) if checkin and checkin.guest_photo_path else None
    ctx['signature_url']   = _static_url(checkin.signature_path)   if checkin and checkin.signature_path   else None
    ctx['id_front_url']    = _private_url(id_doc.front_image_path) if id_doc and id_doc.front_image_path   else None
    ctx['id_back_url']     = _private_url(id_doc.back_image_path)  if id_doc and id_doc.back_image_path    else None

    # Logo — served from static/uploads by filename
    logo_fn = (ctx['hotel'] or {}).get('invoice_logo_filename') or ''
    ctx['logo_url'] = url_for('static', filename='uploads/' + logo_fn) if logo_fn else None

    ctx['pdf_download_url'] = url_for('grc.download_pdf', reservation_id=reservation_id)
    return render_template('grc_preview.html', **ctx)


@grc_bp.route('/<int:reservation_id>/save-foreign-info', methods=['POST'])
@role_required('Admin', 'Manager', 'FrontDesk')
def save_foreign_info(reservation_id):
    """Save foreign national details (AJAX)."""
    reservation = Reservation.query.get_or_404(reservation_id)
    guest = reservation.guest
    data = request.get_json() or request.form

    fni = ForeignNationalInfo.query.filter_by(guest_id=guest.id).first()
    if not fni:
        fni = ForeignNationalInfo(guest_id=guest.id, nationality=guest.country or '')
        db.session.add(fni)

    fni.nationality = data.get('nationality', fni.nationality)
    fni.passport_number = data.get('passport_number', fni.passport_number)
    fni.passport_issue_place = data.get('passport_issue_place', fni.passport_issue_place)
    fni.visa_number = data.get('visa_number', fni.visa_number)
    fni.visa_type = data.get('visa_type', fni.visa_type)
    fni.visa_issue_place = data.get('visa_issue_place', fni.visa_issue_place)
    fni.arrival_from = data.get('arrival_from', fni.arrival_from)
    fni.next_destination = data.get('next_destination', fni.next_destination)
    fni.purpose_of_visit = data.get('purpose_of_visit', fni.purpose_of_visit)
    fni.employed_in_india = data.get('employed_in_india') in ('1', 'true', True)
    fni.employer_name = data.get('employer_name', fni.employer_name)

    # Text length checks
    txt_errs = validate_fields(
        validate_text_length(fni.nationality, 'Nationality', max_len=60),
        validate_text_length(fni.passport_number, 'Passport number', max_len=20),
        validate_text_length(fni.visa_number, 'Visa number', max_len=30),
        validate_text_length(fni.employer_name, 'Employer name', max_len=200),
        validate_text_length(fni.arrival_from, 'Arrival from', max_len=100),
        validate_text_length(fni.next_destination, 'Next destination', max_len=100),
    )
    if txt_errs:
        return jsonify({'success': False, 'errors': txt_errs}), 400

    # Parse dates safely with validation
    date_fields = {
        'passport_issue_date': 'Passport issue date',
        'passport_expiry_date': 'Passport expiry date',
        'visa_issue_date': 'Visa issue date',
        'visa_expiry_date': 'Visa expiry date',
    }
    date_errs = []
    for field, label in date_fields.items():
        val = data.get(field, '')
        parsed, err = parse_date_optional(val, label)
        if err:
            date_errs.append(err)
        elif parsed:
            setattr(fni, field, parsed)

    # Cross-validate: expiry must be after issue
    pp_issue = getattr(fni, 'passport_issue_date', None)
    pp_expiry = getattr(fni, 'passport_expiry_date', None)
    if pp_issue and pp_expiry and pp_expiry <= pp_issue:
        date_errs.append('Passport expiry date must be after issue date.')

    v_issue = getattr(fni, 'visa_issue_date', None)
    v_expiry = getattr(fni, 'visa_expiry_date', None)
    if v_issue and v_expiry and v_expiry <= v_issue:
        date_errs.append('Visa expiry date must be after issue date.')

    if date_errs:
        return jsonify({'success': False, 'errors': date_errs}), 400

    db.session.commit()
    return jsonify({'success': True})
