# Wave 0 — Deliverable D5: Fault Injection Framework
## Completion Report

**Status:** Complete.
**Package:** `verification/faults/`
**Production code changed:** none. Zero lines under `app/`.
**Database impact:** none. No schema object, row, index or migration.

---

## 1. Technical design

### 1.1 The question D1–D4 cannot answer

Each of the first four deliverables carries its own seeded-fault suite,
and each was written to prove that *that layer* works. D1 proves the
parity harness detects a divergence it was built to detect. D4 proves an
invariant fails when its own author's negative seed is applied. Every one
of those proofs is inward-facing.

None of them can answer the question the verification framework exists
for:

> When this defect occurs in production, which parts of the framework
> notice, which stay silent, and does the one that notices name the right
> cause?

That question cannot be answered one layer at a time. It requires
injecting a single realistic defect and asking all four layers at once.
D5 is that instrument.

### 1.2 A fault is a declaration, not a test case

A fault that merely says "something should move" cannot distinguish a
framework that detected a defect from a framework that is simply noisy.
So every fault declares, before it is injected:

- what business rule it challenges;
- which verification layers are expected to react;
- which specific invariants, quantities or reconciliations should fire;
- what should happen to a replay, to parity, and to certification;
- what a real occurrence would cost, and which reports it would misstate;
- where to start looking when it is seen in production;
- how it is injected, and how it is cleaned up.

Twenty-four required fields, validated at import. The measurement is the
smallest part of it. As in D4, the fields that are hard to write are the
ones that expose a fault nobody has thought through: `root_cause_candidates`
and `expected_evidence` cannot be filled in convincingly for a fault whose
purpose is vague, and registration refuses a declaration that leaves them
empty.

### 1.3 Every layer is swept, including the silent ones

The pipeline sweeps all four layers for every fault, not only the layers
the fault declares. This costs roughly four times as much and it is not
optional.

Sweeping only the declared layers would make the platform incapable of
its two most useful outputs. *Which layer missed this?* and *can the
framework tell unrelated failures apart?* both require running the layers
expected to stay silent. A framework in which every layer moves for every
fault has detected nothing — it has only proved it is sensitive to
change.

### 1.4 Signal, not verdict

A probe returns a **signal**: a flat mapping of key to digest. Detection
is "this key moved", which is deliberately weaker than "the layer reported
FAIL".

This matters on this dataset specifically. Several layers legitimately
report FAIL on live production data *before* any fault is injected — D4
is currently reporting six real constitutional violations. Asking whether
the verdict changed would make every one of those layers permanently
blind to new faults. Asking whether the signal moved does not.

### 1.5 Five outcomes, kept apart on purpose

| Outcome | Meaning |
|---|---|
| `ATTRIBUTED` | expected, moved, and moved at the declared target |
| `UNATTRIBUTED` | expected, moved, but not where declared. The layer felt a disturbance; it did not identify a defect |
| `MISSED` | expected, silent. **The finding** |
| `UNEXPECTED` | undeclared layer moved. Blast radius, recorded, never counted as a pass |
| `CORRECTLY_SILENT` | undeclared layer stayed silent. A real result — it is what makes attribution possible at all |

`detected` deliberately does **not** mean "some layer moved". It means an
*expected* layer attributed it.

### 1.6 Five injection methods

A defect can enter a financial system in five places and only one of them
is the database.

| Method | Realised as | Used for |
|---|---|---|
| `SQL` | statements against a private copy | Class A and B — 27 faults |
| `ENGINE_PATCH` | a wrapper installed on a canonical callable inside one throwaway probe subprocess | Class C — 10 faults |
| `CLOCK_SHIFT` | moves the frozen instant via D2's existing `PVF_GM_FREEZE_DATE` | 1 fault |
| `ENV` | process environment overlay | 1 fault |
| `FILE` | corrupts a copy taken into the arena first | 1 fault |

`ENGINE_PATCH` is the design decision that matters. "This function now
double-counts" is not a state any row can be in, so Class C faults cannot
be expressed by data mutation. They are injected at the engine boundary,
inside a probe subprocess that dies with the wrapper. **No file under
`app/` is touched.** Wave 0 forbids changing financial code; a platform
that could not challenge the code would leave the most dangerous class of
regression entirely unexercised, so the wrapper route exists precisely to
respect that constraint rather than work around it.

The clock route reuses D2's existing freeze override rather than
inventing a second mechanism that could drift away from it.

### 1.7 A zero-change injection is refused

Every injection reports how much it changed, and the platform raises
`InjectionDidNotApply` on a rowcount of zero.

This is the lesson D2, D3 and D4 each learned separately. A seed that ran
cleanly and altered nothing produces "not detected", which reads as a
defect in the verification framework rather than in the seed. It is a
false alarm in the one place false alarms are least affordable.

### 1.8 Isolation, verified rather than claimed

A platform that injects faults into a live hotel's financial system on
the strength of an assertion is not a platform; it is an incident waiting
for a bad afternoon.

1. **Production is never opened writable.** Inherited unchanged from D1:
   `mode=ro` source connection, SQLite backup API, SHA-256 before and
   after.
2. **Production is re-verified after every single fault**, not once per
   run, so a breach can be attributed to the injection that caused it.
3. **Each fault gets a private copy derived from a pristine baseline** —
   never from the previous fault's copy — and the baseline is re-hashed
   after every injection. Faults cannot contaminate each other by
   construction, and the platform proves it.
4. **Cleanup is verified.** The copy is deleted and its absence checked.
5. A run that cannot establish its own isolation reports `UNVERIFIED`,
   whatever the detection matrix says.

### 1.9 A latent data race, found and closed

The four probes are independent processes and run concurrently. Every
deliverable before D5 took its working copy under a fixed name —
`pvf_golden.db`, `pvf_replay.db` and so on. That is safe while runs are
serial and it is a silent data race the moment they are not: the second
process recreates the file the first is reading, and both produce results
nobody can trust.

D5 is the first thing to run them concurrently, so the race was closed
rather than avoided. `verification/dbcopy.py` gained
`working_copy_name()`, which applies a `PVF_WORK_SUFFIX` per process.
**The variable is empty by default, so every pre-D5 code path behaves
exactly as it did before.**

This is a defect that existed silently in D1–D4 and would have surfaced
the first time anyone ran two deliverables at once from a CI pipeline —
which is precisely what D8 will do.

### 1.10 The extension point

A new fault is one `@fault(...)` declaration in a `faults_*` module. No
pipeline change, no dispatch table, no classifier edit. That is the whole
mechanism and deliberately the only one.

Registration refuses:

- a duplicate id;
- an unknown category, method, layer, severity or mode;
- an empty required field;
- an empty payload for a method that needs one;
- an expected invariant that is not in the D4 registry — a declaration
  naming `INV-Z99` would report a permanent MISS against an invariant
  that does not exist;
- **an expectation of no layer, with no stated reason.** A fault nothing
  is expected to detect is either a mistake or a verification gap, and
  the platform will not guess which. Declaring it uncovered also requires
  naming the deliverable that will cover it, so the gap is tracked
  instead of forgotten.

All of these raise at import time, so a malformed fault breaks the run
loudly rather than quietly narrowing coverage.

---

## 2. Implementation summary

### Files created

| File | Lines | Purpose |
|---|---|---|
| `verification/faults/__init__.py` | 92 | Package contract and hard rules |
| `verification/faults/model.py` | 363 | `Fault`, `LayerOutcome`, `FaultEvidence`, `FaultResult`, `Metering`; the Category, Layer, TargetLayer, Method, Severity, Detection, Commissioning and Mode vocabularies |
| `verification/faults/registry.py` | 299 | Registration, validation, selection, taxonomy matrices, unbacked-claim cross-check |
| `verification/faults/isolation.py` | 157 | The arena: pristine baseline, per-fault copies, verified cleanup |
| `verification/faults/injection.py` | 293 | The five injection methods and the zero-change refusal |
| `verification/faults/detectors.py` | 213 | D1–D4 wrapped as uniform probes; signal extraction; concurrent sweep |
| `verification/faults/pipeline.py` | 377 | Execution pipeline and the five-outcome classifier |
| `verification/faults/faults_a.py` | 616 | Class A — business faults (10) |
| `verification/faults/faults_b.py` | 560 | Class B — data faults (10) |
| `verification/faults/faults_c.py` | 548 | Class C — engine faults (10) |
| `verification/faults/faults_d.py` | 571 | Class D — operational faults (10) |
| `verification/faults/commission.py` | 509 | Per-fault commissioning (nine elements) and platform self-verification (nine checks) |
| `verification/faults/report.py` | 398 | Evidence packs, matrices, and the gap report |
| **Total** | **4,996** | |

### Files modified

| File | Change | Backwards compatible |
|---|---|---|
| `verification/dbcopy.py` | Added `working_copy_name()`; working copies honour `PVF_WORK_SUFFIX`. Empty by default | Yes — identical behaviour when unset |
| `verification/__main__.py` | Added `_maybe_apply_fip_patch()` and its call in the four internal probe entry points; added `fault-registry`, `fault-run` and `fault-commission` | Yes — the hook is a no-op unless `PVF_FIP_PATCH` is set, which never happens outside a D5 probe |
| `verification/__init__.py` | D5 marked complete | Yes |
| `verification/README.md` | D5 section, artifacts, limitations | Yes |

**No file under `app/` was modified.** No schema object, no migration, no
configuration value, no dependency.

### Interfaces introduced

```
python -m verification fault-registry [--tag TAG]
python -m verification fault-run [--id ID]... [--category C] [--layer L]...
                                 [--mode M] [--serial] [--tag TAG] [--quiet]
python -m verification fault-commission [--id ID]... [--quiet]
```

`fault-registry` touches no database at all, so the taxonomy and the
coverage questions — *which invariant does no fault challenge?* — can be
reviewed without waiting for a run.

### Execution pipeline

1. **Arena** — take a pristine baseline from production; fingerprint both.
2. **Baseline sweep** — run every layer against the clean baseline once
   per platform run. This is what "moved" is measured against, and it is
   why a layer already reporting FAIL on production data can still detect
   a new fault.
3. **Issue** — a private copy of the baseline for this fault.
4. **Inject** — realise the fault; refuse a zero-change injection.
5. **Sweep** — run every layer against the seeded copy, concurrently.
6. **Classify** — per layer: did the signal move, and did it move where
   the fault declared it would?
7. **Collect** — the evidence.
8. **Clean** — delete the copy, verify it is gone, verify the baseline
   and production are byte-identical.

---

## 3. Fault registry

40 faults, 10 per class, validated at import.

| Class | Concern | Count | Injection |
|---|---|---|---|
| A — Business | what a hotel can genuinely do wrong at the desk or in the back office. Legal SQL, plausible data | 10 | SQL |
| B — Data | the record itself is malformed: a dangling reference, a missing row, a date outside its period | 10 | SQL |
| C — Engine | the data is correct and the code is wrong | 10 | ENGINE_PATCH |
| D — Operational | nothing about the money is wrong; the environment is | 10 | SQL, CLOCK_SHIFT, ENV, FILE |

### Severity

| Severity | Count |
|---|---|
| CRITICAL | 25 |
| HIGH | 13 |
| MEDIUM | 2 |

### Category matrix

| Category | CRITICAL | HIGH | MEDIUM | LOW | Total |
|---|---|---|---|---|---|
| A-BUSINESS | 4 | 6 | 0 | 0 | 10 |
| B-DATA | 6 | 4 | 0 | 0 | 10 |
| C-ENGINE | 9 | 1 | 0 | 0 | 10 |
| D-OPERATIONAL | 6 | 2 | 2 | 0 | 10 |

### Layer matrix — how hard each layer has been challenged

Read downwards this is coverage. Read as a comparison between rows it is
a statement about **the platform**, not about the layers: a layer few
faults point at is one this platform has barely tested.

| Layer | Faults pointed at it | Probe cost |
|---|---|---|
| D1_PARITY | 14 | ~2.5s |
| D2_GOLDEN | 3 | ~6.7s |
| D3_REPLAY | 20 | ~3.0s |
| D4_INVARIANTS | 28 | ~3.6s |

**D2_GOLDEN is challenged by only three faults.** That is a real
imbalance and it is stated rather than smoothed. Golden masters are
rendered-surface comparisons: they move when a *displayed figure*
changes, which makes them excellent at catching presentation regressions
and poor at attributing a specific accounting defect. Most faults
therefore declare D3 or D4, and D2 appears mostly as blast radius. The
consequence is that D2's detection ability is the least tested by this
platform, and D6 (Regression Dataset Framework) is where that should be
corrected.

### Invariant challenge coverage

21 of the 24 D4 invariants are challenged by an independently-declared
D5 fault.

The remaining three are **not unverified** — each was commissioned by its
own negative seed under D4. They are *singly* verified: their only proof
of failability is the one their own author wrote. That is a weaker
statement than the other 21 carry, and it is recorded as such rather than
counted as equivalent.

---

## 4. Database impact

None.

- No schema object created, altered or dropped.
- No migration added.
- No row in the production database read through a writable connection,
  or written by any code path in this deliverable.
- Every injection targets a disposable copy under
  `verification/_work/fip_arena/`, which is deleted and verified gone.
- Production is SHA-256 fingerprinted before the run and re-verified
  **after every individual fault**.

The `FILE` fault does not touch a real backup: the artefact is copied
into the arena and the copy is corrupted. A platform that corrupted a
real backup in order to prove backups can be corrupted would have made
the point rather too well.

---

## 5. Risk assessment

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| A fault escapes into production | Critical | `mode=ro` source connection; injection only ever targets an arena copy; production re-hashed after every fault; run reports `UNVERIFIED` on any mismatch | Negligible, and detected rather than assumed |
| A fault contaminates another fault | High | Every copy derives from the pristine baseline, never from the previous copy; the baseline is re-hashed after every injection | Negligible |
| Concurrent probes corrupt each other's working copies | High | `PVF_WORK_SUFFIX` per probe process; `parallel_safety` self-check proves concurrent and serial sweeps agree | Closed; was a latent defect in D1–D4 |
| An engine patch leaks into a real run | High | The wrapper is installed only when `PVF_FIP_PATCH` is set, only inside a probe subprocess, and dies with it. No file under `app/` is written | Negligible |
| A seeded copy survives the run and is picked up later | Medium | Cleanup verified per fault and again at teardown; `cleanup_validation` fails the commissioning if anything remains | Closed |
| A fault "passes" without ever being injected | High | Zero-change injections raise; `injection_validation` proves a no-op injection is refused | Closed |
| The platform reports detection when nothing was injected | High | `false_positive_resistance`: an unmutated copy is swept and must move nothing | Closed |
| The platform is merely noisy | Medium | Attribution is required, not movement; `UNEXPECTED` never counts as a pass; blast radius is reported separately | Managed and visible |
| A fault claims COMMISSIONED without evidence | Medium | Declarations are cross-checked against the most recent commissioning evidence pack; an unbacked claim makes the run `UNVERIFIED` | Closed |
| The run is slow enough that nobody runs it | Medium | Probes run concurrently; `--layer`, `--id` and `--category` scope a run; layer costs are published rather than hidden | Managed |

---

## 6. Automated verification

Two harnesses, kept apart on purpose.

**Fault commissioning** — nine elements per fault:

| Element | What it proves |
|---|---|
| `positive_injection` | the fault was actually introduced, with a rowcount |
| `negative_injection` | the clean baseline is the negative case and moves nothing |
| `detection` | a declared layer attributed it |
| `evidence` | the result carries injection, expectation, timestamp, execution context and root-cause candidates |
| `repeatability` | two challenges give the same classification |
| `determinism` | the same injection and the same detection across runs |
| `order_independence` | reversing the layer order changes nothing |
| `isolation` | baseline and production byte-identical after every injection |
| `cleanup` | every private copy removed and verified gone |

**Platform self-verification** — nine checks on the platform itself. This
matters more than it sounds: everything downstream of D5 will rest on
statements of the form *"the framework detects X, and we know because the
platform said so"*. If the platform is noisy, or leaks state between
faults, or reports a detection when nothing was injected, every one of
those statements is worthless — and it would look exactly the same.

| Check | What it proves |
|---|---|
| `registry_validation` | six deliberately malformed declarations are each refused |
| `injection_validation` | an injection that changes nothing is refused |
| `evidence_validation` | every result in the run carries its declared evidence |
| `cleanup_validation` | no seeded copy survived |
| `repeatability` | proven per fault by the elements above |
| `isolation` | a fault cannot reach the baseline, another fault's copy, or production |
| `false_positive_resistance` | injecting nothing detects nothing |
| `false_negative_resistance` | every covered fault is detected by a declared layer |
| `parallel_safety` | concurrent probes agree with serial ones |

### Backwards compatibility, re-verified after the change

D5 modified two files that D1–D4 depend on (`dbcopy.py` and
`__main__.py`). All four deliverables were re-run afterwards and every
verdict is identical to the one its own completion report documents:

| Deliverable | Command | Verdict | Documented before D5 | Exit |
|---|---|---|---|---|
| D1 | `run` | FAIL — 6 diverged | FAIL — 6 diverged | 1 |
| D2 | `gm-verify` | PASS | PASS | 0 |
| D3 | `replay-verify` | PASS | PASS | 0 |
| D4 | `inv-run` | FAIL — 6 violations | FAIL — 6 violations | 1 |

The two FAILs are the pre-existing, documented findings of those
deliverables on live data. Nothing D5 added moved a verdict in either
direction, which is the requirement: the instrument must not change what
it measures.

---

## 7. Commissioning report — 37/37

Evidence pack: `verification/evidence/20260805_000006_fip_commission`

```
COMMISSIONING RESULT: 37/37 PASS   (4 uncovered, reported separately)
```

36 faults × nine elements, plus the platform itself × nine checks. The
four uncovered faults are excluded from the denominator and reported
separately rather than counted as passes.

### Platform self-verification — 9/9

| Check | Result |
|---|---|
| `registry_validation` | 6/6 deliberately malformed declarations refused |
| `injection_validation` | an injection that changed no rows was refused |
| `evidence_validation` | all 36 results carry injection, timestamp and root-cause candidates |
| `cleanup_validation` | no seeded copy survived |
| `repeatability` | proven per fault by the repeatability and determinism elements |
| `isolation` | pristine baseline and production byte-identical after every injection |
| `false_positive_resistance` | an unmutated copy moved nothing in any layer |
| `false_negative_resistance` | all 36 covered faults attributed by a declared layer |
| `parallel_safety` | 4 concurrent probes agreed with the same probes run serially |

`false_positive_resistance` is the check that makes the rest meaningful.
An untouched copy of the baseline is swept and compared against the
baseline sweep; if anything moved, every "detection" in the run could be
noise. Nothing moved.

### What the first commissioning run found

The first full run returned **36/37**, and the failure was instructive.

**FLT-A10 was never injected.** Its `INSERT ... SELECT` named 17 columns
and the `reservations` table has five further NOT NULL money columns with
no default — `credit_amount`, `credit_settled_amount` and three
`cancellation_amount_*`. The statement raised `IntegrityError`, so the
duplicate reservation was never created.

The platform behaved exactly as designed: `positive_injection` failed,
`detection` failed, and `isolation` was reported as not verified because
the exception path never reached the post-injection verification. It did
**not** report "the framework failed to detect a duplicate reservation",
which is what a platform without a rowcount assertion would have
reported, and which would have sent someone hunting for a defect in D4
that does not exist.

This is the zero-change-injection principle (§1.7) doing its job against
a real mistake rather than a hypothetical one. The declaration was
corrected and the fault now commissions 9/9, attributed by D1_PARITY and
D4_INVARIANTS.

### Two defects the commissioning run exposed in the platform itself

Both were found by reading what the platform said about its own run, and
both are fixed.

**1. `false_negative_resistance` excluded the fault that errored.** Its
population was "results with layers", and FLT-A10 had none because it
never ran. The platform therefore reported *"all 35 covered faults were
attributed by a declared layer"* — a clean statement it had not earned,
in the one check whose entire job is to notice faults going undetected.

An errored fault now counts against the check and is named in the note.
A fault that could not be exercised proves nothing either way, and
silently dropping it from the denominator is the precise failure mode
this deliverable exists to find.

**2. `counts` folded the uncovered faults into `MISSED`.** The summary
read `MISSED: 4` when those four had never been injected at all — nothing
in the framework can see them, which is why they are declared uncovered.
Read quickly, the platform appeared to be reporting four detection
failures. They are now counted only under `uncovered`.

Neither defect hid a real failure — per-fault commissioning caught
FLT-A10 and the suite correctly returned 36/37 and exit code 1. Both,
though, were the platform describing itself more favourably than the
evidence supported, which is the thing it must never do.

---

## 8. Platform run — the framework challenged as a whole

Evidence pack: `verification/evidence/20260805_000007_fip_run_production`

```
registered              : 40
challenged              : 40
detected                : 36
MISSED                  : 0
errors                  : 0
uncovered (not injected): 4
VERDICT                 : INCOMPLETE
```

Duration 276.4s for 40 faults across four layers. Isolation VERIFIED:
production SHA-256 identical before and after, baseline unchanged, 36
copies removed, 0 remaining.

### Attribution and blast radius per layer

| Layer | Faults declaring it | Attributed | Moved undeclared | Selectivity |
|---|---|---|---|---|
| D1_PARITY | 14 | 14 | 9 | good |
| D2_GOLDEN | 3 | 3 | 31 | **poor** |
| D3_REPLAY | 20 | 19 | 10 | good |
| D4_INVARIANTS | 28 | 27 | 2 | **excellent** |

This table is the most useful thing D5 produces, and it could not have
been produced by any layer testing itself.

**D4 is the framework's precision instrument.** It attributed 27 of the
28 faults declaring it and moved for something undeclared only twice.
When D4 fires, it means something specific.

**D2 is a change detector, not an attributor.** It moved for 31 of the 36
injected faults while being the declared detector for 3. Golden masters
compare rendered surfaces, so any defect that alters a displayed figure
moves them — which makes them excellent at catching presentation
regressions and nearly useless for saying *what* went wrong. That is a
property of the technique, not a defect in D2, but it means D2 must never
be the sole evidence that a change was safe: a D2 diff tells you
something changed, and the other three tell you what.

---

## 9. Findings — verification gaps

Two faults were injected that a layer declared it would catch and did
not. Neither is invisible to the framework as a whole; both are places
where the control that *should* have named the defect stayed silent.

### 9.1 A rewritten close total does not move INV-B03 — CRITICAL

**FLT-D03 — the stored close total for an audited day has been
rewritten.**

`D4_INVARIANTS` was declared and returned `MISSED`. `INV-B03` did not
move. D1_PARITY and D3_REPLAY both caught it, so the defect would be
noticed — but by two layers whose job is comparison, not by the invariant
that exists specifically to assert that a closed day's stored totals
match what the data says.

Why it matters in this system: a night audit close total is the figure
the hotel treats as settled history. If it can be rewritten without the
constitutional control firing, then "the day is closed" is an assertion
nobody is checking. The reports that would be wrong are
`main.dashboard` and `reports.night_audit_history`.

Where to look, per the declaration: a manual correction applied to the
log rather than the data; a reopen-and-partially-rerun cycle; a migration
that recalculated stored aggregates.

**This is a D4 finding produced by D5**, which is precisely the
arrangement the charter asked for. It is recorded here and must be closed
by strengthening INV-B03 — under the standing rule, before any Wave 1
change touches night audit.

### 9.2 Replay notices an unexplained balance but cannot name it — HIGH

**FLT-A09 — guest checked out with an unexplained balance.**

`D3_REPLAY` was declared and returned `UNATTRIBUTED`. The day totals for
2026-05-27 and 2026-05-28 moved, but `RC07` — the reconciliation the
fault declared — did not. Replay felt the disturbance and could not
identify it. D1_PARITY and D4_INVARIANTS attributed it correctly.

The distinction matters. A layer that moves without attributing tells an
engineer "something about these two days is different now", which on a
live dataset with genuine pre-existing failures is close to no
information at all. Six reports would be misstated in production:
`ai.api_ai_insights`, `billing.invoice_register`,
`main.command_center_data`, `main.dashboard`, `main.invoice_manager` and
`reports.departures`.

### 9.3 Four faults nothing can detect

Registered so the gap is tracked, never injected, never counted as
passes, and each naming the deliverable that must close it.

| Fault | Why nothing sees it | Tracked against |
|---|---|---|
| FLT-B04 — two reservations sharing one invoice number | no invariant asserts invoice-number uniqueness, and no monetary total moves | **D4** — add the invariant |
| FLT-D04 — a database backup file is corrupt | no layer reads backup artefacts; `backup_logs` stores filename, size and status, but no checksum | **D9** — needs a checksum or an out-of-band manifest before it is detectable at all |
| FLT-D05 — a restored database does not match what was backed up | nothing holds a pre-backup fingerprint, so the restored state is simply the new truth and everything reconciles perfectly against it | **D9** — must fingerprint before backup and re-verify after restore |
| FLT-D07 — a run executes under a different process environment | no layer fingerprints the environment, so two runs under different environments are indistinguishable in the evidence | **D7** — the certificate must record an environment fingerprint |

FLT-D04 and FLT-D05 deserve emphasis. **This system currently cannot tell
whether its backups are restorable.** The schema records that a backup
happened, not that it is any good. That is not a gap in the verification
framework so much as a gap in the data model the framework would need,
and D9 cannot be built on the current `backup_logs` table without adding
one.

### 9.4 Why the verdict is INCOMPLETE, not PASS

`INCOMPLETE` is the correct and intended verdict, and it will remain so
until D7 and D9 exist. Every injected fault was detected and every
commissioned claim is backed by evidence — but two declared layers stayed
silent where they should have spoken, and four registered faults are
invisible to the framework. Reporting `PASS` while that is true is
exactly the kind of control that cannot fail (P9).

---

## 10. Performance

Measured on the live production dataset, four layers, probes concurrent.

| Measure | Value |
|---|---|
| Full run, 40 faults, 4 layers | 276.4s |
| Per fault, median | 6.3s |
| Per fault, max | 13.6s |
| Time to first attribution, median | 3.5s |
| Time to first attribution, max | 11.3s |
| Orchestrator peak memory | 4.1 MB |
| Rows changed across the whole run | 25 |
| Database writes to production | **0** |
| Full commissioning, 36 faults × 3 challenges + self-verification | ~32 min |

Layer probe costs are published in `LAYER_COST_MS` rather than hidden, so
that scoping a run with `--layer` is a stated trade-off. A layer skipped
for cost is a layer that reported nothing, and the report says which
layers were swept.

Concurrency is what makes the run affordable: four probes in parallel
cost the slowest one (~7s) rather than their sum (~16s).

---

## 11. Evidence model

Every run writes a timestamped pack under `verification/evidence/`
containing `result.json` and `report.txt`.

`result.json` carries, per fault: the injection detail and rowcount, the
declared and actual detection, per-layer outcome with moved signal keys,
attributed and missing targets, detection time, affected invariants,
reports, replays and parity checks, certification impact, root-cause
candidates, execution context, metering, and the isolation and cleanup
flags.

The run-level record carries the production SHA-256 before and after, the
baseline hash, the cleanup result, the layer set, the counts, and the
uncovered and unbacked-claim lists.

### Reporting bias, stated

D1 to D4 lead their reports with what passed. **D5 leads with what was
missed.** A fault injection platform that reports "38 of 40 detected" as
a success has buried its only genuinely valuable output on the second
page. The gap report is printed before the summary tables, and every gap
entry names the layer that should have seen the defect, what it failed to
move, which reports would be wrong in production while the framework said
nothing, and where to start looking.

---

## 12. Rollback instructions

This working copy is **not** under version control, so the rollback is
stated as the manual reversal rather than as a `git checkout` that would
fail.

```bash
rm -rf verification/faults/
rm -rf verification/_work/fip_arena/
```

Then reverse four edits by hand, none of which is required for D1–D4 to
work — they are already no-ops when `verification/faults/` is absent:

| File | Reversal |
|---|---|
| `verification/__main__.py` | delete `_cmd_fault_registry`, `_cmd_fault_run`, `_cmd_fault_commission` and their three `sub.add_parser` blocks; delete `_maybe_apply_fip_patch` and its four call sites |
| `verification/dbcopy.py` | delete `working_copy_name()` and its call sites |
| `verification/__init__.py` | restore the D5 status line |
| `verification/README.md` | delete the D5 section |

To remove the whole PVF instead:

```bash
rm -rf verification/
```

No production file, database row, schema object, configuration value or
dependency was modified. The application does not import this package.
Deleting `verification/_work/` at any time is harmless.

**Nothing in D1–D4 imports `verification.faults`.** The dependency runs
one way only: D5 imports `verification.dbcopy`, `verification.config`,
`verification.golden.report`, `verification.replay.timeline` and
`verification.invariants.registry`. Removing D5 alone leaves the first
four deliverables intact.

The two modifications to shared files are both no-ops when D5 is absent:
`PVF_WORK_SUFFIX` is unset, so `working_copy_name()` returns its input
unchanged; `PVF_FIP_PATCH` is unset, so `_maybe_apply_fip_patch()`
returns immediately.

---

## 13. Acceptance against the Wave 0 charter

### The ten required elements

| Required | Where | Met |
|---|---|---|
| Technical design | §1 | Yes |
| Files to be created | §2 — 13 files, 4,996 lines | Yes |
| Files to be modified | §2 — 4 files, all backwards compatible | Yes |
| Database impact | §4 — none | Yes |
| Risk assessment | §5 — 10 risks, mitigation and residual | Yes |
| Implementation | `verification/faults/` | Yes |
| Automated tests | §6 — 9 elements per fault, 9 platform self-checks | Yes |
| Verification evidence | §7–10, two evidence packs | Yes |
| Rollback plan | §12 | Yes |
| Completion report | this document | Yes |

### The implementation rules

| Rule | Actual | Met |
|---|---|---|
| Remain backwards compatible | All four earlier deliverables re-run, no verdict changed (§6) | Yes |
| Avoid production downtime | Nothing runs in the application process; production opened `mode=ro` only | Yes |
| Preserve current hotel operations | No production file, row, schema object or configuration touched | Yes |
| Produce objective evidence | `result.json` + `report.txt` per run, with hashes before and after | Yes |
| Include automated verification | `fault-commission`, exit code 0 only at 37/37 | Yes |
| Include rollback instructions | §12 | Yes |
| Include documentation | This report, `faults/__init__.py`, README §D5 | Yes |

### The D5 objective

| Success criterion | Actual | Met |
|---|---|---|
| Faults are a framework, not isolated test cases | One `@fault(...)` decorator; registration validates 24 fields | Yes |
| Realistic fault taxonomy | 40 faults, 10 per class A/B/C/D | Yes |
| Faults injected safely | Private copy per fault; production re-hashed after every one; VERIFIED | Yes |
| Every layer challenged | All four swept per fault, including those expected to stay silent | Yes |
| Detection demonstrated | 36/36 injected faults attributed by a declared layer | Yes |
| Attribution, not just movement | `ATTRIBUTED` requires the declared target; blast radius reported separately | Yes |
| The platform can itself fail | 9 self-checks; the first run returned 36/37 and exit 1 | Yes |
| Faults commissioned before use | 37/37; declarations cross-checked against the evidence pack | Yes |
| Gaps reported rather than smoothed | 2 gaps and 4 uncovered faults, each with a named successor deliverable | Yes |
| Zero production financial behaviour changed | 0 lines under `app/` | Yes |

### Not covered, stated explicitly

- **D2_GOLDEN is challenged by only 3 faults** and moves as blast radius
  for 31. Its attribution ability is the least tested by this platform.
  D6 is where that should be corrected.
- **Four faults cannot be detected at all** (§9.3). Two of them mean the
  system currently cannot tell whether its backups are restorable.
- **Two declared layers stayed silent** where they should have spoken
  (§9.1, §9.2). Both are recorded as findings against D4 and D3.
- **`ENGINE_PATCH` cannot reach a callable bound at import time under an
  alias.** FLT-C01 declares this explicitly: D1's P16 and P18 reach
  `get_cash_revenue` through the `get_daily_revenue` alias, so a wrapper
  on the canonical name does not cover them. Stated in the declaration
  rather than hidden by dropping the expectation.
- **Three D4 invariants are challenged by no D5 fault.** They are not
  unverified — each was commissioned by its own negative seed — but their
  only proof of failability is the one their own author wrote.
- **`GOLDEN_MASTER`, `HISTORICAL_REPLAY` and `REGRESSION_DATASET` modes
  are declared and unexercised.** They belong to D6 and later.
- **The verdict is INCOMPLETE and will remain so** until D7 and D9 close
  the uncovered faults. That is the honest reading, not a defect.

---

## 14. Position in Wave 0

```
D1  Financial Parity Harness      complete, commissioned  8/8
D2  Golden Master Framework       complete, commissioned 16/16
D3  Historical Replay Framework   complete, commissioned 21/21
D4  Financial Invariant Engine    complete, commissioned 26/26
D5  Fault Injection Framework     complete, commissioned 37/37
```

D5 changes what the framework can claim. Before it, each layer's
reliability rested on its own author's seeds. After it, the four layers
have been challenged together by defects declared independently of any of
them, and the places where they stay silent are written down.

The gaps this deliverable found are not defects in D5. They are the
deliverable's output, and they are now tracked against the deliverables
that must close them.

**Next:** D6 — Regression Dataset Framework.
