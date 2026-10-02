# K7-D4 — Voucher issue date, expiry anchor and expiry test: alternatives for Founder confirmation

| | |
|---|---|
| Prepared | 2026-10-02, at `main` = `0938069`. Analysis only |
| Instruction (Round 11) | "before implementation, present the exact alternatives and consequences for Founder confirmation. Do not silently choose a liability/expiry basis. Production currently has zero vouchers, so this does not block the present data state." |
| Status | **OPEN. Nothing is chosen.** The directive's voucher sites and tests V-1…V-4 wait for this answer. Every other part of the directive is independent of it |
| Used by | `K7_PHASE_3_1_DIRECTIVE.md` §3.1 (voucher rows), §5 item F-1 |

## 1. What the code does today (FACT, `0938069`)

| Element | Site | Basis today |
|---|---|---|
| Issue date | `app/services.py:1965` `issued_date=_d.today()` | calendar |
| Expiry anchor | `app/services.py:1950` `expiry = _d.today() + expiry_days`; the cancellation path passes 365 (`:1854`) | calendar |
| "Expired" status | `app/services.py:2009` `expiry_date < _d.today()` | calendar |
| Redemption refusal | `app/services.py:2077` `expiry_date < _d.today()` | calendar |
| Redemption payment date (W-11) | `app/services.py:2116` | calendar (moves to the business date under K-7 regardless of this decision) |
| Voucher ledger report `days_left` | `app/reports.py:6469` `today = get_business_date()`, `:6497` | **business date** |
| Voucher code `CV-YYYYMMDD-XXXX` | `app/services.py:1928-1932` | calendar; an identifier, unchanged |
| `redeemed_at` | `app/services.py:2138` | technical UTC timestamp, unchanged |

So today the report already measures time left on a different basis from the one that decides expiry. The difference is the **business-date lag** L = calendar date − business date.

Production: 0 vouchers and 0 redemptions (`20260930_adr011_production_application/prod_post_state.json`; the database is byte-identical to that state). **No existing liability changes under any option.** The choice governs vouchers issued from now on.

## 2. The alternatives

| | Issue date | Expiry anchor (issue + 365) | Status / redemption test | Sites changed |
|---|---|---|---|---|
| **A. Business date throughout** | business date | business date + 365 | against the business date | `:1950`, `:1965`, `:2009`, `:2077` |
| **B. Business-date issue, calendar validity** | business date | calendar today + 365 | against the calendar | `:1965` only |
| **C. Business-date issue and anchor, calendar test** | business date | business date + 365 | against the calendar | `:1950`, `:1965` |
| **D. Outside K-7** | calendar | calendar | calendar | none (this contradicts the K7-D2 ruling that names `issued_date` and the anchor; listed only to show consequences, and it would need the Founder to amend K7-D2) |

## 3. Worked consequences

Take a 365-day voucher and the real lag today, **L = +53** (calendar 2026-10-02, business date 2026-08-10).

| Option | `issued_date` | `expiry_date` | Last day it can be redeemed | Against what today's code gives (expiry 2027-10-02, calendar) |
|---|---|---|---|---|
| Today (no K-7) | 2026-10-02 | 2027-10-02 | calendar 2027-10-02 | n/a |
| **A** | 2026-08-10 | 2027-08-10 | while the **business date** ≤ 2027-08-10 | In calendar terms the voucher dies when the business date reaches it. If the lag has closed to 0, that is 2027-08-10, **53 days shorter** than today's behaviour. If the date stays stale it never expires in calendar time |
| **B** | 2026-08-10 | 2027-10-02 | calendar 2027-10-02 | Same expiry as today. The record reads 418 days between issue and expiry |
| **C** | 2026-08-10 | 2027-08-10 | calendar 2027-08-10 | **53 days shorter**, silently, and the printed expiry differs from the guest's calendar sense |

Steady state after the date is current and closes are manual. Close after midnight gives L = +1 between midnight and the close; close before midnight gives L = −1 afterwards. Take a voucher issued at 00:30 on calendar day D+1 while the business date is D:

| Option | `issued_date` | `expiry_date` | Effect vs today |
|---|---|---|---|
| A | D | D+365 | 1 day earlier; redeemable through the business day D+365 even after calendar midnight until that day is closed |
| B | D | D+1+365 | none |
| C | D | D+365, refused from calendar D+366 | 1 day earlier |

**Consistency with the report.** `voucher_ledger` already uses the business date. A makes status, redemption and report agree. B and C leave a gap of L days between the report and the decision, as today.

**Internal consistency of the record.** A: `issued_date`, `expiry_date` and every test share one basis. B: the dates are on different bases (expiry − issue = 365 + L days). C: anchor and test are on different bases, which is the combination the analysis flagged as the worst.

**What each option says about the controlled date.** A matches the FD-013 / AR-008 / ADR-004 intent that financial and operational logic does not silently use `date.today()`. B and C keep a calendar test in a financial decision; that can be a deliberate, recorded exception (guest-facing validity in calendar days) but it must then be written down as one, not left implicit.

**Redemption boundary.** A: refused only once the business date passes expiry, so a redemption made after calendar midnight on the expiry day, before that day is closed, is still accepted. B and C: refused from calendar midnight.

## 4. What each option costs to build and prove

| Option | Code | Tests |
|---|---|---|
| A | four sites | V-1…V-4 on the business date; the status function and the report agree (`days_left`) |
| B | one site | V-1…V-4 on the calendar; the report mismatch is a declared residual |
| C | two sites | as B, plus the shortened-validity case recorded in the declared-delta list |

Under every option the harness runs the boundary day on both sides under F-LAG and F-UTC, with the clock deliberately different from the business date (`K7_PHASE_3_1_DIRECTIVE.md` §7.2).

## 5. ANALYSIS (not a decision)

If the aim of K-7 is one controlled date, **A** is the consistent reading, and it is the only option under which the report, the status and the dated record agree. Its price is a visible one: while the business date is stale, vouchers are issued with an August issue date and an August-based expiry. That price disappears once the date is current and closes are nightly (steady-state difference at most one day). If the Founder wants a guest-facing validity of exactly 365 calendar days regardless of the operating date, **B** delivers that and is the smallest change, at the cost of an explicit recorded exception to single derivation. **C** is not recommended under any reading: it shortens validity by the lag without a rule that says so.

## 6. Answer requested

One of: **A**, **B**, **C**, or an amendment (for example a different `expiry_days`, or a stated exception). Also whether expiry on the boundary day should be inclusive of the day itself (the code today: a voucher is expired only when `expiry_date < today`, so the expiry day is still redeemable; every option above preserves that).
