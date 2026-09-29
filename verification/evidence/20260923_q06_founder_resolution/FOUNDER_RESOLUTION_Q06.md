# Founder Resolution Round 4 — Q06 GST Taxable-Base Defect — recording record

| | |
|---|---|
| Directive | FG-P2-FOUNDER-RESOLUTION-20260923-01 (Founder resolution authorized; governance recording only) |
| Recorded | 2026-09-23 |
| Baseline | `b0d30542ff6b3cdbbc269fd8c17679c80ed9f718` = `origin/main`; tree clean before recording |
| Inputs | `20260923_q06_analysis/` (forensic root-cause analysis, classification Q06-B), `20260923_q06_downstream/` (consumer-chain trace, compensation search, persistence finding) |
| Governance records written | `verification/FOUNDER_DECISIONS.md` — new section "Founder Resolution Round 4 — Q06 GST Taxable-Base Defect — FG-P2-FOUNDER-RESOLUTION-20260923-01" (append-only; prior content byte-identical) |
| ADRs | **not edited.** No ADR governs GST computation directly; the authoritative record of this ruling is `FOUNDER_DECISIONS.md` (FD-018 durable-record principle). |
| Commit / push | **none** — all changes and this directory are untracked, per the directive |
| Production | unchanged — `instance/pms.db` verified read-only before and after (see `RESULT.json`) |
| Status | **Q06 FOUNDER RESOLUTION PASS — ROUND 4 RECORDED — IMPLEMENTATION NOT AUTHORIZED** |

## Factual basis (from prior evidence, not re-derived here)

1. `NightAuditService.tax_snapshot()` (`app/night_audit_service.py:1136`) double-counts taxable base for intrastate charges.
2. CGST and SGST `TaxLine` rows each carry the full, unsplit taxable base (`app/gst_service.py:300-339`).
3. `get_gst_report()` (`app/gst_service.py:674-771`) correctly deduplicates taxable base at the charge level.
4. `tax_snapshot()` does not deduplicate, producing an exact 2x taxable base on the affected intrastate dataset (reproduced: 1,142.85→2,285.70 and 2,952.38→5,904.76).
5. `total_tax` is unaffected in both paths — each row's `tax_amount` is already correctly split.
6. The actual GST/e-invoice filing path (`app/gst_einvoice.py`) sources exclusively from `get_gst_report()` and is not affected.
7. No downstream compensation for the inflated taxable-base figure was found anywhere in `app/` or `verification/`.
8. The `NightAuditLog` record for `audit_date = 2026-08-09` is already persisted and hash-sealed (`snapshot_valid = 1`).
9. That sealed record contains the incorrect taxable-base value `2285.7`.
10. `verification/ledgers/production/dates/*.json` (the replay ledger) also preserves the historical value.

## The three decisions as recorded

| Id | Decision (verbatim gist) | Governance effect | Implementation status |
|---|---|---|---|
| Q06-H1 | Preserve the sealed `NightAuditLog` 2026-08-09 record exactly as recorded — no delete, rewrite, recalculation, mutation, re-sealing, or silent replacement | designates the record a historical artifact of the confirmed defect; no retroactive correction authorized | none required; no record read for modification |
| Q06-H2 | Correct `tax_snapshot()` for future calculations using the same charge-level dedup semantics as `get_gst_report()` | permits a later bounded implementation directive confined to `NightAuditService.tax_snapshot()` | **not implemented**; function unchanged at this recording |
| Q06-H3 | No retroactive production data correction authorized; any future corrected-historical-figure need must use a separate superseding record with explicit provenance, never an overwrite | establishes the supersede-never-overwrite model without building or requiring the mechanism now | not applicable; no mechanism built |

## Append-only proof

`verification/FOUNDER_DECISIONS.md` was extended by appending only: content at `b0d3054` is a byte prefix of the new file; the appended tail equals the drafted section exactly; it appears once; no CR byte introduced. Line count before: 1206 (excluding trailing newline accounting matched to the prior Round 3 entry's end); after: see `RESULT.json`. No prior resolution (Rounds 1-3, FD-001…FD-019, FD-P2-01…07) was rewritten, renumbered, or duplicated.

## Boundary reaffirmed

This recording authorizes governance disposition only. It does **not** authorize:
- implementation of the `tax_snapshot()` code fix (Q06-H2) — a separate directive is required;
- any historical-correction/superseding mechanism (Q06-H3) — not built, not required now;
- any change to CF-10, CF-11, business-date integrity, recovery, deployment rehearsal, maker-checker, or night-audit hardening — all remain exactly as they stood before this entry.
