# BUG INDEX — FG-OVERNIGHT-01

Bugs discovered tonight. **None was fixed:** all are outside the overnight directive's authorized scope (no `app/` or tooling change is authorized). Production effect is stated per item. Severity is the analyst's estimate, for founder triage.

| ID | Area | Finding (file:line at `c9eeff0`) | Severity | Production affected now? | Detail |
|---|---|---|---|---|---|
| FG-ON-01 | settings seed | fresh install seeds `night_audit_enabled='true'` (`app/__init__.py:1897`), contrary to FD-P2-05 | MEDIUM | no (prod `'false'`) | `BUG_FG-ON-01_fresh_install_night_audit_enabled.md` |
| FG-ON-02 | boot migrations | a failed registry migration is logged and swallowed; boot continues; retried every start (`app/__init__.py:1644-1646`); `installer/_run_legacy_migrations.py:26-28` says the opposite | MEDIUM | latent (no migration pending) | `20261002_overnight_b4_postgresql/B4_STARTUP_MIGRATION_ANALYSIS.md` |
| FG-ON-03 | boot schema | fail-open `db.create_all()` when table inspection throws (`app/__init__.py:466-478`) | MEDIUM | latent | same |
| FG-ON-04 | business date | `init_data()` seeds the business date from the wall clock when the row is missing (`app/__init__.py:1850`); K-7 family | LOW–MEDIUM | no (row present) | same; K-7 package |
| FG-ON-05 | launcher | `start.bat:127-134` restarts after any crash every 5 s indefinitely, so a refused boot (e.g. 10.0.0 guard) loops | LOW | only if the app is started | same |
| FG-ON-06 | updater | `update.bat:80-99,171-198`: app started before the pre-update backup; update continues if the backup fails; multi-line `python -c` blocks may not run under cmd.exe — **NOT VERIFIED** | MEDIUM | only on update | same |
| FG-ON-07 | updater | in-app updater migration step (`app/updater.py:585-599`) likely runs already-loaded old code — **NOT VERIFIED** | LOW–MEDIUM | only on update | same |
| FG-ON-08 | launcher log | `start.bat:61-64` reads a non-existent `_startup_info.py`; start log always shows `latest_migration=unknown` | LOW | cosmetic | same |
| FG-ON-09 | PostgreSQL portability | `func.julianday` in `app/routes.py:1101` (comment `:1097-1099` claims PG compatibility); SQLite-only raw SQL in `app/reports.py` `guest_report` (`:1774`, `:1836`, `:1844-1864`) | LOW (SQLite prod) | no | `20261002_overnight_b4_postgresql/POSTGRESQL_VERIFICATION_PLAN.md` |
| FG-ON-10 | PostgreSQL schema | 39 model columns delivered only by the SQLite column fixer (`app/__init__.py:1691,1699-1746`); no path to an existing PG database | MEDIUM if PG adopted | no | same |
| FG-ON-11 | backups | `app/backup_manager.py:262-270` calls bare `pg_dump` (not on PATH here) | LOW (SQLite prod) | no | same |
| FG-ON-12 | evidence | text `MAX(version)` in `20260930_135930_adr011_live_human_provenance/verify_live_human.py:127` → wrong `schema_migrations_latest` | LOW (verdict unaffected) | no | `20261002_overnight_adr011_adoption/CORRECTION_RECORD_live_human_schema_migrations_latest.md` |
| FG-ON-13 | business date / audit | `POST /night-audit/advance-date` (`app/reports.py:3504-3566`, Admin only) jumps the business date to the calendar date, marking each skipped day `NightAuditLog.status='Skipped'`; the docstring says it "Writes an audit trail entry for every skipped day" but **no `AuditLog` row is written** (only `NightAuditLog`). Relevant to the 53-day business-date decision (DQ-16) | MEDIUM | latent — not exercised (business date unchanged since 2026-08-11) | `20261002_overnight_g11_g12_prep/` inconsistency 7; reconfirmed by reading the code |
| FG-ON-14 | upgrade path | `update.bat` performs no signature check, unlike the web updater (`app/updater.py:415`); G11 requires a signed package | MEDIUM | only on update | `20261002_overnight_g11_g12_prep/` inconsistency 6 |
| FG-ON-15 | installer | `start.bat:7,11,24` directs the operator to `setup.bat`, which is not in the repository or its history | LOW | fresh install only | same, inconsistency 5 |
| FG-ON-16 | webhook logging | suspected: a webhook call ending in an exception may leave no `webhook_logs` row — `_log` flushes without commit (`app/webhook.py:87-88`) and handlers roll back before marking failed (`:282`, `:289`, `:339`, `:478`) — **NOT VERIFIED** at runtime | MEDIUM | latent (production webhook calls: 0) | `20261002_overnight_webhook_privacy_copies/WEBHOOK_AUDIT_GAP_ANALYSIS.md` |
| FG-ON-17 | provenance | operator-triggered webhook retry recorded as SYSTEM `webhook` with no user; the operator is not identified | LOW–MEDIUM | latent | same (DQ-49) |
| FG-ON-18 | audit | operator OTA cancel `app/ota.py:673` (`cancel_booking`) cancels with no AuditLog | MEDIUM | latent | same |
| FG-ON-19 | privacy / evidence | redaction commit `a131b86` left the production guest phone number in two current-tree evidence logs (10 occurrences) | **HIGH (privacy)** | repository/remotes, not the DB | `GIT_HISTORY_PRIVACY_DECISION.md`; DQ-45 |

**Operational hazard (not a code bug, recorded for the founder):** every application start registers `notification_queue_flush` (every 5 min, `app/__init__.py:539-544`). Its only gate is the presence of messaging credentials in the environment, so any start with the production `.env` can send WhatsApp/e-mail to guests (observed 2026-09-30: three August messages marked failed). This reinforces the standing rule never to start the live app for testing. Queued as DQ-31 (B4-D6).
