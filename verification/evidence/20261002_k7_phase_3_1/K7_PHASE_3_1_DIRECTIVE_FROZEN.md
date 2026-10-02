# PHASE 3.1 DIRECTIVE — K-7 business-date dating at all writers

| | |
|---|---|
| Directive ID | `FG-P3-1-K7-DIRECTIVE-01` |
| Status | **ACTIVE and FROZEN.** Activated by Founder Round 12 (`verification/FOUNDER_DECISIONS.md`). This file is the text of the Round 11 draft (`20261002_round11_k7_directive/K7_PHASE_3_1_DIRECTIVE.md`, unedited) with exactly the Round 12 answers and corrections C-1 to C-3 applied. It is not edited after activation; a deviation is recorded in the implementation report, never here |
| Prepared | 2026-10-02 |
| Base | `main` = `origin/main` = `0938069`. Every file:line below was re-verified at `0938069` unless marked otherwise |
| Authority | Founder Round 11: GT-D1, K7-D1/GT-D5, K7-D2, K7-D3, K7-D7 (rulings). Founder Round 12: F-1 to F-6, K7-D4 = A, BD-D1 = S1, K7-D10 outside this directive (rulings), C-1 to C-3 recorded |
| Analysis inputs | `verification/evidence/20261002_overnight_k7_analysis/` (branch `overnight-20261002`): `K7_WRITER_INVENTORY.md`, `K7_ARCHITECTURE_ANALYSIS.md`, `K7_DEPENDENCY_MAP.md`, `K7_PRODUCTION_RISK.md`, `K7_DECISION_REQUIRED.md` §P |
| Companion records | `K7_D4_VOUCHER_BASIS_DECISION.md` (answered: A), `K7_FOUNDER_DECISION_REVIEW_PACK.md` (F-1…F-6, C-1…C-3), `K7_D10_CLOSE_PATH_DECISION_PACKAGE.md` (undecided; outside this directive) |

Labels: **FACT** = read from code or a governance record. **RULED** = Founder text recorded in Round 11 or Round 12. This directive selects nothing that is not RULED.

---

## 0. Status and activation

1. This directive is **ACTIVE** from the Round 12 entry and **FROZEN** from the same moment. The Round 12 entry records this file's SHA-256 and path.
2. It authorizes **implementation and evidence generation on the local branch `k7-phase-3-1` only** (F-6).
3. It does **not** authorize push, merge, tag, deployment, a production start, any production data change, a database modification outside disposable copies, a migration, a business-date change, or trading (F-6).
4. Operating rules from the rulings that bind the operator, not the code (§4 BR-11): no trading while the business date is stale (BD-D1); no new vouchers while it is stale (F-1).

## 1. RULED inputs (Founder Round 11, verbatim in `FOUNDER_DECISIONS.md`)

| ID | Ruling in one line | Where it binds here |
|---|---|---|
| GT-D1 | G3's K-7 item closes when Phase 3.1 is completely implemented and evidenced | §2 completion criteria, §8 |
| K7-D1 / GT-D5 | A dedicated Phase 3.1 directive for K-7. B-1 and the undefined Gates A–H are outside it; validate against G3, G6 and G10 | §8 |
| K7-D2 | Scope: W-08, W-09, W-10, W-11, W-17, W-20, W-22, W-23; voucher `issued_date` and expiry anchor; relevant model defaults; business-date fallback paths. Late checkout, report ranges, void/shift-day mapping and invoice/credit-note UTC dating stay outside unless a concrete dependency is demonstrated | §3 |
| K7-D3 | Fail closed with a logged error where the business date cannot be resolved. Defaults resolve the business date at insertion or raise, never the wall clock | §4 |
| K7-D4 | Present exact alternatives and consequences for Founder confirmation; do not silently choose | §5, companion file |
| K7-D7 | Dedicated RED/GREEN harness with the system clock deliberately different from the production business date; disposable production copies; full regression battery; declared-delta list; no new invariant for K-7 | §7 |
| K7-D10 | Close-path alternatives are a separate decision package; neither path is performed in production | **Round 12: remains undecided and outside this directive** |

### Round 12 rulings (verbatim in `FOUNDER_DECISIONS.md`)

| ID | Ruling | Where it binds here |
|---|---|---|
| F-1 / K7-D4 | Voucher basis **A**: business date throughout for voucher issue and expiry semantics. While the business date is stale, do not issue new vouchers. Do not alter existing production vouchers (none exist) | §3.1, BR-9, BR-11 |
| F-2 | Seed row: leave unchanged | §3.2 note, §11 |
| F-3 | Do not expand K-7 to Complete or Reopen; do not change their semantics; record them as residual Phase 3.2/3.4 items. `run_night_audit` may receive the logged-error handling provided it does not silently substitute the wall-clock date | §3.2, BR-10, §11 |
| F-4 | Leave the existing DDL unchanged. Record the corrected finding: production's `credit_vouchers.issued_date` has **no** DDL default | §11 |
| F-5 | Read-only displays: the proposed error/`None` behaviour, provided it is deterministic, logged, and does not substitute the system calendar date | BR-5 |
| F-6 | Activation authorizes implementation and evidence on the local branch only; not push, merge, deployment, production start, business-date change or trading | §0, §9 |
| BD-D1 | Sequence **S1**: complete K-7 implementation and evidence first; address the stale business date separately and time its remediation to go-live. No trading while the business date remains stale | §0, §10 |
| C-1 to C-3 | Corrections from the review pack, recorded without expanding K-7 scope | §3.1, §11, BR-9 |

## 2. Objective and completion

**Objective.** Every financial row created by an in-scope writer is dated from the controlled business date resolved at the moment of posting, never from the wall clock or a model default, and the business-date reader never substitutes the calendar.

**"Completely implemented and evidenced" (GT-D1) means all of:**

| # | Criterion |
|---|---|
| C-1 | All eight writer sites in §3.1 date from the business date, proven RED at base and GREEN on the branch by the §7 harness |
| C-2 | The voucher sites in §3.1 follow the basis the Founder confirmed in K7-D4 |
| C-3 | The three model defaults and every fallback in §3.2 behave per §4 (resolve or raise; no wall-clock substitution) |
| C-4 | The 16 already business-dated writers show no change (S-BD) |
| C-5 | The full regression battery (§7.6) is complete and every moved outcome is on the declared-delta list; any unlisted movement is a defect |
| C-6 | A committed evidence pack names the tested commit; production SHA-256 equal before and after; no application started in the live folder |
| C-7 | The report states plainly which G6 conditions remain open (§8) |

## 3. Scope

### 3.1 IN scope: writers, vouchers, defaults (all at `0938069`)

| ID | Site | Today | Required |
|---|---|---|---|
| W-08 | `app/services.py:1217` (`today = _date.today()`), row `:1228` | calendar | business date of posting |
| W-09 | same function, replacement row `:1258` | calendar | business date of posting (same value as W-08 within one correction) |
| W-10 | `app/services.py:1807` `payment_date=_date.today()` (cancellation refund) | calendar | business date of posting |
| W-11 | `app/services.py:2116` `payment_date=_d.today()` (voucher redemption payment) | calendar | business date of posting |
| W-17 | `app/routes.py:3108-3113` `ExtraCharge(...)` passes no `charge_date`; default `app/models.py:775` | model default (calendar) | explicit business date |
| W-20 | `app/routes.py:8029` `now = datetime.now()`, row `:8084` `charge_date=now.date()` | calendar | business date. The billable-hours computation stays on physical time |
| W-22 | `app/services.py:1306`, row `:1318` (no caller in `app/`, definition `:1283`) | calendar | business date of posting |
| W-23 | same function, row `:1351` | calendar | business date of posting |
| Voucher issue date | `app/services.py:1965` `issued_date=_d.today()` | calendar | business date (K7-D4 = A) |
| Voucher expiry anchor | `app/services.py:1950` `expiry = _d.today() + expiry_days` (caller passes 365, `:1854`) | calendar | business date + `expiry_days` (A) |
| Voucher expiry tests | `app/services.py:2009` (`compute_voucher_status`), `:2077` (`redeem_credit_voucher`) | calendar | business date (A). These are tests, not dating. They must move together: `refresh_voucher_status` (`:2014`) persists the derived status and `expired_at`, runs on redemption, on the lookup API and when the voucher ledger report is opened, and `:2077` repeats the test after it (C-2) |
| Default | `app/models.py:809` `Payment.payment_date` `default=date.today` | calendar | per BR-4 |
| Default | `app/models.py:775` `ExtraCharge.charge_date` `default=date.today` | calendar | per BR-4 |
| Default | `app/models.py:1817` `CreditVoucher.issued_date` `default=date.today` (NOT NULL) | calendar | per BR-4 |

### 3.2 IN scope: business-date fallback paths

| Site | Today | Required |
|---|---|---|
| `app/services.py:619-621` `get_business_date()` | returns `date.today()` when the row is absent | BR-1 |
| `app/routes.py:4769-4770` (night-audit view) | `business_date.current_date if business_date else date.today()` | BR-5 |
| `app/occupancy_engine.py:76-87` | falls back to `_date.today()` on any exception | BR-5 |
| `app/kpi_command_center.py:72` | `ctx.get('business_date') or date.today()` | BR-5 |

Direct readers that do not substitute a date are **not** fallback paths and are not changed in their semantics (F-3): `app/reports.py:3121-3125` (Complete, silently skips the advance), `app/reports.py:3225-3229` (Reopen, silently skips the roll-back), `app/reports.py:3557-3560` (Force Close, already refuses with a message), `app/ceo_kpis.py:392-394` (shows no date). The one exception is `app/services.py:302-306` (`run_night_audit`), which returns silently when the row is absent and receives a logged error under BR-10. The business-date seed (`app/__init__.py:1850-1851`) and `app/models.py:106` stay unchanged (F-2). `get_business_date()` has 115 call sites; BR-1 changes what all of them see when the row is absent (C-3).

### 3.3 OUT of scope (K7-D2)

Late checkout applicability (`app/routes.py:3206-3209` and preview `:3850-3853`); report default ranges (`app/billing.py`, `app/noshow.py`, `app/ota.py`, `app/loyalty.py`, `app/ceo_kpis.py`, `app/ota_reconciliation.py`, `app/reports.py:5897`, dashboard windows); void and shift day mapping (`app/night_audit_service.py:215-219`, `:240-244`; `app/routes.py:7892`; `app/payment_void_service.py:376`); invoice, receipt and credit-note UTC dating (`app/routes.py:163`, `:195`, `:258`; `app/billing.py:607`; invoice templates; `app/gst_einvoice.py:44`; `app/gstr_export.py`); `app/validators.py:101`.

Also out, by other rulings or by being other units: B-1; Gates A–H; the two close paths (K7-D10); Force Close and reopen (3.4); staleness escalation (3.6); the business-date advance itself; any schema or migration; INV-B06 and every other invariant; Golden Master and replay baselines; `app/reports.py` (the DQ56-R1 guard lives there).

### 3.4 Concrete-dependency protocol

K7-D2 allows an out-of-scope item to be pulled in only where "a concrete dependency is demonstrated". Here that means a failing harness test, or a code path read in the implementer's report, that shows an in-scope change cannot be correct or testable without touching the out-of-scope item. On finding one the implementer **stops that item**, records the evidence and the proposed minimum change in the report, and asks. Nothing is widened silently. The Founder's answer is recorded before the work continues.

## 4. Required behaviour (K7-D3)

| # | Rule |
|---|---|
| BR-1 | `get_business_date()` returns `BusinessDate.current_date`. If the row is absent, or `current_date` is NULL, it **logs an ERROR and raises** a single dedicated exception type (one name, used everywhere). It never returns `date.today()` |
| BR-2 | Each in-scope operation resolves the business date once at posting and uses that one value for every row it creates (W-08 and W-09 share it; W-10 refund and any voucher issued in the same disposition share it) |
| BR-3 | If the date is unresolved the operation **refuses**: no payment, charge, voucher, audit or log row is written; the caller receives the failure through that route's existing error idiom; nothing is half-committed |
| BR-4 | The three model defaults no longer use `date.today`. A default resolves the business date **at insertion** or raises under BR-1. Writers still pass the date explicitly; the default is a backstop that must never produce the calendar, NULL or a UTC date. Design constraint: the resolution must not issue a session query from inside a flush (autoflush recursion). Use a context-sensitive default on the flush's own connection, or equivalent, and prove it in the harness. On SQLite do not open `begin_nested()` before DML; use `app.services.nested_transaction()` where a savepoint is needed |
| BR-5 | The three secondary fallbacks stop substituting the calendar, deterministically and with a logged error (F-5). `routes.py` night-audit view: the unresolved date propagates to the app-wide error handler, logged. `occupancy_engine._business_date()`: no longer swallows every exception into the calendar; it logs an ERROR and returns `None`, and the payload label becomes `None` (occupancy counts are unaffected). `kpi_command_center` `today`: no calendar default; an absent context date logs an error and propagates (its route already logs and returns the JSON error envelope) |
| BR-6 | W-20: only the row's `charge_date` changes. Elapsed-hours billing stays on physical time (`app/routes.py:8018-8048`) |
| BR-7 | Technical timestamps (`created_at`, `voided_at`, `redeemed_at`, `checked_in_at`, `checked_out_at`, audit and snapshot times) are unchanged |
| BR-8 | Historical rows are untouched. No data migration, no back-dating, no schema change |
| BR-9 | Vouchers follow basis **A**: `issued_date` is the business date; `expiry_date` is the business date plus `expiry_days`; `compute_voucher_status` and the redemption test compare the expiry date with the business date, and both sites use the same resolved value. The expiry day itself remains redeemable (expired only when `expiry_date` is strictly before the business date). The voucher code string `CV-YYYYMMDD-XXXX` (`app/services.py:1928-1932`) is an identifier and is not changed. Existing vouchers are not altered (none exist on production). The harness must show that opening the voucher ledger report flips the stored status exactly when the business-date basis says so (C-2) |
| BR-10 | `run_night_audit` (`app/services.py:302-306`): when the `business_date` row is absent it logs an ERROR and keeps its existing `return`. It never substitutes the wall clock (F-3) |
| BR-11 | Operating rules, not code guards: no new vouchers are issued while the business date is stale (F-1), and no trading while it is stale (BD-D1). K-7 does not implement a staleness guard, because staleness has no definition yet (B-10 #5, unit 3.6) and a calendar comparison would reintroduce the wall clock. The report restates this as a remaining Founder item |

## 5. Founder answers recorded at activation (Round 12)

| # | Item | Answer |
|---|---|---|
| F-1 | K7-D4 voucher basis | **A**, with the rule that no new vouchers are issued while the date is stale |
| F-2 | Seed row | leave unchanged |
| F-3 | Silent business-date readers | do not expand K-7 to Complete or Reopen; record them as residual Phase 3.2/3.4 items; logged-error handling for `run_night_audit` only |
| F-4 | DDL default | leave the existing DDL; record the corrected finding (production's `credit_vouchers.issued_date` has no DDL default) |
| F-5 | Read-only displays | the proposed error/`None` behaviour, deterministic and logged, no calendar substitution |
| F-6 | Authorization boundary | local branch only; no push, merge, deployment, production start, business-date change or trading |

## 6. Hard constraints

| Rule | Source |
|---|---|
| Production is never opened except read-only as the copy source; SHA-256 recorded before and after (anchor `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434`) | SC-1, SC-2, `finalgrid-production-boundary` |
| No application start in the live folder; no process left running; port 5000 stays free | SC-3 |
| The business date is not advanced, set or closed anywhere except inside disposable copies | Round 11 |
| No schema, migration, `.env` load, messaging or AI call. Messaging and AI environment variables are stripped; a throwaway `SECRET_KEY`; driver pattern `run_pvf_noenv.py` | gotchas |
| Files expected to change in `app/`: `services.py`, `models.py`, `routes.py`, `occupancy_engine.py`, `kpi_command_center.py`. `reports.py` is expected to stay untouched | §3 |
| No re-baseline or reclassification of any frozen suite, Golden Master or replay baseline; old packs are never edited | SC-4, SC-5 |
| Edit with the Edit tool or byte-exact Python, never `sed -i`; keep each file's line endings (`routes.py` CRLF) | gotchas |
| One change, one authorizing reference; code commit separate from evidence commit | SC-6 |

## 7. Evidence standard (K7-D7)

### 7.1 Method

1. Two worktrees: **base** detached at `0938069` (RED) and the **branch** (GREEN), created with `git -c core.longpaths=true worktree add`. Same throwaway `SECRET_KEY` for both.
2. One disposable production copy per scenario, made with `verification/dbcopy.make_copy()` (production opened read-only, SQLite backup API), one process per scenario.
3. Expected results are **registered before the first run** in a committed file (status per scenario at base and on the branch), as `verify_sr1.py` did.
4. The harness copy lives in the new pack; run verbatim copies from a scratch directory so committed evidence is never overwritten.

### 7.2 Clock

The system clock is **deliberately different from the business date in force on the copy**. It is frozen with the proven freezer (`verification/golden/freeze.py` `ClockFreeze`, `install_proven`) and the harness records the freeze proof. The freeze must reach the way `app/` reads time (`date.today`, `datetime.now`, and the aliased `_date` / `_d` imports).

| Fixture | Business date | Clock | Purpose |
|---|---|---|---|
| F-LAG | 2026-08-10 (production's own) | 2026-10-02 12:00 IST | the real lag; every site must date 2026-08-10 |
| F-AHEAD | D+1 | D 23:30 IST | a close before midnight; no row may land in sealed day D |
| F-UTC | any | 00:30 IST (previous UTC day) | UTC-versus-IST edge for the voucher DDL default |
| F-NOROW | `business_date` row deleted | any | fail-closed behaviour |
| F-CLOSED | a Completed log for BD−1 with a payment in it (non-D11, attributed) | any | W-08/W-09 via the void override path |
| F-STAY, F-CANCEL, F-VOUCHER | as `K7_DECISION_REQUIRED.md` §P.2 | any | per-site entry points |

### 7.3 Normative test list (minimum)

Per-site dating (`K7_DECISION_REQUIRED.md` §P.3): S-08/09, S-10, S-VI, S-11, S-17, S-20, S-22/23, S-BD (all 16 already-business-dated writers unchanged), S-TL (tax lines of W-17 and W-20 follow the row date). Negative (§P.4): N-1 (no wall clock, no NULL), N-2 (post-run scan: no created row has a date other than the business date in force), N-3 (F-AHEAD: INV-B01 and INV-B03 hold), N-4 (INV-B04 holds), N-5 (the eight D11 rows and the sealed 2026-08-09 snapshot byte-identical), N-6 (mutation proof: reverting each change turns its test RED). Fallback (§P.5): F-1, F-2 (refuse, no row, no audit row), F-3 (three secondary fallbacks), plus a test that no row ever takes the DDL default. Voucher: V-1…V-4 for the K7-D4 basis, on both sides of the expiry boundary under F-LAG and F-UTC.

### 7.4 RED and GREEN

RED at base must fail exactly where behaviour changes and pass where it does not; GREEN must pass everything. Any mismatch with the registered expectations is reported, not adjusted.

### 7.5 No new invariant

No invariant is created for K-7 (K7-D7). INV-B04 and INV-B01/B03 are run on the copies and reported; their expected movement (calendar-dated rows stop firing INV-B04) goes on the declared-delta list.

### 7.6 Full regression battery on copies, from worktrees

The established SR-1 battery, branch against control, with identical throwaway environment: `inv-run --tag production`, `ds-run`, `ds-commission`, `fault-run`, `gm-verify --tag phase1_aa6d9e91`, `replay-verify --tag production`, `run` (cross-implementation), `inv-registry`, `inv-commission`. Plus: the Phase 2a matrix (29/29); the CF-10/CF-11 harnesses; the DQ56-R1 guard tests (because `app/reports.py` is adjacent); Q06 check; ADR-011 actor checks.

The Phase 1 writer harness (`verify_writers.py`), the W-20 runtime pack and the CF-10 regression harnesses **record** dates; their recorded outcomes will move. They are re-run as **new packs** that supersede, never edit, the old ones (SC-4), with every moved value on the declared-delta list (SC-5). The Golden Master is structurally blind to K-7 (clock frozen to the business date, GET surfaces only); it is a no-regression check only and is not K-7 proof.

### 7.7 Declared-delta list

A table of every recorded outcome that differs from base, with before value, after value, site, and the reason it follows from the ruling. Anything that moves and is not listed is a defect: stop and report. Known candidates: Phase 1 sets A/B findings attributed to K-7 (B04/B06), the W-20 pack's recorded `charge_date`, CF-10 harness recorded dates, INV-B04 on calendar-dated rows, per-site dates in the new harness.

### 7.8 Privacy

Harness fixtures reuse production guests and boot with the production `.env`. The no-env driver is mandatory, and every log is scanned for phone, email and guest-name fields **immediately before each commit**. Counts only are reported.

### 7.9 Pack

`verification/evidence/<date>_k7_phase_3_1/` with the implementation and verification report, `RESULT.json`, the pre-registered expectations, the harness, logs, and the declared-delta list. The report names the tested commit.

## 8. Gate validation (G3, G6, G10)

| Gate | Condition this unit addresses | What 3.1 completion provides | What stays open |
|---|---|---|---|
| **G3** | "business-date dating at all writers (K-7)" | Closes the K-7 item (GT-D1) through C-1…C-7 | The rest of G3: release tag and pack at the tag; the Q17/Q20 scope question (GT-D13) |
| **G6** | C1 single derivation; C2 no wall-clock financial dating | Evidence for C1 (BR-1, BR-5) and C2 (C-1, C-3) | **C3** close/reopen/interrupted-close; **C4** staleness escalation (3.6); **C5** N7 multi-day sequence. 3.1 does not pass G6 |
| **G10** | regression at the change | Battery at the K-7 commit with declared movement only; production anchor unchanged | Golden Master recapture and the SC-1 anchor record (GT-D8) are separate; Golden Master cannot prove K-7 |

Gates A–H are not used (K7-D1). B-1 is not an entry condition for this unit (K7-D1).

## 9. Process and stop points

1. Branch `k7-phase-3-1`, in a worktree, from the activation commit.
2. Commit 1 (if needed): the Founder activation reference. Commit 2: code only, in the files listed in §6. Commit 3: the evidence pack, naming the tested commit.
3. **STOP** after the evidence report. Not authorized: push, merge, tag, deployment, production start, database modification outside disposable copies, migration, business-date change, trading.
4. **Deployment is a separate act.** In this installation `SukoonPMS/` is both the live folder and the `main` checkout, so a merge of K-7 changes the live code at rest, and the new behaviour runs at the next application start. That start, any business-date advance, and the sequencing between them need their own PD-004 authorization (K7-D8, BD-D1…BD-D5). Neither is part of this unit.

## 10. Interactions and hazards (FACT unless marked)

| Topic | Position |
|---|---|
| SR-1 / INV-B06 | No dependency on the integrated reading. A correction or refund inherits its origin's verdict and its own date is not checked, so moving their dates to the business date cannot change INV-B06 for rows that have an origin (SR-1 scenarios S-09 and APP). Rows with no resolvable origin (R-1) are judged on their own date. W-11 `settlement` redemption before arrival already violates INV-B06 under either basis (P-3). Charges (W-17, W-20) are outside INV-B06's population |
| Stale production business date | While the date is 2026-08-10, every in-scope row would date 2026-08-10. That is a separate production decision (BD-D1…BD-D5) and is not made here. INV-B06 does not exempt staleness (Round 10 item 6) |
| D11 rows and Q06-H1 | Untouched. Tested by N-5 |
| DQ56-R1 guard | `app/reports.py` and two night-audit templates carry the guard. K-7 is not expected to touch them; the guard tests are in the battery |
| Notification flush | Harness boots must never start the scheduler against credentials. Use the no-env driver |
| Close-path divergence | Not changed by K-7. See K7-D10 package |
| Voucher liability | Production holds 0 vouchers and 0 redemptions (`20260930_adr011_production_application/prod_post_state.json`; DB byte-identical since). No existing liability changes under any K7-D4 option |

## 11. Residuals

| Residual | Position |
|---|---|
| DDL defaults | **Corrected finding (F-4, C-1):** production's `credit_vouchers.issued_date` is `DATE NOT NULL` with **no** DDL default; `payments.payment_date`, `extra_charges.charge_date` and `business_date.current_date` have none either. The `DEFAULT (date('now'))` (`app/__init__.py:1794`) and `DEFAULT CURRENT_DATE` (`:1577`) DDL exist only in code that creates fresh tables. The DDL is left unchanged |
| Seed | `app/__init__.py:1850-1851` and `app/models.py:106` unchanged (F-2). The G11 day-one procedure must set the date explicitly |
| Complete and Reopen silent skips | `app/reports.py:3121-3125` and `:3225-3229`: **residual Phase 3.2 / 3.4 items** (F-3). Not changed, not tested for changed behaviour |
| Voucher issuance while stale | an operating rule, not a code guard (BR-11) |
| Everything in §3.3 | unchanged unless a concrete dependency is demonstrated and the Founder rules |
