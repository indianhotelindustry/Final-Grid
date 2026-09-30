# ADR-011 system-action provenance — analysis

The full pre-decision analysis is on `main`: `verification/evidence/20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md` (commit `cfec0c8`). Its characterisation of the old model (`characterisation_3efdd2b.json`, 23/23) established:

- system/unattended audit rows used `staff_user_id = 0`; no user 0 exists; `audit_logs.staff_user_id` was NOT NULL FK `users`;
- under FK enforcement every unattended financial path failed closed and could not complete; webhook modifications could not complete;
- a row did not say whether a human or the system acted, nor whether the scheduler or an operator ran the night audit.

Paths that wrote an audit row without an authenticated human, and what each does on this branch:

| Path | Old | Branch |
|---|---|---|
| scheduler `night_audit_job` (room rent, no-show fee, `noshow_posted`) | actor 0 | SYSTEM, `scheduler:night_audit_job`, no user |
| `run_night_audit` called with no operator and no declared mechanism | actor 0 | refused; run rolls back |
| automated no-show outside a declared mechanism | actor 0 | refused; nothing persisted |
| `webhook._write_audit` (`modify_booking`) | hard-coded 0 | SYSTEM, `webhook`, no user |
| `routes._write_audit`, unauthenticated request | 0 | SYSTEM, `web:unauthenticated` |
| `services_group_stay._resolve_actor` without operator | 0 | no user → resolved by the insert listener (declared mechanism or refusal) |
| `dev_seed` reset without an admin | 0 | SYSTEM, `dev_seed` |
| every operator path | user id | HUMAN, user id, `actor_role`, `actor_shift_id`, mechanism `web`/`service` |

Out of scope and unchanged (recorded in the decision package, still open): webhook `modify_booking` audit remains non-strict (F1 still commits an unaudited rate change); webhook `new_booking` / `cancel_booking` still write no AuditLog.
