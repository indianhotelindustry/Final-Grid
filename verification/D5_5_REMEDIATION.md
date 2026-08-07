# D5.5 — Proposed Remediation

Companion to `D5_5_CONSISTENCY_AUDIT.md`. **Nothing here has been
applied.** Kept separate from the investigation so the findings stand on
their own evidence and are not read through the lens of a proposed fix.

Every item below is in the **verification layer**. No production financial
logic or schema change is proposed. Where a production defect was found,
it is listed in §4 for Wave 1 and explicitly not fixed.

---

## 1. Blocking — must land before D6 declares any expectation

These three are in `datasets/financials.py`, which no dataset has ever
run against. Declaring regression expectations on the current probes would
bake the errors into the baseline.

### R-1 — `outstanding` omits tax  *(cause of the −₹1,697.32)*

`financials.py:125-131`. Add the tax component:

```
  room revenue + extra charges + tax − payments(non-voided)
```

Expected effect: −1,697.32 → **+199.92**.

**Verify by:** re-running `financials.measure()` and confirming +199.92,
then confirming the per-reservation trace shows 21 of 28 at exactly 0.00.

### R-2 — `outstanding` will double count once room rent posts

Currently harmless only because `0 of 30` night-rate rows are posted. When
the night audit posts room rent into `extra_charges`, this probe sums it
from **both** sources and overstates charges by ~₹37,217.

Fix with the exclusion the application itself uses and that
`replay/ledger.py` already mirrors:

```sql
extra_charges WHERE charge_type IS NULL OR charge_type <> 'room_rent'
```

**This must ship with R-1, not after it.** The two are one change; fixing
the tax while leaving the double count converts a known-wrong probe into a
plausibly-wrong one, which is worse.

### R-3 — `taxable_total` double counts CGST/SGST

`tax_lines` holds one row per tax component, each repeating the full
taxable base. Either divide by the component count per source, or
aggregate `DISTINCT (charge_source_type, charge_source_id)`. Simply
deleting the probe is also defensible — nothing consumes it yet.

**Verify by:** `taxable_total` ≈ `room_revenue + extra_charges`
(37,946.97), not 75,893.34.

---

## 2. Recommended — coverage gaps with no control behind them

### R-4 — A Class D invariant for orphan overpayment records *(BS-1)*

`INV-A06` is one-directional: it catches an overpayment with no log, never
a log with no overpayment. Propose `INV-D07`:

> Every `overpayment_logs` row references a reservation that was
> genuinely overpaid at the time the row was created, or carries a
> `resolution` explaining why it no longer is.

This is a referential obligation (P14) and belongs with the other Class D
rules. It also gives `DS-ACT-OVERPAY` something to be *violated* against,
which the registry requires: a dataset must be able to break something.

**Negative seed:** insert an `overpayment_logs` row against a reservation
whose balance is zero.

### R-5 — Decide the sub-₹1 overpayment policy *(BS-2)*

The ₹1.00 threshold in `INV-A06` is a materiality judgement that is
currently implicit in code and stated nowhere. Both live overpayments sit
below it.

This is a **decision for the project owner, not an engineering fix.**
Either:

- **(a)** the threshold is correct — then record it in the invariant's
  declared business rule so it is a stated policy rather than a constant,
  and accept that sub-rupee overpayments are unmeasured; or
- **(b)** sub-rupee overpayments matter in aggregate — then a second
  invariant should total them across all reservations and report the
  aggregate, since no single one will ever breach ₹1.

### R-6 — Model `invoice_round_off_amount` *(BS-4)*

Sole cause of the ±0.01–0.16 residue on seven reservations. Until it is
modelled, no dataset can declare an exact per-reservation balance, and D6
expectations would need tolerances — which is how a control quietly stops
being able to fail.

---

## 3. Sequencing

```
R-1 + R-2  ──┐
R-3        ──┼──► re-measure ──► D6 step 1 (wiring, empty registry)
R-6        ──┘
R-4          ──► needed before DS-ACT-OVERPAY is declared
R-5          ──► owner decision; blocks nothing
```

R-1, R-2, R-3 and R-6 are small, isolated, and testable against figures
this audit has already established. R-4 is a full invariant declaration
with a commissioning obligation and should be treated as D4 work, not as
a footnote to D6.

---

## 4. Production defects found — NOT fixed, referred to Wave 1

Per the standing Wave 0 instruction, every layer reads and reports;
nothing repairs. These are instances, not new classes — each was already
on the register.

| Ref | Finding | Amount | Existing control |
|---|---|---|---|
| F-1 | Reservations 10 and 17 are `Walk-in` yet settled through `ota_receivable` modes (MMT Paid, Goibibo Paid) | ₹3,400.30 of ₹7,977.92 total OTA exposure | `INV-C01`, `FLT-A01` |
| F-2 | Reservation 1 checked out owing ₹200.00 | ₹200.00 | `FLT-A09` — and D3's `RC07` **does not detect it** |
| F-3 | `0 of 30` night-rate rows posted; the room-rent divergence remains dormant | ~₹37,217 latent | known dormant defect |

**F-2 deserves emphasis.** D5 recorded as a theoretical gap that `RC07`
does not move for a guest checked out with an unexplained balance. There
is now a live instance in production, reservation 1, that the control is
blind to. The gap is no longer hypothetical, and it should be prioritised
in Wave 1 above the probe fixes above.
