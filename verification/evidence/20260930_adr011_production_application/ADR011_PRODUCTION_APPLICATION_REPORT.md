# ADR-011 PRODUCTION APPLICATION REPORT

**Final status: APPLIED and VERIFIED.** Migration 10.0.0 was applied to production and verified; nothing was rolled back or stopped.

The one item this work could not verify: live confirmation of a real human action on production. It deliberately waits for the Founder's own next login (§6).

| | |
|---|---|
| Recorded | 2026-09-30, machine `DESKTOP-G2PDVG1`, by Claude (Claude Code session) |
| Authority | Founder authorization in session, 2026-09-30: "controlled application of ADR-011 migration 10.0.0 to production, subject to PD-004/PD-005 controls". FOUNDER_DECISIONS.md Round 5 (ADR011-SA). |
| Code | `main` fast-forwarded `16c4ca8` → `e7086da`; application code identical to the tested `3ffeba5` (0-line diff of `app/` and `tools/`) |
| Production | `instance/pms.db`: `51dd83b7…30bc2` → `e67f963b87e4004cee4f5f4abd6b97a07e07763faf328256397d8246e49ec569`; 733,184 B before and after; changed once, at 13:24:35 |
| Machine-readable | `RESULT.json` (built by `build_result.py` from the files in this pack) |

## 1. Pre-application verification (all PASS; no discrepancy found)

| Check | Result |
|---|---|
| `main` = `origin/main` = `16c4ca8`, working tree clean | PASS |
| Branch `adr011-system-actor` `e7086da` = origin; fast-forward of `main`; `app/`+`tools/` identical to tested `3ffeba5` | PASS |
| Pre-production pack (`20260930_adr011_preprod_gate`): 77/77 PASS, production digest `51dd83b7…` | PASS — production still `51dd83b7…`, mtime 2026-08-31 |
| Application not running; no restart flag; `night_audit_enabled=false`; latest migration `9.0.0` | PASS |
| **Fresh backup** `db-backups/pms_20260930_132300_adr011-apply-pre.db` (`tools/backup_db.py`) | PASS — integrity ok, 53 tables / 299 rows match; SHA-256 `99505a47…` **identical to the pre-production gate backup** (independent proof that production had not changed) |
| Restore rehearsal `RR-20260930-ADR011-APPLY` (`tools/restore_db.py`, isolated path) | PASS — 15/15 checks, 0 failures |
| Pre-mutation state: per-table digests of all 53 tables, audit digest `1cf41807…` | recorded (`prod_pre_state.json`) |
| Pre-mutation invariants / Golden Master (from a `16c4ca8` worktree) | inv-run: only the declared D11 exception (INV-A02/A03); gm-verify 158/158, 0 differences |
| Execution-time migration rehearsal on the fresh restore (branch code) | PASS — 21/21 (`preprod_apply_rehearsal.json`) |

## 2. Controlled application

1. `git merge --ff-only adr011-system-actor` in the live folder. No merge commit, no history rewrite.
2. **First application start** (`first_start.py`). The application's own `create_app()` ran with the live folder's production `.env` unmodified (`DATABASE_URL` not overridden; resolved to `instance/pms.db`, mode `production`). Log line:

   `Migration 10.0.0 applied: ADR011-SA … (23 rows carried over, digest 1cf41807b7639e55)`

   Started normally. `night_audit_job` **not registered**. Standing jobs registered as before: `daily_backup_job`, `log_pruning_job`, `notification_queue_flush`, `predictive_maintenance_job`. The scheduler was stopped at the end of the controlled start. No web server was left running.

## 3. Post-migration verification (read-only)

| Check | Result |
|---|---|
| Tables changed | **only** `audit_logs` (shape) and `schema_migrations` (57 → 58 rows, `10.0.0` added) — as rehearsed |
| Historical audit rows | **23**; digest of the nine original columns **identical** (`1cf41807…`) |
| Actor model | all 23 rows `HUMAN`, user 1; no mechanism/role/shift reconstructed; **0 rows with user 0**; users: `(1, Admin, active)` only |
| Schema and constraints | `staff_user_id` nullable; `actor_kind` NOT NULL, `actor_mechanism`, `actor_role`, `actor_shift_id`; CHECKs `ck_audit_actor_kind`, `ck_audit_actor_identity`, `ck_audit_actor_not_zero`; FKs to `users` and `shifts`; `idx_audit_entity`; no leftover rebuild table |
| Integrity / FK | `integrity_check` ok; whole-database `foreign_key_check` (FK on) empty |
| Financial tables | unchanged, digest for digest: payments, extra_charges, folios, tax_lines, credit_vouchers, credit_voucher_redemptions, night_audit_logs, reservations, credit_notes, cico_charge_logs, shifts, users, guests, business_date |
| Scheduler | `night_audit_enabled=false`; `night_audit_job` not registered (first start and smoke) |

## 4. Smoke verification (`smoke.py`)

| Check | Result |
|---|---|
| Second application start | normal; migration **not** re-applied (no-op) |
| `GET /api/health` | 200 `{"online": true, "status": "ok", "version": "2.2.18"}` |
| `GET /auth/login` | 200 |
| `GET /dashboard` unauthenticated | 302 → `/auth/login` (authorization intact) |
| Production digest before/after smoke | identical (`e67f963b…`) — the smoke wrote nothing |

## 5. Post-mutation state (FD-007)

| Check | Result |
|---|---|
| Post-migration backup `pms_20260930_132529_adr011-apply-post.db` | BACKUP VERIFIED, SHA-256 `12ba7b7e…`, 53 tables / 300 rows. This is the new recovery point |
| Its restore rehearsal `RR-20260930-ADR011-POST` | PASS, 15/15 |
| inv-run on migrated production (new `main` worktree) | **object-for-object identical to pre-mutation**; 0 writes |
| gm-verify | **PASS 158/158, 0 differences** |
| replay-verify | identical to baseline (the two governed Q06-H2 deltas only) — PRE-EXISTING |
| cross-implementation | identical to baseline — PRE-EXISTING |

## 6. Human provenance

Performing a logged-in action on live production would write an audit row attributed to the Founder's account for an action the Founder did not take. That is the impersonation ADR011-SA forbids, so it was **not done**.

| Check | Result |
|---|---|
| Real user 1, logged-in request, on a **copy** of the migrated production (from the verified post-migration backup) | row = `HUMAN`, staff user 1, role `Admin`, mechanism `web`, IP recorded, shift empty (user 1 has no open shift — correct) |
| Identity suite on a copy of migrated production (`preprod_apply_post_ident.json`) | 34/34 identity gates PASS: scheduler/no-show/webhook SYSTEM rows; operator HUMAN rows with role and shift; negatives refused with rollback; provenance 8/8. The 35th gate (P-00) compares production against the **pre-migration** anchor and fails only because production is now legitimately `e67f963b…`; before == after within the run |
| Live production confirmation | **NOT VERIFIED — pending.** The Founder's next login writes a login audit row; it should read `HUMAN`, user 1, role `Admin`, mechanism `web`. It can be checked read-only afterwards |

## 7. Recovery

- **Pre-migration recovery point:** `db-backups/pms_20260930_132300_adr011-apply-pre.db` (`99505a47…`), restore-rehearsed.
- **Post-migration recovery point:** `…_132529_adr011-apply-post.db` (`12ba7b7e…`), restore-rehearsed.
- **Rollback:** not needed and not performed. An in-place restore into `instance/` remains a separately authorized PD-004 act (`restore_db.py` refuses it by design).
- **Live-data copies on disk:** `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\adr011_apply\` and `adr011_preprod\`, both outside the repository. Kept (evidence rule); disposal is the Founder's call.

## 8. Classification

| Item | Status |
|---|---|
| Migration 10.0.0 on production | **APPLIED** |
| Migration completion, 23 audit rows, schema/constraints, financial tables unchanged, scheduler disabled, normal start | **VERIFIED** |
| Smoke, identity/digest comparison, actor model, no user 0, no unexpected financial mutation | **VERIFIED** |
| Authenticated human action → HUMAN provenance | **VERIFIED on a copy**; live confirmation **NOT VERIFIED** (awaits the Founder's login) |
| Rollback | not required — nothing **ROLLED BACK**; nothing **STOPPED**; nothing **BLOCKED** |
| G3 / G5 / G11 / G12 | not changed by this work: OPEN / OPEN / BLOCKED / BLOCKED |

**FinalGrid is not 100% production-ready.** ADR-011 is applied. Still open:
- G3: K-7 business-date dating; SR-1/SR-2.
- G5: ADR-011 formal adoption and the remaining provenance envelope.
- G11: deployment rehearsal and procedure.
- G12: certification.
- PostgreSQL verification.
- The recorded carry-overs: webhook audit gaps, guest data in git history, harness notification side effects, in-place PVF runs rewriting `instance/alert_memory.json`, and B-4.
