# Dataset Results - the registered D6 datasets at `aa6d9e91`

Directive FG-P1-VERIFICATION-COMPLETION-20260909-01. Method: the existing `ds-run` path (`builder.build` -> `evaluate.evaluate` -> `builder.discard`) driven by `ds_eval.py`, which additionally inspects each built copy read-only before discarding it. Output: `datasets.json`, `datasets.txt`. Production was read only (`sqlite-backup-api` copies); hash identical before and after.

## 0. Six named, five registered

The verification plan (section 4) names six datasets: `DS-CORE-WALKIN`, `DS-ACT-INHOUSE`, `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN`, `DS-ACT-GROUP`, `DS-ACT-SHIFT`. The registry (`registry.all_datasets()`) holds **five**. `DS-CORE-WALKIN` exists only as the worked example in the docstring of `verification/datasets/datasets_core.py`, a module that is *deliberately empty* ("D6 Step 1 is infrastructure only"). It was never declared, so it cannot be built or evaluated. This is a pre-existing gap in the D6 platform, recorded here as a documented limitation; no dataset was added by this directive.

How datasets work, stated plainly: a dataset is a **declared row set** (`rows=(('table', cols, values), ...)`) materialised into a copy of production and then measured by the invariant engine, the parity quantities, replay and golden-master probes against its own declared expectations. Datasets therefore do **not** drive application writers; the "writer exercised" column below names the *kind of financial row* the dataset declares, with `folio_id` carried in the declared rows. Application-writer runtime coverage is in `WRITER_COVERAGE.md`.

## 1. Results

| Dataset | Verdict | Expectations met / unmet / not run | INV-A02 | INV-A03 | Q14 | NULL-folio rows on the built copy | Reconciliation (reservation vs folio view) | Misrouted |
|---|---|---|---|---|---|---|---|---|
| DS-ACT-INHOUSE@1.0 | **PASS** | 59 / 0 / 0 | HOLDS (expected HOLDS) | not declared | AGREED | none | 0.00 = 0.00, agree | 0 |
| DS-ACT-CORRECTION@1.0 | **PASS** | 55 / 0 / 0 | HOLDS | HOLDS | AGREED | none | 1,200.00 = 1,200.00, agree | 0 |
| DS-ACT-VOIDCN@1.0 | **PASS** | 54 / 0 / 0 | HOLDS | HOLDS | AGREED | none | 200.00 = 200.00, agree | 0 |
| DS-ACT-GROUP@1.0 | **PASS** | 56 / 0 / 0 | HOLDS | HOLDS | AGREED | none | 500.00 = 500.00, agree | 0 |
| DS-ACT-SHIFT@1.0 | **PASS** | 57 / 0 / 0 | HOLDS | VACUOUS (expected VACUOUS - no charges) | AGREED | none | 0.00 = 0.00, agree | 0 |

All five PASS. E-9 ("INV-A02 and INV-A03 HOLDS on the six datasets; Q14 parity AGREED") holds for every registered dataset.

## 2. Per dataset

| Dataset | Setup (declared narrative, business date) | Writer kind exercised (declared rows) | Folio result | Audit result | Reconciliation | Invariant result | Pass/fail | Evidence |
|---|---|---|---|---|---|---|---|---|
| DS-ACT-INHOUSE | Priya Nair one night in 102 at 1,050 inclusive, settles cash, invoiced exact; Rohit Sharma two nights in 101, pays 1,000 to folio A, 1,100 outstanding; business date 2026-06-15; 19 rows | settlement payments, room rent as priced nights | every payment carries folio_id; NULL population empty | 0 `audit_logs` rows (datasets declare financial rows, not audit rows) | agree | INV-A02 HOLDS; parity Q02..Q22 as declared (Q14 AGREED); perturbation `folio_id = NULL` proves the control fires | PASS | datasets.json[0] |
| DS-ACT-CORRECTION | Anita Desai in 103 on 2026-07-10; 500 laundry charge; 1,000 paid; on the 11th the charge is reversed and replaced (200) and the payment reversed and re-posted (1,286); checks out settled; 15 rows | charge reversal/replacement (W-22/23 shape), payment reversal/replacement (W-08/09 shape) - all with `corrects_id` and folio_id | all rows attributed; NULL population empty | 0 audit rows (declared) | 1,200 = 1,200 | INV-D02 activated and HOLDS; INV-A02/A03 HOLDS; Q14 AGREED | PASS | datasets.json[1] |
| DS-ACT-VOIDCN | Vikram Rao in 104 on 2026-08-02; room 1,050 + minibar 236 (18%); settles 1,286; duplicate payment voided with a void request; minibar disputed -> credit note 236 and refund; 15 rows | void request, credit note, refund (W-10 shape) | attributed; NULL population empty | 0 audit rows (declared) | 200 = 200 | INV-D05 activated and HOLDS; INV-D02 VIOLATED **as declared** (the credit-note refund carries no corrects_id by design); A02/A03 HOLDS; Q14 AGREED | PASS | datasets.json[2] |
| DS-ACT-GROUP | Nair wedding party, two rooms under GRP-2026-0001 on 2026-09-20 at 1,050 each; 590 banqueting on the master room; each room settles its own folio (1,640 / 1,050); 20 rows | group-block room rent, master-account charge, per-room settlements | attributed per room folio; NULL population empty | 0 audit rows (declared) | 500 = 500 | A02/A03 HOLDS; Q14 AGREED; perturbation `folio_id = NULL` fires | PASS | datasets.json[3] |
| DS-ACT-SHIFT | Morning shift 2026-10-05 with 2,000 float; Sunil Menon in 107, 1,050 cash at 10:00 inside the shift; 200 petty cash; drawer counted 2,850 = 2,850; 10 rows | settlement payment inside a shift | attributed; NULL population empty | 0 audit rows (declared) | no charges (A03 VACUOUS as declared) | A02 HOLDS; Q21 cash position activated; Q14 AGREED | PASS | datasets.json[4] |

## 3. What this proves and what it does not

- Proves: on populations where every row is attributed, INV-A02/A03 HOLD and Q14 AGREES under the engines shipped at `aa6d9e91`; the D11 exception is the only reason production and production-derived copies differ (see `Q14_PARITY.md`).
- Does not prove: application-writer behaviour (datasets bypass writers by design). That is covered by the runtime sets in `WRITER_COVERAGE.md`.
- Limitation: the dataset declarations were authored before Phase 1 and already expected HOLDS, so they were not changed and did not need changing. No declaration was edited.
- Limitation: `ds-coverage` (what each dataset adds/loses against production) was not run; it measures platform coverage, not Phase 1 behaviour, and is outside the directive's list.
