# DQ56-R1 — Q06-H1 sealed record guard: implementation and verification report

| | |
|---|---|
| Directive | Founder directive DQ56-R1, 2026-10-02 (recorded verbatim, `verification/FOUNDER_DECISIONS.md` Round 8, commit `9ddde22`) |
| Branch | `dq56-q06h1-guard` (local only — **not pushed, not merged**), worktree `C:/wq06h1`, base `c9eeff0` (= `origin/main`) |
| Code commit tested | **`46c4aab`** |
| Control | unchanged `c9eeff0`, worktree `C:/wq06h1base` (detached) |
| Environment | disposable copies only; the live `.env` never loaded; no outbound credentials; throwaway `SECRET_KEY`; in-process scheduler shut down at boot (DQ-56 harness) |
| Production | `instance/pms.db` SHA-256 `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434` **before, during and after every run**; never started; not modified |
| Outcome | **PASS** — all DQ-56 tests GREEN on `46c4aab`; regression identical to control apart from the two expected `/night-audit` UI differences. **Production application: NOT AUTHORIZED** (stopped at the boundary, §9) |

## 1. What was decided

DQ56-R1 says: protect **only** business date 2026-08-09; block Run and Reopen for that date; hide or disable those UI actions. It forbids any change to:
- the database or schema;
- general closed-day Run semantics or business-date logic;
- SR-1, K-7, or any other production behaviour.

The work runs on a copy only, with no push, merge or production change.

It resolves DQ-56b (R1) and DQ-56c (set = {2026-08-09}). DQ-56d is not adopted.

## 2. Change (`git diff --stat c9eeff0 46c4aab`)

```
 app/reports.py                         | 40 ++++++++++++++++++
 app/templates/night_audit_panel.html   | 18 +++++++--
 app/templates/reports/night_audit.html | 22 ++++++++--
 verification/FOUNDER_DECISIONS.md      | 20 +++++++++   (governance record, commit 9ddde22)
```

- **`app/reports.py`**
  - `Q06_H1_PROTECTED_AUDIT_DATES = frozenset({date(2026, 8, 9)})`: a constant, not a setting, so it cannot be changed from the UI.
  - `is_q06h1_protected_date()` accepts a `date`, a `datetime` or an ISO string. Anything else returns False.
  - The template global `q06h1_protected()`.
  - In `night_audit_run` and `night_audit_reopen`, a refusal (flash, then redirect to the panel) placed **after** the existing role check and date parse and **before** any computation, row lock or write. Role behaviour is unchanged: unauthorized roles still get 403.
- **Templates** — for the protected date only, these elements are not rendered:
  - every Run / Re-run form (action column, the hash-mismatch banner and the version-drift banner);
  - the Reopen buttons;
  - both `#reopenModal` dialogs.

  A note, "Sealed historical record (Founder ruling Q06-H1): Run and Reopen are disabled for this date", takes their place.
- **Not changed:**
  - `night_audit_complete`: it already refuses a `Completed` row, and it cannot be reached for 2026-08-09 without a Reopen.
  - Run and Reopen for every other date, including Run on other closed days.
  - `rerun-skipped`, `advance-date`, business-date logic, locking functions, models, schema, migrations, settings, datasets, invariants, Golden Master masters, SR-1 and K-7.
- Line endings preserved: all three files are LF. `git diff --check` is clean. `reports.py` compiles, and both templates parse with Jinja2.

## 3. Test environment and safety controls

| Control | How it was enforced | Observed |
|---|---|---|
| Copy only | `verify_dq56.py` copies the source with `sqlite3` `mode=ro` + backup API into a scratch dir; asserts `SQLALCHEMY_DATABASE_URI` is the copy and not `instance/pms.db`; asserts the work dir and app root are outside the live folder | `db_uri_is_copy: true` |
| Production untouched | SHA-256 of the source/live DB before and after each harness run, and before and after the regression batteries | unchanged in every run (`source_unchanged`, `live_db_unchanged` = true; `prod_hash_before_regression.txt` and the post-battery hash both `21dc0e97…`) |
| No guest messaging / no external calls | live `.env` not loaded; `ULTRAMSG_*`, `SMTP_*`, `GEMINI_*`, `FRONTDESK_WHATSAPP`, `DATABASE_URL` removed from the environment (`verify_dq56.py`, `run_pvf_noenv.py`) | no credentials present in any process |
| Scheduler | DQ-56 harness: `scheduler.shutdown()` immediately after `create_app` | `scheduler_running_after_shutdown: false` |
| Boot effect on copy | copy hash after `create_app` compared with the master copy | `boot_changed_copy: false` (nothing pending) |
| Test isolation | every test resets the copy from a pristine master copy; test users `dq56_<role>` created on the copy only (the production `admin` identity is never used) | — |
| CSRF | disabled in the harness's in-process test client only (`WTF_CSRF_ENABLED=False`) | test-client setting; not an application change |
| Personal data | results hold hashes, counts, statuses, booleans and `total_taxable` only; all 55 pack files scanned for phone/e-mail patterns before commit | 0 hits; free-text fields in the copied row are test strings |

## 4. DQ-56 tests (package §7) — RED (control `c9eeff0`) vs GREEN (`46c4aab`)

Raw results: `dq56_tests/dq56_RED_c9eeff0.json`, `dq56_tests/dq56_GREEN_46c4aab.json`. Summaries: `dq56_tests/summary_*.txt` (produced by `summarize_dq56.py`).

| Test | Action (on a fresh copy) | RED — today's behaviour | GREEN — DQ56-R1 | Verdict |
|---|---|---|---|---|
| T-01 | Admin Reopen 2026-08-09 | status `Completed`→`Reopened`; `snapshot_valid` 1→0; reopen log +1; audit log +1; **business date 2026-08-10 → 2026-08-09** | refused ("Reopen is disabled for 09 Aug 2026 …"); row SHA-256 unchanged; reopen log +0; audit log +0; business date 2026-08-10 | **PASS** |
| T-02 | Run 2026-08-09 as Admin / Manager / Accountant (sentinel `total_revenue = -12345` planted on the copy) | each role: sentinel overwritten to 1200 (Run rewrote the sealed row); unperturbed Run rewrote identical values | each role refused; sentinel preserved (−12345); row unchanged | **PASS** |
| T-03 | Admin Reopen → Run → Complete (override) on 2026-08-09 | snapshot replaced (`d248ae54…` → new hash); **`total_taxable` 2285.7 → 1142.85** (re-sealed with the Q06-H2-corrected value); status back to `Completed` | Reopen refused; Run refused; Complete refused by its existing guard ("already completed"); snapshot `d248ae54…` unchanged; `total_taxable` 2285.7 | **PASS** |
| T-04 | `is_date_locked(2026-08-09)` after the reopen attempt | False | True | **PASS** |
| T-05 | business date and lock after the reopen attempt (the condition that permits new postings into 2026-08-09) | business date 2026-08-09, date unlocked → postings into the sealed day possible | business date 2026-08-10, date locked | **PASS** (verified through business date + lock function; no payment was posted) |
| T-06 | Non-protected 2026-08-10: Run → Complete → Reopen → Run → Complete | Completed, bd → 08-11; Reopened, bd → 08-10; Completed, snapshot valid, bd → 08-11 | **identical** | **PASS** (no regression) |
| T-07 | Run on a non-protected **closed** day (sentinel planted) | sentinel overwritten | **identical** (general closed-day Run semantics unchanged, as directed) | **PASS** |
| T-08 | UI for 2026-08-09, panel and the deprecated report template; normal, and with a simulated version bump (`APP_VERSION` + suffix) | Reopen button, Reopen form and modal present; with drift: drift banner **and** Run form present | Reopen button/form/modal absent; Run form absent (also under drift); protected note present; GETs change nothing | **PASS** |
| T-08b | UI for non-protected closed 2026-08-10 (normal and drift) | Reopen present; with drift, Run present | **identical**; no protected note | **PASS** |
| T-09 | Role matrix on 2026-08-09 | FrontDesk / Housekeeping: 403 / 403; Accountant: Run executes, Reopen 403; Manager: Run executes, Reopen executes | FrontDesk / Housekeeping: 403 / 403; Accountant: Run refused, Reopen 403; Manager: both refused; row `Completed`, valid | **PASS** |
| T-10a | Guard function (branch only) | not present | True for `date`/`datetime`/ISO string of 2026-08-09; False for 08-08, 08-10, `None`, `''`, invalid string | **PASS** |
| T-10 | Regression battery | see §6 | see §6 | **PASS** (no unexpected difference) |
| T-11 | optional verification-side hash check | not in R1 scope | not implemented | NOT APPLICABLE |

## 5. Harness defect found and corrected during the work (recorded, not hidden)

The first RED run (`dq56_tests/dq56_RED_c9eeff0_v1_HARNESS_DEFECT.json` / `.log`, kept unedited) had two harness errors:
1. **It reported the business date as 2026-10-02.** The query `SELECT current_date FROM business_date` returns SQLite's `CURRENT_DATE` keyword (today's UTC date), not the column. Fixed by quoting the column (`verify_dq56.py`, comment at the query).
2. **`/reports/night-audit?date=…` returned 302.** The route redirects bare GETs to the panel; `reports/night_audit.html` renders only for an unrecognised `format` value, a deprecated path (`app/reports.py` W1-R8 comment). The harness now requests `&format=dq56-deprecated`, which exercises that template (its deprecation warning appears in the logs).

Neither defect affected the application or production. All verdicts in §4 come from the corrected harness (`verify_dq56.py` as committed), run on RED and GREEN back to back (09:06–09:08 IST).

## 6. Regression battery (T-10) — control vs branch, same environment

Driver: `run_regression.sh` + `run_pvf_noenv.py`. These are the SR-2 command set; the live `.env` is not loaded. Both worktrees ran in parallel with the **same** throwaway key; production was the read-only source. Outputs: `regression/control_c9eeff0/`, `regression/branch_46c4aab/`. Structured diff: `regression/control_vs_branch_diff.txt` (`pack_diff.py`).

| Suite | Control `c9eeff0` | Branch `46c4aab` | Control vs branch | Classification |
|---|---|---|---|---|
| `inv-run` production | rc=1 | rc=1 | only `memory_peak_kb` metering (144→146) | identical; VERDICT FAIL from INV-A02 VIOLATED 8 and INV-A03 VIOLATED 2 only (`inv_run.log:99-106,235-236`) = the FD-P2-03 D11 declared-exception rows — PRE-EXISTING |
| `ds-run` | rc=0, all datasets PASS (incl. DS-ACT-VOIDCN `synthetic-unreachable`) | same | identical | PASS |
| `ds-commission` | PASS | PASS | identical | PASS |
| `fault-run` | rc=1, VERDICT FAIL | same | only memory metering | PRE-EXISTING (FLT-C07 missed, 4 uncovered — SR-2 REV2 report) |
| `gm-verify phase1_aa6d9e91` | rc=1, 39 differences | rc=1, **41** differences | **39 common, 0 only-control, 2 only-branch, both on `main.night_audit`** (BODY_CHANGED; NORMALISATION_CHANGED `csrf_input` 2→1) | the 39 common: ENVIRONMENTAL / OPERATIONAL (below). The 2 extra: **EXPECTED** — the Golden Master's `/night-audit` landing page is 2026-08-09, and R1 replaces its Reopen button and reopen-modal form with the protected note. **No master was re-baselined** |
| `replay-verify` production | rc=1, 2 differences, FAIL | same | **0 differences** | PRE-EXISTING (the two governed Q06-H2 deltas) |
| cross-implementation | rc=1, FAIL, 5 blocking | same | **0 differences** (logs identical except worktree paths; the Q17 "78/81" is the `ms` timing column) | PRE-EXISTING |
| `inv-registry` | rc=0 | rc=0 | identical | PASS |

**Golden Master 39 common differences** (identical on control and branch):
- ENVIRONMENTAL, caused by this deliberately credential-free environment. Pages that render encrypted guest fields or integration settings (`ota.*`, `loyalty.*`, `groups.*`, `ai.*`, `main.guest_folio__any_guest`, `main.invoice_manager`, `main.room_grid`, `reports.*`, …) differ because the production `PII_ENCRYPTION_KEY`/integration settings are absent. `backup.index` differs because the worktree's `backups/` folder is empty.
- OPERATIONAL / PRE-EXISTING:
  - `/auth/users` (founder logins);
  - `/rates/notification-logs` (+3 rows from 2026-09-30);
  - a date-dependent alert age (`days_active` 75 vs 57).

The SR-2 runs (with the live `.env`) showed 6 differences. The extra 33 here come from the missing `.env`, which is why every comparison is made control-vs-branch under one environment rather than against those earlier packs.

**Exit codes:** identical pattern on both sides, and the same as the SR-2 baseline (`20260930_sr2_inv_d02/baseline_c703150/exit_codes.txt`), except `gm_verify` rc=1 here vs rc=2 there (environment-dependent difference count; same on control and branch).

## 7. What did not change (checked)

- **Database:** no production write. Every copy was disposable and discarded in the scratch directory.
- **Schema / migrations:** no model, migration-registry or schema file touched (`git diff --stat`). No migration pending, and the copy is unchanged by boot (`boot_changed_copy: false`).
- **General closed-day Run semantics:** T-07 identical in RED and GREEN.
- **Business-date logic:** T-06 date movement identical. Lock functions untouched.
- **Other dates:** T-06, T-07 and T-08b identical.
- **SR-1, K-7, invariants, datasets, Golden Master masters:** untouched. `ds-run`, `ds-commission`, `inv-run`, `inv-registry` and replay are identical.

## 8. Limitations and NOT VERIFIED items

- UI checks are HTML-content checks through the Flask test client (form actions, element ids, note id). Rendering in a real browser was **NOT VERIFIED**.
- T-05 was verified through the business date and `is_date_locked`. No actual payment, check-in or charge was posted into 2026-08-09.
- The guard protects the application routes only. A direct database write can still change the row (an architectural limitation, as recorded for SR2-REV2 item 8). An optional verification-side hash check (T-11) was not part of R1.
- In `night_audit_reopen` the existing "reason required" check runs before the guard. A protected-date reopen without a reason therefore gets the reason message, not the protection message. Either way nothing is written.
- Pre-existing and unchanged: three Re-run forms in the deprecated `reports/night_audit.html` post `date` instead of `audit_date`, so they always failed validation. R1 only hides them for the protected date. Recorded, not fixed (outside scope).
- The regression ran without the production `.env`. Absolute Golden Master parity with the adopted master was therefore not measured in this run; the control-vs-branch comparison is the evidence.
- Branch-only: `46c4aab` exists only in the local branch `dq56-q06h1-guard`.

## 9. Production decision boundary — STOPPED

Nothing below is authorized. It describes what production application of R1 would involve, so the founder can decide.

- **What changes in production:** only Python code and two templates. Deploying the code is the whole change: no data migration, no schema change, no setting.
- **How it reaches production:** the live folder runs `c703150` from its own working tree. Applying R1 means bringing `46c4aab`'s three files into that checkout (merge/fast-forward of an integration of `origin/main` + this branch, or a cherry-pick). The protection takes effect only at the next application start.
- **Boot effect at that start:** the boot-time registry runs, as on every start, with nothing pending. The scheduler and notification flush start, as on every start (DQ-31 hazard unchanged). The live `.env` credentials are present there.
- **Prerequisites to decide:**
  - a verified backup of the current state `21dc0e97…` (DQ-37), even though R1 writes no data;
  - whether the application is started at all (production is currently stopped);
  - push/merge authorization for `dq56-q06h1-guard`;
  - whether `origin/main` is updated first.
- **Rollback:** revert `46c4aab` (no data to restore, since R1 writes nothing).

**Decision required (DQ-56e):** authorize, or not, production application of `46c4aab`: push and merge route, live-checkout update, whether and when the app is started, and the backup requirement.

## 10. Status

| Item | Status |
|---|---|
| DQ56-R1 implementation (`46c4aab`) | DONE (local branch) |
| DQ-56 tests T-01…T-10a | **PASS** (GREEN) — RED recorded on control |
| Regression (T-10) | **PASS** — no unexpected difference; 2 EXPECTED Golden Master differences; all failures PRE-EXISTING / ENVIRONMENTAL and identical to control |
| Production | unchanged (`21dc0e97…`), stopped |
| Push / merge | NOT AUTHORIZED — not done |
| Production application | NOT AUTHORIZED — DQ-56e |
