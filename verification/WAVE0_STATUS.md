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
| D6 | Regression Dataset Framework | **Partial — non-functional** | — |
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

## 3. D6 — Regression Dataset Framework: partial, and currently broken

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
| `model.py`, `registry.py`, `schema.py`, `builder.py`, `financials.py`, `evaluate.py` | present |
| `datasets_core.py`, `datasets_activation.py` | **absent — registry raises** |
| `__init__.py` | absent (implicit namespace package only) |
| `commission.py` — the discrimination gate | absent |
| `report.py` | absent |
| CLI wiring in `__main__.py` | absent |

The scaffold is well-formed and its reasoning is sound. What is missing is
the declarations and the gate.

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
| Phase 1 Architecture Audit | **Absent** |
| Phase 2 Financial Truth Certification | **Absent** |
| Phase 2.5 Migration Blueprint | **Absent** |
| Phase 2.6 source (Constitution / PVF / Governance) | **Absent** — cited throughout, including §10 and §13 which this framework defers to |

The framework defers to Phase 2.6 sections that nobody can currently read.
Recovering those documents is not optional work.

---

## 7. Recommended next target

**Complete D6.** It is already started, it is the declared next step in
`D5_COMPLETION_REPORT.md`, and it is the single unblocker for the largest
cluster of open findings — every VACUOUS item in §4.1, and D3's
single-closed-day limitation.

Scope, following the pattern D4 and D5 established:

1. `datasets/__init__.py`
2. `datasets_core.py` — baseline narratives; makes `load_all()` resolve
3. `datasets_activation.py` — datasets targeting the four VACUOUS
   invariants and quantities `Q11`/`Q21`, plus an in-house checked-in
   reservation to resolve D2's four UNRESOLVED surfaces
4. `commission.py` — the discrimination gate: perturb each dataset and
   require the declared expectations to break. A dataset that survives its
   own perturbation is NOT COMMISSIONED and excluded from certification
5. `report.py` and CLI wiring (`ds-registry`, `ds-build`, `ds-run`,
   `ds-commission`)
