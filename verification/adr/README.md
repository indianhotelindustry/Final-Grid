# Architecture Decision Records — FinalGrid

Namespace `ADR-###` adopted by **FD-001** (2026-09-08). Directory created
under `FG-P0-GOV-RECORD-20260908-01`, reconciled under
`FG-P0-ARCH-RESOLUTION-20260908-01`, and brought to its adoption baseline
under `FG-P0-ADR-ADOPTION-20260908-01`. Any ADR numbering proposed before
FD-001 is superseded and carries no authority.

## Authority chain (FD-004)

Founder Decision → Governance/ADR → Implementation Directive → Code/Data
Mutation → Verification Evidence. An ADR translates an adopted Founder
decision into architecture. **An ADR authorizes no implementation**; that
requires a separate implementation directive, and any production mutation
additionally requires PD-004, PD-005 and PD-006 (FD-005).

**Architecture adopted ≠ implemented control ≠ verified production state.**

## Status vocabulary

| Status | Meaning |
|---|---|
| **ADOPTED** | Architecture is settled and repository governance accepts it as the current architectural rule. Recorded in `FOUNDER_DECISIONS.md`. Append-only thereafter. |
| **PROPOSED FOR ADOPTION** | Architecture is materially settled, but an explicit adoption/readiness condition remains. |
| **PROPOSED** | A material architecture/technical choice remains open. |
| **DRAFT** | Insufficiently developed for adoption. |
| **SUPERSEDED** | Replaced by a later authoritative decision, which names it. |

Before adoption, an ADR's status line and its reconciliation/adoption
sections may be updated; earlier content is not rewritten. After adoption
an ADR is append-only; a change is a new ADR that supersedes it.

## Register — adoption baseline, 2026-09-08

| ADR | Subject | Founder decision(s) | Status |
|---|---|---|---|
| [ADR-001](ADR-001-system-of-record-boundary.md) | System-of-record boundary | FD-003, AR-002 | **ADOPTED** |
| [ADR-002](ADR-002-folio-attribution-contract.md) | Folio attribution contract | FD-011, FD-003, FD-010, AR-001, AR-002, AR-004 | **ADOPTED** |
| [ADR-003](ADR-003-room-rent-ownership.md) | Room-rent ownership — *Reservation operational ownership + folio financial ownership* | FD-012, AR-002 | **ADOPTED** (labels M1/M2/M3 retired) |
| [ADR-004](ADR-004-business-date-authority.md) | Business-date authority | FD-013, AR-008 | **ADOPTED** |
| [ADR-005](ADR-005-sqlite-foreign-key-enforcement.md) | SQLite foreign-key enforcement | AR-003 | **ADOPTED** (architecture requirement; not enabled) |
| [ADR-006](ADR-006-production-mutation-controls.md) | Production mutation controls | FD-005, FD-007, FD-019, AR-005 | PROPOSED — migration mechanism, "verified state" open |
| [ADR-007](ADR-007-backup-restore-architecture.md) | Backup / restore architecture | FD-005, FD-006, AR-006 | **ADOPTED** (target architecture; restore not implemented) |
| [ADR-008](ADR-008-application-authorization-architecture.md) | Application authorization architecture | FD-016, FD-015, AR-009 | **ADOPTED** (architecture; FD-015 not implemented) |
| [ADR-009](ADR-009-reporting-authorization.md) | Reporting authorization | FD-016, AR-011 | PROPOSED FOR ADOPTION — awaits MP-D9 and route review |
| [ADR-010](ADR-010-maker-checker-architecture.md) | Maker-checker architecture | FD-016, FD-014, AR-010 | PROPOSED — operation matrix undefined |
| [ADR-011](ADR-011-operator-accountability.md) | Operator accountability | FD-014, AR-012 | PROPOSED FOR ADOPTION — storage/system-actor mechanics open |
| [ADR-012](ADR-012-audit-retention.md) | Audit retention | FD-008, FD-009, AR-007 | PROPOSED — retention design not approved |

Adopted: **7** (001, 002, 003, 004, 005, 007, 008). Proposed for adoption: 2
(009, 011). Proposed: 3 (006, 010, 012). Draft: 0.

## Backlog

Future ADRs and technical decisions the adopted architecture explicitly
requires are tracked in [BACKLOG.md](BACKLOG.md). Nothing in the backlog
is an adopted decision.

All twelve ADRs were drafted at HEAD `237db2ad`, reconciled and adopted at
HEAD `e69f2ac` against database anchor `51dd83b7…30bc2`. Line references
are to checkpoint `237db2ad`.
