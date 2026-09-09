# ADR-011 — Operator Accountability

| | |
|---|---|
| Status | **PROPOSED FOR ADOPTION** — 2026-09-08 under FG-P0-ADR-ADOPTION-20260908-01 (FD-014, AR-012). Accountability architecture settled; **storage location and system-actor mechanics open**; readiness condition: resolution of those mechanics at the relevant phase gate. |
| Founder decision | FD-014 (2026-09-08); context FD-013, FD-016 |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. |

## Context — what provenance a financial row carries today

| Element | `payments` / `extra_charges` | `audit_logs` | `night_audit_logs` | `shifts` |
|---|---|---|---|---|
| Authenticated operator | ✗ (no user column) | `staff_user_id` (NOT NULL) | `run_by_user_id`, `started_by_user_id` | `user_id`, `closed_by_user_id`, `approved_by_user_id` |
| Role at the time | ✗ | ✗ (role recorded only in Phase 2a denial `after_state`) | ✗ | ✗ |
| Operational responsibility (shift) | ✗ | ✗ | ✗ | implicit |
| Technical timestamp | `created_at` UTC | `timestamp` UTC | `run_at`, `completed_at` | `start_time`, `end_time` |
| Business date | `payment_date` / `charge_date` — **mixed basis** (ADR-004) | ✗ | `audit_date` | ✗ |
| Workstation / IP | ✗ | `ip_address` | ✗ | via `close_shift(ip_address=)` into audit only |
| Maker / checker | `voided_by_user_id`; correction `corrects_id` | — | override fields | `approved_by_user_id` |

Evidence for why this matters: the eight FD-010 rows were identified as
commissioning activity only by cross-referencing `admin` + `127.0.0.1`
in `audit_logs`, session transcripts and reopen reasons — none of the
rows themselves record who posted them.

## Decision (as ruled by FD-014)

Financial accountability must distinguish: authenticated operator; role;
operational responsibility; timestamp; business date; applicable
workstation/IP provenance; maker/checker identity where required.

## Proposed architecture

1. **Provenance envelope** captured at every financial posting and persisted with the row or with a coupled audit row: `actor_user_id`, `actor_role` (as at posting — roles change), `shift_id` (operational responsibility, where a shift is open), `business_date` (ADR-004), `created_at` UTC, `ip_address`/workstation identifier, and for approved actions `checker_user_id`.
2. **Where it lives — UNRESOLVED:** (a) new columns on `payments`/`extra_charges` (a schema change → PD-004/005/006), or (b) a mandatory coupled `AuditLog` row per posting with the envelope in `after_state` (no schema change; relies on ADR-012 retention), or (c) both.
3. **Role snapshot** is captured, not joined, because `users.role` can change after the fact.
4. **Unattended actors** (scheduler jobs, FD-009): a designated system actor identity, never NULL and never `admin`, so machine postings are distinguishable from operator postings — **UNRESOLVED** how represented.
5. **Immutability:** provenance is written once with the row; corrections carry their own envelope and point at the original (`corrects_id`).

## Unresolved

Storage location (schema vs audit) · system-actor representation ·
workstation identifier beyond IP on a LAN (`enable_lan.bat` deployments)
· whether `shift_id` is mandatory at posting (blocks posting when no
shift is open) · MP-D9.

## Implementation boundary

None authorized.

## Architecture Resolution Round 1 reconciliation (2026-09-08)

Source: `verification/evidence/20260908_architecture_resolution_round1/RECORD.md`.

- **AR-012**: material actions must be attributable to operator identity, role, action, relevant business date and sufficient provenance; automated/system actions must have equivalent accountability through a controlled system identity/provenance. This confirms *Proposed architecture* items 1, 3 and 4 as requirements.
- **AR-013** adds that any scheduler action capable of materially changing financial or operational state must carry explicit authorization, identifiable provenance, business-date authority, auditability, idempotency, failure handling and verification. A dedicated scheduler-controls ADR is required at the Phase 3/4 gate and is not created in this round (AR-015).
- Status moved DRAFT → PROPOSED. Storage location (schema columns vs coupled audit row), system-actor representation, workstation identifier and mandatory `shift_id` remain unresolved.
- Nothing implemented.

## Adoption review (2026-09-08)

Reviewed under `FG-P0-ADR-ADOPTION-20260908-01` and moved PROPOSED → **PROPOSED FOR ADOPTION**. Settled: the accountability elements (FD-014) and the requirement for equivalent system-actor provenance for automated actions (AR-012); the provenance envelope of *Proposed architecture* item 1; role snapshot at posting (item 3); write-once immutability (item 5). Open, and the reason adoption waits: where the envelope is stored (schema columns → PD-004/005/006, versus coupled audit row → ADR-012 retention), the system-actor representation, the workstation identifier, and whether `shift_id` is mandatory. Tracked in `verification/adr/BACKLOG.md`.

