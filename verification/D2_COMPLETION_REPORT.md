# Wave 0 — Deliverable D2: Golden Master Framework
## Completion Report

**Status:** COMPLETE — commissioned 16/16
**Date:** 2026-08-03
**Baseline:** DSBC Frontline v2.2.18
**Production code modified:** 0 lines
**Production data modified:** 0 rows
**Production SHA-256:** `f07b090a…5aeb2c` — identical before and after every run

---

## 1. Technical design

D1 measures the *engines*. D2 measures the *surfaces*: what a report,
dashboard or API endpoint actually renders. A figure that is correct in
the service layer and wrong on the screen is wrong.

For each catalogued surface the framework records:

| Recorded | Why |
|---|---|
| HTTP status, content type, redirect target | A report that 500s is the most important fact about it |
| Templates rendered | Detects a page silently swapped for another |
| Every numeric figure in the **template context**, by dotted path | The financially meaningful layer — the value the route computed |
| Every numeric leaf of a **JSON body** | What an API consumer actually reads |
| SHA-256 of the **normalised body** | Coarse net for presentation-only change |
| Status returned to an **anonymous** client | Turns the capture into an authorisation-regression detector for one extra request |

Figures are read from the template context, not scraped from HTML,
because HTML numbers have been through Jinja formatting, thousands
separators and rounding filters. Comparing those would confuse a
presentation bug with a financial one.

### Determinism: the frozen clock

The application reads the wall clock in roughly 150 places. Left alone,
every master would differ from itself the next day, the framework would
cry wolf daily, and the first thing anyone under deadline pressure would
do is switch it off.

The clock is therefore pinned to **noon on the business date** — inside
the trading day, away from the midnight rollover the night audit
straddles. Two patches are applied, because the application binds
`datetime` two ways:

1. `datetime.datetime` / `datetime.date` are replaced **on the datetime
   module**, covering function-local imports and every module imported
   afterwards.
2. Already-imported namespaces are rescanned and rebound **by identity**,
   covering aliases such as `from datetime import datetime as _dt`.

The fakes carry a metaclass whose `__instancecheck__` delegates to the
real class, so `isinstance(a_real_date, date)` keeps working after the
patch. Getting that wrong would silently change application behaviour
under test — the harness would lie rather than fail.

`freeze.prove()` is positive evidence that the freeze is in force, tested
through all three binding paths. If it cannot be proven, capture aborts.

### Read-only architecture

Unchanged from D1 and reused wholesale: `mode=ro` source connection,
SQLite backup API, SHA-256 verified before and after, the application
only ever bound to the copy.

---

## 2. Files created

| File | Lines | Purpose |
|---|---|---|
| `verification/golden/__init__.py` | 48 | Package contract |
| `verification/golden/freeze.py` | 243 | Deterministic clock + its proof |
| `verification/golden/catalogue.py` | 453 | Surface catalogue, classification, declared exclusions |
| `verification/golden/client.py` | 74 | Authenticated + anonymous test clients |
| `verification/golden/normalize.py` | 217 | Normalisation rules, figure extraction |
| `verification/golden/capture.py` | 409 | Capture engine and master storage |
| `verification/golden/compare.py` | 205 | Difference classification and severity |
| `verification/golden/commission.py` | 551 | Four-class seeded-fault commissioning |
| `verification/golden/report.py` | 229 | Evidence packs |
| `verification/golden/surfaces.py` | 84 | Render-and-read-context helper used by D1 |
| **Total** | **2,513** | |

Plus `verification/masters/production/` — 158 master records and an index.

## 3. Files modified

**Inside the PVF only. No file under `app/` was touched.**

| File | Change | Why |
|---|---|---|
| `verification/__main__.py` | Added `gm-capture`, `gm-verify`, `gm-commission`, `_gm_capture_json` | CLI surface for D2 |
| `verification/__init__.py` | Version 0.1.0 → 0.2.0; deliverable status | Bookkeeping |
| `verification/quantities.py` | **Implemented P16, P17, P18**; added `self_compared` to the quantity registry; `compare(pairwise=…)` | D1 deferred these to D2 because they needed an authenticated client, which D2 provides |
| `verification/commission.py` | Updated the not-seedable reasons for P16–P18 | They are no longer NOT_IMPLEMENTED |
| `verification/README.md` | D2 commands, artifacts, limitations | Documentation |

## 4. Database impact

**None.** No schema change, no row change, no migration. Production
SHA-256 identical before and after every capture, verification and
commissioning run, including all nine seeded-fault runs.

---

## 5. Risk assessment

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| Harness writes to production | Critical | D1's `mode=ro` + hash verification, reused unchanged | None — empirically verified |
| Clock frozen to the wrong day | Critical | **Occurred during development.** `SELECT current_date` was parsed by SQLite as its CURRENT_DATE keyword and returned the wall-clock date. Now quoted, and the pre-read is cross-checked against `get_business_date()`; a mismatch aborts capture | None — the control that would have caught it now exists |
| Freeze silently ineffective | High | `prove()` tests all three binding paths; capture aborts if unproven. Commissioning seed S-GM-CLOCK proves the freeze is load-bearing | None |
| Normalisation hides a real difference | High | Only three rules, each empirically justified; two drafted rules were **deleted** because they never matched. Hit counts are stored per surface, so a rule that stops applying is itself reported | Low |
| False positives make the gate noisy | High | Null control (S-GM-NULL) and comparator null control both required to report zero | None — 158/158 clean across independent runs |
| Session injection diverges from real login | Medium | Injects exactly what Flask-Login writes; anonymous status captured alongside every surface as an independent authorisation control | Low — the login flow itself is not verified, stated as a limitation |
| A page renders differently for another role | Medium | Not covered. One identity is captured; a role matrix is not a Wave 0 deliverable | Accepted, documented |
| Evidence stored inside the application | Medium | Inherited from D1; export is a release-process responsibility | Accepted, tracked |

---

## 6. Verification evidence

### 6.1 Coverage

```
Surfaces captured : 158        Figures captured : 8,754
Healthy           : 144        Declared gaps    : 150
Unhealthy         :  14        Runtime          : 11.3 s
FINANCIAL         :  80
OPERATIONAL       :  49
ADVISORY          :  23
PUBLIC            :   6
UNCLASSIFIED      :   0
```

Every one of the 150 gaps carries a stated reason and is printed on every
run. 117 are non-GET routes; 15 are parameterised routes not yet
declared; 5 are UNRESOLVED because no matching entity exists in the data;
the remainder are declared exclusions (destructive, network-reaching,
token-gated, or guest documents).

### 6.2 Determinism

Two independent runs, separate processes, fresh copies:

```
Surfaces compared : 158
Surfaces clean    : 158
Differences       : 0
VERDICT           : PASS
```

Achieved with **three** normalisation rules — CSP nonce, CSRF meta tag,
CSRF form input — firing 612 times in total. Two further rules were
drafted and deleted because they never matched anything; an unproven
masking rule can only ever hide a real difference.

### 6.3 Authorisation control

```
anonymous 302 (redirected to login) : 151
anonymous 200 (publicly readable)   :   5
anonymous 400 / 404                 :   2
```

The five publicly readable surfaces are `/api/health`, `/auth/login`,
`/book/`, `/book/api/rates` and `/feedback/complete` — all legitimately
public. Any route that later stops redirecting anonymous callers moves
from 302 to 200 and fails the comparison at BLOCK severity.

### 6.4 Commissioning — 16/16

**A. Data faults** — a mutation must reach the surface.

| Seed | Fault | Result |
|---|---|---|
| S-GM-PAYMENT | Post a 777.00 settlement | 23 surfaces reacted |
| S-GM-CHARGE | Post 333.00 to the pinned reservation | 19 surfaces reacted, including its own folio and invoice |
| S-GM-TAX | Corrupt one stored tax line by 100.00 | 2 surfaces reacted |
| S-GM-ROOM | Flip one vacant room to Dirty | 22 surfaces reacted |
| S-GM-RESERVATION | Raise one nightly rate by 1234.00 | 22 surfaces reacted |
| **S-GM-PAISA** | Move one nightly rate by **0.01** | **15 surfaces reacted** |

The paisa seed tests the claim that there is no tolerance band. A
rounding-tolerant comparison would let a systematic sub-rupee drift
through on every surface at once.

**B. Clock fault** — 21 surfaces moved when the frozen clock moved one
day. The freeze is load-bearing, not decorative.

**C. Comparator faults** — each mutation of a stored master produced
exactly the expected classification: `STATUS_CHANGED`,
`ANON_STATUS_CHANGED`, `FIGURE_CHANGED`, `FIGURE_ADDED`,
`TEMPLATES_CHANGED`, `BODY_CHANGED`, `SURFACE_ADDED`, at the expected
severity.

**D. Null controls** — identical data produced 0 differences; the master
set compared against itself produced 0 differences. A control that always
fires is as useless as one that never does.

### 6.5 A commissioning defect found by commissioning

The first run reported 13/16, and one of the three failures was a lie:
`S-GM-CHARGE` targeted a reservation with status `CheckedIn`, and this
dataset has **none** — all 28 reservations are `CheckedOut`. The
`INSERT ... SELECT` inserted zero rows, succeeded, and the suite reported
"fault not detected", which reads as a defect in the framework rather
than in the seed.

The suite now asserts rowcount after every seed and raises
`SeedDidNotApply`. A seed that did not bite is reported as a broken seed.
This is Principle 11 applied to the commissioning harness itself.

### 6.6 A false positive found and removed

P16 initially reported DIVERGED while all seven of its concept pairs
agreed. Cause: `compare()` flat-compares every implementation against the
first, so it was comparing ADR against accrual revenue. Multi-concept
quantities are now declared `self_compared=True` and carry their own
per-concept comparisons. Confirmed by re-running D1 commissioning:
still **8/8**.

---

## 7. Automated tests

As with D1, verification is by executable control rather than a separate
unit-test suite (that suite does not yet exist and is not a Wave 0
deliverable). Four CLI commands with meaningful exit codes, all
pipeline-ready for D8:

| Command | Proves |
|---|---|
| `gm-capture --dry-run` | Capture runs, coverage and gaps are reported |
| `gm-verify` | Determinism, and no drift against the stored masters |
| `gm-commission` | Detection capability across four fault classes |
| `verification commission` | D1 remains commissioned after the D2 changes |

---

## 8. Findings produced

**No production code was changed. Everything below is recorded, not
fixed, per the standing Wave 0 instruction.**

### 8.1 Eight surfaces do not render at all

| Surface | HTTP | Root cause |
|---|---|---|
| `/reports/daily-reconciliation` | 500 | `TemplateSyntaxError` — `url_for('…', **request.args, format='excel')` is invalid Jinja call syntax |
| `/reports/other-income-report` | 500 | Same pattern |
| `/reports/refund-report` | 500 | Same pattern |
| `/reports/tip-report` | 500 | Same pattern |
| `/reports/ar-aging` | 500 | `BuildError` — `url_for('main.guest_folio')` given `reservation_id`, needs `guest_id` |
| `/reports/guest-report` | 500 | `UndefinedError` — `r.arrival_date.strftime(…)` where `arrival_date` is a `str` |
| `/auth/shifts` | 500 | `AmbiguousForeignKeysError` — two FK paths between `shifts` and `users`, no explicit onclause |
| `/api/tab/reservations` | 500 | `TypeError` — a Jinja `Undefined` reached `json.dumps` |

Six are financial reports. Four share one Jinja incompatibility, which
suggests a library upgrade that was never re-verified against the
templates — precisely the class of regression this framework exists to
catch, and evidence that no such gate existed before.

### 8.2 A revenue alert detector is silently dead

`alert_engine._detect_revenue_alerts` raises
`TypeError: float() argument must be … not 'dict'` on every dashboard
render. The exception is caught and logged, so the dashboard renders
normally with **zero revenue alerts** — the failure is invisible to the
user. A control that fails silently is the exact shape Principle 11
forbids.

### 8.3 Three surfaces disagree about the same day (P16–P18)

For business date 2026-05-28, on identical data:

| Concept | Flash report | Front Office MIS | Dashboard | Canonical engine |
|---|---|---|---|---|
| Daily collections | 15,565.87 | **18,796.15** | 15,565.87 | 15,565.87 |
| ADR / ARR | 0.00 | **1,303.51** | 0.00 | 0.00 |
| Occupancy % | 0.0 | **38.5** | — | 0.0 |
| RevPAR | 0.00 | **501.35** | — | 0.00 |
| Departures completed | 12 | **0** | **0** | — |

- MIS overstates the day's collections by **₹3,230.28** against both the
  flash report and the canonical helper.
- The flash report and the dashboard agree with the engines on money, and
  **disagree with each other on operations**: 12 departures versus 0.
- MIS is the only surface reporting non-zero ADR, occupancy and RevPAR;
  the canonical helpers return zero because `get_adr()` averages the
  tariffs of *currently checked-in* reservations and there are none (the
  same defect P20 records).

This is the reported symptom — "report totals not matching dashboards" —
now quantified, attributed and reproducible.

### 8.4 Wave 1 triage list

Recorded, not acted on: the eight broken surfaces (§8.1), the dead alert
detector (§8.2), and the three-way daily disagreement (§8.3).

---

## 9. Rollback plan

```bash
rm -rf verification/golden/ verification/masters/
git checkout verification/__main__.py verification/quantities.py \
             verification/commission.py verification/__init__.py \
             verification/README.md
```

Or, to remove the whole PVF:

```bash
rm -rf verification/
```

No production file, database row, schema object, configuration value or
dependency was modified. The application does not import this package.
Deleting `verification/_work/` at any time is harmless.

The only cross-deliverable coupling is that `verification/quantities.py`
(D1) now imports `verification.golden.surfaces` for P16–P18. Removing
`golden/` without reverting `quantities.py` would make those three
quantities report ERROR — visibly, not silently.

---

## 10. Acceptance against Phase 2.6

| Criterion | Required | Actual | Met |
|---|---|---|---|
| Report verification | Yes | 80 financial surfaces captured | Yes |
| Dashboard verification | Yes | Dashboard, CEO, command centre, tab APIs | Yes |
| API verification | Yes | JSON surfaces captured by numeric leaf | Yes |
| Golden master testing | Yes | 158 surfaces, 8,754 figures | Yes |
| Deterministic | Yes | 0 differences across independent runs | Yes |
| Attributable | Yes | Per surface, per dotted figure path | Yes |
| Detects both directions | Yes | Added *and* removed figures and surfaces | Yes |
| Under 15 minutes | < 900 s | 11.3 s | Yes |
| Fault-injection commissioned | Yes | 16/16 across four fault classes | Yes |
| Coverage gaps stated | Yes | 150 gaps, each with a reason, printed every run | Yes |

### Not covered, stated explicitly

- **Role-based rendering.** One identity is captured. The anonymous check
  detects a route becoming public; it does not detect a route becoming
  visible to the wrong *role*.
- **Fifteen parameterised routes** remain undeclared (mostly AI/advisory
  and PDF/file downloads). Listed as gaps on every run.
- **Five declared surfaces are UNRESOLVED** — no checked-in reservation,
  no company — and will resolve when D6 supplies regression datasets.
- **Time-of-day behaviour.** The clock is frozen at noon; night-audit
  window and early-shift behaviour are not exercised.
- **POST surfaces.** Capture is GET-only by design; state-changing flows
  are D3 (Historical Replay).

---

## 11. Position in Wave 0

D2 is complete and commissioned. As a side effect it closed the last
three `NOT_IMPLEMENTED` quantities in D1, so the parity harness now
measures all 22:

```
                 before D2    after D2
AGREED               10          11
SINGLE_SOURCE         1           1
DIVERGED              6           8
VACUOUS               2           2
NOT_IMPLEMENTED       3           0
ERROR                 0           0
```

`FAIL` remains the correct overall verdict — the harness is reporting the
defects the governing documents predicted, plus three it did not.

**Next:** D3 — Historical Replay Framework.
