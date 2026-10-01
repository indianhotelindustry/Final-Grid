# G12 Open Risks Register — PREPARATION DRAFT

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, G11/G12 preparation workstream; repository `C:/wtov` at `c9eeff0` |
| Kind | Preparation only. A register of open risks bearing on G11/G12, each with its source. Nothing here closes, accepts or re-classifies any item; dispositions are Founder decisions. Items marked "code reading" were derived from source at `c9eeff0` and were **not** exercised at runtime |
| Status vocabulary | PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE |

`FD` = `verification/FOUNDER_DECISIONS.md`; `CG` = `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md`; `PRI` = `verification/evidence/20260910_phase2_entry/PRODUCTION_READINESS_INVENTORY.md`; `BL` = `verification/adr/BACKLOG.md`.

## A. Carry-forwards preserved open by the Founder registers

| Id | Risk | Consequence | Source | Gate | Status |
|---|---|---|---|---|---|
| OR-01 | **CF-5** unauthorized-role verification (T-N02) not run | negative authorization per writer unproven; becomes blocking the moment a second role exists (MP-D9) | `FD:1100`, `:1202`; `20260910_phase2_founder_resolution/CARRY_FORWARD_REGISTER.md:9` | G4, G10 | OPEN |
| OR-02 | **CF-6** replay does not capture `attribution_control` | a regression in the night-audit reconciliation control would not show in replay | `FD:1100`; `CARRY_FORWARD_REGISTER.md:10` | G10 | OPEN (deliberate) |
| OR-03 | **CF-9** deployment verification — no post-release `inv-run` on a copy of the live DB; pre-release NULL-folio classification | the release has never been verified as deployed | `20260910_phase1_acceptance/CARRY_FORWARD_REGISTER.md:11`; `CARRY_FORWARD_REGISTER.md:11`; `FD:1202` | G11 | OPEN |
| OR-04 | **SR-1** INV-B06 refinement not implemented; no rule text ruled | a legitimate business-dated advance payment in real operation would be reported VIOLATED — an **undeclared** violation, which FD-P2-03 makes a certification failure | `FD:1178-1187`, `:1150`; `overnight_execution/OVERNIGHT_STATE.md` (DQ-01) | G3, G10, G12 | OPEN |
| OR-05 | **K-7** wall-clock dating at financial writers (W-08/09/22/23 `today`, W-10, W-11, W-20, W-17 model default; late-checkout auto-charge) | rows dated to the calendar day instead of the open business day whenever the close lags midnight; closed-day protection (INV-B01/B04/B06) and day totals break | `PRI:11` (FI-3); `FD:707-710`; `BLOCKERS_AND_CARRYFORWARDS.md:10` (PB-2) | G3, G6 | OPEN |
| OR-06 | **Q06 historical record** — sealed `NightAuditLog` 2026-08-09 keeps the defective `total_taxable = 2285.7`; replay shows two governed deltas against a baseline that is not re-frozen | any closed-date view serves the historical figure; G10 "replay 0" is not literally reachable (see OR-24) | Q06-H1/H3 `FD:1219-1246`; `20260923_q06_fix/Q06_REGRESSION.md:36-45` | G3, G10 | OPEN (governed) |

## B. Architecture / mechanism risks

| Id | Risk | Consequence | Source | Gate | Status |
|---|---|---|---|---|---|
| OR-07 | **B-4 boot-time migrations.** `_run_pending_migrations` runs at every `create_app()` (`app/__init__.py:486`), on updater restart, and inside `update.bat`'s backup and migration steps (`update.bat:85-90, 172-176`). The DB lives in the app working tree | merging a migration into `main` in the live folder (or applying a package) and starting the app **migrates production** with no separate step; no down-migrations exist | `FD:543-548` (FD-007 state); `FD:1289`; `BL:15`; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:104, 114` | G7, G11 | OPEN |
| OR-08 | Two schema mechanisms coexist: inline registry and an Alembic tree (`migrations/`, `installer/_alembic_upgrade.py`, `installer/expected_alembic_head.txt`); installer stamp check recorded as one that "can never pass" | schema authority ambiguous for fresh install vs upgrade | `BL:15`; `PRI:71` (RL-3, item 5.5); `FD:543-548` | G7, G11 | OPEN |
| OR-09 | **PostgreSQL unverified** — no credentials, no driver in the app venv; DDL compiled offline only | any PostgreSQL deployment is unverified; G10/G11 evidence is SQLite-only | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:81-98` | G7, G10, G11 | BLOCKED (authorizations) |
| OR-10 | PostgreSQL 13 and 18 services listen on all interfaces (`0.0.0.0:5432`, `:5433`) on the production host | exposure outside FinalGrid's scope; ownership unknown | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:86` (observation) | — | OPEN (observation) |
| OR-11 | FK enforcement OFF on production (ADR-005 adopted, not enabled); `folio_id` nullable | orphan financial rows not prevented by the database (detected by invariants) | `CG:37`; `BL:20` (B-9); `BLOCKERS_AND_CARRYFORWARDS.md:27-28` | G7 | OPEN (non-blocking per `CG:37`) |
| OR-12 | **ADRs exercised but not adopted**: ADR-011 (migration 10.0.0 live), ADR-012 (pruning change live), ADR-006 (every production mutation) | G1 cannot pass for the release surface | `verification/adr/README.md:42-48`; `CG:31` | G1 | OPEN |
| OR-13 | Scheduler automation requires the B-1 ADR; unattended system actions without a declared mechanism are refused after ADR011-SA | enabling `night_audit_job` is not available for the first release | `FD:1288`; `BL:12`; FD-P2-05 `FD:1168-1176` | G9 | OPEN (by design) |

## C. Operational risks

| Id | Risk | Consequence | Source | Gate | Status |
|---|---|---|---|---|---|
| OR-14 | **Stale business date** — production `2026-08-10`, 53 days behind calendar on 2026-10-02 | day one requires a catch-up whose method is undefined; every closed-day invariant is anchored to it | `OVERNIGHT_STATE.md`; `PRI:70` (RL-2); `CG:36` | G6, G11 | OPEN |
| OR-15 | Admin "advance-date" force tool marks each skipped day `Skipped` with an override reason, posts no room rent and writes no `AuditLog` row; uses the wall clock | a catch-up by this tool leaves days with no close and no audit row (code reading) | `app/reports.py:3504-3566` | G5, G6 | NOT VERIFIED (code reading) |
| OR-16 | Two operator close entry points: `POST /night-audit/run` (`app/routes.py:4921`) and the staged `/reports/night-audit/run` → `/complete` → `/reopen` (`app/reports.py:2823, 2895, 3104`) | the written daily-close procedure must designate one | FD-P2-05 `FD:1175` | G9, G11 | OPEN |
| OR-17 | **Starting the application mutates data** via standing jobs: `notification_queue_flush` changed three queue rows and wrote three notification logs on production on 2026-09-30, five minutes after start | every start (including `update.bat` health check) is a production mutation of non-financial rows | `20260930_135930_adr011_live_human_provenance/REPORT.md:50-55`; `app/__init__.py:536-598`; `app/services.py:578-581` | G9, G11 | OPEN |
| OR-18 | **Fresh install seeds `night_audit_enabled='true'`** and registers `night_audit_job` at 02:00 | a new install runs an unattended night audit, contrary to FD-P2-05 / FD-009 (code reading) | `app/__init__.py:1897`; `app/services.py:555-570`; `FD:582` | G9, G11 | NOT VERIFIED (code reading) |
| OR-19 | **Fresh-install artefact absent** — `start.bat` directs the operator to `setup.bat`, which is not in the repository or its history | the fresh-install path cannot be rehearsed from the repository | `start.bat:7, 11, 24`; `git log --all -- setup.bat` empty | G11 | OPEN |
| OR-20 | **`update.bat` does not verify package signatures** (only the web updater does, `app/updater.py:198`) and **continues after a failed pre-update backup** | an unsigned or tampered package can be applied; an upgrade can proceed with no rollback point | `update.bat:75-99, 101-160`; `CG:41` ("signed package") | G11 | NOT VERIFIED (code reading) |
| OR-21 | Launchers LF-only (11 tracked files); FD-017 correction not performed; operator-machine execution never rehearsed | launchers may not execute on the operator machine | `FD:793-813`; `MASTER_PLAN.md:158`; `git ls-files --eol` | G9, G11 | OPEN |
| OR-22 | Launchers kill whatever listens on their `PORT` (`stop.bat:18-20`, `update.bat:63-73`, `reset_pms.bat:60-61`); LAN launchers add/delete the machine-global firewall rule `SukoonPMS` | a rehearsal on the production host can stop production or change its firewall rule | `enable_lan.bat:49-50`; `disable_lan.bat:35`; `README.md:41` | G11 | OPEN |
| OR-23 | **Operating backup path unverified** — `shutil.copy2` of the live file, encrypted, no checksum, purged at 30 days; never restored | the backups the system makes are the untested ones | `app/backup_manager.py:206-228, 330`; `PRI:49, 51, 52` (RC-1/3/4); `CG:38` | G8 | FAIL (as recorded) |
| OR-24 | **G10 replay criterion conflicts with governed deltas** — "replay 0" vs two Q06-H2 deltas with the baseline intentionally not re-frozen | G10 cannot be literally satisfied at any tag without a ruling | `CG:40`; `Q06_REGRESSION.md:45`; `CF10_COMPLETION.md:88` | G10, G11, G12 | OPEN |
| OR-25 | **No verified backup of the current production state** — the newest verified backup `12ba7b7e…` (2026-09-30 13:25) predates production `21dc0e97…` (Founder logins + scheduler retry), per committed evidence | current state has no rehearsed recovery point | `ADR011_PRODUCTION_APPLICATION_REPORT.md:64, 84`; `20260930_135930…/REPORT.md:42-55`; `OVERNIGHT_STATE.md` | G8, G11 | OPEN |
| OR-26 | Production anchor drift — `51dd83b7…` → `e67f963b…` → `21dc0e97…` by authorized acts; GM/`inv-run` not re-run on `21dc0e97…` | the certification anchor must be re-established | `OVERNIGHT_STATE.md`; `REVISION_2_REPORT.md:3, 35` (GM not re-run) | G10, G12 | NOT VERIFIED |

## D. Audit / provenance risks

| Id | Risk | Consequence | Source | Gate | Status |
|---|---|---|---|---|---|
| OR-27 | **Webhook audit gaps** — `modify_booking` non-strict (F1 commits an unaudited `rate_per_night` change); `new_booking` / `cancel_booking` write no `AuditLog`, only `WebhookLog`, which is still pruned after 90 days | OTA-originated changes can lose provenance; webhook is armed (`webhook_api_key` set in production Settings) | `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:41-42, 55`; `app/__init__.py:547-571` | G5 | OPEN |
| OR-28 | Audit archival / retention design (B-6) not adopted; ADR-012 PROPOSED | long-run retention undefined; pruning stopped only for `audit_logs` | `BL:17`; FD-P2-02 `FD:1136-1144` | G5 | OPEN |
| OR-29 | Remaining ADR-011 provenance envelope and adoption | G5 condition "provenance envelope per ADR-011" not closed | `ADR011_PRODUCTION_APPLICATION_REPORT.md:101`; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:123-127` | G5 | OPEN |

## E. Governance / control-model risks

| Id | Risk | Consequence | Source | Gate | Status |
|---|---|---|---|---|---|
| OR-30 | **Single-operator model (FD-P2-01)** is a first-release boundary; creating any FrontDesk / Accountant / Housekeeping account before Phase 4 unit 4.2 reopens it; ≥26 report routes and several writers are login-only | any second role makes G4 blocking immediately | `FD:1125-1134`; `CG:34`, `:50` | G4 | OPEN (bounded by ruling) |
| OR-31 | **Maker-checker not implemented (FD-P2-07)** — ₹10,000 threshold and no-self-approval are policy only; ADR-010 PROPOSED, B-2 matrix undefined; under FD-P2-01 an above-threshold maker-checker operation cannot be completed by the sole Admin | operations needing a second person (including reopening a closed day, per the matrix scope) have no defined path | `FD:1189-1198`; `BL:13`; `verification/adr/README.md:46` | G3/G4/G6 operation | OPEN |
| OR-32 | **D11 comparison key** — FD-P2-03 names eight objects; the engine reports 10 (invariant, object) pairs (INV-A02 ×8, INV-A03 ×2 on `extra_charge` 1, 2) | "violation set equals declared set" is ambiguous until ruled | `FD:1154`; `20260930_adr011_production_application/post_inv.log:145-236` | G12 | OPEN |
| OR-33 | Governance record gap N-01 — SR-2 work is on `origin/main` while Round 7 records push/merge as unauthorised; four 2026-08-31 rulings still unrecovered | G2 traceability | `FD:1354`; `OVERNIGHT_STATE.md` (N-01); `FD:155-166` | G2 | OPEN |
| OR-34 | Maker of the certification: FD-P2-03 requires a manual comparison until a certification engine exists | manual error risk; needs a second reviewer | `FD:1154` | G12 | OPEN |

## F. Data-protection and secret-custody risks

| Id | Risk | Consequence | Source | Gate | Status |
|---|---|---|---|---|---|
| OR-35 | **Key derivation coupling** — if `PII_ENCRYPTION_KEY` is unset, both PII field encryption and backup encryption derive from `SECRET_KEY` | rotating or losing `SECRET_KEY` loses PII fields and every `.enc` backup; whether production sets `PII_ENCRYPTION_KEY` is NOT VERIFIED (production `.env` not read) | `app/encryption.py:53-60`; `app/backup_manager.py:50`; `PRI:54` (RC-6) | G8 | OPEN |
| OR-36 | **PII decryption fails open** — a wrong key returns the ciphertext unchanged; a later write re-encrypts it | silent corruption after restore under a different key (code reading) | `app/encryption.py:86-101` | G8, G11 | NOT VERIFIED (code reading) |
| OR-37 | Key custody undocumented (FD-P2-04 condition 11; B-11); `.env` once found inside an archive | off-box restore impossible to prove; secret exposure history | `FD:1163`; `BL:22`; `PRI:54` | G8 | OPEN |
| OR-38 | Update-signing private key custody — only the public key is in the repository (`installer/update_pubkey.pem`); who holds the private key and how packages are signed is not documented in the repository | a signed release cannot be produced or verified reproducibly | `app/updater.py:145, 198`; `CG:41` | G11 | NOT VERIFIED |
| OR-39 | Production guest phone number in git history on `origin`; purge needs a history rewrite / force-push, which no directive permits | personal data persists in the repository | `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:162`; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:130` | — | OPEN |
| OR-40 | Harnesses boot with the production `.env` and real guests; in-place PVF runs rewrite the live `instance/alert_memory.json` | test runs can touch production-adjacent files and log guest data | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:77, 131-132`; `20260930_135930…/REPORT.md:57-59` | G10, G11 | OPEN |
| OR-41 | Copies of live data outside the repository (`FinalGrid/adr011_apply/`, `adr011_preprod/`, `db-backups/`) retained pending Founder disposal | guest PII in uncatalogued locations | `ADR011_PRODUCTION_APPLICATION_REPORT.md:86`; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:78` | — | OPEN |

## G. Non-blocking by existing classification (listed for completeness)

| Id | Risk | Source | Status |
|---|---|---|---|
| OR-42 | Concurrency on SQLite (`with_for_update` no-op), observability (file logs, shallow health endpoint) | `PRI:72-73` (RL-4, RL-5); `BLOCKERS_AND_CARRYFORWARDS.md:36` | OPEN (non-blocking) |
| OR-43 | Cross-implementation divergences (4 DIVERGED, pre-existing) | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:66` | OPEN |
| OR-44 | W-20 repeat-call hour (product finding) | `CARRY_FORWARD_REGISTER.md:26` | OPEN (non-blocking) |
