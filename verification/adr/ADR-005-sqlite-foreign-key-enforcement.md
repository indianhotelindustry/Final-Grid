# ADR-005 — SQLite Foreign-Key Enforcement

| | |
|---|---|
| Status | **DRAFT** — not adopted; **enable/defer UNRESOLVED** |
| Founder decision | Context: FD-003, FD-011. No Founder decision yet addresses FK enforcement directly; MP-D4 (SQLite as system of record) is OPEN. |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. FK enforcement is not enabled. |

## Context

- SQLite defaults `PRAGMA foreign_keys = OFF` per connection. The application never issues `PRAGMA foreign_keys = ON` (exhaustive search of `app/`, 2026-09-08).
- `tools/production_initialize.py:296` and `verification/datasets/builder.py:68` set it OFF explicitly for bulk operations.
- `verification/invariants/rules_c.py:283` reports it as off; `verification/faults/faults_b.py:6` records a fault the pragma is "supposed to prevent and does not".
- **Why it is off:** NOT DEFINED IN REPOSITORY — no comment or record explains it; the evidence is consistent with inheritance of the SQLite default rather than a decision.
- Live file: `journal_mode = delete`; `INV-C03` (every financial event belongs to a reservation that exists) HOLDS on production, so no financial-row orphans exist today. Orphans in the other 50 tables: NOT VERIFIED.
- Declarative FKs affected include `payments.folio_id`, `extra_charges.folio_id`, `*.reservation_id`, `folios.reservation_id`, `audit_logs.staff_user_id`.

## Implications

| For | Implication |
|---|---|
| `Payment.folio_id`, `ExtraCharge.folio_id` | FK is declarative only; a dangling `folio_id` is caught by `INV-A03`/`INV-C03` on demand, not at write |
| Existing data | Enabling would not alter rows; it would make the *next* violating write fail |
| `after_insert` listener (`app/models.py:745`) | Inserts the folio inside the reservation's transaction — compatible with ON, but ordering must be proven |
| Dataset builders / initializer | Rely on OFF for strip/rebuild order; must keep setting OFF locally |
| Deletes | Cascade / restrict semantics become live; every delete path is affected |
| Rollback | Remove the pragma; no data change |

## Options — UNRESOLVED

| Option | Consequence |
|---|---|
| **E1 — Enable on every application connection** (SQLAlchemy `connect` event) | Referential integrity enforced at write; requires an orphan scan on a copy across all 53 tables, a full `ds-run` and `fault-run` under ON, and review of every delete path |
| **E2 — Enable for financial tables only** | SQLite pragma is connection-wide; not expressible — would require CHECK-style triggers instead |
| **E3 — Defer; rely on invariants** | Status quo; integrity remains on-demand and unbounded between runs (`WAVE1_BLUEPRINT.md` §8: no invariant runs without a human) |

Not chosen here. Depends on MP-D4 and on evidence (orphan scan) that does not yet exist.

## Prerequisites for any enabling directive

1. Orphan scan of all FK columns on a `make_copy()` copy — recorded.
2. `ds-run`, `fault-run`, `inv-run` under ON — recorded.
3. Migration implication: none to schema (connection pragma).
4. Test implication: every fixture and dataset re-run under ON.
5. Rollback: documented pragma removal.

## Implementation boundary

None authorized.
