# ADR-008 — Application Authorization Architecture

| | |
|---|---|
| Status | **DRAFT** — not adopted |
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
