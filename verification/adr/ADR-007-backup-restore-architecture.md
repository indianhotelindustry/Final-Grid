# ADR-007 — Backup / Restore Architecture

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-005 (PD-006), FD-006 (D9 = Backup Restore Verification) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. No backup or restore was executed. |

## Context — verified 2026-09-08

| Capability | State | Evidence |
|---|---|---|
| Backup creation (application) | Exists — `run_backup` → `_run_sqlite_backup` uses **`shutil.copy2`** on the live file; encrypted (`_encrypt_file`); purged after 30 days | `app/backup_manager.py:159-252, 330` |
| Backup creation (tooling) | Exists — sqlite backup API from a `mode=ro` source | `tools/backup_db.py:72-115`; `verification/dbcopy.py:100` |
| Backup integrity record | **Absent** — no checksum/hash in the application path; `BackupLog` has `filename, size_bytes, backup_type, status, error_message, created_by_user_id, created_at` only | `app/models.py:1463-1476` |
| Restore capability | **Absent** — no restore function in `app/`, `tools/`, or any launcher | exhaustive search |
| Restore rehearsal | Never performed | no evidence set among 169 |
| Wave 0 D9 | Blocked/Not started (`WAVE0_STATUS.md`, `README.md`); needs the checksum column, a production schema change Wave 0 forbids | `WAVE0_STATUS.md:316-322` |
| Faults depending on D9 | `FLT-D04` (corrupt backup), `FLT-D05` (restored ≠ backed up) — UNCOVERED | `D5_COMPLETION_REPORT.md:597-611` |
| Pre-update backup | `update.bat:75-97` calls `run_backup(backup_type='pre-update')` | — |
| Repository protection | `git bundle` procedure with restore proof, distinct from data protection | `ENGINEERING_GUIDE.md` §5 R0 |

## Decision (as ruled)

- D9 is **Backup Restore Verification**; backup creation alone does not satisfy it; it is a mandatory production-readiness gate (FD-006).
- PD-006 requires a rehearsed restore proving the recovery artifact restores the system to a verified state (FD-005).

## Proposed architecture

1. **One backup mechanism** for SQLite: the sqlite backup API (transactionally consistent). The `shutil.copy2` path is retired for SQLite under a later directive.
2. **Integrity record per backup:** SHA-256 of the plaintext file, `PRAGMA integrity_check` result, per-table row-count manifest, app version, business date, anchor at time of backup. Stored either as a `backup_logs` checksum column **or** an out-of-band manifest file beside the backup — **UNRESOLVED** (the column is a production schema change; the manifest is not).
3. **Restore procedure:** decrypt → write to a fresh path → verify manifest and hash → boot the application read-only against the restored file → run `inv-run` → record a *restore rehearsal record* (Master Plan §10 artifact).
4. **Scheduled restore verification** on a copy, so D9 can be *commissioned* (a control that has never failed is not commissioned, P9).
5. **Retention:** pre-mutation and pre-update backups exempt from the 30-day purge — **UNRESOLVED**.
6. **Repository bundle** procedure retained as a separate control (R0).

## Minimum capability before any production mutation (proposed)

Items 1, 2 (manifest form), 3 and one recorded rehearsal against the
current anchor. Item 4 may follow.

## Unresolved

Checksum column vs manifest · "verified state" definition (ADR-006) ·
retention policy · whether restore lives in `app/backup_manager.py`,
`tools/`, or the installer · encryption-key custody for restore on a
different machine (`_get_backup_key`, `app/backup_manager.py:34`).

## Implementation boundary

None authorized. Building restore is Phase 9 unit 9.2/9.3 or an earlier
bounded directive if the Founder so orders; not this ADR.
