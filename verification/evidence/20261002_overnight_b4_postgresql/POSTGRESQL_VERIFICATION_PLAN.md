# PostgreSQL verification plan

| | |
|---|---|
| Recorded | 2026-10-02, overnight session, by Claude (Claude Code agent) |
| Code | `C:/wtov` @ `c9eeff0` (= `origin/main`) |
| Nature | **Plan only.** Nothing was installed, no PostgreSQL service was started, stopped, configured or logged into, and no application process was started. Environment state and the authorizations required are in `POSTGRESQL_VERIFICATION_BLOCKER.md`. |
| Current status | PostgreSQL verification: **BLOCKED** (authorizations). It has never been executed for this codebase. |

---

## 1. What "PostgreSQL verification" means here, and what requires it

### 1.1 Sources of the requirement (FACT)

| Source | Text / effect | Location |
|---|---|---|
| ADR-011 implementation preconditions | "PostgreSQL verification **if PostgreSQL is a target** (not executed)" | `verification/evidence/20260930_adr011_implementation/ADR011_IMPLEMENTATION.md:67` |
| ADR-011 regression | NOT EXECUTED. `_AUDIT_LOGS_PG_DDL` "has not been run anywhere". SQLite-with-FK results are not PostgreSQL results | `…/20260930_adr011_implementation/ADR011_REGRESSION.md:43-50` |
| ADR-011 pre-production gate, item 14 | **BLOCKED**; the three prerequisites are listed | `…/20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:43,81-98` |
| ADR-011 production report | "Still open: … PostgreSQL verification" | `…/20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:104` |
| CF-10 completion §3F | Not executed (its stated reason was later corrected) | `…/20260930_cf10_completion/CF10_COMPLETION.md:62`; correction `…/20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:153-158` |
| MP-D4 | "SQLite as system of record" — **OPEN**. Gates Phase 4 (concurrency) and Phase 5 | `verification/MASTER_PLAN.md:70,248`; `verification/adr/BACKLOG.md:26` |
| Application | Accepts any `DATABASE_URL`; non-SQLite gets a pool configuration (`app/__init__.py:114-151`). The SQLite-only boot blocks are skipped (`:1613`, `:1663`). The `10.0.0` PostgreSQL DDL branch exists (`:637-649`, `:719-721`). PostgreSQL backup via `pg_dump` (`app/backup_manager.py:252-325`). `.env.example:20` documents `postgresql+psycopg://…`. `requirements.txt` lists `psycopg[binary]>=3.1.0` as optional (commented) |

**ANALYSIS:** no ADR, Founder decision or Master Plan unit makes PostgreSQL a production target. The requirement is conditional ("if PostgreSQL is a target"), and the condition is MP-D4, which is OPEN. Until MP-D4 is decided, PostgreSQL verification is a **compatibility claim check**: the code carries PostgreSQL branches that have never been run. It is not a production gate. If MP-D4 keeps SQLite as the system of record for the first release, the Founder may rule PostgreSQL verification NOT APPLICABLE to that release (decision PG-D1).

### 1.2 Scope options (for PG-D5)

| Level | Content |
|---|---|
| L1 — migration only | `10.0.0` PostgreSQL DDL on a PostgreSQL database shaped like pre-`10.0.0` production; refusal and rollback negatives |
| L2 — fresh install boot | Empty PostgreSQL database → `create_app()` → `db.create_all()` + 57 registry entries + `10.0.0` "already in shape" → steady-state second boot writes nothing |
| L3 — functional | ADR-011 identity/negative gates and the CF-10 writer harness on PostgreSQL |
| L4 — full parity | Golden Master / replay / invariants on PostgreSQL. Needs harness porting (§3.3) |

---

## 2. SQLite-specific code paths that may behave differently (static inventory)

"Expected" = static reading only; nothing was executed. Every row is NOT VERIFIED.

### 2.1 Defects expected on PostgreSQL (SQLite-only SQL)

| # | Location | Construct | Expected on PostgreSQL |
|---|---|---|---|
| P-1 | `app/routes.py:1101` (dashboard ALOS) | `func.julianday(...)`. The comment at `:1097-1099` says PostgreSQL supports it; **PostgreSQL has no `julianday()` function** | Query error (`function julianday(date) does not exist`) |
| P-2 | `app/reports.py:1844,1851,1859,1864` (`guest_report`, route at `:1686`) | raw `CAST(julianday(d2) - julianday(d1) AS INTEGER)` (deliberate SQLite hotfix, `:1748-1756`) | Query error |
| P-3 | `app/reports.py:1836` | `printf('%04d', g.id)` | Query error (PostgreSQL uses `format`/`lpad`) |
| P-4 | `app/reports.py:1774` | `WHERE p.is_voided = 0` on a `BOOLEAN` column | Query error (`operator does not exist: boolean = integer`) |
| P-5 | `app/__init__.py:1691,1699-1746` | 39 model columns delivered only by the SQLite column fixer (M-5); no registry entry, no Alembic revision | An **upgraded** PostgreSQL database lacks them, and ORM queries on those tables fail. A fresh PostgreSQL install gets them from `create_all()` |
| P-6 | `app/backup_manager.py:262-270` | bare `pg_dump` command | Fails unless `pg_dump` is on `PATH`. On this machine it is not (`POSTGRESQL_VERIFICATION_BLOCKER.md` §1) |

### 2.2 Semantics that differ (behaviour to test, not known defects)

| # | Area | SQLite today | PostgreSQL | Code |
|---|---|---|---|---|
| S-1 | Transactions / SAVEPOINT | pysqlite opens `BEGIN` only before DML; `nested_transaction()` forces `BEGIN` on SQLite only | Real transaction from the first statement. A failed statement aborts the transaction unless a savepoint isolates it | `app/services.py:53-69`; users `:130`, `:1849`; `app/cico_service.py:360` |
| S-2 | Row locks | `with_for_update()` is a no-op; a database-wide write lock serialises writers (`app/__init__.py:126-140`) | Real `SELECT … FOR UPDATE`: blocking, deadlock possible, READ COMMITTED visibility | 39 call sites in `app/` (static count); counters `app/routes.py:156-205,222-270,5749-5849`; `app/services.py:96-137` |
| S-3 | DDL atomicity | DDL autocommits (pysqlite) unless `BEGIN` is explicit; `10.0.0` forces it (`:698-699`) | DDL is transactional; a registry entry is atomic | `app/__init__.py:1626-1646` |
| S-4 | Registry branch | 43 `DO $$` entries **skipped and marked**; `SERIAL`→`AUTOINCREMENT`, `NOW()`→`CURRENT_TIMESTAMP` rewrites; `;`-split | All 57 executed as written, multi-statement in one `execute` | `app/__init__.py:1608-1646` |
| S-5 | FK enforcement | OFF (ADR-005 not enabled) | Always ON | ADR-005; `BACKLOG.md:20` (B-9) |
| S-6 | Type strictness | VARCHAR length not enforced; booleans are 0/1; dates may be stored as text; NUMERIC has REAL/INTEGER affinity | Length overflow raises; booleans strict; NUMERIC exact (Decimal) | `app/models.py` (e.g. `Guest.phone` VARCHAR(20), registry `1.2.0` `:810-813`) |
| S-7 | Case sensitivity | `LIKE` is case-insensitive for ASCII | `LIKE` case-sensitive; `.ilike()` renders `ILIKE` | `.like(` at `app/ai_voice.py:368`, `app/dev_seed.py:242`; `.ilike(` 30 sites (portable) |
| S-8 | Ordering / collation | BINARY collation; NULLs sort first ascending | Locale collation; NULLs sort last ascending | report and list ordering; Golden Master comparisons |
| S-9 | Autoincrement / sequences | `INTEGER PRIMARY KEY [AUTOINCREMENT]` | `SERIAL`/identity sequences; explicit-id inserts do not advance the sequence | registry `SERIAL` (`:785-797` etc.); any data copy into PostgreSQL |
| S-10 | Date functions | `func.date(x)` → `date()` | `date(x)` works as a cast; to be confirmed per site | 35 `func.date(` sites (`app/reports.py` 21, `app/routes.py` 5, others) |
| S-11 | `PRAGMA` | `PRAGMA table_info` in the column fixer (SQLite branch only) | not reached | `app/__init__.py:1769-1770` |
| S-12 | JSON columns | stored as text | `json` type has no equality operator | `Shift.payment_summary`, `AuditLog.before_state/after_state` |
| S-13 | Timestamps | naive `datetime.utcnow` defaults; `CURRENT_TIMESTAMP` text | `TIMESTAMP WITHOUT TIME ZONE`; `NOW()` is the server time zone | model defaults (63 `default=date.today` / `datetime.utcnow`) |
| S-14 | `10.0.0` PostgreSQL path | — | `ALTER … DROP NOT NULL`, three CHECKs, FK to `shifts`; `%s` placeholders via `exec_driver_sql` (psycopg pyformat) | `app/__init__.py:637-649,682-721` |
| S-15 | Alembic | base revision drops `schema_migrations`, and the stamp gate exists for that reason | the same hazard on PostgreSQL | `migrations/versions/e2a21139b806…py:21`; `installer/_alembic_stamp_check.py:13-18` |

### 2.3 Verification tooling that is SQLite-bound (FACT)

`verification/` opens databases with `sqlite3` and builds `sqlite:///` URLs: `verification/__main__.py:105`, `verification/runner.py:49`, `verification/dbcopy.py`, `verification/invariants/context.py`, `verification/golden/capture.py`, `verification/replay/*.py`, `verification/datasets/*.py`, `verification/faults/injection.py`. So are `tools/backup_db.py`, `tools/restore_db.py` and `tools/production_initialize.py` (all use `PRAGMA integrity_check` / `foreign_key_check`), and the ADR-011 77-gate harness (`20260930_adr011_preprod_gate/verify_preprod.py`: 13 `sqlite3`/`PRAGMA` references; `DATABASE_URL` built as `sqlite:///` at `:110`).

**ANALYSIS:** the pre-production report's statement that "the same 77-gate harness can be run with `DATABASE_URL=postgresql+psycopg://…`" (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:98`) is **not true as written**. The harness's direct `sqlite3` checks must be ported, or paired with PostgreSQL equivalents (`information_schema`, `pg_catalog`). L3/L4 therefore need a harness-porting step.

---

## 3. Isolated-environment plan

Every step below needs the authorization named in `POSTGRESQL_VERIFICATION_BLOCKER.md`. None is authorized now.

### 3.1 Principles

1. **Never production.** No production data in PostgreSQL unless separately authorized. Test fixtures are synthetic, or come from a restored **copy** under an explicit data-handling ruling (copies carry guest data).
2. **Throwaway database.** A dedicated database and login role, created for this work only, owned by that role, on a server the Founder designates (PG-D2). The role has no superuser, no `CREATEROLE`, and no rights on other databases. Dropped at the end, or retained, as the Founder rules.
3. **Credentials custody (PG-D3).** The Founder (or the server owner) creates the role and hands over the credentials out of band. The agent receives them only through the process environment of the verification run (`DATABASE_URL` or `PGPASSWORD`), never in a file inside the repository, never in evidence, logs or commit messages. Evidence records the host, port, database name and role name, and the password as `[REDACTED]`. A `pgpass.conf` is created only if the Founder chooses it, and outside the repository.
4. **Separate venv (PG-D4).** The driver (`psycopg[binary]`, version pinned and recorded with its hash) is installed into a **new verification venv outside the repository and outside the live folder**. The application venv inside the live folder is never touched. Installation is its own authorized step with its own evidence (pip log, `pip freeze`).
5. **Separate working tree.** Runs execute from a dedicated git worktree at a recorded commit, with `DATABASE_URL` set explicitly and `FLASK_ENV` set explicitly. Notification credentials (`ULTRAMSG_*`, `SMTP_*`) are **absent** from the run environment, so the scheduler's queue flush cannot message anyone (`app/notifications.py:57,99`). The scheduler is stopped at the end of each boot (precedent: `ADR011_PRODUCTION_APPLICATION_REPORT.md:36`).
6. **No service changes.** No `postgresql.conf` or `pg_hba.conf` edit, no restart. If the designated server needs any change, that is a separate decision.

### 3.2 Sequence

| Step | Action | Gate |
|---|---|---|
| E-0 | Founder rulings PG-D1…PG-D5 recorded | — |
| E-1 | Server owner creates role and database; hands over credentials (PG-D3) | PG-D2, PG-D3 |
| E-2 | Create the verification venv; install pinned `psycopg[binary]` + `requirements.txt`; record `pip freeze` | PG-D4 |
| E-3 | Connectivity: `SELECT version()`, `current_user`, `current_database()`; record the server version (13.23 or 18.4) | E-1, E-2 |
| E-4 | L2 fresh-install boot (tests T-01…T-06) | PG-D5 |
| E-5 | L1 `10.0.0` upgrade path on a pre-`10.0.0`-shaped PostgreSQL schema (T-07…T-11) | PG-D5 |
| E-6 | Static-defect confirmation (T-12…T-16) | PG-D5 |
| E-7 | L3 semantics (T-17…T-24), after harness porting is authorized | PG-D5 |
| E-8 | Teardown or retention per ruling; final evidence | PG-D2 |

### 3.3 Harness porting (needed for L3/L4)

Port or pair the `sqlite3`-based checks in §2.3 with PostgreSQL catalogue queries; add a `postgresql` code path to the copy/restore helpers, or use `pg_dump`/`pg_restore` into fresh databases. This is code in `verification/`, so it needs a bounded directive. Not done here.

---

## 4. Test list

| ID | Level | Test | Expected (from static reading) |
|---|---|---|---|
| T-01 | L2 | Boot against an empty database | `create_all()` runs ("empty database"); 57 registry entries attempted. Record every `Migration … FAILED` line (failures do not stop boot, `app/__init__.py:1644-1646`) |
| T-02 | L2 | `schema_migrations` after T-01 | 57 + `10.0.0` rows, **or** a listed set of failed versions to be explained |
| T-03 | L2 | `10.0.0` on a fresh install | "already in ADR011-SA shape; recorded" (`:692-696`) |
| T-04 | L2 | Model vs database columns (column-level, every table) | Equal. Any difference is a finding |
| T-05 | L2 | Second boot | No DDL; `schema_migrations` unchanged; catalogue snapshot identical |
| T-06 | L2 | `init_data` seeds | Same default rows as SQLite (settings count, payment modes, loyalty, POS) |
| T-07 | L1 | Build pre-`10.0.0` `audit_logs` shape (NOT NULL `staff_user_id`, no actor columns), insert synthetic HUMAN rows, boot | 8 `ALTER`s applied in one transaction; row digest equal; `10.0.0` recorded |
| T-08 | L1 | Same, with a row naming user 0 / NULL / a missing user | Boot refused; schema unchanged (transactional DDL) |
| T-09 | L1 | Inject a failure after the 4th `ALTER` | Full rollback; no partial columns |
| T-10 | L1 | CHECK constraints | `ck_audit_actor_kind`, `ck_audit_actor_identity`, `ck_audit_actor_not_zero` reject the ADR011-SA negatives |
| T-11 | L1 | FK `actor_shift_id → shifts` | Enforced (S-5) |
| T-12 | Static | Dashboard ALOS (`app/routes.py:1101`) | Error (P-1) — confirm |
| T-13 | Static | `guest_report` (`app/reports.py:1686`) | Error (P-2/P-3/P-4) — confirm |
| T-14 | Static | Upgrade-path columns (P-5): pre-Apr-2026 schema + boot | Columns absent — confirm |
| T-15 | Static | `run_backup` on PostgreSQL | Fails without `pg_dump` on PATH (P-6) — confirm |
| T-16 | Static | Every `func.date(` site (S-10) executes | Confirm per site |
| T-17 | L3 | ADR-011 identity gates (SYSTEM/HUMAN rows, mechanisms, role, shift) | As SQLite-with-FK results |
| T-18 | L3 | CF-10 writer harness: audit coupling, F1/F2 rollback | As SQLite; savepoint isolation (S-1) |
| T-19 | L3 | Concurrent counter allocation (invoice, advance receipt, credit note) with two sessions | No duplicates; no deadlock; retries bounded (S-2) |
| T-20 | L3 | Payment idempotency (`ux_payment_idem_ref`, registry `8.0.1`) | Duplicate rejected |
| T-21 | L3 | VARCHAR overflow on representative writers | Defined error, transaction rolled back (S-6) |
| T-22 | L3 | Text ordering in reports vs SQLite | Differences listed (S-8) |
| T-23 | L3 | Numeric rounding on GST / folio totals (Decimal vs float) | Equal to the paisa or differences listed (S-6) |
| T-24 | L3 | Night audit run (manual, operator) on a synthetic dataset | Same postings as SQLite |
| T-25 | L4 | Golden Master / replay / invariants on PostgreSQL | Requires §3.3 |

---

## 5. Evidence requirements

Each run produces, in a new pack under `verification/evidence/<date>_postgresql_*`:

1. `ENVIRONMENT.md`: server version, host/port, database and role names (password `[REDACTED]`), verification venv path, `pip freeze` with the driver version, git commit, `FLASK_ENV`, the absence of notification credentials.
2. Raw logs of every boot, with guest-data redaction applied as in prior packs.
3. Catalogue snapshots before and after (`information_schema.columns`, `table_constraints`, `pg_indexes`), as JSON.
4. `schema_migrations` contents after each boot.
5. Per-test result rows in `RESULT.json`, using only PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE.
6. A statement that production `instance/pms.db` was not opened, with the production SHA-256 taken read-only before and after **if** the Founder asks for it (taking it opens the live folder, so it needs its own authorization).
7. Teardown record (`DROP DATABASE` / role) or a retention note.

---

## 6. Status

| Item | Status |
|---|---|
| PostgreSQL as a production target (MP-D4) | OPEN |
| PostgreSQL verification L1–L4 | BLOCKED (`POSTGRESQL_VERIFICATION_BLOCKER.md`) |
| Static inventory P-1…P-6, S-1…S-15 | NOT VERIFIED (static only) |
| Driver install, credentials, database creation | NOT AUTHORIZED |
