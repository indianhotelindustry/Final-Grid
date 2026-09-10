# Production-Readiness Impact of the Seven Decisions

Directive FG-P2-FOUNDER-DECISION-PACK-20260910-01. Gate letters refer to `20260910_phase2_entry/CERTIFICATION_GATES.md`.

## Impact table

| Item | Production blocker? | Blocks Phase 2b? | Blocks Phase 3? | Safely deferrable? | Required evidence after implementation | Recommended decision |
|---|---|---|---|---|---|---|
| **FD-P2-01** MP-D9 / interim extension | **CONDITIONAL** — NO while only Admin (+Manager) accounts exist; YES the moment another role account is created before Phase 4 unit 4.2 (G4) | **YES** — self-approval and checker identity cannot be defined without it | NO — Phase 3 needs no role decision | NO (a bounded interim ruling is itself the deferral) | ruling recorded; Phase 2a matrix re-run unchanged (29/29); day-one procedure lists the account-creation trigger; later: Phase 4 negative matrix for the roles in use | **B** narrow interim extension (or **C** rule "single-operator" if it is the fact) |
| **FD-P2-02** audit pruning | **YES** (G5; FD-008 / AR-007 "before certification"; exposure ~2026-11-07) | NO | NO | **NO** | bounded directive pack: diff limited to `_prune_old_logs`; test on a copy that `audit_logs` rows older than 90 days survive a run while webhook/notification rows are pruned; scheduler job table unchanged; GM/replay/inv unchanged | **Approve** bounded exemption now; `audit_logs` pruning explicitly OFF pending ADR-012 |
| **FD-P2-03** D11 certification verdict | **YES** (G12 cannot be recorded on OVERALL FAIL) | NO | NO | NO for certification; the rows' *disposition* stays deferred (B-3, Phase 5) | declared-exception register (8 objects) in the certification pack; `inv-run` violation object set == declared set, shown explicitly; INV-A02/A03 sources unchanged (hash of `rules_a.py`); D11 rows unchanged by id/amount | **Adopt** declared-exception certification rule |
| **FD-P2-04** PD-006 definition | **YES** (G8; FD-005/FD-006 mandatory gate) | NO (2b is schema-free; no mutation) | NO | NO | ruling recorded (closes B-5); then the recovery-hardening pack: app-path manifest, off-box `.enc` restore with all twelve conditions, `inv-run`/`gm-verify` on the restored copy, key-custody procedure document | **Adopt** the twelve-condition definition |
| **FD-P2-05** night-audit mode | **YES** as a ruling (G9 needs a stated mode); the mode itself is already the production setting | NO | **NO** — but Phase 3 delivers the staleness escalation and interrupted-close recovery that make manual mode safe | NO | ruling recorded; daily-close procedure written; production `night_audit_enabled=false` confirmed in the deployment rehearsal; Phase 3 packs for 3.5/3.6; multi-day manual-close rehearsal (N7) | **Manual controlled invocation** for the first release |
| **FD-P2-06** INV-B06 / INV-D02 | **YES** for certification readability (G3/G10: real advances and refunds would otherwise register as violations) | NO | NO (Phase 3 can proceed; the refinement is Phase 6 work after the ruling) | NO for the ruling; the implementation follows in Phase 6 | ruling recorded as a constitutional amendment; amended rules with negative seeds commissioned (`inv-commission`); `DS-ACT-VOIDCN` declaration updated; production and datasets re-run; no payment/refund/date behaviour change (diff limited to `verification/invariants/` and dataset declarations) | **Refine both invariants**, keep behaviour |
| **FD-P2-07** maker-checker matrix | **NO** for a single-operator release (existing void/refund control stands, N2); **CONDITIONAL** on MP-D9 for a staffed property | **YES** — B-2 is Phase 2b's entry condition | NO | The *implementation* (2b) is deferrable; the *matrix* is needed for 2b entry | ADR-010 adopted with the matrix; T1 and self-approval rule recorded; later 2b packs: per-operation negative matrix maker≠checker, audit rows per transition, Phase 2a matrix unchanged | **Adopt** four-tier structure; rule T1 and self-approval |

## Readiness arithmetic (no percentages)

- Gates unblocked by these rulings alone: **G5** (after the FD-P2-02 fix), **G12 readability** (FD-P2-03), **G8 criterion** (FD-P2-04), **G9 mode** (FD-P2-05), **G3/G10 readability** (FD-P2-06), **2b entry** (FD-P2-01 + FD-P2-07).
- Gates that still need engineering after the rulings: G3 (CF-10, CF-11, K-7 dating, Q06), G6 (Phase 3), G8 (recovery hardening + off-box rehearsal), G9 (launchers), G11 (procedure + rehearsal), G4 (only if staffed).

## Production certification path, restated with these decisions

```
Decision resolution      FD-P2-01…07 ruled and appended to FOUNDER_DECISIONS.md (one governance directive)
        ↓
Bounded implementation   pre-2b package: audit-pruning exemption (FD-P2-02) · CF-10 coupling · CF-11 credit fix · FD-015 · FD-017
                         invariant refinements (FD-P2-06) in a Phase 6 directive
                         recovery hardening to the PD-006 definition (FD-P2-04)
                         Phase 3 business-date / night-audit units under the manual-mode ruling (FD-P2-05)
                         Phase 2b under the interim profile (FD-P2-01) and the adopted matrix (FD-P2-07) — after the above
        ↓
Verification             per-directive packs; writers 24/24; amended invariants commissioned; Q06 explained
        ↓
Regression               Golden Master (re-baselined with declared deltas where dating changes move surfaces) 0 undeclared;
                         replay 0; datasets 5/5; Phase 2a matrix; Q14 as declared; production anchor unchanged
        ↓
Recovery rehearsal       off-box restore of an application-made encrypted backup meeting all twelve PD-006 conditions
        ↓
Deployment rehearsal     fresh install + upgrade from a copy of the live instance + launchers + day-one procedure +
                         N-day manual closes + rollback; G10 re-run on the rehearsal copy
        ↓
Final certification      G1–G11 packs at the release tag; D11 declared-exception register; Founder certification entry
```

The Master Plan sequence is unchanged; this is the certification sequence laid over it.
