# Implementation Consequences of Round 4 — what each ruling permits later

Directive FG-P2-FOUNDER-RESOLUTION-20260923-01. **Nothing below is authorized by the recording itself**; each line names the separate bounded directive that a ruling now permits, its scope boundary, and the evidence its closure needs (FD-004 authority chain: Founder decision → governance → implementation directive → mutation → verification evidence).

| Ruling | Permits (later directive) | Scope boundary | Closure evidence | Does NOT permit |
|---|---|---|---|---|
| Q06-H1 | Nothing further — this is a standing preservation rule, not a directive-generating decision | no code, schema, or data touches the sealed 2026-08-09 record, ever, under this ruling | none needed; the record stands as-is, cited by id/hash in any future audit | deletion, rewrite, in-place recalculation, re-sealing, or silent replacement of the sealed record |
| Q06-H2 | **Q06 forward-fix directive**: apply charge-level dedup (by `reservation_id`/`charge_source_type`/`charge_source_id`, the same key `get_gst_report()` uses) to `total_taxable` and each `by_rate` bucket's taxable component inside `NightAuditService.tax_snapshot()` | one method in `app/night_audit_service.py`; no change to `get_gst_report()`, `_build_tax_lines`, `app/gst_einvoice.py`, or `revenue_summary()` | diff limited to `tax_snapshot()`; copy test reproducing the known dataset showing `total_taxable` now matches `get_gst_report()` for the same range; `total_tax` unchanged; Golden Master, replay, and `inv-run`/`q06()` re-run clean; production anchor unchanged | any change to `get_gst_report()`, the GST/e-invoice filing path, or any already-sealed `NightAuditLog` record |
| Q06-H3 | A future, separately-authorized **historical-correction/superseding-record directive**, only if a concrete business need arises | would create a new record referencing the original by id, never overwrite it; schema change (a new table/column) would itself need separate authorization (PD-004-style) | not applicable now — no directive exists yet | overwriting, backdating, or otherwise mutating the original sealed snapshot; building the mechanism speculatively |

## Suggested sequence of directives (not an authorization)

1. Q06 forward-fix directive (Q06-H2) — smallest, isolated, already fully scoped by the prior forensic and downstream-impact analyses.
2. (Unchanged from Round 3) CF-11 credit-path fix and CF-10 audit-coupling normalization.
3. (Unchanged from Round 3) Invariant-refinement directive (FD-P2-06).
4. (Unchanged from Round 3) Recovery-hardening directive (FD-P2-04).
5. (Unchanged from Round 3) Phase 3 (business date, night audit; FD-P2-05).
6. (Unchanged from Round 3) ADR-010 adoption (FD-P2-07) → Phase 2b.
7. (Unchanged from Round 3) Deployment rehearsal and certification.

Each directive: one authorizing reference, one commit, one evidence pack (SC-6); production anchor verified at start and end (SC-1).
