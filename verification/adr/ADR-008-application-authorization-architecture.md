# ADR-008 — Application Authorization Architecture

| | |
|---|---|
| Status | **ADOPTED (architecture)** — 2026-09-08 under FG-P0-ADR-ADOPTION-20260908-01 (FD-016, FD-015, AR-009). Chain: Authentication → Role/Permission → Operation → Audit. Phase 2a frozen. **FD-015 not implemented; route-by-route work remains future work.** |
| Founder decision | FD-016 (identity vs authorization; Phase 2a frozen), FD-015 (`list_folios` read scope) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. Phase 2a code is unchanged; FD-015 is **not** implemented by this ADR. |

## Context

- Roles: Admin, Manager, FrontDesk, Housekeeping, Accountant (`app/auth.py:18-26`).
- Seven guard idioms across 298 routes (Register R6): `role_required`/`admin_required` (`app/auth.py:33-49`), `_manager_required` (`app/billing.py:27`), `_deny_role` (`app/routes.py:426`), `_admin_only`, `_require_accountant()` inline, `has_role()+abort(403)`, and blueprint `before_request` guards. All HTML-era guards redirect (302) rather than refuse.
- **Phase 2a (frozen):** `app/folio.py` — fail-closed `before_request` with an explicit endpoint→roles map (`_FOLIO_ROLES`), JSON 401/403, audit coupling, refusal recording; 29/29 negative cases. `list_folios`, `create_folio`, `transfer_charge`, `transfer_payment` all `('Admin','Manager')`.
- ≥26 of 49 report routes carry no restriction beyond login (ADR-009).
- `main.guest_folio` and `main.reservation_folio` are guarded by the `main` blueprint's `before_request` plus inline `_deny_role`.

## Decision (as ruled by FD-016)

- Authentication establishes identity. Authorization establishes whether that identity may perform the operation.
- Phase 2a folio authorization remains complete and frozen.
- Broader authorization is implemented progressively without reopening or weakening Phase 2a.

## FD-015 — recorded scope for `list_folios` (not implemented)

| Role | `list_folios` |
|---|---|
| Admin | Read |
| Manager | Read |
| Accountant | Read |
| Front Desk | Read |
| Other roles | No |

Read-only visibility; no mutation authority. Code at drafting:
`('Admin','Manager')`. The change is a one-entry map edit in
`_FOLIO_ROLES` under a later directive; the three mutating endpoints stay
`('Admin','Manager')`.

## Proposed architecture

1. **One enforcement shape**, generalised from Phase 2a: per-blueprint fail-closed `before_request` with an explicit, enumerable endpoint→roles map. Deny by default; allow only what is named.
2. **Refusal shape by surface:** JSON 401/403 for API endpoints; for HTML routes — **UNRESOLVED** whether to return 403 pages or keep redirect-with-flash.
3. **Map location:** per-blueprint constant (as `_FOLIO_ROLES`) vs one central registry — **UNRESOLVED**.
4. **Migration path:** blueprint by blueprint (`reports`, `billing`, `pos`, `grc`, `loyalty`, `main`), each with its own negative matrix, never touching `app/folio.py`.
5. **Denial recording** for mutating endpoints, best-effort, as Phase 2a does.
6. **Role model:** the five roles are retained until MP-D9 (operator profile) is ruled; no new role is introduced by this ADR.

## Unresolved

HTML refusal shape · central vs per-blueprint map · MP-D9 operator
profile · whether `Housekeeping` has any financial read at all
(Register F13 UNKNOWN) · treatment of the 172 function-local imports
that make guard consolidation awkward (§19 forbids restructuring).

## Implementation boundary

None authorized. Phase 2a is not reopened.

## Architecture Resolution Round 1 reconciliation (2026-09-08)

Source: `verification/evidence/20260908_architecture_resolution_round1/RECORD.md`.

- **AR-009** fixes the chain **Authentication → Role/Permission → Operation → Audit**; authentication alone is not authorization; Phase 2a remains frozen; future work extends rather than bypasses the Phase 2a boundary. This is the shape *Proposed architecture* items 1, 4 and 5 already follow (fail-closed map, blueprint by blueprint, denial recording).
- Status moved DRAFT → PROPOSED FOR ADOPTION. HTML refusal shape and central-vs-per-blueprint map remain implementation-level; MP-D9 (operator profile) is deferred under AR-015.
- **FD-015** remains a recorded decision only: `_FOLIO_ROLES['folio.list_folios']` is still `('Admin','Manager')` at `app/folio.py:47-52`. Not changed. Phase 2a evidence and code untouched.

## Adoption record (2026-09-08)

Adopted under `FG-P0-ADR-ADOPTION-20260908-01`, recorded in `verification/FOUNDER_DECISIONS.md`. What is adopted: the authorization chain **Authentication → Role/Permission → Operation → Audit** (AR-009); authentication alone is not authorization (FD-016); the enforcement shape of *Proposed architecture* items 1, 4 and 5 (fail-closed, enumerable endpoint→roles map; blueprint-by-blueprint extension; denial recording); and that **Phase 2a remains frozen** and is extended, never bypassed or reopened.

Recorded, not implemented: **FD-015** — `list_folios` read access for Admin, Manager, Accountant and Front Desk; no other role; read-only; mutation endpoints unchanged. *This is a Founder-approved authorization decision and is not yet implemented*: `app/folio.py:47-52` still reads `('Admin','Manager')`.

Not adopted (implementation-level or deferred): HTML refusal shape, central vs per-blueprint map, Housekeeping scope (F13/MP-D6), operator profile (MP-D9).

**Authorization architecture adopted; route-by-route implementation remains future work.** From this point the ADR is append-only.

