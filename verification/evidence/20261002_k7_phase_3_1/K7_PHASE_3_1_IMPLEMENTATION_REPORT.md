# K-7 / Phase 3.1: implementation and evidence report

| | |
|---|---|
| Directive | `FG-P3-1-K7-DIRECTIVE-01`, ACTIVE and FROZEN by Founder Round 12. Text: `K7_PHASE_3_1_DIRECTIVE_FROZEN.md`, SHA-256 `28413d8e381fcefced8e6d9f0fc7798a1ef682e3f6d4e39025d0502ae4589f95` |
| Branch | `k7-phase-3-1`, **local only** (worktree `C:/wk7`). Not pushed, not merged, not deployed |
| Base for the RED run | `d21eb50` (activation commit; `app/` and `tools/` byte-identical to `main` `0938069`) |
| **Tested commit (code)** | **`463ad7a`**: `app/models.py`, `app/services.py`, `app/routes.py`, `app/occupancy_engine.py`, `app/kpi_command_center.py` only |
| Later commits (no `app/` change) | `940366e` regression drivers · `e11a0a1` S-TL, comparers, mutation script · this evidence commit. `git diff 463ad7a HEAD -- app tools` is empty |
| Outcome | **GREEN 174/174** on the branch. **RED 173/174** on the base: the single mismatch is a registered expectation that was imprecise (section 3.3). Mutation proof **17/17**. Regression battery: **0 verdict-level differences** between control and branch. Production untouched |
| Status | **K-7 implemented and evidenced on the local branch. STOPPED at the Founder boundary.** |

## 1. What changed (5 files, +119 / −36)

| File | + / − | Change |
|---|---|---|
| `app/models.py` | 37 / 3 | `BusinessDateUnavailable`; `_business_date_at_insert(context)`, a context-sensitive default that reads the business date on the INSERT's own connection or raises; `Payment.payment_date`, `ExtraCharge.charge_date`, `CreditVoucher.issued_date` use it instead of `date.today`. `BusinessDate.current_date` is unchanged (F-2) |
| `app/services.py` | 54 / 23 | `get_business_date()` fails closed: logs an ERROR and raises. W-08/W-09, W-22/W-23 correction pairs, the W-10 refund and the W-11 redemption payment take **one** resolved business date per operation. Voucher basis **A**: `issue_credit_voucher` (new optional `issue_date`), `compute_voucher_status` and `refresh_voucher_status` (new optional `as_of`), and the repeated test in `redeem_credit_voucher` all use the business date. `run_night_audit` logs an ERROR when the row is absent (BR-10) |
| `app/routes.py` (CRLF kept) | 4 / 3 | W-17 and W-20 rows carry `charge_date=get_business_date()` (billing hours stay on physical time). The night-audit view uses `get_business_date()` |
| `app/occupancy_engine.py` | 15 / 6 | `_business_date()` no longer swallows every exception into the calendar: it logs an ERROR and returns `None`; the payload label becomes `None` |
| `app/kpi_command_center.py` | 9 / 1 | no calendar default: an absent context date logs an ERROR and raises `BusinessDateUnavailable` |

Per site (all at `0938069` line numbers; observed values are from the harness):

| Site | Before (observed, clock 2026-10-02, business date 2026-08-10) | After |
|---|---|---|
| W-08/W-09 `post_payment_correction` (service and `POST /payment/<id>/void`) | 2026-10-02 | **2026-08-10** |
| W-10 refund | 2026-10-02 | **2026-08-10** |
| W-11 voucher redemption payment | 2026-10-02 | **2026-08-10** |
| W-17 checkout extra | 2026-10-02 | **2026-08-10** |
| W-20 overstay row (amount 2400.00 on both trees) | 2026-10-02 | **2026-08-10** |
| W-22/W-23 `post_extra_charge_correction` | 2026-10-02 | **2026-08-10** |
| Voucher issue / expiry (365 days) | 2026-10-02 / 2027-10-02 | **2026-08-10 / 2027-08-10** (basis A) |
| Model defaults (ORM insert with no date) | 2026-10-02 | **2026-08-10**; with no row they **raise**, no row written |
| Tax lines of W-17 and W-20 charges | 2026-10-02 | **2026-08-10** (follow the row date) |

Unchanged by design: the 16 already business-dated writers; Complete, Reopen, Force Close; the DDL; the seed row; late checkout; report ranges; void/shift mapping; invoice and credit-note UTC dating; schema; migrations; INV-B06.

## 2. Method (directive section 7)

- **Two trees:** base `C:/wk7base` at `d21eb50`; branch `C:/wk7`. Same throwaway `SECRET_KEY`. No `.env` is loaded and messaging and AI variables are stripped.
- **One disposable copy of production per scenario, one process per scenario** (`verification.dbcopy.make_copy`, production opened read-only). Production SHA-256 `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434` was equal before and after every run.
- **Clock deliberately different from the business date:** the proven freezer (`verification/golden/freeze.py`, `install_proven`) is installed **before** `app` is imported, with its proof recorded and asserted in every scenario. Fixtures: F-LAG (business date 2026-08-10, clock 2026-10-02 12:00), F-AHEAD (business date 2026-10-03, clock 2026-10-02 23:30, day 2026-10-02 sealed), F-UTC (00:30), F-NOROW (row deleted).
- **Expectations registered and committed before the first run** (`fc9746c`, `expectations.json`): 174 assertions in 32 scenarios; 61 of them discriminate base from branch.
- Invariants evaluated in fresh processes. The eight D11 rows and the sealed 2026-08-09 snapshot were byte-identical after every scenario on both trees (N-5).

## 3. Results

### 3.1 RED / GREEN

| Run | Tree | Result |
|---|---|---|
| RED | base `d21eb50` | **173 / 174** as registered. Every K-7 behaviour is the old one: calendar-dated rows, silent calendar fallbacks |
| GREEN | branch `463ad7a` | **174 / 174** as registered |

Scenarios: per-site dating S-08-09 (service), S-08-09-route, S-10, S-VI, S-11, S-17, S-20, S-22-23, S-TL; voucher basis V-1 to V-4; defaults D-1, D-2; fallbacks and fail-closed F-1, F-2 (seven writers and routes), F-3a to F-3d; sealed-day and invariants N-3-AHEAD, S-ALL, S-ALL-UTC; DDL-1, DDL-2.

Selected observations (RED → GREEN):

| Check | RED | GREEN |
|---|---|---|
| `get_business_date()` with no row | returns 2026-10-02 | raises `BusinessDateUnavailable`, ERROR logged |
| Seven writers and routes with no row | rows written (3 to 8 per operation) | **0 rows**, no audit rows |
| ORM insert with no date and no row | inserted | raised, 0 rows |
| Voucher with expiry = business date (V-1) | `expired`, redemption refused | `active`, redemption OK |
| Voucher with expiry 2026-09-15, between business date and calendar (V-3) | `expired`, refused | `active`, OK |
| Opening the voucher ledger report (V-4, C-2) | stored status flips to `expired` | stays `active` |
| Occupancy payload label, no row | 2026-10-02 | `None`, ERROR logged |
| KPI governance block, no date | returns a dict | raises |
| `GET /night-audit`, no row | 200 | 500, ERROR logged |
| `run_night_audit`, no row | returns silently | returns, ERROR logged, 0 logs |
| F-AHEAD: rows dated into the sealed day 2026-10-02 | yes; **INV-B01 VIOLATED** | none; **INV-B01 HOLDS**; INV-B03 unchanged (HOLDS before and after) |
| All writers in one copy, then INV-B04 | **VIOLATED** (before: HOLDS) | **HOLDS** |
| Same at clock 00:30 (S-ALL-UTC) | VIOLATED | HOLDS |
| DDL-1: production-copy schema | no default on `issued_date`, `payment_date`, `charge_date`, `current_date` (C-1 confirmed) | same |
| DDL-2: `credit_vouchers` recreated with the code's DDL (has `DEFAULT (date('now'))`) | issued 2026-10-02 | **issued 2026-08-10**: the ORM value, never the DDL default |

### 3.2 Mutation proof (N-6): every test is load-bearing

17 mutants, each reverting one K-7 change on a scratch worktree of `463ad7a` (`mutation_results.json`). **17 of 17 turned the matching scenarios RED** (1 to 8 failed assertions each): M01 W-08/09, M02 W-22/23, M03 W-10, M04 voucher issue/anchor, M05 W-11, M06 status derivation, M07 repeated redemption test, M08 W-17, M09 W-20, M10/M10b/M10c the three defaults, M11 `get_business_date`, M12 `run_night_audit` logging, M13 occupancy, M14 KPI, M15 night-audit view.

### 3.3 Registered expectation that did not hold (reported, not adjusted)

`N-3-AHEAD.row_dates` was registered as `["2026-10-02"]` for the base. The base actually produces `["2026-10-02", "2026-10-03"]`, because the already business-dated writers and fixture rows are dated 2026-10-03 on both trees. That is a mistake in my registration, not in the code. Before the recorded run I added a precise companion assertion, `any_row_in_sealed_day` (base true, branch false), which holds on both trees. The branch value for `row_dates` (`["2026-10-03"]`) matches.

## 4. Regression battery (control `d21eb50` against branch, same environment)

Run from the two worktrees, no live `.env`, production only as the read-only copy source. Output: `regression/base`, `regression/branch`, `regression/battery_compare.json`, `regression/logs_compare.json`.

| Suite | Control / branch | Difference |
|---|---|---|
| Exit codes of all 36 steps | identical | none |
| `inv-run --tag production` | identical; 26 invariants compared | **0** status, population or violation differences. INV-B01, B03, B04, B06 all HOLD |
| `ds-run`, `ds-commission`, `fault-run`, `gm-verify phase1_aa6d9e91`, `replay-verify`, cross-implementation, `inv-registry`, `inv-commission` | identical | **0** verdict-level differences |
| Phase 2a matrix | 29/29 and 29/29 | none |
| CF-10 / CF-11 groups (cf11, corr, w10, voucher, w12, w13, w14, w24, na, actor, w14 declared) | identical per group | none |
| Phase 1 writers sets A to D, undeclared and declared | identical verdict lines (e.g. A: 86/86, B: 48/48) | **only recorded dates moved** (4.2) |
| Phase 1 execution (undeclared, declared) | 26 and 44 verdict lines identical | none |
| W-20 runtime | 23/23 and 23/23 | recorded `charge_date` moved |
| Q06 fix regression | 14/14 and 14/14 | none |
| Retention, restore-tool tests | identical | none |
| DQ56-R1 guard tests T-01 to T-10 | **9 of 9 test records identical** | none (the guard is intact) |

Pre-existing failures, identical on both sides and **not re-baselined**: every CF-10 group fails the single gate `P-01` (production SHA-256 equals the old anchor `51dd83b7…`; production is `21dc0e97…`, the known GT-D8 item); `inv-run`, `fault-run`, `gm-verify`, `replay-verify`, cross-implementation (Q06, Q14, Q17, Q20 DIVERGED) and `inv-commission` return the same non-zero results as in the SR-1 and DQ-56 packs.

## 5. Declared deltas

### 5.1 Outcomes that moved, all expected (every one follows from the Round 11/12 rulings)

| Where | Base | Branch | Reason |
|---|---|---|---|
| Harness: 61 discriminating assertions in 30 scenarios (section 3) | calendar | business date | K-7 |
| `legacy/writers_A` and `_A_declared`: checkout payments list (W-17 row) | 2026-10-02 | 2026-08-10 | W-17 |
| `legacy/writers_B` and `_B_declared`: void correction pair (W-08/W-09) | 2026-10-02, 2026-10-02 | 2026-08-10, 2026-08-10 | W-08/W-09 |
| same: new-reservation voucher redemption payment (W-11) | 2026-10-02 | 2026-08-10 | W-11 |
| same: charge correction pair (W-22/W-23) | 2026-10-02, 2026-10-02 | 2026-08-10, 2026-08-10 | W-22/W-23 |
| `legacy/w20`: overstay `created row` | 2026-10-02 | 2026-08-10 | W-20 |
| INV-B04 after all writers, INV-B01 in F-AHEAD (harness) | VIOLATED | HOLDS | calendar rows no longer exist |

### 5.2 Expected non-moves (confirmed)

The 16 already business-dated writers; production invariant statuses; every verdict line of every legacy suite; the D11 rows and the sealed 2026-08-09 snapshot (byte-identical); W-20's billed amount (2400.00 both).

### 5.3 Unlisted movement

**None found.** Verdict-level comparison of the PVF layers (0), the legacy suites (0 of 18 logs) and the DQ56 tests (0) shows no movement outside 5.1. The two JSON "differences" the comparer printed are set ordering and a timestamp.

## 6. Deviations from the frozen directive and things that went wrong, stated plainly

1. **F-UTC.** The proven freezer maps `datetime.utcnow()` to the frozen instant, so the UTC-offset edge cannot be represented. S-ALL-UTC runs at 00:30 as a time-of-day edge only. The UTC DDL-default hazard is moot on production (C-1) and DDL-2 covers the fresh-DDL case.
2. **S-BD (the 16 business-dated writers)** is covered by the established Phase 1 writer and CF-10 harnesses compared base against branch (section 4), plus W-04 and W-18 rows inside S-17, not by a separate K-7 scenario.
3. **S-TL was missing from the first registration.** I added it with its expectation registered before any run of it, and repeated the recorded RED and GREEN on the final harness.
4. **Two harness mechanics were repaired before the recorded runs** (the voucher fixture used a constant issue date; the route scenario's new-row baseline counted a fixture row). No expectation changed.
5. **A bug in my own first edit was caught by the harness**: a `sed` rename produced `_nalogger` in `run_night_audit`; F-3d failed with a `NameError`, and I fixed it before the code commit. A first mutation run was invalid (the throwaway key was not exported, so the harness aborted); the script now treats a harness that does not complete as an error, and the recorded mutation run is the second.
6. **The regression battery ran at `940366e`** (same `app/` as `463ad7a`), and the GREEN harness records HEAD `e11a0a1` (docs and tooling only); `code_tree_status` was empty in both recorded JSON files.
7. **Privacy.** Harness logs contained one real guest phone number (the DQ-45 number) in "Queued whatsapp notification…" lines. 71 occurrences were redacted in the committed copies; the pack scans at 0 phone-like, 0 email-like, 0 secret-style matches. The unredacted originals stayed in the scratch directory.

## 7. Residuals and what to know

- **Operating rules, not code** (BR-11): no trading and no new vouchers while the business date is stale. K-7 does not guard staleness: it has no definition (B-10 #5, unit 3.6) and a calendar comparison would reintroduce the wall clock.
- **Residual Phase 3.2 / 3.4 items (F-3), untouched:** Complete (`app/reports.py:3121-3125`) and Reopen (`:3225-3229`) still skip silently when the row is absent. Their semantics were not changed or tested.
- **Blast radius of fail-closed:** `get_business_date()` has 115 call sites. With the row absent, every one of them now raises. The row exists on production and `init_data()` re-seeds it on any start of an empty database.
- **Merge is deployment-at-rest.** `SukoonPMS/` is the live checkout, so merging this branch replaces live code; it takes effect at the next application start. That start, and any business-date advance, remain separate PD-004 acts.
- **Production effect today: none.** Production holds no corrections, refunds or vouchers; the production database is byte-identical and the application is stopped.
- **Existing defect candidate (not K-7):** a voucher force-expired through the admin route is flipped back to `active` by the next status refresh unless its date has passed (read from the code, not run).

## 8. Remaining Founder decisions (none blocks anything already done)

1. Authorize push and merge of `k7-phase-3-1` (separately, as for SR-1; I recommend a fresh gate re-run before any push).
2. G-1 to G-7 governance entries (prepared in the review pack, not ruled).
3. K7-D10 close-path decision and BD-D2 to BD-D5 (the stale-date remediation, timed to go-live under S1).
4. Whether the "no vouchers while stale" and "no trading while stale" operating rules need a code guard once B-10 #5 / unit 3.6 defines staleness.
5. Whether the Complete / Reopen silent-skip residuals are scheduled into units 3.2 and 3.4.
6. K7-D5 late checkout disposition; K7-D8 first-start sequencing.

## 9. Reproduce

`verify_k7.py --worktree <tree> --role base|branch --label <L>` (run a verbatim copy of this pack from a scratch directory, with a throwaway `SECRET_KEY` exported); `run_regression.sh <worktree> <role> <out> <key>`; `compare_battery.py`, `compare_logs.py`; `k7_mutations.py <scratch worktree at 463ad7a> <out.json>`.
