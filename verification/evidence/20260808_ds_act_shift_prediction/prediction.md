# `DS-ACT-SHIFT` — coverage prediction, made before implementation

Written **before** the dataset was authored or built.

Target: **`Q21`, cash position and variance** — VACUOUS on production
because the hotel has never opened a shift. `Severity.BLOCK` in the D1
registry. No invariant and no fault references a shift table, so `Q21` is
the whole of what this dataset activates.

---

## The narrative and the arithmetic

One front-desk shift on 5 October, opened with a ₹2,000 float. A guest
checks in, stays a night and settles ₹1,050 in cash inside the shift
window. ₹200 of petty cash goes out. The drawer is counted at close and
matches.

`shift_service.calculate_expected_cash`:

```
opening_cash                         2,000.00
+ cash payments received in window   1,050.00
- cash payments voided in window         0.00
+ float_add adjustments                  0.00
- payout / float_remove / petty_cash  - 200.00
                                     ----------
expected_cash                        2,850.00
declared_closing_cash                2,850.00
variance                                 0.00
```

The payment window is `Payment.created_at` between `start_time` and
`end_time`, so the payment's timestamp has to sit inside the shift — not
merely its `payment_date`. That is the detail most likely to be got wrong,
and if it is, `Q21` will report a divergence between stored and recomputed
`expected_cash` rather than agreeing.

---

## Predicted `coverage_expectation`

### `surfaces_added` — none

No golden-master resolver is pinned to a shift. `auth.shifts` is a
non-parameterised surface and is already captured on production (as one of
the seven that return HTTP 500), so it is present on both sides.

### `surfaces_lost` — 1

```
reports.night_audit_snapshot__night_audit_log
```

No night audit, as in all four predecessors.

### `invariants_activated` — none

Nothing in D4 references `shifts` or `shift_adjustments`. Predicted empty.

### `invariants_deactivated` — **8**, not the 7 of the last three

```
INV-A03    no extra_charges at all, so nothing to group
INV-B01, INV-B02, INV-B03, INV-B05    no night audit
INV-C01, INV-C05                       cash only
INV-D07                                no overpayment log
```

**`INV-A03` is the differentiator.** `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN`
and `DS-ACT-GROUP` all carry an extra charge, so `INV-A03` kept a
population and merely changed. This narrative has none — the guest pays
for a room and nothing else — so it should deactivate, matching
`DS-ACT-INHOUSE`'s eight rather than the recent seven.

Copying the previous dataset's declaration would get this wrong. It is the
sharpest test in the prediction.

### `quantities_activated` — 1

```
Q21    VACUOUS -> the whole point of the dataset
```

### `quantities_deactivated` — 1

```
Q15    no night audit to recompute
```

---

## Predicted parity verdicts, and where this is weakest

Expected AGREED, from the pattern every previous dataset has shown — a
small clean narrative cannot reproduce production's divergences because it
lacks the populations that cause them:

```
Q12, Q13, Q14, Q17, Q22
```

`Q09`, `Q02` and `Q07` should **not** move: they diverge only where a
correction or reversal exists, and there is neither here.

**`Q21` itself is predicted AGREED** — stored `expected_cash` equal to the
recomputation, no divergence.

**The weak points, stated in advance:**

1. **`Q18` and `Q20`.** `DS-ACT-INHOUSE` moved both; `DS-ACT-CORRECTION`
   and `DS-ACT-VOIDCN` moved neither. The difference appears to be
   occupancy — two rooms against one — and this dataset has one. Predicted
   **not** to move, on that reading, but the reading may be wrong.
2. **`Q17`.** `DS-ACT-GROUP` moved it and the prediction there did not
   expect it. One room may or may not reproduce that. Predicted to move to
   AGREED, as on the single-room datasets.
3. **The shift window.** If the payment's `created_at` falls outside
   `start_time`–`end_time`, `Q21` reports DIVERGED rather than AGREED and
   the dataset is wrong rather than the system.

Recorded now so that whichever way these go, they are not read as
hindsight.
