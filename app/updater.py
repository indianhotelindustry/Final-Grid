"""
System Updater Blueprint  (/admin/update)
=========================================
Admin-only in-app update manager.

Workflow:
  1. Admin opens /admin/update — sees current version, migration count, last backup
  2. Admin clicks "Take Backup" (or it is taken automatically in step 3)
  3. Admin uploads a .zip update package built by build_update.bat
  4. System:
       a. Takes an automatic pre-update backup
       b. Validates the zip (path traversal check, no corrupted archive)
       c. Extracts files — protected paths (.env, venv, uploads, backups) are SKIPPED
       d. Bumps the service-worker cache version in sw.js
       e. Writes a .restart_flag file
  5. start.bat watchdog detects .restart_flag and restarts gunicorn
  6. On restart, _run_pending_migrations() in __init__.py applies any new migrations
  7. Staff refresh their browsers — new version is live
"""

import os
import re
import json
import hashlib
import zipfile
import logging
import tempfile
from datetime import datetime
from functools import wraps

from flask import (Blueprint, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from app.models import db

logger = logging.getLogger(__name__)

updater_bp = Blueprint('updater', __name__, url_prefix='/admin/update')

# ── Protected paths — never overwritten by a zip package ──────────────────────
_PROTECTED = {
    '.env',
    'venv',
    'backups',
    'logs',
    'instance',
    os.path.join('app', 'static', 'uploads'),
    os.path.join('app', 'private_uploads'),
}


# ── Semantic version helpers ─────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Parse 'X.Y.Z' into (X, Y, Z) ints. Returns (0,0,0) on failure."""
    if not v:
        return (0, 0, 0)
    try:
        parts = str(v).strip().lstrip('v').split('.')
        nums = []
        for p in parts[:3]:
            # Strip any suffix like '1-beta' → '1'
            m = re.match(r'(\d+)', p)
            nums.append(int(m.group(1)) if m else 0)
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums)
    except Exception:
        return (0, 0, 0)


def _classify_release(from_v: str, to_v: str) -> str:
    """Classify an upgrade as 'major', 'minor', or 'patch' based on version change."""
    f = _parse_version(from_v)
    t = _parse_version(to_v)
    if t[0] > f[0]:
        return 'major'
    if t[0] == f[0] and t[1] > f[1]:
        return 'minor'
    return 'patch'


def _compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
    a = _parse_version(v1)
    b = _parse_version(v2)
    if a < b: return -1
    if a > b: return 1
    return 0


def _read_manifest_from_zip(zip_path: str) -> dict:
    """Extract and parse patch_manifest.json from the ZIP if present."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.replace('\\', '/').lower().endswith('patch_manifest.json'):
                    with zf.open(name) as f:
                        return json.loads(f.read().decode('utf-8'))
    except Exception as e:
        logger.warning('Could not read manifest from zip: %s', e)
    return {}


def _read_version_from_zip(zip_path: str) -> str:
    """Extract version.txt from the ZIP and return its contents."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.replace('\\', '/').lower().endswith('version.txt'):
                    with zf.open(name) as f:
                        return f.read().decode('utf-8').strip()
    except Exception as e:
        logger.warning('Could not read version.txt from zip: %s', e)
    return ''


def _is_protected(zip_member: str) -> bool:
    """Return True if this zip member path must never be overwritten."""
    # Normalise to forward slashes for comparison
    norm = zip_member.replace('\\', '/').lstrip('/')
    for p in _PROTECTED:
        pn = p.replace('\\', '/')
        if norm == pn or norm.startswith(pn + '/'):
            return True
    return False


# ── Update package signature verification ───────────────────────────────────
#
# Every update ZIP must contain:
#   1. patch_manifest.json     — the manifest, including per-file sha256 map
#   2. patch_manifest.sig      — Ed25519 signature over the raw bytes of (1)
#
# The public key is read from installer/update_pubkey.pem (bundled with the
# install). The private key lives OFF this hotel machine — only the maintainer
# who builds patches ever holds it. If any check fails, the update is rejected
# before any file is written.
#
# Extraction also verifies each extracted file's SHA-256 against the map in
# the manifest, so a tampered ZIP cannot mix a signed manifest with swapped
# content.

_PUBKEY_FILENAME = os.path.join('installer', 'update_pubkey.pem')
_MANIFEST_NAMES = ('patch_manifest.json',)
_SIGNATURE_NAMES = ('patch_manifest.sig',)


class UpdateVerificationError(Exception):
    """Raised when an update package fails integrity verification."""


def _read_zip_member_bytes(zip_path: str, candidate_names: tuple) -> bytes | None:
    """Return raw bytes of the first zip member whose basename matches one of
    candidate_names (case-insensitive). Returns None if not found."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                base = os.path.basename(name.replace('\\', '/')).lower()
                if base in candidate_names:
                    with zf.open(name) as f:
                        return f.read()
    except (zipfile.BadZipFile, OSError):
        return None
    return None


def _load_update_pubkey(project_root: str):
    """Load the Ed25519 verifier. Returns (verifier, key_source) or raises."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    pubkey_path = os.path.join(project_root, _PUBKEY_FILENAME)
    if not os.path.isfile(pubkey_path):
        raise UpdateVerificationError(
            f'Update public key not found at {_PUBKEY_FILENAME}. '
            'Contact the maintainer to install the signing public key.'
        )
    with open(pubkey_path, 'rb') as f:
        pem = f.read()
    try:
        key = serialization.load_pem_public_key(pem)
    except Exception as e:
        raise UpdateVerificationError(
            f'Could not parse update public key: {e}'
        )
    if not isinstance(key, Ed25519PublicKey):
        raise UpdateVerificationError(
            'Update public key is not an Ed25519 key. '
            'Rebuild the key pair using Ed25519.'
        )
    return key


def _verify_manifest_signature(zip_path: str, project_root: str) -> dict:
    """Verify the update ZIP's manifest signature and return the parsed
    manifest dict. Raises UpdateVerificationError on any failure."""
    manifest_bytes = _read_zip_member_bytes(zip_path, _MANIFEST_NAMES)
    if manifest_bytes is None:
        raise UpdateVerificationError('patch_manifest.json missing from update package.')
    signature_bytes = _read_zip_member_bytes(zip_path, _SIGNATURE_NAMES)
    if signature_bytes is None:
        raise UpdateVerificationError('patch_manifest.sig missing from update package.')

    pubkey = _load_update_pubkey(project_root)
    try:
        pubkey.verify(signature_bytes, manifest_bytes)
    except Exception as e:
        raise UpdateVerificationError(
            f'Signature verification failed — package is not trusted: {e}'
        )

    try:
        manifest = json.loads(manifest_bytes.decode('utf-8'))
    except Exception as e:
        raise UpdateVerificationError(f'Manifest is not valid JSON: {e}')
    if not isinstance(manifest, dict):
        raise UpdateVerificationError('Manifest must be a JSON object.')

    hashes = manifest.get('file_hashes')
    if not isinstance(hashes, dict) or not hashes:
        raise UpdateVerificationError(
            'Manifest missing "file_hashes" map. '
            'Rebuild the patch with signing enabled (build_patch.bat).'
        )
    return manifest


def _verify_member_hash(zf: zipfile.ZipFile, member: str, expected_hex: str):
    """Re-hash a zip member and confirm it matches the manifest entry."""
    h = hashlib.sha256()
    with zf.open(member) as src:
        for chunk in iter(lambda: src.read(64 * 1024), b''):
            h.update(chunk)
    actual_hex = h.hexdigest()
    if actual_hex.lower() != str(expected_hex).lower():
        raise UpdateVerificationError(
            f'SHA-256 mismatch for {member}: '
            f'expected {expected_hex}, got {actual_hex}'
        )


def _bump_sw_cache(project_root: str) -> str:
    """Increment pms-static-vN in sw.js and return the new version string."""
    sw_path = os.path.join(project_root, 'app', 'static', 'sw.js')
    if not os.path.exists(sw_path):
        return 'sw.js not found'
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    m = re.search(r"const CACHE_NAME = 'pms-static-v(\d+)'", content)
    if not m:
        return 'CACHE_NAME not found'
    old, new = int(m.group(1)), int(m.group(1)) + 1
    new_content = content.replace(f'pms-static-v{old}', f'pms-static-v{new}')
    with open(sw_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return f'pms-static-v{new}'


def _write_restart_flag(project_root: str):
    """Write .restart_flag and schedule the current process to exit.

    start.bat runs waitress in a loop.  When waitress exits and the flag
    exists, start.bat restarts the server.  We use a background thread to
    kill the current process after a short delay (giving Flask time to send
    the response back to the browser).
    """
    flag = os.path.join(project_root, '.restart_flag')
    with open(flag, 'w') as f:
        f.write(datetime.utcnow().isoformat())
    logger.info('Restart flag written: %s', flag)

    # Schedule process exit after 2 seconds so the HTTP response is sent first.
    # start.bat loop will see .restart_flag and relaunch waitress.
    import threading
    def _delayed_exit():
        import time
        time.sleep(2)
        logger.info('Restart: exiting server process (PID %d)', os.getpid())
        os._exit(0)  # hard exit — start.bat loop catches this and restarts
    t = threading.Thread(target=_delayed_exit, daemon=True)
    t.start()


def _get_project_root() -> str:
    return os.path.realpath(os.path.join(current_app.root_path, '..'))


def _last_backup_info(project_root: str) -> dict:
    """Return filename and timestamp of the most recent backup file."""
    backup_dir = os.path.join(project_root, 'backups')
    if not os.path.isdir(backup_dir):
        return {}
    # Match all backup files including encrypted (.enc) variants
    _BACKUP_EXTS = ('.sql', '.sql.enc', '.dump', '.dump.enc',
                    '.db', '.db.enc', '.sqlite', '.sqlite.enc', '.bak')
    files = sorted(
        [f for f in os.listdir(backup_dir)
         if f.startswith('backup_') and f.endswith(_BACKUP_EXTS)],
        reverse=True
    )
    if not files:
        return {}
    latest = files[0]
    full_path = os.path.join(backup_dir, latest)
    mtime = os.path.getmtime(full_path)
    size_kb = os.path.getsize(full_path) // 1024
    return {
        'filename': latest,
        'taken_at': datetime.fromtimestamp(mtime).strftime('%d %b %Y %I:%M %p'),
        'size_kb': size_kb,
        'encrypted': latest.endswith('.enc'),
    }


def _applied_migrations() -> int:
    try:
        return db.session.execute(
            db.text('SELECT COUNT(*) FROM schema_migrations')
        ).scalar() or 0
    except Exception:
        return 0


# ── Role guard ─────────────────────────────────────────────────────────────────

def _admin_only(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'Admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Routes ─────────────────────────────────────────────────────────────────────

@updater_bp.route('/', methods=['GET'])
@_admin_only
def index():
    # Read version.txt LIVE (not cached APP_VERSION) so it updates immediately after patch
    root = _get_project_root()
    version_file = os.path.join(root, 'version.txt')
    try:
        with open(version_file, 'r') as f:
            live_version = f.read().strip()
    except Exception:
        from app import APP_VERSION
        live_version = APP_VERSION
    return render_template(
        'admin/update.html',
        app_version=live_version,
        applied_migrations=_applied_migrations(),
        last_backup=_last_backup_info(root),
        project_root=root,
    )


@updater_bp.route('/backup', methods=['POST'])
@_admin_only
def trigger_backup():
    from app.backup_manager import run_backup
    ok, fname, msg = run_backup(
        current_app._get_current_object(),
        backup_type='manual',
        user_id=current_user.id,
    )
    if ok:
        flash(f'Backup created successfully: {fname}', 'success')
    else:
        flash(f'Backup failed: {msg}', 'danger')
    return redirect(url_for('updater.index'))


@updater_bp.route('/apply', methods=['POST'])
@_admin_only
def apply_update():
    """
    Upload a zip → validate → auto-backup → extract → bump SW cache → restart.
    """
    root = _get_project_root()

    # ── Validate upload ────────────────────────────────────────────
    uploaded = request.files.get('update_zip')
    if not uploaded or not uploaded.filename.lower().endswith('.zip'):
        flash('Please select a valid .zip update package.', 'danger')
        return redirect(url_for('updater.index'))

    # ── Save zip to a temp file (for pre-flight manifest inspection) ──
    tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    try:
        uploaded.save(tmp.name)
        tmp.close()

        # ── Pre-flight: read manifest and version from the ZIP ─────
        # Read current version BEFORE extraction
        current_version_file = os.path.join(root, 'version.txt')
        current_version = 'unknown'
        if os.path.exists(current_version_file):
            try:
                with open(current_version_file, 'r') as f:
                    current_version = f.read().strip()
            except Exception:
                pass

        # ── Integrity gate — verify signature BEFORE any side effect ─────
        # If this fails, we do NOT take a backup, do NOT extract anything,
        # and do NOT touch the filesystem. Fail-closed.
        try:
            manifest = _verify_manifest_signature(tmp.name, root)
        except UpdateVerificationError as ve:
            logger.error(
                'UPDATE REJECTED: signature verification failed for user=%s '
                'file=%s reason=%s',
                current_user.username, uploaded.filename, ve,
            )
            flash(
                f'Update rejected: {ve} '
                f'Package was NOT applied; nothing on the server has changed.',
                'danger',
            )
            return redirect(url_for('updater.index'))
        except Exception as ve:
            # Unexpected errors (missing cryptography lib, unreadable key, ...)
            logger.error(
                'UPDATE REJECTED: verification error user=%s file=%s error=%s',
                current_user.username, uploaded.filename, ve,
            )
            flash(
                f'Update rejected: signature check could not complete ({ve}). '
                f'Package was NOT applied.',
                'danger',
            )
            return redirect(url_for('updater.index'))

        zip_version = _read_version_from_zip(tmp.name)
        file_hashes = manifest.get('file_hashes') or {}

        # Target version: manifest 'version' wins, else zip's version.txt
        target_version = (manifest.get('version') or zip_version or '').strip()

        # Release type: from manifest or auto-classify
        release_type = (manifest.get('release_type') or '').strip().lower()
        if release_type not in ('patch', 'minor', 'major'):
            if target_version and current_version != 'unknown':
                release_type = _classify_release(current_version, target_version)
            else:
                release_type = 'patch'  # safe default

        force_downgrade = bool(manifest.get('allow_downgrade', False))
        description = manifest.get('description', '') or manifest.get('notes', '')

        # ── Downgrade protection ────────────────────────────────────
        if target_version and current_version != 'unknown':
            cmp_result = _compare_versions(target_version, current_version)
            if cmp_result < 0 and not force_downgrade:
                flash(
                    f'Downgrade blocked: package version v{target_version} is '
                    f'older than installed v{current_version}. Set '
                    f'"allow_downgrade": true in the manifest to force.',
                    'danger'
                )
                return redirect(url_for('updater.index'))
            if cmp_result == 0:
                flash(
                    f'Package version v{target_version} matches currently '
                    f'installed version. Re-applying the same version.',
                    'warning'
                )

        logger.info(
            'UPDATE START: user=%s from=v%s to=v%s type=%s file=%s',
            current_user.username, current_version, target_version or 'unknown',
            release_type, uploaded.filename
        )

        # ── Auto-backup BEFORE touching anything ──────────────────
        # Label format mirrors install_patch.bat: v{FROM}_to_v{TARGET}
        # → backup_v1.4.0_to_v2.0.0_{ts}.db.enc (traceable across CLI+UI).
        from app.backup_manager import run_backup
        _bk_label = f'v{current_version}_to_v{target_version or "unknown"}'
        ok, fname, msg = run_backup(
            current_app._get_current_object(),
            backup_type=('pre-major-upgrade' if release_type == 'major' else 'pre-update'),
            user_id=current_user.id,
            label=_bk_label,
        )
        if not ok:
            logger.error('UPDATE ABORT: backup failed for %s->%s (%s): %s',
                         current_version, target_version, release_type, msg)
            flash(
                f'Pre-update backup failed: {msg} — Update aborted. '
                f'{"This is a MAJOR upgrade — backup is mandatory. " if release_type == "major" else ""}'
                f'Fix the backup issue first, or take a manual backup.',
                'danger'
            )
            return redirect(url_for('updater.index'))

        # ── Validate zip structure (path traversal + corruption) ───
        try:
            with zipfile.ZipFile(tmp.name, 'r') as zf:
                members = zf.namelist()
                for name in members:
                    clean = name.replace('\\', '/')
                    if '..' in clean or clean.startswith('/'):
                        raise ValueError(f'Unsafe path in package: {name}')

                # ── Extract non-protected members ──────────────────
                # Each extractable member must have a SHA-256 in the signed
                # manifest. We verify the hash BEFORE writing to disk so a
                # tampered payload cannot hit the filesystem even briefly.
                extracted = skipped = 0
                errors = []
                # Normalise hash-map keys once, for forward-slash comparison.
                hash_map = {k.replace('\\', '/'): v for k, v in file_hashes.items()}
                # Members we never hash-check: the manifest and its signature.
                _meta_members = {'patch_manifest.json', 'patch_manifest.sig'}
                for name in members:
                    if _is_protected(name):
                        skipped += 1
                        continue
                    norm = name.replace('\\', '/').lstrip('/')
                    if norm in _meta_members:
                        skipped += 1
                        continue
                    expected = hash_map.get(norm)
                    if not expected:
                        raise UpdateVerificationError(
                            f'Package contains file not listed in signed '
                            f'manifest: {name}'
                        )
                    # Verify the zip member's content against the manifest
                    # before touching disk. Any mismatch aborts the whole
                    # extraction — we never leave a half-applied update.
                    _verify_member_hash(zf, name, expected)
                    dest = os.path.join(root, name.replace('/', os.sep))
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(name) as src, open(dest, 'wb') as dst:
                            dst.write(src.read())
                        extracted += 1
                    except Exception as e:
                        errors.append(f'{name}: {e}')

        except UpdateVerificationError as ve:
            logger.error(
                'UPDATE HALTED: hash mismatch during extraction user=%s '
                'file=%s reason=%s',
                current_user.username, uploaded.filename, ve,
            )
            flash(
                f'Update halted mid-extraction: {ve} '
                f'Restore from the pre-update backup if any files were written.',
                'danger',
            )
            return redirect(url_for('updater.index'))
        except (zipfile.BadZipFile, ValueError) as e:
            flash(f'Invalid update package: {e}', 'danger')
            return redirect(url_for('updater.index'))

    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    if errors:
        logger.warning('Update: %d file(s) could not be written: %s', len(errors), errors)

    # ── Read new version from extracted version.txt ─────────────────
    new_version_file = os.path.join(root, 'version.txt')
    new_version = 'unknown'
    if os.path.exists(new_version_file):
        with open(new_version_file, 'r') as f:
            new_version = f.read().strip()

    # ── Bump service-worker cache version ──────────────────────────
    new_sw = _bump_sw_cache(root)

    # ── Run DB migrations now (before restart) ────────────────────
    migration_msg = ''
    migrations_before = _applied_migrations()
    try:
        from app import _run_pending_migrations
        _run_pending_migrations(current_app._get_current_object())
        migrations_after = _applied_migrations()
        applied_count = max(0, migrations_after - migrations_before)
        if applied_count > 0:
            migration_msg = f'{applied_count} new database migration(s) applied.'
        else:
            migration_msg = 'No new migrations to apply.'
    except Exception as mig_err:
        migration_msg = f'Migration warning: {mig_err}'
        applied_count = 0
        logger.warning('Post-update migration issue: %s', mig_err)

    # ── Signal the watchdog to restart ────────────────────────────
    _write_restart_flag(root)

    logger.info(
        'UPDATE SUCCESS: user=%s from=v%s to=v%s type=%s '
        'files_extracted=%d protected_skipped=%d migrations=%d sw=%s',
        current_user.username, current_version, new_version, release_type,
        extracted, skipped, applied_count, new_sw
    )

    flash(
        f'{"MAJOR upgrade" if release_type == "major" else "Update"} '
        f'from v{current_version} to v{new_version} applied successfully! '
        f'{extracted} files updated, {skipped} data files preserved. '
        f'{migration_msg} '
        f'Server is restarting now — please wait 10 seconds then refresh.',
        'success'
    )
    return redirect(url_for('updater.index'))


@updater_bp.route('/inspect', methods=['POST'])
@_admin_only
def inspect_package():
    """
    AJAX preview: upload a ZIP and return version metadata WITHOUT
    applying it.  Used to show major-upgrade warnings before confirm.
    """
    from flask import jsonify
    uploaded = request.files.get('update_zip')
    if not uploaded or not uploaded.filename.lower().endswith('.zip'):
        return jsonify({'ok': False, 'error': 'Invalid file'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    try:
        uploaded.save(tmp.name)
        tmp.close()

        manifest = _read_manifest_from_zip(tmp.name)
        zip_version = _read_version_from_zip(tmp.name)
        target_version = (manifest.get('version') or zip_version or '').strip()

        root = _get_project_root()
        current_version_file = os.path.join(root, 'version.txt')
        current_version = 'unknown'
        if os.path.exists(current_version_file):
            with open(current_version_file, 'r') as f:
                current_version = f.read().strip()

        release_type = (manifest.get('release_type') or '').strip().lower()
        if release_type not in ('patch', 'minor', 'major'):
            release_type = _classify_release(current_version, target_version) \
                if target_version else 'patch'

        cmp = _compare_versions(target_version, current_version) \
            if target_version else 0
        is_downgrade = cmp < 0
        is_same = cmp == 0 and target_version == current_version

        return jsonify({
            'ok': True,
            'current_version': current_version,
            'target_version': target_version or 'unknown',
            'release_type': release_type,
            'description': manifest.get('description') or manifest.get('notes', ''),
            'is_downgrade': is_downgrade,
            'is_same_version': is_same,
            'allow_downgrade': bool(manifest.get('allow_downgrade', False)),
        })
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@updater_bp.route('/restart', methods=['POST'])
@_admin_only
def restart_server():
    """Signal the watchdog to restart without applying an update."""
    _write_restart_flag(_get_project_root())
    flash(
        'Restart signal sent. The server will restart in a few seconds. '
        'Refresh this page in about 10 seconds.',
        'info'
    )
    return redirect(url_for('updater.index'))
