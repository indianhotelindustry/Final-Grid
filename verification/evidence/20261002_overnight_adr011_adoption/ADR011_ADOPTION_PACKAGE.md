# ADR-011 ADOPTION PACKAGE — system action provenance (ADR011-SA)

| | |
|---|---|
| Recorded | 2026-10-02, overnight session FG-OVERNIGHT-01, worktree `C:/wtov`, branch `overnight-20261002` |
| Repository state read | `c9eeff0` (= `origin/main`). `git diff 3ffeba5 c9eeff0 -- app tools` is **empty**: the application code at `c9eeff0` is the code tested at `3ffeba5` and applied to production at `e7086da`. `app/__init__.py` blob `1eeaf5482447…` at both `3ffeba5` and `c9eeff0` (equals `20260930_adr011_preprod_gate/RESULT.json` → `migration.app___init___blob`) |
| Kind | **Governance documentation only.** No application code, ADR file, `FOUNDER_DECISIONS.md`, existing evidence, database or setting was changed. The application was not started and `app` was not imported. No production file and no `pms.db` was opened. |
| Purpose | Assemble what an ADR-011 adoption review needs: the final actor model, its evidence, its limitations, the ADR text deltas required by ADR011-SA, and the open governance questions |
| Companion | `ADR011_FORMAL_ADOPTION_REQUIRED.md` (this directory) — the decisions needed to adopt |

Status vocabulary used for classifications in this document: PASS · FAIL · BLOCKED · OPEN · NOT VERIFIED · NOT AUTHORIZED · NOT APPLICABLE. Words quoted from evidence packs (e.g. "APPLIED", "VERIFIED") are quoted, not re-classified.

---

## 0. Summary

| Item | Status | Source |
|---|---|---|
| ADR011-SA ruling (system actor representation) | recorded | `verification/FOUNDER_DECISIONS.md:1256-1290` |
| Implementation of ADR011-SA (code) | PASS (42/42 branch gates; 77/77 pre-production gates) | `20260930_adr011_implementation/RESULT.json`; `20260930_adr011_preprod_gate/RESULT.json` |
| Migration 10.0.0 on production | PASS ("APPLIED AND VERIFIED") | `20260930_adr011_production_application/RESULT.json` → `status` |
| Live HUMAN provenance on production | PASS | `20260930_135930_adr011_live_human_provenance/REPORT.md:8`, `:63` |
| Live SYSTEM provenance on production | NOT VERIFIED — no SYSTEM writer has run on production (scheduler disabled; 0 webhook calls) | live `RESULT.json` → `audit_counts_system_zero_null: [0,0,0]` |
| PostgreSQL execution of 10.0.0 | BLOCKED (no credentials/database/driver authorized) | `20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:81-98` |
| ADR-011 document status | **PROPOSED FOR ADOPTION** (unchanged since 2026-09-08) | `verification/adr/ADR-011-operator-accountability.md:5`; `verification/FOUNDER_DECISIONS.md:954`; `verification/adr/README.md:47` |
| ADR-011 reconciliation with ADR011-SA | OPEN — deferred by the ruling to the adoption review | `verification/FOUNDER_DECISIONS.md:1287` |
| Formal adoption of ADR-011 | **NOT AUTHORIZED** — no Founder wording adopting ADR-011 exists (§9) | search in §9 |

---

## 1. Governing decisions (verbatim, with location)

### 1.1 ADR011-SA — `verification/FOUNDER_DECISIONS.md:1269-1284`

> **Decision:**
>
> FinalGrid shall distinguish a human actor from a system actor at the audit/provenance layer. System actions shall not impersonate a human user and shall not use a fabricated users.id = 0.
>
> audit_logs shall explicitly represent the actor kind and retain sufficient provenance to distinguish:
>
> human/operator initiated action;
> system/scheduled action;
> execution mechanism;
> relevant operator role/shift where applicable.
>
> Human audit records shall continue referencing the authenticated user.
>
> System audit records shall not require a fabricated human users row merely to satisfy the audit FK.
>
> Scheduler activation remains a separate authorization and is not enabled by this decision.

Recorder's notes attached to the entry (not Founder wording): Option B selected, A and C excluded (`:1286`); "resolves ADR-011 item 4 … and the actor-kind part of the ADR-011 storage question … A system audit row need not reference `users` (its `staff_user_id` may therefore be empty) … ADR-011 is not edited by this entry; the reconciliation is applied to it at its adoption review (precedent: FD-P2-04 for ADR-006/ADR-007)" (`:1287`); scheduler unchanged (`:1288`); migration delivery and production application "not addressed by this ruling" (`:1289`); "Implementation status: not implemented" (`:1290`, true at recording).

### 1.2 Other decisions the actor model must satisfy

| Decision | Location | Relevance |
|---|---|---|
| FD-014 accountability elements | `FOUNDER_DECISIONS.md:714-735` | authenticated operator, role, operational responsibility, timestamp, business date, workstation/IP, maker/checker |
| AR-012 | `20260908_architecture_resolution_round1/RECORD.md:132` | "equivalent accountability through controlled system identity/provenance" |
| AR-013 | `RECORD.md:138` | scheduler controls; dedicated ADR (BACKLOG B-1) not yet created |
| FD-009 | `FOUNDER_DECISIONS.md:582` | no unattended financially material mutation without operator-equivalent controls |
| FD-P2-05 | `FOUNDER_DECISIONS.md:1170-1176` | manual night audit; `night_audit_enabled=false` |
| FD-P2-01 | `FOUNDER_DECISIONS.md:1127-1133` | single Admin operator model for the first release |
| FD-P2-02 | `FOUNDER_DECISIONS.md:1138-1144` | audit records must not be destructively deleted (coupled-audit-row storage depends on this) |
| FD-007 | `FOUNDER_DECISIONS.md:527-541` | production migration preconditions |

---

## 2. Final system actor model (code at `c9eeff0`)

### 2.1 Schema — columns and constraints introduced by migration 10.0.0

Migration identity: `AUDIT_ACTOR_MIGRATION = ('10.0.0', 'ADR011-SA: audit_logs actor kind / mechanism / role / shift; staff_user_id nullable for SYSTEM rows; no users.id 0')` — `app/__init__.py:608-609`.

| Column | Type / nullability | Values | Model | SQLite DDL | PostgreSQL DDL |
|---|---|---|---|---|---|
| `staff_user_id` | INTEGER, **now nullable**, FK `users(id)` | real user id (>0) on HUMAN rows; NULL on SYSTEM rows | `app/models.py:1068` | `app/__init__.py:622,633` | `app/__init__.py:642` |
| `actor_kind` (new) | VARCHAR(10) NOT NULL DEFAULT `'HUMAN'` | `HUMAN` · `SYSTEM` | `app/models.py:1071-1072` | `app/__init__.py:625` | `app/__init__.py:638` |
| `actor_mechanism` (new) | VARCHAR(64), nullable (mandatory on SYSTEM by CHECK) | see §2.3 | `app/models.py:1073` | `app/__init__.py:626` | `app/__init__.py:639` |
| `actor_role` (new) | VARCHAR(20), nullable | snapshot of `users.role` at insert, HUMAN rows only | `app/models.py:1074` | `app/__init__.py:627` | `app/__init__.py:640` |
| `actor_shift_id` (new) | INTEGER, nullable, FK `shifts(id)` | the operator's `Open` shift at insert, HUMAN rows only; NULL if none | `app/models.py:1075` | `app/__init__.py:628,634` | `app/__init__.py:641` |

| Constraint | Expression | Location |
|---|---|---|
| `ck_audit_actor_kind` | `actor_kind IN ('HUMAN','SYSTEM')` | `app/models.py:1079`; `app/__init__.py:630,643` |
| `ck_audit_actor_identity` | `(actor_kind='HUMAN' AND staff_user_id IS NOT NULL) OR (actor_kind='SYSTEM' AND staff_user_id IS NULL AND actor_mechanism IS NOT NULL)` | `app/models.py:1080-1083`; `app/__init__.py:631,644-646` |
| `ck_audit_actor_not_zero` | `staff_user_id IS NULL OR staff_user_id > 0` | `app/models.py:1084-1085`; `app/__init__.py:632,647-648` |
| Index | `idx_audit_entity (entity_type, entity_id)` (re-created after rebuild) | `app/models.py:1078`; `app/__init__.py:717-718` |

Unchanged columns: `id`, `entity_type`, `entity_id`, `action`, `before_state`, `after_state`, `ip_address`, `timestamp` (`app/__init__.py:611-612`). No business-date column was added (§6, L-9).

### 2.2 Resolution mechanism

- `app/audit_actor.py:25-28` — kinds `HUMAN`/`SYSTEM`; `AuditActor(staff_user_id, actor_kind, actor_mechanism)`.
- `app/audit_actor.py:37-50` — `system_action(mechanism)` context manager: declares that code in the block is a SYSTEM actor; a mechanism name is mandatory.
- `app/audit_actor.py:67-86` — `resolve(user_id, mechanism)`, in order: explicit `user_id` → HUMAN (mechanism `web` in a request, else `service`); else logged-in operator → HUMAN `web`; else declared mechanism → SYSTEM; else in a request → SYSTEM `web:unauthenticated`; else **raise `AuditActorError`** (no row is written). `user_id` 0 is treated as no user (`:70-73`).
- `app/models.py:1089-1121` — `before_insert` listener on `AuditLog`: a SYSTEM row has its user forced to NULL and must carry a mechanism; any other row is resolved through `resolve()`; HUMAN rows get `actor_role` from `users.role` and `actor_shift_id` from the user's most recent `Open` shift, unless already set.
- `app/services.py:191-199` — `resolve_audit_actor()` delegates to `resolve()`.
- `app/services.py:202-260` — `audited_financial_write()` (strict financial coupling): an unresolvable actor becomes `AuditCouplingError` (`:225-230`) and the caller's financial transaction rolls back; kind and mechanism are written explicitly (`:246-248`).

### 2.3 Writers — which emit HUMAN and which emit SYSTEM

| Writer | Kind | `actor_mechanism` | Location |
|---|---|---|---|
| Any authenticated web request writing an audit row (all `routes._write_audit` callers, `folio._audited`, `shift_service`, `payment_void_service`, `cico_service`, manual night audit `POST /night-audit/run`, manual no-show, etc.) | HUMAN — the logged-in user, role and open shift snapshotted | `web` | resolution `app/audit_actor.py:73-78`; `routes._write_audit` `app/routes.py:312-330` |
| Service call with an explicit user id outside a request | HUMAN | `service` | `app/audit_actor.py:73-75` |
| Login success / logout | HUMAN — the account | `web` | `app/auth.py:87-93`, `:135-141` |
| Login failure for an existing account | HUMAN — the **target** account (see §6, L-11) | `web` | `app/auth.py:110-117` |
| Scheduled night audit (`night_audit_job` → `scheduled_night_audit`) — room rent, no-show fee, `noshow_posted` | SYSTEM, no user | `scheduler:night_audit_job` | `app/services.py:535-543`; job registration `:562-570`, `:604-612` (only when `night_audit_enabled` is true) |
| Automated no-show (`noshow_service`, no operator) | SYSTEM inside a declared mechanism; otherwise refused | declared mechanism | `app/noshow_service.py:188-207` |
| CICO automatic charge audit row | same actor as the strict row | resolved | `app/cico_service.py:396-412` |
| Webhook `modify_booking` (`webhook._write_audit`) | SYSTEM, no user | `webhook` | `app/webhook.py:348-370` (called at `:468`) |
| Webhook `new_booking` / `cancel_booking` | **no audit row** (unchanged; §6, L-4) | — | handlers `app/webhook.py:148`, `:298` |
| Unauthenticated web request that audits | SYSTEM, no user | `web:unauthenticated` | `app/audit_actor.py:82-83`; `app/routes.py:317-326` |
| Group-stay room-link audit without operator | listener: declared mechanism → SYSTEM, else refused | — | `app/services_group_stay.py:58-74`; `app/models.py:624-632` |
| Dev seed reset without an `admin` account | SYSTEM, no user | `dev_seed` | `app/dev_seed.py:548-556` |
| Unattended call that declares no mechanism (no user, no request) | **refused** (`AuditActorError`; strict financial writers roll back) | — | `app/audit_actor.py:84-86`; `app/services.py:225-230`, `:270-273` |

Other scheduler jobs write no `AuditLog`: `daily_backup_job`, `notification_queue_flush`, `log_pruning_job`, `predictive_maintenance_job` (`20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:47`). The four former `0` conventions named at `FOUNDER_DECISIONS.md:1287` are no longer present at `c9eeff0`: `services.resolve_audit_actor` (`app/services.py:191-199`), `webhook._write_audit` (`app/webhook.py:359-361`), `routes._write_audit` (`app/routes.py:317-319`), `services_group_stay._resolve_actor` (`app/services_group_stay.py:66-74`).

### 2.4 Mapping to the ruling

| ADR011-SA clause (`FOUNDER_DECISIONS.md` line) | Implemented as | Classification |
|---|---|---|
| distinguish human from system at the audit layer (`:1271`) | `actor_kind` + `ck_audit_actor_kind` | PASS |
| no impersonation of a human user (`:1271`) | SYSTEM ⇒ `staff_user_id IS NULL` (`ck_audit_actor_identity`) | PASS |
| no fabricated `users.id = 0` (`:1271`) | `ck_audit_actor_not_zero`; 0 never written; production `users` = one row (id 1) | PASS |
| explicit actor kind (`:1273`) | `actor_kind` NOT NULL | PASS |
| human/operator vs system/scheduled (`:1275-1276`) | `actor_kind` | PASS |
| execution mechanism (`:1277`) | `actor_mechanism` (mandatory on SYSTEM) | PASS (on HUMAN rows created after 10.0.0; legacy rows NULL — L-3) |
| operator role/shift where applicable (`:1278`) | `actor_role`, `actor_shift_id` on HUMAN rows | PASS (snapshot at insert; legacy rows NULL — L-3) |
| human rows reference the authenticated user (`:1280`) | HUMAN ⇒ `staff_user_id` NOT NULL FK `users` | PASS — with the semantic note L-11 (failed login) |
| no fabricated users row for the FK (`:1282`) | `staff_user_id` nullable; no `users` row created | PASS |
| scheduler not enabled (`:1284`) | `night_audit_enabled=false`; `night_audit_job` not registered at first start | PASS (production application `RESULT.json` → `first_start.night_audit_job_registered: false`) |

---

## 3. Provenance model (what a row now answers by itself)

From `20260930_adr011_implementation/ADR011_IMPLEMENTATION.md:91` and pre-production gate item 12: for a scheduler room-rent row and a manual one, the row alone answers what, when (technical UTC `timestamp`), which entity, which amount (`after_state`), why (`flow`, `night_audit_log_id`), **human or system** (`actor_kind`), **execution path** (`scheduler:night_audit_job` vs `web`) and business date (inside `after_state.charge_date`) — 8/8. Before 10.0.0 the human/system and execution-path questions were not answerable (`ADR011_DECISION_REQUIRED.md:69-70`).

Layers of the ADR-011 *Proposed architecture* item 1 envelope (`ADR-011-operator-accountability.md:35`) after ADR011-SA:

| Envelope element | Where it lives now | Status |
|---|---|---|
| `actor_user_id` | `audit_logs.staff_user_id` (HUMAN) | PASS |
| system actor identity | `audit_logs.actor_kind` = SYSTEM + `actor_mechanism` | PASS (live SYSTEM rows: NOT VERIFIED — L-1) |
| `actor_role` snapshot | `audit_logs.actor_role` | PASS |
| `shift_id` | `audit_logs.actor_shift_id` (not mandatory; NULL when no open shift) | PASS as recorded; "mandatory at posting" OPEN (L-8) |
| `business_date` | only inside `after_state` of writers that put it there; no column | OPEN (L-9) |
| `created_at` UTC | `audit_logs.timestamp` | PASS (pre-existing) |
| `ip_address` / workstation | `audit_logs.ip_address`; no workstation identifier | IP PASS (pre-existing); workstation OPEN (L-10) |
| `checker_user_id` | not in `audit_logs`; maker-checker fields exist on specific tables (e.g. void approver) | OPEN (ADR-010 / B-2) |
| storage location for financial rows | coupled `audit_logs` row (option (b) of ADR-011 item 2); `payments`/`extra_charges` still have no user column | actor-kind part resolved by ADR011-SA (`FOUNDER_DECISIONS.md:1287`); remainder OPEN |
| immutability | write-once by application code; no database trigger prevents `UPDATE` of `audit_logs` | application-level only (L-12) |

---

## 4. Migration evidence (production application of 10.0.0)

All values from `20260930_adr011_production_application/RESULT.json` unless stated.

| Item | Value |
|---|---|
| Authority recorded in the pack | "Founder authorization in session 2026-09-30: controlled application of ADR-011 migration 10.0.0 to production subject to PD-004/PD-005" (`authorization`); report line 10 adds "FOUNDER_DECISIONS.md Round 5 (ADR011-SA)" |
| Git | `main_before` `16c4ca8b6bf80cbb9502d75d746073abdbfcd5cb` → `main_after_fast_forward` `e7086da05b692a7a54b155161212c9cbd4c0b068`; `git merge --ff-only adr011-system-actor`; `app_tools_diff_vs_tested_3ffeba5: 0` |
| Production DB | `sha256_before` `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` → `sha256_after` `e67f963b87e4004cee4f5f4abd6b97a07e07763faf328256397d8246e49ec569`; size 733,184 B before and after; `mtime_after` 2026-09-30 13:24:35 +0530 |
| Pre-mutation backup | `pms_20260930_132300_adr011-apply-pre.db`, SHA-256 `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd`, "BACKUP VERIFIED", `equals_preprod_gate_backup: true` |
| Pre restore rehearsal | `RR-20260930-ADR011-APPLY`, `all_checks_ok: true`, `failures: []` |
| Execution-time migration rehearsal | "21/21 PASS" |
| Pre invariants / Golden Master | `20260930_075341_inv_run_production` FAIL (INV-A02, INV-A03 — declared D11 exception); `20260930_075346_gm_verify_phase1_aa6d9e91` PASS 158/158 |
| First start log | "Migration 10.0.0 applied: ADR011-SA: … (23 rows carried over, digest 1cf41807b7639e55)"; `env_mode: production`; `night_audit_job_registered: false`; standing jobs `daily_backup_job`, `log_pruning_job`, `notification_queue_flush`, `predictive_maintenance_job` |
| Tables changed | `audit_logs`, `schema_migrations` only (`schema_migrations` 57 → 58; `schema_migrations_added: ["10.0.0"]`) |
| Audit preservation | `audit_rows: 23`; `audit_digest_equal_to_pre: true`; `audit_digest` `1cf41807b7639e55fe899b86798ce3059b3c528333b60a552004e7041f94efe7`; `actor_kinds: [["HUMAN",1,null,null,null,23]]`; `rows_actor_zero: 0` |
| Shape | `staff_user_id_nullable: true`; three CHECKs; `fks: 2`; `index: true`; `leftover_tables: []` |
| Integrity | `integrity: "ok"`; `foreign_key_check: []` |
| Financial tables | `financial_tables_unchanged` true for payments, extra_charges, folios, tax_lines, credit_vouchers, credit_voucher_redemptions, night_audit_logs, reservations, credit_notes, cico_charge_logs, shifts, users, guests, business_date |
| Smoke | `/api/health` 200 (`version 2.2.18`); `/auth/login` 200; `/dashboard` unauthenticated 302 → login; no re-application on second start |
| Post-mutation backup | `pms_20260930_132529_adr011-apply-post.db`, SHA-256 `12ba7b7eb8004b43492829b5c1f153e0010f777e0b2c146f86b423cb39c8fac6`, "BACKUP VERIFIED"; `RR-20260930-ADR011-POST` `all_checks_ok: true` |
| Post invariants | `20260930_075629_inv_run_production` FAIL, `writes: 0`, `identical_to_pre: true` |
| Post Golden Master | `20260930_075631_gm_verify_phase1_aa6d9e91` PASS 158/158, 0 differences |
| Post replay | FAIL — the two governed Q06-H2 deltas (2026-08-09, 2026-08-10 `nas.tax_snapshot.total_taxable`), pre-existing |
| Post cross-implementation | FAIL — AGREED 15 / DIVERGED 4 / SINGLE_SOURCE 1 / VACUOUS 2, pre-existing |
| Identity suite on a copy of migrated production | `34/35`, failed `P-00` only (anchor comparison to the pre-migration hash; explained in the pack) |
| Rollback | `rolled_back: false` |
| Gates after | G3 OPEN · G5 OPEN · G11 BLOCKED · G12 BLOCKED; `production_ready_100_percent: false` |

Pre-production gate (`20260930_adr011_preprod_gate/RESULT.json`): migration `10.0.0`, code commit `3ffeba5`, `app/__init__.py` blob `1eeaf5482447d54616f3e44f2dc4ae46b207c407`, migration source SHA-256 `e38cb0556b09ab76ea9c0213f86c60b8a3584d02f7046cb053ce149a4fb5364c`; harness `77/77` PASS; rehearsal backup `pms_20260930_111550_adr011-preprod.db` `99505a47…` (same hash as the execution-time backup); restore rehearsal `RR-20260930-ADR011` all checks true; kill-mid-migration recovery proved (report item 12); regression identical between branch `0450c20` and `main` `16c4ca8` on every suite (report item 13).

Branch implementation (`20260930_adr011_implementation/RESULT.json`): `adr011_impl` 42/42 PASS at `3ffeba5bc01d70b577f3cd8db58138f20d6a3416`; migration refuses on invalid history (`refuses_on_invalid_history: true`).

---

## 5. Live human provenance evidence

Source: `20260930_135930_adr011_live_human_provenance/REPORT.md` and `RESULT.json` (read-only `mode=ro` verification, committed at `c703150`).

| Item | Value |
|---|---|
| New audit rows after the 23 historical rows | ids 24 (`login_success`), 25 (`logout`), 26 (`login_success`), all `actor_kind HUMAN`, `staff_user_id 1`, `actor_role Admin`, `actor_shift_id NULL` (no Open shift — correct), `actor_mechanism web`, IP recorded; every row `satisfies_human_model: true` |
| Account | username `admin` (role Admin) — the only production user |
| Historical rows | `audit_rows_existing_unchanged: true`; original-column digest `1cf41807…efe7` |
| SYSTEM / user 0 / no user rows | `audit_counts_system_zero_null: [0, 0, 0]` |
| Production hash | `production_sha256_before` = `production_sha256_after` = `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434` (the verification wrote nothing) |
| Other changes since post-migration backup | `users.last_login` (the login), and `notification_queue` / `notification_logs` changes caused by the standing `notification_queue_flush` job while the application ran (no message sent; no credentials configured) — disclosed in `REPORT.md:44-55`; not ADR-011 behaviour |
| Verdict | **PASS** (`REPORT.md:63`) |

---

## 6. Known limitations (recorded; none reopens the implementation)

| # | Limitation | Status | Source |
|---|---|---|---|
| L-1 | **No SYSTEM row has been observed on production.** `night_audit_enabled=false` (FD-P2-05) so `scheduler:night_audit_job` never runs; the webhook has received no calls. SYSTEM behaviour is proven on copies only (scheduler, automated no-show, webhook, FK on and off). | NOT VERIFIED (live) | live `RESULT.json` `audit_counts_system_zero_null`; pre-production item 12 |
| L-2 | Scheduler activation still requires the AR-013 / BACKLOG B-1 controls ADR (not created) and a separate authorization. The SYSTEM model records provenance; it does not make the scheduler compliant with FD-009. | OPEN / NOT AUTHORIZED | `FOUNDER_DECISIONS.md:1284`, `:1288`; `verification/adr/BACKLOG.md:12` |
| L-3 | **Legacy rows.** The 23 pre-10.0.0 rows were carried as `HUMAN`, user 1, with `actor_mechanism`, `actor_role`, `actor_shift_id` all NULL — deliberately not reconstructed. Readers must treat NULL mechanism/role on a HUMAN row as "recorded before 10.0.0", not "unknown actor". The HUMAN backfill relies on the pre-migration check that every row named a real user (`app/__init__.py:700-708`). | as designed; reading not Founder-confirmed (A11-D3) | production `RESULT.json` `actor_kinds`; `ADR011_DECISION.md:23` |
| L-4 | **Webhook gaps (pre-existing, out of ADR011-SA scope).** `modify_booking` audit is non-strict: an audit failure still commits the `rate_per_night` change (F1); `new_booking` / `cancel_booking` write no `AuditLog`; their only record, `WebhookLog`, is pruned after 90 days (`app/__init__.py:547-560`). The webhook is armed (`webhook_api_key` set). Mechanism is the plain string `webhook`; the channel source is not in the audit row (it is in `WebhookLog.source`). | OPEN — classification question carried since the decision package | `ADR011_DECISION_REQUIRED.md:41-42,121-125`; `ADR011_ANALYSIS.md:46`; pre-production report `:128-129` |
| L-5 | **PostgreSQL.** The 10.0.0 PostgreSQL DDL (`app/__init__.py:637-649`) has never been executed. | BLOCKED | pre-production report §4 |
| L-6 | **FK enforcement.** Production runs with SQLite FK enforcement OFF (ADR-005 adopted, not enabled). FK behaviour of the actor model is proven on copies with `PRAGMA foreign_keys=ON`. The CHECK constraints are enforced regardless. | OPEN (ADR-005 / B-9) | pre-production item 11 |
| L-7 | **Unknown actor ⇒ refusal.** An unattended call without a declared mechanism is refused and (for strict writers) rolls back. Frozen verification suites that call night audit / no-show without an operator must be run with `--system-mechanism verification:<suite>`. A database whose history names no real user will not boot this code (other installations, e.g. older dev databases written with `admin.id or 0`). | as designed; reading not Founder-confirmed (A11-D3) | `ADR011_REGRESSION.md:139-146`; `ADR011_IMPLEMENTATION.md:103-107` |
| L-8 | `shift_id` is recorded when an Open shift exists and is not mandatory; posting is not blocked without a shift. Whether it must be mandatory is ADR-011's open item. | OPEN | `ADR-011-operator-accountability.md:43-46` |
| L-9 | Business date is not an `audit_logs` column; it appears only inside `after_state` where a writer puts it (e.g. `charge_date`, `audit_date`). K-7 business-date dating at all financial writers is open (G3). | OPEN | `ADR011_DECISION_REQUIRED.md:68`; pre-production item 15 |
| L-10 | No workstation identifier beyond `ip_address`. | OPEN | `ADR-011-operator-accountability.md:43-44` |
| L-11 | **Observation (code reading at `c9eeff0`, not covered by any evidence pack):** a failed login for an existing account writes `staff_user_id = <target account>`; the listener therefore records it as `HUMAN`, mechanism `web`, with that account's role (`app/auth.py:110-117`; `app/audit_actor.py:73-75`). The person attempting the login is not authenticated. Behaviour is pre-existing (the column held the same id before 10.0.0). Also, logout auto-closes an open shift before writing the logout row, so a logout row's `actor_shift_id` is NULL (`app/auth.py:128-141`). Not runtime-verified here. | NOT VERIFIED; semantic question A11-D6 | code |
| L-12 | Immutability of provenance is enforced by application code (write-once inserts), not by the database. | recorded | code |
| L-13 | No application screen or report displays `actor_kind` / `actor_mechanism` / `actor_role` / `actor_shift_id` (no template references them). Readers that map `staff_user_id` to a name would show a SYSTEM row as unnamed (e.g. `app/ai_anomaly.py:609-610` → `User #None`). Provenance is queryable in the database and by verification tooling. | recorded | grep of `app/templates`, `app/*.py` |
| L-14 | Evidence-quality note: the live verification `RESULT.json` reports `schema_migrations_latest: "9.0.0"` while its `REPORT.md:53` states "the latest migration is `10.0.0`". The script computes `SELECT MAX(version)` over a text column (`verify_live_human.py:127`), so `'9.0.0'` sorts above `'10.0.0'`. The authoritative proof that 10.0.0 is recorded is `20260930_adr011_production_application/RESULT.json` → `schema_migrations_added: ["10.0.0"]` and `prod_post_state.json:277-278`. The same text-max method appears in `preprod_apply_rehearsal.json:36` (a pre-migration value, therefore correct there). Not corrected in place (evidence is not edited). | recorded (inconsistency in evidence; no effect on the verdict) | as cited |
| L-15 | Live-data copies created by the ADR-011 work remain on disk outside the repository (`FinalGrid/adr011_preprod/`, `FinalGrid/adr011_apply/`, `db-backups/`); disposal is the Founder's call. | OPEN | production report §7 |

---

## 7. ADR text deltas required to reconcile ADR-011 with ADR011-SA (PROPOSED — not applied)

Rule that bounds these edits: before adoption "an ADR's status line and its reconciliation/adoption sections may be updated; earlier content is not rewritten. After adoption an ADR is append-only" (`verification/adr/README.md:29-31`). Accordingly the deltas below are a **status-line replacement** and **appended sections only**; the historical *Context* table (`ADR-011-operator-accountability.md:12-20`) and *Proposed architecture* items are not rewritten. The precedent cited by the ruling (FD-P2-04, `FOUNDER_DECISIONS.md:1164`) has not yet been exercised on ADR-006/ADR-007 (no `FD-P2` reference exists under `verification/adr/`), so this would be the first application of that precedent.

| # | Location in `ADR-011-operator-accountability.md` | Current text (abridged) | Proposed delta |
|---|---|---|---|
| T-1 | `:5` Status | "PROPOSED FOR ADOPTION — 2026-09-08 … storage location and system-actor mechanics open …" | Replace with the status the Founder selects in A11-D1 (draft wording in `ADR011_FORMAL_ADOPTION_REQUIRED.md` §3) |
| T-2 | `:6` Founder decision | "FD-014 (2026-09-08); context FD-013, FD-016" | Add "ADR011-SA (2026-09-30, `FOUNDER_DECISIONS.md:1256-1290`)" |
| T-3 | `:8` Implements | "Nothing." | Append (not replace, if the Founder prefers the historical value kept): "System-actor representation implemented by `3ffeba5` (branch `adr011-system-actor`), applied to production as migration 10.0.0 (`116b221` evidence); live HUMAN provenance verified (`c703150` evidence). An ADR authorizes no implementation (README); these were separately authorized." |
| T-4 | new section after `:63` — *ADR011-SA reconciliation* | — | Record: item 4 **resolved** by ADR011-SA (Option B) — the designated system identity is `actor_kind = SYSTEM` plus a mandatory `actor_mechanism`; it is "never `admin`" (no user) and "never NULL" **as an identity** (kind and mechanism are NOT NULL), while `staff_user_id` is NULL on SYSTEM rows as the ruling permits (`FOUNDER_DECISIONS.md:1282`, `:1287`). Requires Founder confirmation of this reading of "never NULL" (A11-D2). |
| T-5 | same section | item 2 "Where it lives — UNRESOLVED" (`:36`) | Record: actor kind, execution mechanism, role snapshot and open shift are carried by the coupled `audit_logs` row (option (b) for these elements), per `FOUNDER_DECISIONS.md:1287`. Business date as a structured field, workstation identifier and checker identity remain OPEN. |
| T-6 | same section | item 3 "Role snapshot is captured, not joined" (`:37`) | Record: implemented as `audit_logs.actor_role`, snapshot of `users.role` at insert (`app/models.py:1111-1114`). |
| T-7 | same section | item 5 immutability (`:39`) | Record: write-once by application; no database-level immutability (L-12). |
| T-8 | same section | *Unresolved* list (`:43-46`) | Record the remaining list after ADR011-SA: workstation identifier · mandatory `shift_id` · business date in the envelope · checker identity (ADR-010) · MP-D9 beyond first release · webhook audit gaps classification (L-4). Remove "system-actor representation" from the open list **by annotation**, not deletion. |
| T-9 | same section | *Implementation boundary* "None authorized." (`:48-50`) | Record the separately issued authorizations as found in evidence: branch-only delivery (`20260930_adr011_implementation/ADR011_DECISION.md:5`); production application of 10.0.0 (`20260930_adr011_production_application/RESULT.json` → `authorization`). Scheduler activation remains NOT AUTHORIZED. |
| T-10 | same section | — | Record implementation readings for confirmation (A11-D3): unknown actor refused; unauthenticated request ⇒ SYSTEM `web:unauthenticated`; history carried as HUMAN; role/shift/mechanism not reconstructed. |
| T-11 | new section — *Adoption (date, directive)* | — | Only after A11-D1: the adoption statement, scope, and what remains open (draft in companion file §3). |

Consequential deltas outside the ADR file (also not applied):

| # | File | Delta |
|---|---|---|
| T-12 | `verification/adr/README.md:47` (register) and `:50-51` (counts) | Update ADR-011 row and the adopted / proposed-for-adoption counts per A11-D1 |
| T-13 | `verification/adr/BACKLOG.md:19` (B-8) | Annotate: "system-actor representation" resolved by ADR011-SA and implemented (10.0.0); remaining B-8 scope = workstation identifier, mandatory `shift_id`, business date in envelope, financial-row storage beyond the coupled audit row |
| T-14 | `verification/FOUNDER_DECISIONS.md` | New append-only entry recording the adoption (the 2026-09-08 baseline table at `:944-955` is not edited) |

---

## 8. Remaining governance questions

1. **Formal adoption of ADR-011** — adopt now (scope and wording), adopt in part, or keep PROPOSED FOR ADOPTION. → A11-D1.
2. **Reading of item 4 "never NULL"** under ADR011-SA (NULL `staff_user_id` on SYSTEM rows). → A11-D2.
3. **Confirmation of the four implementation readings** raised at `20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:123-127`, never answered in the repository. → A11-D3.
4. **Governance record of the in-session authorizations** (branch-only delivery; merge and production application of 10.0.0 including use of the inline boot-time registry under B-4; rollback path; live read-only verification). These exist only in evidence packs; `FOUNDER_DECISIONS.md` still records ADR011-SA as "Implementation status: not implemented" (`:1290`) with no later entry. Same class of gap as overnight note N-01 (SR-2 push). → A11-D4.
5. **Webhook audit gaps** — inside or outside ADR-011 / Q5-P1. → A11-D5.
6. **Failed-login actor semantics** (L-11) — accept and document, or schedule a later change. → A11-D6.
7. Carried, outside ADR-011 adoption and not raised as decisions here: PostgreSQL verification (L-5); B-1 scheduler ADR (L-2); B-4 migration mechanism in general; disposal of live-data copies (L-15); guest identifier in git history and harness `.env` usage (`ADR011_DECISION_REQUIRED.md:161-163`); in-place PVF runs rewriting `instance/alert_memory.json`.

---

## 9. Is formal adoption already authorized?

**No.** Searches performed at `c9eeff0` (read-only):

- `grep -n "ADR-011\|ADR011" verification/FOUNDER_DECISIONS.md` → lines 733, 954, 1256, 1261-1263, 1287 only. Line 954 records ADR-011 as **PROPOSED FOR ADOPTION** ("awaits storage/system-actor mechanics"); line 1287 states "ADR-011 is not edited by this entry; the reconciliation is applied to it at its adoption review". No entry adopts ADR-011.
- `grep -rn -i adopt` restricted to lines mentioning ADR-011/ADR011 across `verification/**/*.md` → only status statements that ADR-011 is PROPOSED FOR ADOPTION (`adr/ADR-011…md:5,61-63`, `adr/BACKLOG.md:19`, `adr/README.md:47`, `20260908_…/ADR_ADOPTION_READINESS.md:76`, `20260910_phase2_entry/PHASE2_ENTRY_ASSESSMENT.md:66`) and two statements that adoption is **open**: `20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:123` ("formal adoption and reconciliation of the ADR file are open") and `20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:101` ("G5: ADR-011 formal adoption and the remaining provenance envelope").
- No `git log` message on `c9eeff0`'s history records an adoption.

Therefore `ADR011_FORMAL_ADOPTION_REQUIRED.md` is written; `ADR011_ADOPTION_STATUS.md` is not.

### How adoption has been done before (procedure observed)

From the ADR Adoption Baseline (`FOUNDER_DECISIONS.md:896-979`) and its readiness record (`20260908_architecture_resolution_round1/ADR_ADOPTION_READINESS.md`):

1. A Founder directive with an identifier (`FG-P0-ADR-ADOPTION-20260908-01`) adopting named ADRs "Under the Founder's target baseline, subject to evidence consistency (verified in the readiness record)" (`FOUNDER_DECISIONS.md:941-942`).
2. A readiness record in evidence with a per-ADR status and reason table and a read-only consistency verification (`ADR_ADOPTION_READINESS.md` §4, §11).
3. A `FOUNDER_DECISIONS.md` entry with the ADR status table and the boundary "Architecture adopted; implementation remains separately authorized work. Adopted ADRs are append-only from this entry." (`:957-958`).
4. Each ADR's status line replaced with "**ADOPTED** — <date> under <directive> (<decisions>)", qualified where needed, e.g. ADR-005 "ADOPTED (architecture requirement) … Not implemented; not enabled", ADR-007 "ADOPTED (target recovery architecture) … Restore capability is not yet implemented." An appended adoption-review section in the ADR.
5. `verification/adr/README.md` register and counts updated; open mechanics routed to `BACKLOG.md`.

ADR-011 at 2026-09-08 was held at PROPOSED FOR ADOPTION because "storage location and system-actor mechanics" were open (`ADR-011…md:5`, `:63`). ADR011-SA resolved the system-actor part and the actor-kind part of storage; the remaining open items are listed in §7 T-8.

---

## 10. Inconsistencies found (ADR text · ruling · code · evidence)

| # | Between | Finding | Effect |
|---|---|---|---|
| I-1 | ADR text ↔ ruling/code | ADR item 4 says the system actor is "never NULL" (`ADR-011…md:38`); ADR011-SA permits, and the code enforces, `staff_user_id IS NULL` on SYSTEM rows (`app/models.py:1080-1083`). Reconcilable if "never NULL" is read as the identity (kind + mechanism), not the user column. | needs A11-D2 |
| I-2 | ADR text ↔ code/production | ADR status (`:5`), *Unresolved* (`:43`), *Implementation boundary* "None authorized" (`:50`) and *Implements* "Nothing" (`:8`) are stale relative to `c9eeff0` and production. Expected: the ruling deferred reconciliation to adoption review. | T-1…T-10 |
| I-3 | FOUNDER_DECISIONS ↔ evidence | `FOUNDER_DECISIONS.md:1290` "Implementation status: not implemented" and `:1289` "Not addressed by this ruling … application of that change to the production database" have no follow-up entry, while evidence records an in-session authorization and the application (`20260930_adr011_production_application/RESULT.json` → `authorization`). | A11-D4 |
| I-4 | ADR README ↔ BACKLOG ↔ production | `adr/README.md:47` and `BACKLOG.md:19` still list system-actor representation as open. | T-12, T-13 |
| I-5 | Evidence ↔ evidence | Live verification `RESULT.json` `schema_migrations_latest: "9.0.0"` vs its `REPORT.md:53` "latest migration is `10.0.0`" — text `MAX()` artefact (L-14). | none on verdict; correction note only |
| I-6 | Ruling ↔ code (semantic) | "Human audit records shall continue referencing the authenticated user" (`FOUNDER_DECISIONS.md:1280`) vs failed-login rows that reference the targeted, unauthenticated account as HUMAN (`app/auth.py:110-117`) (L-11). Pre-existing behaviour. | A11-D6 (classification only) |

No inconsistency was found between ADR011-SA's clauses and the code at `c9eeff0` other than I-1 (wording) and I-6 (semantics of one pre-existing writer). Code at `c9eeff0` equals the tested and applied code (`git diff 3ffeba5 c9eeff0 -- app tools` empty).
