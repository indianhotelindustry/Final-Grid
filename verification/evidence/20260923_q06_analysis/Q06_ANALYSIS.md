# Q06 — GST/tax divergence between `gst_service.get_gst_report` and `NightAuditService.tax_snapshot`

Baseline commit: `b0d30542ff6b3cdbbc269fd8c17679c80ed9f718` (working tree clean).
Type: read-only forensic analysis. No application/source file, no `instance/pms.db`,
no existing evidence directory, no ADR/FOUNDER_DECISIONS.md/MASTER_PLAN.md was modified.

## 1. Why this exists

`verification/evidence/20260910_phase2_entry/PRODUCTION_READINESS_INVENTORY.md`,
finding **FI-10**, records an unresolved ~2x divergence on production data between:

- `gst_service.get_gst_report(from_date, to_date)` — `app/gst_service.py:674-771`
- `NightAuditService.tax_snapshot()` — `app/night_audit_service.py:1126-1147`

classified **B** ("must verify") → possibly **A**, in the item `Q06 GST divergence on
production` (PRODUCTION_READINESS_INVENTORY.md line 115). FI-10 explicitly declines to
guess which side is right: "one of them is wrong or is measuring a different thing; a
GST return built from the wrong one is a statutory error."

The repo's own verification replay engine, `verification/replay/ledger.py:222-262`
(`_tax()`), already independently recognised the shape of the problem — it deliberately
records **two** taxable-base figures per business date, `tax.taxable_base_raw` and
`tax.taxable_base_deduplicated`, with the comment:

> "A GST regime raises several component lines (CGST and SGST) against one taxable
> amount, so the raw sum of `taxable_amount` double counts; both are recorded because
> the application has historically used each of them in different places (Phase 2, Q06)."

That comment is descriptive, not a ruling — it records that the inconsistency exists,
not which side (if either) is correct. This analysis makes that ruling, using the two
functions themselves, not the replay engine, as ground truth.

Existing evidence consulted (cited, not duplicated):
- `verification/evidence/20260910_phase2_entry/PRODUCTION_READINESS_INVENTORY.md` (FI-10, table row 115)
- `verification/replay/ledger.py` lines 222-262 (`_tax()` — raw vs deduplicated taxable base)
- `verification/ledgers/production/dates/2026-08-09.json` and `2026-08-10.json` — production
  replay snapshots that already contain the exact FI-10 figures (see §3)
- `verification/WAVE1_BLUEPRINT.md` (unrelated use of `1142.85` as an `accrual_net`
  worked example — same production date, different context; not a second GST figure)

No prior evidence directory performs a live, source-level reproduction of both
functions side by side; that is what this directory adds.

## 2. What each path actually queries and computes

### 2.1 `gst_service.get_gst_report(from_date, to_date)` — `app/gst_service.py:674-771`

- **Source table**: `TaxLine` only (`app/models.py`, referenced via `TaxLine.query` at
  gst_service.py:680-687), filtered `TaxLine.charge_date >= from_date` and
  `<= to_date` (inclusive date-range scope, caller-supplied).
- **Legacy-duplicate filter** (gst_service.py:689-702): excludes any `TaxLine` whose
  `charge_source_type == 'extra_charge'` and whose `charge_source_id` names an
  `ExtraCharge` with `charge_type == 'room_rent'` — these are pre-fix duplicate rows
  from before room-night GST was made single-sourced (see `ensure_all_tax_lines`
  docstring, gst_service.py:574-590, and `_ids_of_room_rent_extras`, gst_service.py:607-620).
- **Deduplication key for the taxable base** (gst_service.py:705, 712-716):
  `seen_sources = set()`, keyed on `(tl.reservation_id, tl.charge_source_type,
  tl.charge_source_id)`. `total_taxable` is incremented by `taxable_amount` only the
  **first** time each key is seen — i.e. once per underlying charge, regardless of how
  many `TaxLine` rows (CGST+SGST, or a lone IGST/EXEMPT) that charge produced.
- **Tax totals** (gst_service.py:717-724): `cgst_total`, `sgst_total`, `igst_total` are
  each summed directly from `TaxLine.tax_amount` filtered by `tl.tax_type`, with no
  deduplication — correct, because each row already carries only its own
  already-split tax amount (see §2.3).
- **CGST/SGST/IGST/EXEMPT handling**: rate-wise breakdown (gst_service.py:726-758)
  groups CGST/SGST pairs by rate (doubling the per-line CGST rate to get the display
  rate, since a CGST row stores the *half* rate) and IGST separately; EXEMPT lines
  (`tax_type='EXEMPT'`, `tax_amount=0`) contribute to neither `cgst/sgst/igst_total` but
  are included once in `total_taxable` via the same dedup path.
- **Scope**: reservation-agnostic aggregate over the whole date range; not folio- or
  reservation-scoped (contrast with `get_folio_gst_summary`, gst_service.py:623-667,
  which is the single-reservation analogue and uses the identical dedup pattern).
- **Callers** (repo-wide grep): the GST report route (`app/routes` — GST report view)
  and, per gst_service.py's own comment block, is "the main entry point" alongside
  `get_folio_gst_summary` for invoice/report generation. No other module calls
  `get_gst_report`.

### 2.2 `NightAuditService.tax_snapshot()` — `app/night_audit_service.py:1126-1147`

- **Source table**: `TaxLine`, but scoped at `__init__` time (night_audit_service.py:234-236)
  to a **single business date**: `TaxLine.query.filter(TaxLine.charge_date ==
  business_date).all()`, stored as `self._tax_lines` and reused by all 11 report
  sections (this is one date, not the "from/to" range `get_gst_report` takes).
- **No legacy-duplicate filter**: unlike `get_gst_report`, `tax_snapshot()` does not
  exclude `TaxLine` rows sourced from legacy `room_rent` `ExtraCharge` duplicates. (In
  the production dataset examined here this filter is moot — no such duplicate rows
  exist yet — but it is a latent second divergence source for any dataset that does
  carry pre-fix rows; see §5.)
- **No deduplication by charge source**: `total_taxable` (night_audit_service.py:1136)
  is `sum(_f(t.taxable_amount) for t in self._tax_lines)` — a **straight sum over every
  `TaxLine` row**, with no grouping on `(reservation_id, charge_source_type,
  charge_source_id)`. Likewise the `by_rate` dict (night_audit_service.py:1127-1134)
  accumulates `taxable` per `(tax_type, rate)` bucket directly from each row's
  `taxable_amount`, again without dedup.
- **Tax totals**: `total_tax` (night_audit_service.py:1137) is
  `sum(_f(t.tax_amount) for t in self._tax_lines)` — the same computation `get_gst_report`
  performs (summed per-row `tax_amount`, no dedup needed because each row already
  carries only its own half-rate amount). This figure is **not** affected by the bug.
- **CGST/SGST/IGST/EXEMPT handling**: `by_rate` keys are `f"{tax_type} @ {rate:.0f}%"`
  (e.g. `"CGST @ 2%"`, rate stored is the half-rate, e.g. `2.5` for a 5% total slab,
  displayed rounded); `exempt_lines` counts rows with `is_exempted=True` separately.
- **Scope**: single business date, used inside the wider `full_report()` / Night Audit
  document for one property-day.
- **Callers**: `full_report()` assembles it as section 9 of the Night Audit (docstring,
  night_audit_service.py:15); rendered in Night Audit templates/report and captured in
  the audit snapshot (`recorded.snapshot.tax.*` in the production ledgers, §3). No
  other module calls `tax_snapshot()` directly (repo-wide grep confirms only
  `full_report()` and the verification ledger's independent replay touch this data).

### 2.3 The mechanism (why every intrastate charge is stored as TWO full-value rows)

`gst_service.compute_tax()` (gst_service.py:243-293) computes `cgst_amount` and
`sgst_amount` as *half*-rate amounts on the *same* full `taxable_amount` — that part is
correct double-entry-style GST math (6%+6%=12%, each on the same base).

The bug is in how that gets persisted. `_build_tax_lines()` (gst_service.py:300-339)
turns one charge into **two** `TaxLine` ORM rows for an intrastate charge:

```python
return [
    TaxLine(tax_type='CGST', tax_rate=bd.cgst_rate,
            tax_amount=bd.cgst_amount, **kwargs_base),
    TaxLine(tax_type='SGST', tax_rate=bd.sgst_rate,
            tax_amount=bd.sgst_amount, **kwargs_base),
]
```

`kwargs_base` (gst_service.py:315-324) includes `taxable_amount=bd.taxable_amount` —
the **full** pre-tax charge amount, unsplit — and that same `kwargs_base` is reused for
*both* the CGST row and the SGST row. So a single ₹761.90 room-night charge becomes two
`TaxLine` rows, each stamped `taxable_amount=761.90` (reproduced concretely in §4, rows
id=1/id=2). This is intentional and correct **as a tax-line ledger**: each row is a
complete, self-describing tax-component record (you can look at any one `TaxLine` row
alone and know both the charge's base and that component's tax), and it is exactly why
`tax_amount` sums are safe to add directly without dedup.

It stops being safe the moment `taxable_amount` is summed across rows without first
collapsing rows that share a charge. `get_gst_report` collapses them (via
`seen_sources`); `tax_snapshot` does not.

## 3. Confirmation against evidence already in the repo

The two production dates for which `verification/replay/ledger.py` independently
recomputed both a "raw" and a "deduplicated" taxable base already contain the FI-10
numbers verbatim:

| Date | `tax.taxable_base_deduplicated` (matches `get_gst_report`) | `nas.tax_snapshot.total_taxable` (matches `tax_snapshot`) | ratio |
|---|---|---|---|
| 2026-08-09 | 1142.85 | 2285.70 | 2.0000 |
| 2026-08-10 | 2952.38 (via `accrual_net`; the ledger's own `tax.taxable_base_deduplicated` field is 571.43 for this date because its dedup key omits `reservation_id` — a *different*, unrelated bug in the replay tool itself, not in the application; see note below) | 5904.76 | 2.0000 |

(Source: `verification/ledgers/production/dates/2026-08-09.json` lines 205, 210, 217,
252-253; `2026-08-10.json` lines 241, 246, 253.)

These are exactly the figures FI-10 cites for both paths (`gst_service.get_gst_report`
→ 1,142.85 / 2,952.38; `NightAuditService.tax_snapshot` → 2,285.70 / 5,904.76), confirming
FI-10's numbers describe `total_taxable`, one value per production business date
(2026-08-09 and 2026-08-10), not two figures from a single date/report.

**Note on the replay tool's own `tax.taxable_base_deduplicated` field**: for
2026-08-10 the ledger tool reports 571.43, not 2952.38, because its dedup key
(`verification/replay/ledger.py:252`, `key = (charge_source_type, charge_source_id)`)
omits `reservation_id` and therefore collapses different reservations' same-named
room-night sources (`"night_2026-08-10"`) into one bucket. This is a bug in the
verification replay tool's own dedup logic, separate from Q06, and is not relied on
below — §4 reproduces both application functions directly from their own source, not
through the replay tool.

## 4. Live reproduction (this analysis)

Script: `verification/_work/q06_repro.py` (throwaway, gitignored via
`verification/_work/` — see §7). Run:

```
venv\Scripts\python.exe verification\_work\q06_repro.py
```

Method: `verification/dbcopy.py :: make_copy()` — SQLite backup-API copy of
`instance/pms.db` into `verification/_work/q06_repro.db`; production hash verified
identical before and after (`assert_production_untouched`); Flask app booted against
the copy only (`DATABASE_URL` points at the copy, `TESTING=True`), per the pattern in
`verification/evidence/20260910_retention_control/verify_retention.py`.

Full output captured in `verification/_work/q06_repro_result.json` (12 `TaxLine` rows,
IDs 1–12, spanning 2026-08-09 and 2026-08-10 — the only dates with `TaxLine` data in
this copy).

```
DATE 2026-08-09
  gst_report.total_taxable   = 1142.85
  tax_snapshot.total_taxable = 2285.7   (ratio = 2.0000)
  gst_report.total_tax       = 57.14
  tax_snapshot.total_tax     = 57.14   (ratio = 1.0000)

DATE 2026-08-10
  gst_report.total_taxable   = 2952.38
  tax_snapshot.total_taxable = 5904.76   (ratio = 2.0000)
  gst_report.total_tax       = 147.60
  tax_snapshot.total_tax     = 147.6   (ratio = 1.0000)

MECHANISM CHECK for date 2026-08-09 (4 TaxLine rows):
  naive sum of TaxLine.taxable_amount over ALL rows      = 2285.70  <- tax_snapshot.total_taxable
  sum of TaxLine.taxable_amount DEDUPED by (reservation_id, source_type, source_id) = 1142.85  <- get_gst_report.total_taxable

production sha256 before: 51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2
production sha256 after:  51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2  (unchanged: True)
```

This exactly reproduces FI-10's numbers from source, on a disposable copy, with the
raw `TaxLine` rows visible (see the calculation bridge for the row-level detail).

## 5. Classification: **Q06-B** — one implementation is demonstrably incorrect

**`NightAuditService.tax_snapshot()`'s `total_taxable` field (and the `taxable`
sub-total inside each `by_rate` bucket) is the incorrect one.** It sums
`TaxLine.taxable_amount` over every row with no deduplication by underlying charge.
Because `_build_tax_lines()` stores the full, unsplit taxable amount on *both* the
CGST row and the SGST row of every intrastate charge, this straight sum counts the
taxable base of every non-IGST, non-exempt charge **twice**. On the production dataset
examined — which has zero IGST/interstate charges — this produces an exact, universal
2.0000x inflation of `total_taxable`, matching FI-10's numbers to the cent.

**`gst_service.get_gst_report()`'s `total_taxable` is correct.** It deduplicates by
`(reservation_id, charge_source_type, charge_source_id)` before summing
`taxable_amount`, so each underlying charge (a room-night, an extra charge) contributes
its base exactly once, regardless of whether it produced one `TaxLine` row (IGST or
EXEMPT) or two (CGST+SGST).

This is **not** an intentional semantic difference (ruling out Q06-A): there is no
docstring, comment, or naming in `tax_snapshot()` suggesting `total_taxable` is meant to
represent "taxable base summed once per tax-type bucket" as a deliberate design choice;
the Night Audit docstring (night_audit_service.py:15) describes the section plainly as
"TaxLine aggregation by rate", and `total_taxable` is presented alongside `total_tax`
and `total_lines` as the day's aggregate tax picture — a reader has no way to know it is
silently double-counting.

It is **not** "both correct, different metrics" (ruling out Q06-C): `total_tax` in both
paths agrees exactly (57.14 vs 57.14; 147.60 vs 147.60) — proving the two functions are
in fact trying to measure the *same* underlying day's tax activity, not different
business concepts. If they were deliberately different metrics, there would be no
reason for `total_tax` to land on the same number while `total_taxable` diverges by
exactly 2x; the identical `total_tax` is the tell that this is a partial bug in one
aggregate field, not a difference of definition.

It is **not** evidence-insufficient (ruling out Q06-D): the divergence is mechanically
reproduced from source, on live data, down to the individual `TaxLine` row, with an
exact and universally consistent 2.0000x ratio that has a clean, single-line
arithmetic explanation (missing dedup key). No further data or business input is needed
to identify the defect; what would need Founder input is only the *remediation*
decision (see §6).

**Important scope note**: only `tax_snapshot()`'s `total_taxable` (and the `taxable`
component of each `by_rate` entry) is wrong. `tax_snapshot()`'s `total_tax`,
`total_lines`, `exempt_lines`, and every other Night Audit section are unaffected — they
do not sum `taxable_amount` across rows. The Night Audit's overall reconciliation
(`final_control()`) uses `revenue_summary()['tax_amount']`, which is `sum(_f(t.tax_amount)
for t in self._tax_lines)` (night_audit_service.py:567) — the same correct computation,
not `tax_snapshot()`'s `total_taxable`. So the night audit's cash/accrual reconciliation
is **not** contaminated by this bug; only the `total_taxable` figure surfaced inside the
Tax Snapshot section (and anything downstream that reads it, e.g. the verification
ledger's `nas.tax_snapshot.total_taxable` capture) is wrong.

## 6. Proposed fix boundary (NOT implemented — describes scope only)

- **File**: `app/night_audit_service.py`
- **Function**: `NightAuditService.tax_snapshot()` (currently lines 1126-1147)
- **Change shape** (description only, no code written): deduplicate `taxable_amount`
  accumulation by `(reservation_id, charge_source_type, charge_source_id)` before
  adding to `total_taxable`, mirroring the `seen_sources` pattern already used in
  `gst_service.get_gst_report()` (gst_service.py:705, 712-716) and
  `gst_service.get_folio_gst_summary()` (gst_service.py:645-651). The `by_rate` dict's
  `taxable` sub-total would need the same treatment per rate-key, or a documented
  decision that `by_rate['<rate>'].taxable` is deliberately a per-tax-type-bucket
  figure (in which case `total_taxable` should be derived differently, e.g. from the
  CGST/IGST/EXEMPT buckets only, not SGST, to avoid double-adding the CGST+SGST pair).
  A secondary question the same fix should resolve: whether `tax_snapshot()` should
  also apply the legacy `room_rent`-duplicate filter `get_gst_report()` applies
  (gst_service.py:689-702) — moot on the dataset examined here (zero such rows) but a
  second latent divergence source on any dataset carrying pre-fix duplicate rows.
- **Not touched by this proposal**: `gst_service.get_gst_report()` (already correct),
  `tax_snapshot()`'s `total_tax` (already correct), any other Night Audit section.

**This was not implemented.** Per task constraints, no application file was modified.
**Founder authorization is required** before any implementation, because:
1. `tax_snapshot()`'s `total_taxable` is a production-visible figure inside the Night
   Audit document (and is captured into audit snapshots/ledgers), so a fix changes what
   already-run, possibly Founder-reviewed, night audits would show if regenerated.
2. The fix touches financial-reporting arithmetic in a service explicitly called out in
   this file's own module docstring as authoritative for end-of-day close
   (`RECONCILIATION_TOLERANCE`, `evaluate_reconciliation`, `final_control` — see
   night_audit_service.py:38-125), even though `total_taxable` itself is not part of
   the reconciliation formula (§5) — a Founder should confirm nothing downstream
   (reports, exports, GSTR filing workflow) reads `tax_snapshot()['total_taxable']`
   expecting the current (buggy) value.

## 7. Scratch script disposition

`verification/_work/q06_repro.py` and its output `verification/_work/q06_repro_result.json`
were left in place under `verification/_work/`, which is gitignored
(`.gitignore`: `verification/_work/`) and documented in the repo as a disposable working
area (confirmed by its existing contents — dozens of throwaway `*.db` copies from prior
verification runs). They are not tracked by git and do not need to be deleted, but can
be removed at any time without consequence. No other file was created or modified by
this analysis besides the three files in this evidence directory.

## 8. Read-only guarantee

`verification/dbcopy.py :: make_copy()` opens `instance/pms.db` with SQLite URI
`mode=ro` for the copy operation and hashes it before and after; `assert_production_untouched()`
re-hashes at the end of the repro run. Both hashes in §4 are identical
(`51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`), confirming
`instance/pms.db` was not written during this analysis. All queries and the one Flask
app boot in `q06_repro.py` ran exclusively against the disposable copy
`verification/_work/q06_repro.db`.
