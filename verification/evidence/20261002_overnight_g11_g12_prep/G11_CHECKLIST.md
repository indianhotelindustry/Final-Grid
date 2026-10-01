# G11 Operator Checklist — BLANK TEMPLATE

Preparation draft, 2026-10-02 (FG-OVERNIGHT-01). Companion to `G11_DEPLOYMENT_REHEARSAL_PLAN.md` (step ids match). **Every result field is intentionally empty.** Fill only during an authorized rehearsal. Allowed result values: PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE. Never record secrets (keys, tokens, passwords) in this file; record only that they were set.

## Header

| Field | Value |
|---|---|
| Authorizing directive id |  |
| Founder authorization quote / reference |  |
| Mode (M-DRY / M-CERT) — per GD-D1 |  |
| RUN_ID |  |
| Operator (name / role) |  |
| Second person present (if any) |  |
| Machine name |  |
| Rehearsal root folder (E2) |  |
| Previous code commit (B1) |  |
| Release candidate commit / tag (B5) |  |
| Production anchor SHA-256 at authorization (if A3 authorized) |  |
| Calendar date/time at start (IST and UTC) |  |
| Evidence pack path |  |

## A. Preparation

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| A1.1 | Directive names this mode and these steps | yes |  |  |  |  |
| A2.1 | E2 is outside `...\DSS\FinalGrid\` | yes |  |  |  |  |
| A2.2 | Code is a separate clone (or as ruled in GD-D3) | yes |  |  |  |  |
| A2.3 | `git rev-parse HEAD` in E2 | designated commit |  |  |  |  |
| A2.4 | venv built fresh from `requirements.txt` | yes |  |  |  |  |
| A2.5 | Rehearsal `.env`: `SECRET_KEY` set (new, ≥32 chars) — value NOT recorded | set |  |  |  |  |
| A2.6 | Rehearsal `.env`: `PORT` value | ≠ production port |  |  |  |  |
| A2.7 | Rehearsal `.env`: `ALLOW_LAN` | 0 |  |  |  |  |
| A2.8 | Rehearsal `.env`: `ULTRAMSG_*`, `FRONTDESK_WHATSAPP`, `SMTP_*`, `GEMINI_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, `PUBLIC_BASE_URL` | absent / blank |  |  |  |  |
| A2.9 | `PII_ENCRYPTION_KEY` treatment (per GD-D3) | as ruled |  |  |  |  |
| A2.10 | Outbound block rule applied for rehearsal python | applied / NOT VERIFIED |  |  |  |  |
| A2.11 | Cloudflare tunnel not running | not running |  |  |  |  |
| A3.1 | Production SHA-256 (read-only) | = anchor |  |  |  |  |
| A3.2 | Production size / journal mode / no `-wal` `-journal` |  |  |  |  |  |
| A3.3 | Production business date |  |  |  |  |  |
| A3.4 | Production `night_audit_enabled` | false |  |  |  |  |
| A3.5 | Production latest migration |  |  |  |  |  |
| A3.6 | Production application running? | as ruled |  |  |  |  |
| A4.1 | DC-1 source chosen (per GD-D2) |  |  |  |  |  |
| A4.2 | DC-2 production hash before = after backup |  |  |  |  |  |
| A4.3 | DC-3 backup manifest verdict | BACKUP VERIFIED |  |  |  |  |
| A4.4 | DC-4 restore exit code / checks passed | 0 / all |  |  |  |  |
| A4.5 | DC-4 FD-P2-04 conditions 1–12 (one line each, in the table at the end) | see table |  |  |  |  |
| A4.6 | DC-5 placed copy SHA-256 = restored SHA-256 | equal |  |  |  |  |
| A4.7 | DC-6 inv-run on copy: violation set = declared set | equal |  |  |  |  |
| A4.8 | DC-6 gm-verify on copy | per GD-D9 |  |  |  |  |
| A4.9 | DC-6 replay-verify on copy | per GD-D9 |  |  |  |  |
| A4.10 | DC-6 live `.env` NOT loaded by the harness | confirmed |  |  |  |  |
| A5.1 | Pre-rehearsal per-table digests recorded | yes |  |  |  |  |

## B. Upgrade path

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| B2.1 | DB URI at boot | `<E2>\instance\pms.db` |  |  |  |  |
| B2.2 | Migrations applied at previous-code boot | none |  |  |  |  |
| B2.3 | Jobs registered |  |  |  |  |  |
| B2.4 | `night_audit_job` registered | no |  |  |  |  |
| B3.1 | Application-path backup (`run_backup`) result |  |  |  |  |  |
| B3.2 | Tool-path backup (`backup_db.py`) manifest verdict |  |  |  |  |  |
| B4.1 | Restore of tool-path artifact |  |  |  |  |  |
| B4.2 | Restore of application `.enc` artifact |  |  |  |  |  |
| B5.1 | Upgrade mechanism used (per GD-D5) |  |  |  |  |  |
| B5.2 | Package signature verified (if signed path) |  |  |  |  |  |
| B5.3 | Protected paths unchanged (`.env`, `instance`, `backups`, `venv`, uploads) |  |  |  |  |  |
| B6.1 | Migrations applied at release boot (list) |  |  |  |  |  |
| B6.2 | Second boot is a no-op |  |  |  |  |  |
| B6.3 | `night_audit_enabled` after boot | false |  |  |  |  |
| B6.4 | `night_audit_job` registered | no |  |  |  |  |
| B7.1 | `GET /api/health` | 200 |  |  |  |  |
| B7.2 | `GET /auth/login` | 200 |  |  |  |  |
| B7.3 | `GET /dashboard` unauthenticated | 302 → login |  |  |  |  |
| B7.4 | Version string |  |  |  |  |  |
| B7.5 | DB digest before smoke = after smoke | equal |  |  |  |  |
| B8.1 | Changed tables and classification |  |  |  |  |  |
| B8.2 | Financial tables unchanged (unless declared) |  |  |  |  |  |
| B9.1 | G10 on copy after upgrade (see EV-G10) |  |  |  |  |  |

## C. Fresh install (scope per GD-D6)

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| C1.1 | Install artefact name / version / SHA-256 |  |  |  |  |  |
| C2.1 | Tables created; schema fingerprint |  |  |  |  |  |
| C3.1 | `night_audit_enabled` after first boot |  |  |  |  |  |
| C3.2 | `night_audit_job` registered after first boot |  |  |  |  |  |
| C3.3 | Action taken to satisfy FD-P2-05 (per written procedure) |  |  |  |  |  |
| C4.1 | Users / roles after wizard | one Admin |  |  |  |  |
| C5.1 | Empty-install checks |  |  |  |  |  |

## D. Launchers

| # | Launcher | CRLF count / lines | Executed? (where) | Observed behaviour | Result | Initials / time |
|---|---|---|---|---|---|---|
| D.1 | `start.bat` |  |  |  |  |  |
| D.2 | `start_pms.bat` |  |  |  |  |  |
| D.3 | `stop.bat` |  |  |  |  |  |
| D.4 | `update.bat` |  |  |  |  |  |
| D.5 | `app_mode.bat` |  |  |  |  |  |
| D.6 | `enable_lan.bat` (never on production host) |  |  |  |  |  |
| D.7 | `disable_lan.bat` (never on production host) |  |  |  |  |  |
| D.8 | `reset_pms.bat` (E2 only) |  |  |  |  |  |
| D.9 | `start_hidden.vbs` |  |  |  |  |  |
| D.10 | `cloudflare/start_pms.bat` |  |  |  |  |  |
| D.11 | `cloudflare/start_tunnel.bat` (not to be run in rehearsal) |  |  |  |  |  |
| D.12 | Production port untouched throughout |  |  |  |  |  |

## E. Day-one procedure (per GD-D7)

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| E-1.1 | Business date on copy before day-one |  |  |  |  |  |
| E-2.1 | Catch-up method used (per GD-D7) |  |  |  |  |  |
| E-2.2 | NightAuditLog rows created by catch-up (count / statuses) |  |  |  |  |  |
| E-2.3 | Audit rows created by catch-up |  |  |  |  |  |
| E-2.4 | Business date after catch-up |  |  |  |  |  |
| E-3.1 | Scheduler settings and job list |  |  |  |  |  |
| E-4.1 | Users / roles; FD-P2-01 boundary statement recorded |  |  |  |  |  |
| E-5.1 | First close: entry point used |  |  |  |  |  |
| E-5.2 | First close: status / `run_by_user_id` / snapshot hash |  |  |  |  |  |

## F. N-day operation (N = ____ per GD-D8)

Copy this block once per day.

| Day | Calendar date | Business date before | Activity script id | Close entry point | Close status | Business date after | inv-run violation set = declared? | Undeclared violations | Result | Initials / time |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |  |  |
| … |  |  |  |  |  |  |  |  |  |  |

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| F4.1 | Reopen: who, reason text retained, reopen log row |  |  |  |  |  |
| F4.2 | Re-close after reopen; invariants |  |  |  |  |  |
| F5.1 | Interrupted close: where interrupted |  |  |  |  |  |
| F5.2 | Recovery procedure used |  |  |  |  |  |
| F5.3 | State after recovery = clean close; invariants |  |  |  |  |  |
| F6.1 | Daily backups produced; pre-update artifacts not purged |  |  |  |  |  |

## G. Restore rehearsal

| Artifact | Kind (tool / app `.enc`) | Machine | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 | C12 | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

(C1…C12 = FD-P2-04 conditions, `verification/FOUNDER_DECISIONS.md:1163`.)

## H. Rollback (per `G11_ROLLBACK_PLAN.md`)

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| H.1 | Decision point reached (RB-DP id) and decision-maker |  |  |  |  |  |
| H.2 | Application stopped; no listener on rehearsal port |  |  |  |  |  |
| H.3 | Code returned to previous commit (method, no history rewrite) |  |  |  |  |  |
| H.4 | Data restored from pre-update backup (restore manifest) |  |  |  |  |  |
| H.5 | Restored DB SHA-256 / digests = pre-update state |  |  |  |  |  |
| H.6 | `schema_migrations` after rollback = pre-update list |  |  |  |  |  |
| H.7 | Boot at previous code: no pending migration, jobs, `night_audit_job` absent |  |  |  |  |  |
| H.8 | Smoke after rollback |  |  |  |  |  |
| H.9 | G10 after rollback |  |  |  |  |  |
| H.10 | Data entered after the upgrade: disposition recorded |  |  |  |  |  |

## I. Close-out

| # | Check | Expected | Observed | Result | Evidence file | Initials / time |
|---|---|---|---|---|---|---|
| I-1.1 | Final G10 on rehearsal copy |  |  |  |  |  |
| I-2.1 | Production SHA-256 (read-only) = A3.1 |  |  |  |  |  |
| I-3.1 | Logs scanned for guest data; redactions count |  |  |  |  |  |
| I-3.2 | RESULT.json built from files |  |  |  |  |  |
| I-3.3 | Live-data copies' paths recorded for Founder disposal |  |  |  |  |  |
| I-4.1 | Procedure defects found (list) |  |  |  |  |  |
| I-4.2 | Abort criteria triggered (AB ids) |  |  |  |  |  |

## Sign-off

| Field | Value |
|---|---|
| Operator signature / date |  |
| Reviewer signature / date |  |
| Overall rehearsal result (filled by reviewer, from the rows above only) |  |
| Founder acknowledgement (reference) |  |
