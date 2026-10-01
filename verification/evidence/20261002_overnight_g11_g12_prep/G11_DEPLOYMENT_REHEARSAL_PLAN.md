# G11 Deployment Rehearsal Plan — PREPARATION DRAFT

| | |
|---|---|
| Prepared | 2026-10-02, directive FG-OVERNIGHT-01, G11/G12 preparation workstream |
| Repository read | `C:/wtov`, branch `overnight-20261002` at `c9eeff0` (= `origin/main`) |
| Kind | **Preparation only.** This plan authorizes nothing, executes nothing, and certifies nothing. It is input to a future Founder directive. Every step below is **NOT AUTHORIZED** until such a directive names it. |
| Production at preparation | not opened by this work. Facts about production are taken from `verification/evidence/overnight_execution/OVERNIGHT_STATE.md` (orchestrator, 2026-10-02 00:38) and committed evidence packs, and are cited as such |
| Status vocabulary | PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE |
| Companion files | `G11_CHECKLIST.md`, `G11_ROLLBACK_PLAN.md`, `G11_EVIDENCE_REQUIREMENTS.md`, `G11_G12_DECISION_REQUIRED.md` (decision ids `GD-Dn`) |

## 0. Authority and boundaries

- G11 definition: `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:41` — "on a copy of the current instance: upgrade path (pre-update backup → signed package → boot → checks), fresh-install path, launchers on the operator machine, day-one business-date procedure, N-day operation with nightly close, rollback to the previous tag; each followed by G10 on the rehearsal copy". Evidence: "rehearsal packs; written procedure (`docs/RELEASE.md` or successor)". Status recorded there: FAIL — never performed; procedure absent.
- G11 ordering: `CERTIFICATION_GATES.md:46` — "G11 ← procedure + rehearsal **after** G3/G5/G6/G8/G9".
- Related dimensions in the gate document's definition table: deployment procedure, rollback procedure, operational startup, night audit (`CERTIFICATION_GATES.md:19-23`).
- Production execution boundary: FD-019 (`verification/FOUNDER_DECISIONS.md:839-852`); FD-007 migration authority (`:520-548`); PD-004/005/006 (`:468-496`). **The rehearsal is performed on a copy, never on production.** Nothing in this plan changes `instance/pms.db` of the live folder.
- Night audit operating model for the first release: manual, operator-initiated, scheduler disabled — FD-P2-05 (`FOUNDER_DECISIONS.md:1168-1176`), which also states "a written daily-close procedure is required (deployment rehearsal G11)" (`:1175`).
- Staffing model: single operator / Admin — FD-P2-01 (`:1125-1134`); "the day-one procedure must record that creating any FrontDesk, Accountant or Housekeeping account before Phase 4 unit 4.2 re-opens this boundary" (`:1133`).
- Recovery acceptance criterion: FD-P2-04 twelve-condition verified state (`:1157-1166`); PD-005 minimum = conditions 1–7, 9, 10; G8 minimum = all twelve on an application-made encrypted backup (`:1163`).
- Method precedent: the ADR-011 controlled production change (`verification/evidence/20260930_adr011_preprod_gate/`, `20260930_adr011_production_application/`, `20260930_135930_adr011_live_human_provenance/`) — backup → verify → isolated restore rehearsal → pre-state digests and PVF → controlled start → post-state digests and PVF → smoke → post backup and its restore rehearsal. This plan reuses that method on a rehearsal copy.

## 1. What G11 must demonstrate (decomposed)

| Req | Requirement | Source | Depends on |
|---|---|---|---|
| R1 | Upgrade path on a copy of the current instance: pre-update backup → signed package → boot → checks | `CERTIFICATION_GATES.md:41`, `:19` | GD-D4 (release identity), GD-D5 (upgrade mechanism), G8 |
| R2 | Fresh-install path | `:41`, `:19`; `PRODUCTION_READINESS_INVENTORY.md:88` (VF-8) | GD-D6 (scope; install artefact absent) |
| R3 | Launchers on the operator machine | `:41`; PB-7 `BLOCKERS_AND_CARRYFORWARDS.md:15`; FD-017 `FOUNDER_DECISIONS.md:793-813` | FD-017 correction performed (G9); GD-D3 (machine) |
| R4 | Day-one business-date procedure | `:41`, `:21`; RL-2 `PRODUCTION_READINESS_INVENTORY.md:70`; FD-P2-01 `:1133` | GD-D7; G6 |
| R5 | N-day operation with nightly (manual) close; one reopen; one interrupted close recovered; invariants HOLD after each | `:41`, `:23`; FD-P2-05 | GD-D8 (N; acceptance); G6 (Phase 3 units 3.2–3.6, 3.8) |
| R6 | Rollback to the previous tag and the pre-update backup, with the same verification afterwards | `:41`, `:20` | `G11_ROLLBACK_PLAN.md`; GD-D10, GD-D11 |
| R7 | G10 on the rehearsal copy after each of R1–R6 | `:41`, `:40` | GD-D9 (acceptance of GM/replay on an operated copy) |
| R8 | Written procedure (`docs/RELEASE.md` or successor), including "who does what" | `:19`, `:41`; RL-7 `PRODUCTION_READINESS_INVENTORY.md:75`; PB-9 `BLOCKERS_AND_CARRYFORWARDS.md:17` | Founder adoption of the procedure text. **`docs/` does not exist at `c9eeff0`** (verified: `ls docs` → no such directory) |
| R9 | Restore rehearsal within the deployment (pre-update backup restorable) | `:18`, `:20`; FD-P2-04; G8 `:38` | G8 |

## 2. Execution modes (requires GD-D1)

`CERTIFICATION_GATES.md:46` places the G11 rehearsal **after** G3, G5, G6, G8 and G9. Today none of those is PASS (see `G11_EVIDENCE_REQUIREMENTS.md` §2). Two modes are therefore distinguished; which (if any) may run before the prerequisites pass is **GD-D1**.

| Mode | Purpose | Counts toward G11 PASS? | Code rehearsed |
|---|---|---|---|
| **M-DRY** (procedure-proving dry run) | prove the written procedure, the isolation, the evidence capture and the rollback mechanics on a copy; surface procedure defects early | **No** — cannot be scored (`CERTIFICATION_GATES.md:50`: PASS only with a committed pack at the release tag) | `c9eeff0` or any designated commit; `app/` at `c9eeff0` is identical to production's running `c703150` (verified: `git diff --stat c703150 c9eeff0 -- app tools migrations installer *.bat wsgi.py run.py requirements.txt` → empty) |
| **M-CERT** (certifying rehearsal) | the G11 rehearsal proper | Yes, if every requirement R1–R9 is evidenced at the release tag | the named release tag (GD-D4), after G3/G5/G6/G8/G9 PASS |

## 3. Environment specification

| Id | Item | Specification | Reason / source | Status |
|---|---|---|---|---|
| E1 | Machine | **GD-D3.** R3 says "launchers on the operator machine" — the operator machine is the production host (`DESKTOP-G2PDVG1`, per `20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:9`). FD-P2-04 condition 11 needs a *different* machine for the encrypted off-box restore. | `CERTIFICATION_GATES.md:41`; `FOUNDER_DECISIONS.md:1163` | OPEN |
| E2 | Rehearsal root folder | A new folder **outside** `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\` (e.g. `C:\fg_g11_<RUN_ID>\`). Never inside or beside the live `SukoonPMS` folder. | `app/__init__.py:14` calls `load_dotenv()` with no path (python-dotenv searches upward from the module); `tools/backup_db.py:52` writes to `<parent of repo>\db-backups` — a folder beside the live folder would share both | OPEN |
| E3 | Code checkout | A **separate `git clone`** of `origin` into E2, not a `git worktree` of the live repository. | Worktrees of this repository share the live folder's `.git` (`git rev-parse --git-common-dir` in `C:/wtov` → `C:/Users/SIPL Server/Downloads/DSS/FinalGrid/SukoonPMS/.git`); every worktree git operation writes into the live folder's `.git`. Clone vs worktree is part of GD-D3 | OPEN |
| E4 | Commit | M-DRY: designated by the directive. M-CERT: release tag (GD-D4). No release tag exists today (`git tag -l` → only `v2.2.18-preWave1`, `v2.2.18-wave0.5`, `v2.2.18-wave0.5-frozen`); `version.txt` = `2.2.18` | `CERTIFICATION_GATES.md:9`, `:24`, `:25` | OPEN |
| E5 | Python environment | New venv in E2 built from `requirements.txt`; never copied from the live folder | `start.bat:20-24` (a copied venv is detected as broken) | OPEN |
| E6 | `.env` (rehearsal only) | Own file in E2. `SECRET_KEY` = new random value ≥ 32 chars (boot refuses missing / short / banned keys, `app/__init__.py:78-99`). `DATABASE_URL` unset (resolves to `<E2>\instance\pms.db`, `app/__init__.py:114-120`) or set explicitly to that path. `PORT` **≠ the production port** (production default 5000; production `.env` not read by this work → NOT VERIFIED). `ALLOW_LAN=0`. **Blank/absent:** `ULTRAMSG_INSTANCE`, `ULTRAMSG_TOKEN`, `FRONTDESK_WHATSAPP`, `SMTP_*`, `GEMINI_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, `PUBLIC_BASE_URL`. `PII_ENCRYPTION_KEY`: **GD-D3** | `.env.example` keys; outbound integrations read these (`app/notifications.py`, `app/ai_insights.py`); launchers kill whatever listens on `PORT` (`stop.bat:18-20`, `update.bat:63-73`, `reset_pms.bat:60-61`) — a rehearsal on port 5000 on the production host would kill a running production server | OPEN |
| E7 | Key-material consequence | With a new `SECRET_KEY` and no `PII_ENCRYPTION_KEY`, the copy's `EncryptedString` columns (`app/models.py:180, 543, 1007, 1331, 1351`) and any production `.enc` backup cannot be decrypted. `decrypt_value` **fails open** and returns the ciphertext unchanged (`app/encryption.py:86-101`); a write-back would re-encrypt ciphertext under the rehearsal key. Production `.enc` backups are keyed from `PII_ENCRYPTION_KEY` or `SECRET_KEY` (`app/backup_manager.py:50`). Whether production sets `PII_ENCRYPTION_KEY` is NOT VERIFIED. | representativeness vs key custody — **GD-D3** | OPEN |
| E8 | Network isolation | No Cloudflare tunnel (`cloudflare/start_tunnel.bat` never run); `ALLOW_LAN=0`; do not run `enable_lan.bat`/`disable_lan.bat` on the production host — they add/delete the machine-global firewall rule named `SukoonPMS` that production uses (`enable_lan.bat:49-50`, `disable_lan.bat:35`, `README.md:41`). Optional outbound-block firewall rule for the rehearsal `python.exe` (needs admin; if not applied, record "outbound block: NOT VERIFIED"). The copy carries production's `webhook_api_key` setting (armed webhook, `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:41-42`) — the rehearsal must not be reachable from outside | — | OPEN |
| E9 | Scheduler on the copy | `create_app()` always starts the scheduler (`app/services.py:578-581`) with `daily_backup_job`, `notification_queue_flush` (every 5 min), `log_pruning_job` (04:00), `predictive_maintenance_job` (05:00) (`app/__init__.py:536-598`); `night_audit_job` only if `night_audit_enabled='true'` (`app/services.py:555-570`). `notification_queue_flush` mutates queue rows on start (evidenced on production: `20260930_135930_adr011_live_human_provenance/REPORT.md:50-55`). On the copy these mutations are expected and must be recorded, not prevented by code change. See GD-D12 | — | OPEN |
| E10 | Wall clock | Record calendar date/time at every step. Business-date-sensitive writers still use the wall clock (K-7, `PRODUCTION_READINESS_INVENTORY.md:11` FI-3); `/night-audit/advance-date` uses `date.today()` (`app/reports.py:3522`). Rehearsal results are calendar-dependent | G6 | OPEN |
| E11 | Evidence location | Pack under `verification/evidence/<YYYYMMDD_HHMMSS>_g11_rehearsal_<mode>/` in the rehearsal clone, committed only under a commit authorization (FD-018 `FOUNDER_DECISIONS.md:817-835`). Copies of live data stay outside every repository | precedent `ADR011_PRE_PRODUCTION_GATE_REPORT.md:78` | OPEN |
| E12 | Guest data | The copy holds real guest records. Every log is scanned and redacted before commit (precedent `ADR011_PRE_PRODUCTION_GATE_REPORT.md:79`; `ADR011_REGRESSION.md:55`). Synthetic activity in R5 uses fictitious guests only | constitution / SC rules | OPEN |

## 4. Data copy method

Precedent: `ADR011_PRODUCTION_APPLICATION_REPORT.md:23-24`, `ADR011_PRE_PRODUCTION_GATE_REPORT.md:34-36`.

| Step | Action | Tool / mechanism | Prerequisite | Observable check | Status |
|---|---|---|---|---|---|
| DC-1 | Choose source (**GD-D2**): (a) fresh `tools/backup_db.py` run from the live folder; (b) existing verified backup `db-backups/pms_20260930_132529_adr011-apply-post.db` (SHA-256 `12ba7b7e…`), which **predates** the current production state `21dc0e97…` (3 audit rows, `users.last_login`, notification rows differ — `20260930_135930_adr011_live_human_provenance/REPORT.md:42-55`); (c) synthetic dataset only | — | GD-D2 | source identity recorded | OPEN |
| DC-2 | If (a): production read-only identity before and after the backup (SHA-256, size, journal mode, no `-wal`/`-journal`, business date, `night_audit_enabled`, latest migration) | read-only `mode=ro` queries; `tools/backup_db.py` hashes source before/after (`tools/backup_db.py:15-28`) | Founder authorization to run a read-only tool from the live folder (`tools/backup_db.py` has no `--source`; it always reads `<its repo>/instance/pms.db`, `:44-52`) | before = after; equals the value recorded at authorization | NOT AUTHORIZED |
| DC-3 | Backup verification | `backup_db.py` manifest: integrity ok, per-table row counts | DC-2 | `BACKUP VERIFIED` | NOT AUTHORIZED |
| DC-4 | Isolated restore rehearsal | `tools/restore_db.py --source <artifact> --dest <E2>\restore\pms_restored.db --run-id RR-<RUN_ID>` | DC-3 | exit 0; 15–16/16 checks; FD-P2-04 conditions 1–7, 9, 10 recorded individually | NOT AUTHORIZED |
| DC-5 | Place the copy | Copy `pms_restored.db` to `<E2>\instance\pms.db`, verify SHA-256 equal. (`restore_db.py` refuses any destination inside its own repository's `instance/`, `tools/restore_db.py:18-21, 79-80`, so restore first, then copy) | DC-4 | hash equal | NOT AUTHORIZED |
| DC-6 | Baseline PVF on the placed copy **before any boot** | `inv-run`, `gm-verify`, `replay-verify`, cross-implementation with the verification source pointed at the copy (precedent `run_with_app.py --source`, `20260930_adr011_preprod_gate/run_with_app.py:1-60`) — and **without** loading the live folder's `.env` (that harness loads `<MAIN>/.env`, `:37-39`; MAIN resolves to the live folder for worktrees) | DC-5; GD-D9 | inv-run violation set = declared D11 set (see `G12_CERTIFICATION_TEMPLATE.md` §4); GM/replay per GD-D9 | NOT AUTHORIZED |
| DC-7 | Copies retained outside repositories; disposal is the Founder's call | — | — | paths recorded | — |

## 5. Rehearsal steps

Each step lists its prerequisites. "PRE:" ids refer to `G11_EVIDENCE_REQUIREMENTS.md` §2–§3. Every step is NOT AUTHORIZED today.

### Phase A — Preparation

| Step | Action | Prerequisites | Observable checks | Abort if |
|---|---|---|---|---|
| A1 | Record the authorizing directive, mode (M-DRY / M-CERT), RUN_ID, operator, machine, commit(s) | GD-D1; Founder directive | directive id quoted in the pack | no directive |
| A2 | Build E2–E6 (clone, venv, rehearsal `.env`) | A1; GD-D3 | `git -C <E2> rev-parse HEAD` = designated commit; `.env` keys listed (values never recorded) | E2 under the live folder's parent; PORT = production port |
| A3 | Record production read-only identity (only if authorized) | A1 | SHA-256 / size / business date / `night_audit_enabled` / latest migration | any value ≠ authorized anchor |
| A4 | Data copy DC-1…DC-6 | A2, A3; GD-D2 | §4 | §4 checks fail |
| A5 | Pre-rehearsal state digests of the copy: per-table digests of all tables, audit digest (precedent `prod_pre_state.json`) | A4 | digests recorded | — |

### Phase B — Upgrade path (R1)

| Step | Action | Prerequisites | Observable checks | Abort if |
|---|---|---|---|---|
| B1 | Check out the **previous** code (the code production runs; `c703150` per `OVERNIGHT_STATE.md`) in E2 with the copy in place | A5 | HEAD recorded | — |
| B2 | First start at previous code, controlled (precedent `first_start.py`: `create_app()`, record DB URI, jobs, stop scheduler; no web server) | B1 | DB URI = `<E2>\instance\pms.db`; **no pending migration** (`schema_migrations` unchanged; latest `10.0.0`); `night_audit_job` not registered; job list recorded | DB URI resolves outside E2; any migration applied |
| B3 | Pre-update backup by **both** paths: (i) the application path the operator would use (`run_backup`, `app/backup_manager.py:159`; `shutil.copy2` + encrypt, `:206-228`) and (ii) `tools/backup_db.py` from E2 | B2 | (i) `.enc` created, `backup_logs` row; (ii) manifest BACKUP VERIFIED | (ii) fails; (i) failure is recorded (G8 finding), not silently skipped |
| B4 | Restore rehearsal of the B3 artifacts (`restore_db.py`; `.enc` needs the rehearsal key) — FD-P2-04 conditions recorded | B3 | PASS per condition; cond 11 NOT VERIFIED unless off-box | (ii) restore FAIL |
| B5 | Apply the release candidate by the mechanism decided in **GD-D5**: signed zip through `/admin/update` (`app/updater.py`, Ed25519 manifest signature, pubkey `installer/update_pubkey.pem`), or `update.bat` (no signature check; backup failure "Continuing anyway", `update.bat:95, 98`), or git fast-forward (ADR-011 precedent) | B4; GD-D4, GD-D5; signing-key custody | package signature verified (if signed path); files changed list; protected paths untouched (`.env`, `instance`, `backups`, `venv`, uploads) | signature invalid; protected path changed |
| B6 | Boot the release candidate (controlled start) | B5 | migrations applied listed (before/after `schema_migrations`); each migration's log line; second boot is a no-op; jobs; `night_audit_enabled=false`; `night_audit_job` not registered | migration error; boot refused; `night_audit_job` registered |
| B7 | Smoke (precedent `smoke.py`): `GET /api/health` 200, `GET /auth/login` 200, `GET /dashboard` unauthenticated 302 → login; version string | B6 | as listed; DB digest before = after smoke | any mismatch |
| B8 | Post-upgrade state digests; classify every changed table (expected by migration / caused by scheduler / unexpected) | B7 | only expected tables changed; financial tables identical unless the release declares a change | unexplained change |
| B9 | G10 on the copy (R7) | B8; GD-D9 | per `G11_EVIDENCE_REQUIREMENTS.md` EV-G10 | undeclared difference |

### Phase C — Fresh-install path (R2) — scope per GD-D6

| Step | Action | Prerequisites | Observable checks | Abort if |
|---|---|---|---|---|
| C1 | Identify the install artefact. **Finding:** `start.bat:7, 11, 24` direct the operator to `setup.bat`, which is not in the repository and never was (`git log --all -- setup.bat` → empty; not git-ignored) | GD-D6 | artefact named, versioned, hashed | no install artefact |
| C2 | Fresh install into a second isolated folder with an empty DB (`db.create_all()` runs when the database is empty, `app/__init__.py:471-478`) | C1 | tables created; `schema_migrations` state recorded; schema fingerprint recorded | — |
| C3 | Settings after first boot. **Finding:** `init_data` seeds `night_audit_enabled='true'` (`app/__init__.py:1897`), and `setup_night_audit_scheduler` registers `night_audit_job` at 02:00 when it is `'true'` (`app/services.py:555-570`) — contrary to FD-P2-05 for a fresh install | C2 | value recorded; `night_audit_job` registration recorded | the job is left registered past the first controlled stop |
| C4 | First-run wizard (`app/routes.py:44`, `setup_wizard`), first Admin user, settings per the written procedure | C3 | users = one Admin (FD-P2-01) | any non-Admin role created without a ruling |
| C5 | G10-equivalent checks applicable to an empty install (inv-run VACUOUS expected; schema fingerprint = release-tag expectation, `CERTIFICATION_GATES.md:15`) | C4 | recorded | — |

### Phase D — Launchers (R3)

| Step | Action | Prerequisites | Observable checks | Abort if |
|---|---|---|---|---|
| D1 | Record line endings of every tracked launcher. At `c9eeff0` all 11 are LF-only (`git ls-files --eol`: `i/lf w/lf` for `start.bat`, `start_pms.bat`, `stop.bat`, `update.bat`, `app_mode.bat`, `enable_lan.bat`, `disable_lan.bat`, `reset_pms.bat`, `start_hidden.vbs`, `cloudflare/start_pms.bat`, `cloudflare/start_tunnel.bat`) | FD-017 correction delivered and verified (G9) for M-CERT | CRLF count per file | — |
| D2 | `start.bat` (rehearsal PORT), `stop.bat`, `start_pms.bat`, `app_mode.bat`, `start_hidden.vbs` executed in E2 | D1; E6 PORT ≠ production | process starts/stops on rehearsal PORT only; `logs\start.log` line; no process on production port touched | any action on the production port |
| D3 | `update.bat` exercised only as part of B5 if GD-D5 selects it | GD-D5 | — | — |
| D4 | `enable_lan.bat` / `disable_lan.bat`: **not on the production host** (shared firewall rule name). Off-host only, or NOT APPLICABLE by ruling | GD-D3 | — | run on production host |
| D5 | `reset_pms.bat` (deletes `instance\pms.db`, `reset_pms.bat:80-90`): only in E2, only if the procedure includes it | written procedure | — | run anywhere but E2 |

### Phase E — Day-one procedure (R4) — content per GD-D7

| Step | Action | Prerequisites | Observable checks |
|---|---|---|---|
| E-1 | Confirm business date on the copy (production: `2026-08-10`, 53 days behind calendar on 2026-10-02 — `OVERNIGHT_STATE.md`) | B9 | value recorded |
| E-2 | Bring the business date to the operating date by the method ruled in GD-D7 (sequential manual closes; or Admin force-advance `POST /night-audit/advance-date`, `app/reports.py:3504-3566`, which marks each skipped day `Skipped` with an override reason, posts no room rent and writes no `AuditLog` row — code reading, NOT VERIFIED at runtime; or a Phase 3 staleness procedure) | GD-D7; G6 | NightAuditLog rows per day; business date; audit rows |
| E-3 | Confirm scheduler settings: `night_audit_enabled=false` (FD-P2-05); other jobs as ruled (GD-D12) | E-2 | settings + job list |
| E-4 | Confirm users and roles: one Admin; record the FD-P2-01 boundary statement (`FOUNDER_DECISIONS.md:1133`) | E-3 | user/role list |
| E-5 | First close of the operating day through the designated entry point (GD-D7: `POST /night-audit/run` `app/routes.py:4921` or the staged `/reports/night-audit/run` → `/complete` `app/reports.py:2823, 2895`) | E-4 | NightAuditLog `Completed`; `run_by_user_id`; snapshot hash; audit rows HUMAN |

### Phase F — N-day operation with manual close (R5) — N per GD-D8

| Step | Action | Prerequisites | Observable checks | Abort if |
|---|---|---|---|---|
| F1 | For day d = 1…N: scripted synthetic operator activity (fictitious guests; reservations, check-in, payments incl. one advance, extra charges, checkout, one cancellation refund) | E-5; G3 (K-7) and SR-1 for a readable verdict | rows created; all `folio_id` set | any NULL `folio_id` on a new row |
| F2 | Manual close for day d | F1 | status `Completed`; business date +1 exactly; `night_audit_job` never fired | date moves by ≠ 1 |
| F3 | After each close: `inv-run` on a copy of the rehearsal DB | F2 | violation set = declared D11 set (+ any declared, ruled exception); everything else HOLDS or VACUOUS | any undeclared violation |
| F4 | One reopen (Admin/Manager, mandatory reason, `app/reports.py:3104`) and re-close | F3; FD-P2-07 matrix treatment of "reopening a closed business day" (`FOUNDER_DECISIONS.md:1193`) | `NightAuditReopenLog` row; reason retained; invariants after | reopen without reason |
| F5 | One interrupted close (process killed mid-close) and recovery per the Phase 3 unit 3.5 procedure | F3; **G6** (unit 3.5 not implemented — `MASTER_PLAN.md:149`) | recovered state equals a clean close; invariants HOLD | recovery undefined → BLOCKED |
| F6 | Daily backup behaviour observed (`daily_backup_job`, 30-day purge `app/backup_manager.py:330`) | F2 | backups produced; none of the pre-update artifacts purged | pre-update artifact purged |

### Phase G — Restore rehearsal inside the deployment (R9)

| Step | Action | Prerequisites | Observable checks |
|---|---|---|---|
| G-1 | Restore the B3 pre-update artifact and the latest F6 application backup into isolated paths | F6 | FD-P2-04 conditions 1–10, 12 recorded per artifact |
| G-2 | Off-box restore of an application-made `.enc` on a different machine using custody-held key material only (condition 11) | G8 key-custody procedure; GD-D3 | condition 11 PASS / NOT VERIFIED |

### Phase H — Rollback rehearsal (R6)

Per `G11_ROLLBACK_PLAN.md` (code rollback and data rollback, decision points RB-DP1…).

### Phase I — Close-out

| Step | Action | Observable checks |
|---|---|---|
| I-1 | G10 on the final rehearsal copy (R7) | per GD-D9 |
| I-2 | Production read-only identity again (if A3 was authorized) | SHA-256 equal to A3 |
| I-3 | Evidence pack: manifests, logs (redacted), RESULT.json built from files, operator/machine/directive | `G11_EVIDENCE_REQUIREMENTS.md` |
| I-4 | Report defects in the procedure; no fix inside the rehearsal | — |

## 6. Observable checks catalogue

| Id | Check | How observed |
|---|---|---|
| OC-01 | Production DB unchanged | SHA-256 of live `instance/pms.db` before/after, read-only (only if authorized) |
| OC-02 | Rehearsal DB path | `app.config['SQLALCHEMY_DATABASE_URI']` printed at every boot = `<E2>\instance\pms.db` |
| OC-03 | Code identity | `git rev-parse HEAD`; `git status --porcelain` empty for `app/` |
| OC-04 | Migrations | `SELECT version FROM schema_migrations` before/after each boot; boot log lines |
| OC-05 | Scheduler | job ids at every boot; `night_audit_job` absent |
| OC-06 | Settings | `night_audit_enabled`, `night_audit_time`, `noshow_*` values |
| OC-07 | Outbound | `notification_logs` rows created during rehearsal: all `failed` with "not configured"; no successful send; firewall log if outbound block applied |
| OC-08 | Health | `/api/health` 200 and version |
| OC-09 | Authorization smoke | `/dashboard` unauthenticated → 302 |
| OC-10 | Table digests | per-table digest diff with classification |
| OC-11 | Audit provenance | new audit rows: HUMAN with user/role/mechanism for operator actions; SYSTEM with mechanism for scheduler/webhook; no user 0 (ADR011-SA, `FOUNDER_DECISIONS.md:1267-1290`) |
| OC-12 | Invariants | `inv-run` violation set vs declared set |
| OC-13 | Golden Master / replay | per GD-D9 |
| OC-14 | Backup / restore | manifests; FD-P2-04 per-condition table |
| OC-15 | Business date | `business_date.current_date` after each close |
| OC-16 | Port | only the rehearsal PORT has a listener started by the rehearsal |

## 7. Abort criteria

Abort = stop, preserve evidence, record, report; no corrective action inside the rehearsal.

| Id | Abort criterion |
|---|---|
| AB-01 | Live `instance/pms.db` SHA-256 differs from the authorized anchor at any observation |
| AB-02 | Any rehearsal process resolves its database, `.env`, `backups/` or `db-backups/` to a path inside or beside the live folder |
| AB-03 | Any listener started or killed on the production port, or any change to the `SukoonPMS` firewall rule on the production host |
| AB-04 | Any successful outbound message (WhatsApp, SMTP, AI API) or any inbound webhook call |
| AB-05 | Backup or restore verification fails (tool path) |
| AB-06 | Migration error, refused boot, or an unexpected migration applied |
| AB-07 | `night_audit_job` registered while `night_audit_enabled` is meant to be false, or any unattended close |
| AB-08 | Any undeclared invariant violation, or the declared D11 set not reproduced exactly |
| AB-09 | Any unexplained table change after a step |
| AB-10 | Production guest data found in any file destined for the repository |
| AB-11 | A step requires an action not named in the authorizing directive (stop at the boundary) |
| AB-12 | Business date moves by other than one day per close |

## 8. Not covered by this plan

- PostgreSQL: BLOCKED on authorizations (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:81-98`). The rehearsal is SQLite-only unless a separate decision designates a server.
- Multi-role operation: out of first-release scope (FD-P2-01).
- Any production change. The production upgrade itself is a separate PD-004/PD-005 act under FD-007.
