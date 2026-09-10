# Writer Coverage - all 33 financial constructor sites at `aa6d9e91`

Directive FG-P1-VERIFICATION-COMPLETION-20260909-01. The 33 sites are the `Payment(` / `ExtraCharge(` constructor calls found by the completion review's `ast` scan (routes 11, services 9, seed 5, dev_seed 4, cico 1, noshow 1, pos 1, reports 1). All 33 carry `folio_id=`. The 24 application writers map onto them exactly; the remaining 9 are fixtures.

Runtime evidence: `verify_writers.py` sets A-D (`writers_set{A,B,C,D}.json/.txt`). Earlier runtime evidence is cited by its own pack and is **not** re-claimed as new.

Audit classes: **A-STRICT** = `audited_financial_write` / `_write_audit_strict` (row proven in session, else the transaction rolls back; proven by injected failure). **A-NF-caller** = the service accepts an `audit_writer` and the caller passes `routes._write_audit`, which never raises; the service swallows audit exceptions. **A-NF-entity** = a `_write_audit` row on another entity (Reservation / CreditVoucher), no row for the financial row. **A-DED** = dedicated log table in the same transaction. **run-level** = NightAuditLog / NightAuditReopenLog only. **A0** = no audit row.

## 1. The 24 writers

| ID | Module : function | Object | Attribution mechanism | Audit mechanism (observed) | Runtime status | Runtime evidence |
|---|---|---|---|---|---|---|
| W-01 | routes.py : bulk_booking_api | Payment (advance) | R-1 `_billing_folio_id` | A-STRICT (row added by Phase 1) | **exercised now** + injection | set A W-01-01..07, A1 |
| W-02 | routes.py : new_reservation | Payment (advance) | R-1 | A-STRICT | **exercised now** + injection | set A W-02-01..08, A1/A2 |
| W-03 | routes.py : checkout (OTA auto-settlement) | Payment | R-1 | A-STRICT | **exercised now** (paid_at_ota fixture, source OTA / MMT booking id) | set A W-03-01..07 |
| W-04 | routes.py : checkout (settlement loop) | Payment | R-1 | A-STRICT | **exercised now** + injection (sets A, D) | set A W-04-00..07, A1/A2; set D |
| W-05 | routes.py : add_payment | Payment | R-1 | A-STRICT | already verified (T-W05, T-A01/03); re-observed set D | 20260909_phase1_execution; set D D-05 |
| W-06 | routes.py : walkin_search_express | Payment | R-1 | A-STRICT (row added by Phase 1) | **exercised now** + injection (sets A, D) | set A W-06-01..07, A1; set D |
| W-07 | routes.py : settle_credit | Payment (credit_recovery) | R-1 (static) | A-STRICT (static) | **BLOCKED - pre-existing defect**: `Payment(... notes=...)` raises `TypeError: 'notes' is an invalid keyword argument for Payment`; the model has no `notes` column; keyword present since baseline commit `b5b2514` (2026-08-07); untouched by Phase 1. The route cannot post any credit-recovery payment. | set A W-07-01 (finding) |
| W-08 | services.py : post_payment_correction (reversal) | Payment | R-3 `inherit_billing_folio_id` | A-NF-caller (`payment_reversed`) | already verified (T-W08, T-Q02); re-observed via the void route's correction-pair path | set B W-08-01..07 |
| W-09 | services.py : post_payment_correction (replacement) | Payment | R-3 | A-NF-caller (`payment_corrected`) | **exercised now** via `POST /payment/<id>/void` with Admin audit override on a locked date | set B W-09-00..08 |
| W-10 | services.py : post_cancellation_disposition (refund) | Payment (refund, is_reversal) | R-4 / CD-3 `resolve_billing_folio_id` | A-NF-caller (`cancellation_refund`) | **exercised now** (service with the cancel route's `_write_audit`) | set B W-10-01..08 |
| W-11 | services.py : redeem_credit_voucher | Payment | R-1 (static) | A-NF-entity (`voucher_used`, static) | **BLOCKED - pre-existing defect**: same `notes=` TypeError as W-07; route returns HTTP 500 "redemption failed"; present since `b5b2514`; untouched by Phase 1 | set B W-11-01 (finding) |
| W-12 | services.py : CheckInService.complete_full_checkin (deposit) | Payment | R-1 | A-NF-entity (`checkin_full`, written after commit) | **exercised now** (sets A, D) | set A W-12-01..07; set D |
| W-13 | cico_service.py : post_charge | ExtraCharge | R-1 | A-DED (CICOChargeLog + AuditLog) | already verified (T-W13); re-observed set D | set D D-05 |
| W-14 | noshow_service.py : process_reservation_noshow | ExtraCharge (no-show fee) | R-1 | A-DED (NoShowLog + Reservation `noshow_posted`, same commit) | **exercised now** (sets A, D) | set A W-14-01..08; set D |
| W-15 | pos.py : post_charge | ExtraCharge | R-1 | A-STRICT (atomic, Phase 1) | already verified (T-W15, T-A02/04); re-observed set D | set D D-05 |
| W-16 | reports.py : _rerun_skipped_audit | ExtraCharge (room_rent [recovered]) | R-2 | run-level (NightAuditReopenLog + log update) | **exercised now**: 4 recovered rows, each attributed to its own reservation's folio A | set C W-16-00..10 |
| W-17 | routes.py : checkout (extra charge) | ExtraCharge | R-1 | A-STRICT | **exercised now** | set A W-17-01..07 |
| W-18 | routes.py : checkout (overpay -> tip) | ExtraCharge (tip) | R-1 | A-STRICT | **exercised now** (sets A, D) | set A W-18-01..07; set D |
| W-19 | routes.py : checkout (overpay -> other income) | ExtraCharge (other_income) | R-1 | A-STRICT | **exercised now** (sets A, D) | set A W-19-01..07; set D |
| W-20 | routes.py : add_overstay_charge | ExtraCharge (overstay) | R-1 | A-STRICT | already verified at runtime (W-20 closure 23/23); **not repeated**; repeat-call rounded-hour behaviour remains a carry-forward product finding | 20260909_w20_runtime |
| W-21 | services.py : run_night_audit | ExtraCharge (room_rent) | R-2 | run-level (NightAuditLog) | already verified (T-R01/R02/R04); re-observed sets A, D | set A W-21-R1; set D D-21 |
| W-22 | services.py : post_extra_charge_correction (reversal) | ExtraCharge | R-3 | A-NF-caller (`charge_reversed`) | **exercised now** (service; no route caller exists in `app/`) | set B W-22-01..08 |
| W-23 | services.py : post_extra_charge_correction (replacement) | ExtraCharge | R-3 | A-NF-caller (`charge_corrected`) | **exercised now** (service) | set B W-23-01..08 |
| W-24 | services.py : convert_overpayment_to_upsell | ExtraCharge (room_upsell) | R-2 | A0 | **exercised now** (CASE A after a night audit; rate bump + corrective charge) | set A W-24-00..07 |

## 2. The 9 fixture sites

| Site | Object | Attribution | Status |
|---|---|---|---|
| seed.py x5 | Payment / ExtraCharge | `_folio()` helper (CD-4) | static proof (ast); fixtures, not writers |
| dev_seed.py x4 | Payment / ExtraCharge | folio_id set | static proof (ast); already compliant before Phase 1 |

## 3. Counts

| | Writers | Which |
|---|---|---|
| Runtime-verified before this directive | 6 | W-05, W-08, W-13, W-15, W-20, W-21 |
| Newly runtime-exercised by this directive | 16 | W-01, W-02, W-03, W-04, W-06, W-09, W-10, W-12, W-14, W-16, W-17, W-18, W-19, W-22, W-23, W-24 |
| **Runtime-verified in total** | **22 of 24** | |
| Static proof only | 2 | W-07, W-11 - blocked by the pre-existing `notes=` TypeError (see section 5) |
| Audit-failure injection proven at runtime | 8 | W-01, W-02, W-04, W-05, W-06, W-15, W-20 (closure), plus W-17/W-18 by the same checkout transaction |

Every one of the 22 runtime rows: row created, `folio_id` non-null, `folio_id` equal to the reservation's folio A, that folio belonging to the same reservation with letter A, and no new unattributed row on any copy (NEW-01 on all four sets).

## 4. Audit coupling against Q-5

Q-5 requires "financial mutation and its required audit record succeed together or the operation fails" for Phase 1 financial writers that are touched by implementation. Observed classes:

| Class | Writers | Count |
|---|---|---|
| A-STRICT (Q-5 satisfied, proven by injection) | W-01, W-02, W-03, W-04, W-05, W-06, W-07 (static), W-15, W-17, W-18, W-19, W-20 | 12 |
| A-DED (dedicated log in the same transaction; not the strict helper) | W-13, W-14 | 2 |
| A-NF-caller (caller-supplied `_write_audit`, swallowed on failure) | W-08, W-09, W-10, W-22, W-23 | 5 |
| A-NF-entity (audit on another entity, after or beside the commit) | W-11 (static), W-12 | 2 |
| run-level (NightAuditLog / ReopenLog; no per-row audit, by design) | W-16, W-21 | 2 |
| A0 (no audit row) | W-24 | 1 |

The Phase 1 completion report described this split accurately ("+ strict" only on routes-level writers and POS; "R-1"/"R-2" only elsewhere), so nothing was hidden. But measured against Q-5's wording, **10 of the 24 touched writers do not have strict financial-row audit coupling**. This is recorded as a documented limitation for the Founder (VERIFICATION_COMPLETION.md section 8), not silently accepted and not fixed here.

## 5. Writers not runtime-exercised - exact reason

| Writer | Reason | Evidence |
|---|---|---|
| W-07 settle_credit | `app/routes.py` passes `notes=` to `Payment(...)`; `Payment` has no such column, SQLAlchemy raises `TypeError`, the route's `except` flashes "Credit settlement failed" and redirects (HTTP 302), no row is written. Introduced in `b5b2514` (2026-08-07, pre-Wave-1 baseline); `git diff e69f2ac..aa6d9e91` contains no `notes` line - Phase 1 did not touch it. | set A log: `TypeError: 'notes' is an invalid keyword argument for Payment` at routes.py:9328 |
| W-11 redeem_credit_voucher | `app/services.py` passes `notes=` to `Payment(...)`; same TypeError; the voucher route answers HTTP 500. Same origin commit; untouched by Phase 1. | set B log: TypeError at services.py:2029 |

Both writers' attribution and audit wiring are proven statically (the `folio_id=` and `_write_audit_strict` / `audit_writer` calls are in the source, ast-verified). Neither can be proven at runtime on this codebase without a code change, which this directive forbids.
