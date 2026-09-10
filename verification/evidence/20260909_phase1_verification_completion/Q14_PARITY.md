# Q14 Parity - exact results

Directive FG-P1-VERIFICATION-COMPLETION-20260909-01. Q14 is the existing D1 quantity `verification/quantities.py :: q14` - "Folio balances / partition integrity", policy EXACT, severity BLOCK. It compares **sum over folios (charges)** (`calculate_folio_amount` over every folio) with **sum over reservations (charges)** (`calculate_stay_amount` over every reservation) and reports the unrouted counts. It was executed through the existing parity runner (`verification.runner.run`, mode CROSS_IMPLEMENTATION) via `harness_runs.py parity`, which only passes the `source` the CLI does not expose. Nothing about Q14 was reinterpreted.

## 1. Results

| Population | sum over folios (charges) | sum over reservations (charges) | delta | unrouted charges / payments | Verdict | Evidence pack |
|---|---|---|---|---|---|---|
| Production copy (anchor `51dd83b7...`) | 0.00 | 476.19 | -476.19 | 2 / 6 | **DIVERGED** | `20260909_155832_phase1_vc_production` |
| Clean new-activity copy (set D: 11 payments, 10 charges) | 1,050.00 | 1,526.19 | -476.19 | 2 / 6 | **DIVERGED** | `20260909_160115_phase1_vc_setD` |
| Broad new-activity copy (set A: 15 payments, 12 charges) | 2,582.00 | 3,058.19 | -476.19 | 2 / 6 | **DIVERGED** | `20260909_155829_phase1_vc_newactivity` |
| Five registered datasets | equal | equal | 0 | 0 / 0 | **AGREED** (5/5) | `datasets.json` |

Reading: on every copy derived from production the delta is **exactly 476.19 = extra_charges 1 (380.95) + 2 (95.24)**, the two D11 charges, and the unrouted counts are exactly the eight D11 rows. Every charge posted by the new activity (1,050.00 on set D; 2,582.00 on set A) is reachable through a folio. Q14 therefore behaves as the verification plan predicted: **AGREED where attributed, DIVERGED by the D11 amount wherever the eight preserved rows exist** (FD-010, AR-001). It cannot AGREE on production until the Founder's separate decision on the eight rows (B-3), which this directive does not touch.

## 2. Other quantities in the same runs - recorded, outside this directive

The parity runner evaluates 22 quantities; the directive asked for Q14. For completeness the verdicts are recorded here without reinterpretation.

| Quantity | Production | Set D | Set A | Attributed divergence (from the packs) |
|---|---|---|---|---|
| Q01 | SINGLE_SOURCE | SINGLE_SOURCE | SINGLE_SOURCE | one implementation only |
| Q02, Q03, Q05, Q08, Q09, Q10, Q13, Q16, Q19, Q22 | AGREED | AGREED | AGREED | - |
| Q11, Q21 | VACUOUS | VACUOUS | VACUOUS | no refunds/voids or shift on these copies (Q11 stays VACUOUS on set B too) |
| Q04 room revenue per business date | AGREED | DIVERGED | DIVERGED | `NightAuditService.revenue_summary` / `kpi_helpers.get_accrual_room_revenue` count every in-house night (accrual) vs `sum(posted room_rent charges)` which only exist for audited nights - a definitional difference surfaced by having in-house stays; production has none |
| Q06 taxable base | DIVERGED | DIVERGED | DIVERGED | pre-existing on production (`gst_report` vs `tax_snapshot` factor 2) |
| Q07 tax by component | AGREED | DIVERGED | DIVERGED | live `compute_stay_gst` vs stored `TaxLine` rows - tax lines are only stored at invoicing; in-house stays have none |
| Q12 outstanding per reservation | AGREED | DIVERGED (0.40) | AGREED | unrounded vs invoiced basis on one reservation |
| Q14 | DIVERGED (D11) | DIVERGED (D11) | DIVERGED (D11) | see section 1 |
| Q15 night audit stored vs recomputed | AGREED | DIVERGED | DIVERGED | occupancy_count recomputed after post-close checkouts on set D; on set A additionally the accrual figures moved by the set A fixtures (a stay inserted into the closed 2026-08-09 and a rate change after close) |
| Q17 MIS aggregates | DIVERGED (WARN) | DIVERGED (WARN) | DIVERGED (WARN) | pre-existing on production |
| Q18 dashboard tiles | AGREED | DIVERGED | DIVERGED | dashboard vs flash-report definitions of departures/arrivals/available rooms once movements exist |
| Q20 ADR / RevPAR | DIVERGED | DIVERGED | DIVERGED | pre-existing on production (unscoped average vs date-scoped) |

None of these involve `folio_id`; they are cross-implementation definitional differences in the D1 parity layer that production's four-reservation population never exercised. They are not Phase 1 regressions and are not claimed as Phase 1 findings; they are candidates for the Phase 6 parity review and are listed under documented limitations.

## 3. Production safety for these runs

Every parity run copied its source with the backup API and re-hashed it afterwards (`read_only_verified` in each pack). The production anchor was unchanged before and after the directive (VERIFICATION_COMPLETION.md section 7).
