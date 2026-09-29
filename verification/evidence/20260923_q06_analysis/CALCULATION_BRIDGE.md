# Q06 — Calculation bridge: SOURCE DATA → PATH INPUT → FORMULA → RESULT

Baseline commit: `b0d30542ff6b3cdbbc269fd8c17679c80ed9f718`. Companion to
`Q06_ANALYSIS.md` in this directory. All figures reproduced live via
`verification/_work/q06_repro.py` against a `verification/dbcopy.py :: make_copy()`
disposable copy of `instance/pms.db`; full row dump in
`verification/_work/q06_repro_result.json`.

Worked in full for **2026-08-09** (the smaller of the two dates — 4 `TaxLine` rows);
2026-08-10 follows the identical pattern at larger scale (summarised at the end).

## Step 0 — Source data: the underlying charges for 2026-08-09

Reservation id=1, business date 2026-08-09:

| Charge | Source | Pre-tax amount |
|---|---|---|
| Room night 2026-08-09 | `room_night` / `night_2026-08-09` | ₹761.90 |
| Extra charge id=1 (Late Check-out) | `extra_charge` / `1` | ₹380.95 |

Total actual taxable turnover for the day = 761.90 + 380.95 = **₹1,142.85**. This is
also independently confirmed by `NightAuditService.revenue_summary()['accrual_net']`
for this date (₹1,142.85 — see `verification/ledgers/production/dates/2026-08-09.json`
line 161, and matches `kpi.accrual_summary.accrual_net` line 15/16), and by
`kpi.total_revenue` (line 52) — three independently-computed application figures that
all agree on ₹1,142.85 as the day's real pre-tax revenue.

## Step 1 — What GST posting does to that data: `TaxLine` rows created

`gst_service.compute_tax()` (gst_service.py:243-293) computes, for each charge, a 5%
total GST split as CGST 2.5% + SGST 2.5% (intrastate; hotel state = billing state).
`_build_tax_lines()` (gst_service.py:300-339) then persists **two** `TaxLine` rows per
charge, both carrying the **full, unsplit** `taxable_amount`:

| id | reservation_id | source_type | source_id | tax_type | tax_rate | taxable_amount | tax_amount |
|---|---|---|---|---|---|---|---|
| 1 | 1 | room_night | night_2026-08-09 | CGST | 2.500 | 761.90 | 19.05 |
| 2 | 1 | room_night | night_2026-08-09 | SGST | 2.500 | 761.90 | 19.05 |
| 3 | 1 | extra_charge | 1 | CGST | 2.500 | 380.95 | 9.52 |
| 4 | 1 | extra_charge | 1 | SGST | 2.500 | 380.95 | 9.52 |

(Source: `verification/_work/q06_repro_result.json`, `tax_line_rows`, ids 1-4.)

Note the shape: **2 charges → 4 `TaxLine` rows**, and `taxable_amount` is repeated
identically on both rows of each pair (761.90 on rows 1&2, 380.95 on rows 3&4). This is
by design — see Q06_ANALYSIS.md §2.3 — each `TaxLine` row is a complete, self-describing
tax-component record.

## Step 2 — PATH A: `gst_service.get_gst_report(2026-08-09, 2026-08-09)`

**File/function**: `app/gst_service.py:674-771`

```
rows = TaxLine.query.filter(charge_date between from_date, to_date).all()   # 4 rows
rows = [exclude legacy room_rent-ExtraCharge duplicates]                     # none here, still 4 rows

seen_sources = {}
total_taxable = 0
for tl in rows:
    key = (tl.reservation_id, tl.charge_source_type, tl.charge_source_id)
    if key not in seen_sources:
        total_taxable += tl.taxable_amount     # counted ONCE per (res, source_type, source_id)
        seen_sources.add(key)
    # tax totals, independently, per row:
    if tl.tax_type == 'CGST': cgst_total += tl.tax_amount
    elif tl.tax_type == 'SGST': sgst_total += tl.tax_amount
```

Walking the 4 rows:
- row 1 (CGST, key=(1,'room_night','night_2026-08-09')) → new key → `total_taxable += 761.90` → 761.90; `cgst_total += 19.05` → 19.05
- row 2 (SGST, same key) → key already seen → `total_taxable` unchanged; `sgst_total += 19.05` → 19.05
- row 3 (CGST, key=(1,'extra_charge','1')) → new key → `total_taxable += 380.95` → **1142.85**; `cgst_total += 9.52` → 28.57
- row 4 (SGST, same key) → key already seen → `total_taxable` unchanged; `sgst_total += 9.52` → **28.57**

**Result**: `total_taxable = 1142.85`, `cgst_total = 28.57`, `sgst_total = 28.57`,
`total_tax = 56.14... ` — precisely `28.57 + 28.57 = 57.14` (rounding artifacts aside),
`grand_total = 1142.85 + 57.14 = 1199.99`.

Live output: `gst_report.total_taxable = 1142.85`, `gst_report.total_tax = 57.14`,
`gst_report.grand_total = 1199.99`. ✅ matches the pre-tax turnover established in Step 0.

## Step 3 — PATH B: `NightAuditService.tax_snapshot()`, business_date = 2026-08-09

**File/function**: `app/night_audit_service.py:1126-1147`, fed by `self._tax_lines`
set in `__init__` (night_audit_service.py:234-236):
`TaxLine.query.filter(TaxLine.charge_date == business_date).all()` → the same 4 rows,
**no legacy-duplicate filter applied** (moot here — none exist).

```
total_taxable = 0
for t in self._tax_lines:
    total_taxable += t.taxable_amount   # NO dedup — every row counted
    # by_rate bucket also accumulates taxable per (tax_type, rate) with no dedup
total_tax = sum(t.tax_amount for t in self._tax_lines)   # correct — see Step 4
```

Walking the same 4 rows, with no key/dedup logic at all:
- row 1: `total_taxable += 761.90` → 761.90
- row 2: `total_taxable += 761.90` → 1523.80  *(SGST row re-adds the SAME 761.90 already counted via the CGST row)*
- row 3: `total_taxable += 380.95` → 1904.75
- row 4: `total_taxable += 380.95` → **2285.70**  *(SGST row re-adds the SAME 380.95 already counted via the CGST row)*

**Result**: `total_taxable = 2285.70` — exactly double the real ₹1,142.85 turnover,
because every charge's base was added twice (once from its CGST row, once from its
SGST row).

Live output: `tax_snapshot.total_taxable = 2285.7`, `tax_snapshot.total_tax = 57.14`.

## Step 4 — Why `total_tax` is NOT doubled (the tell)

Both paths sum `tax_amount` per row directly, with no dedup:

- Path A: `cgst_total (28.57) + sgst_total (28.57) = 57.14`
- Path B: `sum of tax_amount over all 4 rows = 19.05+19.05+9.52+9.52 = 57.14`

These agree exactly because each row's `tax_amount` is already the correctly-split
*half*-rate amount for that component (CGST row → 2.5% of 761.90 = 19.05; SGST row →
2.5% of 761.90 = 19.05; together = 5% of 761.90 = 38.10... plus the extra charge's
9.52+9.52=19.04, total 57.14 for the day). Summing per-row `tax_amount` needs no
deduplication because — unlike `taxable_amount` — it is *not* repeated across the pair;
each row owns a distinct slice of the total tax. This is the structural reason the two
paths' `total_tax` values agree to the cent while their `total_taxable` values differ by
exactly 2x: the bug is specific to summing `taxable_amount` without dedup, not to the
tax computation itself.

## Step 5 — The exact divergence point

**Divergence point**: `NightAuditService.tax_snapshot()`, `app/night_audit_service.py`
line 1136:

```python
total_taxable = sum(_f(t.taxable_amount) for t in self._tax_lines)
```

sums `taxable_amount` over every `TaxLine` row in `self._tax_lines` with **no
deduplication key**, whereas the corresponding line in `gst_service.get_gst_report`,
`app/gst_service.py` lines 712-716:

```python
key = (tl.reservation_id, tl.charge_source_type, tl.charge_source_id)
if key not in seen_sources:
    total_taxable += Decimal(str(tl.taxable_amount))
    seen_sources.add(key)
```

deduplicates by the charge's identity before adding. Since every intrastate charge
produces exactly 2 `TaxLine` rows (CGST + SGST) both carrying the full
`taxable_amount` (gst_service.py `_build_tax_lines`, lines 300-339, `kwargs_base`
reused for both rows), the undeduplicated sum in `tax_snapshot()` is exactly 2x the
correct value on any date where all charges are intrastate (as both 2026-08-09 and
2026-08-10 are — zero IGST rows in this dataset). On a date with a mix of intrastate
(2 rows/charge) and interstate (1 IGST row/charge) charges, the inflation would not be
a clean 2x — it would be `taxable_amount` counted twice for every intrastate charge and
once (correctly) for every interstate charge, still wrong but with a data-dependent
ratio.

Note the `by_rate` dict inside `tax_snapshot()` (night_audit_service.py:1127-1134) is,
by itself, **not** wrong in the same way: because each bucket is keyed by
`(tax_type, rate)`, the `CGST @ 2%` bucket only ever accumulates rows where
`tax_type == 'CGST'` — one row per charge — so `by_rate['CGST @ 2%']['taxable']` equals
the true taxable base (1142.85) on its own, and so does
`by_rate['SGST @ 2%']['taxable']` independently (also 1142.85, since every charge also
has exactly one SGST row). Each bucket, read alone, is correct. The bug is that
`total_taxable` (night_audit_service.py:1136) is computed as an **independent** straight
sum over `self._tax_lines`, not as "pick one bucket" or "dedupe across buckets" — so it
effectively adds the CGST bucket's (correct) 1142.85 and the SGST bucket's (correct)
1142.85 together, yielding 2285.70. A reader who only looks at `by_rate` would see the
right number twice; a reader who looks at `total_taxable` sees it doubled.

## Step 6 — Full per-date results (both dates in the dataset)

| Date | Charges (deduped) | Real taxable base (Step 0 / accrual_net) | `get_gst_report.total_taxable` | `tax_snapshot.total_taxable` | ratio | `get_gst_report.total_tax` | `tax_snapshot.total_tax` |
|---|---|---|---|---|---|---|---|
| 2026-08-09 | 2 (1 room-night, 1 extra) | 1,142.85 | **1,142.85** ✅ | **2,285.70** ✗ (2x) | 2.0000 | 57.14 | 57.14 ✅ |
| 2026-08-10 | 4 (3 room-nights, 1 extra) | 2,952.38 | **2,952.38** ✅ | **5,904.76** ✗ (2x) | 2.0000 | 147.60 | 147.60 ✅ |

These are the exact figures FI-10 cites for both functions
(`gst_service.get_gst_report` → 1,142.85 / 2,952.38 across the two dates;
`NightAuditService.tax_snapshot` → 2,285.70 / 5,904.76 across the two dates).

## Step 7 — What a correct `tax_snapshot()` fix would look like (description only, not implemented)

Replace the unkeyed sum at night_audit_service.py:1136 with the same
`seen_sources`-style dedup `get_gst_report` already uses, e.g. (illustrative only —
**no code was changed by this analysis**):

```python
seen = set()
total_taxable = 0.0
for t in self._tax_lines:
    key = (t.reservation_id, t.charge_source_type, t.charge_source_id)
    if key not in seen:
        total_taxable += _f(t.taxable_amount)
        seen.add(key)
```

and apply the equivalent per-rate-key dedup inside the `by_rate` accumulation loop
(night_audit_service.py:1127-1134). See Q06_ANALYSIS.md §6 for the full fix-boundary
discussion and why this requires Founder authorization before implementation.
