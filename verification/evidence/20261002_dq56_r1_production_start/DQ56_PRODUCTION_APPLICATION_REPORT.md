# DQ-56 / R1 — Production application report (controlled start and verification)

| | |
|---|---|
| Authorization | "AUTHORIZE DQ-56 R1 PRODUCTION START", Founder, 2026-10-02 (session). Start the live application once with the existing production environment, solely to activate and verify R1; read-only verification; stop afterwards; no login, transaction, night audit, Run, Reopen, Complete or other work |
| Preceding steps | DQ56-R1 implementation `46c4aab` (`20261002_dq56_r1_guard/`); DQ56e application to code without start (`20261002_dq56_r1_production_application/`, Round 9); live `main` = `origin/main` = `e310c66` |
| Window | server started **09:43:38**, serving 09:43:40, stopped **09:44:13** IST (~35 s) |
| Outcome | **R1 is in production code and was loaded by the production process. Production database byte-identical before and after. No migration, no data change, no guest messaging. Server stopped.** The in-process, authenticated UI view of 2026-08-09 was not exercised, by directive (no login). See §3 |

## 1. How the start was performed

- Command, from the live folder, identical to the launcher's server line (`start.bat:114`):

  ```
  venv\Scripts\python.exe -m waitress --host=127.0.0.1 --port=5000 --threads=4 wsgi:app
  ```

- It was run **once, directly**, not through `start.bat`. The launcher's auto-restart loop (`start.bat:100-135`), port-killing and browser launch are unsuitable for a single controlled start.
- Environment:
  - **production `.env` of the live folder, unmodified**; `DATABASE_URL`, `SECRET_KEY` and `FLASK_ENV` were cleared from the calling shell so that only `.env` values applied;
  - `PORT=5000`;
  - `ALLOW_LAN` not set, so it bound to 127.0.0.1, exactly as the launcher would.
- Process: PID 946596, command line verified as the live venv's `python.exe -m waitress … wsgi:app`.
- Stop: `Stop-Process -Force` on that PID only, after its command line was re-verified. The calling shell then reported `rc=127`, which is the exit status msys reports for an externally killed child. The process had been serving normally (§2).

## 2. Verification results

| # | Required check | Method (read-only) | Result |
|---|---|---|---|
| 1 | Application starts normally | startup log; HTTP | **PASS.** Log: production mode, secret key set, encryption available, LAN disabled, `db.create_all()` skipped, scheduler started, "Serving on http://127.0.0.1:5000"; no ERROR, no traceback. `GET /api/health` → 200 `{"online": true, "status": "ok", "version": "2.2.18"}`; `GET /auth/login` → 200 |
| 2 | R1 active for 2026-08-09 | bytecode written by the production process; on-disk sources; prior rehearsal on the same code and data | **PASS (code level).** The production process recompiled `app/reports.py` at start: `app/__pycache__/reports.cpython-312.pyc` was rewritten at **09:43:39** (previously 2026-09-30 08:05). Its header source-mtime and size equal the current `reports.py` (the R1 file, SHA-256 in `start_pre_state.json`). It contains `Q06_H1_PROTECTED_AUDIT_DATES`, `is_q06h1_protected_date` and `q06h1_protected`. Both templates on disk are byte-identical to `e310c66` (gate report, step 3) and are read from disk at render time |
| 3 | Run and Reopen blocked / hidden | as above; HTTP without login | **PASS (code level); UI under an authenticated session NOT VERIFIED (by directive: no login).** Unauthenticated `GET /night-audit`, `/night-audit?date=2026-08-09` and `/reports/night-audit?date=2026-08-09` → 302 to `/auth/login`, as before. The behaviour of this exact code on this exact data was verified on the restored fresh backup (`20261002_dq56_r1_production_application/rehearsal_green_e310c66_on_RR-20261002-DQ56-APPLY.json`): Run and Reopen refused for every role; page has no Run/Re-run/Reopen controls and shows the sealed-record note. No Run/Reopen request of any kind was sent to production |
| 4 | 2026-08-09 snapshot and financial data unchanged | production SHA-256 and mtime before and after | **PASS.** `instance/pms.db` SHA-256 `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434` and mtime 2026-09-30 13:52:28 are **identical** before (09:43:23) and after (post-stop). The file is byte-identical, so the sealed row (`Completed`, `snapshot_valid=1`, `snapshot_hash` `d248ae54…`, `total_taxable` 2285.7 per the 09:33 backup of the same content) and every financial table are unchanged |
| 5 | No migration / no unexpected DB modification | startup log; file hash | **PASS.** No "Migration … applied" line. The boot-time `CREATE TABLE IF NOT EXISTS` for the voucher tables was a no-op. The database file is byte-identical, so `schema_migrations` is unchanged (latest `10.0.0`) |
| 6 | Background-job activity, incl. guest messaging | startup log; scheduler registrations; DB and file state; timing | **PASS — none executed.** Jobs **registered** at start: daily backup (03:00), `flush_notification_queue` (5-minute interval), log pruning (04:00), predictive maintenance (05:00). The night-audit job was **not** registered. No job **ran**: the server stopped at 35 s, before the first 5-minute flush tick, and the cron jobs were hours away. No WhatsApp/SMTP/send lines in the log. The DB is byte-identical (notification queue still 4 `failed`, 0 `pending`; notification logs unchanged). `instance/alert_memory.json` (176 B, `7f79f337…`) and `backups/` are unchanged |
| 7 | Read-only verification | — | every check above was a GET without credentials, a file hash, a file stat, a log read, or a bytecode header read. No login, no POST, no database connection to production |
| 8 | Application stopped; not left running | process list; port | **PASS.** After the stop: 0 python processes; no listener on port 5000 |

**Changes on disk caused by the start** (complete list, from `start_pre_state.json` vs `start_post_state.json`):
1. `logs/pms.log`: +20 startup lines (7,843,534 → 7,845,551 B). Their content is identical to `start_server.log`, apart from the em-dash encoding. No personal data, and no secret values (only "secret_key: set").
2. `app/__pycache__/*.pyc`: bytecode recompiled for the changed source (expected Python behaviour; `__pycache__` is gitignored).

Nothing else changed: the database, `alert_memory.json`, `instance/`, `backups/`, the git HEAD (`e310c66`) and the working tree (clean) are all identical.

## 3. What was not verified, and why

- **The rendered 2026-08-09 night-audit page and a refused Run/Reopen inside the live process** require an authenticated session. The directive forbids logging in on the founder's behalf, and forging a session would be impersonation. These were therefore **NOT VERIFIED in the live process**. They are covered by:
  - the bytecode proof (§2 item 2);
  - byte-identical templates;
  - the GREEN rehearsal of the same code on the restored backup of the same data.
- **Suggested founder check at next login (read-only):** open the night audit. It lands on 09 Aug 2026 and should show "Sealed historical record (Founder ruling Q06-H1): Run and Reopen are disabled for this date", with no Run, Re-run or Reopen buttons.

## 4. Production status at the end of this step

| Item | Value |
|---|---|
| Live code | `main` @ `e310c66` (= `origin/main`), clean |
| R1 | in production code; loaded and verified at code level; active whenever the application runs |
| Application | **STOPPED** (0 python processes; port 5000 free) |
| Database | `21dc0e97…`, byte-identical to before the start |
| Recovery point | `db-backups/pms_20261002_093338_dq56-apply-pre.db` (`5c78edb2…`), restore-rehearsed 15/15 |
| Business date | 2026-08-10 (unchanged; separate decision) |

## 5. Evidence (this directory)

- `start_pre_state.json`: pre-start hashes/stats (DB, `alert_memory.json`, logs, backups, `reports.py` and its bytecode), git state.
- `start_post_state.json`: the same after stop, plus the comparison block.
- `start_http_checks.json`: the five unauthenticated GETs.
- `start_server.log`: the server's own output (20 lines).
- `start_server.meta`: start and end timestamps.

## 6. Not done (by directive)

- No login, transaction, night audit, Run, Reopen or Complete.
- No K-7, SR-1, PostgreSQL or other queued work.
- No push. This report is committed on the local branch `dq56-q06h1-guard`, together with the unpushed gate-report commit `7f19d54`. Pushing them is for the founder to authorize; they contain evidence only.

## 7. Status

| Item | Status |
|---|---|
| Start once, production environment | DONE |
| Starts normally | PASS |
| R1 loaded by the production process | PASS |
| R1 UI/route behaviour in the live process (authenticated) | NOT VERIFIED (login excluded by directive); verified on the restored backup |
| Snapshot and financial data unchanged | PASS |
| No migration / no DB modification | PASS |
| Background jobs / guest messaging | PASS — none executed |
| Server stopped | PASS |
| Further rollout or implementation | NOT AUTHORIZED |
