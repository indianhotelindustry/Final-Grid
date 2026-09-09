# Expected Phase 1 Deltas — against this Golden Master

Boundary wording follows `verification/evidence/20260908_phase1_implementation_readiness/PHASE1_EXECUTION_PLAN.md` (S0–S7 inside Phase 1; S8–S9 outside) and the Founder rulings Q-1…Q-6. **Nothing here is authorized by this document**; it states what a future verifier should expect to see move, and what must not move.

## 1. EXPECTED to change (when a Phase 1 execution authorization is issued and executed)

| # | Delta | Where it will show | Baseline value → expected |
|---|---|---|---|
| E-1 | **Originating financial writers gain authoritative folio attribution** — every new `payments` / `extra_charges` row carries the reservation's billing folio (Folio A) set at insert, via one service-layer resolver (ADR-002 R-1…R-6) | `FINANCIAL_BASELINE.json` for rows created after deployment; Layer 2 tests; INV-A02/A03 on new-activity copies | 0 attributed rows → every post-deployment row attributed; **the eight baseline rows stay NULL** |
| E-2 | **Missing-folio lifecycle follows Q-1** — a posting that finds no Folio A creates it through the authoritative lifecycle, audits it (`folio_auto_created`), attributes to it; fails closed if it cannot | new negative/positive tests; `audit_logs` may gain that action on copies | not reachable today → defined behaviour |
| E-3 | **Strict audit coupling on touched financial mutations (Q-5)** — mutation and its audit row succeed together or the operation rolls back; writers currently without an audit row gain one | `audit_logs` row per touched mutation on copies; audit-failure injection tests | A-NF / A0 → A-STRICT for touched writers |
| E-4 | **POS ordering corrected (Q-5)** — charge and audit commit together | `app/pos.py` tests | commit-then-audit → atomic |
| E-5 | **Room-rent financial ownership under *reservation operational ownership + folio financial ownership*** — night-audit `room_rent`, recovered room rent, and `room_upsell` rows attributed to the reservation's billing folio; idempotency and business-date handling unchanged; folio-balance meaning unchanged | new-activity copies with a night audit; INV-B01–B03 HOLD after close | NULL by design → attributed (no room-rent rows exist on the baseline) |
| E-6 | **Reconciliation reads the canonical relationship (unit 1.7)** — folio-level figure shown beside the reservation figure with an equality assertion; disagreement rendered as a warning row | night-audit surfaces in the golden master: **a declared difference** on those surfaces only; snapshot JSON keys unchanged; INV-B03 unchanged for 2026-08-09 | reservation-only → both figures |
| E-7 | **Fixtures under contract (CD-4)** — `seed.py` no longer produces NULL-folio rows | seeded copies | counterexample → compliant |
| E-8 | **Correction of a NULL-folio original is refused (Q-2)** | negative test on a copy against the D11 population | inherits NULL → refused |
| E-9 | **Verification outcomes** — INV-A02 and INV-A03: HOLDS on the six datasets and on new-activity copies; Q14 parity AGREED where attributed | `ds-run`, `inv-run` on copies | VIOLATED/DIVERGED → HOLDS/AGREED on those populations |
| E-10 | **Golden master** — a declared, enumerated set of surface differences attributable to E-6 (and any folio-view surface that now shows attributed rows on copies); everything else identical | `gm-verify --tag production` after Phase 1 | 0 differences → only declared differences |

## 2. NOT EXPECTED in Phase 1 (must remain identical to this baseline)

| # | Must not move | Reason |
|---|---|---|
| N-1 | **Production `inv-run` verdict**: still 26 registered · 17 HOLDS · 7 VACUOUS · 2 VIOLATED · INV-A02 8/8 ₹4,776.19 · INV-A03 ₹476.19 · overall FAIL | The eight rows are untouched (FD-010); any movement means Phase 1 touched history |
| N-2 | **The eight D11 rows** — identity, values, `folio_id NULL` | FD-010 Option A; Q-2 |
| N-3 | **Production database file** — hash `51dd83b7…`, 733,184 B — unchanged by Phase 1 *work* (deployment to a live site is a code release governed separately) | SC-1; PD-004/005/006 not triggered by S2–S7 |
| N-4 | **Broad business-date correction** — the eight wall-clock/model-default dating sites keep their basis; `payment_date`/`charge_date` defaults unchanged | Q-3; Phase 3 |
| N-5 | **Migration or retrospective attribution of the D11 rows** | FD-010; unit 1.6 has no authorized action |
| N-6 | **Schema** — `folio_id` stays nullable; no `NOT NULL`; no migration; schema fingerprint `a7428da6840e79dd…` unchanged | Master Plan Phase 1 "no schema migration"; AR-004 Stage G is Phase 5 |
| N-7 | **FK enforcement** — `PRAGMA foreign_keys` stays off in the application | ADR-005 is a requirement; enablement is Phase 4/5 (B-9) |
| N-8 | **Level 3 split billing** — no Folio B creation by writers, no company routing, no itemised split | FD-003; ADR-002 O-3 |
| N-9 | **Authorization** — Phase 2a frozen; `_FOLIO_ROLES` unchanged (FD-015 stays recorded-not-implemented unless the Phase 1 directive names it); report routes unchanged; no new endpoint or role | FD-016 / AR-009 |
| N-10 | **Unrelated financial refactoring** — `routes.py`/`reports.py` structure, `_write_audit` shared-helper behaviour for non-financial callers, void/refund control (N2), `calculate_folio_amount` semantics, `calculate_stay_amount`, invoice numbering, GST computation, night-audit lifecycle and closing, scheduler authority/timing, backup behaviour | Master Plan §19; Phase 2b/3/4/9 |
| N-11 | **Closed-day evidence** — INV-B01/B02/B03 HOLD; `night_audit_logs` snapshot for 2026-08-09 and its hash unchanged | P2/P7/P12 |
| N-12 | **Replay** — the 10 stored August dates reconstruct identically | replay-verify PASS baseline |

## 3. How a verifier should read a post-Phase-1 comparison

1. Run the same five commands as §7 of `GOLDEN_MASTER.md` against the same anchor; production results must match §2 above line for line.
2. Run them against a new-activity copy; results must match §1 (E-1, E-5, E-9).
3. Any `gm-verify` difference not enumerated in the Phase 1 completion report's declared list is a regression.
4. Any change to the eight rows, to N-3 or to N-6 is grounds to reject the work.
