# GATES — DECISIONS REQUIRED (GT-D1 … GT-D16)

| | |
|---|---|
| Prepared | 2026-10-02, analysis only, `C:/wtov` at `c9eeff0` |
| Authority to decide | the Founder only. Nothing here is a decision. OPTIONS are listed without a recommendation unless one is stated as ANALYSIS |
| Register | `GATE_STATUS_REGISTER.md` · `G3_MATRIX.md` · `G6_DEPENDENCY_MAP.md` · `G6_GATE_DEFINITIONS_MISSING.md` |

Index

| ID | Workstream | One-line question |
|---|---|---|
| GT-D1 | G3 / G6 | May G3 PASS with K-7 delivered as Phase 3 unit 3.1 while G6 remains open? |
| GT-D2 | SR-1 / G3 | What is the exact INV-B06 rule text (advance window, refund basis, purposes, seeds), and is it sequenced before or after K-7? |
| GT-D3 | Master Plan / SR-1 | Does FD-P2-06 carve out Phase 6's "Not touched: invariant semantics", and should that be recorded? |
| GT-D4 | Governance / G2 | Who authorized pushing/merging SR-2 to `origin/main`, given Round 7 says it is unauthorised? |
| GT-D5 | Master Plan / Phase 3 | What do Phase Gates A–H mean now: restate them, retire them, or use per-directive gates? |
| GT-D6 | Phase 3 / K-7 | What exactly does the Phase 3 (unit 3.1 minimum) directive cover? |
| GT-D7 | Production / G6 | How and when is the 53-day-stale production business date brought current, relative to a K-7 deploy? |
| GT-D8 | G10 | How are the Golden Master (6 operational diffs), the replay baseline (2 Q06-H2 deltas) and the production anchor re-baselined? |
| GT-D9 | G1 / G5 | Which ADRs does the first release exercise, and is ADR-011 (already applied to production) to be adopted? |
| GT-D10 | Governance / G2 | Should the ADR-011 production authorization, the CF-10/CF-11 directive and the Q06-H2 implementation be durably recorded? |
| GT-D11 | G7 | How is B-4 (migration authority) resolved now that migration 10.0.0 has run through the boot-time registry? |
| GT-D12 | Phase 3 / G6 | Under a single Admin, how do close override (3.3) and reopen (3.4) satisfy FD-P2-07 maker-checker? |
| GT-D13 | G3 | Does G3 include the dimension text "reconciliation views agree" (Q17/Q20 DIVERGED)? |
| GT-D14 | G1–G12 | Which commit or tag is the release candidate against which gate packs will be built? |
| GT-D15 | G8 | Is the FD-P2-04 recovery-hardening directive to be issued now (in parallel with Phase 3)? |
| GT-D16 | G9 / G11 | Is the FD-017 launcher CRLF correction to be executed now? |

---

## GT-D1

| Field | Content |
|---|---|
| DECISION ID | GT-D1 |
| DATE DISCOVERED | 2026-10-02 (first noted as an open question in `FinalGrid/g3_decision_package/G3_DECISION_PACKAGE.md:296`, 2026-09-30) |
| WORKSTREAM | G3 Financial integrity / G6 Business-date integrity |
| QUESTION | May G3 be scored PASS when K-7 is delivered as Phase 3 unit 3.1 alone, while G6 stays open for units 3.2–3.8? |
| WHY REQUIRED | K-7 is a G3 condition, "business-date dating at all writers (K-7)" (`CERTIFICATION_GATES.md:33`). Its content is also G6's "single derivation; no wall-clock financial dating" (`:36`). No record says whether G3 can close on 3.1 alone. The wording differs: G3 is writer-scoped, while G6 "single derivation" also covers the `get_business_date()` fallback (`app/services.py:619-621`) |
| OPTIONS | (a) Yes, on 3.1 evidence alone (writer-scoped); G6 stays open. (b) No, G3 waits for all of G6. (c) Yes, but only if 3.1 also removes the fallback (single derivation), so G3 and G6-C1/C2 share one complete 3.1 pack |
| EVIDENCE | `CERTIFICATION_GATES.md:33,36,46`; `BLOCKERS_AND_CARRYFORWARDS.md:10`; `G6_DEPENDENCY_MAP.md` §5 |
| DEPENDENCIES | GT-D6 (3.1 scope) |
| WHAT IS BLOCKED | the G3 disposition; the scope of the K-7 directive |
| WHAT CAN CONTINUE | SR-1 decision (GT-D2); recovery (GT-D15); launcher (GT-D16); drafting the 3.1 directive content |
| EXACT ACTION AFTER DECISION | Record the ruling in `FOUNDER_DECISIONS.md` (new round). Update `G3_MATRIX.md` row 7 / §3 in a new evidence pack (this pack is not edited afterwards — SC-4). Shape the GT-D6 directive to match |

## GT-D2

| Field | Content |
|---|---|
| DECISION ID | GT-D2 |
| DATE DISCOVERED | 2026-10-02 (SR-1 open since FD-P2-06, 2026-09-10; the text gap is also recorded in `overnight_execution/OVERNIGHT_STATE.md:27` "no exact rule text ruled") |
| WORKSTREAM | SR-1 (INV-B06) / G3 |
| QUESTION | What is the exact INV-B06 amendment? (1) the leading window for `payment_purpose='advance'` before arrival — none, N days, or bounded by booking/reservation creation; (2) whether and how cancellation refunds are admitted, and on which date basis (technical cancellation time vs business date); (3) whether any other purpose changes; (4) negative seeds; (5) severity/blocking unchanged or not; (6) sequencing — SR-1 before K-7 (refund basis ruled independently), after K-7, or refunds excluded from SR-1 |
| WHY REQUIRED | FD-P2-06 rules the principle only: "the amendment's exact text, negative seeds and commissioning are the content of the later directive" (`FOUNDER_DECISIONS.md:1185`). The decision pack's recommended text is a recommendation, and it is internally inconsistent: no lower bound, yet "an advance dated 400 days before arrival still fails" (`G3_DECISION_PACKAGE.md:289`). Master Plan §07 Layer 1: an invariant change "is a constitutional amendment requiring a Founder ruling" (`MASTER_PLAN.md:262`). Precedent: SR-2 needed Founder-issued text (Round 6) and a revision (Round 7) |
| OPTIONS | for (1): no lower bound / fixed N-day window / bounded by reservation creation date. For (2): admit refunds referenced by `reservations.cancellation_refund_payment_id` dated on/before cancellation (technical basis) / same on business-date basis after K-7 / leave refunds under the current window. For (6): before K-7 / after K-7 / split (advances now, refunds after K-7) |
| EVIDENCE | `FOUNDER_DECISIONS.md:1178-1187`; `verification/invariants/rules_b.py:607-611` (unchanged since `b5b2514`); `20260910_phase2_founder_decisions/FOUNDER_DECISION_PACK.md` (INV-B06 table); `IMPLEMENTATION_CONSEQUENCES.md:12`; refunds wall-clock dated at `app/services.py:1807`; production INV-B06 HOLDS (`…/20261001_120800_inv_run_production/result.json`) |
| DEPENDENCIES | GT-D3 (Phase 6 carve-out); GT-D6/K-7 for the refund basis |
| WHAT IS BLOCKED | the SR-1 directive and implementation; G3; a readable INV-B06 verdict in the G6/G11 multi-day rehearsal ("INV-B01–B06 HOLD after each close", `IMPLEMENTATION_CONSEQUENCES.md:11`) |
| WHAT CAN CONTINUE | K-7 code work (independent unless SR-1 is sequenced after it); all non-G3 work |
| EXACT ACTION AFTER DECISION | Record the rule text verbatim in `FOUNDER_DECISIONS.md`. Issue the FD-P2-06 SR-1 directive. Engineering changes `verification/invariants/rules_b.py` only (no `app/`), adds positive and negative cases, re-commissions by hand (backing is by id only, `INV_D02_IMPLEMENTATION_REPORT.md:94`), runs `inv-commission`, `ds-run`, `inv-run` (production read-only) and commits one pack. Push/merge only with a recorded authorization (see GT-D4) |

## GT-D3

| Field | Content |
|---|---|
| DECISION ID | GT-D3 |
| DATE DISCOVERED | 2026-10-02 (conflict first identified `G3_DECISION_PACKAGE.md:285-288`) |
| WORKSTREAM | Master Plan governance / SR-1 (and retrospectively SR-2) |
| QUESTION | Does FD-P2-06's "Phase 6 invariant-refinement directive" override Phase 6's "Not touched: invariant semantics", and should that carve-out be recorded as a `MASTER_PLAN.md` overlay? |
| WHY REQUIRED | Phase 6: "**Not touched:** invariant semantics, VACUOUS classification, fault registry, replay engine" (`MASTER_PLAN.md:172`). FD-P2-06: "permits a **Phase 6 invariant-refinement directive** confined to `verification/invariants/`…" (`FOUNDER_DECISIONS.md:1186`). §18 overlay maps it to the "Phase 6 unit 6.5 family" (`MASTER_PLAN.md:476`) without amending `:172`. SR-2 already changed INV-D02 semantics under Rounds 6–7 with no overlay. FD-002 forbids silently modifying the plan (`FOUNDER_DECISIONS.md:419`) |
| OPTIONS | (a) Record an appended overlay: FD-P2-06 (and SR2-RULE/SR2-REV2) are Founder-ruled constitutional amendments under §07 Layer 1 and are excepted from Phase 6 "Not touched" for INV-B06 and INV-D02 only. (b) Place the refinements outside Phase 6 (a standalone constitutional-amendment directive class). (c) Leave as is (the conflict stays on record) |
| EVIDENCE | `MASTER_PLAN.md:172,262,476`; `FOUNDER_DECISIONS.md:1185-1186,1292-1354` |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | a clean SR-1 directive (GT-D2); G2 consistency for the SR-2 change already made |
| WHAT CAN CONTINUE | everything else |
| EXACT ACTION AFTER DECISION | Append a `MASTER_PLAN.md` overlay section (append-only; earlier text not edited) citing the ruling. Reference it in the SR-1 directive |

## GT-D4

| Field | Content |
|---|---|
| DECISION ID | GT-D4 |
| DATE DISCOVERED | 2026-10-02 (`OVERNIGHT_STATE.md:44`, N-01) |
| WORKSTREAM | Governance / G2 |
| QUESTION | Was pushing and merging the SR-2 work (`94cb87a..c9eeff0`) to `origin/main` authorized, by whom and when, and will that authorization be recorded? |
| WHY REQUIRED | Round 7 records "implementation on local branch `sr2-inv-d02`, not pushed, not merged" (`FOUNDER_DECISIONS.md:1328`) and "Push and merge remain separately unauthorised; the local branch is the only authorised delivery location" (`:1354`). That entry is itself in commit `ff59f1d`, which is on `origin/main` = `c9eeff0` (`git log c703150..c9eeff0`). FD-018: decisions must become durable records before downstream relies on them (`:826`). `FOUNDER_DECISIONS.md` is append-only (`:12-14`), so the fix is a new entry |
| OPTIONS | (a) Founder records that push/merge was authorized (date, scope) in a new round entry. (b) Founder records that it was not authorized and directs a remedy (e.g. a revert commit on `main` — a mutating action needing its own authorization; no history rewrite under SC-6). (c) Founder records the merge as ratified after the fact |
| EVIDENCE | `FOUNDER_DECISIONS.md:1323-1354`; `git log c703150..c9eeff0` (7 commits); `OVERNIGHT_STATE.md:20,26,44`; `20260930_sr2_inv_d02/INV_D02_IMPLEMENTATION_REPORT.md:91` ("Push and merge are not authorized by this directive") |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | G2; any claim that SR-2 is governed as delivered on `main` |
| WHAT CAN CONTINUE | all technical work (SR-2 is verification-only; production unaffected — the live checkout is at `c703150`, `OVERNIGHT_STATE.md:21`) |
| EXACT ACTION AFTER DECISION | Append a new round to `FOUNDER_DECISIONS.md` recording the authorization status of the push/merge. Reference it from the next G2 evidence pack |

## GT-D5

| Field | Content |
|---|---|
| DECISION ID | GT-D5 |
| DATE DISCOVERED | 2026-10-02 (gap recorded since `MASTER_PLAN.md:347`, 2026-09-08) |
| WORKSTREAM | Master Plan / Phase 3 |
| QUESTION | Restate the meaning and pass criteria of Phase Gates A–H, retire them in favour of G1–G12, or require each phase directive to state its own gates? |
| WHY REQUIRED | Phase 3 lists "Gates: A, C, D, E, F, G, H" (`MASTER_PLAN.md:150`). The defining text (FOUNDER-DIR-FINALGRID-TARGET-001) is unrecovered (`:13,347`). An exhaustive search found no definition in the tree or in git history (`G6_GATE_DEFINITIONS_MISSING.md` §2). D and E have no usage anywhere. Reconstruction is forbidden (AR-014, `FOUNDER_DECISIONS.md:923`) |
| OPTIONS | `G6_GATE_DEFINITIONS_MISSING.md` §5: (1) restate A–H as a present-day definition; (2) retire A–H for G1–G12 via an appended overlay; (3) per-directive gates |
| EVIDENCE | `G6_GATE_DEFINITIONS_MISSING.md` §1–§4 |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | checking any Phase 3 (or later) directive and its completion against its phase gates |
| WHAT CAN CONTINUE | G1–G12 evaluation; drafting Phase 3 directive content |
| EXACT ACTION AFTER DECISION | Record the ruling in `FOUNDER_DECISIONS.md`. Append a `MASTER_PLAN.md` overlay (option 1 or 2). Cite it in the Phase 3 directive's acceptance section |

## GT-D6

| Field | Content |
|---|---|
| DECISION ID | GT-D6 |
| DATE DISCOVERED | 2026-10-02 (items first listed `G3_DECISION_PACKAGE.md` §A14) |
| WORKSTREAM | Phase 3 / K-7 / G3 / G6 |
| QUESTION | Issue a Phase 3 directive, and with what scope: (1) unit 3.1 alone or more units (3.5/3.6 are FD-P2-05 first-release controls); (2) the exact K-7 sites; (3) `get_business_date()` fallback — fail closed or calendar; (4) B-10 #1 invoice date, #2 arrival/departure basis (late-checkout rule), #3 shift mapping — in or out; (5) report default ranges — in (ADR-004) or out (Phase 3 "Not touched: reports"); (6) B-10 #5 staleness threshold; B-10 #4 basis invariant (constitutional); (7) authority to re-baseline frozen-suite outcomes that K-7 moves; (8) fresh-install default `night_audit_enabled='true'` — in scope or left to the G11 procedure; (9) push/merge authorization for the result |
| WHY REQUIRED | No Phase 3 directive exists: "No phase implementation is authorized by this entry" (`FOUNDER_DECISIONS.md:1206`). Q-3 forbids unrelated date refactoring (`:1015-1017`). ADR-004 (adopted) moves report ranges to the business date, while Phase 3 excludes reports (`MASTER_PLAN.md:150`). B-10 is "Implementation design needed" (`adr/BACKLOG.md:21`). The fresh-install seed is `app/__init__.py:1897` vs FD-P2-05 (`FOUNDER_DECISIONS.md:1175`) |
| OPTIONS | (1) 3.1 only / 3.1+3.5+3.6 / all of Phase 3. (3) fail closed / calendar with escalation. (5) in / out. (7) authorize re-baselining with declared-delta documents / require new suites. Other items: in / out |
| EVIDENCE | `G3_MATRIX.md` row 7; `G6_DEPENDENCY_MAP.md` §2, §4; `G3_DECISION_PACKAGE.md` §A; `WORK_ESTIMATE.md:10` |
| DEPENDENCIES | GT-D1 (G3 scope), GT-D5 (phase gates), GT-D12 (3.3/3.4 if included), GT-D8 (GM/replay movement) |
| WHAT IS BLOCKED | K-7 implementation; G3; G6; G11 |
| WHAT CAN CONTINUE | SR-1 decision; recovery and launcher work; analysis of K-7 on copies (read-only) |
| EXACT ACTION AFTER DECISION | Record the directive in `FOUNDER_DECISIONS.md`. Engineering implements on a branch (schema-free), runs a RED/GREEN per-site dating matrix on copies from worktrees plus the full regression battery, commits one pack per unit (SC-6). Production deployment remains separate (FD-019) and waits on GT-D7 |

## GT-D7

| Field | Content |
|---|---|
| DECISION ID | GT-D7 |
| DATE DISCOVERED | 2026-10-02 (date now 53 days stale, `OVERNIGHT_STATE.md:24`) |
| WORKSTREAM | Production operation / G6 / G11 |
| QUESTION | How and when is the production business date (2026-08-10) brought current — successive manual closes, a governed single advance, or left until go-live — and must that happen before any K-7 deploy? |
| WHY REQUIRED | With K-7 deployed, every correction, refund, voucher, overstay and checkout extra would be dated 2026-08-10 until days are closed (`G3_DECISION_PACKAGE.md` §A10). Closing or advancing is a production mutation (night-audit rows, room-rent posting for in-house stays) under FD-P2-05, FD-019 and PD-004/005/006 (`FOUNDER_DECISIONS.md:468-496,839-852`). No staleness threshold exists (B-10 #5) |
| OPTIONS | (a) Bring current by N manual closes before the K-7 deploy, under a PD-004 authorization with backup/restore rehearsal. (b) Deploy K-7 first and accept stale-dated postings until the date is current. (c) Defer both until the go-live day-one procedure (G11), keeping the application stopped meanwhile |
| EVIDENCE | `OVERNIGHT_STATE.md:23-25`; `G6_DEPENDENCY_MAP.md` §6 |
| DEPENDENCIES | GT-D6; 3.5/3.6 (recovery and escalation) if done before they exist; GT-D12 if reopen is needed |
| WHAT IS BLOCKED | K-7 production deployment; G6 staleness condition; the G11 day-one procedure |
| WHAT CAN CONTINUE | K-7 code and evidence on copies; all non-production work |
| EXACT ACTION AFTER DECISION | Record the decision. If (a): issue a PD-004 production directive naming the operation; follow PD-005 (backup → verify → rehearse → execute → post-verify → invariants → evidence) and commit a pack |

## GT-D8

| Field | Content |
|---|---|
| DECISION ID | GT-D8 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G10 Regression verification / verification governance |
| QUESTION | (1) Authorize recapturing the Golden Master (now WARN 156/158, 6 operational differences), or declaring those differences? (2) How should "replay 0" be read given the two governed Q06-H2 deltas and a baseline that Q06-H1/H3 keep un-refrozen? (3) Record the new production anchor (`21dc0e97…`, via `e67f963b…`) in place of SC-1's `51dd83b7…`? |
| WHY REQUIRED | G10 requires "Golden Master 0 undeclared differences; replay 0; … production anchor unchanged" (`CERTIFICATION_GATES.md:40`). GM: 6 differences from the Founder's login and a scheduler notification retry, "not re-baselined"; "Recapturing the master needs its own authorization" (`INV_D02_IMPLEMENTATION_REPORT.md:75,93`). Replay: the stored baseline keeps pre-fix values; "a baseline update … is a separate, later, explicitly-authorized action" (`20260923_q06_fix/Q06_REGRESSION.md:45`). Anchor: SC-1 names `51dd83b7…` (`MASTER_PLAN.md:39`); production changed with Founder-authorized migration 10.0.0 and later activity (`ADR011_PRODUCTION_APPLICATION_REPORT.md:12`; `…live_human_provenance/REPORT.md` §2). No gate may pass by weakening a master (`CERTIFICATION_GATES.md:50`), so a re-baseline must be a governed act. K-7 will move GM and replay again (`WORK_ESTIMATE.md:10,24-25`) |
| OPTIONS | (1) recapture now / declare the 6 differences / recapture once after K-7. (2) re-freeze the replay baseline with a declared-delta record / keep it and treat the two deltas as declared. (3) record the new anchor now / at each production change / at the release tag only |
| EVIDENCE | as above; `GATE_STATUS_REGISTER.md` G10 |
| DEPENDENCIES | GT-D6 (K-7 moves surfaces); GT-D10 (anchor record) |
| WHAT IS BLOCKED | G10; therefore G11 and G12 |
| WHAT CAN CONTINUE | all implementation work. Regression comparisons still work as "identical to baseline-run" comparisons, as SR-2 used them |
| EXACT ACTION AFTER DECISION | Record the ruling. If recapture: a verification-only directive (Q-4 precedent) capturing a new tagged master, with a declared-delta document, committed. Update SC-1's operative anchor by an appended `MASTER_PLAN.md` overlay |

## GT-D9

| Field | Content |
|---|---|
| DECISION ID | GT-D9 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G1 Architecture / G5 Auditability |
| QUESTION | Which ADRs does the first release exercise? Specifically: (1) adopt ADR-011, whose system-actor design (ADR011-SA) is implemented and live on production, with the remaining envelope items (workstation identifier, mandatory `shift_id` — B-8); (2) does the release exercise ADR-006 (migration mechanism) and ADR-012 (retention design), both PROPOSED; (3) are ADR-009 and ADR-010 out of the first-release set under FD-P2-01; (4) are the recorded "webhook audit gaps" in or out of G5? |
| WHY REQUIRED | G1: "no ADR the release exercises is still PROPOSED" (`CERTIFICATION_GATES.md:31`). ADR-011 status is "PROPOSED FOR ADOPTION" (`adr/ADR-011-operator-accountability.md:5`); Round 5 deferred the reconciliation "to its adoption review" (`FOUNDER_DECISIONS.md:1287`); production runs migration 10.0.0 (`ADR011_PRODUCTION_APPLICATION_REPORT.md:3`), and that report lists "ADR-011 formal adoption" and "webhook audit gaps" as open (`:101,105`). G5 needs a "provenance envelope per ADR-011" (`CERTIFICATION_GATES.md:35`) |
| OPTIONS | per ADR: adopt / declare not exercised by the first release / keep open (gate stays OPEN) |
| EVIDENCE | `adr/ADR-006…:5`, `ADR-009…:5`, `ADR-010…:5`, `ADR-011…:5,61-63`, `ADR-012…:5,53-55`; `adr/BACKLOG.md:15,17-19` |
| DEPENDENCIES | GT-D11 (ADR-006/B-4) |
| WHAT IS BLOCKED | G1, G5, hence G11/G12 |
| WHAT CAN CONTINUE | all implementation work |
| EXACT ACTION AFTER DECISION | Record an ADR adoption entry in `FOUNDER_DECISIONS.md`. Append an adoption section and status line to each adopted ADR (allowed before adoption per `adr/README.md`). List the release's ADR set in the G1 pack |

## GT-D10

| Field | Content |
|---|---|
| DECISION ID | GT-D10 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | Governance / G2 |
| QUESTION | Will the Founder durably record: (1) the PD-004 authorization for applying ADR-011 migration 10.0.0 to production (2026-09-30); (2) the directive under which CF-10/CF-11 were implemented ("autonomous continuation directive of 2026-09-30"); (3) acknowledgement of the Q06-H2 implementation (`60abea6`) and of CF-10/CF-11 completion against the carry-forward register? |
| WHY REQUIRED | (1) appears only in evidence: "Founder authorization in session, 2026-09-30" (`ADR011_PRODUCTION_APPLICATION_REPORT.md:10`); no PD-004 entry exists in `FOUNDER_DECISIONS.md`. (2) appears only at `CF10_COMPLETION.md:8`; CF-11 required "a separate bounded defect directive later" (`FOUNDER_DECISIONS.md:1090`). (3) the last carry-forward register (`:1250`) still lists CF-10, CF-11 and Q06-H2 as OPEN. FD-018 (`:826`) and G2 (`CERTIFICATION_GATES.md:32`) require durable records |
| OPTIONS | (a) record all three in one new round. (b) record each separately. (c) record that some were not authorized as executed, and direct a remedy |
| EVIDENCE | as above |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | G2 |
| WHAT CAN CONTINUE | everything technical |
| EXACT ACTION AFTER DECISION | Append the round to `FOUNDER_DECISIONS.md`, including an updated carry-forward register that marks CF-10, CF-11 and Q06-H2 closed with evidence paths if the Founder so rules |

## GT-D11

| Field | Content |
|---|---|
| DECISION ID | GT-D11 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G7 Database integrity / Phase 5 |
| QUESTION | Now that the first post-baseline schema change (migration 10.0.0) has run through the unattended boot-time registry, is B-4 (single migration authority; end of unattended boot-time execution) ruled now, or is 10.0.0 recorded as an authorized exception with B-4 binding from the next schema change? |
| WHY REQUIRED | G7: "migration authority decided before any schema change (B-4)" (`CERTIFICATION_GATES.md:37`). Inventory: "**E** (B-4) → **A before the first schema change**" (`PRODUCTION_READINESS_INVENTORY.md:40`). Round 5 recorded the delivery mechanism as "Not addressed by this ruling" and warned that "a boot-time migration committed to `main` would be applied to production at the next application start" (`FOUNDER_DECISIONS.md:1289`). B-4 is still undecided (`adr/BACKLOG.md:15`) |
| OPTIONS | (a) rule B-4 now (inline registry vs Alembic; attended vs boot-time). (b) record 10.0.0 as a one-off exception under its PD-004 authorization; B-4 blocks the next schema change. (c) declare G7's B-4 item satisfied by the PD-004/005 controls actually applied (backup, rehearsal, verified post-state) |
| EVIDENCE | `ADR011_PRODUCTION_APPLICATION_REPORT.md` §1–§5; `20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:31-41` |
| DEPENDENCIES | GT-D10 (record of the 10.0.0 authorization) |
| WHAT IS BLOCKED | G7; any further schema change |
| WHAT CAN CONTINUE | schema-free work (K-7, SR-1, recovery as file-manifest) |
| EXACT ACTION AFTER DECISION | Record the ruling. If (a), issue the ADR-006/B-4 decision and a Phase 5 unit 5.1 directive |

## GT-D12

| Field | Content |
|---|---|
| DECISION ID | GT-D12 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | Phase 3 (3.3 override, 3.4 reopen) / G6 / ADR-010 |
| QUESTION | Under the single-Admin first release, do night-audit override (3.3) and reopening a closed business day (3.4) require maker-checker? If so, how are they completed with no second person (wait, or an emergency/admin control with mandatory reason and flagged audit)? |
| WHY REQUIRED | FD-P2-07 requires the operation matrix to "separately consider … closed-day corrections; reopening a closed business day" and says a maker-checker operation "**cannot be completed by the sole Admin alone**" (`FOUNDER_DECISIONS.md:1193,1196`). FD-P2-01 fixes a single Admin (`:1127`). G6 needs reopen and override semantics (`CERTIFICATION_GATES.md:36`); G11 needs "one reopen" in the rehearsal (`:23`). ADR-010 is PROPOSED with no matrix (`adr/ADR-010…:5`; B-2 `adr/BACKLOG.md:13`). Existing reopen: Admin/Manager with mandatory reason (`app/reports.py:3105`; decision pack FD-P2-05) |
| OPTIONS | (a) reopen and override are role-authorization-only with mandatory reason (current behaviour) for the first release. (b) maker-checker required; a single-operator property uses the emergency/admin control. (c) defer 3.3/3.4 changes to Phase 2b with ADR-010 |
| EVIDENCE | as above |
| DEPENDENCIES | ADR-010 / B-2 |
| WHAT IS BLOCKED | the 3.3/3.4 scope of the Phase 3 directive; the G6 condition "close/reopen … semantics" |
| WHAT CAN CONTINUE | 3.1, 3.5, 3.6, 3.7 |
| EXACT ACTION AFTER DECISION | Record the ruling. Include it in the Phase 3 directive (GT-D6) or in ADR-010 adoption |

## GT-D13

| Field | Content |
|---|---|
| DECISION ID | GT-D13 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G3 scope |
| QUESTION | Is G3 scored on its gate row only (`CERTIFICATION_GATES.md:33`), or also on the "Financial correctness" dimension text "reconciliation views agree; GST/invoice engines agree with each other" (`:14`)? If the latter, do the pre-existing Q17 (MIS aggregates vs canonical engines/flash report) and Q20 (ADR/RevPAR, multiple definitions) DIVERGED quantities need explanation, as Q06 did? |
| WHY REQUIRED | Cross-implementation shows 4 DIVERGED (Q06 structural, Q14 D11, Q17, Q20) (`CF10_COMPLETION.md:90`; `verification/quantities.py:962,1096`). Q06 and Q14 are explained; Q17/Q20 are recorded only as PRE-EXISTING (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:66`) |
| OPTIONS | (a) G3 = gate row only; record Q17/Q20 as outside G3. (b) include them; a read-only analysis directive first (Q06 precedent). (c) route them to another gate (e.g. G10 "no unexplained regression", `CERTIFICATION_GATES.md:5`) |
| EVIDENCE | as above |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | the final G3 scope |
| WHAT CAN CONTINUE | everything |
| EXACT ACTION AFTER DECISION | Record the scope ruling. If (b), issue a read-only Q17/Q20 analysis directive and commit its pack |

## GT-D14

| Field | Content |
|---|---|
| DECISION ID | GT-D14 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | Certification (all gates) |
| QUESTION | When and how is the release candidate named (commit and tag) against which the G1–G12 packs are built? |
| WHY REQUIRED | "A gate is PASS only with a committed evidence pack at the release tag" (`CERTIFICATION_GATES.md:50`). No release tag exists (`git tag -l`: only `v2.2.18-*` pre-Wave-1 tags). FD-P2-04 condition 5 was "NOT VERIFIED for 'release-tag fingerprint' (no release tag exists)" (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:36`) |
| OPTIONS | (a) name the tag after G3/G6 implementation. (b) name a provisional candidate now and re-tag after each change (G10 re-runs "at every later tag", `CERTIFICATION_GATES.md:40`) |
| EVIDENCE | as above |
| DEPENDENCIES | most gates' implementation |
| WHAT IS BLOCKED | every gate's PASS; the G7 fingerprint expectation |
| WHAT CAN CONTINUE | all implementation and pre-tag evidence |
| EXACT ACTION AFTER DECISION | Record the release-tag decision. Tagging is a git act needing its own authorization |

## GT-D15

| Field | Content |
|---|---|
| DECISION ID | GT-D15 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G8 Recovery |
| QUESTION | Is the FD-P2-04 recovery-hardening directive issued now, in parallel with Phase 3? It covers the operating backup path via the backup API with hash/manifest, retention exemption, key-custody procedure, and one off-box `.enc` restore rehearsal meeting all twelve conditions |
| WHY REQUIRED | FD-P2-04 "permits the **recovery-hardening directive**" (`FOUNDER_DECISIONS.md:1165`); none issued. `app/backup_manager.py:206-208` still uses `shutil.copy2`. Condition 11 (encrypted off-box restore) NOT VERIFIED (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:36`) |
| OPTIONS | (a) issue now. (b) after Phase 3. (c) a smaller first step (key-custody procedure only) |
| EVIDENCE | as above; `IMPLEMENTATION_CONSEQUENCES.md:10` |
| DEPENDENCIES | a second machine for the off-box rehearsal; key-custody arrangements (Founder) |
| WHAT IS BLOCKED | G8, hence G11/G12 |
| WHAT CAN CONTINUE | everything else; it is independent of G3/G6 |
| EXACT ACTION AFTER DECISION | Record the directive; engineering implements per `IMPLEMENTATION_CONSEQUENCES.md:10` (manifest as file, no schema change unless PD-004) and commits a rehearsal pack |

## GT-D16

| Field | Content |
|---|---|
| DECISION ID | GT-D16 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | G9 Reliability / G11 |
| QUESTION | Is the FD-017 launcher CRLF correction (nine files, line endings only) to be executed now as a separate bounded directive? |
| WHY REQUIRED | FD-017 approves it but says "Do not perform the correction under this directive" (`FOUNDER_DECISIONS.md:800-807`). All nine launchers are still LF-only at `c9eeff0` (`git ls-files --eol`: `i/lf w/lf`; byte check of `stop.bat`). G9 is blocking for launchers (`CERTIFICATION_GATES.md:39`) |
| OPTIONS | (a) execute now (one commit, byte diff CRLF-only). (b) execute as part of G11 preparation |
| EVIDENCE | as above; `PHASE2_SCOPE.md:13` (P2-A5) |
| DEPENDENCIES | `.gitattributes` / `core.autocrlf=false` handling, so CRLF survives commit and checkout (engineering detail) |
| WHAT IS BLOCKED | G9 launcher condition; G11 launcher rehearsal |
| WHAT CAN CONTINUE | everything else |
| EXACT ACTION AFTER DECISION | Record the directive; engineering converts the nine files, proves a CRLF-only byte diff, commits one pack; execution on the operator machine belongs to G11 |
