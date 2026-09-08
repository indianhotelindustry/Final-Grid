# ADR-001 — System-of-Record Boundary

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-003 (2026-09-08); context FD-011, FD-013 |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. Architecture record only. |

## Context

No system-of-record statement existed in the repository before FD-003.
The Finding Register (MP-D4) asks whether SQLite remains the system of
record; that question is **still open** and is not decided here.

De facto authority, from code at the checkpoint:

| Domain | Where authority lives today | Evidence |
|---|---|---|
| Reservation | `reservations` | `app/models.py:285` |
| Guest identity | `guests`, `guest_id_documents`, `precheckin_*`, `foreign_national_info` | `app/models.py:170`, `:1002` |
| Room / occupancy | `rooms`, `reservation_rooms`, canonical occupancy engine | `app/occupancy_engine.py` |
| Folio | `folios` — one per reservation, owns no rows today | `app/models.py:711-761` |
| Payment / extra charge | `payments`, `extra_charges`, append-only corrections | `app/models.py:764-830` |
| Invoice | `Reservation.invoice_number`; sequence `settings.invoice_counter`; `tax_lines` | `app/models.py:345`, `app/routes.py:212-250`, `:3994` |
| Company billing | `checkin_records.company_id` (live); `Folio.company_id` (inert) | `app/gst_einvoice.py:54`, `app/gstr_export.py:52` |
| Cashiering | `shifts` (expected / declared / variance, approval) | `app/models.py:46-78`, `app/shift_service.py` |
| Business date | `business_date` singleton | `app/models.py:100` |
| Night audit | `night_audit_logs` with `snapshot_json`, `snapshot_hash`, `snapshot_valid` | `app/models.py:908-960` |
| Audit trail | `audit_logs` | `app/models.py:1058` |
| Verification evidence | `verification/evidence/` (Git-tracked) | — |
| Configuration | `settings` table; `.env` bootstrap | `app/__init__.py:78` |
| Reporting | derived from canonical engines (P3) | `app/reports.py` |

## Decision (as ruled by FD-003)

- **Reservation = stay unit.**
- **Folio = billing unit.**
- **Invoice = reservation-level document** under the current Level 2 decision.
- Level 3 split billing is outside current scope.
- Corporate billing remains reservation-level unless separately redesigned and approved.

## Architectural consequences

1. Folio is the unit to which every financial row is attributed (ADR-002); the reservation remains the unit against which the invoice is issued and the stay is reconciled.
2. Under Level 2 the folio-level and reservation-level views of money are required to agree (INV-A03); neither replaces the other.
3. `Folio.company_id` remains inert until a separate redesign is approved (Master Plan Phase 2b unit 2b.3).
4. Business date is the accounting date for all financial-state domains (ADR-004).
5. The audit trail is a system of record for provenance and is subject to ADR-012.
6. Reports are derived, never authoritative; their authorization is ADR-009.

## Unresolved — explicitly not decided here

| Item | Why open |
|---|---|
| Whether SQLite remains the persistence engine (MP-D4) | Founder decision not yet made |
| Whether OTA/webhook payloads are ever authoritative for guest identity | No evidence of a rule; `webhook_logs` retains raw payloads |
| Whether `settings` or `.env` wins when both define a value (`app_name`, `HOTEL_NAME`) | Fallback order exists in code; no governance statement |
| Where invoice *date* comes from (business date vs wall clock) | Depends on ADR-004 |

## Implementation boundary

None authorized. This ADR changes no code and no data.
