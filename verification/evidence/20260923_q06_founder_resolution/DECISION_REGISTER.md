# Decision Register — Founder Resolution Round 4 (2026-09-23)

| Id | Subject | Decision | Supersedes / relates to | Closes | Leaves open |
|---|---|---|---|---|---|
| Q06-H1 | Historical record preservation | Sealed `NightAuditLog` 2026-08-09 record preserved exactly; no delete/rewrite/recalc/mutate/re-seal/replace | relates to Q06 (`20260923_q06_analysis/`, `20260923_q06_downstream/`); consistent with the CF-11 "disclosed, not silently fixed" precedent | the historical-record disposition question for this specific sealed record | whether any future presentation need for a corrected figure arises (see Q06-H3) |
| Q06-H2 | Forward correction | Correct `tax_snapshot()` taxable-base aggregation using `get_gst_report()`'s charge-level dedup semantics, for future calculations only | applies to `app/night_audit_service.py :: NightAuditService.tax_snapshot()`; does not touch `get_gst_report()` or `app/gst_einvoice.py` | nothing yet (implementation pending) | the actual code change, its regression evidence (GM/replay/inv-run/`q06()`), and re-scoring of gates G3/G5 |
| Q06-H3 | Historical correction model | No retroactive production data correction authorized; a future corrected historical figure, if ever needed, must be a separate superseding record with provenance, never an overwrite | governs how any future historical-correction request for this or a similar defect would be handled | the "can we just fix the sealed record" question — answered no | building the actual supersede mechanism (not required unless a future need arises) |

## Interaction notes

- Q06-H1 × Q06-H2: the forward fix (H2) does not retroactively alter the record H1 preserves; `routes.py:4786-4808` will continue serving the 2026-08-09 record frozen exactly as sealed, both before and after H2 is eventually implemented.
- Q06-H2 × G3/G5: implementing Q06-H2 is expected to close the `q06()` divergence check (`verification/quantities.py:496-532`, Severity.BLOCK) but does not by itself close CF-10 (audit-coupling normalization), which is a separate, still-open item also gating G5.
- Q06-H1 × Q06-H3: H3 generalizes H1's specific "don't overwrite" ruling into a standing model for any future case of this kind, without pre-authorizing that future work.

## Not decided by Round 4 (deliberately)

The `tax_snapshot()` code correction itself (reserved to a later bounded implementation directive under Q06-H2); any historical-correction/superseding mechanism (reserved, not required, under Q06-H3); CF-10; CF-11; business-date integrity; recovery/PD-006 hardening; deployment rehearsal (G11); maker-checker implementation; night-audit hardening (Phase 3); any other open Founder decision listed in Round 3's carry-forward register.
