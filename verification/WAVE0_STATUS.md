# Wave 0 — Deliverable Status

DSBC Frontline v2.2.18. Last verified 2026-08-07 (Wave 0.5).

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
| D4 | Financial Invariant Engine | Complete | 26 / 26 |
| D5 | Fault Injection Platform | Complete | 37 / 37 |
| D6 | Regression Dataset Framework | **Step 1 complete + probe remediation; no datasets declared** | — |
| D7 | Certification Engine | Not started | — |
| D8 | CI/CD Verification Pipeline | Not started | — |
| D9 | Backup Restore Verification | **Blocked** | — |
| D10 | Release Gate Framework | Not started | — |

Live registry counts, 2026-08-07:

| Artefact | Count |
|---|---|
| Parity quantities (D1) | 22 — `Q01`–`Q22` |
| Invariants (D4) | 24 — 6 each in classes A/B/C/D, **all 24 COMMISSIONED** |
| Faults (D5) | 40 — 10 each in classes A/B/C/D; 36 COMMISSIONED, 4 UNCOVERED |
| Golden master surfaces (D2) | 158 |
| Replayed business dates (D3) | 28 |
| Retained evidence packs | 80 |
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

**D4 — Financial Invariant Engine.** 24 declared invariants, every one
commissioned across eight elements. Zero writes is measured, not assumed.

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
| `Q11` refunds/voids | D1 | VACUOUS — no production rows |
| `Q21` shift cash and variance | D1 | VACUOUS — no shifts |
| Overpayment recording | D4 | VACUOUS — commissioned, never exercised |
| Corporate credit backing | D4 | VACUOUS |
| Correction/reversal traceability | D4 | VACUOUS |
| Void/credit-note traceability | D4 | VACUOUS |
| 4 golden master surfaces | D2 | UNRESOLVED — no checked-in reservation to pin them to |

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

---

## 5. Blockers on Wave 1

1. **D6–D10 do not exist.** Wave 1 is gated on all ten.
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
   population. This is the argument for D6.
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
| `D1`–`D5` completion reports | Pre-existing, retained |
| `D5_5_REMEDIATION_APPLIED.md` | Written 2026-08-08; records R-1/R-2/R-3/R-6 and four errors found in the D5.5 documents |
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

### The next piece of work

**D6 Step 2.** Cheapest dataset first: `DS-ACT-INHOUSE` (resolves D2's four
UNRESOLVED surfaces and costs almost nothing), then `DS-ACT-OVERPAY`, then
the rest. One dataset at a time, each commissioned before the next.
**Do not write six datasets and then try to commission them** — the gate
is the part most likely to reveal that a declaration was wrong.

**R-4 must land before `DS-ACT-OVERPAY`,** not before `DS-ACT-INHOUSE`. It
is a full Class D invariant declaration with a commissioning obligation —
treat it as D4 work. `DS-ACT-OVERPAY` also needs the R-5 decision below.

### Decisions waiting on the project owner

These block nothing mechanical, but three of them affect correctness of
work not yet done.

1. **P15.** `CONSTITUTION.md` documents P1–P14, recovered from the
   enforcing registry. The charter says P1–P15 and names *"Independent
   evidence"*. No P15 exists in code. Its wording is not recoverable and
   was not invented. See `CONSTITUTION.md` §3.1.
2. **R-5 — the ₹1.00 materiality threshold** in `INV-A06`. Currently an
   implicit constant. Either state it in the invariant's business rule, or
   add a second invariant that aggregates sub-rupee overpayments. Affects
   how `DS-ACT-OVERPAY` is declared.
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
