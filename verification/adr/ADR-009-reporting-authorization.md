# ADR-009 — Reporting Authorization

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-016; context FD-003 (reports are derived, not a system of record) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. |

## Context

- `app/reports.py`: 49 `@reports_bp.route` handlers; one `before_request` guard that is `@login_required` only (`app/reports.py:41-45`); 23 handlers call `_require_accountant()` (Admin/Manager/Accountant) inline. **At least 26 report routes are readable by any authenticated role, including Housekeeping.** The Register (R6, ruling B-3) counts 27; the difference is a counting basis, not a disagreement about the condition.
- `app/billing.py`: `gst_report` Admin/Manager/Accountant; `invoice_register` Admin/Manager/FrontDesk/Accountant.
- Reports consume canonical engines (Constitution P3) and are derived; they are never a system of record (ADR-001).
- Golden masters capture report HTML only (V5); Excel/PDF branches unverified.
- Master Plan: Phase 4 unit 4.2 "close the 27 unrestricted report routes"; Layer 2 coverage "Reporting permissions — Phase 4".

## Decision (derived from FD-016)

Report access is an *authorization* question distinct from
authentication. Financial reports require a financial role; operational
reports require an operational role; no report is readable merely by
being logged in.

## Proposed architecture

1. **Classify every report route** as FINANCIAL / OPERATIONAL / GUEST-DATA / SYSTEM, recorded as data in the blueprint (an enumerable map, as ADR-008).
2. **Default role sets** (proposed, UNRESOLVED until MP-D9): FINANCIAL → Admin, Manager, Accountant; OPERATIONAL → Admin, Manager, FrontDesk (+ Housekeeping only for housekeeping-specific reports); GUEST-DATA → Admin, Manager, FrontDesk; SYSTEM → Admin.
3. **Same enforcement shape** as ADR-008: fail-closed `before_request` on `reports_bp`, map-driven, replacing the 23 inline calls without changing their outcome.
4. **Export branches** (Excel/PDF) inherit the route's classification; golden-master capture extended in Phase 6 (V5).
5. **Negative matrix** per route × role recorded as evidence before the change ships.

## Unresolved

Classification of each of the 49 routes (requires a route-by-route
review not performed here) · Housekeeping scope (F13 UNKNOWN, MP-D6) ·
MP-D9 operator profile · whether report *generation* (writes to
`notification_logs`, exports) counts as a mutation for audit purposes.

## Implementation boundary

None authorized. Master Plan Phase 4.
