# `DS-ACT-CORRECTION@1.0`

The second regression dataset, and **the first that activates anything**.
2026-08-08.

**COMMISSIONED**, six of six elements including ACTIVATION.
**`INV-D02` is no longer VACUOUS** — the only VACUOUS invariant that was
RELEASE_BLOCKING, now exercised by a standing population of 4.

Coverage ledger verdict: **`AS_DECLARED`**, against expectations declared
before the dataset was built.

No application code was modified. Production is byte-identical, verified
per build by the ISOLATION element.

---

## 1. The dataset

| | |
|---|---|
| Key | `DS-ACT-CORRECTION@1.0` |
| Purpose | `ACTIVATE_INVARIANT` |
| Origin | `SYNTHETIC` — production holds no correction of any kind |
| Business date | 2026-07-11 |
| Rows | 15, across 8 tables |
| Content hash | `aa36f32d073b…` |
| Expectations | 46 — 34 financial, 12 invariant |
| Activates | **`INV-D02`**, population 0 → 4 |

One stay. A ₹500 laundry charge raised in error, reversed and replaced with
₹200. A ₹1,000 payment taken short, reversed and replaced with ₹1,286.
Both follow the application's documented pattern exactly — the original row
is never edited:

```
REVERSAL     is_correction=1, is_reversal=1, amount = THE ORIGINAL
REPLACEMENT  is_correction=1, is_reversal=0, amount = the corrected
```

```
room, 1 night x 1,000.00                        room revenue  1,000.00
GST 5% on the room                              tax              50.00
laundry raised / reversed / corrected           charges net     200.00
GST 18% on the net laundry                      tax              36.00
                                                ------------------------
                                                owed          1,286.00
payment 1,000 / reversed / re-posted 1,286      collected     1,286.00
                                                OUTSTANDING       0.00
```

---

## 2. Commissioning

```
BUILD           15 rows into 8 tables, content hash aa36f32d073b
POSITIVE        all 46 declared expectation(s) met
PERTURBATION    1 row(s) changed by 1 statement(s)
DISCRIMINATION  all 1 declared target(s) broke
ACTIVATION      1 claim(s) verified
ISOLATION       production byte-identical across both builds

OVERALL VERDICT: PASS, exit 0
```

**The perturbation breaks the link, not the money.** Nulling `corrects_id`
on the payment reversal leaves every amount, count and balance identical
and turns a traceable correction into precisely what `INV-D02` forbids: a
negative-signed entry with no original. A perturbation that moved money
would have broken the financial probes and proved nothing about whether
the traceability rule can fail.

---

## 3. R-7 had to land first

`financials.py` summed `amount` unsigned. A reversal carries the **original
amount, positive** — `CHECK amount > 0` forbids anything else — and the
application requires every caller to subtract it. So the probes added
reversed money instead of removing it, wrong by twice the reversed amount.

On this dataset the pre-R-7 probes read `outstanding = −3,072.00` against
a truth of `0.00`.

It was invisible on production for exactly the reason this dataset exists:
production has no correction rows, which is the same sentence as "`INV-D02`
is VACUOUS". Same shape as R-2, harmless only while zero night rates were
posted. Fixed and commissioned separately — `evidence/20260808_r7_correction_signing/`,
19 checks — before this dataset declared a single figure.

---

## 4. The production defect this dataset found

**`gst_service.compute_stay_gst` taxes reversed money.**

The GST behind `calculate_stay_amount` — and therefore behind checkout,
the invoice and every downstream report — loops over a reservation's extra
charges and reads `ec.amount` **unsigned** (`gst_service.py:492`). It never
calls `signed_extra_charge_amount`, the function the codebase provides for
exactly this.

```
laundry raised    500.00 x 18%  =  90.00
laundry reversed  500.00 x 18%  =  90.00    <- should be -90.00
laundry corrected 200.00 x 18%  =  36.00
                                  216.00    against a truth of 36.00
room            1,000.00 x  5%  =  50.00
                                  ------
compute_stay_gst reports          266.00    against a truth of 86.00
```

**₹180.00 of GST charged on money the hotel took back**, compounding with
every further correction of the same charge.

### It is declared, not dodged

`INV-C02` is declared **VIOLATED**, by exactly ₹180.00. The guest paid
₹1,286.00 against charges of ₹1,286.00 and owes nothing;
`calculate_stay_amount` believes she still owes ₹180.00.

Making it hold would have meant either charging the guest tax on reversed
money, or dropping tax from the narrative — both of which hide a live
production defect behind a green dataset.

**Per the standing Wave 0 instruction this is reported and NOT repaired.**
No application code was touched. When it is fixed, this expectation must be
re-declared with evidence — that is the dataset doing its job, not the
dataset breaking.

It is a new instance of a class already on the register (multiple
independent definitions of a financial quantity: `tax_lines` says one
thing, `compute_stay_gst` computes another) and **the first instance
anybody has been able to point at**, because production has never held a
correction.

### A schema gap alongside it

`tax_lines` has no `is_reversal` and no `corrects_id`. The correction
pattern that exists for money has **no counterpart for tax**, so a reversed
taxed charge has no declared way to unwind its tax line. The dataset
declares tax on the net supply — the room and the corrected ₹200 — because
that is what was actually supplied. Inventing a reversal convention here
would have meant testing the invention.

---

## 5. Coverage ledger

Declared **before** the dataset was authored, in
`evidence/20260808_ds_act_correction_prediction/prediction.md`, so that any
discrepancy would be a finding rather than a transcription.

| | |
|---|---|
| **Coverage Added** | `INV-D02` — population 0 → 4. No D2 surface |
| **Coverage Lost** | `reports.night_audit_snapshot__night_audit_log`, plus 7 invariants falling to zero population |
| **Coverage Changed** | 13 invariants, 4 with a status move |
| **Expected vs Unexpected** | **`AS_DECLARED`** — every movement declared, every declared movement happened |

Lost invariants: `INV-B01`, `B02`, `B03`, `B05` (no night audit),
`INV-C01`, `C05` (cash only), `INV-D07` (no overpayment log).

Status moves, all four already declared in `expectations.invariants`:

```
INV-A02   VIOLATED over 40 -> HOLDS over 6     production's NULL folio defect
INV-A03   VIOLATED over  5 -> HOLDS over 3     follows from INV-A02
INV-C04   VIOLATED over 30 -> HOLDS over 1     production's double-booked room
INV-C02   HOLDS    over 28 -> VIOLATED over 1  the GST defect above
```

### The prediction was right where it was hardest, and wrong where it was easiest

**Right:** seven deactivations, **not the eight `DS-ACT-INHOUSE` lost.**
The difference is `INV-A03` — that dataset has no `extra_charges` at all,
so `INV-A03` fell to zero there; this one has three on one folio, so it
keeps a population and merely changes. That was the one entry that could
not be got right by copying the previous ledger, and it was predicted from
the narrative before anything was built.

**Wrong:** the prediction named `INV-A01` as the risk — the settlement
identity, whose treatment of a reversed payment could not be derived from
the narrative. `INV-A01` held. The failure came on `INV-C02` instead, and
was not predicted at all.

Recorded rather than quietly corrected. The prediction identified the right
*kind* of risk — an engine that might not sign reversals the way the probes
now do — and put it on the wrong invariant. The engine signs payments and
charges correctly; it is the GST layer that does not.

---

## 6. Framework neutrality

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `ds-commission` | PASS, 2 datasets, 6/6 elements each, 0 unbacked claims |
| `ds-run` | PASS — `DS-ACT-INHOUSE` 44 met, `DS-ACT-CORRECTION` 46 met, 0 unmet |
| `ds-coverage` | `AS_DECLARED`, exit 0 |
| `ds-registry` | `INV-D02` activated by `DS-ACT-CORRECTION@1.0`; 24 of 25 still unactivated |
| `inv-run` (D4) | registered 25, HOLDS 15, VIOLATED 6, VACUOUS 4, violations 57, uncommissioned 0 — **unchanged**; the dataset does not touch production |
| `compare --tag v2.2.18_preWave1` (D1) | 41 changes, `IMPL_ADDED` 38 / `VERDICT_CHANGED` 3, `Q16`–`Q18` — unchanged |

**`INV-D02` remains VACUOUS on production**, and that is correct: production
still holds no correction. What changed is that a commissioned dataset now
exercises it, so the rule is no longer proven only by fault injection.

---

## 7. What this does not do

- It does **not** resolve any D2 surface. `surfaces_added` is empty and the
  declaration says so — this is an activation dataset, not a coverage one.
- It does **not** fix the GST defect. Reported, not repaired.
- It does **not** model the closed-audit trigger. The pattern exists
  because a closed night audit must not be mutated; this dataset declares
  no night audit, so it exercises the correction shape without the
  condition that provokes it. Adding one would drag in `INV-B02`'s snapshot
  hash and `INV-B03`'s recomputation.
- No certification claim follows. D7 does not exist, and `inv-run` still
  reports FAIL with two release-blocking violations on production.

### Next

`DS-ACT-GROUP`, per the standing sequence. `DS-ACT-OVERPAY` remains blocked
on R-5, which is a governance decision and not to be implemented until
explicitly approved.

**Three VACUOUS invariants remain**: `INV-A06` (blocked on R-5),
`INV-C06` (`DS-ACT-CORPCREDIT`), `INV-D05` (`DS-ACT-VOIDCN`). All three are
certification-blocking rather than release-blocking, so the highest-risk
one is now closed.
