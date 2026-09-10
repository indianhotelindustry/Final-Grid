# FinalGrid Phase 1 - Acceptance Recommendation

| | |
|---|---|
| Directive | FG-P1-ACCEPTANCE-PREP-20260909-01 (read-only governance preparation) |
| Prepared | 2026-09-10 |
| Baseline | `aa6d9e91e7294be731383f755d6998acf5f059fc` on `main`, pushed; `origin/main` identical; 0 tracked modifications |
| Production anchor | `instance/pms.db` 733,184 B - `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` - unchanged |
| Inputs | `20260909_phase1_completion_review/` (FG-P1-COMPLETION-REVIEW-20260909-01), `20260909_phase1_verification_completion/` (FG-P1-VERIFICATION-COMPLETION-20260909-01), `20260909_five_commit_execution/`, the Phase 1 execution, Golden Master, W-20 and Recovery Foundation packs |
| What this is | The package a Founder acceptance decision can be taken on. **It does not declare acceptance.** |
| Status | **PHASE 1 ACCEPTANCE PREPARATION PASS - FOUNDER GATE PENDING** |

Companion files: `FOUNDER_DECISION_ITEMS.md` (the decision table), `CARRY_FORWARD_REGISTER.md`, `SEMANTIC_REVIEW_REGISTER.md`, `result.json`.

## 1. Recommended status lines

| Layer | Recommended status | Basis |
|---|---|---|
| Phase 1 implementation | **COMPLETE** | All Master Plan units 1.1-1.5, 1.7, 1.8 implemented at `aa6d9e91`; unit 1.6 correctly has no action (FD-010). Boundary intact: no schema, migration, FK, NOT NULL, authorization, scheduler, retention, D11 or Level 3 change. Five-commit history published (`e69f2ac2` -> `aa6d9e91`). |
| Phase 1 verification | **COMPLETE WITH DOCUMENTED LIMITATIONS** | Completion review (option B) + bounded verification completion (decision B). No Phase 1 attribution regression found on any population. Limitations are enumerated, attributed and carried forward - none is hidden and none is a regression. |
| Phase 1 formal acceptance | **PENDING FOUNDER RESOLUTION** | Acceptance is a governance act (FD-018 durable records; completion-review gate G-2). Nothing in the repository records it yet; `FOUNDER_DECISIONS.md` ends at Founder Resolution Round 2. |

## 2. Settled verification facts

Recorded as established; each traces to a retained pack.

| # | Fact | Evidence |
|---|---|---|
| 1 | Phase 1 implementation is committed and published at `aa6d9e91` (five commits, parents exact, `origin/main` aligned) | `20260909_five_commit_execution/REMOTE_PUSH_VERIFICATION.md` |
| 2 | 33 of 33 financial constructor sites carry `folio_id`; the 24 writers map onto them exactly | completion review `ast` scan; `WRITER_COVERAGE.md` |
| 3 | **22 of 24** financial writers were runtime-exercised on isolated copies; every row attributed to the reservation's folio A; 0 new unattributed rows on any copy | `writers_set{A,B,C,D}.json` (gates 81/81, 42/42, 15/15, 46/46) |
| 4 | **2 writers were not runtime-exercised** because of a pre-existing defect: `settle_credit` (W-07) and `redeem_credit_voucher` (W-11) pass `notes=` to `Payment(...)`, which has no such column (`TypeError`); present since baseline commit `b5b2514` (2026-08-07); untouched by Phase 1 | `WRITER_COVERAGE.md` section 5; set A / set B logs |
| 5 | Static proof (ast) covers the remaining writers and stands | completion review; verification completion section 1 |
| 6 | Five registered datasets passed (INV-A02 HOLDS x5, INV-A03 HOLDS x4 / VACUOUS by declaration x1, 0 unmet) | `DATASET_RESULTS.md`, `datasets.json` |
| 7 | `DS-CORE-WALKIN` is **not** a declared dataset (docstring example in the deliberately empty `datasets_core.py`) | `DATASET_RESULTS.md` section 0 |
| 8 | Q14 **AGREED** on all five datasets | `datasets.json` |
| 9 | Q14 **DIVERGED** on production and on both new-activity copies by **exactly 476.19 = the two D11 charges**; the unrouted counts are exactly the eight D11 rows. **Not a Phase 1 attribution regression**; it is the FD-010 exception measured. | `Q14_PARITY.md` |
| 10 | Phase 2a authorization matrix remains **29/29** at `aa6d9e91` | `PHASE2A_MATRIX.md` |
| 11 | Golden Master `phase1_aa6d9e91` is **158/158 clean**; the historical `production` set is untouched and still shows exactly the four expected E-6 differences | `GOLDEN_MASTER_REBASELINE.md` |
| 12 | Production DB unchanged: hash, size, schema fingerprint, audit_logs 23, integrity ok, at every checkpoint across three directives | `VERIFICATION_COMPLETION.md` section 7 |
| 13 | D11 unchanged: payments 1-6 and extra_charges 1-2, 4,776.19, `folio_id NULL`, on production and on every copy; correction of any of them is refused in code (Q-2) | every pack's D11 check |
| 14 | **No Phase 1 attribution regression** on any population: the clean new-activity copy holds every invariant except INV-A02/A03, which are violated only by the D11 rows; INV-B01-B06 and C02 HOLD after the night audit closes the day | `inv_run_setD.txt`, pack `20260909_160110_inv_run_phase1_vc_setD` |
| 15 | Production `inv-run` verdict is identical to the pre-Phase-1 baseline (N-1 satisfied); replay PASS 10/10 | Phase 1 execution packs `013500`, `013458` |

## 3. Issues resolved into the package

| Issue | Disposition in this package |
|---|---|
| 1 - Q-5 audit coupling scope | Founder decision item **Q5-P1**: retain Q-5 as the architectural target for all financial mutations; do not weaken it; the 12 non-strict writers become carry-forward **CF-10** for a later bounded implementation. Not implemented now. |
| 2 - INV-B06 advance-payment / business-date semantics | Semantic review item **SR-1**: SEMANTIC REVIEW REQUIRED - NO PHASE 1 REGRESSION ESTABLISHED. Nothing changed. |
| 3 - INV-D02 cancellation-refund semantics | Semantic review item **SR-2**: SEMANTIC REVIEW REQUIRED - NO PHASE 1 REGRESSION ESTABLISHED. Nothing changed. |
| 4 - pre-existing credit defects | Defect register entries **DEF-1** (`settle_credit`) and **DEF-2** (`redeem_credit_voucher`): pre-existing, surfaced by bounded runtime verification, not Phase 1 regressions, not fixed under Phase 1; carried to a later defect workstream (**CF-11**). |
| 5 - remaining verification carry-forwards | **CF-5, CF-6, CF-7, CF-9 preserved open** in the register with their owners and gates; none closed. |

## 4. Why acceptance can be recommended despite the limitations

- Every limitation is either **outside Phase 1's authorized scope** (audit normalization at service-level writers - a Q-5 scope question; wall-clock dating - Q-3/Phase 3; invariant semantics - Phase 3/6; D6 dataset gap - Phase 6), or a **pre-existing defect** Phase 1 neither caused nor touched (DEF-1/2), or a **verification breadth** item that has now been closed to the extent the codebase allows (CF-1..CF-4, CF-8).
- The one thing Phase 1 was for - that new financial activity cannot be unattributed - is proven at 22 writers at runtime and at all 33 sites statically, with the resolver fail-closed and the D11 correction path refused.
- Nothing found would be invalidated by, or would block, Phase 2 architecture work. Phase 2b's own entry conditions (MP-D9, B-2) are standing items, not Phase 1 debts.

## 5. What the Founder is asked to do

Take the decisions in `FOUNDER_DECISION_ITEMS.md`. If Phase 1 is accepted, the acceptance entry (an append to `FOUNDER_DECISIONS.md` and a `MASTER_PLAN.md` overlay) is the durable record that closes completion-review gate G-2 and carry-forward CF-7. **This package does not write that entry.**

## 6. Governance safety

No file outside `verification/evidence/20260909_phase1_acceptance_prep/` was created or modified. `FOUNDER_DECISIONS.md`, `MASTER_PLAN.md` and the ADRs are untouched. Nothing committed, nothing pushed. This directory is untracked.
