# G12 Evidence Matrix — gate × required evidence × current evidence × status

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, G11/G12 preparation workstream; repository `C:/wtov` at `c9eeff0` |
| Kind | Preparation only. Maps what each gate requires to the newest committed evidence that bears on it. **No harness was run and production was not opened by this work.** |
| Reading rule | `CERTIFICATION_GATES.md:50`: a gate is PASS only with a committed evidence pack **at the release tag**. No release tag exists (`git tag -l` → `v2.2.18-preWave1`, `v2.2.18-wave0.5`, `v2.2.18-wave0.5-frozen` only). Therefore **no gate can be scored PASS for certification today**; the "status" column reports the state of the newest evidence, not a certification result |
| Vocabulary | PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE. "PASS per pack" = the cited pack records PASS for that sub-item; it was not re-verified here |

Path prefix: `verification/evidence/` unless stated. `CG` = `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md`; `FD` = `verification/FOUNDER_DECISIONS.md`.

## G1 Architecture (`CG:31`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Every ADR the release exercises ADOPTED | `verification/adr/README.md:35-51`: adopted 001, 002, 003, 004, 005, 007, 008; **ADR-006 PROPOSED** (migration mechanism open), **ADR-009 PROPOSED FOR ADOPTION**, **ADR-010 PROPOSED**, **ADR-011 PROPOSED FOR ADOPTION**, **ADR-012 PROPOSED** | OPEN |
| ADR-011 adoption (exercised: migration 10.0.0 is on production) | ADR011-SA ruled (`FD:1267-1290`); "ADR-011 is not edited by this entry; reconciliation applied at its adoption review" (`FD:1287`); `ADR011_PRE_PRODUCTION_GATE_REPORT.md:123-127` (readings need confirmation) | OPEN |
| ADR-012 adoption (exercised: pruning change `b0d3054`) | FD-P2-02 (`FD:1136-1144`); ADR-012 still PROPOSED | OPEN |
| ADR-006 (exercised by every production mutation; B-4) | `verification/adr/BACKLOG.md:15` | OPEN |

## G2 Governance (`CG:32`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Decisions durable, evidence committed, no rewrite | `CG:32` PASS at `a84566ae`; Founder rounds 3–7 recorded (`FD:1114-1354`) | PASS as recorded at `a84566ae`; NOT VERIFIED at `c9eeff0` |
| Four 2026-08-31 rulings | unrecovered — recorded gap (`FD:155-166`, `:862`) | OPEN (recorded as non-blocking at `CG:32`) |
| Authorization record for SR-2 push/merge to `origin/main` | not in `FOUNDER_DECISIONS.md`; Round 7 says push/merge unauthorised (`FD:1354`) while `origin/main` = `c9eeff0` contains it (`overnight_execution/OVERNIGHT_STATE.md`, N-01) | OPEN |

## G3 Financial integrity (`CG:33`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Attribution universal | Phase 1 acceptance (`FD:1065-1074`); `20260910_phase1_acceptance/` | PASS per pack (at `aa6d9e91`) |
| Strict coupling 24/24 (CF-10) | `20260930_cf10_completion/CF10_COMPLETION.md:27, 110`; `RESULT.json` | PASS per pack (at `61286b7`) |
| Business-date dating at all writers (K-7) | none — Phase 3 not started (`MASTER_PLAN.md:146-151`; `PRODUCTION_READINESS_INVENTORY.md:11`) | OPEN |
| Credit/voucher paths (CF-11) | `CF10_COMPLETION.md:111` | PASS per pack |
| GST engines agree (Q06) | `20260923_q06_fix/`; Q06-H1/H2/H3 (`FD:1219-1246`) | PASS per pack (code); historical record preserved by ruling |
| SR-1 (INV-B06) | ruled in principle FD-P2-06 (`FD:1178-1187`); no rule text | OPEN |
| SR-2 (INV-D02) | `20260930_sr2_inv_d02/REVISION_2_REPORT.md`; `20261001_120800_inv_commission/`; SR2-RULE / SR2-REV2 (`FD:1292-1354`) | PASS per pack (verification framework only) |

## G4 Authorization (`CG:34`) — blocking only if multi-role (MP-D9)

| Required evidence | Current evidence | Status |
|---|---|---|
| Matrix for roles in use | FD-P2-01 single operator / Admin for the first release (`FD:1125-1134`) → advisory | NOT APPLICABLE as blocking while FD-P2-01 holds |
| Folio endpoints fail-closed | `20260831_phase2a_folio_authz/`; 29/29 re-run 2026-09-30 (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:58`) | PASS per pack |
| Writers and ≥26 report routes | login-only (`CG:34`); Phase 4 not started (`MASTER_PLAN.md:153-158`) | OPEN |
| Negative matrix per role (CF-5) | `20260910_phase2_founder_resolution/CARRY_FORWARD_REGISTER.md:9` | OPEN |

## G5 Auditability (`CG:35`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Strict coupling | as G3 | PASS per pack |
| `audit_logs` never auto-deleted | `b0d3054`; `20260910_retention_control/RETENTION_CONTROL_TEST.md`; current prune loop covers only `WebhookLog`, `NotificationLog` (`app/__init__.py:547-571`) | PASS per pack |
| Provenance envelope per ADR-011 | `20260930_adr011_implementation/`, `20260930_adr011_preprod_gate/` (77/77), `20260930_adr011_production_application/` (APPLIED AND VERIFIED), `20260930_135930_adr011_live_human_provenance/` (PASS); ADR-011 not adopted; "remaining provenance envelope" open (`ADR011_PRODUCTION_APPLICATION_REPORT.md:101`) | OPEN |
| Webhook audit coverage | `modify_booking` non-strict; `new_booking`/`cancel_booking` no AuditLog (`20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:41-42, 55`) | OPEN |
| Archival / retention design (B-6) | `verification/adr/BACKLOG.md:17` | OPEN |

## G6 Business-date integrity (`CG:36`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Single derivation (3.1) | none | OPEN |
| No wall-clock financial dating (K-7) | none | OPEN |
| Close idempotency / reopen / interrupted-close (3.2–3.5) | none | OPEN |
| Staleness escalation (3.6) | none; production 53 days stale (`OVERNIGHT_STATE.md`) | OPEN |
| N7 multi-day sequence (3.8) | none | OPEN |
| Gate as recorded | `CG:36` | FAIL |

## G7 Database integrity (`CG:37`)

| Required evidence | Current evidence | Status |
|---|---|---|
| `foreign_key_check` = 0 | production post-10.0.0: whole-database `foreign_key_check` (FK on) empty (`ADR011_PRODUCTION_APPLICATION_REPORT.md:46`) | PASS per pack (2026-09-30 state `e67f963b…`); NOT VERIFIED on current `21dc0e97…` |
| Schema fingerprint = tag expectation | no tag; FD-P2-04 cond 5 "release-tag fingerprint" NOT VERIFIED (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:36`) | NOT VERIFIED |
| No pending migration at boot | production second start: 10.0.0 not re-applied (`ADR011_PRODUCTION_APPLICATION_REPORT.md:54`) | PASS per pack (at `e7086da` code) |
| Migration authority decided before schema change (B-4) | undecided (`verification/adr/BACKLOG.md:15`); 10.0.0 applied through the inline registry under a specific authorization (`ADR011_PRODUCTION_APPLICATION_REPORT.md:10`) | OPEN |

## G8 Recovery (`CG:38`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Operating backup path = backup API + integrity record | `app/backup_manager.py:206-208` still `shutil.copy2`; file unchanged since `b5b2514` | FAIL |
| Restore of application `.enc` off-box with key custody (cond 11) | none | OPEN |
| Verified-state definition | FD-P2-04 adopted (`FD:1157-1166`); B-5 closed | PASS (decision recorded) |
| Tool-path rehearsals | `20260908_recovery_foundation/` (RR-20260908-01); `20260930_adr011_preprod_gate/restore/`; `20260930_adr011_production_application/restore_pre*`, `restore_post*` | PASS per pack for the PD-005 minimum (conditions 1–7, 9, 10) |
| Retention of pre-update backups (cond 12; RC-4) | app backups purged at 30 days (`app/backup_manager.py:228, 330`); tool backups kept in `db-backups/` by convention (B-11) | OPEN |
| Gate as recorded | `CG:38` | FAIL |

## G9 Reliability (`CG:39`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Scheduler job table per production setting | jobs observed at production start (`ADR011_PRODUCTION_APPLICATION_REPORT.md:36`); no job-table pack | OPEN |
| Night-audit mode ruled | FD-P2-05 manual (`FD:1168-1176`); production `night_audit_enabled=false` (`OVERNIGHT_STATE.md`) | PASS (ruling recorded) |
| Written daily-close procedure | absent (`FD:1175` requires it) | OPEN |
| Launchers reproducible (FD-017) | 11 tracked launchers LF-only at `c9eeff0` (`git ls-files --eol`); FD-017 correction not performed (`MASTER_PLAN.md:158`) | OPEN |
| Observability | advisory (`CG:39`) | NOT APPLICABLE as blocking |

## G10 Regression verification (`CG:40`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Golden Master 0 undeclared | `20260930_024153_gm_verify_phase1_aa6d9e91/` (158/158 at `61286b7`); production post-10.0.0 158/158 (`ADR011_PRODUCTION_APPLICATION_REPORT.md:67`); none on the current production state `21dc0e97…`; none at `c9eeff0` | NOT VERIFIED at any candidate tag |
| Replay 0 | FAIL — exactly the two governed Q06-H2 deltas; baseline not re-frozen (`20260923_q06_fix/Q06_REGRESSION.md:36-45`; `CF10_COMPLETION.md:88`) | OPEN (criterion needs ruling — GD-D9) |
| Invariants declared movement only | production post-10.0.0: INV-A02 ×8, INV-A03 ×2, all D11 (`20260930_adr011_production_application/post_inv.log:99-236`); `20261001_120800_inv_run_production` (SR-2 runs) | OPEN (comparison form — GD-D13) |
| Five datasets PASS | `20260930_sr2_inv_d02/final_6e46e2c_rev2/` `ds_run rc=0` | PASS per pack (framework commit `6e46e2c`) |
| Phase 2a matrix 29/29 | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:58` | PASS per pack |
| Q14 as declared | Phase 1 acceptance (`FD:1074`) | PASS per pack (at `aa6d9e91`); NOT VERIFIED since |
| Production anchor unchanged | anchor moved by authorized acts: `51dd83b7…` → `e67f963b…` (10.0.0) → `21dc0e97…` (Founder logins + scheduler notification retry) | OPEN — new anchor must be named at certification |

## G11 Deployment rehearsal (`CG:41`)

| Required evidence | Current evidence | Status |
|---|---|---|
| Rehearsal packs (upgrade, fresh install, launchers, day-one, N-day, rollback, G10 after each) | none | BLOCKED (prerequisites G3/G5/G6/G8/G9 not passed; `CG:46`) |
| Written procedure | none (`docs/` absent); this pack's drafts are inputs only | OPEN |
| Gate as recorded | `CG:41` FAIL — never performed | FAIL (as recorded) |

## G12 Production certification (`CG:42`)

| Required evidence | Current evidence | Status |
|---|---|---|
| G1–G11 as required | above | BLOCKED |
| D11 verdict ruled | FD-P2-03 (`FD:1146-1155`) — declared-exception register; manual comparison | PASS (ruling recorded); register not yet built (`G12_CERTIFICATION_TEMPLATE.md` §4 is a blank template) |
| Founder certification entry | none | BLOCKED |
