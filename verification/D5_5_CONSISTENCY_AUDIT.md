# D5.5 — Verification Consistency Audit

> **Two corrections, 2026-08-08**, from applying the remediation. The
> residue table below names **nine** reservations, not the seven BS-4
> states, and then adds "21 others" — 9 + 21 = 30 against a population of
> 28; the enumeration is right and the count is wrong. BS-4's second
> claim, that `invoice_round_off_amount` is the *sole* cause of the
> residue, is also wrong: four of the nine have zero round-off and a
> different mechanism behind them. **The final authoritative table is
> unaffected and every figure in it is confirmed.** See
> `D5_5_REMEDIATION_APPLIED.md` §2 and §5.

Investigation. 2026-08-07. **No production financial logic, schema object
or configuration value was modified.** Every figure below was read through
a `mode=ro` connection to `instance/pms.db`; the file's SHA-256 is
unchanged.

Two inconsistencies surfaced during the D6 design were investigated to
conclusion. Remediation is proposed separately in
`D5_5_REMEDIATION.md` and **nothing has been fixed**.

**Both conclusions are the same in kind: the production accounting is
sound, and the measuring instrument was wrong.**

---

## Question 1 — `overpayment_logs` holds live rows while `INV-A06` reports `VACUOUS`

### Verdict: **population-definition issue with a materiality threshold. Not an invariant defect, not an intentional exclusion.**

### Evidence

`INV-A06` (`invariants/rules_a.py:638-673`) iterates reservations and
builds its population from the *canonical engine*, not from the log table:

```python
balance = dec(calculate_stay_amount(r)['settlement_balance'])
if balance >= Decimal('-1.00'):
    continue                      # not overpaid — excluded
overpaid += 1
if r.id not in logged:            # logged = DISTINCT reservation_id
    violations.append(...)        #          FROM overpayment_logs
```

Its population is **"reservations currently overpaid by more than ₹1"**.
The log table is the *right-hand side* of the check, never the population.

Live run, `python -m verification inv-run --id INV-A06 --tag production`:

```
INV-A06   VACUOUS   POP 0   VIOL 0   136ms   171 reads   0 writes
          "overpaid reservations: no rows in scope"
OVERALL VERDICT: INCOMPLETE   (exit 2)
```

The two log rows:

| log | reservation | `overpaid_amount` | reason | resolution | created |
|---|---|---|---|---|---|
| 1 | 10 | **0.15** | intentional | income | 2026-05-28 |
| 2 | 17 | **0.15** | intentional | income | 2026-05-29 |

Both are **₹0.15** — an order of magnitude below the ₹1.00 materiality
threshold. Neither could ever enter `INV-A06`'s population, whatever the
invariant did.

Traced to source, the accounting is coherent:

```
reservation 10:  room 1,619.19 + other_income 0.15   = taxable 1,619.34
                 GST 5% (CGST 40.48 + SGST 40.48)    =          80.96
                 unrounded grand total                =       1,700.30
                 invoice_round_off_amount             =          -0.30
                 invoice_rounded_grand_total          =       1,700.00
                 guest paid                           =       1,700.15
                 overpaid against the rounded invoice =           0.15  ✓ logged
```

The ₹0.15 overpayment is real, was detected, was logged, and was resolved
by posting ₹0.15 of `other_income`. **The system behaved correctly.**
Reservation 17 is identical.

### Two verification blind spots this exposes

Neither is a defect in `INV-A06` as written. Both are gaps in what the
registry as a whole covers.

**BS-1 — `INV-A06` is one-directional.** It asks "is every overpaid
reservation logged?" Nothing anywhere asks the converse: "does every
`overpayment_logs` row correspond to a real overpayment?" A stale, orphan
or fabricated log row is invisible to every layer. This is a referential
obligation with no Class D invariant behind it.

**BS-2 — sub-₹1 overpayments are entirely unmeasured.** The ₹1.00
threshold is defensible for materiality, but it means the only two
overpayments this hotel has ever recorded sit in an unmeasured band. A
systematic ₹0.15 leak across ten thousand stays is ₹1,500 that no control
would ever report.

---

## Question 2 — production `outstanding` of −₹1,697.32

### Verdict: **verification blind spot in the D6 probe. Not a production accounting defect.**

### Evidence

`datasets/financials.py:125-131` defines `outstanding` as:

```
room revenue (reservation_night_rates.final_rate)
  + extra charges (extra_charges.amount)
  − payments (non-voided)
```

**It omits tax entirely.** Guests pay tax-inclusive totals, so the probe
subtracts money that was collected against a charge it never counted.

Aggregate reconciliation:

| Component | Amount |
|---|---|
| Room revenue (night rates) | 37,217.12 |
| Extra charges | 729.85 |
| **Charges excluding tax** | **37,946.97** |
| Tax (`tax_lines.tax_amount`) | 1,897.24 |
| **Charges including tax** | **39,844.21** |
| Payments, net of voids | 39,644.29 |
| **Probe `outstanding` (excl tax)** | **−1,697.32** |
| **Correct outstanding (incl tax)** | **+199.92** |

−1,697.32 + 1,897.24 = +199.92. The discrepancy is the tax, to the rupee.

The per-reservation trace confirms it is systematic, not concentrated:
**every one of the 28 reservations** shows a negative excl-tax balance
equal to its own tax. Including tax, **21 of 28 are exactly 0.00**.

### The real position: +₹199.92, and it is one reservation

| reservation | room | extras | tax | paid | balance incl tax |
|---|---|---|---|---|---|
| **1** | 1,904.76 | 190.48 | 104.76 | 2,000.00 | **+200.00** |
| 7 | 1,367.14 | 0.00 | 68.36 | 1,436.00 | −0.50 |
| 10, 17 | 1,619.19 | 0.15 | 80.96 | 1,700.15 | +0.15 each |
| 28 | 1,457.27 | 291.45 | 87.44 | 1,836.00 | +0.16 |
| 6, 9, 23, 27 | — | — | — | — | −0.01 each |
| 21 others | — | — | — | — | **0.00** |
| | | | | **TOTAL** | **+199.92** |

The residue of ±0.01–0.16 is **invoice rounding**, which neither probe
models: reservation 10 carries `invoice_round_off_amount = −0.30`.

### Two further probe defects found

**BS-3 — `taxable_total` double counts.** It reports 75,893.34 against
charges excluding tax of 37,946.97 — almost exactly 2×. Indian GST splits
into CGST and SGST, and `tax_lines` carries **one row per component, each
repeating the full taxable base**:

```
src=room_night/night_2026-05-27  taxable=1619.19  CGST @2.5 = 40.48
src=room_night/night_2026-05-27  taxable=1619.19  SGST @2.5 = 40.48
```

Summing `taxable_amount` therefore counts every base twice. Summing
`tax_amount` is correct (each row carries its own half): 1,897.24 against
an expected 5% of 37,946.97 = 1,897.35, the ₹0.11 being rounding.

**BS-4 — no probe models `invoice_round_off_amount`.** It is the sole
cause of the ±0.01–0.16 residue on seven reservations.

---

## Incidental findings — live instances of known defects

Not sought; surfaced by the trace. All three are already on the register
as *classes* of defect. These are the first identified *instances*.

### F-1 — Walk-in reservations settled through OTA receivable heads

| reservation | `source` | payment mode | category | amount |
|---|---|---|---|---|
| 10 | **Walk-in** | MMT Paid | `ota_receivable` | 1,700.15 |
| 17 | **Walk-in** | Goibibo Paid | `ota_receivable` | 1,700.15 |

**₹3,400.30 recognised against a counterparty that does not exist.** This
is precisely what `INV-C01` and `FLT-A01` describe. Aggregate exposure:
₹7,977.92 sits in `ota_receivable` across 5 payments.

### F-2 — A checked-out guest owing ₹200.00

Reservation 1: status `CheckedOut`, grand total ₹2,200.00, paid
₹2,000.00. This is the population D5 recorded that D3's `RC07` **does not
move for** (`FLT-A09`, HIGH). A live instance now exists to test that gap
against.

### F-3 — The dormant `room_rent` divergence is confirmed still dormant

`0 of 30` `reservation_night_rates` rows have `is_posted = 1`. No room
revenue has been posted into `extra_charges`. If posting runs, the
`outstanding` probe — which sums both `reservation_night_rates` **and**
`extra_charges` — would double count room revenue by approximately
**₹37,217**. The probe is one night audit away from being catastrophically
wrong, in the same direction as the defect already on the register.

---

## Conclusion

Neither inconsistency is a production accounting defect.

The hotel's books reconcile: charges including tax of ₹39,844.21 against
collections of ₹39,644.29, leaving ₹199.92 receivable, of which ₹200.00 is
one identified unpaid checkout and the remainder is invoice rounding. The
overpayment control worked — it detected ₹0.15, logged it, and resolved
it.

What failed was measurement. Four blind spots (BS-1 to BS-4) were found in
the verification layer, three of them in `datasets/financials.py` — a D6
module that has never run against a declared dataset. Had D6 proceeded
without this audit, its regression expectations would have been declared
against a probe that omits tax, a probe that double counts, and a
population definition nobody had reconciled.

**This is the authoritative financial truth D6 may declare expectations
against:**

| Statement | Value |
|---|---|
| Charges excluding tax | ₹37,946.97 |
| Tax | ₹1,897.24 |
| Charges including tax | ₹39,844.21 |
| Collections, net of voids | ₹39,644.29 |
| **Outstanding** | **₹199.92** |
| Overpaid reservations (> ₹1) | **0** |
| Overpayment log rows | 2, both ₹0.15, both resolved |
| Misattributed to OTA receivable | ₹7,977.92 across 5 payments |
| Room revenue posted to charges | **0 of 30 nights** |
