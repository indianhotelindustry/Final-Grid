# Founder Resolution Round 3 — Phase 2 Production Readiness — recording record

| | |
|---|---|
| Directive | FG-P2-FOUNDER-RESOLUTION-20260910-01 (Founder resolution authorized; governance recording only) |
| Recorded | 2026-09-10 |
| Baseline | `a84566ae471786955283d107a9f2ad9e800bfcd4` = `origin/main`; tree clean before recording |
| Inputs | `20260910_phase2_entry/` (seven open items), `20260910_phase2_founder_decisions/` (analysis and recommendations) |
| Governance records written | `verification/FOUNDER_DECISIONS.md` — new section "Founder Resolution Round 3 — Phase 2 Production Readiness — FG-P2-FOUNDER-RESOLUTION-20260910-01" (append-only; prior content byte-identical) · `verification/MASTER_PLAN.md` — §18 status overlay (append-only) |
| ADRs | **not edited.** ADR-006 (B-5 now closed), ADR-010 (threshold and no-self-approval policy now ruled), ADR-012 (pruning ruling) are reconciled at their next adoption review; the authoritative record of the rulings is `FOUNDER_DECISIONS.md` (FD-018). Editing ADR status here would implement governance through this directive rather than record it. |
| Commit / push | **none** — all changes and this directory are untracked, per the directive |
| Production | unchanged — verified read-only before and after (see `result.json`) |
| Status | **PHASE 2 FOUNDER RESOLUTION PASS — ROUND 3 RECORDED — IMPLEMENTATION NOT AUTHORIZED** |

## The seven decisions as recorded

| Item | Decision (verbatim gist) | Rationale (from the decision pack) | Implementation consequence | Implementation status |
|---|---|---|---|---|
| FD-P2-01 | Single-operator / Admin model for the first production release; an initial boundary, not a permanent statement | one Admin user in production; Phase 2a interim default already in force; broad authorization is Phase 4 | Phase 2b scoping under the Admin model; day-one rule that a new role account re-opens the boundary; no role/route change | none required |
| FD-P2-02 | Stop destructive audit-log pruning until an archival design is adopted; other log retention unchanged | FD-008 / AR-007 non-compliance, ~2026-11-07 exposure, negligible storage | bounded retention-control directive (remove `AuditLog` from the prune loop) | **not implemented**; job unchanged |
| FD-P2-03 | Certify the eight D11 rows as a declared historical exception; preserve exactly; invariant not exempted; any further unexplained exception fails certification | keeps FD-010, Q-2, AR-001 intact; control still capable of failing | certification pack carries the declared-exception register and a set comparison | none required; rows and invariants unchanged |
| FD-P2-04 | Adopt the twelve-condition PD-006 verified-state definition | distinguishes "backup exists" from "restored and verified"; builds on RR-20260908-01 | recovery-hardening directive; closes B-5 | not implemented |
| FD-P2-05 | Manual / controlled operator execution of the night audit for the first release; unattended scheduler not the operating model | FD-009; no B-1 ADR; blockers silent at 02:00; manual route accountable | daily-close procedure; Phase 3 units 3.5/3.6 as first-release controls; `night_audit_enabled` stays false | no code or setting changed |
| FD-P2-06 | Refine INV-B06 and INV-D02 to represent legitimate advance-payment and cancellation-refund semantics; behaviour unchanged; detection preserved | invariant design gap / semantics ambiguity; no GST effect | Phase 6 invariant-refinement directive (constitutional amendment) with commissioning evidence | invariants unchanged |
| FD-P2-07 | Initial maker-checker threshold ₹10,000; no self-approval; operation-specific controls regardless of amount; emergency/admin operations explicitly auditable; matrix must cover voids, closed-day corrections, reopen, large transfers, large forfeits/credits, other material corrections | AR-010, B-2; existing void/refund and shift controls as reference | ADR-010 adoption with the matrix; Phase 2b entry with CF-10 | not implemented |

## Append-only proof

Both governance files were extended by appending only: for each, the content at `a84566ae` is a byte prefix of the new file, the appended tail equals the drafted section exactly, it appears once, and no CR byte was introduced. Line counts before → after are recorded in `result.json`. No prior resolution was rewritten or duplicated; the Round 1 and Round 2 entries, FD-001…FD-019 and the Phase 1 acceptance entry are untouched.

## What this directive did not do

No change to `app/`, `verification/invariants/`, the scheduler, night-audit code or settings, roles, ADR files, the eight D11 rows, `instance/pms.db`, ledgers or masters. No commit, no push. Every implementation the rulings permit remains a separate bounded directive (`IMPLEMENTATION_CONSEQUENCES.md`).
