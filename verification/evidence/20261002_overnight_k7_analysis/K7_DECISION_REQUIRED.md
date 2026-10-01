# K-7 DECISION REQUIRED

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, analysis only |
| Code / governance | `C:/wtov` at `c9eeff0` (`app/` = live `c703150`) |
| Current status | K-7 implementation **NOT AUTHORIZED**; production deployment **NOT AUTHORIZED** (`K7_ARCHITECTURE_ANALYSIS.md` §0) |
| Companions | `K7_ARCHITECTURE_ANALYSIS.md`, `K7_WRITER_INVENTORY.md`, `K7_DEPENDENCY_MAP.md`, `K7_PRODUCTION_RISK.md`, `BUSINESS_DATE_PRODUCTION_DECISION.md` |

Nothing below is a decision. Options are listed without preference unless a line is explicitly labelled **ANALYSIS**. The stale production business date is decided separately (BD-D1 … in `BUSINESS_DATE_PRODUCTION_DECISION.md`) and must not be bundled into any K-7 deployment.

---

## K7-D1 — Directive and phase authority

- **DECISION ID:** K7-D1
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** K-7 / Phase 3 governance
- **QUESTION:** Will a Phase 3 directive be issued for unit 3.1 (K-7 core) ahead of units 3.2–3.8, and does it waive or require the Phase 3 entry item "scheduler-controls ADR" (B-1) and the unrecovered Gates A, C–H?
- **WHY REQUIRED:** FD-013 (`verification/FOUNDER_DECISIONS.md:705`), AR-008 (`verification/evidence/20260908_architecture_resolution_round1/RECORD.md:106`) and ADR-004 (`verification/adr/ADR-004-business-date-authority.md:53-55`) forbid implementation without a directive; Q-3 places K-7 in Phase 3 (`FOUNDER_DECISIONS.md:1015`); `FOUNDER_DECISIONS.md:1206` "No phase implementation is authorized". Master Plan §14 lists the scheduler-controls ADR as a Phase 3 prerequisite (`verification/MASTER_PLAN.md:370`); no B-1 ADR exists (`verification/adr/BACKLOG.md:12`). Phase 3 gates "A, C, D, E, F, G, H" (`MASTER_PLAN.md:150`) cannot be checked (`:347`).
- **OPTIONS:**
  - A. Directive for unit 3.1 only (K-7 core), stating that B-1 is not an entry condition for 3.1 because the first release keeps the scheduler off (FD-P2-05), and that the directive is checked against G-gates (G3/G6/G10) instead of A–H.
  - B. Directive for units 3.1 + 3.5 + 3.6 (the FD-P2-05 first-release controls) together.
  - C. Full Phase 3 directive (3.1–3.8), after the B-1 ADR is written.
  - D. No directive now; K-7 stays OPEN.
- **EVIDENCE:** `K7_ARCHITECTURE_ANALYSIS.md` §0; `K7_DEPENDENCY_MAP.md` E-1…E-3; `FOUNDER_DECISIONS.md:1175` (FD-P2-05 consequence).
- **DEPENDENCIES:** none upstream; K7-D2…K7-D7 supply the directive's content.
- **WHAT IS BLOCKED:** all K-7 code and its evidence pack; the G3 "business-date dating" item; G6 "no wall-clock financial dating".
- **WHAT CAN CONTINUE:** this analysis; the test plan and fixture design in §P (documents only); SR-1 decisions (DQ-01…DQ-05) except the refund-basis coupling (K7-D2/DQ-04); the business-date production decision (BD-D1…).
- **EXACT ACTION AFTER DECISION:** record the ruling in `FOUNDER_DECISIONS.md` (new round entry); if A/B/C, issue the directive text naming sites (K7-D2), fallback/default rules (K7-D3), voucher basis (K7-D4), late checkout (K7-D5), reports (K7-D6), evidence standard (K7-D7), "historical rows untouched", push/merge authority, and "no production deployment".

## K7-D2 — Site scope of the K-7 unit

- **DECISION ID:** K7-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** K-7 scope
- **QUESTION:** Which sites are in the K-7 unit?
- **WHY REQUIRED:** `KNOWN_DEFECTS.md:13` lists the writer sites and model defaults only; the inventory found additional calendar/UTC dating that ADR-004 governs or leaves UNRESOLVED (`K7_WRITER_INVENTORY.md` §§1–8). Q-3 forbids "unrelated date refactoring" (`FOUNDER_DECISIONS.md:1017`), so scope must be explicit.
- **OPTIONS (each item in or out):**
  1. Core writers W-08, W-09, W-10, W-11, W-17, W-20, W-22, W-23 (`K7_WRITER_INVENTORY.md` §1) — W-22/W-23 have no caller in `app/` (`app/services.py:1283`): change, or leave and record as unreachable.
  2. Voucher `issued_date` (`app/services.py:1965`) — see K7-D4 for expiry.
  3. Secondary business-date fallbacks `app/routes.py:4770`, `app/occupancy_engine.py:87`, `app/kpi_command_center.py:72`.
  4. Late-checkout applicability (B-10 #2) — K7-D5.
  5. Void day mapping (`app/night_audit_service.py:215-219`) and shift day mapping (`:240-244`) — B-10 #3.
  6. Invoice / receipt / credit-note dates and their UTC rendering (`app/templates/invoice.html:39-40`, `app/templates/invoice_pdf.html:331-332`, `app/gst_einvoice.py:44`, `app/gstr_export.py:40`, `:192-193`, `:281-282`, `app/routes.py:195`) — B-10 #1.
  7. Report default ranges — K7-D6.
- **EVIDENCE:** `K7_WRITER_INVENTORY.md`; ADR-004 `:39-47`.
- **DEPENDENCIES:** K7-D1. Item 1's W-10 couples to SR-1 DQ-04 (`verification/evidence/overnight_execution/DECISION_QUEUE.md:12`).
- **WHAT IS BLOCKED:** directive text; harness test matrix.
- **WHAT CAN CONTINUE:** §P per-site test design for every candidate site (it is scope-agnostic).
- **EXACT ACTION AFTER DECISION:** write the in-scope site list, with file:line at the directive's base commit, into the directive; mark out-of-scope items OPEN with their B-10 number in `verification/adr/BACKLOG.md` only if the Founder authorizes editing it (otherwise in the new evidence pack).

## K7-D3 — `get_business_date()` fallback and model defaults

- **DECISION ID:** K7-D3
- **DATE DISCOVERED:** 2026-10-02 (fallback recorded 2026-09-08 in ADR-004 `:26-27`; DDL hazard new)
- **WORKSTREAM:** K-7 design
- **QUESTION:** (a) When the `business_date` row is missing, should `get_business_date()` fail closed (raise) or return the calendar? (b) What replaces `default=date.today` on `payments.payment_date`, `extra_charges.charge_date`, `credit_vouchers.issued_date`?
- **WHY REQUIRED:** AR-008 forbids silent substitution of `date.today()` (`RECORD.md:106`); the fallback is silent (`app/services.py:621`). Removing a default without a replacement stores **NULL** for payments/charges (nullable, no DDL default — `app/models.py:775`, `:809`) or the **UTC** date for vouchers (`app/__init__.py:1794` `DEFAULT (date('now'))`) (`K7_ARCHITECTURE_ANALYSIS.md` §6).
- **OPTIONS:**
  - (a1) fail closed with a logged error; (a2) calendar with a logged warning; (a3) unchanged.
  - (b1) a Python default that resolves `get_business_date()` at insert; (b2) a default that raises unless the writer passes a date (fail closed); (b3) keep `date.today` (out of scope); (b4) NOT NULL at DB level — a schema change (B-3/B-4, PD-004) — not proposed.
- **EVIDENCE:** `app/services.py:619-621`; `app/models.py:775`, `:809`, `:1817`; `app/__init__.py:1577`, `:1794`, `:1845-1852`.
- **DEPENDENCIES:** K7-D1.
- **WHAT IS BLOCKED:** negative tests N-1/N-2 and fallback tests F-1…F-3 in §P cannot have expected results.
- **WHAT CAN CONTINUE:** fixture design for the missing-row case.
- **EXACT ACTION AFTER DECISION:** state the chosen (a)/(b) options in the directive; the harness asserts them.

## K7-D4 — Credit-voucher date basis (issue, expiry anchor, expiry test)

- **DECISION ID:** K7-D4
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** K-7 scope / liability terms
- **QUESTION:** On which basis are a voucher's issue date, expiry anchor (`issued + expiry_days`) and expiry test evaluated — business date or calendar — and must the voucher report use the same basis?
- **WHY REQUIRED:** today the anchor and test are calendar (`app/services.py:1950`, `:2009`, `:2077`) and the report's `days_left` uses the business date (`app/reports.py:6429`, `:6457`). Moving only the issue date shortens or lengthens guest liabilities by the business-date lag (`K7_PRODUCTION_RISK.md` §4). ADR-004 does not name vouchers.
- **OPTIONS:** (A) all on business date; (B) issue date on business date, expiry anchor and test on calendar (contractual validity in calendar days); (C) issue date and anchor on business date, test on calendar (not recommended by the analysis: shortens validity by the lag); (D) out of K-7 scope.
- **EVIDENCE:** as above; production holds 0 vouchers (`20260930_adr011_production_application/prod_post_state.json`).
- **DEPENDENCIES:** K7-D1, K7-D2.
- **WHAT IS BLOCKED:** voucher tests V-1…V-4 in §P.
- **WHAT CAN CONTINUE:** fixture design for boundary-date vouchers.
- **EXACT ACTION AFTER DECISION:** write the basis into the directive; the harness asserts issue, expiry and redemption refusal on both sides of the boundary.

## K7-D5 — Late-checkout applicability (B-10 #2)

- **DECISION ID:** K7-D5
- **DATE DISCOVERED:** 2026-09-09 (F-7, `20260909_phase1_verification_completion/VERIFICATION_COMPLETION.md:117`); re-confirmed 2026-10-02 incl. the GET preview
- **WORKSTREAM:** K-7 scope / B-10
- **QUESTION:** Is "departure day or later" judged on the business date or the calendar, and is it inside the K-7 unit?
- **WHY REQUIRED:** POST `app/routes.py:3206-3209` and preview `:3850-3853` both use the calendar; ADR-004 leaves the basis UNRESOLVED (`ADR-004:44`); B-10 #2 (`BACKLOG.md:21`). Preview and post must move together (`app/routes.py:3862-3868`).
- **OPTIONS:** (A) business date, in K-7; (B) calendar retained, recorded as ruled; (C) out of K-7, later B-10 directive.
- **EVIDENCE:** `K7_PRODUCTION_RISK.md` §§1, 5.
- **DEPENDENCIES:** K7-D1; BD-D1 (with a stale date, option A suppresses the fee; calendar over-applies it for walk-ins).
- **WHAT IS BLOCKED:** test L-1…L-3 in §P.
- **WHAT CAN CONTINUE:** fixture design.
- **EXACT ACTION AFTER DECISION:** directive names both lines; harness asserts preview amount = posted amount.

## K7-D6 — Report default ranges

- **DECISION ID:** K7-D6
- **DATE DISCOVERED:** 2026-09-30 (conflict §C.1 of the 09-30 package); list widened 2026-10-02
- **WORKSTREAM:** K-7 scope / reporting
- **QUESTION:** Do report default ranges move to the business date inside K-7, and do statutory exports (GSTR-1 default previous month, `app/reports.py:5897`) stay calendar-based?
- **WHY REQUIRED:** ADR-004 `:42` (ranges on business date) conflicts with Master Plan Phase 3 "Not touched: … reports" (`MASTER_PLAN.md:150`). Sites: `K7_WRITER_INVENTORY.md` §7.
- **OPTIONS:** (A) in K-7 except statutory exports; (B) in K-7 including statutory exports; (C) out of K-7 — a later reporting directive (Phase 4/6) with an explicit carve-out of Phase 3's "Not touched".
- **EVIDENCE:** as above.
- **DEPENDENCIES:** K7-D1; ADR-009 (reporting authorization, PROPOSED) if routes are touched.
- **WHAT IS BLOCKED:** report-range tests R-1/R-2.
- **WHAT CAN CONTINUE:** the site list in `K7_WRITER_INVENTORY.md` §7 is available for the directive.
- **EXACT ACTION AFTER DECISION:** directive lists the report sites in or out; if in, the Golden Master expectation must be restated (a run with clock = business date will not show movement — `K7_DEPENDENCY_MAP.md` E-17).

## K7-D7 — Evidence standard, basis invariant and frozen suites

- **DECISION ID:** K7-D7
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** K-7 verification
- **QUESTION:** (a) What evidence proves K-7? (b) Is a basis-checking invariant registered (B-10 #4)? (c) How are frozen suites whose recorded outcomes move (Phase 1 sets A/B, W-20 pack, CF-10 regression harnesses) handled?
- **WHY REQUIRED:** no test proves dating basis today (`verify_writers.py:172`, `:480`, `:752` record dates; `20260909_w20_runtime/verify.py:211` records); the Golden Master cannot see K-7 (clock frozen to the business date, GET-only — `verification/golden/capture.py:7-10`, `:246-258`; `verification/golden/catalogue.py:4`); SC-4 forbids editing packs (`MASTER_PLAN.md:42`), SC-5 forbids reclassification without a ruling (`:43`); §07 Layer 1 makes a new invariant a constitutional matter (`:262`).
- **OPTIONS:**
  - (a1) a K-7 harness on copies with clock ≠ business date, RED at base / GREEN at K-7 commit, plus the G10 battery (§P); (a2) a1 plus a Layer-2 test module kept in the repository.
  - (b1) register a basis invariant (constitutional amendment, commissioning with seeds); (b2) no invariant; harness evidence only.
  - (c1) new superseding packs, old packs stay as history, with a declared-delta list; (c2) re-baseline the old expectations (requires explicit authorization; conflicts with SC-4 as written).
- **EVIDENCE:** `K7_DEPENDENCY_MAP.md` E-14…E-18.
- **DEPENDENCIES:** K7-D1…K7-D6.
- **WHAT IS BLOCKED:** the K-7 evidence pack's acceptance criteria.
- **WHAT CAN CONTINUE:** §P plan.
- **EXACT ACTION AFTER DECISION:** directive cites the evidence standard; the pack contains the declared-delta list for every frozen suite outcome that moved.

## K7-D8 — Deployment sequencing with the stale business date

- **DECISION ID:** K7-D8
- **DATE DISCOVERED:** 2026-09-30 (D-K1); restated 2026-10-02 (53 days)
- **WORKSTREAM:** K-7 / production
- **QUESTION:** May K-7 be deployed to production before the business date is brought current, and is a separate production authorization required for the deployment?
- **WHY REQUIRED:** with the date at 2026-08-10, K-7 dates all new activity on 2026-08-10, in the same day as five D11 rows (`K7_PRODUCTION_RISK.md` §§2–3, 8). FD-019 (`FOUNDER_DECISIONS.md:848-850`) separates implementation from production authorization.
- **OPTIONS:** (A) deploy only after BD-D1 is executed and verified; (B) deploy first, accept 2026-08-10 dating until the date is advanced; (C) no deployment in the first release.
- **EVIDENCE:** `K7_PRODUCTION_RISK.md`; `BUSINESS_DATE_PRODUCTION_DECISION.md`.
- **DEPENDENCIES:** K7-D1; BD-D1. Constraint regardless of option: the business-date advance and the K-7 deployment are **separate** production operations with separate evidence (SC-6, `MASTER_PLAN.md:44`).
- **WHAT IS BLOCKED:** any K-7 production deployment.
- **WHAT CAN CONTINUE:** K-7 code on copies once K7-D1 is ruled.
- **EXACT ACTION AFTER DECISION:** record the sequencing in the deployment authorization (PD-004) with PD-005 steps and FD-P2-04 conditions 1–7, 9, 10.

## K7-D9 — Gate accounting (G3 vs G6)

- **DECISION ID:** K7-D9
- **DATE DISCOVERED:** 2026-09-30 (09-30 package §C.5)
- **WORKSTREAM:** certification
- **QUESTION:** Can G3's "business-date dating at all writers (K-7)" be scored PASS on unit 3.1 alone while G6 (3.2–3.8, staleness, N7) remains open?
- **WHY REQUIRED:** `CERTIFICATION_GATES.md:33` (G3) and `:36` (G6) share content; neither text answers it.
- **OPTIONS:** (A) yes — G3 needs 3.1 evidence only; (B) no — G3's item passes only with G6.
- **EVIDENCE:** as above.
- **DEPENDENCIES:** K7-D1.
- **WHAT IS BLOCKED:** G3 disposition after K-7.
- **WHAT CAN CONTINUE:** everything else.
- **EXACT ACTION AFTER DECISION:** note in the G3 evidence pack which reading applies.

## K7-D10 — Night-audit close-path divergence

- **DECISION ID:** K7-D10
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** Phase 3 (3.1 / 3.2)
- **QUESTION:** Is the divergence between the two operator close paths (path A posts no-shows and room rent, `app/services.py:353`, `:413-421`; path B — the panel's Run/Complete — posts neither, `app/reports.py:2824-3101`) and path A's date-free in-house filter (`app/services.py:364`) inside the 3.1 directive, a separate 3.2 item, or accepted as is for the first release?
- **WHY REQUIRED:** FD-P2-05 makes the manual close the first-release model (`FOUNDER_DECISIONS.md:1172`); which path the "written daily-close procedure" (`:1175`) uses decides whether room-rent ledger rows and no-show processing exist at all. Bringing the business date current (BD-D1) also depends on it.
- **OPTIONS:** (A) in 3.1; (B) Phase 3 unit 3.2 directive; (C) accept; the daily-close procedure names one path and its effects.
- **EVIDENCE:** `K7_ARCHITECTURE_ANALYSIS.md` §3; `verification/FORCE_CLOSE_INVESTIGATION.md` §8.
- **DEPENDENCIES:** K7-D1; BD-D2.
- **WHAT IS BLOCKED:** the written daily-close procedure (G11).
- **WHAT CAN CONTINUE:** rehearsal of both paths on copies (§P, test C-3).
- **EXACT ACTION AFTER DECISION:** record the ruling; name the path in the procedure.

## K7-D11 — Disposition of defect candidates found by this analysis

- **DECISION ID:** K7-D11
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** defect register
- **QUESTION:** Are the following registered as carry-forward findings and routed (to K-7, B-10 #1, or a bounded fix directive): N-7 invoice/e-invoice/GSTR-1 dates rendered from UTC `checked_out_at` without IST conversion; N-8 probable exclusion of last-day credit notes from GSTR-1 CDNR (`app/gstr_export.py:278-284`, NOT VERIFIED); N-10 `NoShowResult` constructed with non-existent fields after a `rollback()` (`app/noshow_service.py:100-108`)?
- **WHY REQUIRED:** SC-5 (`MASTER_PLAN.md:43`) — findings are not reclassified or absorbed without a ruling; N-7/N-8 touch statutory output.
- **OPTIONS:** (A) register and route each; (B) register only; (C) verify N-8 on a copy first, then decide.
- **EVIDENCE:** `K7_ARCHITECTURE_ANALYSIS.md` §9.
- **DEPENDENCIES:** none.
- **WHAT IS BLOCKED:** nothing in K-7 directly.
- **WHAT CAN CONTINUE:** all.
- **EXACT ACTION AFTER DECISION:** add the findings to the carry-forward register in a new evidence pack (SC-4).

---

## §P — Preparation that can proceed without a decision (plans only; no code written)

### P.1 Principles

- All runs on disposable copies made with `verification/dbcopy.py :: make_copy()` (SC-2, `MASTER_PLAN.md:40`); production SHA-256 recorded before and after (SC-1).
- Worktree at the base commit for RED and at the K-7 commit for GREEN (ADR-011 method; see `verification/evidence/20260930_cf10_completion/`).
- The clock is frozen with the existing proven freezer (`verification/golden/freeze.py:112` `ClockFreeze`, `:262` `install_proven`) at an instant whose **date differs from the copy's business date**; the harness records the freeze proof. The Golden Master's own capture is not used for K-7 (E-17).
- No application process outlives a run (SC-3); no harness touches `instance/`.

### P.2 Fixture design (built on the copy, through application code paths where one exists)

| Fixture | Content | Purpose |
|---|---|---|
| F-BD | `business_date` set on the copy to **2026-08-10**; clock frozen at **2026-10-02 12:00 IST** ("lag" case) | every site: row date must equal 2026-08-10 after K-7, 2026-10-02 before |
| F-AHEAD | business date **D+1**, clock **D 23:30 IST** (close performed before midnight) | closed-day case: rows must not land in D |
| F-UTC | clock **00:30 IST** (= previous UTC day) | UTC-vs-IST boundary for voucher DDL default, invoice date, void day |
| F-CLOSED | a `NightAuditLog` Completed for business date − 1 with a payment dated in it (non-D11, attributed) | W-08/W-09 correction via the void override path |
| F-STAY | CheckedIn reservation with folio A, normal rate; a second one `booking_type='Hourly'` with `checkout_time` set | W-17, W-20, late checkout |
| F-CANCEL | Confirmed reservation with an advance payment | W-10 refund and voucher issue (dispositions `refund_full`, `credit_voucher`) |
| F-VOUCHER | active voucher with expiry = business date, = calendar date, and between the two | expiry basis |
| F-NOROW | copy with the `business_date` row deleted | fallback tests |
| D11 | the eight D11 rows untouched (FD-010) | must be byte-identical after every run |

### P.3 Per-site dating tests (one row per site; expected values depend on K7-D2…D5)

| Test | Site | Entry point | RED at base (expected) | GREEN at K-7 (expected) |
|---|---|---|---|---|
| S-08/09 | W-08/09 | `POST` void with Admin override on F-CLOSED (`app/routes.py:7816`) and `billing.direct_void` (`app/billing.py:398`) | reversal/replacement dated clock date | dated business date |
| S-10 | W-10 | `POST` cancel (`app/routes.py:8760`) on F-CANCEL | refund dated clock | business date |
| S-VI | voucher issue | cancel with `credit_voucher` disposition | `issued_date` clock; expiry clock+365 | per K7-D4 |
| S-11 | W-11 | `voucher_redeem` (`app/routes.py:9438`) and new-reservation redemption (`:2266`) | payment dated clock | business date |
| S-17 | W-17 | checkout with extra (`app/routes.py:3049`) | model default = clock | business date (or explicit, per K7-D3) |
| S-20 | W-20 | overstay on the Hourly stay (`app/routes.py:7983`) | `now.date()` | business date; amount unchanged |
| S-22/23 | W-22/23 | service call (no route exists) | clock | business date |
| S-BD | all 16 BD writers | their routes | business date | business date (no regression) |
| S-TL | TaxLines generated for S-17/S-20 | `gst_service` | `charge_date` = row date | = business date |

### P.4 Negative tests

| Test | Assertion |
|---|---|
| N-1 | a `Payment`/`ExtraCharge` created without an explicit date behaves as ruled in K7-D3(b) (raises, or takes the business date) — never the calendar, never NULL |
| N-2 | scan after the full run: no `payments`/`extra_charges`/`credit_vouchers` row created during the run has a date ≠ the business date in force at its `created_at` |
| N-3 | F-AHEAD: no row lands in the closed day D; `inv-run` INV-B01 and INV-B03 HOLD |
| N-4 | F-BD: INV-B04 HOLDS after the run (no row dated beyond the business date) |
| N-5 | D11 rows and the 2026-08-09 snapshot byte-identical before/after (FD-010, Q06-H1) |
| N-6 | each GREEN dating change is reverted on a scratch copy of the code and the matching S-test turns RED (the test is load-bearing) |

### P.5 Fallback tests

| Test | Assertion |
|---|---|
| F-1 | F-NOROW: `get_business_date()` behaves as ruled (raise + log, or calendar + log) |
| F-2 | F-NOROW: each writer either refuses (no row, no audit row) or dates as ruled; nothing is written silently |
| F-3 | the three secondary fallbacks (`app/routes.py:4770`, `app/occupancy_engine.py:87`, `app/kpi_command_center.py:72`) behave as ruled, if in scope |

### P.6 Other scope-dependent tests

- L-1 late checkout on departure day by the ruled basis; L-2 not before departure; L-3 preview amount = posted amount.
- V-1…V-4 voucher redemption accepted/refused on each side of the expiry boundary under F-BD and F-UTC; status derivation agrees with the report's `days_left`.
- R-1/R-2 report default ranges (if in scope) under F-BD with a clock ≠ business date.
- C-3 close-path comparison: run path A and path B for the same date on two copies; record the posting difference (input to K7-D10 and BD-D2).

### P.7 Regression battery (G10, at the K-7 commit, on copies)

`gm-verify` against `phase1_aa6d9e91` (no-regression only), replay on production copy, `inv-run` (production read-only and copies), `ds-run` five datasets incl. SR-2 reachability, `fault-run`, cross-implementation (Q14), Phase 2a matrix 29/29, CF-10/CF-11 harnesses, Phase 1 writer harness and W-20 pack **as new packs** (declared deltas per K7-D7), Q06 check (`verification/quantities.py:496-532`), retention check, ADR-011 actor checks, restore-tool rehearsal.

### P.8 Rollback approach for a K-7 deployment (plan)

1. K-7 is schema-free and migration-free; rollback is a **code** rollback: return the live checkout to the previous tag (fast-forward-only history, one commit per unit — SC-6), followed by the smoke and G10 checks used for ADR-011 (`verification/evidence/20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md` §§2–4).
2. Rows written between deploy and rollback keep their business dates — which is the ADR-004-intended basis — so **no data rollback** is planned. Their ids are listed in the deployment evidence so that a later mixed-basis period is identifiable.
3. Before deploy: an FD-P2-04 backup meeting conditions 1–7, 9, 10 (`FOUNDER_DECISIONS.md:1163`) with a restore rehearsal (`tools/restore_db.py`), as a recovery path for unexpected effects, not as the rollback mechanism.
4. The deployment must not coincide with any business-date advance (K7-D8); if both are authorized they are executed, verified and evidenced separately so either can be rolled back alone.
5. Stop criterion: any row dated ≠ business date, any D11 or sealed-snapshot change, any invariant movement not in the declared-delta list → stop, roll back code, report.
