# FinalGrid Phase 1 - Bounded Verification Completion

| | |
|---|---|
| Directive | FG-P1-VERIFICATION-COMPLETION-20260909-01 (read-only verification) |
| Executed | 2026-09-09 21:19-21:35 IST (evidence packs stamped 20260909_1558xx-1604xx UTC) |
| Baseline | `aa6d9e91e7294be731383f755d6998acf5f059fc` on `main`, pushed; `origin/main` identical; 0 tracked modifications before and after |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` |
| Production anchor | `instance/pms.db` 733,184 B - `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` - unchanged at every checkpoint (section 7) |
| Purpose | close CF-1..CF-9 from `20260909_phase1_completion_review/` without reopening implementation |
| Result | **PHASE 1 VERIFICATION COMPLETION PASS - NO NEW REGRESSION** |
| Decision | **B. VERIFICATION COMPLETE WITH DOCUMENTED LIMITATIONS** (section 10) |
| Formal acceptance | **not declared here** - Founder governance gate, separate |

Companion documents: `WRITER_COVERAGE.md`, `DATASET_RESULTS.md`, `Q14_PARITY.md`, `PHASE2A_MATRIX.md`, `GOLDEN_MASTER_REBASELINE.md`, `result.json`. Scripts and raw output are retained in this directory (`verify_writers.py`, `harness_runs.py`, `ds_eval.py`, `phase2a_verify.py`, `*.txt`, `*.json`).

## 1. Method and safety

- Every mutation happened on disposable copies made by `verification.dbcopy.make_copy` (SQLite backup API from a `mode=ro` connection): four writer copies (`p1vc_setA..D.db`), the harness's own copies for `inv-run`, parity, datasets and golden-master capture, and the Phase 2a copy. Production was opened read-only for hashing only.
- No application code, schema, fixture, ledger, historical Golden Master, governance record, ADR or git object was modified. Nothing was committed or pushed. This directory, the harness evidence packs it produced and the new master set are untracked.
- The eight D11 rows were never used as fixtures and are proven unchanged by id and amount on every copy (D11-01..04 on all four sets) and on production (section 7).
- Static proof (the completion review's `ast` sweep: 33/33 constructor sites carry `folio_id`) stands and was not discarded; runtime coverage was added on top of it.

## 2. Writer coverage (CF-1)

Detail in `WRITER_COVERAGE.md`.

| | Count | Writers |
|---|---|---|
| Runtime-verified before this directive | 6 | W-05, W-08, W-13, W-15, W-20, W-21 |
| Newly runtime-exercised now | 16 | W-01, W-02, W-03, W-04, W-06, W-09, W-10, W-12, W-14, W-16, W-17, W-18, W-19, W-22, W-23, W-24 |
| **Runtime-verified total** | **22 of 24** | |
| Static proof only | 2 | W-07 settle_credit, W-11 redeem_credit_voucher - **blocked by a pre-existing defect**: both pass `notes=` to `Payment(...)`, which has no such column; `TypeError` at runtime; present since baseline commit `b5b2514` (2026-08-07); untouched by Phase 1 |
| Audit-failure injection proven | 8 | W-01, W-02, W-04 (+W-17/W-18 in the same transaction), W-05, W-06, W-15, W-20 |

For each of the 22 runtime writers the directive's seven assertions were made: row created; `folio_id` non-null; equal to the reservation's folio A; that folio belongs to the same reservation with letter A; an audit record exists (classified by mechanism); the audit carries the row's folio/amount identity where the mechanism records it; atomicity proven by injection where the writer uses the strict helper; production untouched. Gate results: set A 81/81, set B 42/42, set C 15/15, set D 46/46. **No new unattributed row appeared on any copy** (NEW-01 x4).

Audit-coupling classes observed against Q-5 (recorded, not decided): A-STRICT at 12 writers; A-DED at 2 (W-13, W-14); caller-supplied never-raising `_write_audit` at 5 (W-08, W-09, W-10, W-22, W-23); entity-level only at 2 (W-11, W-12); run-level only at 2 (W-16, W-21); none at 1 (W-24). See section 8, item 2.

## 3. Invariant engine on new-activity copies (CF-2)

The existing engine (`verification.invariants.engine.run`) was pointed at each writer copy; each run proved read-only, repeatable and order-independent, and wrote its own pack.

| Copy | Content | HOLDS / VIOLATED / VACUOUS | Violations | Attribution of every violation | Pack |
|---|---|---|---|---|---|
| **Set D - clean new-activity** (business-date writers only; night audit closes last) | 11 payments, 10 charges: walk-in express, full check-in deposit, add-payment, POS, CICO, no-show fee, two checkouts (settlement + tip, + other income), night audit | **18 / 2 / 6** | INV-A02 8 of 21 (the D11 rows, 4,776.19); INV-A03 2 of 10 (the D11 charges, 476.19) | **Both are the expected baseline exception (FD-010 / AR-001).** INV-B01, B02, B03, B04, B05, B06 HOLD; INV-C02 HOLDS; INV-D07 moved VACUOUS -> HOLDS (an overpayment record now exists). INV-R01 HOLDS but stays NOT_COMMISSIONED (baseline). **This is E-9 / slice-4 satisfied: no new violation.** | `20260909_160110_inv_run_phase1_vc_setD` |
| Set A - broad runtime copy | 15 payments, 12 charges incl. calendar-dated advance bookings, a stay inserted into the closed 2026-08-09, a CheckedOut fixture left unsettled, a rate change after close (upsell CASE A) | 16 / 6 / 4 | A02 (D11), A03 (D11), **B03**, **B04**, **B06**, **C02** | B03: closed-day figures for 08-09 moved by the W-07 fixture stay inserted into the already-closed day, and 08-10 by the upsell rate bump after close - **fixture / sequencing artefacts**. B04: `extra_charge 4` dated 2026-09-09 = W-17's model-default `date.today()` - **K-7, pre-existing, Phase 3**. B06: payments 7 and 8 are advance payments dated on the business date for stays starting later - **the invariant's definition vs advance semantics; pre-existing, not Phase 1** (Phase 1 changed neither dates nor purposes). C02: reservation 10 = the W-07 fixture (ORM-created CheckedOut without `checked_out_at`) - **fixture artefact**. **None caused by attribution.** | `20260909_155816_inv_run_phase1_vc_setA` |
| Set B - wall-clock / correction writers | 11 payments, 5 charges: correction pair via the locked-date override route, refund, voucher (blocked), charge corrections | 12 / 8 / 6 | A02 (D11), A03 (D11), **B01, B03, B04, B06, D02, R01** | B01/B03/R01: the W-09 fixture payment deliberately moved onto the closed 2026-08-09 to reach the route's correction-pair path - **fixture artefact**. B04/B06: rows dated 2026-09-09 by `date.today()` in the correction, refund and voucher services - **K-7, pre-existing, Phase 3**. D02: refund `payment 11` is `is_reversal` without `corrects_id` - **pre-existing design of `post_cancellation_disposition`** (Phase 1 added only `folio_id`). **None caused by attribution.** | `20260909_160407_inv_run_phase1_vc_setB` (supersedes `155820`) |
| Set C - skipped-audit rerun | 6 payments, 6 charges: 4 recovered room-rent rows | **17 / 2 / 7** | A02 (D11), A03 (D11) | identical shape to the production baseline; **no new violation** | `20260909_155824_inv_run_phase1_vc_setC` |

PASS criterion ("no new Phase 1-caused invariant violation"): **met**. Every violation beyond the expected baseline is attributed above to a fixture placed in a closed period, to the documented K-7 wall-clock dating (Q-3, Phase 3), or to pre-existing service semantics; INV-A02/A03 never exceed the eight D11 rows on any copy.

## 4. Six datasets (CF-3)

Detail in `DATASET_RESULTS.md`. Five datasets are registered (`DS-ACT-INHOUSE`, `-CORRECTION`, `-VOIDCN`, `-GROUP`, `-SHIFT`); **all five PASS** (met 59/55/54/56/57, unmet 0), INV-A02 HOLDS on all five, INV-A03 HOLDS on four and VACUOUS by declaration on `-SHIFT`, Q14 AGREED on all five, no NULL-folio row, reconciliation views agree, 0 misrouted. The sixth named dataset, `DS-CORE-WALKIN`, **was never declared** (it is a docstring example in the deliberately empty `datasets_core.py`) - a pre-existing D6 gap, recorded as a limitation.

## 5. Q14 parity (CF-3)

Detail in `Q14_PARITY.md`. Exact results: production **DIVERGED** (0.00 vs 476.19); clean new-activity copy **DIVERGED** (1,050.00 vs 1,526.19); broad copy **DIVERGED** (2,582.00 vs 3,058.19); datasets **AGREED** 5/5. In every DIVERGED case the delta is exactly -476.19 = the two D11 charges and the unrouted counts are exactly the eight D11 rows: all new charges partition correctly; Q14 cannot AGREE on production-derived copies until the eight rows are ruled on (B-3). Other D1 quantities that diverge on populated copies (Q04, Q07, Q12, Q15, Q18, plus the pre-existing Q06/Q17/Q20) are recorded without reinterpretation as outside this directive.

## 6. Phase 2a matrix (CF-4)

Detail in `PHASE2A_MATRIX.md`. The 2026-08-31 script, copied verbatim, at `aa6d9e91`: **29 / 29 PASS**, production read-only verified, D11 freeze by identity (T29) intact. Established outcome unchanged.

## 7. Production safety (section 8 of the directive)

Read-only scratch-copy gate (`dbcheck.py`, copy inspected in `mode=ro`) before the first action and after the last:

| Anchor | Before | After |
|---|---|---|
| SHA-256 | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` | identical |
| Size | 733,184 B | identical |
| D11 payments 1-6 | 800 / 400 / 1500 / 1000 / 500 / 100 | identical |
| D11 extra_charges 1-2 | 380.95 / 95.24 | identical |
| D11 total | 4,776.19 | identical |
| audit_logs | 23 | 23 |
| Schema | 144 objects, fingerprint `e38454ba...` | identical |
| integrity_check | ok | ok |
| WAL / SHM / journal sidecars | none | none |

In addition every harness run re-hashed production itself (`read_only_verified: true` in all 11 packs), all four writer sets asserted PROD-01/02, and the Phase 2a script asserted its own before/after hash. No production anchor changed at any point; the STOP condition was never reached.

## 8. Golden Master re-baseline (CF-8)

Detail in `GOLDEN_MASTER_REBASELINE.md`. Performed only after sections 2-6 passed. `gm-capture --tag phase1_aa6d9e91` wrote a **new** master set (158 surfaces, frozen 2026-08-10T12:00, app v2.2.18); `gm-verify --tag phase1_aa6d9e91` = **158/158 clean, PASS**; `gm-verify --tag production` (historical, untouched) = 157/158 with the **same four E-6 differences** on `main.night_audit`, so E-6 remains correctly classified as expected. The tracked `masters/production/` set is unmodified (git status clean under `verification/masters/`).

## 9. Carry-forward matrix (CF-1 .. CF-9)

| Carry-forward | Verification performed | Result | Remaining gap |
|---|---|---|---|
| CF-1 runtime cases for the 18 static-only writers; injection beyond W-05/W-15/W-20 | 16 writers exercised through real routes / real service functions on isolated copies; injection at W-01, W-02, W-04(+17/18), W-06; W-20 closure kept as authoritative | **PASS** - 22/24 runtime-verified; 0 attribution failures; 0 new unattributed rows | W-07 and W-11 cannot be exercised on this codebase (pre-existing `notes=` TypeError - a defect, not a coverage choice). 10 writers keep non-strict audit coupling (Q-5 scope question, section 10) |
| CF-2 `inv-run` on a new-activity copy (A02/A03 HOLD for new rows; B01-B03 HOLD after a close) | Engine run on four copies; clean copy (set D) closed by the night audit | **PASS** - set D: 18 HOLDS, only A02/A03 VIOLATED and only by the eight D11 rows; B01-B06 and C02 HOLD | none for attribution. Observations: INV-B06 flags business-dated advance payments; INV-D02 flags refund rows (design); both pre-existing |
| CF-3 `ds-run` six datasets; Q14 parity | 5 registered datasets evaluated (`ds_eval.py` = `ds-run` path); Q14 via the parity runner on production, set D, set A | **PASS** - 5/5 datasets PASS, Q14 AGREED on datasets; DIVERGED by exactly the D11 amount on production-derived copies | `DS-CORE-WALKIN` never declared (D6 gap). Other D1 divergences on populated copies recorded, outside scope |
| CF-4 Phase 2a 29-case matrix at `aa6d9e91` | script re-run verbatim | **PASS** 29/29 | none |
| CF-5 T-N02 unauthorized-role-per-writer negative cases | **not performed** - not listed in this directive; no authorization changed by Phase 1; the folio endpoints are covered by CF-4 | n/a | remains open, low risk (Phase 4 / Register R6 territory) |
| CF-6 `attribution_control` outside the replay ledger | not in scope (Phase 6 ledger work) | n/a | remains (deliberate) |
| CF-7 governance index / Phase 1 acceptance entry | not in scope (governance records may not be edited) | n/a | remains - Founder acceptance entry (G-2) |
| CF-8 Golden Master carries four declared differences | verification-only capture under a new tag | **PASS** - `phase1_aa6d9e91` 158/158; historical set intact | commit / tag-adoption decision (Founder) |
| CF-9 Phase 1 committed and pushed, not deployed | not in scope (release decision) | n/a | remains - awareness |

## 10. Completion decision

**B. VERIFICATION COMPLETE WITH DOCUMENTED LIMITATIONS.**

Why not A: two writers (W-07, W-11) cannot be runtime-verified because a pre-existing defect makes their routes non-functional; one of the six named datasets does not exist; ten touched writers do not meet Q-5's strict coupling as worded; and CF-5 was not run. Why not C: nothing found blocks Phase 1 - every runtime writer that can execute attributes correctly, the clean new-activity copy holds every invariant except the D11 exception, datasets and Q14 behave exactly as the plan predicted, the Phase 2a matrix is unchanged, the production anchor never moved, and a clean post-Phase-1 Golden Master now exists.

Phase 1 is **not** declared formally accepted by this document. Formal acceptance remains the Founder's separate governance gate (completion review gate G-2).

## 11. Findings for the Founder (new, from runtime)

1. **Pre-existing defect: `settle_credit` (W-07) and `redeem_credit_voucher` (W-11) cannot post a payment.** Both pass `notes=` to `Payment(...)`; the model has no `notes` column; SQLAlchemy raises `TypeError`. Credit recovery flashes "Credit settlement failed"; voucher redemption answers HTTP 500. Present since `b5b2514` (2026-08-07), untouched by Phase 1, found only because these routes were exercised at runtime for the first time. Needs a bounded fix directive (not Phase 1); candidate K-21.
2. **Q-5 coverage is narrower than Q-5's wording.** Strict coupling was delivered at the routes-level writers and POS (12 of 24). W-08/09/10/22/23 rely on a caller-supplied `_write_audit` that never raises and whose failure the service swallows; W-11/W-12 audit only at entity level; W-16/W-21 at run level; W-24 not at all. The Phase 1 report described this split, but a Founder decision is needed: accept the delivered scope, or authorize a bounded coupling directive for the service-level writers.
3. **INV-B06 fires on any advance booking**: a payment dated on the business date for a stay that starts later is reported as "outside the stay". Either the invariant should exempt `payment_purpose='advance'` or advance dating should change - a Phase 3 / Phase 6 question, not Phase 1.
4. **INV-D02 fires on cancellation refunds**: `post_cancellation_disposition` posts `is_reversal=True` rows with no `corrects_id` by design. Same category as item 3.
5. **`DS-CORE-WALKIN` was never declared**; the D6 baseline module is empty. Phase 6 item.
6. **D1 parity divergences beyond Q14** (Q04, Q07, Q12, Q15, Q18 in addition to the pre-existing Q06/Q17/Q20) appear as soon as a copy has in-house activity. None involve `folio_id`. Phase 6 parity review.
7. **Checkout auto-posts a late-checkout charge from the calendar clock** (a full night after the slab cut-off, because the calendar is 30 days ahead of the business date). K-7 family; it was waived in the probes with the Admin waiver. Phase 3.

## 12. Limitations of this verification

- Copies only; nothing was deployed or operated against the live instance.
- W-07 and W-11: static proof only (section 11, item 1).
- Datasets bypass application writers by design; they prove engines, not routes.
- The set A and set B copies carry fixtures placed in closed periods and calendar-dated rows to reach specific code paths; their invariant results are attributed line by line (section 3) and should not be read as production predictions. Set D is the clean E-9 evidence.
- `ds-coverage`, `fault-run`, `replay-verify` were not re-run (not requested; replay was PASS at Phase 1 execution and the ledger was not touched by anything here).
- CF-5 not performed.
- Working copies remain under `verification/_work/` (ignored, disposable).

## 13. Evidence produced by this directive

This directory (untracked): `VERIFICATION_COMPLETION.md`, `WRITER_COVERAGE.md`, `DATASET_RESULTS.md`, `Q14_PARITY.md`, `PHASE2A_MATRIX.md`, `GOLDEN_MASTER_REBASELINE.md`, `result.json`; scripts `verify_writers.py`, `harness_runs.py`, `ds_eval.py`, `phase2a_verify.py`; raw output `writers_set{A,B,C,D}.{txt,json}`, `inv_run_set{A,B,C,D}.txt`, `inv_phase1_vc_set{A,B,C,D}.json`, `parity_{production,newactivity,setD}.txt`, `parity_phase1_vc_*.json`, `datasets.{txt,json}`, `phase2a_matrix.txt`, `phase2a_result.json`, `gm_capture_phase1_aa6d9e91.txt`, `gm_verify_phase1_aa6d9e91.txt`, `gm_verify_production.txt`.

Harness packs (untracked): `20260909_155816_inv_run_phase1_vc_setA`, `20260909_155820_inv_run_phase1_vc_setB` (superseded by `160407`), `20260909_155824_inv_run_phase1_vc_setC`, `20260909_160110_inv_run_phase1_vc_setD`, `20260909_160407_inv_run_phase1_vc_setB`, `20260909_155829_phase1_vc_newactivity`, `20260909_155832_phase1_vc_production`, `20260909_160115_phase1_vc_setD`, `20260909_160149_gm_capture_phase1_aa6d9e91`, `20260909_160158_gm_verify_phase1_aa6d9e91`, `20260909_160212_gm_verify_production`; master set `verification/masters/phase1_aa6d9e91/`.

Nothing committed, nothing pushed.
