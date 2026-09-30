# ADR011-SA — the decision and how it was read

Source: `verification/FOUNDER_DECISIONS.md`, Founder Resolution Round 5 (`FG-P2-FOUNDER-RESOLUTION-20260930-01`, commit `16c4ca8` on `main`), recorded verbatim.

Delivery (Founder answer in session, 2026-09-30): **branch only**. Implement and verify on a separate branch in an isolated worktree on disposable copies; `main` is not touched. Merging to `main`, and applying the migration to production, are separate authorizations.

| Clause of the ruling | Implementation |
|---|---|
| distinguish a human actor from a system actor at the audit/provenance layer | `audit_logs.actor_kind` ∈ {`HUMAN`, `SYSTEM`}, NOT NULL, CHECK `ck_audit_actor_kind` |
| system actions shall not impersonate a human user | a SYSTEM row carries no user: CHECK `ck_audit_actor_identity` (SYSTEM ⇒ `staff_user_id IS NULL`) |
| shall not use a fabricated `users.id = 0` | CHECK `ck_audit_actor_not_zero`; every code path that wrote 0 now resolves a real actor or refuses |
| audit_logs shall explicitly represent the actor kind | `actor_kind` column |
| … execution mechanism | `actor_mechanism` (`web`, `service`, `scheduler:night_audit_job`, `webhook`, `web:unauthenticated`, `dev_seed`); SYSTEM ⇒ NOT NULL (CHECK) |
| … relevant operator role/shift where applicable | `actor_role` (snapshot of `users.role`) and `actor_shift_id` (the operator's open shift, FK `shifts`) on HUMAN rows; empty on SYSTEM rows and on pre-existing rows (not reconstructed: that would be writing history, not recording it) |
| human audit records shall continue referencing the authenticated user | HUMAN ⇒ `staff_user_id` NOT NULL, FK `users` (CHECK) |
| system audit records shall not require a fabricated human users row to satisfy the FK | `staff_user_id` nullable; no `users` row is created |
| scheduler activation remains a separate authorization | the `night_audit_job` registration is still gated only by `night_audit_enabled` (production `false`); only the job's entry point changed so that it declares its mechanism |

Readings made where the ruling is silent (bounded, recorded here for review):

1. **Unknown actor ⇒ refuse, never label.** A no-operator path that has not declared a mechanism is refused (the audit row, and for strict writers the whole financial transaction, fails) rather than recorded as SYSTEM with a guessed mechanism. This follows FD-009 (no uncontrolled unattended financial writer) and Q5-P1.
2. **Unauthenticated web request ⇒ SYSTEM `web:unauthenticated`.** Only public routes can produce it; it is not a human identity.
3. **History is carried, not reclassified.** All existing rows become `HUMAN` unchanged. The migration refuses if any existing row names no real user (NULL, 0 or missing); on production there are none (all 23 rows are user 1). Reclassifying such rows elsewhere would be a Founder decision.
4. **Role/shift snapshot at insert time** from `users.role` and the operator's `Open` shift; nothing is snapshotted for SYSTEM rows.
