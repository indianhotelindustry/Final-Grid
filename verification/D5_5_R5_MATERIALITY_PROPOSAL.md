# R-5 — the ₹1.00 overpayment materiality threshold

**Governance proposal. Nothing has been changed and nothing will be until
this is approved.** Awaiting the project owner's decision.

The question: **is ₹1.00 the right threshold below which an overpayment is
not worth measuring, and if so, should it be stated as policy rather than
left as a constant?**

---

## 1. What the threshold is

`INV-A06` takes a reservation into its population only when the canonical
`settlement_balance` is below `-1.00`. A guest in credit by ₹0.99 is not
overpaid as far as any control is concerned.

It is a **materiality judgement**, and it is currently implicit in code and
stated in no business rule, no policy document and no report. Nobody
approved it; it is simply what the constant says.

Since R-4 it is also declared in **two** places — `INV-A06` inline and
`MATERIALITY_THRESHOLD` in `rules_d.py`. Two independent definitions of one
policy value is what P1 forbids for financial quantities, and they will not
stay in step by themselves. Deliberately not collapsed: unifying them
before the policy is settled would bake today's answer into the structure.

---

## 2. The measured position

Read through the canonical engine on 2026-08-08, production untouched.
Evidence: `evidence/20260808_r5_balance_distribution/`.

| | Count | Total |
|---|---|---|
| Reservations | 28 | |
| Settled exactly | 24 | |
| Owing money | 2 | ₹200.01 |
| **In credit** | **2** | **₹0.30** |
| — overpaid by more than ₹1.00 (`INV-A06`'s population) | **0** | ₹0.00 |
| — overpaid by ₹0.01 to ₹1.00 (unmeasured band) | **2** | ₹0.30 |

Both are ₹0.15, on reservations 10 and 17, both from invoice rounding, both
logged and both resolved by posting ₹0.15 of `other_income`.

> **Every overpayment this hotel has ever recorded is below the
> threshold.** The measured coverage of `INV-A06` on real data is zero, and
> always has been.

---

## 3. What follows from leaving it as it is

**`INV-A06` is VACUOUS and stays VACUOUS.** It is commissioned — D5's
`FLT-A07` proves it fires when an overpayment is injected — but it has
never been exercised by anything the hotel actually did. A commissioned
rule over an empty population proves nothing about the data (P10).

**`DS-ACT-OVERPAY` would have to invent a shape the hotel has never
produced.** To lift `INV-A06` the dataset must contain an overpayment
larger than ₹1.00. That is legitimate synthetic data, but it means the
control's only population would be one the business does not generate — the
regression dataset would prove the rule works and prove nothing about
whether the hotel's real overpayments are handled.

**`INV-A06` and `INV-D07` disagree below the threshold.** Measured:

| Reservation overpaid by | `INV-A06` | `INV-D07` (log row unresolved) |
|---|---|---|
| ₹0.50 | not in population | **VIOLATED** |
| ₹2.00 | in population | HOLDS |

Below ₹1.00, `INV-D07` reads the reservation as *not overpaid* and reports
its overpayment record as baseless — when the overpayment is real, merely
immaterial. Production escapes this today only because both live rows carry
`resolution = 'income'`. **An unresolved ₹0.15 overpayment — the exact
shape this hotel has produced twice — would be reported as an orphan
liability.**

**A systematic leak would be invisible.** ₹0.15 across ten thousand stays
is ₹1,500 that no control would report, because no single instance ever
breaches ₹1.00.

**The threshold is one-sided.** There is no equivalent materiality on the
receivable side: reservation 11 is owed ₹0.01 and nothing objects. Whether
that asymmetry is intended is part of this decision.

---

## 4. Options

### (a) Keep ₹1.00 and declare it

State the threshold in `INV-A06`'s business rule so it is approved policy
rather than a constant, and accept in writing that sub-rupee overpayments
are unmeasured.

- Cheapest. No behavioural change.
- `INV-A06` stays VACUOUS on production indefinitely.
- `DS-ACT-OVERPAY` proceeds with a synthetic >₹1.00 overpayment.
- Does **not** resolve the `INV-D07` disagreement — a rule would still call
  a truthful sub-rupee record baseless.

### (b) Keep ₹1.00, and add an aggregate invariant

As (a), plus a new invariant totalling sub-rupee credit across all
reservations and reporting the aggregate against a stated limit.

- Closes the systematic-leak blind spot, which is the real exposure.
- No single instance is chased, so the operational burden stays nil.
- Full D4 work: a declaration, a seed and eight commissioning elements.
- Needs an approved aggregate limit — a second policy decision.

### (c) Lower the threshold to the rounding floor (₹0.01, or zero)

Treat any credit balance as an overpayment.

- **`INV-A06` becomes non-VACUOUS immediately, on real data** — population
  2, and both are already logged, so it should hold.
- Removes the `INV-D07` disagreement entirely: the two rules would agree
  about who is overpaid at every magnitude.
- `DS-ACT-OVERPAY` could be built from a realistic rounding overpayment
  rather than an invented large one.
- Every future sub-rupee rounding difference becomes a row somebody must
  resolve. On this data that is 2 in 28 stays; at scale it is an
  operational cost that has not been sized.
- Changes what `INV-A06` reports on production, so it needs a declared
  expected movement and evidence under the migration model
  (`ENGINEERING_GUIDE.md` §5).

---

## 5. Recommendation

**(c), with (a)'s discipline: lower the threshold to ₹0.01 and state it in
the business rule.**

The argument is coverage. Options (a) and (b) both leave `INV-A06` measuring
nothing on real data and leave the `INV-D07` contradiction standing. Option
(c) is the only one that makes the overpayment controls exercise the
overpayments this hotel actually produces, and it does so with data that
already exists and is already correctly handled — the hotel detected both
₹0.15 overpayments, logged them and resolved them. The system's behaviour
is right; only the measurement excludes it.

**The honest counter-argument**, which is the owner's to weigh: the ₹1.00
threshold may exist precisely so that front-desk staff are not asked to
resolve rounding paise. Option (c) makes every rounding difference a
tracked item. Nobody has sized that at this hotel's real occupancy, and
this proposal does not have the data to. If that cost is unacceptable,
**(b)** is the right answer — it catches the aggregate leak, which is the
material risk, without generating per-stay work.

**(a) is not recommended.** It is the current behaviour with a paragraph
attached, and it leaves a control that has never measured anything looking
approved.

---

## 6. What is blocked until this is decided

- **`DS-ACT-OVERPAY`.** The threshold determines what the dataset must
  contain to enter `INV-A06`'s population. Declaring it now would set
  regression expectations against an unsettled policy — the exact mistake
  the D5.5 probe remediation existed to prevent. D6 has been re-sequenced
  so `DS-ACT-GROUP` runs first; see `D6_SEQUENCING_DECISION.md`.
- **Collapsing the duplicate threshold constant.**
- Under (b) or (c): a declared expected movement, and re-commissioning of
  `INV-A06` and `INV-D07`.

Nothing else. `INV-D07` is commissioned and correct under the present
policy; it is the policy that is undecided, not the rule.

---

## 7. On approval

State the decision and the work follows the migration model: declare the
expected movement per invariant, capture a baseline, change, compare,
retain the evidence pack. Under (c) the declared movement is
`INV-A06 VACUOUS → HOLDS over 2` and `INV-D07` unchanged at `HOLDS over 2`.
