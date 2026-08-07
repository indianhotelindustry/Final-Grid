# Wave 0 — Deliverable D1: Financial Parity Harness
## Completion Report

**Status:** COMPLETE — commissioned
**Date:** 2026-08-03
**Baseline:** DSBC Frontline v2.2.18
**Production code modified:** 0 lines
**Production data modified:** 0 rows

---

## 1. Technical design

A read-only measurement instrument that computes each of the 22 parity
quantities (Phase 2.6 §5) by **every implementation the codebase currently
contains**, and compares them against each other.

Two modes:

- **Cross-implementation** — today's mode. Reveals where the codebase
  already disagrees with itself. Produces the pre-migration baseline.
- **Baseline / compare** — the Wave 1+ release gate. Captures values on
  current code, then diffs after a change, reporting movement in *both*
  directions.

The second direction matters and is easy to omit: a value that held when
it was declared to move means the change did not take effect.

### Read-only architecture

```
instance/pms.db  ──[SHA-256]──> fingerprint
       │
       │ sqlite3 connect(mode=ro).backup()
       ▼
verification/_work/pvf_working.db  ──> create_app(DATABASE_URL=copy)
       │                                      │
       │                                      ▼
       │                              22 measurements
       ▼                                      │
instance/pms.db ──[SHA-256]──> re-verify  <───┘
```

`create_app()` writes — legacy migrations, the SQLite column fixer and
`init_data()` seeding all commit. The copy absorbs them. The production
fingerprint is re-verified at the end of every run and a mismatch aborts
with `ProductionWriteDetected`.

---

## 2. Files created

| File | Lines | Purpose |
|---|---|---|
| `verification/__init__.py` | 48 | Package contract and deliverable status |
| `verification/config.py` | 152 | Paths, variance policies, severities, verdicts |
| `verification/dbcopy.py` | 168 | Safe copy + read-only proof |
| `verification/evidence.py` | 238 | Evidence pack writer (JSON + text) |
| `verification/quantities.py` | 780 | The 22 measurement functions |
| `verification/runner.py` | 196 | Orchestration, baseline, compare |
| `verification/commission.py` | 306 | Seeded-fault commissioning |
| `verification/__main__.py` | 168 | CLI |
| `verification/README.md` | — | Operating documentation |

## 3. Files modified

**None.** No file under `app/`, no configuration, no dependency, no
database object. Verified: zero `.py` files under `app/` carry a
modification timestamp from this session.

## 4. Database impact

**None.** Production SHA-256 `f07b090a…5aeb2c` identical before and after
every run including the eight seeded-fault runs. No schema change, no row
change, no migration.

---

## 5. Risk assessment

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| Harness writes to production | Critical | `mode=ro` source connection; hash verified before and after; all app instances bound to the copy | None — empirically verified |
| Harness reports false agreement | Critical | `VACUOUS` verdict for empty populations; `NOT_IMPLEMENTED` never counts as pass; commissioned by seeded faults | None for the 8 commissioned quantities |
| Harness gives a false positive | High | Found and fixed during commissioning (P15 compared descriptive labels, not figures) | Low |
| Non-determinism makes diffs noisy | High | Two independent runs produced byte-identical verdicts and values | None |
| Runtime causes the gate to be skipped | Medium | 3.6 s against production-sized data; budget is 900 s | None |
| Evidence stored inside the application | Medium | Documented; export is a release-process responsibility | Accepted, tracked |

---

## 6. Verification evidence

### 6.1 Read-only guarantee

```
production : instance/pms.db  (733,184 bytes)
sha256 before : f07b090a40452453392ee14996ee9ccb93c454e9e26ffaad6c6d2a86a85aeb2c
sha256 after  : f07b090a40452453392ee14996ee9ccb93c454e9e26ffaad6c6d2a86a85aeb2c
copy method   : sqlite-backup-api
VERDICT       : READ-ONLY VERIFIED
```

### 6.2 Measurement run

```
AGREED           10
SINGLE_SOURCE     1
DIVERGED          6
VACUOUS           2
NOT_IMPLEMENTED   3
ERROR             0
TOTAL            22

OVERALL          FAIL   (exit code 1)
runtime          3.61 s   (budget 900 s)
```

`FAIL` is the correct and expected verdict. The harness is reporting the
defects the governing documents already identified; a `PASS` here would
mean the instrument was not working.

### 6.3 Determinism

Two independent runs, 22 quantities compared on verdict **and**
implementation values: **0 differing**. `compare` against the stored
baseline reports "No change against baseline".

### 6.4 Seeded-fault commissioning (Principle 9)

| Seed | Target | Fault injected | Result |
|---|---|---|---|
| S-P03 | P03 | Post a `room_rent` ledger row | AGREED → DIVERGED **detected** |
| S-P04 | P04 | Same, at date level | AGREED → DIVERGED **detected** |
| S-P09 | P09 | Insert a payment reversal | AGREED → DIVERGED **detected** |
| S-P02 | P02 | Insert a charge reversal | AGREED → DIVERGED **detected** |
| S-P07 | P07 | Corrupt a stored tax line | AGREED → DIVERGED **detected** |
| S-P15 | P15 | Tamper with a stored audit total | AGREED → DIVERGED **detected** |
| S-P22 | P22 | Record an OTA payout | value moved 0.00 → −1000.00 **detected** |
| S-P14 | P14 | Route a charge to a folio | value moved 0.00 → 0.15 **detected** |

**8 / 8 detected. COMMISSIONING PASS.**

The first commissioning attempt **failed** (6/8) and the failure was real:
for quantities already diverging, detection was keyed on the divergence
*count*, which does not move when a quantity emits one aggregate
divergence whose *magnitude* changes. The criterion now compares measured
values. This is Principle 9 operating on the commissioning logic itself.

---

## 7. Findings reproduced independently

The harness re-derived every Phase 1 and Phase 2 financial finding from
live code paths, with no reference to the audit documents:

| Quantity | Finding | Measured |
|---|---|---|
| P06 | Night-audit taxable base double-counted | 75,893.34 raw vs 37,946.67 deduped — **2.00× exactly** |
| P12 | Two balance definitions per reservation | 6 reservations disagree; res 10 and 17 at +0.15 vs −0.15 |
| P13 | Contradictory settlement classification | 4 reservations classified differently by the two bases |
| P14 | Folio sub-ledger inert | 5 charges and 35 payments with `folio_id` NULL; folio sum 0.00 vs 729.85 |
| P20 | ADR has no date scope | `get_adr()` = 0.00 vs date-scoped 1,283.35 |
| P22 | OTA receivable never nets payouts | gross 7,977.92 vs net 0.00; **5 payments on OTA heads against non-OTA bookings** |

### New observation (not previously recorded)

`ota_reconciliation.get_ota_pending()` returned **−1000.00** under seed
S-P22 — a payout on a channel with no receivable produces a *negative*
receivable. A receivable that can go negative is arguably defective. This
is recorded as an observation for Wave 1 triage; **no action taken**, per
the standing instruction not to change financial logic during Wave 0.

---

## 8. Automated tests

The harness is self-verifying through three mechanisms rather than a
separate test suite, which does not yet exist (that is D2/W0.1):

1. `selfcheck` — proves the read-only guarantee in isolation.
2. `commission` — proves detection capability against 8 seeded faults.
3. `compare` — proves determinism by diffing a run against a baseline.

All three are CLI commands with meaningful exit codes, so they are
pipeline-ready for D8.

---

## 9. Rollback plan

```bash
rm -rf verification/
```

Complete. No production file, database row, schema object, configuration
value or dependency was modified; the application does not import this
package. To roll back while retaining evidence, move
`verification/evidence/` and `verification/baselines/` first.

Partial rollback is also safe: deleting `verification/_work/` at any time
is harmless, as copies are recreated per run.

---

## 10. Acceptance against Phase 2.6 W0.6 / W0.7

| Criterion | Required | Actual | Met |
|---|---|---|---|
| Covers all 22 quantities | 22 | 22 declared, 19 measured, 3 explicitly NOT_IMPLEMENTED | Partial — by design |
| Runs against a restore | Yes | Yes, via backup API | Yes |
| Deterministic | Yes | 0 differences across runs | Yes |
| Attributable to entity | Yes | Per reservation / date / shift / payment | Yes |
| Detects both directions | Yes | Value-move detection in compare mode | Yes |
| Under 15 minutes | < 900 s | 3.6 s | Yes |
| Fault-injection commissioned | All | 8/8 seedable detected | Yes |

**Three quantities (P16–P18) remain NOT_IMPLEMENTED and two (P11, P21)
are VACUOUS.** Per Principle 10 these are reported explicitly on every
run and the harness therefore reports `INCOMPLETE` rather than `PASS`
once the blocking divergences are resolved. Closing them requires D2
(Golden Master, for route-rendered surfaces) and D6 (Regression Datasets,
for refund/void and shift/cash populations).

---

## 11. Position in Wave 0

D1 is complete and commissioned. It is **not** sufficient on its own to
gate Wave 1 — the release gate requires D4 (invariants), D7
(certification) and D10 (gate framework), and full parity coverage
requires D2 and D6.

**Next:** D2 — Golden Master Framework, which also unblocks P16–P18.
