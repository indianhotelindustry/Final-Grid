# `DS-ACT-VOIDCN@1.0`

The third regression dataset. 2026-08-08.

**COMMISSIONED**, six of six. **`INV-D05` activated** — the second VACUOUS
invariant closed — and **`Q11` lifted from VACUOUS to DIVERGED**, which
immediately produced a finding.

Coverage ledger: **`AS_DECLARED`**, after the ledger caught a movement the
prediction missed.

No application code modified. Production byte-identical.

---

## 1. Why this was taken ahead of `DS-ACT-GROUP`

The standing plan made `DS-ACT-GROUP` next once `INV-D02` was activated.
The owner's stated principle — *activate the highest-risk verification
before extending ordinary business coverage* — says otherwise, and it was
given as governing rather than as a one-off.

| Candidate | Activates | Also | Obstacle |
|---|---|---|---|
| **`DS-ACT-VOIDCN`** | **`INV-D05`** — VACUOUS, certification-blocking | **`Q11`** — VACUOUS, D1, severity BLOCK | none |
| `DS-ACT-CORPCREDIT` | `INV-C06` — VACUOUS, certification-blocking | 2 D2 surfaces | **structural, below** |
| `DS-ACT-GROUP` | **nothing** | 1 D2 surface | none |

Nothing in D1, D4 or D5 references `group_blocks`, so `DS-ACT-GROUP`
activates no invariant, fault or quantity. Under the principle it is the
lowest-priority remaining item.

### `DS-ACT-CORPCREDIT` is structurally blocked, and was not started

`companies` is a **PRESERVED master table**, and `builder.content_hash`
covers only the transactional and guest tables. Measured:

```
companies        PRESERVED      content_hash covers it: False
credit_notes     transactional  content_hash covers it: True
void_requests    transactional  content_hash covers it: True
group_blocks     transactional  content_hash covers it: True
```

A dataset declaring a company would carry master data **not part of its own
identity** — `strip()` never clears it, and the hash a certificate is issued
against would not cover it. The exclusion is deliberate and well argued, but
it was reasoned about master data *inherited from production*, not master
data a dataset *declares*. That needs deciding before `DS-ACT-CORPCREDIT`
can be written. **Recorded, not resolved.**

Evidence for all of the above, written before any of this dataset existed:
`evidence/20260808_ds_act_voidcn_prediction/prediction.md`.

---

## 2. The dataset

| | |
|---|---|
| Key | `DS-ACT-VOIDCN@1.0` |
| Purpose | `ACTIVATE_INVARIANT` |
| Business date | 2026-08-03 |
| Rows | 15, across 10 tables |
| Content hash | `20d069cfa2bb…` |
| Expectations | 46 — 34 financial, 12 invariant |
| Activates | **`INV-D05`** (0 → 2) and **`INV-D02`** (0 → 1) |

A duplicate payment voided with a void request recording who asked and why;
a disputed minibar charge credited by credit note and refunded.

```
raised     1,286.00   room 1,000 + minibar 200 + tax 86
collected  1,050.00   1,286 settled, duplicate voided, 236 refunded
OUTSTANDING  236.00
```

### Commissioning

```
BUILD           15 rows into 10 tables, content hash 20d069cfa2bb
POSITIVE        all 46 declared expectation(s) met
PERTURBATION    1 row(s) changed by 1 statement(s)
DISCRIMINATION  all 1 declared target(s) broke
ACTIVATION      2 claim(s) verified
ISOLATION       production byte-identical across both builds
```

The perturbation points the void request at a payment that does not exist.
Every amount, count and balance is untouched, and the cancellation record
stops naming anything real — which is exactly what `INV-D05` forbids.

---

## 3. Two production findings

### 3.1 Every cancellation refund violates `INV-D02`

`services.post_cancellation_disposition` builds the refund row with
`is_reversal=True` and **never sets `corrects_id`**. The only four
assignments of `corrects_id` in `services.py` are inside
`post_payment_correction` and `post_extra_charge_correction`.

`INV-D02` — CRITICAL, RELEASE_BLOCKING — requires every row flagged
`is_correction` **or** `is_reversal` to carry a resolving `corrects_id`.
**So every refund the application issues violates it.**

Found by reading the refund path *before* writing the dataset, then
confirmed by building it. The refund is modelled field for field as the
application builds it and `INV-D02` is declared **VIOLATED**. Giving it a
`corrects_id` would produce a green dataset describing an application that
does not exist.

Never seen because production has issued no refund — the same fact that
kept `INV-D02` VACUOUS until `DS-ACT-CORRECTION`.

### 3.2 The night audit reports voided payments as refunds

`Q11` went from VACUOUS to **DIVERGED** on its first exposure to real data:

```
payment_purpose = refund (true refunds)            236.00
voided payments (what night audit calls refunds) 1,286.00
```

A voided payment never left the bank; a refund did. Conflating them
overstates refunds by the value of every void — here more than fivefold.
`Q11` is `Severity.BLOCK` in the D1 registry and exists to detect exactly
this. It had never fired, because production has neither voids nor refunds.

**Both reported, neither repaired.** No application code was touched.
Evidence: `evidence/20260808_ds_act_voidcn_q11/`.

---

## 4. A gap, recorded rather than fixed

**No probe nets credit notes against the balance.** `outstanding` reports
236.00, which is what it measures: charges raised less collections. The
minibar *was* raised, and a credit note writes it off rather than removing
it. The true receivable is `outstanding − credit_note_total` = **0.00**, and
nothing computes that.

Recorded as a candidate **R-8** rather than fixed. Unlike R-7 this is a
*missing* quantity rather than a *wrong* one, so it bakes no error into the
baseline — `outstanding` means what it says. Both figures are declared, so
the relationship is measurable today.

---

## 5. Coverage ledger

Declared before the dataset was built. **`AS_DECLARED`** — after a
correction.

| | |
|---|---|
| **Added** | `INV-D05` (0 → 2) and `INV-D02` (0 → 1). No D2 surface |
| **Lost** | `reports.night_audit_snapshot__night_audit_log`, plus 7 invariants falling to zero population |
| **Changed** | 13 invariants, 3 with a status move, all declared |
| **Expected vs Unexpected** | `AS_DECLARED` |

### The ledger caught what the prediction missed — again

The first run reported `UNDECLARED_MOVEMENT`: **`INV-D02` was activated and
had not been declared as such.**

The reasoning had got the hard part right — it predicted from source that
the refund would violate `INV-D02`, and declared it VIOLATED — and then
failed to notice that *giving an invariant a population is an activation*.
Every one of the 46 expectations passed. Only the ledger saw it.

That is the second time the ledger has found coverage movement that careful
reading did not, and the first time it has done so on a dataset whose
expectations were all green. Corrected in both
`activates_invariants` and `coverage_expectation`, and recorded rather than
quietly added.

### What the ledger still cannot see

`Q11` is half this dataset's justification and **`coverage.py` does not
measure D1**. Predicted in advance and measured by hand instead — the same
way `DS-ACT-INHOUSE`'s D2 claim had to be. Two of the three datasets now
carry a headline claim the ledger cannot check. That is an argument for
extending it to D1 and D2, not for trusting it further than it goes.

---

## 6. Framework neutrality

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `ds-commission` | PASS — 3 datasets, 6/6 each, 0 unbacked claims |
| `ds-run` | PASS — 44 / 46 / 46 met, 0 unmet |
| `ds-coverage` | `AS_DECLARED`, exit 0 |
| `ds-registry` | 2 of 25 invariants now have an activating dataset |
| `inv-run` (D4) | registered 25, HOLDS 15, VIOLATED 6, VACUOUS 4, violations 57 — **unchanged**; the dataset does not touch production |

**`INV-D05` remains VACUOUS on production**, correctly: production holds no
void and no credit note. What changed is that a commissioned dataset now
exercises it.

---

## 7. Where this leaves Wave 0

**Two of the four VACUOUS invariants are now closed by commissioned
datasets.** The two that remain:

- **`INV-A06`** — blocked on R-5, a governance decision awaiting approval.
- **`INV-C06`** — blocked on the `companies` / `content_hash` question in
  §1, which needs deciding before `DS-ACT-CORPCREDIT` can be written.

**Every remaining activation is blocked on a decision, not on engineering.**

`DS-ACT-GROUP` is unblocked and activates nothing; it closes `groups.detail`,
the last UNRESOLVED D2 surface with no other owner. It is the sensible next
piece of work only because everything with higher verification value is
waiting on someone.

No certification claim follows from any of this. D7 does not exist, and
`inv-run` still reports FAIL with two release-blocking violations.
