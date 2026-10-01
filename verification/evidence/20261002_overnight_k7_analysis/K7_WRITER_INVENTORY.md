# K-7 WRITER INVENTORY — every financial dating site in `app/` at `c9eeff0`

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, analysis only |
| Code | `C:/wtov` at `c9eeff0` (`app/` identical to the live `c703150`: `git diff --stat c703150 c9eeff0 -- app/` empty) |
| Method | (1) `grep -n -E "date\.today\|datetime\.now\|datetime\.utcnow\|\.today\(\)\|utcnow"` over `app/*.py` (flat package; no sub-packages contain `.py` files) → **297 lines in 44 files**; (2) `grep` for `server_default\|CURRENT_DATE\|CURRENT_TIMESTAMP\|date('now')` → DDL defaults; (3) every constructor `Payment(`, `ExtraCharge(`, `CreditVoucher(`, `CreditVoucherRedemption(`, `CreditNote(`, `NightAuditLog(`, `ReservationNightRate(`, `Folio(` outside `models.py`/`seed.py`/`dev_seed.py`; (4) every assignment to `business_date.current_date`. Each hit was read in context |
| Baseline list | Phase 1 inventory `verification/evidence/20260908_phase1_implementation_readiness/FINANCIAL_WRITER_INVENTORY.md` (24 writers, W-01…W-24, line numbers at `e69f2ac`) |
| Prior package | `FinalGrid/g3_decision_package/G3_DECISION_PACKAGE.md` §A2 (2026-09-30). Column "09-30" says whether that package recorded the site: **REC** recorded · **MISSED** not recorded · **n/a** not a K-7 item |

Date-source codes: **BD** controlled business date · **WC** wall clock (`date.today()` / `datetime.now().date()`) · **MD** model default (`date.today`) because no value passed · **UTC** a UTC timestamp or UTC date · **TS** technical timestamp (ADR-004 keeps it technical, `verification/adr/ADR-004-business-date-authority.md:33`, `:46`).

ADR-004 intended source: `ADR-004:39` payments/charges → business date at posting; `:40` corrections/refunds → business date of posting; `:41` night audit unchanged; `:42` report ranges → business date, "generated at" technical; `:43` invoice date UNRESOLVED; `:44` arrival/departure validation UNRESOLVED; `:45` shift mapping UNRESOLVED. Where ADR-004 is silent the cell says **OPEN**.

---

## 1. Financial row writers (rows in `payments`, `extra_charges`, `credit_vouchers`)

| W-id | Row constructed | Date assignment | Function | Row | Current source | ADR-004 intended | Reachable from | 09-30 |
|---|---|---|---|---|---|---|---|---|
| W-01 | `app/routes.py:1961` | `:1966` `payment_date=today_biz` (`today_biz = get_business_date()` `:1959`) | `bulk_booking_api` | Payment advance/settlement | BD | BD — no change | route | REC (as "already BD") |
| W-02 | `app/routes.py:2235` | `:2240` (`:2230`) | `new_reservation` | Payment advance | BD | BD — no change | route | REC |
| W-03 | `app/routes.py:3303` | `:3308` `get_business_date()` | `checkout` OTA settlement | Payment | BD | BD — no change | route | REC |
| W-04 | `app/routes.py:3343` | `:3348` | `checkout` settlement | Payment | BD | BD — no change | route | REC |
| W-05 | `app/routes.py:5837` | `:5842` | `add_payment` | Payment | BD | BD — no change | route (lock guard on BD `:5801`) | REC |
| W-06 | `app/routes.py:7544` | `:7549` `business_date` (`:7340`) | `walkin_search_express` | Payment | BD | BD — no change | route | REC |
| W-07 | `app/routes.py:9348` | `:9353` | `settle_credit` | Payment credit_recovery | BD | BD — no change | route | REC |
| **W-08** | `app/services.py:1223` | `:1228` `payment_date = today`; `today = _date.today()` `:1217` | `post_payment_correction` reversal | Payment correction | **WC** | BD of posting (`ADR-004:40`) | `app/routes.py:7855` (void, locked date + Admin override), `app/billing.py:433` (direct void) | REC (`:1217`) |
| **W-09** | `app/services.py:1253` | `:1258` | `post_payment_correction` replacement | Payment correction | **WC** | BD of posting | as W-08 | REC |
| **W-10** | `app/services.py:1802` | `:1807` `payment_date=_date.today()` | `post_cancellation_disposition` | Payment refund (`is_reversal`) | **WC** | BD of posting | `app/routes.py:8855` (`cancel_reservation`, lock on `arrival_date` `:8768`) | REC (`:1807`) |
| **W-11** | `app/services.py:2111` | `:2116` `payment_date=_d.today()` | `redeem_credit_voucher` | Payment settlement | **WC** | BD | `app/routes.py:2266` (new reservation), `:9466` (`voucher_redeem`) | REC (`:2116`) |
| W-12 | `app/services.py:3160` | `:3167` | `CheckInService.complete_full_checkin` | Payment deposit | BD | BD — no change | route via service | REC |
| W-13 | `app/cico_service.py:361` | `:366` `charge_date or get_business_date()` | `post_charge` (early/late) | ExtraCharge | BD (callers pass none) | BD — no change | checkout `app/routes.py:3251`, check-in `:2949` | REC |
| W-14 | `app/noshow_service.py:145` | `:151` `charge_date=business_date` | `process_reservation_noshow` | ExtraCharge no-show fee | BD (parameter) | BD — no change | `run_night_audit` `app/services.py:353`; `manual_noshow` `app/noshow_service.py:285-315` | REC |
| W-15 | `app/pos.py:118` | `:123` | `post_charge` | ExtraCharge POS | BD | BD — no change | route | REC |
| W-16 | `app/reports.py:3345` | `:3351` `charge_date=target_date` | `_rerun_skipped_audit` | ExtraCharge room_rent [recovered] | BD (closed target date) | unchanged (`ADR-004:41`) | `app/reports.py:3454` (Admin) | REC |
| **W-17** | `app/routes.py:3108` | **none** — `ExtraCharge(…)` at `:3108-3113` passes no `charge_date` | `checkout` extra | ExtraCharge | **MD** → `app/models.py:775` | BD | route | REC (`:3106`; now `:3108`) |
| W-18 | `app/routes.py:3466` | `:3471` | `checkout` tip | ExtraCharge | BD | BD — no change | route | REC |
| W-19 | `app/routes.py:3502` | `:3507` | `checkout` other income | ExtraCharge | BD | BD — no change | route | REC |
| **W-20** | `app/routes.py:8079` | `:8084` `charge_date=now.date()`; `now = datetime.now()` `:8029` | `add_overstay_charge` | ExtraCharge overstay | **WC** | BD (elapsed-hours computation stays on physical time) | route | REC (`:8029`, `:8084`) |
| W-21 | `app/services.py:413` | `:418` `charge_date=_bd` | `run_night_audit` | ExtraCharge room_rent | BD | unchanged | scheduler; `app/routes.py:4927` | REC |
| **W-22** | `app/services.py:1313` | `:1318` `charge_date = today`; `today = _date.today()` `:1306` | `post_extra_charge_correction` reversal | ExtraCharge correction | **WC** | BD of posting | **no caller in `app/`** (only the definition `:1283`) | REC (date) / **MISSED** (no caller) |
| **W-23** | `app/services.py:1346` | `:1351` | `post_extra_charge_correction` replacement | ExtraCharge correction | **WC** | BD of posting | no caller in `app/` | REC / **MISSED** (no caller) |
| W-24 | `app/services.py:2876` | `:2882` | `convert_overpayment_to_upsell` | ExtraCharge room_upsell | BD | BD — no change | checkout / overpayment routes | REC |
| — (W-10 leg) | `app/services.py:1960` | `:1965` `issued_date=_d.today()`; expiry `:1950` `_d.today() + expiry_days` (365 from `:1854`) | `issue_credit_voucher` | CreditVoucher (liability) | **WC** (issue and expiry anchor) | **OPEN** — ADR-004 names payments/charges/corrections/refunds, not vouchers; AR-008 (`RECORD.md:106`) covers "financial/operational logic" generally | `post_cancellation_disposition` `:1850` | REC (issue) / **MISSED** (expiry anchor `:1950`) |

Count: **8 writer sites** date from the wall clock or model default (W-08, W-09, W-10, W-11, W-17, W-20, W-22, W-23) plus **voucher issuance** (not a W-id). 16 W-ids are business-dated. This matches `KNOWN_DEFECTS.md:13` and `FINANCIAL_WRITER_INVENTORY.md` observation 3, with the voucher leg and the caller-less W-22/W-23 added.

## 2. Other date-bearing financial rows (not in the 24)

| Site | Row | Date fields | Source | ADR-004 intended | 09-30 |
|---|---|---|---|---|---|
| `app/services.py:2134` | CreditVoucherRedemption | `redeemed_at = _dt.utcnow()` `:2138` | TS | technical — NOT APPLICABLE | n/a |
| `app/billing.py:610` (`create_credit_note`) | CreditNote | only `issued_at` (`app/models.py:1695`, TS default); number year `datetime.utcnow()` `app/billing.py:607` | UTC | **OPEN** (statutory document; no accounting-date column; GSTR-1 period from `issued_at`, `app/gstr_export.py:278-284`) | **MISSED** |
| `app/services.py:337`; `app/reports.py:2864`, `:2979`, `:3538` | NightAuditLog | `audit_date` = business date / requested date / Force-Close cursor | BD (Force Close: dates up to the calendar) | unchanged | n/a |
| `app/nightly_rate_service.py:249` | ReservationNightRate | `stay_date` (a stay night, not an accounting date) | stay calendar | NOT APPLICABLE | n/a |
| `app/routes.py:7892`; `app/payment_void_service.py:376` | Payment (void flag) | `voided_at = datetime.utcnow()`; close counts `date(voided_at) == business_date` (`app/night_audit_service.py:215-219`) | UTC → day | **OPEN** | **MISSED** |

## 3. Financial decisions taken on the wall clock (no row date, but a financial outcome)

| Site | Decision | Source | Intended | 09-30 |
|---|---|---|---|---|
| `app/routes.py:3206-3209` | late-checkout charge applies if `datetime.now().date() >= departure_date` | WC | **OPEN** (B-10 #2) | REC |
| `app/routes.py:3850-3853` | late-checkout **preview** at GET uses the same calendar test (drives the amount the operator is asked to collect) | WC | follows the ruling above | **MISSED** |
| `app/routes.py:2937-2945` | early check-in by wall-clock time of day | WC (time) | NOT APPLICABLE (physical time) | n/a |
| `app/routes.py:8029-8048` | overstay billable hours from `datetime.now()` − planned checkout | WC (time) | NOT APPLICABLE (physical time); only the row date (W-20) is K-7 | REC (row) |
| `app/services.py:2007-2010` | voucher status `expired` if `expiry_date < date.today()` | WC | **OPEN** | **MISSED** |
| `app/services.py:2077-2078` | redemption refused if `expiry_date < date.today()` | WC | **OPEN** | **MISSED** |
| `app/services.py:2208`, `:2255` | credit "days open/outstanding" aging from the calendar | WC | **OPEN** (operational KPI; ADR-004 silent) | **MISSED** |
| `app/payment_void_service.py:89` | void window = `utcnow - created_at` | TS | NOT APPLICABLE (elapsed time) | n/a |
| `app/routes.py:8147` | hourly extension must be in the future (`datetime.now()`) | WC (time) | NOT APPLICABLE | n/a |
| `app/reports.py:3522`, `:3535`, `:3555` | Force Close advances the business date **to the calendar date** | WC | Phase 3 (3.4/3.6) design; see `BUSINESS_DATE_PRODUCTION_DECISION.md` | **MISSED** |
| `app/services.py:364` | night-audit room rent posted for every `CheckedIn` reservation, no date condition | n/a (no date filter) | Phase 3 (3.1/3.2) | **MISSED** |

## 4. Model and DDL defaults on financial date columns

| Column | Default | Citation | Nullable | 09-30 |
|---|---|---|---|---|
| `extra_charges.charge_date` | `default=date.today` (Python) | `app/models.py:775` | yes | REC |
| `payments.payment_date` | `default=date.today` | `app/models.py:809` | yes | REC |
| `credit_vouchers.issued_date` | `default=date.today` | `app/models.py:1817` | NOT NULL | REC |
| `credit_vouchers.issued_date` (DDL) | SQLite `DEFAULT (date('now'))` = **UTC date**; PG path `DEFAULT CURRENT_DATE` | `app/__init__.py:1794`, `:1577` | NOT NULL | **MISSED** |
| `business_date.current_date` | `default=date.today`; seed `BusinessDate(current_date=date.today())` | `app/models.py:106`; `app/__init__.py:1851` | NOT NULL | **MISSED** (seed) |
| `equipment_health_logs.snapshot_date` | `default=date.today` / `DEFAULT CURRENT_DATE` | `app/models.py:1296`; `app/__init__.py:1278` | — | n/a (maintenance) |

## 5. Business-date fallbacks to the calendar

| Site | Code | 09-30 |
|---|---|---|
| `app/services.py:621` | `return bd.current_date if bd else date.today()` | REC |
| `app/routes.py:4770` | `bd = business_date.current_date if business_date else date.today()` (night-audit view) | **MISSED** |
| `app/occupancy_engine.py:76-87` | `get_business_date()`; on exception `_date.today()` | **MISSED** |
| `app/kpi_command_center.py:72` | `ctx.get('business_date') or date.today()` | **MISSED** |

## 6. Documents and statutory dating (ADR-004 item "Invoices" UNRESOLVED; B-10 #1)

| Site | What | Source | 09-30 |
|---|---|---|---|
| `app/routes.py:258` | invoice number year | UTC year | REC (as "invoice numbering on first view") |
| `app/routes.py:4122` | invoice number assigned on first invoice view | — | REC |
| `app/routes.py:163`, `:195`; `:4023` | advance receipt number year; `advance_receipt_date = datetime.utcnow()`; receipt printed with that date | UTC | **MISSED** |
| `app/billing.py:607` | credit-note number year | UTC year | **MISSED** |
| `app/templates/invoice.html:39-40`; `app/templates/invoice_pdf.html:331-332` | printed invoice date/time = `checked_out_at` (UTC, set `app/routes.py:3716`) with no IST conversion | UTC | **MISSED** |
| `app/gst_einvoice.py:44` | e-invoice `invoice_date` = `(checked_out_at or utcnow)` | UTC | **MISSED** |
| `app/gstr_export.py:38-41`, `:192-193` | GSTR-1 invoice date and period selection by `date(checked_out_at)` | UTC | **MISSED** |
| `app/gstr_export.py:278-284`, `:314` | GSTR-1 CDNR period by `CreditNote.issued_at` against `date` bounds | UTC; probable end-day exclusion — NOT VERIFIED | **MISSED** |

## 7. Report default ranges and "today" scopes on the calendar (ADR-004 `:42` vs Master Plan Phase 3 "Not touched: reports", `MASTER_PLAN.md:150`)

| Site | Surface | 09-30 |
|---|---|---|
| `app/billing.py:50-54` | GST report default month-to-date | REC |
| `app/billing.py:89` | invoice register "today" tab | REC (as `:89`) |
| `app/noshow.py:119-123` | no-show report default range | **MISSED** (prior said "others") |
| `app/ota.py:310`, `:507-515`, `:542` | OTA dashboard / bookings range | **MISSED** |
| `app/reports.py:5897` | GSTR-1 export default = previous calendar month (statutory period — calendar may be correct; needs a ruling) | **MISSED** |
| `app/loyalty.py:290` | programme stats month | **MISSED** |
| `app/ceo_kpis.py:322` | OTA receivable aging `as_of` | **MISSED** |
| `app/ota_reconciliation.py:124`, `:411` | payout-date validation; summary `today` | **MISSED** |
| `app/routes.py:690`, `:1063`, `:7022` | dashboard "checked in/out today" windows | **MISSED** |
| `app/routes.py:1810`, `:7108` | reservations list 30-day cancelled window | **MISSED** |
| `app/performance_service.py:22`, `:133` | staff performance "today" | **MISSED** |
| `app/services.py:736` | dashboard scope resolver `today_real` (deliberately shows calendar alongside business date) | **MISSED** (by design; ruling needed whether it stays) |
| `app/revenue_guard.py:74`; `app/ota_journey.py:112` | tariff-guard fallback; OTA journey earned nights | **MISSED** |
| `app/reports.py:2788`, `app/routes.py:4886` | `today=date.today()` passed to night-audit templates (Force Close modal condition `bd < today`, `app/templates/night_audit_panel.html:716`, `:1107`) | **MISSED** |

## 8. Validation on the calendar (B-10 #2, `ADR-004:44`)

`app/validators.py:101` (`validate_not_past`, used at `app/routes.py:2153` and `app/booking.py:136`); `app/booking.py:59`, `:83`, `:290`; `app/webhook.py:415`; `app/routes.py:2397` (date of birth — NOT APPLICABLE). 09-30: REC for `booking.py:83` only.

## 9. Classification of the remaining grep hits (exhaustiveness)

All 297 lines were classified. Lines not listed above are **TS** or out of K-7 scope:

| File(s) | Lines | Class |
|---|---|---|
| `models.py` | 64 | 54 `created_at`/`updated_at`/`*_at` UTC defaults (TS); the 5 `default=date.today` above; `:759` folio listener `created_at` (TS) |
| `ai_anomaly.py`, `ai_insights.py`, `ai_predictive_maintenance.py`, `ai_pricing.py`, `ai_sentiment.py`, `ai_routes.py` | 48 | analytics windows, cache TTL, "generated at" — out of scope (no financial row, no close input) |
| `auth.py`, `portal.py`, `feedback.py`, `alert_service.py`, `notifications.py`, `backup_manager.py`, `updater.py`, `maintenance.py`, `grc_service.py`, `groups.py`, `mis_service.py`, `audit_explanation_service.py`, `webhook.py:512`, `date_ranges.py:5` (comment) | ~40 | TS (login lockout, tokens, retries, backup file names, GRC timestamps, check-in timestamps) |
| `shift_service.py` | 3 | shift `end_time`/`approved_at` TS — day mapping is B-10 #3 (§2 above) |
| `payment_void_service.py` | 6 | void decision timestamps TS; `:89` window; `:376` (§2) |
| `services.py` | 30 | the sites above plus TS: `:483-484`, `:522`, `:1154`, `:1834`, `:2024-2026`, `:2138`, `:2174`, `:2760`, `:3005`, `:3115`, `:3146`; `:778-838` UTC-window helpers (default `at=date.today()` only when the caller passes none) |
| `routes.py` | 45 | the sites above plus TS: `:447`, `:2497`, `:2579`, `:2597`, `:2621`, `:2829`, `:2890`, `:2907`, `:3173`, `:3181`, `:3650`, `:3716`, `:3732`, `:7460`, `:7519`, `:7763`, `:8982`, `:9271`; check-in form default time `:1840`, `:2679`, `:2994`, `:6665`, `:7135` (`:2679`/`:2994` render **UTC** as the default check-in time — UI observation, not a dating site); `:6321-6322` alerts; `:73` install date |
| `reports.py` | 22 | the sites above plus "generated at" (`:75`, `:1124`, `:1946`, `:4813`, `:4958`, `:5237`), close timestamps TS (`:2871`, `:3013-3014`, `:3091`, `:3190`, `:3397-3403`, `:3545-3557`), shift-report window `:485` |
| `seed.py`, `dev_seed.py` | 14 | fixtures — NOT APPLICABLE to production behaviour |
| `night_audit_service.py:274`; `gst_einvoice.py:219`; `occupancy_engine.py:411` | 3 | "generated at" / log timestamp — TS |

ANALYSIS: the K-7 list as recorded (`KNOWN_DEFECTS.md:13`) is accurate for **writer rows**. What it does not contain, and what a Phase 3 unit-3.1 directive must decide in or out, is: voucher issue/expiry basis (§1, §3), the three secondary fallbacks (§5), void and shift day mapping (§2), late-checkout preview (§3), the document/statutory dates (§6), and the wider report-range list (§7).
