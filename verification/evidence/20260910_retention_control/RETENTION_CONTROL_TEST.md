# Retention Control — Test and Regression Record

## 1. Focused test — `verify_retention.py` (this directory)

Method: `verification.dbcopy.make_copy()` copy of production (`retention_control.db`, backup API); application booted against the copy (`DATABASE_URL`), `TESTING=True`; the real job obtained from the module scheduler (`app.services.scheduler.get_job('log_pruning_job')`) and its function called once; fixtures inserted on the copy only: one `audit_logs`, one `webhook_logs` and one `notification_logs` row timestamped 100 days ago and one of each timestamped now. Output: `retention_test.txt`, `retention_test_result.json`.

| Case | What | Result |
|---|---|---|
| RC-01 | `log_pruning_job` registered (jobs: `daily_backup_job`, `log_pruning_job`, `notification_queue_flush`, `predictive_maintenance_job`) | PASS |
| RC-02 | trigger unchanged: cron hour 4, minute 0 | PASS |
| RC-03 | `misfire_grace_time` 3600 unchanged | PASS |
| RC-04 | job function is the `_prune_old_logs` closure | PASS |
| RC-05 | job executes without raising | PASS |
| **RC-06** | **`audit_logs` row older than 90 days survives the prune** | **PASS** |
| RC-07 | `audit_logs` count unchanged by the run (25 → 25) | PASS |
| RC-08 | `MIN(audit_logs.timestamp)` did not advance | PASS |
| RC-09 | old webhook row still pruned | PASS |
| RC-10 | old notification row still pruned | PASS |
| RC-11 | recent rows in all three tables survive | PASS |
| RC-12 | webhook / notification counts each dropped by exactly one (2→1, 7→6) | PASS |
| RC-13 | unrelated audit behaviour unchanged: `add_payment` still writes its strict-coupled `posted` row (HTTP 200) | PASS |
| **RC-N1** | **negative control**: the pre-change loop (re-created in the test, including `AuditLog`) deletes the same old audit row — 1 row, alive → gone | **PASS** (proves RC-06 can fail) |
| D11-01/02 | D11 id sets and amounts unchanged on the copy | PASS |
| PROD-01/02 | production hash and size unchanged | PASS |

**18 / 18 passed.** Application boot: 298 routes (baseline 298).

Two defects in the test script itself were found and fixed during the run (a detached ORM instance used outside the app context; tuple keys in the result JSON); neither touched the application. The final run is clean.

## 2. Existing audit-log tests

The Phase 2a authorization matrix (`phase2a_verify.py`, verbatim copy of the 2026-08-31 script; output `phase2a_matrix.txt`, `phase2a_result.json`): **29 / 29 PASS**, including T20/T22 (audit row written on transfers) and T27 (audit failure → rollback, HTTP 500). Production read-only verified. There is no other audit-log test in the repository (no `tests/` directory; `tools/test_restore_db.py` is unrelated).

## 3. Regression — Golden Master

`python -m verification gm-verify --tag phase1_aa6d9e91 --quiet` → **158 / 158 clean, 0 differences, 0 blocking, PASS**, read-only verified. Pack `20260910_064223_gm_verify_phase1_aa6d9e91`. Output `gm_verify_phase1_aa6d9e91.txt`.

## 4. Regression — replay

`python -m verification replay-verify --tag production --quiet` → **10 / 10 dates clean, 0 differences, PASS**, read-only verified. Pack `20260910_064244_replay_verify_production`. Output `replay_verify.txt`.

## 5. Regression — invariants

`python -m verification inv-run --tag production --quiet` → 26 registered · 17 HOLDS · 7 VACUOUS · 2 VIOLATED (INV-A02 8/8 ₹4,776.19, INV-A03 ₹476.19 — the D11 exception) · INV-R01 NOT_COMMISSIONED · overall FAIL by design; read-only, repeatable and order-independent all VERIFIED. **SUMMARY block byte-identical to the Phase 1 baseline pack `20260909_013500_inv_run_production`.** Output `inv_run.txt`; pack named in `RESULT.json`.

## 6. Production anchor

Read-only scratch-copy gate before the first action and after the last: SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, 733,184 B, D11 payments 1–6 / charges 1–2 = ₹4,776.19, `audit_logs` 23, 144 schema objects, fingerprint unchanged, integrity ok, no WAL/SHM/journal sidecars. Every harness run and the focused test additionally re-hashed production themselves.

## 7. Verdict

Focused test PASS, existing audit tests PASS, Golden Master PASS, replay PASS, invariants unchanged, boot unchanged, production untouched. No stop condition was met.
