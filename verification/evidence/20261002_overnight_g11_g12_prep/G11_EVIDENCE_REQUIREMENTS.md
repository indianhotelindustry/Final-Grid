# G11 Evidence Requirements and Prerequisites — PREPARATION DRAFT

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, G11/G12 preparation workstream; repository `C:/wtov` at `c9eeff0` |
| Kind | Preparation only. Lists the evidence G11 needs and the prerequisites that must PASS first. Statuses are taken from committed evidence at `c9eeff0` and from `verification/evidence/overnight_execution/OVERNIGHT_STATE.md`; **nothing was re-run by this work** (no application start, no harness run, production not opened) |
| Scoring rule | "A gate is PASS only with a committed evidence pack at the release tag" (`CERTIFICATION_GATES.md:50`) |

## 1. What the gate document says G11 depends on (verified)

- `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:46`: "**G11 ← procedure + rehearsal after G3/G5/G6/G8/G9**". Verified verbatim.
- `CERTIFICATION_GATES.md:41`: each rehearsal element is "followed by G10 on the rehearsal copy"; evidence = "rehearsal packs; written procedure (`docs/RELEASE.md` or successor)".
- Blockers mapped to G11: PB-3 (night-audit semantics and rehearsal → G6, G11), PB-7 (launchers → G9, G11), PB-9 (deployment and rollback procedure → G11) (`BLOCKERS_AND_CARRYFORWARDS.md:11, 15, 17`).
- Carry-forward CF-9 "Deployment verification" → owner "release decision (MP-D3 / PD controls); G11" (`20260910_phase2_founder_resolution/CARRY_FORWARD_REGISTER.md:11`); deployment rehearsal register row (`:23`).
- FD-P2-05: "a written daily-close procedure is required (deployment rehearsal G11)" (`FOUNDER_DECISIONS.md:1175`).

Note on wording: the G11 row lists G10 as an *in-rehearsal* step, not as a prerequisite; `:46` does not list G1, G2, G4 or G7. G7 becomes relevant if the release contains a schema change (`CERTIFICATION_GATES.md:37` "B-4 open (E, only bites on a schema change)"; FD-007).

## 2. Gate prerequisites for G11 — current status

| # | Prerequisite | Must be | Current status (2026-10-02) | Evidence for the status |
|---|---|---|---|---|
| P-G3 | **G3 Financial integrity** | PASS | **OPEN** | see sub-items |
| P-G3.1 | Strict audit coupling at all 24 writers (CF-10) | PASS | PASS per pack (242/242 at `61286b7`) | `20260930_cf10_completion/CF10_COMPLETION.md:27, 110` |
| P-G3.2 | Credit/voucher paths functional (CF-11) | PASS | PASS per pack (cf11 48/48) | `CF10_COMPLETION.md:111` |
| P-G3.3 | GST engines agree (Q06 explained) | PASS | code fix PASS per pack (Q06-H2 at `60abea6`); historical sealed record preserved by ruling (Q06-H1/H3) | `20260923_q06_fix/`; `FOUNDER_DECISIONS.md:1219-1246` |
| P-G3.4 | SR-2 (INV-D02) resolved | PASS | implemented and verified in the verification framework (`6e46e2c`, Revision 2); Founder confirmation SR2-REV2; on `origin/main` `c9eeff0`. Not re-verified here | `20260930_sr2_inv_d02/REVISION_2_REPORT.md`; `FOUNDER_DECISIONS.md:1323-1354` |
| P-G3.5 | SR-1 (INV-B06) resolved | PASS | **OPEN** — ruled in principle (FD-P2-06), no rule text ruled | `FOUNDER_DECISIONS.md:1178-1187`; `OVERNIGHT_STATE.md` (SR-1 row, DQ-01) |
| P-G3.6 | Business-date dating at all writers (K-7) | PASS | **OPEN** — Phase 3 not started | `PRODUCTION_READINESS_INVENTORY.md:11` (FI-3); `ADR011_PRE_PRODUCTION_GATE_REPORT.md:44`; `OVERNIGHT_STATE.md` |
| P-G5 | **G5 Auditability** | PASS | **OPEN** | see sub-items |
| P-G5.1 | Strict coupling (G3) | PASS | PASS per pack (P-G3.1) | as above |
| P-G5.2 | `audit_logs` never auto-deleted | PASS | PASS per pack — `AuditLog` removed from the prune loop at `b0d3054` (FD-P2-02); current loop prunes only `WebhookLog`, `NotificationLog` (`app/__init__.py:547-571`) | `20260910_retention_control/` |
| P-G5.3 | Provenance envelope per ADR-011 | PASS | **OPEN** — ADR011-SA implemented and applied to production (10.0.0), live HUMAN provenance PASS; **ADR-011 still PROPOSED FOR ADOPTION**; "remaining provenance envelope" open | `verification/adr/README.md:47`; `ADR011_PRODUCTION_APPLICATION_REPORT.md:97-102`; `20260930_135930_adr011_live_human_provenance/REPORT.md` |
| P-G5.4 | Webhook audit gaps classified | — | **OPEN** — webhook `modify_booking` non-strict (F1 commits an unaudited rate change); `new_booking`/`cancel_booking` write no `AuditLog` | `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:41-42, 55`; `ADR011_PRODUCTION_APPLICATION_REPORT.md:105` |
| P-G6 | **G6 Business-date integrity** | PASS | **FAIL** (as recorded; no Phase 3 evidence since) — single derivation, closed/reopen/interrupted-close semantics, staleness escalation, N7 multi-day sequence all absent; production business date 2026-08-10, 53 days behind calendar | `CERTIFICATION_GATES.md:36`; `MASTER_PLAN.md:146-151`; `OVERNIGHT_STATE.md` |
| P-G8 | **G8 Recovery** | PASS | **FAIL** (as recorded) — operating backup path unchanged since baseline (`shutil.copy2`, `app/backup_manager.py:206-208`; `git log -- app/backup_manager.py` → only `b5b2514`); no application `.enc` restore rehearsed; no off-box restore; key custody undocumented. B-5 closed by FD-P2-04. Tool path (`tools/backup_db.py` / `restore_db.py`) PASS for the PD-005 minimum in four rehearsals (RR-20260908-01, RR-20260930-ADR011, -APPLY, -POST) | `CERTIFICATION_GATES.md:38`; `FOUNDER_DECISIONS.md:1157-1166`; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:36` (conditions 5 and 11 NOT VERIFIED) |
| P-G9 | **G9 Reliability** | PASS | **OPEN** | see sub-items |
| P-G9.1 | Launchers reproducible (FD-017) | PASS | **OPEN** — FD-017 CRLF correction not performed; all 11 tracked launchers LF-only at `c9eeff0` (`git ls-files --eol` → `i/lf w/lf`); launcher rehearsal never performed (NOT VERIFIED on the operator machine) | `FOUNDER_DECISIONS.md:793-813`; `MASTER_PLAN.md:158` |
| P-G9.2 | Night-audit automation controlled or manual by ruling | PASS | ruled manual (FD-P2-05); production `night_audit_enabled=false`; **written daily-close procedure absent → OPEN** | `FOUNDER_DECISIONS.md:1168-1176`; `OVERNIGHT_STATE.md` |
| P-G9.3 | Scheduler jobs documented per production setting | PASS | **OPEN** — no job table pack; jobs observed at production first start: `daily_backup_job`, `log_pruning_job`, `notification_queue_flush`, `predictive_maintenance_job` | `ADR011_PRODUCTION_APPLICATION_REPORT.md:36`; `RL-1` `PRODUCTION_READINESS_INVENTORY.md:69` |
| P-PROC | **Written procedure** (`docs/RELEASE.md` or successor), adopted | exists, Founder-adopted | **OPEN** — absent (`docs/` does not exist at `c9eeff0`); this pack's plan is a draft input only | `CERTIFICATION_GATES.md:41`; RL-7 `PRODUCTION_READINESS_INVENTORY.md:75` |
| P-G7c | (conditional) **B-4 / migration authority** if the release contains a schema change | decided | **OPEN** — B-4 undecided; 10.0.0 was applied through the inline boot-time registry under a specific Founder authorization | `verification/adr/BACKLOG.md:15`; `FOUNDER_DECISIONS.md:1289`; `ADR011_PRODUCTION_APPLICATION_REPORT.md:10` |

## 3. Non-gate prerequisites for executing any rehearsal

| # | Prerequisite | Status | Reference |
|---|---|---|---|
| X-1 | Founder directive authorizing the rehearsal (mode, steps, machine) | NOT AUTHORIZED | FD-004 chain (`verification/adr/README.md:9-15`) |
| X-2 | Ruling on rehearsal mode before prerequisites pass | OPEN | GD-D1 |
| X-3 | Source data method (and authorization to read production for a fresh backup) | OPEN / NOT AUTHORIZED | GD-D2 |
| X-4 | Environment, isolation form, key material | OPEN | GD-D3 |
| X-5 | Release candidate identity / tag | OPEN — no release tag exists | GD-D4 |
| X-6 | Upgrade mechanism and signing-key custody | OPEN | GD-D5 |
| X-7 | Fresh-install scope and artefact | OPEN — `setup.bat` absent | GD-D6 |
| X-8 | Day-one catch-up method and close entry point | OPEN | GD-D7 |
| X-9 | N and multi-day acceptance | OPEN | GD-D8 |
| X-10 | G10-on-rehearsal-copy acceptance (GM after operations; replay vs governed Q06 deltas) | OPEN | GD-D9 |
| X-11 | Rollback authorization model | OPEN | GD-D11 |
| X-12 | Scheduler jobs allowed during rehearsal / first release | OPEN | GD-D12 |

## 4. Evidence artefacts G11 requires

All artefacts live in one pack per rehearsal run, committed under a commit authorization and never edited afterwards (SC-4; `CERTIFICATION_GATES.md:24`). Machine-readable results are built by a script from the files in the pack (precedent `build_result.py` in `20260930_adr011_production_application/`).

| Id | Artefact | Content | Plan step | Satisfies |
|---|---|---|---|---|
| EV-01 | `AUTHORIZATION.md` | directive id, quoted authorization, mode, scope, named steps | A1 | X-1 |
| EV-02 | Procedure document + SHA-256 | the adopted `docs/RELEASE.md` (or successor) used for the run | — | R8, P-PROC |
| EV-03 | `environment.json` | machine, folder, clone origin and HEAD, `pip freeze`, `.env` **key names only**, port, isolation checks (OC-02, OC-16) | A2 | E1–E12 |
| EV-04 | `prod_identity_before.json`, `prod_identity_after.json` | read-only SHA-256, size, journal mode, business date, `night_audit_enabled`, latest migration (only if authorized) | A3, I-2 | OC-01 |
| EV-05 | backup manifest, restore manifest, `fd_p2_04_conditions.json` | per-condition PASS / NOT VERIFIED with reason | DC-2…DC-5 | R9, FD-P2-04 |
| EV-06 | baseline PVF packs on the copy | `inv-run`, `gm-verify`, `replay-verify`, cross-implementation | DC-6 | R7 |
| EV-07 | `pre_state.json` | per-table digests of every table; audit digest | A5 | OC-10 |
| EV-08 | upgrade record | package, signature verification output, file list, protected-path check, boot logs (first and second), `schema_migrations` before/after, jobs, settings | B2–B6 | R1 |
| EV-09 | `smoke.json` | health, login, unauthenticated redirect, version, digest before/after | B7 | R1 |
| EV-10 | `post_upgrade_state.json` + classification table | changed tables and cause | B8 | R1 |
| EV-11 | G10 packs after upgrade | per GD-D9 | B9 | R7 |
| EV-12 | fresh-install record | artefact hash, boot log, schema fingerprint, settings incl. `night_audit_enabled`, users | C1–C5 | R2 |
| EV-13 | launcher record | per launcher: CRLF/line counts, where executed, transcript, port observed | D1–D5 | R3 |
| EV-14 | day-one record | business date before/after, method, NightAuditLog rows, audit rows, users/roles, FD-P2-01 boundary statement | E-1…E-5 | R4 |
| EV-15 | per-day records (N) | activity script id, close record, business date, `inv-run` pack per day | F1–F3 | R5 |
| EV-16 | reopen and interrupted-close records | reason retained, reopen log row, recovery steps, post-recovery invariants | F4–F5 | R5 |
| EV-17 | restore rehearsal records | tool artifact, application `.enc` artifact, off-box run (condition 11) | G-1, G-2 | R9, G8 |
| EV-18 | rollback record | DR-1…DR-9, old-code-on-new-schema observations (T1), rows lost (T2), G10 after | Phase H | R6 |
| EV-19 | outbound / notification record | `notification_logs` / `notification_queue` changes during the run; outbound block status | OC-07 | AB-04 |
| EV-20 | redaction log | guest-field scan method and count of redactions | I-3 | E12 |
| EV-21 | `RESULT.json` + `build_result.py` | built from EV files only | I-3 | scoring |
| EV-22 | filled `G11_CHECKLIST.md` | signed | all | — |
| EV-23 | deviations / aborts record | AB ids triggered, procedure defects | all | — |

## 5. What would still not be shown by a PASSing G11

- PostgreSQL (BLOCKED on authorizations, `ADR011_PRE_PRODUCTION_GATE_REPORT.md:81-98`).
- Multi-role authorization (FD-P2-01 boundary).
- The production upgrade itself (a separate PD-004/PD-005 act under FD-007 and FD-019).
