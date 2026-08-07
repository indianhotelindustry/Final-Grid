"""
Safe disposable copies of the production database.

This module is the single point at which the PVF touches production data,
and it is the reason the rest of the package can be trusted to be
read-only.

Guarantee
---------
The production database file is opened with SQLite URI ``mode=ro`` and is
hashed before and after every operation. If the two hashes differ, the
run is aborted and the discrepancy is reported as a critical incident —
because something wrote to production during a verification run, which
must never happen.

Why a copy at all, given we open read-only?
-------------------------------------------
Because the harness must create a Flask application instance to reach the
canonical engines, and ``create_app()`` writes: it runs the legacy
migration registry, the SQLite column fixer, and ``init_data()`` seeding.
Those writes are harmless and idempotent, but they are writes. Pointing an
application instance at production would violate the read-only guarantee
within seconds of boot. The copy absorbs them.

The copy is disposable and is recreated on every run, so no state carries
between runs and determinism is preserved.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass

from verification.config import PRODUCTION_DB, PVF_WORK_DIR


class ProductionWriteDetected(RuntimeError):
    """Raised when the production database changed during a PVF run.

    This is never expected. It means either the application was running
    and serving traffic during verification, or the PVF itself wrote to
    production. Both are incidents.
    """


@dataclass(frozen=True)
class CopyHandle:
    """A disposable working copy plus the evidence that production was
    untouched while it was made."""
    copy_path: str
    source_path: str
    source_hash_before: str
    source_size: int
    method: str                 # 'sqlite-backup-api' | 'file-copy'


def _sha256(path: str) -> str:
    """SHA-256 of a file, read in chunks so a large database does not
    have to fit in memory."""
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def production_fingerprint(path: str = PRODUCTION_DB) -> tuple[str, int]:
    """Return ``(sha256, size_bytes)`` for the production database.

    Reading a file does not modify it, so this is safe to call at any
    point including while the application is running.
    """
    return _sha256(path), os.path.getsize(path)


def working_copy_name(name: str) -> str:
    """Apply ``PVF_WORK_SUFFIX`` to a working-copy filename.

    Every deliverable takes its working copy under a fixed name —
    ``pvf_golden.db``, ``pvf_replay.db`` and so on. That is fine while
    runs are serial and it is a silent data race the moment two are not:
    the second run recreates the file the first is reading, and both
    produce results nobody can trust.

    D5 runs verification layers concurrently, so the suffix exists to
    give each process its own file. Empty by default, which is exactly
    the previous behaviour, so nothing that existed before D5 changes.
    """
    suffix = os.environ.get('PVF_WORK_SUFFIX', '')
    if not suffix:
        return name
    stem, dot, extension = name.rpartition('.')
    if not dot:
        return f'{name}{suffix}'
    return f'{stem}{suffix}.{extension}'


def make_copy(name: str = 'pvf_working.db',
              source: str = PRODUCTION_DB) -> CopyHandle:
    """Create a disposable working copy of *source*.

    Prefers SQLite's backup API, which produces a transactionally
    consistent copy even if a writer is active. Falls back to a plain file
    copy only if the backup API is unavailable, and records which method
    was used so the evidence pack is honest about it.
    """
    if not os.path.isfile(source):
        raise FileNotFoundError(f'Production database not found: {source}')

    os.makedirs(PVF_WORK_DIR, exist_ok=True)
    dest = os.path.join(PVF_WORK_DIR, working_copy_name(name))

    hash_before, size_before = production_fingerprint(source)

    # Remove any previous copy so no state survives between runs.
    for suffix in ('', '-wal', '-shm', '-journal'):
        stale = dest + suffix
        if os.path.exists(stale):
            os.remove(stale)

    method = 'sqlite-backup-api'
    try:
        # mode=ro guarantees the source connection cannot write.
        src_uri = 'file:' + source.replace('\\', '/') + '?mode=ro'
        src_conn = sqlite3.connect(src_uri, uri=True)
        try:
            dst_conn = sqlite3.connect(dest)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
    except Exception:
        # Fall back to a byte copy. Recorded in the handle so the evidence
        # pack states which mechanism produced the copy.
        method = 'file-copy'
        shutil.copy2(source, dest)

    # Prove we did not disturb the source.
    hash_after, _ = production_fingerprint(source)
    if hash_after != hash_before:
        raise ProductionWriteDetected(
            f'Production database changed while making a verification copy.\n'
            f'  before: {hash_before}\n'
            f'  after:  {hash_after}\n'
            f'Either the application was serving traffic during the run, or '
            f'the PVF wrote to production. Both are incidents and must be '
            f'investigated before any verification result is trusted.'
        )

    return CopyHandle(
        copy_path=dest,
        source_path=source,
        source_hash_before=hash_before,
        source_size=size_before,
        method=method,
    )


def assert_production_untouched(handle: CopyHandle) -> str:
    """Re-verify that production is byte-identical to when the copy began.

    Called at the end of every PVF run. The returned hash goes into the
    evidence pack as positive proof of the read-only guarantee — which is
    Principle 11 applied to the harness itself: the control produces
    positive evidence when the system is correct, not merely silence.
    """
    hash_now, _ = production_fingerprint(handle.source_path)
    if hash_now != handle.source_hash_before:
        raise ProductionWriteDetected(
            f'Production database changed DURING a verification run.\n'
            f'  at copy time: {handle.source_hash_before}\n'
            f'  now:          {hash_now}\n'
            f'Verification results from this run must be discarded.'
        )
    return hash_now


def sqlalchemy_url(handle: CopyHandle) -> str:
    """SQLAlchemy URL for the working copy, for ``DATABASE_URL``."""
    return 'sqlite:///' + handle.copy_path.replace('\\', '/')
