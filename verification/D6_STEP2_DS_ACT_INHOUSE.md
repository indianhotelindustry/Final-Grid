# D6 Step 2 — `DS-ACT-INHOUSE@1.0`

The first declared regression dataset. 2026-08-08.

**COMMISSIONED**, all six elements, first of the six planned datasets.
Step 2 is begun, not finished: five remain.

No production financial logic, schema object or configuration value was
modified. Production is byte-identical, verified per build by the
ISOLATION element rather than once per run.

---

## 1. The dataset

| | |
|---|---|
| Key | `DS-ACT-INHOUSE@1.0` |
| Title | One guest in house part paid, one departed and settled |
| Purpose | `BASELINE` |
| Origin | `SYNTHETIC` — no production row copied, transformed or sampled |
| Business date | 2026-06-15 |
| Rows | 19, across 8 tables |
| Content hash | `061b19c2df20e765…` |
| Expectations | 41 — 31 financial, 10 invariant |

Two stays, both correct:

```
reservation 1, in house, 2 nights x 1,000.00   room     2,000.00
  GST 5% (CGST 2.5 + SGST 2.5)                 tax        100.00
  advance taken at check-in, cash                     - 1,000.00
                                               owed     1,100.00

reservation 2, departed, 1 night x 1,000.00    room     1,000.00
  GST 5%                                       tax         50.00
  settled in full on departure, cash                  - 1,050.00
                                               owed         0.00
                                               --------------------
room revenue 3,000.00  tax 150.00  paid 2,050.00  OUTSTANDING 1,100.00
```

Every figure is exact at two places. `1,000.00 × 2.5% = 25.00` exactly, six
times, so no rounding residue is possible — deliberately, because
production cannot make that claim and a first dataset whose arithmetic is
arguable makes every failure ambiguous.

---

## 2. Commissioning

```
BUILD          19 rows into 8 tables, content hash 061b19c2df20
POSITIVE       all 41 declared expectation(s) met
PERTURBATION   2 row(s) changed by 2 statement(s)
DISCRIMINATION all 4 declared target(s) broke
ACTIVATION     0 claim(s) verified
ISOLATION      production byte-identical across both builds

OVERALL VERDICT: PASS, exit 0
```

The perturbation is two statements chosen to break two different *kinds*
of expectation — `amount = 500.00` and `folio_id = NULL` on payment 1 —
because a perturbation that only moves money shows the financial probes
discriminating and says nothing about whether an invariant expectation can
fail. Declared broken: `outstanding`, `payments_gross`, `payments_net`,
`INV-A02`. All four broke.

`ACTIVATION` reports **0 claims verified**, which is honest rather than
weak. An in-house stay lifts none of the four VACUOUS invariants — those
need an overpayment, a corporate booking, a correction and a void
respectively. Claiming an activation here would have failed the gate.

**Build determinism** was verified separately, since certification depends
on it and no commissioning element checks it: three consecutive builds
produced the identical content hash.

---

## 3. The gate rejected the first declaration, correctly

The first draft declared `INV-C01: HOLDS` — *no payment through an
`ota_receivable` mode belongs to a `Walk-in` reservation*. Both stays pay
cash, so the invariant's population is empty and the engine reports
`VACUOUS`. Commissioning failed `POSITIVE` on it.

The declaration was wrong, not the engine: an empty population proves
nothing (P10), and the fix was to declare `VACUOUS` — which states out
loud that this dataset does not exercise `INV-C01` — rather than to add an
OTA payment so the number would come out right. This is the D6 charter's
own argument for declaring expectations before running anything, and it
failed on the first dataset written under it.

---

## 4. What this dataset does to D2 — measured, and it is not what was planned

The roadmap justifies `DS-ACT-INHOUSE` as resolving "D2's four UNRESOLVED
surfaces". Three of those four words are wrong.

**The count is six, not four.** Read from
`masters/production/index.json`, not from a document:

| Resolver | Surfaces | Endpoints |
|---|---|---|
| `inhouse_reservation` | 3 | `main.checkout`, `main.reservation_folio`, `pos.room_charges_api` |
| `any_company` | 2 | `main.get_company_credit`, `main.company_detail` |
| `any_group` | 1 | `groups.detail` |

`WAVE0_STATUS.md` §4.1 says four; the D2 completion report §10 says five.
The index says six. **`groups.detail` is covered by no planned dataset at
all** — `group_blocks` is empty and there is no `DS-ACT-GROUP` on the list.

**A dataset can lose D2 coverage as well as gain it.** The first version of
this dataset had only the in-house guest. Captured against, it resolved
the three in-house surfaces and **un-resolved four** pinned to
`checked_out_reservation` — the tax invoice, the invoice detail API, the
split-billing sub-ledger and the settled-folio variant.

That is structural, not a slip. `builder.strip()` *replaces* the
transactional layer, so D2 coverage over a dataset is never automatically
a superset of coverage over production, and the trade is invisible unless
somebody captures masters and counts. Nothing in D6 does, because D6
cannot declare a D2 outcome (§5).

The narrative therefore carries both shapes. Measured after:

```
production            158 surfaces captured, 6 UNRESOLVED
DS-ACT-INHOUSE@1.0    160 surfaces captured, 4 UNRESOLVED

gained   main.checkout, main.reservation_folio, pos.room_charges_api  (+3)
lost     reports.night_audit_snapshot                                 (-1)
```

The remaining loss is stated rather than worked around. `night_audit_log`
resolves on production because one row exists there; this dataset declares
no night audit. A hand-written one is not a row that can be invented —
`INV-B02` checks `snapshot_hash` against a recomputation of
`snapshot_json`, and `INV-B03`, the CRITICAL invariant with a demonstrated
detection gap (`FLT-D03`), checks that recomputing the closed day
reproduces the frozen figures. Either it fails both or it gets tuned until
it passes. It belongs in a dataset written for it.

---

## 5. Registry gap — D6 cannot declare a D2 outcome

`Expectations` carries charter elements 3 to 7: financial, invariants,
replay, parity, faults. **There is no element for D2.**
`Layer.D2_GOLDEN` exists in the vocabulary and `evaluate.PROBE_FOR` maps it
to a probe, but `Expectations.declared_layers()` is computed from
`parity`, `replay`, `invariants` and `faults` alone, so `D2_GOLDEN` is
never returned and never swept. It is dead vocabulary.

The consequence lands squarely on the first dataset: the thing
`DS-ACT-INHOUSE` primarily exists to do is the one thing the registry
cannot check. Every figure in §4 was produced by hand
(`_gm_capture_json --db`) and none of it is enforced by a gate.

Closing it means a sixth expectation element and a resolver-count probe.
That is D2/D6 integration work, not a footnote to a dataset. **Recorded,
not fixed.**

---

## 6. A platform defect this dataset exposed — fixed

`registry.unbacked_commissioning_claims()` is the cross-check that stops a
`COMMISSIONED` status typed into source from being trusted without
evidence. **It could never find evidence.**

```python
packs = sorted(n for n in os.listdir(EVIDENCE_DIR)
               if n.endswith('_ds_commission'))      # before
```

`ds-commission` writes its pack as `{timestamp}_ds_commission_{tag}`, and
it only writes one when `--tag` is given — so a commissioning pack always
carries a trailing tag and `endswith('_ds_commission')` can never match.
Every dataset declaring `COMMISSIONED` would have been reported as an
unbacked claim forever, on a check that looked like it was working.

**Step 1 could not have found this.** With an empty registry there are no
claimants and the function returns before it looks at the evidence
directory. It surfaced the moment a dataset first declared `COMMISSIONED`.

Fixed to match on containment. The repair was then commissioned rather
than assumed, because "make the check find something" is the same defect
with the opposite sign — a cross-check that always passes is no better
than one that never fires. Seven cases, EVIDENCE_DIR pointed at a
throwaway directory each time:

| Evidence state | Required answer | Got |
|---|---|---|
| No packs at all | claim reported | ✓ |
| Tagged pack, dataset passed | claim backed | ✓ |
| Tagged pack, dataset **failed** | claim reported | ✓ |
| Older pack passed, latest failed | claim reported | ✓ |
| Older pack failed, latest passed | claim backed | ✓ |
| Only a `ds_registry` pack present | claim reported | ✓ |

The third row is the one the original suffix match could never reach, and
it is the case the check exists for.

After the fix, `ds-registry` reports **0 unbacked claims** and names the
pack it read.

---

## 7. Framework neutrality

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `compare --tag v2.2.18_preWave1` (D1) | 41 changes, `IMPL_ADDED` 38 / `VERDICT_CHANGED` 3, `Q16`–`Q18` — identical to Step 1 and to the R-1/R-2/R-3 remediation |
| `inv-run` (D4) | registered 24, violations 57, uncommissioned 0, release-blocking `INV-A03` `INV-B03` — identical to `wave0_freeze` |
| `ds-registry` | 1 registered, 0 unbacked claims, evidence pack named |
| `ds-run` | PASS, 41 met, 0 unmet, 0 not-run |
| `ds-commission` | PASS, 6 of 6 elements |

---

## 8. What is still true

`ds-run` and `ds-commission` now exit 0 rather than 2. That is a statement
about one dataset and nothing more. **No certification claim follows from
it**: D7 does not exist, `fault-run` still reports INCOMPLETE, and the
invariant engine still reports FAIL with two release-blocking violations
on production. Nothing in Wave 0 may be described as certified.

### Next

1. **`DS-ACT-OVERPAY`** — needs **R-4** (the Class D invariant for orphan
   overpayment records) declared and commissioned first, and needs the
   **R-5** owner decision on the ₹1.00 materiality threshold, because that
   threshold determines what the dataset has to produce to be in the
   population at all.
2. Then `DS-ACT-CORPCREDIT` (closes 2 more D2 surfaces),
   `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN`, `DS-ACT-SHIFT`.
3. **`DS-ACT-GROUP` is missing from the plan** and is the only route to
   `groups.detail`. Add it or record the surface as permanently
   unresolved.
4. The D2 expectation element (§5), if D6 is to enforce its own main claim.
