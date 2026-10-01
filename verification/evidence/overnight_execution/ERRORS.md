# ERRORS — FG-OVERNIGHT-01

Every error, failure or denial, classified (NEW / PRE-EXISTING / EXPECTED / ENVIRONMENTAL / TEST DEFECT / GOVERNANCE BLOCK / UNKNOWN). Nothing is hidden or deleted; corrections are appended.

| # | Time (IST) | Activity | What happened | Class | Effect | Disposition |
|---|---|---|---|---|---|---|
| E-01 | 2026-10-02 ~00:55 | SR-1 analysis: read-only `SELECT` of production `payments` (purpose/flags/dates) via `sqlite3 mode=ro` | Denied by the session permission classifier before execution | GOVERNANCE BLOCK (tooling) | none — command did not run; production hash checked before and after other reads: `21dc0e97…` | Not retried, not worked around. Production facts for SR-1 are taken from committed evidence (`20261001_120800_inv_commission`, 6 payments HOLDS) and the 2026-09-30 analysis. Earlier read-only reads of `business_date`, `settings` and `schema_migrations` were permitted and ran. |

## Pre-existing failures carried into the night (not new; from committed evidence)

| Item | Source | Class |
|---|---|---|
| `inv-commission` 27/28 — INV-R01 FAIL (declared NOT_COMMISSIONED, `rules_r.py:87`) | `20261001_120800_inv_commission/report.txt:300`; `20260930_sr2_inv_d02/INV_D02_IMPLEMENTATION_REPORT.md:62` | PRE-EXISTING |
| `fault-run` FAIL — FLT-C07 missed, 4 uncovered | `20260930_sr2_inv_d02/REVISION_2_REPORT.md:34` | PRE-EXISTING |
| `gm-verify phase1_aa6d9e91` WARN 156/158 — `/auth/users` (`last_login`), `/rates/notification-logs` (+3) | `20260930_sr2_inv_d02/INV_D02_IMPLEMENTATION_REPORT.md:75` | PRE-EXISTING (operational data movement, not re-baselined) |
