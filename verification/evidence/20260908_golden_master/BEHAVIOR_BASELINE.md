# Behavioural Baseline — as of HEAD `e69f2ac`, anchor `51dd83b7…`

Sources: the code paths enumerated in `verification/evidence/20260908_phase1_implementation_readiness/FINANCIAL_WRITER_INVENTORY.md` (24 writers, W-01…W-24, line numbers at `237db2ad`/`e69f2ac`), the recaptured golden master, the invariant run and the replay run of 2026-09-09. **Nothing here was executed against production**; the harness runs used `make_copy()` copies. No behaviour was modified.

## 1. Financial creation paths — current behaviour

| Path | Writer(s) | Behaviour now | Date basis | Audit now | Reservation available |
|---|---|---|---|---|---|
| Payment creation — advance/settlement at booking, check-in, checkout, add-payment, walk-in express, credit settle, deposit | W-01, W-02, W-03, W-04, W-05, W-06, W-07, W-12 | `Payment(...)` constructed with `reservation_id`; **`folio_id` never set → NULL** | business date (`get_business_date()` / `today_biz`) | A-NF (`_write_audit`, flush-only, never raises) at W-02/03/04/05/12; **none** in W-01, W-06, W-07 | yes |
| Voucher redemption payment | W-11 (`redeem_credit_voucher`) | settlement payment, NULL folio | **wall clock** (`_d.today()`) | none in function | yes |
| Refund | W-10 (`post_cancellation_disposition`) | `Payment(payment_purpose='refund', is_reversal=True)`, NULL folio | **wall clock** (`_date.today()`) | none in function | yes |
| Payment correction | W-08 / W-09 (`post_payment_correction`) | reversal + replacement rows; `folio_id` **inherited** from the original (NULL today) | **wall clock** (`today`) | caller-dependent | yes |
| Extra-charge creation — checkout extra/tip/other income, overstay, early/late (CICO), no-show, POS | W-17, W-18, W-19, W-20, W-13, W-14, W-15 | `ExtraCharge(...)` with `reservation_id`; **`folio_id` never set → NULL** | business date except W-17 (**model default `date.today`**, no `charge_date` passed) and W-20 (**`now().date()`**) | A-NF at W-17/18/19/20; dedicated log tables at W-13 (`CICOChargeLog`) and W-14 (`NoShowLog`); **W-15 commits before auditing** | yes |
| Charge correction | W-22 / W-23 | reversal + replacement; `folio_id` inherited | **wall clock** | caller-dependent | yes |
| Room rent (night audit) | W-21 (`run_night_audit`) | per in-house reservation per business date, `ExtraCharge(charge_type='room_rent', charge_date=_bd)`, **`folio_id` NULL by design**; idempotent on reservation × type × date; marks `ReservationNightRate.is_posted/is_locked` | business date | `NightAuditLog` for the run; no per-row AuditLog | yes |
| Room rent recovery | W-16 (`_rerun_skipped_audit`) | same shape, `[recovered]`, idempotent | business date (`target_date`) | none per row | yes |
| Room upsell | W-24 (`convert_overpayment_to_upsell`) | `charge_type='room_upsell'`, NULL folio | business date | none in function | yes |

**Observed on the production copy:** the night audit has never posted room rent for the four reservations (`reservation_night_rates.is_posted=0` ×4; 0 `room_rent` rows); the two charges are `late_checkout` rows written by the CICO path at checkout (`audit_logs` actions `auto_late_checkout_charge`, `checkout`).

## 2. Folio lifecycle — current behaviour

- Folio A ("Guest") is created for every reservation by the `after_insert` listener (`app/models.py:745`); the four production reservations each have exactly one Folio A.
- Additional folios only via `folio.create_folio` (Phase 2a: Admin/Manager, fail-closed, audit-coupled). `list_folios` is Admin/Manager in code (FD-015 approves widening; not implemented).
- Transfers only via `folio.transfer_charge` / `transfer_payment` (Phase 2a); they tolerate a NULL source folio.
- `calculate_folio_amount` sums charges/payments routed to the folio and **excludes room-rent rows**; on every production folio it returns zero (no rows are attributed). Reconciliation (`calculate_stay_amount`, night-audit folio control, replay ledger) reads the reservation level.

## 3. Correction, void and audit — current behaviour

- Corrections never mutate; they post reversal + replacement rows linked by `corrects_id` (both tables). Void/refund maker-checker (`can_request_void`/`can_approve_void`, Admin/Manager) — preserved strength N2; unchanged.
- `_write_audit` (`app/routes.py:312-334`) flushes an `AuditLog` row and **never raises**; callers commit afterwards. Consequence: an audit-write failure does not stop the financial commit.
- POS (`app/pos.py:110-134`): charge committed **first**, audit attempted **second**, exceptions swallowed.
- Phase 2a folio endpoints use `_audited()` — row proven in session or the mutation is rolled back — the strict pattern that Q-5 makes binding for Phase 1 writers.

## 4. Surface baseline — non-200 surfaces captured as rendered

`auth.login` 302 · `main.index` 302 · `main.guest_database` 302 · `main.advance_receipt__any_reservation` 302 · `main.edit_reservation__any_reservation` 302 · `portal.view_submission__any_reservation` 302 · `reports.night_audit` 302 · `booking.availability_api` 400 · `main.api_cico_preview` 400 · `main.voucher_lookup` 400 · `main.load_tab__booking` 404 · `main.setup_wizard` 404. These are the framework's recorded responses for the `admin` principal (and anonymous, where applicable) at frozen time 2026-08-10T12:00; they are baseline, not findings. The single `folio_bp` surface, `folio.list_folios__checked_out_reservation`, returns 401 to anonymous callers and 200 to the principal — the Phase 2a-intended state.

## 5. Temporal and scheduler baseline

Business date 2026-08-10, unlocked; calendar date at capture 2026-09-09 (30 days behind). The scheduler (`night_audit_job`, `daily_backup_job`, `notification_queue_flush`, `log_pruning_job`, `predictive_maintenance_job`) starts with `create_app()`; during harness runs it started inside the harness process against the copy and was shut down at exit (logged); no job fired. `audit_logs` oldest row 2026-08-09 — the 90-day prune would first act on or about 2026-11-07 on a running production instance.

## 6. Replay baseline

`replay-verify --tag production`: 10 business dates (2026-08-01 … 2026-08-10) reconstruct exactly as stored; 0 differences. The untracked August ledgers under `verification/ledgers/production/` remain the stored replay.

## 7. What this baseline does not cover

Excel/PDF export branches (V5) · POST-only and non-GET endpoints (121 catalogue gaps) · dataset runs (`ds-run`) · fault injection (`fault-run`, INCOMPLETE by design until D7/D9) · any behaviour of the encrypted application-backup path · concurrent-writer behaviour (R5).
