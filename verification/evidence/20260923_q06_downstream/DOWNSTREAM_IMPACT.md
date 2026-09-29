# Q06 downstream-impact trace — `NightAuditService.tax_snapshot()`

Baseline commit: `b0d30542ff6b3cdbbc269fd8c17679c80ed9f718` (working tree clean
except the pre-existing untracked `verification/evidence/20260923_q06_analysis/`,
not touched by this task).

This is a read-only trace of every consumer of the confirmed Q06 defect
(`app/night_audit_service.py:1136`, `total_taxable = sum(_f(t.taxable_amount)
for t in self._tax_lines)` — double-counts taxable base because
`app/gst_service.py::_build_tax_lines` (lines 300-339) stores the full,
unsplit taxable amount on both the CGST and SGST `TaxLine` row for every
intrastate charge). No fix was applied. No application/model file, database,
or existing evidence directory was modified.

## 1. The method and its exact return keys

`app/night_audit_service.py`, `tax_snapshot()`, lines 1126-1147:

```python
def tax_snapshot(self) -> dict:
    by_rate: dict = {}
    for t in self._tax_lines:
        key = f"{t.tax_type} @ {_f(t.tax_rate):.0f}%"
        by_rate.setdefault(key, {'taxable': 0.0, 'tax': 0.0, 'count': 0,
                                 'tax_type': t.tax_type, 'rate': _f(t.tax_rate)})
        by_rate[key]['taxable'] += _f(t.taxable_amount)   # <- inflated
        by_rate[key]['tax'] += _f(t.tax_amount)            # correct
        by_rate[key]['count'] += 1

    total_taxable = sum(_f(t.taxable_amount) for t in self._tax_lines)  # <- inflated (line 1136)
    total_tax = sum(_f(t.tax_amount) for t in self._tax_lines)           # correct
    exempt_count = sum(1 for t in self._tax_lines if t.is_exempted)

    return {
        'by_rate': dict(sorted(by_rate.items())),
        'total_taxable': total_taxable,     # inflated
        'total_tax': total_tax,             # correct, no dedup needed
        'total_lines': len(self._tax_lines),
        'exempt_lines': exempt_count,
        'has_data': len(self._tax_lines) > 0,
    }
```

Affected fields: `total_taxable`, and each `by_rate[<key>]['taxable']`.
Unaffected fields: `total_tax`, every `by_rate[<key>]['tax']`, `total_lines`,
`exempt_lines`, `has_data`.

`self._tax_lines` is populated once, at `NightAuditService.__init__`
(`app/night_audit_service.py:234`, `TaxLine.query...` for the business date),
and is read in exactly two places in the whole class:

- `night_audit_service.py:567`, inside `revenue_summary()` — sums
  `t.tax_amount` only (`tax_total = sum(_f(t.tax_amount) for t in
  self._tax_lines)`), used to derive `accrual_gross`. This is the *tax*
  amount, already correctly split per CGST/SGST row, so it is **not**
  affected by the double-counted *taxable* base and needs no change.
- `night_audit_service.py:1128-1146`, inside `tax_snapshot()` itself.

No other method of `NightAuditService` reads `_tax_lines`, `total_taxable`,
or any `by_rate` bucket.

## 2. Direct caller

`app/night_audit_service.py::full_report()`, lines 1807-1835:

```python
'tax': self._get('tax_snapshot'),
```

`full_report()` is the single orchestration point; `self._get(name)` is a
memoising wrapper (calls `tax_snapshot()` once and caches the dict).
`tax_snapshot()` is never called directly by any route, script, or CLI —
every caller in the app goes through `full_report()['tax']`.

## 3. Indirect / UI / report / export consumers of `full_report()['tax']`

All found via `grep -rn "report\['tax'\]" app/` plus a template scan for
`tax.total_taxable` / `tax.by_rate`:

| Consumer | File:line | What it does |
|---|---|---|
| Live night-audit screen | `app/templates/night_audit_panel.html:1190,1451-1465` | `{% set tax = report['tax'] %}`; renders `tax.by_rate` rows and the `Total` row (`tax.total_taxable`) directly to screen, on every live view of an **open** audit date. |
| Night-audit HTML report | `app/templates/reports/night_audit.html:2996-3028` | Renders `tax.total_taxable` and per-rate `v.taxable` in the "Taxable Amount" KPI card and the tax table. |
| Night-audit print view | `app/templates/reports/night_audit_print.html:497-509` | Same figures, printable layout. |
| Night-audit routes | `app/reports.py:2479`, `app/reports.py:2798`, `app/routes.py:4827` | `tax=report['tax']` passed into the templates above; `report = svc.full_report()`. |
| Night-audit Excel export | `app/reports.py:3618-3629, 4056-4079` (`_night_audit_excel`) | Writes `t['taxable']` per rate row and `tax_snap['total_taxable']` into the exported workbook's grand-total cell. |

None of these consumers re-derive or adjust the taxable figure — they render
exactly what `tax_snapshot()` returns.

## 4. Persisted consumers

### 4a. `NightAuditLog.snapshot_json` (production database)

`app/models.py:932-943` — `NightAuditLog.snapshot_json` (Text),
`snapshot_valid` (Bool), `snapshot_hash` (SHA-256 of the JSON text). This is
the **frozen, integrity-checked** state of a *closed* audit date. It is
written by three code paths, all serialising `NightAuditService(date).full_report()`
(which includes `tax_snapshot()`'s output under the `'tax'` key) to JSON:

- `app/services.py:441-466` — auto-complete path (no blockers) on night-audit close.
- `app/reports.py:3049-3078` — manual `/complete` path (comment at 3398 says
  "Store frozen snapshot so later views don't recompute").
- `app/reports.py:3398-3421` — re-run-from-Skipped recovery path.

Once written, `app/routes.py:4786-4808` prefers the **frozen** snapshot over
a live recompute for any closed date:
```python
if audit_is_closed and current_log.snapshot_json and current_log.snapshot_valid:
    report = _json.loads(current_log.snapshot_json)
```
and `app/reports.py:2748-2757` / `app/services.py:1554-1595` re-hash
`snapshot_json` against the stored `snapshot_hash` to detect tampering —
i.e. the frozen JSON, including its `tax.total_taxable` figure, is treated
as an authoritative historical record, not a value that gets recomputed on
each view.

**Verified against the actual production database** (read-only, via a
disposable copy made with `verification/dbcopy.py::make_copy()`, exactly the
pattern in `verification/_work/q06_repro.py`; production SHA-256 confirmed
unchanged before/after — see `RESULT.json`):

```
total night_audit_logs rows: 1
rows with non-null snapshot_json: 1
rows with snapshot_valid = 1: 1
  audit_date=2026-08-09  status=Completed  snapshot_valid=1
  stored tax.total_taxable = 2285.7
  stored tax.total_tax     = 57.14
  stored tax.total_lines   = 4
  stored tax.has_data      = True
```

This is a **real, hash-sealed, buggy figure already sitting in production**.
`get_gst_report(2026-08-09, 2026-08-09)['total_taxable']` (the correct,
deduplicated figure) is roughly half of this (consistent with the ~2x
inflation factor established in `verification/_work/q06_repro.py` /
`verification/evidence/20260923_q06_analysis/`). Fixing `tax_snapshot()`
going forward will **not** retroactively correct this row — by design, the
frozen-snapshot mechanism is meant to keep historical state immutable, and
`routes.py:4806-4808` will keep serving this exact stale JSON (with the
buggy 2285.7 figure) for the 2026-08-09 audit date until/unless someone
explicitly decides to regenerate it. This is flagged as a candidate STOP
condition in §7.

### 4b. `verification/ledgers/production/dates/*.json` (replay evidence)

`verification/replay/engines.py:101-120` (`NAS_SECTIONS` includes
`'tax_snapshot'`; `_nas_probes()` calls `NightAuditService(day).tax_snapshot`
by name) feeds `verification/replay/replay.py`'s per-date "freeze" ledger.
Read directly (read-only) from the JSON files already checked into
`verification/ledgers/production/dates/`:

```
2026-08-01 .. 2026-08-08.json : total_taxable = 0 (no tax lines that day)
2026-08-09.json               : total_taxable = 2285.7, total_tax = 57.14
2026-08-10.json                : total_taxable = 5904.76, total_tax = 147.6
```

These are **verification evidence artifacts**, not production financial
records, but they are persisted files that already contain the buggy 2x
value, frozen at `frozen_at` timestamps recorded in each file. They exist to
let the replay/reconcile machinery detect drift, not to declare a taxable
base as correct (see §5 — `Q06` in `verification/quantities.py` is exactly
the check that flags this as wrong, at `Severity.BLOCK`).

## 5. Verification consumers — does anything already compensate?

`verification/quantities.py:496-532`, function `q06()`:

```python
rep = _d(get_gst_report(d, d)['total_taxable'])           # deduplicated (correct)
audit = _d(ctx.nas(d).tax_snapshot()['total_taxable'])     # raw (buggy)
per_date[str(d)] = {'gst_report_deduped': str(rep), 'night_audit_raw': str(audit)}
if abs(rep - audit) > Decimal('1.00'):
    div.append(Divergence(str(d), 'gst_service.get_gst_report',
                          'NightAuditService.tax_snapshot', str(rep), str(audit), str(rep - audit)))
```

`Q06` is registered `@quantity('Q06', 'Taxable base (deduplicated vs raw)',
Policy.RUPEE, Severity.BLOCK)`. It calls **both** `get_gst_report()` (via a
top-level `dedup_map` keyed on `(reservation_id, charge_source_type,
charge_source_id)`, lines 504-508) and `tax_snapshot()`, and **records a
`Divergence`, at BLOCK severity, whenever they disagree by more than ₹1**.
It does not compensate, adjust, average, or otherwise mask the two figures —
it deliberately keeps them side by side and treats the gap as a defect to be
reported (`note = 'CGST and SGST each carry the full taxable value of one
supply. Summing both double-counts the base.'`). This is consistent with
`verification/evidence/20260923_q06_analysis/`: the harness has already
correctly identified and is already flagging this exact bug; it has not
worked around it.

`verification/replay/engines.py` (§4b) persists `tax_snapshot()`'s raw
output into the replay ledger **without** dedup — it is an honest replay of
what the application actually returns, which is the whole point of that
module (see its module docstring: "no financial policy," "states what is in
the books"). It does not compensate either.

## 6. Compensation search — explicit result

Grepped the whole repository for divide-by-2 patterns, dedup logic, and any
special-casing of `tax_snapshot`/`total_taxable`/`by_rate`:

- `grep -rn "total_taxable" app/` → four call sites outside
  `night_audit_service.py`: `app/gst_einvoice.py:108,225,333,352` (all
  consume `gst_data`/`gst_summary` sourced from `gst_service.get_gst_report()`
  / `get_folio_gst_summary()`, **never** `tax_snapshot()` — confirmed by
  `gst_einvoice.py`'s own docstring, "Caller passes data from
  `gst_service.get_gst_report()`") and `app/reports.py:4075` (the Excel
  export, §3 — renders the value as-is, no adjustment).
- `grep -rn "dedup|deduplicat" app/night_audit_service.py` → no matches
  (the class has no dedup logic anywhere, including inside `tax_snapshot()`).
- No `/ 2`, `* 0.5`, or similar halving of `total_taxable` or any `by_rate`
  taxable component exists anywhere in `app/` or `verification/`.
- The one `/2` found near the tax UI (`night_audit_panel.html:1455-1456,
  1463-1464`) divides `tax`/`total_tax` (the already-correct figure) in half
  to *display* a CGST/SGST split per row — an unrelated, pre-existing
  display convention, not a taxable-base compensation, and not something
  this trace was asked to fix or judge further.

**Explicit finding: no code anywhere in the repository compensates for the
2x inflation in `tax_snapshot()`'s `total_taxable` / `by_rate[...]['taxable']`.**
Every consumer (UI, print report, Excel export, frozen DB snapshot, replay
ledger) receives and stores/displays the raw inflated figure as-is.

## 7. Isolation assessment — can the fix stay inside `tax_snapshot()`?

Yes, with one caveat about frozen historical data (not a code-isolation
problem):

- `self._tax_lines` (the source list) is read in only two places in the
  class (§1): `revenue_summary()` (uses `tax_amount`, unaffected) and
  `tax_snapshot()` itself. Adding the same dedup key `get_gst_report()` uses
  (`(reservation_id, charge_source_type, charge_source_id)` — see
  `verification/quantities.py:504-508` and `app/gst_service.py:705,
  712-716`) inside `tax_snapshot()`'s `by_rate` and `total_taxable`
  computation touches no other method's logic.
- `total_tax` is computed independently from `t.tax_amount`, which is
  already correctly split per row; a dedup fix to `taxable_amount` handling
  does not need to (and must not) touch `total_tax`.
- No other section of `full_report()` reads `report['tax']`'s fields to
  compute a *different* section's value — each of the 13 `full_report()`
  sections is independently keyed and independently cached via `self._get()`
  (`night_audit_service.py:1807-1835`); nothing downstream of `tax_snapshot()`
  re-derives a further figure from `total_taxable` inside `NightAuditService`.
- The **caveat**: `verification/replay/engines.py:101-111`'s `NAS_SECTIONS`
  freezes `tax_snapshot()`'s section verbatim into the replay ledger. A code
  fix changes the *live* figure from the next audit run onward; it does not
  and cannot retroactively alter already-frozen `NightAuditLog.snapshot_json`
  rows (§4a) or already-written `verification/ledgers/production/dates/*.json`
  files (§4b) — those are deliberately immutable records of what the code
  produced at the time. That is a historical-data question, not a
  code-isolation problem, and is exactly the kind of thing flagged below.

## 8. Explicit STOP-condition check

- **A downstream workflow intentionally depending on the 2x value?** Not
  found. §5 and §6 show every consumer treats it as a plain pass-through
  figure; `verification/quantities.py::q06()` treats the divergence as a
  defect to report, not a value to rely on.
- **Need for historical correction?** Yes — flagged, not resolved here.
  Production `NightAuditLog` id=1 (`audit_date=2026-08-09`, `status=Completed`,
  `snapshot_valid=1`) has a hash-sealed `snapshot_json` whose `tax.total_taxable`
  (2285.7) is the buggy, ~2x-inflated figure (§4a), and `routes.py:4806-4808`
  will keep serving that exact frozen JSON for that date regardless of any
  future code fix. Whether/how to regenerate or re-flag that one frozen
  record is a decision for whoever authorizes the fix — this trace does not
  make that call or touch the record.
- **Ripple into another financial calculation?** Not found — §7 shows the
  fix is code-isolated to `tax_snapshot()`'s `total_taxable`/`by_rate`
  taxable component; `total_tax` and every other `full_report()` section are
  independent.
- **A broader business rule discovered?** Not found. `_build_tax_lines`
  (`app/gst_service.py:300-339`) storing the full unsplit taxable amount on
  both the CGST and SGST row is confirmed (in the prior Q06 analysis) to be
  a mechanical bug, not an intentional GST-filing convention — the only code
  that produces a GST-return-shaped artifact (`gst_einvoice.py`) sources
  from `get_gst_report()`, which already applies the correct dedup, and
  never from `tax_snapshot()`.

**Net: one STOP-worthy item found (§4a, the sealed production
`NightAuditLog` row for 2026-08-09) that a fix authorization should account
for explicitly; no other STOP condition triggered.**
