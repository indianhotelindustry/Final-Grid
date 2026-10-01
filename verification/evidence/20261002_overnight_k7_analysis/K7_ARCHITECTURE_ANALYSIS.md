# K-7 ARCHITECTURE ANALYSIS — business-date storage, derivation, advancement and wall-clock leakage

| | |
|---|---|
| Prepared | 2026-10-02, overnight session FG-OVERNIGHT-01, by Claude (analysis only) |
| Repository | `C:/wtov`, branch `overnight-20261002`, base `c9eeff0` (= `origin/main`); HEAD `419852a` adds evidence only |
| `app/` identity | `git diff --stat c703150 c9eeff0 -- app/` and `git diff --stat c703150 HEAD -- app/ tools/` are both empty: the code analysed here is the code the live checkout (`c703150`) runs |
| Production | not opened. Facts used are the orchestrator's read-only observations of 2026-10-02 00:40 IST (SHA-256 `21dc0e97…3e434`, 733,184 B; `business_date` = 2026-08-10, updated 2026-08-11 12:42:48; `night_audit_enabled='false'`, `night_audit_time='02:00'`; application stopped) and committed evidence packs, cited where used |
| Changed | nothing outside this directory. No application start, no `create_app()`, no git mutation |
| Prior input | `FinalGrid/g3_decision_package/G3_DECISION_PACKAGE.md` Part A and `G3_DEPENDENCY_MAP.md` (2026-09-30, `c703150`). Every line number below was re-verified at `c9eeff0`; items the prior package did not record are marked **[NEW]** |

Labels: **FACT** = read from code or a governance record, cited. **ANALYSIS** = inference from facts. **OPTION** = a choice for the Founder; nothing here selects one. Status words are limited to PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE.

---

## 0. Answer first: is K-7 implementation authorized today?

**K-7 implementation: NOT AUTHORIZED. K-7 production deployment: NOT AUTHORIZED.**

| Source | Text (verbatim or exact) | Effect |
|---|---|---|
| FD-013, `verification/FOUNDER_DECISIONS.md:701`, `:705` | "Business date is the authoritative financial/operational accounting date." … "Do not implement the date-authority refactor now." | principle adopted; refactor not authorized |
| AR-008, `verification/evidence/20260908_architecture_resolution_round1/RECORD.md:106` | "Financial/operational logic must not silently substitute `date.today()` … No code changes are authorized now." | same |
| ADR-004, `verification/adr/ADR-004-business-date-authority.md:8`, `:53-55`, `:69` | "Implements: Nothing. The refactor is explicitly not authorized (FD-013)." / "Implementation boundary: None authorized." / "implementation remains separately authorized work" | architecture adopted, no implementation |
| Q-3, `FOUNDER_DECISIONS.md:1015`, `:1017` | wall-clock/business-date defects "remain primarily a Phase 3 concern"; "Do not use this decision to permit unrelated date refactoring." | K-7 is Phase 3 work |
| K-7, `verification/evidence/20260908_golden_master/KNOWN_DEFECTS.md:13` | "Q-3: Phase 3 concern" | same |
| Master Plan Phase 3, `verification/MASTER_PLAN.md:145`, `:149` | "PHASE 3 — Night Audit & Business-Day Integrity — **NOT STARTED**"; unit 3.1 "single source of business-date derivation" | K-7 = unit 3.1 territory; phase not started |
| Master Plan §14, `MASTER_PLAN.md:370` | Phase 3 still needs "Phase 1 complete; ADR-004 adoption; **scheduler-controls ADR**" | B-1 ADR still absent (`verification/adr/BACKLOG.md:12`) |
| FD-P2-05, `FOUNDER_DECISIONS.md:1175` | Phase 3 units 3.5/3.6 "are scoped accordingly" | scoping, not authorization |
| Round 3 gate, `FOUNDER_DECISIONS.md:1206` | "**No phase implementation is authorized by this entry.**" | — |
| Round 4, `FOUNDER_DECISIONS.md:1254` | "No implementation, schema, database, or production-record change is authorized by this entry." | — |
| Round 6, `FOUNDER_DECISIONS.md:1321` | "SR-1 (INV-B06), K-7 and all other open items are unaffected." | — |
| Round 7, `FOUNDER_DECISIONS.md:1354` | "No change to `app/`, the schema, production, K-7, SR-1 or any other rule." | — |
| FD-019, `FOUNDER_DECISIONS.md:848`, `:850` | "Implementation completion is not production authorization." / no production data mutation without the applicable decision and gates | deployment is a further, separate act |

ANALYSIS: no later entry (Rounds 4–7, ADR011-SA, SR2-RULE, SR2-REV2) lifts the FD-013 / AR-008 / ADR-004 boundary. The directive this work would need is a **Phase 3 directive covering at least unit 3.1**, and production deployment would need a further authorization under FD-019 / FD-005 (`FOUNDER_DECISIONS.md:468`). See `K7_DECISION_REQUIRED.md`.

---

## 1. How the business date is stored

| Item | FACT | Citation |
|---|---|---|
| Table | `business_date` — singleton, enforced only in application code | `app/models.py:100-108` |
| Columns | `current_date DATE NOT NULL default=date.today` (Python-side), `is_locked BOOLEAN default False`, `updated_at DATETIME default=datetime.utcnow` | `app/models.py:106-108` |
| Seeding | `init_data()` inserts `BusinessDate(current_date=date.today())` when no row exists — runs at every application start | `app/__init__.py:1845-1852`; `init_data()` called at `app/__init__.py:528` |
| `is_locked` | written `False` on every advance; read only for display (`g_business_date_locked`, CEO KPI) | `app/services.py:521`, `app/reports.py:3090`, `:3556`; `app/__init__.py:430`; `app/ceo_kpis.py:394` |
| Closed-day record | one `NightAuditLog` row per date (`audit_date`), `status` ∈ Pending / InProgress / Completed / Warning / Reopened / Skipped; `snapshot_json`, `snapshot_hash`, `snapshot_valid` (default **True**) | `app/models.py:908-937` |

ANALYSIS: the business date is a single mutable row; history of how it moved exists only indirectly (NightAuditLog rows, NightAuditReopenLog rows, AuditLog rows where written). `is_locked` is not a guard anywhere in the writer paths.

---

## 2. How the business date is read

### 2.1 The canonical reader and its calendar fallback

FACT — `app/services.py:619-621`:

```python
def get_business_date():
    bd = BusinessDate.query.first()
    return bd.current_date if bd else date.today()
```

- If the row is missing, the **calendar date is returned silently** (no log, no error).
- ANALYSIS: in a running system the row is seeded by `init_data()` at boot, so the fallback is reachable only (a) between table creation and `init_data()`, (b) if the row is deleted, (c) in harnesses/tools that call writers without the seed. It is still a silent wall-clock substitution, which AR-008 (`RECORD.md:106`) names as non-compliant ("must not silently substitute `date.today()`").

### 2.2 Other readers (unit 3.1 "single source of derivation")

| Reader | Behaviour | Citation |
|---|---|---|
| `get_business_date()` | canonical; calls in `app/`: reports.py 50, routes.py 28, services.py 10, ai_voice.py 8, ai_forecast.py 7, others 1–2 each (grep count at `c9eeff0`) | `app/services.py:619` |
| `night_audit()` view | reads the row directly; **own calendar fallback** `bd = business_date.current_date if business_date else date.today()` | `app/routes.py:4769-4770` |
| `night_audit_advance_date` | reads the row directly | `app/reports.py:3517` |
| `occupancy_engine._business_date()` | calls `get_business_date()`, **second fallback** `_date.today()` on any exception | `app/occupancy_engine.py:76-87` |
| `kpi_command_center` | `ctx.get('business_date') or date.today()` — **third fallback** | `app/kpi_command_center.py:72` |
| `run_night_audit` | reads the row `with_for_update()` (inert on SQLite — `FORCE_CLOSE_INVESTIGATION.md` §6) and returns silently if absent | `app/services.py:302-306` |

ANALYSIS **[NEW]**: the prior package recorded one fallback (`services.py:621`). There are at least **three further calendar fallbacks** (routes.py:4770, occupancy_engine.py:87, kpi_command_center.py:72) and two direct readers that bypass `get_business_date()`. Unit 3.1 "single source of business-date derivation" is therefore wider than the writer sites.

---

## 3. How the business date is advanced (and moved back)

Complete set of writers to `business_date.current_date` at `c9eeff0` (exhaustive grep for `.current_date =` in `app/` and `tools/`):

| # | Path | Trigger | Date effect | Posts financial rows? | Seals snapshot? | Other effects | Citation |
|---|---|---|---|---|---|---|---|
| A | `services.run_night_audit` | scheduler `night_audit_job` (only when `night_audit_enabled='true'`) **or** `POST /night-audit/run` → `main.run_night_audit_manual` (Admin/Manager/Accountant) | +1 day, **only when no blockers** (pending checkouts, open shifts, zero-rate in-house rooms); otherwise log left `Pending`, date unchanged | **Yes**: no-show processing (`process_all_noshows(_bd)`, may post a no-show fee `ExtraCharge` dated `_bd`, sets reservation `NoShow`, frees room) and one `room_rent` `ExtraCharge` per `CheckedIn` reservation dated `_bd` | Yes on auto-complete (hash) | idempotency: any existing `NightAuditLog` for `_bd` → silent skip | `app/services.py:264`, `:312-317`, `:353`, `:364`, `:413-421`, `:457-476`, `:482-512`, `:520`; `app/routes.py:4921-4927`; `app/noshow_service.py:145-151`, `:212-229` |
| B | `reports.night_audit_run` + `reports.night_audit_complete` (the Night Audit panel's buttons) | Run: Admin/Manager/Accountant; Complete: Admin/Manager; hard blocks overridable with a reason | +1 day, **only if** `bd.current_date == audit_date` | **No** — neither route posts room rent nor processes no-shows | Yes (hash, `_meta` stamp) | — | `app/reports.py:2824`, `:2896`, `:2934-2966`, `:3011`, `:3060-3081`, `:3086-3091`; panel forms `app/templates/night_audit_panel.html:172`, `:978` |
| C | `reports.night_audit_reopen` | Admin/Manager, reason required | −1 day, **only if** `bd.current_date == audit_date + 1` | No | invalidates (`snapshot_valid=False`) | writes `NightAuditReopenLog` + AuditLog (swallowed on failure) | `app/reports.py:3105`, `:3144-3161`, `:3186-3191` |
| D | `reports.night_audit_advance_date` ("Force Close") | Admin only | **jump to calendar today** in one step | **No** | **No** — but inserted rows take `snapshot_valid=True` from the model default | marks every intervening date `Skipped` (overwrites Pending/InProgress/Reopened rows), clears `is_locked`, **no `audit_logs` row** | `app/reports.py:3505-3565` (`:3522`, `:3535-3553`, `:3555`); `app/models.py:937`; investigation `verification/FORCE_CLOSE_INVESTIGATION.md` |
| E | `reports._rerun_skipped_audit` | Admin, reason required | none (date untouched) | **Yes** — posts missing `room_rent` for the target date, dated `target_date` | Yes | rewrites a `Skipped` log to Completed/Warning | `app/reports.py:3218`, `:3345-3351`, `:3454` |
| F | `tools/production_initialize.py` | operator CLI | sets an arbitrary date | deletes **all** activity rows | — | destructive reset | `tools/production_initialize.py:290-325` |

FACTS worth stating plainly:

1. **[NEW] The two operator close paths have different financial effects.** Path A posts no-shows and room rent; path B (the one the current panel renders) posts neither. `main.run_night_audit_manual` is registered (`app/routes.py:4921`) but its only form is in `app/templates/night_audit.html:6`, which no route renders (grep of `render_template` at `c9eeff0`); it is reachable by a direct POST only. FORCE_CLOSE_INVESTIGATION §8 recorded the paths on 2026-08-08 but not this divergence as a finding.
2. Path A's in-house population is `Reservation.status == 'CheckedIn'` with **no date condition** (`app/services.py:364`), whereas `NightAuditService` uses `arrival_date <= date < departure_date` (`app/night_audit_service.py:186-192`). With a stale business date, a guest checked in for a stay that starts after the business date would receive `room_rent` dated before arrival (see `BUSINESS_DATE_PRODUCTION_DECISION.md` §4).
3. No path advances the date *and* runs the full close for more than one day. There is no "set business date" route; the only arbitrary setter is the destructive tool F.
4. Scheduler: `setup_night_audit_scheduler` registers `night_audit_job` only when `night_audit_enabled` is `'true'` (`app/services.py:546-575`); production has `'false'` (orchestrator fact; FD-P2-05 `FOUNDER_DECISIONS.md:1175`).

---

## 4. Where wall-clock dates leak into financial / business dating

Full site list with W-ids: `K7_WRITER_INVENTORY.md`. Summary by area:

| Area | Current date source | Citation | ADR-004 intended source | Phase 1 W-id |
|---|---|---|---|---|
| **Payments** — advance/settlement/deposit/credit recovery | business date | `app/routes.py:1966`, `:2240`, `:3308`, `:3348`, `:5842`, `:7549`, `:9353`; `app/services.py:3167` | business date (unchanged) | W-01…W-07, W-12 |
| **Payment corrections** (reversal + replacement) | **calendar** `today = _date.today()` | `app/services.py:1217`, rows `:1228`, `:1258` | business date of posting (`ADR-004:40`) | W-08, W-09 |
| **Charge corrections** (reversal + replacement) | **calendar** | `app/services.py:1306`, rows `:1318`, `:1351` | business date of posting | W-22, W-23 — **[NEW] no caller in `app/`** (grep: only the definition at `services.py:1283`) |
| **Cancellation refund** | **calendar** `payment_date=_date.today()` | `app/services.py:1807` | business date of posting | W-10 |
| **Voucher issue** | **calendar** `issued_date=_d.today()`; expiry `_d.today() + expiry_days` (365 from the cancellation path) | `app/services.py:1950`, `:1965`; caller `:1850-1857` | not stated by ADR-004 (voucher is a liability, not a payment/charge) — **OPEN** | not in the 24 (voucher row is not a Payment/ExtraCharge) **[NEW]** |
| **Voucher code** | calendar `CV-YYYYMMDD-XXXX` | `app/services.py:1928-1932` | identifier, not an accounting date — NOT APPLICABLE unless ruled | — |
| **Voucher expiry test** | **calendar** `expiry_date < _d.today()` in status derivation and redemption | `app/services.py:2007-2010`, `:2077-2078` | **OPEN** (calendar vs business date not ruled) | **[NEW]** |
| **Voucher redemption payment** | **calendar** `payment_date=_d.today()` | `app/services.py:2116` | business date | W-11 |
| **Voucher redemption row** | `redeemed_at = _dt.utcnow()` (technical) | `app/services.py:2138` | technical timestamp stays (`ADR-004:33`) | — |
| **Checkout extra charge** | **model default** (no `charge_date` passed) | `app/routes.py:3108-3113`; default `app/models.py:775` | business date | W-17 |
| **Checkout tip / other income** | business date | `app/routes.py:3471`, `:3507` | unchanged | W-18, W-19 |
| **Late checkout** | charge dated on business date (`cico_service.post_charge`, `app/cico_service.py:366`); **applicability** decided by the calendar: `_today = datetime.now().date()`; `_today >= departure_date`; GET preview likewise | `app/routes.py:3206-3209`; preview `:3850-3853` | charge: unchanged; applicability: **OPEN** — B-10 #2 (arrival/departure basis), `ADR-004:44` | W-13 (charge); finding F-7 (`20260909_phase1_verification_completion/VERIFICATION_COMPLETION.md:117`) |
| **Early check-in** | charge on business date; applicability by wall-clock **time of day** only | `app/routes.py:2937-2945`, `app/cico_service.py:366` | time of day is a physical fact — NOT APPLICABLE to K-7 | W-13 |
| **Overstay** | **calendar** `charge_date=now.date()`, `now = datetime.now()`; billable hours from wall-clock elapsed time | `app/routes.py:8029`, `:8084` | charge date: business date; elapsed-hours computation is physical time — NOT APPLICABLE | W-20 |
| **No-show fee** | business date passed from the close | `app/noshow_service.py:151` | unchanged | W-14 |
| **Night-audit room rent** | business date `_bd` | `app/services.py:418` | unchanged (`ADR-004:41`) | W-21 |
| **Recovered room rent** | target (closed) date | `app/reports.py:3351` | unchanged | W-16 |
| **POS charge** | business date | `app/pos.py:123` | unchanged | W-15 |
| **Upsell** | business date | `app/services.py:2882` | unchanged | W-24 |
| **Payment void** (non-locked) | `voided_at = datetime.utcnow()`; night audit counts voids by `date(voided_at) == business_date` | `app/routes.py:7892`; `app/payment_void_service.py:376`; `app/night_audit_service.py:215-219` | **OPEN** — a void's accounting day is derived from a UTC timestamp compared against the business date **[NEW]** | — |
| **Model defaults** | `ExtraCharge.charge_date`, `Payment.payment_date`, `CreditVoucher.issued_date` (NOT NULL), `BusinessDate.current_date` = `date.today` | `app/models.py:775`, `:809`, `:1817`, `:106` | "not `date.today` model defaults" (`ADR-004:39`) | — |
| **DDL defaults** **[NEW]** | `credit_vouchers.issued_date … DEFAULT (date('now'))` (SQLite, **UTC**) / `DEFAULT CURRENT_DATE` (PG path) | `app/__init__.py:1794`, `:1577` | relevant only if the Python default is removed (§6) | — |
| **Invoice number / receipt / credit-note number year** | `datetime.utcnow().strftime('%Y')` | `app/routes.py:258`, `:163`; `app/billing.py:607` | invoice date rule **UNRESOLVED** (`ADR-004:43`, B-10 #1) | — |
| **Invoice date as printed** **[NEW]** | `reservation.checked_out_at` (stored UTC, `app/routes.py:3716`) formatted **without IST conversion** | `app/templates/invoice.html:39-40`, `app/templates/invoice_pdf.html:331-332`; e-invoice `app/gst_einvoice.py:44`; GSTR-1 `app/gstr_export.py:38-41`, `:192-193` | B-10 #1 **OPEN** | — |
| **Credit note date / period** **[NEW]** | `CreditNote.issued_at` (UTC timestamp) — no accounting-date column; GSTR-1 CDNR filters `issued_at` between `date` bounds | `app/models.py:1695`; `app/gstr_export.py:278-284`, `:314` | **OPEN** | — |
| **Shift → day mapping** | `date(Shift.start_time) == business_date` (UTC start time vs business date) | `app/night_audit_service.py:236-244` | B-10 #3 **OPEN** | — |
| **Reports — default ranges on the calendar** | GST report `app/billing.py:50-54`; invoice register `:89`; no-show report `app/noshow.py:119-123`; OTA dashboard/bookings `app/ota.py:310`, `:507-515`, `:542`; GSTR-1 export default previous month `app/reports.py:5897`; loyalty `app/loyalty.py:290`; OTA aging `app/ceo_kpis.py:322`; OTA reconciliation `app/ota_reconciliation.py:411`; dashboard "today" windows `app/routes.py:690`, `:1063`, `:7022`; reservations list `:1810`, `:7108` | ADR-004 `:42` (ranges on business date) vs Master Plan Phase 3 "Not touched: … reports" (`MASTER_PLAN.md:150`) — **conflict OPEN** (prior package §C.1) | — |
| **Validation** | new-booking arrival `validate_not_past` against the calendar (`app/validators.py:101`, used `app/routes.py:2153`, `app/booking.py:136`); public engine `app/booking.py:83`; OTA modify `app/webhook.py:415` | B-10 #2 **OPEN** | — |
| **Walk-in / express check-in arrival** | `arrival_date = business_date` | `app/routes.py:2477`, `:2732` | consistent with the business date | — |

Technical timestamps that ADR-004 keeps technical (`ADR-004:33`, `:46`): `created_at`, `AuditLog.timestamp`, shift `start_time/end_time`, `checked_in_at/checked_out_at`, `redeemed_at`, `cancellation_processed_at`, `voided_at`, snapshot `generated_at`. These are NOT APPLICABLE to K-7 **except where a report or close derives an accounting day from them** (voids, shifts, invoice date, credit notes, GSTR-1 period) — those derivations are the leak, not the timestamp.

---

## 5. Business-date boundaries and closed-day protection

FACTS:

- A date is "locked" when a `NightAuditLog` for it has status Completed, Warning or **Skipped** (`app/services.py:1006-1017`, `:1020-1045`, `:1048-1059`).
- Guards that consult the lock, and the date they test:

| Guard | Date tested | Citation |
|---|---|---|
| Add payment | business date | `app/routes.py:5801` |
| Check-in (three paths) | business date | `app/routes.py:2366`, `:7344`, `:7722`; `app/services.py:2962`, `:3051` |
| Checkout | `reservation.departure_date` (Admin override) | `app/routes.py:3067-3079` |
| Void / direct void | `payment.payment_date` (Admin override → correction pair) | `app/routes.py:7831-7845`; `app/billing.py:327-329`, `:411-421` |
| Edit / cancel reservation | `arrival_date` | `app/routes.py:6832`, `:8768`; `app/services.py:1029` |
| Corrections, refunds, voucher issue/redemption, overstay, checkout extra, POS, CICO | **none** — the services do not consult the lock | `app/services.py:1177-1283`, `:1692-1830`, `:1935-2140`; `app/routes.py:7983-8110` |

ANALYSIS:

1. **Wall-clock rows escape the lock in both directions.**
   - *Business date behind the calendar (production today):* a calendar-dated row (e.g. refund dated 2026-10-02) lies in a business day that has not been reached; no `NightAuditLog` exists for it, so `get_locking_audit(payment_date)` is `None` and the row can be voided directly at any time (`app/routes.py:7844`). It is also outside the current close's totals: `NightAuditService` selects `payment_date == business_date` and `charge_date == business_date` (`app/night_audit_service.py:207-213`, `:222-231`). The row will be swept into whichever close eventually reaches that calendar date.
   - *Business date ahead of the calendar (a close performed before midnight):* path A or B advances the date to D+1 while the calendar is still D; any correction, refund, voucher redemption, overstay or checkout extra posted before midnight is dated D, **into the day just sealed**. The sealed snapshot no longer matches recomputation (INV-B01/INV-B03 family) — the "close lags/leads midnight" risk recorded at `20260910_phase2_entry/BLOCKERS_AND_CARRYFORWARDS.md:10`.
2. **After K-7 (business-date dating) both cases close:** the open business date is by construction never locked (every close advances past it), so every new row lands in the open day and appears in that day's close.
3. **Sealed snapshots are frozen views.** Closed audit dates are served from `snapshot_json`, not recomputed (Q06-H1 rationale, `FOUNDER_DECISIONS.md:1225`). The historical record of 2026-08-09 (sealed, `snapshot_valid=1`) must not be changed (`FOUNDER_DECISIONS.md:1219-1227`). K-7 does not touch it.

---

## 6. Model defaults — what "remove or replace" would actually do

| Column | Python default | DB default | Nullable | If the Python default were removed and a writer omitted the value |
|---|---|---|---|---|
| `extra_charges.charge_date` | `date.today` (`app/models.py:775`) | none (created by `create_all`) | yes | row stored with `charge_date NULL` → invisible to every day-scoped query (`charge_date == …`), silently dropped from closes and GST |
| `payments.payment_date` | `date.today` (`:809`) | none | yes | same, for payments |
| `credit_vouchers.issued_date` | `date.today` (`:1817`) | `DEFAULT (date('now'))` = **UTC date** (`app/__init__.py:1794`) | NOT NULL | SQLite fills the **UTC** date — a different wall clock (00:00–05:29 IST maps to the previous day) |
| `business_date.current_date` | `date.today` (`:106`) | none | NOT NULL | seed path passes the value explicitly (`app/__init__.py:1851`) |

ANALYSIS: merely deleting `default=date.today` converts a wrong-basis date into either a NULL (payments, charges) or a UTC date (vouchers). A fail-closed alternative (a default that raises, or an explicit-date assertion before flush) or a business-date default must be chosen — an implementation-design question, listed in `K7_DECISION_REQUIRED.md` (K7-D3). No DDL change is needed for any of these options (SQLAlchemy `default=` is client-side); a NOT NULL change would be a schema change (B-3/B-4 territory) and is not proposed.

---

## 7. Night-audit posting basis

- Room rent: `charge_date=_bd` (`app/services.py:418`); idempotency keyed on `(reservation, 'room_rent', _bd)` (`:369-375`).
- No-show fee: `charge_date=business_date` (`app/noshow_service.py:151`); candidates `status in (Reserved, Confirmed) and arrival_date <= business_date and not exempt` (`:70-82`).
- Close totals: payments/charges/tax lines by equality with the audit date (`app/night_audit_service.py:207-234`); voids and shifts by `date(UTC timestamp)` (`:215-219`, `:240-244`).
- Snapshot: `full_report()` JSON + `compute_snapshot_hash` (`app/services.py:493-512`; `app/reports.py:3048-3078`). Q06-H2 is present in `tax_snapshot()` (`app/night_audit_service.py:1126-1166`).

ANALYSIS: night-audit *posting* is already business-dated (ADR-004 "Night audit — unchanged", `ADR-004:41`). The K-7 exposure is in what the close *counts*: calendar-dated rows from other writers, UTC-derived void and shift days.

---

## 8. What K-7 (unit 3.1 core) would and would not change — for orientation only

| Would change (if directed) | Would not change |
|---|---|
| the 8 writer rows (W-08/09/10/11/17/20/22/23) and voucher `issued_date`/expiry basis; the 3 model defaults; the `get_business_date()` fallback and the three secondary fallbacks | the 16 business-dated writers; night-audit posting; historical rows. ANALYSIS: no production row appears to carry a wall-clock date — the eight D11 rows carry business dates 2026-08-09/10 although created 2026-08-10/11 UTC (`FOUNDER_DECISIONS.md:47-56`), "Production holds no correction or refund rows" (`:1350`), and the voucher tables hold 0 rows (`20260930_adr011_production_application/prod_post_state.json`). NOT VERIFIED today against production itself |
| optionally (only if ruled): late-checkout applicability (B-10 #2), report default ranges (ADR-004 vs Phase 3 conflict), void/shift day mapping (B-10 #3), invoice/credit-note date (B-10 #1) | schema (no DDL), migrations (B-4 not engaged), production data |

---

## 9. Findings not previously recorded (summary)

| # | Finding | Citation | Kind |
|---|---|---|---|
| N-1 | Three further calendar fallbacks for the business date | `app/routes.py:4770`; `app/occupancy_engine.py:87`; `app/kpi_command_center.py:72` | unit 3.1 scope |
| N-2 | Operator close path B posts neither room rent nor no-shows; path A does | `app/reports.py:2896-3101` vs `app/services.py:353`, `:413-421` | Phase 3 (3.1/3.2) design question |
| N-3 | Path A posts room rent for every `CheckedIn` reservation with no date condition | `app/services.py:364` | stale-date hazard |
| N-4 | W-22/W-23 have no caller in `app/` | `app/services.py:1283` (only reference) | inventory accuracy |
| N-5 | Voucher issue date, expiry computation and expiry test use the calendar | `app/services.py:1950`, `:1965`, `:2009`, `:2077` | K-7 scope question |
| N-6 | Void day derived from UTC `voided_at` in the close | `app/night_audit_service.py:215-219` | K-7-adjacent |
| N-7 | Printed/e-invoice/GSTR-1 invoice date = UTC `checked_out_at` without IST conversion | `app/templates/invoice.html:39-40`; `app/templates/invoice_pdf.html:331-332`; `app/gst_einvoice.py:44`; `app/gstr_export.py:40`, `:192-193` | defect candidate (B-10 #1 adjacent) |
| N-8 | GSTR-1 CDNR filter compares `CreditNote.issued_at` (DATETIME) with `date` bounds — credit notes issued on the period's last day after 00:00:00 are probably excluded | `app/gstr_export.py:278-284` | defect candidate — **NOT VERIFIED** at runtime (SQLAlchemy not available outside the application environment; must be proven on a copy) |
| N-9 | `credit_vouchers.issued_date` has a UTC DDL default | `app/__init__.py:1794` | design input for K7-D3 |
| N-10 | `NoShowResult(...)` built with fields the NamedTuple does not have, after a `rollback()` inside the caller's close transaction | `app/noshow_service.py:29-32`, `:100-108` | latent defect (unreachable in normal flow) |
