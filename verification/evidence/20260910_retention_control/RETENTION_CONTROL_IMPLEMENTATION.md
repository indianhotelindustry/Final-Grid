# Retention Control — Implementation Record (FD-P2-02)

| | |
|---|---|
| Authority | **FD-P2-02** (Founder Resolution Round 3): stop destructive audit-log pruning until an archival design is adopted; non-audit log retention unchanged; authorizes this bounded implementation only. FD-008, AR-007, ADR-012 item 1 |
| Governance checkpoint (parent) | `805ee0d9cc6730255288b74fab61ba31c13940f7` — "FinalGrid governance: record Founder Resolution Round 3" |
| Baseline for regression | Phase 1 baseline `aa6d9e91`; Golden Master `phase1_aa6d9e91`; invariant baseline pack `20260909_013500_inv_run_production` |
| Implemented | 2026-09-10 |
| Implementation commit | the single checkpoint commit that contains this directory (hash reported in the directive's final report; it cannot be embedded in a file the commit contains) |
| Readiness basis | `verification/evidence/20260910_retention_control_readiness/` — one automatic deletion path (P-1); the code was re-inspected before editing and matched the report line for line |

## 1. Exact behaviour changed

`app/__init__.py :: create_app() :: _prune_old_logs` (the closure registered as APScheduler job `log_pruning_job`, cron 04:00 daily, `misfire_grace_time=3600`) pruned three tables in one transaction: `audit_logs` (`AuditLog.timestamp < now − 90 d`), `webhook_logs` (`received_at`), `notification_logs` (`sent_at`).

**After this change it prunes two:** `webhook_logs` and `notification_logs`. **`audit_logs` is never deleted by the automatic pruning job.** Schedule, job id, grace time, the single-transaction commit, the rollback-on-error handling and the log messages are unchanged.

## 2. Exact files changed (application)

| File | Change | Lines |
|---|---|---|
| `app/__init__.py` | removed `AuditLog` from the local import inside `_prune_old_logs`; removed the `(AuditLog, AuditLog.timestamp)` entry from the model list | 1 insertion, 2 deletions; one hunk; no other reference to `AuditLog` existed in the module |

Byte-level verification: the working file differs from the parent commit in exactly three lines; line endings unchanged (LF, as at HEAD); the module parses; the application boots with **298 routes** (baseline 298) and the same four scheduler job ids (`daily_backup_job`, `log_pruning_job`, `notification_queue_flush`, `predictive_maintenance_job`; `night_audit_job` absent because `night_audit_enabled=false`, unchanged).

```diff
-                from app.models import db, AuditLog, WebhookLog, NotificationLog
+                from app.models import db, WebhookLog, NotificationLog
                 ...
                     for LogModel, ts_col in [
-                        (AuditLog, AuditLog.timestamp),
                         (WebhookLog, WebhookLog.received_at),
                         (NotificationLog, NotificationLog.sent_at),
```

## 3. What was deliberately not done (FD-P2-02 boundary)

No retention redesign · no archival · no configurable retention setting · the pruning job not removed · `reset_transactional_data.py` / `admin_reset` / `tools/production_initialize.py` untouched (PD-004 territory) · no schema change · no data change · no scheduler registration change · no change to any other module.

## 4. Confirmations

| Confirmation | Result |
|---|---|
| `audit_logs` automatic pruning disabled | **YES** — RC-06/07/08: a 100-day-old audit row survives a real run of the job; count and `MIN(timestamp)` unchanged |
| webhook / notification pruning remains active | **YES** — RC-09/10/12: 100-day-old rows in both tables deleted, counts each −1 |
| job still executes; identity unchanged | **YES** — RC-01..05 |
| unrelated audit behaviour unchanged | **YES** — RC-13 (strict coupling on `add_payment` still writes its row); Phase 2a matrix 29/29 incl. T20/T22/T27 audit cases |
| negative control | **YES** — RC-N1: the pre-change loop, re-created in the test, deletes the same old audit row (the assertion can fail) |
| no production mutation | **YES** — anchor `51dd83b7…` / 733,184 B / D11 / `audit_logs` 23 / schema fingerprint identical before and after every step; no sidecar files; every harness run `read-only VERIFIED` |
| no regression | **YES** — Golden Master 158/158, replay 10/10, `inv-run` summary identical to the Phase 1 baseline pack (section 5 of `RETENTION_CONTROL_TEST.md`) |

## 5. Limitations

1. The fix protects only instances that receive it; the pre-existing exposure (~2026-11-07 on a running instance) stands until deployment (CF-9). The deployment rehearsal should check `MIN(audit_logs.timestamp)` on the live database before and after the upgrade.
2. `audit_logs` will now grow without bound until the ADR-012 archival design is adopted — measured cost ≈153 bytes per row; not a constraint for a single property.
3. No invariant yet detects unexpected audit-row loss; recommended for Phase 6 (ADR-012 item 4).
4. The commissioning reset/initialisation tools can still delete `audit_logs` by explicit Admin/CLI action; they remain governed by PD-004 and were not touched.
5. K-10 ("destructive audit-log pruning scheduled") is closed by this implementation; the known-defects register text is historical evidence and is not rewritten — the closure is recorded here and in `RESULT.json`.

## 6. Carry-forwards preserved

CF-5, CF-6, CF-9, CF-10, CF-11, SR-1, SR-2, schema/FK/NOT NULL, migration mechanism, recovery implementation, night-audit hardening, deployment rehearsal, final certification, Q06 divergence, W-20 hour — all open and unchanged. Future controls preserved: commissioning reset/initialisation tools remain governed by PD-004; Phase 6 should add an invariant detecting unexpected audit-row loss.

## 7. Governance

No Founder decision modified. No ADR edited; no architectural contradiction was found (ADR-012's "immediate" item is exactly what was implemented, and its reconciliation is a documentation act for its next review). Nothing pushed.
