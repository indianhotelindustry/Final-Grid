"""Verified read-only snapshot of the production database.

Operational tooling, deliberately NOT part of ``verification/``. The
verification package is a measuring instrument and must not become part of
the thing it measures; this script is the opposite — it exists to change
the state of the world by producing a backup.

It is an interim measure. D9 (Backup Restore Verification) will supersede
it, and cannot be built until ``backup_logs`` carries a checksum column —
which is a production schema change and therefore Wave 1 work. Until then
this script's manifest is the only fingerprint of a backup that exists,
and it is written beside the snapshot rather than into the database.

Guarantees, in the order they are established:

1. **The source is opened read-only.** SQLite URI ``mode=ro``. The
   connection is incapable of writing.
2. **The source is hashed before and after.** A difference aborts and is
   reported as an incident: something else wrote to production while the
   backup ran.
3. **The copy is transactionally consistent.** SQLite's backup API, which
   is safe even against a live writer. A byte copy of a database with an
   active WAL is not.
4. **The snapshot is opened and checked.** ``PRAGMA integrity_check``,
   plus a row-count comparison against the source across every table. A
   backup nobody has opened is a file, not a backup (P9).
5. **The snapshot is written outside the repository**, so live financial
   data is never at risk of being committed.

Usage::

    python tools/backup_db.py
    python tools/backup_db.py --label pre-wave1
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

PRODUCTION_DB = os.path.join(REPO, 'instance', 'pms.db')

#: Outside the repository, deliberately. A snapshot inside it would be one
#: careless `git add -A` away from committing live guest and payment data.
BACKUP_DIR = os.path.join(os.path.dirname(REPO), 'db-backups')


class BackupFailed(RuntimeError):
    """The snapshot could not be shown to be a faithful copy."""


class ProductionWriteDetected(RuntimeError):
    """The production database changed while the backup was running."""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _ro_connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect('file:' + path.replace('\\', '/') + '?mode=ro',
                           uri=True)


def table_counts(path: str) -> dict:
    """Row count per table, read through a read-only connection."""
    conn = _ro_connect(path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                for t in tables}
    finally:
        conn.close()


def make_backup(label: str = '') -> dict:
    if not os.path.isfile(PRODUCTION_DB):
        raise BackupFailed(f'Production database not found: {PRODUCTION_DB}')

    os.makedirs(BACKUP_DIR, exist_ok=True)

    stamp = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'pms_{stamp}' + (f'_{label}' if label else '') + '.db'
    dest = os.path.join(BACKUP_DIR, name)

    # --- 1/2. fingerprint the source before touching it ------------------
    hash_before = sha256(PRODUCTION_DB)
    size_before = os.path.getsize(PRODUCTION_DB)
    counts_before = table_counts(PRODUCTION_DB)

    print(f'source     : {PRODUCTION_DB}')
    print(f'size       : {size_before:,} bytes')
    print(f'sha256     : {hash_before}')
    print(f'tables     : {len(counts_before)}, '
          f'{sum(counts_before.values()):,} rows')

    # --- 3. transactionally consistent copy, read-only source ------------
    src = _ro_connect(PRODUCTION_DB)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    # --- 2 (cont). prove production is untouched -------------------------
    hash_after = sha256(PRODUCTION_DB)
    if hash_after != hash_before:
        raise ProductionWriteDetected(
            'Production database changed while the backup was running.\n'
            f'  before: {hash_before}\n'
            f'  after:  {hash_after}\n'
            'Either the application was serving traffic, or something else '
            'wrote to it. The snapshot must not be trusted as a point-in-'
            'time copy until this is explained.')

    # --- 4. open the snapshot and check it -------------------------------
    verify = _ro_connect(dest)
    try:
        integrity = verify.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        verify.close()
    if integrity != 'ok':
        raise BackupFailed(f'integrity_check on the snapshot: {integrity}')

    counts_after = table_counts(dest)
    if counts_after != counts_before:
        differing = {t: (counts_before.get(t), counts_after.get(t))
                     for t in set(counts_before) | set(counts_after)
                     if counts_before.get(t) != counts_after.get(t)}
        raise BackupFailed(f'row counts differ from source: {differing}')

    snapshot_hash = sha256(dest)
    manifest = {
        'created_at': _dt.datetime.now().isoformat(timespec='seconds'),
        'label': label,
        'source_path': PRODUCTION_DB,
        'source_sha256_before': hash_before,
        'source_sha256_after': hash_after,
        'source_size_bytes': size_before,
        'source_unchanged': True,
        'snapshot_path': dest,
        'snapshot_sha256': snapshot_hash,
        'snapshot_size_bytes': os.path.getsize(dest),
        'method': 'sqlite-backup-api',
        'source_opened': 'mode=ro',
        'integrity_check': integrity,
        'tables': len(counts_after),
        'total_rows': sum(counts_after.values()),
        'row_counts': counts_after,
        'note': ('Interim operational backup. Superseded by D9 once '
                 'backup_logs carries a checksum column.'),
    }
    with open(dest + '.manifest.json', 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    print()
    print(f'snapshot   : {dest}')
    print(f'sha256     : {snapshot_hash}')
    print(f'integrity  : {integrity}')
    print(f'row counts : match across {len(counts_after)} tables')
    print(f'source now : {hash_after}')
    print('VERDICT    : BACKUP VERIFIED — production unchanged')
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--label', default='',
                    help='suffix for the snapshot filename, e.g. pre-wave1')
    args = ap.parse_args()
    try:
        make_backup(args.label)
    except (BackupFailed, ProductionWriteDetected) as exc:
        print(f'\nFAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
