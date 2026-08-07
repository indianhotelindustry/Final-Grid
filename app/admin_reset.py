"""
Admin UI wrapper for Reset Transactional Data.

This blueprint is a THIN wrapper around `reset_transactional_data.py` — it
does NOT duplicate any classification, delete-order, backup, or reset logic.
The CLI script remains the source of truth; this module just exposes the
same workflow through a protected admin page.

Route:    /admin/reset-transactional-data
Access:   Admin role only (mirrors the /admin/update pattern)
Safety:   GET  → render dry-run report
          POST → validate phrase → run backup → run delete (all reused from CLI)
"""
import logging
from functools import wraps

from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

from app.models import db

# Import the existing CLI helpers — single source of truth.
# NB: reset_transactional_data.py lives at the project root, not in app/.
# The PMS is always launched with that root on sys.path (wsgi.py / run.py),
# so the bare import works.
import reset_transactional_data as _reset

logger = logging.getLogger(__name__)

admin_reset_bp = Blueprint(
    'admin_reset', __name__, url_prefix='/admin/reset-transactional-data')


# ─── Role guard (mirrors app/updater.py:_admin_only) ──────────────────────
def _admin_only(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'Admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── Routes ────────────────────────────────────────────────────────────────
@admin_reset_bp.route('/', methods=['GET'])
@_admin_only
def index():
    """Render the dry-run preview page. No data is modified."""
    # Reuse the CLI's classification + row-count logic verbatim.
    report = _reset._collect_report(db, include_guests=False)

    preserved = [r for r in report if r[1].startswith('PRESERVED')]
    clear = [r for r in report if r[1] == 'CLEAR']

    return render_template(
        'admin/reset_transactional_data.html',
        preserved=preserved,
        clear=clear,
        preserved_total=sum(r[2] for r in preserved),
        clear_total=sum(r[2] for r in clear),
        tables_to_clear=len(clear),
        confirmation_phrase=_reset.CONFIRMATION_PHRASE,
        result=None,
    )


@admin_reset_bp.route('/execute', methods=['POST'])
@_admin_only
def execute():
    """Validate phrase → take backup → run FK-safe deletes. Reuses CLI
    helpers verbatim; no delete-order or backup logic is duplicated here."""
    entered = (request.form.get('confirmation_phrase') or '').strip()

    # Gate 1: exact phrase match
    if entered != _reset.CONFIRMATION_PHRASE:
        flash(
            f'Confirmation phrase did not match. Type exactly: '
            f'{_reset.CONFIRMATION_PHRASE}',
            'danger')
        return redirect(url_for('admin_reset.index'))

    logger.warning(
        'RESET_TRANSACTIONAL_DATA start: user=%s role=%s',
        getattr(current_user, 'username', '?'),
        getattr(current_user, 'role', '?'))

    # Gate 2: mandatory backup (reuses CLI helper — same signature-aware path)
    from flask import current_app
    ok, fname, msg = _reset._run_backup(current_app._get_current_object())
    if not ok:
        logger.error('RESET_TRANSACTIONAL_DATA abort: backup failed: %s', msg)
        flash(
            f'Backup failed — reset aborted. No data was deleted. Error: {msg}',
            'danger')
        return redirect(url_for('admin_reset.index'))

    # Gate 3: execute delete (reuses CLI helper — FK-safe order + identity
    # reset + SQLite/PostgreSQL handling all inside _execute_delete)
    try:
        deleted = _reset._execute_delete(db, include_guests=False)
    except Exception as exc:
        db.session.rollback()
        logger.error('RESET_TRANSACTIONAL_DATA failed: %s', exc, exc_info=True)
        flash(
            f'Delete failed — transaction rolled back, no data lost. '
            f'Backup file {fname} is safe. Error: {exc}',
            'danger')
        return redirect(url_for('admin_reset.index'))

    total_rows = sum(deleted.values())
    logger.warning(
        'RESET_TRANSACTIONAL_DATA success: user=%s tables_cleared=%d '
        'rows_deleted=%d backup=%s',
        getattr(current_user, 'username', '?'),
        len(deleted), total_rows, fname)

    # Re-render with result block so the admin sees what happened
    report = _reset._collect_report(db, include_guests=False)
    preserved = [r for r in report if r[1].startswith('PRESERVED')]
    clear = [r for r in report if r[1] == 'CLEAR']
    return render_template(
        'admin/reset_transactional_data.html',
        preserved=preserved,
        clear=clear,
        preserved_total=sum(r[2] for r in preserved),
        clear_total=sum(r[2] for r in clear),
        tables_to_clear=len(clear),
        confirmation_phrase=_reset.CONFIRMATION_PHRASE,
        result={
            'ok': True,
            'backup_filename': fname,
            'tables_cleared': len(deleted),
            'rows_deleted': total_rows,
            'deleted_per_table': deleted,
            'guests_preserved_count': _reset._row_count(db, 'guests'),
        },
    )
