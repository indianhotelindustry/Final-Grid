# Production Verification Framework — Wave 0

Measurement instrumentation for DSBC Frontline. **Contains no production
code and is never imported by the application.**

Governing documents: Phase 1 (Architecture Audit), Phase 2 (Financial Truth
Certification), Phase 2.5 (Engineering Blueprint), Phase 2.6 (Financial
Constitution & PVF).

---

## Status

| # | Deliverable | Status |
|---|---|---|
| D1 | Financial Parity Harness | **Complete — commissioned 8/8** |
| D2 | Golden Master Framework | **Complete — commissioned 16/16** |
| D3 | Historical Replay Framework | **Complete — commissioned 21/21** |
| D4 | Financial Invariant Engine | **Complete — commissioned 26/26** |
| D5 | Fault Injection Framework | **Complete — commissioned 37/37** |
| D6 | Regression Dataset Framework | Not started |
| D7 | Certification Engine | Not started |
| D8 | CI/CD Verification Pipeline | Not started |
| D9 | Backup Restore Verification | Not started |
| D10 | Release Gate Framework | Not started |

Wave 1 may not begin until all ten are complete and commissioned.

---

## Safety guarantees

1. **Production is never opened writable.** Every run works on a
   disposable copy produced through SQLite's backup API with the source
   connection opened `mode=ro`.
2. **The guarantee is proven, not asserted.** The production file is
   SHA-256 fingerprinted before the copy and re-verified at the end of
   every run. A mismatch raises `ProductionWriteDetected` and the run's
   results are discarded.
3. **The application is only ever bound to the copy.** `create_app()`
   writes — legacy migrations, the SQLite column fixer and `init_data()`
   all commit. The copy absorbs those writes.

Two application helpers are deliberately **not** used, because they write:

- `gst_service.get_folio_gst_summary()` → calls `ensure_all_tax_lines()`
  which commits (`app/gst_service.py:590`). TaxLine rows are queried
  directly instead.
- `services.run_night_audit()` → posts charges and advances the business
  date. The read-only `NightAuditService` report builder is used instead.

---

## Commands

```bash
# Prove the read-only guarantee, run nothing else
python -m verification selfcheck

# Cross-implementation parity run (the baseline measurement)
python -m verification run --tag some_label

# Capture a baseline for later before/after comparison
python -m verification baseline --tag v2.2.18_preWave1

# Re-measure and diff against a stored baseline  (Wave 1+ release gate)
python -m verification compare --tag v2.2.18_preWave1

# Seeded-fault commissioning — proves the harness can detect
python -m verification commission
```

### D2 — Golden Master Framework

```bash
# Capture golden masters for every catalogued surface
python -m verification gm-capture --tag production

# Capture and report WITHOUT writing masters (inspection only)
python -m verification gm-capture --tag production --dry-run

# Re-render every surface and diff against the stored masters
python -m verification gm-verify --tag production

# Seeded-fault commissioning of the golden master framework
python -m verification gm-commission
```

`gm-verify` exit codes: `0` PASS, `1` FAIL (a blocking difference),
`2` WARN (differences, none blocking), `4` UNVERIFIED (read-only
guarantee not established).

### D3 — Historical Replay Framework

```bash
# Replay every historical business date and reconcile it three ways
python -m verification replay --tag production

# Replay and report WITHOUT storing the result (inspection only)
python -m verification replay --tag production --dry-run

# Narrow the window
python -m verification replay --from 2026-05-01 --to 2026-05-28

# Skip the reverse-order pass. Halves the runtime and is REPORTED as
# not run, because the risk it measures is then unmeasured.
python -m verification replay --fast

# Re-replay and diff against the stored replay  (the release gate)
python -m verification replay-verify --tag production

# Seeded-fault commissioning of the replay framework
python -m verification replay-commission
```

`replay-verify` exit codes: `0` PASS, `1` FAIL (a blocking difference),
`2` WARN, `4` UNVERIFIED.

**What a replay compares.** For every business date from the first of the
month of the first activity to the current business date:

| Account | Produced by | Answers |
|---|---|---|
| LEDGER | this package, plain SQL, no application code | what is in the books |
| ENGINE | the application's date-parameterised helpers and the read-only `NightAuditService`, clock frozen to noon on that date | what the application says |
| RECORDED | the `NightAuditLog` row and its `snapshot_json` | what the system froze at close |

LEDGER against ENGINE is checked by 20 **declared** reconciliations
(`verification/replay/reconcile.py`). ENGINE against RECORDED is
`HISTORY DRIFT`. Every past date is additionally replayed with the clock
frozen to *today*; anything that moves is `ASAT DRIFT` — a present-tense
query inside a historical report.

**Severity in `replay-verify` follows the state of the day.** A closed
day may not move at all (BLOCK); a past day that was never closed may
move but is reported (WARN); the current business date is expected to
move (INFO). A gate that failed every day the hotel traded would be
switched off within a week.

### D4 — Financial Invariant Engine

```bash
# The registry, the matrices and the constitutional coverage.
# Touches no database.
python -m verification inv-registry

# Evaluate every invariant against a disposable copy of production
python -m verification inv-run --tag production

# Scope it
python -m verification inv-run --mode BUSINESS_DATE --date 2026-05-27
python -m verification inv-run --mode SINGLE_RESERVATION --reservation 7
python -m verification inv-run --id INV-A02 --id INV-C01

# Was it true then? Is it still true today? Where did it first break?
python -m verification inv-history --tag production

# Commission every invariant: eight elements each, with fault injection
python -m verification inv-commission
```

**An invariant is a declaration, not an assertion.** Each carries its
business purpose, business rule, severity, blocking level, data sources,
canonical engine, validation method, evidence produced, failure message,
likely root causes, suggested investigation, applicable releases and
dates, and its commissioning status. Registration **refuses** a
declaration with an empty required field, an unknown vocabulary value, or
no stated way to make it fail.

**Adding an invariant** is one `@invariant(...)` declaration in
`verification/invariants/rules_{a,b,c,d}.py`. Nothing else changes. Per
the standing rule, any future financial feature, report, night-audit
change or accounting change must register its invariants before
implementation is permitted.

| Class | Concern | Count |
|---|---|---|
| A — Accounting | the books add up | 6 |
| B — Temporal | closed periods, snapshots, one business date | 6 |
| C — Domain | the hotel's own rules | 6 |
| D — Referential | every financial fact has an origin | 6 |

**The commissioning gate.** An invariant that has never been shown to
fail is not a control (P9). Its result is reported but **excluded from
every verdict** until commissioning demonstrates the failure across all
eight elements: positive case, negative case, fault injection, detection,
evidence, repeatability, determinism, order independence. A declaration
claiming `COMMISSIONED` is cross-checked against the most recent
commissioning evidence pack; an unbacked claim makes the whole run
`UNVERIFIED`.

**Zero writes is measured, not assumed.** Every statement issued on the
raw connection and by SQLAlchemy is counted and classified. One write
anywhere fails the run, whatever the invariants reported.

### D5 — Fault Injection Framework

```bash
# The fault taxonomy and its matrices. Touches no database.
python -m verification fault-registry

# Inject every fault into a private copy and sweep every layer
python -m verification fault-run --tag production

# Scope it
python -m verification fault-run --category C-ENGINE
python -m verification fault-run --id FLT-A01 --id FLT-B03
python -m verification fault-run --layer D4_INVARIANTS   # cheap, one probe

# Run probes one at a time instead of concurrently (diagnostics)
python -m verification fault-run --serial

# Commission every fault (nine elements each) and self-verify the platform
python -m verification fault-commission
```

**D5 asks a question the other four cannot.** D1–D4 each prove that *that
layer* detects the defects *that layer* was written to detect. D5 injects
one defect and asks all four at once: which noticed, which stayed silent,
and did the one that noticed name the right cause?

**Every layer is swept, including the ones expected to stay silent.**
Sweeping only the declared layers would make the platform incapable of
its most useful output. A framework where every layer moves for every
fault has detected nothing — it has only proved it is sensitive to change.

| Result | Meaning |
|---|---|
| `ATTRIBUTED` | expected, moved, and moved at the declared target |
| `UNATTRIBUTED` | expected, moved, but not where declared — a disturbance felt, not a defect identified |
| `MISSED` | expected, silent. **The finding this deliverable exists to produce** |
| `UNEXPECTED` | undeclared layer moved. Blast radius, recorded, never a pass |
| `CORRECTLY_SILENT` | undeclared layer stayed silent. A real result — it is what makes attribution possible |

| Class | Concern | Count |
|---|---|---|
| A — Business | what a hotel can genuinely do wrong | 10 |
| B — Data | the record itself is malformed | 10 |
| C — Engine | the data is right and the code is wrong | 10 |
| D — Operational | the money is right and the environment is wrong | 10 |

**Five injection methods**, because a defect can enter a financial system
in five places and only one of them is the database: `SQL`,
`ENGINE_PATCH` (a wrapper installed inside one throwaway probe
subprocess — the only way to express "this function now double-counts"),
`CLOCK_SHIFT`, `ENV` and `FILE` (always on a copy taken into the arena
first).

**A zero-change injection is refused.** An injection that ran cleanly and
altered nothing produces "not detected", which reads as a defect in the
framework rather than in the seed. Rowcount is asserted every time.

**Isolation is verified after every single fault, not once per run**, so
a breach can be attributed to the injection that caused it. Each fault
gets a private copy derived from a pristine baseline, never from the
previous fault's copy, and the baseline is re-hashed after every
injection.

**Adding a fault** is one `@fault(...)` declaration in
`verification/faults/faults_{a,b,c,d}.py`. No pipeline change, no dispatch
table, no classifier edit. Registration **refuses** a fault that expects
no layer to detect it without saying why — a fault nothing detects is
either a mistake or a verification gap, and the platform will not guess
which.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | PASS |
| 1 | FAIL — a blocking divergence, or drift against baseline |
| 2 | INCOMPLETE — quantities not implemented, or vacuous |
| 3 | ERROR — a measurement raised |
| 4 | UNVERIFIED — read-only guarantee not established |

---

## Verdict vocabulary

| Verdict | Meaning |
|---|---|
| `AGREED` | All implementations agree within the variance policy |
| `SINGLE_SOURCE` | Only one implementation exists; value recorded as evidence |
| `DIVERGED` | Implementations disagree — the finding the harness exists to produce |
| `VACUOUS` | Implementations agreed, but over an **empty population**, so the agreement proves nothing (Principle 10) |
| `NOT_IMPLEMENTED` | Declared but not yet measured — never counted as agreement |
| `ERROR` | The measurement raised |

`VACUOUS` exists because two implementations of shift cash both returning
zero when there are no shifts have not been shown to agree about anything.
Reporting that as `AGREED` would make the harness the very kind of control
that cannot fail.

---

## Operating model for a migration

1. **Declare first.** Before the change, state for each quantity: unchanged,
   or changed by a stated amount with a stated cause.
2. **Capture a baseline** on the current code.
3. **Make the change.**
4. **Compare.** A value that moved when it should have held is a failure —
   and so is a value that held when it should have moved, because that
   means the change did not take effect.
5. **Retain the evidence pack** as release evidence (Phase 2.6 §13).

---

## Artifacts

```
verification/
  _work/       disposable database copies (safe to delete at any time)
  evidence/    timestamped evidence packs: result.json + report.txt
  baselines/   named baselines for D1 compare mode
  masters/     golden master sets for D2 (index.json + surfaces/*.json)
  ledgers/     stored replays for D3 (index.json + dates/*.json)
  golden/      D2 source: freeze, catalogue, client, normalize, capture,
               compare, commission, report, surfaces
  replay/      D3 source: timeline, ledger, engines, recorded, reconcile,
               replay, compare, commission, report
  invariants/  D4 source: model, registry, context, engine, helpers,
               rules_a..d, history, commission, report
  faults/      D5 source: model, registry, isolation, injection,
               detectors, pipeline, faults_a..d, commission, report
  _work/fip_arena/   per-fault disposable copies. Empty between runs; a
               file left here after a run is a cleanup failure and the
               run reports it
```

`_work/` is disposable. `evidence/` and `baselines/` are retained; per
Phase 2.6 §10 evidence proving the application's correctness should
ultimately be exported outside the application, which the release process
is responsible for.

---

## Rollback

This deliverable adds files and touches nothing else.

```bash
rm -rf verification/
```

That is the complete rollback. No production file, database row, schema
object, configuration value or dependency was modified. The application
does not import this package and is unaffected by its presence or absence.

To roll back while retaining the evidence, move `verification/evidence/`
and `verification/baselines/` elsewhere first.

---

## Known limitations

- **Q11 and Q21 are `VACUOUS`.** Refund/void and shift/cash have no
  production data. They need regression datasets (D6).
- **Fourteen quantities cannot be commissioned by data mutation.** The
  reasons are recorded in `evidence/*_commission/commission.json`. Some
  are already diverging on live data; others have two named
  implementations that are structurally the same code, so their agreement
  is tautological. That distinction is itself a finding.
- **Evidence is stored inside the project.** Phase 2.6 §10 requires
  certification evidence to live outside the application. Export is a
  release-process responsibility and is not automated here.

### D2-specific limitations

- **The golden master is captured as one identity — the lowest-id active
  Admin.** It therefore verifies *what a page renders*, not *who may see
  it*, except through the anonymous-status check taken alongside every
  surface. A full role-by-role authorisation matrix is not a Wave 0
  deliverable and is not covered.
- **Seven surfaces return HTTP 500 and are captured as such.** A master
  over a 500 records a defect; it is not evidence of correctness. They
  are listed on every capture report under UNHEALTHY SURFACES.
- **Four surfaces are UNRESOLVED** because the dataset contains no
  checked-in reservation to pin them to. They are reported as declared
  gaps on every run and will resolve once D6 supplies an in-house
  regression dataset.
- **The clock is frozen to noon on the business date.** Any behaviour
  that depends on a different time of day — a night-audit window, an
  early-morning shift rule — is not exercised by the masters.

### D3-specific limitations

- **The dataset has one closed business day.** The comparison against
  what the system froze at close is therefore exercised on a single
  date. It found a defect there, but one date is not a demonstration
  that the control scales.
- **As-at drift reports nothing on this dataset.** The control is proven
  live by commissioning (`S-RP-ASAT`) rather than by a live finding. On
  a dataset whose room statuses and credit balances have moved further
  from history, it should have more to say.
- **Twenty declared reconciliations cover 20 of roughly 220 engine
  figures per date.** The uncovered ones are captured and compared
  between runs but are not checked against the primary record. They are
  listed in full on every run rather than left implicit.
- **The ledger is not a second implementation of financial policy.** It
  states what is in the books, sliced to mirror the application's own
  filters. Where a reconciliation fails it says the two disagree; it does
  not say which is right.

### D4-specific limitations

- **Four invariants are VACUOUS on this dataset.** Overpayments,
  corporate credit, corrections/reversals and voids/credit notes have no
  live rows, so those rules were not exercised. They are commissioned —
  a seeded fault makes each fail — but a commissioned rule over an empty
  population still proves nothing about the data (P10). They need
  regression datasets (D6).
- **P2 and P4 are enforced only indirectly.** `INV-B01`, `INV-B02` and
  `INV-B03` cover frozen-value immutability and the night audit's
  orchestration role as a side effect of what they measure; neither
  principle has an invariant written specifically for it.
- **Historical replay cannot restore historical data.** There is no
  archive of the database as it was. `inv-history` evaluates each past
  date under two clocks against current data, which measures
  clock-dependence; genuine historical state exists only in the frozen
  night-audit snapshots, and `INV-B03` is the invariant that uses them.
- **The engine reads; it never repairs.** Every finding below is
  recorded, attributed and costed. Nothing is fixed, per the standing
  Wave 0 instruction.

### D5-specific limitations

- **Two declared layers stay silent where they should speak.** `INV-B03`
  does not move when an audited day's stored close total is rewritten
  (FLT-D03, CRITICAL); D3's `RC07` does not move for a guest checked out
  with an unexplained balance, though the day totals do (FLT-A09, HIGH).
  Both defects are caught by other layers, so neither is invisible — but
  the control that should name them does not.
- **Four faults nothing in the framework can detect.** Registered so the
  gaps are tracked, never injected, never counted as passes: invoice
  number uniqueness (needs a D4 invariant), backup corruption and restore
  mismatch (need D9, and `backup_logs` has no checksum column to build
  on), and environment drift (needs a D7 environment fingerprint).
  **The system currently cannot tell whether its backups are restorable.**
- **D2_GOLDEN is a change detector, not an attributor.** It moved for 31
  of 36 injected faults while being the declared detector for 3. A golden
  master diff says something changed; it does not say what. D2 must never
  be the sole evidence that a change was safe.
- **`ENGINE_PATCH` cannot reach a callable bound at import time under a
  different name.** FLT-C01 declares this explicitly rather than dropping
  the expectation: D1's Q16 and Q18 reach `get_cash_revenue` through the
  `get_daily_revenue` alias, which a wrapper on the canonical name does
  not cover.
- **Three D4 invariants are challenged by no D5 fault.** Not unverified —
  each was commissioned by its own negative seed — but singly verified.
- **`fault-run` reports INCOMPLETE, not PASS, and will until D7 and D9
  exist.** Every injected fault was detected and every commissioning
  claim is backed, but two layers have gaps and four faults are
  undetectable. Reporting PASS would make this the kind of control that
  cannot fail.
- **The platform injects; it never repairs.** Per the standing Wave 0
  instruction, nothing found here is fixed.
