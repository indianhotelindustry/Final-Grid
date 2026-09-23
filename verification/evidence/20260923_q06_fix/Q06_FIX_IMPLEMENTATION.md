# Q06 Forward Correction — Implementation Record

| | |
|---|---|
| Authority | Founder Resolution Round 4, **Q06-H2** (`FG-P2-FOUNDER-RESOLUTION-20260923-01`), `verification/FOUNDER_DECISIONS.md` |
| Baseline | `b0d30542ff6b3cdbbc269fd8c17679c80ed9f718` = `origin/main`; tree had only the pre-existing uncommitted Round 4 governance change and the three pre-existing Q06 evidence directories before this work started |
| Implemented | 2026-09-23 |
| Inputs | `verification/evidence/20260923_q06_analysis/` (root-cause), `verification/evidence/20260923_q06_downstream/` (downstream-impact, confirmed isolated) |

## 1. Exact behaviour changed

`NightAuditService.tax_snapshot()` (`app/night_audit_service.py`, method starting at line 1126) previously summed `TaxLine.taxable_amount` over **every** row with no deduplication (old line 1136: `total_taxable = sum(_f(t.taxable_amount) for t in self._tax_lines)`). Because an intrastate charge produces two `TaxLine` rows (CGST + SGST) that each carry the **full, unsplit** taxable base (`app/gst_service.py:334-339`), this double-counted the taxable base for every intrastate charge.

**After this change:** `total_taxable` (and each `by_rate` bucket's `taxable` component) is accumulated once per **charge**, using the same dedup key `gst_service.get_gst_report()` already uses: `(reservation_id, charge_source_type, charge_source_id)`. `total_tax`, `total_lines`, `exempt_lines`, `has_data`, and the `by_rate` grouping key (`f"{tax_type} @ {rate}%"`) are all unchanged.

## 2. Exact source change

File: `app/night_audit_service.py`
Function: `NightAuditService.tax_snapshot()` (only)
Diff stat: **21 insertions, 2 deletions**, one function, one file.

```diff
     def tax_snapshot(self) -> dict:
-        by_rate: dict = {}
-        for t in self._tax_lines:
-            key = f"{t.tax_type} @ {_f(t.tax_rate):.0f}%"
-            by_rate.setdefault(key, {'taxable': 0.0, 'tax': 0.0, 'count': 0,
-                                     'tax_type': t.tax_type, 'rate': _f(t.tax_rate)})
-            by_rate[key]['taxable'] += _f(t.taxable_amount)
-            by_rate[key]['tax'] += _f(t.tax_amount)
-            by_rate[key]['count'] += 1
-
-        total_taxable = sum(_f(t.taxable_amount) for t in self._tax_lines)
-        total_tax = sum(_f(t.tax_amount) for t in self._tax_lines)
-        exempt_count = sum(1 for t in self._tax_lines if t.is_exempted)
+        # Q06 (FG-P2-FOUNDER-RESOLUTION-20260923-01, Q06-H2): ...
+        by_rate: dict = {}
+        seen_taxable_overall: set = set()
+        seen_taxable_by_rate: dict = {}
+        total_taxable = 0.0
+        for t in self._tax_lines:
+            key = f"{t.tax_type} @ {_f(t.tax_rate):.0f}%"
+            by_rate.setdefault(key, {'taxable': 0.0, 'tax': 0.0, 'count': 0,
+                                     'tax_type': t.tax_type, 'rate': _f(t.tax_rate)})
+            src_key = (t.reservation_id, t.charge_source_type, t.charge_source_id)
+
+            bucket_seen = seen_taxable_by_rate.setdefault(key, set())
+            if src_key not in bucket_seen:
+                by_rate[key]['taxable'] += _f(t.taxable_amount)
+                bucket_seen.add(src_key)
+            by_rate[key]['tax'] += _f(t.tax_amount)
+            by_rate[key]['count'] += 1
+
+            if src_key not in seen_taxable_overall:
+                total_taxable += _f(t.taxable_amount)
+                seen_taxable_overall.add(src_key)
+
+        total_tax = sum(_f(t.tax_amount) for t in self._tax_lines)
+        exempt_count = sum(1 for t in self._tax_lines if t.is_exempted)
```

(full diff reproducible via `git diff app/night_audit_service.py` against baseline `b0d3054`)

## 3. Deduplication semantics used

Reused, not reinvented: the key `(reservation_id, charge_source_type, charge_source_id)` is exactly the key `get_gst_report()` uses at `app/gst_service.py:705,712-716` to dedupe its own `total_taxable`. No new business rule was introduced. The `get_gst_report()`-specific legacy `room_rent` `ExtraCharge` exclusion (`gst_service.py:689-702`) was deliberately **not** ported — it addresses a separate, unconfirmed concern outside the Q06 factual basis and is out of this bounded directive's scope; the production dataset examined has no such legacy rows (see `Q06_REGRESSION.md`), so this scope decision does not affect the measured result.

## 4. What was deliberately not done (Q06-H2 boundary)

- `app/gst_service.py` — **not touched** (already correct; Q06-H2 explicitly names no change).
- `app/gst_einvoice.py` — **not touched** (already sources exclusively from `get_gst_report()`; unaffected by this defect per the downstream-impact trace).
- The sealed `NightAuditLog` record for `audit_date = 2026-08-09` — **not touched** (see §7, historical record rule).
- No schema change, no migration, no business-date logic change, no payment/folio writer change, no unrelated refactor.

## 5. Files changed

| File | Change |
|---|---|
| `app/night_audit_service.py` | `NightAuditService.tax_snapshot()` — dedup fix (21 insertions, 2 deletions) |
| `verification/evidence/20260923_q06_fix/verify_q06_fix.py` | new — focused regression script |
| `verification/evidence/20260923_q06_fix/q06_fix_regression_result.json` | new — `verify_q06_fix.py`'s machine-readable output (14/14 PASS) |
| `verification/evidence/20260923_q06_fix/phase2a_verify.py` | new — verbatim copy of the existing Phase 2a matrix script, re-run from this directory so its output does not overwrite the committed `verification/evidence/20260910_retention_control/` pack (see §8) |
| `verification/evidence/20260923_q06_fix/{Q06_FIX_IMPLEMENTATION.md, Q06_REGRESSION.md, RESULT.json}` | new — this evidence pack's narrative and summary records |

No separate console-transcript file was written by either script; their console output is reproduced verbatim (numbers and verdicts) in `Q06_REGRESSION.md`. §8 below also explains why `phase2a_verify.py`'s own `result.json` output does not exist as a separate file in this directory.

## 6. Confirmations

| Confirmation | Result |
|---|---|
| `tax_snapshot().total_taxable` now agrees with `get_gst_report()` for the same date | **YES** — see `Q06_REGRESSION.md` RC-Q06-02/04 |
| `total_tax` unchanged | **YES** — RC-Q06-03, byte-for-byte on both known dates |
| `by_rate` no longer inflated beyond the true base | **YES** — RC-Q06-05 |
| unrelated tax lines / counts unaffected | **YES** — RC-Q06-06 |
| sealed historical `NightAuditLog` 2026-08-09 record untouched | **YES** — RC-Q06-08, `snapshot_hash` byte-identical before/after |
| no production mutation | **YES** — anchor `51dd83b7…30bc2` unchanged before/after every run in this pack |
| `get_gst_report()` / `gst_einvoice.py` unchanged | **YES** — `git diff --name-only` shows only `app/night_audit_service.py` under `app/` |

## 7. Historical record rule (Q06-H1 / Q06-H3) — honoured

The sealed `NightAuditLog` record for `audit_date = 2026-08-09` was **queried, never written**, in every script in this pack. Its `snapshot_hash` and `snapshot_json` are confirmed byte-identical before and after the regression run (`verify_q06_fix.py`, RC-Q06-08). No corrective/superseding record was created — none is authorized by Q06-H3 at this time. `routes.py:4786-4808` continues to serve that record frozen, exactly as before this change.

## 8. Incidental finding, corrected in-session

Running the pre-existing `verification/evidence/20260910_retention_control/phase2a_verify.py` script directly (its committed location) writes its output to `result.json` next to itself; on this Windows filesystem that silently overwrote the committed, differently-cased `RESULT.json` in the same directory (448 insertions/30 deletions observed via `git diff`). This was **immediately reverted** (`git checkout -- verification/evidence/20260910_retention_control/RESULT.json`) before any further work, and the script was instead **copied** into this evidence directory and re-run from there so its output lands only in new, untracked files.

The same case-insensitivity then recurred harmlessly inside this new directory: `phase2a_verify.py` (run at 21:24) wrote its own `result.json`, and this file, `RESULT.json` (written via this evidence pass at 21:26), was saved afterward and overwrote it on disk (case-insensitive collision, same as above). No committed file was affected this time — both files were new and untracked — but the standalone machine-readable `phase2a` output is consequently not present as a separate file; its numbers (29/29 PASS, production byte-identical, D11 freeze unchanged) are fully captured in prose in `Q06_REGRESSION.md` §2 from the console transcript instead. Recorded here for transparency.
