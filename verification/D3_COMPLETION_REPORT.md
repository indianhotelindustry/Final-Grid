# Wave 0 — Deliverable D3: Historical Replay Framework
## Completion Report

**Status:** COMPLETE — commissioned 21/21
**Date:** 2026-08-04
**Baseline:** DSBC Frontline v2.2.18
**Production code modified:** 0 lines
**Production data modified:** 0 rows
**Production SHA-256:** `f07b090a…5aeb2c` — identical before and after every run

---

## 1. Technical design

D1 measures the engines against each other, today. D2 measures the
surfaces against a stored master, today. Neither asks the question that
matters most before a financial migration:

> Does the system still tell the same story about days that are already
> closed?

A closed business day is a promise. It was reported to the owner, it
underpins a GST return, and it is the basis on which cash was reconciled.
If a code change quietly moves the number for 27 May, nothing in D1 or D2
finds out — D1 compares today's engines to each other and both moved
together; D2 compares today's page to today's master, and the master is
recaptured after every intended change. History is not recaptured.

### Three independent accounts of every historical date

| Account | Produced by | Answers |
|---|---|---|
| **LEDGER** | this package, plain `sqlite3`, no application code | what is in the books |
| **ENGINE** | the application's date-parameterised helpers and the read-only `NightAuditService`, clock frozen to noon on the replayed date | what the application says |
| **RECORDED** | the `NightAuditLog` row and its `snapshot_json` | what the system froze at close |

The LEDGER exists because every other account is produced by the code
under test. If that code changes, they all move together and agree with
each other just as convincingly as before. An account independent of the
code under test is the only thing that can say which of them moved.

It contains **no financial policy**. It does not decide what revenue is
or which payments count as cash; it states what is in the transactional
rows, sliced the few ways the application's own filters slice them, so
that an engine figure can be compared against the aggregate it is
supposed to equal. Where a slice mirrors an application filter, the
filter is named at the slice — which makes the mirroring reviewable, and
makes a change to that filter show up as a failed reconciliation rather
than being absorbed.

### Declared reconciliation, not discovered agreement

Twenty rules (`RC01`–`RC20`) each name one engine path, one expression
over ledger paths, and the reason the two should be equal. Matching by
searching for pairs that happen to agree would be circular: the framework
would report agreement exactly where it went looking for it, and a figure
that reconciles to nothing would drop silently out of the report. Every
engine figure no rule covers is listed on each run as the framework's own
coverage gap — 201 of them today.

Tolerance is EXACT. The single 0.005 epsilon absorbs the difference
between a float the application rounded to 2 dp and the same figure
summed in `Decimal`, and it is documented per rule rather than applied as
a band.

### The retroactivity control

Every past date is replayed a **second** time with the clock frozen to
the current business date — asking today about a day that is already
closed. A closed day's figures must not depend on when the question is
asked. Anything that moves is an as-of-now query inside a historical
report and is reported as `ASAT_DRIFT`.

### Determinism, and the risk the design creates

Replaying every date in one process is what keeps the framework inside
its runtime budget: a process launch and a full `create_app()` per date
would put a two-year dataset far outside fifteen minutes, and a harness
that takes an hour is switched off in the week it matters.

The cost is the risk that state carries from one date to the next. That
risk is not argued away — it is **measured**. Every date is replayed
again in reverse order and the two answers must be identical
(`PASS B`). If any figure depends on the order the dates were replayed
in, the run fails and says so.

Three further controls produce positive evidence rather than silence:

* the clock freeze is re-installed and **re-proven per date** (28/28);
* the LEDGER is rebuilt after the application has run and must be
  byte-identical to the LEDGER built before it — which proves the replay
  wrote nothing to the copy;
* production is SHA-256 fingerprinted before and after, unchanged from
  D1.

### Two vocabulary decisions

**`NO_ACTIVITY` is not `VACUOUS`.** Both sides agreeing at zero over an
empty population proves nothing, and D1 rightly calls that `VACUOUS`. But
every real dataset contains days on which the hotel did no business, and
a framework that reported INCOMPLETE for the rest of time on account of
them could never pass. A gate that can never pass is abandoned exactly as
fast as one that can never fail. So agreement at zero on a day with **no
primary record at all** is recorded as `NO_ACTIVITY` — stated, counted,
never called agreement, and not counted as a gap in verification. On a
day that *did* trade, an empty population is still `VACUOUS`.

**Severity follows the state of the day, not the kind of figure.** A
closed day may not move at all (BLOCK). A past day never closed may move
but is reported (WARN). The current business date is expected to move
(INFO) — the hotel is trading. A date appearing *earlier* than the stored
history is BLOCK regardless: that is a posting back-dated into a period
the stored replay says did not exist.

---

## 2. Files created

| File | Lines | Purpose |
|---|---|---|
| `verification/replay/__init__.py` | 69 | Package contract |
| `verification/replay/timeline.py` | 269 | History discovery, closure state, window |
| `verification/replay/ledger.py` | 414 | Primary-record reconstruction |
| `verification/replay/engines.py` | 163 | Date-parameterised probes, replayability census |
| `verification/replay/recorded.py` | 128 | The frozen close and its integrity |
| `verification/replay/reconcile.py` | 346 | The 20 declared reconciliations |
| `verification/replay/replay.py` | 716 | Orchestration, the three passes, storage |
| `verification/replay/compare.py` | 292 | Difference classification and severity |
| `verification/replay/report.py` | 422 | Evidence packs |
| `verification/replay/commission.py` | 786 | Five-class seeded-fault commissioning |
| **Total** | **3,605** | |

Plus `verification/ledgers/production/` — 28 date records and an index.

## 3. Files modified

**Inside the PVF only. No file under `app/` was touched.**

| File | Change | Why |
|---|---|---|
| `verification/__main__.py` | Added `replay`, `replay-verify`, `replay-commission`, `_replay_json` | CLI surface for D3 |
| `verification/__init__.py` | Version 0.2.0 → 0.3.0; deliverable status | Bookkeeping |
| `verification/README.md` | D3 commands, accounts, severity model, limitations | Documentation |

D3 reuses D1's `dbcopy` and `config` and D2's `freeze`, `normalize` and
`report.write_pack` **unchanged**. No D1 or D2 module was edited.

## 4. Database impact

**None.** No schema change, no row change, no migration. Production
SHA-256 identical before and after every replay, verification and
commissioning run, including all eight seeded-fault runs. The LEDGER
stability control additionally proves the *working copy's* primary
record was not written to while the application ran.

---

## 5. Risk assessment

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| Harness writes to production | Critical | D1's `mode=ro` + hash verification, reused unchanged | None — empirically verified |
| State leaks between dates in one process | Critical | The design's own risk. Measured, not asserted: every date is replayed again in reverse order and must give identical figures. Session identity map dropped between dates | None on this dataset — 0 mismatches; the control fails loudly if it ever occurs |
| Clock frozen to the wrong day | Critical | Timeline pre-read with `sqlite3` before any app import; business date cross-checked against `get_business_date()`; freeze re-proven per date, capture aborts if unproven | None |
| The reconciliations are tautological — both sides reading the same rows through the same filter | High | **This is the failure mode specific to D3.** Commissioned by `S-RP-ORPHAN-MODE`, a fault engineered so the two application views genuinely disagree while the ledger counts the row as neither. RC11 moves RECONCILED → UNRECONCILED | None — proven capable of failing |
| The ledger becomes a second implementation of financial policy | High | It computes no policy: only sums, counts and date spans, with every application-mirroring filter named at the slice. Where a rule fails it reports that the two disagree, not which is right | Low — reviewable by construction |
| As-at exclusion hides a real difference | High | One rule, named, justified, with its hit count printed. `S-RP-ASAT` removes it and requires the masked drift to appear — proving the two passes really ran under different clocks | None |
| False positives make the gate noisy | High | Null control and comparator null control both required to report zero; `S-RP-CMP-TODAY` requires movement on the current business date to be reported at INFO, never BLOCK | None — 0 spurious differences |
| Runtime grows with history | Medium | 7.9 s for 28 dates. Linear in dates; `--fast` and `--from`/`--to` are available and both are reported when used | Low — re-measure on a multi-year dataset |
| One closed day in the dataset | Medium | Not mitigable by the framework. Stated in coverage, in the report, and in §10 | Accepted, documented |
| Evidence stored inside the application | Medium | Inherited from D1; export is a release-process responsibility | Accepted, tracked |

---

## 6. Verification evidence

### 6.1 Coverage

```
Dates replayed        : 28   (2026-05-01 .. 2026-05-28)
  with primary records:  2
  with none           : 26   (replayed anyway)
Closed (night audit)  :  1
With frozen snapshot  :  1
Engine figures        : 4,918 across all dates (317 and 337 on the trading days)
Ledger figures        : 51 per trading day
Reconciliations       : 36 reconciled, 0 UNRECONCILED, 2 VACUOUS,
                        494 on days with no activity
Month-to-date (RC20)  : 28/28 reconciled
Runtime               : 7.9 s   (budget 900 s)
```

The replay window starts at the **first of the month** containing the
first activity, not at the first activity. Month-to-date figures are
among the most frequently wrong in a PMS and can only be checked against
the sum of their days if every day of the month is in the set. Days with
no rows are replayed anyway, so a day that later acquires a back-dated
posting is visible as a change rather than as a new date appearing from
nowhere.

### 6.2 Controls — positive evidence

```
read-only         : VERIFIED  production byte-identical after run
frozen clock      : proven on 28/28 dates (re-installed and re-proven per date)
ledger stable     : VERIFIED  primary record byte-identical before and after
                              the application ran
order independent : VERIFIED  reverse-order replay produced identical figures
```

### 6.3 Determinism

Two independent replays, separate processes, fresh copies:

```
Dates compared : 28
Dates clean    : 28
Differences    :  0
VERDICT        : PASS
```

Achieved with **one** masking rule, applied only to the as-at
comparison — `nas.audit_header.generated_at`, which records when the
report was produced and is *supposed* to move when the clock moves. Its
hit count is printed on every run, so a rule that stops applying is
itself reported.

### 6.4 Commissioning — 21/21

**A. Data faults, seeded into the closed day 2026-05-27.** Each seed
declares which control must react; detection elsewhere does not count.

| Seed | Fault | Result |
|---|---|---|
| S-RP-BACKDATE | Post a 555.00 settlement into the closed day | 7 ledger and 43 engine figures moved; 3 new history drifts |
| **S-RP-PAISA** | Move one closed-day payment by **0.01** | 5 ledger and 22 engine figures moved; history drift raised |
| S-RP-VOID | Void a payment belonging to the closed day | detected on all three accounts |
| S-RP-CHARGE | Post a 222.00 charge into the closed day | accrual extras and total revenue moved |
| S-RP-RATE | Raise one closed-day nightly rate by 111.00 | `night_rates.final` moved |
| S-RP-STORED | Rewrite the stored close total by 999.00 | `total_collected vs stored.total_revenue` drift raised |
| S-RP-SNAPSHOT | Tamper `snapshot_json`, leave the hash | integrity `True → False` |

The paisa seed tests the claim that there is no tolerance band on
history. A rounding-tolerant replay would let a systematic sub-rupee
drift through on every day at once.

**B. Reconciliation fault** — the one that matters most for this
deliverable.

`S-RP-ORPHAN-MODE` points one closed-day payment at a payment mode that
does not exist. `night_audit_service` defaults a missing mode to DIRECT
cash (`app/night_audit_service.py:537`); `kpi_helpers` inner-joins
`PaymentMode` and drops the row entirely. The two application views
therefore disagree about the same rupees, and the ledger — which counts
the row as neither direct nor OTA — is what reveals which of them moved.
**RC11 moved RECONCILED → UNRECONCILED.**

Without this seed, every reconciliation rule could have been
tautological: two views of the same rows through the same filter,
agreeing forever and proving nothing.

**C. The as-at control** — `S-RP-ASAT` clears the single declared
exclusion and requires the drift it was masking to appear. It did, on
**27 past dates**. This is end-to-end proof that PASS A and PASS C really
ran under different clocks and that the comparator compares them; had the
two passes been identical, nothing would have appeared.

**D. Comparator faults** — a stored replay mutated field by field. Each
produced exactly the expected classification at the expected severity:
`LEDGER_CHANGED`, `ENGINE_CHANGED`, `RECORDED_CHANGED`,
`SNAPSHOT_INTEGRITY_CHANGED`, `CLOSURE_CHANGED`, `DATE_REMOVED`,
`BACKDATED_DAY`, `RECONCILIATION_CHANGED`, `ORDER_MISMATCH_CHANGED` — all
BLOCK. Plus `S-RP-CMP-TODAY`, which requires 5,000 more cash on the
**current** business date to be reported at **INFO and never BLOCK**. A
gate that fails every day the hotel trades is a gate nobody keeps.

**E. Null controls** — identical data produced 0 differences across all
28 dates; the stored replay compared against itself produced 0. A control
that always fires is as useless as one that never does.

### 6.5 Two commissioning defects found by commissioning

**The seed the schema refused.** `S-RP-UNCATEGORISED` originally posted a
payment through a mode whose category was neither `direct_payment` nor
`ota_receivable`. SQLite rejected it: `CHECK constraint failed:
ck_payment_mode_category`. That constraint is a real control and is now
recorded as one. The same disagreement is reached instead by a route the
schema does not close — foreign keys are not enforced on this database,
so a payment can point at a mode row that does not exist.

**The seed that was backwards.** `S-RP-CMP-DATE-GONE` deleted the closed
date from the *stored* side and expected `DATE_REMOVED`. A date missing
from the stored set is an **addition**, not a removal, and the comparator
correctly reported `DATE_ADDED`. Read quickly, that looks like a
comparator defect. The seed now declares which side it injects into, and
the reason is recorded at the field.

Both are Principle 11 applied to the commissioning harness itself: a
suite whose failures cannot be distinguished from the failures of the
thing it commissions is not a suite.

---

## 7. Automated tests

As with D1 and D2, verification is by executable control rather than a
separate unit-test suite (that suite does not exist and is not a Wave 0
deliverable). Three CLI commands with meaningful exit codes, all
pipeline-ready for D8:

| Command | Proves |
|---|---|
| `replay --dry-run` | The replay runs, all four controls establish, coverage and gaps are reported |
| `replay-verify` | Determinism, and that no closed day has moved since the stored replay |
| `replay-commission` | Detection capability across five fault classes |

`verification commission` (D1, PASS) and `gm-commission` (D2, 16/16) were
re-run after these changes and are unaffected.

---

## 8. Findings produced

**No production code was changed. Everything below is recorded, not
fixed, per the standing Wave 0 instruction.**

### 8.1 A closed day's outstanding balance has moved — BLOCKING

```
2026-05-27  nas.folio_control.total_outstanding
    frozen at close : 0.16
    recomputed now  : 200.15
```

Reservation 1 was in-house on 27 May and did not check out until **29
May**, when a 200.00 individual credit was approved against it
(`credit_approved_at = 2026-05-29`). `NightAuditService.folio_control`
buckets each reservation by `Reservation.status` — a present-tense field
— so recomputing 27 May today sees the guest as `CheckedOut` with an
unpaid balance and adds 200.00 to that night's checkout outstanding.

Neither the credit nor the checkout existed on the night of 27 May. A
credit granted two days later has been retroactively added to a closed
day's position. Anyone reprinting that night audit today gets a different
answer from the one that was reconciled and signed off.

### 8.2 Fifty-seven engine figures do not vary with the date at all

Held identical on all 28 replayed dates, including days before the hotel
had any activity:

| Figure | Value on every date |
|---|---|
| `kpi.dashboard_kpis.adr` | 0 |
| `kpi.dashboard_kpis.occupancy_pct` | 0 |
| `kpi.dashboard_kpis.occupied` | 0 |
| `kpi.dashboard_kpis.revpar` | 0 |
| `nas.folio_control.individual_credit_outstanding` | 200 |
| `nas.folio_control.total_credit_outstanding` | 200 |

`get_dashboard_kpis(business_date)` **takes a date and ignores it** for
occupancy, ADR and RevPAR: it delegates to `get_occupancy()`,
`get_adr()` and `get_revpar()`, none of which accept one. A caller
passing a historical date receives today's numbers under a historical
heading, with nothing in the signature to warn them. This is the same
root cause as the zero ADR that D1's P20 and D2's §8.3 recorded, now
shown to affect *every* date rather than only today.

`individual_credit_outstanding = 200` on 1 May is the same defect as
§8.1: a credit approved on 29 May appearing in the position of a day four
weeks earlier.

The framework reports this census as informational, not blocking: a
figure that never moves is either genuinely constant — the room count,
the tax rate — or not date-scoped at all, and telling those apart is an
engineering judgement, not a measurement.

### 8.3 Seven engine entry points have no historical form

Declared and printed on every run, because "this figure cannot be
verified against history" is one of the more useful things to know before
a migration starts:

`get_occupancy`, `get_occupied_count`, `get_adr`, `get_revpar`,
`get_sellable_room_count`, `occupancy_engine.occupancy_snapshot`, and the
room half of `NightAuditService.occupancy_position` — all read
`Reservation.status` or `Room.status`, which say what a room or booking
is like *now*.

### 8.4 A payment can be counted as cash by one engine and by neither the other nor the books

Found while commissioning, not while replaying, and recorded because it
is a live gap rather than a seeded one. `night_audit_service.py:544`
treats a payment whose mode is missing as `direct_payment`;
`kpi_helpers.get_cash_revenue` inner-joins `PaymentMode` and drops it.
Foreign keys are not enforced on this database, so the state is
reachable. Today no such row exists — which is why the framework had to
create one to prove the reconciliation can fail.

### 8.5 Wave 1 triage list

Recorded, not acted on: the retroactive credit on a closed day (§8.1),
the date-ignoring dashboard bundle (§8.2), the seven unreplayable entry
points (§8.3), and the orphan-mode cash disagreement (§8.4).

---

## 9. Rollback plan

```bash
rm -rf verification/replay/ verification/ledgers/
git checkout verification/__main__.py verification/__init__.py \
             verification/README.md
```

Or, to remove the whole PVF:

```bash
rm -rf verification/
```

No production file, database row, schema object, configuration value or
dependency was modified. The application does not import this package.
Deleting `verification/_work/` at any time is harmless.

D3 has **no cross-deliverable coupling in the other direction**: it
imports from `verification.dbcopy`, `verification.config`,
`verification.golden.freeze`, `verification.golden.normalize` and
`verification.golden.report`, and nothing in D1 or D2 imports from
`verification.replay`. Removing D3 alone leaves D1 and D2 intact.

---

## 10. Acceptance against Phase 2.6

| Criterion | Required | Actual | Met |
|---|---|---|---|
| Historical data replayed | Yes | 28 business dates | Yes |
| Reconstruction independent of the code under test | Yes | LEDGER built with `sqlite3`, no application code | Yes |
| Closed periods verified against what was reported | Yes | ENGINE vs `snapshot_json` and the stored close totals | Yes |
| Retroactivity detected | Yes | Every past date replayed under two clocks | Yes |
| Deterministic | Yes | 0 differences across independent runs | Yes |
| Attributable | Yes | Per date, per dotted path, per named reconciliation | Yes |
| Detects both directions | Yes | Figures and dates added *and* removed | Yes |
| Under 15 minutes | < 900 s | 7.9 s | Yes |
| Fault-injection commissioned | Yes | 21/21 across five fault classes | Yes |
| Coverage gaps stated | Yes | 201 uncovered figures, 7 unreplayable entry points, 1 masking rule, all printed every run | Yes |

### Not covered, stated explicitly

- **One closed business day.** The comparison against the frozen close is
  exercised on a single date. It found a defect there; one date is not a
  demonstration that the control scales. D6's regression datasets should
  supply more.
- **As-at drift reports nothing on this dataset.** The control is proven
  live by commissioning, not by a live finding.
- **Twenty reconciliations cover 20 of ~220 engine figures per date.**
  The other 201 are captured and compared between runs but are not
  checked against the primary record.
- **Reports and dashboards are not replayed.** D3 replays engines. The
  surfaces are D2's territory, and D2 captures them for the current
  business date only. Rendering a historical report page under a frozen
  clock is a natural extension and is not claimed here.
- **State-changing flows are still not exercised.** D2 deferred POST
  surfaces to D3; D3 replays what the recorded transactions *mean*, not
  the act of posting them. Exercising a check-in or a night audit against
  a copy belongs with D5 (Fault Injection) and D6 (Regression Datasets),
  where a dataset exists to run them against and be restored afterwards.
  Recorded here rather than left as an implied promise.

---

## 11. Position in Wave 0

D3 is complete and commissioned. The framework now measures history as
well as the present, and it has produced the first blocking finding about
a closed period: a day that was reconciled and signed off no longer
computes the same way.

```
D1  Financial Parity Harness      complete, commissioned  8/8
D2  Golden Master Framework       complete, commissioned 16/16
D3  Historical Replay Framework   complete, commissioned 21/21
```

`FAIL` is the correct overall verdict for the replay: the harness is
reporting a real defect in a closed period, which is exactly what it was
built to do.

**Next:** D4 — Financial Invariant Engine.
