# ADR-011 PRE-PRODUCTION GATE REPORT

| | |
|---|---|
| Recorded | 2026-09-30, machine `DESKTOP-G2PDVG1`, by Claude (Claude Code session) under the Founder's "ADR-011 Production Gate Directive" |
| Scope | Every safe pre-production activity for merging `adr011-system-actor` and the first production start. **Nothing was merged, migrated, started or configured in production.** |
| Machine-readable | `RESULT.json` (built by `build_result.py` from the files in this pack) |
| Pack | `verification/evidence/20260930_adr011_preprod_gate/` on branch `adr011-system-actor` |

Classification vocabulary: PASS · FAIL · BLOCKED · NOT VERIFIED · PRE-EXISTING · FOUNDER DECISION REQUIRED.

## 1. Summary

The ADR-011 migration and system-actor model were rehearsed end to end on a **verified restore of the current production database**:

- **backup → verify → restore → verify:** PASS.
- **Migration 10.0.0:** carries all 23 audit rows over byte-identical in their original columns and touches no other table. Unchanged `main` changes nothing on boot; the branch changes only `audit_logs` (shape) and `schema_migrations`.
- **Failure behaviour:** idempotent. It refuses cleanly on invalid history or failed validation, and rolls back to the exact pre-migration database when the process is **killed mid-migration**.
- **Negatives:** every negative case refuses, with the financial change rolled back and the audit table unchanged.
- **Regression:** every established suite gives the same result on the branch as on unchanged `main`, including Golden Master 158/158 on both.
- **PostgreSQL:** BLOCKED on authorizations.

The remaining steps are Founder decisions (§6–§7).

## 2. Items

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Current `main` | **PASS** — `16c4ca8b6bf8…` = `origin/main`, clean, sync `0 0` | `RESULT.json.main_sha`; `git rev-list --left-right --count origin/main...main` = `0 0` at start and end |
| 2 | ADR-011 branch | **PASS** — `adr011-system-actor` `0450c203851f…` = origin, sync `0 0`; app code identical to `3ffeba5` | `RESULT.json.branch_sha_tested` |
| 3 | Migration identity | **PASS** — `10.0.0`, code commit `3ffeba5`, `app/__init__.py` blob `1eeaf5482447…`, migration source SHA-256 `e38cb0556b09…` | `RESULT.json.migration` |
| 4 | Production DB identity | **PASS** — `instance/pms.db`, 733,184 B, mtime 2026-08-31 11:53:14, SQLite page 4096 × 179, `journal_mode=delete`, 53 tables / 299 rows, 23 audit rows (all user 1), latest migration `9.0.0`, 10.0.0 absent | `preprod_final.json` B-00…B-04 |
| 5 | Production DB digest | **PASS** — SHA-256 `51dd83b7…30bc2` before and after every step (backup, restore, 77-gate harness, both regression batteries) | every result file |
| 6 | Backup identity | **PASS** — `db-backups/pms_20260930_111550_adr011-preprod.db`, SHA-256 `99505a475fec…`, via `tools/backup_db.py` (source `mode=ro`, backup API, outside the repo) | `restore/backup_manifest.json` |
| 7 | Backup verification | **PASS** — integrity ok, row counts match across 53 tables, production unchanged during backup | same |
| 8 | Restore rehearsal | **PASS** — `RR-20260930-ADR011`, `tools/restore_db.py` into an isolated folder outside the repo; 16/16 checks (manifest hash, integrity, FK check, schema SQL equal, row counts, content digests of every table, body identical beyond header). FD-P2-04: conditions 1–4, 6, 7, 9, 10, 12 **PASS**; 8 **PASS** (inv-run on the restored file object-for-object identical to production; gm-verify 158/158, 0 differences); 5 **PASS** for source-equality, **NOT VERIFIED** for "release-tag fingerprint" (no release tag exists); 11 (encrypted off-box restore) **NOT VERIFIED** — not part of the PD-005 minimum (1–7, 9, 10) | `restore/restore_manifest.json`, `restored_pvf/`, `preprod_final.json` B-01…B-03 |
| 9 | Migration rehearsal | **PASS** — on copies of the restored file: boot migrates; recorded; repeat boots 2 and 3 change nothing; scheduler job not registered | D-01…D-03, D-JOB |
| 10 | Audit preservation | **PASS** — 23 rows; digest of the nine original columns identical (`1cf41807b763…`); all rows HUMAN, user 1; role/shift/mechanism not reconstructed; no row names user 0 | D-04…D-10 |
| 10b | Financial data preservation | **PASS** — payments, extra charges, folios, tax lines, vouchers, redemptions, night-audit logs, reservations, credit notes, CICO logs, users, shifts identical to the restored source after migration; every non-audit table identical to a boot of unchanged `main` | D-12a…D-12c |
| 11 | FK enforcement | **PASS** (SQLite with `PRAGMA foreign_keys=ON` on copies) — `foreign_key_check` empty after migration; scheduled night audit, automated no-show and webhook complete under FK enforcement as SYSTEM rows; invalid user rejected by FK and rolled back. Production keeps FK enforcement OFF (ADR-005 not enabled; not changed) | D-11b, S1/S2/S3-GREEN-FK, E-01 |
| 12 | ADR-011 identity and negatives | **PASS** — 77/77 gates. Identity: scheduler / automated no-show / webhook = SYSTEM, no user, mechanism; operator = HUMAN, user, role `Admin`, open shift, `web`; provenance 8/8 from the row. Negatives: invalid user, user 0, HUMAN without user, SYSTEM with user, SYSTEM without mechanism (SQL and ORM), unknown actor, failed audit write F1/F2 — each refused, financial change rolled back, audit table unchanged. Migration negatives: injected validation failure, invalid history (user 0 / dangling / mixed) — boot refused, database unchanged; **process killed after `DROP TABLE` and after `RENAME`** — hot journal rolled back to the exact pre-migration database, next start migrates cleanly | `preprod_final.json` |
| 13 | Regression (branch vs unchanged `main`, both from worktrees with the same environment) | **PASS** — identical on every suite (table below) | `regression_branch/`, `regression_main/` |
| 14 | PostgreSQL | **BLOCKED** — see §4 | `postgresql/`, `RESULT.json.postgresql` |
| 15 | G3 blockers | **OPEN** — K-7 business-date dating at all financial writers (Phase 3, not authorized); SR-1 / SR-2 invariant refinement (FD-P2-06 directive not issued). CF-10, CF-11, Q06 are done | CERTIFICATION_GATES.md G3 |
| 16 | G11 blockers | **BLOCKED** — deployment rehearsal never performed; written install/upgrade/rollback/day-one procedure absent; prerequisite gates G3, G5, G6, G8, G9 not passed | CERTIFICATION_GATES.md G11 |
| 17 | G12 blockers | **BLOCKED** — requires G1–G11 as required and a Founder certification entry; not reachable | CERTIFICATION_GATES.md G12 |
| 18 | Governance questions | **FOUNDER DECISION REQUIRED** — §6 | — |
| 19 | Founder action | **FOUNDER DECISION REQUIRED** — §7 | — |
| 20 | Is the production merge safe to authorize? | **FOUNDER DECISION REQUIRED** — §8 | — |

### Regression detail (item 13)

| Suite | Branch `0450c20` | Baseline `main` `16c4ca8` | Classification |
|---|---|---|---|
| CF-10 / CF-11 harness | 242/242 (w14 with its automated call declared) | 242/242 | PASS |
| Phase 1 writers A / B / C / D | 89 / 48 / 15 / 46 (A, D declared) | 89 / 48 / 15 / 46 | PASS |
| Phase 1 execution | 44/44 (declared) | 44/44 | PASS |
| Phase 2a authorization | 29/29 | 29/29 | PASS |
| Q06 fix | 15 / 0 | 15 / 0 | PASS |
| Retention | 18/18 | 18/18 | PASS |
| W-20 runtime | 23/23 | 23/23 | PASS |
| Restore tool | 19 OK | 19 OK | PASS |
| Golden Master | **PASS 158/158, 0 differences** | PASS 158/158, 0 differences | PASS |
| Replay | FAIL — the two Q06-H2 forward-fix deltas | identical | PRE-EXISTING (governed, Q06-H1/H3) |
| inv-run | FAIL — INV-A02/A03 on the eight D11 objects | record-identical | PRE-EXISTING (FD-P2-03 declared exception) |
| Cross-implementation | FAIL — 15 AGREED / 4 DIVERGED / 1 SINGLE_SOURCE / 2 VACUOUS | record-identical | PRE-EXISTING |
| Console logging errors (`UnicodeEncodeError` on "→" in notification warnings) | same count per comparable log (e.g. 3 vs 3 in set A) | present | PRE-EXISTING |

**Undeclared unattended calls: refused by design.** Phase 1 writers sets A and D, Phase 1 execution and CF-10 case W14-E1 stand in for the scheduler by calling the night audit or no-show code with no operator. Run undeclared on the branch, each stops at `AuditActorError` and nothing else (`regression_branch/*.log`). This is the ADR011-SA "unknown actor ⇒ refuse" behaviour. The suites were not edited: they were re-run with that call declared as a system action, giving the results above. The same four suites pass undeclared on `main`, as before.

These baseline numbers match the committed in-place packs of `3efdd2b`. Replay, inv-run and cross-implementation are record-identical.

## 3. Isolation and environment

- **Where code ran.** Application code ran only from git worktrees (`C:\wt_adr011` for the branch, `C:\wt_main` for `main`). Every boot was a separate process against a copy of the restored file or a PVF working copy. The live folder never had the branch checked out, and the application was never started there (confirmed not running; no startup entry; no restart flag).
- **Worktree environment.** Each worktree carried copies of two app-root files: `instance/alert_memory.json` and the one `backups/backup_*.enc` file that the `/backup/` surface lists. That is why Golden Master is 158/158 on both. The earlier 9 "environmental" differences came from their absence.
- **Pre-existing side effect.** Any PVF run started *in place* in the main folder (gm-verify, replay, inv-run, run, ds-run) boots the application from the live folder and rewrites the live `instance/alert_memory.json`. This affected earlier sessions' runs and my runs of 2026-09-30 before 10:52 (last write 10:51:55; size unchanged). All runs in this directive used worktrees, and the live file hash `7f79f337…` was unchanged throughout.
- **Isolated folder.** Backup artifact: `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\db-backups\` (retained). Restored and scenario databases: `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\adr011_preprod\`. Both are outside the repository. They hold copies of live data and were **not deleted** (evidence rule); their disposal is for the Founder.
- **Guest data.** Logs in this pack were scanned against every production guest phone, email and name; matches are replaced with `[REDACTED-PRODUCTION-GUEST-FIELD]`.

## 4. PostgreSQL (item 14) — BLOCKED

| Fact | Value |
|---|---|
| Services | `postgresql-x64-13` (13.23) and `postgresql-x64-18` (18.4), auto-start, running as NetworkService |
| Listening | `0.0.0.0:5432` and `0.0.0.0:5433` — **all interfaces** (observation, outside this scope) |
| Databases | not listed — requires a login |
| Credentials | none provided; none in the environment; no `pgpass.conf` |
| Python driver | none in the application venv (`psycopg`, `psycopg2`, `pg8000`, `asyncpg` absent); `requirements.txt` lists `psycopg[binary]` as optional |
| Migration compatibility | offline compile only: `postgresql/static_ddl_postgresql.sql` (fresh-install `CREATE TABLE` from the models, and the eight `ALTER` statements of 10.0.0) — syntactically well-formed; **never executed** |

**Required to proceed:**

1. The Founder designates which PostgreSQL server may be used for testing. Their ownership and contents are unknown to this work.
2. A disposable database and credentials.
3. Authorization to install `psycopg[binary]` into a **separate verification venv** (not the application venv).

Then the same 77-gate harness can be run with `DATABASE_URL=postgresql+psycopg://…`.

## 5. What the migration does at first production start (for the decision)

| Step | Behaviour | Evidence |
|---|---|---|
| Trigger | The inline registry runs at **every application start** (`create_app` → `_run_pending_migrations`, and after an updater restart). No manual step exists | FD-007 state note; `app/__init__.py` |
| Refusal | If any existing audit row names no real user, boot is refused and the database is left unchanged. On production today: 0 such rows | E-11 |
| Execution | One transaction: SQLite table rebuild (copy → drop → rename → index), digest compared, `10.0.0` recorded, commit | D-01…D-11 |
| Interruption | A kill at any point before commit leaves a hot journal; the next open restores the exact pre-migration database; the next start migrates | E-13 |
| Validation failure | Rolled back; boot refused (the app will not run until resolved) | E-10 |
| After | Existing operator behaviour unchanged. An unattended night audit or no-show that declares no mechanism is refused (scheduler stays off). Audit rows gain actor kind, mechanism, role and shift | D-12, identity checks |

## 6. Governance questions — FOUNDER DECISION REQUIRED

1. **Migration authority (FD-007, B-4).** FD-007 requires Founder-approved scope, **PD-004 authorization**, the PD-005 protocol, verified PD-006 recovery, pre/post snapshots and invariant states, controlled execution, retained evidence and a defined rollback path. It also records that the single schema authority (inline registry vs Alembic) is **not decided**. Merging uses the inline, unattended, boot-time registry for this migration: accept it for 10.0.0, or decide B-4 first.
2. **Where the merge happens.** This repository folder *is* the production install, with `main` checked out. Merging into `main` here, or pulling it here, places the migration so that the **next application start migrates production**. Merging only on `origin` does not reach production by itself: the updater is a manual, signed zip upload and does not pull from GitHub.
3. **Rollback path.** `tools/restore_db.py` refuses to restore into `instance/` (by design: "in-place production restore is a separately authorized PD-004 act"). The rollback path is therefore:
   1. stop the application;
   2. restore the pre-mutation backup to an isolated path with `restore_db.py`;
   3. under a PD-004 authorization, replace `instance/pms.db` with it;
   4. return the code to `16c4ca8`.

   It is defined here but has not been authorized or rehearsed on the live path.
4. **Execution-time backup.** PD-005 needs a backup at execution time. The 11:15 rehearsal artifact is valid only if production is still `51dd83b7…` at execution. A fresh `backup_db.py` run plus a `restore_db.py` rehearsal at execution time is the conservative reading.
5. **ADR-011 status.** ADR-011 is still PROPOSED FOR ADOPTION. ADR011-SA resolves its item 4; formal adoption and reconciliation of the ADR file are open. The "readings" recorded in `20260930_adr011_implementation/ADR011_DECISION.md` need confirmation:
   - an unknown actor is refused;
   - an unauthenticated request is SYSTEM `web:unauthenticated`;
   - history is carried as HUMAN;
   - role and shift are not reconstructed.
6. **Carried over, still open:**
   - classification of the webhook audit gaps;
   - the production guest phone number in git history (purge needs a force-push);
   - harnesses booting with the production `.env` and real guests;
   - PVF in-place runs writing the live `instance/alert_memory.json`.

## 7. Exact action required from the Founder

Decide **MERGE** or **DO NOT MERGE**. If MERGE, the evidence here supports issuing, in one directive:

1. a **PD-004 authorization** naming migration `10.0.0` on `instance/pms.db`, and the acceptance or replacement of the inline boot-time mechanism (question 1);
2. an **execution window** under PD-005, carried out in the live folder only within that window:
   1. `backup_db.py` and verify;
   2. `restore_db.py` rehearsal of that artifact;
   3. pre-mutation `inv-run` / `gm-verify` from a worktree;
   4. merge `adr011-system-actor` into `main` and push;
   5. controlled first start;
   6. post-mutation verification: audit digest `1cf41807…` unchanged, `10.0.0` recorded, `inv-run` and `gm-verify` equal to pre;
   7. retained evidence;
3. an **authorization of the rollback path** in question 3;
4. confirmation that the scheduler stays disabled (FD-P2-05), which the merge does not change.

## 8. Is the production merge safe to authorize?

**On the technical evidence: yes, the migration is safe to apply to a database identical to current production.** The evidence for that:
- it was rehearsed on a verified restore of that database;
- it preserves every audit row and all financial data;
- it is idempotent;
- it fails closed on invalid history and on validation failure;
- it survives a mid-migration crash;
- it introduces no regression against `main` in any established suite.

**It is not safe to merge without the preconditions in §6–§7.** Merging into `main` in this folder arms the migration for the next start, so the merge itself is the production-mutation decision. That decision is the Founder's. Nothing here closes G3, G5, G11 or G12, or makes FinalGrid production-ready as a whole. PostgreSQL remains unverified.
