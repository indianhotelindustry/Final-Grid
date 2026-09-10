# Carry-Forward Register — as preserved by the Phase 1 acceptance (2026-09-10)

Directive FG-P1-ACCEPTANCE-20260910-01 §7. Carried verbatim from `20260909_phase1_acceptance_prep/CARRY_FORWARD_REGISTER.md`; the only change is that **CF-7 is closed by the acceptance entry**. Nothing else is closed.

## Open

| Item | Subject | Status | Owner / gate |
|---|---|---|---|
| **CF-5** | T-N02 unauthorized-role-per-writer negative cases | OPEN — not run; low risk (no authorization changed by Phase 1; folio endpoints covered by the 29/29 Phase 2a matrix) | Phase 4 / Register R6, or a bounded verification directive |
| **CF-6** | Replay ledger does not capture `attribution_control` (deliberate, to keep the stored ledger intact — N-12) | OPEN | Phase 6 ledger re-baseline directive |
| **CF-9** | Deployment verification — `aa6d9e91` is accepted but not released; post-release `inv-run` on a copy of the live database and classification of any pre-release NULL-folio rows are not yet possible | OPEN | separate operational release decision (MP-D3 / PD controls); post-release verification directive |
| **CF-10** | Financial Mutation Audit-Coupling Normalization — strict coupling at the 12 non-strict writers: W-08, W-09, W-10, W-22, W-23 (caller-supplied, swallowed); W-11, W-12 (entity-level); W-13, W-14 (dedicated log, same transaction — lowest priority); W-16, W-21 (run-level, by design); W-24 (none). Architecture target Q-5 retained universally. | OPEN — deferred to the bounded pre-Phase-2b work; not implemented | bounded pre-Phase-2b directive |
| **CF-11** | Pre-existing credit defects DEF-1 `settle_credit` (W-07) and DEF-2 `redeem_credit_voucher` (W-11): `Payment(... notes=...)` → `TypeError`; routes non-functional since `b5b2514`; not Phase 1 regressions; not fixed | OPEN — separate bounded defect directive later; candidate K-21 | defect workstream |
| **SR-1** | INV-B06 vs advance-payment / business-date semantics | SEMANTIC REVIEW REQUIRED — NO PHASE 1 REGRESSION ESTABLISHED; invariant, payment and business-date behaviour unchanged | architecture / business-semantics review track (Phase 3 ADR-004 / B-10; Phase 6 declaration) |
| **SR-2** | INV-D02 vs cancellation-refund semantics | SEMANTIC REVIEW REQUIRED — NO PHASE 1 REGRESSION ESTABLISHED; invariant, refund and cancellation behaviour unchanged | architecture / business-semantics review track (Phase 6; or Phase 2b if B-2 covers refunds) |

## Closed — and what closed each

| Item | Closed by |
|---|---|
| CF-1 runtime cases for the static-only writers | verification completion: 16 writers newly exercised (22/24), injection at 8; residual tracked as CF-11 |
| CF-2 `inv-run` on a new-activity copy | verification completion: clean copy set D — 18 HOLDS, D11-only violations, B01–B06 and C02 HOLD |
| CF-3 datasets and Q14 | verification completion: 5/5 datasets PASS, Q14 AGREED on datasets; `DS-CORE-WALKIN` gap → Phase 6 |
| CF-4 Phase 2a matrix | verification completion: 29/29 |
| **CF-7** governance acceptance entry | **this directive**: `FOUNDER_DECISIONS.md` § "Phase 1 Formal Acceptance — FG-P1-ACCEPTANCE-20260910-01" and `MASTER_PLAN.md` §17 |
| CF-8 Golden Master declared differences | verification completion: `phase1_aa6d9e91` 158/158; adopted by this directive (GM-TAG) |

## Not carry-forwards (settled elsewhere)

D11 disposition (FD-010, Q-2, AR-001; next decision Phase 5 / B-3) · wall-clock dating (Q-3 → Phase 3) · FK / NOT NULL / migration mechanism (Phase 4/5) · FD-015 implementation · scheduler, retention, maker-checker, reporting authorization (B-1, B-6, B-2, B-7) · MP-D9 (Phase 2b entry) · `DS-CORE-WALKIN` (Phase 6) · W-20 repeat-call billing (recorded product finding).
