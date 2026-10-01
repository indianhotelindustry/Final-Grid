# GATE STATUS REGISTER — G1 to G12 (master register)

| | |
|---|---|
| Prepared | 2026-10-02, overnight session FG-OVERNIGHT-01, **analysis only** |
| Repository read | `C:/wtov`, branch `overnight-20261002` = `origin/main` = `c9eeff0` |
| Written | only this directory (`verification/evidence/20261002_overnight_gates_g3_g6/`) |
| Not done | no application start, no `app` import, no production folder or `pms.db` opened, no mutating git command, no change outside this directory |
| Production facts used | supplied by the orchestrator (verified 2026-10-02 00:40 IST) and recorded in `verification/evidence/overnight_execution/OVERNIGHT_STATE.md:23-25`: SHA-256 `21dc0e97…3953e434`, business date 2026-08-10 (53 days behind calendar), application stopped, `night_audit_enabled=false` |
| Companion documents | `G3_MATRIX.md` · `G6_DEPENDENCY_MAP.md` · `G6_GATE_DEFINITIONS_MISSING.md` · `GATES_DECISION_REQUIRED.md` (decision IDs GT-D1…GT-D16) |

Labels used in this pack: **FACT** = read from a cited file or command; **ANALYSIS** = this document's reasoning from facts; **OPTION** = a possible course, not a recommendation and not a decision.

## 0. How a gate passes, and the convention used here

**FACT — gate source.** The twelve gates are defined in `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:29-42`, with dependencies at `:46` and the scoring rule at `:50`:

> "A gate is PASS only with a committed evidence pack at the release tag. A gate marked "advisory" for a single-operator property becomes blocking the moment a second role is created (MP-D9). No gate may be passed by weakening an invariant, a master, a dataset declaration or a matrix expectation (SC-5, Master Plan §07 Layer 1)." (`CERTIFICATION_GATES.md:50`)

Deployment condition: "ALL PRODUCTION-BLOCKING GATES PASS **and** NO UNEXPLAINED REGRESSION **and** RECOVERY REHEARSAL PASS **and** DEPLOYMENT REHEARSAL PASS **and** FORMAL PRODUCTION CERTIFICATION RECORDED." (`CERTIFICATION_GATES.md:5`)

**FACT — no release tag exists.** `git -C C:/wtov tag -l` lists only `v2.2.18-preWave1`, `v2.2.18-wave0.5`, `v2.2.18-wave0.5-frozen` (all pre-Wave-1). No release candidate tag has been named in `FOUNDER_DECISIONS.md`.

**ANALYSIS — consequence.** Under `:50`, **no gate can be PASS today**, whatever tests show. The column "Gate status at `c9eeff0`" below therefore reports the state of the gate's conditions at the current commit, using this convention:

| Status | Used here when |
|---|---|
| PASS | not used for any gate (no release tag) |
| FAIL | a blocking condition is demonstrably unmet at `c9eeff0` / production **and** no work towards it has started |
| OPEN | some conditions met with committed evidence; others still need implementation, a decision, a record, or re-verification |
| BLOCKED | the gate cannot be evaluated until the gates it depends on (`CERTIFICATION_GATES.md:46`) have passed |
| DONE | used only for a single **condition item** that has committed evidence (never for a whole gate) |
| NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE | as the words say, per condition item |

The 2026-09-10 column is copied from `CERTIFICATION_GATES.md` ("Current status at `a84566ae`").

## 1. Summary

| Gate | Blocking (per `CERTIFICATION_GATES.md`) | Recorded at `a84566ae` (2026-09-10) | Gate status at `c9eeff0` (2026-10-02) | One-line reason |
|---|---|---|---|---|
| G1 Architecture | yes | PASS for Phase 1 surface; open for later | **OPEN** | ADR-011 is PROPOSED FOR ADOPTION, yet migration 10.0.0 implementing it runs on production. ADR-006 and ADR-012 are PROPOSED while the release exercises them |
| G2 Governance | yes | PASS | **OPEN** | four executed actions lack a durable `FOUNDER_DECISIONS.md` record (SR-2 push/merge, ADR-011 production application, CF-10/CF-11 directive, production anchor change) |
| G3 Financial integrity | yes | PARTIAL | **OPEN** | 5 condition items DONE (attribution, CF-10, CF-11, Q06, SR-2); K-7 and SR-1 open |
| G4 Authorization | yes if multi-role; otherwise advisory | PARTIAL | **OPEN — advisory for the first release** (FD-P2-01) | folio PASS; reports and several writers login-only; FD-015 not implemented |
| G5 Auditability | yes | FAIL | **OPEN** | coupling 24/24 and pruning stop DONE; ADR-011 envelope implemented and applied but ADR-011 not adopted; webhook audit gaps recorded |
| G6 Business-date integrity | yes | FAIL | **FAIL** | Phase 3 not started; wall-clock dating sites present at `c9eeff0`; production date 53 days stale; no Phase 3 directive |
| G7 Database integrity | yes (fingerprint, no-pending-migration) | PARTIAL | **OPEN** | FK check 0 and no pending migration evidenced after 10.0.0; fingerprint changed (no tag expectation yet); B-4 still undecided although a schema change has now happened |
| G8 Recovery | yes | FAIL | **FAIL** | operating backup path still `shutil.copy2`; no `.enc` off-box rehearsal; recovery-hardening directive not issued |
| G9 Reliability | yes (launchers, scheduler settings) | PARTIAL | **OPEN** | manual night audit ruled (FD-P2-05); audit pruning stopped; launchers still LF-only (FD-017 not performed); job table not written |
| G10 Regression verification | yes | PASS at `aa6d9e91` | **OPEN** | GM now WARN 156/158 (6 operational diffs); replay shows 2 governed Q06-H2 deltas; anchor changed; must be re-run at the release tag |
| G11 Deployment rehearsal | yes | FAIL | **BLOCKED** | depends on G3, G5, G6, G8, G9; its own items never performed; `docs/RELEASE.md` absent |
| G12 Production certification | yes | NOT REACHED | **BLOCKED** | depends on all; D11 verdict question ruled (FD-P2-03) |

## 2. Gate-by-gate register

### G1 — Architecture

- **Definition (FACT, `CERTIFICATION_GATES.md:31`):** "Every architecture the release relies on is ADOPTED; no ADR the release exercises is still PROPOSED". Evidence: "ADR status table; `FOUNDER_DECISIONS.md`". Blocking: yes.
- **Status: OPEN.**

| Condition item | State | Evidence |
|---|---|---|
| ADR-001/002/003/004/005/007/008 ADOPTED | DONE | `FOUNDER_DECISIONS.md:944-952`; status lines `verification/adr/ADR-00{1,2,3,4,5,7,8}-*.md:5` |
| ADR-011 (operator accountability) adopted | OPEN | `verification/adr/ADR-011-operator-accountability.md:5` still "PROPOSED FOR ADOPTION". Round 5 resolved the system-actor item but did not edit the ADR: "ADR-011 is not edited by this entry; the reconciliation is applied to it at its adoption review" (`FOUNDER_DECISIONS.md:1287`). Its implementation is live: migration 10.0.0 was applied to production (`20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:3,12`). The same report lists "ADR-011 formal adoption" as still open (`:101`) |
| ADR-006 (mutation controls / migration mechanism) | OPEN | `adr/ADR-006-production-mutation-controls.md:5` PROPOSED: "migration mechanism … remain[s] unresolved". Migration 10.0.0 nevertheless ran through the boot-time registry (`ADR011_PRODUCTION_APPLICATION_REPORT.md` §2; risk recorded at `FOUNDER_DECISIONS.md:1289`) |
| ADR-012 (audit retention) | OPEN | `adr/ADR-012-audit-retention.md:5` PROPOSED. The release carries the FD-P2-02 interim control (commit `b0d3054`), which governance authorized directly (`FOUNDER_DECISIONS.md:1136-1144`) |
| ADR-009 (reporting authz), ADR-010 (maker-checker) | NOT VERIFIED whether the first release "exercises" them | ADR-009 PFA, ADR-010 PROPOSED (`adr/ADR-009…md:5`, `adr/ADR-010…md:5`). **ANALYSIS:** under FD-P2-01 (single Admin) G4 is advisory and no maker-checker beyond the existing void/refund control is implemented, so the release may not exercise them. That is a definitional question (GT-D9) |

- **What remains:** a Founder ruling on which ADRs the first release exercises, plus adoption (or explicit non-reliance) for each (GT-D9).
- **Dependency:** Founder only. No engineering dependency.

### G2 — Governance

- **Definition (FACT, `CERTIFICATION_GATES.md:32`):** "Every decision the release relies on is recorded durably; evidence committed; no rewrite". Evidence: "acceptance entry; commit history; append-only proofs". Blocking: yes.
- **Status: OPEN.** The 2026-09-10 PASS predates the gaps below.

| Condition item | State | Evidence |
|---|---|---|
| Phase 1 acceptance recorded | DONE | `FOUNDER_DECISIONS.md:1055-1110` |
| Rounds 3–7 recorded | DONE | `FOUNDER_DECISIONS.md:1114-1354` |
| SR-2 push/merge authorization recorded | **OPEN — inconsistency** | Round 7: "Governed HEAD `c703150…` (`main`); implementation on local branch `sr2-inv-d02`, not pushed, not merged" (`:1328`), and "Push and merge remain separately unauthorised; the local branch is the only authorised delivery location" (`:1354`). Yet `origin/main` = `c9eeff0` contains `94cb87a..c9eeff0` (`git log c703150..c9eeff0`; `OVERNIGHT_STATE.md:26,44`). No later entry records the authorization. GT-D4 |
| ADR-011 production application (PD-004) recorded | **OPEN** | The authority is cited only in the evidence pack: "Founder authorization in session, 2026-09-30: 'controlled application of ADR-011 migration 10.0.0 to production, subject to PD-004/PD-005 controls'" (`ADR011_PRODUCTION_APPLICATION_REPORT.md:10`). `FOUNDER_DECISIONS.md` has no PD-004 entry. FD-018: "Accepted Founder decisions must become durable repository governance records before downstream implementation relies upon them" (`FOUNDER_DECISIONS.md:826`). GT-D10 |
| CF-10/CF-11 implementation directive recorded | **OPEN** | The completion pack cites "autonomous continuation directive of 2026-09-30" as part of its authority (`20260930_cf10_completion/CF10_COMPLETION.md:8`). CF-11 was "require[d] a separate bounded defect directive later" (`FOUNDER_DECISIONS.md:1090`). No directive entry exists. GT-D10 |
| Production anchor redefinition recorded | **OPEN** | SC-1 still names `51dd83b7…30bc2` (`MASTER_PLAN.md:39`). Production is now `21dc0e97…` (`20260930_135930_adr011_live_human_provenance/RESULT.json:3,213`) through `e67f963b…` (migration, `ADR011_PRODUCTION_APPLICATION_REPORT.md:12`) and then logins plus a scheduler notification retry (`…live_human_provenance/REPORT.md` §2). Neither anchor change is in `FOUNDER_DECISIONS.md`. GT-D8 |
| Q06-H2 and FD-P2-02 implementations | DONE (acknowledged) / NOT VERIFIED (directive text) | Round 4 records its governed HEAD as "`b0d30542…` (audit-retention fix; FD-P2-02 implemented)" (`FOUNDER_DECISIONS.md:1213`). The Q06 fix cites Q06-H2 as its authority (`20260923_q06_fix/Q06_FIX_IMPLEMENTATION.md:5`). No later round acknowledges the Q06-H2 implementation (`60abea6`) |
| Four 2026-08-31 rulings | NOT APPLICABLE (closed as evidence gap) | AR-014 closure: "CLOSED — HISTORICAL EVIDENCE GAP" (`FOUNDER_DECISIONS.md:917-937`) |
| Evidence committed, append-only | DONE for packs on `origin/main` | git history; SC-4 (`MASTER_PLAN.md:42`) |

- **What remains:** record or ratify the four items above (GT-D4, GT-D8, GT-D10).
- **Dependency:** Founder only.

### G3 — Financial integrity

- **Definition (FACT, `CERTIFICATION_GATES.md:33`):** "attribution universal (done); strict coupling at all 24 writers (CF-10); business-date dating at all writers (K-7); credit/voucher paths functional (CF-11); GST engines agree (Q06 explained); SR-1/SR-2 resolved". Evidence: "writer runtime pack 24/24; Q06 analysis; rulings". Blocking: yes.
- **Status: OPEN.** Full matrix: `G3_MATRIX.md`.

| Condition item | State | Evidence |
|---|---|---|
| Attribution universal | DONE | `FOUNDER_DECISIONS.md:1074`; W-07/W-11 covered later by the cf11 group (`20260930_cf10_completion/CF10_COMPLETION.md:52`) |
| CF-10 strict coupling 24/24 | DONE | `CF10_COMPLETION.md:27,110` (242/242 at `61286b7`); re-run 242/242 on the ADR-011 code (`20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:55`). `app/` and `tools/` are identical between `3ffeba5` and `c9eeff0` (`git diff --stat 3ffeba5 c9eeff0 -- app tools` empty) |
| CF-11 credit/voucher paths | DONE | `CF10_COMPLETION.md:111` (cf11 48/48) |
| Q06 GST engines agree / explained | DONE | Q06-H1..H3 `FOUNDER_DECISIONS.md:1219-1246`; fix `60abea6`; `20260923_q06_fix/RESULT.json` (per-date divergences empty) |
| SR-2 (INV-D02) resolved | DONE (governance gap GT-D4) | `FOUNDER_DECISIONS.md:1292-1354`; `20260930_sr2_inv_d02/REVISION_2_REPORT.md:30-31`; `20261001_120800_inv_commission` |
| SR-1 (INV-B06) resolved | OPEN | ruled in principle only (`FOUNDER_DECISIONS.md:1178-1187`); `verification/invariants/rules_b.py` last changed at `b5b2514` |
| K-7 dating at all writers | OPEN | not started; sites at `c9eeff0` listed in `G3_MATRIX.md` |
| Evidence pack at release tag | NOT VERIFIED | no release tag (§0) |

- **What remains:** GT-D1, GT-D2, GT-D6, GT-D7, then K-7 and SR-1 implementation under directives, then a release-tag pack.
- **Dependency:** Founder decisions → Phase 3 (unit 3.1) directive and FD-P2-06 SR-1 directive (`CERTIFICATION_GATES.md:46`: "G3 ← P2-A1, P2-A2, Phase 3 (dating), Q06 analysis, SR rulings").

### G4 — Authorization

- **Definition (FACT, `CERTIFICATION_GATES.md:34`):** "matrix adopted for the roles in use (MP-D9); folio (done), writers, reports enforced fail-closed; negative matrix per role". Blocking: "**yes if multi-role** (MP-D9); otherwise advisory".
- **Status: OPEN — advisory for the first release.** FD-P2-01 fixes the first release to a "SINGLE-OPERATOR / ADMIN MODEL" (`FOUNDER_DECISIONS.md:1127-1133`). Under the gate's own blocking rule, G4 is advisory until a second role is created (`CERTIFICATION_GATES.md:50`).

| Condition item | State | Evidence |
|---|---|---|
| Folio endpoints fail-closed, 29/29 | DONE (latest re-run) | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:58` (29/29 branch and main) |
| Roles-in-use matrix (MP-D9) | DONE for first release only | FD-P2-01 `FOUNDER_DECISIONS.md:1132` ("MP-D9 as a full operator-profile decision remains OPEN for Phase 4") |
| Writers and ≥26 report routes role-enforced | OPEN | `PRODUCTION_READINESS_INVENTORY.md:27-28` (AU-1, AU-2); Phase 4 unit 4.2 not started (`MASTER_PLAN.md:153-158`) |
| FD-015 `list_folios` read scope | OPEN (decided, not implemented) | `app/folio.py:48` still `('Admin', 'Manager')` |
| CF-5 negative matrix per role | OPEN | `20260910_phase2_founder_resolution/CARRY_FORWARD_REGISTER.md:9` |

- **What remains:** nothing blocking while the property stays single-Admin. Phase 4 work if a second role is introduced.
- **Dependency:** MP-D9 (full), Phase 4, ADR-009 (B-7).

### G5 — Auditability

- **Definition (FACT, `CERTIFICATION_GATES.md:35`):** "strict coupling (G3); `audit_logs` never auto-deleted; provenance envelope per ADR-011". Evidence: "prune test; audit coverage pack". Blocking: yes.
- **Status: OPEN** (was FAIL).

| Condition item | State | Evidence |
|---|---|---|
| Strict coupling | DONE | as G3 CF-10 row |
| `audit_logs` never auto-deleted | DONE | commit `b0d3054`; `20260910_retention_control/RETENTION_CONTROL_IMPLEMENTATION.md` §1, §4; retention 18/18 re-run on the ADR-011 code (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:60`); `app/__init__.py:549-555` model list holds only `WebhookLog`, `NotificationLog` |
| Provenance envelope per ADR-011 | OPEN | ADR011-SA ruled (`FOUNDER_DECISIONS.md:1267-1290`); implemented and applied (`ADR011_PRODUCTION_APPLICATION_REPORT.md:3`); live HUMAN rows verified (`20260930_135930_adr011_live_human_provenance/REPORT.md` §4). Still open: ADR-011 adoption and "the remaining provenance envelope" (`ADR011_PRODUCTION_APPLICATION_REPORT.md:101`), and "webhook audit gaps" (`:105`) |

- **What remains:** ADR-011 adoption with the envelope fields settled (workstation identifier, mandatory `shift_id` — B-8 `adr/BACKLOG.md:19`), and a decision on the webhook audit gaps (GT-D9).
- **Dependency:** G3 (coupling), ADR-011 adoption.

### G6 — Business-date integrity

- **Definition (FACT, `CERTIFICATION_GATES.md:36`):** "single derivation; no wall-clock financial dating; night-audit close/reopen/interrupted-close semantics; staleness escalation; N7 multi-day sequence". Evidence: "Phase 3 packs; multi-day rehearsal". Blocking: yes.
- **Status: FAIL.** Full map: `G6_DEPENDENCY_MAP.md`.

| Condition item | State | Evidence |
|---|---|---|
| Single derivation (3.1) | FAIL | `get_business_date()` falls back to `date.today()` (`app/services.py:619-621`) |
| No wall-clock financial dating (3.1 / K-7) | FAIL | `app/services.py:1217,1306,1807,1965,2116`; `app/models.py:775,809,1817`; `app/routes.py:8029` |
| Close / reopen / interrupted-close semantics (3.2–3.5) | OPEN — not started | Phase 3 "NOT STARTED" (`MASTER_PLAN.md:146`); FD-P2-05 scopes 3.5 as a first-release control (`FOUNDER_DECISIONS.md:1175`) |
| Staleness escalation (3.6) | FAIL | not implemented; production date 53 days stale (`OVERNIGHT_STATE.md:24`) |
| N7 multi-day sequence (3.8) | OPEN — not started | no Phase 3 pack exists (evidence listing: no `*phase3*`, `*k7*`, `*night*` pack) |

- **What remains:** Phase 3 directive(s) (none exists: "No phase implementation is authorized by this entry", `FOUNDER_DECISIONS.md:1206`), B-10 rulings, the Phase Gates A–H definitions (`G6_GATE_DEFINITIONS_MISSING.md`), and a stale-date decision.
- **Dependency:** Phase 3 (`CERTIFICATION_GATES.md:46`: "G6 ← Phase 3").

### G7 — Database integrity

- **Definition (FACT, `CERTIFICATION_GATES.md:37`):** "`foreign_key_check` = 0; schema fingerprint = tag expectation; no pending migration at boot; migration authority decided before any schema change (B-4)". Blocking: "yes (fingerprint, no-pending-migration); FK-ON and NOT NULL **not** blocking".
- **Status: OPEN.**

| Condition item | State | Evidence |
|---|---|---|
| `foreign_key_check` = 0 | DONE (after 10.0.0) | `ADR011_PRODUCTION_APPLICATION_REPORT.md` §3 "whole-database `foreign_key_check` (FK on) empty" |
| No pending migration at boot | DONE (at 10.0.0) | §4: "migration **not** re-applied (no-op)" on second start |
| Schema fingerprint = tag expectation | NOT VERIFIED | the schema changed with 10.0.0; no release tag, so no expectation exists. FD-P2-04 condition 5 recorded as "NOT VERIFIED for 'release-tag fingerprint' (no release tag exists)" (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:36`) |
| Migration authority decided before any schema change (B-4) | **OPEN — inconsistency** | B-4 still undecided (`adr/BACKLOG.md:15`). Round 5 recorded the risk as "not addressed by this ruling" (`FOUNDER_DECISIONS.md:1289`). The first post-baseline schema change (10.0.0) was applied through the boot-time registry on in-session Founder authority (`ADR011_PRODUCTION_APPLICATION_REPORT.md:10`). The inventory classed B-4 "**E** (B-4) → **A before the first schema change**" (`PRODUCTION_READINESS_INVENTORY.md:40`). GT-D11 |

- **What remains:** GT-D11. Fingerprint expectation at the release tag.
- **Dependency:** B-4 only if a further schema change is planned (`CERTIFICATION_GATES.md:46`).

### G8 — Recovery

- **Definition (FACT, `CERTIFICATION_GATES.md:38`):** "operating backup path = backup API + integrity record; restore rehearsed from an application `.enc` artifact off-box with key custody; 'verified state' (B-5) confirmed; retention of pre-update backups". Blocking: yes.
- **Status: FAIL.**

| Condition item | State | Evidence |
|---|---|---|
| "Verified state" defined (B-5) | DONE (ruling) | FD-P2-04 `FOUNDER_DECISIONS.md:1157-1166` ("closes BACKLOG B-5") |
| Operating backup path = backup API + integrity | FAIL | `app/backup_manager.py:206-208` still `shutil.copy2` |
| `.enc` off-box restore with key custody | FAIL — never performed | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:36` "11 (encrypted off-box restore) **NOT VERIFIED**" |
| Tool-path restore rehearsals | DONE (tool path only) | RR-20260908-01 (`FOUNDER_DECISIONS.md:1047`); RR-20260930-ADR011, -APPLY, -POST (`ADR011_PRODUCTION_APPLICATION_REPORT.md` §1, §5) |
| Retention of pre-update backups (B-11) | OPEN | `adr/BACKLOG.md:22` |

- **What remains:** the FD-P2-04 recovery-hardening directive (permitted, not issued: `FOUNDER_DECISIONS.md:1165`) (GT-D15).
- **Dependency:** independent of G3/G6. Can run in parallel.

### G9 — Reliability

- **Definition (FACT, `CERTIFICATION_GATES.md:39`):** "scheduler jobs documented per production setting; night-audit automation either controlled (B-1) or manual by ruling; launchers reproducible (FD-017); health/observability adequate for the operator". Blocking: "yes (launchers, scheduler settings); observability advisory".
- **Status: OPEN.**

| Condition item | State | Evidence |
|---|---|---|
| Night audit manual by ruling | DONE (ruling) | FD-P2-05 `FOUNDER_DECISIONS.md:1168-1176`; setting `false` (`OVERNIGHT_STATE.md:25`) |
| Fresh-install default for the night-audit setting | OPEN (ANALYSIS) | `init_data` seeds `('night_audit_enabled', 'true', …)` (`app/__init__.py:1897`), but only when the key is missing (`:1958-1960`). Production keeps `false`. A **fresh install** (a G11 path) would therefore start with automatic night audit enabled, contrary to FD-P2-05 ("the first-release configuration keeps `night_audit_enabled=false`", `FOUNDER_DECISIONS.md:1175`), unless the day-one procedure changes it |
| Audit pruning controlled | DONE | as G5 |
| Scheduler jobs documented per production setting | OPEN | no job table document found. Standing jobs observed: `daily_backup_job`, `log_pruning_job`, `notification_queue_flush`, `predictive_maintenance_job` (`ADR011_PRODUCTION_APPLICATION_REPORT.md` §2). `notification_queue_flush` mutated production `notification_queue` when the app ran (`…live_human_provenance/REPORT.md` §2) |
| Launchers reproducible (FD-017) | FAIL | all nine launchers LF-only at `c9eeff0` (`git ls-files --eol`: `i/lf w/lf`; byte check of `stop.bat`). FD-017 approved, "Do not perform the correction under this directive" (`FOUNDER_DECISIONS.md:807`). GT-D16 |
| Observability | advisory | — |

- **What remains:** FD-017 execution directive (GT-D16); a written job table.
- **Dependency:** "G9 ← P2-A5, B-1 or interim ruling" (`CERTIFICATION_GATES.md:46`).

### G10 — Regression verification

- **Definition (FACT, `CERTIFICATION_GATES.md:40`):** "at the release tag on copies: Golden Master 0 undeclared differences; replay 0; invariants declared movement only; five datasets PASS; Phase 2a matrix; Q14 as declared; production anchor unchanged" — "must be re-run at every later tag". Blocking: yes.
- **Status: OPEN.**

| Condition item | Latest evidence | State |
|---|---|---|
| Golden Master 0 undeclared differences | `phase1_aa6d9e91` **WARN 156/158, 6 differences** (`/auth/users` `last_login`; `/rates/notification-logs` +3), "not re-baselined" (`20260930_sr2_inv_d02/INV_D02_IMPLEMENTATION_REPORT.md:75`, unresolved item 3 at `:93`) | OPEN — recapture needs authorization (GT-D8) |
| Replay 0 | FAIL with exactly the two governed Q06-H2 deltas (`20260923_q06_fix/RESULT.json`; `INV_D02_IMPLEMENTATION_REPORT.md:76`). The stored baseline is deliberately not re-frozen (Q06-H1/H3) | OPEN — conflicts with "replay 0" as written (GT-D8) |
| Invariants declared movement only | D11 declared exception only (INV-A02/A03); INV-B06 HOLDS; INV-D02 VACUOUS (`20260930_sr2_inv_d02/final_6e46e2c_rev2/pvf/20261001_120800_inv_run_production/result.json`) | DONE at `c9eeff0` code |
| Five datasets PASS | `ds-run` 5/5 (`INV_D02_IMPLEMENTATION_REPORT.md:72`) | DONE at `c9eeff0` code |
| Phase 2a matrix | 29/29 (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:58`) | DONE |
| Q14 as declared | DIVERGED by the D11 ₹476.19 only (`CF10_COMPLETION.md:90`) | DONE |
| Production anchor unchanged | changed twice since the anchor (§G2) | OPEN — anchor redefinition (GT-D8) |
| At the release tag | — | NOT VERIFIED |

- **What remains:** GT-D8 (master recapture, replay baseline treatment, new anchor), then a full battery at the release tag.
- **Dependency:** "G10 ← every code change" (`CERTIFICATION_GATES.md:46`). K-7 is expected to move GM and replay (`WORK_ESTIMATE.md:10,24-25`).

### G11 — Deployment rehearsal

- **Definition (FACT, `CERTIFICATION_GATES.md:41`):** "on a copy of the current instance: upgrade path (pre-update backup → signed package → boot → checks), fresh-install path, launchers on the operator machine, day-one business-date procedure, N-day operation with nightly close, rollback to the previous tag; each followed by G10 on the rehearsal copy". Evidence: "rehearsal packs; written procedure (`docs/RELEASE.md` or successor)". Blocking: yes.
- **Status: BLOCKED** ("G11 ← procedure + rehearsal after G3/G5/G6/G8/G9", `CERTIFICATION_GATES.md:46`). Its own items have never been performed. `docs/` does not exist in the tree. FD-P2-05 adds "a written daily-close procedure is required (deployment rehearsal G11)" (`FOUNDER_DECISIONS.md:1175`).
- **What remains:** everything. The procedure text can be drafted earlier (OPTION), but the rehearsal waits on G3/G5/G6/G8/G9.

### G12 — Production certification

- **Definition (FACT, `CERTIFICATION_GATES.md:42`):** "G1–G11 as required; the D11 verdict question ruled (disposition or population declaration) so the `inv-run` verdict is readable; Founder certification entry recorded". Blocking: yes.
- **Status: BLOCKED.**

| Condition item | State | Evidence |
|---|---|---|
| D11 verdict question ruled | DONE (ruling) | FD-P2-03 `FOUNDER_DECISIONS.md:1146-1155` — declared-exception register at certification |
| G1–G11 | BLOCKED | this register |
| Founder certification entry | NOT VERIFIED (not reached) | — |

## 3. Cross-cutting facts that affect several gates

1. **No release tag exists.** No gate can be PASS (§0).
2. **Production has changed since the anchor all governance records cite.** `51dd83b7…` (SC-1, `MASTER_PLAN.md:39`) → `e67f963b…` (migration 10.0.0, 2026-09-30 13:24:35) → `21dc0e97…` (Founder logins and logout; a `notification_queue_flush` retry; `…live_human_provenance/REPORT.md` §2). Affects G2, G7, G10.
3. **The live checkout is 7 commits behind `origin/main`** (`OVERNIGHT_STATE.md:21,45`). Those 7 commits are verification-only (SR-2), so the production application code equals `c703150` = `c9eeff0` for `app/` and `tools/` (ANALYSIS from the empty `git diff --stat 3ffeba5 c9eeff0 -- app tools` and the ADR-011 fast-forward to `e7086da`).
4. **PostgreSQL behaviour is NOT VERIFIED** (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:21,43`; `CF10_COMPLETION.md:62`). No gate names PostgreSQL. Recorded for completeness only.
5. **Commissioning backing is checked by invariant id only** (`INV_D02_IMPLEMENTATION_REPORT.md:94`). Any SR-1 rule change must therefore be re-commissioned by hand. Affects G3 (SR-1) and G10.
