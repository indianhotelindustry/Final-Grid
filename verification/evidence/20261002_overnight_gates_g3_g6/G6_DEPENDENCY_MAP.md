# G6 DEPENDENCY MAP — Business-date integrity

| | |
|---|---|
| Prepared | 2026-10-02, analysis only, `C:/wtov` at `c9eeff0` |
| Master register | `GATE_STATUS_REGISTER.md` (G6: **FAIL**) |
| Related | `G3_MATRIX.md` (K-7 overlap) · `G6_GATE_DEFINITIONS_MISSING.md` (Phase Gates A–H) · `GATES_DECISION_REQUIRED.md` |

## 1. G6 definition and conditions (FACT)

> **G6 Business-date integrity** | single derivation; no wall-clock financial dating; night-audit close/reopen/interrupted-close semantics; staleness escalation; N7 multi-day sequence | Phase 3 packs; multi-day rehearsal | yes | **FAIL** — Phase 3 not started; production date 30 days stale; audit never nightly (`verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:36`)

Dependency: "G6 ← Phase 3" (`CERTIFICATION_GATES.md:46`). Related dimension text (`CERTIFICATION_GATES.md:22-23`):
- "Business-date behaviour | one derivation, one authoritative date, staleness escalation, midnight behaviour documented";
- "Night audit | multi-day rehearsal on a copy: N consecutive closes, one reopen, one interrupted close recovered, invariants HOLD after each".

Blockers mapped to G6: PB-2 "Business-date integrity at financial writers (FI-3, K-7) … Phase 3 unit 3.1 | G6"; PB-3 "Night-audit operational semantics and rehearsal (FI-4, RL-2) … Phase 3 units 3.2–3.6, 3.8; G11 multi-day rehearsal | G6, G11" (`BLOCKERS_AND_CARRYFORWARDS.md:10-11`).

| # | G6 condition | Status at `c9eeff0` | Evidence |
|---|---|---|---|
| C1 | single derivation | FAIL | `get_business_date()` returns `date.today()` when the row is absent (`app/services.py:619-621`). Other wall-clock references sit in the same module (`app/services.py:736,830,838`; purpose not analysed here — NOT VERIFIED whether financial) |
| C2 | no wall-clock financial dating | FAIL | eight writer sites and three model defaults (`G3_MATRIX.md` row 7) |
| C3 | close / reopen / interrupted-close semantics | OPEN — not started as Phase 3 work | partial pre-existing properties: a second run for a dated log is skipped (idempotency proven on copies, T-R02, `PRODUCTION_READINESS_INVENTORY.md:12`). Since CF-10, the W-21 close is a single transaction that on audit failure leaves "no log, no charge, date unchanged" (`20260930_cf10_completion/CF10_COMPLETION.md:57`). Manual run `app/reports.py:2823`, `app/routes.py:4921`; reopen `app/reports.py:3105`. **ANALYSIS:** transaction-level rollback is not the same as interrupted-close recovery (3.5: process killed or power lost mid-close). It is not evidenced |
| C4 | staleness escalation | FAIL | not implemented; production business date 2026-08-10, **53 days** behind calendar (`verification/evidence/overnight_execution/OVERNIGHT_STATE.md:24`) |
| C5 | N7 multi-day sequence | OPEN — not started | no Phase 3 or rehearsal pack exists |

## 2. Phase 3 units 3.1–3.8 → G6 (and other gates)

Source: `verification/MASTER_PLAN.md:146-151`. Entry "Phase 1 complete" — **met** (P1-ACC `FOUNDER_DECISIONS.md:1065-1074`; `PHASE2_ENTRY_ASSESSMENT.md:162`). Findings R8, N7, V8, R10. Gates "A, C, D, E, F, G, H" (meaning unrecovered — see `G6_GATE_DEFINITIONS_MISSING.md`). **Not touched:** "folio model, authorization idioms outside night audit, reports, snapshot-hash and closed-period protections" (`MASTER_PLAN.md:150`).

| Unit | Content (`MASTER_PLAN.md:149`) | G6 condition | Also feeds | FD-P2-05 role | Open inputs |
|---|---|---|---|---|---|
| 3.1 | single source of business-date derivation | C1, C2 (= **K-7**) | **G3** (K-7), G10 (GM/replay move) | prerequisite of safe manual mode (with a stale date, K-7 dates rows to the stale day) | `get_business_date()` fallback rule; B-10 #1 invoice date, #2 arrival/departure basis, #3 shift mapping; reports in/out (ADR-004 vs "Not touched: reports"); frozen-suite re-baseline |
| 3.2 | close idempotency | C3 | G11 (N-day closes) | — | partly evidenced (T-R02); scope of new evidence undefined |
| 3.3 | blocker/override semantics with approver identity and retained reason | C3 | G5 (provenance), G11 | override at close must be observable and auditable | maker-checker for override (FD-P2-07 lists "closed-day corrections", "other financially material corrections"); ADR-010 not adopted |
| 3.4 | bounded, authorized reopen | C3 | G11 ("one reopen") | — | FD-P2-07 lists "reopening a closed business day" for the operation matrix (`FOUNDER_DECISIONS.md:1193`). Under FD-P2-01 (single Admin), if reopen needs maker-checker the sole Admin cannot complete it alone (`:1196`). **Undefined** until ADR-010 / B-2 (GT-D12) |
| 3.5 | interrupted-close recovery | C3 | G11 ("one interrupted close recovered"), G9 | **named first-release control** (`FOUNDER_DECISIONS.md:1175`) | recovery semantics undefined |
| 3.6 | staleness escalation | C4 | G9, G11 (day-one procedure) | **named first-release control** (`:1175`) | B-10 #5 staleness threshold undefined (`adr/BACKLOG.md:21`) |
| 3.7 | remove control recomputation from `night_audit_panel.html` (V8) | — (not named in G6 row) | Phase 3 completeness | — | none known |
| 3.8 | multi-day sequence verification (N7) | C5 | G11, G10 (replay over N dates) | G11 rehearsal of "N-day manual closes" (`20260910_phase2_founder_resolution/IMPLEMENTATION_CONSEQUENCES.md:11`) | N undefined; replay-ledger re-baseline "needs its own authorization" (`WORK_ESTIMATE.md:25`); INV-B06 behaviour on advances (SR-1) |

## 3. FD-P2-05 — manual close (FACT and consequences)

> "MANUAL / CONTROLLED OPERATOR EXECUTION FOR FIRST PRODUCTION RELEASE. An authorized operator initiates the close; business date is explicitly controlled; execution must be observable; financial mutations must be auditable; recovery must be available; unattended scheduler execution is NOT the first-release operating model." (`FOUNDER_DECISIONS.md:1170-1172`)

Implementation consequence (`:1175`): `night_audit_enabled=false` kept; "a written daily-close procedure is required (deployment rehearsal G11)"; "Phase 3 units 3.5 (interrupted-close recovery) and 3.6 (staleness escalation) are the controls that make manual mode safe and are scoped accordingly". Scheduler automation requires B-1 first.

| FD-P2-05 requirement | State at `c9eeff0` | Evidence |
|---|---|---|
| authorized operator initiates | DONE (existing manual route, Admin/Manager/Accountant) | `FOUNDER_DECISION_PACK.md` FD-P2-05 "Two invocation paths"; `app/reports.py:2823` |
| business date explicitly controlled | OPEN | 3.1 (K-7) and 3.6 not implemented |
| execution observable | NOT VERIFIED | no Phase 3 evidence |
| financial mutations auditable | DONE | W-16/W-21 per-charge strict audit (`CF10_COMPLETION.md:37,56-57`). Under ADR011-SA a manual close writes HUMAN rows; the scheduler writes SYSTEM rows and is not enabled (`FOUNDER_DECISIONS.md:1269-1288`) |
| recovery available | OPEN | 3.5 |
| unattended scheduler not used | DONE on production | setting `false` (`OVERNIGHT_STATE.md:25`) |
| fresh-install default | OPEN (ANALYSIS) | `init_data` seeds `night_audit_enabled='true'` when missing (`app/__init__.py:1897,1958-1960`); a fresh install would contradict FD-P2-05 unless the day-one procedure sets it |
| written daily-close procedure | OPEN | absent (`docs/` does not exist) |

## 4. B-10 items (FACT: `verification/adr/BACKLOG.md:21`)

"**Business-date implementation questions** — invoice date rule, arrival/departure validation basis, shift-to-business-date mapping, basis-checking invariant, staleness threshold | AR-008, ADR-004 | Implementation design needed | Phase 3 | Architecture adopted."

| B-10 # | Question | Phase 3 unit | G6 condition | Founder or engineering? | State |
|---|---|---|---|---|---|
| 1 | invoice date rule | 3.1 | C2 (if invoices are "financial dating") | design + Founder scope (ADR-004 consequence vs "Not touched: reports") | OPEN |
| 2 | arrival/departure validation basis | 3.1 | C1/C2 (late-checkout decision reads the calendar clock: `G3_DECISION_PACKAGE.md` §A2) | design; Founder if behaviour on stale days changes | OPEN |
| 3 | shift-to-business-date mapping | 3.1 / 3.3 | C1 | design | OPEN |
| 4 | basis-checking invariant | 3.1 / 3.8 evidence | C2 evidence | **constitutional** — a new invariant under Master Plan §07 Layer 1 needs a Founder ruling (`MASTER_PLAN.md:262`) | OPEN |
| 5 | staleness threshold | 3.6 | C4 | **Founder** (operational policy) | OPEN |

## 5. K-7 overlap with G3

| Fact | Source |
|---|---|
| G3 condition "business-date dating at all writers (K-7)" | `CERTIFICATION_GATES.md:33` |
| G6 conditions "single derivation; no wall-clock financial dating" | `CERTIFICATION_GATES.md:36` |
| Both resolve through Phase 3 unit 3.1 | `BLOCKERS_AND_CARRYFORWARDS.md:10`; `PRODUCTION_READINESS_INVENTORY.md:11` (FI-3 "Phase 3 (3.1)") |
| No document says whether G3 can PASS on 3.1 alone while G6 waits for 3.2–3.8 | `G3_DECISION_PACKAGE.md:296`; no later record (searched `FOUNDER_DECISIONS.md` Rounds 4–7) |

**ANALYSIS.** The K-7 code change is the same for both gates, so its evidence would be shared. One difference matters. G3's wording is "dating at all writers" (writer-scoped). G6's wording, "single derivation", also covers the `get_business_date()` fallback and non-writer readers. A K-7 directive scoped to writers only could therefore satisfy G3's text and still leave G6 C1 open.

**OPTIONS** (for GT-D1, not recommendations):
- (a) G3 may PASS on unit 3.1 evidence alone; G6 stays open for 3.2–3.8.
- (b) G3 waits for G6 as a whole.
- (c) G3 passes on 3.1 only when 3.1 also covers the fallback (single derivation), so both gates share one complete 3.1 pack.

## 6. Other dependencies

| Dependency | Kind | Source |
|---|---|---|
| **Stale production business date** (2026-08-10, 53 days) | production operation; bringing it current means ~53 manual closes or an advance, under FD-P2-05 / FD-019 | `OVERNIGHT_STATE.md:24`; `G3_DECISION_PACKAGE.md` §A10 |
| **SR-1 (INV-B06)** | the G6/G11 rehearsal expects INV-B01–B06 to HOLD after each close (`IMPLEMENTATION_CONSEQUENCES.md:11`); INV-B06 fires on legitimate advances until SR-1 is implemented (`FOUNDER_DECISIONS.md:1184`) | GT-D2 |
| **ADR-010 / B-2 maker-checker matrix** | 3.3 override and 3.4 reopen semantics | `FOUNDER_DECISIONS.md:1193-1197`; `adr/BACKLOG.md:13`; GT-D12 |
| **B-1 scheduler ADR** | only if automation is wanted; not needed under FD-P2-05 | `adr/BACKLOG.md:12`; `FOUNDER_DECISIONS.md:1175` |
| **ADR011-SA** | close provenance: HUMAN for manual, SYSTEM for the scheduler | `FOUNDER_DECISIONS.md:1267-1290` (implemented, applied) |
| **CF-10 W-16/W-21** | close audit coupling — DONE | `CF10_COMPLETION.md:37` |
| **Golden Master / replay** | "every date change moves report figures → Golden Master re-baseline with declared deltas; replay ledger interaction (N7)" | `WORK_ESTIMATE.md:10`; GT-D8 |
| **Phase Gates A–H** | Phase 3 lists A, C, D, E, F, G, H; definitions unrecovered | `MASTER_PLAN.md:150,347`; `G6_GATE_DEFINITIONS_MISSING.md`; GT-D5 |
| **Phase 3 "Not touched: reports"** vs ADR-004 report consequence | scope conflict | `MASTER_PLAN.md:150`; `G3_DECISION_PACKAGE.md:284`; GT-D6 |
| **Phase 3 directive** | none exists | `FOUNDER_DECISIONS.md:1206` |

## 7. Independently clear vs undefined

**Clear now (FACT-backed; could proceed under a directive without further Founder definition):**
- Phase 3 entry condition is met (`PHASE2_ENTRY_ASSESSMENT.md:162,170`).
- The wall-clock site list for 3.1 (`G3_MATRIX.md` row 7) and the no-schema-change character of 3.1 (`G3_DECISION_PACKAGE.md` §A8–A9).
- First-release operating mode = manual (FD-P2-05); `night_audit_enabled=false` on production.
- 3.5 and 3.6 are first-release controls (FD-P2-05).
- Close audit coupling (CF-10) and actor provenance (ADR011-SA) are done.
- 3.7 (V8) has no open Founder input.
- A daily-close procedure is required (FD-P2-05). Its text can be drafted as a document (OPTION; not performed here).

**Undefined (needs a Founder decision or directive):**
- Whether G3 may pass on 3.1 alone (GT-D1).
- Phase 3 directive scope: 3.1 alone or the whole phase; `get_business_date()` fallback; reports in or out; B-10 #1–#3 (GT-D6).
- Staleness threshold (B-10 #5), and a basis-checking invariant (B-10 #4, constitutional) (GT-D6).
- Reopen / override control under a single operator (GT-D12).
- How and when the 53-day stale production date is brought current (GT-D7).
- N for the multi-day sequence, the interrupted-close scenarios, and replay/GM re-baseline authority (GT-D6, GT-D8).
- The meaning of Phase Gates A–H for Phase 3 (GT-D5).
- Fresh-install default `night_audit_enabled='true'` versus FD-P2-05 (GT-D6 scope or G11 procedure).
