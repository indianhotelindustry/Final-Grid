# G11 / G12 — Decisions Required

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, G11/G12 preparation workstream; repository `C:/wtov` at `c9eeff0` |
| Kind | Decision package. **No option is chosen here and no recommendation is made.** Options are listed with their recorded consequences only. Every decision belongs to the Founder (FD-004 authority chain, `verification/adr/README.md:9-15`) |
| Companion files | `G11_DEPLOYMENT_REHEARSAL_PLAN.md`, `G11_CHECKLIST.md`, `G11_ROLLBACK_PLAN.md`, `G11_EVIDENCE_REQUIREMENTS.md`, `G12_CERTIFICATION_TEMPLATE.md`, `G12_EVIDENCE_MATRIX.md`, `G12_OPEN_RISKS.md` |

`FD` = `verification/FOUNDER_DECISIONS.md`; `CG` = `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md`.

---

## GD-D1

| Field | Content |
|---|---|
| DECISION ID | GD-D1 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 deployment rehearsal — sequencing |
| QUESTION | May a **non-certifying procedure-proving rehearsal (M-DRY)** be performed on an isolated copy before G3, G5, G6, G8 and G9 pass, or must all G11 activity wait for those gates? |
| WHY REQUIRED | `CG:46` says "G11 ← procedure + rehearsal **after** G3/G5/G6/G8/G9". None of the five is PASS today (`G11_EVIDENCE_REQUIREMENTS.md` §2). A dry run would exercise the procedure, isolation and rollback mechanics but cannot be scored (`CG:50`). Engineering must not infer which reading applies |
| OPTIONS | **A.** No G11 activity until G3/G5/G6/G8/G9 PASS. **B.** Permit M-DRY on an isolated copy at a designated commit, explicitly non-certifying, under a bounded directive; M-CERT later at the release tag. **C.** Permit M-DRY limited to parts that do not depend on the open gates (data copy, upgrade at unchanged code, launchers, rollback mechanics) and exclude day-one / N-day / interrupted close until G6 |
| EVIDENCE | `CG:41`, `:46`, `:50`; `G11_DEPLOYMENT_REHEARSAL_PLAN.md` §2; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:45` (G11 BLOCKED on G3/G5/G6/G8/G9) |
| DEPENDENCIES | GD-D2, GD-D3 (needed for any rehearsal) |
| WHAT IS BLOCKED | Every rehearsal step; writing a procedure that has been exercised at least once |
| WHAT CAN CONTINUE | Drafting the written procedure; G3/G5/G6/G8/G9 workstreams; preparation documents |
| EXACT ACTION AFTER DECISION | If A: record "G11 waits" and keep G11 BLOCKED. If B or C: issue a bounded directive naming mode M-DRY, the commit, the allowed phases of the plan (§5), the machine and folder (GD-D3), the data source (GD-D2) and the evidence pack location; then execute only those phases and stop |

## GD-D2

| Field | Content |
|---|---|
| DECISION ID | GD-D2 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 — rehearsal source data |
| QUESTION | Which database does the rehearsal copy start from, and is a read-only backup run against live production authorized for it? How are the resulting live-data copies retained and disposed of? |
| WHY REQUIRED | G11 requires "a copy of the current instance" (`CG:41`). The newest verified backup (`pms_20260930_132529_adr011-apply-post.db`, `12ba7b7e…`) predates the current production state `21dc0e97…` (`20260930_135930_adr011_live_human_provenance/REPORT.md:42-55`). `tools/backup_db.py` has no `--source` and always reads `<its repo>/instance/pms.db` (`tools/backup_db.py:44-52`), so a fresh backup means running a read-only tool from the live folder — an action on the production folder the standing boundary reserves to the Founder. Copies hold real guest data |
| OPTIONS | **A.** Fresh `tools/backup_db.py` run from the live folder (DB opened `mode=ro`, hashed before/after), then isolated restore — the ADR-011 method. **B.** Use the existing verified backup `12ba7b7e…` and record that it is not the current state. **C.** Synthetic dataset only (no live data); the rehearsal then does not use "a copy of the current instance". For retention: keep copies outside repositories pending Founder disposal (precedent), or dispose at rehearsal close |
| EVIDENCE | `ADR011_PRODUCTION_APPLICATION_REPORT.md:23-24, 64, 86`; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:34-36, 78-79`; `OVERNIGHT_STATE.md` (production `21dc0e97…`, stopped) |
| DEPENDENCIES | GD-D1 |
| WHAT IS BLOCKED | Plan steps A3, A4 (DC-1…DC-6) and everything after |
| WHAT CAN CONTINUE | Environment build on an empty folder; procedure drafting |
| EXACT ACTION AFTER DECISION | Record the chosen source and (for A) an authorization naming: the live folder, `tools/backup_db.py` only, read-only, the expected anchor `21dc0e97…`, abort if it differs; then perform DC-2…DC-6 and record the retention/disposal rule in the pack |

## GD-D3

| Field | Content |
|---|---|
| DECISION ID | GD-D3 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 — rehearsal environment, isolation and key material |
| QUESTION | (1) On which machine does the rehearsal run (production host vs a separate machine; G8 needs a different machine for the off-box restore)? (2) Is the code a separate `git clone` or a `git worktree` of the live repository? (3) Does the rehearsal use its own new `SECRET_KEY` with no production key material, or custody-controlled production key material (`PII_ENCRYPTION_KEY` / `SECRET_KEY`)? |
| WHY REQUIRED | (1) `CG:41` requires "launchers on the operator machine" and FD-P2-04 condition 11 requires "a different machine" (`FD:1163`). (2) Worktrees of this repository share the live folder's `.git` (`git rev-parse --git-common-dir` → `…/SukoonPMS/.git`), and the precedent harness loads the live folder's `.env` (`20260930_adr011_preprod_gate/run_with_app.py:37-39`). (3) With a new key the copy's encrypted PII columns (`app/models.py:180, 543, 1007, 1331, 1351`) and production `.enc` backups are unreadable, and `decrypt_value` fails open, returning ciphertext (`app/encryption.py:86-101`); with production key material, a secret leaves its custody location |
| OPTIONS | (1) **A.** production host, isolated folder, separate port; **B.** separate machine for everything; **C.** production host for launchers only + separate machine for restore/off-box. (2) **A.** separate clone from `origin`; **B.** worktree of the live repository (as in prior sessions). (3) **A.** new rehearsal key only (encrypted columns not representative; recorded); **B.** custody-controlled production key material under a written custody procedure (also needed for G8 condition 11) |
| EVIDENCE | `G11_DEPLOYMENT_REHEARSAL_PLAN.md` §3 E1–E8; `app/backup_manager.py:50`; `app/encryption.py:53-60`; `PRODUCTION_READINESS_INVENTORY.md:54` (RC-6) |
| DEPENDENCIES | GD-D1; G8 key-custody procedure (B-11, `verification/adr/BACKLOG.md:22`) |
| WHAT IS BLOCKED | Plan step A2 and all later steps |
| WHAT CAN CONTINUE | Procedure drafting; listing `.env` keys (names only) for the rehearsal |
| EXACT ACTION AFTER DECISION | Record machine, isolation form and key rule in the authorizing directive; build E2–E6 accordingly; record `.env` key names (never values) in EV-03 |

## GD-D4

| Field | Content |
|---|---|
| DECISION ID | GD-D4 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 / G12 — release identity |
| QUESTION | What is the release candidate (commit), how is the release tag named and versioned, and who is authorized to create and push it? |
| WHY REQUIRED | Production readiness is defined "at a named release tag" (`CG:9`); PASS requires packs "at the release tag" (`CG:50`); the certification entry names the tag (`CG:25`). Only `v2.2.18-preWave1`, `v2.2.18-wave0.5`, `v2.2.18-wave0.5-frozen` exist; `version.txt` is `2.2.18` across every change since baseline; FD-P2-04 condition 5 "release-tag fingerprint" was NOT VERIFIED for lack of a tag (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:36`) |
| OPTIONS | **A.** Tag only after G3/G5/G6/G8/G9 work is merged (single release candidate). **B.** Tag interim candidates for M-DRY rehearsals and a final tag for M-CERT. Version: **A.** bump `version.txt` per tag; **B.** keep `2.2.18` and identify by tag only |
| EVIDENCE | `git tag -l`; `version.txt`; `CG:9, 24, 25, 50` |
| DEPENDENCIES | GD-D1 |
| WHAT IS BLOCKED | M-CERT rehearsal; G10 at a tag; schema fingerprint expectation (G7); G12 |
| WHAT CAN CONTINUE | M-DRY at a designated commit (if GD-D1 allows) |
| EXACT ACTION AFTER DECISION | Record the tag rule; at the chosen point create the tag under a push authorization; record tag, SHA and schema fingerprint in the rehearsal pack |

## GD-D5

| Field | Content |
|---|---|
| DECISION ID | GD-D5 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 — upgrade mechanism |
| QUESTION | Which upgrade mechanism is the property's procedure: (A) git fast-forward in the live folder, (B) signed zip through the web updater, or (C) `update.bat`? Who holds the update-signing private key? |
| WHY REQUIRED | G11 names "pre-update backup → signed package → boot → checks" (`CG:41`). The ADR-011 change used git (`ADR011_PRODUCTION_APPLICATION_REPORT.md:31`). The web updater verifies an Ed25519 manifest signature (`app/updater.py:198`, called at `:415`) and takes an application-path backup (`:487`). `update.bat` performs no signature check (`update.bat:101-160`), continues after a failed backup (`:95, 98`), runs `create_app()` during backup and migration steps (`:85-90, 172-176`) and starts a health-check server (`:209-235`). Only the public key is in the repository (`installer/update_pubkey.pem`) |
| OPTIONS | **A.** git fast-forward (no signed package; G11 wording would need a ruling). **B.** web updater with signed package (needs signing-key custody and a package build procedure). **C.** `update.bat` (unsigned; backup fail-open). Combinations (e.g. B as procedure, A as emergency) |
| EVIDENCE | as above; `G12_OPEN_RISKS.md` OR-20, OR-38 |
| DEPENDENCIES | GD-D4; G8 (pre-update backup path) |
| WHAT IS BLOCKED | Plan steps B3–B6; rollback option CR-A/CR-C selection |
| WHAT CAN CONTINUE | Rehearsal phases that do not upgrade (data copy, launchers at unchanged code) if GD-D1 allows |
| EXACT ACTION AFTER DECISION | Write the chosen mechanism into the procedure; if B, record the signing custody procedure (without key material) and build/sign the candidate package; rehearse B3–B6 with that mechanism only |

## GD-D6

| Field | Content |
|---|---|
| DECISION ID | GD-D6 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 — fresh-install path |
| QUESTION | Is the fresh-install path in scope for the first-release G11 (single existing property), and if so, what is the install artefact and how must a fresh install satisfy FD-P2-05? |
| WHY REQUIRED | G11 requires a "fresh-install path" (`CG:41`; VF-8 `PRODUCTION_READINESS_INVENTORY.md:88`). `start.bat:7, 11, 24` tell the operator to run `setup.bat`, which is not in the repository or its history. On a fresh database `init_data` seeds `night_audit_enabled='true'` (`app/__init__.py:1897`) and the scheduler then registers `night_audit_job` at 02:00 (`app/services.py:555-570`) — contrary to FD-P2-05 (`FD:1170-1175`) and FD-009 (`FD:582`); code reading, NOT VERIFIED at runtime |
| OPTIONS | **A.** In scope: provide/locate the install artefact; the procedure sets `night_audit_enabled=false` before any unattended period, or a code change makes the seed `false` (separate implementation directive). **B.** Out of scope for the first release (existing instance only), recorded as a G11 ruling and an open risk |
| EVIDENCE | `git log --all -- setup.bat` (empty); `installer/` contents; `app/routes.py:44` (setup wizard) |
| DEPENDENCIES | GD-D4; B-4 (two schema mechanisms, `verification/adr/BACKLOG.md:15`) |
| WHAT IS BLOCKED | Plan Phase C |
| WHAT CAN CONTINUE | All other phases |
| EXACT ACTION AFTER DECISION | If A: name the artefact, add Phase C to the directive, and (if a code change) issue its own bounded directive first. If B: record the ruling and mark Phase C NOT APPLICABLE in the pack |

## GD-D7

| Field | Content |
|---|---|
| DECISION ID | GD-D7 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 day-one procedure / G6 |
| QUESTION | How is the 53-day-stale business date (2026-08-10 on 2026-10-02) brought to the operating date on day one, and which close entry point is the FD-P2-05 daily-close procedure? |
| WHY REQUIRED | Day one must "set the business date … run the first close" (`CG:21`); RL-2 (`PRODUCTION_READINESS_INVENTORY.md:70`). Mechanisms present: sequential manual closes; Admin force-advance `POST /night-audit/advance-date` (`app/reports.py:3504-3566`: marks each skipped day `Skipped` with an override reason, posts no room rent, writes no `AuditLog` row, uses the wall clock — code reading); two close entry points (`app/routes.py:4921`; staged `app/reports.py:2823, 2895, 3104`). Phase 3 unit 3.6 (staleness escalation) is unimplemented (`MASTER_PLAN.md:149`). The open day 2026-08-10 carries five of the eight D11 rows (`FD:52-56`) |
| OPTIONS | **A.** Sequential manual closes for each day to the operating date. **B.** Force-advance with skipped days, accepted by ruling (and its audit gap recorded or remedied first). **C.** Defer to the Phase 3 procedure (3.1/3.6) once implemented. Entry point: **A.** `/night-audit/run`; **B.** staged run → complete; plus the reopen route for exceptions |
| EVIDENCE | above; `OVERNIGHT_STATE.md`; `G12_OPEN_RISKS.md` OR-14…OR-16 |
| DEPENDENCIES | G6 (Phase 3); FD-P2-07 matrix for reopen (`FD:1193`); GD-D1 |
| WHAT IS BLOCKED | Plan Phases E and F; the written daily-close procedure; G9.2 |
| WHAT CAN CONTINUE | Phases A, B, D, G, H |
| EXACT ACTION AFTER DECISION | Write the day-one and daily-close procedure with the chosen method and entry point; rehearse it on the copy (Phase E) and record NightAuditLog rows, business date and audit rows per day |

## GD-D8

| Field | Content |
|---|---|
| DECISION ID | GD-D8 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 / G6 — multi-day rehearsal acceptance |
| QUESTION | What is N (consecutive manual closes), what synthetic activity must each day contain, and what is the pass criterion for the reopen and the interrupted-close recovery? |
| WHY REQUIRED | `CG:23`: "multi-day rehearsal on a copy: N consecutive closes, one reopen, one interrupted close recovered, invariants HOLD after each"; `CG:41`: "N-day operation with nightly close". N is not defined anywhere in the repository. Interrupted-close recovery is Phase 3 unit 3.5, not implemented (`MASTER_PLAN.md:149`; FD-P2-05 `FD:1175`) |
| OPTIONS | N: a Founder-chosen number (e.g. a week, a month-end crossing, a GST period). Activity: minimum list in plan F1 or a Founder list. Interrupted close: **A.** require the Phase 3 3.5 recovery procedure (G11 waits for G6); **B.** rehearse the current behaviour and record it without a pass criterion (M-DRY only) |
| EVIDENCE | `CG:23, 41`; `G11_DEPLOYMENT_REHEARSAL_PLAN.md` Phase F |
| DEPENDENCIES | GD-D7; G6; SR-1 (OR-04) and K-7 (OR-05) for a readable invariant verdict on new activity |
| WHAT IS BLOCKED | Plan Phase F; EV-15/EV-16 |
| WHAT CAN CONTINUE | Other phases |
| EXACT ACTION AFTER DECISION | Record N, the activity script requirements and the reopen / interrupted-close criteria in the directive; write the activity script with fictitious guests only |

## GD-D9

| Field | Content |
|---|---|
| DECISION ID | GD-D9 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G10 inside G11; G12 regression record |
| QUESTION | How is "G10 on the rehearsal copy" judged (a) after operations have changed the copy, when Golden Master surfaces at the frozen business date no longer apply, and (b) for replay, where `CG:40` requires "replay 0" but replay reports exactly the two governed Q06-H2 deltas and the baseline is intentionally not re-frozen? |
| WHY REQUIRED | Without a rule, G10 cannot be scored at any tag and every G11 step "followed by G10" is unreadable. Replay status: FAIL — expected, governed (`20260923_q06_fix/Q06_REGRESSION.md:36-45`; `CF10_COMPLETION.md:88`); "a baseline update, if ever wanted, is a separate, later, explicitly-authorized action" (`Q06_REGRESSION.md:45`). GM `phase1_aa6d9e91` is captured against production data at a frozen business date (`FD:1082-1086`) |
| OPTIONS | (a) **A.** GM before operations only (immediately after upgrade and after rollback); after operations rely on invariants + digests; **B.** capture a rehearsal-specific master before the N-day run and verify against it; **C.** other Founder rule. (b) **A.** declare the two Q06 deltas as a governed exception at certification (like FD-P2-03); **B.** authorize a replay baseline re-freeze under its own directive; **C.** read "replay 0" as "0 undeclared" by ruling |
| EVIDENCE | `CG:40-41`; `G12_EVIDENCE_MATRIX.md` G10; `G12_OPEN_RISKS.md` OR-24 |
| DEPENDENCIES | Q06-H1/H3 (`FD:1219-1246`); GD-D4 |
| WHAT IS BLOCKED | Plan steps DC-6, B9, I-1, rollback DR-8; G10 at tag; G12 §6 |
| WHAT CAN CONTINUE | Running the suites and recording raw results without a verdict |
| EXACT ACTION AFTER DECISION | Record the rule; for (b)B issue the re-freeze directive; then define the expected-result tables in EV-06/EV-11 accordingly |

## GD-D10

| Field | Content |
|---|---|
| DECISION ID | GD-D10 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 / G7 — migration authority for the release |
| QUESTION | If the release contains schema changes (likely for G8 — an integrity record for the operating backup path; possibly Phase 3), are they delivered through the inline boot-time registry under a per-migration authorization as 10.0.0 was, or must B-4 (single schema authority, end of unattended boot-time execution) be decided first? |
| WHY REQUIRED | FD-007 requires Founder-approved scope, PD-004, PD-005, PD-006 and a defined rollback for any production migration (`FD:527-541`); B-4 undecided (`verification/adr/BACKLOG.md:15`); "a boot-time migration committed to `main` would be applied to production at the next application start" (`FD:1289`); `update.bat` also triggers migrations during its backup step (`update.bat:85-90`). G7 "B-4 open (E, only bites on a schema change)" (`CG:37`). Code rollback does not undo migrations (`G11_ROLLBACK_PLAN.md` T1) |
| OPTIONS | **A.** Per-migration authorization through the inline registry (10.0.0 precedent). **B.** Decide B-4 before any further schema change. **C.** Keep the first release schema-free relative to production (no migration beyond 10.0.0) |
| EVIDENCE | above; `ADR011_PRE_PRODUCTION_GATE_REPORT.md:113-114`; FD-005 state note (`FD:491-496`) |
| DEPENDENCIES | G8 design (recovery-hardening directive, `FD:1165`); GD-D4 |
| WHAT IS BLOCKED | M-CERT upgrade path (Phase B) for any release with migrations; rollback T1b rehearsal design |
| WHAT CAN CONTINUE | M-DRY at code with no pending migration (`c9eeff0`: `app/` identical to production's `c703150`) |
| EXACT ACTION AFTER DECISION | Record the rule; for each migration in the release add an old-code-on-new-schema rehearsal (rollback T1) and the FD-007 evidence list to the rehearsal directive |

## GD-D11

| Field | Content |
|---|---|
| DECISION ID | GD-D11 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G11 rollback / production deployment |
| QUESTION | (1) Is the in-place restore into `instance/pms.db` (a PD-004 act) pre-authorized as part of a deployment directive, so it can be executed at a rollback decision point without a new authorization? (2) After go-live, may a data rollback discard real post-upgrade transactions and audit rows, or is forward-fix the only permitted path? |
| WHY REQUIRED | `tools/restore_db.py` refuses `instance/` by design (`tools/restore_db.py:18-21`); the precedent rollback path was "defined here but has not been authorized or rehearsed on the live path" (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:115-121`). A restore after operation deletes audit history written after the backup, which FD-008 protects (`FD:561`) |
| OPTIONS | (1) **A.** pre-authorize within each deployment directive, bounded to the named pre-update backup; **B.** separate authorization at the moment of need (production stays stopped meanwhile). (2) **A.** data rollback only before the first post-upgrade financial transaction; **B.** data rollback allowed with re-entry of post-upgrade transactions and retention of the discarded DB as evidence; **C.** forward-fix only after go-live |
| EVIDENCE | `G11_ROLLBACK_PLAN.md` §3, §6 (T2), §7 |
| DEPENDENCIES | G8 (verified pre-update backup); GD-D5 |
| WHAT IS BLOCKED | Finalising RB-DP2…RB-DP6 defaults; the rollback section of the written procedure |
| WHAT CAN CONTINUE | Rollback rehearsal on a copy (Phase H) if GD-D1 allows |
| EXACT ACTION AFTER DECISION | Write the decision-point defaults into `G11_ROLLBACK_PLAN.md` §7 successor in the procedure; rehearse the chosen path in Phase H |

## GD-D12

| Field | Content |
|---|---|
| DECISION ID | GD-D12 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G9 / G11 — scheduler jobs at start |
| QUESTION | Which standing scheduler jobs may run (a) during the rehearsal and (b) in the first release: `notification_queue_flush`, `daily_backup_job`, `log_pruning_job`, `predictive_maintenance_job`? Is their start-up mutation accepted and recorded, or must a control be built first? |
| WHY REQUIRED | `create_app()` always starts the scheduler (`app/services.py:578-581`); the jobs have no settings switch (`app/__init__.py:536-598`); `notification_queue_flush` mutated production rows five minutes after a start on 2026-09-30 (`20260930_135930_adr011_live_human_provenance/REPORT.md:50-55`). G9 requires "the scheduler starting only the jobs the production settings allow" (`CG:13`) and a job table per production setting (`CG:39`) |
| OPTIONS | **A.** Accept all four as-is; document each job's effect; record every start-up mutation. **B.** Require a settings switch per job (separate implementation directive) before G11. **C.** Accept some, control others (Founder list) |
| EVIDENCE | above; RL-1 `PRODUCTION_READINESS_INVENTORY.md:69`; `G12_OPEN_RISKS.md` OR-17 |
| DEPENDENCIES | B-1 (`verification/adr/BACKLOG.md:12`) for any financial automation; FD-009 (`FD:582`) |
| WHAT IS BLOCKED | G9 job-table evidence; plan E9 classification rules |
| WHAT CAN CONTINUE | Rehearsal with jobs running and mutations recorded on the copy (if GD-D1 allows) |
| EXACT ACTION AFTER DECISION | Record the job list and accepted effects in the procedure; if B/C, issue the implementation directive; verify job registration at every boot (OC-05) |

## GD-D13

| Field | Content |
|---|---|
| DECISION ID | GD-D13 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G12 — FD-P2-03 declared-exception comparison |
| QUESTION | For the assertion "the `inv-run` violation set equals the declared set", is the comparison made on **distinct objects** (eight) or on **(invariant, object) pairs**, and if pairs, is INV-A03 on `extra_charges` 1 and 2 part of the declared exception? |
| WHY REQUIRED | FD-P2-03 names "the eight objects" (`FD:1154`). The engine on production reported INV-A02 VIOLATED on all eight and INV-A03 VIOLATED on `extra_charge` 1 and 2 — 10 pairs over 8 objects (`20260930_adr011_production_application/post_inv.log:99-236`). INV-A03 is tiered RELEASE_BLOCKING, INV-A02 CERTIFICATION_BLOCKING (same log, `:115`, `:172`). FD-010 records both INV-A02 and INV-A03 as the expected consequence (`FD:633-637`) |
| OPTIONS | **A.** Object-level: V = distinct objects in any violated invariant; must equal the eight. **B.** Pair-level with a declared pair list: INV-A02 × 8 and INV-A03 × 2. **C.** Pair-level with INV-A02 × 8 only (INV-A03 then needs its own ruling) |
| EVIDENCE | above; `G12_CERTIFICATION_TEMPLATE.md` §4.3–§4.4 |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | G12 §4.4 result; the D11 part of every G10/G11 invariant check (AB-08) |
| WHAT CAN CONTINUE | All rehearsal work; the comparison can be computed in both forms meanwhile |
| EXACT ACTION AFTER DECISION | Record the form; fill `G12_CERTIFICATION_TEMPLATE.md` §4.4 "Comparison form ruled"; use the same form in every rehearsal `inv-run` check |
