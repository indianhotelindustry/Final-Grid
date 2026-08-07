from flask import Blueprint, render_template, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from app.auth import admin_required
from app.models import db, BackupLog
import os

backup_bp = Blueprint('backup', __name__, url_prefix='/backup')


@backup_bp.before_request
@login_required
def require_login():
    pass


@backup_bp.route('/')
@admin_required
def index():
    from flask import current_app
    from app.backup_manager import list_backups
    files = list_backups(current_app._get_current_object())
    logs = BackupLog.query.order_by(BackupLog.created_at.desc()).limit(20).all()
    return render_template('backup/index.html', files=files, logs=logs)


@backup_bp.route('/run', methods=['POST'])
@admin_required
def run_now():
    from flask import current_app
    from app.backup_manager import run_backup
    success, filename, message = run_backup(
        current_app._get_current_object(),
        backup_type='manual',
        user_id=current_user.id
    )
    flash(message, 'success' if success else 'danger')
    return redirect(url_for('backup.index'))


@backup_bp.route('/download/<filename>')
@admin_required
def download(filename):
    # Prevent path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        abort(400)
    from flask import current_app
    from app.backup_manager import _backup_dir
    backup_dir = _backup_dir(current_app._get_current_object())
    filepath = os.path.join(backup_dir, filename)
    if not os.path.isfile(filepath):
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=filename)


@backup_bp.route('/delete/<filename>', methods=['POST'])
@admin_required
def delete(filename):
    if '..' in filename or '/' in filename or '\\' in filename:
        abort(400)
    from flask import current_app
    from app.backup_manager import _backup_dir
    backup_dir = _backup_dir(current_app._get_current_object())
    filepath = os.path.join(backup_dir, filename)
    if os.path.isfile(filepath):
        os.remove(filepath)
        flash(f'Backup {filename} deleted.', 'success')
    else:
        flash('File not found.', 'warning')
    return redirect(url_for('backup.index'))
