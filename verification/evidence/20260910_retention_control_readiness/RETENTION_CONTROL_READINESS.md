# Retention-Control Implementation Readiness (FD-P2-02) — read-only inspection

| | |
|---|---|
| Prepared | 2026-09-10, after governance checkpoint `805ee0d9cc6730255288b74fab61ba31c13940f7` |
| Authority | FD-P2-02 (Founder Resolution Round 3): stop destructive audit-log pruning until an archival design is adopted; other non-audit log retention unchanged; authorizes a **later** bounded retention-control implementation. FD-008, AR-007, ADR-012 item 1 |
| Scope of this report | inspection and planning only — **no code, schema, data, scheduler or production change** |
| Repository inspected | `app/`, `tools/`, `installer/`, root scripts, `migrations/`, `verification/` (harness), at `805ee0d9` |
| Production anchor | `51dd83b7…30bc2`, 733,184 B, D11 unchanged, `audit_logs` 23 — verified before and after the governance commit |

## 1. Every path that can remove `audit_logs` rows

| # | Path | Kind | Trigger | Tables affected | Deletes `audit_logs`? | Governance |
|---|---|---|---|---|---|---|
| P-1 | `app/__init__.py:547-566` `_prune_old_logs` → registered at `:568-572` as APScheduler job `log_pruning_job`, cron **04:00 daily**, `misfire_grace_time=3600`, `replace_existing=True`; created inside `create_app()`; **no settings switch** | automatic, unattended | scheduler started by every `create_app()` (web, launchers, updater restart, and in-process harness boots) | `audit_logs` (`timestamp < now-90d`), `webhook_logs` (`received_at`), `notification_logs` (`sent_at`) via `LogModel.query.filter(ts_col < cutoff).delete()` then one `commit()` | **YES — directly, automatically.** Present since baseline `b5b2514` (2026-08-07). First eligible row on a running instance ≈ 2026-11-07 (oldest row 2026-08-09) | **the FD-P2-02 target** |
| P-2 | `reset_transactional_data.py` (project root) — `TRANSACTIONAL_TABLES_IN_DELETE_ORDER` includes `audit_logs` (line 117) and `night_audit_logs` (122); `_execute_delete` issues `DELETE FROM <table>` for every listed table (`:296-318`); exposed through `app/admin_reset.py` (`/execute`, Admin-only decorator, typed confirmation phrase) | deliberate operator action (full transactional reset / re-initialisation) | Admin POST with confirmation phrase, or CLI | all transactional tables incl. `audit_logs` | **YES — directly, wholesale, but only by explicit Admin action** | a production mutation: governed by PD-004 / FD-007 / FD-019, **not** by retention policy. Outside FD-P2-02 scope; recorded for Founder attention (§8) |
| P-3 | `tools/production_initialize.py` — `DELETE FROM "{table}"` for every table of a *cleared* class per `initialization_classification.py` (`:299`); dry-run default, pre-run snapshot, hash and row-count verification, boot check | deliberate commissioning tool (CLI) | operator CLI run without `--dry-run` | cleared classes (transactional, incl. audit rows per classification) | **YES — by design of a commissioning reset** | same as P-2 (PD-004 territory; its authorization is "NOT DEFINED IN REPOSITORY" per ADR-006). Outside FD-P2-02 scope |
| P-4 | Alembic revisions `c4d5e6f7a8b9_add_hot_path_indexes.py`, `e6f7a8b9c0d1_backfill_reservation_rooms.py` reference `audit_logs` | migration artefacts | none — Alembic has no caller and no `alembic_version` table (R2) | index creation / row insertion | **NO** (no `drop_table`, no delete) | — |
| P-5 | Inline migration registry (`app/__init__.py` `_run_pending_migrations`) | boot-time migration | every `create_app()` | `night_audit_logs` column adds only | **NO** | — |
| P-6 | ORM cascades — `Reservation.passengers` and `ReservationRoom.reservation` backrefs carry `cascade='all, delete-orphan'` (`models.py:473`, `:577`); `AuditLog.staff_user_id → users.id` has no `ondelete`; no `relationship('AuditLog', cascade=…)` anywhere; no user-deletion route found | indirect | — | not `audit_logs` | **NO** | — |
| P-7 | `tools/test_restore_db.py:223` `DROP TABLE audit_logs` | unit-test fixture on a scratch database it creates | test run | scratch file only | **NO production path** | — |
| P-8 | `db.create_all()` (`app/__init__.py:452-481`) | schema bootstrap, gated off in production | — | creates missing tables only | **NO** (never drops) | — |
| P-9 | Verification harness (`inv-run`, `gm-*`, `verify.py` scripts) boot the application in-process, so `log_pruning_job` is scheduled inside those processes too | incidental | a harness process alive at 04:00 | the **copy** the harness is bound to (`DATABASE_URL` → `verification/_work/*.db`); never `instance/pms.db` (SC-1/SC-2; every pack re-hashes production) | not production | note only |

**Conclusion:** `audit_logs` is deleted **directly and automatically by exactly one path, P-1**. Two further paths (P-2, P-3) delete it only as part of an explicit, confirmed, wholesale reset — they are production-mutation tools, not retention, and are governed by PD-004. No cascade, migration, updater or installer path deletes audit rows.

## 2. Current behaviour of P-1, precisely

- Runs inside `create_app()` for **every** application process, with no configuration switch (the only job-level switch in the application, `night_audit_enabled`, gates a different job).
- Deletes in one transaction across three models; on any exception rolls back all three and logs an error — so a failure in webhook pruning also protects audit rows, and vice versa.
- Retention window: 90 days on `AuditLog.timestamp` (UTC, `default=datetime.utcnow`).
- Production today: 23 rows, oldest 2026-08-09 12:16 UTC, newest 2026-08-30; **0 rows currently eligible**; first eligible ≈ 2026-11-07 04:00 on any running instance.
- Measured payload ≈153 bytes per row; a property writing 500 rows/day would add ≈27 MB/year. Storage is not a justification for pruning.

## 3. Tests currently covering this behaviour

**None.** There is no `tests/` directory; the only unittest module is `tools/test_restore_db.py` (restore tool). No `verify.py` under `verification/evidence/` exercises `_prune_old_logs`. No registered invariant detects loss of audit rows (the invariants that touch audit tables — INV-B02, INV-B05 — concern `night_audit_logs`). The fault registry has no fault for audit-row deletion. The behaviour is therefore unobserved by every existing control (ADR-012 context; P9 "a control that cannot fail").

## 4. Smallest safe implementation boundary required by FD-P2-02

**Proposed minimal change (not implemented):** in `app/__init__.py :: _prune_old_logs`, remove the `(AuditLog, AuditLog.timestamp)` entry from the model list and drop `AuditLog` from the local import; leave `WebhookLog` and `NotificationLog` pruning, the 90-day window, the job id, schedule, `misfire_grace_time`, the log message and the error handling exactly as they are. Roughly three lines within one function.

| Alternative considered | Why rejected |
|---|---|
| Add a settings switch / configurable `audit_log_retention_days` | creates a second policy surface and a way to re-enable deletion; FD-P2-02 says audit records *must not* be destructively deleted until an archival design is adopted — a switch is not a design |
| Remove the whole `log_pruning_job` | changes non-audit log retention, which FD-P2-02 explicitly leaves unchanged |
| Archive-then-delete now | that is the ADR-012 design FD-P2-02 defers |
| Touch `reset_transactional_data.py` / `production_initialize.py` | different governance (PD-004), different risk; would be scope creep and would blur the ruling |

## 5. Regression risks

| Risk | Assessment |
|---|---|
| Financial figures, invariants, replay, night audit | none — `audit_logs` is read by no canonical engine; the change deletes fewer rows, never more |
| Golden Master (`phase1_aa6d9e91`) | no surface renders pruned-vs-unpruned audit rows at the frozen date; `webhook.webhook_logs` and `rates.notification_logs` surfaces are unaffected because their pruning is unchanged; expected 0 differences |
| Scheduler | job id and schedule unchanged; the other four jobs untouched; boot route count expected 298 |
| Storage growth | negligible (§2) |
| Edit locality | `app/__init__.py` is a large boot module (`create_app`, migration registry); the diff must be confined to lines 547-566 and verified by `git diff` line count |
| Phase 2a / authorization | untouched |
| Behaviour on an instance that already pruned | rows already deleted are gone; the fix only stops future deletion (see §7) |

## 6. Verification plan (for the implementation directive)

1. **Static:** `git diff` limited to `_prune_old_logs`; no other hunk in `app/__init__.py`; no other file.
2. **Copy test (Phase 1 idiom, `make_copy()`):** insert into the copy one `AuditLog`, one `WebhookLog` and one `NotificationLog` row timestamped 100 days ago plus one of each timestamped today; obtain the job callable via `app.apscheduler`/`_sched.get_job('log_pruning_job').func` (or call the function through the scheduler's job store) and run it once; assert: old `AuditLog` row **survives**, old webhook and notification rows are **deleted**, today's rows survive, `audit_logs` count unchanged by the run. Negative control (P9): run the *pre-change* function on a copy and show the old audit row is deleted — proving the test can fail.
3. **Boot:** `create_app()` on a copy → 298 routes; scheduler job ids identical to baseline (`notification_queue_flush`, `log_pruning_job`, `predictive_maintenance_job`, backup jobs; `night_audit_job` absent because disabled).
4. **Regression:** `gm-verify --tag phase1_aa6d9e91` → 158/158; `replay-verify` → 10/10; `inv-run --tag production` → summary identical to the baseline pack; Phase 2a matrix optional (no authorization change).
5. **Production safety:** anchor hash/size/D11/audit_logs=23 before and after; the copy only is mutated.
6. **Evidence:** pack under `verification/evidence/<stamp>_retention_control/` (verify script, result.json, diff, gm/replay/inv packs); one commit citing FD-P2-02; K-10 recorded as CLOSED-BY-IMPLEMENTATION in the next known-defects update; ADR-012 reconciliation at its next review.
7. **Later (Phase 6, not this directive):** register a detection invariant that `MIN(audit_logs.timestamp)` never advances (ADR-012 item 4), so the control can fail.

## 7. Production-safety considerations

- The change is code-only; it takes effect on a running instance only when that instance is **deployed** with the fix (CF-9). Until then the exposure date (~2026-11-07) stands for any instance actually running. The deployment rehearsal (G11) should include a check on the live database that `MIN(audit_logs.timestamp)` still equals the oldest expected row before and after the upgrade.
- No production mutation is involved in the implementation; the fix touches no row.
- Harness processes prune only their copies; irrelevant to production.
- P-2 and P-3 remain able to delete audit history wholesale by explicit Admin/CLI action; their use against `instance/pms.db` is a PD-004 matter (§8).

## 8. Items requiring Founder attention

1. **`reset_transactional_data.py` (via the Admin reset page) and `tools/production_initialize.py` can wipe `audit_logs` in one action.** They are commissioning tools, not retention, and FD-P2-02 does not cover them. Recommendation: record explicitly that neither may be run against `instance/pms.db` except under a PD-004 directive (ADR-006 already notes `production_initialize.py`'s authorization is undefined). No change proposed here.
2. **No control detects audit-row loss** today; the detection invariant (ADR-012 item 4) is recommended for Phase 6 so the retention rule is verifiable, not just implemented.
3. **The fix protects only instances that receive it** — release timing (CF-9) matters relative to 2026-11-07.

## 9. Carry-forwards — preserved

CF-5, CF-6, CF-9, CF-10, CF-11, SR-1, SR-2, schema/FK/NOT NULL, migration mechanism, recovery implementation, night-audit hardening, deployment rehearsal, final certification, Q06 divergence, W-20 hour — all unchanged and open. This report closes nothing.
