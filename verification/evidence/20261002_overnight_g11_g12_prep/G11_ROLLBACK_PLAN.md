# G11 Rollback Plan — PREPARATION DRAFT

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, G11/G12 preparation workstream; repository `C:/wtov` at `c9eeff0` |
| Kind | Preparation only. Defines what the G11 rehearsal must rehearse for rollback (R6) and the decision points a production deployment directive must settle. **Nothing here is authorized.** An in-place restore into the live `instance/` is a PD-004 act (`verification/FOUNDER_DECISIONS.md:477-478`) and `tools/restore_db.py` refuses it by design (`tools/restore_db.py:18-21`) |
| Requirement | `CERTIFICATION_GATES.md:20` — "a written, rehearsed procedure that returns the property to the previous tag and the pre-update backup, with the same verification afterwards"; `:41` — "rollback to the previous tag" in G11; FD-007 "defined recovery/rollback path" (`FOUNDER_DECISIONS.md:541`) |
| Precedent | `20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:115-121` (rollback path defined: stop → isolated restore → PD-004 replacement → code back) — "defined here but has not been authorized or rehearsed on the live path"; `20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:81-85` (pre/post recovery points, rollback not needed, not performed) |
| Master Plan | `verification/MASTER_PLAN.md:296-305` — code: `git revert`, no history rewriting; production data: restore from pre-migration backup, confidence recorded as Low |

## 1. Layers that can need rolling back

| Layer | What changes in an upgrade | Rolled back by | Rolled back automatically by the other layer? |
|---|---|---|---|
| L1 Code | `app/`, `tools/`, launchers, templates, `version.txt` | §2 | **No** |
| L2 Schema | tables / columns / constraints changed by boot-time migrations (`app/__init__.py:486` → `_run_pending_migrations`, `:739`), recorded in `schema_migrations` | §3 (data restore) only — the inline registry has **no down-migrations** (`_run_pending_migrations` only applies versions absent from `schema_migrations`, `:739-760`) | **No** — rolling code back leaves the schema migrated |
| L3 Data | rows written by the migration, by the first start (scheduler jobs) and by operation after go-live | §3 | No |
| L4 Configuration | `.env`, `Settings` rows (e.g. `night_audit_enabled`), firewall rule, scheduled tasks | §4 | No |
| L5 Artifacts | backups produced after the upgrade; application backup purge (30 days, `app/backup_manager.py:330`) | retention (§5) | — |

## 2. Code rollback (L1) — no history rewrite

| Option | Mechanism | Notes |
|---|---|---|
| CR-A | In the install folder: `git checkout --detach <previous tag/commit>` | No history change; `main` stays where it is; the folder is then on a detached HEAD, which the written procedure must record. Precedent upgrade used `git merge --ff-only` (`ADR011_PRODUCTION_APPLICATION_REPORT.md:31`) |
| CR-B | `git revert <release commits>` on a branch, reviewed, then fast-forward the install folder | Forward commits restore previous behaviour; matches `MASTER_PLAN.md:300`. Push requires its own authorization |
| CR-C | Signed-zip install (if GD-D5 selects the updater): re-apply the previous release's signed package | `update.bat` / the updater **only write** files from the zip (`update.bat:101-160`); files added by the newer release are **not removed**. The previous package must be retained and its hash recorded. Rehearse before relying on it |
| Forbidden | `git reset --hard` on a shared branch, force-push, rebase of published history | History rewrite (`MASTER_PLAN.md:300`; FD-018 append-only, `FOUNDER_DECISIONS.md:826-830`) |

## 3. Data rollback (L2 + L3)

| Step | Action | Prerequisite | Verification |
|---|---|---|---|
| DR-1 | Stop the application; confirm no listener on the install's port and no python process holding the DB | decision RB-DP* | no `-wal`/`-journal` file; process list |
| DR-2 | Record the current (post-upgrade) DB: SHA-256, size, `schema_migrations`, per-table digests; take a `tools/backup_db.py` backup of it (it is evidence of what is being rolled back and must not be lost — FD-008 forbids destructive loss of audit history, `FOUNDER_DECISIONS.md:561`) | DR-1 | manifest BACKUP VERIFIED |
| DR-3 | Restore the **pre-update** backup with `tools/restore_db.py` into an isolated path | pre-update backup exists, verified, restore-rehearsed at upgrade time (FD-P2-04 conditions 1–7, 9, 10 minimum, `FOUNDER_DECISIONS.md:1163`) | exit 0; manifest hash = backup-time hash |
| DR-4 | **PD-004 act:** move the current `instance/pms.db` aside (retain, never delete) and copy the restored file into `instance/pms.db` | explicit Founder authorization naming this replacement (GD-D11) | SHA-256 of placed file = restored file; body identical beyond header to the pre-update backup |
| DR-5 | Return code to the previous tag (§2) **before** any start | DR-4 | `git rev-parse HEAD` = previous tag |
| DR-6 | Controlled start at previous code (precedent `first_start.py`) | DR-5 | no pending migration; `schema_migrations` = pre-update list; jobs; `night_audit_job` absent; DB URI = `instance/pms.db` |
| DR-7 | Smoke (precedent `smoke.py`) | DR-6 | `/api/health` 200; `/auth/login` 200; `/dashboard` 302 |
| DR-8 | Same verification as after the upgrade: `inv-run` (declared set only), `gm-verify`, `replay-verify`, per-table digests = pre-update state | DR-7 | per GD-D9 |
| DR-9 | Post-rollback backup + restore rehearsal = the new recovery point | DR-8 | BACKUP VERIFIED; restore PASS |

**Order matters.** Data must be restored and code returned before the next start. If the code is returned without the data restore, the old code runs on the new schema (trap T1). If the data is restored but the new code is still checked out, the next start re-applies the release migrations to the restored file (the registry runs at every `create_app()`, FD-007 state note `FOUNDER_DECISIONS.md:543-546`; also inside `update.bat`'s backup and migration steps, which call `create_app()`, `update.bat:85-90, 172-176`).

## 4. Configuration rollback (L4)

- `.env`: keep a copy of the pre-update `.env` in custody (never in evidence). Restore it if the release changed keys.
- `Settings`: restored with the data (DR-4). Confirm `night_audit_enabled=false` after rollback (FD-P2-05, `FOUNDER_DECISIONS.md:1175`).
- Firewall rule `SukoonPMS` and any Windows scheduled task: record before the upgrade; compare after rollback.

## 5. Retention of rollback artifacts

- The pre-update backup must be exempt from purge (FD-P2-04 condition 12; RC-4 `PRODUCTION_READINESS_INVENTORY.md:52`). Application backups in `backups/` are purged after 30 days (`app/backup_manager.py:228, 330`); `tools/backup_db.py` writes to `<parent>/db-backups/` outside the application's purge (`tools/backup_db.py:49-52`).
- Retain the previous release package / tag and its hash (CR-C).

## 6. Traps

| Id | Trap | Evidence | Status |
|---|---|---|---|
| T1 | **Rolling code back does not roll back an applied migration.** No down-migrations exist; `schema_migrations` keeps the version; old code then runs on the new schema | `app/__init__.py:739-760`; FD-007 state note `FOUNDER_DECISIONS.md:543-548` | by code reading |
| T1a | Concrete instance (10.0.0): code before `3ffeba5` resolves the system actor to `0` (`git show 16c4ca8:app/services.py`, `resolve_audit_actor` at `:191-207`, `return 0`); the migrated `audit_logs` carries `CHECK (staff_user_id IS NULL OR staff_user_id > 0)` (`app/__init__.py:632`). Old code on the migrated schema would therefore have its system-actor audit writes rejected; under strict coupling the coupled financial operation fails closed. Human rows still satisfy the schema (`actor_kind DEFAULT 'HUMAN'`, `:625`) | code reading only | NOT VERIFIED at runtime |
| T1b | Today's "previous tag" for production is the running `c703150`, which already contains 10.0.0, so T1a does not arise for a release that adds no migration. Any release that adds a migration (e.g. a `backup_logs` integrity column for G8 — FD-005 state note `FOUNDER_DECISIONS.md:491-496`; Phase 3 changes) re-creates T1 and needs its own old-code-on-new-schema rehearsal | — | OPEN |
| T2 | A data restore discards every row written after the backup — including real financial rows and audit rows written after go-live. That is a loss of audit history (FD-008) and of real transactions unless re-entered | FD-008 `FOUNDER_DECISIONS.md:561` | decision GD-D11 |
| T3 | Starting the application at all (including `update.bat` backup/migration steps and its health check, `update.bat:85-90, 172-176, 209-235`) runs the scheduler: `notification_queue_flush` mutates queue rows within 5 minutes | `20260930_135930_adr011_live_human_provenance/REPORT.md:50-55` | evidenced on production |
| T4 | `update.bat` continues after a failed pre-update backup ("Continuing anyway", `update.bat:95, 98`), so a rollback point may not exist | code reading | OPEN |
| T5 | The application's own backup is `shutil.copy2` of the live file, encrypted, unverified, purged at 30 days (`app/backup_manager.py:206-228`); it has never been restored (G8 FAIL, `CERTIFICATION_GATES.md:38`). Use `tools/backup_db.py` artifacts as the rollback point until G8 passes | RC-1/RC-3 `PRODUCTION_READINESS_INVENTORY.md:49, 51` | OPEN |
| T6 | Encrypted backups need the production key material (`app/backup_manager.py:50`); losing it loses every `.enc` backup | RC-6 `PRODUCTION_READINESS_INVENTORY.md:54` | OPEN |
| T7 | A zip-based code rollback (CR-C) leaves files added by the newer release in place | `update.bat:101-160` | OPEN |
| T8 | A rehearsal on the production host with the production port would let `stop.bat`/`update.bat` kill the production server (`stop.bat:18-20`, `update.bat:63-73`) | code reading | mitigated by E6 in the plan |

## 7. Decision points

| Id | When | Question | Who decides | Default if no decision recorded |
|---|---|---|---|---|
| RB-DP1 | Before the upgrade, after pre-checks | Go / no-go: anchor hash matches, backup verified, restore rehearsed, pre-state PVF recorded | Founder (directive) | no-go |
| RB-DP2 | Boot refuses / migration error | Restore (DR) or hold stopped for diagnosis. Precedent: 10.0.0 rolled back atomically on validation failure or kill (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:107-108`); other migrations not proven | Founder | hold stopped; no retry |
| RB-DP3 | Smoke fails | Restore vs diagnose | Founder | hold stopped |
| RB-DP4 | Post-upgrade verification shows undeclared difference (digests, `inv-run`, `gm-verify`) before any operator use | Restore vs accept with a recorded ruling | Founder | hold stopped |
| RB-DP5 | Defect found **after** operation resumed (real rows written) | Forward fix, or restore plus re-entry of post-upgrade transactions (T2) | Founder | no restore without ruling (GD-D11) |
| RB-DP6 | The rollback itself fails at DR-3…DR-8 | Escalate; production stays stopped; the retained post-upgrade DB (DR-2) and pre-update backup remain | Founder | stopped |

## 8. What the G11 rehearsal must show for rollback

1. DR-1…DR-9 executed on the rehearsal copy after the upgrade (Phase H of the plan), with the copy's own "instance" replaced only inside E2.
2. Old-code-on-new-schema behaviour for every migration in the release (T1/T1b), observed and recorded — not assumed.
3. A rollback after N-day operation (T2) — what is lost, measured as row counts per table.
4. G10 after rollback equal to the pre-update G10 result.
