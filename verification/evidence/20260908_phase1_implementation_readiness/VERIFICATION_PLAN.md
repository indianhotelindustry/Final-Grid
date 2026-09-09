# Phase 1 — Verification Plan

**Directive:** FG-P1-IMPLEMENTATION-READINESS-20260908-01 · **HEAD:** `e69f2ac` · **Status:** PLAN ONLY. No test was written or run; no evidence created; no golden master recaptured.

Idiom: `verify.py` per slice in the Phase 2a shape (disposable copy from `dbcopy.make_copy()`, production hashed before and after, per-case expected/got, `result.json` + report). No test framework is installed (Phase 6); pytest is not introduced by Phase 1.

## 1. Global assertions in every slice

G-1 anchor `51dd83b7…30bc2` unchanged before/after · G-2 D11 freeze by id set (payments [1..6], charges [1,2] NULL before and after) · G-3 Phase 2a matrix 29/29 · G-4 port 5000 clear · G-5 `selfcheck` READ-ONLY VERIFIED · G-6 no schema change (`PRAGMA table_info` of `payments`, `extra_charges`, `folios` identical to baseline).

## 2. Per-slice tests

### Slice 2 — foundation
Positive: T-L01 every reservation-creation path → exactly one Folio A; resolver returns it. T-L03 with B present, resolver still returns A. Negative: T-L02 reservation inserted by raw SQL without a folio → CD-1 outcome (create+audit, or refuse per Q-1) and never NULL; T-L04 invalid reservation id → exception, no row. Invariants: INV-A02, INV-A03 HOLD on the copy. Regression: `ds-run` six datasets green.

### Slice 3 — originating writers (18 sites + 4 corrections + fixtures)
Positive: T-P01…T-P12, T-C01…T-C09 — post through the real function/route; assert `folio_id == Folio A id`; amounts/dates unchanged from baseline behaviour (dates unchanged unless Q-3). Negative: T-N01 a row constructed with `folio_id=None` on any application path is detected by the suite; T-N02 unauthorized role per writer per today's role set → refused, no row; T-N03 duplicate posting where idempotency exists (W-05 `idem:` key, W-13) → single row; T-A01 audit-write failure injected at each touched writer → financial row rolled back, HTTP 500/exception, no partial state; T-A02 POS: charge and audit commit together or not at all; T-X01 correction of a NULL-folio original (only D11 rows) → refused (Q-2 default). Invariants: INV-A02/A03 HOLD on the new-activity copy; INV-B06 (payment dated inside stay) unchanged; FLT-B02 negative seed still fires. Regression: production `inv-run` verdicts identical to baseline; `ds-run` green; seed database no longer a counterexample (CD-4).

### Slice 4 — room rent / night audit / upsell
Positive: T-R01 fresh stay on a copy, night audit run → `room_rent` rows attributed to Folio A, `ReservationNightRate.is_posted/is_locked/posted_charge_id` set; T-R02 rerun posts nothing; skipped-audit rerun attributes and is idempotent; T-R03 upsell attributed; T-R04 `calculate_folio_amount` excludes room revenue exactly as before. Negative: T-R05 rerun for an already-posted date creates no row; T-R06 night audit on a copy with a NULL Folio-A fault → CD-1 path or refusal, never a NULL room-rent row. Invariants: INV-A02/A03 HOLD; INV-B01/B02/B03 HOLD after close; INV-B04/B05 unchanged. Idempotency: explicit. Business date: `charge_date == business date` for every posted row.

### Slice 5 — reconciliation
Positive: T-N01 folio-level == reservation-level for every reservation on datasets and the new-activity copy. Negative: T-N03 a deliberately mis-attributed row on a copy surfaces as a warning row, not averaged away (P11). Invariants: INV-B03 unchanged for 2026-08-09; snapshot JSON keys unchanged. Golden master: night-audit surfaces show a declared difference (the new row) and nothing else.

### Slice 6 — classification evidence
The pack itself is the test: population count, D11 match on four attributes, remainder = 0.

### Slice 7 — gate
| Artifact | Satisfies |
|---|---|
| Layer 2 test record for every creation site | Gate A, F |
| Phase 2a matrix re-run | Gate B (inherited), G |
| `inv-run` production before/after — identical | Gate C, F |
| `inv-run` new-activity copy — A02/A03 HOLD, B01–B03 HOLD | Gate C, D |
| `ds-run` + `ds-coverage` six datasets green | Gate C, F |
| Parity: Q14 AGREED on datasets and new-activity copy; no other quantity moves | Gate C, G |
| `gm-verify` and `replay-verify` — declared differences only | Gate G |
| Completion report with §18 answerability, D11 freeze by id, baseline integrity record | Gate H, SC-1 |

Gates A–H are cited as the Master Plan cites them; their source text (TARGET-001) is unrecovered.

## 3. Invariant coverage map

| Invariant | Slices | Expected |
|---|---|---|
| INV-A02 every financial row belongs to a folio | 2–7 | HOLDS on datasets and new-activity copies; VIOLATED 8/8 on production by design |
| INV-A03 folio view == reservation view | 2–7 | HOLDS / VIOLATED as above |
| INV-A01 settlement identity, INV-A04 daily collections, INV-A05 tax lines, INV-A06 overpayment | all | unchanged |
| INV-B01 no row into a closed date, INV-B02 snapshot hash, INV-B03 closed-day recomputation, INV-B04 one business date, INV-B05 audit sequence, INV-B06 payment inside stay | 4, 5 | unchanged / HOLD |
| INV-C03 every financial event has a reservation | all | HOLDS |
| FK integrity | S8 only | `foreign_key_check` = 0 (already 0) |
| Audit coupling | 3 | T-A01/T-A02 |
| Idempotency | 3, 4 | T-N03, T-R02/R05 |
| Q14 folio partition parity | 7 | AGREED where attributed |

## 4. Regression corpus that must stay green

Six D6 datasets (`DS-CORE-WALKIN`, `DS-ACT-INHOUSE`, `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN`, `DS-ACT-GROUP`, `DS-ACT-SHIFT`) via `ds-run`/`ds-coverage`; `fault-run` (40 faults; INCOMPLETE remains INCOMPLETE until D7/D9 — not a Phase 1 regression); `replay-verify` (order-independence, zero drift over the two active dates); Phase 2a 29 cases; W1-R1/W1-R8 evidence surfaces.

## 5. Golden master

Current master captured 2026-08-03; `gm-verify` FAILs with 3,342 declared differences predating Phase 2a. **Rebaseline is required for Gate G to be meaningful** for Phase 1. Two options: (a) recapture before Slice 2 as a verification-only act (Q-4, recommended); (b) continue the Phase 2a discipline of declaring Phase 1's own differences on top of the stale set. Recapture is not performed now. Excel/PDF branches remain unverified (V5) and are declared uncovered at every gate.

## 6. Population-specific INV-A02/A03 declaration (required in every pack)

Datasets: HOLDS · new-activity copy: HOLDS · production copy: VIOLATED 8/8 (₹4,776.19) and INV-A03 VIOLATED, identical to the frozen baseline — expected under FD-010, declared, not papered over.
