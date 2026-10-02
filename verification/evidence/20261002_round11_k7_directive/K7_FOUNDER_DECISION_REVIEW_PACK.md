# K-7 FOUNDER DECISION REVIEW PACK

| | |
|---|---|
| Prepared | 2026-10-02, at `main` = `origin/main` = `0938069`; Round 11 pack at `round11-k7-directive` `545eae1` |
| Status | **Review material. Not committed, not pushed. Nothing here is a decision or an activation.** `FG-P3-1-K7-DIRECTIVE-01` stays a DRAFT |
| Not done | No directive activated, no code, no tests run, no push, no merge, no application start, no production access, no business-date change |
| What was read | Source files at `0938069`; the committed Round 8-11 records; the verified recovery point `pms_20261002_093338_dq56-apply-pre.db` (SHA-256 `5c78edb2…`, a copy of production at 09:33, byte-identical to production since). That copy was opened read-only and immutable and queried for **counts and schema text only**; no guest data was read or printed |
| Labels | **FACT** read in code or a record at `0938069`. **COPY** read from the recovery-point copy. **ANALYSIS** inference. **RECOMMENDATION** my suggested answer; the decision is yours |

---

## 0. The short version

- **Nothing in BD-D1 to BD-D5 gates K-7.** They gate the first application start with K-7 code *and trading*, and the date remediation itself.
- To activate the directive you need: the K7-D4 voucher answer (F-1), your answers to F-2 to F-6 (each has a default reading I can proceed on), and acceptance of three small corrections to the draft (§2.7). Two of those corrections come from facts I found in this review.
- The seven governance-record gaps are drafted in §4 as proposed append-only entries. They are not gating.
- Two findings in this review change earlier statements. **The production `credit_vouchers` table has no DDL default** (so the UTC-default hazard I described does not exist on production). **A voucher's stored status is rewritten on read** (so the expiry basis has a data-mutation side, not only a date side).

---

## 1. K7-D4: voucher issue date, expiry anchor and expiry test

### 1.1 What the code does (FACT, `0938069`)

| Element | Site | Behaviour |
|---|---|---|
| Issue date | `app/services.py:1965` | `issued_date=_d.today()` (calendar) |
| Expiry anchor | `app/services.py:1950` | `today + expiry_days`; the cancellation path passes 365 (`:1854`) |
| Status derivation | `compute_voucher_status` `:1992-2011` | `expired` if `expiry_date < _d.today()` (`:2009`) |
| **Status is stored and rewritten on read** | `refresh_voucher_status` `:2014-2037` | If the derived status differs from the stored one, it **writes** it: sets `status` and `expired_at` (`:2025-2026`, a UTC technical timestamp) and, if an audit writer is passed, an audit row. It runs on redemption (`:2073`, and again after the redemption row is added, `:2146`), on the voucher lookup API (`app/routes.py:9420`) and on **opening the voucher ledger report** (`app/reports.py:6463`, followed by a commit) |
| Redemption guard | `redeem_credit_voucher` `:2050-2078` | refreshes status (`:2073`), refuses unless `status == 'active'` (`:2075`), **then repeats the calendar test** at `:2077` |
| Report | `voucher_ledger` `app/reports.py:6469`, `:6497` | `days_left` computed against the **business date** |
| Displays | `app/templates/reports/voucher_ledger.html`, `app/templates/tabs/reservations.html:4374`, `app/routes.py:9431-9432` | print `issued_date` and `expiry_date`; no logic |
| Redemption payment (W-11) | `:2116` | moves to the business date under K-7 whichever option is chosen |
| Voucher code, `redeemed_at`, `expired_at` | `:1928-1932`, `:2138`, `:2026` | identifier or UTC technical timestamp; unchanged |

Production holds **0 vouchers and 0 redemptions** (COPY). No existing liability changes under any option.

Two consequences of those facts that the earlier package did not state:

1. **The two expiry tests must move together.** `:2009` decides the stored status; `:2077` is a second, independent calendar test applied after it. If only one is changed, a voucher can show `active` and still be refused with "Voucher expired on …" (or the reverse).
2. **A basis choice decides when the stored status flips and when `expired_at` and any audit row are written.** The flip happens in a read path (the report), so merely opening the ledger can change data. The recompute is symmetric: if the derived status goes back to `active`, the next refresh writes `active` again (`expired_at` is not cleared). By the same reading, a voucher force-expired through the admin route (`expire_credit_voucher` `:2166`, `app/routes.py:9499-9502`) is flipped back to `active` by the next refresh unless its date has passed. That is existing behaviour, read from the code and **not run**, outside K-7, and recorded here as a defect candidate.

### 1.2 The alternatives

| | Issue date | Expiry anchor (issue + 365) | Status and redemption tests | Sites |
|---|---|---|---|---|
| **A. Business date throughout** | business date | business date + 365 | business date | `:1950`, `:1965`, `:2009`, `:2077` |
| **B. Business-date issue, calendar validity** | business date | calendar today + 365 | calendar | `:1965` |
| **C. Business-date issue and anchor, calendar test** | business date | business date + 365 | calendar | `:1950`, `:1965` |
| **D. Voucher dates outside K-7** | calendar | calendar | calendar | none. This contradicts K7-D2, which names `issued_date` and the anchor. Shown only for completeness |

### 1.3 Consequences

**With the date stale (lag L = +53 today).** A 365-day voucher issued on calendar 2026-10-02 while the business date is 2026-08-10:

| | `issued_date` | `expiry_date` | Redeemable until | Versus today's behaviour (expiry 2027-10-02) |
|---|---|---|---|---|
| A | 2026-08-10 | 2027-08-10 | the business date passes 2027-08-10 | If the lag later closes to 0 this is **53 calendar days shorter**; if the date stays stale it never expires in calendar time |
| B | 2026-08-10 | 2027-10-02 | calendar 2027-10-02 | none; the record spans 418 days |
| C | 2026-08-10 | 2027-08-10 | calendar 2027-08-10 | **53 days shorter**, silently |

**With the date current** (manual closes; the lag is -1, 0 or +1 depending on whether the close is before midnight, at midnight or after). A voucher issued at 00:30 on calendar D+1 while the business date is still D: A and C expire one day earlier than today; B does not. A redeems through the business day D+365 even after calendar midnight, until that day is closed.

| Dimension | A | B | C |
|---|---|---|---|
| Status, redemption, report agree with each other | **yes** | no (report differs by L) | no |
| Dates inside one record on one basis | yes | no (expiry − issue = 365 + L) | no |
| Stored-status flip follows | the business date | the calendar | the calendar |
| Fit with FD-013 / AR-008 (no silent `date.today()` in financial logic) | consistent | an explicit exception, if recorded | an implicit exception |
| Code and proof | 4 sites; V-1…V-4 on the business date | 1 site | 2 sites; shortened validity on the declared-delta list |

### 1.4 The interaction that decides how much this matters

The difference between A and B is large only while vouchers are issued with a lag. A voucher exists only after a cancellation with a credit-voucher disposition (`app/services.py:1850`). If **no trading happens until the business date is current** (BD-D1 below), the A/B gap is at most one day. If vouchers could be issued while the date is stale, A and C carry the 53-day shortening above.

### 1.5 ANALYSIS and RECOMMENDATION

- **A** is the only option under which the status, the redemption test, the stored record and the report agree, and it matches the stated intent of K-7. Its visible cost appears only if a voucher is issued while the date is stale.
- **B** gives guests exactly 365 calendar days regardless of the operating date, at the cost of one recorded exception and a standing mismatch with the report.
- **C** is not recommended under any reading.
- **RECOMMENDATION: A**, conditional on the standing rule that no voucher is issued while the business date is stale (which is already implied by "no trading while stale"). If you want guest-facing validity pinned to calendar days, choose B and record it as a deliberate exception.

**Answer needed:** A, B, C, or an amendment (different `expiry_days`, stated exception). Inclusive expiry day is preserved by every option (a voucher is expired only when `expiry_date` is strictly before the test date).

---

## 2. F-1 to F-6: exact readings and consequences

F-1 is K7-D4 above.

### 2.1 F-2: the business-date seed

**Reading (FACT).**
- `init_data()` runs on every application start (`app/__init__.py:528`). It inserts `BusinessDate(current_date=date.today())` only when `BusinessDate.query.first()` is empty (`:1850-1851`).
- The only code that creates a `BusinessDate` row is that seed. `app/models.py:106` has `default=date.today` but nothing inserts a row without a value.
- Production has the row, 2026-08-10 (COPY), so the seed never runs there.
- The calendar is therefore used exactly once, when a database with no row is first started.

| Answer | Consequence |
|---|---|
| **(a) Leave as read (the draft's reading)** | K-7 changes nothing here. Fail-closed BR-1 is reachable only if the row is deleted or the database is empty before `init_data()`. The G11 fresh-install and day-one procedure must set the date explicitly, as the gate text already requires ("set the business date") |
| (b) Rule it in | The seed would need an operator-supplied date, and a start with no row would refuse to boot. That redesigns fresh install and the day-one procedure (DQ-40, G11), which is not a dating fix |

**RECOMMENDATION: (a).**

### 2.2 F-3: direct readers of the business-date row

**Reading (FACT).** `get_business_date()` has 115 call sites in `app/`. Besides it, the row is read directly in these places. They differ in what happens when the row is absent:

| Site | If the row is absent | Substitutes a date? |
|---|---|---|
| `app/services.py:620` `get_business_date()` | returns `date.today()` | **yes** (BR-1) |
| `app/routes.py:4769-4770` night-audit view | `date.today()` | **yes** (BR-5) |
| `app/occupancy_engine.py:78-87` | `date.today()` on any exception | **yes** (BR-5) |
| `app/kpi_command_center.py:72` | `date.today()` when `ctx` lacks it | **yes** (BR-5) |
| `app/services.py:302-306` `run_night_audit` | **returns silently**, no log | no |
| `app/reports.py:3121-3125` Complete | `if bd and …`: the day is marked Completed and the date is **not advanced**, silently | no |
| `app/reports.py:3225-3229` Reopen | skips the roll-back silently | no |
| `app/reports.py:3557-3560` Force Close | flashes "Business date record not found." and returns | no (already refuses, with a message, no log line) |
| `app/ceo_kpis.py:392-394` | shows no date (`None`) | no |

The four substituting sites are in the directive. The silent ones are not.

| Answer | Consequence |
|---|---|
| **(a) Leave the silent ones** (the draft's reading) | K-7 stays in the files named in the directive. `reports.py`, which carries the DQ56-R1 guard and the close paths, is not touched. A missing row would still let Complete mark a day Completed without advancing the date |
| **(b) Add a logged error to `run_night_audit` only** | One log line and the existing `return`, in `services.py`, which K-7 already edits. No behaviour change |
| (c) Convert all three silent paths to logged-error refusals | Honours K7-D3 literally for every direct reader, but puts `reports.py` (two sites) and the close paths in scope. The DQ56-R1 guard tests join the battery, and it crosses into K7-D10 territory. It needs the concrete-dependency finding the directive requires, and none exists |

Reachability for all of this: the row is absent only if deleted or before `init_data()` runs (see F-2). **RECOMMENDATION: (b)**, and record the Complete and Reopen sites as residuals for units 3.2 and 3.4.

### 2.3 F-4: the DDL default for `credit_vouchers.issued_date`

**Correction to the draft.** The draft says the production column has the UTC default `DEFAULT (date('now'))`. **It does not.** The recovery-point schema (COPY) reads:

| Column on production | Declared |
|---|---|
| `credit_vouchers.issued_date` | `DATE NOT NULL`, no default |
| `payments.payment_date` | `DATE`, no default |
| `extra_charges.charge_date` | `DATE`, no default |
| `business_date.current_date` | `DATE NOT NULL`, no default |

**Reading (FACT).** The `DEFAULT (date('now'))` and `DEFAULT CURRENT_DATE` DDL exists only in code, for fresh SQLite tables (`app/__init__.py:1794`) and PostgreSQL migration 9.0.0 (`:1577`). There are no raw SQL inserts into `credit_vouchers`, `payments` or `extra_charges` in `app/` or `tools/` (only fixtures in `tools/test_restore_db.py` on a temporary database). The ORM always supplies the value.

On production, an insert that omitted `issued_date` would fail `NOT NULL`, not take a UTC date; omitting the payment or charge date would store NULL.

| Answer | Consequence |
|---|---|
| **(a) Leave the DDL (the draft's reading, with the corrected facts)** | No schema change. The harness proves the default is never used by inserting through the ORM on the production-copy schema (expect a Python-supplied business date) and on a freshly created table. K-7's BR-4 makes the ORM default resolve the business date or raise |
| (b) Change the column defaults | A schema change: B-3/B-4 and PD-004. Not proposed |

**RECOMMENDATION: (a).** Fix the directive text (§2.7, C-1).

### 2.4 F-5: how a failed lookup shows in read-only displays

**Reading (FACT).** BR-1 makes `get_business_date()` raise when the row is absent. Its 115 callers will all raise in that situation, whether or not the three display fallbacks are changed. The fallbacks differ only in what they do beyond that:

| Site | What it feeds | Today on failure | After BR-1 / BR-5 |
|---|---|---|---|
| `routes.py:4769` night-audit panel | the default audit date and the `bd` template value | calendar date shown as if it were the business date | an unhandled exception goes to the app-wide 500 handler (`app/__init__.py:341`) with a logged error |
| `occupancy_engine.py:78-87` | one label, `'business_date'`, in the occupancy payload (`:387`). The counts do not use it. The wrapper swallows **every** exception | calendar label | must stop swallowing. Raising would fail every module that builds the payload (eight modules import it); returning `None` with an ERROR log keeps the counts and labels the date unavailable |
| `kpi_command_center.py:72` | aging of receivables over 30 days | calendar | its route already passes `get_business_date()` and sits in a `try` that logs and returns the existing JSON error (`command_center_data`, `routes.py:6054-6068`), so a missing date already yields a logged error envelope |

| Answer | Consequence |
|---|---|
| **(a) Occupancy label = `None` plus ERROR log; the other two propagate** | The smallest blast radius and still fail-closed for any figure derived from the date. Needs a one-line definition of the "unavailable" label |
| (b) Propagate everywhere | Simplest. A missing row turns every occupancy-based dashboard into an error, for a label |
| (c) A degraded read-only mode | Outside K-7 |

**RECOMMENDATION: (a).**

### 2.5 F-6: authorization boundary for the result

**Reading (FACT).**
- `SukoonPMS/` is both the live folder and the `main` checkout (`git worktree list`). The earlier fast-forwards changed live files at rest while the application stayed stopped.
- Merging K-7 therefore replaces live application code. It takes effect at the **next start**.
- The directive stops after the evidence report; push, merge, tag and deployment are not authorized.
- SR-1 precedent: branch local until a separate authorization; a fresh gate re-run before the push; fast-forward only.

| Answer | Consequence |
|---|---|
| **(a) Activation authorizes implementation and evidence on a local branch only** (the draft) | Matches SR-1. You review the evidence, then authorize push and merge separately |
| (b) Also authorize pushing the branch (not `main`) | The work is backed up remotely during review. `main` and the live code are unaffected. Costs one more line in the entry |
| (c) Pre-authorize push and merge after the gate re-run | Not recommended: a merge replaces live code and you have not seen the evidence |

Deployment (the first start with K-7 code, and any business-date advance) stays a separate PD-004 act under every answer. **RECOMMENDATION: (a)**, or (b) if you want the remote copy.

### 2.6 F-1

See §1. Needed for the voucher sites and tests only.

### 2.7 Corrections I propose to the draft directive (to be applied at activation)

| # | Where | Correction |
|---|---|---|
| C-1 | §5 F-4 and §11 | Replace the claim that the production column carries a UTC default with the §2.3 facts: no DDL default on production; defaults exist only in fresh-table DDL |
| C-2 | §3.1 and §4 BR-9 | State that `compute_voucher_status` (`:2009`) and the repeated test at `:2077` must follow the same basis, that `refresh_voucher_status` persists the stored status and `expired_at`, and that the ledger report refreshes on read. Add a test that opening the report under each basis flips status exactly when the confirmed basis says so |
| C-3 | §5 F-3 and §3.2 | Replace the two-reader list with the §2.2 table and carry the F-3 answer into BR-5 |

---

## 3. BD-D1 to BD-D5

### 3.1 What is now verified about production (COPY, plus the committed record)

| Fact | Value |
|---|---|
| Business date | 2026-08-10 (one row). 53 days behind on 2026-10-02, and +1 for every calendar day that passes |
| Closed days | one: 2026-08-09, `Completed`, `snapshot_valid=1`, with **5** historical reopen records, all for 2026-08-09 |
| Reservations | 4, **all `CheckedOut`**: none `CheckedIn`, none `Reserved` or `Confirmed`. Three have `arrival_date` ≥ 2026-08-10 (they are the D11 stays) |
| Shifts | 0 |
| Settings | `night_audit_enabled='false'`, `night_audit_time='02:00'`, `noshow_fee_enabled='false'` |
| `notification_queue` | 4 rows, **all `failed`**. The flush selects only `pending` rows with attempts below the maximum (`app/notifications.py:216-218`), so **it has nothing to send** |
| Vouchers and redemptions | 0 and 0 |
| Open-day content (committed, `FOUNDER_DECISIONS.md:47-56`) | the D11 rows payments 3, 4, 5, 6 and extra charge 2: ₹3,100.00 + ₹95.24 = ₹3,195.24, all dated 2026-08-10 |

This resolves two items the earlier pack listed as NOT VERIFIED: the queue holds no pending messages, and there are no in-house or reserved stays. It does not resolve whether a quiet day passes the close checks (`can_close`), which needs a copy run.

### 3.2 What gates what

| Decision | Gates K-7 activation | Gates K-7 code and evidence | Gates K-7 merge | Gates the first start with K-7 code | Gates the date remediation | Gates trading / G11 / G6 |
|---|---|---|---|---|---|---|
| BD-D1 when | no | no | no | **yes** (K7-D8: no trading while stale) | it is the decision | yes |
| BD-D2 mechanism | no | no | no | no | **yes** | yes (procedure text) |
| BD-D3 D11 close | no | no | no | no | **yes** (every application path closes the open day) | yes (G12 D11 verdict) |
| BD-D4 target, timing, interim rule | no | no | no | indirectly (pre-K-7 closes before midnight date rows into a sealed day) | **yes** | yes |
| BD-D5 authorization and rehearsal | no | no | no | **yes** (any start) | **yes** | yes |
| K7-D10 close path | no | no | no | no | informs BD-D2 | yes (procedure) |

**K-7 can be activated, implemented and evidenced with none of BD-D1 to BD-D5 decided.** The merge replaces live code at rest and starts nothing.

### 3.3 BD-D1: whether and when the date is brought current

**Key finding (ANALYSIS).** The number of closes is fixed by the date you start trading. Closing now, then not running the application, only leaves the date stale again tomorrow. Advancing early buys nothing unless the application runs a close every day afterwards.

| Option | Consequence |
|---|---|
| (a) Now | 53 closes now, and the lag restarts the moment the application stops. Useful only to produce evidence early. Mutates production for no operating benefit |
| **(b) As the first act of the first trading day (the G11 day-one procedure)** | The count is whatever the lag is that day; the rehearsal on a copy uses the same count. No exposure in between |
| (c) After units 3.5 and 3.6 exist | Same as (b) with interrupted-close recovery and staleness escalation in place first. The FD-P2-05 first-release controls |
| (d) Stale and trade | Not supported. 16 writers date 2026-08-10, 8 date on the calendar, INV-B04 and INV-B06 fire, walk-ins are dated August (`K7_PRODUCTION_RISK.md` §1) |

**RECOMMENDATION: (b) or (c)**, with a copy rehearsal long before. Either satisfies K7-D8 and the one binding rule: **no trading, and no voucher issued, while the date is stale.**

### 3.4 BD-D2: mechanism

On the verified production state there are no in-house or reserved stays, no shifts and no no-show fee, so the two operator close paths would post **no ledger rows** for any of the 53 dates. The choice affects logs, snapshots, effort and risk, not the ledger.

| Mechanism | What it writes | Notes |
|---|---|---|
| **B53 panel Run + Complete per date** | 53 `NightAuditLog` rows, 53 hashed snapshots, the date row; no charges, no payments, no audit rows | Existing UI, FD-P2-05 manual model. Whether Complete alone suffices without Run is NOT VERIFIED (Complete creates a Pending log if none exists). The panel has **no calendar guard**: nothing stops closing today's date or beyond (§3.6) |
| A53 `run_night_audit` per date | the same logs and snapshots, plus rent and no-show effects that are empty here | No rendered form; direct POST only; stalls as `Pending` on any blocker and repeats are silently skipped |
| B1+D close 2026-08-10, then Force Close | one real close, then 52 `Skipped` rows with **no snapshots** and no audit row | Silences INV-B05; the panel itself says "emergency only" |
| D53 Force Close everything | 53 `Skipped` rows, including 2026-08-10 with the D11 rows | as above |
| S direct SQL | no `NightAuditLog` rows | ungoverned; INV-B05 gap |

**RECOMMENDATION: B53**, preceded by a copy rehearsal that measures rows, snapshot size, time and per-day `can_close`.

### 3.5 BD-D3: closing the day that holds the D11 rows

Closing 2026-08-10 does not change payments 3 to 6 or extra charge 2, but it seals them into a hashed snapshot and locks the day. FD-010 says "No night-audit modification is authorized" for these rows; FD-P2-03 says the ruling "does not authorize financial mutation". Whether a close counts is unruled.

| Option | Consequence |
|---|---|
| (a) An ordinary close is permitted and is not a modification | Simplest. No special evidence |
| **(b) Permitted only with the D11 rows named by identity in the close evidence as the declared exception** | Keeps the sealing observable and auditable; the rows themselves are unchanged |
| (c) Not permitted | The day stays open, and **no later day can be closed by the panel or the service**, because each advances only from the current date. Only Force Close or SQL remains. This blocks go-live until the D11 disposition is ruled (the G12 D11 question, DQ-44) |

**RECOMMENDATION: (b).**

### 3.6 BD-D4: target date, time of day, interim rule

**Reading (FACT).** Run and Complete contain no reference to the calendar (`app/reports.py:2856-3140`, no `today`). Complete advances the date whenever `bd.current_date == audit_date` (`:3124-3125`). Nothing prevents closing the current calendar day, which would put the business date a day **ahead** of the calendar. Only Force Close stops at today (`:3595`). So the target is procedural.

- **Close after midnight (target = calendar date of execution):** the date is current during the day. Until K-7 is deployed, wall-clock rows are dated correctly during trading.
- **Close before midnight:** the date moves ahead while the calendar day is still running. Before K-7, a correction, refund, redemption, overstay or checkout extra posted before midnight is dated into the day just sealed (the F-AHEAD case; INV-B01/B03 exposure). After K-7 this is harmless for the writers.
- **Interim staleness rule until unit 3.6:** no software control exists (B-10 #5). A written rule is the only option, for example "no trading when the business date differs from the calendar date".
- **Job windows to avoid during a session** (FACT, `app/__init__.py:540-597`): the daily backup at 03:00, the log-pruning job at 04:00 (deletes webhook and notification logs older than 90 days), predictive maintenance at 05:00, plus the notification flush every 5 minutes. Their triggers are in-memory cron schedules, so a session that does not span those clock times does not run them.

**RECOMMENDATION:** target = the calendar date of execution, closes performed after midnight, the written interim rule above, sessions kept clear of 03:00-05:00.

### 3.7 BD-D5: authorization, rehearsal and evidence

| Item | Status |
|---|---|
| Authorization path: PD-004, PD-005, FD-P2-04 conditions 1-7, 9, 10 | required |
| Full rehearsal of the chosen mechanism on a copy at the code that will run | recommended: yields N7 and G11 multi-day evidence |
| Pending notifications | **none**: all four rows are `failed` (COPY); re-check immediately before any start |
| In-house or reserved stays | **none** (COPY); re-check |
| Open shifts | none (COPY) |
| `noshow_fee_enabled` | `false` (COPY) |
| Per-day `can_close`, including 2026-08-10 | NOT VERIFIED; needs the copy run |
| Fresh backup and restore rehearsal | the existing recovery point reflects production as of 09:33 on 2026-10-02; a **new** one is needed immediately before the operation (FD-P2-04) |
| Encrypted off-box copy (condition 11) | NOT VERIFIED (G8) |
| Start side effects | the five jobs above; the session window rule in §3.6 |

**RECOMMENDATION:** option (a) of BD-D5 in the earlier package (PD-004 + PD-005 + FD-P2-04 + full copy rehearsal).

### 3.8 Two workable sequences (neither is decided here)

| | S1: K-7 first | S2: date first |
|---|---|---|
| Order | K-7 evidence → push/merge (live code at rest, still stopped) → date remediation → trading | date remediation at `0938069` → K-7 evidence and merge → trading |
| K-7 meets the stale date | only if the application starts and trades before remediation, which the rule forbids | never |
| Rehearsal code | rehearse the remediation at the K-7 code that will run | rehearse at `0938069` |
| Effort and risk | the K-7 work proceeds immediately; the production operation is done once, at go-live timing | produces an early production mutation that goes stale again |
| Fit with §3.3 | **matches (b)/(c)** | matches (a) |

Both obey "no trading while stale". **RECOMMENDATION: S1.**

---

## 4. Proposed append-only entries for the seven governance-record gaps

**DRAFT. Not committed, not appended.** `FOUNDER_DECISIONS.md` is append-only, so each is written as an entry you can adopt, amend, or reject. I cannot supply a Founder statement I do not have: where the authorization text was given in a session I cannot see, the line is marked **[FOUNDER TO SUPPLY]**. Facts are from committed evidence or from this session.

Suggested wrapper for one round: `# Founder Resolution Round 12 — governance record entries — FG-P2-FOUNDER-RESOLUTION-20261002-05`, `Kind: governance record, no new decision`.

### G-1: SR-1 readings R-1 to R-4

> **R12-G1 — Founder confirmation of SR-1 implementation readings (recorded verbatim, line breaks collapsed; given in session, 2026-10-02).**
> "I confirm the following four SR-1 implementation readings: R-1: If a correction/refund has no resolvable originating transaction, judge it by its own date under the general INV-B06 window. R-2: Identify cancellation refunds using the governed SR2-REV2 lineage definition: exactly one reservation points to the refund; it is that reservation's own refund; disposition is refund_full or refund_partial; cancellation_processed_at is present; amount agreement is NOT part of lineage. R-3: A correction of a voided original inherits that original's INV-B06 verdict. The void exclusion applies to the cancellation refund's advance set. R-4: Keep the existing commissioning negative seed unchanged. Per-class negative coverage remains in the scenario suite. These four readings are now founder-approved."
> Effect: confirms the readings listed in `20261002_sr1_inv_b06/SR1_INV_B06_IMPLEMENTATION_REPORT.md` §4. No other effect.

### G-2: SR-1 push and merge

> **R12-G2 — Authorization of the SR-1 push and fast-forward (recorded verbatim; given in session, 2026-10-02).**
> Round 10 recorded: "No production changes, no merge to main, and no deployment are authorized by this directive." The Founder subsequently authorized, in session: "Phase 3 — push SR-1 branch. If all checks pass, push: sr1-inv-b06 → origin/sr1-inv-b06. Do not modify main yet. Phase 4 — integration. After verifying the remote branch exactly matches 0938069, fast-forward main only: e310c66 → 0938069. No squash, no rebase, no force push, no cherry-pick." and, in the later message, "This is an execution authorization for SR-1 only. Do not start K-7, do not start the production app, and do not modify production data." and "Fast-forward main only: e310c66 → 0938069. Then push main."
> Executed: `sr1-inv-b06` pushed (`0938069`); `main` fast-forwarded and pushed (`e310c66..0938069`), 6 commits, no merge commit. Gate re-run before the push: 28/28, control 18/28, regression with no verdict difference.

### G-3: DQ-56 controlled production start

> **R12-G3 — Authorization of the DQ-56 R1 controlled production start.**
> Round 9 recorded: "Do not start the live application until I separately authorize the production-start step." The authorization is cited in committed evidence (`20261002_dq56_r1_production_start/DQ56_PRODUCTION_APPLICATION_REPORT.md`) as `"AUTHORIZE DQ-56 R1 PRODUCTION START"`, Founder, 2026-10-02 (session): start the live application once with the existing production environment, solely to activate and verify R1; read-only verification; stop afterwards; no login, transaction, night audit, Run, Reopen, Complete or other work. **[FOUNDER TO SUPPLY the verbatim text, or confirm that the quotation above is the authorization.]**
> Executed: one start 09:43:38-09:44:13 (about 35 seconds); R1 loaded; database byte-identical; no migration, data change or guest message; stopped.

### G-4: SR-2 push and merge (DQ-06 / GT-D4)

> **R12-G4 — Authorization of the SR-2 push and integration.**
> Round 7 recorded "Push and merge remain separately unauthorised". `origin/main` contained the six SR-2 commits (`6488075` … `c9eeff0`, 2026-09-30 to 2026-10-01) before the Round 8 work. **[FOUNDER TO SUPPLY whether this was authorized, by what words, and when.]** Options: (a) record the authorization with its date and scope; (b) record that it was not authorized and direct a remedy (a mutating act needing its own authorization); (c) record ratification after the fact.

### G-5: GT-D10

> **R12-G5 — Record of three in-session authorizations and closure of the carry-forward items.**
> (1) ADR-011 migration 10.0.0, cited in committed evidence as "Founder authorization in session, 2026-09-30: 'controlled application of ADR-011 migration 10.0.0 to production, subject to PD-004/PD-005 controls'" (`20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:10`). (2) The CF-10 / CF-11 implementation, cited as the "autonomous continuation directive of 2026-09-30" (`20260930_cf10_completion/CF10_COMPLETION.md:8`). (3) The Q06-H2 forward fix (`60abea6`). **[FOUNDER TO SUPPLY verbatim text for (1) and (2), and to rule whether CF-10, CF-11 and Q06-H2 are closed with the evidence paths named in the packs.]**

### G-6: GT-D3 for INV-D02

> **R12-G6 — Phase 6 carve-out for INV-D02.**
> Round 10 item 5 recorded FD-P2-06 as the carve-out for INV-B06 only. SR2-RULE and SR2-REV2 (Rounds 6 and 7) changed INV-D02 semantics without an overlay. **[FOUNDER TO RULE]** Options: (a) record that SR2-RULE and SR2-REV2 are Founder-ruled constitutional amendments under Master Plan §07 Layer 1, excepted from Phase 6 "Not touched: invariant semantics" for INV-D02 only; (b) place invariant refinements outside Phase 6 as a standalone directive class; (c) leave the conflict on record. No `MASTER_PLAN.md` text is edited under any option; an appended overlay would be a separate commit.

### G-7: the three DQ-56 evidence commits that entered `main` with SR-1

> **R12-G7 — Ratification of the DQ-56 evidence commits integrated with SR-1.**
> The commits `7f19d54` (pre-start gate report), `2e19974` (controlled-start record), `28e6b63` (JSON escape fix) were committed locally on `dq56-q06h1-guard`, with the report stating "Pushing them is for the founder to authorize; they contain evidence only". They entered `origin/main` in the six-commit fast-forward described in R12-G2, whose commit list the Founder named. **[FOUNDER TO CONFIRM]** that the authorization in R12-G2 covered them, or record otherwise.

---

## 5. Final checklist: Founder decisions required before `FG-P3-1-K7-DIRECTIVE-01` may be activated

Mark each; the default is what I will take if you reply "proceed with the recommendations".

| # | Decision | Needed to activate? | Options | Default (RECOMMENDATION) |
|---|---|---|---|---|
| 1 | **F-1 / K7-D4** voucher basis | yes, for the voucher sites (and so for activation unless you split the voucher work out) | A / B / C / amend | **A**, with the "no voucher while the date is stale" rule |
| 2 | **F-2** seed row | confirm | (a) leave / (b) rule in | (a) |
| 3 | **F-3** silent readers | confirm | (a) / (b) / (c) | (b) one log line in `run_night_audit`; Complete and Reopen recorded as residuals |
| 4 | **F-4** DDL default | confirm | (a) leave / (b) schema change | (a), with the corrected facts |
| 5 | **F-5** read-only display behaviour | confirm | (a) / (b) / (c) | (a) occupancy label `None` + ERROR log; the others propagate |
| 6 | **F-6** authorization boundary | yes | (a) branch only / (b) + push the branch / (c) pre-authorize merge | (a) |
| 7 | **Accept corrections C-1 to C-3** to the draft directive | yes | accept / amend | accept |
| 8 | **K7-D5** late-checkout disposition | no: ruled out of K-7 | calendar basis retained as ruled / deferred to a later B-10 directive | not needed for activation |
| 9 | Seven governance-record gaps (§4) | **no** | adopt / amend / reject each | dictate when convenient |
| 10 | **BD-D1 to BD-D5** | **no** | §3 | S1 sequence; decide near go-live planning |
| 11 | **K7-D10** close path | **no** | two alternatives | decide with BD-D2 and the daily-close procedure |

**Activation entry.** When items 1 to 7 are answered I would draft an entry of this shape, for you to approve before it is appended: "Round 12 (or 13) — activation of `FG-P3-1-K7-DIRECTIVE-01`. Base `<commit>`. Answers: F-1 = _, F-2 = _, F-3 = _, F-4 = _, F-5 = _, F-6 = _. Corrections C-1 to C-3 applied. Authorizes implementation and evidence on a local branch only. Not authorized: push, merge, tag, deployment, application start, production change, business-date change."

---

## 6. Limits of this review

- Production was not opened. Facts marked COPY come from the verified 09:33 recovery point, which is byte-identical to production's current hash. Nothing has been written to production since, so they describe it today. They are counts and schema text only.
- Not verified: whether Complete works without Run; per-day `can_close` for the 53 dates; encrypted off-box recovery; the verbatim text of authorizations given in sessions I cannot see (G-3 to G-5).
- Nothing was run against the application. Every behavioural statement is read from source at `0938069`.
