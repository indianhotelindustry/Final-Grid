# D6 — Enterprise Regression Dataset Platform

Technical design. Wave 0, deliverable 6. Written 2026-08-07, after Wave 0.5.

Status of what exists: six modules present and importing, registry
non-functional, zero datasets declared. See `WAVE0_STATUS.md` §3.

---

## 1. The problem D6 exists to solve

D4 commissioned 24 invariants. Four of them have never been exercised,
because the hotel has never produced a row of the shape they check. D1
has the same problem with two quantities. D2 has four surfaces it cannot
pin to anything.

A commissioned rule over an empty population proves nothing (P10). The
framework currently reports `VACUOUS` honestly, which is correct and
useless: it means seven controls are carried on the books as working
without evidence that they work *on data*.

Measured against production on 2026-08-07:

| Probe | Value | Consequence |
|---|---|---|
| `credit_note_count` | 0 | void/credit-note traceability never exercised |
| `void_request_count` | 0 | same |
| `corporate_bookings` | 0 | corporate credit backing never exercised |
| `corporate_credit_used` | 0.00 | same |
| `overpayment_count` | **2** | **see §7.1 — this should not be VACUOUS** |
| `outstanding` | **−1697.32** | **see §7.2 — the hotel has collected more than it charged** |

D6 closes this by making the *data* a declared artefact, held to the same
standard as an invariant or a fault: it must state what it proves, and it
must be shown capable of failing.

---

## 2. What already exists, and is sound

Do not rewrite these. They were designed against the right constraints.

| Module | What it does | Verified |
|---|---|---|
| `model.py` | `Dataset`, `Event`, `Provenance`, `Expectations`, `DatasetResult`. `verdict` treats `NOT_RUN` and `still_vacuous` as `INCOMPLETE`, never `PASS` | imports |
| `registry.py` | `@dataset` declaration + `_validate`. Refuses: no timeline, no principle, no perturbation, no expectation, a perturbation breaking nothing measured, an `activates_invariants` claim with no declared outcome, real guest data with no disclosure statement | imports |
| `schema.py` | `PRESERVED_TABLES` / transactional strip order, and `verify_classification()` | **0 unclassified, 0 missing against live schema** |
| `builder.py` | `strip`, `insert_rows`, `set_business_date`, `content_hash`, `build`, `discard`, `perturb` | imports |
| `financials.py` | 24 declared probes, `measure()`, `unknown_probes()` | **runs against production** |
| `evaluate.py` | Observers for invariants/parity/replay, `_evaluate_faults`, `evaluate()` | imports |

The build strategy is right and should not be revisited: **strip a copy of
production and rebuild the transactional layer**, so the schema is real by
construction and the master data is the hotel's own. `schema.py`'s
docstring records why — D5's `FLT-A10` was never injected because the real
`reservations` table has five NOT NULL money columns a hand-written
statement did not know about. A synthetic schema would have accepted it.

---

## 3. What is missing

| Component | Why it blocks | Effort |
|---|---|---|
| `datasets_core.py` | `registry.load_all()` imports it; **every registry call raises `ImportError`** | large |
| `datasets_activation.py` | same import; this is where the VACUOUS-closing datasets live | large |
| `commission.py` | the discrimination gate. Without it every dataset is `NOT_COMMISSIONED` and excluded from certification by design | medium |
| `report.py` | human-readable output, matching D4/D5 | medium |
| `__init__.py` | package is implicit-namespace only; inconsistent with `golden/`, `replay/`, `invariants/`, `faults/` | trivial |
| CLI in `__main__.py` | `ds-registry`, `ds-build`, `ds-run`, `ds-commission` | small |

---

## 4. Design

### 4.1 The two declaration modules

Split by purpose, not by size, so the reason a dataset exists is visible
from its file.

**`datasets_core.py` — datasets that describe an ordinary hotel.**
The baseline narratives: a walk-in stay paid in cash; a stay across a
closed night audit; a multi-night stay with tax. These exist so that
"nothing is wrong" is a measured statement rather than an assumption, and
so a perturbation has something normal to be perturbed away from.

**`datasets_activation.py` — datasets that exist to activate a control.**
One dataset per empty population. Each declares `activates_invariants`,
and the registry already refuses an activation claim with no declared
expected outcome.

| Dataset | Activates | Closes |
|---|---|---|
| `DS-ACT-OVERPAY` | overpayment recording | D4 VACUOUS |
| `DS-ACT-CORPCREDIT` | corporate credit backing | D4 VACUOUS |
| `DS-ACT-CORRECTION` | correction/reversal traceability | D4 VACUOUS |
| `DS-ACT-VOIDCN` | void/credit-note traceability | D4 VACUOUS, `Q11` |
| `DS-ACT-SHIFT` | shift cash and variance | `Q21` |
| `DS-ACT-INHOUSE` | a checked-in reservation | **D2's 4 UNRESOLVED surfaces** |

`DS-ACT-INHOUSE` is worth calling out: it is the cheapest dataset in the
list and it closes a D2 gap that has been open since the golden masters
were first captured.

### 4.2 The discrimination gate — `commission.py`

Mirrors D4/D5 commissioning. For each dataset:

1. Build it. Record `content_hash`.
2. Evaluate. **Every declared expectation must be met.** A dataset whose
   expectations do not hold on its own data is wrong before it is useful.
3. Apply `perturbation` to a throwaway copy.
4. Re-evaluate. **Every target in `perturbation_breaks` must now be
   unmet.** A dataset that survives its own perturbation is inert.
5. Verify each `activates_invariants` claim: the invariant must no longer
   report `VACUOUS`. A dataset that claims to activate an invariant and
   leaves it vacuous has not done its job — `model.py` already says so;
   this is where it is enforced.
6. Verify production is unchanged (`content_hash` of the source).

A dataset failing any element is `NOT_COMMISSIONED`, reported, and
excluded from every verdict. Same rule as an uncommissioned invariant.

### 4.3 CLI

```bash
python -m verification ds-registry                    # touches no database
python -m verification ds-build   --id DS-ACT-OVERPAY
python -m verification ds-run     --tag production
python -m verification ds-commission
```

`ds-registry` must report, as D4's does: the purpose/origin/version
matrices, the invariant activation matrix, `unactivated_invariants()`,
`unbuildable_datasets()`, `commissioning_gaps()` and
`unbacked_commissioning_claims()` — all six already exist in `registry.py`
and are currently unreachable.

### 4.4 Exit codes

Unchanged from the framework: `0` PASS, `1` FAIL, `2` INCOMPLETE, `3`
ERROR, `4` UNVERIFIED. `ds-run` will report **INCOMPLETE** while any
dataset is uncommissioned or any declared invariant remains vacuous —
`DatasetResult.verdict` already implements this.

---

## 5. Implementation order

Each step ends in a runnable state and a commit.

1. `__init__.py` + CLI stub + `report.py` skeleton → `ds-registry` runs and
   reports an empty registry. **Proves the wiring before any data exists.**
2. `datasets_core.py` with **one** dataset, fully declared → `ds-build`
   and `ds-run` work end to end on a single narrative.
3. `commission.py` → that one dataset is commissioned, or is shown not to
   discriminate and is fixed.
4. `datasets_activation.py`, one dataset at a time, cheapest first:
   `DS-ACT-INHOUSE`, then `DS-ACT-OVERPAY`, then the rest.
5. Remaining core narratives.
6. `D6_COMPLETION_REPORT.md` and README status update.

Do not write six datasets and then try to commission them. The gate is the
part most likely to reveal that a declaration was wrong.

---

## 6. Verification of D6 itself

- `ds-commission` — every dataset discriminates.
- `inv-run --tag production` — the four VACUOUS invariants report `HOLDS`
  or `VIOLATED` on their activation datasets, not `VACUOUS`.
- `run` — `Q11` and `Q21` leave `VACUOUS`.
- `gm-capture` — D2's four UNRESOLVED surfaces resolve.
- `selfcheck` before and after — production untouched.
- `compare --tag v2.2.18_preWave1` — **must show no movement.** D6 adds
  datasets; it must not change what production measures.

---

## 7. Two findings to resolve before declaring expectations

Both surfaced while validating the probes for this design. Neither is
caused by D6, and neither should be designed around until understood.

### 7.1 `overpayment_logs` has 2 rows, yet the overpayment invariant is VACUOUS

D4's completion report lists overpayment recording among the four VACUOUS
invariants. `financials.measure()` reports `overpayment_count = 2` against
the same database.

Both cannot be right. Either the invariant's population filter is narrower
than the raw table (in which case the VACUOUS report is correct and the
probe is measuring something else), or the invariant is not reaching rows
that exist (in which case a control believed to be merely unexercised is
actually not working).

**This must be resolved before `DS-ACT-OVERPAY` is written**, because its
expectations would be declared against whichever answer is assumed.
Investigation: read the invariant's `data_sources` and validation method,
then compare its population query against `SELECT COUNT(*) FROM
overpayment_logs`.

### 7.2 `outstanding` is negative on production: −1697.32

Charges raised less payments collected is **−₹1,697.32** — the hotel has
recorded more collection than it has raised charges for.

This is consistent with defects already on the register (walk-in payments
settled into OTA receivable heads; the dormant divergence awaiting
`room_rent` posting), but it has not been attributed to any of them. A
core dataset declaring a "nothing is wrong" narrative cannot be written
honestly until it is known whether a negative outstanding is a defect or
an artefact of the `room_rent` exclusion.

Recommend: attribute this before step 2 of §5.

---

## 8. Out of scope

- Fixing anything D6 finds. Wave 0 measures; Wave 1 repairs.
- Anonymised datasets from real guest data. The registry supports the
  origin and demands a disclosure statement, but no such dataset is needed
  for the VACUOUS populations, and every one avoided is a data-protection
  risk avoided.
- D9's backup checksum. Still blocked on a production schema change; see
  `WAVE0_STATUS.md` §5.2.
