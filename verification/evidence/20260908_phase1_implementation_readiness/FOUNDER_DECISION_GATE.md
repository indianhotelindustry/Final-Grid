# Phase 1 — Founder Decision Gate

**Directive:** FG-P1-IMPLEMENTATION-READINESS-20260908-01 · **HEAD:** `e69f2ac`. Only decisions that genuinely require Founder input before Phase 1 execution. Implementation minutiae resolvable by engineering are not listed. Existing governance IDs are used where they exist; new questions are labelled `Q-n` (questions, not FD numbers — FD numbers are assigned by the Founder on ruling).

| ID | Question | Why it matters | Recommended default | Consequences | Blocks Phase 1? | Recommendation |
|---|---|---|---|---|---|---|
| **Q-1** (= CD-1, B-12) | When a posting path finds a reservation with no Folio A: create-and-audit, or refuse the posting? | Determines fail-closed shape of the resolver; affects front-desk continuity on a data fault | Create + audit (ADR-002 C-2) | Create: front desk keeps working, fault is audited. Refuse: stricter, surfaces the fault immediately, posting fails | Yes (Slice 2) | **Create + audit** |
| **Q-2** (new; extends R-3) | Correction/reversal of an original row whose `folio_id` is NULL: refuse (fail-closed) or resolve to the default folio? | The only NULL originals are the eight FD-010 rows; refusing also enforces FD-010 mechanically | Refuse | Refuse: a correction of a D11 row is impossible by code as well as by rule. Resolve: would attribute a D11-derived row, contradicting FD-010 | Yes (Slice 3) | **Refuse** |
| **Q-3** (new; scope) | May Phase 1 change the dating basis at the seven wall-clock writers and the model-default site it touches (W-08/09/22/23, W-10, W-11, W-20, W-17), or does dating stay Phase 3? | Changing `payment_date`/`charge_date` basis moves report figures and INV-A04/B06 populations; Master Plan places business-date derivation in Phase 3 unit 3.1 | Stay Phase 3 (Phase 1 = attribution only) | Attribution-only keeps Phase 1's declared movement to Q14 alone. Fixing dates now conflates two changes and complicates Gate C declaration | Yes (Slice 3 scope) | **Attribution only; dates in Phase 3** |
| **Q-4** (new; verification) | Authorize a golden-master recapture as a verification-only action before Slice 2 (Master Plan places rebaseline in Phase 6)? | Gate G is blind against a master from 2026-08-03 with 3,342 declared differences | Yes | Yes: Gate G detects Phase 1 regressions. No: Phase 1 declares its own differences on top of a stale set (Phase 2a precedent) | No (weakens Gate G) | **Yes — recapture** |
| **Q-5** (= Phase 2a default #3 extended) | Apply strict audit coupling (A-STRICT: prove-in-session, roll back on failure) to every financial writer Phase 1 touches, and re-order POS so charge and audit commit together? | A control-strictness change: today audit failure never blocks a commit (`_write_audit` never raises); POS commits before auditing | Yes | Yes: closes the confirmed atomicity gap for touched writers (Operation → Audit, ADR-008). No: attribution ships on writers that can commit without audit | Yes (Slice 3) | **Yes** |
| **Q-6** (new; sequencing) | Accept Slice 1 (Recovery Foundation: restore tool, rehearsal, retention) as a bounded pre-Phase-1 implementation, deviating from Master Plan Phase 9 placement? | Without it PD-006 is unsatisfiable and a deployed Phase 1 has no demonstrated data rollback; it is also the only way Stage E/G could ever be scheduled | Yes | Yes: recovery gate becomes satisfiable; Phase 9 unit 9.2 partially pre-empted. No: Phase 1 code can still be authorized on `git revert` rollback only, with data rollback undemonstrated | Yes for execution authorization (this plan) | **Yes — authorize as its own bounded directive** |

## Decisions deliberately **not** put to the Founder now

| Item | Why not now |
|---|---|
| B-3 disposition of the eight rows before NOT NULL | Not needed by any Phase 1 slice; Phase 5 |
| B-4 migration mechanism | Not needed by any Phase 1 code slice; needed for Stage G only; option analysis provided |
| B-1 scheduler controls ADR | Phase 1 does not change scheduler authority or timing; dependency recorded |
| B-2 maker-checker matrix | No Phase 1 writer requires approval; Phase 2b |
| MP-D9 operator profile | Phase 1 adds no endpoint or role |
| CD-3 (refund → default folio), CD-4 (fixtures under contract) | Defaults are unambiguous and consistent with ADR-002; listed under B-12 for confirmation at directive approval, not as blockers |
| Resolver name, helper placement, test file layout | Engineering |

## Execution authorization prerequisites (for the Founder's later directive)

1. Q-1…Q-6 ruled. 2. Slice 1 directive issued and rehearsal record produced. 3. `PHASE1_EXECUTION_PLAN.md` adopted (or re-issued) as the Phase 1 implementation directive, recorded in `FOUNDER_DECISIONS.md`. 4. Branch and commit policy per SC-6. Nothing else requires new architecture.
