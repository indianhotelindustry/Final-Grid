# D6 — dataset sequencing: `DS-ACT-GROUP` before `DS-ACT-OVERPAY`

Decision recorded 2026-08-08. The instruction was to re-sequence **unless
repository evidence demonstrates that overpayment coverage is required
first**, so the evidence was gathered before the conclusion.

**Outcome: re-sequenced. The evidence does not demonstrate that
overpayment must come first, and on one point actively argues against it.**

---

## 1. The evidence, both ways

Read from the registries, not from the roadmap.

### Against group-first — the case for overpayment

| Evidence | Reading |
|---|---|
| `INV-A06` is VACUOUS and `CERTIFICATION_BLOCKING` | The strongest single argument. Closing VACUOUS populations is the stated reason D6 exists (`datasets/model.py`), and `INV-A06` is one of the four named targets |
| `INV-D07` is `CERTIFICATION_BLOCKING` and new | Its behaviour below the materiality threshold has never met a real overpayment population |
| `FLT-A07` "Guest overpaid with no overpayment record" | A declared D5 fault on this exact population |
| A group dataset lifts **0** invariants | `DS-ACT-GROUP` does not advance D6's headline metric at all |

### For group-first

| Evidence | Reading |
|---|---|
| **`DS-ACT-OVERPAY` is blocked on R-5** | Decisive. The ₹1.00 threshold determines what the dataset must produce to enter `INV-A06`'s population, and R-5 is now formally awaiting owner approval. The dataset cannot be declared correctly until it is answered |
| `groups.detail` has **no planned dataset at all** | The only UNRESOLVED D2 surface with no route to closure. Every other one has an owner |
| `group_blocks` is trivially materialisable | 17 columns, 5 required (`group_name`, `group_code`, `arrival_date`, `departure_date`, `total_rooms`), 0 rows today |
| `FLT-A07` is already `COMMISSIONED` | Overpayment *detection* is already demonstrated by injection. What is missing is a standing population, not proof the control works |

---

## 2. The decision

**Re-sequenced.** `DS-ACT-GROUP` is next; `DS-ACT-OVERPAY` follows R-5.

The reasoning is not that group coverage is more valuable — it is not. It
is that **`DS-ACT-OVERPAY` is blocked and `DS-ACT-GROUP` is not**, and
writing a blocked dataset against a threshold that may change would be
declaring expectations against an unsettled policy. That is the same
mistake the D5.5 remediation existed to prevent: `financials.py` had to be
fixed *before* Step 2 declared expectations against it, or the defects
would have been baked into the baseline permanently. R-5 is the same shape.

`FLT-A07` being commissioned matters here. Overpayment detection is not
unproven — D5 injected the fault and the framework caught it. The gap is
that no *standing* population exercises `INV-A06`, which is a coverage gap,
not a correctness risk. It can wait for the right threshold.

### What is given up by waiting

Stated plainly rather than minimised: `INV-A06` and `INV-D07` stay
certification-blocking for longer, and `INV-A06` stays VACUOUS. Nothing
about that is improved by `DS-ACT-GROUP`. If R-5 is answered quickly the
order should be revisited — this decision is contingent on R-5 being open,
not on group coverage having overtaken overpayment in value.

---

## 3. A naming problem this exposes

`DS-ACT-GROUP` **activates no invariant**, because no invariant, fault or
parity quantity references `group_blocks` anywhere in the registries. Nor
did `DS-ACT-INHOUSE`, which declares `activates_invariants=()`.

The `DS-ACT-` prefix and the `datasets_activation` module both mean
"activates a VACUOUS D4 control". Two of the planned datasets do not, and
both of them are really D2-surface datasets. The modules' own split —
`datasets_core` for positive controls, `datasets_activation` for activating
a VACUOUS control — has **no category for a dataset that exists to give a
golden-master resolver an entity to pin to**.

Not renamed here. Renaming `DS-ACT-INHOUSE` would change a commissioned
dataset's identity, and `dataset_id@version` is its identity — the registry
is explicit that editing a dataset in place is what versioning exists to
prevent. Recorded so the third such dataset does not inherit the confusion
by default.

---

## 4. Revised order

```
1  DS-ACT-INHOUSE     COMMISSIONED 2026-08-08.  D2 +3 / -1
2  DS-ACT-GROUP       next. Closes groups.detail, the only UNRESOLVED
                      surface with no planned owner. Activates 0
                      invariants — a D2-coverage dataset, and the record
                      must say so.
3  DS-ACT-OVERPAY     BLOCKED on R-5. Lifts INV-A06 (VACUOUS,
                      certification-blocking) and gives INV-D07 its first
                      real population.
4  DS-ACT-CORPCREDIT  lifts INV-C06; also closes the 2 company D2 surfaces
5  DS-ACT-CORRECTION  lifts INV-D02 — the only RELEASE_BLOCKING one of the
                      four, which is an argument for moving it earlier
6  DS-ACT-VOIDCN      lifts INV-D05; also lifts Q11
7  DS-ACT-SHIFT       lifts Q21
```

**One observation not acted on.** `INV-D02` is the only VACUOUS invariant
that is `RELEASE_BLOCKING`; the other three are certification-blocking. On
blocking severity alone `DS-ACT-CORRECTION` outranks everything below it
and arguably outranks `DS-ACT-OVERPAY`. Flagged, not re-ordered — the
instruction covered the group/overpay pair only, and re-ordering the rest
on my own reading of severity would be exactly the unilateral
re-prioritisation this record exists to avoid.

---

## 5. Coverage obligation

From this point every new dataset records Coverage Added, Lost, Changed and
Expected vs Unexpected movement, measured rather than asserted. See
`D6_COVERAGE_LEDGER.md`. `DS-ACT-GROUP` is the first dataset that will
carry one from the start; `DS-ACT-INHOUSE` has been backfilled.
