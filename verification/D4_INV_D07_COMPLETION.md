# R-4 — `INV-D07`, orphan overpayment records

Class D referential invariant, declared and commissioned 2026-08-08.
Closes blind spot **BS-1** of `D5_5_CONSISTENCY_AUDIT.md`.

**COMMISSIONED**, eight of eight elements. The registry now holds **25**
invariants; `inv-run` reports **HOLDS 15 / VIOLATED 6 / VACUOUS 4**, and
the only movement against the `wave0_freeze` state is `registered 24 → 25`
and `HOLDS 14 → 15`. Violations remain 57, release-blocking remains 2.

No production financial logic or schema change. Zero writes, measured by
the engine's own write control across the whole registry.

---

## 1. The gap it closes

`INV-A06` asks *"is every overpaid reservation logged?"* Its population is
reservations, and the log table is only the right-hand side of the check.
Nothing anywhere asked the converse. A stale, orphan or fabricated
`overpayment_logs` row was invisible to every layer — a referential
obligation with no Class D rule behind it.

> **`INV-D07`.** Every `overpayment_logs` row references an existing
> reservation, and either that reservation is still overpaid by more than
> the materiality threshold, or the row carries a non-empty `resolution`
> explaining why it is not.

The population is **the log table**, which is what makes this the converse
of `INV-A06` rather than a restatement of it — and what makes it useful
today: on production it is 2, so **`INV-D07` is not VACUOUS**. It is the
only rule touching overpayment that currently measures anything.

---

## 2. Commissioning

```
positive_case        baseline status HOLDS over 2 row(s), 0 violation(s)
negative_case        status HOLDS -> VIOLATED
fault_injection      1 row(s) changed by the declared seed
detection            the declared invariant fired
evidence             evidence complete
repeatability        identical on re-evaluation in the same process
determinism          two independent processes agreed
order_independence   unchanged when the registry was evaluated in reverse

NULL-CONTROL   0 spurious movements
WRITE-CONTROL  0 writes counted across the whole registry

COMMISSIONING RESULT: 27/27 PASS
```

The seed inserts a 500.00 record against a reservation that is not in
credit, with `resolution` empty rather than omitted — the column is NOT
NULL, and an omitted one would fail to insert and report a broken control
instead of a detected defect.

### All four branches were exercised, not just the seeded one

The declared seed reaches one of the rule's four branches. The other three
decide its answer and would otherwise have been asserted rather than
demonstrated (P9). Each on its own disposable copy:

| Branch | Condition | Required | Result |
|---|---|---|---|
| live | still overpaid beyond threshold, resolution empty | HOLDS | ✓ |
| resolved | not overpaid, resolution recorded | HOLDS | ✓ |
| unexplained | not overpaid, resolution empty | VIOLATED | ✓ |
| orphan | reservation does not exist | VIOLATED | ✓ |

The `live` case deliberately leaves `resolution` empty: if the rule read
the resolution field instead of the balance it would fire, and it does
not. The `orphan` case deliberately carries a resolution: a referential
failure is not excusable by explanation, and it violates anyway.

11 checks, 0 failed. Production byte-identical throughout.
Evidence: `evidence/20260808_inv_d07_branches/`.

---

## 3. Two findings

### 3.1 The threshold makes `INV-A06` and `INV-D07` disagree below it

Measured at the boundary:

| Reservation overpaid by | `INV-D07` |
|---|---|
| 0.50, log row unresolved | **VIOLATED** |
| 2.00, log row unresolved | HOLDS |

Below ₹1.00 this rule reads the reservation as *not overpaid* and reports
its log row as baseless — while `INV-A06` reads the same reservation as
outside its population entirely. **The two rules disagree about whether an
overpayment exists**, and `INV-D07` calls a truthful record unfounded.

Production escapes this only because both live rows carry
`resolution = 'income'`. An unresolved sub-rupee overpayment — the exact
shape this hotel has produced twice — would be reported as an orphan
liability when it is a real one.

This is not suppressed. Suppressing it would hide the consequence of a
policy nobody has decided, and it is the strongest available argument that
**R-5 needs an answer rather than a default**. Carried into
`D5_5_R5_MATERIALITY_PROPOSAL.md`.

### 3.2 The threshold is now declared in two places

`MATERIALITY_THRESHOLD` in `rules_d.py` and `Decimal('-1.00')` inline in
`INV-A06`. Two independent definitions of one business policy is the
defect P1 forbids for financial quantities, and they will not stay in step
by themselves.

Deliberate and recorded rather than collapsed: R-5 is open, and unifying
them now would bake today's answer into the structure. Whichever way R-5
is decided should remove the duplication.

---

## 4. An operational trap found while commissioning

`inv-commission --id INV-D07` writes an evidence pack covering only that
invariant. `registry.unbacked_commissioning_claims()` reads **the most
recent pack**, so the partial run superseded the full one and all 24
previously-commissioned invariants immediately read as unbacked claims.

The engine is right to treat that as fatal — `UNVERIFIED` outranks
everything, and `inv-run` went from exit 1 to **exit 4** — but the trap is
easy to walk into and leaves the registry looking catastrophically broken
when nothing is wrong with it.

**Remedy: a scoped `--id` commissioning run must always be followed by a
full one before the evidence is trusted.** Done here; the full run is
`evidence/20260808_074606_inv_commission`, 27/27.

Not fixed in code. The behaviour is arguably correct — the latest pack
*is* the current evidence — and changing it means deciding whether packs
should merge, which is a D4/D7 question about what a certificate covers.
Recorded for D7.

---

## 5. Framework neutrality

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `inv-commission` (full) | 27/27 PASS, 0 spurious movements, 0 writes |
| `inv-run` | registered 25, HOLDS 15, VIOLATED 6, VACUOUS 4, violations 57, uncommissioned 0, release-blocking `INV-A03` `INV-B03` |
| `compare --tag v2.2.18_preWave1` (D1) | 41 changes, `IMPL_ADDED` 38 / `VERDICT_CHANGED` 3, `Q16`–`Q18` — unchanged |
| `ds-registry` / `ds-run` | 1 dataset, 0 unbacked claims, PASS |

`inv-run` exits 1 for the reasons recorded in `WAVE0_STATUS.md` §1a. Those
are unchanged by this work: `INV-D07` holds, and adds no violation.

---

## 6. What this does not do

- It does **not** make `INV-A06` non-VACUOUS. That still needs a
  reservation genuinely overpaid by more than ₹1.00 — `DS-ACT-OVERPAY`.
- It does **not** settle R-5, and the R-5 decision changes this rule's
  behaviour below the threshold.
- No certification claim follows. D7 does not exist.
