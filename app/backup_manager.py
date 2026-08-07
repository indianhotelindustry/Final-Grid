"""
Automated database backup service.
- PostgreSQL: pg_dump to local backups/ folder
- SQLite: file copy to local backups/ folder
- 30-day retention (auto-delete old files)
- Scheduled via APScheduler (daily at configurable time)
- BackupLog records every attempt
- Backups are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256)
"""
import os
import shutil
import subprocess
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = 'backups'


class BackupEncryptionUnavailable(Exception):
    """Raised when encryption is required but cannot be performed."""


def _allow_unencrypted() -> bool:
    """Opt-in escape hatch for disaster-recovery rigs that deliberately keep
    plaintext backups. Accepts '1', 'true', 'yes' (case-insensitive). Absent
    or anything else means 'no' — default is fail-closed, encryption only."""
    v = (os.getenv('ALLOW_UNENCRYPTED_BACKUPS') or '').strip().lower()
    return v in ('1', 'true', 'yes')


def _get_backup_key():
    """Derive a Fernet key for backup encryption from PII_ENCRYPTION_KEY or
    SECRET_KEY. Raises BackupEncryptionUnavailable if encryption cannot be
    performed — callers MUST either encrypt or refuse to write the backup.
    Never returns None for a silent-plaintext fallback."""
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        import base64
    except ImportError as e:
        raise BackupEncryptionUnavailable(
            "The 'cryptography' package is not installed. "
            "Install it with 'pip install cryptography' or re-run setup.bat."
        ) from e

    key_material = os.getenv('PII_ENCRYPTION_KEY') or os.getenv('SECRET_KEY', '')
    if not key_material:
        raise BackupEncryptionUnavailable(
            'No encryption key available. Set PII_ENCRYPTION_KEY (or '
            'SECRET_KEY) in .env before running backups.'
        )
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'pms-backup-encryption-salt',
        info=b'backup-key',
    )
    derived = kdf.derive(key_material.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def _encrypt_file(filepath):
    """Encrypt a backup file in-place. Adds .enc extension.

    Fail-closed: if encryption is unavailable, the plaintext file is REMOVED
    and BackupEncryptionUnavailable is raised — we never leave an
    unencrypted backup sitting on disk. To allow plaintext deliberately,
    set ALLOW_UNENCRYPTED_BACKUPS=1 in the environment (opt-in only).
    """
    try:
        fernet = _get_backup_key()
    except BackupEncryptionUnavailable as e:
        if _allow_unencrypted():
            logger.error(
                'Backup stored UNENCRYPTED because ALLOW_UNENCRYPTED_BACKUPS '
                'is set: %s — file=%s', e, os.path.basename(filepath),
            )
            return filepath
        # Remove the plaintext file so we do not leak on disk, then bubble up.
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            logger.warning(
                'Could not remove plaintext backup after encryption failure: %s',
                filepath,
            )
        logger.error('Backup encryption unavailable — aborting backup: %s', e)
        raise

    with open(filepath, 'rb') as f:
        data = f.read()
    encrypted = fernet.encrypt(data)
    enc_path = filepath + '.enc'
    with open(enc_path, 'wb') as f:
        f.write(encrypted)
    os.remove(filepath)  # remove unencrypted version
    logger.info('Backup encrypted: %s', os.path.basename(enc_path))
    return enc_path


def decrypt_backup_file(filepath):
    """Decrypt an encrypted backup file. Returns decrypted bytes or None."""
    try:
        fernet = _get_backup_key()
    except BackupEncryptionUnavailable as e:
        logger.error('No encryption key available to decrypt backup: %s', e)
        return None
    with open(filepath, 'rb') as f:
        data = f.read()
    try:
        return fernet.decrypt(data)
    except Exception as e:
        logger.error('Failed to decrypt backup: %s', e)
        return None


def _backup_dir(app):
    path = os.path.join(app.root_path, '..', BACKUP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return os.path.realpath(path)


def _parse_db_url(db_url):
    """Return dict with host, port, dbname, user, password from DATABASE_URL."""
    p = urlparse(db_url)
    return {
        'host': p.hostname or 'localhost',
        'port': str(p.port or 5432),
        'dbname': p.path.lstrip('/'),
        'user': p.username or '',
        'password': p.password or '',
    }


def _sqlite_path(db_url):
    """Extract the filesystem path from a sqlite:/// URL."""
    # sqlite:////absolute/path  or  sqlite:///relative/path
    if db_url.startswith('sqlite:////'):
        return db_url[len('sqlite:///'):]
    if db_url.startswith('sqlite:///'):
        return db_url[len('sqlite:///'):]
    return None


def _sanitize_label(label):
    """Keep only [A-Za-z0-9._-] so the label is safe as part of a filename."""
    import re as _re
    if not label:
        return None
    s = _re.sub(r'[^A-Za-z0-9._-]', '_', str(label)).strip('_')
    return s or None


def run_backup(app, backup_type='manual', user_id=None, label=None):
    """
    Execute a database backup and record result in BackupLog.

    Args:
        label: Optional filename marker. When provided, the backup filename
               becomes "backup_{label}_{timestamp}.db" instead of the generic
               "backup_pms_{timestamp}.db". Used by the patch installer to
               include from/to versions and install_id in the filename.

    Returns (success: bool, filename: str, message: str).
    """
    from app.models import db, BackupLog

    db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    is_sqlite = db_url.startswith('sqlite')
    label = _sanitize_label(label)

    if is_sqlite:
        return _run_sqlite_backup(app, db, BackupLog, db_url, backup_type, user_id, label)
    elif db_url.startswith('postgresql'):
        return _run_pg_backup(app, db, BackupLog, db_url, backup_type, user_id, label)
    else:
        msg = 'Backup not supported for this database engine.'
        logger.warning(msg)
        return False, '', msg


def _run_sqlite_backup(app, db, BackupLog, db_url, backup_type, user_id, label=None):
    """Backup SQLite by copying the database file."""
    src = _sqlite_path(db_url)
    if not src or not os.path.exists(src):
        return False, '', f'SQLite database file not found: {src}'

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    tag = label or 'pms'
    filename = f"backup_{tag}_{timestamp}.db"
    backup_path = os.path.join(_backup_dir(app), filename)

    log_entry = BackupLog(
        filename=filename,
        backup_type=backup_type,
        status='success',
        created_by_user_id=user_id,
    )

    try:
        # Use shutil.copy2 to preserve metadata; safe for SQLite in WAL mode
        # when done outside of active writes (scheduled at 3am)
        shutil.copy2(src, backup_path)

        # Encrypt the backup at rest. Raises BackupEncryptionUnavailable if
        # encryption is not possible — we treat this as a backup FAILURE
        # instead of silently writing plaintext.
        try:
            backup_path = _encrypt_file(backup_path)
        except BackupEncryptionUnavailable as enc_err:
            raise RuntimeError(
                f'Backup aborted: encryption unavailable ({enc_err}). '
                f'Set ALLOW_UNENCRYPTED_BACKUPS=1 only if you explicitly '
                f'require plaintext backups.'
            )
        filename = os.path.basename(backup_path)
        log_entry.filename = filename

        size = os.path.getsize(backup_path)
        log_entry.size_bytes = size
        logger.info('SQLite backup created: %s (%d bytes)', filename, size)

        _purge_old_backups(app, days=30)

        with app.app_context():
            db.session.add(log_entry)
            db.session.commit()

        return True, filename, f'Backup created: {filename} ({size // 1024} KB)'

    except Exception as e:
        err = str(e)
        log_entry.status = 'failed'
        log_entry.error_message = err
        logger.error('SQLite backup failed: %s', err)
        try:
            with app.app_context():
                db.session.add(log_entry)
                db.session.commit()
        except Exception:
            pass
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False, '', f'Backup failed: {err}'


def _run_pg_backup(app, db, BackupLog, db_url, backup_type, user_id, label=None):
    """Backup PostgreSQL using pg_dump."""
    params = _parse_db_url(db_url)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    tag = label or params['dbname']
    filename = f"backup_{tag}_{timestamp}.sql"
    backup_path = os.path.join(_backup_dir(app), filename)

    env = os.environ.copy()
    if params['password']:
        env['PGPASSWORD'] = params['password']

    cmd = [
        'pg_dump',
        '-h', params['host'],
        '-p', params['port'],
        '-U', params['user'],
        '-F', 'p',          # plain SQL format
        '-f', backup_path,
        params['dbname'],
    ]

    log_entry = BackupLog(
        filename=filename,
        backup_type=backup_type,
        status='success',
        created_by_user_id=user_id,
    )

    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or 'pg_dump failed')

        # Encrypt the backup at rest. Fail-closed — see _encrypt_file.
        try:
            backup_path = _encrypt_file(backup_path)
        except BackupEncryptionUnavailable as enc_err:
            raise RuntimeError(
                f'Backup aborted: encryption unavailable ({enc_err}). '
                f'Set ALLOW_UNENCRYPTED_BACKUPS=1 only if you explicitly '
                f'require plaintext backups.'
            )
        filename = os.path.basename(backup_path)
        log_entry.filename = filename

        size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
        log_entry.size_bytes = size
        logger.info('Backup created: %s (%d bytes)', filename, size)

        # Purge backups older than 30 days
        _purge_old_backups(app, days=30)

        with app.app_context():
            db.session.add(log_entry)
            db.session.commit()

        return True, filename, f'Backup created: {filename} ({size // 1024} KB)'

    except Exception as e:
        err = str(e)
        log_entry.status = 'failed'
        log_entry.error_message = err
        logger.error('Backup failed: %s', err)
        try:
            with app.app_context():
                db.session.add(log_entry)
                db.session.commit()
        except Exception:
            pass
        # Remove partial file if it exists
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False, '', f'Backup failed: {err}'


def _purge_old_backups(app, days=30):
    """Delete backup files older than `days` days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    backup_dir = _backup_dir(app)
    for fname in os.listdir(backup_dir):
        if not fname.startswith('backup_'):
            continue
        fpath = os.path.join(backup_dir, fname)
        mtime = datetime.utcfromtimestamp(os.path.getmtime(fpath))
        if mtime < cutoff:
            try:
                os.remove(fpath)
                logger.info('Purged old backup: %s', fname)
            except OSError:
                pass


def list_backups(app):
    """Return list of backup files sorted newest-first."""
    backup_dir = _backup_dir(app)
    files = []
    for fname in os.listdir(backup_dir):
        if not fname.startswith('backup_'):
            continue
        fpath = os.path.join(backup_dir, fname)
        stat = os.stat(fpath)
        files.append({
            'filename': fname,
            'size_kb': stat.st_size // 1024,
            'created_at': datetime.utcfromtimestamp(stat.st_mtime),
        })
    return sorted(files, key=lambda x: x['created_at'], reverse=True)


def setup_backup_scheduler(app, scheduler):
    """Register daily backup job on the existing APScheduler instance."""
    from app.models import Settings

    with app.app_context():
        setting = Settings.query.filter_by(key='backup_time').first()
        backup_time = setting.value if setting else '03:00'

    try:
        hour, minute = map(int, backup_time.split(':'))
    except (ValueError, AttributeError):
        hour, minute = 3, 0

    def _scheduled_backup():
        run_backup(app, backup_type='scheduled', user_id=None)

    scheduler.add_job(
        func=_scheduled_backup,
        trigger='cron',
        hour=hour,
        minute=minute,
        id='daily_backup_job',
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info('Daily backup scheduled at %02d:%02d', hour, minute)
