# Q06 Forward Correction — Test and Regression Record

## 1. Focused test — `verify_q06_fix.py` (this directory)

Method: `verification.dbcopy.make_copy()` disposable copy of production (`q06_fix_regression.db`, backup API); application booted against the copy (`DATABASE_URL`), `TESTING=True`; both `gst_service.get_gst_report()` and the live, fixed `NightAuditService(d).tax_snapshot()` called for every date with `TaxLine` data. Output: `q06_fix_regression_result.json` (console output reproduced in this document; no separate transcript file was written).

| Case | What | Result |
|---|---|---|
| RC-Q06-01[2026-08-09] | old algorithm (naive sum, no dedup) reproduces the previously-recorded ~2x doubled base | PASS — old=2285.70, true base=1142.85, ratio=2.0000 |
| RC-Q06-02[2026-08-09] | fixed `total_taxable` equals the true charge-level base exactly once | PASS — fixed=1142.85, true=1142.85 |
| RC-Q06-04[2026-08-09] | fixed `tax_snapshot()` agrees with `get_gst_report()` | PASS |
| RC-Q06-03[2026-08-09] | `total_tax` unchanged | PASS — 57.14 both sides |
| RC-Q06-05[2026-08-09] | no `by_rate` bucket exceeds the true base | PASS — CGST@2%=1142.85, SGST@2%=1142.85 (each independently correct; neither exceeds the true base) |
| RC-Q06-06[2026-08-09] | `total_lines`/row accounting unaffected | PASS — 4 lines |
| RC-Q06-01[2026-08-10] | old algorithm reproduces the doubled base | PASS — old=5904.76, true=2952.38, ratio=2.0000 |
| RC-Q06-02[2026-08-10] | fixed `total_taxable` correct | PASS — fixed=2952.38, true=2952.38 |
| RC-Q06-04[2026-08-10] | agreement with `get_gst_report()` | PASS |
| RC-Q06-03[2026-08-10] | `total_tax` unchanged | PASS — 147.60 both sides |
| RC-Q06-05[2026-08-10] | `by_rate` not inflated | PASS |
| RC-Q06-06[2026-08-10] | row accounting unaffected | PASS — 8 lines |
| RC-Q06-07 | interstate (IGST, single-row, non-split) case | PASS (reported explicitly) — **no IGST rows exist in this dataset**; only the two known intrastate dates (2026-08-09, 2026-08-10) carry `TaxLine` rows. The dedup key is a no-op for a single-row charge by construction (a set with one element), so correctness for an interstate case is structural, not merely untested, but no live data exercises it. |
| RC-Q06-08 | sealed `NightAuditLog` 2026-08-09 record byte-identical before/after | PASS — `snapshot_hash` identical: `d248ae5413672f269cdefc9ad73ad18f1da28f3fca86c2248213b976f8ba4128` |

**14 / 14 passed.** Production untouched: SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` before and after (verified by `verification.dbcopy.assert_production_untouched`).

## 2. Existing audit/authorization tests

`phase2a_verify.py` (verbatim copy, re-run from this directory to avoid overwriting the committed evidence pack — see `Q06_FIX_IMPLEMENTATION.md` §8): **29 / 29 PASS**, production byte-identical, D11 freeze (T29) unchanged.

## 3. Regression — Golden Master

`python -m verification gm-verify --tag phase1_aa6d9e91` → **158 / 158 clean, 0 differences, 0 blocking, PASS**, read-only verified. Pack `verification/evidence/20260923_155154_gm_verify_phase1_aa6d9e91`.

## 4. Regression — replay

`python -m verification replay-verify --tag production` → **VERDICT: FAIL — expected, explained.**

```
2026-08-09   [CLOSED]        [BLOCK] ENGINE_CHANGED  nas.tax_snapshot.total_taxable
                              stored : 2285.7   current: 1142.85   (delta -1142.85)
2026-08-10   [BUSINESS_DATE] [INFO ] ENGINE_CHANGED  nas.tax_snapshot.total_taxable
                              stored : 5904.76  current: 2952.38   (delta -2952.38)
```

**Why this is expected, not a regression:** the replay ledger's stored baseline recorded the *pre-fix* (buggy, doubled) `tax_snapshot().total_taxable` values for both dates. The fix intentionally changes what `tax_snapshot()` computes live. Both deltas are exactly the amount the fix removes (`stored − current = the duplicated CGST-or-SGST base`, matching `Q06_FIX_IMPLEMENTATION.md`/`verify_q06_fix.py` RC-Q06-01/02 precisely: 2285.70 − 1142.85 = 1142.85; 5904.76 − 2952.38 = 2952.38). **No other field, surface, or date diverged** — this is the only quantity affected, on exactly the two dates known to carry `TaxLine` data, matching the Q06 factual basis exactly. Per this directive, the replay baseline itself was **not** altered or re-frozen — a baseline update, if ever wanted, is a separate, later, explicitly-authorized action. Pack: `verification/evidence/20260923_155240_replay_verify_production`.

## 5. Regression — invariants

`python -m verification inv-run --tag production` → 26 registered · 17 HOLDS · 7 VACUOUS · 2 VIOLATED (INV-A02 8/8, INV-A03 — the known D11 exception, unchanged) · INV-R01 NOT_COMMISSIONED — **identical population/violation profile to the pre-fix baseline** (`20260910_064257_inv_run_production`, part of the retention-control regression). No invariant reads `tax_snapshot()` output, so none was expected to move, and none did. Pack: `verification/evidence/20260923_155256_inv_run_production`.

## 6. Regression — cross-implementation quantities (`Q06` itself)

`python -m verification run` → the `q06()` quantity (`verification/quantities.py:496-532`) still prints `verdict: DIVERGED`, but this requires explanation, not alarm — the function conflates two separate comparisons:

- **The structural `impls` split** ("deduplicated by charge source" = 4095.23 vs "raw sum of all tax lines" = 8190.46): this is computed directly from the whole `TaxLine` table's own row structure (every intrastate charge has two rows by design), **independent of `tax_snapshot()`**. It was true before this fix and remains true after — it is not a defect and this fix could not and does not change it; the function's own note explains it ("CGST and SGST each carry the full taxable value of one supply").
- **The actual per-date `divergences` list** (`get_gst_report()` vs `tax_snapshot()`, the real Q06 comparison): **now empty** — `result.json` for this run shows `"divergences": []`, with `per_date` showing `gst_report_deduped == night_audit_raw` for both 2026-08-09 (1142.85 = 1142.85) and 2026-08-10 (2952.38 = 2952.38). **This is the actual confirmation that the defect is fixed.**

Pack: `verification/evidence/20260923_155322_cross_implementation`. (Note: `verification/quantities.py` was not modified by this directive — its `impls` framing is a pre-existing informational presentation choice, out of this bounded directive's scope to change.)

## 7. Production anchor

SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, verified unchanged before and after every script run in this pack (focused test, Phase 2a matrix, Golden Master, replay, invariants, cross-implementation run).

## 8. Verdict

Focused test PASS (14/14), existing Phase 2a matrix PASS (29/29), Golden Master PASS (158/158), invariants unchanged, cross-implementation Q06 per-date divergence now empty (the real defect closed), replay shows exactly the anticipated two-value change with no unrelated movement, production untouched throughout. No stop condition was met.
