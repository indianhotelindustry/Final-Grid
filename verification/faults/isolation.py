"""
The isolation layer.

Every fault is injected into a **private disposable copy** and nothing
else. This module owns that guarantee and, more importantly, owns the
evidence for it — a platform that injects faults into a live financial
system on the strength of an assertion is not a platform, it is an
incident waiting for a bad afternoon.

Four guarantees, each verified rather than claimed:

1. **Production is never opened writable.** Inherited unchanged from D1:
   ``mode=ro`` source connection, SQLite backup API, SHA-256 before and
   after. The platform re-verifies at the end of every fault, not once
   per run, so the fault that broke it can be named.

2. **Each fault gets its own file.** Derived from a pristine baseline
   copy, never from the previous fault's copy. Faults cannot contaminate
   each other by construction, and the platform proves it by hashing the
   baseline before and after every injection.

3. **Cleanup is verified.** The seeded copy is deleted and its absence
   checked. A cleanup that silently failed would leave a fault's data on
   disk for the next run to pick up.

4. **Concurrency is safe.** Layer probes run in parallel, each in its own
   process with its own ``PVF_WORK_SUFFIX``, so the fixed working-copy
   names D1-D4 use cannot collide. Without the suffix two concurrent
   probes would recreate each other's working file mid-read and both
   would produce results nobody could trust — a data race that existed
   silently until this platform needed it not to.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field

from verification.config import PRODUCTION_DB, PVF_WORK_DIR
from verification.dbcopy import (
    CopyHandle, assert_production_untouched, make_copy, production_fingerprint,
)

#: Where seeded copies live. Separate from ``_work`` so a stray file is
#: obviously a fault artefact rather than a deliverable's working copy.
ARENA_DIR = os.path.join(PVF_WORK_DIR, 'fip_arena')


class IsolationBreach(RuntimeError):
    """The platform's containment did not hold.

    Never expected. Means a fault escaped its private copy, or the
    baseline moved underneath the run. Either invalidates every result
    produced after it.
    """


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Arena:
    """A pristine baseline plus the evidence that it stays pristine."""
    baseline_path: str
    baseline_hash: str
    production_path: str
    production_hash: str
    handle: CopyHandle = None
    issued: list = field(default_factory=list)

    # -- per-fault copies -------------------------------------------------

    def issue(self, fault_id: str) -> str:
        """A private copy of the baseline for one fault."""
        os.makedirs(ARENA_DIR, exist_ok=True)
        safe = ''.join(c if c.isalnum() or c in '._-' else '_'
                       for c in fault_id)
        path = os.path.join(ARENA_DIR, f'{safe}.db')
        for suffix in ('', '-wal', '-shm', '-journal'):
            stale = path + suffix
            if os.path.exists(stale):
                os.remove(stale)
        shutil.copy2(self.baseline_path, path)
        self.issued.append(path)
        return path

    def verify_baseline(self, fault_id: str = '') -> None:
        """The baseline must be byte-identical to when the run started."""
        now = _sha256(self.baseline_path)
        if now != self.baseline_hash:
            raise IsolationBreach(
                f'The pristine baseline changed during the run'
                + (f' (while handling {fault_id})' if fault_id else '')
                + f'.\n  at start: {self.baseline_hash}\n  now:      {now}\n'
                f'A fault escaped its private copy. Every result produced '
                f'after this point is worthless and the run must be '
                f'discarded.')

    def verify_production(self, fault_id: str = '') -> str:
        """Production must be byte-identical. Checked per fault, not per run,
        so a breach can be attributed to the injection that caused it."""
        now, _size = production_fingerprint(self.production_path)
        if now != self.production_hash:
            raise IsolationBreach(
                f'PRODUCTION CHANGED during fault injection'
                + (f' ({fault_id})' if fault_id else '')
                + f'.\n  at start: {self.production_hash}\n  now:      {now}')
        return now

    def cleanup(self, path: str) -> bool:
        """Delete a seeded copy and verify it is gone."""
        for suffix in ('', '-wal', '-shm', '-journal'):
            target = path + suffix
            if os.path.exists(target):
                try:
                    os.remove(target)
                except OSError:
                    return False
        return not os.path.exists(path)

    def cleanup_all(self) -> dict:
        results = {path: self.cleanup(path) for path in self.issued}
        self.issued = [p for p, ok in results.items() if not ok]
        return results


def open_arena(source: str = PRODUCTION_DB) -> Arena:
    """Take the pristine baseline every fault will be derived from."""
    production_hash, _size = production_fingerprint(source)
    handle = make_copy(name='fip_baseline.db', source=source)
    return Arena(
        baseline_path=handle.copy_path,
        baseline_hash=_sha256(handle.copy_path),
        production_path=handle.source_path,
        production_hash=production_hash,
        handle=handle,
    )


def close_arena(arena: Arena) -> dict:
    """Tear down and report what the teardown proved."""
    cleanup = arena.cleanup_all()
    arena.verify_baseline()
    production_hash = arena.verify_production()
    return {
        'copies_removed': sum(1 for ok in cleanup.values() if ok),
        'copies_left_behind': [p for p, ok in cleanup.items() if not ok],
        'baseline_unchanged': True,
        'production_unchanged': production_hash == arena.production_hash,
        'production_sha256': production_hash,
    }
