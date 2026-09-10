# Phase 2a Authorization Matrix - re-run at `aa6d9e91`

Directive FG-P1-VERIFICATION-COMPLETION-20260909-01, section 6. Verification only; no authorization behaviour changed.

| | |
|---|---|
| Script | `verification/evidence/20260831_phase2a_folio_authz/verify.py`, copied **verbatim** to this directory as `phase2a_verify.py` so its `result.json` lands here (`phase2a_result.json`) instead of overwriting the 2026-08-31 evidence |
| Run | 2026-09-09 21:27:50-21:27:51 IST, `venv\Scripts\python.exe`, disposable copy `phase2a_authz.db` (sqlite-backup-api) |
| Result | **29 / 29 cases passed - VERDICT PASS** |
| Production | sha256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` before and after - READ-ONLY VERIFIED |
| Expected | the established Phase 2a outcome (29/29, `20260831_phase2a_folio_authz/COMPLETION_REPORT.md` Gate B) - **unchanged** |

## Cases

| Group | Cases | Result at aa6d9e91 |
|---|---|---|
| Unauthorized roles refused on every folio endpoint (FrontDesk, Accountant, Housekeeping x list_folios, create_folio, transfer_charge, transfer_payment) | T01-T12 | 403 each, no data change |
| Unauthenticated refused | T13-T16 | 401 each |
| Authorized paths unchanged (Admin/Manager list; Manager transfer_charge / transfer_payment / create_folio) with audit rows written | T17-T23 | 200 / 200 / 200+audit / 200+audit / 201 |
| Denial recorded; fail-closed on an unmapped endpoint; guard commissioned (relaxed guard admits) | T24-T26 | as established |
| Audit coupling: audit failure -> rollback, HTTP 500 | T27 | 500 |
| NULL-source transfer tolerated | T28 | 200 |
| D11 freeze by identity: payments [1..6], charges [1,2] unattributed before and after | T29 | identical |

`_FOLIO_ROLES` at `aa6d9e91` is byte-identical to Phase 2a (`app/folio.py` unchanged since `237db2ad`); FD-015 (`list_folios` read scope for Accountant/FrontDesk) remains approved and **not implemented** - T01/T02 still expect and get 403, which is the correct current-code outcome and is unchanged by this directive.

Full output: `phase2a_matrix.txt`; machine-readable: `phase2a_result.json`.
