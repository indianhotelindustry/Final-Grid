# Carry-Forward Register - Phase 1 at `aa6d9e91`

Directive FG-P1-ACCEPTANCE-PREP-20260909-01. Consolidates the completion review's CF-1..CF-9 with their verification-completion outcomes and adds the two items that the runtime verification raised (CF-10, CF-11). Nothing is silently closed: every closure names the evidence that closed it.

| CF | Item | Origin | Status after verification completion | Evidence | Owner / gate |
|---|---|---|---|---|---|
| CF-1 | Runtime cases for the 18 static-only writers; audit-failure injection beyond W-05/W-15/W-20 | completion review | **CLOSED to the extent the codebase allows**: 16 writers newly exercised (22/24 runtime total); injection proven at 8. Residual: W-07 and W-11 cannot execute (see CF-11); the remaining coverage gap is not a verification choice but a defect. | `WRITER_COVERAGE.md`; `writers_set{A,B,C,D}.json` | closed; residual tracked as CF-11 |
| CF-2 | `inv-run` on a new-activity copy | completion review | **CLOSED**: clean copy (set D) = 18 HOLDS, INV-A02/A03 violated only by the eight D11 rows, INV-B01-B06 and C02 HOLD after close | pack `20260909_160110_inv_run_phase1_vc_setD` | closed; observations SR-1, SR-2 registered separately |
| CF-3 | `ds-run` six datasets; Q14 parity | completion review | **CLOSED with limitation**: 5 registered datasets PASS, Q14 AGREED x5; Q14 DIVERGED by exactly the D11 amount on production-derived copies (expected); `DS-CORE-WALKIN` was never declared (D6 gap, Phase 6) | `DATASET_RESULTS.md`, `Q14_PARITY.md` | closed; DS-CORE-WALKIN -> Phase 6 |
| CF-4 | Phase 2a 29-case matrix at `aa6d9e91` | completion review | **CLOSED**: 29/29 PASS | `PHASE2A_MATRIX.md` | closed |
| **CF-5** | T-N02 unauthorized-role-per-writer negative cases | verification plan slice 3 | **OPEN - not run** (not listed in the verification-completion directive; no authorization changed by Phase 1; folio endpoints covered by CF-4). Low risk. | - | Phase 4 / Register R6 authorization work, or a bounded verification directive |
| **CF-6** | Replay ledger does not capture `attribution_control` | Phase 1 execution section 6 | **OPEN - deliberate**: the control was placed outside `NAS_SECTIONS` to keep the stored ledger intact (N-12). | Phase 1 execution report; completion review CF-6 | Phase 6 ledger re-baseline directive |
| **CF-7** | Governance index: FG-P1-EXEC, Golden Master, W-20, precommit / commit / push, completion review, verification completion and this package are not indexed in `FOUNDER_DECISIONS.md` / `MASTER_PLAN.md`; Phase 1 acceptance unrecorded | completion review | **OPEN**: governance records may not be edited by any of the read-only directives. Closed by the acceptance entry itself (decision P1-ACC). | - | Founder acceptance entry (bounded governance-record directive) |
| CF-8 | Golden Master carried four declared differences | completion review | **CLOSED**: `phase1_aa6d9e91` captured, 158/158 clean; historical set intact; adoption/commit is decision GM-TAG | `GOLDEN_MASTER_REBASELINE.md` | closed; GM-TAG pending |
| **CF-9** | Phase 1 committed and pushed, not deployed; pre-release live activity would create non-D11 NULL rows | completion review | **OPEN - release decision** (MP-D3 / PD controls). Deployment verification (post-release `inv-run` on a copy of the live database; classification of any pre-release NULL rows) is not yet possible. | - | Founder (decision REL); post-release verification directive |
| **CF-10** | Q-5 strict audit coupling at the 12 non-strict writers: W-08, W-09, W-10, W-22, W-23 (caller-supplied, swallowed); W-11, W-12 (entity-level); W-13, W-14 (dedicated log, same transaction - lowest priority); W-16, W-21 (run-level, by design); W-24 (none) | verification completion section 8 / decision Q5-P1 | **OPEN - documented carry-forward**. Architecture target retained; implementation not authorized. | `WRITER_COVERAGE.md` section 4 | Founder assigns (recommended: bounded pre-Phase-2b directive) |
| **CF-11** | Pre-existing defects DEF-1 `settle_credit` (W-07) and DEF-2 `redeem_credit_voucher` (W-11): `Payment(... notes=...)` -> `TypeError`; routes non-functional since `b5b2514`; not Phase 1 regressions; not fixed under Phase 1 | verification completion section 11 / decision DEF-FIX | **OPEN - defect workstream**. Runtime verification of W-07/W-11 becomes possible only after the fix. | `WRITER_COVERAGE.md` section 5; set A / set B logs | Founder assigns (decision DEF-FIX); candidate K-21 |

## Closed items - what closed them

CF-1 (16 writers at runtime, injection at 8), CF-2 (clean copy holds all but the D11 exception), CF-3 (5/5 datasets, Q14 AGREED on datasets), CF-4 (29/29), CF-8 (158/158 under the new tag). Each closure is a retained pack under `20260909_phase1_verification_completion/` or a harness pack listed in its `result.json`.

## Open items - summary

| Open | Kind |
|---|---|
| CF-5 | verification breadth (low risk) |
| CF-6 | Phase 6 ledger coverage (deliberate) |
| CF-7 | governance record (closed by the acceptance entry) |
| CF-9 | release / deployment verification |
| CF-10 | Q-5 audit-coupling normalization (implementation carry-forward) |
| CF-11 | pre-existing credit defects (defect workstream) |

None of the open items is a Phase 1 attribution regression, and none blocks the acceptance recommendation; CF-7 is closed by the act of acceptance.
