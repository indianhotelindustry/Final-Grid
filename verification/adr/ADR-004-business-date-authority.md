# ADR-004 — Business-Date Authority

| | |
|---|---|
| Status | **ADOPTED** — 2026-09-08 under FG-P0-ADR-ADOPTION-20260908-01 (FD-013, AR-008). Architecture adopted; implementation remains separately authorized work. |
| Founder decision | FD-013 (2026-09-08) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. The refactor is explicitly not authorized (FD-013). |

## Context

Constitution principle **P8 — One temporal basis** is registered as
invariant-enforced. The invariants that declare P8 (`INV-A04`, `INV-B03`,
`INV-B04`, `INV-B05`, `INV-B06`) check *bounds and sequence*, not the
*basis* a row was dated on. The code mixes bases:

| Source | Count in `app/` | Financially material examples |
|---|---|---|
| `business_date` | 526 references | night audit posting (`charge_date=_bd`), business-date advance, KPI scope resolver (`app/services.py:333+`) |
| `date.today()` | 61 | **`Payment.payment_date` default** (`app/models.py:812`); **`ExtraCharge.charge_date` default** (`:775`); refund `payment_date` (`app/services.py:1493`); correction "today" (`:920`, `:1003`); billing / no-show / OTA report default ranges; `booking.py:83` arrival validation |
| `datetime.now()` | 19 | checkout timestamp (`app/routes.py:3145`), report "generated at" |
| `datetime.utcnow()` | 139 | `created_at`, `AuditLog.timestamp`, shift `start_time` |

Consequence today: `extra_charges.charge_date` carries two bases in one
column (night-audit rows on business date, all other writers on wall
clock). `get_business_date()` itself falls back to `date.today()` when
the singleton is absent (`app/services.py:328-330`). The live business
date was 2026-08-10 at drafting, 29 days behind the calendar.

## Decision (as ruled by FD-013)

- **Business date is the authoritative financial/operational accounting date.**
- **System clock timestamps may remain technical timestamps.**

## Architectural consequences (for the later refactor directive)

| Area | Consequence |
|---|---|
| Payments / charges | `payment_date` and `charge_date` are accounting dates → derive from the business date at posting, not `date.today` model defaults |
| Corrections / refunds | dated on the business date of posting |
| Night audit | unchanged (already business-date based) |
| Reports | default *ranges* on business date; "generated at" stays a technical timestamp |
| Invoices | invoice date — **UNRESOLVED**: business date at issue, or date of first view (current numbering behaviour assigns on first view, `app/routes.py:212`) |
| Reservations, check-in/out | arrival/departure validation — **UNRESOLVED** whether against business date or calendar date |
| Cashiering | shift `start_time`/`end_time` remain technical timestamps; the rule mapping a shift to a business date is **UNRESOLVED** |
| Audit records | `AuditLog.timestamp` stays UTC technical; provenance should additionally carry the business date (ADR-011) |
| Verification | an invariant that checks *basis* (not merely bounds) would be a new registration under CONSTITUTION §4 — **UNRESOLVED** whether to add one |

## Unresolved

1. Invoice date rule. 2. Arrival/departure validation basis. 3. Shift-to-business-date mapping. 4. Whether a basis-checking invariant is registered. 5. Behaviour when the business date is stale by more than a threshold (Master Plan Phase 3 unit 3.6 "staleness escalation").

## Implementation boundary

None authorized.

## Architecture Resolution Round 1 reconciliation (2026-09-08)

Source: `verification/evidence/20260908_architecture_resolution_round1/RECORD.md`.

- **AR-008** restates FD-013 with the operative rule this ADR proposed: the controlled business date is authoritative for financial and operational accounting; system timestamps remain technical timestamps (event chronology, diagnostics, infrastructure logging, audit timing); financial/operational logic must not silently substitute `date.today()` where business-date semantics apply.
- Status moved DRAFT → PROPOSED FOR ADOPTION. The five *Unresolved* items (invoice date rule, arrival/departure validation basis, shift-to-business-date mapping, a basis-checking invariant, staleness threshold) are Phase 3 gate items under AR-015 and do not block adoption of the principle.
- Nothing implemented. `Payment.payment_date` / `ExtraCharge.charge_date` still default to `date.today` at the model.

## Adoption record (2026-09-08)

Adopted under `FG-P0-ADR-ADOPTION-20260908-01`, recorded in `verification/FOUNDER_DECISIONS.md`. The *Decision* is verbatim FD-013; AR-008 supplies the operative rule (no silent substitution of `date.today()` where business-date semantics apply; system timestamps remain technical). No conflicting architecture exists. The *Unresolved* items (invoice date rule, arrival/departure validation basis, shift-to-business-date mapping, basis-checking invariant, staleness threshold) are implementation-design questions for the Phase 3 gate and are tracked in `verification/adr/BACKLOG.md`.

**Architecture adopted; implementation remains separately authorized work.** `Payment.payment_date` and `ExtraCharge.charge_date` still default to `date.today` at this recording. From this point the ADR is append-only.

