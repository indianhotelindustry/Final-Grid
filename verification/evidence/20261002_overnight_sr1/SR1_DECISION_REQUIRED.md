# SR-1 / INV-B06 — DECISION REQUIRED

| | |
|---|---|
| Prepared | 2026-10-02, directive FG-OVERNIGHT-01 §9–§10, branch `overnight-20261002` at base `c9eeff0` |
| Outcome | **BLOCKED — FOUNDER DECISION REQUIRED.** No implementation was made. `verification/invariants/rules_b.py` is unchanged. |
| Production | not touched. Production facts are cited from committed evidence only. |
| Supersedes | nothing. Extends Part B of `FinalGrid/g3_decision_package/G3_DECISION_PACKAGE.md` (2026-09-30, outside the repository) with application-path findings made at `c9eeff0` |

## 1. Why implementation stopped

The directive requires the exact approved SR-1 rule to be recovered from the founder records before code changes, and forbids inventing wording.

| Record | What it says about INV-B06 | Exact rule text? |
|---|---|---|
| SR-1 / SR-2 retention (`verification/FOUNDER_DECISIONS.md:1094-1096`) | "Do NOT modify INV-B06 … until resolved" | no |
| FD-P2-06 (`FOUNDER_DECISIONS.md:1178-1187`) | "INV-B06 must not treat a legitimate business-dated advance payment as an automatic integrity failure … The refinement must preserve detection of genuinely incorrect activity." Governance effect: "**the amendment's exact text, negative seeds and commissioning are the content of the later directive**." | **no — explicitly deferred to a later directive** |
| FD-P2-06 decision pack (`verification/evidence/20260910_phase2_founder_decisions/FOUNDER_DECISION_PACK.md`, INV-B06 table) | a **recommendation** ("Amendment (Founder ruling): …") | recommendation only; the ruling adopted the principle, not the text (`G3_DECISION_PACKAGE.md` B3) |
| Rounds 6 and 7 (`FOUNDER_DECISIONS.md:1292-1354`) | SR-2 only; "SR-1 (INV-B06), K-7 and all other open items are unaffected" (`:1321`); "No change to … SR-1" (`:1354`) | no |

For SR-2 the founder gave rule text (SR2-RULE) and then an interpretation (SR2-REV2) before implementation was accepted. SR-1 has neither. The SR-2 history shows the risk: the first SR-2 directive text, applied literally, would have kept failing legitimate refunds (`INV_D02_STOP_REPORT.md`). The recommended INV-B06 text has a defect of the same kind (§3).

## 2. Current rule (FACT, `verification/invariants/rules_b.py:610-698` at `c9eeff0`)

- Population: every `payments` row with a non-NULL `payment_date` joined to its reservation. All purposes are included: advance, settlement, refund, credit_recovery, NULL. Corrections and reversals are included too.
- Rule: `arrival_date ≤ payment_date ≤ departure_date + 30 days`. The 30-day tail is declared ("post-checkout credit recovery is a legitimate business flow"). There is no leading window.
- MEDIUM / OPERATIONAL; principles P8, P10; COMMISSIONED.
- Negative seed: `UPDATE payments SET payment_date = DATE(payment_date, '-400 day') WHERE id = (SELECT MIN(id) FROM payments)`.
- Latest commissioning: `verification/evidence/20261001_120800_inv_commission/report.txt:137` — `[PASS] INV-B06 (data seed)`, baseline HOLDS over 6 rows, seeded VIOLATED; blast radius `INV-B03: HOLDS/0 -> VIOLATED/2`.
- Production: HOLDS, 6 payments, all settlement, no advance (`G3_DECISION_PACKAGE.md` B2; commissioning positive case "6 row(s)").
- No dataset declares an INV-B06 expectation. No fault-catalogue entry expects INV-B06 (`FLT-B06` is an unrelated tax-line fault, `verification/faults/faults_b.py:306`). An SR-1 change therefore touches only the rule, its seed(s) and commissioning.

## 3. Application payment paths the rule meets (FACT, file:line at `c9eeff0`)

| # | Path | `payment_purpose` | Flags | Date source | Typical date vs stay | Current INV-B06 |
|---|---|---|---|---|---|---|
| F1 | advance at booking — `app/routes.py:2235` (new reservation), `:1961` (bulk/group booking) | `'advance'` if `arrival_date > business_date`, else `'settlement'` (`:2234`, `:1960`) | — | `get_business_date()` | **before arrival** (any lead; see F1-note) | **VIOLATED** (legitimate) |
| F2 | voucher redeemed at advance booking — `routes.py:2266` → `app/services.py:2111` (`redeem_credit_voucher`) | **`'settlement'`** | — | **`_d.today()` (calendar)**, K-7 site W-11 | **before arrival** | **VIOLATED** (legitimate flow; wall-clock dated) |
| F3 | cancellation refund — `services.py:1802` (`post_cancellation_disposition`) | `'refund'` | `is_reversal` | **`_date.today()` (calendar)**, K-7 site W-10 | usually before arrival | **VIOLATED** when before arrival (legitimate) |
| F4 | payment correction pair — `services.py:1223` (reversal), `:1253` (replacement) | **NULL** | `is_correction` (+`is_reversal`) | **`_date.today()` (calendar)**, K-7 sites W-08/09 | the posting day: before arrival when an advance is corrected, or any time after departure | **VIOLATED** when outside window (legitimate per ADR-004: "corrections … dated on the business date of posting") |
| F5 | check-in deposit — `services.py:3160` | NULL | — | `get_business_date()` | arrival day if business date is current; **weeks before arrival if business date is stale** | HOLDS if current; VIOLATED if stale |
| F6 | settlements (checkout, in-stay, OTA) — `routes.py:3303`, `:3343`, `:5837`, `:7544` | `'settlement'` | — | business date | within stay | HOLDS |
| F7 | credit recovery — `routes.py:9348`, `:5837` | `'credit_recovery'` | — | business date | after departure; may exceed 30 days | VIOLATED beyond 30 days (declared tail) |

**F1-note:** the application imposes **no booking horizon**. `app/booking.py:83-88` only rejects past arrivals and stays over 30 nights, so an advance taken 400 days before arrival is a legitimate application outcome. Any leading window is a declared business assumption, like the 30-day tail, and not a fact the code supplies.

**No booking business date is stored.** `reservations` has `created_at` (`app/models.py:337`, `default=datetime.utcnow`, a UTC wall-clock technical timestamp), but no business date of booking. FD-013 makes business date the accounting authority and leaves system timestamps technical (`FOUNDER_DECISIONS.md:692`).

## 4. Findings that make the recommended text unusable as written

The recommendation (FD-P2-06 pack) reads: "payments with `payment_purpose='advance'` may be dated on or before arrival; refunds linked to a cancelled reservation (`reservations.cancellation_refund_payment_id`) may be dated on or before the cancellation; all other purposes keep the current window … negative seed (an advance dated 400 days before arrival still fails)."

| ID | Finding | Effect |
|---|---|---|
| S1-1 | **Internal contradiction.** "On or before arrival" has no lower bound, yet "an advance dated 400 days before arrival still fails" needs one (also `G3_DECISION_PACKAGE.md` §C-3). The app has no booking horizon (F1-note), so the contradiction cannot be resolved from code. | a lead window value or anchor must be ruled |
| S1-2 | **Voucher redemption at booking (F2) is `'settlement'`, not `'advance'`.** An advance-only carve-out keeps reporting a legitimate booking-time voucher application. | purpose scope must be ruled |
| S1-3 | **Corrections carry NULL purpose (F4).** A correction of a pre-arrival advance would stay VIOLATED. A correction of a past stay posted more than 30 days after departure is dated on the posting day, as ADR-004 requires, and is also VIOLATED. | correction treatment must be ruled |
| S1-4 | **Refund date basis.** "On or before the cancellation": the cancellation is evidenced by `cancellation_processed_at` (a technical UTC timestamp, `app/services.py:1834` `_dt.utcnow()`; SR2-REV2 item 3 says it is not proof of status, only of the processing event). The refund `payment_date` is the calendar date today, and the business date after K-7. In IST, a cancellation processed between 00:00 and 05:30 local time has a UTC timestamp on the previous calendar day, so a same-moment refund compares one day late. After K-7, with a stale business date, the refund is dated weeks *before* the processing timestamp. | refund bound and basis must be ruled; depends on K-7 (D-S1) |
| S1-5 | **Stale business date.** With the production business date at 2026-08-10 (53 days stale on 2026-10-02), every business-dated payment is dated 2026-08-10. A check-in deposit (F5) for a stay arriving 2026-10-02 would be dated 53 days before arrival and violate the current rule. That is arguably *genuinely incorrect activity* (posting into a stale day), which FD-P2-06 requires the refinement to keep detecting. A refinement that exempts by purpose alone does not stop detecting it here (the purpose is NULL). A refinement keyed on "any payment before arrival" would. | the founder should confirm that stale-date postings are meant to stay detectable |
| S1-6 | **Seed target.** The existing seed moves `MIN(id)` regardless of purpose. Under a purpose-based exemption it still fails wherever `MIN(id)` is not exempt (production: a settlement). But it would no longer *prove* detection of a far-off advance. FD-P2-06 makes the seeds directive content. | seeds must be ruled (at least one per exempted class) |
| S1-7 | **No lower anchor in data.** A "bounded by the booking date" option has only `reservations.created_at` (UTC technical) to use. Using it mixes bases (FD-013). With a stale business date, every new advance (dated 2026-08-10) predates its reservation's creation (2026-10-02) and would violate. | anchor choice must be ruled |
| S1-8 | **Credit-recovery tail (F7).** A legitimate recovery more than 30 days after departure is reported today. FD-P2-06 does not name it. The 30-day tail is a declared assumption (`rules_b.py` `validation_method`). | in or out of SR-1 scope |

## 5. Decision items (executable)

### DQ-01 / SR1-D1 — INV-B06 exact amendment text

- **DECISION ID:** SR1-D1 (overnight queue DQ-01)
- **DATE DISCOVERED:** 2026-10-02 (gap first recorded 2026-09-30, `G3_DECISION_PACKAGE.md` B14-1)
- **WORKSTREAM:** SR-1 / INV-B06 (G3)
- **QUESTION:** What is the exact INV-B06 rule for payments dated before arrival? Specifically:
  - (a) which payments may precede arrival: `'advance'` only; or also booking-time voucher redemptions (F2) and corrections of exempt rows (F4);
  - (b) the leading bound for those payments: none; a fixed N days before arrival; or anchored to some recorded booking event;
  - (c) whether other payments before arrival (NULL/settlement, e.g. F5 under a stale business date) keep failing.
- **WHY REQUIRED:** FD-P2-06 reserves the exact text to the founder ("the amendment's exact text, negative seeds and commissioning are the content of the later directive"). The recommended text contradicts itself (S1-1) and misses legitimate application paths (S1-2, S1-3). Master Plan §07 Layer 1: invariant changes are constitutional amendments requiring a founder ruling.
- **OPTIONS:**
  - **A — Recommendation as worded, advance unbounded:** `'advance'` exempt from the lower bound; others unchanged. Consequences: F2 and F4 stay VIOLATED; no detection of mis-dated advances, however far; the "400 days still fails" clause is dropped.
  - **B — Advance with a declared lead window of N days** (founder sets N): `arrival − N ≤ payment_date ≤ departure + 30` for `'advance'`. Consequences: detection survives for absurd dates; a legitimate booking more than N days ahead is reported, as the 30-day tail does today for long recoveries.
  - **C — "Pre-arrival class" = advance + booking-time voucher redemption + corrections whose `corrects_id` original is in the class, with window N:** covers F1, F2 and F4. The redemption is identified only by its `'settlement'` purpose plus a `credit_voucher_redemptions` link, so the rule needs that join (verification-side only, no app change).
  - **D — Anchor to `reservations.created_at`:** technical UTC basis (FD-013 conflict); fails every advance taken while the business date is stale (S1-7). Listed for completeness, not recommended.
- **EVIDENCE:** §2–§4 of this file; `FOUNDER_DECISIONS.md:1178-1187`; FD-P2-06 pack; `rules_b.py:610-698`; `app/routes.py:1960,1961,2234,2235,2266`; `app/services.py:1223,1253,1802,2111,3160`; `app/booking.py:83-88`.
- **DEPENDENCIES:** SR1-D2 (refunds) and SR1-D3 (seeds) are part of the same text. SR1-D4 (K-7 sequencing) applies only to the refund clause.
- **WHAT IS BLOCKED:** any edit to `rules_b.py` INV-B06; its commissioning; the SR-1 row of G3.
- **WHAT CAN CONTINUE:** everything else; the SR-1 test design (§6) is written and ready.
- **EXACT ACTION AFTER DECISION:** branch `sr1-inv-b06` from `origin/main` in worktree `C:/wtsr1`; edit INV-B06 rule, metadata text and seeds only; run targeted scenario tests (§6), `inv-commission`, `inv-run` production (expect HOLDS, 6 rows), `ds-run`, `ds-commission`, `fault-run`, `gm-verify phase1_aa6d9e91`, `replay-verify`, cross-implementation, baseline vs branch from worktrees (SR-2 method, `20260930_sr2_inv_d02/run_regression.sh`); evidence pack `verification/evidence/<date>_sr1_inv_b06/`; commit; push the branch only if the directive authorizes it.

### DQ-02 / SR1-D2 — refunds and corrections dated outside the stay

- **DECISION ID:** SR1-D2 (DQ-02)
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** SR-1 / INV-B06
- **QUESTION:** How does INV-B06 treat (a) cancellation refunds (F3) and (b) correction pairs posted outside the stay window (F4, ADR-004 posting-date semantics)?
- **WHY REQUIRED:** both are legitimate application outcomes that the current rule reports. The recommended "on or before the cancellation" bound has no consistent date basis (S1-4).
- **OPTIONS:**
  - (a-1) refunds with SR2-REV2 cancellation lineage are excluded from INV-B06 (lineage is INV-D02's subject; dating of the cancellation event is then unchecked);
  - (a-2) refunds bounded by the lead window of the payments they refund (same N as SR1-D1);
  - (a-3) "on or before the cancellation" with an explicit basis: date of `cancellation_processed_at` converted to local (IST) time, plus a tolerance; it breaks after K-7 with a stale business date (S1-4);
  - (b-1) corrections inherit the original's window via `corrects_id`;
  - (b-2) corrections are excluded (dated by posting rule ADR-004; INV-D02 governs their lineage);
  - (b-3) unchanged (keep reporting).
- **EVIDENCE:** `services.py:1223,1253,1802`; ADR-004 (adopted; "Corrections / refunds | dated on the business date of posting" — `verification/adr/ADR-004-business-date-authority.md:40`); SR2-REV2 items 2–3 (`FOUNDER_DECISIONS.md:1336-1337`).
- **DEPENDENCIES:** SR1-D4 (K-7 dating of refunds and corrections); INV-D02 (SR-2, done).
- **WHAT IS BLOCKED:** INV-B06 refund/correction clauses.
- **WHAT CAN CONTINUE:** all other work.
- **EXACT ACTION AFTER DECISION:** encode the clause; add a positive scenario (legitimate refund/correction holds) and a negative one (a refund dated far from any window fails).

### DQ-03 / SR1-D3 — negative seeds and commissioning

- **DECISION ID:** SR1-D3 (DQ-03)
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** SR-1 / INV-B06
- **QUESTION:** Which negative seeds must the amended INV-B06 fail on?
- **WHY REQUIRED:** FD-P2-06 makes the seeds directive content. The single existing seed (`MIN(id)` −400 days) does not prove detection for any exempted class (S1-6). The commissioning engine supports one `negative_seed` tuple per invariant, so additional proofs would be scenario tests rather than commissioning seeds, unless the founder requires a framework change.
- **OPTIONS:** keep the existing seed unchanged (it still fails on production's settlement row under options A–C), **plus** scenario negatives:
  - (i) a non-advance payment before arrival;
  - (ii) an advance outside the ruled window (options B/C only);
  - (iii) a payment after departure + tail;
  - (iv) a refund/correction outside its ruled bound;
  - optionally (v) a stale-date check-in deposit (S1-5).
- **EVIDENCE:** `rules_b.py` `negative_seed`; `20261001_120800_inv_commission/report.txt:137-145`.
- **DEPENDENCIES:** SR1-D1, SR1-D2.
- **WHAT IS BLOCKED:** commissioning of the amended rule.
- **WHAT CAN CONTINUE:** test design (§6).
- **EXACT ACTION AFTER DECISION:** encode the seeds; run `inv-commission`; the INV-B06 element must read PASS.

### DQ-04 / SR1-D4 — sequencing with K-7

- **DECISION ID:** SR1-D4 (DQ-04)
- **DATE DISCOVERED:** 2026-09-30 (`G3_DEPENDENCY_MAP.md` D-S1); reconfirmed 2026-10-02
- **WORKSTREAM:** SR-1 × K-7
- **QUESTION:** Is SR-1 ruled and implemented before K-7 (with refund/correction clauses that do not depend on dating basis, e.g. a-1/a-2 and b-1/b-2), or after K-7?
- **WHY REQUIRED:** refunds and corrections are dated by the calendar today (W-08/09/10/11) and by the business date after K-7. A date-comparing clause changes meaning across K-7.
- **OPTIONS:**
  - SR-1 first, with basis-independent clauses;
  - SR-1 after K-7;
  - SR-1 split: the advance clause now, the refund/correction clauses after K-7.
- **EVIDENCE:** `G3_DEPENDENCY_MAP.md` §2 row 1; `services.py:1217,1807,2116`.
- **DEPENDENCIES:** K-7 directive (K7-D items).
- **WHAT IS BLOCKED:** choice of SR1-D2 option a-3 and any refund date clause.
- **WHAT CAN CONTINUE:** SR1-D1 can be ruled independently.
- **EXACT ACTION AFTER DECISION:** sequence the SR-1 directive accordingly.

### DQ-05 / SR1-D5 — scope carve-out (Phase 6 "Not touched")

- **DECISION ID:** SR1-D5 (DQ-05)
- **DATE DISCOVERED:** 2026-09-30 (`G3_DECISION_PACKAGE.md` §C-2)
- **WORKSTREAM:** SR-1 governance
- **QUESTION:** Does the SR-1 directive itself act as the carve-out from Master Plan Phase 6 "Not touched: invariant semantics", as was done implicitly for SR-2?
- **WHY REQUIRED:** SR-2 proceeded without a recorded carve-out. Recording one keeps SR-1 consistent with SR-2.
- **OPTIONS:** state the carve-out in the SR-1 directive; or record a general amendment to Phase 6 for the FD-P2-06 family.
- **EVIDENCE:** `G3_DECISION_PACKAGE.md` §C-2; `FOUNDER_DECISIONS.md:1185-1186`.
- **DEPENDENCIES:** none.
- **WHAT IS BLOCKED:** nothing technically; governance completeness.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** cite it in the SR-1 evidence pack.

### SR1-D6 (optional) — credit-recovery tail

- Whether a legitimate `credit_recovery` payment more than 30 days after departure (F7) stays reported. Not named by FD-P2-06. The founder may leave it out of scope.

## 6. SR-1 test design, ready for when the text is ruled (preparation, no code committed)

Scenario tests are built on a dataset or production **copy**, never production. Each row is "expected under the ruled option".

| Scenario | Purpose / flags | Date | Expect |
|---|---|---|---|
| P-1 advance at booking, arrival +20 d | advance | arrival − 20 | HOLDS (all options) |
| P-2 advance at booking, arrival +400 d | advance | arrival − 400 | HOLDS under A; VIOLATED under B/C if N < 400 |
| P-3 voucher redeemed at booking | settlement + redemption row | arrival − 20 | HOLDS under C only |
| P-4 correction pair of P-1 before arrival | NULL, `is_correction`, `corrects_id`→P-1 | arrival − 10 | HOLDS under C / b-1 / b-2 |
| P-5 cancellation refund with SR2-REV2 lineage | refund, `is_reversal` | cancellation day | HOLDS under a-1 / a-2 (a-3 depends on basis) |
| P-6 settlement inside stay | settlement | arrival + 1 | HOLDS |
| P-7 credit recovery, departure + 10 | credit_recovery | departure + 10 | HOLDS |
| N-1 existing seed (`MIN(id)` −400 d) | any | — | VIOLATED (all options, when `MIN(id)` is non-exempt) |
| N-2 settlement before arrival | settlement | arrival − 5 | VIOLATED |
| N-3 advance after departure + 30 | advance | departure + 31 | VIOLATED |
| N-4 advance beyond the ruled window | advance | arrival − (N+1) | VIOLATED (B/C) |
| N-5 refund without lineage, before arrival | refund, `is_reversal`, no reservation pointer | arrival − 5 | VIOLATED |
| N-6 stale-date check-in deposit | NULL | arrival − 53 | VIOLATED (confirms S1-5) |

Regression battery and comparison method: as for SR-2 (`verification/evidence/20260930_sr2_inv_d02/run_regression.sh`, `run_pvf.py`), baseline worktree on unchanged `origin/main` and implementation worktree, run with a throwaway `SECRET_KEY`. Production is the read-only source only.

## 7. Status

| Item | Status |
|---|---|
| SR-1 exact rule text | **BLOCKED — FOUNDER DECISION REQUIRED** (SR1-D1…D5) |
| SR-1 implementation | **NOT AUTHORIZED** (no ruled text) |
| SR-1 verification | NOT VERIFIED (nothing to verify) |
| INV-B06 code | unchanged at `c9eeff0` |
| Production | not touched |
