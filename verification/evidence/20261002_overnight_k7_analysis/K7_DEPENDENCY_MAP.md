# K-7 DEPENDENCY MAP

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, analysis only |
| Code / governance | `C:/wtov` at `c9eeff0` (`app/` = live `c703150`) |
| Supersedes nothing | extends `FinalGrid/g3_decision_package/G3_DEPENDENCY_MAP.md` (2026-09-30); differences are marked **[NEW]** or **[CHANGED]** |

Status vocabulary: PASS · FAIL · BLOCKED · OPEN · NOT VERIFIED · NOT AUTHORIZED · NOT APPLICABLE.

---

## 1. Tree

```
K-7 business-date dating (G3 condition; G6 content) ................ OPEN — NOT AUTHORIZED
├── Authority
│   ├── FD-013 / AR-008 / ADR-004 principle ............................ adopted; "no implementation"
│   ├── Phase 3 directive (unit 3.1 at least) .......................... OPEN (none exists)
│   │   ├── Phase 3 entry: "Phase 1 complete" ......................... PASS (MASTER_PLAN.md:370; accepted FOUNDER_DECISIONS.md §Phase 1 Formal Acceptance)
│   │   ├── Phase 3 entry: ADR-004 adoption ............................ PASS (FOUNDER_DECISIONS.md:949)
│   │   ├── Phase 3 entry: scheduler-controls ADR (B-1) ................ OPEN — no ADR (BACKLOG.md:12)   [NEW]
│   │   └── Phase 3 gates A, C–H ....................................... OPEN — text unrecovered (MASTER_PLAN.md:13, :347)
│   └── production deployment authorization (FD-019, FD-005/PD-005) .... NOT AUTHORIZED
├── Design rulings (B-10, ADR-004 "Unresolved")
│   ├── #1 invoice date rule ........................................... OPEN (+ UTC printing, N-7)   [NEW detail]
│   ├── #2 arrival/departure validation basis (late checkout F-7) ..... OPEN
│   ├── #3 shift → business-date mapping (also void day, N-6) ......... OPEN   [NEW detail]
│   ├── #4 basis-checking invariant (constitutional registration) ..... OPEN
│   └── #5 staleness threshold (unit 3.6) .............................. OPEN — production 53 days stale
├── Scope rulings not in B-10   [NEW]
│   ├── voucher issue date / expiry anchor / expiry test basis ........ OPEN
│   ├── get_business_date() fallback + 3 secondary fallbacks .......... OPEN
│   ├── model-default replacement (NULL / UTC-DDL hazard) ............. OPEN
│   └── report default ranges (ADR-004 :42 vs Phase 3 "Not touched: reports") ... OPEN (conflict)
├── Verification dependencies
│   ├── frozen suites whose recorded outcomes may move ................ re-baseline NOT AUTHORIZED
│   │   (Phase 1 sets A/B; W-20 pack; CF-10 regression harnesses)
│   ├── Golden Master: structurally blind to K-7 (clock frozen = business date) ... NOT APPLICABLE as K-7 evidence   [NEW]
│   ├── no Layer-2 test suite (R3) .................................... OPEN — K-7 needs its own harness
│   └── G10 regression battery at the K-7 commit ...................... OPEN
└── Production dependencies
    ├── production business date 2026-08-10, 53 days stale ............ OPEN — separate decision (BUSINESS_DATE_PRODUCTION_DECISION.md)
    ├── open day 2026-08-10 contains 5 of the 8 D11 rows ............... FD-010 / FD-P2-03 interplay   [NEW]
    └── sealed 2026-08-09 snapshot (Q06-H1) ............................ untouched by K-7 — NOT APPLICABLE
```

---

## 2. Edges

| # | From | To | Kind | Evidence | Note |
|---|---|---|---|---|---|
| E-1 | K-7 code | Phase 3 directive (3.1) | **requires** | `FOUNDER_DECISIONS.md:705`, `:1015-1017`, `:1206`; `ADR-004:53-55` | no directive → NOT AUTHORIZED |
| E-2 | Phase 3 directive | B-1 scheduler-controls ADR | **entry condition as written** | `MASTER_PLAN.md:370` ("scheduler-controls ADR"); `BACKLOG.md:12` (no ADR) | **[NEW]** the 09-30 package said "Entry: Phase 1 complete (met)"; §14 also lists the B-1 ADR. FD-P2-05 (`:1175`) defers automation behind B-1 but does not waive the entry line. Needs a ruling (K7-D1) |
| E-3 | Phase 3 directive | Gates A, C–H meaning | **checkability** | `MASTER_PLAN.md:150`, `:347` | unchanged from 09-30 (#7) |
| E-4 | K-7 scope | B-10 #2 | **in-scope only if ruled** | `ADR-004:44`; `BACKLOG.md:21`; F-7 `VERIFICATION_COMPLETION.md:117` | late-checkout applicability `app/routes.py:3206-3209`, preview `:3850-3853` |
| E-5 | K-7 scope | B-10 #1 | **in-scope only if ruled** | `ADR-004:43` | invoice/receipt/credit-note dates are UTC-derived (`app/templates/invoice.html:39-40`, `app/gst_einvoice.py:44`, `app/gstr_export.py:40`, `:192-193`, `:281-282`) |
| E-6 | K-7 scope | B-10 #3 | **in-scope only if ruled** | `ADR-004:45` | shifts and voids are mapped to days from UTC timestamps (`app/night_audit_service.py:215-219`, `:240-244`) |
| E-7 | K-7 evidence | B-10 #4 | **if a basis invariant is wanted** | `ADR-004:47`; `MASTER_PLAN.md:262` (§07 Layer 1) | a new invariant is a constitutional registration; without it K-7 evidence is harness-only |
| E-8 | K-7 deploy | B-10 #5 / unit 3.6 | **operational safety** | FD-P2-05 `FOUNDER_DECISIONS.md:1175`; `CERTIFICATION_GATES.md:22` ("staleness escalation") | with K-7, a stale date silently back-dates every row; no escalation exists |
| E-9 | K-7 deploy | production business date current | **blocks sensible dating** | orchestrator fact: 2026-08-10 vs 2026-10-02 | see `K7_PRODUCTION_RISK.md`; separate decision BD-D1 |
| E-10 | business date current | FD-P2-05 manual close + unit 3.5 | procedure | `FOUNDER_DECISIONS.md:1172-1175` | 53 closes or Force Close; each a production operation |
| E-11 | SR-1 (INV-B06 refund clause) | K-7 refund dating | **text depends on** | `20261002_overnight_sr1/SR1_DECISION_REQUIRED.md` SR1-D4 (DQ-04) | refund `payment_date` is WC today (`app/services.py:1807`), BD after K-7 |
| E-12 | SR-1 (INV-B06 advance clause) | stale business date | **outcome depends on** | INV-B06 bounds `[arrival, departure+30]` (`verification/invariants/rules_b.py:607-698`); BD writers date payments 2026-08-10 | **[NEW]** with the date stale, *every* business-dated payment for a stay arriving on or after 2026-10-02 is dated before arrival — INV-B06 fires on W-01…W-07/W-12 today, independent of K-7 |
| E-13 | SR-2 (INV-D02) | K-7 | **none** | SR2-REV2 item 7 (`FOUNDER_DECISIONS.md:1341`): no ordering check on dates | NOT APPLICABLE |
| E-14 | K-7 | Phase 1 sets A/B outcomes | **outcomes move as intended** | `VERIFICATION_COMPLETION.md:47-48` (B04/B06 attributed to K-7) | re-running at the K-7 commit changes recorded findings; SC-4 (`MASTER_PLAN.md:42`) forbids editing the old pack, SC-5 (`:43`) forbids reclassifying without a ruling |
| E-15 | K-7 | W-20 runtime pack | **recorded value moves** | `20260909_w20_runtime/W20_RUNTIME_VERIFICATION.md:78` (`charge_date` 2026-09-09), `:178` | the pack records, does not assert, the date (`verify.py:211`) |
| E-16 | K-7 | CF-10 / ADR-011 regression harnesses | recorded values may move | `20260930_cf10_completion/reg_verify_writers.py`, `reg_w20_runtime_verify.py` (copies of the Phase 1 harnesses) | the harness at `20260909_phase1_verification_completion/verify_writers.py:480` notes W-17's model default as "K-7, Phase 3"; dates are recorded (`:172`, `:752`), not asserted |
| E-17 | K-7 evidence | Golden Master | **cannot detect K-7** | `verification/golden/capture.py:7-10`, `:246-258` (clock frozen at noon of the copy's business date); `verification/golden/catalogue.py:4` (GET surfaces only) | **[NEW]** wall clock = business date inside every GM run and no writer is exercised, so GM 0-difference is a no-regression check only. `PVF_GM_FREEZE_DATE` (`capture.py:249-256`) is "commissioning-only". `20260910_phase2_entry/WORK_ESTIMATE.md:10` ("every date change moves report figures → Golden Master re-baseline") is therefore not expected for writer changes; for report-range changes it holds only if a run's clock ≠ its business date |
| E-18 | K-7 evidence | Layer-2 tests | **absent** | `MASTER_PLAN.md:204` (R3 "No app business-logic test suite", Phase 6) | K-7 needs a dedicated harness (see `K7_DECISION_REQUIRED.md` §P) |
| E-19 | K-7 | G3 | condition | `CERTIFICATION_GATES.md:33` | G3 also needs SR-1 (open); SR-2 delivered on `main` |
| E-20 | K-7 | G6 | shared content | `CERTIFICATION_GATES.md:36` ("single derivation; no wall-clock financial dating; …; staleness escalation; N7") | G6 also needs 3.2–3.8; whether G3's K-7 item can pass on 3.1 alone is unstated (09-30 #6) |
| E-21 | K-7, BD advance | G11 | procedure | `CERTIFICATION_GATES.md:21` ("day-one procedure: set the business date … run the first close"), `:41` | G11 needs a written procedure that does not exist |
| E-22 | K-7 | G10 | every change | `CERTIFICATION_GATES.md:40` | worktree battery (ADR-011 method) |
| E-23 | BD advance | FD-010 / FD-P2-03 (D11 rows) | **interpretation** | `FOUNDER_DECISIONS.md:47-56` (payments 3–6 and extra_charges 2 lie in the open day 2026-08-10); FD-010 "No night-audit modification is authorized" (`:593` section) | **[NEW]** closing 2026-08-10 seals five D11 rows into a closed, locked day and a hashed snapshot. Whether that is a permitted ordinary close or a "night-audit modification" of D11 is not ruled |
| E-24 | K-7 deploy | B-4 migration mechanism | none | K-7 is schema-free (`K7_ARCHITECTURE_ANALYSIS.md` §6) | NOT APPLICABLE unless a NOT NULL change is chosen |
| E-25 | K-7 | Q06-H1 sealed record | none | `FOUNDER_DECISIONS.md:1219-1227` | K-7 writes forward only; NOT APPLICABLE |
| E-26 | K-7 | CF-11 | prerequisite — PASS | W-11 functional since CF-11 (`app/services.py:2108-2110` comment) | W-11 can now be exercised at runtime |
| E-27 | K-7 | server timezone | removes a dependency | `date.today()` / `datetime.now()` use the host's local zone; IST helpers assume a fixed offset (`app/services.py:787-788`) | business-dated rows stop depending on the host clock zone |

---

## 3. Order constraints (facts; no order chosen)

1. K-7 **code** can be written and verified on copies without touching production — once a Phase 3 (3.1) directive exists (E-1) and E-2/E-3 are ruled or explicitly set aside.
2. K-7 **deployment** cannot sensibly precede a decision on the stale business date (E-9). The reverse is possible: the business date can be brought current under today's code without K-7 (`BUSINESS_DATE_PRODUCTION_DECISION.md`). The two must not be bundled into one production operation (one change, one authorizing reference — SC-6, `MASTER_PLAN.md:44`).
3. SR-1's refund clause either waits for K-7's refund-date ruling or is written basis-independent (E-11; DQ-04).
4. SR-1's advance clause is affected by the stale date regardless of K-7 (E-12).
5. Frozen-suite outcomes that K-7 moves need either an authorization to supersede them with new packs or a ruling that the old packs stand as historical (E-14…E-16). Editing them is excluded by SC-4.
6. The Golden Master cannot be the K-7 proof (E-17); a K-7-specific harness with a clock ≠ business date is required (E-18).

---

## 4. Decision queue (cross-reference)

| Decision | File | Unblocks |
|---|---|---|
| K7-D1 … K7-D9 | `K7_DECISION_REQUIRED.md` | Phase 3 (3.1) directive content; evidence standard; deployment sequencing |
| BD-D1 … BD-D5 | `BUSINESS_DATE_PRODUCTION_DECISION.md` | bringing the production business date current, or accepting it stale |
| DQ-01 … DQ-05 (SR-1) | `verification/evidence/overnight_execution/DECISION_QUEUE.md` | SR-1 directive; DQ-04 couples to K7-D2 |
