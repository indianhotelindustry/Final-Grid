# `DS-ACT-CORRECTION` — coverage prediction, made before implementation

Written **before** the dataset was authored, built or measured, so that any
discrepancy against `ds-coverage` is a finding rather than a transcription.
Reasoned from the narrative and from the production registries alone.

Narrative: one stay. A ₹500 laundry charge raised in error, reversed and
replaced with ₹200. A ₹1,000 payment taken in error, reversed and replaced
with ₹1,250. Both follow the application's documented post-audit
correction pattern. No night audit, no OTA payment, no overpayment, no
company, no group.

---

## Predicted `coverage_expectation`

### `surfaces_added` — **none**

This dataset adds no golden-master surface. Every parameterised resolver it
satisfies (`any_reservation`, `any_guest`, `any_room`, `any_payment`,
`checked_out_reservation`) already resolves on production. It has no
CheckedIn reservation, no company and no group block, so the six surfaces
production leaves UNRESOLVED stay UNRESOLVED.

**This is an invariant-activation dataset, not a D2-coverage one**, and the
prediction says so up front.

### `surfaces_lost` — 1

```
reports.night_audit_snapshot__night_audit_log
```

The narrative declares no night audit, so there is no `night_audit_logs`
row for the snapshot surface to pin to. Same loss as `DS-ACT-INHOUSE`, same
reason, and not worked around for the same reason: a hand-written snapshot
would have to satisfy `INV-B02`'s hash check and `INV-B03`'s recomputation
or be tuned until it passed.

### `invariants_activated` — 1, and it is the point

```
INV-D02    population 0 on production -> 4 here
```

`INV-D02` is the only VACUOUS invariant that is RELEASE_BLOCKING. Its
population is rows in `payments` or `extra_charges` flagged `is_correction`
or `is_reversal`. The narrative produces four: a reversal and a replacement
in each table.

No other VACUOUS invariant moves. `INV-A06` needs an overpayment beyond the
materiality threshold, `INV-C06` a corporate booking, `INV-D05` a void or
credit note. None is in this narrative.

### `invariants_deactivated` — 7

```
INV-B01    no night audit -> no closed date to protect
INV-B02    no night audit -> no snapshot to hash
INV-B03    no night audit -> no closed day to recompute
INV-B05    no night audit -> no audit sequence
INV-C01    the only payments are cash, so no OTA head is involved
INV-C05    same population as INV-C01
INV-D07    no overpayment_logs row
```

**Seven, not the eight `DS-ACT-INHOUSE` lost.** The difference is
`INV-A03` — charges grouped by folio against charges grouped by
reservation. `DS-ACT-INHOUSE` has no `extra_charges` at all, so `INV-A03`
fell to zero there. This dataset has three, all on one folio, so `INV-A03`
keeps a population and should merely *change* rather than deactivate.

That single difference is the sharpest test of the prediction: it is the
one place where reasoning from the narrative gives a different answer from
copying the previous dataset's ledger.

---

## Also predicted, and not part of the ledger

- `INV-D02` should report **HOLDS**, not merely non-VACUOUS. Every
  correction row carries a `corrects_id` that resolves within its own
  table.
- `INV-A03` should **HOLD**: all three charges sit on one folio and one
  reservation, so the two groupings cannot disagree.
- `outstanding` should be **0.00** — the guest is settled exactly once the
  reversals are signed, which is only true because R-7 landed first.

## The risk in this prediction

`INV-A01` is the settlement identity through `calculate_stay_amount`. It is
declared `HOLDS` in the dataset's expectations, but the engine's treatment
of a reversed-and-replaced payment is **not something this prediction can
derive from the narrative** — it depends on whether the canonical engine
signs reversals the way the probes now do. If it does not, `POSITIVE` will
fail and that is a finding about the engine under corrections, which is
precisely the population `INV-D02`'s VACUOUS message said was untested.

Stated in advance so that whichever way it goes, it is not read as
hindsight.
