import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, send_file, Response
from flask_login import login_required, current_user
from app.models import db, Room, RoomType, Guest, Reservation, Payment, PaymentMode, ExtraCharge, BusinessDate, Settings, NightAuditLog, Company, AuditLog, CheckInRecord, User
from app.services import get_business_date, calculate_stay_amount, run_night_audit

logger = logging.getLogger(__name__)
from app.rates import get_applicable_rate
from datetime import datetime, date, timedelta
from sqlalchemy import func, inspect

bp = Blueprint('main', __name__)


# ---------------------------------------------------------------------------
# Health check — lightweight endpoint for connectivity detection
# ---------------------------------------------------------------------------
@bp.route('/api/health')
def health_check():
    """Returns 200 OK if the server is reachable. No auth required.

    Also reports the running app version (read from version.txt) so the
    patch installer can verify post-restart that the newly-deployed
    version is actually the one serving requests.
    """
    version = 'unknown'
    try:
        import os as _os
        _vf = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)),
                            'version.txt')
        if _os.path.exists(_vf):
            with open(_vf, 'r', encoding='utf-8') as _f:
                version = _f.read().strip() or 'unknown'
    except Exception:
        pass
    return jsonify({'status': 'ok', 'online': True, 'version': version})


# ---------------------------------------------------------------------------
# First-run setup wizard — only available when no admin user exists
# ---------------------------------------------------------------------------
@bp.route('/setup', methods=['GET', 'POST'])
def setup_wizard():
    """Browser-based hotel setup. Only works on first run (no admin user)."""
    if User.query.filter_by(role='Admin').first():
        abort(404)

    if request.method == 'POST':
        # Hotel details → Settings
        _settings = {
            'hotel_name': request.form.get('hotel_name', 'My Hotel').strip(),
            'hotel_address': request.form.get('hotel_address', '').strip(),
            'hotel_contact': request.form.get('hotel_contact', '').strip(),
            'hotel_email': request.form.get('hotel_email', '').strip(),
            'hotel_gstin': request.form.get('hotel_gstin', '').strip(),
            'hotel_state_code': request.form.get('hotel_state_code', '').strip(),
            'hotel_contact_person': request.form.get('hotel_contact_person', '').strip(),
        }
        for key, value in _settings.items():
            s = Settings.query.filter_by(key=key).first()
            if s:
                s.value = value
            else:
                db.session.add(Settings(key=key, value=value))

        # Property identity
        import re as _setup_re
        _slug = _setup_re.sub(r'[^a-z0-9]+', '-', _settings['hotel_name'].lower()).strip('-')
        for _pk, _pv in [
            ('property_id', _slug),
            ('property_group', ''),
            ('install_date', date.today().isoformat()),
            ('installed_version', os.environ.get('APP_VERSION', '1.0.0')),
        ]:
            if not Settings.query.filter_by(key=_pk).first():
                db.session.add(Settings(key=_pk, value=_pv))

        # Update HOTEL_NAME in .env
        from flask import current_app
        current_app.config['HOTEL_NAME'] = _settings['hotel_name']

        # Admin account
        admin_user = request.form.get('admin_username', 'admin').strip() or 'admin'
        admin_pass = request.form.get('admin_password', '').strip()
        admin_name = request.form.get('admin_fullname', 'Administrator').strip()
        if not admin_pass or len(admin_pass) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('setup_wizard.html')

        admin = User(
            username=admin_user,
            full_name=admin_name,
            role='Admin',
            is_active=True,
            is_app_owner=True,
        )
        admin.set_password(admin_pass)
        db.session.add(admin)

        # Logo upload
        logo_file = request.files.get('hotel_logo')
        if logo_file and logo_file.filename:
            _ext = os.path.splitext(logo_file.filename)[1].lower()
            if _ext in ('.png', '.jpg', '.jpeg', '.svg', '.webp'):
                logo_fn = f'hotel_logo{_ext}'
                upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                logo_file.save(os.path.join(upload_dir, logo_fn))
                s = Settings.query.filter_by(key='invoice_logo_filename').first()
                if s:
                    s.value = logo_fn
                else:
                    db.session.add(Settings(key='invoice_logo_filename', value=logo_fn))

        db.session.commit()
        flash(f'Setup complete! Welcome to {_settings["hotel_name"]} PMS.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('setup_wizard.html')


# ---------------------------------------------------------------------------
# Check-in input validation helpers
# ---------------------------------------------------------------------------
from app.validators import (
    clean_phone as _clean_phone, validate_phone, validate_email,
    validate_name, validate_fields, validate_id_proof, validate_pin_code,
    validate_positive_int, validate_non_negative_float, validate_positive_float,
    validate_date_range, validate_not_past, validate_enum,
    validate_text_length, validate_phone_optional, validate_email_required,
)

import re as _re


def _validate_guest_input(name: str | None, phone: str | None) -> str | None:
    """Return an error message if guest name/phone are invalid, else None."""
    errs = validate_fields(
        validate_name(name, 'Guest name'),
        validate_phone(phone, 'Guest phone'),
    )
    return errs[0] if errs else None


def _generate_advance_receipt_number(reservation) -> str | None:
    """Atomically assign a sequential, year-scoped Advance Receipt number.

    Format: ``AR-YYYY-NNNN`` (e.g. AR-2026-0001). The counter resets at the
    start of each calendar year (no manual reset — driven by the year prefix
    embedded in the sequence key).

    Returns the generated number or None on failure. Idempotent — if a
    number is already on the row, that value is returned unchanged.
    """
    from sqlalchemy.exc import IntegrityError
    import logging as _arn_log
    _logger = _arn_log.getLogger(__name__)

    if reservation.advance_receipt_number:
        return reservation.advance_receipt_number

    year = datetime.utcnow().strftime('%Y')
    counter_key = f'advance_receipt_counter_{year}'

    max_retries = 3
    for attempt in range(max_retries):
        try:
            counter_row = (db.session.query(Settings)
                           .filter_by(key=counter_key)
                           .with_for_update()
                           .first())
            if counter_row:
                new_val = int(counter_row.value or 0) + 1
                # Optimistic-lock update — fails the row if it changed
                # under us, forcing a retry.
                result = db.session.execute(
                    db.update(Settings)
                    .where(Settings.key == counter_key)
                    .where(Settings.value == counter_row.value)
                    .values(value=str(new_val))
                )
                if (result.rowcount or 0) == 0:
                    raise IntegrityError('counter advanced under us', None, None)
                current_n = new_val
            else:
                current_n = 1
                db.session.add(Settings(
                    key=counter_key, value='1',
                    description=f'Advance receipt counter for year {year}'))
                db.session.flush()

            receipt_no = f'AR-{year}-{current_n:04d}'
            reservation.advance_receipt_number = receipt_no
            reservation.advance_receipt_date   = datetime.utcnow()
            db.session.commit()
            return receipt_no

        except IntegrityError:
            db.session.rollback()
            _logger.warning(
                'Advance receipt number conflict (attempt %d/%d) for reservation %d',
                attempt + 1, max_retries, reservation.id)
            db.session.refresh(reservation)
            if reservation.advance_receipt_number:
                return reservation.advance_receipt_number

    _logger.error('Failed to allocate advance receipt number for res=%d', reservation.id)
    return None


def _generate_invoice_number(reservation, inv_settings: dict) -> str | None:
    """
    Atomically assign a sequential invoice number to a reservation.

    Uses atomic UPDATE ... SET value = value + 1 to prevent race conditions
    on both PostgreSQL and SQLite (no read-modify-write gap).

    Returns the generated invoice number, or None on failure.
    """
    from flask import current_app
    from sqlalchemy.exc import IntegrityError
    import logging as _inv_log
    _logger = _inv_log.getLogger(__name__)

    if reservation.invoice_number:
        return reservation.invoice_number          # already assigned

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Atomic increment: UPDATE settings SET value = CAST(value AS INTEGER) + 1
            # WHERE key = 'invoice_counter' RETURNING value
            # This avoids the read-modify-write race on both PG and SQLite.
            counter_row = (db.session.query(Settings)
                           .filter_by(key='invoice_counter')
                           .with_for_update()
                           .first())
            if counter_row:
                # Use SQLAlchemy expression-level update for atomicity
                new_val = int(counter_row.value or 0) + 1
                db.session.execute(
                    db.update(Settings)
                    .where(Settings.key == 'invoice_counter')
                    .where(Settings.value == counter_row.value)  # optimistic lock
                    .values(value=str(new_val))
                )
                current_n = new_val
            else:
                current_n = 1
                db.session.add(Settings(
                    key='invoice_counter', value='1',
                    description='Running sequential invoice number counter'))
                db.session.flush()

            prefix = (inv_settings.get('invoice_prefix') or 'INV').strip().upper()
            loc    = (inv_settings.get('invoice_location_code') or '').strip().upper()
            year   = datetime.utcnow().strftime('%Y')
            inv_no = (f'{prefix}-{loc}-{year}-{current_n:06d}'
                      if loc else f'{prefix}-{year}-{current_n:06d}')

            reservation.invoice_number = inv_no
            db.session.commit()
            return inv_no

        except IntegrityError:
            db.session.rollback()
            _logger.warning(
                'Invoice number conflict (attempt %d/%d) for reservation %d',
                attempt + 1, max_retries, reservation.id)
            db.session.refresh(reservation)
            if reservation.invoice_number:
                return reservation.invoice_number
            continue
        except Exception as e:
            db.session.rollback()
            _logger.error('Invoice number generation failed: %s', e)
            return None

    _logger.error('Invoice number generation exhausted retries for reservation %d',
                  reservation.id)
    return None


def _validate_checkin_numbers(nights=None, rate=None, advance=None) -> str | None:
    """Return an error message if numeric check-in fields are invalid, else None."""
    if nights is not None:
        if not isinstance(nights, int) or nights < 1:
            return 'Number of nights must be at least 1.'
        if nights > 365:
            return 'Number of nights cannot exceed 365.'
    if rate is not None:
        try:
            rate = float(rate)
        except (ValueError, TypeError):
            return 'Tariff / rate must be a valid number.'
        if rate < 0:
            return 'Tariff / rate cannot be negative.'
    if advance is not None:
        try:
            advance = float(advance)
        except (ValueError, TypeError):
            return 'Advance payment must be a valid number.'
        if advance < 0:
            return 'Advance payment cannot be negative.'
    return None


# ---------------------------------------------------------------------------
# Audit helper — call this on every state-changing operation
# ---------------------------------------------------------------------------
def _write_audit(entity_type, entity_id, action, before_state, after_state):
    """Write an entry to the AuditLog table. Never raises — audit failures are non-fatal."""
    import logging as _logging
    _audit_log = _logging.getLogger(__name__)
    try:
        user_id = current_user.id if current_user and current_user.is_authenticated else 0
        log = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
            staff_user_id=user_id,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(log)
        db.session.flush()
    except Exception as _exc:
        # Log the failure — never silently swallow audit errors
        _audit_log.error(
            'AuditLog write FAILED | entity=%s id=%s action=%s | %s',
            entity_type, entity_id, action, _exc, exc_info=True
        )


# ---------------------------------------------------------------------------
# Auth guard — all routes in this blueprint require login
# ---------------------------------------------------------------------------
@bp.before_request
def require_login():
    """Redirect unauthenticated users to the login page for every main route."""
    # Exempt public routes from login requirement
    _public = {'main.health_check', 'main.setup_wizard'}
    if request.endpoint in _public:
        return
    # If no admin exists yet, redirect everything to setup wizard
    if not User.query.filter_by(role='Admin').first():
        if request.endpoint != 'main.setup_wizard':
            return redirect(url_for('main.setup_wizard'))
        return
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))


# ---------------------------------------------------------------------------
# File upload helper — validate type and size before saving
# ---------------------------------------------------------------------------
_ALLOWED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
# Map extension → expected MIME type prefix (validated via imghdr)
_ALLOWED_MIME_SIGS = {
    b'\xff\xd8\xff': 'jpeg',   # JPEG
    b'\x89PNG':      'png',    # PNG
    b'RIFF':         'webp',   # WEBP (bytes 0-3; bytes 8-11 == WEBP confirmed separately)
}
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def _check_image_magic(data: bytes, ext: str) -> bool:
    """Return True if the file's magic bytes match the declared extension."""
    if ext in ('.jpg', '.jpeg'):
        return data[:3] == b'\xff\xd8\xff'
    if ext == '.png':
        return data[:4] == b'\x89PNG'
    if ext == '.webp':
        return data[:4] == b'RIFF' and data[8:12] == b'WEBP'
    return False


def _save_upload(file_obj, prefix, upload_subdir='checkin'):
    """
    Validate and save an uploaded file. Returns relative path or None.
    Raises ValueError with a user-friendly message on bad input.
    Checks: extension whitelist, magic bytes (MIME), size limit, safe filename.
    """
    import os
    from flask import current_app
    from werkzeug.utils import secure_filename as _secure_filename

    if not file_obj or not file_obj.filename:
        return None

    # Sanitize the original filename against path traversal / special chars
    safe_orig = _secure_filename(file_obj.filename)
    if not safe_orig:
        raise ValueError('Invalid filename.')

    ext = os.path.splitext(safe_orig)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise ValueError(f'Invalid file type "{ext}". Allowed: jpg, jpeg, png, webp.')

    # Check size before reading full content
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(0)
    if size > _MAX_UPLOAD_BYTES:
        raise ValueError(f'File too large ({size // 1024} KB). Maximum is 5 MB.')

    # Read enough bytes to verify magic signature
    header = file_obj.read(12)
    file_obj.seek(0)
    if not _check_image_magic(header, ext):
        raise ValueError('File content does not match the declared image type.')

    # Build a safe, unique filename — no user-controlled components
    filename = f"{prefix}_{int(datetime.utcnow().timestamp())}{ext}"
    upload_path = os.path.join(current_app.root_path, 'static', 'uploads', upload_subdir)
    os.makedirs(upload_path, exist_ok=True)
    file_obj.save(os.path.join(upload_path, filename))
    return f"uploads/{upload_subdir}/{filename}"


# ---------------------------------------------------------------------------
# Role helper (inline, no circular import)
# ---------------------------------------------------------------------------
def _deny_role(*allowed_roles):
    """Return a 403-redirect if current_user's role is not in allowed_roles."""
    if current_user.role not in allowed_roles:
        flash('You do not have permission to access that page.', 'danger')
        return redirect(url_for('main.dashboard'))
    return None


def _resolve_default_checkout_hm() -> str:
    """Return the hotel-configured default checkout time as an 'HH:MM' string.

    Priority:
      1. Settings['default_checkout_time']  — legacy key, consumed by the
         reservations grid and shared badges.
      2. Settings['cico_standard_checkout'] — CICO engine's own key, used
         for early/late-CO slab detection.
      3. Hard default '11:00'.

    The value is validated (5 chars, 'HH:MM' shape) before being returned
    so a malformed Settings row cannot inject bad markup into templates.
    """
    def _valid(v):
        v = (v or '').strip()
        return v if (len(v) == 5 and v[2:3] == ':'
                     and v[:2].isdigit() and v[3:].isdigit()) else None
    for key in ('default_checkout_time', 'cico_standard_checkout'):
        row = Settings.query.filter_by(key=key).first()
        v = _valid(row.value) if row else None
        if v:
            return v
    return '11:00'


@bp.route('/private-uploads/<path:filepath>')
@login_required
def serve_private_upload(filepath):
    """Serve files from private_uploads/ — requires login. Prevents direct URL access to PII documents."""
    import os, mimetypes
    from flask import current_app, send_file, abort
    # Prevent path traversal: reject any path containing '..'
    if '..' in filepath or filepath.startswith('/'):
        abort(400)
    base_dir = os.path.join(current_app.root_path, 'private_uploads')
    full_path = os.path.realpath(os.path.join(base_dir, filepath))
    # Ensure resolved path is still inside private_uploads
    if not full_path.startswith(os.path.realpath(base_dir) + os.sep):
        abort(400)
    if not os.path.isfile(full_path):
        abort(404)
    mime, _ = mimetypes.guess_type(full_path)
    return send_file(full_path, mimetype=mime or 'application/octet-stream')


@bp.route('/health')
def health():
    """Health check endpoint for uptime monitors, Cloudflare tunnel, and process managers."""
    from app import APP_VERSION
    db_ok = False
    try:
        db.session.execute(db.text('SELECT 1'))
        db_ok = True
    except Exception:
        pass
    status = 'ok' if db_ok else 'degraded'
    return jsonify({
        'status': status,
        'version': APP_VERSION,
        'db': 'ok' if db_ok else 'error',
    }), 200 if db_ok else 503


@bp.route('/')
def index():
    return redirect(url_for('main.dashboard'))

@bp.route('/api/dashboard/rooms/<int:room_id>/mark-clean', methods=['POST'])
@login_required
def dashboard_mark_clean(room_id):
    """AJAX: mark a single dirty room as clean. Returns JSON."""
    from app.models import Room as RoomModel
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Housekeeping')
    if denied:
        return jsonify({'ok': False, 'error': 'Permission denied'}), 403
    room = RoomModel.query.get_or_404(room_id)
    if room.status != 'Dirty':
        return jsonify({'ok': False, 'error': f'Room {room.room_number} is not Dirty (current: {room.status})'}), 400
    room.status = 'Vacant'
    db.session.commit()
    _write_audit('Room', room.id, 'marked_clean', {'status': 'Dirty'}, {'status': 'Vacant'})
    dirty_count = RoomModel.query.filter_by(status='Dirty').count()
    return jsonify({'ok': True, 'room_number': room.room_number, 'dirty_count': dirty_count})


@bp.route('/api/dashboard/rooms/mark-all-clean', methods=['POST'])
@login_required
def dashboard_mark_all_clean():
    """AJAX: mark all dirty rooms as clean. Returns JSON."""
    from app.models import Room as RoomModel
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Housekeeping')
    if denied:
        return jsonify({'ok': False, 'error': 'Permission denied'}), 403
    dirty_rooms = RoomModel.query.filter_by(status='Dirty').all()
    updated = 0
    errors = []
    for room in dirty_rooms:
        try:
            room.status = 'Vacant'
            _write_audit('Room', room.id, 'marked_clean', {'status': 'Dirty'}, {'status': 'Vacant'})
            updated += 1
        except Exception as exc:
            errors.append(f'Room {room.room_number}: {exc}')
    db.session.commit()
    return jsonify({'ok': True, 'updated': updated, 'errors': errors, 'dirty_count': 0})


@bp.route('/api/dashboard/card-preview/<card_type>')
@login_required
def dashboard_card_preview(card_type):
    """Return a compact HTML snippet for a dashboard card preview modal."""
    from flask import current_app
    from app.services import calculate_stay_amount
    today = get_business_date()

    try:
        if card_type == 'in_house':
            items = (Reservation.query
                     .filter_by(status='CheckedIn')
                     .order_by(Reservation.departure_date)
                     .limit(25).all())
            rows = ''.join(
                f'<tr><td>{r.room.room_number if r.room else "—"}</td>'
                f'<td>{r.guest.name if r.guest else "—"}</td>'
                f'<td>{r.arrival_date.strftime("%d %b")}</td>'
                f'<td>{r.departure_date.strftime("%d %b")}</td>'
                f'<td><span class="badge bg-success">In-House</span></td></tr>'
                for r in items)
            return _card_preview_table(
                ['Room', 'Guest', 'Arrival', 'Departure', 'Status'], rows,
                f'{len(items)} guests currently checked in')

        elif card_type == 'dirty':
            from app.models import Room as RoomModel
            rooms = RoomModel.query.filter_by(status='Dirty').order_by(RoomModel.room_number).all()
            if not rooms:
                return '<div class="p-4 text-center text-muted"><i class="bi bi-check-circle-fill text-success fs-4 d-block mb-2"></i>All rooms are clean!</div>'
            rows_html = ''.join(
                f'<tr data-room-id="{r.id}">'
                f'<td class="fw-semibold">{r.room_number}</td>'
                f'<td>{r.room_type.name if r.room_type else "—"}</td>'
                f'<td><span class="badge bg-warning text-dark">Dirty</span></td>'
                f'<td class="text-end">'
                f'<button class="btn btn-xs btn-success js-mark-clean" data-room-id="{r.id}" data-room-number="{r.room_number}" style="font-size:.72rem;padding:2px 8px;">'
                f'<i class="bi bi-check2"></i> Mark Clean</button></td></tr>'
                for r in rooms)
            ths = ''.join(
                f'<th class="text-uppercase" style="font-size:.7rem;color:#6c757d;font-weight:600;">{h}</th>'
                for h in ['Room', 'Type', 'Status', ''])
            summary = f'<div class="px-3 pt-2 pb-1 d-flex align-items-center justify-content-between flex-wrap gap-2">' \
                      f'<span class="small text-muted">{len(rooms)} rooms need cleaning</span>' \
                      f'<button class="btn btn-sm btn-success js-mark-all-clean" style="font-size:.76rem;">' \
                      f'<i class="bi bi-check2-all me-1"></i>Mark All Rooms Clean</button></div>'
            return (
                summary +
                '<div class="table-responsive">'
                '<table class="table table-sm table-hover mb-0" id="dirtyRoomsTable" style="font-size:.82rem;">'
                f'<thead class="table-light"><tr>{ths}</tr></thead>'
                f'<tbody>{rows_html}</tbody>'
                '</table></div>'
            )

        elif card_type == 'out_of_order':
            from app.models import Room as RoomModel
            rooms = RoomModel.query.filter(RoomModel.status.in_(['Out of Order', 'Maintenance'])).order_by(RoomModel.room_number).all()
            rows = ''.join(
                f'<tr><td>{r.room_number}</td>'
                f'<td>{r.room_type.name if r.room_type else "—"}</td>'
                f'<td><span class="badge bg-danger">{r.status}</span></td></tr>'
                for r in rooms)
            return _card_preview_table(['Room', 'Type', 'Status'], rows,
                                       f'{len(rooms)} rooms out of service')

        elif card_type == 'pending_checkins':
            items = (Reservation.query
                     .filter(Reservation.arrival_date == today,
                             Reservation.status.in_(['Reserved', 'Confirmed']))
                     .order_by(Reservation.created_at)
                     .limit(25).all())
            rows = ''.join(
                f'<tr><td>{r.guest.name if r.guest else "—"}</td>'
                f'<td>{r.room.room_number if r.room else "—"}</td>'
                f'<td>{r.adults}A{" +"+str(r.children)+"C" if r.children else ""}</td>'
                f'<td><span class="badge bg-info text-dark">{r.source or "—"}</span></td></tr>'
                for r in items)
            return _card_preview_table(['Guest', 'Room', 'Guests', 'Source'], rows,
                                       f'{len(items)} guests expected today')

        elif card_type == 'departures':
            items = (Reservation.query
                     .filter(Reservation.departure_date == today,
                             Reservation.status == 'CheckedIn')
                     .order_by(Reservation.room_id)
                     .limit(25).all())
            rows = ''.join(
                f'<tr><td>{r.room.room_number if r.room else "—"}</td>'
                f'<td>{r.guest.name if r.guest else "—"}</td>'
                f'<td>₹{calculate_stay_amount(r)["balance"]:,.0f}</td>'
                f'<td><span class="badge bg-secondary">Departing</span></td></tr>'
                for r in items)
            return _card_preview_table(['Room', 'Guest', 'Balance', 'Status'], rows,
                                       f'{len(items)} guests scheduled to depart today')

        elif card_type == 'pending_checkouts':
            # Overstays only — matches the dashboard "Overstays" card filter
            # (strictly past due). Today's scheduled departures are shown by
            # the separate `departures_today` card / modal.
            items = (Reservation.query
                     .filter(Reservation.status == 'CheckedIn',
                             Reservation.departure_date < today)
                     .order_by(Reservation.departure_date)
                     .limit(25).all())
            rows = ''.join(
                f'<tr><td>{r.room.room_number if r.room else "—"}</td>'
                f'<td>{r.guest.name if r.guest else "—"}</td>'
                f'<td>{r.departure_date.strftime("%d %b")}</td>'
                f'<td class="text-danger fw-semibold">₹{calculate_stay_amount(r)["balance"]:,.0f}</td></tr>'
                for r in items)
            return _card_preview_table(['Room', 'Guest', 'Due Date', 'Balance Due'], rows,
                                       f'{len(items)} overstaying guest(s)')

        elif card_type == 'checked_outs_today':
            # Match the dashboard KPI: reservations checked out within today's
            # UTC window, status='CheckedOut'. Ordered by most recent checkout.
            from app.services import get_business_day_utc_window
            _d0, _d1 = get_business_day_utc_window(date.today())
            items = (Reservation.query
                     .filter(Reservation.checked_out_at >= _d0,
                             Reservation.checked_out_at < _d1,
                             Reservation.status == 'CheckedOut')
                     .order_by(Reservation.checked_out_at.desc())
                     .limit(50).all())
            rows = ''.join(
                f'<tr>'
                f'<td class="fw-semibold">#{r.id}</td>'
                f'<td>{(r.guest.name if r.guest else "—")}</td>'
                f'<td>{(r.room.room_number if r.room else "—")}</td>'
                f'<td>{r.arrival_date.strftime("%d %b")}</td>'
                f'<td>{r.checked_out_at.strftime("%d %b %H:%M") if r.checked_out_at else "—"}</td>'
                f'<td><span class="badge bg-light text-dark border">{r.source or "—"}</span></td>'
                f'<td>{r.invoice_number or "—"}</td>'
                f'</tr>'
                for r in items)
            summary = (f'{len(items)} checkout(s) today' if items
                       else 'No checkouts today')
            return _card_preview_table(
                ['Res #', 'Guest', 'Room', 'Check-in', 'Check-out', 'Source', 'Invoice'],
                rows, summary)

        elif card_type == 'pending_payments':
            items = (Reservation.query
                     .filter(Reservation.status.in_(['CheckedIn', 'Reserved']))
                     .limit(50).all())
            owing = [(r, calculate_stay_amount(r)) for r in items if calculate_stay_amount(r)['balance'] > 0.01]
            owing.sort(key=lambda x: -x[1]['balance'])
            rows = ''.join(
                f'<tr><td>{r.room.room_number if r.room else "—"}</td>'
                f'<td>{r.guest.name if r.guest else "—"}</td>'
                f'<td>₹{b["total"]:,.0f}</td>'
                f'<td>₹{b["paid"]:,.0f}</td>'
                f'<td class="text-danger fw-bold">₹{b["balance"]:,.0f}</td></tr>'
                for r, b in owing[:20])
            total_due = sum(b['balance'] for _, b in owing)
            return _card_preview_table(['Room', 'Guest', 'Total Bill', 'Paid', 'Outstanding'], rows,
                                       f'{len(owing)} guests · Total outstanding ₹{total_due:,.0f}')

        elif card_type == 'not_ready':
            from app.models import Room as RoomModel
            rooms = RoomModel.query.filter(RoomModel.status.in_(['Dirty', 'Out of Order', 'Maintenance'])).order_by(RoomModel.status, RoomModel.room_number).all()
            rows = ''.join(
                f'<tr><td>{r.room_number}</td>'
                f'<td>{r.room_type.name if r.room_type else "—"}</td>'
                f'<td><span class="badge {"bg-warning text-dark" if r.status=="Dirty" else "bg-danger"}">{r.status}</span></td></tr>'
                for r in rooms)
            return _card_preview_table(['Room', 'Type', 'Status'], rows,
                                       f'{len(rooms)} rooms not available')

        elif card_type == 'loyal_guests':
            guests = (Guest.query
                      .join(Reservation, Guest.id == Reservation.guest_id)
                      .group_by(Guest.id)
                      .having(db.func.count(Reservation.id) >= 2)
                      .order_by(db.func.count(Reservation.id).desc())
                      .limit(20).all())
            from sqlalchemy import func as sqlfunc
            counts = {g.id: Reservation.query.filter_by(guest_id=g.id).count() for g in guests}
            rows = ''.join(
                f'<tr><td>{g.name}</td>'
                f'<td>{g.phone}</td>'
                f'<td class="text-center"><span class="badge bg-primary">{counts.get(g.id,0)}</span></td></tr>'
                for g in guests)
            return _card_preview_table(['Guest Name', 'Phone', 'Visits'], rows,
                                       f'{len(guests)} repeat guests')

        elif card_type == 'total_profiles':
            guests = Guest.query.order_by(Guest.created_at.desc()).limit(15).all()
            total = Guest.query.count()
            rows = ''.join(
                f'<tr><td>{g.name}</td>'
                f'<td>{g.phone}</td>'
                f'<td>{g.email or "—"}</td>'
                f'<td>{"✓" if g.id_proof_type else "—"}</td></tr>'
                for g in guests)
            return _card_preview_table(['Name', 'Phone', 'Email', 'ID'], rows,
                                       f'{total} total profiles · showing 15 most recent')

        elif card_type == 'kyc_pending':
            # Check actual KYC completeness, not just id_proof_type
            guests = Guest.query.order_by(Guest.created_at.desc()).limit(100).all()
            pending = [g for g in guests if not g.is_kyc_complete()][:20]
            def _kyc_missing(g):
                missing = []
                if not (g.first_name or '').strip() or not (g.last_name or '').strip():
                    missing.append('Name')
                ph = (g.phone or '').strip().lstrip('+').lstrip('91')
                import re as _re
                if not _re.match(r'^[1-9]\d{9}$', ph):
                    missing.append('Phone')
                if not (g.state or '').strip(): missing.append('State')
                if not (g.city or '').strip(): missing.append('City')
                if not (g.pin_code or '').strip(): missing.append('PIN')
                if not (g.address or '').strip(): missing.append('Address')
                if not (g.id_proof_type or '').strip(): missing.append('ID Type')
                if not (g.id_proof_number or '').strip(): missing.append('ID No.')
                return ', '.join(missing[:3]) + ('...' if len(missing) > 3 else '') if missing else 'Photo/ID Scan'
            rows = ''.join(
                f'<tr><td>{g.display_name}</td>'
                f'<td>{g.phone}</td>'
                f'<td><span class="badge bg-warning text-dark">{_kyc_missing(g)}</span></td></tr>'
                for g in pending)
            return _card_preview_table(['Name', 'Phone', 'Missing'], rows,
                                       f'{len(pending)} guests with incomplete KYC')

        else:
            return '<div class="p-3 text-muted text-center">Preview not available for this card.</div>'

    except Exception as exc:
        current_app.logger.error('card_preview error card_type=%s: %s', card_type, exc, exc_info=True)
        return f'<div class="p-3 text-danger text-center"><i class="bi bi-exclamation-circle me-1"></i>Could not load preview.</div>'


def _card_preview_table(headers, rows, summary=''):
    """Return a compact Bootstrap table HTML string for card preview modals."""
    if not rows:
        return '<div class="p-4 text-center text-muted"><i class="bi bi-inbox fs-4 d-block mb-2"></i>Nothing to show right now.</div>'
    ths = ''.join(f'<th class="text-uppercase" style="font-size:.7rem;color:#6c757d;font-weight:600;">{h}</th>' for h in headers)
    summary_html = f'<div class="px-3 pt-2 pb-1 small text-muted">{summary}</div>' if summary else ''
    return (
        summary_html +
        '<div class="table-responsive">'
        '<table class="table table-sm table-hover mb-0" style="font-size:.82rem;">'
        f'<thead class="table-light"><tr>{ths}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        '</table></div>'
    )


def _build_dashboard_context():
    """Compute ALL dashboard KPI data. Shared by the full-page dashboard route
    and the AJAX ``/api/tab/test-view`` endpoint so numbers are always consistent."""
    business_date = get_business_date()
    from app.kpi_helpers import get_adr, get_revpar, get_daily_revenue
    # Canonical occupancy (KPI Phase 1, Step 3): reservation-driven truth
    # from app.occupancy_engine. Room.status is never consulted for
    # occupancy. occupancy_snapshot() is the single source for the
    # dashboard occupancy cards.
    from app.occupancy_engine import occupancy_snapshot
    _occ = occupancy_snapshot()
    total_rooms = _occ['total']
    sellable_rooms = _occ['sellable']
    occupied = _occ['occupied']
    occupancy_pct = _occ['pct']
    occupancy_anomaly = _occ['anomaly']
    occupancy_orphan_checked_in = _occ['orphan_checked_in']
    # KPI Phase 1, Step 5 — temporary diagnostic telemetry. Appends one
    # canonical occupancy record (counts, room-id set, sellable
    # composition, stale/unflagged drift sets, orphan list) per dashboard
    # load to logs/occupancy_engine_debug.log. Wrapped so a telemetry
    # failure can never break the dashboard. Remove once the Phase 1
    # convergence window has closed and the numbers are trusted.
    try:
        from app.occupancy_engine import log_occupancy_debug
        log_occupancy_debug()
    except Exception:
        logger.debug('occupancy debug telemetry skipped', exc_info=True)
    # Room-status bucket counts in a single pass over the rooms table.
    # Out of Order: rooms flagged unavailable via the dedicated is_out_of_order
    # field (manager toggle in masters) OR status in ('Maintenance','Out of Order').
    # The previous logic counted only status='Maintenance', which missed rooms
    # marked OOO via the boolean flag.
    from sqlalchemy import case as _room_case
    def _rcount(expr):
        return func.count(_room_case((expr, 1)))
    _room_counts = db.session.query(
        _rcount(Room.status == 'Vacant').label('vacant'),
        _rcount(Room.status == 'Dirty').label('dirty'),
        _rcount(db.or_(
            Room.is_out_of_order == True,
            Room.status.in_(['Maintenance', 'Out of Order']),
        )).label('maintenance'),
    ).filter(Room.is_active == True).one()
    vacant      = int(_room_counts.vacant or 0)
    dirty       = int(_room_counts.dirty or 0)
    maintenance = int(_room_counts.maintenance or 0)
    # Available-to-sell rooms = canonical sellable inventory minus rooms
    # currently occupied. Computed here (KPI Phase 1, Step 3.6) so the
    # dashboard template carries NO occupancy arithmetic. Clamped at 0:
    # occupied can exceed sellable in the OOO-with-guest anomaly.
    available_rooms = max(0, sellable_rooms - occupied)

    # Check high demand threshold
    high_demand_threshold = 85
    threshold_setting = Settings.query.filter_by(key='high_demand_threshold').first()
    if threshold_setting:
        high_demand_threshold = int(threshold_setting.value)
    show_high_demand_alert = occupancy_pct >= high_demand_threshold

    # Monthly revenue target (configurable via Settings table)
    _rev_target_row = Settings.query.filter_by(key='monthly_revenue_target').first()
    revenue_target_configured = bool(_rev_target_row and _rev_target_row.value)
    monthly_revenue_target = float(_rev_target_row.value) if revenue_target_configured else 0.0
    # Monthly occupancy target % (configurable via Settings table)
    _occ_target_row = Settings.query.filter_by(key='monthly_occupancy_target').first()
    occupancy_target_configured = bool(_occ_target_row and _occ_target_row.value)
    monthly_occupancy_target = float(_occ_target_row.value) if occupancy_target_configured else 0.0

    # ── N+1 fix: consolidate 8 separate COUNT() queries into one pass over
    # the reservations table. Each bucket below is a CASE WHEN that the DB
    # evaluates once per row — cheaper than 8 round trips, same semantics.
    from sqlalchemy import case
    def _one(expr):
        # Count rows matching `expr`. COUNT(CASE WHEN ... THEN 1 END) — the
        # ELSE branch is implicitly NULL, and COUNT ignores NULLs.
        return func.count(case((expr, 1)))

    _res_counts = db.session.query(
        _one(db.and_(Reservation.arrival_date == business_date,
                     Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn']))).label('arrivals_today'),
        _one(db.and_(Reservation.arrival_date == business_date,
                     Reservation.status.in_(['Reserved', 'Confirmed']))).label('pending_arrivals'),
        _one(db.and_(Reservation.departure_date == business_date,
                     Reservation.status == 'CheckedIn')).label('departures_today'),
        _one(db.and_(Reservation.status == 'CheckedIn',
                     Reservation.departure_date < business_date)).label('pending_departures'),
        _one(db.and_(Reservation.status == 'CheckedIn',
                     Reservation.arrival_date < business_date,
                     Reservation.departure_date > business_date)).label('stayovers'),
        _one(db.and_(Reservation.status == 'CheckedIn',
                     Reservation.arrival_date == business_date)).label('today_checkins'),
        _one(db.and_(Reservation.status == 'CheckedIn',
                     Reservation.booking_type == 'Hourly')).label('hourly_checkins'),
        _one(db.and_(Reservation.booking_type == 'Hourly',
                     Reservation.arrival_date == business_date,
                     Reservation.status.in_(('CheckedIn', 'CheckedOut')))).label('hourly_rooms_today'),
    ).one()
    arrivals_today     = int(_res_counts.arrivals_today or 0)
    pending_arrivals   = int(_res_counts.pending_arrivals or 0)
    departures_today   = int(_res_counts.departures_today or 0)
    # Overstays: checked-in guests whose scheduled departure is strictly in
    # the past. Paired with `departures_today` (scheduled today) so the two
    # dashboard cards are complementary and never double-count.
    pending_departures = int(_res_counts.pending_departures or 0)
    # Stayovers = checked-in guests who arrived before today AND are not departing today.
    stayovers          = int(_res_counts.stayovers or 0)
    # Today check-ins = checked-in guests who arrived today
    today_checkins     = int(_res_counts.today_checkins or 0)
    # Hourly in-house — hourly bookings currently checked-in (any arrival date).
    hourly_checkins    = int(_res_counts.hourly_checkins or 0)
    # Hourly rooms today — hourly bookings that arrived today, in-house or
    # already checked out. Counts the total hourly turnover for the day.
    hourly_rooms_today = int(_res_counts.hourly_rooms_today or 0)

    # Source-wise check-ins today — rooms that arrived today grouped by booking
    # source. Drives the OTA / Walk-in / Calling cards on Row 3.
    _source_counts = dict(db.session.query(
        Reservation.source, func.count(Reservation.id)
    ).filter(
        Reservation.arrival_date == business_date,
        Reservation.status.in_(('CheckedIn', 'CheckedOut'))
    ).group_by(Reservation.source).all())
    ota_rooms_today     = _source_counts.get('OTA', 0)
    walkin_rooms_today  = _source_counts.get('Walk-in', 0)
    calling_rooms_today = _source_counts.get('Calling', 0)

    # Occupancy anomaly check (KPI Phase 1, Step 3). The pre-canonical
    # validator compared a reservation-row SUM (stayovers + checkins +
    # departures + overdue) against `occupied` — but `occupied` is now a
    # canonical DISTINCT-ROOM count. Those are different cardinalities
    # (a multi-room reservation, or any overstay, makes them diverge),
    # so the old comparison warned permanently and meaninglessly.
    # The meaningful anomaly is the engine's own flag: occupied >
    # sellable, which is physically impossible and indicates an occupied
    # room was flagged OOO/Maintenance with a guest still in it.
    kpi_mismatch = occupancy_anomaly
    if kpi_mismatch:
        import logging
        logging.getLogger(__name__).warning(
            'Occupancy anomaly: occupied=%d exceeds sellable=%d '
            '(an occupied room appears flagged OOO/Maintenance).',
            occupied, sellable_rooms,
        )

    today_revenue = get_daily_revenue(business_date)
    yesterday_revenue = get_daily_revenue(business_date - timedelta(days=1))

    # OTA receivable postings today and month-to-date (NOT cash — money owed by OTA)
    from app.kpi_helpers import get_ota_receivable_posted, get_ota_receivable_mtd
    ota_receivable_today = get_ota_receivable_posted(business_date)
    ota_receivable_mtd = get_ota_receivable_mtd(business_date)

    # v2.2.11: removed combined ``total_revenue_today = today_revenue +
    # ota_receivable_today`` aggregate. That hybrid double-counted OTA
    # receivable across the MTD Revenue tile and the OTA Receivable tiles.
    # The dashboard now exposes the two components separately via:
    #   cash_collected_today  = today_revenue          (direct payment cash)
    #   ota_posted_today      = ota_receivable_today   (OTA receivable, not cash)
    # See CHANGELOG v2.2.11 for the rationale.

    # OTA outstanding (lifetime gross receivable) — still used for header badge
    # and the warning threshold comparison below.
    try:
        from app.ota_settlement_service import compute_ota_outstanding
        _ota_raw = compute_ota_outstanding()
        ota_outstanding_total = float(_ota_raw.get('total_amount', 0) if isinstance(_ota_raw, dict) else 0)
    except Exception:
        ota_outstanding_total = 0.0

    # Configurable OTA warning threshold (default 50000)
    _ota_warn_row = Settings.query.filter_by(key='ota_outstanding_warning_threshold').first()
    ota_warning_threshold = float(_ota_warn_row.value) if _ota_warn_row and _ota_warn_row.value else 50000.0

    # Payment-mode-wise + source-wise + monthly revenue.
    # v2.2.11: all four aggregations now route through canonical helpers in
    # ``app.kpi_helpers``. All filter to ``PaymentMode.category='direct_payment'``
    # so the dashboard's cash-basis tiles reconcile correctly (daily ≈ sum of
    # daily payments, MTD ≈ running sum of daily values). OTA receivable
    # postings stay separately surfaced via get_ota_receivable_* helpers.
    from app.kpi_helpers import (
        get_payment_by_mode, get_revenue_by_source,
        get_monthly_revenue, get_previous_month_revenue,
    )
    revenue_by_mode = get_payment_by_mode(business_date)
    upi_revenue = revenue_by_mode.get('UPI', 0)
    card_revenue = revenue_by_mode.get('Card', 0) + revenue_by_mode.get('Credit Card', 0) + revenue_by_mode.get('Debit Card', 0)
    cash_only_revenue = revenue_by_mode.get('Cash', 0)

    revenue_by_source = get_revenue_by_source(business_date)
    ota_revenue = revenue_by_source.get('OTA', 0)
    calling_revenue = revenue_by_source.get('Calling', 0)

    month_start = business_date.replace(day=1)
    mtd_revenue = get_monthly_revenue(month_start, business_date)
    last_month_revenue = get_previous_month_revenue(business_date)

    total_folios = Guest.query.count()
    # KYC complete = has first_name, last_name, phone valid, state, city, pin, address, ID type+number
    complete_folios = Guest.query.filter(
        Guest.first_name.isnot(None), Guest.first_name != '',
        Guest.last_name.isnot(None), Guest.last_name != '',
        Guest.state.isnot(None), Guest.state != '',
        Guest.city.isnot(None), Guest.city != '',
        Guest.pin_code.isnot(None), Guest.pin_code != '',
        Guest.address.isnot(None), Guest.address != '',
        Guest.id_proof_type.isnot(None), Guest.id_proof_type != '',
        Guest.id_proof_number.isnot(None), Guest.id_proof_number != '',
    ).count()
    incomplete_folios = total_folios - complete_folios
    loyal_customers = Guest.query.join(Reservation).group_by(Guest.id).having(func.count(Reservation.id) > 1).count()

    # Standardized KPIs from kpi_helpers (rate-based ADR, ARR*occ for RevPAR)
    arr = get_adr()
    revpar = get_revpar(adr=arr, occ_pct=occupancy_pct)

    # GOPAR (proxy) = (today_revenue * (1 - operating_cost_ratio)) / available_rooms
    # True GOPAR requires full operating-cost data (payroll, utilities, F&B
    # cost, etc.) which the PMS does not yet track. Until a full P&L pipeline
    # exists, we surface a configurable proxy: assume a flat operating-cost
    # ratio (default 35%) and derive GOP from today's gross revenue.
    # Set via Settings.operating_cost_ratio (0.0 - 1.0). available_rooms
    # excludes OOO rooms so GOPAR reflects sellable-room productivity.
    _cost_row = Settings.query.filter_by(key='operating_cost_ratio').first()
    try:
        _cost_ratio = float(_cost_row.value) if _cost_row and _cost_row.value else 0.35
    except (TypeError, ValueError):
        _cost_ratio = 0.35
    _cost_ratio = max(0.0, min(1.0, _cost_ratio))
    _available_rooms = max(0, total_rooms - maintenance)
    if _available_rooms > 0:
        goppar = round(float(today_revenue) * (1.0 - _cost_ratio) / _available_rooms, 2)
    else:
        goppar = 0.0
    goppar_is_proxy = True  # flag for template to label clearly

    # Use real calendar date for activity KPIs — not business_date, which can
    # lag when a night audit is pending/reopened.
    # checked_in_at / checked_out_at / created_at are stored as UTC. Use the
    # shared helper to get the matching UTC window for local "today".
    from app.services import get_business_day_utc_window
    _today = date.today()
    _utc_day_start, _utc_day_end = get_business_day_utc_window(_today)

    checked_in_today = Reservation.query.filter(
        Reservation.checked_in_at >= _utc_day_start,
        Reservation.checked_in_at < _utc_day_end,
    ).count()

    # Booking source breakdown — scoped to reservations ACTUALLY checked in
    # today (checked_in_at within today's UTC window), not by arrival_date
    # (which excludes late/early check-ins and includes no-shows).
    ota_bookings = Reservation.query.filter(
        Reservation.checked_in_at >= _utc_day_start,
        Reservation.checked_in_at < _utc_day_end,
        Reservation.source == 'OTA',
    ).count()
    walkin_bookings = Reservation.query.filter(
        Reservation.checked_in_at >= _utc_day_start,
        Reservation.checked_in_at < _utc_day_end,
        Reservation.source == 'Walk-in',
    ).count()
    calling_bookings = Reservation.query.filter(
        Reservation.checked_in_at >= _utc_day_start,
        Reservation.checked_in_at < _utc_day_end,
        Reservation.source == 'Calling',
    ).count()
    # Mismatch sentinel: sum of the 3 sources should equal total checked-in-today
    # (if other sources like Website/Agent are used, this will surface).
    source_mismatch = (ota_bookings + walkin_bookings + calling_bookings) != checked_in_today

    # ALOS = avg(nights) over stays COMPLETED in the last 30 days. Completed
    # stays give an honest picture (scheduled dates of in-house guests can
    # change). Falls back to 0.0 when no data.
    _alos_from = business_date - timedelta(days=30)
    # Use julianday() for SQLite compatibility; PostgreSQL also supports it via
    # extract(epoch ...) but julianday works on both when dates are stored as
    # ISO strings (SQLite) or native DATE (PG via SQLAlchemy type coercion).
    alos_data = db.session.query(
        func.avg(func.julianday(Reservation.departure_date) - func.julianday(Reservation.arrival_date))
    ).filter(
        Reservation.status == 'CheckedOut',
        Reservation.departure_date >= _alos_from,
        Reservation.departure_date <= business_date,
    ).scalar()
    alos = round(float(alos_data), 1) if alos_data else 0.0

    checked_out_today = Reservation.query.filter(
        Reservation.checked_out_at >= _utc_day_start,
        Reservation.checked_out_at < _utc_day_end,
        Reservation.status == 'CheckedOut'
    ).count()

    walk_in_today = Reservation.query.filter(
        Reservation.created_at >= _utc_day_start,
        Reservation.created_at < _utc_day_end,
        Reservation.arrival_date == business_date,
        Reservation.source == 'Walk-in',
    ).count()
    
    pending_checkouts = Reservation.query.filter(
        Reservation.status == 'CheckedIn',
        Reservation.departure_date < business_date
    ).all()
    
    vacant_clean = vacant
    vacant_dirty = 0
    occupy_clean = occupied
    occupy_dirty = 0

    # Target vs Actual
    rev_achievement_pct = round(float(mtd_revenue) / monthly_revenue_target * 100, 1) if monthly_revenue_target > 0 else 0.0
    occ_achievement_pct = round(float(occupancy_pct) / monthly_occupancy_target * 100, 1) if monthly_occupancy_target > 0 else 0.0

    # Pending payments + discount impact (single loop over in-house reservations)
    from sqlalchemy.orm import subqueryload as _sq, joinedload as _jl
    _inhouse = (Reservation.query.filter_by(status='CheckedIn')
                .options(_sq(Reservation.payments), _sq(Reservation.extra_charges),
                         _jl(Reservation.room_type))
                .all())
    pending_payments     = 0.0
    leakage_amount       = 0.0
    leakage_rooms        = 0
    upsell_amount        = 0.0
    upsell_rooms         = 0
    post_discount_amount = 0.0
    post_discount_rooms  = 0
    for _r in _inhouse:
        _bal = calculate_stay_amount(_r)['balance']
        if _bal > 0.01:
            pending_payments += _bal
        # Tariff adjustment — use stored DB fields when available; fall back to dynamic
        _adj_type = getattr(_r, 'adjustment_type', None)
        _adj_amt  = float(getattr(_r, 'adjustment_amount', None) or 0)
        if _adj_type == 'LEAKAGE' and _adj_amt > 0:
            leakage_amount += _adj_amt
            leakage_rooms  += 1
        elif _adj_type == 'UPSELL' and _adj_amt > 0:
            upsell_amount += _adj_amt
            upsell_rooms  += 1
        elif getattr(_r, 'standard_tariff', None) is None and _r.room_type:
            # Fallback for records created before this feature
            _base   = float(_r.room_type.base_rate or 0)
            _actual = float(_r.rate_per_night or 0)
            if _base > 0.0 and _actual < _base:
                leakage_amount += (_base - _actual)
                leakage_rooms  += 1
            elif _base > 0.0 and _actual > _base:
                upsell_amount  += (_actual - _base)
                upsell_rooms   += 1
        # Actual post-billing discounts
        _disc = float(getattr(_r, 'discount_amount', None) or 0)
        if _disc > 0:
            post_discount_amount += _disc
            post_discount_rooms  += 1
    pending_payments     = round(pending_payments, 2)
    leakage_amount       = round(leakage_amount, 2)
    upsell_amount        = round(upsell_amount, 2)
    post_discount_amount = round(post_discount_amount, 2)
    # Keep discount_amount/discount_rooms for backward-compat with ri_rules
    discount_amount = leakage_amount
    discount_rooms  = leakage_rooms
    # % of today's revenue for dashboard display
    _rev_base = float(today_revenue) if float(today_revenue) > 0 else 1.0
    leakage_pct       = round(leakage_amount       / _rev_base * 100, 1)
    upsell_pct        = round(upsell_amount        / _rev_base * 100, 1)
    post_discount_pct = round(post_discount_amount / _rev_base * 100, 1)

    # ── User-wise revenue control (Admin/Manager table) ────────────────────
    _user_rev: dict = {}

    def _dash_user_row(uname: str) -> dict:
        if uname not in _user_rev:
            _user_rev[uname] = {
                'username': uname, 'checkin_rooms': 0,
                'leakage': 0.0, 'leakage_rooms': 0,
                'upsell': 0.0,  'upsell_rooms': 0,
                'discount': 0.0, 'discount_rooms': 0,
            }
        return _user_rev[uname]

    for _r in _inhouse:
        # Resolve check-in user — prefer stored checkin_by, fallback to CheckInRecord
        _ci_by = getattr(_r, 'checkin_by', None)
        if not _ci_by:
            if _r.checkin_record and _r.checkin_record.staff_user_id:
                _ci_u = db.session.get(User, _r.checkin_record.staff_user_id)
                _ci_by = _ci_u.username if _ci_u else f'#{_r.checkin_record.staff_user_id}'
        _ci_by = (_ci_by or '—').strip() or '—'

        # Tariff adjustment (same fallback as the primary loop above)
        _radj_type = getattr(_r, 'adjustment_type', None)
        _radj_amt  = float(getattr(_r, 'adjustment_amount', None) or 0)
        if _radj_type is None and getattr(_r, 'standard_tariff', None) is None and _r.room_type:
            _rbase   = float(_r.room_type.base_rate or 0)
            _ractual = float(_r.rate_per_night or 0)
            if _rbase > 0 and _ractual < _rbase:
                _radj_type = 'LEAKAGE'; _radj_amt = _rbase - _ractual
            elif _rbase > 0 and _ractual > _rbase:
                _radj_type = 'UPSELL';  _radj_amt = _ractual - _rbase

        _ru = _dash_user_row(_ci_by)
        _ru['checkin_rooms'] += 1
        if _radj_type == 'LEAKAGE' and _radj_amt > 0:
            _ru['leakage']       += _radj_amt
            _ru['leakage_rooms'] += 1
        elif _radj_type == 'UPSELL' and _radj_amt > 0:
            _ru['upsell']       += _radj_amt
            _ru['upsell_rooms'] += 1

        # Discount attributed to discount_given_by (may differ from checkin_by)
        _rdisc = float(getattr(_r, 'discount_amount', None) or 0)
        if _rdisc > 0:
            _disc_by = (getattr(_r, 'discount_given_by', None) or _ci_by or '—').strip() or '—'
            _du = _dash_user_row(_disc_by)
            _du['discount']       += _rdisc
            _du['discount_rooms'] += 1

    # Finalise and sort — worst net_impact first
    for _u in _user_rev.values():
        _u['leakage']    = round(_u['leakage'],  2)
        _u['upsell']     = round(_u['upsell'],   2)
        _u['discount']   = round(_u['discount'], 2)
        _u['net_impact'] = round(_u['upsell'] - _u['leakage'] - _u['discount'], 2)
        _u['highest_leakage'] = False
        _u['highest_upsell']  = False

    user_rev_table = sorted(_user_rev.values(), key=lambda x: x['net_impact'])

    if user_rev_table:
        _hl = max(user_rev_table, key=lambda x: x['leakage'])
        _hu = max(user_rev_table, key=lambda x: x['upsell'])
        if _hl['leakage'] > 0:
            _hl['highest_leakage'] = True
        if _hu['upsell'] > 0:
            _hu['highest_upsell'] = True

    # ── Revenue trend vs yesterday ─────────────────────────────────────────
    _today_rev_f = float(today_revenue)
    _yest_rev_f  = float(yesterday_revenue)
    revenue_change_pct = round(
        (_today_rev_f - _yest_rev_f) / _yest_rev_f * 100, 1
    ) if _yest_rev_f > 0 else 0.0

    # ── Yesterday occupancy (approximate) for occupancy trend ─────────────
    _yesterday = business_date - timedelta(days=1)
    _yesterday_occ = Reservation.query.filter(
        Reservation.status.in_(['CheckedIn', 'CheckedOut']),
        Reservation.arrival_date <= _yesterday,
        Reservation.departure_date > _yesterday
    ).count()
    yesterday_occ_pct = round(_yesterday_occ / sellable_rooms * 100, 1) if sellable_rooms > 0 else 0.0
    occ_change_pts = round(float(occupancy_pct) - yesterday_occ_pct, 1)

    # ── 7-day occupancy forecast ───────────────────────────────────────────
    forecast_days = []
    for _i in range(1, 8):
        _fd = business_date + timedelta(days=_i)
        _fc = Reservation.query.filter(
            Reservation.arrival_date <= _fd,
            Reservation.departure_date > _fd,
            Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn'])
        ).count()
        forecast_days.append({
            'label': _fd.strftime('%a'),
            'date':  _fd.strftime('%d %b'),
            'pct':   int(round(_fc / sellable_rooms * 100)) if sellable_rooms > 0 else 0,
            'count': _fc,
        })

    # ── Balance-due guest count (reuses _inhouse) ─────────────────────────
    balance_due_count = sum(1 for r in _inhouse if calculate_stay_amount(r)['balance'] > 0.01)
    overdue_count = len(pending_checkouts)

    # ── Smart suggestions ─────────────────────────────────────────────────
    suggestions = []
    if overdue_count > 0:
        suggestions.append({'type': 'danger', 'icon': 'bi-clock-history',
            'text': f'{overdue_count} overdue checkout{"s" if overdue_count > 1 else ""} — rooms are blocking availability.'})
    if dirty > 0 and pending_arrivals > 0:
        suggestions.append({'type': 'warning', 'icon': 'bi-brush',
            'text': f'{dirty} dirty room{"s" if dirty > 1 else ""} with {pending_arrivals} pending arrival{"s" if pending_arrivals > 1 else ""} — assign housekeeping now.'})
    if balance_due_count > 0:
        suggestions.append({'type': 'danger', 'icon': 'bi-currency-rupee',
            'text': f'\u20b9{pending_payments:,.0f} outstanding from {balance_due_count} in-house guest{"s" if balance_due_count > 1 else ""} — collect before checkout.'})
    if revenue_target_configured and rev_achievement_pct < 70 and business_date.day > 7:
        suggestions.append({'type': 'info', 'icon': 'bi-graph-up-arrow',
            'text': f'MTD revenue at {rev_achievement_pct}% of target — consider promotional rates or OTA visibility boost.'})
    if forecast_days and max(f['pct'] for f in forecast_days) >= 90:
        _peak_day = next(f for f in forecast_days if f['pct'] >= 90)
        suggestions.append({'type': 'info', 'icon': 'bi-calendar-check',
            'text': f'High occupancy forecast on {_peak_day["date"]} ({_peak_day["pct"]}%) — ensure rooms and pricing are ready.'})
    if not suggestions:
        suggestions.append({'type': 'success', 'icon': 'bi-check-circle',
            'text': 'No critical actions needed. Operations look healthy.'})

    # ══════════════════════════════════════════════════════════════════════
    # REVENUE INTELLIGENCE ENGINE
    # ══════════════════════════════════════════════════════════════════════

    # ── Demand signal: occupancy vs target ────────────────────────────────
    _occ_f = float(occupancy_pct)
    _occ_target_f = float(monthly_occupancy_target)
    if not occupancy_target_configured:
        demand_signal = 'no_target'; demand_color = 'secondary'; demand_label = 'No Target Set'
    elif _occ_f >= _occ_target_f:
        demand_signal = 'high';  demand_color = 'success'; demand_label = 'High Demand'
    elif _occ_f >= _occ_target_f * 0.70:
        demand_signal = 'medium'; demand_color = 'warning'; demand_label = 'Moderate Demand'
    else:
        demand_signal = 'low';   demand_color = 'danger';  demand_label = 'Low Demand'
    demand_gap_pts = round(_occ_f - _occ_target_f, 1) if occupancy_target_configured else 0.0

    # ── Pricing signal: ARR vs recommended rate ───────────────────────────
    _arr_f = float(arr)
    if _arr_f > 0:
        if _occ_f >= 85:
            recommended_rate = round(_arr_f * 1.20);  pricing_signal = 'raise'
            pricing_label = 'Raise Price';  pricing_color = 'success';  pricing_pct_diff = 20
        elif _occ_f >= 70:
            recommended_rate = round(_arr_f * 1.10);  pricing_signal = 'nudge_up'
            pricing_label = 'Slight Increase'; pricing_color = 'info'; pricing_pct_diff = 10
        elif _occ_f >= 50:
            recommended_rate = round(_arr_f);         pricing_signal = 'hold'
            pricing_label = 'Hold Rate';  pricing_color = 'secondary'; pricing_pct_diff = 0
        else:
            recommended_rate = round(_arr_f * 0.85);  pricing_signal = 'discount'
            pricing_label = 'Offer Discount'; pricing_color = 'warning'; pricing_pct_diff = -15
    else:
        recommended_rate = 0.0; pricing_signal = 'no_data'
        pricing_label = 'No Check-ins'; pricing_color = 'secondary'; pricing_pct_diff = 0

    # ── Inventory signal: available rooms ─────────────────────────────────
    _avail = total_rooms - occupied - maintenance
    _inv_pct = round(_avail / total_rooms * 100) if total_rooms > 0 else 0
    if _inv_pct <= 10:
        inventory_signal = 'critical'; inventory_color = 'danger';  inventory_label = 'Critical'
    elif _inv_pct <= 25:
        inventory_signal = 'tight';    inventory_color = 'warning'; inventory_label = 'Tight'
    elif _inv_pct <= 50:
        inventory_signal = 'moderate'; inventory_color = 'info';    inventory_label = 'Moderate'
    else:
        inventory_signal = 'open';     inventory_color = 'success'; inventory_label = 'Open'
    ri_avail_rooms   = _avail
    ri_avail_pct     = _inv_pct

    # ── Source percentages ────────────────────────────────────────────────
    _ci_d      = today_checkins if today_checkins > 0 else 1
    ota_pct    = round(ota_bookings    / _ci_d * 100) if today_checkins > 0 else 0
    walkin_pct = round(walkin_bookings / _ci_d * 100) if today_checkins > 0 else 0
    calling_pct= round(calling_bookings/ _ci_d * 100) if today_checkins > 0 else 0

    # ── Waived amount today (from AuditLog) ───────────────────────────────
    _waiver_rows = (AuditLog.query
                    .filter(AuditLog.entity_type == 'Reservation',
                            AuditLog.action == 'overstay_waived',
                            func.date(AuditLog.timestamp) == business_date)
                    .with_entities(AuditLog.after_state)
                    .all())
    waived_today_dash = round(
        sum(float((row[0] or {}).get('waived_amount', 0)) for row in _waiver_rows), 2
    )

    # ── Forecast (tonight = current; tomorrow from 7-day list) ────────────
    tonight_pct   = int(_occ_f)
    _tmrw         = forecast_days[0] if forecast_days else {'pct': 0, 'count': 0, 'label': '—', 'date': '—'}
    tomorrow_pct  = _tmrw['pct']
    tomorrow_date = _tmrw.get('date', '—')
    if tomorrow_pct >= 85:
        tomorrow_risk = 'High Risk';   tomorrow_risk_color = 'danger'
    elif tomorrow_pct >= 60:
        tomorrow_risk = 'Moderate';    tomorrow_risk_color = 'warning'
    else:
        tomorrow_risk = 'Low Risk';    tomorrow_risk_color = 'success'
    _fc_peak     = max(forecast_days, key=lambda x: x['pct']) if forecast_days else {'pct': 0, 'date': '—', 'label': '—'}
    fc_peak_pct  = _fc_peak['pct']
    fc_peak_date = _fc_peak.get('date', '—')

    # ── Rule-based revenue actions (4 rules, priority-ordered) ────────────
    ri_rules = []
    # Rule 1: Low occupancy → discount + OTA push
    if _occ_f < 60:
        ri_rules.append({
            'priority': 1, 'type': 'warning', 'signal': 'Demand',
            'icon': 'bi-arrow-down-circle-fill',
            'rule': 'Low Occupancy — Drive Demand',
            'action': ((f'Apply a 10–15% promotional rate (suggested: ₹{recommended_rate:,.0f}) '
                        f'and boost OTA channel visibility immediately.')
                       if recommended_rate > 0 else
                       'Apply a 10–15% promotional rate and boost OTA channel visibility immediately.'),
            'metric': (f'{occupancy_pct}% occupied vs {monthly_occupancy_target:.0f}% target'
                       if occupancy_target_configured else f'{occupancy_pct}% occupied')
        })
    # Rule 2: High occupancy → raise prices
    if _occ_f >= 85:
        ri_rules.append({
            'priority': 1, 'type': 'success', 'signal': 'Pricing',
            'icon': 'bi-arrow-up-circle-fill',
            'rule': 'High Demand — Maximise Revenue',
            'action': (f'Increase rate to ₹{recommended_rate:,.0f} '
                       f'({pricing_pct_diff}% above current ARR of ₹{_arr_f:,.0f}). '
                       f'Consider walk-in premium pricing.'),
            'metric': f'{occupancy_pct}% occupancy — demand justifies premium'
        })
    # Rule 3: High pending payments → follow up
    if pending_payments > 5000:
        ri_rules.append({
            'priority': 2, 'type': 'danger', 'signal': 'Leakage',
            'icon': 'bi-exclamation-circle-fill',
            'rule': 'Pending Payments — Collect Before Checkout',
            'action': (f'Follow up with {balance_due_count} in-house guest'
                       f'{"s" if balance_due_count > 1 else ""} for '
                       f'₹{pending_payments:,.0f} outstanding.'),
            'metric': f'₹{pending_payments:,.0f} at risk'
        })
    # Rule 4: High dirty rooms → housekeeping action
    _dirty_pct_ri = round(dirty / total_rooms * 100) if total_rooms > 0 else 0
    if _dirty_pct_ri >= 20 or (dirty > 0 and pending_arrivals > 0):
        ri_rules.append({
            'priority': 2, 'type': 'warning', 'signal': 'Inventory',
            'icon': 'bi-brush-fill',
            'rule': 'Housekeeping Backlog — Room Readiness Risk',
            'action': (f'Assign housekeeping to {dirty} dirty room'
                       f'{"s" if dirty > 1 else ""} now. '
                       f'{pending_arrivals} arrival{"s" if pending_arrivals > 1 else ""} pending.'),
            'metric': f'{dirty} rooms blocked, {_dirty_pct_ri}% of inventory unavailable'
        })
    # Bonus: discounted tariffs active
    if discount_rooms > 0:
        ri_rules.append({
            'priority': 3, 'type': 'info', 'signal': 'Pricing',
            'icon': 'bi-tag-fill',
            'rule': 'Below-Rack Tariffs Active',
            'action': (f'{discount_rooms} room{"s" if discount_rooms > 1 else ""} booked below '
                       f'base rate. Review authorisation and tariff compliance.'),
            'metric': f'₹{discount_amount:,.0f} total rate leakage vs rack rate'
        })
    ri_rules.sort(key=lambda x: x['priority'])

    # ── Duplicate active check-ins per room ───────────────────────────────
    # Finds rooms that have more than one CheckedIn reservation (data integrity issue)
    _dup_subq = (db.session.query(Reservation.room_id)
                 .filter(Reservation.status == 'CheckedIn',
                         Reservation.room_id.isnot(None))
                 .group_by(Reservation.room_id)
                 .having(func.count(Reservation.id) > 1)
                 .subquery())
    duplicate_checkin_rooms = (db.session.query(Reservation.room_id)
                               .filter(Reservation.room_id.in_(db.select(_dup_subq)))
                               .distinct()
                               .count())
    if duplicate_checkin_rooms > 0:
        suggestions.insert(0, {
            'type': 'danger',
            'icon': 'bi-exclamation-octagon-fill',
            'text': (
                f'{duplicate_checkin_rooms} room'
                f'{"s have" if duplicate_checkin_rooms > 1 else " has"} '
                f'multiple active check-ins — this is a data integrity issue. '
                f'<a href="/admin/duplicate-checkins" class="alert-link">Fix now</a>.'
            ),
        })

    # Live alert counts for dashboard badge
    try:
        from app.alert_service import AlertService
        alert_counts = AlertService.get_alert_counts()
    except Exception:
        alert_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'total': 0}

    return {
        'alert_counts': alert_counts,
        'business_date': business_date,
        'total_rooms': total_rooms,
        'sellable_rooms': sellable_rooms,
        'occupied': occupied,
        'available_rooms': available_rooms,
        'vacant': vacant,
        'dirty': dirty,
        'maintenance': maintenance,
        'occupancy_pct': occupancy_pct,
        'occupancy_anomaly': occupancy_anomaly,
        'occupancy_orphan_checked_in': occupancy_orphan_checked_in,
        'arrivals_today': arrivals_today,
        'pending_arrivals': pending_arrivals,
        'departures_today': departures_today,
        'pending_departures': pending_departures,
        'stayovers': stayovers,
        'today_checkins': today_checkins,
        'hourly_checkins': hourly_checkins,
        'hourly_rooms_today': hourly_rooms_today,
        'ota_rooms_today': ota_rooms_today,
        'walkin_rooms_today': walkin_rooms_today,
        'calling_rooms_today': calling_rooms_today,
        'today_revenue': today_revenue,
        # v2.2.11 semantic split: total_revenue_today removed (hybrid that
        # double-counted OTA receivable). Two explicit components below.
        'cash_collected_today': today_revenue,
        'ota_posted_today': ota_receivable_today,
        'ota_receivable_today': ota_receivable_today,
        'ota_receivable_mtd': ota_receivable_mtd,
        'ota_outstanding_total': ota_outstanding_total,
        'ota_warning_threshold': ota_warning_threshold,
        'upi_revenue': upi_revenue,
        'card_revenue': card_revenue,
        'cash_only_revenue': cash_only_revenue,
        'ota_revenue': ota_revenue,
        'calling_revenue': calling_revenue,
        'yesterday_revenue': yesterday_revenue,
        'mtd_revenue': mtd_revenue,
        'last_month_revenue': last_month_revenue,
        'total_folios': total_folios,
        'complete_folios': complete_folios,
        'incomplete_folios': incomplete_folios,
        'loyal_customers': loyal_customers,
        'arr': arr,
        'revpar': revpar,
        'ota_bookings': ota_bookings,
        'walkin_bookings': walkin_bookings,
        'calling_bookings': calling_bookings,
        'source_mismatch': source_mismatch,
        'kpi_mismatch': kpi_mismatch,
        'pending_payments': pending_payments,
        'monthly_revenue_target': monthly_revenue_target,
        'rev_achievement_pct': rev_achievement_pct,
        'monthly_occupancy_target': monthly_occupancy_target,
        'occ_achievement_pct': occ_achievement_pct,
        'alos': alos,
        'goppar': goppar,
        'goppar_is_proxy': goppar_is_proxy,
        'checked_in_today': checked_in_today,
        'checked_out_today': checked_out_today,
        'walk_in_today': walk_in_today,
        'pending_checkouts': pending_checkouts,
        'vacant_clean': vacant_clean,
        'vacant_dirty': vacant_dirty,
        'occupy_clean': occupy_clean,
        'occupy_dirty': occupy_dirty,
        'show_high_demand_alert': show_high_demand_alert,
        'high_demand_threshold': high_demand_threshold,
        'revenue_change_pct': revenue_change_pct,
        'yesterday_occ_pct': yesterday_occ_pct,
        'occ_change_pts': occ_change_pts,
        'forecast_days': forecast_days,
        'balance_due_count': balance_due_count,
        'overdue_count': overdue_count,
        'suggestions': suggestions,
        'demand_signal': demand_signal,
        'demand_color': demand_color,
        'demand_label': demand_label,
        'demand_gap_pts': demand_gap_pts,
        'pricing_signal': pricing_signal,
        'pricing_label': pricing_label,
        'pricing_color': pricing_color,
        'pricing_pct_diff': pricing_pct_diff,
        'recommended_rate': recommended_rate,
        'inventory_signal': inventory_signal,
        'inventory_color': inventory_color,
        'inventory_label': inventory_label,
        'ri_avail_rooms': ri_avail_rooms,
        'ri_avail_pct': ri_avail_pct,
        'ota_pct': ota_pct,
        'walkin_pct': walkin_pct,
        'calling_pct': calling_pct,
        'discount_amount': discount_amount,
        'discount_rooms': discount_rooms,
        'leakage_amount': leakage_amount,
        'leakage_rooms': leakage_rooms,
        'leakage_pct': leakage_pct,
        'upsell_amount': upsell_amount,
        'upsell_rooms': upsell_rooms,
        'upsell_pct': upsell_pct,
        'post_discount_amount': post_discount_amount,
        'post_discount_rooms': post_discount_rooms,
        'post_discount_pct': post_discount_pct,
        'user_rev_table': user_rev_table,
        'waived_today_dash': waived_today_dash,
        'tonight_pct': tonight_pct,
        'tomorrow_pct': tomorrow_pct,
        'tomorrow_date': tomorrow_date,
        'tomorrow_risk': tomorrow_risk,
        'tomorrow_risk_color': tomorrow_risk_color,
        'fc_peak_pct': fc_peak_pct,
        'fc_peak_date': fc_peak_date,
        'ri_rules': ri_rules,
        'revenue_target_configured': revenue_target_configured,
        'occupancy_target_configured': occupancy_target_configured,
        'duplicate_checkin_rooms': duplicate_checkin_rooms,
        # ── Date-scope clarity (Apr 2026) ──────────────────────────────
        # Every KPI tile picks one of three scopes and the template tags
        # it accordingly. See resolve_dashboard_scopes() docstring for the
        # exact semantics. `settled_*` fields are pulled from the most
        # recent NightAuditLog snapshot — they are immutable ledger truth
        # and are what the brief calls "default to LAST CLOSED AUDIT".
        # `live_*` fields are the existing realtime values, kept for the
        # secondary "(Live)" tiles.
        **_build_scope_payload(business_date, today_revenue, occupancy_pct, arr, revpar),
    }


def _build_scope_payload(business_date, _ignored_payment_revenue,
                         live_occ_pct, live_arr, live_revpar):
    """Bundle the three date scopes + parallel settled / live KPI values.

    REVENUE SOURCING RULE (Apr 2026 — non-negotiable):

      * Settled headline    →  NightAuditLog snapshot (audit close = truth)
      * Live secondary      →  charges (rate × nights + extras),
                               NOT payments
      * Payments            →  settlement only — never displayed as revenue

    The third positional arg used to be `live_today_revenue` derived from
    summing the Payment table. That was wrong: payments are settlement
    (₹1 test payments shouldn't move the revenue tile). It's now ignored
    — kept as a positional arg only to avoid touching every caller — and
    we recompute the live revenue from charges via
    ``compute_live_today_charges``.
    """
    from app.services import (resolve_dashboard_scopes, compute_live_today_charges,
                              build_daily_financial_summary)
    scopes = resolve_dashboard_scopes()
    last_log = scopes['last_closed_log']

    # ── Daily Financial Summary (owner panel) ─────────────────────────
    # Single rollup: earned vs collected vs liability vs receivable.
    # Defensive: never let a query failure break the dashboard.
    try:
        daily_financial_summary = build_daily_financial_summary(business_date)
    except Exception:
        logger.exception('build_daily_financial_summary failed')
        daily_financial_summary = None

    # ── Individual Credit Outstanding (current open credit balance) ───
    # Sum the LIVE outstanding balance for reservations that were checked
    # out on individual credit. Using calculate_stay_amount means a later
    # payment correctly drops the tile total, while credit_amount stays
    # as the original snapshot for historical / aging records.
    credit_outstanding_total = 0.0
    credit_outstanding_count = 0
    try:
        from app.services import calculate_stay_amount as _calc
        _credit_res = (Reservation.query
                       .filter(Reservation.credit_amount > 0)
                       .all())
        for _r in _credit_res:
            try:
                _bal = float(_calc(_r).get('balance', 0) or 0)
            except Exception:
                _bal = float(_r.credit_amount or 0)
            if _bal > 0.01:
                credit_outstanding_total += _bal
                credit_outstanding_count += 1
    except Exception:
        credit_outstanding_total = 0.0
        credit_outstanding_count = 0

    # ── Settled KPIs from the closed NightAuditLog snapshot ───────────
    # Every settled field below comes from a column on the audit log row
    # — no recomputation, no payment-table sums. This is what the brief
    # calls "Direct Revenue = NightAuditLog.total_revenue".
    #
    # NightAuditLog model column meanings (from app/models.py docstring):
    #   total_revenue   — cash collected (frozen at audit close)
    #   net_revenue     — cash net (cash - discount)
    #   accrual_revenue — accrual-basis room+extras-discount, frozen
    #   occupancy_count — rooms_sold for that audit date
    if last_log is not None:
        settled_revenue   = float(last_log.total_revenue or 0)
        settled_net_rev   = float(last_log.net_revenue   or 0)
        settled_accrual   = float(last_log.accrual_revenue or 0)
        settled_rooms_sold = int(last_log.occupancy_count or 0)
        # ADR + RevPAR aren't stored as columns; they're derived from
        # the snapshot using the same formulas the audit uses internally.
        settled_adr = round(settled_accrual / settled_rooms_sold, 2) if settled_rooms_sold > 0 else 0.0
        # RevPAR uses sellable rooms ON the audit date. We don't have a
        # frozen sellable count — fall back to the current sellable
        # number; for single-property installs this is stable across
        # days. (Future: add `sellable_rooms` column to NightAuditLog.)
        try:
            from app.kpi_helpers import get_occupancy as _get_occ
            _o = _get_occ()
            _sellable_for_revpar = int(_o.get('sellable') or 0) or 1
        except Exception:
            _sellable_for_revpar = 1
        settled_revpar = round(settled_accrual / _sellable_for_revpar, 2) if settled_accrual else 0.0
        # Settled occupancy % — computed server-side from the canonical
        # sellable denominator (occupancy_engine) so the dashboard
        # template carries NO occupancy arithmetic (KPI Phase 1, Step 3.6).
        from app.occupancy_engine import sellable_rooms as _engine_sellable
        _sellable_now = _engine_sellable()
        settled_occ_pct = round(settled_rooms_sold / _sellable_now * 100, 1) if _sellable_now else 0.0
    else:
        settled_revenue = settled_net_rev = settled_accrual = None
        settled_rooms_sold = settled_adr = settled_revpar = None
        settled_occ_pct = None

    # ── Live values — accrual-basis from charges, NEVER from payments ──
    live_charges = compute_live_today_charges(business_date)
    live_today_revenue_charges = live_charges['total_revenue']
    live_today_room_rev_charges = live_charges['room_revenue']
    live_today_extras_charges  = live_charges['extras_revenue']
    live_rooms_sold_today       = live_charges['rooms_sold']

    return {
        'dashboard_scopes': {
            'business_date':        scopes['business_date'].isoformat(),
            'business_date_human':  scopes['business_date'].strftime('%d %b %Y'),
            'today_real':           scopes['today_real'].isoformat(),
            'today_real_human':     scopes['today_real'].strftime('%d %b %Y'),
            'last_closed_date':     scopes['last_closed_date'].isoformat() if scopes['last_closed_date'] else None,
            'last_closed_human':    scopes['last_closed_date'].strftime('%d %b %Y') if scopes['last_closed_date'] else None,
            'is_business_stale':    scopes['is_business_stale'],
            'is_today_audited':     scopes['is_today_audited'],
            'has_any_closed_audit': scopes['has_any_closed_audit'],
            'days_since_close':     scopes['days_since_close'],
        },
        # Settled — sourced exclusively from NightAuditLog snapshot.
        'settled_revenue':    settled_revenue,
        'settled_net_rev':    settled_net_rev,
        'settled_accrual':    settled_accrual,
        'settled_rooms_sold': settled_rooms_sold,
        'settled_occupancy':  settled_rooms_sold,   # alias for legacy template refs
        'settled_occ_pct':    settled_occ_pct,      # pre-computed % (no template math)
        'settled_adr':        settled_adr,
        'settled_revpar':     settled_revpar,
        # Live — sourced exclusively from CHARGES, never from payments.
        'live_today_revenue':       live_today_revenue_charges,
        'live_today_room_revenue':  live_today_room_rev_charges,
        'live_today_extras':        live_today_extras_charges,
        'live_rooms_sold':          live_rooms_sold_today,
        'live_occupancy_pct':       live_occ_pct,
        'live_arr':                 live_arr,
        'live_revpar':              live_revpar,
        # Credit (Individual) — outstanding only, NOT revenue
        'credit_outstanding_total': credit_outstanding_total,
        'credit_outstanding_count': credit_outstanding_count,
        # Daily Financial Summary panel — earned / collected / liability / receivable
        'daily_financial_summary':  daily_financial_summary,
    }


@bp.route('/dashboard')
def dashboard():
    ctx = _build_dashboard_context()
    return render_template('dashboard.html', **ctx)


@bp.route('/rooms')
def rooms():
    floor_filter = request.args.get('floor', type=int)
    status_filter = request.args.get('status')
    
    query = Room.query
    if floor_filter:
        query = query.filter_by(floor=floor_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    rooms = query.order_by(Room.room_number).all()
    floors = sorted(set(r.floor for r in Room.query.with_entities(Room.floor).distinct() if r.floor is not None))
    
    return render_template('rooms.html', rooms=rooms, floors=floors)

@bp.route('/rooms/<int:room_id>/status', methods=['POST'])
def update_room_status(room_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    new_status = request.form.get('status')
    if new_status in ['Vacant', 'Occupied', 'Dirty', 'Maintenance']:
        try:
            room = db.session.query(Room).with_for_update().filter_by(id=room_id).first_or_404()
            old_status = room.status
            room.status = new_status
            db.session.commit()
            _write_audit('Room', room.id, 'status_change',
                         {'status': old_status}, {'status': new_status})
            flash(f'Room {room.room_number} status updated to {new_status}', 'success')
        except Exception as e:
            db.session.rollback()
            logger.error('Failed to update room status: %s', e, exc_info=True)
            flash('Failed to update room status. Please try again.', 'danger')
    return redirect(url_for('main.rooms'))

@bp.route('/reservations')
def reservations():
    business_date = get_business_date()
    from datetime import date as _date_cls, timedelta as _td_cls
    _today = _date_cls.today()
    # Cancelled lookback — keep recent cancellations visible so the
    # Cancelled filter pill actually has rows. Default 30 days; admin
    # can tune via the Cancelled tab "Show all" link if needed.
    _cancelled_window = _today - _td_cls(days=30)
    reservations = Reservation.query.filter(
        db.or_(
            Reservation.status.in_(['Reserved', 'Confirmed', 'Overbooked', 'CheckedIn', 'Blocked']),
            # Show today's checkouts in the Checked Out tab (use real calendar date)
            db.and_(
                Reservation.status == 'CheckedOut',
                func.date(Reservation.checked_out_at) == _today
            ),
            # Cancelled within the last 30 days — keeps staff visibility
            # without flooding the list with ancient rows.
            db.and_(
                Reservation.status == 'Cancelled',
                db.or_(
                    db.and_(Reservation.cancellation_processed_at.isnot(None),
                            func.date(Reservation.cancellation_processed_at) >= _cancelled_window),
                    Reservation.arrival_date >= _cancelled_window,
                ),
            ),
        )
    ).order_by(Reservation.arrival_date.desc()).all()
    room_types = RoomType.query.all()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    companies = Company.query.filter_by(is_active=True).all()
    vacant_rooms = Room.query.filter_by(status='Vacant', is_active=True).order_by(Room.room_number).all()
    from app.geo_data import COUNTRIES, INDIA_STATES_CITIES
    now_time = datetime.now().strftime('%H:%M')
    default_checkout_hm = _resolve_default_checkout_hm()
    return render_template('reservations.html',
                         reservations=reservations,
                         business_date=business_date,
                         room_types=room_types,
                         payment_modes=payment_modes,
                         companies=companies,
                         vacant_rooms=vacant_rooms,
                         countries=COUNTRIES,
                         india_states_cities=INDIA_STATES_CITIES,
                         now_time=now_time,
                         default_checkout_hm=default_checkout_hm)

@bp.route('/api/reservations/bulk-booking', methods=['POST'])
@login_required
def bulk_booking_api():
    """
    JSON endpoint for the rebuilt Bulk Booking modal.
    Accepts: { guest_id, first_name, last_name, phone, email, group_name,
               special_requests, source, arrival_date, departure_date,
               advance, payment_mode_id,
               rows: [{ room_type_id, quantity, rate, adults, children, notes }] }
    """
    from app.rates import resolve_rate_for_reservation
    data = request.get_json(silent=True) or {}

    # ── Dates ──
    try:
        arrival_date   = datetime.strptime(data.get('arrival_date', ''), '%Y-%m-%d').date()
        departure_date = datetime.strptime(data.get('departure_date', ''), '%Y-%m-%d').date()
    except ValueError:
        return jsonify(success=False, error='Invalid dates provided.')
    if departure_date <= arrival_date:
        return jsonify(success=False, error='Departure must be after arrival.')

    # ── Guest ──
    guest_id = data.get('guest_id')
    if guest_id:
        guest = Guest.query.get(guest_id)
        if not guest:
            return jsonify(success=False, error='Selected guest not found.')
    else:
        first_name = (data.get('first_name') or '').strip()
        last_name  = (data.get('last_name')  or '').strip()
        phone      = (data.get('phone')      or '').strip()
        email      = (data.get('email')      or '').strip() or None
        if not first_name or not phone:
            return jsonify(success=False, error='First name and mobile are required.')
        full_name = f'{first_name} {last_name}'.strip()
        guest = Guest.query.filter_by(phone=phone).first()
        if not guest:
            guest = Guest(name=full_name, phone=phone, email=email or None)
            db.session.add(guest)
            db.session.flush()

    group_name       = (data.get('group_name')       or '').strip()
    special_requests = (data.get('special_requests') or '').strip()
    source           = (data.get('source')            or 'Walk-in').strip()
    advance          = float(data.get('advance') or 0)
    payment_mode_id  = data.get('payment_mode_id')

    rows = data.get('rows') or []
    if not rows:
        return jsonify(success=False, error='At least one room line is required.')

    created_count = 0
    for row in rows:
        room_type_id = row.get('room_type_id')
        quantity     = max(1, int(row.get('quantity') or 1))
        rate         = float(row.get('rate') or 0)
        adults       = max(1, int(row.get('adults') or 1))
        children     = max(0, int(row.get('children') or 0))
        notes        = (row.get('notes') or '').strip()

        room_type = db.session.get(RoomType, room_type_id)
        if not room_type:
            db.session.rollback()
            return jsonify(success=False, error=f'Invalid room type id={room_type_id}.')

        # Inventory check for this row (inactive rooms excluded from sellable inventory)
        total_of_type = Room.query.filter_by(room_type_id=room_type_id, is_active=True).count()
        overlapping   = Reservation.query.filter(
            Reservation.room_type_id == room_type_id,
            Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn', 'Overbooked']),
            Reservation.arrival_date < departure_date,
            Reservation.departure_date > arrival_date,
        ).count()
        available = total_of_type - overlapping
        if quantity > available:
            db.session.rollback()
            return jsonify(success=False,
                error=f'Only {available} room(s) of type "{room_type.name}" available for these dates (requested {quantity}).')

        for i in range(quantity):
            label = f'{group_name} — {room_type.name} {i+1}' if group_name else f'{room_type.name} Guest {i+1}'
            reservation = Reservation(
                guest_id        = guest.id,
                room_type_id    = room_type_id,
                arrival_date    = arrival_date,
                departure_date  = departure_date,
                adults          = adults,
                children        = children,
                rate_per_night  = rate if rate > 0 else resolve_rate_for_reservation(
                    room_type_id, arrival_date, departure_date).rate_per_night,
                advance_payment = 0,
                status          = 'Reserved',
                source          = source,
                special_requests= (f'[{group_name}] ' if group_name else '') + (notes or special_requests or '') or None,
            )
            db.session.add(reservation)
            created_count += 1

    # Record advance payment on first reservation if provided.
    # Bulk booking is by definition a future-stay flow; treat as advance.
    if advance > 0 and payment_mode_id:
        db.session.flush()
        first_res = Reservation.query.filter_by(guest_id=guest.id, arrival_date=arrival_date).order_by(Reservation.id.desc()).first()
        if first_res:
            today_biz = get_business_date()
            _purpose = 'advance' if first_res.arrival_date > today_biz else 'settlement'
            pmt = Payment(
                reservation_id  = first_res.id,
                payment_mode_id = int(payment_mode_id),
                amount          = advance,
                payment_date    = today_biz,
                payment_purpose = _purpose,
            )
            db.session.add(pmt)

    db.session.commit()
    flash(f'Bulk booking created: {created_count} reservation(s) for {group_name or guest.name}', 'success')
    return jsonify(success=True, created=created_count)


@bp.route('/reservations/bulk-booking', methods=['POST'])
def bulk_booking():
    room_type_id = request.form.get('room_type_id', type=int)
    quantity = request.form.get('quantity', type=int)
    try:
        arrival_date = datetime.strptime(request.form.get('arrival_date', ''), '%Y-%m-%d').date()
        departure_date = datetime.strptime(request.form.get('departure_date', ''), '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid dates provided for bulk booking.', 'danger')
        return redirect(url_for('main.reservations'))
    if departure_date <= arrival_date:
        flash('Departure date must be after arrival date.', 'danger')
        return redirect(url_for('main.reservations'))
    group_name = request.form.get('group_name', '')
    
    room_type = db.session.get(RoomType, room_type_id)
    if not room_type:
        flash('Invalid room type selected.', 'danger')
        return redirect(url_for('main.reservations'))
    from app.rates import resolve_rate_for_reservation
    _resolved = resolve_rate_for_reservation(room_type_id, arrival_date, departure_date)
    rate = _resolved.rate_per_night

    # Inventory guard: ensure enough rooms of this type exist for the requested dates
    total_rooms_of_type = Room.query.filter_by(room_type_id=room_type_id, is_active=True).count()
    overlapping = Reservation.query.filter(
        Reservation.room_type_id == room_type_id,
        Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn', 'Overbooked']),
        Reservation.arrival_date < departure_date,
        Reservation.departure_date > arrival_date,
    ).count()
    available = total_rooms_of_type - overlapping
    if quantity > available:
        flash(
            f'Only {available} room(s) of type "{room_type.name}" available for these dates '
            f'(requested {quantity}).',
            'danger'
        )
        return redirect(url_for('main.reservations'))

    # Bulk booking: generate unique placeholder phones to avoid unique constraint violations
    import secrets as _sec
    for i in range(quantity):
        guest = Guest(name=f'{group_name} - Guest {i+1}' if group_name else f'Group Guest {i+1}',
                      phone=f'bulk_{_sec.token_hex(6)}')
        db.session.add(guest)
        db.session.flush()
        
        reservation = Reservation(
            guest_id=guest.id,
            room_type_id=room_type_id,
            arrival_date=arrival_date,
            departure_date=departure_date,
            adults=1,
            children=0,
            rate_per_night=rate,
            advance_payment=0,
            status='Reserved',
            source='Bulk Booking'
        )
        db.session.add(reservation)
    
    db.session.commit()
    flash(f'Bulk booking created: {quantity} rooms for {group_name or "Group"}', 'success')
    return redirect(url_for('main.reservations'))

@bp.route('/reservations/block-rooms', methods=['POST'])
def block_rooms():
    room_type_id = request.form.get('room_type_id', type=int)
    quantity = request.form.get('quantity', type=int)
    try:
        from_date = datetime.strptime(request.form.get('from_date', ''), '%Y-%m-%d').date()
        to_date = datetime.strptime(request.form.get('to_date', ''), '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid dates provided for room block.', 'danger')
        return redirect(url_for('main.reservations'))
    if to_date <= from_date:
        flash('End date must be after start date.', 'danger')
        return redirect(url_for('main.reservations'))
    block_reason = request.form.get('block_reason')
    notes = request.form.get('notes', '')
    
    # Block rooms: generate unique placeholder phones
    import secrets as _sec
    for i in range(quantity):
        guest = Guest(name=f'BLOCKED - {block_reason}', phone=f'blocked_{_sec.token_hex(6)}')
        db.session.add(guest)
        db.session.flush()
        
        reservation = Reservation(
            guest_id=guest.id,
            room_type_id=room_type_id,
            arrival_date=from_date,
            departure_date=to_date,
            adults=0,
            children=0,
            rate_per_night=0,
            advance_payment=0,
            status='Blocked',
            source=block_reason
        )
        db.session.add(reservation)
    
    db.session.commit()
    flash(f'Rooms blocked: {quantity} rooms for {block_reason}', 'success')
    return redirect(url_for('main.reservations'))

@bp.route('/reservations/new', methods=['GET', 'POST'])
def new_reservation():
    if request.method == 'POST':
        # Resolve guest — returning guest via guest_id, or create from name fields
        guest_id = request.form.get('guest_id', type=int)
        if guest_id:
            guest = Guest.query.get(guest_id)
            if not guest:
                flash('Selected guest not found. Please search again.', 'danger')
                room_types = RoomType.query.all()
                payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                return render_template('reservation_form.html', room_types=room_types, payment_modes=payment_modes)
        else:
            first_name  = request.form.get('first_name', '').strip()
            last_name   = request.form.get('last_name',  '').strip()
            # fallback: accept legacy single guest_name field
            guest_name  = f"{first_name} {last_name}".strip() or request.form.get('guest_name', '').strip()
            guest_phone = request.form.get('guest_phone', '').strip()
            guest_email = request.form.get('guest_email', '').strip()

            guest_errs = validate_fields(
                validate_name(guest_name, 'Guest name'),
                validate_phone(guest_phone, 'Guest phone'),
                validate_email(guest_email),
            )
            if guest_errs:
                for e in guest_errs:
                    flash(e, 'danger')
                room_types = RoomType.query.all()
                payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                return render_template('reservation_form.html', room_types=room_types, payment_modes=payment_modes)

            guest_phone = _clean_phone(guest_phone)
            guest = Guest.query.filter_by(phone=guest_phone).first()
            if not guest:
                guest = Guest(name=guest_name, phone=guest_phone, email=guest_email or None)
                db.session.add(guest)
                db.session.flush()
        
        # Create reservation
        room_type_id = request.form.get('room_type_id', type=int)
        try:
            arrival_date = datetime.strptime(request.form.get('arrival_date', ''), '%Y-%m-%d').date()
            departure_date = datetime.strptime(request.form.get('departure_date', ''), '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid arrival or departure date.', 'danger')
            room_types = RoomType.query.all()
            payment_modes = PaymentMode.query.filter_by(is_active=True).all()
            return render_template('reservation_form.html', room_types=room_types,
                                   payment_modes=payment_modes)

        adults = request.form.get('adults', 1, type=int)
        children = request.form.get('children', 0, type=int)
        rate = request.form.get('rate', type=float)
        advance = request.form.get('advance_payment', 0, type=float)
        manager_override = request.form.get('manager_override', type=int)
        source = request.form.get('source', 'Walk-in').strip() or 'Walk-in'
        special_requests = request.form.get('special_requests', '').strip() or None

        _VALID_SOURCES = {'Walk-in', 'OTA', 'Calling', 'Website', 'Agent', 'Corporate'}
        res_errs = validate_fields(
            validate_date_range(arrival_date, departure_date, 'Arrival date', 'Departure date'),
            validate_not_past(arrival_date, 'Arrival date'),
            validate_positive_float(rate, 'Room rate'),
            validate_non_negative_float(advance if advance else 0, 'Advance payment'),
            validate_positive_int(adults, 'Adults', min_val=1, max_val=20),
            validate_positive_int(children if children else 0, 'Children', min_val=0, max_val=20),
            validate_enum(source, _VALID_SOURCES, 'Booking source'),
            validate_text_length(special_requests, 'Special requests', max_len=500),
        )
        if res_errs:
            for e in res_errs:
                flash(e, 'danger')
            room_types = RoomType.query.all()
            payment_modes = PaymentMode.query.filter_by(is_active=True).all()
            return render_template('reservation_form.html', room_types=room_types,
                                   payment_modes=payment_modes)

        # Check overbooking — always check availability regardless of advance
        status = 'Reserved'
        alternate_types = []

        total_rooms_of_type = Room.query.filter_by(room_type_id=room_type_id, is_active=True).count()
        confirmed_count = Reservation.query.filter(
            Reservation.room_type_id == room_type_id,
            Reservation.status.in_(['Confirmed', 'CheckedIn']),
            Reservation.arrival_date < departure_date,
            Reservation.departure_date > arrival_date
        ).count()

        if confirmed_count >= total_rooms_of_type:
            if manager_override == 1:
                status = 'Overbooked'
                flash('Manager override applied: Reservation marked as Overbooked', 'warning')
            else:
                # Find alternate room types
                all_types = RoomType.query.filter(RoomType.id != room_type_id).all()
                for rt in all_types:
                    total = Room.query.filter_by(room_type_id=rt.id, is_active=True).count()
                    confirmed = Reservation.query.filter(
                        Reservation.room_type_id == rt.id,
                        Reservation.status.in_(['Confirmed', 'CheckedIn']),
                        Reservation.arrival_date < departure_date,
                        Reservation.departure_date > arrival_date
                    ).count()
                    if confirmed < total:
                        alternate_types.append(rt.name)

                alt_msg = f" Alternate types available: {', '.join(alternate_types)}" if alternate_types else ""
                flash(f'Cannot confirm: All rooms of this type are fully booked for selected dates.{alt_msg} Reservation saved as Reserved.', 'warning')
                status = 'Reserved'
        elif advance > 0:
            status = 'Confirmed'
        
        reservation = Reservation(
            guest_id=guest.id,
            room_type_id=room_type_id,
            arrival_date=arrival_date,
            departure_date=departure_date,
            adults=adults,
            children=children,
            rate_per_night=rate,
            advance_payment=advance,
            status=status,
            source=source,
            special_requests=special_requests,
        )
        db.session.add(reservation)
        db.session.flush()   # assign reservation.id before creating the payment FK

        # Record advance payment if any.
        # ACCOUNTING RULE — for an Advance Booking (future stay), the
        # payment is a LIABILITY (guest deposit) on the booking date,
        # NOT revenue. Revenue is recognised on the stay date by the
        # Night Audit's accrual computation (charges, not payments).
        # The payment_purpose='advance' tag is what lets reports separate
        # this from Settlement (cash collected against earned revenue).
        if advance > 0:
            payment_mode_id = request.form.get('payment_mode_id', type=int)
            today_biz = get_business_date()
            # If the stay starts today (extreme edge — same-day "advance
            # booking"), it's effectively settlement; everything else is
            # an actual advance/deposit.
            purpose = 'advance' if arrival_date > today_biz else 'settlement'
            payment = Payment(
                reservation_id=reservation.id,
                payment_mode_id=payment_mode_id,
                amount=advance,
                payment_date=today_biz,
                payment_purpose=purpose,
            )
            db.session.add(payment)
            db.session.flush()
            _write_audit('Payment', payment.id, 'posted',
                         {},
                         {'amount': float(advance),
                          'reservation_id': reservation.id,
                          'payment_purpose': purpose,
                          'flow': 'advance_booking'})

        # ── Apr 2026: Apply Credit Voucher if one was supplied ────────
        voucher_msg = None
        try:
            v_id_raw = (request.form.get('voucher_id') or '').strip()
            v_amt_raw = (request.form.get('voucher_redeem_amount') or '').strip()
            v_id  = int(v_id_raw)  if v_id_raw  else 0
            v_amt = float(v_amt_raw) if v_amt_raw else 0.0
            if v_id > 0 and v_amt > 0.005:
                from app.models import CreditVoucher
                from app.services import redeem_credit_voucher
                voucher = db.session.get(CreditVoucher, v_id)
                if voucher is None:
                    raise ValueError('Voucher not found')
                _result = redeem_credit_voucher(
                    voucher, reservation, v_amt,
                    user_id      = current_user.id,
                    notes        = f'Applied at advance booking #{reservation.id}',
                    audit_writer = _write_audit,
                )
                voucher_msg = (f'Voucher {voucher.voucher_code}: ₹{v_amt:,.2f} applied · '
                               f'Remaining ₹{_result["remaining"]:,.2f}.')
        except ValueError as exc:
            db.session.rollback()
            flash(f'Voucher could not be applied: {exc}', 'danger')
            room_types = RoomType.query.all()
            payment_modes = PaymentMode.query.filter_by(is_active=True).all()
            return render_template('reservation_form.html', room_types=room_types,
                                   payment_modes=payment_modes)

        db.session.commit()
        flash('Advance booking created successfully' + (' · ' + voucher_msg if voucher_msg else ''), 'success')
        return redirect(url_for('main.reservations'))
    
    room_types = RoomType.query.all()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    return render_template('reservation_form.html', room_types=room_types, payment_modes=payment_modes)

@bp.route('/checkin/new', methods=['GET', 'POST'])
def walkin_checkin_new():
    from app.services import CheckInService, CheckInException
    import base64, os
    from flask import current_app
    
    business_date = get_business_date()

    if request.method == 'POST':
        try:
            from app.models import ReservationPassenger
            import json as _json
            # 1. First, create the Reservation from the walk-in inputs
            guest_name  = request.form.get('guest_name', '').strip()
            guest_phone = _clean_phone(request.form.get('guest_phone'))
            guest_email = request.form.get('guest_email', '').strip()
            room_type_id = request.form.get('room_type_id', type=int)
            nights       = request.form.get('nights', 1, type=int)
            adults       = max(1, request.form.get('adults', 1, type=int))
            children     = max(0, request.form.get('children', 0, type=int))
            advance      = request.form.get('advance_payment', 0, type=float)
            room_id      = request.form.get('room_id', type=int)

            # New fields
            country      = request.form.get('guest_country', 'India').strip() or 'India'
            state        = request.form.get('guest_state', '').strip()
            city         = request.form.get('guest_city', '').strip()
            pin_code     = request.form.get('guest_pin', '').strip()
            id_type      = request.form.get('id_type', '').strip()
            id_number    = request.form.get('id_number', '').strip()
            booking_type = request.form.get('booking_type', 'Regular')
            checkin_time  = request.form.get('checkin_time', '').strip()
            checkout_time = request.form.get('checkout_time', '').strip()
            tariff_str   = request.form.get('rate_per_night', '')
            tariff_modified = request.form.get('tariff_modified_manually') == '1'

            # ── Input validation ──────────────────────────────────────────
            _VALID_BOOKING_TYPES = {'Regular', 'Hourly'}
            _VALID_GENDERS = {'Male', 'Female', 'Other', ''}
            checkin_errs = validate_fields(
                validate_name(guest_name, 'Guest name'),
                validate_phone(guest_phone, 'Guest phone'),
                validate_email(guest_email),
                validate_id_proof(id_type, id_number),
                validate_pin_code(pin_code),
                validate_positive_int(nights, 'Nights', min_val=1, max_val=365),
                validate_positive_int(adults, 'Adults', min_val=1, max_val=20),
                validate_positive_int(children, 'Children', min_val=0, max_val=20),
                validate_non_negative_float(advance if advance else 0, 'Advance payment'),
                validate_enum(booking_type, _VALID_BOOKING_TYPES, 'Booking type'),
                validate_enum(request.form.get('guest_gender', ''), _VALID_GENDERS, 'Gender'),
            )
            if not room_type_id or not room_id:
                checkin_errs.append('Room type and room selection are required.')
            if checkin_errs:
                for e in checkin_errs:
                    flash(e, 'danger')
                return redirect(url_for('main.walkin_checkin_new'))
            num_err = _validate_checkin_numbers(nights=nights, rate=tariff_str or None, advance=advance)
            if num_err:
                flash(num_err, 'danger')
                return redirect(url_for('main.walkin_checkin_new'))

            # ── Business date lock guard ──────────────────────────────────
            from app.services import assert_business_date_unlocked
            ok, lock_err = assert_business_date_unlocked(business_date, 'check in')
            if not ok:
                flash(lock_err, 'danger')
                return redirect(url_for('main.walkin_checkin_new'))

            guest = Guest.query.filter_by(phone=guest_phone).first()
            if not guest:
                guest = Guest(name=guest_name, phone=guest_phone,
                              email=guest_email if guest_email else None)
                db.session.add(guest)
                db.session.flush()

            # Update address fields on existing or new guest
            guest.first_name = request.form.get('first_name', '').strip() or guest.first_name
            guest.last_name  = request.form.get('last_name', '').strip() or guest.last_name
            # Sync legacy name field
            if guest.first_name:
                guest.name = f'{guest.first_name} {guest.last_name or ""}'.strip()
            guest.country  = country
            guest.state    = state or guest.state
            guest.city     = city or guest.city
            guest.pin_code = pin_code or guest.pin_code
            if id_type:    guest.id_proof_type   = id_type
            if id_number:  guest.id_proof_number = id_number

            # GRC fields
            _dob_str = request.form.get('guest_dob', '').strip()
            if _dob_str:
                try:
                    from datetime import date as _date_cls
                    _dob = _date_cls.fromisoformat(_dob_str)
                    if _dob > date.today():
                        flash('Date of birth cannot be in the future.', 'warning')
                    else:
                        guest.date_of_birth = _dob
                except ValueError:
                    flash('Invalid date of birth format.', 'warning')
            guest.gender = request.form.get('guest_gender', '').strip() or guest.gender
            guest.purpose_of_visit = request.form.get('purpose_of_visit', '').strip() or guest.purpose_of_visit

            room_type = RoomType.query.get_or_404(room_type_id)
            departure_date = business_date + timedelta(days=nights)

            # ── Pricing engine: server-authoritative via centralized helper ──
            from app.financial import compute_pricing_from_mode, PricingError
            pricing_mode = request.form.get('pricing_mode', 'standard').strip()

            # ── Backend safety: detect per-night / total confusion ──────
            # If tariff is modified, nights > 1, and the entered per-night
            # value would produce a total far above standard, the user
            # likely intended it as a total stay amount.
            _entered_pn_raw = request.form.get('entered_per_night', '')
            _entered_ts_raw = request.form.get('entered_stay_total', '')
            if (pricing_mode == 'per_night' and tariff_modified and nights > 1
                    and _entered_pn_raw):
                try:
                    _pn_val = float(_entered_pn_raw)
                    _std_total = float(room_type.base_rate) * nights
                    # If entered "per night" value × nights > 1.8× standard total,
                    # and the entered value is close to standard total itself,
                    # the user almost certainly entered a total, not a per-night rate.
                    if (_pn_val * nights > _std_total * 1.8
                            and _pn_val >= _std_total * 0.5
                            and _pn_val <= _std_total * 1.5):
                        logger.warning(
                            'PRICING SAFETY: per_night value %.2f × %d nights = %.2f '
                            '(>1.8× std %.2f). Forcing total_stay mode.',
                            _pn_val, nights, _pn_val * nights, _std_total
                        )
                        pricing_mode = 'total_stay'
                        _entered_ts_raw = _entered_pn_raw
                        _entered_pn_raw = ''
                        flash('Pricing mode auto-corrected to "Total Stay Amount" — '
                              'the entered value appeared to be a full-stay total, '
                              'not a per-night rate.', 'info')
                except (ValueError, TypeError):
                    pass

            try:
                _pricing = compute_pricing_from_mode(
                    pricing_mode=pricing_mode,
                    standard_rate=room_type.base_rate,
                    nights=nights,
                    entered_per_night=_entered_pn_raw or tariff_str or None,
                    entered_stay_total=_entered_ts_raw or None,
                    discount_amount=request.form.get('discount_amount', 0),
                    discount_reason=request.form.get('discount_reason', ''),
                    discount_authorized_by=request.form.get('discount_authorized_by', ''),
                    discount_given_by=request.form.get('discount_given_by', ''),
                )
            except PricingError as pe:
                flash(str(pe), 'danger')
                return redirect(url_for('main.walkin_checkin_new'))

            rate         = _pricing.rate_per_night
            charged_total = _pricing.charged_total
            adj_amount   = _pricing.adjustment_amount
            adj_type     = _pricing.adjustment_type
            disc_val     = _pricing.discount_amount
            disc_reason  = _pricing.discount_reason
            disc_auth    = _pricing.discount_authorized_by
            disc_given   = _pricing.discount_given_by
            pricing_mode = _pricing.pricing_mode

            if _pricing.warnings:
                for w in _pricing.warnings:
                    flash(w, 'warning')

            reservation = Reservation(
                guest_id=guest.id,
                room_type_id=room_type_id,
                arrival_date=business_date,
                departure_date=departure_date,
                adults=adults,
                children=children,
                rate_per_night=rate,
                advance_payment=advance,
                status='Reserved',
                source='Walk-in',
                booking_type=booking_type,
                checkin_time=checkin_time or None,
                checkout_time=checkout_time or None,
                tariff_modified_manually=(pricing_mode != 'standard'),
                pricing_mode=pricing_mode,
                standard_tariff=_pricing.standard_rate,
                adjustment_type=adj_type,
                adjustment_amount=adj_amount,
                discount_amount=disc_val,
                discount_reason=disc_reason or None,
                discount_authorized_by=disc_auth or None,
                discount_given_by=disc_given or None,
                discount_at=datetime.utcnow() if disc_val and disc_val > 0 else None,
            )
            db.session.add(reservation)
            db.session.flush()

            # ── Nightly rate rows (Phase B) ─────────────────────────
            from app.nightly_rate_service import safe_sync_nightly_rates
            safe_sync_nightly_rates(
                reservation, reason='new_booking',
                override_final_total=charged_total if pricing_mode != 'standard' else None,
                discount_total=disc_val,
                pricing_mode=pricing_mode,
                manual_override=(pricing_mode != 'standard'),
            )

            # ── Pricing audit trail (non-standard modes) ─────���──────
            if pricing_mode != 'standard':
                _write_audit('Reservation', reservation.id, 'pricing_override', {
                    'standard_rate': _pricing.standard_rate,
                    'standard_total': _pricing.standard_total,
                }, {
                    'pricing_mode': pricing_mode,
                    'rate_per_night': rate,
                    'charged_total': charged_total,
                    'adjustment_amount': adj_amount,
                    'adjustment_type': adj_type,
                    'discount_amount': float(disc_val) if disc_val else 0,
                    'discount_reason': disc_reason,
                    'discount_authorized_by': disc_auth,
                })

            # Save additional passengers
            passengers_json = request.form.get('passengers_json', '[]')
            try:
                passengers_data = _json.loads(passengers_json)
                for p in passengers_data:
                    pname = (p.get('name') or '').strip()
                    if not pname:
                        continue
                    pax = ReservationPassenger(
                        reservation_id=reservation.id,
                        name=pname,
                        age=int(p['age']) if p.get('age') else None,
                        gender=p.get('gender') or None,
                        mobile=p.get('mobile') or None,
                        id_type=p.get('id_type') or None,
                        id_number=p.get('id_number') or None,
                        relationship=p.get('relationship') or None,
                    )
                    db.session.add(pax)
            except Exception as e:
                logger.warning('Failed to parse passenger data for reservation %d: %s', reservation.id, e)
                flash('Warning: Additional passenger data could not be saved. Please add them manually.', 'warning')

            # 2. Process check-in for the new reservation
            form_data = request.form.to_dict()
            form_data['room_id'] = room_id
            form_data['company_id'] = request.form.get('company_id', type=int)
            form_data['deposit_amount'] = request.form.get('deposit_amount', 0)
            form_data['deposit_payment_mode_id'] = request.form.get('deposit_payment_mode_id', type=int)
            form_data['total_amount'] = request.form.get('total_amount', 0)

            # Photo upload — validated type + size
            guest_photo_path = None
            try:
                if 'guest_photo' in request.files:
                    guest_photo_path = _save_upload(
                        request.files['guest_photo'],
                        f"guest_{reservation.guest_id}"
                    )
            except ValueError as ve:
                flash(str(ve), 'warning')
            # Webcam capture (base64) — validated size before saving
            if not guest_photo_path:
                webcam_data = request.form.get('webcam_photo_data', '')
                if webcam_data and ',' in webcam_data:
                    try:
                        import os
                        img_bytes = base64.b64decode(webcam_data.split(',')[1])
                        if len(img_bytes) > _MAX_UPLOAD_BYTES:
                            flash('Webcam photo is too large (max 5 MB). Photo was not saved.', 'warning')
                        else:
                            filename = f"guest_{reservation.guest_id}_{int(datetime.utcnow().timestamp())}_webcam.jpg"
                            upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'checkin')
                            os.makedirs(upload_path, exist_ok=True)
                            with open(os.path.join(upload_path, filename), 'wb') as f:
                                f.write(img_bytes)
                            guest_photo_path = f"uploads/checkin/{filename}"
                    except Exception as _photo_err:
                        current_app.logger.error('Webcam photo save failed for guest %s: %s', reservation.guest_id, _photo_err)
                        flash('Could not save webcam photo. Check-in was recorded without a photo.', 'warning')

            signature_path = None
            if 'signature_data' in request.form:
                sig_data = request.form.get('signature_data')
                if sig_data and ',' in sig_data:
                    try:
                        import os
                        sig_bytes = base64.b64decode(sig_data.split(',')[1])
                        if len(sig_bytes) <= _MAX_UPLOAD_BYTES:
                            filename = f"signature_{reservation.guest_id}_{datetime.utcnow().timestamp()}.png"
                            upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'checkin')
                            os.makedirs(upload_path, exist_ok=True)
                            with open(os.path.join(upload_path, filename), 'wb') as f:
                                f.write(sig_bytes)
                            signature_path = f"uploads/checkin/{filename}"
                    except Exception:
                        pass

            form_data['guest_photo_path'] = guest_photo_path
            form_data['signature_path'] = signature_path
            form_data['device_info'] = request.headers.get('User-Agent', '')

            checkin = CheckInService.complete_full_checkin(
                reservation.id,
                form_data,
                current_user.id,
                request.remote_addr
            )

            # GRC declaration + signature tracking
            try:
                checkin.grc_declaration_accepted = request.form.get('grc_declaration_accepted') == '1'
                checkin.grc_signature_ip = request.remote_addr
                checkin.grc_signature_timestamp = datetime.utcnow()
            except Exception:
                pass

            # Save foreign national info if applicable
            try:
                if country and country.lower() != 'india':
                    from app.models import ForeignNationalInfo
                    fni = ForeignNationalInfo.query.filter_by(guest_id=guest.id).first()
                    if not fni:
                        fni = ForeignNationalInfo(guest_id=guest.id, nationality=country)
                        db.session.add(fni)
                    fni.nationality = country
                    fni.passport_number = request.form.get('passport_number', '').strip() or fni.passport_number
                    fni.passport_issue_place = request.form.get('passport_issue_place', '').strip() or fni.passport_issue_place
                    fni.visa_number = request.form.get('visa_number', '').strip() or fni.visa_number
                    fni.visa_type = request.form.get('visa_type', '').strip() or fni.visa_type
                    fni.visa_issue_place = request.form.get('visa_issue_place', '').strip() or fni.visa_issue_place
                    fni.arrival_from = request.form.get('arrival_from', '').strip() or fni.arrival_from
                    fni.next_destination = request.form.get('next_destination', '').strip() or fni.next_destination
                    for _df in ('passport_expiry_date', 'visa_issue_date', 'visa_expiry_date'):
                        _dv = request.form.get(_df, '').strip()
                        if _dv:
                            try:
                                from datetime import date as _dt
                                setattr(fni, _df, _dt.fromisoformat(_dv))
                            except ValueError:
                                pass
                    db.session.commit()
            except Exception as _fni_err:
                logger.warning('Foreign national info save failed: %s', _fni_err)

            # Welcome WhatsApp notification (non-blocking)
            try:
                from flask import current_app
                from app.notifications import notify_checkin_welcome
                notify_checkin_welcome(reservation, app=current_app._get_current_object())
            except Exception:
                pass

            flash('Walk-in Check-in completed successfully', 'success')
            return redirect(url_for('main.reservations'))
            
        except CheckInException as e:
            db.session.rollback()
            logger.error('Check-in failed: %s', e, exc_info=True)
            flash('Check-in failed. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            logger.error('Unexpected error: %s', e, exc_info=True)
            flash('An unexpected error occurred. Please try again.', 'danger')

    vacant_rooms = Room.query.filter_by(status='Vacant', is_active=True).all()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    companies = Company.query.filter_by(is_active=True).all()
    room_types = RoomType.query.all()

    from app.geo_data import COUNTRIES, INDIA_STATES_CITIES
    now_time = datetime.utcnow().strftime('%H:%M')
    default_checkout_hm = _resolve_default_checkout_hm()

    return render_template('checkin_new.html',
        reservation=None,
        checkin_record=None,
        vacant_rooms=vacant_rooms,
        payment_modes=payment_modes,
        companies=companies,
        room_types=room_types,
        business_date=business_date,
        countries=COUNTRIES,
        india_states_cities=INDIA_STATES_CITIES,
        now_time=now_time,
        default_checkout_hm=default_checkout_hm,
    )

@bp.route('/walkin-full-checkin', methods=['POST'])
def walkin_full_checkin():
    """Create a walk-in reservation and redirect straight to the Full Check-in form."""
    guest_name  = request.form.get('guest_name', '').strip()
    guest_phone = request.form.get('guest_phone', '').strip()
    guest_email = request.form.get('guest_email', '').strip()
    room_type_id = request.form.get('room_type_id', type=int)
    nights       = request.form.get('nights', 1, type=int)
    adults       = request.form.get('adults', 1, type=int)
    children     = request.form.get('children', 0, type=int)
    advance      = request.form.get('advance_payment', 0, type=float)
    payment_mode_id = request.form.get('payment_mode_id', type=int)

    if not guest_name or not guest_phone or not room_type_id:
        flash('Guest name, mobile, and room type are required.', 'danger')
        return redirect(url_for('main.reservations'))

    business_date = get_business_date()
    departure_date = business_date + timedelta(days=nights)

    # Find or create guest
    guest = Guest.query.filter_by(phone=guest_phone).first()
    if not guest:
        guest = Guest(name=guest_name, phone=guest_phone,
                      email=guest_email if guest_email else None)
        db.session.add(guest)
        db.session.flush()

    room_type = RoomType.query.get_or_404(room_type_id)

    # Create the reservation in Reserved status so the full check-in form can process it
    from app.rates import resolve_rate_for_reservation
    _resolved = resolve_rate_for_reservation(room_type_id, business_date, departure_date)
    reservation = Reservation(
        guest_id=guest.id,
        room_type_id=room_type_id,
        arrival_date=business_date,
        departure_date=departure_date,
        adults=adults,
        children=children,
        rate_per_night=_resolved.rate_per_night,
        standard_tariff=_resolved.base_rate,
        advance_payment=advance,
        status='Reserved',
        source='Walk-in'
    )
    db.session.add(reservation)
    db.session.flush()

    from app.nightly_rate_service import safe_sync_nightly_rates
    safe_sync_nightly_rates(reservation, reason='new_booking')

    db.session.commit()
    flash(f'Walk-in reservation created for {guest.name}. Please complete the full check-in below.', 'info')
    return redirect(url_for('main.checkin', reservation_id=reservation.id))

@bp.route('/reservations/<int:reservation_id>/checkin', methods=['GET', 'POST'])
def checkin(reservation_id):
    from app.services import CheckInService, CheckInException
    import base64, os
    from flask import current_app
    
    reservation = Reservation.query.get_or_404(reservation_id)
    
    columns = [col['name'] for col in inspect(db.engine).get_columns('checkin_records')]
    checkin_record = None
    if 'checkin_mode' in columns and 'is_profile_complete' in columns:
        checkin_record = CheckInService.get_checkin_record(reservation_id)
    else:
        flash('Database migration required. Run: python run_migration.py', 'warning')
    
    if request.method == 'POST':
        try:
            # ── Pricing engine: process tariff modification ──────────
            # This is the CRITICAL path for existing reservations being
            # checked in.  Without this, modified tariffs are silently lost.
            tariff_modified = request.form.get('tariff_modified_manually') == '1'
            if tariff_modified:
                from app.financial import compute_pricing_from_mode, PricingError
                _pricing_mode = request.form.get('pricing_mode', 'standard').strip()
                _nights = (reservation.departure_date - reservation.arrival_date).days
                _nights = max(_nights, 1)
                _tariff_str = request.form.get('rate_per_night', '')
                _entered_pn = request.form.get('entered_per_night', '')
                _entered_ts = request.form.get('entered_stay_total', '')

                # Backend safety: detect per-night/total confusion
                if (_pricing_mode == 'per_night' and _nights > 1 and _entered_pn):
                    try:
                        _pn_val = float(_entered_pn)
                        _std_total = float(reservation.room_type.base_rate) * _nights
                        if (_pn_val * _nights > _std_total * 1.8
                                and _pn_val >= _std_total * 0.5
                                and _pn_val <= _std_total * 1.5):
                            logger.warning(
                                'PRICING SAFETY [checkin]: per_night %.2f x %d nights = %.2f '
                                '(>1.8x std %.2f). Forcing total_stay.',
                                _pn_val, _nights, _pn_val * _nights, _std_total)
                            _pricing_mode = 'total_stay'
                            _entered_ts = _entered_pn
                            _entered_pn = ''
                            flash('Pricing mode auto-corrected to "Total Stay Amount".', 'info')
                    except (ValueError, TypeError):
                        pass

                try:
                    _pricing = compute_pricing_from_mode(
                        pricing_mode=_pricing_mode,
                        standard_rate=reservation.room_type.base_rate,
                        nights=_nights,
                        entered_per_night=_entered_pn or _tariff_str or None,
                        entered_stay_total=_entered_ts or None,
                        discount_amount=request.form.get('discount_amount', 0),
                        discount_reason=request.form.get('discount_reason', ''),
                        discount_authorized_by=request.form.get('discount_authorized_by', ''),
                        discount_given_by=request.form.get('discount_given_by', ''),
                    )
                except PricingError as pe:
                    flash(str(pe), 'danger')
                    return redirect(url_for('main.checkin', reservation_id=reservation_id))

                # Update reservation pricing fields
                reservation.rate_per_night        = _pricing.rate_per_night
                reservation.pricing_mode          = _pricing.pricing_mode
                reservation.tariff_modified_manually = True
                reservation.standard_tariff       = _pricing.standard_rate
                reservation.adjustment_type       = _pricing.adjustment_type
                reservation.adjustment_amount     = _pricing.adjustment_amount
                reservation.discount_amount       = _pricing.discount_amount
                reservation.discount_reason       = _pricing.discount_reason
                reservation.discount_authorized_by = _pricing.discount_authorized_by
                reservation.discount_given_by     = _pricing.discount_given_by
                if _pricing.discount_amount and _pricing.discount_amount > 0:
                    reservation.discount_at = datetime.utcnow()
                db.session.flush()

                logger.info(
                    'PRICING [checkin route] res=%d mode=%s rate=%.2f charged=%.2f adj=%.2f(%s)',
                    reservation_id, _pricing.pricing_mode, _pricing.rate_per_night,
                    _pricing.charged_total, _pricing.adjustment_amount,
                    _pricing.adjustment_type or 'NONE')

                # Audit trail
                _write_audit('Reservation', reservation_id, 'pricing_override', {
                    'standard_rate': _pricing.standard_rate,
                    'standard_total': _pricing.standard_total,
                }, {
                    'pricing_mode': _pricing.pricing_mode,
                    'rate_per_night': _pricing.rate_per_night,
                    'charged_total': _pricing.charged_total,
                    'adjustment_amount': _pricing.adjustment_amount,
                    'adjustment_type': _pricing.adjustment_type,
                })

                if _pricing.warnings:
                    for w in _pricing.warnings:
                        flash(w, 'warning')

                # Nightly rate rows (Phase B)
                from app.nightly_rate_service import safe_sync_nightly_rates
                safe_sync_nightly_rates(
                    reservation, reason='checkin_override',
                    override_final_total=_pricing.charged_total,
                    discount_total=_pricing.discount_amount,
                    pricing_mode=_pricing.pricing_mode,
                    manual_override=True,
                )

            form_data = request.form.to_dict()
            form_data['room_id'] = request.form.get('room_id', type=int)
            form_data['company_id'] = request.form.get('company_id', type=int)
            form_data['deposit_amount'] = request.form.get('deposit_amount', 0)
            form_data['deposit_payment_mode_id'] = request.form.get('deposit_payment_mode_id', type=int)
            form_data['total_amount'] = request.form.get('total_amount', 0)

            guest_photo_path = None
            if 'guest_photo' in request.files:
                try:
                    guest_photo_path = _save_upload(
                        request.files['guest_photo'],
                        f"guest_{reservation.guest_id}"
                    )
                except ValueError as ve:
                    flash(str(ve), 'warning')
            
            # Webcam capture (base64) — validated size
            if not guest_photo_path:
                webcam_data = request.form.get('webcam_photo_data', '')
                if webcam_data and ',' in webcam_data:
                    try:
                        img_bytes = base64.b64decode(webcam_data.split(',')[1])
                        if len(img_bytes) > _MAX_UPLOAD_BYTES:
                            flash('Webcam photo is too large (max 5 MB). Photo was not saved.', 'warning')
                        else:
                            filename = f"guest_{reservation.guest_id}_{int(datetime.utcnow().timestamp())}_webcam.jpg"
                            upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'checkin')
                            os.makedirs(upload_path, exist_ok=True)
                            with open(os.path.join(upload_path, filename), 'wb') as f:
                                f.write(img_bytes)
                            guest_photo_path = f"uploads/checkin/{filename}"
                    except Exception as _photo_err:
                        current_app.logger.error('Webcam photo save failed for guest %s: %s', reservation.guest_id, _photo_err)
                        flash('Could not save webcam photo. Check-in was recorded without a photo.', 'warning')

            signature_path = None
            if 'signature_data' in request.form:
                sig_data = request.form.get('signature_data')
                if sig_data and ',' in sig_data:
                    try:
                        sig_bytes = base64.b64decode(sig_data.split(',')[1])
                        if len(sig_bytes) <= _MAX_UPLOAD_BYTES:
                            filename = f"signature_{reservation.guest_id}_{int(datetime.utcnow().timestamp())}.png"
                            upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'checkin')
                            os.makedirs(upload_path, exist_ok=True)
                            with open(os.path.join(upload_path, filename), 'wb') as f:
                                f.write(sig_bytes)
                            signature_path = f"uploads/checkin/{filename}"
                    except Exception as _sig_err:
                        current_app.logger.error('Signature save failed for guest %s: %s', reservation.guest_id, _sig_err)
            
            form_data['guest_photo_path'] = guest_photo_path
            form_data['signature_path'] = signature_path
            form_data['device_info'] = request.headers.get('User-Agent', '')
            
            checkin = CheckInService.complete_full_checkin(
                reservation_id,
                form_data,
                current_user.id,
                request.remote_addr
            )

            # ── Early check-in charge (auto-posted when rule applies) ──────
            try:
                from app.cico_service import (
                    get_cico_settings as _get_cico,
                    compute_early_checkin as _calc_early,
                    post_charge as _post_cico,
                )
                _cico = _get_cico()
                if _cico['auto_post'] and _cico['early_enabled']:
                    _nights = (reservation.departure_date - reservation.arrival_date).days
                    _now    = datetime.now()          # server local time (hotel TZ)
                    _result = _calc_early(
                        float(reservation.rate_per_night),
                        _now.time(),
                        _nights,
                        rules=_cico,
                    )
                    # Store actual check-in time string on reservation
                    reservation.checkin_time = _now.strftime('%H:%M')
                    if _result['applicable'] and not _result['grace'] and _result['amount'] > 0:
                        # pre-expire is defensive; post_charge() also expires internally
                        db.session.expire(reservation, ['extra_charges'])
                        _ec = _post_cico(
                            reservation,
                            'early_checkin',
                            _result['amount'],
                            f"{_now.strftime('%I:%M %p')} — {_result['pct']}%",
                            user_id=current_user.id,
                            pct=_result['pct'],
                            actual_time_str=_now.strftime('%H:%M'),
                        )
                        if _ec:
                            db.session.commit()
                            flash(
                                f"Early Check-in applied: {_result['pct']}% = "
                                f"₹{_result['amount']:,.2f} "
                                f"({_result['slab_label']})",
                                'info',
                            )
                    elif _result['applicable'] and _result['grace']:
                        flash(
                            f"Early Check-in: {_result['slab_label']} — no charge.",
                            'info',
                        )
            except Exception as _cico_err:
                current_app.logger.warning(
                    '[CICO] Early CI charge failed for res=%d: %s',
                    reservation_id, _cico_err
                )
            # ──────────────────────────────────────────────────────────────

            flash('Check-in completed successfully', 'success')
            return redirect(url_for('main.reservations'))
        
        except CheckInException as e:
            logger.error('Check-in failed: %s', e, exc_info=True)
            flash('Check-in failed. Please try again.', 'danger')
        except Exception as e:
            logger.error('Unexpected error: %s', e, exc_info=True)
            flash('An unexpected error occurred. Please try again.', 'danger')
    
    vacant_rooms = Room.query.filter_by(status='Vacant', is_active=True).all()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    companies = Company.query.filter_by(is_active=True).all()
    room_types = RoomType.query.all()

    from app.geo_data import COUNTRIES, INDIA_STATES_CITIES
    now_time = datetime.utcnow().strftime('%H:%M')
    default_checkout_hm = _resolve_default_checkout_hm()

    # Guest-level duplicate warning: same phone → another active stay
    guest_duplicate_warning = None
    if reservation.guest and reservation.guest.phone:
        _dup = (Reservation.query
                .join(Guest, Reservation.guest_id == Guest.id)
                .filter(Guest.phone == reservation.guest.phone,
                        Reservation.status == 'CheckedIn',
                        Reservation.id != reservation_id)
                .first())
        if _dup:
            _dup_room = _dup.room.room_number if _dup.room else '—'
            guest_duplicate_warning = (
                f'This guest (mobile: {reservation.guest.phone}) already has an '
                f'active stay in Room {_dup_room} (Reservation #{_dup.id}).'
            )

    # GRC: pre-fill from portal + foreign national info
    prefill = {}
    is_foreign = False
    foreign_info = None
    try:
        from app.grc_service import prefill_from_precheckin, is_foreign_national
        from app.models import ForeignNationalInfo
        prefill = prefill_from_precheckin(reservation_id)
        if reservation.guest:
            is_foreign = is_foreign_national(reservation.guest)
            if is_foreign:
                foreign_info = ForeignNationalInfo.query.filter_by(guest_id=reservation.guest_id).first()
    except Exception:
        pass

    return render_template('checkin_new.html',
        reservation=reservation,
        checkin_record=checkin_record,
        vacant_rooms=vacant_rooms,
        payment_modes=payment_modes,
        companies=companies,
        room_types=room_types,
        business_date=get_business_date(),
        countries=COUNTRIES,
        india_states_cities=INDIA_STATES_CITIES,
        now_time=now_time,
        default_checkout_hm=default_checkout_hm,
        guest_duplicate_warning=guest_duplicate_warning,
        prefill=prefill,
        is_foreign=is_foreign,
        foreign_info=foreign_info,
    )



@bp.route('/checkout/<int:reservation_id>', methods=['GET', 'POST'])
def checkout(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)

    # Only CheckedIn reservations can be checked out
    if reservation.status != 'CheckedIn':
        flash(f'Cannot checkout: reservation status is "{reservation.status}".', 'danger')
        return redirect(url_for('main.reservations'))

    # Mark checkout as initiated the moment front-desk opens the checkout page.
    # Escalates badge to CRITICAL on the overview if not completed within 2 hours.
    if not reservation.checkout_initiated:
        reservation.checkout_initiated = True
        db.session.commit()

    if request.method == 'POST':
        # Lock guard: block checkout if the departure date is locked by a
        # completed audit. Admin can override with reason — the override is
        # written to the audit log alongside the checkout itself.
        from app.services import assert_or_admin_override
        ok, lock_err, _ovr_used, _ovr_reason = assert_or_admin_override(
            reservation.departure_date, 'checkout', request, current_user
        )
        if not ok:
            flash(lock_err, 'danger')
            return redirect(url_for('main.reservations'))
        if _ovr_used:
            _write_audit('Reservation', reservation.id, 'audit_lock_override',
                         {'departure_date': reservation.departure_date.isoformat()},
                         {'action': 'checkout',
                          'override_reason': _ovr_reason,
                          'admin_user_id': current_user.id})

        try:
            # Pessimistic lock: prevent concurrent checkout of same reservation.
            # Use of=Reservation to avoid PostgreSQL error when nullable FKs
            # cause LEFT OUTER JOINs (FOR UPDATE cannot lock outer-join sides).
            reservation = (db.session.query(Reservation)
                           .with_for_update(of=Reservation)
                           .filter_by(id=reservation_id)
                           .first())
            if not reservation or reservation.status != 'CheckedIn':
                db.session.rollback()
                flash('Reservation is no longer checked-in (may have been checked out by another user).', 'warning')
                return redirect(url_for('main.reservations'))

            # Lock the room too to prevent concurrent room status changes
            locked_room = None
            if reservation.room_id:
                locked_room = db.session.query(Room).with_for_update(of=Room).filter_by(id=reservation.room_id).first()
                if not locked_room:
                    db.session.rollback()
                    flash('Room not found for this reservation.', 'danger')
                    return redirect(url_for('main.reservations'))

            # Add extra charges if any
            extra_desc = request.form.get('extra_description')
            extra_amount = request.form.get('extra_amount', type=float)

            if extra_desc and extra_amount and extra_amount > 0:
                extra = ExtraCharge(
                    reservation_id=reservation.id,
                    description=extra_desc,
                    amount=extra_amount
                )
                db.session.add(extra)
                db.session.flush()

            # ── Discount — applied before billing calc so balance is correct ──
            co_disc_amt  = request.form.get('discount_amount', type=float) or 0.0
            co_disc_reason = request.form.get('discount_reason', '').strip() or None
            co_disc_auth   = request.form.get('discount_authorized_by', '').strip() or None
            if co_disc_amt < 0:
                db.session.rollback()
                flash('Discount amount cannot be negative.', 'danger')
                payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                billing = calculate_stay_amount(reservation)
                return render_template('checkout.html', reservation=reservation,
                                       billing=billing, payment_modes=payment_modes,
                                       checkout_debug=None)
            # Cap discount to total charges (room + extras) — prevent negative balance
            if co_disc_amt > 0:
                _pre_billing = calculate_stay_amount(reservation)
                _max_discount = _pre_billing['room_charges'] + _pre_billing['extra_charges']
                if co_disc_amt > _max_discount:
                    db.session.rollback()
                    flash(f'Discount ₹{co_disc_amt:,.0f} exceeds total charges ₹{_max_discount:,.0f}. Maximum discount allowed is ₹{_max_discount:,.0f}.', 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = _pre_billing
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
            if co_disc_amt > 0:
                if not co_disc_auth:
                    db.session.rollback()
                    flash('"Authorized By" is required when a discount is applied.', 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = calculate_stay_amount(reservation)
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
                # Policy check (raises ValueError if over threshold without manager role)
                from app.revenue_guard import validate_discount
                try:
                    validate_discount(current_user, co_disc_amt)
                except ValueError as ve:
                    db.session.rollback()
                    flash(str(ve), 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = calculate_stay_amount(reservation)
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
                reservation.discount_amount        = co_disc_amt
                reservation.discount_reason        = co_disc_reason
                reservation.discount_authorized_by = co_disc_auth
                reservation.discount_given_by      = current_user.username if current_user.is_authenticated else ''
                reservation.discount_at            = datetime.utcnow()
                # ── Source-captured leakage classification (Apr 2026) ──
                # Authoritative type — overrides any later heuristic in
                # night_audit_service. Reports prefer this stored value.
                reservation.leakage_type                  = 'DISCOUNT'
                reservation.leakage_intent                = 'INTENTIONAL'
                reservation.leakage_reason                = (co_disc_reason or 'Checkout discount')[:200]
                reservation.leakage_authorized_by_user_id = current_user.id
                reservation.leakage_created_at            = datetime.utcnow()
                # Fire discount alert (non-fatal)
                try:
                    from app.alert_service import AlertService
                    AlertService.check_discount(
                        user_id=current_user.id,
                        discount_amount=co_disc_amt,
                        reservation_id=reservation.id,
                        room_no=reservation.room.room_number if reservation.room else None,
                    )
                except Exception:
                    pass
            else:
                # Explicitly clear any discount that was set at check-in
                reservation.discount_amount        = 0
                reservation.discount_reason        = None
                reservation.discount_authorized_by = None
                reservation.discount_given_by      = None
                reservation.discount_at            = None
            db.session.flush()

            # ── Late check-out charge (auto-posted when rule applies) ──────
            # Only apply if checking out ON or AFTER the departure date.
            # Early departures (today < departure_date) never incur late fees.
            _late_co_posted_amt = 0.0
            _now_co = datetime.now()                          # single authoritative timestamp
            reservation.checkout_time = _now_co.strftime('%H:%M')  # always recorded
            _today = _now_co.date()
            _is_departure_day_or_later = _today >= reservation.departure_date
            try:
                from app.cico_service import (
                    get_cico_settings as _get_cico,
                    compute_late_checkout as _calc_late,
                    post_charge as _post_cico,
                    log_waiver as _log_waiver,
                )
                _cico = _get_cico()
                _waive_late  = request.form.get('waive_late_checkout') == '1'
                _waive_reason = request.form.get('waive_late_co_reason', '').strip()
                if _cico['auto_post'] and _cico['late_enabled'] and _is_departure_day_or_later:
                    _nights = (reservation.departure_date - reservation.arrival_date).days
                    _result = _calc_late(
                        float(reservation.rate_per_night),
                        _now_co.time(),
                        _nights,
                        rules=_cico,
                    )
                    _uid = current_user.id if current_user.is_authenticated else None
                    if _waive_late and _cico.get('allow_waive') and _result['applicable'] \
                            and not _result['grace']:
                        # Waiver path — require a reason
                        if not _waive_reason:
                            flash('A waiver reason is required to waive the late check-out charge.',
                                  'warning')
                            # continue checkout but log waiver without reason as blank
                            _waive_reason = '(no reason given)'
                        _log_waiver(
                            reservation,
                            'late_checkout',
                            _result['amount'],
                            _result['slab_label'],
                            _result['pct'],
                            _now_co.strftime('%H:%M'),
                            _uid,
                            _waive_reason,
                        )
                    elif not _waive_late and _result['applicable'] \
                            and not _result['grace'] and _result['amount'] > 0:
                        # pre-expire is defensive; post_charge() also expires internally
                        db.session.expire(reservation, ['extra_charges'])
                        _ec = _post_cico(
                            reservation,
                            'late_checkout',
                            _result['amount'],
                            f"{_now_co.strftime('%I:%M %p')} — {_result['pct']}%",
                            user_id=_uid,
                            pct=_result['pct'],
                            actual_time_str=_now_co.strftime('%H:%M'),
                        )
                        if _ec:
                            _late_co_posted_amt = _result['amount']
                            db.session.flush()
            except Exception as _cico_err:
                from flask import current_app
                current_app.logger.warning(
                    '[CICO] Late CO charge failed for res=%d: %s',
                    reservation.id, _cico_err
                )
            # ──────────────────────────────────────────────────────────────

            # ── Payments — one fixed field per active payment mode ───────────
            # Snapshot paid amount BEFORE processing this checkout's payments
            billing_before_pay = calculate_stay_amount(reservation)
            payment_modes = PaymentMode.query.filter_by(is_active=True).all()

            # ── OTA auto-settlement (Phase 1) ────────────────────────────────
            # If the reservation was paid at OTA, post the room_charges to the
            # matching ota_receivable head automatically BEFORE the normal
            # payment loop.  The guest should not be paying room revenue at
            # the hotel — only extras / incidentals.
            from app.ota_settlement_service import (
                is_ota_prepaid, suggest_ota_settlement_head)
            ota_settled_amount = 0.0
            if is_ota_prepaid(reservation):
                # Only post if no room-revenue OTA settlement exists yet
                _existing_ota_settle = Payment.query.join(PaymentMode).filter(
                    Payment.reservation_id == reservation.id,
                    Payment.is_voided == False,
                    PaymentMode.category == 'ota_receivable',
                ).first()
                if not _existing_ota_settle:
                    ota_head = suggest_ota_settlement_head(reservation.source
                                                            or reservation.market_segment)
                    # Prefer ota_booking_id prefix if source is generic 'OTA'
                    if ota_head and (reservation.source or '').strip().lower() == 'ota' \
                            and reservation.ota_booking_id:
                        # Fall back to generic OTA head if source is unclear
                        pass
                    if ota_head:
                        _room_amt = round(billing_before_pay['room_charges']
                                          - billing_before_pay['discount'], 2)
                        if _room_amt > 0.01:
                            _ota_pmt = Payment(
                                reservation_id=reservation.id,
                                payment_mode_id=ota_head.id,
                                amount=_room_amt,
                                payment_date=get_business_date(),
                                reference_number=(reservation.ota_booking_id or '')[:100],
                                payment_purpose='settlement',
                            )
                            db.session.add(_ota_pmt)
                            db.session.flush()
                            ota_settled_amount = _room_amt
                            logger.info(
                                'OTA auto-settle: res=%d head=%s amount=%.2f source=%s',
                                reservation.id, ota_head.name, _room_amt, reservation.source)

            paying_now_total = ota_settled_amount
            for pm in payment_modes:
                amt_str = request.form.get(f'pm_amount_{pm.id}', '0') or '0'
                try:
                    amt = float(amt_str)
                except (ValueError, TypeError):
                    amt = 0.0
                if amt <= 0:
                    continue
                # Block OTA heads from manual guest-payment form.  They are
                # only posted via OTA auto-settlement above.
                if pm.category == 'ota_receivable':
                    logger.warning(
                        'OTA head %s used in manual checkout form for res=%d — '
                        'skipping (OTA heads auto-post only)', pm.name, reservation.id)
                    continue
                paying_now_total += amt
                pmt = Payment(
                    reservation_id=reservation.id,
                    payment_mode_id=pm.id,
                    amount=amt,
                    payment_date=get_business_date(),
                    payment_purpose='settlement',
                )
                db.session.add(pmt)
                db.session.flush()

            # ── CRITICAL: expire the SQLAlchemy identity-map cache for the
            # payments (and extra_charges) relationship before re-reading.
            # Without this, calculate_stay_amount() iterates the already-loaded
            # collection which does NOT include the payments just flushed above,
            # causing the balance check to see a stale (pre-payment) balance.
            db.session.expire(reservation, ['payments', 'extra_charges'])

            # Re-calculate after new payments — uses fresh DB data
            billing = calculate_stay_amount(reservation)

            # ── Company credit ────────────────────────────────────────────────
            credit_amount = 0.0
            credit_amount_raw = request.form.get('credit_amount', '0')
            try:
                credit_amount = float(credit_amount_raw) if credit_amount_raw else 0.0
            except ValueError:
                credit_amount = 0.0

            if credit_amount < 0:
                db.session.rollback()
                flash('Company credit amount cannot be negative.', 'danger')
                return render_template('checkout.html', reservation=reservation,
                                       billing=billing, payment_modes=payment_modes,
                                       business_date=get_business_date(),
                                       inv_settings=inv_settings)

            if credit_amount > 0:
                if not (reservation.checkin_record and reservation.checkin_record.company_id):
                    db.session.rollback()
                    flash('No company linked to this reservation for billing credit.', 'danger')
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
                if credit_amount > billing['balance'] + 0.01:
                    db.session.rollback()
                    flash(
                        f'Credit amount ₹{credit_amount:,.2f} exceeds outstanding '
                        f'balance ₹{billing["balance"]:,.2f}.', 'danger'
                    )
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)

            # ── Overpayment handling ──────────────────────────────────────────
            # v2.2.16 FIX 1 — overpayment detection must use the ROUNDED
            # settlement basis (settlement_balance), never the paise-level
            # `balance`. settlement_balance is computed against
            # rounded_grand_total — the exact figure the guest is invoiced
            # and pays. Using `balance` here flagged a guest who paid the
            # printed invoice total as "Overpaid ₹0.xx", forcing a bogus
            # refund/tip/income/upsell resolution. The final shortfall gate
            # below already uses settlement_balance; this aligns the
            # overpayment branch with it.
            _settle = billing.get('settlement_balance', billing['balance'])
            if _settle < -0.01:
                overpay_amount   = round(abs(_settle), 2)
                overpay_reason   = request.form.get('overpay_reason',     '').strip() or 'mistake'
                overpay_res      = request.form.get('overpay_resolution', '').strip()

                # Server-side validation — resolution is mandatory
                if overpay_res not in ('refund', 'tip', 'income', 'upsell'):
                    db.session.rollback()
                    flash('Please select how to resolve the overpayment before checking out.', 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = calculate_stay_amount(reservation)
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)

                # Collect sub-fields
                refund_mode_id = None
                waiter_name    = None
                remarks        = None

                if overpay_res == 'refund':
                    rm_raw = request.form.get('overpay_refund_mode', '').strip()
                    if not rm_raw:
                        db.session.rollback()
                        flash('Please select a Refund Mode for the overpayment.', 'danger')
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               checkout_debug=None)
                    try:
                        refund_mode_id = int(rm_raw)
                    except ValueError:
                        refund_mode_id = None
                    remarks = request.form.get('overpay_refund_remarks', '').strip() or None

                elif overpay_res == 'tip':
                    waiter_name = request.form.get('overpay_waiter_name', '').strip()
                    if not waiter_name:
                        db.session.rollback()
                        flash('Waiter / Staff Name is required when recording a tip.', 'danger')
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               checkout_debug=None)
                    remarks = request.form.get('overpay_tip_remarks', '').strip() or None
                    # Post tip as an ExtraCharge so it clears the negative balance.
                    # charge_type='tip' + charge_category='Tip' is what tells the GST
                    # engine this is a funds-reclassification line, not a taxable
                    # supply — no GST is computed on it (kills the ghost-balance trap).
                    label = f'Tip — {waiter_name}'
                    db.session.add(ExtraCharge(
                        reservation_id=reservation.id,
                        description=label,
                        amount=overpay_amount,
                        charge_date=get_business_date(),
                        charge_type='tip',
                        charge_category='Tip',
                    ))
                    db.session.flush()
                    db.session.expire(reservation, ['payments', 'extra_charges'])
                    billing = calculate_stay_amount(reservation)

                elif overpay_res == 'income':
                    remarks = request.form.get('overpay_income_remarks', '').strip()
                    if not remarks:
                        db.session.rollback()
                        flash('Remarks are required when adjusting overpayment as Other Income.', 'danger')
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               checkout_debug=None)
                    # Post to other income so it clears the negative balance.
                    # charge_type='other_income' + charge_category='Other Income' is
                    # what tells the GST engine this is a funds-reclassification line,
                    # not a taxable supply — no GST is computed on it (kills the
                    # ghost-balance trap where the resolution ExtraCharge re-introduced
                    # an unpayable rounding remainder).
                    db.session.add(ExtraCharge(
                        reservation_id=reservation.id,
                        description=f'Other Income — {remarks}',
                        amount=overpay_amount,
                        charge_date=get_business_date(),
                        charge_type='other_income',
                        charge_category='Other Income',
                    ))
                    db.session.flush()
                    db.session.expire(reservation, ['payments', 'extra_charges'])
                    billing = calculate_stay_amount(reservation)

                elif overpay_res == 'upsell':
                    # The room was sold above standard tariff (guest paid the
                    # higher offered rate). Convert the excess into UPSELL
                    # revenue: bumps rate_per_night, posts a corrective room_rent
                    # ExtraCharge so the upsell flows through the room-revenue
                    # ledger, and stamps the reservation as UPSELL with the new
                    # adjustment amount. After this, the bill matches what the
                    # guest paid and checkout proceeds normally.
                    remarks = request.form.get('overpay_upsell_remarks', '').strip() or None
                    from app.services import convert_overpayment_to_upsell
                    _result = convert_overpayment_to_upsell(
                        reservation,
                        overpay_gross=overpay_amount,
                        reason=remarks,
                        authorized_by_user_id=(current_user.id
                                               if current_user.is_authenticated else None),
                    )
                    if not _result.get('ok'):
                        db.session.rollback()
                        flash(_result.get('error') or
                              'Could not convert overpayment to upsell.', 'danger')
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               checkout_debug=None)
                    db.session.flush()
                    db.session.expire(reservation, ['payments', 'extra_charges'])
                    billing = calculate_stay_amount(reservation)

                # Write overpayment audit log
                from app.models import OverpaymentLog
                db.session.add(OverpaymentLog(
                    reservation_id      = reservation.id,
                    guest_id            = reservation.guest_id,
                    overpaid_amount     = overpay_amount,
                    reason              = overpay_reason,
                    resolution          = overpay_res,
                    refund_mode_id      = refund_mode_id,
                    waiter_name         = waiter_name,
                    remarks             = remarks,
                    resolved_by_user_id = current_user.id if current_user.is_authenticated else None,
                ))
                db.session.flush()

            # ── Individual Credit Checkout ───────────────────────────────────
            # Allows checkout with outstanding balance for individual guests
            # (no company linked). Requires Manager/Admin approval, a reason,
            # and the approver name. The outstanding amount is recorded on the
            # reservation and tracked in the Credit Ledger; it is NOT counted
            # as revenue (revenue stays in NightAuditLog snapshot).
            individual_credit_taken = False
            individual_credit_amt   = 0.0
            ind_credit_enabled = request.form.get('individual_credit_enabled') == '1'
            if ind_credit_enabled:
                # Block if a company is linked — they should use company credit instead
                if reservation.checkin_record and reservation.checkin_record.company_id:
                    db.session.rollback()
                    flash('This reservation is linked to a company — use Company Credit, not Individual Credit.', 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = calculate_stay_amount(reservation)
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
                # Role gate
                if not (current_user.is_authenticated and current_user.has_role('Admin', 'Manager')):
                    db.session.rollback()
                    flash('Individual Credit Checkout requires Manager or Admin authorisation.', 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = calculate_stay_amount(reservation)
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
                ind_reason   = (request.form.get('individual_credit_reason')      or '').strip()
                ind_approver = (request.form.get('individual_credit_approved_by') or '').strip()
                if not ind_reason or not ind_approver:
                    db.session.rollback()
                    flash('Credit Reason and Approved By are mandatory for Individual Credit Checkout.', 'danger')
                    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                    billing = calculate_stay_amount(reservation)
                    return render_template('checkout.html', reservation=reservation,
                                           billing=billing, payment_modes=payment_modes,
                                           checkout_debug=None)
                # Compute outstanding-after-payments-and-company-credit
                _outstanding = round(float(billing['balance']) - float(credit_amount), 2)
                if _outstanding <= 0.01:
                    # Nothing actually outstanding — silently ignore the credit flag
                    individual_credit_taken = False
                else:
                    # ── Apr 2026 Section 4: per-credit limit + Admin gate ──
                    # Hard ceiling: refuse outright when above the
                    # global limit (regardless of role).
                    from app.services import (
                        get_individual_credit_default_limit as _gicdl,
                        get_individual_credit_admin_threshold as _gicat,
                    )
                    _limit     = _gicdl()
                    _threshold = _gicat()
                    _is_admin  = bool(current_user.is_authenticated and current_user.has_role('Admin'))

                    if _outstanding > _limit + 0.01:
                        db.session.rollback()
                        flash(f'Individual Credit ₹{_outstanding:,.2f} exceeds the '
                              f'hard limit of ₹{_limit:,.0f}. Reduce, settle, or '
                              f'use Company Credit if applicable.', 'danger')
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               checkout_debug=None)

                    # Above-threshold credits require Admin (not Manager)
                    if _outstanding > _threshold + 0.01 and not _is_admin:
                        db.session.rollback()
                        flash(f'Individual Credit ₹{_outstanding:,.2f} exceeds the '
                              f'₹{_threshold:,.0f} approval threshold — Admin authorisation required.',
                              'danger')
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               checkout_debug=None)

                    individual_credit_taken = True
                    individual_credit_amt   = _outstanding
                    reservation.credit_amount             = individual_credit_amt
                    reservation.credit_reason             = ind_reason[:200]
                    reservation.credit_approved_by_user_id = current_user.id
                    reservation.credit_approved_at        = datetime.utcnow()
                    # Audit log — same shape as before, plus the threshold context
                    _audit_action = ('individual_credit_admin_approved'
                                     if _outstanding > _threshold + 0.01
                                     else 'individual_credit_posted')
                    _write_audit('Reservation', reservation.id, _audit_action,
                                 None,
                                 {'amount': individual_credit_amt,
                                  'reason': ind_reason[:200],
                                  'approver_user_id':   current_user.id,
                                  'approver_name':      ind_approver[:100],
                                  'approver_is_admin':  _is_admin,
                                  'admin_threshold':    _threshold,
                                  'global_limit':       _limit,
                                  'above_threshold':    _outstanding > _threshold + 0.01})

            # ── Balance check ─────────────────────────────────────────────────
            # Use the SETTLEMENT BALANCE (computed against the rounded
            # grand_total) — this is what the guest was actually charged
            # on the invoice. Without this, a ₹1800.50 bill rounded to
            # ₹1801 and paid ₹1801 would falsely show "Overpaid 0.50".
            remaining = billing.get('settlement_balance', billing['balance']) - credit_amount
            manager_override = request.form.get('manager_override_checkout') == '1' or individual_credit_taken

            # ── Debug logging (visible in server logs) ────────────────────────
            from flask import current_app
            current_app.logger.info(
                '[CHECKOUT DEBUG] res=%d  total_bill=%.2f  extra=%.2f  disc=%.2f  '
                'paid_before_checkout=%.2f  paying_now_form=%.2f  final_paid=%.2f  '
                'final_outstanding=%.2f  credit=%.2f  override=%s',
                reservation.id,
                billing['total'],
                billing['extra_charges'],
                billing['discount'],
                billing_before_pay['paid'],
                paying_now_total,
                billing['paid'],
                remaining,
                credit_amount,
                manager_override,
            )

            # Allow up to 1 paisa rounding tolerance; anything > 0.01 is a real shortfall
            if remaining > 0.01 and not manager_override:
                db.session.rollback()
                flash(
                    f'Cannot checkout: outstanding balance of ₹{remaining:,.2f}. '
                    f'Add more payments, credit to company, or use Manager Override.',
                    'danger'
                )
                # Pass debug info for Admin/Manager so they can diagnose
                _dbg = None
                if current_user.has_role('Admin', 'Manager'):
                    _dbg = {
                        'total_bill':      billing['total'],
                        'already_paid':    billing_before_pay['paid'],
                        'paying_now':      paying_now_total,
                        'final_paid':      billing['paid'],
                        'final_outstanding': remaining,
                    }
                return render_template('checkout.html', reservation=reservation,
                                       billing=billing, payment_modes=payment_modes,
                                       checkout_debug=_dbg)

            # Complete checkout
            reservation.status = 'CheckedOut'
            reservation.checked_out_at = datetime.utcnow()
            reservation.checkout_by = current_user.username if current_user.is_authenticated else ''

            # ── Apr 2026 Section 5: freeze invoice rounding snapshot ──
            # At checkout success, store the 5 rounding-reconciliation
            # values on the reservation. Reports use these instead of
            # recomputing from live tables — guaranteeing the displayed
            # total never drifts due to later voids, edits, or the
            # paise-vs-rounded difference.
            try:
                _final_billing = billing  # already recomputed after payments
                reservation.invoice_taxable_total         = _final_billing.get('total')
                reservation.invoice_gst_total             = _final_billing.get('gst_amount')
                reservation.invoice_unrounded_grand_total = _final_billing.get('grand_total')
                reservation.invoice_rounded_grand_total   = _final_billing.get('rounded_grand_total')
                reservation.invoice_round_off_amount      = _final_billing.get('round_off')
                reservation.invoice_finalised_at          = datetime.utcnow()
            except Exception:
                # Non-fatal — checkout still completes if the snapshot
                # write fails for some unrelated reason.
                logger.exception('checkout: invoice rounding snapshot failed for res=%d',
                                 reservation.id)

            if reservation.room:
                reservation.room.status = 'Dirty'

            # Update company credit (with limit enforcement)
            _credit_posted = 0.0
            if credit_amount > 0 and reservation.checkin_record and reservation.checkin_record.company_id:
                from app.models import Company
                company = db.session.get(Company, reservation.checkin_record.company_id)
                if company:
                    available_credit = float(company.credit_limit or 0) - float(company.credit_used or 0)
                    # Enforce limit (credit_limit > 0 means limit is set; 0 = no credit line)
                    if float(company.credit_limit or 0) > 0 and available_credit < credit_amount:
                        flash(f'Company credit limit exceeded. Available: ₹{available_credit:,.0f}, Requested: ₹{credit_amount:,.0f}. Reduce company credit or get manager override.', 'danger')
                        db.session.rollback()
                        payment_modes = PaymentMode.query.filter_by(is_active=True).all()
                        billing = calculate_stay_amount(reservation)
                        return render_template('checkout.html', reservation=reservation,
                                               billing=billing, payment_modes=payment_modes,
                                               today=get_business_date())
                    old_used = float(company.credit_used or 0)
                    company.credit_used = old_used + credit_amount
                    _credit_posted = credit_amount
                    _write_audit('Company', company.id, 'credit_posted',
                                 {'credit_used': old_used},
                                 {'credit_used': old_used + credit_amount,
                                  'reservation_id': reservation.id,
                                  'amount': credit_amount})
            elif remaining > 1 and manager_override and reservation.checkin_record and reservation.checkin_record.company_id:
                from app.models import Company
                company = db.session.get(Company, reservation.checkin_record.company_id)
                if company:
                    available_credit = float(company.credit_limit or 0) - float(company.credit_used or 0)
                    # credit_limit=0 with no explicit unlimited flag → no credit line, don't post
                    if float(company.credit_limit or 0) > 0:
                        post_amount = min(remaining, available_credit)
                    else:
                        # No credit limit set — manager override posts full remaining
                        post_amount = remaining
                    if post_amount > 0:
                        old_used = float(company.credit_used or 0)
                        company.credit_used = old_used + post_amount
                        _credit_posted = post_amount
                        _write_audit('Company', company.id, 'credit_posted_override',
                                     {'credit_used': old_used},
                                     {'credit_used': old_used + post_amount,
                                      'reservation_id': reservation.id,
                                      'amount': post_amount,
                                      'manager_override': True})

            # Record how much credit was posted on the check-in record
            if _credit_posted > 0 and reservation.checkin_record:
                reservation.checkin_record.company_credit_posted = _credit_posted

            # Write audit log BEFORE commit so it's in the same transaction
            _write_audit('Reservation', reservation.id, 'checkout',
                         {'status': 'CheckedIn'},
                         {'status': 'CheckedOut', 'balance_at_checkout': float(billing['balance'])})

            # Award loyalty points (atomic with checkout)
            try:
                from app.loyalty import award_checkout_points
                guest = reservation.guest
                if guest and guest.loyalty_number:
                    award_checkout_points(reservation,
                                          user_id=current_user.id if current_user.is_authenticated else None)
                if guest:
                    guest.total_stays = (guest.total_stays or 0) + 1
            except Exception as _loyalty_err:
                logger.warning('Loyalty point award failed (non-blocking): %s', _loyalty_err)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error('Checkout failed: %s', e, exc_info=True)
            flash(f'Checkout failed: {e}', 'danger')
            payment_modes = PaymentMode.query.filter_by(is_active=True).all()
            billing = calculate_stay_amount(reservation)
            return render_template('checkout.html', reservation=reservation,
                                   billing=billing, payment_modes=payment_modes,
                                   checkout_debug=None)

        # Thank-you WhatsApp notification (non-blocking)
        try:
            from flask import current_app
            from app.notifications import notify_checkout_thanks
            billing_final = calculate_stay_amount(reservation)
            notify_checkout_thanks(
                reservation,
                total_paid=float(billing_final.get('paid', 0)),
                app=current_app._get_current_object()
            )
        except Exception:
            pass

        flash('Guest checked out successfully.', 'success')
        return redirect(url_for('main.invoice', reservation_id=reservation.id))

    billing = calculate_stay_amount(reservation)
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()

    # ── Late check-out preview for display (not posted at GET time) ────────
    # Only show preview if today >= departure date (no late fee for early departures)
    late_co_preview = None
    cico_allow_waive = False
    try:
        from app.cico_service import (
            get_cico_settings as _get_cico,
            compute_late_checkout as _calc_late,
            already_has_charge as _already,
        )
        _cico = _get_cico()
        cico_allow_waive = _cico.get('allow_waive', True)
        _now = datetime.now()
        _is_departure_or_later = _now.date() >= reservation.departure_date
        if _cico['late_enabled'] and _is_departure_or_later and not _already(reservation, 'late_checkout'):
            _nights = (reservation.departure_date - reservation.arrival_date).days
            late_co_preview = _calc_late(
                float(reservation.rate_per_night),
                _now.time(),
                _nights,
                rules=_cico,
            )
            if late_co_preview and not late_co_preview['applicable']:
                late_co_preview = None
            # ── CRITICAL: gross-up the late fee with the room GST rate ──
            # The pre-tax `amount` returned above is what the server posts
            # as ExtraCharge. The server's tax pipeline then applies room
            # GST on top — so the front-end MUST add GST too, or it
            # will display a smaller total than the server enforces and
            # collect short payment ("checkout denied after exact pay").
            if late_co_preview and late_co_preview.get('amount', 0) > 0:
                try:
                    from app.gst_service import get_room_gst_rate
                    from decimal import Decimal as _D
                    _rate = get_room_gst_rate(
                        _D(str(reservation.rate_per_night or 0)),
                        getattr(reservation, 'room_type', None)
                    )
                    _rate_pct = float(_rate or 0)
                    _gross = float(late_co_preview['amount']) * (1 + _rate_pct / 100.0)
                    late_co_preview['amount_pretax']  = float(late_co_preview['amount'])
                    late_co_preview['gst_rate']       = _rate_pct
                    late_co_preview['gst_amount']     = round(_gross - float(late_co_preview['amount']), 2)
                    late_co_preview['amount_with_gst'] = round(_gross, 2)
                except Exception:
                    # Failure here means JS just sees the pre-tax amount
                    # (the original behaviour — server still validates).
                    late_co_preview['amount_pretax']  = float(late_co_preview.get('amount', 0))
                    late_co_preview['gst_rate']       = 0.0
                    late_co_preview['gst_amount']     = 0.0
                    late_co_preview['amount_with_gst'] = float(late_co_preview.get('amount', 0))
    except Exception:
        pass
    # ──────────────────────────────────────────────────────────────────────

    from app.models import Payment as _Pmt
    pending_void_count = _Pmt.query.filter_by(
        reservation_id=reservation.id, is_voided=False
    ).count()

    # Loyalty info for checkout UI
    loyalty_info = None
    try:
        from app.loyalty import get_loyalty_balance, get_tier_config
        _g = reservation.guest
        if _g and _g.loyalty_number:
            _bal = get_loyalty_balance(_g.id)
            _cfg = get_tier_config(_g.loyalty_tier or 'Silver')
            loyalty_info = {
                'enrolled': True,
                'balance': _bal,
                'tier': _g.loyalty_tier,
                'loyalty_number': _g.loyalty_number,
                'color': _cfg.color_hex if _cfg else '#6c757d',
                'redemption_value': float(_cfg.redemption_value) if _cfg else 0,
                'max_discount': round(_bal * float(_cfg.redemption_value), 2) if _cfg else 0,
            }
    except Exception:
        pass

    # OTA settlement info (Phase 1) — never allow failures here to 500 checkout
    ota_info = None
    try:
        from app.ota_settlement_service import is_ota_prepaid, suggest_ota_settlement_head
        if is_ota_prepaid(reservation):
            _head = suggest_ota_settlement_head(reservation.source or reservation.market_segment)
            ota_info = {
                'is_ota_prepaid': True,
                'head_name': _head.name if _head else None,
                'head_code': _head.code if _head else None,
                'source': reservation.source,
                'booking_ref': reservation.ota_booking_id,
            }
    except Exception as _ota_err:
        logger.warning('Checkout OTA info lookup failed for res=%d: %s',
                       reservation.id, _ota_err)

    # Audit-lock info — UI uses this to show banner + Admin-override box.
    from app.services import get_locking_audit
    _is_admin = bool(current_user.is_authenticated
                     and current_user.has_role('Admin'))

    def _lock_payload(target_date):
        if target_date is None:
            return None
        row = get_locking_audit(target_date)
        if row is None:
            return None
        return {
            'date':         row.audit_date,
            'date_human':   row.audit_date.strftime('%d %b %Y'),
            'audit_id':     row.id,
            'status':       row.status,
            'completed_at': row.completed_at,
            'is_admin':     _is_admin,
        }

    audit_lock = _lock_payload(reservation.departure_date)

    # Per-payment lock map — drives the override block inside each Void
    # modal so Admin can void a payment that falls in a closed audit date.
    payment_lock_map = {}
    for _p in (reservation.payments or []):
        if _p is None or _p.is_voided:
            continue
        payment_lock_map[_p.id] = _lock_payload(_p.payment_date)

    return render_template('checkout.html', reservation=reservation,
                           billing=billing, payment_modes=payment_modes,
                           checkout_debug=None,
                           late_co_preview=late_co_preview,
                           cico_allow_waive=cico_allow_waive,
                           pending_void_count=pending_void_count,
                           loyalty_info=loyalty_info,
                           ota_info=ota_info,
                           audit_lock=audit_lock,
                           payment_lock_map=payment_lock_map)

@bp.route('/advance-receipt/<int:reservation_id>')
def advance_receipt(reservation_id):
    """Advance Receipt OR Booking Confirmation for a future reservation.

    Critically NOT a tax invoice. Issued for any non-CheckedIn,
    non-CheckedOut reservation. Shows the booking metadata + advance
    payment trail (if any). The page header makes the legal status
    explicit so it's never confused with an invoice.

    Routing rule:
      * status in ('CheckedIn', 'CheckedOut')  → redirect to /invoice/<id>
                                                  (the actual tax invoice)
      * status in ('Reserved', 'Confirmed',     → render this page
                   'Overbooked')
      * status == 'Cancelled'                   → still render (with badge)
      * status == 'NoShow'                      → render (with badge)
    """
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)

    # Stay invoice already exists → redirect there. Never serve an
    # advance receipt for a folio that has already been invoiced.
    if reservation.status in ('CheckedIn', 'CheckedOut'):
        return redirect(url_for('main.invoice', reservation_id=reservation.id))

    # Roll up advance / refund / net for the receipt header.
    from app.services import advance_summary
    adv = advance_summary(reservation)

    # Per-payment breakdown — only purpose='advance' rows are shown
    # (refunds appear as a separate negative line).
    advance_payments = [p for p in (reservation.payments or [])
                        if not p.is_voided
                        and (getattr(p, 'payment_purpose', '') or '').lower() == 'advance']
    refund_payments  = [p for p in (reservation.payments or [])
                        if not p.is_voided
                        and (getattr(p, 'payment_purpose', '') or '').lower() == 'refund']

    # Receipt number — sequential, year-scoped, audit-ready. Allocated on
    # first view and frozen thereafter. Falls back to id-based form ONLY
    # if allocation fails (defensive — we should never see the fallback
    # in normal operation).
    receipt_number = _generate_advance_receipt_number(reservation) \
                     or f'AR-{reservation.id:06d}'
    receipt_date   = reservation.advance_receipt_date or datetime.utcnow()

    # Property settings — reuse the invoice key set so logo / hotel info
    # render identically to the tax invoice. Also pull the GST-on-advance
    # toggle so the template can show GST when the operator opts in.
    _settings_keys = [
        'invoice_logo_filename', 'invoice_show_logo', 'invoice_header',
        'invoice_footer', 'invoice_thankyou',
        'hotel_name', 'hotel_address', 'hotel_contact',
        'hotel_contact_person', 'hotel_email',
        'apply_gst_on_advance', 'advance_gst_rate',
    ]
    inv = {s.key: s.value for s in
           Settings.query.filter(Settings.key.in_(_settings_keys)).all()}

    # GST on advance — disabled by default. When enabled, the receipt
    # shows tax breakdown on the net advance using the configured rate
    # (default 12% — typical for hospitality services in India; verify
    # with your CA before enabling in production).
    apply_gst_on_advance = (inv.get('apply_gst_on_advance') or '').strip().lower() in ('1','true','yes','on')
    try:
        advance_gst_rate = float(inv.get('advance_gst_rate') or 12.0)
    except (TypeError, ValueError):
        advance_gst_rate = 12.0

    advance_gst = None
    if apply_gst_on_advance and adv['net_advance'] > 0.005:
        # Treat the advance amount as TAX-INCLUSIVE (guest paid X total).
        # Reverse-compute the taxable base + GST split.
        gross  = float(adv['net_advance'])
        rate   = max(0.0, advance_gst_rate)
        base   = round(gross * 100.0 / (100.0 + rate), 2) if rate > 0 else gross
        tax    = round(gross - base, 2)
        # 50/50 between CGST/SGST for intra-state. Operator can adjust
        # this in a future polish; current scope: simple 50/50 split.
        cgst   = round(tax / 2.0, 2)
        sgst   = round(tax - cgst, 2)
        advance_gst = {
            'rate':           rate,
            'taxable_amount': base,
            'cgst':           cgst,
            'sgst':           sgst,
            'total_tax':      tax,
            'grand_total':    gross,
        }

    nights = (reservation.departure_date - reservation.arrival_date).days
    return render_template(
        'advance_receipt.html',
        reservation          = reservation,
        receipt_number       = receipt_number,
        receipt_date         = receipt_date,
        advance              = adv,
        advance_payments     = advance_payments,
        refund_payments      = refund_payments,
        nights               = max(0, nights),
        inv                  = inv,
        apply_gst_on_advance = apply_gst_on_advance,
        advance_gst          = advance_gst,
    )


@bp.route('/invoice/<int:reservation_id>')
def invoice(reservation_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)
    billing = calculate_stay_amount(reservation)
    from app.services import get_room_charge_lines, build_rate_breakdown
    room_lines = get_room_charge_lines(reservation)
    from app.gst_service import get_folio_gst_summary, get_hotel_gstin, get_hotel_address
    gst = get_folio_gst_summary(reservation)
    rate_breakdown = build_rate_breakdown(reservation, gst)
    hotel_gstin   = get_hotel_gstin()
    hotel_address = get_hotel_address()

    # ── Load all invoice + property settings in one query ─────────────────
    _ALL_INV_KEYS = [
        'invoice_logo_filename', 'invoice_header', 'invoice_footer',
        'invoice_qr_enabled', 'invoice_template', 'invoice_title',
        'invoice_prefix', 'invoice_location_code', 'invoice_pan',
        'invoice_thankyou', 'invoice_terms',
        'invoice_show_logo', 'invoice_show_signatory',
        'invoice_show_guest_address', 'invoice_show_booking_type',
        'invoice_show_payment_summary', 'invoice_show_gst_breakdown',
        'invoice_show_terms', 'invoice_show_balance_badge',
        'invoice_show_cg_note', 'invoice_show_rate_breakdown',
        'invoice_layout', 'invoice_counter',
        'hotel_name', 'hotel_address', 'hotel_contact',
        'hotel_contact_person', 'hotel_email', 'hotel_cin',
        # Corporate-invoice identity fields (rendered only when present).
        'hotel_website', 'hotel_state_code', 'hotel_fssai',
    ]
    inv = {s.key: s.value for s in
           Settings.query.filter(Settings.key.in_(_ALL_INV_KEYS)).all()}

    # ── Assign sequential invoice number on first view ─────────────────────
    if not reservation.invoice_number:
        inv_no = _generate_invoice_number(reservation, inv)
        if inv_no:
            inv['invoice_number_generated'] = inv_no
        else:
            flash('Failed to generate invoice number. Please try again.', 'danger')

    # ── Settlement status ──────────────────────────────────────────────────
    from app.financial import is_settled, is_zero
    if is_settled(billing['balance']):
        inv_status = 'Settled'
    elif is_zero(billing['paid']):
        inv_status = 'Unsettled'
    else:
        inv_status = 'Partial'

    return render_template(
        'invoice.html',
        reservation=reservation,
        billing=billing,
        room_lines=room_lines,
        rate_breakdown=rate_breakdown,
        gst=gst,
        hotel_gstin=hotel_gstin,
        hotel_address=hotel_address,
        inv=inv,
        inv_status=inv_status,
    )

@bp.route('/invoice/<int:reservation_id>/pdf')
def invoice_pdf(reservation_id):
    """Generate and download a clean PDF of the invoice using xhtml2pdf."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied
    import io
    from flask import current_app
    reservation = Reservation.query.get_or_404(reservation_id)
    billing = calculate_stay_amount(reservation)
    from app.services import get_room_charge_lines, build_rate_breakdown
    room_lines = get_room_charge_lines(reservation)
    from app.gst_service import get_folio_gst_summary, get_hotel_gstin, get_hotel_address
    gst           = get_folio_gst_summary(reservation)
    rate_breakdown = build_rate_breakdown(reservation, gst)
    hotel_gstin   = get_hotel_gstin()
    hotel_address = get_hotel_address()

    _ALL_INV_KEYS = [
        'invoice_logo_filename', 'invoice_header', 'invoice_footer',
        'invoice_qr_enabled', 'invoice_template', 'invoice_title',
        'invoice_prefix', 'invoice_location_code', 'invoice_pan',
        'invoice_thankyou', 'invoice_terms',
        'invoice_show_logo', 'invoice_show_signatory',
        'invoice_show_guest_address', 'invoice_show_booking_type',
        'invoice_show_payment_summary', 'invoice_show_gst_breakdown',
        'invoice_show_terms', 'invoice_show_balance_badge',
        'invoice_show_cg_note', 'invoice_show_rate_breakdown',
        'invoice_layout', 'invoice_counter',
        'hotel_name', 'hotel_address', 'hotel_contact',
        'hotel_contact_person', 'hotel_email', 'hotel_cin',
        # Corporate-invoice identity fields (rendered only when present).
        'hotel_website', 'hotel_state_code', 'hotel_fssai',
    ]
    inv = {s.key: s.value for s in
           Settings.query.filter(Settings.key.in_(_ALL_INV_KEYS)).all()}

    from app.financial import is_settled as _is_s, is_zero as _is_z
    if _is_s(billing['balance']):
        inv_status = 'Settled'
    elif _is_z(billing['paid']):
        inv_status = 'Unsettled'
    else:
        inv_status = 'Partial'

    # Build logo absolute path for PDF embedding
    logo_path = None
    logo_filename = inv.get('invoice_logo_filename')
    if logo_filename and inv.get('invoice_show_logo', 'true') == 'true':
        logo_path = os.path.join(
            current_app.static_folder, 'uploads', logo_filename)
        if not os.path.exists(logo_path):
            logo_path = None

    html = render_template(
        'invoice_pdf.html',
        reservation=reservation,
        billing=billing,
        room_lines=room_lines,
        rate_breakdown=rate_breakdown,
        gst=gst,
        hotel_gstin=hotel_gstin,
        hotel_address=hotel_address,
        inv=inv,
        inv_status=inv_status,
        logo_path=logo_path,
    )

    try:
        from xhtml2pdf import pisa
    except ImportError:
        return Response('xhtml2pdf not installed. Run: pip install xhtml2pdf', status=500)

    buf = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=buf)
    if pisa_status.err:
        return Response('PDF generation failed. Please try Print / PDF instead.', status=500)
    buf.seek(0)

    inv_no = (reservation.invoice_number
              or reservation.booking_reference
              or f'RES-{reservation.id}')
    filename = f'invoice-{inv_no}.pdf'
    return send_file(buf, download_name=filename, as_attachment=True,
                     mimetype='application/pdf')


@bp.route('/housekeeping')
def housekeeping():
    floor_filter = request.args.get('floor', type=int)
    
    query = Room.query.filter_by(status='Dirty')
    if floor_filter:
        query = query.filter_by(floor=floor_filter)
    
    dirty_rooms = query.order_by(Room.room_number).all()
    floors = sorted(set(r.floor for r in Room.query.with_entities(Room.floor).distinct() if r.floor is not None))

    return render_template('housekeeping.html', dirty_rooms=dirty_rooms, floors=floors)

@bp.route('/invoice-manager')
def invoice_manager():
    """
    Production-grade Invoice Manager with KPIs, exception alerts,
    smart filters, enhanced status system, and audit insights.
    """
    from decimal import Decimal
    from app.models import (AuditLog, User, CreditNote, OverpaymentLog,
                            VoidRequest, RevenueAlert, Folio)
    from app.financial import SETTLEMENT_TOLERANCE

    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied

    today     = get_business_date()
    tab       = request.args.get('tab',    'all').strip()
    search    = request.args.get('search', '').strip()
    room_f    = request.args.get('room',   '').strip()
    inv_f     = request.args.get('invoice', '').strip()
    source_f  = request.args.get('source', '').strip()
    mode_f    = request.args.get('mode',   '').strip()
    status_f  = request.args.get('status', '').strip()
    staff_f   = request.args.get('staff',  '').strip()
    date_type = request.args.get('date_type', 'checkout').strip()
    quick     = request.args.get('quick',  '').strip()
    fmt       = request.args.get('format', 'html')

    # Quick filter overrides
    if quick == 'today':
        from_date = to_date = today
    elif quick == 'yesterday':
        from_date = to_date = today - timedelta(days=1)
    elif quick == 'week':
        from_date = today - timedelta(days=6); to_date = today
    elif quick == 'month':
        from_date = today.replace(day=1); to_date = today
    else:
        _default_from = (today - timedelta(days=29)).isoformat()
        from_str = request.args.get('from', _default_from)
        to_str   = request.args.get('to',   today.isoformat())
        try:
            from_date = date.fromisoformat(from_str)
            to_date   = date.fromisoformat(to_str)
        except ValueError:
            from_date = today - timedelta(days=29); to_date = today

    # ── Base query ──────────────────────────────────────────────────
    q = (Reservation.query
         .options(db.joinedload(Reservation.payments).joinedload(Payment.payment_mode),
                  db.joinedload(Reservation.extra_charges),
                  db.joinedload(Reservation.guest),
                  db.joinedload(Reservation.room),
                  db.joinedload(Reservation.checkin_record))
         .filter(Reservation.status == 'CheckedOut'))

    # Date filter by type.
    # checked_out_at is UTC, but user-facing filter dates are local.
    # Use the shared helper to get the matching UTC window.
    from app.services import get_business_day_utc_range
    _utc_from, _utc_to = get_business_day_utc_range(from_date, to_date)
    if date_type == 'invoice':
        q = q.filter(Reservation.checked_out_at >= _utc_from,
                     Reservation.checked_out_at < _utc_to)
    elif date_type == 'arrival':
        q = q.filter(Reservation.arrival_date >= from_date,
                     Reservation.arrival_date <= to_date)
    elif date_type == 'departure':
        q = q.filter(Reservation.departure_date >= from_date,
                     Reservation.departure_date <= to_date)
    else:  # checkout (default)
        q = q.filter(Reservation.checked_out_at >= _utc_from,
                     Reservation.checked_out_at < _utc_to)

    if search:
        _like = f'%{search}%'
        q = (q.join(Reservation.guest, isouter=True)
              .filter(db.or_(Guest.name.ilike(_like), Guest.phone.ilike(_like))))
    if room_f:
        q = (q.join(Reservation.room, isouter=True)
              .filter(Room.room_number.ilike(f'%{room_f}%')))
    if inv_f:
        q = q.filter(db.or_(
            Reservation.invoice_number.ilike(f'%{inv_f}%'),
            Reservation.booking_reference.ilike(f'%{inv_f}%')))
    if source_f:
        q = q.filter(Reservation.source == source_f)

    all_reservations = q.order_by(Reservation.checked_out_at.desc()).all()

    _tol = float(SETTLEMENT_TOLERANCE)

    # ── Billing & status for each reservation ───────────────────────
    def _billing(res):
        nights  = max((res.departure_date - res.arrival_date).days, 1)
        room_ch = Decimal(str(res.rate_per_night or 0)) * Decimal(nights)
        extras  = [ec for ec in res.extra_charges if ec.charge_type != 'room_rent']
        extra_total = sum(Decimal(str(ec.amount or 0)) for ec in extras)
        discount = Decimal(str(getattr(res, 'discount_amount', None) or 0))
        gross   = room_ch + extra_total - discount

        valid_payments = [p for p in res.payments if not p.is_voided]
        paid    = sum(Decimal(str(p.amount or 0)) for p in valid_payments)
        voided  = sum(Decimal(str(p.amount or 0)) for p in res.payments if p.is_voided)

        # Company credit
        ci_rec = res.checkin_record
        credit  = Decimal(str(ci_rec.company_credit_posted if ci_rec else 0))

        balance = gross - paid - credit
        return {
            'nights': nights,
            'room_charges': float(room_ch),
            'extra_charges': float(extra_total),
            'discount': float(discount),
            'gross': float(gross),
            'paid': float(paid),
            'credit': float(credit),
            'voided': float(voided),
            'balance': float(balance),
        }

    def _status(b):
        bal = b['balance']
        if b['voided'] > 0 and b['paid'] <= _tol:
            return 'Voided'
        if bal < -_tol:
            return 'Overpaid'
        if bal <= _tol:
            if b['credit'] > _tol:
                return 'Credit'
            return 'Paid'
        if b['paid'] <= _tol and b['credit'] <= _tol:
            return 'Unpaid'
        return 'Partial'

    _STATUS_COLORS = {
        'Paid': 'success', 'Partial': 'warning', 'Unpaid': 'danger',
        'Credit': 'info', 'Overpaid': 'purple', 'Voided': 'secondary',
    }

    def _modes(res):
        m = {}
        for p in res.payments:
            if not p.is_voided and p.payment_mode:
                m[p.payment_mode.name] = m.get(p.payment_mode.name, 0.0) + float(p.amount)
        return m

    all_rows = []
    for res in all_reservations:
        b = _billing(res)
        st = _status(b)
        all_rows.append({
            'reservation': res,
            'billing': b,
            'status': st,
            'status_color': _STATUS_COLORS.get(st, 'secondary'),
            'modes': _modes(res),
        })

    # ── Filter by status / mode / tab ───────────────────────────────
    if status_f:
        all_rows = [r for r in all_rows if r['status'] == status_f]
    if mode_f:
        all_rows = [r for r in all_rows if mode_f in r['modes']]

    # Tab shortcuts
    if   tab == 'pending':  rows = [r for r in all_rows if r['status'] in ('Unpaid', 'Partial')]
    elif tab == 'paid':     rows = [r for r in all_rows if r['status'] == 'Paid']
    elif tab == 'credit':   rows = [r for r in all_rows if r['status'] == 'Credit']
    elif tab == 'overpaid': rows = [r for r in all_rows if r['status'] == 'Overpaid']
    elif tab == 'voided':   rows = [r for r in all_rows if r['status'] == 'Voided']
    else:                   rows = all_rows

    # ── KPI Summary ─────────────────────────────────────────────────
    total_billed    = round(sum(r['billing']['gross']   for r in all_rows), 2)
    total_collected = round(sum(r['billing']['paid']    for r in all_rows), 2)
    total_pending   = round(sum(max(r['billing']['balance'], 0) for r in all_rows), 2)
    total_credit    = round(sum(r['billing']['credit']  for r in all_rows), 2)
    total_voided    = round(sum(r['billing']['voided']  for r in all_rows), 2)
    total_overpaid  = round(abs(sum(min(r['billing']['balance'], 0) for r in all_rows)), 2)
    avg_invoice     = round(total_billed / len(all_rows), 2) if all_rows else 0

    status_counts = {}
    for r in all_rows:
        status_counts[r['status']] = status_counts.get(r['status'], 0) + 1

    summary = {
        'count': len(all_rows),
        'total_billed': total_billed,
        'total_collected': total_collected,
        'total_pending': total_pending,
        'total_credit': total_credit,
        'total_voided': total_voided,
        'total_overpaid': total_overpaid,
        'avg_invoice': avg_invoice,
        'status_counts': status_counts,
    }

    # ── Exception alerts ────────────────────────────────────────────
    exceptions = []

    # Pending checkouts not yet invoiced
    pending_co = Reservation.query.filter(
        Reservation.status == 'CheckedIn',
        Reservation.departure_date <= today
    ).count()
    if pending_co:
        exceptions.append({
            'label': f'{pending_co} Pending Checkout(s)',
            'color': 'danger', 'icon': 'bi-door-open',
            'filter': 'tab=pending',
        })

    unpaid_ct = status_counts.get('Unpaid', 0) + status_counts.get('Partial', 0)
    if unpaid_ct:
        exceptions.append({
            'label': f'{unpaid_ct} Unpaid Invoice(s)',
            'color': 'danger', 'icon': 'bi-exclamation-triangle',
            'filter': 'tab=pending',
        })

    credit_ct = status_counts.get('Credit', 0)
    if credit_ct:
        exceptions.append({
            'label': f'{credit_ct} Credit Bill(s)',
            'color': 'info', 'icon': 'bi-building',
            'filter': 'tab=credit',
        })

    overpaid_ct = status_counts.get('Overpaid', 0)
    if overpaid_ct:
        exceptions.append({
            'label': f'{overpaid_ct} Overpayment(s)',
            'color': 'warning', 'icon': 'bi-cash-coin',
            'filter': 'tab=overpaid',
        })

    # Revenue alerts (unresolved)
    rev_alerts = RevenueAlert.query.filter_by(resolved=False).count()
    if rev_alerts:
        exceptions.append({
            'label': f'{rev_alerts} Revenue Alert(s)',
            'color': 'danger', 'icon': 'bi-shield-exclamation',
            'filter': '',
        })

    # ── Batch checkout staff ────────────────────────────────────────
    res_ids = [r['reservation'].id for r in rows]
    checkout_user_map = {}
    if res_ids:
        audit_entries = (AuditLog.query
                         .filter(AuditLog.entity_type == 'Reservation',
                                 AuditLog.action == 'checkout',
                                 AuditLog.entity_id.in_(res_ids))
                         .with_entities(AuditLog.entity_id, AuditLog.staff_user_id)
                         .all())
        res_to_staff = {eid: sid for eid, sid in audit_entries}
        staff_ids    = set(res_to_staff.values())
        user_map     = {u.id: u.full_name
                        for u in User.query.filter(User.id.in_(staff_ids)).all()} if staff_ids else {}
        checkout_user_map = {eid: user_map.get(sid, '—')
                             for eid, sid in res_to_staff.items()}

    for r in rows:
        r['checkout_by'] = checkout_user_map.get(r['reservation'].id, '—')

    # Staff filter (post-attribution)
    if staff_f:
        rows = [r for r in rows if staff_f.lower() in r['checkout_by'].lower()]

    # ── Footer totals (for filtered rows only) ──────────────────────
    footer = {
        'gross':   round(sum(r['billing']['gross']   for r in rows), 2),
        'paid':    round(sum(r['billing']['paid']    for r in rows), 2),
        'balance': round(sum(r['billing']['balance'] for r in rows), 2),
        'credit':  round(sum(r['billing']['credit']  for r in rows), 2),
        'voided':  round(sum(r['billing']['voided']  for r in rows), 2),
        'count':   len(rows),
    }

    # ── Dropdown options for filters ────────────────────────────────
    payment_modes = PaymentMode.query.filter_by(is_active=True).order_by(PaymentMode.name).all()
    sources = db.session.query(Reservation.source).filter(
        Reservation.source.isnot(None)).distinct().all()
    source_list = sorted(set(s[0] for s in sources if s[0]))

    # ── Excel export ────────────────────────────────────────────────
    if fmt == 'excel':
        import io as _io
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
        except ImportError:
            return Response('openpyxl not installed.', status=500)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Invoice Manager'
        hdr_fill = PatternFill('solid', fgColor='1F4E79')
        hdr_font = Font(color='FFFFFF', bold=True)
        ws.append([f'Invoice Manager — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'])
        ws.cell(1, 1).font = Font(bold=True, size=13)
        ws.append([f'Tab: {tab.capitalize()}  |  Rows: {len(rows)}'])
        ws.append([])
        headers = ['Invoice No.', 'Checkout Date', 'Guest Name', 'Phone', 'Room',
                   'Source', 'Arrival', 'Departure', 'Nights',
                   'Room Charges', 'Extras', 'Discount', 'Gross Total',
                   'Paid', 'Credit', 'Balance', 'Status', 'Payment Modes', 'Checkout By']
        hr = ws.max_row + 1
        ws.append(headers)
        for ci, _ in enumerate(headers, 1):
            c = ws.cell(hr, ci)
            c.fill = hdr_fill; c.font = hdr_font
            c.alignment = Alignment(horizontal='center')
        for r in rows:
            res = r['reservation']; b = r['billing']
            ws.append([
                res.invoice_number or res.booking_reference or f'RES-{res.id}',
                res.checked_out_at.date().isoformat() if res.checked_out_at else '',
                res.guest.name  if res.guest else '',
                res.guest.phone if res.guest else '',
                res.room.room_number if res.room else '',
                res.source or '',
                res.arrival_date.isoformat(), res.departure_date.isoformat(),
                b['nights'], b['room_charges'], b['extra_charges'], b['discount'],
                b['gross'], b['paid'], b['credit'], b['balance'],
                r['status'],
                ', '.join(f'{k}: {v:,.0f}' for k, v in r['modes'].items()),
                r['checkout_by'],
            ])
        for ci in range(1, len(headers) + 1):
            max_len = max((len(str(ws.cell(row, ci).value or ''))
                           for row in range(1, ws.max_row + 1)), default=10)
            ws.column_dimensions[get_column_letter(ci)].width = min(max_len + 4, 40)
        buf = _io.BytesIO()
        wb.save(buf); buf.seek(0)
        return send_file(buf, download_name=f'invoice_manager_{tab}_{from_date}_{to_date}.xlsx',
                         as_attachment=True,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # ── Apr 2026 trust fix: empty-state diagnostics ──
    # When the current filters return zero rows, run quick counts against
    # the OTHER date_type values so the UI can suggest "23 invoices exist
    # by Invoice Date — try changing the date type." Costs 3 cheap COUNT
    # queries; only runs when the page would otherwise be blank.
    alt_date_type_counts = {}
    if len(all_rows) == 0:
        try:
            _alt_q = Reservation.query.filter(Reservation.status == 'CheckedOut')
            # Count by checked_out_at (UTC window already computed)
            alt_date_type_counts['checkout'] = (_alt_q
                .filter(Reservation.checked_out_at >= _utc_from,
                        Reservation.checked_out_at < _utc_to)
                .count())
            # Count by arrival_date
            alt_date_type_counts['arrival'] = (_alt_q
                .filter(Reservation.arrival_date >= from_date,
                        Reservation.arrival_date <= to_date)
                .count())
            # Count by departure_date
            alt_date_type_counts['departure'] = (_alt_q
                .filter(Reservation.departure_date >= from_date,
                        Reservation.departure_date <= to_date)
                .count())
            # Lifetime count of CheckedOut (sanity check)
            alt_date_type_counts['lifetime'] = _alt_q.count()
        except Exception:
            alt_date_type_counts = {}

    # Filter summary line for the UI banner
    _date_type_label = {
        'checkout':  'Checkout Date',
        'invoice':   'Invoice Date',
        'arrival':   'Arrival Date',
        'departure': 'Departure Date',
    }.get(date_type, date_type)
    filter_summary = (
        f'Showing invoices from {from_date.strftime("%d %b %Y")} '
        f'to {to_date.strftime("%d %b %Y")} by {_date_type_label}'
    )

    return render_template('invoice_manager.html',
                           rows=rows, summary=summary, footer=footer,
                           exceptions=exceptions, tab=tab,
                           from_date=from_date, to_date=to_date,
                           date_type=date_type, quick=quick,
                           search=search, room_f=room_f, inv_f=inv_f,
                           source_f=source_f, mode_f=mode_f, status_f=status_f,
                           staff_f=staff_f,
                           payment_modes=payment_modes, source_list=source_list,
                           status_options=['Paid','Partial','Unpaid','Credit','Overpaid','Voided'],
                           alt_date_type_counts=alt_date_type_counts,
                           filter_summary=filter_summary)

@bp.route('/api/invoice-detail/<int:reservation_id>')
def invoice_detail_api(reservation_id):
    """AJAX endpoint returning invoice detail JSON for the side drawer."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return jsonify({'error': 'Forbidden'}), 403

    res = Reservation.query.options(
        db.joinedload(Reservation.payments).joinedload(Payment.payment_mode),
        db.joinedload(Reservation.extra_charges),
        db.joinedload(Reservation.guest),
        db.joinedload(Reservation.room),
        db.joinedload(Reservation.checkin_record),
    ).get_or_404(reservation_id)

    billing = calculate_stay_amount(res)

    # Payment history
    payments = []
    for p in sorted(res.payments, key=lambda x: x.created_at or datetime.min):
        payments.append({
            'id': p.id,
            'mode': p.payment_mode.name if p.payment_mode else '?',
            'amount': float(p.amount),
            'date': p.payment_date.strftime('%d %b %Y') if p.payment_date else '',
            'reference': p.reference_number or '',
            'voided': p.is_voided,
            'void_reason': p.void_reason or '',
        })

    # Extra charges — hide night-audit room_rent rows; they're room
    # revenue, displayed in the room-charges block, not under "extras".
    extras = []
    for ec in sorted(res.extra_charges, key=lambda x: x.charge_date or date.min):
        if (ec.charge_type or '') == 'room_rent':
            continue
        extras.append({
            'description': ec.description,
            'amount': float(ec.amount),
            'date': ec.charge_date.strftime('%d %b %Y') if ec.charge_date else '',
            'category': ec.charge_category or '',
            'type': ec.charge_type or '',
        })

    # Audit trail (last 20 entries)
    from app.models import AuditLog, User
    audit = AuditLog.query.filter_by(
        entity_type='Reservation', entity_id=res.id
    ).order_by(AuditLog.timestamp.desc()).limit(20).all()
    audit_trail = []
    staff_ids = set(a.staff_user_id for a in audit)
    staff_map = {u.id: u.full_name for u in User.query.filter(User.id.in_(staff_ids)).all()} if staff_ids else {}
    for a in audit:
        audit_trail.append({
            'action': a.action,
            'staff': staff_map.get(a.staff_user_id, '—'),
            'timestamp': a.timestamp.strftime('%d %b %Y %H:%M') if a.timestamp else '',
            'ip': a.ip_address or '',
        })

    ci = res.checkin_record
    return jsonify({
        'guest': {
            'name': res.guest.name if res.guest else '—',
            'phone': res.guest.phone if res.guest else '',
            'email': res.guest.email if res.guest else '',
        },
        'stay': {
            'room': res.room.room_number if res.room else '—',
            'room_type': res.room_type.name if res.room_type else '',
            'arrival': res.arrival_date.strftime('%d %b %Y'),
            'departure': res.departure_date.strftime('%d %b %Y'),
            'nights': billing.get('nights', 0),
            'source': res.source or '—',
            'invoice_number': res.invoice_number or res.booking_reference or f'RES-{res.id}',
            'checked_out_at': res.checked_out_at.strftime('%d %b %Y %H:%M') if res.checked_out_at else '',
        },
        'billing': {
            'room_charges': billing.get('room_charges', 0),
            'extra_charges': billing.get('extra_charges', 0),
            'discount': billing.get('discount', 0),
            'total': billing.get('total', 0),
            'paid': billing.get('paid', 0),
            'company_credit': billing.get('company_credit', 0),
            'balance': billing.get('balance', 0),
        },
        'company': {
            'name': ci.company.name if ci and ci.company else None,
            'credit_posted': float(ci.company_credit_posted) if ci else 0,
            'billing_ref': ci.company_billing_ref if ci else '',
        },
        'payments': payments,
        'extras': extras,
        'audit_trail': audit_trail,
    })


@bp.route('/housekeeping/<int:room_id>/clean', methods=['POST'])
def mark_clean(room_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Housekeeping')
    if denied:
        return denied
    room = Room.query.get_or_404(room_id)
    if room.status not in ('Dirty', 'Maintenance'):
        flash(f'Room {room.room_number} is {room.status}, not Dirty. Cannot mark clean.', 'warning')
        return redirect(url_for('main.housekeeping'))
    old_status = room.status
    room.status = 'Vacant'
    db.session.commit()
    _write_audit('Room', room.id, 'marked_clean',
                 {'status': old_status}, {'status': 'Vacant'})
    flash(f'Room {room.room_number} marked as clean', 'success')
    return redirect(url_for('main.housekeeping'))

@bp.route('/night-audit')
def night_audit():
    denied = _deny_role('Admin', 'Manager', 'Accountant')
    if denied:
        return denied

    from app.night_audit_service import NightAuditService
    import json as _json

    business_date = BusinessDate.query.first()
    bd = business_date.current_date if business_date else date.today()
    active_tab = request.args.get('tab', 'dashboard')

    # ── Resolve audit_date ──────────────────────────────────────────
    # Precedence:
    #   1. Explicit ?date= param (Analytics/History browsing)
    #   2. Most recent NightAuditLog with status Completed/Warning
    #      → "yesterday's closed audit" view by default
    #   3. Current business date as fallback (first run, no audits yet)
    import json as _json

    date_str = request.args.get('date', '')
    if date_str:
        try:
            audit_date = date.fromisoformat(date_str)
        except ValueError:
            audit_date = bd
    else:
        _last_closed = (NightAuditLog.query
                        .filter(NightAuditLog.status.in_(['Completed', 'Warning']))
                        .order_by(NightAuditLog.audit_date.desc())
                        .first())
        audit_date = _last_closed.audit_date if _last_closed else bd

    # Current log for the selected date
    current_log = NightAuditLog.query.filter_by(audit_date=audit_date).first()
    audit_is_closed = current_log and current_log.status in ('Completed', 'Warning')

    # ── Report data source: snapshot-first for closed audits ─────
    # Closed audits with a VALID stored snapshot_json show FROZEN data
    # (what the numbers were at close time). Live recompute is used for
    # un-closed dates, for a missing or corrupt snapshot, and for a snapshot
    # that has been explicitly invalidated.
    #
    # DEF-004 Phase 5: snapshot_valid is the authority, not status. Reopen
    # sets snapshot_valid=False while deliberately keeping snapshot_json for
    # forensic comparison, and it also moves status off 'Completed'/'Warning'
    # — which is why gating on status alone happened to behave correctly.
    # Any path that invalidates a snapshot WITHOUT changing status, such as
    # the INV-B02 hash-mismatch control, would otherwise keep rendering a
    # snapshot the system has already declared untrustworthy.
    report = None
    exc_summary = None
    panel_ui = None
    panel_explanation = None
    audit_source = 'none'  # 'snapshot' | 'live' | 'none'

    if active_tab in ('dashboard', 'analytics') or request.args.get('format') in ('json', 'print', 'excel'):
        # Try snapshot first for closed audits
        if audit_is_closed and current_log.snapshot_json and current_log.snapshot_valid:
            try:
                report = _json.loads(current_log.snapshot_json)
                audit_source = 'snapshot'
                exc_summary = report.get('exceptions')
                panel_ui = NightAuditService.ui_state(report)
                from app.audit_explanation_service import AuditExplanationService as _AES
                panel_explanation = _AES.explain(report)
            except Exception as _snap_err:
                import logging as _na_log
                _na_log.getLogger(__name__).warning(
                    'Night audit snapshot parse failed for %s: %s — falling back to live',
                    audit_date, _snap_err)
                report = None
                audit_source = 'none'

        # Fall back to live recompute
        if report is None:
            try:
                from app.audit_explanation_service import AuditExplanationService as _AES
                svc = NightAuditService(audit_date)
                report = svc.full_report()
                audit_source = 'live'
                exc_summary = report['exceptions']
                panel_ui = NightAuditService.ui_state(report)
                panel_explanation = _AES.explain(report)
            except Exception:
                report = None
                audit_source = 'none'

    # Fallback exc_summary from stored log when both fail
    if exc_summary is None and current_log:
        exc_summary = {
            'blocker_count': current_log.blocker_count or 0,
            'warning_count': current_log.warning_count or 0,
            'blockers': [],
            'warnings': [],
        }

    # History: last 60 audit logs
    history_logs = (NightAuditLog.query
                    .order_by(NightAuditLog.audit_date.desc())
                    .limit(60).all())

    settings = {s.key: s.value for s in Settings.query.all()}

    return render_template(
        'night_audit_panel.html',
        business_date=business_date,
        bd=bd,
        audit_date=audit_date,
        audit_is_closed=audit_is_closed,
        audit_source=audit_source,
        active_tab=active_tab,
        current_log=current_log,
        report=report,
        exc_summary=exc_summary,
        history_logs=history_logs,
        settings=settings,
        today=date.today(),
        panel_ui=panel_ui,
        panel_explanation=panel_explanation,
    )


@bp.route('/night-audit/settings', methods=['POST'])
def night_audit_settings_save():
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied

    enabled = request.form.get('night_audit_enabled', 'false')
    run_time = request.form.get('night_audit_time', '02:00').strip()

    for key, val in [('night_audit_enabled', enabled), ('night_audit_time', run_time)]:
        s = Settings.query.filter_by(key=key).first()
        if s:
            s.value = val
        else:
            db.session.add(Settings(key=key, value=val))
    db.session.commit()

    # Live-update the scheduler job without requiring a server restart
    from app.services import reschedule_night_audit
    try:
        reschedule_night_audit()
    except Exception:
        logger.warning('Could not reschedule night audit job', exc_info=True)

    flash('Night Audit settings saved.', 'success')
    return redirect(url_for('main.night_audit', tab='settings'))


@bp.route('/night-audit/run', methods=['POST'])
def run_night_audit_manual():
    denied = _deny_role('Admin', 'Manager', 'Accountant')
    if denied:
        return denied
    try:
        run_night_audit()
        # Check what actually happened — was it completed or left pending?
        from app.services import get_business_date
        bd = get_business_date()
        # The audit was for the previous date if it auto-completed (date advanced),
        # or for the current date if it's still pending.
        from datetime import timedelta
        log = NightAuditLog.query.filter_by(audit_date=bd).first()
        prev_log = NightAuditLog.query.filter_by(audit_date=bd - timedelta(days=1)).first()
        audit_log = log or prev_log
        if audit_log and audit_log.status == 'Completed':
            flash('Night audit completed successfully. Business date advanced.', 'success')
        elif audit_log and audit_log.status == 'Pending':
            flash(f'Night audit created but has blockers requiring manual review. {audit_log.notes or ""}', 'warning')
        else:
            flash('Night audit skipped — already exists for current business date.', 'info')
    except Exception as e:
        logger.error('Manual night audit failed: %s', e, exc_info=True)
        flash('Night audit failed. Check logs for details.', 'danger')
    return redirect(url_for('main.night_audit', tab='dashboard'))

@bp.route('/masters')
def masters():
    denied = _deny_role('Admin')
    if denied:
        return denied
    room_types    = RoomType.query.order_by(RoomType.name).all()
    payment_modes = PaymentMode.query.order_by(PaymentMode.name).all()

    _PROP_KEYS = ['hotel_name', 'hotel_address', 'hotel_contact',
                  'hotel_contact_person', 'hotel_gstin', 'hotel_email']
    _INV_KEYS  = [
        'invoice_logo_filename', 'invoice_header', 'invoice_footer',
        'invoice_qr_enabled', 'invoice_template',
        'invoice_title', 'invoice_prefix', 'invoice_location_code',
        'invoice_pan', 'invoice_thankyou', 'invoice_terms',
        'invoice_show_logo', 'invoice_show_signatory',
        'invoice_show_guest_address', 'invoice_show_booking_type',
        'invoice_show_payment_summary', 'invoice_show_gst_breakdown',
        'invoice_show_terms', 'invoice_show_balance_badge',
        'invoice_show_cg_note', 'invoice_layout',
    ]

    prop = {s.key: s.value for s in
            Settings.query.filter(Settings.key.in_(_PROP_KEYS)).all()}
    inv  = {s.key: s.value for s in
            Settings.query.filter(Settings.key.in_(_INV_KEYS)).all()}
    sett = {s.key: s.value for s in Settings.query.all()}

    rooms = (Room.query
             .join(RoomType)
             .order_by(Room.sort_order, Room.floor, Room.room_number)
             .all())

    from app.cico_service import get_cico_settings
    cico = get_cico_settings()

    from app.models import WebhookLog
    webhook_logs = WebhookLog.query.order_by(WebhookLog.received_at.desc()).limit(100).all()

    return render_template('masters.html',
                           room_types=room_types,
                           rooms=rooms,
                           payment_modes=payment_modes,
                           prop=prop, inv=inv, sett=sett,
                           cico=cico,
                           webhook_logs=webhook_logs)


@bp.route('/masters/room-type', methods=['POST'])
def add_room_type():
    denied = _deny_role('Admin')
    if denied:
        return denied
    from decimal import Decimal as _D
    name = request.form.get('name', '').strip()
    rate = request.form.get('rate', type=float)
    if not name or not rate or rate <= 0:
        flash('Name and a positive rate are required.', 'danger')
        return redirect(url_for('main.masters'))
    if RoomType.query.filter_by(name=name).first():
        flash(f'Room type "{name}" already exists.', 'danger')
        return redirect(url_for('main.masters'))
    is_taxable       = request.form.get('is_taxable') == 'on'
    gst_exempted     = not is_taxable
    gst_rate         = 0 if gst_exempted else (request.form.get('gst_rate', type=float) or 0)
    if gst_rate not in (0, 5, 12, 18):
        gst_rate = 0
    is_gst_inclusive = is_taxable and (request.form.get('rate_type') == 'inclusive')
    # Always store base_rate as pre-tax (exclusive). Convert if admin entered inclusive.
    if is_gst_inclusive and gst_rate > 0:
        stored_rate = round(rate / (1 + gst_rate / 100), 2)
    else:
        stored_rate = rate
    room_type = RoomType(
        name             = name,
        base_rate        = stored_rate,
        description      = request.form.get('description', '').strip() or None,
        floor_number     = request.form.get('floor_number', '').strip() or None,
        gst_rate         = gst_rate,
        gst_exempted     = gst_exempted,
        is_gst_inclusive = is_gst_inclusive,
        is_active        = request.form.get('is_active', '1') == '1',
    )
    db.session.add(room_type)
    db.session.commit()
    flash(f'Room type "{name}" added successfully.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/room-type/<int:rt_id>/edit', methods=['POST'])
def edit_room_type(rt_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    rt   = RoomType.query.get_or_404(rt_id)
    name = request.form.get('name', '').strip()
    rate = request.form.get('rate', type=float)
    if not name or not rate or rate <= 0:
        flash('Name and a positive rate are required.', 'danger')
        return redirect(url_for('main.masters'))
    conflict = RoomType.query.filter(RoomType.name == name, RoomType.id != rt_id).first()
    if conflict:
        flash(f'Room type "{name}" already exists.', 'danger')
        return redirect(url_for('main.masters'))
    is_taxable       = request.form.get('is_taxable') == 'on'
    gst_exempted     = not is_taxable
    gst_rate         = 0 if gst_exempted else (request.form.get('gst_rate', type=float) or 0)
    if gst_rate not in (0, 5, 12, 18):
        gst_rate = 0
    is_gst_inclusive = is_taxable and (request.form.get('rate_type') == 'inclusive')
    # Always store base_rate as pre-tax. Convert if admin entered inclusive.
    if is_gst_inclusive and gst_rate > 0:
        stored_rate = round(rate / (1 + gst_rate / 100), 2)
    else:
        stored_rate = rate
    rt.name             = name
    rt.base_rate        = stored_rate
    rt.description      = request.form.get('description', '').strip() or None
    rt.floor_number     = request.form.get('floor_number', '').strip() or None
    rt.gst_rate         = gst_rate
    rt.gst_exempted     = gst_exempted
    rt.is_gst_inclusive = is_gst_inclusive
    rt.is_active        = request.form.get('is_active', '1') == '1'
    db.session.commit()
    flash(f'Room type "{rt.name}" updated.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/room-type/<int:rt_id>/delete', methods=['POST'])
def delete_room_type(rt_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    rt = RoomType.query.get_or_404(rt_id)
    if rt.rooms:
        flash(f'Cannot delete "{rt.name}" — {len(rt.rooms)} room(s) are assigned to this type.', 'danger')
        return redirect(url_for('main.masters'))
    name = rt.name
    db.session.delete(rt)
    db.session.commit()
    flash(f'Room type "{name}" deleted.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/payment-mode', methods=['POST'])
def add_payment_mode():
    denied = _deny_role('Admin')
    if denied:
        return denied
    name = request.form.get('name', '').strip()
    if not name:
        flash('Payment mode name is required.', 'danger')
        return redirect(url_for('main.masters'))
    if PaymentMode.query.filter_by(name=name).first():
        flash(f'Payment mode "{name}" already exists.', 'danger')
        return redirect(url_for('main.masters'))
    pm = PaymentMode(name=name, is_active=request.form.get('is_active', '1') == '1')
    db.session.add(pm)
    db.session.commit()
    flash(f'Payment mode "{name}" added.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/payment-mode/<int:pm_id>/edit', methods=['POST'])
def edit_payment_mode(pm_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    pm   = PaymentMode.query.get_or_404(pm_id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name is required.', 'danger')
        return redirect(url_for('main.masters'))
    conflict = PaymentMode.query.filter(PaymentMode.name == name, PaymentMode.id != pm_id).first()
    if conflict:
        flash(f'Payment mode "{name}" already exists.', 'danger')
        return redirect(url_for('main.masters'))
    pm.name      = name
    pm.is_active = request.form.get('is_active', '1') == '1'
    db.session.commit()
    flash(f'Payment mode "{pm.name}" updated.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/payment-mode/<int:pm_id>/delete', methods=['POST'])
def delete_payment_mode(pm_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    pm   = PaymentMode.query.get_or_404(pm_id)
    used = Payment.query.filter_by(payment_mode_id=pm_id).count()
    if used:
        flash(f'Cannot delete "{pm.name}" — referenced by {used} payment record(s).', 'danger')
        return redirect(url_for('main.masters'))
    name = pm.name
    db.session.delete(pm)
    db.session.commit()
    flash(f'Payment mode "{name}" deleted.', 'success')
    return redirect(url_for('main.masters'))


# ── Rooms Master CRUD ────────────────────────────────────────────────────────

@bp.route('/masters/room', methods=['POST'])
def masters_add_room():
    denied = _deny_role('Admin')
    if denied:
        return denied
    room_number = request.form.get('room_number', '').strip().upper()
    floor       = request.form.get('floor', type=int)
    room_type_id = request.form.get('room_type_id', type=int)
    if not room_number or floor is None or not room_type_id:
        flash('Room number, floor and room type are required.', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')
    if Room.query.filter_by(room_number=room_number).first():
        flash(f'Room {room_number} already exists.', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')
    if not RoomType.query.get(room_type_id):
        flash('Invalid room type.', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')
    room = Room(
        room_number       = room_number,
        room_name         = request.form.get('room_name', '').strip() or None,
        floor             = floor,
        wing              = request.form.get('wing', '').strip() or None,
        room_type_id      = room_type_id,
        max_adults        = request.form.get('max_adults', type=int) or 2,
        max_children      = request.form.get('max_children', type=int) or 2,
        extra_bed_allowed = request.form.get('extra_bed_allowed') == 'on',
        is_active         = request.form.get('is_active', 'on') == 'on',
        is_sellable       = request.form.get('is_sellable', 'on') == 'on',
        is_out_of_order   = request.form.get('is_out_of_order') == 'on',
        maintenance_note  = request.form.get('maintenance_note', '').strip() or None,
        sort_order        = request.form.get('sort_order', type=int) or 0,
        status            = 'Vacant',
    )
    db.session.add(room)
    db.session.commit()
    _write_audit('Room', room.id, 'created', {}, {'room_number': room_number})
    flash(f'Room {room_number} added successfully.', 'success')
    return redirect(url_for('main.masters') + '#pane-rooms')


@bp.route('/masters/room/<int:room_id>/edit', methods=['POST'])
def masters_edit_room(room_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    room = Room.query.get_or_404(room_id)
    room_number  = request.form.get('room_number', '').strip().upper()
    floor        = request.form.get('floor', type=int)
    room_type_id = request.form.get('room_type_id', type=int)
    if not room_number or floor is None or not room_type_id:
        flash('Room number, floor and room type are required.', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')
    conflict = Room.query.filter(Room.room_number == room_number, Room.id != room_id).first()
    if conflict:
        flash(f'Room {room_number} already exists.', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')
    old = {'room_number': room.room_number}
    room.room_number       = room_number
    room.room_name         = request.form.get('room_name', '').strip() or None
    room.floor             = floor
    room.wing              = request.form.get('wing', '').strip() or None
    room.room_type_id      = room_type_id
    room.max_adults        = request.form.get('max_adults', type=int) or 2
    room.max_children      = request.form.get('max_children', type=int) or 2
    room.extra_bed_allowed = request.form.get('extra_bed_allowed') == 'on'
    room.is_active         = request.form.get('is_active') == 'on'
    room.is_sellable       = request.form.get('is_sellable') == 'on'
    room.is_out_of_order   = request.form.get('is_out_of_order') == 'on'
    room.maintenance_note  = request.form.get('maintenance_note', '').strip() or None
    room.sort_order        = request.form.get('sort_order', type=int) or 0
    db.session.commit()
    _write_audit('Room', room.id, 'updated', old, {'room_number': room.room_number})
    flash(f'Room {room.room_number} updated.', 'success')
    return redirect(url_for('main.masters') + '#pane-rooms')


@bp.route('/masters/room/<int:room_id>/toggle', methods=['POST'])
def masters_toggle_room(room_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    room = Room.query.get_or_404(room_id)
    room.is_active = not room.is_active
    db.session.commit()
    state = 'activated' if room.is_active else 'deactivated'
    flash(f'Room {room.room_number} {state}.', 'success')
    return redirect(url_for('main.masters') + '#pane-rooms')


@bp.route('/masters/room/<int:room_id>/delete', methods=['POST'])
def masters_delete_room(room_id):
    denied = _deny_role('Admin')
    if denied:
        return denied
    room = Room.query.get_or_404(room_id)
    num = room.room_number

    if room.status == 'Occupied':
        flash(f'Cannot delete Room {num} — currently occupied.', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')

    # Pre-check ALL foreign-key tables that reference rooms.id.  If any
    # row exists, show a specific reason instead of a generic failure.
    from app.models import (
        Reservation, CheckInRecord, MaintenanceRequest,
        ReservationNightRate, Equipment, PreventiveSchedule,
        EquipmentHealthLog,
    )
    # (label, model, date_column_attr_name) — date column used to find
    # the oldest dependency so the user sees how far back history goes.
    dep_checks = [
        ('reservation(s)',           Reservation,           'arrival_date'),
        ('check-in record(s)',       CheckInRecord,         'checkin_date'),
        ('nightly rate record(s)',   ReservationNightRate,  'stay_date'),
        ('maintenance request(s)',   MaintenanceRequest,    'created_at'),
        ('equipment record(s)',      Equipment,             'created_at'),
        ('preventive schedule(s)',   PreventiveSchedule,    'scheduled_date'),
        ('equipment health log(s)',  EquipmentHealthLog,    'snapshot_date'),
    ]
    blockers = []
    for label, model, date_attr in dep_checks:
        oldest = newest = None
        try:
            count = model.query.filter_by(room_id=room_id).count()
            if count:
                col = getattr(model, date_attr)
                oldest, newest = db.session.query(
                    db.func.min(col), db.func.max(col)
                ).filter(model.room_id == room_id).first()
        except Exception:
            count = 0
        if count:
            def _fmt(d):
                try:
                    return d.strftime('%d %b %Y')
                except Exception:
                    return str(d) if d else None
            since = _fmt(oldest)
            last = _fmt(newest)
            if since and last and since != last:
                blockers.append(f'{count} {label} (first: {since}, last: {last})')
            elif since:
                blockers.append(f'{count} {label} (since {since})')
            else:
                blockers.append(f'{count} {label}')

    if blockers:
        flash(
            f'Cannot delete Room {num}. Historical records exist: '
            f'{"; ".join(blockers)}. Deactivate the room instead to hide it '
            f'from booking while preserving history.',
            'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')

    room_data = {
        'room_number': room.room_number,
        'floor': room.floor,
        'room_type': room.room_type.name if room.room_type else None,
        'status': room.status,
    }
    try:
        db.session.delete(room)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        # Capture the specific FK error for the log, show friendly flash
        logger.error('Room delete FK error for Room %s (id=%d): %s',
                     num, room_id, exc, exc_info=True)
        _msg = str(exc).lower()
        if 'foreign key' in _msg or 'violates' in _msg or 'constraint' in _msg:
            hint = 'It has linked records in another table. Deactivate the room instead.'
        else:
            hint = 'Deactivate the room instead.'
        flash(f'Cannot delete Room {num} — {hint}', 'danger')
        return redirect(url_for('main.masters') + '#pane-rooms')

    # Audit after successful commit so a flush failure cannot roll back the delete
    _write_audit('Room', room_id, 'delete', room_data, {})
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    flash(f'Room {num} deleted successfully.', 'success')
    return redirect(url_for('main.masters') + '#pane-rooms')


@bp.route('/masters/rooms/bulk-add', methods=['POST'])
def bulk_add_rooms():
    """Bulk add rooms from spreadsheet-like UI. Expects JSON {rooms: [...]}."""
    denied = _deny_role('Admin')
    if denied:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    if not data or not data.get('rooms'):
        return jsonify({'success': False, 'error': 'No rooms provided'}), 400

    added = 0
    skipped = []
    for r in data['rooms']:
        room_no = (r.get('room_number') or '').strip()
        if not room_no:
            continue
        # Check for duplicate room number
        if Room.query.filter_by(room_number=room_no).first():
            skipped.append(room_no)
            continue
        floor = r.get('floor', 0)
        rt_id = r.get('room_type_id')
        if not rt_id:
            skipped.append(f'{room_no} (no type)')
            continue

        room = Room(
            room_number=room_no,
            room_name=r.get('room_name', '').strip() or None,
            floor=int(floor),
            wing=r.get('wing', '').strip() or None,
            room_type_id=int(rt_id),
            max_adults=int(r.get('max_adults', 2)),
            max_children=int(r.get('max_children', 2)),
            extra_bed_allowed=bool(r.get('extra_bed_allowed')),
            status='Vacant',
            is_active=True,
            is_sellable=True,
        )
        db.session.add(room)
        added += 1

    if added:
        _write_audit('Room', 0, 'bulk_add', {},
                     {'count': added, 'skipped': skipped})
        db.session.commit()

    msg = f'{added} room(s) added.'
    if skipped:
        msg += f' Skipped: {", ".join(skipped)} (duplicate or missing type).'
    flash(msg, 'success' if added else 'warning')
    return jsonify({'success': True, 'added': added, 'skipped': skipped})


# ---------------------------------------------------------------------------
# Dev-only seed data endpoints
# ---------------------------------------------------------------------------
# Double-gated: both FLASK_ENV=development AND ENABLE_DEV_SEED=1 are required.
# In production either gate is off, so the routes respond 404 and the UI hides.
# The seeder itself lives in app/dev_seed.py and never touches production rows:
# it only deletes what it inserted, tracked via a Settings marker row.

def dev_seed_enabled() -> bool:
    return (os.getenv('FLASK_ENV', 'production') == 'development'
            and os.getenv('ENABLE_DEV_SEED') == '1')


@bp.route('/dev/seed', methods=['POST'])
@login_required
def dev_seed_create():
    if not dev_seed_enabled():
        abort(404)
    denied = _deny_role('Admin')
    if denied:
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    from app.dev_seed import seed
    try:
        result = seed()
    except Exception as exc:
        logger.exception('dev seed failed')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify({'success': True, **result})


@bp.route('/dev/seed/reset', methods=['POST'])
@login_required
def dev_seed_reset():
    if not dev_seed_enabled():
        abort(404)
    denied = _deny_role('Admin')
    if denied:
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    from app.dev_seed import reset
    try:
        result = reset()
    except Exception as exc:
        logger.exception('dev seed reset failed')
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500
    return jsonify({'success': True, **result})


@bp.route('/masters/property', methods=['POST'])
def save_property():
    denied = _deny_role('Admin')
    if denied:
        return denied
    _PROP = {
        'hotel_name':           'Property Name',
        'hotel_address':        'Address',
        'hotel_contact':        'Contact Number',
        'hotel_contact_person': 'Contact Person',
        'hotel_gstin':          'GSTIN',
        'hotel_email':          'Email Address',
    }
    for key, desc in _PROP.items():
        value = request.form.get(key, '').strip()
        s = Settings.query.filter_by(key=key).first()
        if s:
            s.value = value
        else:
            db.session.add(Settings(key=key, value=value, description=desc))
    db.session.commit()
    flash('Property configuration saved.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/invoice-settings', methods=['POST'])
def save_invoice_settings():
    denied = _deny_role('Admin')
    if denied:
        return denied
    from flask import current_app
    import os

    # Text / select fields
    _INV_STR = {
        'invoice_header':         'Invoice Header Text',
        'invoice_footer':         'Invoice Footer Text',
        'invoice_template':       'Invoice Template',
        'invoice_title':          'Invoice Title',
        'invoice_prefix':         'Invoice Number Prefix',
        'invoice_location_code':  'Invoice Location Code',
        'invoice_pan':            'Hotel PAN Number',
        'invoice_thankyou':       'Invoice Thank You Message',
        'invoice_terms':          'Invoice Terms and Conditions',
        'invoice_layout':         'Invoice Print Layout',
    }
    # Boolean toggle fields (checkbox → 'true'/'false')
    _INV_BOOL = {
        'invoice_qr_enabled':           'Invoice QR Code Enabled',
        'invoice_show_logo':            'Show Logo on Invoice',
        'invoice_show_signatory':       'Show Authorized Signatory on Invoice',
        'invoice_show_guest_address':   'Show Guest Address on Invoice',
        'invoice_show_booking_type':    'Show Booking Type on Invoice',
        'invoice_show_payment_summary': 'Show Payment Summary on Invoice',
        'invoice_show_gst_breakdown':   'Show GST Breakdown on Invoice',
        'invoice_show_terms':           'Show Terms on Invoice',
        'invoice_show_balance_badge':   'Show Balance Status Badge on Invoice',
        'invoice_show_cg_note':         'Show Computer Generated Note on Invoice',
    }

    def _upsert_inv(key, value, desc):
        s = Settings.query.filter_by(key=key).first()
        if s:
            s.value = value
        else:
            db.session.add(Settings(key=key, value=value, description=desc))

    for key, desc in _INV_STR.items():
        _upsert_inv(key, request.form.get(key, '').strip(), desc)
    for key, desc in _INV_BOOL.items():
        _upsert_inv(key, 'true' if request.form.get(key) == 'true' else 'false', desc)

    logo_file = request.files.get('invoice_logo')
    if logo_file and logo_file.filename:
        allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = logo_file.filename.rsplit('.', 1)[-1].lower() if '.' in logo_file.filename else ''
        if ext not in allowed:
            flash('Invalid logo type. Allowed: PNG, JPG, GIF, WEBP.', 'danger')
            db.session.commit()
            return redirect(url_for('main.masters'))
        uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        filename = f'invoice_logo.{ext}'
        logo_file.save(os.path.join(uploads_dir, filename))
        s = Settings.query.filter_by(key='invoice_logo_filename').first()
        if s:
            s.value = filename
        else:
            db.session.add(Settings(key='invoice_logo_filename', value=filename,
                                    description='Invoice Logo'))

    db.session.commit()
    flash('Invoice settings saved.', 'success')
    return redirect(url_for('main.masters'))

@bp.route('/masters/settings', methods=['POST'])
def update_settings():
    denied = _deny_role('Admin')
    if denied:
        return denied

    # Boolean settings: checkbox sends 'true' when checked, absent when unchecked
    _BOOL_KEYS = [
        'night_audit_enabled',
        'noshow_fee_enabled',
        'noshow_ota_auto_process',
    ]
    # String/numeric settings
    _STR_KEYS = [
        'night_audit_time',
        'noshow_fee_mode',
        'noshow_fee_amount',
        'hotel_gstin',
        'hotel_state_code',
        'hotel_gst_policy',
        'hotel_cin',
        'void_window_hours',
        'admin_void_window_hours',
        'shift_variance_threshold',
        'high_demand_threshold',
        'google_review_url',
        'cloudflare_tunnel_url',
        'backup_time',
        'monthly_revenue_target',
        'monthly_occupancy_target',
    ]

    def _upsert(key, value, desc=''):
        s = Settings.query.filter_by(key=key).first()
        if s:
            s.value = value
        else:
            db.session.add(Settings(key=key, value=value, description=desc))

    for key in _BOOL_KEYS:
        _upsert(key, 'true' if request.form.get(key) == 'true' else 'false')

    for key in _STR_KEYS:
        value = request.form.get(key, '').strip()
        # Uppercase for GST fields
        if key in ('hotel_gstin', 'hotel_state_code'):
            value = value.upper()
        _upsert(key, value)

    db.session.commit()
    flash('Settings saved successfully.', 'success')
    return redirect(url_for('main.masters'))


@bp.route('/masters/cico-rules', methods=['POST'])
def save_cico_rules():
    """Save Check-in / Check-out Rule Engine settings."""
    denied = _deny_role('Admin')
    if denied:
        return denied

    from app.cico_service import (
        save_cico_settings,
        DEFAULT_EARLY_SLABS, DEFAULT_LATE_SLABS,
    )
    import json as _json

    # Booleans from checkbox fields
    early_enabled = request.form.get('cico_early_enabled') == '1'
    late_enabled  = request.form.get('cico_late_enabled')  == '1'
    allow_waive   = request.form.get('cico_allow_waive')   == '1'
    auto_post     = request.form.get('cico_auto_post')     == '1'
    std_ci        = request.form.get('cico_standard_checkin',  '11:00').strip() or '11:00'
    std_co        = request.form.get('cico_standard_checkout', '11:00').strip() or '11:00'

    # Rebuild early slabs — read time windows, labels, and percentages from form
    early_count = int(request.form.get('cico_early_slab_count', len(DEFAULT_EARLY_SLABS)))
    early_slabs = []
    for i in range(early_count):
        default = DEFAULT_EARLY_SLABS[i] if i < len(DEFAULT_EARLY_SLABS) else {'from_hm': '00:00', 'to_hm': '00:00', 'pct': 0, 'label': ''}
        from_hm = request.form.get(f'cico_early_from_{i}', default['from_hm']).strip() or default['from_hm']
        to_hm   = request.form.get(f'cico_early_to_{i}',   default['to_hm']).strip()   or default['to_hm']
        label   = request.form.get(f'cico_early_label_{i}', default['label']).strip()   or default['label']
        try:
            pct = int(float(request.form.get(f'cico_early_pct_{i}', str(default['pct']))))
        except (ValueError, TypeError):
            pct = default['pct']
        early_slabs.append({'from_hm': from_hm, 'to_hm': to_hm, 'pct': pct, 'label': label})

    # Rebuild late slabs — same pattern
    late_count = int(request.form.get('cico_late_slab_count', len(DEFAULT_LATE_SLABS)))
    late_slabs = []
    for i in range(late_count):
        default = DEFAULT_LATE_SLABS[i] if i < len(DEFAULT_LATE_SLABS) else {'from_hm': '00:00', 'to_hm': '00:00', 'pct': 0, 'label': ''}
        from_hm = request.form.get(f'cico_late_from_{i}', default['from_hm']).strip() or default['from_hm']
        to_hm   = request.form.get(f'cico_late_to_{i}',   default['to_hm']).strip()   or default['to_hm']
        label   = request.form.get(f'cico_late_label_{i}', default['label']).strip()   or default['label']
        try:
            pct = int(float(request.form.get(f'cico_late_pct_{i}', str(default['pct']))))
        except (ValueError, TypeError):
            pct = default['pct']
        late_slabs.append({'from_hm': from_hm, 'to_hm': to_hm, 'pct': pct, 'label': label})

    save_cico_settings({
        'early_enabled': early_enabled,
        'late_enabled':  late_enabled,
        'allow_waive':   allow_waive,
        'auto_post':     auto_post,
        'std_checkin':   std_ci,
        'std_checkout':  std_co,
        'early_slabs':   early_slabs,
        'late_slabs':    late_slabs,
    })
    db.session.commit()
    flash('Check-in / Check-out rules saved.', 'success')
    return redirect(url_for('main.masters') + '#pane-cico')


@bp.route('/ceo')
@login_required
def ceo_dashboard():
    """Owner-only CEO dashboard.

    Renders the empty shell — all data is loaded async via JS from
    /api/ceo/kpi-pack and /api/ai/insights?mode=ceo so the page paints
    fast and never blocks on the LLM call.
    """
    if not current_user.is_app_owner:
        abort(403)
    return render_template('ceo_dashboard.html')


@bp.route('/owner/app-branding')
def app_branding():
    if not current_user.is_app_owner:
        abort(403)
    return render_template('app_branding.html')


@bp.route('/owner/app-branding', methods=['POST'])
def save_app_branding():
    if not current_user.is_app_owner:
        abort(403)
    from flask import current_app
    import os

    # Save app name
    app_name = request.form.get('app_name', '').strip()
    setting = Settings.query.filter_by(key='app_name').first()
    if setting:
        setting.value = app_name
    else:
        db.session.add(Settings(key='app_name', value=app_name,
                                description='App display name in navbar'))

    # Handle logo upload
    logo_file = request.files.get('app_logo')
    if logo_file and logo_file.filename:
        allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = logo_file.filename.rsplit('.', 1)[-1].lower() if '.' in logo_file.filename else ''
        if ext not in allowed:
            flash('Invalid file type. Allowed: PNG, JPG, GIF, WEBP.', 'danger')
            return redirect(url_for('main.app_branding'))
        uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        filename = f'app_logo.{ext}'
        logo_file.save(os.path.join(uploads_dir, filename))
        logo_setting = Settings.query.filter_by(key='app_logo_filename').first()
        if logo_setting:
            logo_setting.value = filename

    db.session.commit()
    flash('App branding updated.', 'success')
    return redirect(url_for('main.app_branding'))

@bp.route('/api/search-guests')
@login_required
def search_guests():
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify([]), 403
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    search_pattern = f'%{query}%'
    guests = Guest.query.filter(
        db.or_(
            Guest.phone.ilike(search_pattern),
            Guest.name.ilike(search_pattern),
            Guest.company.ilike(search_pattern)
        )
    ).limit(10).all()
    
    results = [{
        'id': g.id,
        'name': g.name,
        'phone': g.phone,
        'email': g.email or '',
        'company': g.company or '',
        'folio_no': f'F{g.id:04d}'
    } for g in guests]
    
    return jsonify(results)

@bp.route('/api/reservation/<int:reservation_id>/add-payment', methods=['POST'])
@login_required
def add_payment(reservation_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify({'error': 'Permission denied'}), 403
    from app.services import (calculate_stay_amount, assert_business_date_unlocked,
                              get_business_date, apply_credit_settlement, credit_status)
    from sqlalchemy.exc import IntegrityError

    data = request.get_json() or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400
    payment_mode_id = data.get('payment_mode_id')
    idempotency_key = data.get('idempotency_key', '')

    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    try:
        # Lock the reservation row — this serialises concurrent add_payment
        # calls for the same reservation, making the idempotency-check /
        # insert pair atomic. Without the lock, two double-click submits
        # could both pass the "existing" check before either inserts.
        reservation = (db.session.query(Reservation)
                       .filter_by(id=reservation_id)
                       .with_for_update(of=Reservation)
                       .first())
        if not reservation:
            db.session.rollback()
            return jsonify({'error': 'Reservation not found'}), 404

        # ── Checked-out gate ─────────────────────────────────────────────
        # Historically Add Payment was blocked entirely for CheckedOut
        # reservations. Now it transparently routes credit-checkout folios
        # through apply_credit_settlement(): one button, two flows.
        is_credit_settlement = False
        credit_remaining     = 0.0
        if reservation.status == 'CheckedOut':
            _orig    = float(reservation.credit_amount or 0)
            _settled = float(reservation.credit_settled_amount or 0)
            credit_remaining = max(0.0, round(_orig - _settled, 2))
            if _orig <= 0.005:
                db.session.rollback()
                return jsonify({'error':
                    'Cannot add payment to a checked-out reservation '
                    '(no open credit on this folio).'}), 400
            if credit_remaining <= 0.005:
                db.session.rollback()
                return jsonify({'error':
                    'This credit is already fully settled.'}), 400
            if amount > credit_remaining + 0.01:
                db.session.rollback()
                return jsonify({'error':
                    f'Amount ₹{amount:,.2f} exceeds remaining credit '
                    f'₹{credit_remaining:,.2f}.'}), 400
            is_credit_settlement = True
        # Lock guard: block payment posting on a locked business date
        ok, lock_err = assert_business_date_unlocked(get_business_date(), 'post payment')
        if not ok:
            db.session.rollback()
            return jsonify({'error': lock_err}), 403

        # Idempotency: under the reservation row lock above, this check and
        # the subsequent insert are atomic — a duplicate double-click
        # becomes a quick "already done" response instead of a second row.
        if idempotency_key:
            existing = Payment.query.filter_by(
                reservation_id=reservation_id,
                reference_number=f'idem:{idempotency_key}'
            ).first()
            if existing:
                billing = calculate_stay_amount(reservation)
                db.session.rollback()
                return jsonify({'paid_amount': billing['paid'],
                                'balance': billing['balance'],
                                'duplicate': True})

        # Resolve payment mode — use what was sent, fall back to Cash
        if payment_mode_id:
            payment_mode = db.session.get(PaymentMode, payment_mode_id)
        else:
            payment_mode = PaymentMode.query.filter_by(name='Cash').first()
        if not payment_mode:
            payment_mode = PaymentMode.query.first()
        if not payment_mode:
            db.session.rollback()
            return jsonify({'error': 'No payment mode configured.'}), 500

        # Purpose tag — credit_recovery when this is a post-checkout
        # credit settlement (see is_credit_settlement gate above);
        # settlement otherwise. Never 'advance' here — advance booking
        # uses the new_reservation route only.
        _purpose = 'credit_recovery' if is_credit_settlement else 'settlement'
        payment = Payment(
            reservation_id=reservation_id,
            payment_mode_id=payment_mode.id,
            amount=amount,
            payment_date=get_business_date(),
            reference_number=f'idem:{idempotency_key}' if idempotency_key else None,
            payment_purpose=_purpose,
        )
        db.session.add(payment)
        try:
            db.session.flush()   # get payment.id AND trigger UNIQUE index check
        except IntegrityError:
            # A concurrent request beat us to it. The partial UNIQUE index
            # ux_payment_idem_ref on payments(reference_number) WHERE
            # reference_number LIKE 'idem:%' caught the duplicate. Return
            # the same "duplicate" shape the application-level check returns,
            # so the client can't distinguish whether the lock or the index
            # won the race — both outcomes are equivalent.
            db.session.rollback()
            existing = Payment.query.filter_by(
                reservation_id=reservation_id,
                reference_number=f'idem:{idempotency_key}' if idempotency_key else None,
            ).first()
            if existing:
                billing = calculate_stay_amount(existing.reservation)
                return jsonify({'paid_amount': billing['paid'],
                                'balance': billing['balance'],
                                'duplicate': True})
            # Unexpected — integrity error with no matching row. Let outer
            # except handle reporting.
            raise

        # Write the audit row in the SAME transaction as the payment so
        # they succeed or fail together.
        _write_audit('Payment', payment.id, 'posted',
                     {},
                     {'amount': amount, 'mode': payment_mode.name,
                      'reservation_id': reservation_id,
                      'flow': 'credit_settlement' if is_credit_settlement else 'standard'})

        # Credit-settlement hook — advances credit_settled_amount and
        # stamps credit_settled_at when the receivable hits zero. The
        # helper writes its own audit row (individual_credit_payment_received
        # or individual_credit_settled).
        credit_result = None
        if is_credit_settlement:
            credit_result = apply_credit_settlement(
                reservation, amount,
                by_user_id=current_user.id,
                ref_payment_id=payment.id,
                audit_writer=_write_audit,
            )

        db.session.commit()

        billing = calculate_stay_amount(reservation)
        resp = {'paid_amount': billing['paid'], 'balance': billing['balance']}
        if is_credit_settlement and credit_result is not None:
            resp.update({
                'credit_settlement': True,
                'credit_status':     credit_result['status'],
                'credit_remaining':  credit_result['remaining'],
                'credit_recovered_now': credit_result['recovered_now'],
                'credit_fully_settled': credit_result['fully_settled'],
                'message': ('Credit fully settled.' if credit_result['fully_settled']
                            else f'Partial recovery — ₹{credit_result["remaining"]:,.2f} remaining.'),
            })
        return jsonify(resp)
    except Exception as e:
        db.session.rollback()
        logger.error('add_payment failed reservation_id=%d: %s',
                     reservation_id, e, exc_info=True)
        return jsonify({'error': 'Could not record payment. Please try again.'}), 500

@bp.route('/api/reservation/<int:reservation_id>')
@login_required
def get_reservation(reservation_id):
    from app.services import calculate_stay_amount
    reservation = Reservation.query.get_or_404(reservation_id)
    
    data = {
        'guest_id': reservation.guest.id,
        'guest_name': reservation.guest.name,
        'guest_email': reservation.guest.email,
        'phone': reservation.guest.phone,
        'folio_no': reservation.guest.id,
        'arrival': reservation.arrival_date.strftime('%d %b %Y'),
        'arrival_date': reservation.arrival_date.strftime('%Y-%m-%d'),
        'departure': reservation.departure_date.strftime('%d %b %Y'),
        'departure_date': reservation.departure_date.strftime('%Y-%m-%d'),
        'room_type': reservation.room_type.name,
        'room_type_id': reservation.room_type_id,
        'source': reservation.source or 'Walk-in',
        'status': reservation.status,
        'adults': reservation.adults,
        'children': reservation.children,
        'rate_per_night': reservation.rate_per_night
    }
    
    if reservation.status == 'CheckedIn':
        billing = calculate_stay_amount(reservation)
        data['room_number'] = reservation.room.room_number if reservation.room else 'N/A'
        data['checked_in_at'] = reservation.checked_in_at.strftime('%d %b %Y %I:%M %p') if reservation.checked_in_at else 'N/A'
        data['total_amount'] = billing['total']
        data['paid_amount'] = billing['paid']
        data['balance'] = billing['balance']

    # Open Individual Credit info — drives the Add Payment UI on the slide
    # panel for checked-out folios so the cashier sees remaining receivable
    # without leaving the screen.
    _orig    = float(reservation.credit_amount or 0)
    _settled = float(reservation.credit_settled_amount or 0)
    if _orig > 0.005:
        from app.services import credit_status as _cstat
        _remaining = max(0.0, round(_orig - _settled, 2))
        data['credit'] = {
            'open':       _remaining > 0.005,
            'status':     _cstat(reservation),
            'original':   _orig,
            'recovered':  _settled,
            'remaining':  _remaining,
            'reason':     reservation.credit_reason or '',
        }

    return jsonify(data)

@bp.route('/api/dashboard/<tab_name>')
@login_required
def load_dashboard_tab(tab_name):
    if tab_name == 'analytics':
        return render_template('tabs/analytics.html')
    if tab_name == 'command-center':
        # Accountant gets read access (per Phase-1 approval note) alongside
        # Admin/Manager. FrontDesk and Housekeeping are excluded because the
        # Command Center exposes targets / variance / forecast, which aren't
        # front-line operational concerns. Gate enforced here so a direct URL
        # hit can't serve the shell to unauthorised roles.
        denied = _deny_role('Admin', 'Manager', 'Accountant')
        if denied:
            return denied
        return render_template('tabs/command_center.html')
    return '', 404


# ---------------------------------------------------------------------------
# KPI Command Center — data endpoint (Phase 2: skeleton payload only)
# ---------------------------------------------------------------------------

_CC_VALID_SOURCES     = {'ALL', 'DIRECT', 'OTA', 'CORPORATE', 'AGENT', 'WALKIN'}
_CC_VALID_TREND_MODES = {'6m', '12m', 'fy'}


def _cc_safe_date(raw):
    """Parse YYYY-MM-DD → date, or return None on any failure (never raises)."""
    if not raw:
        return None
    try:
        from datetime import date as _date
        return _date.fromisoformat(raw)
    except Exception:
        return None


def _cc_parse_filters(args) -> dict:
    """Parse + sanitise query params for the Command Center API.

    Every field gets a defined default and never raises — invalid values
    fall back silently so the API keeps responding even when the frontend
    mis-sends a param.
    """
    from app.date_ranges import PRESETS
    preset = (args.get('preset') or 'today').strip()
    if preset not in PRESETS:
        preset = 'today'
    source = (args.get('source') or 'ALL').strip().upper()
    if source not in _CC_VALID_SOURCES:
        source = 'ALL'
    trend_mode = (args.get('trend_mode') or '6m').strip()
    if trend_mode not in _CC_VALID_TREND_MODES:
        trend_mode = '6m'
    return {
        'property_id': (args.get('property_id') or '').strip() or None,
        'preset':      preset,
        'date_from':   _cc_safe_date(args.get('date_from')),
        'date_to':     _cc_safe_date(args.get('date_to')),
        'compare':     args.get('compare') in ('1', 'true', 'on', 'yes'),
        'source':      source,
        'trend_mode':  trend_mode,
        'debug':       args.get('debug') in ('1', 'true'),
    }


def _cc_error_envelope(message: str, status: int = 500):
    """Last-ditch shape for unexpected failures — keeps the frontend alive.

    Every section key the UI reads is present (empty dicts) so no JS lookup
    crashes with ``undefined is not an object``.
    """
    return jsonify({
        'success':  False,
        'metadata': {'error': True, 'message': message, 'phase': '2-skeleton'},
        'filters':  {},
        'quick_answers':   {},
        'summary_cards':   {},
        'sales_vs_target': {},
        'monthly_trend':   {},
        'range_revenue':   {},
        'empty_state':     {'is_empty': True, 'message': message},
    }), status


@bp.route('/api/dashboard/command-center/data')
@login_required
def command_center_data():
    denied = _deny_role('Admin', 'Manager', 'Accountant')
    if denied:
        # _deny_role returns a redirect HTML response; the API needs JSON.
        return _cc_error_envelope('Access denied', status=403)
    try:
        from app.kpi_command_center import build_command_center_payload
        filters = _cc_parse_filters(request.args)
        payload = build_command_center_payload(filters, get_business_date())
        return jsonify(payload)
    except Exception as exc:
        logger.exception('command_center_data failed')
        return _cc_error_envelope(str(exc), status=500)


@bp.route('/api/analytics/data')
@login_required
def analytics_data():
    """Dashboard Analytics data endpoint — DB-agnostic (SQLite + Postgres).

    Returns a JSON payload matching the shape expected by
    ``templates/tabs/analytics.html``:
      - occupancy_trend:  [{date, pct}]   daily % anchored on business_date
      - revenue_trend:    [{date, rev}]   non-voided payments per payment_date
      - booking_sources:  [{source, count}]  arrivals-in-range by Reservation.source
      - current_alos:     float|null      avg (departure-arrival) for CheckedOut
      - alos_trend:       [{date, alos}]
      - room_performance: [{room, bookings, revenue, avg_rate, occ_pct}]

    Date arithmetic and day-by-day iteration are done in Python (not in SQL)
    because earlier versions used Postgres-only ``generate_series`` / ``::date``
    casts / ``LEAST`` / ``GREATEST`` which are not valid SQLite. Python iteration
    is also cheap at any realistic range (365 days max) and keeps the
    aggregation logic inspectable and unit-testable.
    """
    from datetime import date, timedelta
    from decimal import Decimal
    from sqlalchemy import func
    from app.models import Reservation, Payment, Room

    # --- date range (anchor on business date, not system clock) ---
    range_param   = request.args.get('range', '30')
    date_from_str = request.args.get('date_from')
    date_to_str   = request.args.get('date_to')
    today = get_business_date()

    if date_from_str and date_to_str:
        try:
            date_from = date.fromisoformat(date_from_str)
            date_to   = date.fromisoformat(date_to_str)
            if date_from > date_to:
                date_from, date_to = date_to, date_from
        except ValueError:
            date_from, date_to = today - timedelta(days=29), today
    elif range_param == 'today':
        date_from = date_to = today
    else:
        try:
            days = int(range_param)
        except ValueError:
            days = 30
        days = max(1, min(days, 365))  # clamp — avoid runaway ranges
        date_from = today - timedelta(days=days - 1)
        date_to   = today

    num_days    = (date_to - date_from).days + 1
    days_list   = [date_from + timedelta(days=i) for i in range(num_days)]
    total_rooms = db.session.query(func.count(Room.id)).scalar() or 0

    def _d(x):
        """Normalise DB date/datetime return to a ``date``.

        ``datetime`` is a subclass of ``date``, so the naive ``isinstance``
        check won't distinguish them — check ``datetime`` first and call
        ``.date()`` so downstream comparisons stay homogeneous.
        """
        if x is None:
            return None
        if isinstance(x, datetime):
            return x.date()
        return x

    try:
        # 1. Occupancy Trend — reservations active the night of each day
        #    (arrival_date <= day < departure_date), status in in-house/completed.
        #    One range scan, bucket in Python — O(days × stays) but ranges are small.
        active_stays = (
            db.session.query(Reservation.arrival_date, Reservation.departure_date)
            .filter(Reservation.status.in_(('CheckedIn', 'CheckedOut')),
                    Reservation.arrival_date <= date_to,
                    Reservation.departure_date > date_from)
            .all()
        )
        occ_counts = {d: 0 for d in days_list}
        for arr, dep in active_stays:
            arr = _d(arr); dep = _d(dep)
            # Clamp overlap window to the requested range.
            day = max(arr, date_from)
            end = min(dep - timedelta(days=0), date_to + timedelta(days=1))
            while day < end and day <= date_to:
                if day in occ_counts:
                    occ_counts[day] += 1
                day += timedelta(days=1)
        denom = total_rooms if total_rooms > 0 else 1
        occupancy_trend = [
            {'date': d.isoformat(),
             'pct':  round(occ_counts[d] / denom * 100, 1)}
            for d in days_list
        ]

        # 2. Revenue Trend — sum non-voided payments per payment_date
        rev_rows = (
            db.session.query(Payment.payment_date, func.sum(Payment.amount))
            .filter(Payment.is_voided == False,           # noqa: E712 — SQL-level
                    Payment.payment_date >= date_from,
                    Payment.payment_date <= date_to)
            .group_by(Payment.payment_date)
            .all()
        )
        rev_map = {_d(r[0]): float(r[1] or 0) for r in rev_rows if r[0] is not None}
        revenue_trend = [
            {'date': d.isoformat(), 'rev': rev_map.get(d, 0.0)}
            for d in days_list
        ]

        # 3. Booking Sources — arrivals in range, excluding Cancelled/NoShow
        src_rows = (
            db.session.query(Reservation.source, func.count(Reservation.id))
            .filter(Reservation.arrival_date >= date_from,
                    Reservation.arrival_date <= date_to,
                    Reservation.status.notin_(('Cancelled', 'NoShow')))
            .group_by(Reservation.source)
            .all()
        )
        booking_sources = [
            {'source': (s or 'Walk-in'), 'count': int(c)}
            for s, c in src_rows if c
        ]
        booking_sources.sort(key=lambda x: x['count'], reverse=True)

        # 4. ALOS — avg (departure - arrival) days for CheckedOut stays whose
        #    checkout fell in the selected range. Subtraction in Python keeps us
        #    off SQL-dialect minefields (::numeric, julianday(), DATEDIFF, ...).
        checked_out = (
            db.session.query(Reservation.arrival_date,
                             Reservation.departure_date,
                             Reservation.checked_out_at)
            .filter(Reservation.status == 'CheckedOut',
                    Reservation.checked_out_at.isnot(None))
            .all()
        )
        alos_pairs = []       # list of (date, nights) for range-limited stays
        total_nights = 0
        total_stays  = 0
        for arr, dep, co_at in checked_out:
            co_date = _d(co_at)
            if not co_date or co_date < date_from or co_date > date_to:
                continue
            nights = (_d(dep) - _d(arr)).days
            if nights <= 0:
                continue
            alos_pairs.append((co_date, nights))
            total_nights += nights
            total_stays  += 1
        current_alos = round(total_nights / total_stays, 1) if total_stays else None

        # Day-wise ALOS trend (only days with at least one checkout).
        trend_bucket: dict = {}
        for d, n in alos_pairs:
            b = trend_bucket.setdefault(d, {'sum': 0, 'cnt': 0})
            b['sum'] += n
            b['cnt'] += 1
        alos_trend = [
            {'date': d.isoformat(), 'alos': round(trend_bucket[d]['sum'] / trend_bucket[d]['cnt'], 1)}
            for d in sorted(trend_bucket.keys())
        ]

        # 5. Room Performance — reservations overlapping the range,
        #    excluding Cancelled/NoShow. Revenue = SUM(non-voided payments on
        #    those reservations). Nights in range = clamped overlap.
        overlap_stays = (
            db.session.query(
                Reservation.id,
                Reservation.room_id,
                Reservation.arrival_date,
                Reservation.departure_date,
                Reservation.rate_per_night,
            )
            .filter(Reservation.room_id.isnot(None),
                    Reservation.status.notin_(('Cancelled', 'NoShow')),
                    Reservation.arrival_date <= date_to,
                    Reservation.departure_date > date_from)
            .all()
        )
        stay_ids = [s[0] for s in overlap_stays]
        pay_by_res: dict = {}
        if stay_ids:
            pay_rows = (
                db.session.query(Payment.reservation_id, func.sum(Payment.amount))
                .filter(Payment.is_voided == False,       # noqa: E712
                        Payment.reservation_id.in_(stay_ids))
                .group_by(Payment.reservation_id)
                .all()
            )
            pay_by_res = {rid: float(amt or 0) for rid, amt in pay_rows}

        rooms_meta = {r.id: r.room_number for r in Room.query.all()}
        # Aggregate per-room in Python (keeps dialect-neutral + readable).
        room_agg: dict = {}
        for res_id, room_id, arr, dep, rate in overlap_stays:
            slot = room_agg.setdefault(room_id, {
                'bookings': 0, 'revenue': 0.0, 'rate_sum': Decimal('0'),
                'rate_n': 0, 'days': 0,
            })
            slot['bookings'] += 1
            slot['revenue']  += pay_by_res.get(res_id, 0.0)
            if rate is not None:
                slot['rate_sum'] += Decimal(rate)
                slot['rate_n']   += 1
            # Overlap days within [date_from, date_to].
            start = max(_d(arr), date_from)
            end   = min(_d(dep) - timedelta(days=0), date_to + timedelta(days=1))
            if end > start:
                slot['days'] += (end - start).days

        room_performance = []
        for room_id, slot in room_agg.items():
            avg_rate = float(slot['rate_sum'] / slot['rate_n']) if slot['rate_n'] else 0.0
            room_performance.append({
                'room':     rooms_meta.get(room_id, str(room_id)),
                'bookings': slot['bookings'],
                'revenue':  round(slot['revenue'], 2),
                'avg_rate': round(avg_rate, 0),
                'occ_pct':  round(min(slot['days'] / num_days * 100, 100), 1),
            })
        room_performance.sort(key=lambda r: (-r['revenue'], -r['bookings']))
        room_performance = room_performance[:50]

    except Exception as exc:
        import traceback
        logger.error('analytics_data error: %s\n%s', exc, traceback.format_exc())
        return jsonify({'error': str(exc)}), 500

    return jsonify({
        'date_from':        date_from.isoformat(),
        'date_to':          date_to.isoformat(),
        'total_rooms':      total_rooms,
        'occupancy_trend':  occupancy_trend,
        'revenue_trend':    revenue_trend,
        'booking_sources':  booking_sources,
        'current_alos':     current_alos,
        'alos_trend':       alos_trend,
        'room_performance': room_performance,
    })


@bp.route('/dashboard/alerts-summary')
def dashboard_alerts_summary():
    """
    Lightweight alert aggregation for the 4 overstay dashboard cards.
    2 queries total — no joins, no N+1.
    Returns JSON: hourly_active, hourly_due, hourly_overdue,
                  due_soon_total, overdue_total, overdue_critical,
                  overstay_revenue_today, waived_today
    """
    from flask import jsonify

    now   = datetime.now()
    today = date.today()

    GRACE_MIN        = 30    # minutes silent after checkout (guest packing / brief delay)
    DUE_SOON_HOURLY  = 30   # minutes before checkout → "due soon" for Hourly
    DUE_SOON_REGULAR = 120  # minutes before checkout → "due soon" for Regular
    CRITICAL_MIN     = 120  # minutes overdue → escalate to critical / overstay

    # Default checkout time for Regular bookings — read from Settings, fall back to noon
    _co_row = Settings.query.filter_by(key='default_checkout_time').first()
    _co_val = (_co_row.value or '').strip() if _co_row else ''
    DEFAULT_CHECKOUT_HM = (
        _co_val
        if len(_co_val) == 5 and _co_val[2:3] == ':' and _co_val[:2].isdigit() and _co_val[3:].isdigit()
        else '12:00'
    )

    # ── Query 1: all checked-in reservations (fields only, no joins) ──────────
    checkins = (Reservation.query
                .filter(Reservation.status == 'CheckedIn')
                .with_entities(Reservation.booking_type,
                               Reservation.departure_date,
                               Reservation.checkout_time,
                               Reservation.checkout_initiated)
                .all())

    hourly_active    = 0
    hourly_due       = 0
    hourly_overdue   = 0
    due_soon_total   = 0
    overdue_total    = 0
    overdue_critical = 0

    for booking_type, departure_date, checkout_time, checkout_initiated in checkins:
        is_hourly = (booking_type == 'Hourly')

        # Build planned checkout datetime
        co_time = checkout_time
        if not co_time:
            if is_hourly:
                continue   # Hourly with no time → not trackable
            co_time = DEFAULT_CHECKOUT_HM  # hotel-configured default (noon unless overridden)

        try:
            co_dt = datetime.strptime(
                f'{departure_date.isoformat()} {co_time}', '%Y-%m-%d %H:%M'
            )
        except (ValueError, AttributeError):
            continue

        if is_hourly:
            hourly_active += 1

        minutes_past = (now - co_dt).total_seconds() / 60

        if minutes_past > GRACE_MIN:
            # 30+ min past checkout: counts as overdue (needs attention)
            overdue_total += 1
            if is_hourly:
                hourly_overdue += 1
            if minutes_past > CRITICAL_MIN and checkout_initiated:
                # 120+ min past checkout AND checkout was opened: true blocker
                overdue_critical += 1
        elif minutes_past > -(DUE_SOON_HOURLY if is_hourly else DUE_SOON_REGULAR):
            # Due soon: within threshold window before checkout
            due_soon_total += 1
            if is_hourly:
                hourly_due += 1

    # ── Query 2: today's overstay audit events (revenue + waivers) ───────────
    today_overstay_logs = (AuditLog.query
                           .filter(AuditLog.entity_type == 'Reservation',
                                   AuditLog.action.in_(('overstay_charged',
                                                        'overstay_waived')),
                                   func.date(AuditLog.timestamp) == today)
                           .with_entities(AuditLog.action, AuditLog.after_state)
                           .all())

    overstay_revenue = 0.0
    waived_today     = 0.0
    for log_action, after_state in today_overstay_logs:
        s = after_state or {}
        if log_action == 'overstay_charged':
            overstay_revenue += float(s.get('charge_excl_gst', 0))
        elif log_action == 'overstay_waived':
            waived_today += float(s.get('waived_amount', 0))

    return jsonify({
        'hourly_active':          hourly_active,
        'hourly_due':             hourly_due,
        'hourly_overdue':         hourly_overdue,
        'due_soon_total':         due_soon_total,
        'overdue_total':          overdue_total,
        'overdue_critical':       overdue_critical,
        'overstay_revenue_today': round(overstay_revenue, 2),
        'waived_today':           round(waived_today, 2),
    })

@bp.route('/guest-database')
def guest_database():
    """Legacy route — redirect to /guests."""
    return redirect(url_for('main.guests_list', **request.args))


@bp.route('/api/guests/duplicates')
@login_required
def find_duplicate_guests():
    """Find potential duplicate guest profiles by phone or name similarity."""
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return jsonify({'error': 'Permission denied'}), 403

    from sqlalchemy import func as sqlfunc

    # Find duplicates by phone (most reliable)
    phone_dupes = (
        db.session.query(Guest.phone, sqlfunc.count(Guest.id).label('cnt'))
        .filter(Guest.phone.isnot(None), Guest.phone != '')
        .group_by(Guest.phone)
        .having(sqlfunc.count(Guest.id) > 1)
        .all()
    )

    # Find duplicates by name (less reliable)
    name_dupes = (
        db.session.query(sqlfunc.lower(Guest.name), sqlfunc.count(Guest.id).label('cnt'))
        .group_by(sqlfunc.lower(Guest.name))
        .having(sqlfunc.count(Guest.id) > 1)
        .limit(50)
        .all()
    )

    groups = []
    seen_ids = set()

    for phone, cnt in phone_dupes:
        guests = Guest.query.filter_by(phone=phone).all()
        group = {
            'match_type': 'phone',
            'match_value': phone,
            'guests': [{
                'id': g.id, 'name': g.name, 'phone': g.phone, 'email': g.email,
                'reservations': Reservation.query.filter_by(guest_id=g.id).count(),
                'created_at': g.created_at.isoformat() if g.created_at else None,
            } for g in guests]
        }
        groups.append(group)
        for g in guests:
            seen_ids.add(g.id)

    for name_lower, cnt in name_dupes:
        guests = Guest.query.filter(sqlfunc.lower(Guest.name) == name_lower).all()
        # Skip if already covered by phone dedup
        guest_ids = {g.id for g in guests}
        if guest_ids & seen_ids:
            continue
        group = {
            'match_type': 'name',
            'match_value': guests[0].name if guests else name_lower,
            'guests': [{
                'id': g.id, 'name': g.name, 'phone': g.phone, 'email': g.email,
                'reservations': Reservation.query.filter_by(guest_id=g.id).count(),
                'created_at': g.created_at.isoformat() if g.created_at else None,
            } for g in guests]
        }
        groups.append(group)

    return jsonify({'groups': groups, 'total_groups': len(groups)})


@bp.route('/api/guests/merge', methods=['POST'])
@login_required
def merge_guests():
    """Merge duplicate guest profiles. Keep primary, reassign reservations from secondary."""
    denied = _deny_role('Admin')
    if denied:
        return jsonify({'error': 'Admin only'}), 403

    data = request.get_json() or {}
    primary_id = data.get('primary_id')
    secondary_ids = data.get('secondary_ids', [])

    if not primary_id or not secondary_ids:
        return jsonify({'error': 'primary_id and secondary_ids required'}), 400

    primary = db.session.get(Guest, primary_id)
    if not primary:
        return jsonify({'error': 'Primary guest not found'}), 404

    merged_count = 0
    for sec_id in secondary_ids:
        if sec_id == primary_id:
            continue
        secondary = db.session.get(Guest, sec_id)
        if not secondary:
            continue

        # Reassign all reservations
        Reservation.query.filter_by(guest_id=sec_id).update({'guest_id': primary_id})
        # Reassign checkin records
        from app.models import CheckInRecord
        CheckInRecord.query.filter_by(guest_id=sec_id).update({'guest_id': primary_id})

        # Merge fields: fill in blanks on primary from secondary
        if not primary.email and secondary.email:
            primary.email = secondary.email
        if not primary.address and secondary.address:
            primary.address = secondary.address
        if not primary.id_proof_type and secondary.id_proof_type:
            primary.id_proof_type = secondary.id_proof_type
            primary.id_proof_number = secondary.id_proof_number

        # Accumulate stay count
        primary.total_stays = (primary.total_stays or 0) + (secondary.total_stays or 0)

        _write_audit('Guest', primary_id, 'profile_merged',
                     {'merged_from': sec_id, 'secondary_name': secondary.name},
                     {'primary_name': primary.name})

        # Delete secondary (phone unique constraint would block keeping both)
        db.session.delete(secondary)
        merged_count += 1

    db.session.commit()
    return jsonify({'ok': True, 'merged': merged_count, 'primary_id': primary_id})


@bp.route('/guests')
@login_required
def guests_list():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'recent')
    search = request.args.get('search', '').strip()
    
    query = Guest.query
    
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Guest.name.ilike(search_pattern),
                Guest.phone.ilike(search_pattern),
                Guest.email.ilike(search_pattern),
                Guest.company.ilike(search_pattern)
            )
        )
    
    if sort_by == 'recent':
        query = query.order_by(Guest.created_at.desc())
    elif sort_by == 'name':
        query = query.order_by(Guest.name.asc())
    elif sort_by == 'visits':
        query = query.outerjoin(Reservation).group_by(Guest.id).order_by(func.count(Reservation.id).desc())
    
    guests = query.paginate(page=page, per_page=20)

    # Real DB-backed summary counts (full database, not just current page)
    total_guests   = Guest.query.count()
    active_stays   = Reservation.query.filter_by(status='CheckedIn').with_entities(Reservation.guest_id).distinct().count()
    checked_out    = (Guest.query
                      .join(Reservation)
                      .filter(Reservation.status == 'CheckedOut')
                      .distinct(Guest.id).count())
    repeat_guests  = (Guest.query
                      .join(Reservation)
                      .group_by(Guest.id)
                      .having(func.count(Reservation.id) > 1)
                      .count())

    return render_template('guest_database.html',
                           guests=guests,
                           search=search,
                           sort_by=sort_by,
                           total_guests=total_guests,
                           active_stays=active_stays,
                           checked_out=checked_out,
                           repeat_guests=repeat_guests)

@bp.route('/guest/<int:guest_id>')
def guest_folio(guest_id):
    """Guest Profile — identity + summary metrics (CRM view)."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied
    guest = Guest.query.get_or_404(guest_id)
    reservations = Reservation.query.filter_by(guest_id=guest_id).order_by(Reservation.arrival_date.desc()).all()

    # Compute summary metrics + per-stay billing rows
    total_visits    = len(reservations)
    last_stay       = reservations[0] if reservations else None
    lifetime_spend  = 0.0
    total_paid_all  = 0.0
    outstanding_bal = 0.0
    history_rows    = []

    for r in reservations:
        b = calculate_stay_amount(r)
        lifetime_spend  += b['total']
        total_paid_all  += b['paid']
        if b['balance'] > 0.01:
            outstanding_bal += b['balance']
        history_rows.append({'reservation': r, 'billing': b})

    latest_billing = history_rows[0]['billing'] if history_rows else None
    companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()

    return render_template(
        'guest_folio.html',
        guest=guest,
        reservations=reservations,
        history_rows=history_rows,
        total_visits=total_visits,
        last_stay=last_stay,
        latest_billing=latest_billing,
        companies=companies,
        lifetime_spend=round(lifetime_spend, 2),
        total_paid_all=round(total_paid_all, 2),
        outstanding_bal=round(outstanding_bal, 2),
    )


@bp.route('/api/cico/preview')
@login_required
def api_cico_preview():
    """
    Live preview for early check-in or late check-out charge.
    GET params: type=early|late, reservation_id=X, time=HH:MM
    Returns JSON: {applicable, amount, pct, slab_label, grace}
    """
    from app.cico_service import (
        get_cico_settings, compute_early_checkin, compute_late_checkout,
    )
    charge_type    = request.args.get('type', 'late')
    reservation_id = request.args.get('reservation_id', type=int)
    time_str       = request.args.get('time', '').strip()

    if not reservation_id:
        return jsonify({'error': 'reservation_id required'}), 400

    reservation = Reservation.query.get_or_404(reservation_id)
    nights = (reservation.departure_date - reservation.arrival_date).days
    rules  = get_cico_settings()

    if not time_str:
        time_str = datetime.now().strftime('%H:%M')

    if charge_type == 'early':
        result = compute_early_checkin(
            float(reservation.rate_per_night), time_str, nights, rules=rules
        )
    else:
        result = compute_late_checkout(
            float(reservation.rate_per_night), time_str, nights, rules=rules
        )

    return jsonify(result)


@bp.route('/api/guest/<int:guest_id>/update', methods=['POST'])
@login_required
def api_update_guest(guest_id):
    """Update basic guest profile fields. Returns JSON."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    guest = Guest.query.get_or_404(guest_id)
    data = request.get_json(silent=True) or {}

    name  = (data.get('name')  or '').strip()
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip()
    pin   = (data.get('pin_code') or '').strip()
    id_t  = (data.get('id_proof_type') or '').strip()
    id_n  = (data.get('id_proof_number') or '').strip()

    errs = validate_fields(
        validate_name(name, 'Name'),
        validate_phone(phone, 'Mobile number'),
        validate_email(email),
        validate_pin_code(pin),
        validate_id_proof(id_t, id_n),
    )
    if errs:
        return jsonify({'success': False, 'error': errs[0]}), 400

    phone = _clean_phone(phone)

    # Uniqueness check — exclude self
    clash = Guest.query.filter(Guest.phone == phone, Guest.id != guest_id).first()
    if clash:
        return jsonify({'success': False, 'error': 'Mobile number already registered to another guest'}), 400

    # ── Apr 2026 trust fix: sync ALL name fields together ──
    # Guest has THREE name surfaces:
    #   * `name`        — legacy single field (used by reservation tab,
    #                     guest_database list, search index)
    #   * `first_name`  — structured form (used by GRC, edit forms,
    #                     `display_name` property → preferred when set)
    #   * `last_name`   — structured form
    # Updating only `name` left first/last STALE — the reservation tab
    # then computed `name.split()` which read the new name correctly,
    # but anywhere using `display_name` (GRC, edit modal pre-fill) saw
    # the old structured pair. Splitting once and writing all three
    # via `Guest.set_name` keeps all surfaces in lock-step.
    _name_parts = name.split(None, 1)
    Guest.set_name(guest, _name_parts[0],
                   _name_parts[1] if len(_name_parts) > 1 else '')
    guest.phone         = phone
    guest.email         = (data.get('email')         or '').strip() or None
    guest.company       = (data.get('company')       or '').strip() or None
    guest.address       = (data.get('address')       or '').strip() or None
    guest.country       = (data.get('country')       or 'India').strip()
    guest.state         = (data.get('state')         or '').strip() or None
    guest.city          = (data.get('city')          or '').strip() or None
    guest.pin_code      = (data.get('pin_code')      or '').strip() or None
    guest.id_proof_type = (data.get('id_proof_type') or '').strip() or None
    guest.id_proof_number = (data.get('id_proof_number') or '').strip() or None

    # Optional corporate billing — update the most recent CheckInRecord if provided
    if 'is_corporate' in data:
        from app.models import CheckInRecord
        ci = CheckInRecord.query.filter_by(guest_id=guest_id)\
                .order_by(CheckInRecord.created_at.desc()).first()
        if ci:
            is_corp = bool(data.get('is_corporate'))
            corp_company_id = data.get('company_id') or None
            if isinstance(corp_company_id, str):
                corp_company_id = int(corp_company_id) if corp_company_id.isdigit() else None
            corp_ref = (data.get('company_billing_ref') or '').strip() or None
            if is_corp and corp_company_id:
                corp_obj = Company.query.get(corp_company_id)
                if corp_obj and not guest.company:
                    guest.company = corp_obj.name
                ci.company_id = corp_company_id
                ci.company_billing_ref = corp_ref
                ci.billing_responsibility = 'Company'
            else:
                ci.company_id = None
                ci.company_billing_ref = None
                ci.billing_responsibility = 'Guest'

    # Audit trail — record the rename so any "wait, who changed this?"
    # question has an answer. Cheap (1 row), high-value.
    try:
        _old_name = (data.get('_old_name_for_audit') or '').strip()
        if _old_name and _old_name != name:
            _write_audit('Guest', guest_id, 'profile_renamed',
                         {'name': _old_name},
                         {'name': name, 'by_user_id': current_user.id})
    except Exception:
        pass

    db.session.commit()
    return jsonify({'success': True, 'message': 'Profile updated successfully',
                    'name': name,
                    'first_name': guest.first_name,
                    'last_name':  guest.last_name})


@bp.route('/guest/<int:guest_id>/history')
@login_required
def guest_history(guest_id):
    """Visit History — all stays for this guest with folio/invoice links."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied
    guest = Guest.query.get_or_404(guest_id)
    reservations = Reservation.query.filter_by(guest_id=guest_id).order_by(Reservation.arrival_date.desc()).all()

    # Attach billing to each reservation for display
    rows = []
    for r in reservations:
        b = calculate_stay_amount(r)
        rows.append({'reservation': r, 'billing': b})

    return render_template('guest_history.html', guest=guest, rows=rows)


@bp.route('/folio/<int:reservation_id>')
@login_required
def reservation_folio(reservation_id):
    """Reservation Folio — charges, payments, and balance for a single stay."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)
    billing = calculate_stay_amount(reservation)
    return render_template('reservation_folio.html', reservation=reservation, billing=billing)

@bp.route('/reservation/<int:reservation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_reservation(reservation_id):
    if not reservation_id or reservation_id <= 0:
        abort(400)
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)

    # Checked-out reservations are locked — no booking edits allowed.
    # Guest personal details can still be updated via the Guest Profile section.
    if reservation.status in ('CheckedOut', 'Cancelled', 'NoShow'):
        flash('This reservation is locked and cannot be edited. '
              'Use Guest Profile to update personal details.', 'warning')
        return redirect(url_for('main.reservations'))

    if request.method == 'POST':
        # Lock guard: block edits touching a locked arrival or departure date
        from app.services import assert_business_date_unlocked
        for chk_date in [reservation.arrival_date, reservation.departure_date]:
            ok, lock_err = assert_business_date_unlocked(chk_date, 'edit reservation')
            if not ok:
                flash(lock_err, 'danger')
                return redirect(url_for('main.reservations'))

        before = {
            'arrival_date': str(reservation.arrival_date),
            'departure_date': str(reservation.departure_date),
            'rate_per_night': float(reservation.rate_per_night),
            'adults': reservation.adults,
            'children': reservation.children,
            'guest_first_name': reservation.guest.first_name or '',
            'guest_last_name': reservation.guest.last_name or '',
            'guest_phone': reservation.guest.phone or '',
            'guest_email': reservation.guest.email or '',
        }
        try:
            new_arrival = datetime.strptime(request.form.get('arrival_date', ''), '%Y-%m-%d').date()
            new_departure = datetime.strptime(request.form.get('departure_date', ''), '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid arrival or departure date.', 'danger')
            return redirect(url_for('main.edit_reservation', reservation_id=reservation.id))
        new_rate = request.form.get('rate', type=float)
        new_adults = request.form.get('adults', type=int)
        new_children = request.form.get('children', type=int)

        # Guest fields — accept structured first/last name with legacy fallback
        from app.validators import validate_name, validate_phone, validate_email, clean_phone
        guest_first_name = request.form.get('guest_first_name', '').strip()
        guest_last_name  = request.form.get('guest_last_name', '').strip()
        guest_full_name  = (f'{guest_first_name} {guest_last_name}'.strip()
                            or request.form.get('guest_name', '').strip())
        guest_phone = request.form.get('guest_phone', '').strip()
        guest_email = request.form.get('guest_email', '').strip()

        edit_errs = validate_fields(
            validate_date_range(new_arrival, new_departure, 'Arrival date', 'Departure date'),
            validate_positive_float(new_rate, 'Room rate'),
            validate_positive_int(new_adults, 'Adults', min_val=1, max_val=20),
            validate_positive_int(new_children if new_children else 0, 'Children', min_val=0, max_val=20),
            validate_name(guest_full_name, 'Guest name'),
            validate_phone(guest_phone, 'Guest phone'),
            validate_email(guest_email),
        )
        if edit_errs:
            for e in edit_errs:
                flash(e, 'danger')
            return redirect(url_for('main.edit_reservation', reservation_id=reservation.id))

        reservation.arrival_date = new_arrival
        reservation.departure_date = new_departure
        reservation.room_type_id = request.form.get('room_type_id', type=int)
        reservation.adults = new_adults
        reservation.children = new_children
        reservation.rate_per_night = new_rate

        # Update guest fields. Phone changes only allowed if no collision.
        guest = reservation.guest
        new_phone = clean_phone(guest_phone)
        if new_phone and new_phone != guest.phone:
            collision = Guest.query.filter(Guest.phone == new_phone, Guest.id != guest.id).first()
            if collision:
                flash('Another guest already uses that phone number; phone not changed.', 'warning')
            else:
                guest.phone = new_phone
        if guest_first_name:
            guest.first_name = guest_first_name
            guest.last_name = guest_last_name
            guest.name = guest_full_name
        else:
            guest.name = guest_full_name
        guest.email = guest_email or None

        db.session.commit()
        after = {
            'arrival_date': str(reservation.arrival_date),
            'departure_date': str(reservation.departure_date),
            'rate_per_night': float(reservation.rate_per_night),
            'adults': reservation.adults,
            'children': reservation.children,
            'guest_first_name': guest.first_name or '',
            'guest_last_name': guest.last_name or '',
            'guest_phone': guest.phone or '',
            'guest_email': guest.email or '',
        }
        _write_audit('Reservation', reservation.id, 'edited', before, after)
        flash('Reservation updated successfully', 'success')
        return redirect(url_for('main.reservations'))
    
    room_types = RoomType.query.all()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    return render_template('edit_reservation.html', 
                         reservation=reservation, 
                         room_types=room_types,
                         payment_modes=payment_modes)

@bp.route('/api/tab/<tab_name>')
@login_required
def load_tab(tab_name):
    business_date = get_business_date()
    
    if tab_name == 'overview':
        # Canonical occupancy (KPI Phase 1, Step 3) — same engine the
        # full dashboard context uses, so the AJAX tab refresh and the
        # initial render never diverge.
        from app.occupancy_engine import occupancy_snapshot
        _occ = occupancy_snapshot()
        total_rooms = _occ['total']
        occupied = _occ['occupied']
        occupancy_pct = _occ['pct']
        occupancy_anomaly = _occ['anomaly']
        sellable_rooms = _occ['sellable']
        vacant = Room.query.filter_by(status='Vacant', is_active=True).count()
        dirty = Room.query.filter_by(status='Dirty', is_active=True).count()
        maintenance = Room.query.filter_by(status='Maintenance', is_active=True).count()

        arrivals_today = Reservation.query.filter(
            Reservation.arrival_date == business_date,
            Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn'])
        ).count()

        departures_today = Reservation.query.filter(
            Reservation.departure_date == business_date,
            Reservation.status == 'CheckedIn'
        ).count()

        # Stayovers = checked-in guests who arrived before today AND are not departing today
        stayovers = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.arrival_date < business_date,
            Reservation.departure_date > business_date
        ).count()

        # Today check-ins = checked-in guests who arrived today
        today_checkins = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.arrival_date == business_date
        ).count()

        # Booking source breakdown — scoped to today's check-ins only
        ota_bookings = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.arrival_date == business_date,
            Reservation.source == 'OTA'
        ).count()
        walkin_bookings = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.arrival_date == business_date,
            Reservation.source == 'Walk-in'
        ).count()
        calling_bookings = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.arrival_date == business_date,
            Reservation.source == 'Calling'
        ).count()
        source_mismatch = (ota_bookings + walkin_bookings + calling_bookings) != today_checkins

        # Occupancy anomaly check (KPI Phase 1, Step 3) — canonical
        # engine flag, same semantic as _build_dashboard_context.
        kpi_mismatch = occupancy_anomaly
        if kpi_mismatch:
            import logging
            logging.getLogger(__name__).warning(
                'Occupancy anomaly: occupied=%d exceeds sellable=%d '
                '(an occupied room appears flagged OOO/Maintenance).',
                occupied, sellable_rooms,
            )
        
        daily_reservations = Reservation.query.filter(
            Reservation.created_at >= business_date,
            Reservation.created_at < business_date + timedelta(days=1)
        ).count()
        
        from app.kpi_helpers import get_daily_revenue, get_adr, get_revpar
        today_revenue = get_daily_revenue(business_date)
        yesterday_revenue = get_daily_revenue(business_date - timedelta(days=1))

        month_start = business_date.replace(day=1)
        mtd_revenue = float(db.session.query(func.sum(Payment.amount)).filter(
            Payment.payment_date >= month_start,
            Payment.payment_date <= business_date,
            Payment.is_voided == False
        ).scalar() or 0)

        # Standardized: rate-based ADR, ARR*occ RevPAR (from kpi_helpers)
        avg_rate = get_adr()
        revpar = get_revpar(adr=avg_rate, occ_pct=occupancy_pct)

        # Use UTC window for timestamp-based filters (IST offset)
        from app.services import get_business_day_utc_window as _get_utc_win
        _ov_today = date.today()
        _ov_utc_start, _ov_utc_end = _get_utc_win(_ov_today)

        checked_in_today = Reservation.query.filter(
            Reservation.checked_in_at >= _ov_utc_start,
            Reservation.checked_in_at < _ov_utc_end,
        ).count()

        checked_out_today = Reservation.query.filter(
            Reservation.checked_out_at >= _ov_utc_start,
            Reservation.checked_out_at < _ov_utc_end,
            Reservation.status == 'CheckedOut'
        ).count()

        walk_in_today = Reservation.query.filter(
            Reservation.created_at >= _ov_utc_start,
            Reservation.created_at < _ov_utc_end,
            Reservation.arrival_date == business_date,
            Reservation.source == 'Walk-in'
        ).count()
        
        pending_checkouts = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.departure_date < business_date
        ).all()
        
        balance_dues = []
        total_balance_due = 0
        from sqlalchemy.orm import subqueryload
        inhouse_res = (Reservation.query
            .filter_by(status='CheckedIn')
            .options(subqueryload(Reservation.payments), subqueryload(Reservation.extra_charges))
            .all())
        for res in inhouse_res:
            billing = calculate_stay_amount(res)
            if billing['balance'] > 0:
                balance_dues.append({'reservation': res, 'balance': billing['balance']})
                total_balance_due += billing['balance']
        
        vacant_clean = vacant
        occupy_clean = occupied
        room_block = maintenance
        
        return render_template('tabs/overview.html',
                             business_date=business_date,
                             total_rooms=total_rooms,
                             occupied=occupied,
                             vacant=vacant,
                             dirty=dirty,
                             occupancy_pct=occupancy_pct,
                             arrivals_today=arrivals_today,
                             departures_today=departures_today,
                             stayovers=stayovers,
                             today_checkins=today_checkins,
                             daily_reservations=daily_reservations,
                             today_revenue=today_revenue,
                             yesterday_revenue=yesterday_revenue,
                             mtd_revenue=mtd_revenue,
                             avg_rate=avg_rate,
                             revpar=revpar,
                             ota_bookings=ota_bookings,
                             walkin_bookings=walkin_bookings,
                             calling_bookings=calling_bookings,
                             source_mismatch=source_mismatch,
                             checked_in_today=checked_in_today,
                             checked_out_today=checked_out_today,
                             walk_in_today=walk_in_today,
                             pending_checkouts=pending_checkouts,
                             balance_dues=balance_dues,
                             total_balance_due=total_balance_due,
                             vacant_clean=vacant_clean,
                             occupy_clean=occupy_clean,
                             occupy_dirty=0,
                             room_block=room_block)
    
    elif tab_name == 'test-view':
        # Reuse the exact same data-gathering logic as the main dashboard
        # so AJAX-loaded test_view.html always gets complete, consistent data.
        ctx = _build_dashboard_context()
        return render_template('tabs/test_view.html', **ctx)

    elif tab_name == 'booking':
        return '', 404
    
    elif tab_name == 'reservations':
        from datetime import date as _date_cls, timedelta as _td_cls
        _today = _date_cls.today()
        _cancelled_window = _today - _td_cls(days=30)
        reservations = Reservation.query.filter(
            db.or_(
                Reservation.status.in_(['Reserved', 'Confirmed', 'Overbooked', 'CheckedIn', 'Blocked']),
                # Cancelled within last 30 days — visible under the Cancelled filter pill.
                db.and_(
                    Reservation.status == 'Cancelled',
                    db.or_(
                        db.and_(Reservation.cancellation_processed_at.isnot(None),
                                func.date(Reservation.cancellation_processed_at) >= _cancelled_window),
                        Reservation.arrival_date >= _cancelled_window,
                    ),
                ),
            )
        ).order_by(Reservation.arrival_date.desc()).all()
        from app.geo_data import COUNTRIES, INDIA_STATES_CITIES
        from app.models import PaymentMode, Company
        from app.services import get_forfeit_approval_threshold
        return render_template('tabs/reservations.html',
            reservations=reservations,
            business_date=business_date,
            room_types=RoomType.query.all(),
            payment_modes=PaymentMode.query.filter_by(is_active=True).all(),
            companies=Company.query.filter_by(is_active=True).all(),
            countries=COUNTRIES,
            india_states_cities=INDIA_STATES_CITIES,
            now_time=datetime.now().strftime('%H:%M'),
            # The template pipes this through |tojson; without it the AJAX tab
            # refresh renders an Undefined into json.dumps and 500s, while the
            # full-page render (which does pass it) works. Same single
            # authority the other three render paths use.
            default_checkout_hm=_resolve_default_checkout_hm(),
            forfeit_admin_threshold=get_forfeit_approval_threshold())
    
    return '', 404



@bp.route('/api/checkin/company/<int:company_id>')
@login_required
def get_company_credit(company_id):
    company = Company.query.get_or_404(company_id)
    return jsonify({
        'name': company.name,
        'credit_limit': float(company.credit_limit),
        'credit_used': float(company.credit_used),
        'available_credit': float(company.credit_limit - company.credit_used)
    })

@bp.route('/api/companies', methods=['GET', 'POST'])
@login_required
def handle_companies():
    if request.method == 'POST':
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        comp_phone = (data.get('phone') or '').strip()
        comp_email = (data.get('email') or '').strip()

        comp_errs = validate_fields(
            validate_name(name, 'Company name', max_len=200),
            validate_phone_optional(comp_phone, 'Company phone'),
            validate_email(comp_email),
            validate_non_negative_float(data.get('credit_limit', 0), 'Credit limit'),
            validate_text_length(data.get('contact_person', ''), 'Contact person', max_len=100),
            validate_text_length(data.get('head_office', ''), 'Head office', max_len=200),
        )
        if comp_errs:
            return jsonify({'success': False, 'error': comp_errs[0]}), 400

        company = Company.query.filter_by(name=name).first()
        if company:
            return jsonify({'success': False, 'error': 'Company already exists', 'id': company.id}), 400

        company = Company(
            name=name,
            credit_limit=data.get('credit_limit', 0),
            contact_person=data.get('contact_person', ''),
            phone=comp_phone,
            email=comp_email,
            head_office=data.get('head_office', ''),
            business_category=data.get('business_category', ''),
            vendor_code_generated=bool(data.get('vendor_code_generated', False)),
        )
        db.session.add(company)
        db.session.commit()
        return jsonify({'success': True, 'id': company.id, 'name': company.name})
    
    companies = Company.query.filter_by(is_active=True).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in companies])


@bp.route('/api/companies/<int:company_id>', methods=['GET', 'PUT'])
@login_required
def company_detail(company_id):
    """Get or update a company's details."""
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    company = Company.query.get_or_404(company_id)

    if request.method == 'GET':
        return jsonify({
            'id': company.id,
            'name': company.name,
            'credit_limit': float(company.credit_limit or 0),
            'credit_used': float(company.credit_used or 0),
            'available_credit': float((company.credit_limit or 0) - (company.credit_used or 0)),
            'contact_person': company.contact_person or '',
            'phone': company.phone or '',
            'email': company.email or '',
            'gstin': company.gstin or '',
            'state_code': company.state_code or '',
            'head_office': company.head_office or '',
            'business_category': company.business_category or '',
            'is_active': company.is_active,
        })

    # PUT — update
    data = request.get_json() or {}
    from app.validators import validate_gstin
    edit_errs = validate_fields(
        validate_name(data.get('name', company.name), 'Company name', max_len=200) if 'name' in data else None,
        validate_phone_optional(data.get('phone', ''), 'Company phone') if 'phone' in data else None,
        validate_email(data.get('email', '')) if 'email' in data else None,
        validate_non_negative_float(data.get('credit_limit', 0), 'Credit limit') if 'credit_limit' in data else None,
        validate_gstin(data.get('gstin', '')) if 'gstin' in data else None,
    )
    if edit_errs:
        return jsonify({'success': False, 'error': edit_errs[0]}), 400

    before = {
        'name': company.name,
        'credit_limit': float(company.credit_limit or 0),
        'gstin': company.gstin,
        'state_code': company.state_code,
    }

    if 'name' in data:
        new_name = data['name'].strip()
        clash = Company.query.filter(Company.name == new_name, Company.id != company_id).first()
        if clash:
            return jsonify({'success': False, 'error': 'Company name already exists'}), 400
        company.name = new_name
    if 'credit_limit' in data:
        company.credit_limit = float(data['credit_limit'])
    if 'contact_person' in data:
        company.contact_person = data['contact_person']
    if 'phone' in data:
        company.phone = data['phone']
    if 'email' in data:
        company.email = data['email']
    if 'gstin' in data:
        company.gstin = data['gstin'].strip().upper() or None
    if 'state_code' in data:
        company.state_code = data['state_code'].strip() or None
    if 'head_office' in data:
        company.head_office = data['head_office']
    if 'business_category' in data:
        company.business_category = data['business_category']
    if 'is_active' in data:
        company.is_active = bool(data['is_active'])

    db.session.commit()

    after = {
        'name': company.name,
        'credit_limit': float(company.credit_limit or 0),
        'gstin': company.gstin,
        'state_code': company.state_code,
    }
    _write_audit('Company', company.id, 'updated', before, after)

    return jsonify({'success': True, 'message': f'Company "{company.name}" updated.'})


@bp.route('/api/companies/<int:company_id>/adjust-credit', methods=['POST'])
@login_required
def adjust_company_credit(company_id):
    """Manually adjust company credit_used (e.g. when company pays an invoice).

    JSON body: { "amount": -5000, "reason": "Invoice INV-2026-000123 paid" }
    Positive = increase credit_used (company owes more)
    Negative = decrease credit_used (company paid)
    """
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    company = Company.query.get_or_404(company_id)
    data = request.get_json() or {}

    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Amount must be a number'}), 400

    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required for credit adjustments'}), 400

    old_used = float(company.credit_used or 0)
    new_used = max(0, old_used + amount)  # never go below 0

    company.credit_used = new_used
    db.session.commit()

    _write_audit('Company', company.id, 'credit_adjustment',
                 {'credit_used': old_used},
                 {'credit_used': new_used, 'adjustment': amount, 'reason': reason})

    return jsonify({
        'success': True,
        'message': f'Credit adjusted by ₹{amount:+,.2f}. New balance: ₹{new_used:,.2f}',
        'credit_used': new_used,
        'available_credit': float(company.credit_limit or 0) - new_used,
    })


@bp.route('/api/checkin/walkin-search-express', methods=['POST'])
@login_required
def walkin_search_express():
    from app.services import CheckInService, CheckInException
    try:
        data = request.get_json() or {}

        # ── Validate room up-front ──────────────────────────────────────────
        room_id = data.get('room_id')
        if not room_id:
            return jsonify({'success': False, 'error': 'Room assignment is required'}), 400

        business_date = get_business_date()

        # ── Business date lock guard ──────────────────────────────────────
        from app.services import assert_business_date_unlocked
        ok, lock_err = assert_business_date_unlocked(business_date, 'check in')
        if not ok:
            return jsonify({'success': False, 'error': lock_err}), 403

        # 1. Guest Handling
        guest_id = data.get('guest_id')
        if not guest_id:
            name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            phone = _clean_phone(data.get('phone'))
            guest_err = _validate_guest_input(name, phone)
            if guest_err:
                return jsonify({'success': False, 'error': guest_err}), 400
            guest = Guest.query.filter_by(phone=phone).first()
            if not guest:
                guest = Guest(name=name, phone=phone, email=data.get('email', ''))
                db.session.add(guest)
                db.session.flush()
            guest_id = guest.id
        else:
            guest = db.session.get(Guest, guest_id)
            if not guest:
                return jsonify({'success': False, 'error': 'Guest not found'}), 400

        # 2. Idempotency — return existing if guest already checked in to this room today
        existing = Reservation.query.filter_by(
            guest_id=guest_id,
            room_id=room_id,
            status='CheckedIn',
            arrival_date=business_date
        ).first()
        if existing:
            return jsonify({'success': True, 'reservation_id': existing.id, 'duplicate': True})

        # 3. Lock room row to prevent concurrent double-booking
        room = Room.query.filter_by(id=room_id).with_for_update().first()
        if room is None:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Room not found'}), 404
        if room.status != 'Vacant':
            db.session.rollback()
            return jsonify({'success': False, 'error': f'Room {room.room_number} is not vacant'}), 400

        # 4. Reservation creation — validate numeric inputs
        nights = max(1, int(data.get('nights', 1) or 1))
        advance = float(data.get('advance', 0) or 0)
        adults = max(1, int(data.get('adults', 1) or 1))
        children = max(0, int(data.get('children', 0) or 0))
        tariff_modified = bool(data.get('tariff_modified_manually'))

        departure_date = business_date + timedelta(days=nights)

        # ── Pricing: total_tariff from JS is the total WITH GST for the
        # ENTIRE stay.  We must back out GST, then derive rate_per_night.
        # When tariff is not modified, use room type base_rate directly.
        from app.financial import compute_pricing_from_mode, PricingError

        _total_tariff_raw = float(data.get('total_tariff', 0) or 0)
        _tariff_excl_gst  = float(data.get('tariff_excl_gst', 0) or 0)
        _room_type = room.room_type
        _std_rate = float(_room_type.base_rate) if _room_type else 0
        _gst_rate = float(_room_type.gst_rate or 0) if _room_type else 0
        _gst_exempted = _room_type.gst_exempted if _room_type else False

        if tariff_modified and _total_tariff_raw > 0:
            # User modified tariff — the entered value is the total stay
            # amount (incl GST).  Back out GST to get excl-GST total.
            if _tariff_excl_gst > 0:
                stay_total_excl = _tariff_excl_gst
            elif not _gst_exempted and _gst_rate > 0:
                stay_total_excl = round(_total_tariff_raw / (1 + _gst_rate / 100), 2)
            else:
                stay_total_excl = _total_tariff_raw

            try:
                _pricing = compute_pricing_from_mode(
                    pricing_mode='total_stay',
                    standard_rate=_std_rate,
                    nights=nights,
                    entered_stay_total=stay_total_excl,
                )
            except PricingError as pe:
                db.session.rollback()
                return jsonify({'success': False, 'error': str(pe)}), 400
            rate_per_night = _pricing.rate_per_night
            _pricing_mode = _pricing.pricing_mode
        else:
            # Standard: use central rate resolver (respects rate plans)
            from app.rates import resolve_rate_for_reservation
            _resolved = resolve_rate_for_reservation(
                room.room_type_id, business_date, departure_date)
            rate_per_night = _resolved.rate_per_night
            _pricing_mode = 'standard'

        num_err = _validate_checkin_numbers(nights=nights, rate=rate_per_night, advance=advance)
        if num_err:
            db.session.rollback()
            return jsonify({'success': False, 'error': num_err}), 400

        logger.info(
            'EXPRESS PRICING: total_tariff_raw=%.2f tariff_excl=%.2f nights=%d '
            'mode=%s rate_per_night=%.2f std_rate=%.2f modified=%s',
            _total_tariff_raw, _tariff_excl_gst, nights,
            _pricing_mode, rate_per_night, _std_rate, tariff_modified)

        reservation = Reservation(
            guest_id=guest_id,
            room_type_id=room.room_type_id,
            room_id=room.id,
            arrival_date=business_date,
            departure_date=departure_date,
            adults=adults,
            children=children,
            rate_per_night=rate_per_night,
            advance_payment=advance,
            status='CheckedIn',
            source='Walk-in',
            checked_in_at=datetime.utcnow(),
            pricing_mode=_pricing_mode,
            tariff_modified_manually=tariff_modified,
            standard_tariff=_std_rate,
        )
        db.session.add(reservation)
        db.session.flush()

        # Nightly rate rows (Phase B)
        from app.nightly_rate_service import safe_sync_nightly_rates
        _charged = rate_per_night * nights
        safe_sync_nightly_rates(
            reservation, reason='new_booking',
            override_final_total=_charged if tariff_modified else None,
            pricing_mode=_pricing_mode,
            manual_override=tariff_modified,
        )

        # 4a. Leakage detection + expected tariff
        from app.services import apply_tariff_adjustment
        from app.revenue_guard import apply_leakage_with_expected
        if room.room_type:
            reservation.room_type = room.room_type
        apply_tariff_adjustment(reservation)
        try:
            apply_leakage_with_expected(
                reservation=reservation,
                user_id=current_user.id if current_user.is_authenticated else 0,
                room_no=room.room_number,
            )
        except Exception:
            pass  # non-fatal

        # 4a-ii. Staff attribution for user-wise revenue reporting
        reservation.checkin_by = current_user.username if current_user.is_authenticated else ''

        # 4b. Discount — validated via revenue_guard (raises ValueError on policy breach)
        disc_amt    = float(data.get('discount_amount') or 0)
        disc_reason = (data.get('discount_reason') or '').strip() or None
        disc_auth   = (data.get('discount_authorized_by') or '').strip() or None
        if disc_amt < 0:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Discount amount cannot be negative'}), 400
        if disc_amt > 0:
            if not disc_auth:
                db.session.rollback()
                return jsonify({'success': False,
                                'error': '"Authorized By" is required when a discount is applied'}), 400
            # Policy check (raises ValueError if over threshold without manager role)
            from app.revenue_guard import validate_discount
            try:
                validate_discount(current_user, disc_amt)
            except ValueError as ve:
                db.session.rollback()
                return jsonify({'success': False, 'error': str(ve)}), 403
            reservation.discount_amount        = disc_amt
            reservation.discount_reason        = disc_reason
            reservation.discount_authorized_by = disc_auth
            reservation.discount_given_by      = current_user.username if current_user.is_authenticated else ''
            reservation.discount_at            = datetime.utcnow()
            # Fire discount alert (non-fatal)
            try:
                from app.alert_service import AlertService
                AlertService.check_discount(
                    user_id=current_user.id,
                    discount_amount=disc_amt,
                    reservation_id=reservation.id,
                    room_no=room.room_number,
                )
            except Exception:
                pass

        room.status = 'Occupied'

        # R2A: bridge-write invariant — mirror the primary room into
        # reservation_rooms. Idempotent — back-compat for already-bridged rows.
        from app.services_group_stay import mirror_room_to_bridge
        mirror_room_to_bridge(reservation)

        # 5. Payments
        # Walk-in check-in: guest is being checked in TODAY, so any
        # payment is for today's stay (settlement, not advance).
        payments = data.get('payments', [])
        for p in payments:
            payment = Payment(
                reservation_id=reservation.id,
                payment_mode_id=p['mode_id'],
                amount=p['amount'],
                payment_date=business_date,
                reference_number=p.get('reference', ''),
                payment_purpose='settlement',
            )
            db.session.add(payment)

        # 6. Corporate credit validation
        _billing_resp = data.get('billing_responsibility', 'Guest')
        _corp_company_id = data.get('company_id')
        if _billing_resp == 'Company' and _corp_company_id:
            _corp = Company.query.get(_corp_company_id)
            if _corp and float(_corp.credit_limit or 0) > 0:
                _avail = float(_corp.credit_limit or 0) - float(_corp.credit_used or 0)
                _est_total = float(reservation.rate_per_night) * (reservation.departure_date - reservation.arrival_date).days
                if _avail < _est_total:
                    # Warn but don't block — credit is settled at checkout
                    pass  # Low-credit warning handled by UI

        # 7. Check-in Record
        checkin_mode = data.get('checkin_mode', 'EXPRESS')
        checkin = CheckInRecord(
            reservation_id=reservation.id,
            guest_id=guest_id,
            room_id=room_id,
            checkin_mode=checkin_mode,
            is_profile_complete=False,
            staff_user_id=current_user.id,
            ip_address=request.remote_addr,
            billing_responsibility=_billing_resp,
            company_id=_corp_company_id,
        )
        db.session.add(checkin)

        db.session.commit()
        return jsonify({'success': True, 'reservation_id': reservation.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
@bp.route('/api/rooms/vacant')
@login_required
def get_vacant_rooms():
    rooms = (Room.query
             .filter_by(status='Vacant', is_active=True, is_sellable=True, is_out_of_order=False)
             .order_by(Room.sort_order, Room.room_number)
             .all())
    return jsonify([{
        'id':             r.id,
        'room_number':    r.room_number,
        'room_name':      r.room_name or '',
        'floor':          r.floor,
        'wing':           r.wing or '',
        'room_type_id':   r.room_type_id,
        'room_type_name': r.room_type.name if r.room_type else '',
        'max_adults':     r.max_adults or 2,
        'max_children':   r.max_children or 2,
        'extra_bed_allowed': bool(r.extra_bed_allowed),
    } for r in rooms])


@bp.route('/api/room/<int:room_id>/tariff')
@login_required
def get_room_tariff(room_id):
    """Return the resolved tariff for a room, respecting active rate plans."""
    room = Room.query.get_or_404(room_id)
    rt = room.room_type
    base_rate = float(rt.base_rate)
    gst_rate  = float(rt.gst_rate or 0)

    # Resolve rate using central resolver (arrival/departure from query params or today)
    from app.rates import resolve_rate_for_reservation
    _arrival = request.args.get('arrival')
    _departure = request.args.get('departure')
    try:
        arr = date.fromisoformat(_arrival) if _arrival else get_business_date()
    except ValueError:
        arr = get_business_date()
    try:
        dep = date.fromisoformat(_departure) if _departure else arr + timedelta(days=1)
    except ValueError:
        dep = arr + timedelta(days=1)

    _resolved = resolve_rate_for_reservation(room.room_type_id, arr, dep)
    resolved_rate = _resolved.rate_per_night

    display_rate = round(resolved_rate * (1 + gst_rate / 100), 2) if (not rt.gst_exempted and gst_rate) else resolved_rate

    # Nightly breakdown — only when rates vary across nights
    nightly_breakdown = None
    nights = (dep - arr).days
    if nights > 1 and _resolved.source == 'rate_plan' and _resolved.nightly_rates:
        has_mixed = len(set(_resolved.nightly_rates)) > 1
        if has_mixed:
            from app.rates import get_stay_rates_detailed
            detailed = get_stay_rates_detailed(room.room_type_id, arr, dep)
            nightly_breakdown = [
                {'date': d.strftime('%a %d %b'), 'rate': r,
                 'source': pn if pn else 'Base Rate'}
                for d, r, pn in detailed
            ]

    return jsonify({
        'room_id':          room.id,
        'room_number':      room.room_number,
        'room_type_id':     room.room_type_id,
        'room_type_name':   rt.name,
        'base_rate':        base_rate,
        'resolved_rate':    resolved_rate,
        'gst_rate':         gst_rate,
        'gst_exempted':     bool(rt.gst_exempted),
        'is_gst_inclusive': bool(rt.is_gst_inclusive),
        'display_rate':     display_rate,
        'rate_source':      _resolved.source,
        'applied_plan':     _resolved.applied_plan_name,
        'used_fallback':    _resolved.used_fallback,
        'nightly_breakdown': nightly_breakdown,
    })

# ---------------------------------------------------------------------------
# Revenue Intelligence API endpoints
# ---------------------------------------------------------------------------

@bp.route('/api/alerts/live')
@login_required
def api_alerts_live():
    """Return active (unresolved) revenue alerts for the dashboard panel."""
    from app.alert_service import AlertService
    severity = request.args.get('severity')  # optional filter
    limit    = request.args.get('limit', 50, type=int)
    alerts   = AlertService.get_live_alerts(limit=limit, severity_filter=severity)
    counts   = AlertService.get_alert_counts()
    return jsonify({'alerts': alerts, 'counts': counts})


@bp.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
def api_resolve_alert(alert_id):
    """Mark a single revenue alert as resolved."""
    if not current_user.has_role('Admin', 'Manager'):
        return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403
    from app.alert_service import AlertService
    ok, msg = AlertService.resolve_alert(alert_id, current_user.id)
    return jsonify({'success': ok, 'message': msg})


@bp.route('/api/staff/performance/today')
@login_required
def api_staff_performance_today():
    """Return today's staff performance scorecard."""
    if not current_user.has_role('Admin', 'Manager'):
        return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403
    from app.performance_service import PerformanceService
    data = PerformanceService.get_today_performance()
    return jsonify({'success': True, 'performance': data})


@bp.route('/api/checkin/express/<int:reservation_id>', methods=['POST'])
@login_required
def express_checkin_api(reservation_id):
    from app.services import CheckInService, CheckInException
    try:
        data = request.get_json() or {}
        room_id = int(data.get('room_id')) if data.get('room_id') else request.form.get('room_id', type=int)
        if not room_id:
            return jsonify({'success': False, 'error': 'Room ID is required for express check-in.'}), 400
        # Business date lock guard
        from app.services import assert_business_date_unlocked
        ok, lock_err = assert_business_date_unlocked(get_business_date(), 'check in')
        if not ok:
            return jsonify({'success': False, 'error': lock_err}), 403
        checkin = CheckInService.express_checkin(reservation_id, room_id, current_user.id, request.remote_addr)
        return jsonify({'success': True, 'checkin_id': checkin.id, 'mode': 'EXPRESS'})
    except CheckInException as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@bp.route('/api/guest/<int:guest_id>/id-document', methods=['POST'])
@login_required
def upload_id_document(guest_id):
    from app.models import GuestIDDocument
    import os

    _ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
    _MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

    try:
        guest = Guest.query.get_or_404(guest_id)
        doc_type = request.form.get('document_type', '')
        doc_number = request.form.get('document_number', '').strip()
        if not doc_number:
            return jsonify({'success': False, 'error': 'Document number is required'}), 400

        # Store in private_uploads (NOT static) so files are not web-accessible
        upload_path = os.path.join(current_app.root_path, 'private_uploads', 'id_docs')
        os.makedirs(upload_path, exist_ok=True)

        front_path = None
        back_path = None
        for field in ('front_image', 'back_image'):
            f = request.files.get(field)
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lstrip('.').lower()
                if ext not in _ALLOWED_EXTENSIONS:
                    return jsonify({'success': False, 'error': f'File type .{ext} not allowed. Use JPG, PNG or PDF.'}), 400
                data = f.read()
                if len(data) > _MAX_FILE_BYTES:
                    return jsonify({'success': False, 'error': 'File too large. Maximum 5 MB per image.'}), 400
                fname = f"id_{guest_id}_{field}_{int(datetime.utcnow().timestamp())}.{ext}"
                dest = os.path.join(upload_path, fname)
                with open(dest, 'wb') as out:
                    out.write(data)
                if field == 'front_image':
                    front_path = f"id_docs/{fname}"
                else:
                    back_path = f"id_docs/{fname}"

        # If an existing doc ID is provided, update that record (partial upload support)
        existing_doc_id = request.form.get('existing_doc_id', type=int)
        if existing_doc_id:
            doc = GuestIDDocument.query.filter_by(id=existing_doc_id, guest_id=guest_id).first()
            if doc:
                if doc_type:
                    doc.document_type = doc_type
                if doc_number:
                    doc.document_number = doc_number
                if front_path:
                    doc.front_image_path = front_path
                if back_path:
                    doc.back_image_path = back_path
                db.session.commit()
                return jsonify({
                    'success': True, 'document_id': doc.id,
                    'front_uploaded': bool(doc.front_image_path),
                    'back_uploaded':  bool(doc.back_image_path),
                })

        # No existing doc — create new
        doc = GuestIDDocument(
            guest_id=guest_id,
            document_type=doc_type,
            document_number=doc_number,
            front_image_path=front_path,
            back_image_path=back_path,
            verification_status='Pending'
        )
        db.session.add(doc)
        db.session.commit()
        return jsonify({
            'success': True, 'document_id': doc.id,
            'front_uploaded': bool(front_path),
            'back_uploaded':  bool(back_path),
        })

    except Exception as e:
        current_app.logger.error('upload_id_document failed for guest %s: %s', guest_id, e, exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Server error while saving document. Please try again.'}), 500

@bp.route('/payment/<int:payment_id>/void', methods=['POST'])
@login_required
def void_payment(payment_id):
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied
    payment = Payment.query.get_or_404(payment_id)
    if payment.is_voided:
        flash('Payment is already voided.', 'warning')
        return redirect(request.referrer or url_for('main.reservations'))
    if payment.is_correction:
        flash('Cannot void a correction entry directly. Post a fresh correction instead.', 'warning')
        return redirect(request.referrer or url_for('main.reservations'))

    # Audit-lock guard (Admin override allowed).
    from app.services import (assert_or_admin_override, post_payment_correction,
                              get_locking_audit)
    ok, lock_err, override_used, override_reason = assert_or_admin_override(
        payment.payment_date, 'void payment', request, current_user
    )
    if not ok:
        flash(lock_err, 'danger')
        return redirect(request.referrer or url_for('main.reservations'))

    reason = request.form.get('void_reason', '').strip() or 'Voided by manager'

    # ── Correction-entry path ─────────────────────────────────────────
    # When the payment falls in a closed Night Audit and Admin chose to
    # override, NEVER mutate the original row. Instead post a reversal
    # (and optional replacement) so the audit trail stays whole.
    is_locked = get_locking_audit(payment.payment_date) is not None
    if is_locked and override_used:
        try:
            new_amount_raw = (request.form.get('correction_new_amount') or '').strip()
            new_amount = float(new_amount_raw) if new_amount_raw else None
            if new_amount is not None and new_amount <= 0:
                new_amount = None
            new_mode_raw = (request.form.get('correction_new_mode_id') or '').strip()
            new_mode_id = int(new_mode_raw) if new_mode_raw else None
            new_ref = (request.form.get('correction_new_reference') or '').strip() or None
            full_reason = f'{reason} | Override: {override_reason}'
            result = post_payment_correction(
                payment,
                new_amount=new_amount,
                new_mode_id=new_mode_id,
                new_reference=new_ref,
                reason=full_reason,
                user_id=current_user.id,
                audit_writer=_write_audit,
            )
            _write_audit('Payment', payment.id, 'audit_lock_override',
                         {'payment_date': payment.payment_date.isoformat(),
                          'amount':       float(payment.amount)},
                         {'action':           'correction_pair',
                          'reversal_id':      result['reversal'].id,
                          'replacement_id':   (result['replacement'].id
                                                if result['replacement'] else None),
                          'override_reason':  override_reason,
                          'admin_user_id':    current_user.id})
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.exception('correction-pair void failed for payment_id=%d', payment_id)
            flash(f'Correction failed: {exc}', 'danger')
            return redirect(request.referrer or url_for('main.reservations'))

        if result['replacement'] is not None:
            flash(f'Correction posted — reversal ₹{float(payment.amount):,.2f} '
                  f'+ replacement ₹{float(result["replacement"].amount):,.2f}. '
                  f'Original row preserved.', 'success')
        else:
            flash(f'Reversal posted — ₹{float(payment.amount):,.2f} cancelled. '
                  f'Original row preserved (audit-safe).', 'success')
        return redirect(request.referrer or url_for('main.reservations'))

    # ── Standard void path (open date — direct mutation is fine) ──────
    before = {'is_voided': False, 'amount': float(payment.amount)}
    payment.is_voided = True
    payment.voided_at = datetime.utcnow()
    payment.voided_by_user_id = current_user.id
    payment.void_reason = reason
    db.session.commit()
    _write_audit('Payment', payment.id, 'voided', before,
                 {'is_voided': True, 'void_reason': reason})
    flash(f'Payment of ₹{float(payment.amount):,.2f} voided. Reason: {reason}', 'success')
    return redirect(request.referrer or url_for('main.reservations'))


@bp.route('/reservation/<int:reservation_id>/extend', methods=['POST'])
@login_required
def extend_stay(reservation_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status != 'CheckedIn':
        flash('Stay extension is only allowed for checked-in reservations.', 'warning')
        return redirect(url_for('main.reservations'))
    new_departure_str = request.form.get('new_departure_date', '').strip()
    try:
        new_departure = datetime.strptime(new_departure_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('main.reservations'))
    if new_departure <= reservation.departure_date:
        flash('New departure date must be after the current departure date.', 'danger')
        return redirect(url_for('main.reservations'))
    old_departure = reservation.departure_date
    reservation.departure_date = new_departure
    db.session.commit()
    _write_audit('Reservation', reservation.id, 'stay_extended',
                 {'departure_date': str(old_departure)},
                 {'departure_date': str(new_departure)})
    flash(f'Stay extended to {new_departure.strftime("%d %b %Y")}.', 'success')
    return redirect(url_for('main.reservations'))


@bp.route('/reservation/<int:reservation_id>/shorten-stay', methods=['POST'])
@login_required
def shorten_stay(reservation_id):
    """Early departure — shorten the stay with rate recalculation."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status != 'CheckedIn':
        flash('Stay shortening is only allowed for checked-in reservations.', 'warning')
        return redirect(url_for('main.reservations'))

    new_departure_str = request.form.get('new_departure_date', '').strip()
    try:
        new_departure = datetime.strptime(new_departure_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('main.reservations'))

    if new_departure >= reservation.departure_date:
        flash('New departure must be before current departure. Use extend stay for later dates.', 'danger')
        return redirect(url_for('main.reservations'))

    if new_departure <= reservation.arrival_date:
        flash('New departure must be after arrival date.', 'danger')
        return redirect(url_for('main.reservations'))

    from app.services import get_business_date
    if new_departure < get_business_date():
        flash('Cannot shorten stay to a date before today.', 'danger')
        return redirect(url_for('main.reservations'))

    old_departure = reservation.departure_date
    old_nights = (old_departure - reservation.arrival_date).days
    new_nights = (new_departure - reservation.arrival_date).days

    reservation.departure_date = new_departure
    db.session.commit()

    _write_audit('Reservation', reservation.id, 'stay_shortened',
                 {'departure_date': str(old_departure), 'nights': old_nights},
                 {'departure_date': str(new_departure), 'nights': new_nights})
    flash(f'Stay shortened to {new_departure.strftime("%d %b %Y")} ({new_nights} night{"s" if new_nights != 1 else ""}).', 'success')
    return redirect(url_for('main.reservations'))


# ---------------------------------------------------------------------------
# Overstay Billing
# ---------------------------------------------------------------------------

@bp.route('/reservation/<int:reservation_id>/overstay-charge', methods=['POST'])
@login_required
def add_overstay_charge(reservation_id):
    """
    Add an overstay extra charge for a checked-in Hourly booking.
    Idempotent: tracks overstay_billed_until so repeated calls never
    double-bill the same time window.

    POST params:
      waive_charge  = '1'   → waive instead of charging  (Manager/Admin only)
      waive_reason  = str   → mandatory reason for waiver
    """
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied

    reservation = Reservation.query.get_or_404(reservation_id)

    if reservation.status != 'CheckedIn':
        flash('Overstay charge only applies to checked-in reservations.', 'warning')
        return redirect(url_for('main.reservations'))

    if reservation.booking_type != 'Hourly':
        flash('Overstay billing currently supports Hourly bookings only.', 'info')
        return redirect(url_for('main.reservations'))

    if not reservation.checkout_time:
        flash('Checkout time not recorded — cannot calculate overstay.', 'danger')
        return redirect(url_for('main.reservations'))

    rate_per_night = float(reservation.rate_per_night or 0)
    if rate_per_night <= 0:
        flash('Cannot calculate overstay charge — room rate is zero or not set.', 'danger')
        return redirect(url_for('main.reservations'))

    import math as _math

    # ── Build planned checkout datetime ───────────────────────────────────────
    try:
        planned_checkout = datetime.strptime(
            f'{reservation.departure_date.isoformat()} {reservation.checkout_time}',
            '%Y-%m-%d %H:%M'
        )
    except ValueError:
        flash('Invalid checkout date/time on this reservation.', 'danger')
        return redirect(url_for('main.reservations'))

    GRACE_MINUTES = 10
    now = datetime.now()

    # ── Re-read current billing state from DB (prevent double-post race) ──────
    db.session.refresh(reservation)
    bill_from = reservation.overstay_billed_until or planned_checkout

    elapsed_seconds  = (now - bill_from).total_seconds()
    billable_minutes = elapsed_seconds / 60

    # Apply grace only on the very first charge (no prior billing)
    if reservation.overstay_billed_until is None:
        billable_minutes -= GRACE_MINUTES

    if billable_minutes <= 0:
        flash('No overstay charge applicable — within grace period or already billed.', 'info')
        return redirect(url_for('main.reservations'))

    billable_hours = _math.ceil(billable_minutes / 60)
    hourly_rate    = round(rate_per_night / 24, 2)
    charge_amount  = round(hourly_rate * billable_hours, 2)

    # ── Waive path (Manager / Admin only) ─────────────────────────────────────
    waive = request.form.get('waive_charge') == '1'
    if waive:
        if not current_user.has_role('Admin', 'Manager'):
            flash('Only Manager or Admin can waive overstay charges.', 'danger')
            return redirect(url_for('main.reservations'))
        waive_reason = request.form.get('waive_reason', '').strip()
        if not waive_reason:
            flash('Waiver reason is required.', 'danger')
            return redirect(url_for('main.reservations'))
        reservation.overstay_billed_until = now
        db.session.commit()
        _write_audit('Reservation', reservation.id, 'overstay_waived', {},
                     {
                         'action_type': 'waive',
                         'billed_from': str(bill_from),
                         'billed_until': str(now),
                         'overdue_minutes': round(billable_minutes, 1),
                         'billable_hours': billable_hours,
                         'hourly_rate': hourly_rate,
                         'waived_amount': charge_amount,
                         'waive_reason': waive_reason,
                         'waived_by_user_id': current_user.id,
                     })
        flash(f'Overstay charge of ₹{charge_amount:,.2f} waived. Reason: {waive_reason}', 'info')
        return redirect(url_for('main.reservations'))

    # ── Add extra charge ──────────────────────────────────────────────────────
    hrs_label = f'{billable_hours} hr{"s" if billable_hours > 1 else ""}'
    extra = ExtraCharge(
        reservation_id=reservation.id,
        description=f'Overstay — {hrs_label} @ ₹{hourly_rate:,.2f}/hr',
        amount=charge_amount,
        charge_date=now.date()
    )
    db.session.add(extra)
    reservation.overstay_billed_until = now
    db.session.commit()

    _write_audit('Reservation', reservation.id, 'overstay_charged', {},
                 {
                     'action_type': 'charge',
                     'billed_from': str(bill_from),
                     'billed_until': str(now),
                     'overdue_minutes': round(billable_minutes, 1),
                     'billable_hours': billable_hours,
                     'hourly_rate': hourly_rate,
                     'charge_excl_gst': charge_amount,
                     'description': extra.description,
                 })
    flash(f'Overstay charge ₹{charge_amount:,.2f} ({hrs_label}) added to folio.', 'success')
    return redirect(url_for('main.reservations'))


@bp.route('/reservation/<int:reservation_id>/extend-hourly', methods=['POST'])
@login_required
def extend_hourly(reservation_id):
    """
    Extend a Hourly booking to a new checkout date + time.
    Also clears overstay_billed_until so the fresh window is re-evaluated.
    """
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied

    reservation = Reservation.query.get_or_404(reservation_id)

    if reservation.status != 'CheckedIn':
        flash('Stay extension is only allowed for checked-in reservations.', 'warning')
        return redirect(url_for('main.reservations'))

    new_date_str = request.form.get('new_checkout_date', '').strip()
    new_time_str = request.form.get('new_checkout_time', '').strip()

    if not new_date_str or not new_time_str:
        flash('New checkout date and time are both required.', 'danger')
        return redirect(url_for('main.reservations'))

    try:
        new_departure = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        datetime.strptime(new_time_str, '%H:%M')   # validate time format
    except ValueError:
        flash('Invalid date or time format.', 'danger')
        return redirect(url_for('main.reservations'))

    new_co_dt = datetime.strptime(f'{new_date_str} {new_time_str}', '%Y-%m-%d %H:%M')
    if new_co_dt <= datetime.now():
        flash('New checkout time must be in the future.', 'danger')
        return redirect(url_for('main.reservations'))

    # Must also be later than the current planned checkout
    if reservation.checkout_time:
        try:
            current_co_dt = datetime.strptime(
                f'{reservation.departure_date.isoformat()} {reservation.checkout_time}',
                '%Y-%m-%d %H:%M'
            )
            if new_co_dt <= current_co_dt:
                flash('New checkout must be later than the current planned checkout.', 'danger')
                return redirect(url_for('main.reservations'))
        except ValueError:
            pass  # malformed current checkout — skip comparison

    old_departure = reservation.departure_date
    old_co_time   = reservation.checkout_time

    reservation.departure_date         = new_departure
    reservation.checkout_time          = new_time_str
    reservation.overstay_billed_until  = None    # reset — new checkout window starts fresh

    db.session.commit()
    _write_audit('Reservation', reservation.id, 'hourly_extended',
                 {'departure_date': str(old_departure), 'checkout_time': old_co_time},
                 {'departure_date': str(new_departure), 'checkout_time': new_time_str})

    flash(
        f'Hourly stay extended to {new_departure.strftime("%d %b %Y")} {new_time_str}.',
        'success'
    )
    return redirect(url_for('main.reservations'))


@bp.route('/reservation/<int:reservation_id>/block-room', methods=['POST'])
@login_required
def block_room(reservation_id):
    """Pre-assign a specific room to a reservation before check-in."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status not in ('Reserved', 'Confirmed'):
        flash('Room blocking is only available for Reserved or Confirmed reservations.', 'warning')
        return redirect(url_for('main.reservations'))

    room_id = request.form.get('room_id', type=int)
    if not room_id:
        flash('Please select a room to block.', 'danger')
        return redirect(url_for('main.reservations'))

    room = Room.query.get_or_404(room_id)

    # Verify room is of the correct type
    if room.room_type_id != reservation.room_type_id:
        flash(f'Room {room.room_number} is not of type {reservation.room_type.name}.', 'danger')
        return redirect(url_for('main.reservations'))

    # Verify room is not already blocked/occupied for these dates.
    # Bridge-aware via rooms_held_in_window (Group Stay Phase 1) — catches
    # secondary rooms of multi-room reservations as well as primary rooms.
    # Status set preserved verbatim from the prior implementation.
    from app.services import rooms_held_in_window
    held = rooms_held_in_window(
        [room_id],
        reservation.arrival_date,
        reservation.departure_date,
        exclude_res_id=reservation.id,
        active_statuses=('Confirmed', 'CheckedIn', 'Reserved'),
    )
    if room_id in held:
        flash(f'Room {room.room_number} is already assigned to another reservation for overlapping dates.', 'danger')
        return redirect(url_for('main.reservations'))

    old_room_id = reservation.room_id
    reservation.room_id = room_id
    reservation.status = 'Confirmed'  # upgrade to Confirmed when room is blocked

    # R2A: bridge-write invariant. If this is a re-block (changed room), swap;
    # otherwise mirror. swap_room_in_bridge handles both the orphan-promotion
    # case (no pre-existing bridge row for old_room_id) and the legacy
    # re-block case (bridge row exists for old room).
    from app.services_group_stay import (
        swap_room_in_bridge,
        mirror_room_to_bridge,
    )
    if old_room_id and old_room_id != room_id:
        swap_room_in_bridge(reservation, old_room_id, room_id)
    else:
        mirror_room_to_bridge(reservation)

    db.session.commit()

    _write_audit('Reservation', reservation.id, 'room_blocked',
                 {'room_id': old_room_id},
                 {'room_id': room_id, 'room_number': room.room_number})
    flash(f'Room {room.room_number} blocked for reservation #{reservation.id}.', 'success')
    return redirect(url_for('main.reservations'))


@bp.route('/api/ai/guest-profile/<int:guest_id>')
@login_required
def ai_guest_profile(guest_id):
    """Smart guest profile with learned preferences."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify({'error': 'Permission denied'}), 403
    from app.ai_guest_profile import get_smart_profile
    profile = get_smart_profile(guest_id)
    if not profile:
        return jsonify({'error': 'Guest not found'}), 404
    return jsonify(profile)


@bp.route('/api/ai/housekeeping-schedule')
@login_required
def ai_housekeeping_schedule():
    """AI-optimized housekeeping cleaning schedule."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Housekeeping')
    if denied:
        return jsonify({'error': 'Permission denied'}), 403
    from app.ai_housekeeping import get_housekeeping_scheduler
    scheduler = get_housekeeping_scheduler()
    schedule = scheduler.generate_schedule()
    summary = scheduler.get_summary()
    return jsonify({'schedule': schedule, 'summary': summary})


@bp.route('/api/reservation/<int:reservation_id>/upsell')
@login_required
def upsell_recommendations(reservation_id):
    """AI upsell recommendations for a reservation."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify([]), 403
    reservation = Reservation.query.get_or_404(reservation_id)
    from app.ai_upsell import get_upsell_recommendations
    recommendations = get_upsell_recommendations(reservation)
    return jsonify(recommendations)


@bp.route('/api/reservation/<int:reservation_id>/available-rooms')
@login_required
def available_rooms_for_reservation(reservation_id):
    """API: return rooms available for blocking to a reservation."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify([]), 403
    reservation = Reservation.query.get_or_404(reservation_id)

    # Find rooms of the correct type that aren't occupied/blocked for these dates.
    # Bridge-aware via rooms_held_in_window (Group Stay Phase 1) — checks
    # both Reservation.room_id (legacy primary) AND reservation_rooms
    # (Phase 1+ multi-room secondary rooms). Status set preserved verbatim
    # from the prior implementation: 'Confirmed' + 'CheckedIn' only —
    # 'Reserved' is intentionally not yet treated as holding a room here
    # (the room hasn't been blocked yet).
    from app.services import rooms_held_in_window

    candidate_rooms = Room.query.filter(
        Room.room_type_id == reservation.room_type_id,
        Room.is_active == True,
        Room.is_sellable == True,
        Room.is_out_of_order == False,
    ).order_by(Room.sort_order, Room.room_number).all()

    held_ids = rooms_held_in_window(
        [r.id for r in candidate_rooms],
        reservation.arrival_date,
        reservation.departure_date,
        exclude_res_id=reservation.id,
        active_statuses=('Confirmed', 'CheckedIn'),
    )

    available = [r for r in candidate_rooms if r.id not in held_ids]

    return jsonify([{
        'id': r.id,
        'room_number': r.room_number,
        'floor': r.floor,
        'status': r.status,
    } for r in available])


@bp.route('/reservation/<int:reservation_id>/room-change', methods=['POST'])
@login_required
def room_change(reservation_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    new_room_id = request.form.get('new_room_id', type=int)
    if not new_room_id:
        flash('Please select a room.', 'danger')
        return redirect(url_for('main.reservations'))

    try:
        # Pessimistic lock: lock reservation, old room, and new room
        reservation = (db.session.query(Reservation)
                       .with_for_update(of=Reservation)
                       .filter_by(id=reservation_id)
                       .first_or_404())
        if reservation.status != 'CheckedIn':
            db.session.rollback()
            flash('Room change is only allowed for checked-in reservations.', 'warning')
            return redirect(url_for('main.reservations'))

        new_room = (db.session.query(Room)
                    .with_for_update()
                    .filter_by(id=new_room_id)
                    .first_or_404())
        if new_room.status != 'Vacant':
            db.session.rollback()
            flash(f'Room {new_room.room_number} is not vacant (status: {new_room.status}).', 'danger')
            return redirect(url_for('main.reservations'))

        old_room = None
        old_room_num = '—'
        if reservation.room_id:
            old_room = (db.session.query(Room)
                        .with_for_update()
                        .filter_by(id=reservation.room_id)
                        .first())
            old_room_num = old_room.room_number if old_room else '—'

        # Release old room
        if old_room:
            old_room.status = 'Dirty'
        # Assign new room
        new_room.status = 'Occupied'
        reservation.room_id = new_room_id

        # R2A: bridge-write invariant — swap old→new in reservation_rooms.
        # Handles orphan-promotion if old room had no bridge row.
        from app.services_group_stay import swap_room_in_bridge
        swap_room_in_bridge(
            reservation,
            old_room.id if old_room else None,
            new_room_id,
        )

        # If the room type changed, update room_type_id and recalculate rate
        old_rate = float(reservation.rate_per_night)
        old_room_type_id = reservation.room_type_id
        rate_changed = False
        if new_room.room_type_id != old_room_type_id:
            reservation.room_type_id = new_room.room_type_id
            new_rate = get_applicable_rate(
                new_room.room_type_id,
                reservation.arrival_date,
                reservation.departure_date,
            )
            reservation.rate_per_night = new_rate
            rate_changed = True

        db.session.commit()

        # Build audit trail
        before_state = {'room': old_room_num}
        after_state = {'room': new_room.room_number}
        if rate_changed:
            before_state['rate_per_night'] = str(old_rate)
            before_state['room_type_id'] = old_room_type_id
            after_state['rate_per_night'] = str(float(reservation.rate_per_night))
            after_state['room_type_id'] = reservation.room_type_id

        _write_audit('Reservation', reservation.id, 'room_changed',
                     before_state, after_state)

        if rate_changed:
            flash(
                f'Room changed from {old_room_num} to {new_room.room_number}. '
                f'Room type changed — rate updated from ₹{old_rate:.2f} to '
                f'₹{float(reservation.rate_per_night):.2f}. Old room marked Dirty.',
                'success',
            )
        else:
            flash(f'Room changed from {old_room_num} to {new_room.room_number}. Old room marked Dirty.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error('Room change failed: %s', e, exc_info=True)
        flash('Room change failed. Please try again.', 'danger')
    return redirect(url_for('main.reservations'))


# ---------------------------------------------------------------------------
# Room Grid / Tape Chart
# ---------------------------------------------------------------------------

@bp.route('/room-grid')
def room_grid():
    from datetime import date as _date
    business_date = get_business_date()
    view   = request.args.get('view', '14days')
    offset = request.args.get('offset', 0, type=int)

    # num_days and nav_step per view mode
    if view == 'today':
        num_days = 1;  nav_step = 1
    elif view == '7days':
        num_days = 7;  nav_step = 7
    elif view == 'weekly':
        num_days = 7;  nav_step = 7
    elif view == 'monthly':
        num_days = 30; nav_step = 30
    else:  # '14days' default
        num_days = 14; nav_step = 14

    start_date = business_date + timedelta(days=offset)
    end_date   = start_date + timedelta(days=num_days - 1)
    dates      = [start_date + timedelta(days=i) for i in range(num_days)]
    today      = business_date

    rooms  = Room.query.order_by(Room.floor, Room.room_number).all()
    floors = sorted(set(r.floor for r in rooms))

    # Fetch all reservations overlapping the date window
    active_statuses = ['Reserved', 'Confirmed', 'CheckedIn', 'Blocked', 'Overbooked']
    reservations = Reservation.query.filter(
        Reservation.status.in_(active_statuses),
        Reservation.arrival_date < end_date + timedelta(days=1),
        Reservation.departure_date > start_date,
    ).all()

    # Build grid: {room_id: {date: cell_dict}}
    grid = {}
    for res in reservations:
        if not res.room_id:
            continue
        # guest_fmt: FirstName + LastInitial
        _gname = (res.guest.name if res.guest and res.guest.name else '') if res.guest else ''
        _parts  = _gname.split()
        if len(_parts) >= 2:
            _guest_fmt = _parts[0] + ' ' + _parts[-1][0] + '.'
        else:
            _guest_fmt = (_parts[0][:8] if _parts else '')

        # cell_type: confirmed = has advance payment; reserved = no advance payment
        if res.status == 'CheckedIn':
            _cell_type = 'checkedin'
        elif res.status in ('Reserved', 'Confirmed'):
            _adv = float(res.advance_payment or 0)
            _cell_type = 'confirmed' if _adv > 0 else 'reserved'
        else:
            _cell_type = 'reserved'

        for d in dates:
            if res.arrival_date <= d < res.departure_date:
                if res.room_id not in grid:
                    grid[res.room_id] = {}
                _nights = (res.departure_date - res.arrival_date).days
                grid[res.room_id][d] = {
                    'type':          _cell_type,
                    'res_id':        res.id,
                    'room_id':       res.room_id,
                    'room_type_id':  res.room_type_id,
                    'guest':         _gname,
                    'guest_fmt':     _guest_fmt,
                    'arrival':       res.arrival_date.strftime('%d %b'),
                    'arrival_iso':   res.arrival_date.isoformat(),
                    'departure':     res.departure_date.strftime('%d %b'),
                    'departure_iso': res.departure_date.isoformat(),
                    'nights':        _nights,
                    'booking_type':       res.booking_type or 'Regular',
                    'checkout_time':      res.checkout_time or '',
                    'checkout_initiated': res.checkout_initiated or False,
                    'start':              d == res.arrival_date,
                    'end':           d == res.departure_date - timedelta(days=1),
                    'source':        res.source or '',
                }

    # Overlay room status for rooms with no reservation on a date
    for room in rooms:
        if room.status in ('Dirty', 'Maintenance'):
            for d in dates:
                if room.id not in grid or d not in grid.get(room.id, {}):
                    if room.id not in grid:
                        grid[room.id] = {}
                    if d not in grid[room.id]:
                        grid[room.id][d] = {'type': room.status.lower()}

    _co_row2 = Settings.query.filter_by(key='default_checkout_time').first()
    _co_val2 = (_co_row2.value or '').strip() if _co_row2 else ''
    rg_default_checkout_hm = (
        _co_val2
        if len(_co_val2) == 5 and _co_val2[2:3] == ':' and _co_val2[:2].isdigit() and _co_val2[3:].isdigit()
        else '12:00'
    )
    return render_template('room_grid.html',
                           rooms=rooms, floors=floors, dates=dates,
                           start_date=start_date, end_date=end_date,
                           today=today, offset=offset, grid=grid,
                           view=view, nav_step=nav_step,
                           default_checkout_hm=rg_default_checkout_hm)


# ---------------------------------------------------------------------------
# Planning Board — Move reservation (room + date shift)
# ---------------------------------------------------------------------------

@bp.route('/api/reservation/move', methods=['POST'])
@login_required
def api_reservation_move():
    data        = request.get_json(silent=True) or {}
    res_id      = data.get('reservation_id')
    new_room_id = data.get('new_room_id')
    date_shift  = int(data.get('date_shift', 0))

    if not res_id:
        return jsonify({'ok': False, 'error': 'reservation_id required'}), 400

    try:
        # Pessimistic lock: lock reservation row to prevent concurrent moves
        res = (db.session.query(Reservation)
               .with_for_update(of=Reservation)
               .filter_by(id=res_id)
               .first())
        if not res:
            db.session.rollback()
            return jsonify({'ok': False, 'error': 'Reservation not found'}), 404

        # Permission: CheckedIn only for Manager/Admin
        if res.status == 'CheckedIn':
            if current_user.role not in ('Admin', 'Manager'):
                db.session.rollback()
                return jsonify({'ok': False, 'error': 'Checked-in reservations can only be moved by Manager or Admin'}), 403
        if res.status in ('CheckedOut', 'Cancelled', 'NoShow'):
            db.session.rollback()
            return jsonify({'ok': False, 'error': 'Cannot move a completed reservation'}), 400

        old_room_id   = res.room_id
        old_arrival   = res.arrival_date
        old_departure = res.departure_date
        duration      = (old_departure - old_arrival).days

        target_room_id = int(new_room_id) if new_room_id else old_room_id
        new_arrival    = old_arrival   + timedelta(days=date_shift)
        new_departure  = new_arrival   + timedelta(days=duration)

        # Lock target room to prevent concurrent assignment
        room = (db.session.query(Room)
                .with_for_update()
                .filter_by(id=target_room_id)
                .first())
        if not room:
            db.session.rollback()
            return jsonify({'ok': False, 'error': 'Target room not found'}), 400

        # Room type must match
        if room.room_type_id != res.room_type_id:
            db.session.rollback()
            return jsonify({'ok': False,
                            'error': f'Room {room.room_number} is type "{room.room_type.name}" — reservation requires "{res.room_type.name}"'}), 409

        # Room must not be Maintenance/Blocked
        if room.status in ('Maintenance', 'Blocked'):
            db.session.rollback()
            return jsonify({'ok': False,
                            'error': f'Room {room.room_number} is {room.status} and cannot accept bookings'}), 409

        # No overlap with another reservation.
        # R7 fix (R2A): bridge-aware conflict detection — also catches
        # secondary rooms of multi-room reservations. Previously this used
        # a direct Reservation.room_id == query which would silently allow
        # double-bookings on a SECONDARY room of another multi-room hold.
        from app.services import rooms_held_in_window
        held_ids = rooms_held_in_window(
            [target_room_id],
            new_arrival,
            new_departure,
            exclude_res_id=res_id,
            active_statuses=('Reserved', 'Confirmed', 'CheckedIn'),
        )
        if target_room_id in held_ids:
            db.session.rollback()
            return jsonify({'ok': False,
                            'error': f'Room {room.room_number} is occupied — conflicts with another reservation'}), 409

        # Apply
        before = {
            'room_id':        old_room_id,
            'arrival_date':   old_arrival.isoformat(),
            'departure_date': old_departure.isoformat(),
        }
        res.room_id       = target_room_id
        res.arrival_date  = new_arrival
        res.departure_date = new_departure

        # R2A: bridge-write invariant — swap old→new if room changed.
        if target_room_id != old_room_id:
            from app.services_group_stay import swap_room_in_bridge
            swap_room_in_bridge(res, old_room_id, target_room_id)
        elif old_room_id:
            # Date-only shift: ensure bridge row exists for orphan rows.
            from app.services_group_stay import mirror_room_to_bridge
            mirror_room_to_bridge(res)

        action_parts = []
        if target_room_id != old_room_id: action_parts.append('moved_room')
        if date_shift != 0:               action_parts.append('moved_date')
        action = '_'.join(action_parts) or 'moved'

        _write_audit('Reservation', res_id, action, before, {
            'room_id':        target_room_id,
            'arrival_date':   new_arrival.isoformat(),
            'departure_date': new_departure.isoformat(),
        })
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

    old_room = Room.query.get(old_room_id)
    return jsonify({
        'ok':           True,
        'message':      f'Reservation #{res_id} moved to Room {room.room_number}',
        'reservation_id': res_id,
        'new_room_id':  target_room_id,
        'new_room_number': room.room_number,
        'new_arrival':  new_arrival.isoformat(),
        'new_departure': new_departure.isoformat(),
    })


# ---------------------------------------------------------------------------
# Planning Board — Resize reservation (change departure date)
# ---------------------------------------------------------------------------

@bp.route('/api/reservation/resize', methods=['POST'])
@login_required
def api_reservation_resize():
    data            = request.get_json(silent=True) or {}
    res_id          = data.get('reservation_id')
    new_dep_str     = data.get('new_departure')

    if not res_id or not new_dep_str:
        return jsonify({'ok': False, 'error': 'reservation_id and new_departure required'}), 400

    res = Reservation.query.get(res_id)
    if not res:
        return jsonify({'ok': False, 'error': 'Reservation not found'}), 404

    if res.status == 'CheckedIn':
        if current_user.role not in ('Admin', 'Manager'):
            return jsonify({'ok': False, 'error': 'Cannot resize a checked-in reservation'}), 403
    if res.status in ('CheckedOut', 'Cancelled', 'NoShow'):
        return jsonify({'ok': False, 'error': 'Cannot resize a completed reservation'}), 400

    try:
        new_departure = date.fromisoformat(new_dep_str)
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid departure date format'}), 400

    if new_departure <= res.arrival_date:
        return jsonify({'ok': False, 'error': 'Departure date must be after arrival date'}), 400

    old_departure = res.departure_date

    # Check for overlap when extending
    if new_departure > old_departure:
        conflict = Reservation.query.filter(
            Reservation.id != res_id,
            Reservation.room_id == res.room_id,
            Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn']),
            Reservation.arrival_date < new_departure,
            Reservation.departure_date > old_departure,
        ).first()
        if conflict:
            return jsonify({'ok': False,
                            'error': f'Extension blocked — reservation #{conflict.id} starts before new departure'}), 409

    nights = (new_departure - res.arrival_date).days
    _write_audit('Reservation', res_id, 'resized_stay',
                 {'departure_date': old_departure.isoformat(), 'nights': (old_departure - res.arrival_date).days},
                 {'departure_date': new_departure.isoformat(), 'nights': nights})

    res.departure_date = new_departure
    db.session.commit()

    return jsonify({
        'ok':           True,
        'message':      f'Stay updated to {new_departure.strftime("%d %b %Y")} ({nights} nights)',
        'reservation_id': res_id,
        'new_departure': new_departure.isoformat(),
        'nights':        nights,
    })


# ---------------------------------------------------------------------------
# Housekeeping Mobile View
# ---------------------------------------------------------------------------

@bp.route('/hk')
@login_required
def hk_mobile():
    floor_filter = request.args.get('floor', type=int)
    query = Room.query
    if floor_filter:
        query = query.filter_by(floor=floor_filter)
    rooms = query.order_by(Room.floor, Room.room_number).all()
    floors = sorted(set(r.floor for r in Room.query.all()))
    dirty_count = sum(1 for r in rooms if r.status == 'Dirty')
    maintenance_count = sum(1 for r in rooms if r.status == 'Maintenance')
    return render_template('hk/mobile.html',
                           rooms=rooms, floors=floors,
                           dirty_count=dirty_count,
                           maintenance_count=maintenance_count,
                           floor_filter=floor_filter)


@bp.route('/reservation/<int:reservation_id>/cancel', methods=['POST'])
@login_required
def cancel_reservation(reservation_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return denied
    reservation = Reservation.query.get_or_404(reservation_id)
    # Lock guard: block cancellation if arrival date is locked
    from app.services import (assert_business_date_unlocked, advance_summary,
                              post_cancellation_disposition)
    ok, lock_err = assert_business_date_unlocked(reservation.arrival_date, 'cancel reservation')
    if not ok:
        flash(lock_err, 'danger')
        return redirect(url_for('main.reservations'))

    if reservation.status not in ('Reserved', 'Confirmed', 'Overbooked'):
        flash('Cannot cancel a reservation that is already checked in or checked out', 'warning')
        return redirect(url_for('main.reservations'))

    # ── Read disposition fields from form ─────────────────────────────
    summary = advance_summary(reservation)
    has_advance = summary['net_advance'] > 0.005
    disposition = (request.form.get('cancel_disposition') or '').strip()
    reason      = (request.form.get('cancel_reason') or '').strip()

    # If there's an advance, disposition + reason are mandatory.
    if has_advance:
        if disposition not in ('refund_full', 'refund_partial',
                                'forfeit', 'credit_voucher'):
            flash('Choose how to handle the advance: refund, partial refund, '
                  'forfeit, or credit voucher.', 'danger')
            return redirect(url_for('main.reservations'))
        if not reason:
            flash('Cancellation reason is required when an advance has been collected.', 'danger')
            return redirect(url_for('main.reservations'))
    else:
        # No advance — record the symmetry row so the audit trail still shows it.
        disposition = 'no_advance'
        if not reason:
            reason = 'Cancellation (no advance on file)'

    refund_amount  = 0.0
    voucher_amount = 0.0
    refund_mode_id = None
    refund_ref     = None
    try:
        if disposition == 'refund_partial':
            refund_amount = float(request.form.get('cancel_refund_amount') or 0)
        if disposition in ('refund_full', 'refund_partial'):
            refund_mode_id = int(request.form.get('cancel_refund_mode_id') or 0) or None
            refund_ref     = (request.form.get('cancel_refund_reference') or '').strip() or None
        if disposition == 'credit_voucher':
            voucher_amount = float(request.form.get('cancel_voucher_amount') or 0)
    except ValueError:
        flash('Invalid number entered for refund / voucher amount.', 'danger')
        return redirect(url_for('main.reservations'))

    # ── Forfeit approval gate (route-side role enforcement) ───────────
    # Forfeit ALWAYS requires Manager or Admin (the route's _deny_role
    # check above already covers this). When the projected forfeit
    # exceeds the configured threshold, additionally require Admin.
    from app.services import get_forfeit_approval_threshold as _gft
    available = summary['net_advance']  # advance net of any prior refund
    projected_forfeit = 0.0
    if disposition == 'forfeit':
        projected_forfeit = available
    elif disposition == 'refund_partial':
        projected_forfeit = max(0.0, round(available - refund_amount, 2))
    elif disposition == 'credit_voucher':
        projected_forfeit = max(0.0, round(available - voucher_amount, 2))

    is_admin = bool(current_user.is_authenticated and current_user.has_role('Admin'))
    is_manager = bool(current_user.is_authenticated and current_user.has_role('Admin', 'Manager'))

    if projected_forfeit > 0.005 and not is_manager:
        flash('Forfeit requires Manager or Admin authorisation.', 'danger')
        return redirect(url_for('main.reservations'))

    forfeit_threshold = _gft()
    approver_is_admin = False
    approver_user_id  = None
    approval_reason   = (request.form.get('forfeit_approval_reason') or '').strip()
    if projected_forfeit > forfeit_threshold + 0.005:
        approval_chk = request.form.get('forfeit_admin_approval') == '1'
        if not is_admin:
            flash(f'Forfeit ₹{projected_forfeit:,.2f} exceeds ₹{forfeit_threshold:,.0f} '
                  f'threshold — only an Admin may approve.', 'danger')
            return redirect(url_for('main.reservations'))
        if not approval_chk or not approval_reason:
            flash(f'Admin approval (with written reason) is required for a '
                  f'forfeit of ₹{projected_forfeit:,.2f}.', 'danger')
            return redirect(url_for('main.reservations'))
        approver_is_admin = True
        approver_user_id  = current_user.id

    old_status = reservation.status
    try:
        result = post_cancellation_disposition(
            reservation,
            disposition       = disposition,
            refund_amount     = refund_amount,
            refund_mode_id    = refund_mode_id,
            refund_reference  = refund_ref,
            voucher_amount    = voucher_amount,
            reason            = reason,
            user_id           = current_user.id,
            approver_user_id  = approver_user_id,
            approver_is_admin = approver_is_admin,
            approval_reason   = approval_reason or None,
            audit_writer      = _write_audit,
        )
        reservation.status = 'Cancelled'
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('main.reservations'))
    except Exception:
        db.session.rollback()
        logger.exception('cancel_reservation failed for res=%d', reservation_id)
        flash('Cancellation failed. See server logs.', 'danger')
        return redirect(url_for('main.reservations'))

    _write_audit('Reservation', reservation.id, 'cancelled',
                 {'status': old_status},
                 {'status': 'Cancelled',
                  'disposition': disposition,
                  'refund_amount': result['refund_amount'],
                  'forfeit_amount': result['forfeit_amount'],
                  'voucher_amount': result['voucher_amount']})

    # Cancellation WhatsApp + email notification (non-blocking)
    try:
        from flask import current_app
        from app.notifications import notify_booking_cancelled
        notify_booking_cancelled(reservation, app=current_app._get_current_object())
    except Exception:
        pass

    # Build user-facing summary
    parts = []
    if result['refund_amount'] > 0.005:
        parts.append(f'Refund ₹{result["refund_amount"]:,.2f}')
    if result['forfeit_amount'] > 0.005:
        parts.append(f'Forfeit ₹{result["forfeit_amount"]:,.2f}')
    if result['voucher_amount'] > 0.005:
        if result.get('voucher_code'):
            parts.append(f'Credit Voucher ₹{result["voucher_amount"]:,.2f} ({result["voucher_code"]})')
        else:
            parts.append(f'Credit Voucher ₹{result["voucher_amount"]:,.2f}')
    detail = ' · '.join(parts) if parts else 'No advance on file'
    flash(f'Reservation cancelled — {detail}.', 'success')
    return redirect(url_for('main.reservations'))


# ===========================================================================
# ADMIN — Duplicate Active Check-in Cleanup
# ===========================================================================

@bp.route('/admin/duplicate-checkins')
@login_required
def admin_duplicate_checkins():
    """List rooms that have more than one CheckedIn reservation."""
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied

    # Find room_ids with multiple CheckedIn reservations
    from sqlalchemy import func as _f
    dup_room_ids = (db.session.query(Reservation.room_id)
                   .filter(Reservation.status == 'CheckedIn',
                           Reservation.room_id.isnot(None))
                   .group_by(Reservation.room_id)
                   .having(_f.count(Reservation.id) > 1)
                   .all())
    dup_room_ids = [r[0] for r in dup_room_ids]

    groups = []
    for room_id in dup_room_ids:
        room = Room.query.get(room_id)
        reservations = (Reservation.query
                        .filter_by(room_id=room_id, status='CheckedIn')
                        .order_by(Reservation.checked_in_at)
                        .all())
        groups.append({'room': room, 'reservations': reservations})

    return render_template('admin/duplicate_checkins.html', groups=groups)


@bp.route('/admin/duplicate-checkins/action', methods=['POST'])
@login_required
def admin_duplicate_checkin_action():
    """Force-checkout or cancel a specific reservation from the cleanup tool."""
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied

    reservation_id = request.form.get('reservation_id', type=int)
    action = request.form.get('action')  # 'force_checkout' | 'cancel'

    if not reservation_id or action not in ('force_checkout', 'cancel'):
        flash('Invalid request.', 'danger')
        return redirect(url_for('main.admin_duplicate_checkins'))

    try:
        # Pessimistic lock on reservation and its room
        reservation = (db.session.query(Reservation)
                       .with_for_update(of=Reservation)
                       .filter_by(id=reservation_id)
                       .first_or_404())
        if reservation.status != 'CheckedIn':
            db.session.rollback()
            flash(f'Reservation #{reservation_id} is not checked-in; no action taken.', 'warning')
            return redirect(url_for('main.admin_duplicate_checkins'))

        locked_room = None
        if reservation.room_id:
            locked_room = db.session.query(Room).with_for_update().filter_by(id=reservation.room_id).first()

        old_status = reservation.status
        if action == 'force_checkout':
            reservation.status = 'CheckedOut'
            reservation.checked_out_at = datetime.utcnow()
            reservation.checkout_time = datetime.now().strftime('%H:%M')
            # Free the room only if no other CheckedIn res holds it
            _still_occupied = (Reservation.query
                               .filter(Reservation.room_id == reservation.room_id,
                                       Reservation.status == 'CheckedIn',
                                       Reservation.id != reservation_id)
                               .count())
            if not _still_occupied and reservation.room:
                reservation.room.status = 'Dirty'
            db.session.commit()
            _write_audit('Reservation', reservation_id, 'admin_force_checkout',
                         {'status': old_status},
                         {'status': 'CheckedOut', 'reason': 'duplicate cleanup'})
            flash(f'Reservation #{reservation_id} force-checked-out.', 'success')

        elif action == 'cancel':
            reservation.status = 'Cancelled'
            db.session.commit()
            _write_audit('Reservation', reservation_id, 'admin_cancel_duplicate',
                         {'status': old_status},
                         {'status': 'Cancelled', 'reason': 'duplicate cleanup'})
            flash(f'Reservation #{reservation_id} cancelled.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error('Action failed: %s', e, exc_info=True)
        flash('Action failed. Please try again.', 'danger')

    return redirect(url_for('main.admin_duplicate_checkins'))


# ---------------------------------------------------------------------------
# Admin: Convert overpayment to upsell — repair stuck reservations
# ---------------------------------------------------------------------------
# Used when the room was sold above standard tariff but the system was
# checked in at the lower standard rate. The guest's full payment then
# appears as an "overpayment" and the checkout flow gets stuck (especially
# combined with the GST-on-resolution-ExtraCharge ghost-balance trap, now
# fixed). This route bumps rate_per_night to absorb the excess as recognised
# UPSELL revenue, posts the corrective ledger row, and writes an audit
# entry. Safe to call on CheckedIn or CheckedOut reservations; refuses
# when there is no actual overpayment.

@bp.route('/admin/reservation/<int:reservation_id>/convert-overpay-to-upsell',
          methods=['POST'])
@login_required
def admin_convert_overpay_to_upsell(reservation_id):
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied

    reason = (request.form.get('reason') or '').strip() or None
    next_url = request.form.get('next') or request.referrer or \
               url_for('main.dashboard')

    try:
        reservation = (db.session.query(Reservation)
                       .with_for_update()
                       .filter_by(id=reservation_id)
                       .first_or_404())

        if reservation.status not in ('CheckedIn', 'CheckedOut'):
            db.session.rollback()
            flash(f'Reservation #{reservation_id} is "{reservation.status}" — '
                  f'upsell conversion only applies to CheckedIn / CheckedOut.',
                  'warning')
            return redirect(next_url)

        # Snapshot before-state for the audit row
        before = {
            'rate_per_night':    str(float(reservation.rate_per_night or 0)),
            'standard_tariff':   str(float(reservation.standard_tariff or 0)),
            'adjustment_type':   reservation.adjustment_type,
            'adjustment_amount': str(float(reservation.adjustment_amount or 0)),
        }
        billing_before = calculate_stay_amount(reservation)

        from app.services import convert_overpayment_to_upsell
        result = convert_overpayment_to_upsell(
            reservation,
            reason=reason,
            authorized_by_user_id=(current_user.id
                                   if current_user.is_authenticated else None),
        )

        if not result.get('ok'):
            db.session.rollback()
            flash(result.get('error') or
                  'Could not convert overpayment to upsell.', 'warning')
            return redirect(next_url)

        # Recompute live billing so we can report the new state
        db.session.expire(reservation, ['payments', 'extra_charges'])
        billing_after = calculate_stay_amount(reservation)

        db.session.commit()

        _write_audit(
            'Reservation', reservation_id,
            'admin_convert_overpay_to_upsell',
            before,
            {
                'rate_per_night':       str(float(reservation.rate_per_night or 0)),
                'adjustment_type':      reservation.adjustment_type,
                'adjustment_amount':    str(float(reservation.adjustment_amount or 0)),
                'overpay_gross':        str(float(result.get('overpay_gross', 0))),
                'pretax_increment':     str(float(result.get('pretax_increment', 0))),
                'gst_rate_applied':     str(float(result.get('gst_rate_applied', 0))),
                'branch':               result.get('branch'),
                'reason':               reason,
                'balance_before':       str(float(billing_before.get('balance', 0))),
                'balance_after':        str(float(billing_after.get('balance', 0))),
            }
        )

        flash(
            f'Overpayment of ₹{float(result["overpay_gross"]):,.2f} converted '
            f'to Upsell on Reservation #{reservation_id}. '
            f'Rate/night: ₹{float(result["old_rate_per_night"]):,.2f} → '
            f'₹{float(result["new_rate_per_night"]):,.2f}. '
            f'Balance now ₹{float(billing_after.get("balance", 0)):,.2f}.',
            'success'
        )
    except Exception as e:
        db.session.rollback()
        logger.exception(
            'admin_convert_overpay_to_upsell failed for res=%d', reservation_id)
        flash(f'Conversion failed: {e}', 'danger')

    return redirect(next_url)


# ---------------------------------------------------------------------------
# LAN Access toggle (Admin-only — writes .env)
# ---------------------------------------------------------------------------
# Mirrors the enable_lan.bat / disable_lan.bat shell helpers but exposes
# the toggle in the UI so admins don't have to open a terminal. Writes are
# line-oriented on .env so existing unrelated entries are preserved.
# Takes effect only after a server restart (the bind host is read once at
# startup by start.bat); the UI makes that requirement explicit.

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')


def _read_allow_lan_flag() -> bool:
    """Read ALLOW_LAN from the .env file. Truthy = 1/true/yes (ci)."""
    try:
        with open(_ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                k, _, v = line.partition('=')
                if k.strip().upper() == 'ALLOW_LAN':
                    return v.strip().lower() in ('1', 'true', 'yes')
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning('read ALLOW_LAN from .env failed: %s', e)
    return False


def _write_allow_lan_flag(enable: bool) -> tuple[bool, str]:
    """Rewrite .env so the ALLOW_LAN line reflects `enable`. Idempotent —
    creates the key if absent, replaces it if present. Returns (ok, msg)."""
    try:
        try:
            with open(_ENV_PATH, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            return False, '.env file not found. Contact the installer.'
        target_value = '1' if enable else '0'
        replaced = False
        new_lines = []
        for line in lines:
            k, _, _v = line.partition('=')
            if k.strip().upper() == 'ALLOW_LAN':
                new_lines.append(f'ALLOW_LAN={target_value}')
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f'ALLOW_LAN={target_value}')
        tmp_path = _ENV_PATH + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')
        os.replace(tmp_path, _ENV_PATH)
        return True, ''
    except PermissionError:
        return False, ('Could not write .env — file is read-only. '
                       'Close any editor, then retry.')
    except Exception as e:
        logger.exception('write ALLOW_LAN to .env failed')
        return False, f'Unexpected error: {e}'


@bp.route('/admin/lan-access', methods=['GET', 'POST'])
@login_required
def admin_lan_access():
    """Admin toggle for LAN multi-user access."""
    denied = _deny_role('Admin')
    if denied:
        return denied

    current_port = os.getenv('PORT') or '5000'
    current_enabled = _read_allow_lan_flag()
    server_bound_lan = (os.getenv('ALLOW_LAN') or '0').strip().lower() in ('1', 'true', 'yes')
    restart_required = False

    if request.method == 'POST':
        want = request.form.get('allow_lan') == '1'
        ok, msg = _write_allow_lan_flag(want)
        if not ok:
            flash(msg, 'danger')
        else:
            _write_audit('System', 0, 'lan_access_toggled',
                         {'enabled': current_enabled},
                         {'enabled': want, 'port': current_port})
            flash(
                ('LAN access ENABLED.' if want else 'LAN access DISABLED.') +
                ' Restart the server for the change to take effect. '
                'Run enable_lan.bat (admin) to also open the Windows Firewall port.'
                if want else
                ('LAN access DISABLED. Restart the server to rebind to localhost.'),
                'success'
            )
            current_enabled = want

    # restart_required is true when the on-disk flag disagrees with what
    # the running server has bound to.
    restart_required = (current_enabled != server_bound_lan)
    return render_template(
        'admin/lan_access.html',
        allow_lan_on_disk=current_enabled,
        allow_lan_running=server_bound_lan,
        restart_required=restart_required,
        port=current_port,
    )


# ---------------------------------------------------------------------------
# Night Audit: mark a CheckedOut folio's outstanding as Individual Credit,
# so the audit blocker clears without forcing the cashier to open a fresh
# checkout flow on a row that is already CheckedOut.
# ---------------------------------------------------------------------------

@bp.route('/night-audit/mark-receivable', methods=['POST'])
@login_required
def night_audit_mark_receivable():
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied
    try:
        reservation_id = int(request.form.get('reservation_id') or 0)
    except (TypeError, ValueError):
        flash('Invalid reservation id.', 'danger')
        return redirect(url_for('reports.night_audit'))
    reason      = (request.form.get('reason') or '').strip()
    approved_by = (request.form.get('approved_by') or '').strip()

    if reservation_id <= 0:
        flash('Reservation id is required.', 'danger')
        return redirect(url_for('reports.night_audit'))
    if not reason or not approved_by:
        flash('Reason and Approved By are both required.', 'danger')
        return redirect(url_for('reports.night_audit'))

    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status != 'CheckedOut':
        flash('Mark Receivable is only valid for CheckedOut folios.', 'warning')
        return redirect(url_for('reports.night_audit'))

    from app.services import calculate_stay_amount as _calc
    billing = _calc(reservation)
    outstanding = round(float(billing.get('balance', 0) or 0), 2)
    if outstanding <= 0.005:
        flash('No outstanding balance on this folio — nothing to mark as receivable.',
              'info')
        return redirect(url_for('reports.night_audit'))

    # Snapshot onto Reservation.credit_amount — same shape as Individual Credit
    # at checkout. If a credit row already exists, add to it (handles repeat
    # marks). Audit-log so the AuditLog tells the full story.
    prior_credit = float(reservation.credit_amount or 0)
    reservation.credit_amount             = round(prior_credit + outstanding, 2)
    if not reservation.credit_reason:
        reservation.credit_reason         = (f'{reason} | Mark-receivable from Night Audit')[:200]
    if reservation.credit_approved_by_user_id is None:
        reservation.credit_approved_by_user_id = current_user.id
        reservation.credit_approved_at    = datetime.utcnow()

    _write_audit('Reservation', reservation.id, 'mark_receivable_from_night_audit',
                 {'prior_credit_amount': prior_credit,
                  'balance_at_mark':     outstanding},
                 {'new_credit_amount':   float(reservation.credit_amount),
                  'reason':              reason[:200],
                  'approved_by':         approved_by[:100],
                  'by_user_id':          current_user.id})
    db.session.commit()

    flash(f'Outstanding ₹{outstanding:,.2f} for {reservation.guest.name if reservation.guest else "guest"} '
          f'moved to Individual Credit. Folio will no longer block the audit.', 'success')
    return redirect(url_for('reports.night_audit'))


# ---------------------------------------------------------------------------
# Settle Individual Credit — receive a payment against a credit-checked-out
# folio, advance credit_settled_amount, and audit-log the recovery.
# ---------------------------------------------------------------------------

@bp.route('/credit/<int:reservation_id>/settle', methods=['GET', 'POST'])
@login_required
def settle_credit(reservation_id):
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return denied

    reservation = Reservation.query.get_or_404(reservation_id)
    original = float(reservation.credit_amount or 0)
    if original <= 0.005:
        flash('This reservation has no individual credit on record.', 'warning')
        return redirect(url_for('reports.credit_ledger'))

    from app.services import credit_status, apply_credit_settlement, calculate_stay_amount
    status = credit_status(reservation)
    settled = float(reservation.credit_settled_amount or 0)
    remaining = max(0.0, round(original - settled, 2))

    payment_modes = (PaymentMode.query
                     .filter_by(is_active=True, category='direct_payment')
                     .all())

    if request.method == 'POST':
        if status == 'Settled':
            flash('This credit is already fully settled.', 'info')
            return redirect(url_for('reports.credit_ledger'))

        try:
            amount = float(request.form.get('amount', '0') or 0)
        except ValueError:
            amount = 0.0
        try:
            mode_id = int(request.form.get('payment_mode_id', '0') or 0)
        except ValueError:
            mode_id = 0
        ref_no = (request.form.get('reference_number') or '').strip()
        notes  = (request.form.get('notes') or '').strip()

        if amount <= 0.01:
            flash('Enter a valid amount greater than zero.', 'danger')
            return redirect(url_for('main.settle_credit', reservation_id=reservation_id))
        if amount > remaining + 0.01:
            flash(f'Amount ₹{amount:,.2f} exceeds remaining credit ₹{remaining:,.2f}.', 'danger')
            return redirect(url_for('main.settle_credit', reservation_id=reservation_id))
        if mode_id <= 0:
            flash('Select a payment mode.', 'danger')
            return redirect(url_for('main.settle_credit', reservation_id=reservation_id))

        pm = db.session.get(PaymentMode, mode_id)
        if pm is None or pm.category != 'direct_payment':
            flash('Invalid payment mode.', 'danger')
            return redirect(url_for('main.settle_credit', reservation_id=reservation_id))

        try:
            payment = Payment(
                reservation_id   = reservation.id,
                amount           = amount,
                payment_mode_id  = mode_id,
                payment_date     = get_business_date(),
                reference_number = ref_no or None,
                notes            = (notes or None),
                payment_purpose  = 'credit_recovery',
            )
            db.session.add(payment)
            db.session.flush()

            apply_credit_settlement(reservation, amount,
                                    by_user_id=current_user.id,
                                    ref_payment_id=payment.id,
                                    audit_writer=_write_audit)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.exception('Credit settlement failed for res=%d: %s',
                             reservation_id, exc)
            flash('Credit settlement failed. See server logs.', 'danger')
            return redirect(url_for('main.settle_credit', reservation_id=reservation_id))

        new_status = credit_status(reservation)
        if new_status == 'Settled':
            flash(f'Credit fully settled — ₹{amount:,.2f} received via {pm.name}.', 'success')
        else:
            flash(f'Partial credit recovery — ₹{amount:,.2f} received via {pm.name}. '
                  f'Remaining ₹{(remaining - amount):,.2f}.', 'success')
        return redirect(url_for('reports.credit_ledger'))

    return render_template('settle_credit.html',
                           reservation=reservation,
                           original=original,
                           settled=settled,
                           remaining=remaining,
                           status=status,
                           payment_modes=payment_modes,
                           billing=calculate_stay_amount(reservation))


# ---------------------------------------------------------------------------
# Credit Voucher — JSON lookup + redeem against a reservation + admin actions
# ---------------------------------------------------------------------------

@bp.route('/api/voucher/lookup')
@login_required
def voucher_lookup():
    """Return a voucher's live state by code. Used by the booking UI to
    pre-validate before applying. 404 if not found."""
    denied = _deny_role('Admin', 'Manager', 'FrontDesk', 'Accountant')
    if denied:
        return jsonify({'error': 'Permission denied'}), 403
    code = (request.args.get('code') or '').strip().upper()
    if not code:
        return jsonify({'error': 'voucher code is required'}), 400
    from app.models import CreditVoucher
    from app.services import (refresh_voucher_status, voucher_remaining,
                              compute_voucher_status)
    v = CreditVoucher.query.filter(
        db.func.upper(CreditVoucher.voucher_code) == code
    ).first()
    if v is None:
        return jsonify({'error': 'voucher not found'}), 404
    refresh_voucher_status(v)
    db.session.commit()
    return jsonify({
        'id':              v.id,
        'voucher_code':    v.voucher_code,
        'guest_id':        v.guest_id,
        'guest_name':      v.guest.name if v.guest else None,
        'issued_amount':   float(v.issued_amount or 0),
        'redeemed_amount': float(v.redeemed_amount or 0),
        'remaining':       voucher_remaining(v),
        'status':          v.status,
        'issued_date':     v.issued_date.isoformat() if v.issued_date else None,
        'expiry_date':     v.expiry_date.isoformat() if v.expiry_date else None,
    })


@bp.route('/api/voucher/<int:voucher_id>/redeem', methods=['POST'])
@login_required
def voucher_redeem(voucher_id):
    """Redeem ``amount`` from voucher against a reservation. Posts a
    Payment(purpose='settlement') and a CreditVoucherRedemption row.

    POST JSON: { reservation_id: int, amount: float, notes?: str }
    """
    denied = _deny_role('Admin', 'Manager', 'FrontDesk')
    if denied:
        return jsonify({'error': 'Permission denied'}), 403
    from app.models import CreditVoucher
    from app.services import redeem_credit_voucher
    v = CreditVoucher.query.get_or_404(voucher_id)

    data = request.get_json(silent=True) or {}
    try:
        res_id = int(data.get('reservation_id') or 0)
        amount = float(data.get('amount') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid reservation_id / amount'}), 400
    notes = (data.get('notes') or '').strip() or None

    if res_id <= 0:
        return jsonify({'error': 'reservation_id is required'}), 400
    reservation = Reservation.query.get(res_id)
    if reservation is None:
        return jsonify({'error': 'reservation not found'}), 404

    try:
        result = redeem_credit_voucher(
            v, reservation, amount,
            user_id      = current_user.id,
            notes        = notes,
            audit_writer = _write_audit,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception('voucher redeem failed: voucher=%d res=%d', voucher_id, res_id)
        return jsonify({'error': 'redemption failed; see server logs'}), 500

    return jsonify({
        'success':         True,
        'voucher_code':    v.voucher_code,
        'amount_applied':  float(result['redemption'].amount),
        'remaining':       result['remaining'],
        'status':          v.status,
        'payment_id':      (result['payment'].id if result['payment'] else None),
        'redemption_id':   result['redemption'].id,
    })


@bp.route('/admin/voucher/<int:voucher_id>/expire', methods=['POST'])
@login_required
def voucher_expire(voucher_id):
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied
    from app.models import CreditVoucher
    from app.services import expire_credit_voucher
    v = CreditVoucher.query.get_or_404(voucher_id)
    try:
        expire_credit_voucher(v, user_id=current_user.id, audit_writer=_write_audit)
        db.session.commit()
        flash(f'Voucher {v.voucher_code} marked expired.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to expire voucher: {exc}', 'danger')
    return redirect(request.referrer or url_for('reports.voucher_ledger'))


# ---------------------------------------------------------------------------
# Nightly Rate Inspector (Admin/Manager internal tool — Phase B)
# ---------------------------------------------------------------------------

@bp.route('/reservations/<int:reservation_id>/nightly-rates')
@login_required
def nightly_rate_inspector(reservation_id):
    """Internal inspection view for ReservationNightRate rows."""
    denied = _deny_role('Admin', 'Manager')
    if denied:
        return denied

    reservation = Reservation.query.get_or_404(reservation_id)

    from app.nightly_rate_service import validate_nightly_rows
    result = validate_nightly_rows(reservation)

    from flask import render_template_string
    return render_template_string(
        _NIGHTLY_INSPECTOR_TPL,
        reservation=reservation,
        rows=result['rows'],
        nights=result['nights'],
        warnings=result['warnings'],
        summary=result['summary'],
    )


_NIGHTLY_INSPECTOR_TPL = r'''
{% extends "base.html" %}
{% block title %}Nightly Rates — Res #{{ reservation.id }}{% endblock %}
{% block content %}
<div class="container py-3" style="max-width:1000px">
<div class="d-flex align-items-center gap-2 mb-3">
    <a href="{{ url_for('main.reservations') }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-arrow-left"></i></a>
    <h5 class="mb-0"><i class="bi bi-calendar3 me-2"></i>Nightly Rate Inspector</h5>
    <span class="badge bg-dark">Res #{{ reservation.id }}</span>
    {% if reservation.invoice_number %}<span class="badge bg-primary">{{ reservation.invoice_number }}</span>{% endif %}
</div>
<div class="card mb-3"><div class="card-body py-2" style="font-size:.85rem">
    <div class="d-flex flex-wrap gap-3">
        <span><strong>Guest:</strong> {{ reservation.guest.name if reservation.guest else '—' }}</span>
        <span><strong>Room:</strong> {{ reservation.room.room_number if reservation.room else '—' }}</span>
        <span><strong>Stay:</strong> {{ reservation.arrival_date.strftime('%d %b') }} → {{ reservation.departure_date.strftime('%d %b %Y') }} ({{ nights }}N)</span>
        <span><strong>Status:</strong> <span class="badge bg-secondary">{{ reservation.status }}</span></span>
        <span><strong>rate_per_night:</strong> ₹{{ '{:,.2f}'.format(reservation.rate_per_night|float) }}</span>
        <span><strong>pricing_mode:</strong> {{ reservation.pricing_mode or 'standard' }}</span>
    </div>
</div></div>

{% if warnings %}
<div class="alert alert-warning py-2 mb-3">
    <strong><i class="bi bi-exclamation-triangle me-1"></i>Warnings ({{ warnings|length }}):</strong>
    <ul class="mb-0 mt-1" style="font-size:.82rem">{% for w in warnings %}<li>{{ w }}</li>{% endfor %}</ul>
</div>
{% elif rows %}
<div class="alert alert-success py-2 mb-3" style="font-size:.85rem">
    <i class="bi bi-check-circle me-1"></i>All checks passed. {{ rows|length }} nightly rows, no gaps or mismatches.
</div>
{% endif %}

{% if rows %}
<div class="table-responsive">
<table class="table table-sm table-striped table-hover align-middle" style="font-size:.8rem">
    <thead class="table-light"><tr>
        <th>Date</th><th class="text-end">Standard</th><th class="text-end">Resolved</th>
        <th class="text-end">Final</th><th class="text-end">Discount</th>
        <th>Source</th><th>Plan</th><th>Mode</th>
        <th class="text-center">Posted</th><th class="text-center">Locked</th><th>Charge</th>
    </tr></thead>
    <tbody>{% for r in rows %}
    <tr>
        <td class="fw-semibold">{{ r.stay_date.strftime('%a %d %b') }}</td>
        <td class="text-end">{{ '{:,.2f}'.format(r.standard_rate|float) }}</td>
        <td class="text-end {% if r.resolved_rate|float != r.standard_rate|float %}text-info fw-semibold{% endif %}">{{ '{:,.2f}'.format(r.resolved_rate|float) }}</td>
        <td class="text-end fw-bold {% if r.final_rate|float < r.standard_rate|float %}text-danger{% elif r.final_rate|float > r.standard_rate|float %}text-success{% endif %}">{{ '{:,.2f}'.format(r.final_rate|float) }}</td>
        <td class="text-end {% if r.discount_amount|float > 0 %}text-danger{% endif %}">{{ '{:,.2f}'.format(r.discount_amount|float) if r.discount_amount|float > 0 else '—' }}</td>
        <td>{% set sc = {'base_rate':'bg-secondary','rate_plan':'bg-success','manual_override':'bg-warning text-dark','group_rate':'bg-info'} %}<span class="badge {{ sc.get(r.rate_source,'bg-secondary') }}" style="font-size:.65rem">{{ r.rate_source }}</span></td>
        <td><small>{{ r.rate_plan_name or '—' }}</small></td>
        <td><small>{{ r.pricing_mode or '—' }}</small></td>
        <td class="text-center">{% if r.is_posted %}<i class="bi bi-check-circle-fill text-success"></i>{% else %}<i class="bi bi-circle text-muted"></i>{% endif %}</td>
        <td class="text-center">{% if r.is_locked %}<i class="bi bi-lock-fill text-danger"></i>{% else %}<i class="bi bi-unlock text-muted"></i>{% endif %}</td>
        <td>{{ r.posted_charge_id or '—' }}</td>
    </tr>{% endfor %}</tbody>
    {% if summary %}
    <tfoot class="table-light fw-bold" style="font-size:.8rem">
        <tr><td>Totals ({{ summary.row_count }}/{{ summary.expected_nights }})</td>
            <td class="text-end">{{ '{:,.2f}'.format(summary.total_standard) }}</td><td>—</td>
            <td class="text-end">{{ '{:,.2f}'.format(summary.total_final) }}</td>
            <td class="text-end text-danger">{{ '{:,.2f}'.format(summary.total_discount) if summary.total_discount > 0 else '—' }}</td>
            <td colspan="6"></td></tr>
        <tr class="table-info"><td colspan="3">AVG(final_rate)</td>
            <td class="text-end">{{ '{:,.2f}'.format(summary.avg_final) }}</td>
            <td colspan="2">reservation.rate_per_night</td>
            <td>{{ '{:,.2f}'.format(summary.res_rate_per_night) }}</td>
            <td colspan="4">{% if (summary.avg_final - summary.res_rate_per_night)|abs < 0.02 %}<span class="badge bg-success"><i class="bi bi-check"></i> Match</span>{% else %}<span class="badge bg-danger"><i class="bi bi-x"></i> Mismatch</span>{% endif %}</td></tr>
    </tfoot>{% endif %}
</table>
</div>
{% else %}
<div class="text-center py-4 text-muted">
    <i class="bi bi-calendar-x fs-1 d-block mb-2"></i>
    <p>No nightly rate rows found for this reservation.</p>
    <small>Nightly rows are created for new reservations since Phase B. Older reservations use reservation.rate_per_night directly.</small>
</div>
{% endif %}
</div>
{% endblock %}
'''
