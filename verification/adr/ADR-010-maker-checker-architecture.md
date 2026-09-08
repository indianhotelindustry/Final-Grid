# ADR-010 — Maker-Checker Architecture

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-016, FD-014; context FD-011 |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. |

## Context — three approval models exist, none aligned with the others

| Model | Where | Shape | Status |
|---|---|---|---|
| Void / refund | `app/payment_void_service.py` (`can_request_void`, `can_approve_void` → Admin/Manager; `void_requests`; time windows; append-only reversals) | Request → approve/reject; direct void for privileged roles | **Preserved strength** (Register N2). Must survive unchanged. |
| Shift close | `app/shift_service.py` (`close_shift` → `PendingApproval` when variance exceeds threshold; `approve_shift_close`; `approval_status` auto/pending/approved/override) | Maker closes; checker approves above threshold | Live |
| Folio mutation | `app/folio.py` `_FOLIO_ROLES` — mutating endpoints Admin/Manager, chosen to match `can_approve_void` so Phase 2b can add an approval step to the same boundary | Single-actor with audit | Phase 2a — frozen; Phase 2b adds approval |

Also: night-audit override (`override_used`, `override_reason` — one live record carries the reason "cvnvhm"), reopen (`night_audit_reopen_logs`, 5 rows with reasons "testing", "test", "dfhd"); credit-limit override at checkout (Register N1). Reason quality is unenforced.

## Decision (derived from FD-016 / FD-014)

Sensitive financial mutations require an identifiable maker and, where
the action is irreversible or crosses a materiality threshold, an
identifiable checker distinct from the maker; both identities, roles,
timestamps, business date and IP provenance are recorded (FD-014).

## Proposed architecture

1. **Define "sensitive financial mutation"** as data: initially `create_folio`, `transfer_charge`, `transfer_payment`, any future folio close, billing-responsibility change, void/refund (already), shift close above threshold (already), night-audit override and reopen.
2. **One request/approve lifecycle** shape reused across models: request row (maker, target, before/after, reason) → approval row (checker ≠ maker, decision, reason) → execution; `AuditLog` rows on each transition, coupled to the transaction as Phase 2a does (audit failure rolls back).
3. **Reason quality:** minimum length / non-placeholder validation — **UNRESOLVED** whether to enforce.
4. **Maker ≠ checker enforcement** — the void model permits `direct_void` for privileged roles; whether Admin may self-approve anywhere is **UNRESOLVED** (MP-D9-dependent: a one-person hotel has no second approver).
5. **Existing void/refund control is not modified**; it is the reference implementation.

## Unresolved

Materiality thresholds · self-approval policy for single-operator
properties · whether shift and folio approvals converge on one table or
stay separate · reason validation · MP-D9.

## Implementation boundary

None authorized. Master Plan Phase 2b.
