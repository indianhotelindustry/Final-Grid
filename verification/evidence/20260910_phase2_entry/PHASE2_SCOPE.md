# Phase 2 Scope — proposed, not authorized

Directive FG-P2-ENTRY-READINESS-20260910-01, section 4. "Phase 2" is the Master Plan's **Phase 2b — Folio Auditability & Maker-Checker** (Phase 2a is complete and frozen). The Founder's acceptance entry (Q5-P1) already created a **bounded pre-Phase-2b work package** for CF-10; this proposal places into that package the other small items that are already decided and need no new architecture, and defines Phase 2b proper behind its prerequisites. The eleven-phase sequence is unchanged; nothing below is an implementation authorization.

## A. Bounded pre-Phase-2b package (enterable under existing decisions)

| Item | Why it belongs here | Prerequisite | Impl. | Verif. | Prod-blocking? | Rollback / recovery | ADR / decision | Evidence required for closure |
|---|---|---|---|---|---|---|---|---|
| **P2-A1 CF-10 audit-coupling normalization** — apply `audited_financial_write` at W-08, W-09, W-10, W-22, W-23 (replace the swallowed caller-supplied writer inside the service, or make the service raise), W-11, W-12 (a coupled Payment-level row), W-24 (a row), and decide W-13/W-14 (dedicated logs already atomic — wrap for uniformity or record as accepted), W-16/W-21 (run-level by design — record as accepted or add per-row rows, which changes closed-day evidence volume: **decision inside the directive**) | Founder placed it pre-2b (Q5-P1); Phase 2b will route approvals through exactly these services | none beyond a bounded directive; schema-free | yes | **yes** (by Founder sequencing; provenance of corrections/refunds) | `git revert`; no data; regression: Golden Master 0 diff except declared audit-count surfaces, replay 0, invariants unchanged | Q-5, Q5-P1, ADR-008 | per-writer runtime case with audit-failure injection (extend `verify_writers.py` sets), 24/24 A-STRICT or explicitly accepted classes, GM/replay/inv packs |
| **P2-A2 CF-11 credit defects** — remove/replace the `notes=` keyword at `settle_credit` and `redeem_credit_voucher` (the model has `reference_number`; the intended field is a directive decision) | Two routes are non-functional; tiny, isolated, pre-existing | none | yes (2 lines + tests) | **yes** if credit/voucher features are used | `git revert` | none needed (defect) | W-07 and W-11 runtime cases pass (row, folio A, audit, injection); 24/24 runtime coverage |
| **P2-A3 Audit-pruning exemption** — remove `AuditLog` from `_prune_old_logs`, leaving `WebhookLog`/`NotificationLog` as-is (ADR-012 item 1) | FD-008 / AR-007 require it before certification; exposure ~2026-11-07; smallest compliant change | **Founder confirmation** that this is a bounded exemption now (ADR-012 open question), not Phase 4 | yes (one function) | **yes** | `git revert`; no data; no row deleted either way | FD-008, AR-007, ADR-012 | test proving `audit_logs` rows older than 90 days survive a prune run on a copy; scheduler job list unchanged otherwise |
| **P2-A4 FD-015 `list_folios` read scope** — `_FOLIO_ROLES['folio.list_folios']` → Admin, Manager, Accountant, FrontDesk; mutating endpoints unchanged | Decided 2026-09-08; read-only; Phase 2a boundary explicitly allows it | none | yes (one tuple) | no | `git revert` | FD-015, FD-016 | Phase 2a matrix re-run with T01/T02 expectations updated to 200 and the mutating cases unchanged (27 unchanged + 2 changed) |
| **P2-A5 FD-017 launcher CRLF** — nine `.bat`/`.vbs` files, line endings only | Approved; deployability (V10) | none | mechanical | **yes** for G11 | `git revert` | FD-017 | byte diff shows CRLF only; launchers executed on the operator machine (part of G11) |
| **P2-A6 SR-1 / SR-2 semantic review** — resolve INV-B06 vs advance dating and INV-D02 vs refunds as a review directive (no code) | Needed before any real-day invariant verdict is readable; 2b touches refunds | none | no (review) | **yes** (decision) | n/a | FD-013, ADR-004, invariant registry | Founder ruling recorded; then either an invariant-declaration change (constitutional, Founder-ruled) or a Phase 3 dating change |

Suggested order: A2 and A5 (trivial, independent) → A3 (time-bound) → A1 (largest) → A4 → A6 in parallel as a review. Each is one directive, one commit, one evidence pack (SC-6).

## B. Phase 2b proper — behind prerequisites

| Unit | Content (Master Plan §05) | Why Phase 2b | Prerequisite | Impl. | Verif. | Prod-blocking? | Rollback | ADR / decision | Closure evidence |
|---|---|---|---|---|---|---|---|---|---|
| 2b.0 | Maker-checker operation matrix — sensitive-mutation list, materiality thresholds, self-approval policy, convergence of void / shift / folio approval models, reason validation | The plan requires the matrix "in a dedicated ADR before implementation" (AR-010) | **MP-D9** (single-operator self-approval is the crux) | no (ADR) | n/a | no (C) | n/a | ADR-010 → ADOPTED; B-2 | ADR adopted and indexed in `FOUNDER_DECISIONS.md` |
| 2b.1 | Define sensitive financial mutation; maker-checker where irreversible (folio create/transfer/close; billing-responsibility change; void/refund already) | Control model half of R7 | 2b.0; CF-10 | yes; **schema-free** by reusing the existing request/approval shapes (`void_requests`, `PendingApproval`) or PD-004 if a new table is required | yes | no (C) — void/refund control already exists (N2) | `git revert`; approval rows are data — need a PD-004 plan only if a new table | ADR-010, FD-014, FD-016 | negative matrix maker≠checker per operation; audit rows per transition; Phase 2a matrix unchanged |
| 2b.2 | Govern billing-responsibility changes | Same control family | 2b.1 | yes | yes | no (C) | `git revert` | ADR-010 | runtime cases; invariants unchanged |
| 2b.3 | Reconcile `Folio.company_id` (inert) vs `CheckInRecord.company_id` (live) (N1) | Duplicated linkage named for 2b | ADR-001/002 (adopted); may need a data reconciliation → PD-004 if any production row changes (none expected: `company_id` NULL on all four production folios) | yes | yes | no (C) | data change only under PD-004/005/006 | ADR-001, ADR-002, FD-003 | INV-C06 activation on a copy; company surfaces in GM declared |
| 2b.4 | Complete AuditLog coverage for the mutation set (operator, role, business date, IP; system actor for jobs) | Accountability (AR-012) | ADR-011 storage decision (coupled audit row needs no schema; columns need PD-004) | yes | yes | **C** (A if envelope required for certification — E) | `git revert` | ADR-011, FD-014 | every sensitive mutation has a coupled row with the envelope; injection tests |

## C. Explicitly not Phase 2

Business-date and night-audit work (Phase 3 — enterable now, see `PHASE2_ENTRY_ASSESSMENT.md` §2), report/route authorization and reliability (Phase 4), FK / NOT NULL / migration mechanism (Phase 5), verification tooling (Phase 6), guest identity (Phase 7), dormant subsystems (Phase 8), backup-path hardening and scheduled restore verification (Phase 9 — though a bounded earlier directive is possible, as Q-6 was for restore), Level 3 split billing (out of scope).

## D. Entry conditions for Phase 2b implementation, restated

1. MP-D9 ruled, or the interim Admin/Manager default extended explicitly to 2b with a self-approval rule.
2. B-2 operation-matrix ADR adopted (2b.0).
3. CF-10 delivered and verified (P2-A1).
4. Scope declared schema-free, or a PD-004 authorization issued for any new table.
5. Golden Master `phase1_aa6d9e91` (or its pre-2b successor after package A) at 0 differences as the Gate G reference.
