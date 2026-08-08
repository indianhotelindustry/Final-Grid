# Wave 0 — Deliverable Status

DSBC Frontline v2.2.18. Last verified 2026-08-08 (Wave 0.8).

Counts in this document are read from the live registries, not
transcribed from the completion reports. Where a report and the
repository disagree, the repository wins and the disagreement is stated.

**Wave 1 may not begin until all ten deliverables are complete and
commissioned.** Five are. Wave 0 is half done.

---

## 1. Status at a glance

| # | Deliverable | Status | Commissioned |
|---|---|---|---|
| D1 | Financial Parity Harness | Complete | 8 / 8 |
| D2 | Golden Master Framework | Complete | 16 / 16 |
| D3 | Historical Replay Framework | Complete | 21 / 21 |
| D4 | Financial Invariant Engine | Complete | 27 / 27 |
| D5 | Fault Injection Platform | Complete | 37 / 37 |
| D6 | Regression Dataset Framework | **Step 2 — 5 datasets commissioned. Every unblocked one is written; the rest need a decision** | 5 / 5 |
| D7 | Certification Engine | Not started | — |
| D8 | CI/CD Verification Pipeline | Not started | — |
| D9 | Backup Restore Verification | **Blocked** | — |
| D10 | Release Gate Framework | Not started | — |

Live registry counts, 2026-08-08:

| Artefact | Count |
|---|---|
| Parity quantities (D1) | 22 — `Q01`–`Q22` |
| Invariants (D4) | **25** — `INV-D07` added by R-4, 2026-08-08; **all 25 COMMISSIONED** |
| Faults (D5) | 40 — 10 each in classes A/B/C/D; 36 COMMISSIONED, 4 UNCOVERED |
| Regression datasets (D6) | 5 — `DS-ACT-INHOUSE`, `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN`, `DS-ACT-GROUP`, `DS-ACT-SHIFT`, all COMMISSIONED, all with a passing coverage ledger |
| Invariants with an activating dataset | 2 of 25 — `INV-D02`, `INV-D05` |
| Golden master surfaces (D2) | 158 — 6 UNRESOLVED on production; `groups.detail` now resolves on a dataset |
| Replayed business dates (D3) | 28 |
| Retained evidence packs | 147 |
| Constitutional principles enforced | 14 — no principle uncovered |

---

## 1a. Measured state at the freeze point

`python -m verification inv-run --tag wave0_freeze`, 2026-08-07.
Evidence: `evidence/20260807_163441_inv_run_wave0_freeze`. **Exit 1.**

```
Registered 24    HOLDS 14    VIOLATED 6    VACUOUS 4
Violations found  : 57
Uncommissioned    : 0
OVERALL VERDICT   : FAIL
Release blocking  : 2
Cert. blocking    : 5
```

| Invariant | Violations | Note |
|---|---|---|
| `INV-A02` Every financial row belongs to a folio | **40** | the universal NULL folio attribution defect |
| `INV-C01` A walk-in is never settled through an OTA head | 5 | all 5 `ota_receivable` payments are on walk-ins |
| `INV-C05` An OTA settlement identifies the agent | 5 | same population |
| `INV-A03` Charges summed over folios equal charges | 5 | follows from `INV-A02` |
| `INV-B03` Recomputing a closed day reproduces its figures | 1 | **CRITICAL / RELEASE_BLOCKING** |
| `INV-C04` No room is occupied by two reservations | 1 | |

The four `VACUOUS` are `INV-A06`, `INV-C06`, `INV-D02`, `INV-D05` — the
exact four D6 exists to activate.

**This section records the freeze run and is not rewritten.** Since R-4 the
registry holds 25 and the same run reports `HOLDS 15 / VIOLATED 6 /
VACUOUS 4`: `INV-D07` holds over a population of 2. Violations, the
violated set, release-blocking and certification-blocking counts are all
unchanged. Latest: `evidence/20260808_074618_inv_run_d07_final`.

**This is why nothing here may be described as certified.** The engine
reports `FAIL` with two release-blocking violations, and D7 — the
Certification Engine that would issue a certificate — does not exist.

---

## 2. D1–D5 — complete and commissioned

Each was independently commissioned, each demonstrated production-safe
operation, and each produced real findings. No production financial
behaviour was modified by any of them.

**D1 — Financial Parity Harness.** 22 quantities, each measured by every
implementation the codebase contains and compared against the others.
Renamed `P01`–`P22` → `Q01`–`Q22` in Wave 0.5 to clear the collision with
the constitution; see `CONSTITUTION.md` §3.3.

**D2 — Golden Master Framework.** 158 surfaces captured and re-rendered.
Change detection, not attribution — it moved for 31 of 36 injected faults
while being the declared detector for 3.

**D3 — Historical Replay Framework.** Every historical business date
reconciled three ways: LEDGER (plain SQL, no application code), ENGINE
(the application, clock frozen), RECORDED (the night-audit snapshot).

**D4 — Financial Invariant Engine.** 25 declared invariants, every one
commissioned across eight elements. Zero writes is measured, not assumed.
`INV-D07` was added by R-4 in Wave 0.6.

**D5 — Fault Injection Platform.** 40 faults across five injection
methods. Asks the question the other four cannot: inject one defect, ask
all four layers at once which noticed and which stayed silent.

---

## 3. D6 — Regression Dataset Framework: partial

The roadmap and `README.md` both record D6 as "Not started". **This is
wrong.** Six modules exist, written 2026-08-05 06:15–06:20, after the D5
report was finalised at 05:37:

```
datasets/  model.py  registry.py  schema.py  builder.py  financials.py  evaluate.py
```

All six import cleanly. The registry does not work:

```
>>> registry.all_datasets()
ImportError: cannot import name 'datasets_core' from 'verification.datasets'
```

`registry.py:222-224` imports `datasets_core` and `datasets_activation`.
**Neither file exists.** Zero datasets are declared.

Missing against the pattern D4 and D5 both established:

| Component | State |
|---|---|
| `model.py`, `registry.py`, `schema.py`, `builder.py`, `financials.py`, `evaluate.py` | present from the start |
| `__init__.py` | **added, Step 1** |
| `datasets_core.py`, `datasets_activation.py` | **added, Step 1 — present and empty** |
| `commission.py` — the discrimination gate | **added, Step 1** |
| `report.py` | **added, Step 1** |
| CLI wiring in `__main__.py` | **added, Step 1** — `ds-registry`, `ds-build`, `ds-run`, `ds-commission` |
| **Dataset declarations** | **none — this is Step 2** |

### Step 1 complete (commit `23e3b94`)

The platform is wired and proved to run. `ds-registry` exits 0 against an
empty registry; `ds-run` and `ds-commission` exit 2 `INCOMPLETE`, never
`PASS`, because a platform that has measured nothing has demonstrated
nothing (P10).

The two declaration modules are **present and empty** rather than absent:
`registry.load_all()` imports them by name, so deleting them breaks every
registry call, and making `load_all()` tolerant of a missing module would
hide a genuinely absent declaration file later.

Verified at Step 1: production `sha256` unchanged, 64 modules import, and
the D1 release gate is byte-identical before and after — 41 changes,
`IMPL_ADDED` 38 / `VERDICT_CHANGED` 3, `Q16`–`Q18`, both runs.

### Probe remediation complete (2026-08-08)

R-7 followed in Wave 0.7: the probes summed `amount` unsigned, so a
reversal was added where it must be subtracted. See §7.

`financials.py` carried three defects that would have been baked into the
Step 2 baseline. R-1, R-2, R-3 and R-6 are applied and verified; the same
D1 gate is byte-identical again, a third time. See §7 and
`D5_5_REMEDIATION_APPLIED.md`. **Step 2 is no longer blocked.**

---

## 4. Open findings carried into Wave 1

None of these are fixed. Per the standing Wave 0 instruction, every layer
reads and reports; nothing repairs.

### 4.1 Empty populations — what D6 exists to close

| Item | Layer | Why it proves nothing |
|---|---|---|
| `Q11` refunds/voids | D1 | **CLOSED 2026-08-08** — lifted to DIVERGED by `DS-ACT-VOIDCN`, and it found the night audit reporting voided payments as refunds |
| `Q21` shift cash and variance | D1 | **CLOSED 2026-08-08** — activated by `DS-ACT-SHIFT`, AGREED over one balanced shift |
| Overpayment recording (`INV-A06`) | D4 | VACUOUS — commissioned, never exercised. **Every overpayment this hotel has recorded is below its ₹1.00 threshold**, so its real coverage is zero; see the R-5 proposal |
| Orphan overpayment records (`INV-D07`) | D4 | **Not vacuous** — population 2, HOLDS. Added by R-4 |
| Corporate credit backing | D4 | VACUOUS |
| Correction/reversal traceability (`INV-D02`) | D4 | **CLOSED 2026-08-08** — activated by `DS-ACT-CORRECTION@1.0`, population 4, HOLDS. Still VACUOUS on production, correctly: production holds no correction |
| Void/credit-note traceability (`INV-D05`) | D4 | **CLOSED 2026-08-08** — activated by `DS-ACT-VOIDCN@1.0`, population 2, HOLDS. Still VACUOUS on production, correctly |
| **6** golden master surfaces | D2 | UNRESOLVED — 3 need a checked-in reservation, 2 a company, 1 a group block. `DS-ACT-INHOUSE` closes the first 3 **on the dataset**; production is unchanged |

A commissioned rule over an empty population still proves nothing about
the data (P10).

### 4.2 Controls that do not speak when they should

| Finding | Severity |
|---|---|
| `INV-B03` does not move when an audited day's stored close total is rewritten (`FLT-D03`) | **CRITICAL** |
| D3's `RC07` does not move for a guest checked out with an unexplained balance, though day totals do (`FLT-A09`) | HIGH |

Both defects are caught by other layers, so neither is invisible — but the
control that should *name* them does not. Note that `INV-B03` is also the
sole invariant enforcing P4 (Night Audit orchestrates rather than
derives): the principle with the narrowest coverage is the one with a
demonstrated detection gap.

### 4.3 Four faults nothing in the framework can detect

Registered so the gaps are tracked. Never injected, never counted as
passes.

| Fault | Needs |
|---|---|
| Invoice number uniqueness | a D4 invariant |
| Backup file corruption (`FLT-D04`) | **D9** |
| Restored database does not match what was backed up (`FLT-D05`) | **D9** |
| Environment drift between runs (`FLT-D07`) | **D7** environment fingerprint |

**The system currently cannot tell whether its backups are restorable.**

### 4.4 Coverage that is thinner than it looks

- **7 golden master surfaces return HTTP 500** and are captured as such. A
  master over a 500 records a defect; it is not evidence of correctness.
- **20 declared reconciliations cover ~20 of ~220 engine figures per
  date.** The rest are compared between runs but not against the primary
  record.
- **D3 has one closed business day.** The control against what the system
  froze at close is exercised on a single date. It found a defect there;
  one date is not a demonstration that the control scales.
- **As-at drift reports nothing on this dataset.** Proven live only by
  commissioning (`S-RP-ASAT`), not by a live finding.
- **P2 and P4 are enforced only indirectly.** `INV-B01/B02/B03` cover them
  as a side effect; neither principle has an invariant written for it.
- **3 D4 invariants are challenged by no D5 fault.** Singly verified, not
  unverified.
- **`ENGINE_PATCH` cannot reach a callable bound at import time under a
  different name** — `Q16` and `Q18` reach `get_cash_revenue` through the
  `get_daily_revenue` alias (`FLT-C01` declares this rather than dropping
  the expectation).

### 4.5 Known production defects, found by the framework, unfixed

Recorded in the completion reports and not rediscovered here:

- Multiple independent room revenue definitions
- Night Audit using present-tense operational state
- Historical reports drifting after closure
- Walk-in payments settled into OTA receivable accounts
- Universal NULL folio attribution
- Dashboard KPI methods ignoring historical dates
- Dormant financial divergence awaiting `room_rent` posting

Added 2026-08-08, found by `DS-ACT-CORRECTION` and **not repaired**:

- **`compute_stay_gst` taxes reversed money.** `gst_service.py:492` reads
  `ec.amount` unsigned and never calls `signed_extra_charge_amount`, so a
  reversed charge is taxed instead of untaxed. Measured: **₹180.00 of GST
  on a ₹500 charge that was taken back**, compounding with each further
  correction, inherited by checkout, the invoice, `settlement_balance` and
  every report downstream of `calculate_stay_amount`. A new instance of
  the "multiple independent definitions" class — `tax_lines` says one
  thing, `compute_stay_gst` computes another — and the first anybody has
  been able to point at, because production holds no correction row.
  `DS-ACT-CORRECTION` declares `INV-C02` VIOLATED by exactly that amount.
  Evidence: `evidence/20260808_gst_reversal_defect/`.
- **`tax_lines` cannot express a reversal.** No `is_reversal`, no
  `corrects_id`. The correction pattern that exists for money has no
  counterpart for tax, so a reversed taxed charge has no declared way to
  unwind its tax line. Schema gap; belongs with whoever owns the GST path.

Added 2026-08-08, found by `DS-ACT-VOIDCN` and **not repaired**:

- **Every cancellation refund violates `INV-D02`.**
  `services.post_cancellation_disposition` builds the refund row with
  `is_reversal=True` and **never sets `corrects_id`** — the only four
  assignments of it in `services.py` are inside `post_payment_correction`
  and `post_extra_charge_correction`. `INV-D02` is CRITICAL and
  RELEASE_BLOCKING and forbids exactly that. Derived from source before
  the dataset was written, then confirmed by building it.
  `DS-ACT-VOIDCN` declares `INV-D02` VIOLATED.
- **The night audit reports voided payments as refunds.** `Q11` went
  VACUOUS → DIVERGED on its first exposure to real data: **₹1,286.00 of
  voided payments counted as refunds against ₹236.00 of true refunds.** A
  voided payment never left the bank; a refund did, so conflating them
  overstates refunds by the value of every void. `Q11` is `Severity.BLOCK`
  and exists to detect this; it had never fired.
  Evidence: `evidence/20260808_ds_act_voidcn_q11/`.
- ~~No probe nets credit notes against the balance~~ — **closed by R-8**,
  `net_receivable`. Recorded here because it was found by `DS-ACT-VOIDCN`
  before it was fixed.
- **The application has no master-account routing.**
  `group_blocks.billing_instructions` is free text and nothing implements
  it; `services_group_stay` only links reservations to rooms. Billing a
  real group to a master account would leave every non-master reservation
  reported by `INV-C02` as checked out and unsettled. Found by
  `DS-ACT-GROUP`.
- **Three parity quantities agree on production and prove nothing.**
  `Q09` (payments total, signed vs raw), `Q02` (charge count by category)
  and `Q07` (tax by component) all read AGREED on production and DIVERGE
  the moment a correction or reversal exists. `Q09` measures exactly the
  defect class R-7 fixed and had never been able to fire. Found by
  extending the coverage ledger to D1.
- **`Q18` and `Q20` diverge on extra charges, not on occupancy.** The
  executive dashboard tiles and the ADR/RevPAR definitions agree on a
  room-only hotel and disagree the moment an extra charge exists —
  established across five datasets, two rooms appearing on both sides of
  the split. This narrows a production DIVERGED that predates Wave 0 to its
  cause. Found by the coverage ledger.

---

## 5. Blockers on Wave 1

1. **D6 is partial; D7–D10 do not exist.** Wave 1 is gated on all ten. D6
   has its platform and one commissioned dataset of six.
2. **D9 is blocked at the schema.** `backup_logs` stores filename, size
   and status but **no checksum**. `FLT-D04`/`FLT-D05` are undetectable
   until that changes — which requires a production schema change that
   Wave 0 forbids. This needs an explicit, recorded exception before D9
   can start. It is the only Wave 0 deliverable that cannot be built
   without touching production.
3. **`fault-run` reports INCOMPLETE and will until D7 and D9 exist.**
   Correct behaviour — reporting PASS would make it a control that cannot
   fail — but it means no green Wave 0 verdict is achievable on the
   current deliverable set.
4. **The dataset is thin.** 733 KB production database, one closed
   business day. Every framework built so far measures a near-empty
   population. This is the argument for D6, and one dataset does not
   answer it — the four VACUOUS invariants are still VACUOUS, because
   `DS-ACT-INHOUSE` activates none of them and said so.
5. **Evidence lives inside the application.** Phase 2.6 §10 requires
   certification evidence to be exported outside it. Not automated; a
   release-process responsibility.

---

## 6. Governance documents

Recovered or created in Wave 0.5. The Phase 1 / 2 / 2.5 / 2.6 source
documents were **not present in the repository** and remain unrecovered.

| Document | State |
|---|---|
| `CONSTITUTION.md` | Recovered from the enforcing registry. P15 open — see §3.1 of that file |
| `ENGINEERING_GUIDE.md` | Written Wave 0.5 |
| `WAVE0_STATUS.md` | This file |
| `README.md` | Pre-existing, authoritative for framework usage |
| `D4_INV_D07_COMPLETION.md` | Written 2026-08-08; R-4 |
| `D5_5_R5_MATERIALITY_PROPOSAL.md` | Written 2026-08-08; **awaiting owner approval** |
| `D6_SEQUENCING_DECISION.md` | Written 2026-08-08; the group/overpay re-sequencing and its evidence |
| `D6_COVERAGE_LEDGER.md` | Written 2026-08-08; the Added/Lost/Changed obligation |
| `D6_DS_ACT_CORRECTION.md` | Written 2026-08-08; the first activating dataset, and the GST-on-reversed-money defect |
| `D6_DS_ACT_VOIDCN.md` | Written 2026-08-08; `INV-D05` and `Q11`, the refund `corrects_id` defect, and the voids-reported-as-refunds divergence |
| `D6_DS_ACT_GROUP.md` | Written 2026-08-08; the group dataset, and the absence of master-account routing |
| `D6_DS_ACT_SHIFT.md` | Written 2026-08-08; `Q21`, and what five datasets settled about `Q18`/`Q20` |
| `WAVE1_BLUEPRINT.md` | Written 2026-08-08; the Wave 1 readiness review, the silence census and the gate |
| `D1`–`D5` completion reports | Pre-existing, retained |
| `D5_5_REMEDIATION_APPLIED.md` | Written 2026-08-08; records R-1/R-2/R-3/R-6 and four errors found in the D5.5 documents |
| `D6_STEP2_DS_ACT_INHOUSE.md` | Written 2026-08-08; the first commissioned dataset, and the D2 measurement behind it |
| Phase 1 Architecture Audit | **Absent** |
| Phase 2 Financial Truth Certification | **Absent** |
| Phase 2.5 Migration Blueprint | **Absent** |
| Phase 2.6 source (Constitution / PVF / Governance) | **Absent** — cited throughout, including §10 and §13 which this framework defers to |

The framework defers to Phase 2.6 sections that nobody can currently read.
Recovering those documents is not optional work.

---

## 7. Where to resume

**This section is the handover. Read it first.**

State as of 2026-08-08, working tree clean, three tags:
`v2.2.18-preWave1`, `v2.2.18-wave0.5`, `v2.2.18-wave0.5-frozen`.

### The probe fixes are done

**R-1, R-2, R-3 and R-6 landed 2026-08-08.** `datasets/financials.py` is
now safe to declare expectations against — which was the whole reason they
blocked Step 2.

| | Fix | Result |
|---|---|---|
| **R-1** | `outstanding` omits tax | −1,697.32 → **+199.92** ✓ |
| **R-2** | `outstanding` will double count once room rent posts | excluded; **commissioned by injecting all 30 night rates** — probe holds at 199.92 where the old form moves to 37,417.04 |
| **R-3** | `taxable_total` double counts CGST/SGST | 75,893.34 → **37,946.67** ✓ |
| R-6 | no probe models `invoice_round_off_amount` | four invoice probes added; `unrounded + round_off = rounded` exact on all 28 |

21 of the 23 pre-existing probes hold; the 2 that moved are the 2 declared
to move. D1, D4 and `ds-registry` are unchanged, and the 68 production
`.py` files and `pms.db` hash identically before and after.

Report: `D5_5_REMEDIATION_APPLIED.md`.
Evidence: `evidence/20260808_r123_remediation/`.

**Three specification errors were found while applying it** — R-1's
"21 of 28" (it is 19), R-3's grouping key (omitting `reservation_id`
under-counts to 18,613.29), and R-3's expected value (37,946.67, not
37,946.97). A fourth is in the audit: BS-4's residue attribution. All four
are recorded in `D5_5_REMEDIATION_APPLIED.md` §8. The audit's final
authoritative table is confirmed in full and remains the truth to declare
against.

### D6 Step 2 has begun — one dataset of six

**`DS-ACT-INHOUSE@1.0` is COMMISSIONED**, all six elements, 2026-08-08.
19 rows, 41 expectations, content hash `061b19c2df20e765`, deterministic
across three builds. `ds-run` and `ds-commission` now exit 0 rather than 2.

Report: `D6_STEP2_DS_ACT_INHOUSE.md`.

Three things it established that were not known before:

- **The gate rejected the first declaration.** It claimed `INV-C01: HOLDS`
  where the population is empty and the answer is `VACUOUS`. Fixed by
  correcting the declaration, not by adding data to make the number come
  out right.
- **A dataset can lose D2 coverage as well as gain it.** The first version
  resolved 3 in-house surfaces and un-resolved 4 checked-out ones, because
  `builder.strip()` replaces the transactional layer rather than adding to
  it. The narrative now carries a departed stay as well: measured, +3 / −1.
- **D6 cannot declare a D2 outcome at all.** `Expectations` has no element
  for it and `Layer.D2_GOLDEN` is dead vocabulary. The dataset's main
  purpose is the one thing the registry cannot check.

### Wave 0.6 — the four instructed pieces (accepted)

Wave 0.5 and D6 Step 2 were accepted 2026-08-08. The four follow-on
instructions:

| | Commit | State |
|---|---|---|
| **R-4** — `INV-D07`, orphan overpayment records | `fdb992b` | COMMISSIONED, 8/8 elements plus null and write controls. Registry 24 → 25, HOLDS 14 → 15 |
| **R-5** — materiality proposal | `3254d59` | **Written. Awaiting owner approval. No policy changed, no constant moved** |
| D6 re-sequencing | `eead335` | `DS-ACT-GROUP` now precedes `DS-ACT-OVERPAY` |
| Coverage ledger | `6beb1a7` | `ds-coverage` command, itself commissioned. `DS-ACT-INHOUSE` backfilled |

What the coverage ledger found on its first real measurement: **eight
invariants lose their population** on `DS-ACT-INHOUSE` — `INV-A03`,
`B01`, `B02`, `B03`, `B05`, `C01`, `C05`, `D07`. The earlier `+3 / −1`
figure covered D2 surfaces only. It was right about surfaces and silent
about invariants, and the dataset covers substantially less of the
invariant registry than production does.

### Wave 0.7 — `INV-D02` activated

The owner re-sequenced again, on a stated principle worth keeping:
**a regression dataset should activate the highest-risk verification
before extending ordinary business coverage, because Wave 0's objective is
verification completeness rather than business-feature completeness.**

| | Commit | State |
|---|---|---|
| **R-7** — probes must sign corrections and reversals | `6653f15` | Commissioned in both directions, 19 checks |
| **`DS-ACT-CORRECTION@1.0`** | `1254eab` | COMMISSIONED 6/6. **`INV-D02` activated**, population 0 → 4. Ledger `AS_DECLARED` |

**`INV-D02` was the only VACUOUS invariant that was RELEASE_BLOCKING. It is
now exercised by a commissioned dataset.** The three that remain
(`INV-A06`, `INV-C06`, `INV-D05`) are all certification-blocking.

Two things it found:

- **R-7.** `financials.py` summed `amount` unsigned, so a reversal was
  added where it must be subtracted — wrong by twice the reversed amount.
  On this dataset the pre-R-7 probes read `outstanding = −3,072.00` against
  a truth of `0.00`. Invisible on production for exactly the reason the
  dataset exists: no correction rows, which is the same sentence as
  "`INV-D02` is VACUOUS".
- **A production defect, reported and not repaired.**
  `gst_service.compute_stay_gst` reads extra charges unsigned
  (`gst_service.py:492`) and therefore **taxes reversed money** — ₹180.00
  of GST on a ₹500 charge that was taken back, compounding with each
  further correction, inherited by checkout, the invoice and every report
  downstream of `calculate_stay_amount`. `INV-C02` is declared VIOLATED by
  exactly that amount. First identified instance of a class already on the
  register. See `D6_DS_ACT_CORRECTION.md` §4.

### `DS-ACT-VOIDCN` — `INV-D05` activated, `Q11` lifted (`7da7740`)

Taken ahead of `DS-ACT-GROUP` on the owner's activation-first principle and
on evidence gathered before writing: it activates `INV-D05`
(certification-blocking) **and** lifts `Q11` (D1, severity BLOCK), while
`DS-ACT-GROUP` activates nothing at all.

**Two more production findings, both reported and not repaired:**

- **Every cancellation refund violates `INV-D02`.**
  `post_cancellation_disposition` sets `is_reversal=True` and never sets
  `corrects_id`; the only four assignments in `services.py` are inside the
  two correction functions. `INV-D02` is CRITICAL and RELEASE_BLOCKING.
  Derived from source before the dataset was written, then confirmed.
- **The night audit reports voided payments as refunds.** `Q11` went
  VACUOUS → DIVERGED on first exposure: ₹1,286.00 of voided payments
  counted as refunds against ₹236.00 of true refunds. A voided payment
  never left the bank; a refund did.

**Candidate R-8, recorded not fixed:** no probe nets credit notes against
the balance. `outstanding − credit_note_total` is the true receivable and
nothing computes it. A *missing* quantity rather than a *wrong* one, so it
bakes no error into the baseline.

### Two of four VACUOUS invariants are closed. Both that remain are blocked on a decision

| | Blocked on |
|---|---|
| `INV-A06` | **R-5** — governance, awaiting approval |
| `INV-C06` | **the `companies` / `content_hash` question**, below |

`companies` is a PRESERVED master table and `builder.content_hash` covers
only the transactional and guest tables. A dataset declaring a company
would carry master data **not part of its own identity**. The exclusion is
deliberate but was reasoned about master data *inherited* from production,
not master data a dataset *declares*. **`DS-ACT-CORPCREDIT` cannot be
written until this is decided**, and it was not started.

### Wave 0.8 — verification enhancements, then the last non-blocked dataset

| | Commit | State |
|---|---|---|
| **R-8** — `net_receivable` | `e1438a0` | `outstanding` less credit notes. Verification layer only |
| Ledger measures **D1** | `afe4088` | And corrected my own record: it already measured D2 |
| **D2 declarable** | `570561e` | `Expectations.golden`. `Layer.D2_GOLDEN` was dead vocabulary since Step 1 |
| Ledger **mandatory** | `1117e33` | `datasets_without_coverage_ledger()`, a check rather than a convention |
| **`DS-ACT-GROUP@1.0`** | `b7290f7` | COMMISSIONED. The last non-blocked dataset |

**Extending the ledger to D1 immediately found five movements nobody had
recorded** — and three of them matter:

- **`Q09`, `Q02`, `Q07` read AGREED on production and their agreement
  proves nothing.** All three diverge the moment a correction or reversal
  exists, and production has neither. `Q09` is *Payments total (signed vs
  raw)* — the D1 quantity measuring exactly the defect class R-7 fixed in
  the probes, and it had never been able to fire.
- `Q15` falls to VACUOUS on all four datasets; none declares a night audit.
- `Q11` is now confirmed mechanically instead of by hand.

### `DS-ACT-GROUP` found two things

- **The application has no master-account routing.**
  `group_blocks.billing_instructions` is free text, `services_group_stay`
  only links reservations to rooms, and nothing moves one reservation's
  charges onto another's folio. Billing a real group to a master account
  would have every non-master reservation reported by `INV-C02`.
- A group block has its own status vocabulary; the builder named the
  constraint rather than surfacing an opaque `IntegrityError` — the
  failure mode it was written after (`FLT-A10`), working.

### `DS-ACT-SHIFT` — `Q21` activated (`32e8b60`)

The last VACUOUS parity quantity any planned dataset could reach. One
shift, opened with a float, one cash settlement inside the window, petty
cash out, drawer counted and balanced.

The perturbation changes the payout without touching the stored
`expected_cash`: every financial probe and the declared closing figure are
unchanged and only the recomputation moves — the failure `Q21` exists to
catch, a till that balances on paper because the expected figure was
written down once and never recomputed.

**The ledger settled something nobody had.** The prediction named `Q18` and
`Q20` as its weak points and got them wrong — it reasoned they track
occupancy. Five datasets falsify that:

| dataset | rooms | extras | `Q18`/`Q20` → AGREED |
|---|---|---|---|
| `DS-ACT-INHOUSE` | 2 | no | **yes** |
| `DS-ACT-SHIFT` | 1 | no | **yes** |
| `DS-ACT-CORRECTION` | 1 | yes | no |
| `DS-ACT-VOIDCN` | 1 | yes | no |
| `DS-ACT-GROUP` | 2 | yes | no |

Occupancy does not predict it; **extra charges predict it exactly**. The
dashboard tiles and the ADR/RevPAR definitions agree on a room-only hotel
and disagree the moment an extra charge exists — a long-standing production
DIVERGED narrowed to its cause, by the ledger rather than by reading.

---

## 7a. Every unblocked dataset is written. What remains needs a decision.

Five datasets, all commissioned, all with a passing coverage ledger. Of the
empty populations D6 exists to close:

| | State |
|---|---|
| `INV-D02` corrections | **closed** — `DS-ACT-CORRECTION` |
| `INV-D05` voids / credit notes | **closed** — `DS-ACT-VOIDCN` |
| `Q11` refunds vs voids | **closed** — `DS-ACT-VOIDCN` |
| `Q21` shift cash | **closed** — `DS-ACT-SHIFT` |
| 3 in-house D2 surfaces | **closed** — `DS-ACT-INHOUSE` |
| `groups.detail` | **closed** — `DS-ACT-GROUP` |
| **`INV-A06`** overpayment | **blocked — R-5**, governance, awaiting approval |
| **`INV-C06`** corporate credit | **blocked — the `companies` / `content_hash` question** |

### The two decisions, stated so they can be taken

**R-5 — the ₹1.00 materiality threshold.** Proposal written and awaiting
approval: `D5_5_R5_MATERIALITY_PROPOSAL.md`. Three options costed against
measured data; recommended (c), lower to the rounding floor and state it in
the business rule, with the counter-argument stated.

**The master-data identity question.** `companies` is a PRESERVED table and
`builder.content_hash` covers only the transactional and guest tables, so a
dataset declaring a company would carry master data **outside its own
identity** — `strip()` never clears it, and the hash a certificate is
issued against would not cover it. The exclusion is deliberate and well
argued, but it was reasoned about master data *inherited* from production,
not master data a dataset *declares*. Until it is settled,
`DS-ACT-CORPCREDIT` cannot be written and `INV-C06` cannot be activated.

**Beyond those two, D6 Step 2 has nothing left that engineering can
unblock.** The next deliverables are D7–D10, and D9 remains blocked on its
own schema exception.

---

## 7b. Wave 1 Readiness Review — the gate, 2026-08-08

`WAVE1_BLUEPRINT.md`. **No production code was written and none may be
until the gate in its §9 is passed.**

**Verdict: Wave 0 is engineering-complete for diagnosis and for silent
remediation; it is NOT complete as chartered.** D7, D8 and D10 do not
exist and D9 is blocked, but they bite differently — D9 blocks material
work because rollback of a data migration is an unproven restore; D7 and
D10 block the *claim*, not the work; D8 blocks nothing but human error.

**The silence census** (`evidence/20260808_wave1_silence_census/`) is the
one new piece of analysis, and it reorders the backlog: **13 of 21 defects
have no live population**, so a fix can be shipped and *proved* neutral.
Silent work goes first and needs no deliverable Wave 0 has not built.

**Three findings changed the original ordering:**

- **The folio backfill moves no money total.** `folio_id` appears zero
  times in the financial probes; it moves `Q14`, `INV-A02`, `INV-A03` and
  nothing else. Its ₹40,374.14 headline reads like a large restatement
  and it is not one — promoted from late to third.
- **The ADR/RevPAR fix is not "add a date parameter".** The coverage
  ledger established `Q18`/`Q20` diverge on **extra charges**, not
  occupancy. Date-scoping alone would have left them DIVERGED.
- **The night-audit fix must not be bundled with the folio fix.**
  `INV-B03` is the sole invariant enforcing P4 **and has a demonstrated
  detection gap** (`FLT-D03`). Shipping a closed-period change behind a
  control known not to fire is the sequencing error most worth avoiding.

**Three releases permanently change historical accounting** and need
written management or auditor approval: the closed-period recomputation,
the ₹7,977.92 OTA reclassification, and the double-sold room night. The
other four explicitly do **not**, and should not be routed through an
approval they do not need.

**Four items are NOT ready** and are excluded from every release until
they pass the six criteria: the `tax_lines` reversal schema gap, absent
master-account routing, the negative-receivable judgement, and invoice
number uniqueness — which needs a D4 invariant declared and commissioned
**before** its fix, or the fix ships with nothing able to prove it worked.

### The next piece of work

**Not production code.** Either:

1. **D9**, which unblocks everything material — and needs the recorded
   schema exception for a `backup_logs` checksum column; or
2. **W1-R1 / W1-R2**, the two silent releases, which need no further
   deliverable and are gated by what Wave 0 already provides; or
3. the two open decisions — **R-5**, and the master-data identity
   question.

Nothing else in the backlog can start.

**Closed since:** the coverage ledger now measures **D1 as well as D2 and
D4**. `DS-ACT-VOIDCN`'s `Q11` claim is mechanical rather than hand-measured.

*Correction to the line that stood here:* it said the ledger measured
neither D1 nor D2. The D2 half was wrong — it has measured golden-master
surfaces since it was built, and `DS-ACT-INHOUSE`'s backfill pack shows it
reporting three surfaces added. Only D1 was missing.

In this order, and the order is the point:

1. declare `coverage_expectation` **before** the dataset is built — the
   ledger cannot catch anything if the declaration follows the measurement;
2. `ds-commission` passes all six elements;
3. `ds-coverage --id DS-ACT-GROUP --tag <tag>` exits 0;
4. the ledger appears in its completion record.

**It activates no invariant.** Nothing in D1, D4 or D5 references
`group_blocks`, so it is a D2-coverage dataset and its record must say so
rather than let the `DS-ACT-` prefix imply otherwise. See
`D6_SEQUENCING_DECISION.md` §3 — that prefix is wrong for this dataset and
for `DS-ACT-INHOUSE`, and neither `datasets_core` nor `datasets_activation`
has a category for a dataset that exists to give a golden-master resolver
an entity to pin to.

**`DS-ACT-OVERPAY` is blocked on R-5** and stays blocked until the owner
answers. The threshold determines what the dataset must contain to enter
`INV-A06`'s population; declaring expectations against an unsettled policy
is the mistake the D5.5 probe remediation existed to prevent.

Then `DS-ACT-CORPCREDIT` (closes 2 more D2 surfaces), `DS-ACT-CORRECTION`,
`DS-ACT-VOIDCN`, `DS-ACT-SHIFT`. One dataset at a time, each commissioned
before the next. **Do not write five datasets and then try to commission
them** — the gate is the part most likely to reveal that a declaration was
wrong, and on the first dataset it was.

**That flag was taken up.** `INV-D02` was the only VACUOUS invariant that
was `RELEASE_BLOCKING`, and the owner re-sequenced `DS-ACT-CORRECTION`
ahead of everything on the principle recorded above. It is now
commissioned and `INV-D02` is activated. The three VACUOUS invariants that
remain are all certification-blocking.

### Decisions waiting on the project owner

**R-5 now blocks work.** The others do not.

1. **P15.** `CONSTITUTION.md` documents P1–P14, recovered from the
   enforcing registry. The charter says P1–P15 and names *"Independent
   evidence"*. No P15 exists in code. Its wording is not recoverable and
   was not invented. See `CONSTITUTION.md` §3.1.
2. **R-5 — the ₹1.00 materiality threshold.** **Proposal written and
   awaiting approval: `D5_5_R5_MATERIALITY_PROPOSAL.md`.** Three options
   costed against measured data. Recommended: lower to the rounding floor
   and state it in the business rule, on coverage grounds — with the
   counter-argument stated, since it makes every rounding paisa a tracked
   item and nobody has sized that at real occupancy.

   Measured: **all 28 reservations, 2 in credit, both ₹0.15, both below the
   threshold.** Every overpayment this hotel has ever recorded is in the
   unmeasured band, so `INV-A06`'s coverage on real data is zero and always
   has been. Since R-4 the threshold is also declared in two places, which
   is a P1 defect held open deliberately until this is answered.

   **Blocks `DS-ACT-OVERPAY` and the collapse of the duplicate constant.
   Nothing else.**
3. **Private remote.** Not configured; no `gh` CLI on this machine.
   Operational, explicitly not an engineering gate. Bundles in
   `../repo-backups/` are the interim protection.
4. **D9's schema exception.** `backup_logs` has no checksum column. D9
   cannot start without a production schema change that Wave 0 forbids.

### Protection in place

- `../repo-backups/*.bundle` — verified by restore into a fresh directory:
  identical tree hash, all tags, 713 files, `fsck` clean.
- `../db-backups/pms_20260807_223539_wave0.5-frozen.db` + manifest —
  verified read-only snapshot, `integrity_check ok`, row counts matched
  across 53 tables. Interim until D9. Regenerate with
  `python tools/backup_db.py --label <name>`.

Both live on the same disk as the repository. Getting one copy off this
machine is the outstanding operational risk.
