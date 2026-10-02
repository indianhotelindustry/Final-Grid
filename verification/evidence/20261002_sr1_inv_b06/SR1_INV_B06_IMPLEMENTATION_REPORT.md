# SR-1 / INV-B06 — Implementation and verification report

| | |
|---|---|
| Authorization | Founder Round 10 (`verification/FOUNDER_DECISIONS.md`): `SR1-RULE` (directive, verbatim) and `SR1-INT` (two interpretation answers, verbatim). Commit `c6a36d8` |
| Branch | `sr1-inv-b06` (worktree `C:/wtsr1`), from `28e6b63`. That is the local `dq56-q06h1-guard` head, which holds Round 9; `app/` and `verification/` code are identical to `origin/main` `e310c66` |
| Tested commit | **`362535d`** — `verification/invariants/rules_b.py` only |
| Control | `28e6b63` (worktree `C:/wtsr1base`), unchanged rule |
| Outcome | **Targeted scenarios 28/28 PASS on `362535d`** (RED on control: 18/28, failing exactly where the ruling changes behaviour). **Regression: no status difference between control and branch in any suite.** Production untouched. **Not pushed, not merged.** STOPPED at the integration boundary |

## 1. What changed

One file: `verification/invariants/rules_b.py`, INV-B06 only. 138 insertions and 31 deletions; CRLF preserved; `diff --check` clean. Nothing in `app/`, the schema, K-7, business-date logic, the financial writers, datasets, faults, Golden Master baselines or other invariants changed.

The rule now reads:

| Payment | Verdict |
|---|---|
| `payment_purpose = 'advance'` | own date within **arrival − 30 days .. departure + 30 days** (DQ-01) |
| any other original payment (settlement, credit_recovery, NULL, …) | own date within **arrival .. departure + 30 days** (unchanged) |
| correction (`corrects_id` set) | **inherits the verdict** of the payment it corrects, followed to the root; its own date is not checked (DQ-02, SR1-INT Q1) |
| cancellation refund with SR2-REV2 lineage | **inherits the verdict** of every non-voided advance on its reservation, and fails if any of them fails; its own date is not checked (DQ-02, SR1-INT Q2) |
| correction or refund with no resolvable origin | its own date, under the general window (implementer reading R-1, §4) |

No cancellation timestamp, business date or wall clock is read (DQ-04: basis-independent, SR-1 before K-7). A stale business date gets no exemption (item 6). The 30-day tail and the population (`payment_date IS NOT NULL`, scope date in DATED mode) are unchanged.

Violations now record `basis` ("own date" or "inherited: …") and `originating_payments`, so an inherited failure names the payment that broke it.

**Negative seed: unchanged** (`MIN(id)` moved back 400 days). In application data `MIN(id)` is always an original payment: a correction or a cancellation refund requires an earlier payment. So the seed still lands on a row whose own date is checked. On production it is a settlement, and commissioning confirms HOLDS → VIOLATED. The per-class negative coverage DQ-03 requires is in the scenario tests (§2). The commissioning engine takes one seed per invariant.

**DQ-05:** recorded in Round 10. FD-P2-06 is the explicit Phase 6 carve-out for INV-B06.

## 2. Targeted scenarios (`verify_sr1.py`)

Each case ran on its own disposable copy of production (read-only source, SQLite backup API) and evaluated INV-B06 alone, one process per case. Settings:
- `verification` and `app` were taken from `--worktree`;
- the live `.env` was not loaded, messaging and AI variables were stripped, and a throwaway `SECRET_KEY` was used;
- scenario stay: arrival 2026-09-20, departure 2026-09-22.

Each check compares (status, exact set of flagged payment ids).

| Case | Situation | Expected | Control `28e6b63` | Branch `362535d` |
|---|---|---|---|---|
| P-00 | unseeded production copy | HOLDS | HOLDS | **HOLDS** |
| N-1 | registered negative seed | VIOLATED | VIOLATED | **VIOLATED** |
| P-1 | advance, arrival − 20 | HOLDS | VIOLATED | **HOLDS** |
| P-2 | advance, arrival − 400 | VIOLATED | VIOLATED | **VIOLATED** |
| P-3 | booking-time voucher application (`settlement`), arrival − 20 | VIOLATED | VIOLATED | **VIOLATED** |
| P-4 | correction pair of a valid advance, arrival − 10 | HOLDS | VIOLATED | **HOLDS** |
| P-5 | cancellation refund (lineage) of a valid advance | HOLDS | VIOLATED | **HOLDS** |
| P-6 | settlement inside the stay | HOLDS | HOLDS | **HOLDS** |
| P-7 | credit recovery, departure + 10 | HOLDS | HOLDS | **HOLDS** |
| N-2 | settlement, arrival − 5 (non-exempt pre-arrival) | VIOLATED | VIOLATED | **VIOLATED** |
| N-3 | advance, departure + 31 | VIOLATED | VIOLATED | **VIOLATED** |
| N-4 | advance, arrival − 31 (one day beyond the window) | VIOLATED | VIOLATED | **VIOLATED** |
| N-5 | refund without cancellation lineage, arrival − 5 | VIOLATED (refund only) | VIOLATED (+ valid advance) | **VIOLATED (refund only)** |
| N-6 | stale-business-date deposit (NULL purpose), arrival − 53 | VIOLATED | VIOLATED | **VIOLATED** |
| S-01 | advance exactly arrival − 30 (inclusive) | HOLDS | VIOLATED | **HOLDS** |
| S-02 | settlement, departure + 31 | VIOLATED | VIOLATED | **VIOLATED** |
| S-03 | settlement, departure + 30 (tail boundary) | HOLDS | HOLDS | **HOLDS** |
| S-04 | correction pair of an advance at arrival − 45 | VIOLATED (advance + both rows) | same | **same** |
| S-05 | cancellation refund whose only advance is at arrival − 45 | VIOLATED (advance + refund) | same | **same** |
| S-06 | refund drawn from a valid and an out-of-window advance | VIOLATED (bad advance + refund) | VIOLATED (+ valid advance) | **as expected** |
| S-07 | correction of a valid settlement posted departure + 45 | HOLDS | VIOLATED | **HOLDS** |
| S-08 | correction of a correction, root advance at arrival − 45 | VIOLATED (all 5 rows) | same | **same** |
| S-09 | correction of a valid advance dated arrival − 400 | HOLDS (own date unchecked) | VIOLATED | **HOLDS** |
| S-10 | correction naming a missing original, arrival − 5 | VIOLATED (R-1) | VIOLATED | **VIOLATED** |
| S-11 | cancellation refund whose only advance is voided, arrival − 5 | VIOLATED, refund only (R-1) | VIOLATED (+ voided advance) | **as expected** |
| S-12 | S-04 in BUSINESS_DATE mode for the correction's date | VIOLATED (both correction rows, inherited) | same | **same** |
| APP | **real writers** on a copy: `post_cancellation_disposition` refund of a 20-day advance; `post_payment_correction` of a 2026-08-10 settlement | HOLDS | VIOLATED (4 rows) | **HOLDS** |
| PROD | production `pms.db` SHA-256 before and after | equal | equal | **equal** |
| | | | **18/28** | **28/28** |

DQ-03 negative coverage:

| DQ-03 class | Cases |
|---|---|
| advances beyond 30 days | P-2, N-4 |
| non-exempt pre-arrival payments | N-2, P-3 |
| stale-business-date deposits | N-6 |
| invalid post-departure transactions | N-3, S-02 |
| lineage whose origin is outside the window | S-04, S-05, S-06, S-08, S-12 |

The APP case also shows the real writers date the refund and the correction rows by the calendar (2026-10-02) while the stays are in August. That is why the verdict reading, not the window reading, is basis-independent.

Logs and JSON: `red_control_28e6b63.log`, `sr1_red_control_28e6b63.json`, `green_362535d.log`, `sr1_green_362535d.json`.

## 3. Regression battery (control vs branch)

The battery is `run_regression.sh`: a verbatim copy of `20261002_dq56_r1_guard/run_regression.sh`, plus `inv-commission`. The driver `run_pvf_noenv.py` is verbatim; its `[dq56]` log tag is inherited. Both worktrees ran in parallel with the same throwaway `SECRET_KEY`, 11:54–12:07 IST. Production `21dc0e97…` was the read-only source; its hash was identical at start and end.

| Suite | Exit control / branch | Result control / branch | Difference |
|---|---|---|---|
| `inv-run --tag production` | 1 / 1 | identical status, POP and VIOL for every invariant; **INV-B06 HOLDS, 6 payments, 0 violations** on both | metering only: INV-B06 reads 1→3, rows 6→12, peak KB 2→6 (the lineage lookups); ms timing noise elsewhere |
| `ds-run` | 0 / 0 | identical | paths only |
| `ds-commission` | 0 / 0 | PASS / PASS | paths only |
| `fault-run` | 1 / 1 | FAIL / FAIL (pre-existing) | paths only |
| `gm-verify phase1_aa6d9e91` | 1 / 1 | FAIL / FAIL, the same 41 differences (31 BODY_CHANGED, 3+3+3 FIGURE, 1 NORMALISATION; environmental, plus R1's two already in the base) | paths only |
| `replay-verify --tag production` | 1 / 1 | FAIL / FAIL (pre-existing `ENGINE_CHANGED` on `total_taxable`, the governed Q06 deltas) | paths only |
| `run` (cross-implementation) | 1 / 1 | identical verdict per query (Q06, Q14, Q17 DIVERGED pre-existing) | `ms` column only |
| `inv-registry` | 0 / 0 | — | **exactly the INV-B06 rule and metadata text** |
| `inv-commission` | 1 / 1 | 27/28 / 27/28; **INV-B06 PASS on both** (baseline HOLDS over 6 rows → seeded VIOLATED; blast radius INV-B03 HOLDS/0 → VIOLATED/2, the same as 2026-10-01) | paths only. The one failure is **INV-R01** (seed does not fire), identical on both sides, pre-existing and outside SR-1 |

**No difference in any verdict, status, population or violation count between control and branch.** The only expected content difference is the INV-B06 registry text. Pre-existing failures are reported as found, identical on both sides, and **nothing was re-baselined**.

## 4. Implementer readings (not founder text — for confirmation)

- **R-1 — no origin:** a correction whose `corrects_id` does not resolve, or a cycle, has nothing to inherit from. So does a refund without SR2-REV2 cancellation lineage, or a lineage refund whose reservation has no non-voided advance. Each is judged on its own date under the general window. The founder-adopted scenario N-5 ("refund without lineage, before arrival → VIOLATED") requires this. S-10 and S-11 apply it.
- **R-2 — identifying a cancellation refund:** this uses the governed SR2-REV2 item 2 definition. Exactly one reservation names the refund, it is the refund's own, the disposition is `refund_full` / `refund_partial`, and `cancellation_processed_at` is present. Amount agreement is not used (item 5).
- **R-3 — a correction of a voided original** still inherits that original's verdict. Only the refund's advance set excludes voided rows, as the founder answered.
- **R-4 — seed unchanged** (reason in §1).

## 5. Consequences of the ruling (facts, for awareness — no action taken)

- **Booking-time voucher application** (`redeem_credit_voucher`, `payment_purpose='settlement'`, before arrival) stays a violation, because DQ-01 exempts advances only (P-3).
- **Stale production business date:** with the business date at 2026-08-10, any advance the app records today for an arrival after 2026-09-09 is dated 2026-08-10. That is more than 30 days early, so it is a **violation**, as item 6 intends. Check-in deposits for current arrivals violate too (N-6). Production currently HOLDS: 6 settlement payments, no advance.
- **Verdict inheritance** means a correction or refund with an absurd date of its own is not detected by INV-B06 when its origin is valid (S-09). Its lineage remains INV-D02's subject.

## 6. Safety

- Production `instance/pms.db` was `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434` before and after both scenario runs and the battery.
- No application was started in the live folder.
- The live `.env` was never loaded.
- No database copies are in this pack; `verification/_work/` is gitignored.
- 56 files were scanned: 0 phone-number-like and 0 e-mail-like matches.

## 7. Status

| Item | Status |
|---|---|
| Round 10 recorded verbatim | DONE (`c6a36d8`) |
| INV-B06 implementation | DONE on branch (`362535d`) |
| Targeted scenarios | **PASS** 28/28 (RED 18/28 on control) |
| Regression, control vs branch | **PASS — no status difference**; pre-existing failures unchanged, not re-baselined |
| INV-B06 commissioning | **PASS** |
| SR-1 row of G3 | **VERIFIED on branch, NOT INTEGRATED** |
| Push / merge / deployment | **NOT AUTHORIZED — awaiting separate founder authorization** |
| Production | untouched |
