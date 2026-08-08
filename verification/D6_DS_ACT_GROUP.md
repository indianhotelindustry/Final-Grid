# `DS-ACT-GROUP@1.0`

The fourth regression dataset, and **the last non-blocked one**.
2026-08-08.

**COMMISSIONED**, six of six. Coverage ledger **`AS_DECLARED`**.
`ACTIVATION` verifies **0 claims**, which is the honest result: this
dataset activates nothing.

No application code modified. Production byte-identical.

---

## 1. The reassessment

The instruction was conditional: implement it *if* it still activates no
additional verification and no new blocking evidence has emerged.
Re-measured rather than assumed.

**Still activates nothing.** No invariant's `data_sources` names a group
table, no fault mentions one, no parity quantity reads `GroupBlock`.
Re-checked *after* the ledger was extended to D1 — if any quantity touched
groups, that extension was the moment it would have surfaced. None did.

**No new blocking evidence.** `group_blocks` is transactional and covered
by `content_hash`, so it carries none of the `DS-ACT-CORPCREDIT` problem.

**One thing changed in its favour.** The D2 expectation element now exists,
so this dataset can *declare* that `groups.detail` resolves and have the
registry check it. Written a day earlier the claim would have been
unverifiable — exactly where `DS-ACT-INHOUSE` was left.

So it goes ahead as what it is: a **D2-coverage dataset that activates
nothing**, closing the last UNRESOLVED surface with no other owner. It is
written now because everything with higher verification value is blocked on
a decision rather than on engineering.

---

## 2. The dataset

| | |
|---|---|
| Key | `DS-ACT-GROUP@1.0` |
| Purpose | `BASELINE` |
| Business date | 2026-09-21 |
| Rows | 20, across 9 tables |
| Content hash | `c03c512e6592…` |
| Expectations | 56 — 34 financial, 11 invariant, 6 parity, 5 golden |

Two rooms for one night under group block `GRP-2026-0001`, with a ₹590
banqueting charge on the first. Raised ₹2,690.00, collected ₹2,690.00,
outstanding nil.

```
BUILD           20 rows into 9 tables, content hash c03c512e6592
POSITIVE        all 56 declared expectation(s) met
PERTURBATION    1 row(s) changed by 1 statement(s)
DISCRIMINATION  all 1 declared target(s) broke; 2 further also broke
ACTIVATION      0 claim(s) verified
ISOLATION       production byte-identical across both builds
```

The perturbation moves the banqueting charge off its folio. The money is
untouched — same amount, same reservation — and the charge stops belonging
to a folio, which is the production defect `INV-A02` reports 40 times over.

---

## 3. Two findings

### 3.1 The application has no master-account routing

The first draft settled the whole ₹2,690.00 on the master folio, which is
what "billed to one master account" ought to mean. **`INV-C02` reported
room 106 as a checked-out reservation that was never settled, and it was
right to.**

`group_blocks.billing_instructions` is **free text**.
`services_group_stay` only links reservations to rooms. Nothing anywhere
moves one reservation's charges onto another's folio.

So the narrative was describing something the system cannot do. It is
modelled as the system actually works — each room settling its own folio —
and the gap is recorded rather than papered over. **Anyone billing a real
group to a master account would have every non-master reservation reported
by `INV-C02`.** Whether that is a missing feature or a missing invariant
exemption is a Wave 1 question.

### 3.2 A group block has its own status vocabulary

`CHECK ck_group_status` allows only `Tentative`, `Confirmed`, `Cancelled`
and `Completed` — not the reservation vocabulary. The first draft assumed
otherwise, and `builder.insert_rows` named the constraint rather than
surfacing an opaque `IntegrityError`. That is the failure mode the builder
was written after (`FLT-A10`), working as intended.

---

## 4. Coverage ledger

Declared before the dataset was built:
`evidence/20260808_ds_act_group_prediction/prediction.md`.

| | |
|---|---|
| **Added** | `groups.detail__any_group` — the whole point |
| **Lost** | `reports.night_audit_snapshot__night_audit_log`, 7 invariants, `Q15` |
| **Changed** | 13 invariants and 4 quantities |
| **Expected vs Unexpected** | **`AS_DECLARED`** |

### The prediction, scored honestly

Right: the single surface added; the seven deactivated invariants (not
eight — `INV-A03` survives because there is an extra charge); `Q15` lost;
no invariant activated; `Q09`, `Q02` and `Q07` **not** moving, since they
diverge only where a correction or reversal exists and this narrative has
neither. That last one was the sharpest test — copying the previous
dataset's parity declaration would have got it wrong.

Wrong: **`Q17`**. Predicted AGREED, measured DIVERGED. The prediction named
`Q20` as its weakest point and `Q20` held. Two occupied rooms on one night
is the first dataset to give the MIS aggregates more than a single room to
add up, and they disagree with the flash report over it. Recorded rather
than quietly corrected.

---

## 5. Framework neutrality

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `ds-commission` | PASS — 4 datasets, 6/6 each, 0 unbacked claims |
| `ds-coverage` | `AS_DECLARED`, exit 0 |
| `ds-registry` | 4 registered, **0 datasets without a passing ledger** |
| production | DB and all 68 `app/*.py` byte-identical |

---

## 6. Where Wave 0 stands

**This is the last non-blocked dataset.** Everything remaining waits on a
decision:

| | Blocked on |
|---|---|
| `DS-ACT-OVERPAY` → `INV-A06` | **R-5**, governance, awaiting approval |
| `DS-ACT-CORPCREDIT` → `INV-C06` | **the `companies` / `content_hash` question** |
| `DS-ACT-SHIFT` → `Q21` | nothing — but it activates a D1 quantity only |

`DS-ACT-SHIFT` is the one genuinely unblocked item left, and it lifts `Q21`
(shift cash and variance, VACUOUS). It was not started here because the
instruction was to implement `DS-ACT-GROUP` "before returning to
governance-dependent work", and that is where the queue now points.

Two of the four VACUOUS invariants are closed. The two that remain are both
certification-blocking and both blocked on someone's decision.

No certification claim follows. D7 does not exist, and `inv-run` still
reports FAIL with two release-blocking violations on production.
