# Semantic Review Register - observations from bounded runtime verification

Directive FG-P1-ACCEPTANCE-PREP-20260909-01. Each item records an observed interaction between an invariant and existing application semantics. **Nothing was changed**: not the invariant, not the behaviour. Each is classified **SEMANTIC REVIEW REQUIRED - NO PHASE 1 REGRESSION ESTABLISHED**. Phase 1 changed neither the dates, purposes, reversal flags nor `corrects_id` handling of any row; it added `folio_id` only.

## SR-1 - INV-B06 vs advance-payment / business-date semantics

| | |
|---|---|
| Invariant | INV-B06 "A payment is never dated outside the stay it belongs to" (MEDIUM / OPERATIONAL_WARNING) |
| Observed | On the broad copy (set A) INV-B06 reported payments 7 and 8: advance payments of 300 and 400 posted by `new_reservation` (W-02) and `bulk_booking_api` (W-01), dated on the business date 2026-08-10 for stays starting 2026-09-11 and 2026-08-13. On set B, payment 10 (advance via W-02) the same way. Production has no advance payment, so the invariant has never fired there. |
| Application semantics | `new_reservation` dates the advance on the booking's business date by design ("payment is a LIABILITY (guest deposit) on the booking date"; `payment_purpose='advance'`). Both are pre-Phase-1 behaviours. |
| Why not a Phase 1 regression | Phase 1 added `folio_id=_billing_folio_id(reservation)` and the strict audit call at these writers; `payment_date` and `payment_purpose` are unchanged (`git diff e69f2ac..aa6d9e91`). The invariant fires on the pre-existing dating rule. |
| Question for review | Should INV-B06 exempt `payment_purpose='advance'` (a deposit legitimately precedes the stay), or should advance dating change? Either answer changes report figures and belongs to the business-date programme. |
| Do NOT change until resolved | the invariant, payment behaviour, business-date behaviour |
| Evidence | `inv_run_setA.txt` (INV-B06 affected objects), `inv_run_setB.txt`; `VERIFICATION_COMPLETION.md` section 3 |
| Suggested owner | Phase 3 (ADR-004 business-date authority; BACKLOG B-10) with a Phase 6 invariant-declaration update |

## SR-2 - INV-D02 vs cancellation-refund semantics

| | |
|---|---|
| Invariant | INV-D02 "Every correction and reversal references the transaction it corrects" (CRITICAL / RELEASE_BLOCKING) |
| Observed | On set B, INV-D02 reported payment 11: the cancellation refund posted by `post_cancellation_disposition` (W-10) as `is_reversal=True`, `payment_purpose='refund'`, with `corrects_id NULL`. The same shape is **declared expected** by the registered dataset `DS-ACT-VOIDCN` ("INV-D02: VIOLATED" for its credit-note refund), so the platform already knows refunds fire this rule. |
| Application semantics | A cancellation refund reverses an advance as a whole, not a specific payment row; the service sets `is_reversal=True` and records the reason in `correction_reason`, never a `corrects_id`. Pre-Phase-1 behaviour. |
| Why not a Phase 1 regression | Phase 1 added `folio_id=resolve_billing_folio_id(reservation, ...)` to the refund row only; `is_reversal`, `corrects_id`, `payment_purpose` unchanged. |
| Question for review | Should a refund carry `corrects_id` (which payment it refunds - ambiguous when several advances exist), or should INV-D02 scope reversals to `payment_purpose in ('correction', ...)` and exclude refunds? |
| Do NOT change until resolved | the invariant, refund behaviour, cancellation behaviour |
| Evidence | `inv_run_setB.txt` (INV-D02 affected objects); `DATASET_RESULTS.md` (DS-ACT-VOIDCN declaration) |
| Suggested owner | Phase 6 invariant review; or Phase 2b if the maker-checker matrix (B-2) covers refunds |

## Observations recorded but not registered as semantic reviews

| Observation | Where | Why not a review item |
|---|---|---|
| INV-B04 / INV-B01 / INV-B03 / INV-R01 violations on sets A and B | `VERIFICATION_COMPLETION.md` section 3 | attributed to verification fixtures (a stay inserted into the closed 2026-08-09; a payment moved onto that date to reach the correction route; a rate change after close) or to K-7 wall-clock dating already ruled to Phase 3 (Q-3) |
| Checkout auto-posts a late-checkout charge from the calendar clock | finding F-7 | K-7 family; Phase 3 |
| D1 parity divergences beyond Q14 (Q04, Q07, Q12, Q15, Q18 + pre-existing Q06/Q17/Q20) | `Q14_PARITY.md` section 2 | cross-implementation definitional differences in the D1 layer; none involve `folio_id`; Phase 6 parity review |
| INV-D07 moved VACUOUS -> HOLDS on set D | `inv_run_setD.txt` | positive: an overpayment record now exists on a copy with activity; nothing to review |
