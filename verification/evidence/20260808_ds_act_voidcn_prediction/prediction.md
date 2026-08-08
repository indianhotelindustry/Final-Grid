# `DS-ACT-VOIDCN` — sequencing evidence and coverage prediction

Both written **before** the dataset was authored, built or measured.

---

## Part 1 — why this and not `DS-ACT-GROUP`

`INV-D02` has been activated by a commissioned dataset, so the hold on
`DS-ACT-GROUP` is lifted and the standing plan makes it next.

The owner's stated principle says otherwise, and it was stated as
governing rather than as a one-off:

> A regression dataset should activate the highest-risk verification
> before extending ordinary business coverage, because Wave 0's objective
> is verification completeness rather than business-feature completeness.

Applied to what is left, and read from the registries:

| Candidate | Activates | Also | Obstacle |
|---|---|---|---|
| **`DS-ACT-VOIDCN`** | **`INV-D05`** — VACUOUS, certification-blocking | **`Q11`** — VACUOUS, D1, severity BLOCK | none |
| `DS-ACT-CORPCREDIT` | `INV-C06` — VACUOUS, certification-blocking | 2 D2 surfaces | **structural, see below** |
| `DS-ACT-GROUP` | **nothing** | 1 D2 surface | none |
| `DS-ACT-OVERPAY` | `INV-A06` | — | blocked on R-5 (governance) |

`DS-ACT-GROUP` activates no invariant, no fault and no parity quantity —
nothing in D1, D4 or D5 references `group_blocks`. Under the principle
above it is the lowest-priority remaining item, not the highest.

### `DS-ACT-CORPCREDIT` has a structural obstacle, found while checking

`companies` is a **PRESERVED master table** (`schema.PRESERVED_TABLES`),
and `builder.content_hash` deliberately covers only the transactional and
guest tables. Measured:

```
companies          PRESERVED       content_hash covers it: False
credit_notes       transactional   content_hash covers it: True
void_requests      transactional   content_hash covers it: True
group_blocks       transactional   content_hash covers it: True
```

So a dataset declaring a company would carry master data that is **not
part of its own identity**: `strip()` never clears it, and the hash a
certificate is issued against would not cover it. The exclusion is
deliberate and well-argued — master data changes when the hotel
reconfigures itself and must not invalidate every certificate at once —
but it was reasoned about master data *inherited from production*, not
master data a dataset *declares*.

That needs deciding before `DS-ACT-CORPCREDIT` can be written, and it is
not a decision to take while writing it. Recorded; not resolved here.

### Conclusion

**`DS-ACT-VOIDCN` is the highest-priority path the repository supports.**
It activates a certification-blocking invariant and a BLOCK-severity parity
quantity, across two layers, with no obstacle. `DS-ACT-GROUP` remains
next-but-one and is unaffected.

---

## Part 2 — a production defect this dataset will expose

Found while checking how a refund is constructed, before writing anything.

`services.post_cancellation_disposition` creates the refund row as:

```python
refund_payment = Payment(
    ...
    payment_purpose   = 'refund',
    is_reversal       = True,
    correction_reason = f'Cancellation refund | {reason_clean}',
)
```

**`corrects_id` is never set.** The only four assignments of `corrects_id`
in `services.py` are inside `post_payment_correction` and
`post_extra_charge_correction`; the refund path is not one of them.

`INV-D02` requires that *every* row flagged `is_correction` **or**
`is_reversal` carries a `corrects_id` that resolves. So **every
cancellation refund the application issues violates `INV-D02`** — a
CRITICAL, RELEASE_BLOCKING invariant.

It has never been seen because production has issued no refunds, the same
fact that kept `INV-D02` VACUOUS until yesterday.

The dataset will therefore model the refund **exactly as the application
builds it** and declare `INV-D02: VIOLATED`. Modelling it with a
`corrects_id` would produce a green dataset describing an application that
does not exist.

---

## Part 3 — predicted `coverage_expectation`

### `surfaces_added` — none

Every resolver this dataset satisfies already resolves on production. No
CheckedIn reservation, no company, no group block.

### `surfaces_lost` — 1

```
reports.night_audit_snapshot__night_audit_log
```

No night audit declared, same as both previous datasets and for the same
reason.

### `invariants_activated` — 1

```
INV-D05   population 0 -> 2   (one void_requests row, one credit_notes row)
```

### `invariants_deactivated` — 6

```
INV-B01, INV-B02, INV-B03, INV-B05    no night audit
INV-C01, INV-C05                       cash only, no OTA head
```

**Six, not the seven `DS-ACT-CORRECTION` lost and not the eight
`DS-ACT-INHOUSE` lost.** `INV-D07` is the difference: its population is the
`overpayment_logs` table, which was empty in both earlier datasets. This
one has no overpayment either — so `INV-D07` **should also deactivate**,
making it seven.

Correcting the prediction before recording it: **seven**, the same set as
`DS-ACT-CORRECTION`. `INV-A03` keeps a population here too, because this
dataset has an extra charge.

### The risk in this prediction

`Q11` is a D1 parity quantity and **the coverage ledger does not measure
D1** — that is a stated gap in `coverage.py`. So the ledger cannot confirm
the `Q11` activation that is half this dataset's justification. It will
have to be measured separately, the same way `DS-ACT-INHOUSE`'s D2 claim
had to be.

Stated in advance so it is not read as hindsight.
