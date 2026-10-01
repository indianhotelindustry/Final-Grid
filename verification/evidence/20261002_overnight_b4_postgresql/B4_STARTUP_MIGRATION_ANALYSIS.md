# B-4 — Startup migration and boot-time write analysis

| | |
|---|---|
| Recorded | 2026-10-02, overnight session, by Claude (Claude Code agent), analysis only |
| Code analysed | worktree `C:/wtov`, branch `overnight-20261002` = `origin/main` = `c9eeff0`. Live checkout runs `c703150`; `app/` is identical to `c9eeff0` (stated by the directive; not re-measured here) |
| Method | Static reading only. The application was **not** started. `app` was **not** imported and `create_app()` was **not** called. No database was opened. The live production folder was not opened. |
| Backlog item | `verification/adr/BACKLOG.md:15` (B-4 — schema migration mechanism: single authority, retirement of the other, **end of unattended boot-time execution**, column-level drift detection) |
| Governance | FD-005 (`verification/FOUNDER_DECISIONS.md:468`), FD-007 (`:520`), FD-009 (`:575`), FD-019 (`:839`), ADR011-SA note (`:1289`), ADR-006 (`verification/adr/ADR-006-production-mutation-controls.md:19,39,55-57,70`) |

Labels used below: **FACT** = read directly from a cited line. **ANALYSIS** = a conclusion drawn from facts; not executed. **OPTION** = appears only in the decision package (`B4_DECISION_PACKAGE.md`).

---

## 0. The central question

**Can merely starting the application modify the production database?**

**Yes.** Starting it does not *always* modify the database. It does whenever a boot-time condition is not yet satisfied. Nothing at boot asks for confirmation. Nothing at boot takes a backup.

- **FACT:** every `create_app()` runs schema DDL and data seeding against whatever `DATABASE_URL` points to. When `DATABASE_URL` is unset, the target is `instance/pms.db` inside the application folder (`app/__init__.py:114-121`). The sequence is §1.
- **FACT (evidence):** with production already in its current shape, a second start wrote nothing. The production digest was identical before and after the smoke start (`verification/evidence/20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:54,58`). So a **steady-state boot is a no-op today**.
- **ANALYSIS:** the no-op holds only while every condition in §10 is already met. Any of these turns the next start into a production mutation: a new registry entry, a new column-fixer entry, a new default setting or seed, a deleted settings or payment-mode row, a reservation with a NULL `ota_channel`, a failed-and-unrecorded earlier migration, or a failed table inspection. The ADR011-SA note says the same thing about code merged to `main` (`FOUNDER_DECISIONS.md:1289`).
- **FACT:** starting the application also starts the scheduler. Five minutes after boot, the scheduler can send WhatsApp and e-mail messages to guests from `notification_queue`. Its daily jobs write to and delete from the database (§11).

---

## 1. Boot sequence (`create_app()`, in execution order)

| # | Step | Location | Writes? |
|---|---|---|---|
| 1 | `load_dotenv()` at import | `app/__init__.py:14` | no |
| 2 | Production log file handler; creates `logs/` | `:56-64` | file system only |
| 3 | SECRET_KEY fail-closed checks (production) | `:82-102` | no (may abort boot) |
| 4 | Resolve `DATABASE_URL`, else `sqlite:///<app>/../instance/pms.db`; **creates `instance/`** | `:114-121` | directory only |
| 5 | Engine options; `DB_IS_SQLITE` | `:124-151` | no |
| 6 | Security banner (reads env; `SCHEMA_STRICT`) | `:181-245` | no |
| 7 | `db.init_app`, `migrate.init_app` (Flask-Migrate registers CLI only; no upgrade) | `:259-260` | no |
| 8 | Blueprint imports and registration; `flask seed` / `flask unseed` CLI commands registered, not run (`:331-333`) | `:279-333` | no |
| 9 | **Gated `db.create_all()`** | `:452-484` | **yes, conditional** |
| 10 | **`_run_pending_migrations(app)`** | `:486` → `:739-1842` | **yes, conditional** |
| 11 | Table-level drift check (raises only if `SCHEMA_STRICT=1`) | `:488-526` | no |
| 12 | **`init_data()`** | `:528` → `:1845-2044` | **yes, conditional** |
| 13 | `setup_night_audit_scheduler(app)`, which **starts the scheduler** | `:531-532`; `app/services.py:546-582` | no at boot; jobs later |
| 14 | `setup_backup_scheduler` | `:535-536`; `app/backup_manager.py:364-387` | no at boot; job later |
| 15 | `notification_queue_flush` job | `:539-544` | no at boot; job later |
| 16 | `log_pruning_job` | `:547-571` | no at boot; job later |
| 17 | `predictive_maintenance_job` | `:574-600` | no at boot; job later |
| 18 | `atexit` scheduler shutdown | `:602-603` | no |

Steps 9, 10 and 12 run inside one `app.app_context()` (`:279`), before the server accepts any request. Migration therefore happens **before** the application serves traffic and **after** the configuration is fixed.

---

## 2. Mechanisms that change schema or data at boot

| ID | Mechanism | Location | Engine | Recorded in `schema_migrations`? |
|---|---|---|---|---|
| M-1 | Gated `db.create_all()` (creates missing tables only; never alters) | `app/__init__.py:452-484` | both | no |
| M-2 | Tracking-table bootstrap `CREATE TABLE IF NOT EXISTS schema_migrations` + commit, **every boot** | `:749-758` | both (`CURRENT_TIMESTAMP` / `NOW()`) | n/a |
| M-3 | Inline registry: **57** `(version, description, sql)` tuples | `:764-1602`, loop `:1604-1646` | both. 43 entries contain `DO $$` and are PostgreSQL-only; 14 run on SQLite | yes |
| M-4 | ADR011-SA migration `10.0.0` (`_migrate_audit_actor_kind`), outside the list, always after it | `:1650` → `:666-736` | both (SQLite table rebuild; PostgreSQL 8 `ALTER`s at `:637-649`) | yes |
| M-5 | SQLite column fixer: **55** `(table, column, type, default)` entries; `PRAGMA table_info`, then `ALTER TABLE … ADD COLUMN` if missing, **every boot** | `:1663-1779` (list `:1679-1747`) | SQLite only | **no** |
| M-6 | SQLite table/index bootstrap: `credit_vouchers`, `credit_voucher_redemptions`, 4 indexes, `CREATE … IF NOT EXISTS`, **every boot** | `:1786-1842` | SQLite only | **no** |
| M-7 | `init_data()` seeds, backfills, promotion | `:1845-2044` | both | **no** |

Mechanisms outside boot (they are not called at start, but they call boot):

| ID | Mechanism | Location | Note |
|---|---|---|---|
| X-1 | Alembic tree, 7 revisions, head `f7a8b9c0d1e2` | `migrations/versions/`, `installer/expected_alembic_head.txt` | Never invoked by `create_app()`. Runs only via `installer/_alembic_upgrade.py`, which **calls `create_app()` first** (`installer/_alembic_upgrade.py:47-49`), so M-1…M-7 always run before Alembic. The base revision **drops `schema_migrations`** (`migrations/versions/e2a21139b806_initial_schema_snapshot_v1_2_0.py:21`). `alembic.ini` points at `instance/pms.db` (`migrations/alembic.ini:26`). |
| X-2 | `update.bat` step 5: `create_app()` plus an inline `ALTER TABLE checkin_records ADD COLUMN company_credit_posted` | `update.bat:171-198` | Errors are hidden (`2>nul`, `logging.disable`). No errorlevel check follows. |
| X-3 | In-app updater: in-process `_run_pending_migrations`, then restart flag | `app/updater.py:585-603` | See F-6. |
| X-4 | `installer/_run_legacy_migrations.py` | whole file | Boots `create_app()` explicitly (`:57-63`). |

---

## 3. Discovery, ordering and version comparison

- **FACT — discovery:** the registry is an inline Python list literal (`app/__init__.py:764-1602`). No files are scanned. The `run_migration_*.py` glob in `update.bat:180-187` does nothing (its loop body is `pass`).
- **FACT — ordering:** entries run in **list order**. There is no sort and no version comparison. The list is not in version order: `1.3.1` (`:830`) comes before `1.2.3` (`:865`), `1.3.0` (`:898`) comes after `1.3.3` (`:890`), and `7.0.0` (`:1512`) comes after `7.4.0` (`:1486`). `10.0.0` is not in the list. It always runs after the loop (`:1650`).
- **FACT — applied check:** this is set membership on the exact string (`applied = {row[0] …}` at `:1604-1606`; `if version in applied` at `:1609`). For `10.0.0` it is `SELECT 1 … WHERE version = ?` (`:686-689`).
- **ANALYSIS — "10.0.0" vs "9.0.0":** inside the application, string comparison **does not matter**, because no code compares versions by order. It **does matter wherever someone computes "latest" with `MAX(version)` or `ORDER BY version`**. Lexicographically, `'9.0.0' > '10.0.0'`. Instances found:
  - `verification/evidence/20260930_135930_adr011_live_human_provenance/verify_live_human.py:127` (`SELECT MAX(version)`). Its output `RESULT.json:211` records `"schema_migrations_latest": "9.0.0"`. That run was taken **after** `10.0.0` was applied. Its own `REPORT.md:53` says "the latest migration is `10.0.0`". **The machine-readable field is wrong. The prose is right.** See F-1.
  - `verification/evidence/20260930_adr011_preprod_gate/verify_preprod.py:138,143` (`ORDER BY version`, `migs[-1]`). That run was pre-migration, so `9.0.0` happened to be correct. The same code would report `9.0.0` after the migration.
  - `verification/evidence/20260908_golden_master/baseline.py:47` (`max(version)`). This is pre-10.0.0 and was correct at the time.
  - `start.bat:61-64` reads the "latest migration" from `_startup_info.py`, **which does not exist in the repository**, so `MIG_VER` is always `unknown`.

---

## 4. Transaction boundaries

| Mechanism | Boundary | Analysis |
|---|---|---|
| M-3, each entry | `db.session.execute` (the SQL, split on `;` for SQLite at `:1631-1635`), then `INSERT INTO schema_migrations`, then **one `commit()` per entry** (`:1636-1642`) | **FACT (repo's own note):** pysqlite issues `BEGIN` only before INSERT/UPDATE/DELETE (`app/services.py:56-60`). **ANALYSIS:** on SQLite, a multi-statement **DDL** entry (e.g. `8.0.0`, 11 `CREATE INDEX`, `:1542-1552`; `9.0.0`, `:1570-1601`) runs each DDL statement in autocommit. If statement *k* fails, statements 1…k-1 stay applied and the version is not recorded. The entry is therefore **not atomic on SQLite**. Idempotent `IF NOT EXISTS` statements make the retry harmless for these entries. That is a property of how each entry is written, not a guarantee from the runner. On PostgreSQL, DDL is transactional, so each entry is atomic. NOT VERIFIED at runtime. |
| M-3, PG-only skip on SQLite | `INSERT` version + commit; failure swallowed (`:1613-1623`) | — |
| M-4 (`10.0.0`) | Own connection. SQLite: explicit `BEGIN` before the DDL (`:698-699`). Validation, digest before and after, then mark and commit (`:700-730`). Any exception: rollback and **re-raise** (`:731-734`) | Atomic by design. Evidence: interruption after `DROP`/`RENAME` rolled back via the hot journal (`20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:41`, item 12). |
| M-5 | One `ALTER` + commit per column (`:1771-1778`) | One column per transaction; no version record. |
| M-6 | One `CREATE` + commit per table and per index (`:1825-1842`) | — |
| M-7 | Settings, room type, payment modes, business date: one commit (`:1963`). Loyalty (`:1979`, `:1986`), POS (`:2002`), owner promotion (`:2014`), `ota_channel` backfill (`:2038`): separate commits | No exception handler around `:1849-1963`, so a failure there aborts boot. The backfill has its own handler (`:2039-2041`). |

---

## 5. Failure behaviour

| Mechanism | On failure | Location | Boot continues? |
|---|---|---|---|
| M-1 table inspection | Exception → `_existing_tables = set()` → treated as **empty database** → `db.create_all()` **runs** | `:466-478` | yes (**fail-open**, F-4) |
| M-3 entry | `rollback()`, `logger.error`, **continue with the next entry**; version not recorded, so it is **retried at every later boot** | `:1644-1646` | **yes** (F-5) |
| M-4 `10.0.0` | rollback, `logger.critical`, **raise** → `create_app()` fails | `:731-734` | **no** |
| M-5 column | rollback, `logger.warning`, continue | `:1777-1779` | yes |
| M-6 table/index | rollback, `logger.warning`, continue | `:1830-1842` | yes |
| Drift check | warning; raises only with `SCHEMA_STRICT=1` | `:488-526` | yes unless strict |
| M-7 main block | unhandled → `create_app()` fails | `:1849-1963` | no |

**Interaction with the launcher. FACT:** `start.bat` restarts the server **5 seconds after any non-zero exit, indefinitely** (`start.bat:101-134`, crash branch `:127-134`). **ANALYSIS:** a boot refused by M-4 (or an M-7 failure) becomes a restart loop. Each iteration re-runs M-1…M-3 and M-5…M-6. Each iteration retries any unrecorded M-3 entry against production. NOT VERIFIED at runtime.

---

## 6. Recording in `schema_migrations`

- **FACT:** the table is `version VARCHAR(20) PRIMARY KEY, description TEXT, applied_at TIMESTAMP DEFAULT …` (`:751-756`). Production has 58 rows after `10.0.0` (`ADR011_PRODUCTION_APPLICATION_REPORT.md:42`).
- **FACT:** on SQLite, the 43 PostgreSQL-only entries are **recorded as applied without executing anything** (`:1613-1623`). Their schema effect on SQLite comes from M-1 (fresh installs) and M-5 (existing installs).
- **FACT:** M-5, M-6 and M-7 leave **no record**.
- **ANALYSIS:** so `schema_migrations` is **not a faithful statement of applied DDL** on SQLite. Two databases with identical `schema_migrations` can differ in columns. Because drift detection is table-level only (`:497-503`), column drift is invisible (BACKLOG B-4 "drift detection at column level"; Master Plan 5.2).
- **ANALYSIS (PostgreSQL upgrade path):** 38 column-fixer entries (`:1699-1746`: credit, correction, payment-purpose, cancellation, advance-receipt, snapshot, leakage, invoice-rounding columns) plus `checkin_records.company_credit_posted` (`:1691`) appear in **no registry entry** (`:764-1602`) and **no Alembic revision** (static name search). M-5 is SQLite-only. On PostgreSQL these columns exist only if the table was created from the models. An **existing** PostgreSQL database would not receive them (`update.bat:193-196` adds only `company_credit_posted`). NOT VERIFIED (no PostgreSQL run).

---

## 7. Rollback / down-migrations

- **FACT:** the inline registry has **no down-migrations** and no rollback command. Rollback exists only per transaction, on error (§4).
- **FACT:** Alembic revisions have `downgrade()` functions (e.g. `e2a21139b806…py:41-66`). Alembic is not the boot mechanism (X-1).
- **FACT:** the governed recovery path is restore from a verified backup: `tools/backup_db.py` and `tools/restore_db.py`. The restore tool refuses an in-place restore into `instance/`. That act is a separately authorized PD-004 step (`ADR011_PRODUCTION_APPLICATION_REPORT.md:85`).

---

## 8. Backup expectations

- **FACT:** `create_app()` takes **no backup** before M-1…M-7. Nothing in `app/__init__.py` calls `run_backup` or `tools/backup_db.py`.
- **FACT:** `update.bat` step 2 takes a "pre-update" backup **by calling `create_app()`** (`update.bat:80-99`), so M-1…M-7 and the scheduler start run **before** the backup is taken. A failed backup prints "Continuing anyway" and the update proceeds (`:94-98`).
- **FACT:** the repository's own incident notes say the multi-line `python -c "…"` pattern used by `update.bat:80-99` and `:171-198` **does not execute under cmd.exe** (`installer/_alembic_upgrade.py:3-9`, `installer/_alembic_stamp_check.py:3-5`). **ANALYSIS:** if that holds for `update.bat`, its backup and migration steps silently do nothing. The first boot of new code then happens at the health check (`update.bat:212`, `waitress wsgi:app` against the production database) or at the next start, with **no pre-update backup**. NOT VERIFIED (no launcher was executed; FD-017 / G11 launcher rehearsal not performed).
- **FACT:** the in-app updater takes a pre-update backup and **aborts on failure** (`app/updater.py:482-502`). The application backup is `shutil.copy2` of the live file (`app/backup_manager.py:206`), with no checksum record (FD-005 state note, `FOUNDER_DECISIONS.md:489-494`).
- **FACT:** `_purge_old_backups` deletes every `backup_*` file older than 30 days, **pre-update backups included** (`app/backup_manager.py:330-344`). The retention exemption is unresolved (`ADR-007…md:35`).
- **ANALYSIS:** PD-005 (backup → backup verification → recovery rehearsal → mutation → verification) cannot be satisfied by any automatic boot path. It was satisfied for `10.0.0` only because the operator controlled the merge and the first start by hand (`ADR011_PRODUCTION_APPLICATION_REPORT.md:22-36`).

---

## 9. Where the boot path is triggered

| Trigger | Location | Note |
|---|---|---|
| `start.bat` server loop (also via `start_hidden.vbs` at Windows login, `start_pms.bat`) | `start.bat:101-134`; `start_hidden.vbs:1-8` | auto-restart on crash and on `.restart_flag` |
| `run.py`, `wsgi.py` (module import calls `create_app()`) | `run.py:4`; `wsgi.py:4` | any import of `wsgi` boots |
| `update.bat` backup step, migration step, health check | `update.bat:80-99`, `:171-198`, `:212` | three boots per update |
| In-app updater restart | `app/updater.py:263-285`, `:603` | — |
| Installer helpers | `installer/_run_legacy_migrations.py:57-63`; `installer/_alembic_upgrade.py:47-49` | — |
| Verification framework run in place | `verification/__main__.py:105`, `verification/runner.py:49` set `DATABASE_URL` to a copy | The URL is a copy, but the app root is the folder the harness runs from. In-place runs rewrote the live `instance/alert_memory.json` (`20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:77`). That file is written by request handling (`app/alert_engine.py:183-215`), not by boot. |

---

## 10. Every boot-time database write path

"Every boot" = statement executed at every start. "Conditional" = writes only when the condition holds. Production steady state: no condition currently holds (evidence §0).

| # | Write | Location | Condition | Kind |
|---|---|---|---|---|
| W-01 | `db.create_all()`: creates every missing model table | `app/__init__.py:473-478` | `FLASK_ENV=development`, **or** `DB_AUTO_CREATE` truthy, **or** no tables, **or table inspection raised** (`:466-470`) | schema |
| W-02 | `CREATE TABLE IF NOT EXISTS schema_migrations` + commit | `:751-758` | every boot (no-op if present) | schema |
| W-03 | Registry entry SQL + `INSERT schema_migrations` | `:1608-1643` | entry version not in `schema_migrations` (includes every previously **failed** entry) | schema and data (seeds `1.2.1` `:814-817`, `2.1.3` `:1019-1040`) |
| W-04 | `INSERT schema_migrations` for a skipped PG-only entry (SQLite) | `:1613-1623` | SQLite and version absent | tracking |
| W-05 | `10.0.0` rebuild/ALTER + mark | `:666-736` | `10.0.0` absent (production: applied 2026-09-30) | schema |
| W-06 | `10.0.0` "already in shape" mark only | `:692-696` | `10.0.0` absent and table already new-shape (fresh install) | tracking |
| W-07 | `ALTER TABLE … ADD COLUMN` (55 candidates) | `:1748-1779` | SQLite and column missing | schema |
| W-08 | `CREATE TABLE IF NOT EXISTS credit_vouchers`, `credit_voucher_redemptions` | `:1825-1834` | SQLite, every boot (no-op if present) | schema |
| W-09 | 4 × `CREATE INDEX IF NOT EXISTS` | `:1780-1785`, `:1836-1842` | SQLite, every boot (no-op if present) | schema |
| W-10 | `BusinessDate(current_date=date.today())` | `:1850-1852` | `business_date` empty (wall-clock seed; FD-013 / K-7 family) | data |
| W-11 | `RoomType('Standard', base_rate=1000)` | `:1855-1857` | no room type named exactly `Standard` (re-created if renamed or deleted) | data (master) |
| W-12 | 3 direct payment modes; **backfill `code`/`category`** on existing rows | `:1866-1876` | name missing / field empty | data (master) |
| W-13 | 9 OTA receivable payment modes | `:1889-1892` | name missing (re-created if renamed) | data (master) |
| W-14 | 47 default `settings` rows, including **`webhook_api_key = secrets.token_hex(24)`** | `:1896-1963` | key missing. A deleted `webhook_api_key` row is **re-created with a new random secret**, which silently changes the channel-manager webhook credential (`app/webhook.py:38`, `app/ota.py:362`) | data (configuration) |
| W-15 | 3 loyalty tiers | `:1967-1979` | `loyalty_config` empty | data |
| W-16 | 3 loyalty milestones | `:1980-1986` | `loyalty_milestones` empty | data |
| W-17 | 8 sample POS items | `:1989-2002` | `pos_items` empty | data |
| W-18 | **Promote first active Admin to `is_app_owner`** | `:2010-2015` | no app owner exists | data (`users`, privilege flag) |
| W-19 | **Backfill `reservations.ota_channel`** for every `source='OTA'` row with NULL | `:2024-2041` | any such row. No audit row is written. | data (reservations; reporting-relevant) |

Non-database boot writes: `logs/` and the `pms.log` handler (`:56-64`); `instance/` directory (`:118`). Every database write above runs **without an audit row and without an actor**. Under ADR011-SA a system action needs a SYSTEM audit row with a mechanism (`FOUNDER_DECISIONS.md:1271-1282`). **ANALYSIS:** W-11…W-19 are unattended data mutations outside that model. Whether any is "financially material" (FD-009) is not decided.

---

## 11. Background jobs registered at boot

All jobs live in one in-memory `BackgroundScheduler` (`app/services.py:6`). It is **always started** by `setup_night_audit_scheduler` (`app/services.py:579-582`). **ANALYSIS (APScheduler 3.10.4, `requirements.txt`):** with a fresh in-memory job store, cron jobs get their next fire time computed from "now". A start therefore does not replay missed runs. The interval job first fires 5 minutes after start. NOT VERIFIED at runtime.

| Job id | Schedule | Registered | Writes DB | Sends externally | Gate |
|---|---|---|---|---|---|
| `night_audit_job` | cron `night_audit_time` (default 02:00) | `app/services.py:546-576` | **yes**: room-rent postings, `NightAuditLog`, business-date advance (`FOUNDER_DECISIONS.md:586-589`) | — | **setting** `night_audit_enabled` (production `false`, FD-P2-05 `:1168-1176`; evidence `ADR011_PRODUCTION_APPLICATION_REPORT.md:36,48`). SYSTEM actor `scheduler:night_audit_job` (`app/services.py:535-543`) |
| `daily_backup_job` | cron `backup_time` (default 03:00) | `app/backup_manager.py:364-387` | **yes**: `backup_logs` row (`:228-233`); writes a backup file; **deletes backup files > 30 days** (`:330-344`). PostgreSQL path shells out to bare `pg_dump` (`:262-270`) | — | none (time setting only) |
| `log_pruning_job` | cron 04:00 | `app/__init__.py:547-571` | **yes**: **deletes** `webhook_logs` and `notification_logs` older than 90 days. `audit_logs` no longer pruned (commit `b0d3054`, FD-P2-02) | — | none |
| `predictive_maintenance_job` | cron 05:00 | `app/__init__.py:574-600` | **yes**: `equipment_health_logs` (`app/ai_predictive_maintenance.py:633-656`), `preventive_schedules` (`:536-621`), `UPDATE … status='Overdue'` | — | none |
| `notification_queue_flush` | interval 5 min | `app/__init__.py:539-544` | **yes**: `notification_queue.status/attempts/next_retry_at`, `notification_logs` (`app/notifications.py:209-258`) | **yes**: WhatsApp via UltraMSG HTTPS (`:45-84`) and SMTP e-mail (`:87-117`) **to guests**, for every `pending` row due for retry | **environment only**: `ULTRAMSG_INSTANCE`/`ULTRAMSG_TOKEN`, `SMTP_HOST`/`SMTP_USER`/`SMTP_PASS`. **No settings flag** |

Not boot-registered: the housekeeping "scheduler" (`app/ai_housekeeping.py:225-233`) is created on request (`app/routes.py:8271`). Notification sends from booking flows are request-driven threads (`app/notifications.py:203-206`). `alert_memory.json` is written per dashboard request (`app/alert_engine.py:191-215`).

---

## 12. Findings

| ID | Finding | Location | Status |
|---|---|---|---|
| F-1 | Lexicographic `MAX(version)` records `"schema_migrations_latest": "9.0.0"` on a database where `10.0.0` is applied. This contradicts the same pack's `REPORT.md:53`. Defect in historical evidence. Not edited (evidence rule). | `verification/evidence/20260930_135930_adr011_live_human_provenance/verify_live_human.py:127` → `RESULT.json:211`. Same pattern: `20260930_adr011_preprod_gate/verify_preprod.py:138,143`, `20260908_golden_master/baseline.py:47` | FAIL (evidence field) |
| F-2 | Boot can mutate production with no backup, no confirmation and no audit row (§10) | `app/__init__.py:452-528,1845-2044` | OPEN (B-4) |
| F-3 | `schema_migrations` does not faithfully state applied DDL: PG-only entries are marked on SQLite; M-5/M-6/M-7 are unrecorded | `:1613-1623`, `:1663-1842` | OPEN (B-4, Master Plan 5.2/5.6) |
| F-4 | Fail-open gate: an inspection exception makes `db.create_all()` run on production | `app/__init__.py:466-478` | OPEN |
| F-5 | A failed registry entry is logged and skipped; boot continues and retries every start. `installer/_run_legacy_migrations.py:26-28,61-62` claims the opposite ("If any legacy migration fails, create_app() raises") | `app/__init__.py:1644-1646` | OPEN |
| F-6 | In-app updater calls `_run_pending_migrations` after extracting new files. **ANALYSIS:** the `app` module already imported is the pre-update code (Python does not reload it), so this call runs the **old** registry and reports "No new migrations". The new entries apply at the restart boot. | `app/updater.py:585-599` | NOT VERIFIED |
| F-7 | `update.bat` takes its pre-update backup by booting the application first, and continues when the backup fails. Its multi-line `python -c` blocks match the pattern the repository records as non-executing under cmd.exe | `update.bat:80-99,171-198`; `installer/_alembic_upgrade.py:3-9` | NOT VERIFIED |
| F-8 | Registry list is not in version order; no code depends on order today | `:830/865`, `:890/898`, `:1486/1512` | OPEN (informational) |
| F-9 | On SQLite, multi-statement DDL entries are not atomic (pysqlite autocommit for DDL) | `:1631-1642`; `app/services.py:56-60` | NOT VERIFIED |
| F-10 | 38 + 1 model columns have no PostgreSQL / Alembic delivery path | `:1691`, `:1699-1746` | NOT VERIFIED |
| F-11 | Alembic base revision drops `schema_migrations`; Alembic always runs after a boot | `migrations/versions/e2a21139b806…py:21`; `installer/_alembic_upgrade.py:47-49` | OPEN (B-4) |
| F-12 | `webhook_api_key` is re-created with a fresh random value if its row is missing | `app/__init__.py:1899,1959` | OPEN (informational) |
| F-13 | Starting the application arms guest messaging (5-min queue flush), gated only by environment credentials | `app/__init__.py:539-544`; `app/notifications.py:209-258` | OPEN (B-1 / FD-009 adjacent) |
| F-14 | `start.bat` reads `_startup_info.py`, which is absent, so the start log always records `latest_migration=unknown` | `start.bat:61-64` | OPEN (Master Plan 5.4 "correct the boot log") |
| F-15 | `.env.example` documents a **relative** SQLite URL (`sqlite:///instance/pms.db`, `:23`), which resolves against the process working directory, not the app folder. **ANALYSIS:** a mismatched working directory would create a new empty database and seed it (W-01, W-10…W-17) | `.env.example:23`; `app/__init__.py:114-121,471-478` | NOT VERIFIED |

---

## 13. Status summary

| Item | Status |
|---|---|
| Static analysis of boot migration machinery | PASS (completed; static only) |
| "Can starting the app modify production?" | Answered: **yes, conditionally**; steady state is a no-op (evidence) |
| Runtime confirmation of F-4, F-5, F-6, F-7, F-9, F-10, F-15 | NOT VERIFIED (application start not authorized) |
| B-4 architecture decision | OPEN (`B4_DECISION_PACKAGE.md`) |
| Any code or behaviour change | NOT AUTHORIZED (none made) |
