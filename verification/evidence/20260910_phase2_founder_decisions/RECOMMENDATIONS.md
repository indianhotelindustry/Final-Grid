# Recommendations — decisions I recommend we take now

Directive FG-P2-FOUNDER-DECISION-PACK-20260910-01. No implementation occurs in this pack; each approval authorizes only the *later* step named.

## 1. Decisions that can safely be approved immediately (clear safe default; no business choice hidden inside)

| Decision | Recommended ruling | What approval authorizes later | What it does NOT authorize |
|---|---|---|---|
| **FD-P2-02 Audit-pruning exemption** | `audit_logs` is removed from the automatic prune loop; `webhook_logs` / `notification_logs` pruning unchanged; `audit_logs` pruning stays OFF until an archival design is approved under ADR-012 | a **bounded retention-control directive** (one function, one test, one pack) | any archival, retention-period or deletion design; any scheduler change beyond that function |
| **FD-P2-03 D11 certification verdict** | Certification uses a **declared-exception register**: the eight rows listed by id and amount; the invariant verdict is certifiable as PASS-WITH-DECLARED-EXCEPTION only when the violation set equals the declared set; INV-A02/A03 and the rows unchanged | the certification pack format (G12) and the manual set-comparison step | any attribution, reversal, deletion, invoice or GST change; any invariant change; the rows' disposition (B-3 stays deferred) |
| **FD-P2-04 PD-006 "verified state"** | The twelve conditions in the pack (identity, completion, integrity, FK, schema, data identity, informational hash, functional equivalence, manifest, accountability, off-box key custody, retention); closes B-5 | the **recovery-hardening directive** (app-path manifest/hash, off-box encrypted restore rehearsal, custody document) | building a scheduled restore service (Phase 9); any production mutation |
| **FD-P2-05 Night-audit operating mode** | **Manual controlled invocation** for the first production release (`night_audit_enabled=false`), with a written daily-close procedure; automation only after the AR-013 / B-1 scheduler ADR | the daily-close procedure document; Phase 3 units 3.5/3.6 scope; the G9/G11 rehearsal expectation | enabling the scheduler; any night-audit code change |
| **FD-P2-06 INV-B06 / INV-D02 refinement** | Constitutional amendment: INV-B06 admits `payment_purpose='advance'` on or before arrival and cancellation refunds on or before cancellation; INV-D02 accepts a reversal row referenced by `reservations.cancellation_refund_payment_id`; both keep severity and negative seeds; **no payment, refund or business-date behaviour change** | a **Phase 6 invariant-refinement directive** (rules, seeds, commissioning, `DS-ACT-VOIDCN` declaration) | any change to `app/` |

## 2. Decisions requiring a genuine Founder / business choice

| Decision | The choice only the Founder can make | Recommended answer if the facts allow | What approval authorizes later |
|---|---|---|---|
| **FD-P2-01 MP-D9 operator profile** | Is the property a single-operator (Admin, perhaps one Manager) hotel for the first release, or will Front-Desk / Accountant / Housekeeping staff have their own logins? | If single-operator: rule it (option C) — it settles ADR-009/010/011's open items at once. If unsure: approve the **narrow interim extension** (option B) with its four conditions (roles in use; self-approval only when no other approver exists, with reason and flagged audit; account-creation trigger; report/writer routes unchanged until Phase 4) | Phase 2b entry (with FD-P2-07); the day-one procedure's account rule. Does not authorize Phase 4 authorization work or any new role |
| **FD-P2-07 Maker-checker matrix** | (a) the rupee threshold **T1** above which a folio transfer needs a second approver; (b) the **self-approval** rule for a one-person property; (c) whether **reopening a closed day** needs a second approver where one exists | (a) a figure of the same order as the existing leakage alert (₹3,000) unless the business prefers stricter; (b) Admin only, reason mandatory, audit flagged, reviewed at next close; (c) yes where a second approver exists, emergency override otherwise | adoption of ADR-010 with the four-tier matrix (B-2) → Phase 2b entry. Does not authorize implementation of 2b |

## 3. Decisions that should remain explicitly deferred

| Item | Why deferred | Where it returns |
|---|---|---|
| Disposition of the eight D11 rows (B-3) | reserved by FD-010's last clause; needed only for `folio_id NOT NULL` (Phase 5) | Phase 5 gate |
| Archival / retention design (ADR-012 classes, periods, archive custody, detection invariant) | not needed to stop the immediate loss (FD-P2-02 does that); needs design | Phase 4 / 6 |
| Night-audit automation (AR-013 / B-1 ADR) | manual mode is safe and compliant now | Phase 3 / 4 gate |
| Scheduled restore verification service (Phase 9 unit 9.2) | one rehearsed off-box restore satisfies G8 for the first release | Phase 9 |
| Convergence of the three approval tables | design detail for 2b | ADR-010 design / 2b |
| Full MP-D9 profile beyond the interim (report classification per role, Housekeeping scope) | Phase 4 unit 4.2; depends on staffing | Phase 4 gate |
| Schema authority (B-4), FK enforcement, NOT NULL | no schema change in the release | Phase 5 gate / first schema change |

## Implementation consequences, in one line each

- Approve FD-P2-01 → permits Phase 2b scoping under the interim profile; does NOT authorize any role or route change.
- Approve FD-P2-02 → permits a bounded retention-control directive; does NOT authorize implementation in this pack.
- Approve FD-P2-03 → permits the certification pack to use a declared-exception register; does NOT touch the rows or the invariants.
- Approve FD-P2-04 → permits the recovery-hardening directive against a fixed acceptance criterion; does NOT authorize a production mutation.
- Approve FD-P2-05 → permits the daily-close procedure and fixes Phase 3's manual-mode assumptions; does NOT enable the scheduler.
- Approve FD-P2-06 → permits a Phase 6 invariant-refinement directive; does NOT change application behaviour.
- Approve FD-P2-07 → permits adoption of ADR-010 and Phase 2b entry once FD-P2-01 and CF-10 are done; does NOT implement maker-checker.

## Suggested order of rulings

1. FD-P2-02, FD-P2-05 (time-bound / already the operating reality).
2. FD-P2-03, FD-P2-04, FD-P2-06 (certification criteria; unblock later packs).
3. FD-P2-01, then FD-P2-07 (business facts; unblock Phase 2b).

All seven can be recorded in one governance-record directive; that directive is the next authorization to issue.
