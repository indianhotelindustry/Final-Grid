# Wave 0 — Deliverable D4: Financial Invariant Engine
## Completion Report

**Status:** COMPLETE — commissioned 26/26 (24 invariants + 2 engine controls)
**Date:** 2026-08-04
**Baseline:** DSBC Frontline v2.2.18
**Production code modified:** 0 lines
**Production data modified:** 0 rows
**Database writes during evaluation:** 0, counted not assumed
**Production SHA-256:** `f07b090a…5aeb2c` — identical before and after every run

---

## 1. Technical design

### 1.1 An invariant is a declaration, not an assertion

An assertion tells you something is wrong. An invariant has to tell you
*what obligation was broken, whose obligation it was, what it costs,
where to look, and whether the control that found it has ever been shown
to work*. A bare `assert charges - payments == outstanding` carries none
of that, and six months later nobody can say whether it was ever true, on
which dates, or what a failure means for the accounts.

So every invariant is a frozen structured object carrying all seventeen
declared fields:

| Field | Purpose |
|---|---|
| `invariant_id` | Stable identity across releases and history |
| `title` | What it asserts, in one line |
| `category` | Class A / B / C / D |
| `business_purpose` | Why a hotelier should care |
| `business_rule` | The obligation, stated precisely |
| `severity` | CRITICAL / HIGH / MEDIUM / LOW |
| `blocking` | RELEASE / CERTIFICATION / OPERATIONAL / INFORMATIONAL |
| `data_sources` | Tables read |
| `canonical_engine` | Which engine it goes through, or "none" |
| `validation_method` | How it is measured, and why that way |
| `evidence_produced` | What a run leaves behind |
| `failure_message` | What a failure means |
| `likely_root_causes` | Where to start at 2am |
| `suggested_investigation` | The next three commands |
| `applicable_releases` | Version applicability |
| `applicable_business_dates` | Temporal applicability |
| `commissioning_status` | Whether it has been shown to be able to fail |

The measurement function is the smallest part of it. The fields that are
hard to write — `business_purpose`, `likely_root_causes`,
`suggested_investigation` — are exactly the ones that expose an invariant
nobody has thought through, and **registration refuses a declaration that
leaves any of them empty**. The registry is therefore a statement of what
the system owes, not a bag of checks.

### 1.2 The extension point

Adding an invariant is one `@invariant(...)` declaration in a rules
module. No list to update, no dispatch table, no engine edit. That is the
whole mechanism and deliberately the only one, because it is what makes
the standing rule enforceable: *any future financial feature, report,
night-audit enhancement or accounting change must register its invariants
before implementation is permitted*.

Registration validates at import time and raises on:

* a duplicate id — two invariants answering to `INV-A01` would make every
  report ambiguous and every historical comparison wrong;
* an unknown category, severity, blocking level or mode;
* an empty required field;
* no `principles` — an invariant enforcing nothing in the constitution is
  a preference, not an obligation;
* **neither a `negative_seed` nor a `negative_patch` nor a stated
  `not_seedable_reason`.** Under P9, "how would this break?" is a
  question for the moment the invariant is written, not for whenever
  somebody gets round to commissioning it.

### 1.3 The commissioning gate

An invariant that has only ever reported HOLDS has not been shown to
detect anything. It might be comparing a number to itself; its filter
might exclude the very rows it was written for.

So `commissioning_status` is part of the declaration, and until it reads
`COMMISSIONED` the invariant's result is **reported but excluded from
every verdict**. That is the mechanism behind "no invariant may enter
production until commissioning passes".

A declaration in code is the right gate — flipping it is a deliberate act
a reviewer can see — but it is also a gate somebody can walk through
without doing the work. So the claim is **cross-checked against the most
recent commissioning evidence pack**. An invariant declaring
`COMMISSIONED` that the last commissioning run did not pass makes the
entire run `UNVERIFIED`, not merely that invariant.

### 1.4 Two fault-injection routes

Most invariants are broken by mutating data. A few are internal
consistency checks — they assert that a canonical engine's own outputs
agree with each other — and **no data mutation can break those**, because
every input moves both sides together. The only thing that can break them
is the code, and Wave 0 forbids changing it.

For those, the fault is injected at the **engine boundary**: the returned
value is perturbed inside the commissioning subprocess only, through a
wrapper installed on the imported module object. No file under `app/` is
touched and nothing survives the process. `INV-A01` is commissioned this
way; the other twenty-three take data seeds.

### 1.5 Zero writes, measured

`db_writes` is counted on both paths — statements issued through the
context's `mode=ro` connection, and statements SQLAlchemy issues on the
application's behalf, classified by leading keyword. The listener is
installed *after* `create_app()` finishes, because application boot
legitimately writes to the copy; counting those would make the
measurement meaningless rather than strict.

One write anywhere fails the run outright, whatever the invariants
reported. A verification engine that modified the system it was verifying
would invalidate its own findings.

### 1.6 Determinism and order independence

Both are measured, not asserted. Every run evaluates the registry three
times: forward, forward again, and in reverse declaration order. The
comparison is over the *finding* — status, population, violation count,
affected objects, observed result — and deliberately not over timings,
memory or read counts, which legitimately vary and would make the control
fire on noise. A control that cries wolf is switched off.

### 1.7 Status vocabulary

`HOLDS`, `VIOLATED`, `VACUOUS`, `NOT_APPLICABLE`, `ERROR`.

`VACUOUS` exists because an invariant evaluated over an empty population
was not tested. Reporting it as HOLDS would make the engine exactly the
kind of control that cannot fail (P10). A VACUOUS result keeps the run at
`INCOMPLETE`, never `PASS`.

---

## 2. Implementation summary

### Files created

| File | Lines | Purpose |
|---|---|---|
| `verification/invariants/__init__.py` | 77 | Package contract |
| `verification/invariants/model.py` | 393 | Invariant, Evidence, Violation, Metering; the vocabularies; P1–P12 |
| `verification/invariants/registry.py` | 303 | Registration, validation, selection, matrices, the commissioning cross-check |
| `verification/invariants/context.py` | 256 | Read-only connection, application, scope, metering |
| `verification/invariants/engine.py` | 447 | Execution pipeline, determinism and order proofs, zero-write enforcement |
| `verification/invariants/helpers.py` | 99 | Decimal handling, verdict, scope clauses |
| `verification/invariants/rules_a.py` | 673 | Class A — accounting (6) |
| `verification/invariants/rules_b.py` | 698 | Class B — temporal (6) |
| `verification/invariants/rules_c.py` | 634 | Class C — domain (6) |
| `verification/invariants/rules_d.py` | 627 | Class D — referential (6) |
| `verification/invariants/history.py` | 273 | Historical replay, earliest divergence |
| `verification/invariants/commission.py` | 477 | Eight-element commissioning with fault injection |
| `verification/invariants/report.py` | 543 | Registry, run and history reports; evidence packs |
| **Total** | **5,500** | |

### Files modified

**Inside the PVF only. No file under `app/` was touched.**

| File | Change |
|---|---|
| `verification/__main__.py` | Added `inv-registry`, `inv-run`, `inv-history`, `inv-commission`, `_inv_json` |
| `verification/__init__.py` | Version 0.3.0 → 0.4.0; deliverable status |
| `verification/README.md` | D4 commands, classes, gates, limitations |

### Interfaces introduced

```python
Invariant(...)                      # the declaration (frozen dataclass)
@invariant(**declaration)           # registration decorator — the extension point
Context(db_path, app, scope)        # what an invariant may reach
Scope(mode, business_date, ...)     # validation modes
InvariantResult / Evidence /
Violation / Metering                # the evidence model
engine.run(...) -> EngineRun        # the pipeline
engine.evaluate_database(...)       # in-process evaluation of a prepared DB
history.run_history(...)            # temporal replay
```

An invariant function's contract is
`fn(ctx) -> (status, population, violations, extras)`.

### Execution pipeline

1. Copy production through the SQLite backup API, fingerprint the
   original.
2. Freeze the clock to the scope's business date, or the dataset's.
3. Build the Flask application bound to the copy; **then** start metering.
4. Evaluate each invariant in isolation, each metered independently.
5. Re-evaluate forward and in reverse for the determinism proofs.
6. Re-verify production is byte-identical.

### Configuration

None. There are no tunables, no thresholds file and no severity
overrides: an invariant's severity and blocking level are part of its
declaration, so changing them is a reviewable code change rather than a
config edit nobody sees.

### D1–D3 reuse

`dbcopy`, `config`, `golden.freeze`, `golden.capture.FREEZE_TIME`,
`golden.report.write_pack` and `replay.timeline` are used **unchanged**.
No D1, D2 or D3 module was edited. All three were re-run after these
changes: D1 PASS, D2 16/16, D3 `replay-verify` PASS with 0 differences.

---

## 3. Invariant registry

24 invariants, six per class.

| ID | Title | Sev | Blocking |
|---|---|---|---|
| INV-A01 | Settlement identity: grand total − payments − company credit = balance | CRITICAL | RELEASE |
| INV-A02 | Every financial row belongs to a folio | HIGH | CERTIFICATION |
| INV-A03 | Charges summed over folios equal charges summed over reservations | HIGH | RELEASE |
| INV-A04 | Daily collections equal the direct payments recorded for the day | CRITICAL | RELEASE |
| INV-A05 | Every stored tax line equals its taxable base times its rate | CRITICAL | CERTIFICATION |
| INV-A06 | A guest who has paid more than they owe has an overpayment record | HIGH | CERTIFICATION |
| INV-B01 | No financial row was created into a business date after that date closed | CRITICAL | RELEASE |
| INV-B02 | Every frozen night-audit snapshot matches its stored hash | CRITICAL | RELEASE |
| INV-B03 | Recomputing a closed day reproduces the figures it reported | CRITICAL | RELEASE |
| INV-B04 | Exactly one business date exists and no activity is dated beyond it | CRITICAL | RELEASE |
| INV-B05 | Night audits form an unbroken sequence up to the business date | HIGH | CERTIFICATION |
| INV-B06 | A payment is never dated outside the stay it belongs to | MEDIUM | OPERATIONAL |
| INV-C01 | A walk-in reservation is never settled through an OTA receivable | CRITICAL | CERTIFICATION |
| INV-C02 | A checked-out reservation is settled, or its balance is explained | HIGH | CERTIFICATION |
| INV-C03 | Every financial event belongs to a reservation that exists | CRITICAL | RELEASE |
| INV-C04 | No room is occupied by two reservations on the same night | HIGH | CERTIFICATION |
| INV-C05 | An OTA settlement identifies the agent it will be collected from | MEDIUM | OPERATIONAL |
| INV-C06 | Corporate credit is backed by a company account that exists | HIGH | CERTIFICATION |
| INV-D01 | Every folio references a reservation that exists | CRITICAL | RELEASE |
| INV-D02 | Every correction and reversal references the transaction it corrects | CRITICAL | RELEASE |
| INV-D03 | Every payment references a payment mode that exists | CRITICAL | RELEASE |
| INV-D04 | Every tax line names the charge it was raised on | HIGH | CERTIFICATION |
| INV-D05 | Every void request and credit note references what it cancels | HIGH | CERTIFICATION |
| INV-D06 | Every priced room night belongs to a stay that covers that night | HIGH | RELEASE |

The full register — all seventeen fields per invariant — is printed by
`python -m verification inv-registry` and stored in the evidence pack.

---

## 4. Category matrix

```
CATEGORY            CRITICAL      HIGH    MEDIUM       LOW   TOTAL
A-ACCOUNTING               3         3         0         0       6
B-TEMPORAL                 4         1         1         0       6
C-DOMAIN                   2         3         1         0       6
D-REFERENTIAL              3         3         0         0       6
```

### Constitutional coverage — P1 to P12

| Principle | Enforced by |
|---|---|
| P1 One canonical derivation | 14 invariants |
| P2 Frozen historical values remain immutable | INV-B01, B02, B03 |
| P3 Reports consume canonical engines | INV-A04, INV-D03 |
| P4 Night Audit orchestrates rather than derives | INV-B03 |
| P5 Validation occurs at the service layer | 15 invariants |
| **P6 Evidence must be capable of falsifying a change** | **structural** — registration refuses an invariant with no declared way to fail |
| P7 Closed periods are append-only | INV-B01, B02, B03, B05 |
| P8 One temporal basis | INV-A04, B03, B04, B05, B06, D06 |
| **P9 Controls must be capable of failure** | **structural** — the commissioning gate |
| **P10 Absence of evidence is not evidence of correctness** | **structural** — VACUOUS is never HOLDS |
| P11 Observable correctness | 9 invariants |
| P12 Historical immutability | INV-B01, B02, B03 |

Three principles are obligations of the *verification framework* rather
than of the system, and are enforced structurally. Listing them as
"uncovered" would be as misleading as quietly counting them as covered,
so the registry states which mechanism enforces each.

**Honest gap:** P2 and P4 have no invariant written specifically for
them. They are covered as a side effect of the Class B rules. Recorded,
not papered over.

---

## 5. Severity matrix

```
SEVERITY             RELEASE   CERTIFICATION     OPERATIONAL   INFORMATIONAL
CRITICAL                  10               2               0               0
HIGH                       2               8               0               0
MEDIUM                     0               0               2               0
LOW                        0               0               0               0
```

Severity is about the world; blocking is about the process. They are
deliberately separate — a HIGH finding can be certification-blocking
(explain it before the books are signed) without stopping a release.

### Validation modes

| Mode | Invariants |
|---|---|
| ENTIRE_DATABASE | 24 |
| RELEASE_VERIFICATION | 24 |
| CONTINUOUS_MONITORING | 24 |
| REGRESSION_DATASET | 23 |
| BUSINESS_DATE / NIGHT_AUDIT / HISTORICAL_REPLAY | 8 |
| SINGLE_RESERVATION | 3 |
| GOLDEN_MASTER | 0 — declared and reported as unexercised |

`GOLDEN_MASTER` is printed with a count of zero rather than omitted,
because a mode nothing declares is a run that would evaluate nothing and
report PASS.

---

## 6. Commissioning report — 26/26

Every invariant, eight elements each, plus two registry-wide controls.

| Control | Result |
|---|---|
| NULL-CONTROL — identical data must produce identical results | PASS, 0 spurious movements across all 24 |
| WRITE-CONTROL — the engine performs zero writes | PASS, 0 write statements counted |

| Route | Count |
|---|---|
| Data seed | 23 |
| Engine patch | 1 (INV-A01) |
| Not seedable | 0 |

Detection for an invariant already failing on live data cannot be a
status change — it was already VIOLATED. It is proven by the violation
count **rising**, which the suite handles explicitly:

```
INV-A01  engine patch  status HOLDS -> VIOLATED
INV-A02  data seed     already violated on live data; violations 40 -> 41
INV-A03  data seed     already violated on live data; violations  5 -> 6
INV-B03  data seed     already violated on live data; violations  1 -> 2
INV-C01  data seed     already violated on live data; violations  5 -> 6
INV-C04  data seed     already violated on live data; violations  1 -> 3
INV-C05  data seed     already violated on live data; violations  5 -> 6
INV-A06  data seed     status VACUOUS -> VIOLATED
INV-C06  data seed     status VACUOUS -> VIOLATED
INV-D02  data seed     status VACUOUS -> VIOLATED
INV-D05  data seed     status VACUOUS -> VIOLATED
(the remaining 13)     status HOLDS   -> VIOLATED
```

A green baseline is deliberately **not** required for the positive case.
Several invariants legitimately fail on live production data — that is
the point of the engine — and demanding HOLDS would mean deleting the
findings in order to commission the finder. What is required is that the
invariant *evaluated*: a status, a population, and no error.

---

## 7. Fault injection results — and what commissioning found in the engine

The first commissioning run reported **21/26**. Every one of the five
failures was a defect in this deliverable, found by its own commissioning
suite. All five are recorded here rather than quietly fixed, because the
distinction between "the seed was broken" and "the invariant was blind"
is exactly what a commissioning suite exists to draw.

### 7.1 A tautological invariant — the important one

`INV-A04` compared `get_cash_revenue(d)` against a ledger sum that used
**the same INNER JOIN the engine uses**. The seeded fault — a payment
pointing at a payment mode that does not exist — was dropped by *both*
sides. They agreed, the money vanished from the day's cash figure, and
the invariant reported HOLDS.

That is the precise failure mode a financial invariant engine exists to
avoid: a control that appears to cross-check and in fact self-checks.

The rule was **widened, not the seed weakened**. The ledger side now
LEFT-joins and totals anything landing in neither the direct nor the OTA
bucket, and the business rule now reads "…and no non-voided payment falls
outside the classification". `INV-A04` now moves HOLDS → VIOLATED on the
seed.

### 7.2 Two seeds that could not bite

* `INV-A02` seeded `UPDATE payments SET folio_id = NULL WHERE folio_id IS
  NOT NULL`. On this dataset **every** payment is already unrouted, so
  the subquery returned NULL and the statement matched nothing. Reported
  as a broken seed, not as an undetected fault. The seed now *inserts* an
  unrouted row.
* `INV-D04` seeded `charge_source_id = NULL`. That column is `NOT NULL`;
  the statement raised `IntegrityError`. The seed now points the line at
  a night the guest never stayed.

### 7.3 A seed that swapped one violation for another

`INV-A03` re-routed an existing charge to a mismatched folio. Since every
charge is already unrouted, that merely moved it from one violation
category to another and left the count unchanged. The seed now *adds* a
cross-routed charge.

### 7.4 A seed that landed on the one justified case

`INV-C02` added an unpaid charge to the lowest-id checked-out
reservation — which happens to carry a 200.00 credit arrangement, so the
balance was correctly treated as justified. The seed now selects a
reservation with no credit.

### 7.5 A false positive in an invariant

`INV-D04` originally knew only about integer source ids and reported all
sixty `room_night` tax lines as unresolvable. `gst_service` writes the
composite key `night_<stay_date>`, which is a legitimate form. The
resolver now handles it, and the invariant went from 60 false positives
to HOLDS.

---

## 8. Historical replay compatibility

`python -m verification inv-history` replays every date-capable invariant
across the dataset's history: 28 business dates, 8 invariants, in 1.9 s.

### What it can and cannot answer

The database holds one state: the present one. There is no archive of
what it looked like on 27 May, so "was this invariant true then" **cannot
mean** "restore the database and evaluate". Claiming otherwise would be
the most damaging kind of false evidence, because it would look exactly
like the real thing.

Three things that *are* true statements are produced instead:

1. **As of the date** — evaluated scoped to that business date with the
   clock frozen to noon on it.
2. **As of today** — the same date-scoped invariant with the clock frozen
   to the current business date. A difference is clock-dependence: a
   present-tense query inside a date-scoped rule.
3. **Against the frozen record** — where a night audit closed the day,
   the snapshot is genuine historical state. `INV-B03` uses it.

**Earliest divergence** is reported with the population at that date,
because "first failed on 3 May" means something different when 3 May had
four hundred rows than when it had none.

### Result

```
ID        SEVERITY  EARLIEST FAIL   POP  CLOCK-DEP  TODAY
INV-A02   HIGH      2026-05-27       17          0     no
INV-A04   CRITICAL  —                 0          0  holds
INV-A05   CRITICAL  —                 0          0  holds
INV-B01   CRITICAL  —                 0          0     no
INV-B02   CRITICAL  —                 0          0     no
INV-B03   CRITICAL  2026-05-27        8          0     no
INV-B06   MEDIUM    —                 0          0  holds
INV-C01   CRITICAL  2026-05-27        3          0     no
```

Three invariants first diverge on 2026-05-27, the first trading day. No
invariant is clock-dependent on this dataset — which is a real result,
not an absent one: the control is proven live by D3's equivalent
commissioning, and here it reports zero.

Sixteen invariants declare no date-scoped mode and are **listed as not
replayed** with the reason, so a historical run's coverage is never
overstated.

---

## 9. Evidence model

Every evaluation produces an `Evidence` record, whether it passed or
failed. Evidence only for failures would leave "verified" indistinguishable
from "never ran" (P11).

| Field | Content |
|---|---|
| `inputs` | Populations, denominators, declared constants |
| `expected_result` | The obligation, as evaluated |
| `observed_result` | What was found, in one sentence |
| `variance` | The rupee or count difference |
| `confidence` | PROVEN / TRUNCATED / PARTIAL / NONE |
| `evidence_files` | Referenced artefacts |
| `affected_objects` | `type:id` for every violating row |
| `root_cause_candidates` | The declared causes, attached on failure |
| `timestamp` | UTC, second precision |
| `business_date` | The date under evaluation |
| `replay_context` | Which clock the question was asked under |

`confidence` degrades to `TRUNCATED` when the violation listing is capped
at 200. **The count is always exact**; only the listing is capped, and
the downgrade means a reader can never mistake the cap for completeness.

### Failure reporting

For each violated invariant the report produces: what it means, why it
matters, financial impact in rupees, population, violation count,
confidence, observed result, variance, the constitutional principles
engaged, the reports affected, the root-cause candidates, the recommended
investigation, and the affected objects with expected/observed per row.

---

## 10. Performance results

`ENTIRE_DATABASE`, 24 invariants, 28 reservations / 35 payments / 66 tax
lines:

```
Wall clock (whole run, incl. copy, app boot, 3 passes)  2.9 s
Evaluation only, 24 invariants                          661 ms
Database reads                                          674
Database WRITES                                           0   <-- counted
Rows examined                                           439
Peak memory (worst single invariant)                  4,641 KB

Slowest:  INV-B03  300 ms   83 reads  4,641 KB
          INV-A01  149 ms  169 reads  1,304 KB
          INV-A06  105 ms  171 reads    417 KB
          INV-C02   98 ms  129 reads    643 KB
```

The four slowest all go through `calculate_stay_amount` or
`NightAuditService` per row — the price of checking the canonical engine
rather than around it, and the reason `data_sources` and
`canonical_engine` are declared fields.

**Scalability.** Cost is linear in rows for the SQL invariants and linear
in reservations for the four engine-backed ones. `inv-history` is linear
in dates × date-capable invariants (28 × 8 in 1.9 s). Budget headroom
against the 15-minute Phase 2.6 limit is large; re-measure on a
production-sized dataset before relying on that.

**Production safety.** Read-only verified by SHA-256 before and after;
zero writes counted on both the raw connection and the SQLAlchemy engine;
determinism and order independence both proven on every run.

---

## 11. Findings produced

**No production code was changed. Everything below is recorded, not
fixed, per the standing Wave 0 instruction.**

```
Registered  24     HOLDS 14     VIOLATED 6     VACUOUS 4     ERROR 0
Release blocking      2
Certification blocking 5
Total violations     57
```

### 11.1 Every financial row in the system is unrouted — ₹40,374.14
**INV-A02, HIGH, certification-blocking**

All 35 payments and all 5 extra charges carry `folio_id = NULL`. Not
some — all. The Financial Constitution (Article V §3) requires every row
to belong to a folio; the folio is the unit a bill is issued against and
a company or OTA is invoiced on. Money that belongs to no folio cannot
appear on a split bill, cannot be reconciled downstream, and cannot be
attributed to anything.

D1 recorded this as a count. It is now costed: **₹40,374.14 of
unattributable money**.

### 11.2 The folio view of charges sees none of them — ₹729.85
**INV-A03, HIGH, release-blocking**

The reservation view totals ₹729.85 across 5 charges; the folio view
totals ₹0.00. The same money, sliced two ways, differs by 100%. This is
the direct consequence of §11.1 and is reported separately because a
release that fixed folio routing without fixing the double view would
close one and not the other.

### 11.3 A closed day's outstanding balance has moved — ₹199.99
**INV-B03, CRITICAL, release-blocking**

```
2026-05-27  night audit outstanding
    frozen at close : 0.16
    recomputed now  : 200.15
```

The same finding D3 produced, now expressed as a constitutional
violation rather than a drift measurement: a 200.00 credit approved on
**29 May** is being counted into the position of a day closed on **27
May**, because `folio_control` buckets reservations by
`Reservation.status`, a present-tense field.

### 11.4 Five walk-in guests were settled through OTA receivables — ₹7,977.92
**INV-C01, CRITICAL, certification-blocking**

| Payment | Reservation | Source | OTA head | Amount |
|---|---|---|---|---|
| 7 | 7 | Walk-in | Other OTA Paid | 1,435.50 |
| 10 | 10 | Walk-in | MMT Paid | 1,700.15 |
| 11 | 11 | Walk-in | EaseMyTrip Paid | 1,611.99 |
| 17 | 17 | Walk-in | Goibibo Paid | 1,700.15 |
| 28 | 28 | Walk-in | MMT Paid | 1,530.13 |

An OTA receivable posting says *a travel agent owes us this money and
will remit it*. For a guest who walked in off the street there is no
agent, so **₹7,977.92 is booked as owed by nobody**. Either the cash was
taken at the desk and is missing from the cash figure, or it was never
taken. Every one of these five reservations is `source = 'Walk-in'` with
`ota_channel` and `ota_booking_id` both NULL.

This also explains a figure D2 recorded without attributing: the ₹4,747.64
of "OTA settled" in the 27 May night audit is part of this.

### 11.5 The same five receivables cannot be collected from anyone
**INV-C05, MEDIUM, operational**

All five reservations carrying OTA postings have neither `ota_channel`
nor `ota_booking_id`. Even if the OTA head were right, there is no agent
and no reference to reconcile a remittance against.

### 11.6 Room 21 was sold twice on the same night
**INV-C04, HIGH, certification-blocking**

Reservations 20 and 27 both occupy room 21 on 2026-05-28. Two guests
cannot sleep in one room: either a room move was not recorded, or the
night was sold twice — in which case occupancy, ADR and RevPAR for that
night are all overstated.

### 11.7 Four invariants could not be tested at all
**VACUOUS — commissioned, but not exercised**

| Invariant | Why |
|---|---|
| INV-A06 overpayment recording | no overpaid reservation exists |
| INV-C06 corporate credit backing | no company, no corporate booking |
| INV-D02 correction/reversal traceability | no correction or reversal rows exist |
| INV-D05 void / credit-note traceability | neither table has a row |

Each is commissioned — a seeded fault makes it fail — but a commissioned
rule over an empty population still proves nothing about the data. Of
these, `INV-D02` matters most: it means the sign-flipping logic in
`signed_extra_charge_amount`, which D1's P02 also flagged as untested, has
never been exercised by live data. These need D6's regression datasets.

### 11.8 A latent hole found while commissioning, not while running
**INV-D03 / INV-A04**

Foreign keys are not enforced (`PRAGMA foreign_keys = 0`), so a payment
can point at a payment mode that does not exist. `night_audit_service.py:537`
treats a missing mode as **direct cash**; `kpi_helpers.get_cash_revenue`
inner-joins `PaymentMode` and **drops the row**. The same rupees would be
counted by one report and not the other. No such row exists today — which
is why commissioning had to create one.

### 11.9 Wave 1 triage list

Recorded, not acted on: unrouted financial rows (§11.1–11.2), the
retroactive credit on a closed day (§11.3), the walk-in OTA settlements
(§11.4–11.5), the double-sold room night (§11.6), the four untested
invariants (§11.7), and the orphan-mode cash hole (§11.8).

---

## 12. Rollback instructions

```bash
rm -rf verification/invariants/
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

D4 imports from `verification.dbcopy`, `verification.config`,
`verification.golden.freeze`, `verification.golden.capture`,
`verification.golden.report` and `verification.replay.timeline`. **Nothing
in D1, D2 or D3 imports from `verification.invariants`**, so removing D4
alone leaves them intact — verified by re-running all three after this
deliverable.

---

## 13. Acceptance against the D4 charter

| Success criterion | Actual | Met |
|---|---|---|
| Every invariant is registered | 24, validated at import | Yes |
| Every invariant is commissionable | 24/24, no `NOT_SEEDABLE` remaining | Yes |
| Every invariant produces evidence | Evidence record on pass and fail alike | Yes |
| Every invariant can fail | Demonstrated 24/24 by seeded fault | Yes |
| Every invariant supports historical replay | 8 date-capable and replayed; the other 16 declare no date-scoped mode and are listed with the reason | Partly, stated |
| Every invariant is deterministic | Proven every run: repeat pass + reverse-order pass | Yes |
| Zero production financial behaviour changes | 0 lines under `app/` | Yes |
| Extensible framework, not isolated assertions | One decorator; registration validates | Yes |
| Structured invariant object, 17 fields | All 17 required and enforced | Yes |
| Classes A/B/C/D | 6 each | Yes |
| Severity + blocking model | Both declared, kept separate | Yes |
| Multiple validation modes | 9 declared, 8 exercised | Yes |
| Evidence model complete | All 11 fields | Yes |
| Commissioning: 8 elements | All 8, per invariant | Yes |
| Failure reporting complete | 11 sections per violated invariant | Yes |
| Performance measured | Time, memory, reads, writes, rows | Yes |
| Database writes zero | 0, counted on both paths | Yes |

### Not covered, stated explicitly

- **Historical replay covers 8 of 24 invariants.** The other sixteen are
  whole-database rules with no date-scoped form. They are listed as not
  replayed rather than dropped.
- **P2 and P4 have no invariant of their own.** Covered as a side effect
  of Class B.
- **`GOLDEN_MASTER` mode is declared and unused.** Printed with a count
  of zero, because a mode nothing declares would evaluate nothing and
  report PASS.
- **Four invariants are VACUOUS on live data.** They need D6.
- **Financial impact is the sum of the amounts on violating rows.** It is
  an exposure figure, not an audited loss; INV-C04's impact is 0 because
  a double-sold room night carries no row amount, and that does not mean
  it is free.
- **Fault injection is one seed per invariant.** D5 is the deliverable
  that generalises this into a framework; D4 provides the two routes and
  the eight-element harness it will build on.

---

## 14. Position in Wave 0

```
D1  Financial Parity Harness      complete, commissioned  8/8
D2  Golden Master Framework       complete, commissioned 16/16
D3  Historical Replay Framework   complete, commissioned 21/21
D4  Financial Invariant Engine    complete, commissioned 26/26
```

D4 is the permanent constitutional verification engine. From this point
the standing rule is enforceable rather than aspirational: **any future
financial feature, report, night-audit enhancement or accounting change
must register its invariants before implementation is permitted**, and
registration will refuse a declaration that cannot state how it would
fail.

`FAIL` is the correct verdict. The engine is reporting six real
constitutional violations — two release-blocking — and it has been shown,
invariant by invariant, to be capable of reporting them.

**Next:** D5 — Fault Injection Framework.
