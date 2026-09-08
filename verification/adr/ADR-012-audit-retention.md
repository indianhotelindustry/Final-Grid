# ADR-012 — Audit Retention

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-008 (audit history must not be automatically deleted), FD-009 (unattended scheduler) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. **The pruning job is unchanged. No audit row was modified.** |

## Context

- `_prune_old_logs` — `app/__init__.py:547-566` — registered as `log_pruning_job`, cron daily 04:00, `misfire_grace_time=3600`. It executes `LogModel.query.filter(ts_col < cutoff).delete()` for `AuditLog` (`timestamp`), `WebhookLog` (`received_at`) and `NotificationLog` (`sent_at`) with `cutoff = utcnow − 90 days`, then commits.
- `audit_logs` at drafting: 23 rows, oldest `2026-08-09 12:16:14`, newest `2026-08-30 06:20:10`; **0 rows currently older than 90 days**. First deletion would occur on or about **2026-11-07** if the application is running on that date.
- The job starts with `create_app()` and has no configuration switch (only `night_audit_enabled` gates a job, and it gates a different one).
- Constitution: P7 *closed periods are append-only*, P12 *historical immutability*, P14 *every financial object has provenance* — all invariant-enforced principles. No registered invariant currently detects audit-row loss.
- Phase 2a evidence relies on `audit_logs` (`folio_create`, `folio_charge_transfer`, `folio_payment_transfer`, `folio_access_denied`); the D11-F2 provenance rests on `audit_logs` content.
- `AuditLog` has no archival flag, no partition, no export.

## Decision (as ruled by FD-008)

Audit history must not be automatically deleted until a formally
designed archival/retention mechanism has been approved and implemented.

## Proposed architecture

1. **Immediate (separate bounded directive, not this ADR):** remove `AuditLog` from the pruning loop, leaving `WebhookLog` and `NotificationLog` behaviour as-is — the smallest change that makes the running system comply with FD-008. Zero schema, zero data impact.
2. **Retention classes:** FINANCIAL-PROVENANCE audit rows (entity types touching payments, charges, folios, night audit, shifts, invoices, GST) — **permanent**; OPERATIONAL audit rows — retention period **UNRESOLVED**; `webhook_logs` / `notification_logs` — technical logs, 90 days acceptable pending Founder confirmation.
3. **Archival before any deletion:** export to an append-only, hash-chained archive file under the backup store, with the archive's hash recorded, before any row leaves `audit_logs`. Deletion of archived rows is itself a production mutation under PD-004.
4. **Detection control:** register an invariant that the minimum `audit_logs.timestamp` never advances (or that a count/hash ledger of archived rows reconciles), so audit loss is *capable of failing* (P9) — new registration under CONSTITUTION §4, **UNRESOLVED**.
5. **Scheduler governance (FD-009):** the pruning job is a financially material mutation path for FINANCIAL-PROVENANCE rows and must meet the same controls as an operator action; until then it must not touch them.

## Unresolved

Retention period for OPERATIONAL rows · archive format and custody ·
whether archival deletion is ever permitted for financial provenance ·
the detection invariant · whether the fix is a Phase 0 bounded exemption
(as FD-017 is for launchers) or Phase 4 work — **Founder decision**.

## Implementation boundary

None authorized. Time-bound note: FD-008 becomes actively violated by the
running system on or about 2026-11-07 unless an implementation directive
precedes it.
