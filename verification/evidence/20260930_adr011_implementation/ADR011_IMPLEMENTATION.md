# ADR011-SA — implementation (branch `adr011-system-actor`, commit `3ffeba5`)

| | |
|---|---|
| Branch base | `16c4ca8` (`main`; Founder decision recorded) |
| Code commit | `3ffeba5` — 10 files, +335 / −32 |
| Worktree | `C:\wt_adr011` (outside the production working tree; `main`'s working tree was never switched) |
| Production | `instance/pms.db` `51dd83b7…30bc2`, 733,184 B, mtime 2026-08-31 11:53:14 — never opened for writing; SHA-256 checked in every result file |
| Status | **Implemented and verified on the branch. Not merged. Not applied to production.** |

## Files

| File | Change |
|---|---|
| `app/audit_actor.py` (new) | `AuditActor`, `resolve()`, `system_action()` context manager, `AuditActorError` |
| `app/models.py` | `AuditLog`: `staff_user_id` nullable; `actor_kind`, `actor_mechanism`, `actor_role`, `actor_shift_id`; three CHECKs; `before_insert` listener that resolves unknown/0 actors (or refuses) and snapshots role and open shift for HUMAN rows |
| `app/__init__.py` | migration `10.0.0` `_migrate_audit_actor_kind`, run by `_run_pending_migrations` before the SQLite column fixer; raises on failure so the application does not boot on a half-migrated audit table |
| `app/services.py` | `resolve_audit_actor` returns an `AuditActor`; `audited_financial_write` writes kind and mechanism and turns an unknown actor into `AuditCouplingError`; `scheduled_night_audit()` is the `night_audit_job` entry point under `system_action('scheduler:night_audit_job')` |
| `app/noshow_service.py`, `app/cico_service.py` | the Reservation-level rows carry the resolved kind and mechanism |
| `app/webhook.py` | SYSTEM, `webhook`, no user (was 0) |
| `app/routes.py` | `_write_audit`: no user ⇒ None (listener resolves), never 0 |
| `app/services_group_stay.py` | `_resolve_actor` fallback None, never 0 |
| `app/dev_seed.py` | reset without admin ⇒ SYSTEM `dev_seed` |

## Migration behaviour (group `mig`, fresh subprocess per boot)

| Case | Result |
|---|---|
| M-01..M-04 production copy | boots; 23 rows carried over with identical count and digest of all nine pre-existing columns (`1cf41807b7639e55…`); new shape (nullable `staff_user_id`, 4 actor columns, 3 CHECKs, index); all rows HUMAN; `10.0.0` recorded; `integrity_check` ok; FK check clean |
| M-05 | `night_audit_job` not registered after boot (production setting false) |
| M-06 | second boot: no change (idempotent) |
| M-07 | a copy with a history row naming user 0: boot **refused**, table byte-identical, migration not recorded, no leftover rebuild table |
| M-08 | empty database: models create the new shape; `10.0.0` recorded |

## Directive §10 classes on the branch (group `sys`, `human`)

| Writer | GREEN | RED (F1/F2) | FK-RED (invalid actor) | other RED | HUMAN |
|---|---|---|---|---|---|
| scheduler night audit (`scheduled_night_audit`) | completes with FK **on** and off; room rent, fee and `noshow_posted` rows are SYSTEM, no user, `scheduler:night_audit_job`; `run_by_user_id` and `NoShowLog.posted_by_user_id` empty | 4/4 whole run rolled back | FK on, actor 999999: FK failure, run rolled back | forced 0: CHECK `ck_audit_actor_not_zero` rejects, rolled back (FK off); undeclared no-operator call: refused, rolled back | manual `POST /night-audit/run`, FK on and off: every row HUMAN, the operator, role `Admin`, the operator's open shift, `web`; `run_by_user_id` set |
| automated no-show | completes FK on and off; fee + `noshow_posted` SYSTEM, no user | 2/2 nothing persisted | FK on, invalid actor: nothing persisted | undeclared: refused, nothing persisted | manual no-show FK on: HUMAN, operator, `Admin`, no open shift |
| webhook `modify_booking` | completes FK on (previously could not) and off; SYSTEM, no user, `webhook` | (non-strict writer unchanged — out of scope) | — | — | — |
| unauthenticated `_write_audit` | SYSTEM, `web:unauthenticated` | — | — | — | — |
| raw SQL around the application | — | — | — | user 0, HUMAN without user, SYSTEM without mechanism, SYSTEM with a user: all four rejected by CHECK | — |

Provenance (directive §8), answered from the row alone for a scheduler room-rent row and a manual one: what, when, which entity, which amount, why (`flow`, `night_audit_log_id`), **human or system** (`actor_kind` SYSTEM vs HUMAN) and **execution path** (`scheduler:night_audit_job` vs `web`) and business date — 8/8. The two questions the old model could not answer are now answered.

Result: `results_3ffeba5.json` — **42/42 gates PASS**, application commit `3ffeba5`, `app/` clean.

## Test history (not hidden)

The first runs of the new harness failed four gates, all test defects, corrected before the committed run:

- S1-RED-FK: error text truncated at 110 characters cut off "FOREIGN KEY" (widened to 300);
- H-NA-FK and the `prov` group: the manual-run fixture opens a shift, which is a night-audit blocker, so the first run left the day Pending and later runs of that date were correctly skipped as idempotent; the harness now advances the copy's business date between runs;
- P-why / P-business_date: the first row of a run is the no-show fee (`flow noshow_fee`), not room rent; the harness now selects the room-rent row.

## Behaviour changes (deliberate, from the ruling)

1. An unattended night audit or automated no-show that does not declare a mechanism is **refused** (rolled back) instead of writing actor 0. The only production unattended entry point, `night_audit_job`, declares it; the job remains disabled.
2. Audit rows of operator actions now also carry `actor_role`, `actor_shift_id`, `actor_mechanism`.
3. A database whose history contains a row naming no real user will not boot this code until that history is dispositioned (production: none).

## Preconditions before merge / production (not authorized here)

- Founder authorization to merge to `main` knowing the migration then runs at the next application start from the production working tree (the inline registry is unattended; B-4 undecided);
- PD-005 / PD-006: a verified-state backup of `instance/pms.db` immediately before first start, and a restore rehearsal proving the migrated file;
- PostgreSQL verification if PostgreSQL is a target (not executed; see `ADR011_REGRESSION.md`).
