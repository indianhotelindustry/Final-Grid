# Decision Register — Founder Resolution Round 3 (2026-09-10)

| Id | Subject | Decision | Supersedes / relates to | Closes | Leaves open |
|---|---|---|---|---|---|
| FD-P2-01 | Initial staffing profile | Single-operator / Admin model for the first production release; bounded to that release | confirms the Phase 2a interim Admin/Manager default; relates to FD-014, FD-015, FD-016, ADR-008/009/010/011 | MP-D9 **interim** question for the first release | MP-D9 full operator profile (Phase 4 gate, AR-015); ADR-009 route classification; Housekeeping scope (F13 / MP-D6) |
| FD-P2-02 | Audit retention | Stop destructive audit-log pruning until an archival design is adopted; non-audit log retention unchanged | applies FD-008 and AR-007; ADR-012 "immediate" item | nothing yet (implementation pending) | ADR-012 design: retention classes, periods, archive format/custody, detection invariant (B-6) |
| FD-P2-03 | D11 certification | Eight rows certified as a declared historical exception; preserved exactly; invariant not exempted; extra exception = failure | D11-F2, FD-010 Option A, AR-001, Q-2 all stand | the certification-verdict question (G12 readability) | disposition of the rows (B-3, Phase 5); `folio_id NOT NULL` (AR-004 step 5) |
| FD-P2-04 | PD-006 verified state | Twelve-condition definition adopted | FD-005 PD-006, FD-006 D9, ADR-006 proposal, ADR-007 target architecture, AR-006 | **BACKLOG B-5** | recovery-hardening implementation; retention exemption (B-11); scheduled restore service (Phase 9) |
| FD-P2-05 | Night-audit operating mode | Manual / controlled operator execution for the first release; scheduler automation not the operating model | FD-009, AR-013 | the first-release operating-mode question (G9) | B-1 scheduler-controls ADR; Phase 3 units 3.1–3.8 |
| FD-P2-06 | INV-B06 / INV-D02 | Refine both invariants for legitimate advance payments and cancellation refunds; behaviour unchanged; detection preserved; bounded constitutional amendment with evidence | Master Plan §07 Layer 1 (Founder-ruled amendment); FD-013 / ADR-004 context | SR-1 and SR-2 as **review** items | SR-1 / SR-2 **implementation and verification** (Phase 6 directive) |
| FD-P2-07 | Maker-checker | Initial threshold ₹10,000; no self-approval; operation-specific controls regardless of amount; auditable emergency/admin operations; minimum operation set named | AR-010, ADR-010, FD-014, FD-016; N2 void/refund control preserved | the policy content of B-2 | ADR-010 adoption text (matrix); table convergence; reason validation; Phase 2b implementation (needs CF-10) |

## Interaction notes

- FD-P2-01 × FD-P2-07: under the single-operator model a maker-checker operation at or above ₹10,000 cannot be completed by the sole Admin alone; the matrix (ADR-010) must define how such an operation waits for, or is escalated through, the explicitly audited emergency/admin control. This is a design item for the ADR, not a gap in the rulings.
- FD-P2-03 × FD-P2-06: after the invariant refinements, the only expected production violation set is the eight D11 objects; the declared-exception register is therefore exact, not approximate.
- FD-P2-04 × FD-P2-02: pre-mutation and pre-update backups used for a verified restore must be exempt from the 30-day purge (condition 12); this is recovery retention, distinct from audit retention.
- FD-P2-05 × Phase 3: the manual mode is safe only with staleness escalation (3.6) and interrupted-close recovery (3.5); Phase 3 is scoped to deliver them before the first release.

## Not decided by Round 3 (deliberately)

MP-D1, MP-D3, MP-D4, MP-D6, MP-D7, MP-D8; MP-D9 full profile; B-1, B-3, B-4, B-6, B-7, B-8, B-9, B-10, B-11; ADR-006/009/010/011/012 adoption text; any implementation.
