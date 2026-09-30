# ADR-011 SYSTEM-ACTION PROVENANCE DECISION MEMORANDUM

| | |
|---|---|
| Recorded | 2026-09-30 |
| HEAD examined | `3efdd2b` (= `origin/main`, clean). Application code is identical to `61286b7`: `git diff 61286b7 3efdd2b -- app tools` is empty. |
| Outcome | **DECISION_REQUIRED.** No option is implemented. No application code, schema, data, setting, FK mode or scheduler state was changed. |
| Production | `instance/pms.db` `51dd83b7…30bc2`, 733,184 B, mtime 2026-08-31 11:53:14 — read-only, identical before and after |
| Evidence | `verify_adr011_current.py` → `characterisation_3efdd2b.json` (23/23 gates, 7 findings); `regression_logs/` |

## 1. Existing governance — why this stops here

| Source | What it settles | What it leaves open |
|---|---|---|
| AR-012 (`20260908_architecture_resolution_round1/RECORD.md` §3) | Automated/system actions must have "equivalent accountability through **controlled system identity/provenance**" | the representation |
| ADR-011 (PROPOSED FOR ADOPTION; `FOUNDER_DECISIONS.md:954`) | item 4: "a designated system actor identity, **never NULL and never `admin`**, so machine postings are distinguishable from operator postings" | "**UNRESOLVED** how represented"; storage location of the provenance envelope (schema columns vs coupled AuditLog row) also unresolved |
| AR-013 | scheduler actions need explicit authorization, identifiable system/operator provenance, business-date authority, auditability, idempotency, failure handling, verification | a dedicated scheduler-controls ADR is **required and deliberately not created** (AR-015; BACKLOG B-1) |
| FD-009 | no unattended financially material mutation without operator-equivalent controls | how those controls are met |
| FD-P2-05 | first release: manual operator close; `night_audit_enabled=false`; automation only after B-1 ADR + verification | — |
| FD-P2-01 | single Admin operator model for the first release; any new account of another role re-opens the boundary | — |
| ADR-005 (ADOPTED) | FK enforcement is the architecture requirement on every connection | not enabled in the application |
| PD-004 / PD-005 / PD-006, B-4 | schema change needs authorization; production mutation needs a verified-state backup; migration mechanism undecided | — |

No Founder decision selects Option A, B or C. Per the directive (§6), implementation stops at this boundary.

## 2. Current model (established from source at `3efdd2b` and runtime characterisation)

**Database contract**

- `audit_logs.staff_user_id INTEGER NOT NULL REFERENCES users(id)`. There is no ON DELETE clause, no role column, no shift column and no business-date column. `timestamp` is technical UTC (`datetime.utcnow`).
- `users.id INTEGER PRIMARY KEY`. `users.role` is constrained by **`ck_user_role CHECK (role IN ('Admin','Manager','FrontDesk','Housekeeping','Accountant'))`**, so no non-human role exists. `password_hash NOT NULL`. Login requires `is_active` and a password (`auth.py:80`). `load_user` (`__init__.py:274`) does not check `is_active`.
- Production has exactly one user (id 1, Admin, active) and **no user 0**. All 23 production audit rows carry actor 1, and **0 rows carry actor 0**.
- `PRAGMA foreign_keys` is never enabled by the application (SQLite default OFF). Tests enable it on disposable copies only. PostgreSQL enforces FKs always.

**Where the application writes an audit row without an authenticated human**

| Path | Actor written | Financial? | Live in first release? |
|---|---|---|---|
| `services.run_night_audit` from the scheduler (`night_audit_job`) — room rent per charge (W-21) | `resolve_audit_actor(None)` → **0** | yes | no — `night_audit_enabled=false` (FD-P2-05) |
| `noshow_service` inside a scheduler night audit — fee (W-14) + `noshow_posted` | **0**; `NoShowLog.posted_by_user_id` NULL (documented "night audit" origin) | yes | no (scheduler off) |
| `webhook._write_audit` — `modify_booking` (`webhook.py:357`) | **0**, hard-coded | no financial row; changes `rate_per_night` / dates | **armed**: `webhook_api_key` is set in production Settings; 0 calls received so far |
| `webhook` `new_booking` / `cancel_booking` | **no AuditLog at all**; only `WebhookLog` (pruned after 90 days by `log_pruning_job`) | no financial row | armed |
| `routes._write_audit` fallback when unauthenticated (`routes.py:317`) | **0** | no (all mutating routes require login) | only if a public route audits |
| `services_group_stay._resolve_actor` (R2A backfill) | **0** when no operator | no | backfill tooling only |
| `dev_seed.py:552` | `admin.id or 0` | dev data | no |

Other scheduler jobs write no AuditLog: `daily_backup_job` (`backup_manager.py:380`, `user_id=None`), `notification_queue_flush`, `log_pruning_job` (webhook/notification logs only since FD-P2-02), `predictive_maintenance_job` (maintenance schedules). Night audit writes no `TaxLine` rows; tax lines are generated at invoicing (`gst_service.generate_room_tax_lines`), so "taxes" is not a system-writer concern.

**Runtime characterisation** (`characterisation_3efdd2b.json`; directive §9–§10 classes)

| Writer | GREEN (FK off) | RED (F1/F2 audit failure) | FK-RED (FK on, actor 0) | HUMAN equivalent |
|---|---|---|---|---|
| Scheduler night audit (room rent + no-show fee + `noshow_posted`) | commits; one audit row per financial row; **actor 0** | rolled back: no log, no rent, no fee, date unchanged (4/4) | FK failure → rolled back atomically; **cannot complete** | `POST /night-audit/run`: commits; every row names the operator; `run_by_user_id` set — FK off **and** FK on |
| Automated no-show (no operator, no request) | commits with audit; **actor 0** | rolled back (2/2) | FK failure → nothing persisted; **cannot complete** | manual no-show names the operator (CF-10 `actor` A-02) |
| Webhook `modify_booking` | commits with audit; **actor 0** | **F1: rate change committed with no audit row (HTTP 200)**; F2: whole request fails (HTTP 500) | FK failure → request fails (HTTP 500), rate unchanged; **OTA modifications cannot complete** | n/a (no operator equivalent) |

Financial atomicity holds on every system financial path: an audit failure, FK or otherwise, never leaves a financial row behind. The problem is identity: under any FK-enforcing engine the system financial paths cannot run at all, and under the current configuration they write an actor that references no user.

**Provenance (directive §8) of a scheduler room-rent audit row**

| Question | Answerable from the row? |
|---|---|
| What happened | yes — `action='posted'`, `entity_type` |
| When | yes — technical UTC `timestamp` |
| Which financial entity | yes — `entity_id` |
| Which amount | yes — `after_state.amount` |
| Why | yes — `after_state.flow='night_audit'`, `night_audit_log_id` |
| Business date | yes — `after_state.charge_date` (inside JSON; no column) |
| Human or system (explicit) | **no** — only implied by `staff_user_id = 0` and `NightAuditLog.run_by_user_id IS NULL` |
| Execution path (scheduler vs manual) | **no** — `flow` is `night_audit` on both paths; only the actor differs |
| Operator role at the time; shift | **no** — not captured anywhere (ADR-011 item 1 gap, independent of this decision) |

## 3. Problem

AR-012 and ADR-011 item 4 require a controlled system identity. The code uses `0`, which is no identity: it references no user, is indistinguishable from "unknown/unauthenticated", violates the FK the schema declares, and makes every unattended financial path inoperable under FK enforcement (ADR-005's adopted target) or on PostgreSQL. The same representation also decides how "execution path" and "human vs system" become explicit, and what the webhook (an armed unattended writer) records.

## 4. Options — implications only (no option is ranked)

### Option A — Seeded system actor (a `users` row)

- **Identity/role.** The row must satisfy `ck_user_role`, so it must carry a human role (Admin, Manager, FrontDesk, Housekeeping or Accountant) unless the CHECK is changed. Changing the CHECK is a schema change (see B).
  - Role drives permissions everywhere (`_deny_role`, `has_role`).
  - `role='Admin'` rows drive setup-wizard gating (`routes.py:46,377`, `auth.py:60`), the "first admin" logic (`__init__.py:1875`) and admin-count guards (`auth.py:375,408`). A system row in the Admin role would suppress the setup wizard on a fresh install. ADR-011 item 4 also says "never `admin`"; whether that forbids the Admin *role* or only the `admin` *account* is for the Founder to say.
  - Any other role creates a new account of that role, which FD-P2-01 says re-opens the single-operator boundary.
  - Under FD-P2-07, a second Admin-role identity could be mistaken for the "second authorized person" of maker-checker.
- **Authentication.** `password_hash` is NOT NULL, so some hash must be stored. `is_active=False` blocks login (`auth.py:80`). The user-management UI can re-activate a user and reset its password (`auth.py:384,413`), so the row would need UI exclusion (code change) to stay non-loginable. `load_user` does not check `is_active`; sessions are signed, so this matters only if `SECRET_KEY` is exposed. The row also appears to every `User.query.all()` consumer (staff analytics: `ai_anomaly.py`, `performance_service.py`).
- **Id.** Seeding id `0` would make every existing `0` writer FK-valid with no code change: SQLite and PostgreSQL both accept an explicit `0` primary key. No historical production audit row references `0`, so nothing historical changes meaning. A new id instead requires code changes at each writer.
- **Production data.** An INSERT into `users` on production is a production mutation → PD-005 (verified-state backup per FD-P2-04 conditions 1–7, 9, 10) and a Founder authorization. Fresh installs need the same seed.
- **Provenance.** Distinguishes system from human by id, if only one system identity exists. Does not by itself make the execution path explicit (webhook vs scheduler would share one id unless several rows are seeded).

### Option B — Explicit actor-kind in the schema

- **Shape.** For example `audit_logs.actor_kind` (`HUMAN` / `SYSTEM`) with `staff_user_id` nullable, optionally plus a component identifier (e.g. `scheduler:night_audit_job`, `webhook:<source>`) that makes the execution path explicit.
  - A NULL FK is valid under FK enforcement on both engines.
  - ADR-011 item 4 says "never NULL". Whether a NULL `staff_user_id` beside a non-null `actor_kind`/component satisfies that is a Founder interpretation.
- **Schema/migration.** A schema change → PD-004 authorization; B-4 migration mechanism (inline registry vs Alembic) is **undecided**.
  - SQLite cannot drop NOT NULL in place. `audit_logs` would be rebuilt (copy table), physically rewriting the audit table while preserving rows. That touches the ADR-012 / FD-P2-02 audit-preservation concern and needs row-for-row proof.
  - PostgreSQL: `ALTER COLUMN … DROP NOT NULL` and `ADD COLUMN … DEFAULT 'HUMAN'`.
  - The G7 schema fingerprint changes.
- **Historical rows.** All 23 production rows are human (actor 1), so a default of `HUMAN` is accurate for every existing row; no row value changes.
- **Provenance.** Can make "human vs system" and "execution path" explicit columns. Role/shift (ADR-011 item 1) could be added in the same migration or separately, because ADR-011 storage is also open.

### Option C — Scheduler / system-actor governance (AR-013 / B-1 ADR), human identity retained

- **Shape.** Actor identity stays a real human `users.id`. Unattended financial actions are permitted only under an ADR-defined control. For example, the job runs under the identity of the operator who authorized or armed it, with the execution path recorded in the coupled audit row's `after_state`. Otherwise unattended financial actions stay disabled (as FD-P2-05 already does for the first release).
- **FK.** Satisfied, since every actor is a real user. No schema or data change is required for the financial paths.
- **Distinguishing automated operations.** Via `after_state` (execution-path field, arming operator, authorization reference). This is option (b) of ADR-011's storage question, and it relies on ADR-012 retention.
- **Limits.**
  - Does not by itself answer ADR-011 item 4's "designated system actor identity … never `admin`" if the arming operator is the Admin. The Founder would need to say whether delegated human identity satisfies item 4.
  - Does not cover the **webhook**, an unattended non-financial writer with no operator to delegate from. It still needs a representation (A or B) or an explicit exemption, or it cannot run under FK enforcement.
- **Scheduler.** Remains off until the ADR's controls are implemented and verified (FD-P2-05). Choosing C does not enable it.

## 5. Unresolved Founder decision

1. **The system-actor representation**: A, B, C, or a combination (for example C for scheduled financial actions plus A or B for the webhook).
2. If A: the role the row carries (given `ck_user_role`), whether "never `admin`" excludes the Admin role, and authorization for the production `users` INSERT (PD-005).
3. If B: authorization for the schema change (PD-004), and selection of the B-4 migration mechanism.
4. If C: adoption of the AR-013 / B-1 scheduler-controls ADR, and whether delegated operator identity satisfies ADR-011 item 4.
5. Independent of the choice, and needed for G5: the ADR-011 provenance-envelope storage (schema columns vs coupled AuditLog `after_state`), including role snapshot and `shift_id`.
6. Surfaced here and not decided:
   - the webhook `modify_booking` audit is non-strict (F1 commits an unaudited `rate_per_night` change);
   - webhook `new_booking` / `cancel_booking` write no AuditLog;
   - their only record (`WebhookLog`) is pruned at 90 days.

   Whether these fall under Q5-P1 (they change no financial row) is a classification question for the Founder.

## 6. Implementation consequence of each

| | A | B | C |
|---|---|---|---|
| Code change | none if id 0 is seeded; UI exclusion to keep it non-loginable | writers set `actor_kind`/component; readers of `staff_user_id` handle NULL | scheduler path records the authorizing operator + execution path; webhook still needs A/B/exemption |
| Schema | none (unless the role CHECK is widened) | yes (PD-004; B-4) | none |
| Production data | INSERT into `users` (PD-005) | table rebuild on SQLite (rows preserved) | none |
| FK enforcement becomes possible | yes | yes | yes for financial paths; webhook depends on its own choice |
| Explicit human/system + path | by id (one id per component if needed) | by column | by `after_state` |
| Scheduler | stays off (FD-P2-05) | stays off | stays off until the ADR is implemented and verified |

## 7. Evidence required after the decision

- Per affected system writer (scheduler night audit W-21/W-14, automated no-show, webhook, any other path the decision covers):
  - GREEN under FK off **and** FK on;
  - RED (F1/F2) proving the financial rollback;
  - FK-RED with a deliberately invalid actor, proving the rollback;
  - HUMAN GREEN proving operator rows unchanged.

  `verify_adr011_current.py` is the starting harness: its FK-RED and "actor names an existing user" findings must flip to PASS.
- PostgreSQL execution of the same cases. This needs a provisioned disposable database and credentials, plus Founder authorization to install `psycopg[binary]` (optional in `requirements.txt`) into the application venv or a separate verification venv.
- If A or B: a PD-006 verified-state backup before any production change; a restore rehearsal proving the change; row-for-row proof that historical `audit_logs` are unchanged (and, for B, survive the rebuild).
- Full regression as in `regression_logs/` (CF-10 harness, Phase 1 writers, Phase 1 execution, Phase 2a, Q06, retention, W-20, restore tool, Golden Master, replay, inv-run, cross-implementation), with any movement explained.

## 8. Corrections to earlier evidence (not edited in place)

- `20260930_cf10_completion/CF10_COMPLETION.md` §3F states PostgreSQL was not executed because "no server is installed". **That reason is wrong.** PostgreSQL 13 and 18 services are installed and running on this machine (`postgresql-x64-13`, `postgresql-x64-18`; `psql.exe` under `C:\Program Files\PostgreSQL\`). The accurate reason is:
  - no credentials or test database are provisioned for this work;
  - the application venv has no PostgreSQL driver;
  - installing one is outside what these directives permit.

  The conclusion (PostgreSQL NOT-VERIFIED) stands.
- The verbatim regression copies in `20260930_cf10_completion/` (`reg_phase2a_verify.py`, `reg_phase1_execution_verify.py`, `reg_w20_runtime_verify.py`) write `result.json`. On this case-insensitive filesystem that is the pack's `RESULT.json`. Running them here overwrote it; it was restored from git (`3efdd2b`) and verified unchanged. The per-suite outputs were moved to `regression_logs/` immediately after each run. **Future runs must copy those scripts to a directory without a `RESULT.json`.**
- `CF10_COMPLETION.md` §6 states that nothing else in that pack contains a production guest field. **That was incorrect** for six harness logs added after the scan. The W-24 checkout cases use the production copy's seed guest, and the checkout notification warning logs the destination phone number. These logs were redacted in commit `a131b86` (42 lines, token-only). The same redaction was applied before commit to three logs in this pack (`regression_logs/cf10_harness.log`, `verify_writers_setA.log`, `verify_writers_setD.log`).
- **Two further Founder items.**
  - The phone number remains in git history on `origin` (and was already in `20260909_phase1_verification_completion/writers_setA.txt` and `writers_setD.txt`). Removing it from history needs a history rewrite and force-push, which no directive permits.
  - The harnesses boot the application with the production `.env`, and their fixtures reuse production guests. No messaging credentials are configured today, so nothing was sent. If WhatsApp or e-mail credentials are ever configured, test runs on copies would message real guests. Stubbing notifications or using synthetic guests in the harnesses would be a verification-tooling change for a later directive.
