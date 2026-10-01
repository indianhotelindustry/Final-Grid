# K-7 PRODUCTION RISK — behaviour if K-7 shipped while the business date is 2026-08-10

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, analysis only — nothing was run against production or a copy |
| Code | `C:/wtov` at `c9eeff0` (`app/` = live `c703150`) |
| Production facts (orchestrator, read-only, 2026-10-02 00:40 IST) | `business_date` = **2026-08-10** (updated 2026-08-11 12:42:48); calendar **2026-10-02** → **53 days** behind; `night_audit_enabled='false'`; application stopped; DB SHA-256 `21dc0e97…3e434` |
| Production facts (committed evidence) | the open day 2026-08-10 holds five of the eight D11 rows (payments 3–6, extra_charges 2) — `verification/FOUNDER_DECISIONS.md:47-56`; one `night_audit_logs` row (2026-08-09, Completed, sealed — Q06-H1 `:1219-1227`); 4 reservations, 0 shifts, 0 credit vouchers, 0 credit notes, 4 `notification_queue` rows — `verification/evidence/20260930_adr011_production_application/prod_post_state.json`; "production has none" (in-house stays) — `verification/evidence/20260909_phase1_verification_completion/Q14_PARITY.md:25`. Reservation statuses today: **NOT VERIFIED** |
| Assumed K-7 shape | "K-7 core" as framed in the 09-30 package §A6: the eight WC/MD writer sites and voucher issuance dated from `get_business_date()`; model defaults replaced; fallback decided. Late-checkout applicability, report ranges and documents only where stated |

**Status of the scenario:** NOT AUTHORIZED (K-7 implementation and deployment — `K7_ARCHITECTURE_ANALYSIS.md` §0). This document describes consequences so the Founder can decide sequencing; it does not recommend shipping.

---

## 1. Baseline: the stale date already governs 16 writers today

FACT: 16 of 24 writers already date rows from `get_business_date()` (`K7_WRITER_INVENTORY.md` §1). If the application were started today, unchanged, every advance, settlement, deposit, POS charge, CICO charge, tip, other-income, upsell and no-show fee would be dated **2026-08-10**.

FACT: walk-in check-in creates the stay **at the business date**: `arrival_date=business_date`, `departure_date = business_date + nights` (`app/routes.py:2407`, `:2477` in `walkin_checkin_new`; `:2714`, `:2732` in `walkin_full_checkin`; `:7393` in walk-in express `walkin_search_express`). New advance reservations are validated against the **calendar** (`validate_not_past`, `app/validators.py:101`, `app/routes.py:2153`).

ANALYSIS: the stale date is a production hazard **with or without K-7**. K-7 changes *how many* rows take the stale date (8 more sites + vouchers) and removes the wall-clock rows; it does not create the stale-date problem. Hazards that exist today without K-7:

| Today, no K-7 | Citation | Consequence |
|---|---|---|
| A guest walking in on 2026-10-02 gets a stay 2026-08-10 → 2026-08-1x | `app/routes.py:2407`, `:2477`, `:2714`, `:2732`, `:7393` | room nights, room tax lines (`app/gst_service.py:414` `charge_date=current` night) and occupancy dated in August |
| Late-checkout test is calendar ≥ departure; for that walk-in, departure is in August, so **every** checkout is "departure day or later" and the time-of-day slab applies | `app/routes.py:3206-3209`; F-7 `VERIFICATION_COMPLETION.md:117` ("a full night after the slab cut-off, because the calendar is 30 days ahead") | late-checkout fee charged on every such checkout after the slab time |
| Overstay (Hourly bookings only, `app/routes.py:8003-8005`) bills wall-clock hours since `departure_date + checkout_time`; with an August departure the elapsed time is weeks | `app/routes.py:8018-8048` | a very large overstay amount offered for posting |
| Every BD-dated payment for a stay arriving on/after 2026-10-02 is dated before arrival | INV-B06 `verification/invariants/rules_b.py:611-612` | INV-B06 VIOLATED on every advance/settlement (SR-1 interplay) |
| Calendar-dated rows (corrections, refunds, voucher redemptions, overstay, checkout extras) dated after the business date | INV-B04 `rules_b.py:395-404` ("no payment or charge is dated later than it"; CRITICAL / RELEASE) | INV-B04 VIOLATED by each such row |

---

## 2. Per transaction type: today vs K-7 shipped with the date stale

"Open day" = 2026-08-10 (the business date). "Its close" = the night audit for 2026-08-10, whenever it happens.

| Transaction | Today (no K-7) | K-7 shipped, date stale | What changes for the operator / books |
|---|---|---|---|
| Advance / settlement / deposit / credit recovery (W-01…W-07, W-12) | 2026-08-10 | 2026-08-10 | nothing — already stale |
| **Payment correction** (W-08/09; only via void of a payment in a **closed** day with Admin override, `app/routes.py:7844-7855`, `app/billing.py:421-433`) | calendar date (e.g. 2026-10-02) | 2026-08-10 | Production's only closed day is 2026-08-09, whose payments are D11 rows with `folio_id NULL`; Q-2 refuses their correction (`inherit_billing_folio_id`, `app/services.py:1221`; `FOUNDER_DECISIONS.md` Q-2). Practical change: none today. Later, corrections land in the open day instead of a future calendar day |
| Charge correction (W-22/23) | calendar | 2026-08-10 | NOT APPLICABLE — no caller in `app/` |
| **Cancellation refund** (W-10) | calendar (2026-10-0x) | 2026-08-10 | refund moves from a future, unclosed calendar day into the open day; it now appears in the 2026-08-10 close's refund totals and nets against advances dated the same day. Today it appears in no close until the business date reaches its calendar day |
| **Voucher issue** | `issued_date` calendar; expiry anchor calendar + 365 (`app/services.py:1950`, `:1965`) | `issued_date` 2026-08-10; expiry anchor depends on ruling (K7-D4) | see §4 — expiry may move **53 days earlier in calendar terms** |
| **Voucher redemption** (W-11) | calendar | 2026-08-10 | payment joins the open day |
| **Checkout extra** (W-17) | model default = calendar | 2026-08-10 | charge and its TaxLines (`app/gst_service.py:541`, `:563` copy `charge_date`) move into August |
| **Overstay** (W-20) | `now.date()` | 2026-08-10 | row and TaxLines move into August; billable-hours computation unchanged (physical time) |
| Late checkout (W-13 row) | row already 2026-08-10; applicability by calendar | row 2026-08-10; applicability **unchanged unless B-10 #2 is ruled in** | if ruled to business date: `2026-08-10 >= departure` is false for any reservation departing after the business date → **no late-checkout fee while the date is stale**; today the opposite (fee applies too often for August-dated walk-ins). Either way the stale date makes the rule wrong |
| Early check-in | time of day | unchanged | NOT APPLICABLE |
| No-show fee (W-14) | business date at close | unchanged | — |
| POS, CICO, tip, other income, upsell | 2026-08-10 | unchanged | — |
| Payment void (non-locked) | flag + `voided_at` UTC; counted by `date(voided_at)` (`app/night_audit_service.py:215-219`) | unchanged unless void mapping is ruled in | a void on 2026-10-02 is counted in the close of business date 2026-10-02, not 2026-08-10, while the voided payment itself is dated 2026-08-10 |
| Invoice | number year UTC; printed date = UTC checkout | unchanged unless B-10 #1 is ruled in | an October invoice lists payments and charges dated 2026-08-10 |
| Credit note | `issued_at` UTC only | unchanged | — |

---

## 3. Closed-day interplay

FACTS: a date is locked when its `NightAuditLog` status is Completed/Warning/Skipped (`app/services.py:1006-1017`). Only 2026-08-09 is locked on production. The services behind corrections, refunds, vouchers, overstay and checkout extras do not consult the lock (`K7_ARCHITECTURE_ANALYSIS.md` §5).

| Case | Today | K-7, date stale |
|---|---|---|
| Row dated into a closed day | possible when a close runs **before** midnight (calendar D, business date D+1): any WC/MD row posted before midnight is dated D, the sealed day → INV-B01/B03 exposure | not possible: the open business date is never locked |
| Row dated into a not-yet-reached day | every WC/MD row (2026-10-0x) — invisible to the open day's close; directly voidable without lock (`app/routes.py:7844`) until that calendar day is closed | eliminated |
| Size of the open day | 16 writers' rows since deploy + D11 rows 3–6, 2 | **24 writers' rows** since deploy + D11 rows. If the date is not advanced for weeks, the first close of "2026-08-10" seals weeks of real trading, the five D11 rows and every new row into one day and one hash |
| Reopen hazard (independent of K-7) | `night_audit_reopen` accepts 2026-08-09 while the business date is 2026-08-10 (`app/reports.py:3137-3140`, `:3186-3191`) and would flip the Q06-H1 sealed record to `Reopened`, `snapshot_valid=False` (`:3152-3161`) | same | the Q06-H1 record "shall not be … mutated" (`FOUNDER_DECISIONS.md:1223`); the UI path exists today. ANALYSIS: advancing the date by at least one day removes this path (reopen requires `bd == audit_date + 1`) |

---

## 4. Voucher expiry

FACTS: issuance anchors expiry on the calendar (`expiry = _d.today() + 365 days`, `app/services.py:1950`, from the cancellation path `:1854`); status and redemption compare `expiry_date < date.today()` (`:2009`, `:2077`); the voucher report computes `days_left` against the **business date** (`app/reports.py:6403` `voucher_ledger`, `today = get_business_date()` `:6429`, `days_left` `:6457`).

| Combination after K-7 | Effect with business date 53 days behind |
|---|---|
| Anchor → business date, test stays calendar | voucher expires **53 calendar days earlier** than today's behaviour (2027-08-10 instead of 2027-10-0x): a guest liability shortened silently |
| Anchor and test → business date | consistent internally; in calendar terms the voucher lives as long as the business date lags (could be longer than 365 calendar days) |
| Anchor and test stay calendar (only `issued_date` moves) | `issued_date` (2026-08-10) and expiry (2027-10-0x) on different bases; validity reads as 418 days |
| Today | anchor and test calendar; report `days_left` on the business date → the report already overstates days left by the lag |

ANALYSIS: the voucher basis is a liability term, not only a dating detail. It needs an explicit ruling (K7-D4). Production holds no vouchers today, so no existing liability changes.

---

## 5. Late checkout

See §2 row. Additional facts: the GET preview (`app/routes.py:3850-3853`) computes the amount the operator is asked to collect with the calendar test; the POST posts with the same test (`:3206-3209`). If only one of them moved, the screen and the posted charge would disagree — the kind of mismatch the preview comment warns about ("checkout denied after exact pay", `app/routes.py:3862-3868`). Any change must move both.

---

## 6. Reporting

| Surface | Basis today | After K-7 with date stale |
|---|---|---|
| Night audit (open day) | `payment_date/charge_date == business_date` (`app/night_audit_service.py:207-231`) | contains everything posted since deploy |
| GST report default range | calendar month-to-date (`app/billing.py:50-54`) | October default view shows **no** new taxable extras (all TaxLines dated 2026-08-10); today it shows only the WC/MD rows |
| GSTR-1 export | default previous calendar month (`app/reports.py:5897`); invoices selected by UTC checkout date (`app/gstr_export.py:192-193`) | invoices (by checkout date) and TaxLine-based GST report (by charge date) fall into **different months** for the same supply — a statutory reconciliation risk (already present for BD-dated extras today) |
| No-show, OTA, loyalty, aging reports | calendar ranges (`K7_WRITER_INVENTORY.md` §7) | show nothing of the new business-dated activity in their default views |
| Dashboards "checked in/out today" | UTC timestamp windows for the calendar day (`app/routes.py:690`, `:1063`) | unchanged (operational, technical timestamps) |
| Business-date dashboards | `get_business_date()` (`app/services.py:716-760`) | show 2026-08-10 figures that keep growing |

---

## 7. Comparison: K-7 shipped **after** the business date is current

| Aspect | Effect |
|---|---|
| Dating | rows dated on the (current) business date; closes made nightly keep calendar and business date within one day |
| Remaining drift | only the close-timing window (close before/after midnight) — which K-7 makes harmless for writers |
| Residual items not fixed by K-7 core | late-checkout/arrival basis (B-10 #2), invoice/credit-note dates (B-10 #1, UTC printing), void/shift day mapping (B-10 #3), report ranges, staleness escalation (3.6) |

---

## 8. Conclusion (ANALYSIS, not a decision)

1. Shipping K-7 while the business date is 53 days stale would date **all** new financial activity on 2026-08-10, in the same day as five D11 rows, and remove the last wall-clock rows that currently keep some activity in October. It would make the books internally consistent (one basis) but consistently **wrong against the calendar**, GST periods and invoices.
2. Not shipping K-7 leaves production with a mixed basis (16 writers on 2026-08-10, 8 on the calendar) — also wrong, and INV-B04 fires on every wall-clock row.
3. Neither state is fit for operation; the stale business date is the dominant problem in both. That is why the business date is analysed as a **separate production decision** (`BUSINESS_DATE_PRODUCTION_DECISION.md`) and must not be bundled into a K-7 deployment.
