# ADR-006 — Production Mutation Controls

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-005 (PD-004 / PD-005 / PD-006), FD-007 (migration authority), FD-019 (execution boundary), FD-004 (authority chain) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. **Records no authorization for any mutation.** |

## Context

Before FD-005, the production-data safety controls existed only in the
Master Plan artifact (§08). The repository's own closest apparatus:

- `verification/dbcopy.py :: make_copy()` — sqlite backup API copy; `selfcheck` proves read-only; SHA-256 anchor discipline (`ENGINEERING_GUIDE.md` §4).
- `ENGINEERING_GUIDE.md` §5 — declare-first / baseline / change / compare / retain.
- `WAVE1_BLUEPRINT.md` §9 — ten-step gate for material releases, including "D9 exists and is commissioned, or a recorded exception … with a manually verified snapshot".
- `tools/production_initialize.py` — an existing production-data mutation tool with dry-run default, pre-run snapshot, hash and row-count verification, boot check. Its authorization is NOT DEFINED IN REPOSITORY.
- Migration mechanisms: inline `_run_pending_migrations` (57 entries, tracked in `schema_migrations`, **runs unattended at every `create_app()`** and on updater restart); Alembic (7 revisions, no caller, no `alembic_version` table); `update.bat` glob of `run_migration_*.py`; `_sqlite_cols_to_add` column fixer.

## Decision (as ruled)

**PD-004 — Production Mutation Authorization.** Explicit Founder authorization for a defined production schema/data mutation.

**PD-005 — Production Mutation Protocol.** backup → backup verification → recovery plan/rehearsal → execute mutation → post-mutation verification → invariant verification → evidence.

**PD-006 — Restore Verification.** A rehearsed restore proving that the recovery artifact can actually restore the system to a verified state.

**FD-007** enumerates what a production migration requires; **FD-019** states that implementation completion is not production authorization.

## Architecture — how each PD-005 step is satisfied (proposed)

| Step | Mechanism (proposed) | Exists today? |
|---|---|---|
| Authorization (PD-004) | A `PD-###` directive naming the mutation, tables/rows, expected invariant movement per figure, and rollback path; recorded in `FOUNDER_DECISIONS.md` before execution | Procedural — no mechanism needed |
| Backup | sqlite backup API only (as `tools/backup_db.py`, `make_copy()`); **not** `shutil.copy2` | Partially (`copy2` path must not be used) |
| Backup verification | SHA-256 + `PRAGMA integrity_check` + per-table row-count manifest, recorded | Pattern exists in `production_initialize.py`; not a standing control |
| Recovery plan / rehearsal (PD-006) | Restore the backup to a fresh file, prove equality, boot read-only against it, run `inv-run`; record | **No restore capability exists** — see ADR-007 |
| Execute | Under an operator session, scheduler disabled, port clear (SC-3), never at boot time unattended | Unattended boot-time migration is the current behaviour — must change under a separate directive |
| Post-mutation verification | `integrity_check`; manifest comparison; `gm-verify`; `replay-verify` | Tools exist |
| Invariant verification | `inv-run` compared to the pre-mutation pack; movement must match the declaration figure by figure ("a value that held when it should have moved is also a failure", `ENGINEERING_GUIDE.md` §5) | Tool exists |
| Evidence | Pack under `verification/evidence/<stamp>_pd###_<name>/`, committed, never edited (SC-4) | Practised |

## Definition proposed for "verified state" (PD-006)

Identical SHA-256 of the restored file **or**, where a legitimate
difference is expected (vacuum, journal), identical `integrity_check`
result, identical per-table row-count and per-row hash manifest, and
identical `inv-run` verdicts. **UNRESOLVED** — needs Founder confirmation.

## Unresolved

| Item | Status |
|---|---|
| Single schema authority (inline registry vs Alembic vs new) | **Not decided.** Register R2 finds the inline registry live and Alembic orphaned. |
| Whether boot-time unattended migration is acceptable at all on production | Not decided; FD-009 principle applies to financially material mutation |
| Scope of "production migration" in PD-004 — schema only or any data mutation | FD-007 lists "schema/data migration"; treated here as **any production schema or data mutation**, including `production_initialize.py` runs and any future row attribution |
| "Verified state" definition | Proposed above; unconfirmed |
| Retention exemption for pre-mutation backups from the 30-day purge (`backup_manager.py:330`) | Not decided |

## Implementation boundary

None authorized. No mutation is authorized by this ADR or by FD-005.
