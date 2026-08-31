# Engineering Guide — FinalGrid

How work is done on this system. Written Wave 0.5.

This guide is subordinate to `CONSTITUTION.md`. Where the two disagree,
the constitution wins and this document is wrong.

---

## 1. The operating premise

This is a hotel property management system holding live financial records.
The verification framework exists because the codebase was found to
contain multiple independent definitions of room revenue, historical
reports that drift after closure, and a night audit that reads
present-tense operational state. Those are not hypotheses; each was found
by measurement and each is recorded in `WAVE0_STATUS.md` §4.5.

The consequence is the rule that governs everything else:

> **Verification is built before the thing it verifies is changed.** (P13)

Wave 0 builds measurement instrumentation and changes nothing. Wave 1
changes financial logic, and may not begin until Wave 0's ten deliverables
are complete and commissioned.

---

## 2. The implementation workflow

Every engineering task follows this sequence. No step is optional and the
order is not negotiable.

1. **Understand the approved objective.** If it is not on the roadmap, it
   is not the objective.
2. **Inspect the existing implementation.** Read it. Do not infer it from
   the documentation — in this project the documentation has been wrong
   about the code more than once.
3. **Identify architectural impact.** Which canonical engines, which
   reports, which invariants.
4. **Produce a technical implementation plan**, including the blast
   radius measured rather than estimated.
5. **Identify every file affected.**
6. **Implement incrementally.** One reviewable commit per coherent change.
7. **Run the relevant verification frameworks.**
8. **Produce evidence.**
9. **Summarise findings.**
10. **Document completion.**

**Never skip verification.** A change that cannot be verified is not
ready, however obviously correct it looks.

---

## 3. Implementation rules

These are the rules the frameworks are built to enforce. Most of them can
be checked mechanically; that is deliberate.

1. **One canonical derivation.** A financial quantity is derived in
   exactly one place. A second implementation is a defect even when it
   agrees, because it will not agree forever. (P1)
2. **Reports consume canonical engines.** A report that computes its own
   figure has created a second definition. (P3)
3. **Night Audit orchestrates; it does not derive.** (P4)
4. **Validation lives in the service layer**, not in routes and not in
   templates. (P5)
5. **Closed periods are append-only.** A correction to a closed day is a
   new entry, never an edit. (P7, P12)
6. **One temporal basis.** A historical report answers as at the business
   date it covers, never as at today. (P8)
7. **Never silently improve a calculation.** A calculation that changes
   is a behavioural change, requires declared expected movement, and
   requires evidence.
8. **Every financial object has provenance.** Where the figure came from
   is part of the figure. (P14)
9. **A control must be capable of failing.** An invariant, dataset or
   fault that has never been shown to fail is not evidence and is
   excluded from every verdict until commissioning demonstrates it. (P9)
10. **Absence of evidence is not evidence.** An empty population reports
    `VACUOUS`, never `AGREED` or `HOLDS`. (P10)

### Adding to the frameworks

Adding an invariant, a fault or a dataset is **one declaration** in the
relevant `rules_*.py`, `faults_*.py` or `datasets_*.py`. No pipeline
change, no dispatch table, no classifier edit. Registration **refuses** a
declaration with an empty required field, an unknown vocabulary value, or
no stated way to make it fail.

**Standing rule:** any future financial feature, report, night-audit
change or accounting change must register its invariants *before*
implementation is permitted.

---

## 4. The evidence model

### What an evidence pack is

Every run writes a timestamped directory under `verification/evidence/`:

```
evidence/20260807_154716_v2.2.18_preWave1/
  result.json          the full measurement
  report.txt           the human-readable report
  baseline_diff.json   (compare runs) the change list
```

Packs are **retained and never edited**. They are release evidence under
Phase 2.6 §13 and immutable under P12. When an identifier changes, the
packs keep the identifier they were written with and the reader
translates — see §6. Rewriting an old pack so it reads as though it had
always used today's vocabulary is falsifying the record, and it is
precisely the failure mode this framework exists to detect.

`verification/_work/` is the opposite: disposable copies of the production
database, safe to delete at any time, never committed.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | PASS |
| 1 | FAIL — a blocking divergence, or drift against baseline |
| 2 | INCOMPLETE — quantities not implemented, or vacuous |
| 3 | ERROR — a measurement raised |
| 4 | UNVERIFIED — read-only guarantee not established |

`4` is not a soft failure. It means the framework could not prove it left
production untouched, so nothing it reported can be trusted.

### Verdict vocabulary

| Verdict | Meaning |
|---|---|
| `AGREED` | All implementations agree within the variance policy |
| `SINGLE_SOURCE` | Only one implementation exists; recorded as evidence |
| `DIVERGED` | Implementations disagree — the finding the harness exists to produce |
| `VACUOUS` | Agreement over an **empty population**, which proves nothing (P10) |
| `NOT_IMPLEMENTED` | Declared but not measured — never counted as agreement |
| `ERROR` | The measurement raised |

For fault injection: `ATTRIBUTED`, `UNATTRIBUTED`, `MISSED` (the finding
D5 exists to produce), `UNEXPECTED`, `CORRECTLY_SILENT`.

### The read-only guarantee

Every run works on a disposable copy made through SQLite's backup API from
a connection opened `mode=ro`. The production file is SHA-256
fingerprinted before the copy and re-verified at the end of every run; a
mismatch raises `ProductionWriteDetected` and **the run's results are
discarded**.

The guarantee is proven on demand and costs seconds:

```bash
python -m verification selfcheck
```

Two application helpers are deliberately never called because they write:
`gst_service.get_folio_gst_summary()` (commits via `ensure_all_tax_lines`)
and `services.run_night_audit()` (posts charges and advances the business
date).

---

## 5. The release process

### The migration operating model

1. **Declare first.** Before the change, state for each quantity:
   unchanged, or changed by a stated amount with a stated cause.
2. **Capture a baseline** on the current code.
3. **Make the change.**
4. **Compare.** A value that moved when it should have held is a failure —
   **and so is a value that held when it should have moved**, because that
   means the change did not take effect. This second case is the one
   teams forget.
5. **Retain the evidence pack** as release evidence (Phase 2.6 §13).

### The gate

```bash
python -m verification selfcheck                        # prove read-only
python -m verification compare  --tag <baseline>        # D1
python -m verification gm-verify --tag production       # D2
python -m verification replay-verify --tag production   # D3
python -m verification inv-run   --tag production       # D4
python -m verification fault-run --tag production       # D5
```

**D2 must never be the sole evidence that a change was safe.** A golden
master diff says something changed; it does not say what. It moved for 31
of 36 injected faults while being the declared detector for 3.

### Version control

Every change is committed. The commit message states what was verified and
how, because six months later the commit message is the only place that
information still exists. Rollback is `git reset --hard <tag>`.

| Tag | Meaning |
|---|---|
| `v2.2.18-preWave1` | engineering baseline, before Wave 0.5 |
| `v2.2.18-wave0.5` | Wave 0.5 complete |
| `v2.2.18-wave0.5-frozen` | freeze point before Wave 1 |

No tag on this repository asserts certification, and none may until D7 —
the Certification Engine — exists and issues one.

### Repository protection (R0)

The repository carries the code, the governance documents and all 83
evidence packs. Losing it loses the audit trail, which under Phase 2.6 §13
is release evidence.

**Bundle.** A single-file snapshot of every branch and tag:

```bash
git bundle create ../repo-backups/SukoonPMS-<date>-<tag>.bundle --all
git bundle verify ../repo-backups/SukoonPMS-<date>-<tag>.bundle
```

**Restore, and prove the restore.** A backup that has never been restored
is not a backup — the same principle D5 applies to controls (P9):

```bash
git clone <bundle> /some/fresh/dir
git -C /some/fresh/dir rev-parse 'HEAD^{tree}'   # must equal the origin's
git -C /some/fresh/dir fsck
```

Refresh the bundle at every tag, and keep it off this machine.

**What the bundle does NOT contain**, by design:

- `instance/pms.db` — the production database
- `.env` — secrets
- `verification/_work/` — disposable copies

**Repository protection is not data protection.** The database needs its
own backup, on its own schedule, and that backup needs its own restore
test. D5 recorded that the system cannot currently tell whether its
backups are restorable (`FLT-D04`, `FLT-D05`, both blocked on D9).

---

## 6. Identifiers

| Namespace | Range | Meaning |
|---|---|---|
| `P1`–`P14` | constitution | Constitutional principles |
| `Q01`–`Q22` | D1 | Parity quantities |
| `INV-{A,B,C,D}nn` | D4 | Invariants |
| `FLT-{A,B,C,D}nn` | D5 | Faults |
| `RCnn` | D3 | Declared reconciliations |
| `S-*` | D1/D3 | Commissioning seeds |

The quantities were `P01`–`P22` until Wave 0.5 and collided with the
principles. They were renamed; the constitution was not, because it is
cited by external governance documents and by every invariant declaration.

**Renaming an identifier does not license editing stored artefacts.**
Baselines and evidence packs keep the identifiers they were written with;
`quantities.canonicalise_quantity_map()` translates them when a baseline
is read. If you rename anything else, follow the same pattern:

1. Rename in source, line-anchored, never a blanket regex — the two
   namespaces overlapped textually and a careless replace would have
   silently rewritten constitutional citations.
2. Gate the migration on a per-file occurrence count matched against
   inspection, and refuse to write on a mismatch.
3. Add a legacy alias applied on **read**.
4. Prove neutrality by controlled experiment: stash the rename, re-run the
   gate on the old code against the same database and baseline, and show
   the outputs are identical after normalising the identifier.

---

## 7. Communication

Be direct. Be evidence-driven. Challenge assumptions when evidence
contradicts them. Do not generate unnecessary documentation. Do not repeat
completed analysis. Prefer implementation over discussion.

State what was verified and what was not. "Verification not run" is a
usable statement; a confident summary that quietly skipped a check is not.

When a document and the repository disagree, **the repository is the
source of truth** and the disagreement gets written down. In this project
that has happened repeatedly: the roadmap recorded D6 as not started when
six of its modules existed, and two source labels described the
constitution as ending at P12 while P13 and P14 were registered, enforced
and reported.
