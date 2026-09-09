# Phase 1 — Recovery Gate Plan

**Directive:** FG-P1-IMPLEMENTATION-READINESS-20260908-01 · **HEAD:** `e69f2ac` · **Status:** PLAN ONLY. No backup, restore, or rehearsal was executed; no backup code was changed.

## 1. Gate definition (not weakened)

Before any Phase 1 **production data mutation**: PD-004 (Founder authorization naming the mutation) · PD-005 (backup → backup verification → recovery plan/rehearsal → execute → post-mutation verification → invariant verification → evidence) · PD-006 (rehearsed restore proving the artifact restores to a verified state) · integrity verification · manifest · cryptographic hash · restore verification evidence.

**Current state: UNSATISFIED.** Consequence: **no production data migration is schedulable.** (On the live database Phase 1 needs none — `MIGRATION_AND_DATA_PLAN.md` §4 — but the gate also governs demonstrated rollback for a deployed code release, which is why Slice 1 comes first.)

## 2. What exists today — measured against ADR-007's seven components

| # | Component | `tools/backup_db.py` (manual) | `app/backup_manager.py` (app, scheduled 03:00 / pre-update) | Gap |
|---|---|---|---|---|
| 1 | Transactionally safe backup | **Yes** — sqlite backup API, source `mode=ro` | **No** — `shutil.copy2` on the live file | App path must not be relied upon |
| 2 | Integrity verification | **Yes** — `PRAGMA integrity_check` on the snapshot | No | — |
| 3 | Cryptographic hash | **Yes** — source before/after, snapshot SHA-256 | No | — |
| 4 | Machine-readable manifest | **Yes** — `<snapshot>.manifest.json` incl. per-table row counts | No (`backup_logs` has no checksum) | — |
| 5 | Retained recovery artifact | Written outside the repo (`../db-backups/`), no retention policy | Encrypted, purged after 30 days (`_purge_old_backups`) | Retention rule needed; pre-mutation snapshots must be exempt from purge |
| 6 | Rehearsed restore | **No** | **No** | **Restore does not exist** |
| 7 | Documented restore verification | **No** | **No** | — |

Key custody: application backups are Fernet-encrypted with a key derived (HKDF) from `PII_ENCRYPTION_KEY` or `SECRET_KEY` (`backup_manager.py:34-66`). A restore on a different machine requires the same key material; `.env` is untracked and not in the repository bundle. Must be documented in the recovery procedure.

## 3. Work required (planning; Slice 1)

| # | Work item | Kind | Notes |
|---|---|---|---|
| R1 | Backup creation | reuse `tools/backup_db.py`; add `--label` conventions (`pre-<slice>`, `pre-pd###`) | Already API-based |
| R2 | SQLite consistency | reuse (backup API; `journal_mode=delete` on the live file) | — |
| R3 | Integrity check | reuse | — |
| R4 | Cryptographic hash | reuse; add hash of manifest itself | — |
| R5 | Manifest | reuse; add `app_version`, `business_date`, `anchor_sha256`, `alembic/schema_migrations` state | Small change to the tool |
| R6 | Retention | new policy: pre-mutation and rehearsal snapshots never auto-purged; scheduled app backups keep 30 days | Documentation + tool flag |
| R7 | **Restore** | new `tools/restore_db.py`: input snapshot (+ optional `.enc` decrypt using the same HKDF derivation), target path **never** `instance/pms.db` unless `--confirm-production` under a PD-004 directive; writes atomically to a temp file then renames | New |
| R8 | Restored-database verification | hash equality with manifest `snapshot_sha256`; `integrity_check`; per-table row counts equal manifest | New (mirrors backup checks) |
| R9 | Row-count verification | included in R8 | — |
| R10 | **Application-open verification** | **Not by booting `create_app()` against the restored file** — boot runs `_run_pending_migrations`, `init_data()` and starts the scheduler (F5 in the readiness report), which would mutate the restored file and could post a night audit. Instead: `verification/dbcopy.py :: make_copy(source=<restored file>)` then `python -m verification inv-run --tag restore_rehearsal` and `selfcheck`; verdict equality with the source pack proves the application reads the restored state identically | Uses existing harness |
| R11 | Rehearsal evidence | `verification/evidence/<stamp>_restore_rehearsal/` with manifest, restore record, `inv-run` before/after, hashes | New pack format = Master Plan §10 "Restore rehearsal record" |
| R12 | Rollback usage | procedure: PD-005 step 1 snapshot with `--label pre-<mutation>` → on failure, `restore_db.py` to a scratch path → R8/R10 verification → only then, under the PD-004 directive's rollback clause, replace production | Documented; production replacement itself is a PD-004 act |

"Verified state" for PD-006 (proposed in ADR-006, unconfirmed — B-5): identical SHA-256 to the manifest, **or** identical `integrity_check` + row-count manifest + `inv-run` verdicts where a byte difference is expected and explained.

## 4. Rehearsal protocol (to be executed only under a Slice 1 directive)

1. `selfcheck` → READ-ONLY VERIFIED; record anchor.
2. `tools/backup_db.py --label rehearsal` → manifest M.
3. `tools/restore_db.py <snapshot> --to <scratch>/restored.db` → restore record R (hash, integrity, counts).
4. `make_copy(source=<scratch>/restored.db)` → `inv-run --tag restore_rehearsal` → pack P2; compare with the Slice 0 baseline pack P1: registered/HOLDS/VIOLATED/figures identical; D11 ids identical.
5. Record R11 pack; anchor re-verified unchanged; port 5000 clear.
6. Repeat once from an **encrypted application backup** to prove key custody works.

Exit: two rehearsal records (plain and encrypted source) against the current anchor. Until then PD-006 is unsatisfied.

## 5. Explicit non-actions

Nothing executed. `backups/` untouched. No snapshot created. No key material read or printed.
