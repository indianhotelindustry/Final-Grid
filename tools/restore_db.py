"""Isolated, verified restore of a FinalGrid SQLite backup.

Operational tooling, deliberately NOT part of ``verification/`` and NOT part
of ``app/``. It is the restore half of the recovery architecture adopted as
ADR-007 (target components: transactionally safe copy, integrity check,
cryptographic hash, machine-readable manifest, retained artifact, rehearsed
restore, documented verification). ``tools/backup_db.py`` is the backup half
and is unchanged.

What this tool proves, when it exits 0:

    A named backup artifact restores into an explicitly supplied, isolated
    destination and the restored file is an openable, internally consistent
    SQLite database whose contents match the backup.

What it deliberately does NOT do:

* It never writes to ``instance/pms.db``. A destination that resolves to the
  production database, or to anything inside the repository's ``instance``
  directory, is refused before any file is touched. There is no flag to
  override this. In-place production restore is a separately authorized
  PD-004 act and is not built here.
* It never opens the backup writably. The source is opened ``mode=ro`` and
  copied through SQLite's backup API, so a damaged or half-written source is
  detected rather than propagated.
* It never boots the application against the restored file. ``create_app()``
  runs migrations, ``init_data()`` and starts the scheduler, which would
  mutate the very file being verified. Verification here is database-level
  only, and the manifest says so.
* It never records secrets. Encrypted application backups (``*.enc``) are
  decrypted in memory with key material taken from the environment; the key
  is not logged and does not appear in the manifest.

Verification performed on every run, in order:

1. Source exists, is non-empty, and carries the SQLite header (or, for
   ``*.enc``, decrypts to one).
2. Source SHA-256 is computed. If a ``<source>.manifest.json`` written by
   ``backup_db.py`` exists (or ``--manifest`` is given), the recorded
   ``snapshot_sha256`` must match, otherwise the run FAILS before restoring.
3. ``PRAGMA integrity_check`` on the source, read-only.
4. Restore: backup API from the read-only source into a temporary file next
   to the destination, then an atomic rename. The destination must not
   already exist unless ``--overwrite-dest`` is given (and even then it can
   never be the production path).
5. Restored file: SHA-256, ``PRAGMA integrity_check``, ``PRAGMA
   foreign_key_check`` (run with ``foreign_keys=ON``), required tables
   present, ``sqlite_master`` readable, per-table row counts.
6. Logical equivalence: schema SQL (``sqlite_master``) restored == source;
   row counts restored == source for every table; content digests (SHA-256
   over the ordered rows of every table) restored == source.
7. Physical equivalence: every byte beyond the 100-byte SQLite file header
   restored == source, and the sizes are equal. The backup API rewrites
   header fields (file change counter, version-valid-for number) on the
   destination, so whole-file SHA-256 equality is recorded but is NOT a
   pass/fail criterion; any difference outside the header is a failure.
8. A machine-readable restore manifest is written. Exit 0 only if every
   check passed; 1 on verification failure; 2 on refusal or usage error.

Usage::

    python tools/restore_db.py --source ../db-backups/pms_X.db --dest /isolated/path/restored.db
    python tools/restore_db.py --source backups/backup_pms_X.db.enc --dest ... --run-id rehearsal-01
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INSTANCE_DIR = os.path.join(REPO, 'instance')
PRODUCTION_DB = os.path.join(INSTANCE_DIR, 'pms.db')

SQLITE_HEADER = b'SQLite format 3\x00'

#: Tables a FinalGrid database must contain to be considered structurally
#: usable. Financial tables carry a content digest as well as a row count.
REQUIRED_TABLES = (
    'users', 'settings', 'business_date', 'schema_migrations',
    'reservations', 'folios', 'payments', 'extra_charges', 'tax_lines',
    'night_audit_logs', 'audit_logs',
)
DIGEST_TABLES = ('reservations', 'folios', 'payments', 'extra_charges',
                 'tax_lines', 'audit_logs', 'night_audit_logs')

#: There is no ``invoices`` table in FinalGrid; invoice identity lives on
#: ``reservations.invoice_number`` and invoice tax lines in ``tax_lines``.
#: The manifest reports both so "invoices" is evaluated without pretending a
#: table exists.
INVOICE_QUERY = 'SELECT COUNT(*) FROM reservations WHERE invoice_number IS NOT NULL'


class RestoreRefused(RuntimeError):
    """The request was unsafe or malformed. Nothing was written."""


class RestoreFailed(RuntimeError):
    """The restore ran but verification did not pass."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _ro_connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect('file:' + path.replace('\\', '/') + '?mode=ro',
                           uri=True)


def is_production_path(path: str) -> bool:
    """True if *path* is the production database or lives under instance/."""
    p = _norm(path)
    if p == _norm(PRODUCTION_DB):
        return True
    inst = _norm(INSTANCE_DIR)
    return p == inst or p.startswith(inst + os.sep)


def has_sqlite_header(path: str) -> bool:
    try:
        with open(path, 'rb') as fh:
            return fh.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def table_names(conn: sqlite3.Connection) -> list:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def row_counts(conn: sqlite3.Connection) -> dict:
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in table_names(conn)}


def content_digest(conn: sqlite3.Connection, table: str) -> str:
    """SHA-256 over every row of *table*, ordered by rowid, all columns."""
    h = hashlib.sha256()
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    h.update(('|'.join(cols) + '\n').encode('utf-8'))
    for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
        h.update(repr(tuple(row)).encode('utf-8'))
        h.update(b'\n')
    return h.hexdigest()


def schema_sql(conn: sqlite3.Connection) -> list:
    return [r[0] for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
        "ORDER BY type, name")]


SQLITE_HEADER_SIZE = 100


def byte_diff(a: str, b: str) -> dict:
    """Compare two files byte-for-byte, separating the 100-byte header.

    Returns sizes, whole-file identity, the header offsets that differ, and
    the number of differing bytes beyond the header (which must be 0 for a
    faithful page copy)."""
    sa, sb = os.path.getsize(a), os.path.getsize(b)
    header_offsets, beyond = [], 0
    with open(a, 'rb') as fa, open(b, 'rb') as fb:
        off = 0
        while True:
            ca, cb = fa.read(1024 * 1024), fb.read(1024 * 1024)
            if not ca and not cb:
                break
            if ca != cb:
                n = max(len(ca), len(cb))
                for i in range(n):
                    x = ca[i] if i < len(ca) else None
                    y = cb[i] if i < len(cb) else None
                    if x != y:
                        pos = off + i
                        if pos < SQLITE_HEADER_SIZE:
                            header_offsets.append(pos)
                        else:
                            beyond += 1
            off += len(ca)
    return {'size_source': sa, 'size_restored': sb, 'size_equal': sa == sb,
            'identical': sa == sb and not header_offsets and beyond == 0,
            'header_diff_offsets': header_offsets,
            'diff_bytes_beyond_header': beyond}


def integrity_check(conn: sqlite3.Connection) -> str:
    """Return 'ok' or the first integrity problem. A database so damaged that
    SQLite refuses to inspect it raises DatabaseError; that is reported as a
    failure string rather than allowed to escape as a traceback."""
    try:
        return conn.execute('PRAGMA integrity_check').fetchone()[0]
    except sqlite3.DatabaseError as exc:
        return f'integrity_check raised {exc.__class__.__name__}: {exc}'


def foreign_key_check(conn: sqlite3.Connection) -> list:
    conn.execute('PRAGMA foreign_keys=ON')
    return [tuple(r) for r in conn.execute('PRAGMA foreign_key_check')]


# ---------------------------------------------------------------------------
# encrypted application backups
# ---------------------------------------------------------------------------

def _derive_fernet():
    """Mirror of app.backup_manager._get_backup_key(), kept local so this tool
    never imports the application package. Key material comes from the
    environment only and is never returned to the caller as text."""
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        import base64
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RestoreRefused("the 'cryptography' package is required to "
                             "restore an encrypted backup") from exc
    key_material = os.getenv('PII_ENCRYPTION_KEY') or os.getenv('SECRET_KEY', '')
    if not key_material:
        raise RestoreRefused('encrypted backup given but neither '
                             'PII_ENCRYPTION_KEY nor SECRET_KEY is set')
    derived = HKDF(algorithm=hashes.SHA256(), length=32,
                   salt=b'pms-backup-encryption-salt',
                   info=b'backup-key').derive(key_material.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def decrypt_to_temp(enc_path: str, workdir: str) -> str:
    fernet = _derive_fernet()
    with open(enc_path, 'rb') as fh:
        token = fh.read()
    try:
        plain = fernet.decrypt(token)
    except Exception as exc:
        raise RestoreFailed(f'could not decrypt {enc_path}: {exc.__class__.__name__}') from exc
    fd, tmp = tempfile.mkstemp(prefix='restore_plain_', suffix='.db', dir=workdir)
    with os.fdopen(fd, 'wb') as out:
        out.write(plain)
    return tmp


# ---------------------------------------------------------------------------
# the restore
# ---------------------------------------------------------------------------

def restore(source: str, dest: str, *, manifest_path: str | None = None,
            run_id: str | None = None, overwrite_dest: bool = False,
            evidence_dir: str | None = None, quiet: bool = False) -> dict:
    """Restore *source* into *dest* and verify. Returns the restore manifest.

    Raises RestoreRefused before touching anything if the request is unsafe;
    raises RestoreFailed after writing the manifest if verification fails.
    """
    log = (lambda *a: None) if quiet else (lambda *a: print(*a))
    run_id = run_id or _dt.datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8]
    started = _dt.datetime.now().isoformat(timespec='seconds')

    # ---- refusals: nothing has been written yet ---------------------------
    if not source or not os.path.isfile(source):
        raise RestoreRefused(f'backup artifact not found: {source!r}')
    if os.path.getsize(source) == 0:
        raise RestoreRefused(f'backup artifact is empty: {source!r}')
    if not dest:
        raise RestoreRefused('an explicit isolated --dest is required')
    if is_production_path(dest):
        raise RestoreRefused('destination resolves to the production database '
                             'or the instance/ directory; refusing')
    if is_production_path(source) and _norm(source) == _norm(PRODUCTION_DB):
        raise RestoreRefused('the production database is not a backup '
                             'artifact; refusing to use it as a source')
    if _norm(source) == _norm(dest):
        raise RestoreRefused('source and destination are the same file')
    if os.path.isdir(dest):
        raise RestoreRefused(f'destination is a directory: {dest!r}')
    if os.path.exists(dest) and not overwrite_dest:
        raise RestoreRefused(f'destination already exists: {dest!r} '
                             '(pass --overwrite-dest to replace an isolated file)')
    dest_dir = os.path.dirname(os.path.abspath(dest)) or '.'
    os.makedirs(dest_dir, exist_ok=True)

    if manifest_path is None:
        cand = source + '.manifest.json'
        manifest_path = cand if os.path.isfile(cand) else None

    result = {
        'tool': 'tools/restore_db.py',
        'run_id': run_id,
        'started_at': started,
        'source_path': os.path.abspath(source),
        'source_manifest_path': os.path.abspath(manifest_path) if manifest_path else None,
        'restored_path': os.path.abspath(dest),
        'production_db_path': PRODUCTION_DB,
        'production_touched': False,
        'checks': {},
        'failures': [],
        'limitations': [
            'Database-level verification only. The application was not booted '
            'against the restored file (create_app() runs migrations, init_data() '
            'and the scheduler). Application-level equivalence is not claimed.',
            'No table named "invoices" exists in FinalGrid; invoice identity is '
            'evaluated via reservations.invoice_number and tax_lines.',
        ],
        'verification_status': 'FAIL',
    }
    checks = result['checks']
    failures = result['failures']

    def check(name, ok, detail=None):
        checks[name] = {'ok': bool(ok), 'detail': detail}
        if not ok:
            failures.append(f'{name}: {detail}')
        log(f'  [{"ok" if ok else "FAIL"}] {name}' + (f' — {detail}' if detail and not ok else ''))
        return ok

    workdir = tempfile.mkdtemp(prefix='restore_work_', dir=dest_dir)
    plain_source = source
    try:
        # ---- 1. source is a SQLite database ------------------------------
        log(f'run        : {run_id}')
        log(f'source     : {source}')
        result['source_encrypted'] = source.lower().endswith('.enc')
        if result['source_encrypted']:
            plain_source = decrypt_to_temp(source, workdir)
            result['source_sha256_encrypted'] = sha256_file(source)
        check('source_sqlite_header', has_sqlite_header(plain_source),
              'file does not start with the SQLite header')
        result['source_sha256'] = sha256_file(plain_source)
        result['source_size_bytes'] = os.path.getsize(plain_source)
        log(f'source sha : {result["source_sha256"]}')

        # ---- 2. manifest agreement --------------------------------------
        if manifest_path:
            with open(manifest_path, 'r', encoding='utf-8') as fh:
                bmanifest = json.load(fh)
            expected = bmanifest.get('snapshot_sha256')
            result['backup_manifest'] = {
                'snapshot_sha256': expected,
                'source_sha256_before': bmanifest.get('source_sha256_before'),
                'method': bmanifest.get('method'),
                'created_at': bmanifest.get('created_at'),
                'row_counts': bmanifest.get('row_counts'),
            }
            check('source_matches_backup_manifest',
                  expected == result['source_sha256'],
                  f'manifest {expected} != actual {result["source_sha256"]}')
        else:
            checks['source_matches_backup_manifest'] = {
                'ok': None, 'detail': 'no backup manifest available; source hash recorded, not verified'}

        if failures:
            raise RestoreFailed('source verification failed before restore')

        # ---- 3. source integrity (read-only) -----------------------------
        src = _ro_connect(plain_source)
        try:
            src_integrity = integrity_check(src)
            if not check('source_integrity_check', src_integrity == 'ok', src_integrity):
                raise RestoreFailed('source integrity check failed; not restoring a damaged backup')
            src_counts = row_counts(src)
            src_digests = {t: content_digest(src, t) for t in src_counts}
            src_schema = schema_sql(src)
            src_invoices = src.execute(INVOICE_QUERY).fetchone()[0]
        finally:
            src.close()
        if failures:
            raise RestoreFailed('source integrity check failed; not restoring a damaged backup')

        # ---- 4. restore through the backup API into a temp file ----------
        tmp_dest = os.path.join(workdir, 'restored.tmp')
        src = _ro_connect(plain_source)
        try:
            dst = sqlite3.connect(tmp_dest)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        if os.path.exists(dest):
            os.remove(dest)          # only reachable with --overwrite-dest, never production
        os.replace(tmp_dest, dest)
        result['restored_at'] = _dt.datetime.now().isoformat(timespec='seconds')
        result['restore_method'] = 'sqlite-backup-api'

        # ---- 5. restored file verification -------------------------------
        check('restored_file_exists', os.path.isfile(dest), 'restored file missing')
        result['restored_sha256'] = sha256_file(dest)
        result['restored_size_bytes'] = os.path.getsize(dest)
        log(f'restored   : {dest}')
        log(f'restored sha: {result["restored_sha256"]}')
        check('restored_sqlite_header', has_sqlite_header(dest), 'no SQLite header')

        rc = _ro_connect(dest)
        try:
            r_integrity = integrity_check(rc)
            check('restored_integrity_check', r_integrity == 'ok', r_integrity)
            fk = foreign_key_check(rc)
            result['foreign_key_check_violations'] = fk[:50]
            check('restored_foreign_key_check', len(fk) == 0, f'{len(fk)} violation(s)')
            names = table_names(rc)
            missing = [t for t in REQUIRED_TABLES if t not in names]
            result['restored_tables'] = len(names)
            check('required_tables_present', not missing, f'missing: {missing}')
            try:
                rc.execute('SELECT sql FROM sqlite_master').fetchall()
                check('schema_readable', True)
            except sqlite3.Error as exc:
                check('schema_readable', False, str(exc))
            r_counts = row_counts(rc)
            r_digests = {t: content_digest(rc, t) for t in r_counts}
            r_schema = schema_sql(rc)
            r_invoices = rc.execute(INVOICE_QUERY).fetchone()[0]
        finally:
            rc.close()
        check('schema_sql_equal', src_schema == r_schema,
              f'{len(src_schema)} source vs {len(r_schema)} restored schema objects, or text differs')

        # ---- 6. data comparison -----------------------------------------
        diff_counts = {t: (src_counts.get(t), r_counts.get(t))
                       for t in set(src_counts) | set(r_counts)
                       if src_counts.get(t) != r_counts.get(t)}
        result['row_counts'] = {
            'tables': len(r_counts),
            'total_rows_source': sum(src_counts.values()),
            'total_rows_restored': sum(r_counts.values()),
            'key_tables': {t: {'source': src_counts.get(t), 'restored': r_counts.get(t)}
                           for t in ('reservations', 'folios', 'payments', 'extra_charges',
                                     'tax_lines', 'audit_logs', 'night_audit_logs')},
            'invoices': {'source': src_invoices, 'restored': r_invoices,
                         'basis': 'reservations.invoice_number IS NOT NULL'},
            'differences': diff_counts,
        }
        check('row_counts_equal', not diff_counts, f'differences: {diff_counts}')
        check('invoice_count_equal', src_invoices == r_invoices,
              f'{src_invoices} != {r_invoices}')
        diff_digest = [t for t in src_digests if src_digests[t] != r_digests.get(t)]
        result['content_digests'] = {
            'tables_compared': len(src_digests),
            'financial_tables': {t: {'source': src_digests.get(t), 'restored': r_digests.get(t)}
                                 for t in DIGEST_TABLES if t in src_digests},
            'differing_tables': diff_digest,
        }
        check('content_digests_equal_all_tables', not diff_digest, f'differ: {diff_digest}')
        if manifest_path and result.get('backup_manifest', {}).get('row_counts'):
            mcounts = result['backup_manifest']['row_counts']
            mdiff = {t: (mcounts.get(t), r_counts.get(t)) for t in set(mcounts) | set(r_counts)
                     if mcounts.get(t) != r_counts.get(t)}
            check('row_counts_match_backup_manifest', not mdiff, f'differences: {mdiff}')

        # ---- 7. physical equivalence beyond the header --------------------
        bd = byte_diff(plain_source, dest)
        result['byte_comparison'] = bd
        result['restored_sha256_equals_source'] = bd['identical']
        checks['whole_file_sha256_identical'] = {
            'ok': None,
            'detail': ('identical' if bd['identical'] else
                       f'header fields differ at offsets {bd["header_diff_offsets"]} '
                       '(backup API rewrites change counter / version-valid-for); informational')}
        check('body_identical_beyond_header',
              bd['size_equal'] and bd['diff_bytes_beyond_header'] == 0,
              f'size_equal={bd["size_equal"]}, differing bytes beyond header={bd["diff_bytes_beyond_header"]}')

        # ---- production never touched ------------------------------------
        result['production_touched'] = False

        result['verification_status'] = 'PASS' if not failures else 'FAIL'
        result['finished_at'] = _dt.datetime.now().isoformat(timespec='seconds')
        if failures:
            raise RestoreFailed('; '.join(failures))
        return result
    except RestoreFailed:
        result['verification_status'] = 'FAIL'
        result['finished_at'] = _dt.datetime.now().isoformat(timespec='seconds')
        raise
    finally:
        # the manifest is written on success and on verification failure alike
        _write_manifest(result, dest, evidence_dir)
        shutil.rmtree(workdir, ignore_errors=True)


def _write_manifest(result: dict, dest: str, evidence_dir: str | None) -> None:
    targets = [os.path.abspath(dest) + '.restore_manifest.json']
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        targets.append(os.path.join(evidence_dir, 'restore_manifest.json'))
    result['manifest_paths'] = targets
    for t in targets:
        try:
            with open(t, 'w', encoding='utf-8') as fh:
                json.dump(result, fh, indent=2, sort_keys=True)
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--source', required=True, help='backup artifact (.db or .db.enc)')
    ap.add_argument('--dest', required=True,
                    help='explicit isolated destination file; never instance/pms.db')
    ap.add_argument('--manifest', default=None,
                    help='backup manifest to verify the source against '
                         '(default: <source>.manifest.json if present)')
    ap.add_argument('--run-id', default=None)
    ap.add_argument('--evidence-dir', default=None,
                    help='also write restore_manifest.json here')
    ap.add_argument('--overwrite-dest', action='store_true',
                    help='replace an existing ISOLATED destination file')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args(argv)
    try:
        res = restore(args.source, args.dest, manifest_path=args.manifest,
                      run_id=args.run_id, overwrite_dest=args.overwrite_dest,
                      evidence_dir=args.evidence_dir, quiet=args.quiet)
    except RestoreRefused as exc:
        print(f'REFUSED    : {exc}', file=sys.stderr)
        return 2
    except RestoreFailed as exc:
        print(f'VERDICT    : RESTORE FAILED — {exc}', file=sys.stderr)
        return 1
    if not args.quiet:
        print(f'VERDICT    : RESTORE VERIFIED — {res["restored_path"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
