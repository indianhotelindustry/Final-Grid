# Phase 1 — Financial Writer Inventory

**Directive:** FG-P1-IMPLEMENTATION-READINESS-20260908-01 · **Recorded:** 2026-09-08 · **HEAD:** `e69f2ac` · **Method:** re-enumerated from the current tree — every `Payment(`, `ExtraCharge(` and `Folio(` constructor under `app/` (fixtures `seed.py`/`dev_seed.py` and `models.py` excluded), plus a search for raw SQL / bulk inserts into `payments`/`extra_charges` (**none exist**) and for `folio_id` assignments outside constructors (**only the two Phase 2a transfer endpoints**). Line numbers at `e69f2ac` (identical to checkpoint `237db2ad` for these files). One apparent match, `routes.py:9312`, is a docstring and is excluded.

**Result: 24 originating/derived financial writers (12 Payment, 12 ExtraCharge), 1 folio creator, 1 folio listener.** Every writer has the reservation available at construction time.

## Legend

Audit coupling — **A0** none in the writing function · **A-NF** `_write_audit` (flush-only, never raises) then caller commits → audit failure does not block commit · **A-POST** commit first, audit second, exceptions swallowed · **A-DED** dedicated log table row in the same session · **A-STRICT** Phase 2a `_audited` pattern (row proven in session, else rollback).
Business date — **BD** controlled business date · **WC** wall clock (`date.today()` / `now().date()`) · **MD** model default (`date.today`) because no date passed.
Authorization — roles that can reach the writer; "login" = blueprint `before_request` login only; **NV** = caller role not verified in this review.

## Inventory

| ID | File:line | Function | Type | Pay | Chg | Rev/Ref | Room-rent | `folio_id` now | Res ctx | Folio ctx | Audit | BD | Authorization | Idem | Phase 1 treatment | Test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-01 | `routes.py:1930` | `bulk_booking_api` | advance / settlement | Y | – | – | – | NULL | Y (`first_res`) | via reservation | A0 | BD (`today_biz`) | login only | N | R-1 resolver; add audit coupling | T-P01 |
| W-02 | `routes.py:2195` | `new_reservation` | advance | Y | – | – | – | NULL | Y | via reservation | A-NF | BD | login only | N | R-1; strict coupling | T-P02 |
| W-03 | `routes.py:3242` | `checkout` (OTA settlement) | settlement | Y | – | – | – | NULL | Y | via reservation | A-NF | BD | login; Admin/Manager for override at `:3495` | partial | R-1; strict coupling | T-P03 |
| W-04 | `routes.py:3274` | `checkout` | settlement | Y | – | – | – | NULL | Y | via reservation | A-NF | BD | as W-03 | partial | R-1; strict coupling | T-P04 |
| W-05 | `routes.py:5745` | `add_payment` | settlement / purpose | Y | – | – | – | NULL | Y | via reservation | A-NF | BD | Admin, Manager, FrontDesk (`:5652`) | Y (`idem:` key) | R-1; strict coupling | T-P05 |
| W-06 | `routes.py:7448` | `walkin_search_express` | settlement | Y | – | – | – | NULL | Y | via reservation | A0 | BD | login only | partial | R-1; add audit coupling | T-P06 |
| W-07 | `routes.py:9227` | `settle_credit` | credit_recovery | Y | – | – | – | NULL | Y | via reservation | A0 | BD | Admin, Manager, FrontDesk, Accountant (`:9176`) | N | R-1; add audit coupling | T-P07 |
| W-08 | `services.py:922` | `post_payment_correction` (reversal) | correction | Y | – | Y | – | **inherits** original | Y | inherits | caller | **WC** (`today`) | callers `billing.py:433`, `routes.py:7752` — NV | N | R-3 ratify; **fail-closed if original NULL** | T-P08 |
| W-09 | `services.py:953` | `post_payment_correction` (replacement) | correction | Y | – | Y | – | inherits | Y | inherits | caller | WC | as W-08 | N | R-3 ratify; fail-closed if original NULL | T-P09 |
| W-10 | `services.py:1489` | `post_cancellation_disposition` | refund (`is_reversal`) | Y | – | Y | – | NULL | Y | via reservation | A0 | **WC** (`_date.today()`) | caller `routes.py:8741` — NV | partial | R-4 resolver (CD-3); strict coupling; **date unchanged in Phase 1** | T-P10 |
| W-11 | `services.py:1785` | `redeem_credit_voucher` | settlement | Y | – | – | – | NULL | Y | via reservation | A0 | **WC** (`_d.today()`) | `voucher_redeem` Admin/Manager/FrontDesk; `new_reservation` login | N | R-1; strict coupling; date unchanged | T-P11 |
| W-12 | `services.py:2791` | `CheckInService.complete_full_checkin` | deposit | Y | – | – | – | NULL | Y (`reservation_id`) | via reservation | A-NF | BD | callers `routes.py:2557`, `:2867` — NV | partial | R-1; strict coupling | T-P12 |
| W-13 | `cico_service.py:353` | `post_charge` | early/late check-in/out | – | Y | – | – | NULL | Y | via reservation | A-DED (`CICOChargeLog` + AuditLog) | BD (or passed) | checkout/check-in routes — NV | **Y** | R-1 | T-C01 |
| W-14 | `noshow_service.py:143` | `process_reservation_noshow` | no-show fee | – | Y | – | – | NULL | Y | via reservation | A-DED (`NoShowLog`, `posted_by_user_id` None when automated) | BD (param) | night audit (automated) or manual route — NV | lock | R-1; **system-actor provenance dependency (AR-013)** | T-C02 |
| W-15 | `pos.py:110` | `post_charge` | POS charge | – | Y | – | – | NULL | Y | via reservation | **A-POST** (commit, then audit, swallowed) | BD | Admin, Manager, FrontDesk (`pos.py:33`) | N | R-1; **re-order to strict coupling** | T-C03 |
| W-16 | `reports.py:3341` | `_rerun_skipped_audit` | room_rent [recovered] | – | Y | – | **Y** | NULL | Y | via reservation | A0 (function) | BD (`target_date`) | `reports.py:3460` — NV | **Y** (`already` check) | R-2 resolver; keep idempotency | T-R02 |
| W-17 | `routes.py:3055` | `checkout` (extra) | extra charge | – | Y | – | – | NULL | Y | via reservation | A-NF | **MD** (no `charge_date`) | as W-03 | N | R-1; strict coupling; **date defect noted, not fixed** | T-C04 |
| W-18 | `routes.py:3390` | `checkout` (tip) | tip | – | Y | – | – | NULL | Y | via reservation | A-NF | BD | as W-03 | N | R-1 | T-C05 |
| W-19 | `routes.py:3418` | `checkout` (other income) | other_income | – | Y | – | – | NULL | Y | via reservation | A-NF | BD | as W-03 | N | R-1 | T-C06 |
| W-20 | `routes.py:7976` | `add_overstay_charge` | overstay | – | Y | – | – | NULL | Y | via reservation | A-NF | **WC** (`now.date()`) | Admin, Manager, FrontDesk (`:7890`); waiver Admin/Manager (`:7950`) | N | R-1; strict coupling; date defect noted | T-C07 |
| W-21 | `services.py:147` | `run_night_audit` | **room_rent** | – | Y | – | **Y** | NULL by design | Y (`in_house` loop) | via reservation | `NightAuditLog` (no per-row AuditLog) | BD (`_bd`) | scheduler (automated) or `routes.py:4835` manual — NV | **Y** (`already_posted`) | R-2 resolver; keep idempotency; **AR-013 dependency** | T-R01 |
| W-22 | `services.py:1007` | `post_extra_charge_correction` (reversal) | correction | – | Y | Y | inherits type | inherits | Y | inherits | caller | WC | callers NV | N | R-3 ratify; fail-closed if original NULL | T-C08 |
| W-23 | `services.py:1041` | `post_extra_charge_correction` (replacement) | correction | – | Y | Y | inherits type | inherits | Y | inherits | caller | WC | callers NV | N | R-3 ratify; fail-closed if original NULL | T-C09 |
| W-24 | `services.py:2537` | `convert_overpayment_to_upsell` | **room_upsell** | – | Y | – | Y (room revenue) | NULL | Y | via reservation | A0 (function) | BD | callers `routes.py:3440` (checkout), `:8944` — NV | partial | R-2 resolver | T-R03 |
| F-01 | `folio.py:237` | `create_folio` | folio creation | – | – | – | – | n/a | Y (locked) | creates | **A-STRICT** | – | Admin, Manager (Phase 2a, frozen) | Y (unique letter) | **untouched** | Phase 2a T04–T06, T23 |
| L-01 | `models.py:745` | `_auto_create_default_folio` | folio A on reservation insert | – | – | – | – | n/a | Y | creates A | none | – | implicit | unique constraint | **untouched**; CD-1 covers absence | T-L01 |

## Observations that drive the plan

1. **Reservation context is available at all 24 sites**; no writer is `BLOCKED — attribution design required`. Folio context is never available today; every site resolves through the reservation (R-1) or inherits (R-3).
2. **Audit coupling is weak everywhere except Phase 2a.** Pattern A-NF (`_write_audit` flush-only, never raises; `routes.py:312-334`) means a failed audit write is logged and the financial commit proceeds. W-15 (POS) commits the charge **before** attempting its audit and swallows any error. W-01, W-06, W-07, W-10, W-11, W-16, W-24 write no `AuditLog` row in the writing function at all. See `READINESS_REPORT.md` §12.
3. **Business date is mixed.** 16 sites use the controlled business date; W-08/09/22/23 (corrections), W-10 (refund), W-11 (voucher) use wall clock; W-17 passes no date (model default `date.today`); W-20 uses `now.date()`. Phase 1 attribution work touches these sites but **does not change their dates** unless the Founder rules otherwise (`FOUNDER_DECISION_GATE.md`).
4. **Idempotency exists where it matters most**: W-21 and W-16 (room rent, keyed on reservation × `charge_type` × `charge_date`), W-13 (CICO), W-05 (`idem:` reference). Others rely on request semantics; none is made worse by attribution.
5. **Automated writers**: W-21 (night audit, scheduler) and W-14 when called from it. AR-013 controls do not yet exist; Phase 1 changes only *what* they attribute, not *when* or *under whose authority*. Dependency recorded, not resolved.
6. **Authorization coverage varies**: seven sites are reachable by any authenticated role (W-01, W-02, W-03/04/17/18/19 via `checkout` apart from the override check, W-06). This is Register R6 territory (Phase 4) and is not changed by Phase 1; recorded so the negative tests know what "unauthorized" means today.
7. **Two Payment sites carry `payment_date` explicitly from the business date already** in the walk-in/bulk paths (W-01, W-06) — attribution there is a one-argument change.
