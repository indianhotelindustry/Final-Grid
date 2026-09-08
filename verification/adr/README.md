# Architecture Decision Records — FinalGrid

Namespace `ADR-###` adopted by **FD-001** (2026-09-08). This directory was
created under `FG-P0-GOV-RECORD-20260908-01`. Any ADR numbering proposed
before FD-001 is superseded and carries no authority.

## Authority chain (FD-004)

Founder Decision → Governance/ADR → Implementation Directive → Code/Data
Mutation → Verification Evidence. An ADR translates an adopted Founder
decision into architecture. **An ADR authorizes no implementation**; that
requires a separate implementation directive, and any production mutation
additionally requires PD-004, PD-005 and PD-006 (FD-005).

## Status vocabulary

| Status | Meaning |
|---|---|
| **DRAFT** | Prepared for Founder review. Not adopted. Technical choices marked UNRESOLVED remain open. |
| **ADOPTED** | Founder has accepted the ADR as architecture. Recorded in `FOUNDER_DECISIONS.md`. |
| **SUPERSEDED** | Replaced by a later ADR, which names it. |

ADRs are append-only once adopted; a change is a new ADR that supersedes.

## Register

| ADR | Subject | Founder decision(s) | Status |
|---|---|---|---|
| [ADR-001](ADR-001-system-of-record-boundary.md) | System-of-record boundary | FD-003 | DRAFT |
| [ADR-002](ADR-002-folio-attribution-contract.md) | Folio attribution contract | FD-011, FD-003, FD-010 | DRAFT |
| [ADR-003](ADR-003-room-rent-ownership.md) | Room-rent ownership | FD-012 | DRAFT |
| [ADR-004](ADR-004-business-date-authority.md) | Business-date authority | FD-013 | DRAFT |
| [ADR-005](ADR-005-sqlite-foreign-key-enforcement.md) | SQLite foreign-key enforcement | FD-003, FD-011 (context) | DRAFT |
| [ADR-006](ADR-006-production-mutation-controls.md) | Production mutation controls | FD-005, FD-007, FD-019 | DRAFT |
| [ADR-007](ADR-007-backup-restore-architecture.md) | Backup / restore architecture | FD-005, FD-006 | DRAFT |
| [ADR-008](ADR-008-application-authorization-architecture.md) | Application authorization architecture | FD-016, FD-015 | DRAFT |
| [ADR-009](ADR-009-reporting-authorization.md) | Reporting authorization | FD-016 | DRAFT |
| [ADR-010](ADR-010-maker-checker-architecture.md) | Maker-checker architecture | FD-016, FD-014 | DRAFT |
| [ADR-011](ADR-011-operator-accountability.md) | Operator accountability | FD-014 | DRAFT |
| [ADR-012](ADR-012-audit-retention.md) | Audit retention | FD-008, FD-009 | DRAFT |

All twelve were drafted 2026-09-08 at HEAD `237db2ad` against database
anchor `51dd83b7…30bc2`. Line references are to that checkpoint.
