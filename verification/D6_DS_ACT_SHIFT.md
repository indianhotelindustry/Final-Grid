# `DS-ACT-SHIFT@1.0`

The fifth regression dataset. 2026-08-08.

**COMMISSIONED**, six of six. **`Q21` activated** — the last VACUOUS parity
quantity any planned dataset could reach. Coverage ledger **`AS_DECLARED`**.

No application code modified. Production byte-identical.

---

## 1. The dataset

| | |
|---|---|
| Key | `DS-ACT-SHIFT@1.0` |
| Purpose | `ACTIVATE_INVARIANT` |
| Business date | 2026-10-05 |
| Rows | 10, across 9 tables |
| Content hash | `fd9373398747…` |
| Expectations | 57 — 34 financial, 11 invariant, 9 parity, 3 golden |
| Activates | **`Q21`**, VACUOUS → AGREED |

One front-desk shift, opened with a ₹2,000 float, one cash settlement of
₹1,050 inside the window, ₹200 of petty cash out, drawer counted and
balanced.

```
opening float                          2,000.00
+ cash received in the window          1,050.00
- payout / float_remove / petty_cash    - 200.00
                                       ----------
expected_cash                          2,850.00
declared_closing_cash                  2,850.00
variance                                   0.00
```

### The window was the part that mattered

`shift_service.calculate_expected_cash` selects cash payments by
`Payment.created_at` between `start_time` and `end_time` — **the timestamp,
not `payment_date`**. A payment dated to the right day but stamped outside
the window contributes nothing, and `Q21` would then report the stored
`expected_cash` diverging from the recomputation: the dataset wrong and the
system right, which is the least useful kind of red.

Predicted in advance as the most likely thing to get wrong, and it was got
right — the dataset passed on its first build.

### Commissioning

```
BUILD           10 rows into 9 tables, content hash fd9373398747
POSITIVE        all 57 declared expectation(s) met
PERTURBATION    1 row(s) changed by 1 statement(s)
DISCRIMINATION  all 1 declared target(s) broke
ACTIVATION      0 claim(s) verified
ISOLATION       production byte-identical across both builds
```

The perturbation changes the petty-cash amount without touching the stored
`expected_cash`. Every financial probe, the declared closing figure and the
variance are unchanged; only the recomputation moves. **That is the failure
`Q21` exists to catch** — a till that balances on paper because the
expected figure was written down once and never recomputed.

`ACTIVATION` reports 0 claims because that element checks the D4 registry
only, and `Q21` is a D1 quantity. The activation is verified by the
coverage ledger instead — which it could not have been before D1 was added
to the ledger earlier the same day.

---

## 2. What the ledger caught, and what it settled

Declared before building:
`evidence/20260808_ds_act_shift_prediction/prediction.md`.

**Right:** no surface added; `Q21` activated; `Q15` lost; no invariant
activated; and — the sharpest test — **eight invariants deactivated, not
the seven of the last three datasets.** `INV-A03` is the differentiator:
those three carry an extra charge and this narrative has none, so it loses
its population here. Copying the previous declaration would have got that
wrong.

**Wrong: `Q18` and `Q20`.** The prediction named these two as its weak
points and got them wrong. It reasoned they track *occupancy* —
`DS-ACT-INHOUSE` has two rooms and moved them, the single-room datasets did
not.

**Five datasets now falsify that, and identify the real cause:**

| dataset | rooms | extra charges | `Q18`/`Q20` → AGREED |
|---|---|---|---|
| `DS-ACT-INHOUSE` | 2 | no | **yes** |
| `DS-ACT-SHIFT` | 1 | no | **yes** |
| `DS-ACT-CORRECTION` | 1 | yes | no |
| `DS-ACT-VOIDCN` | 1 | yes | no |
| `DS-ACT-GROUP` | 2 | yes | no |

Occupancy does not predict it — two-room datasets appear on both sides.
**Extra charges predict it exactly.**

So the executive dashboard tiles and the ADR/RevPAR definitions **agree on
a room-only hotel and disagree the moment an extra charge exists**. That
narrows a long-standing production DIVERGED to its cause, and it is a
finding the coverage ledger produced rather than anybody's reading of the
code. It is the third time the ledger has found something no one had.

---

## 3. Framework neutrality

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `ds-commission` | PASS — 5 datasets, 6/6 each, 0 unbacked claims |
| `ds-coverage` | `AS_DECLARED`, exit 0 |
| `ds-registry` | 5 registered, **0 without a passing ledger** |
| production | DB and all 68 `app/*.py` byte-identical |

---

## 4. Where Wave 0 stands

**Every unblocked regression dataset is now written.** Five datasets, all
commissioned, all with a passing coverage ledger.

Of the empty populations D6 was built to close:

| | State |
|---|---|
| `INV-D02` corrections | **closed** — `DS-ACT-CORRECTION` |
| `INV-D05` voids / credit notes | **closed** — `DS-ACT-VOIDCN` |
| `Q11` refunds vs voids | **closed** — `DS-ACT-VOIDCN` |
| `Q21` shift cash | **closed** — this dataset |
| 3 in-house D2 surfaces | **closed** — `DS-ACT-INHOUSE` |
| `groups.detail` | **closed** — `DS-ACT-GROUP` |
| `INV-A06` overpayment | **blocked on R-5** — governance |
| `INV-C06` corporate credit | **blocked on the `companies` / `content_hash` question** |

**Nothing further can be closed without a decision.** Both remaining items
are blocked on someone, not on engineering.

No certification claim follows. D7 does not exist, and `inv-run` still
reports FAIL with two release-blocking violations on production.
