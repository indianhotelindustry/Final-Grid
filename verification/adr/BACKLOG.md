# ADR Backlog — decisions the adopted architecture still requires

Established 2026-09-08 under `FG-P0-ADR-ADOPTION-20260908-01`. **Nothing
here is an adopted decision.** Each entry names the kind of work it needs:

- **Architecture decision needed** — a Founder decision or ADR must settle a choice.
- **Implementation design needed** — the architecture is settled; the design of how to realise it is not.
- **Implementation authorization needed** — design may be settled; no directive authorizes doing it.

| # | Item | Required by | Kind | Phase gate | Notes |
|---|---|---|---|---|---|
| B-1 | **Scheduler financial-action controls** — authorization, system-actor provenance, business-date authority, auditability, idempotency, failure handling, verification for `night_audit_job`, `log_pruning_job` and any future financial automation | AR-013, FD-009 | Architecture decision needed (dedicated ADR) | Phase 3 / Phase 4 | No ADR exists. Current scheduler is non-compliant and unchanged. |
| B-2 | **Maker-checker operation matrix** — which operations, materiality thresholds, self-approval policy for single-operator properties, convergence of void/shift/folio approval models, reason validation | AR-010, ADR-010 | Architecture decision needed (dedicated ADR); depends on MP-D9 | Phase 2b | ADR-010 stays PROPOSED until this exists. |
| B-3 | **`folio_id NOT NULL` enforcement mechanics** — SQLite table rebuild, index/constraint carry-over, rowid preservation, pre/post manifests, rollback via rehearsed restore; disposition of the eight FD-010 rows before step 5 | AR-004, ADR-002 | Implementation design needed **and** a separate Founder decision on the eight rows; implementation authorization needed (PD-004) | Phase 5 | Step 5 is unreachable while any row is NULL. |
| B-4 | **Schema migration mechanism** — which version-controlled artefact is the single authority (inline registry in `app/__init__.py` vs Alembic tree), retirement of the other, end of unattended boot-time execution, drift detection at column level | AR-005, ADR-006, Master Plan 5.1 | Architecture decision needed | Phase 5 | ADR-006 stays PROPOSED until this exists. |
| B-5 | **PD-006 "verified state" definition** — equality criteria for a rehearsed restore | FD-005, ADR-006, ADR-007 | Architecture decision needed (Founder confirmation of the ADR-006 proposal) | Before any production mutation | |
| B-6 | **Audit retention/archival design** — retention classes and periods, archive format and custody, detection invariant, removal of `audit_logs` from the prune loop | AR-007, FD-008, ADR-012 | Architecture decision needed; then bounded implementation authorization | Before production certification; exposure ~2026-11-07 | ADR-012 stays PROPOSED. |
| B-7 | **Report route classification and default role sets** — 49 routes × 4 categories; role sets per category | AR-011, ADR-009 | Implementation design needed; depends on MP-D9 (Founder) | Phase 4 | ADR-009 stays PROPOSED FOR ADOPTION. |
| B-8 | **Operator-accountability storage** — schema columns vs coupled audit row; system-actor representation; workstation identifier; mandatory `shift_id` | AR-012, ADR-011 | Implementation design needed; schema path would need PD-004 | Phase 2b / Phase 3 | ADR-011 stays PROPOSED FOR ADOPTION. |
| B-9 | **FK enforcement prerequisites** — orphan scan across all FK columns on a copy; `ds-run`/`fault-run`/`inv-run` under ON; delete-path review; initializer/dataset-builder handling | AR-003, ADR-005 | Implementation design needed; implementation authorization needed | Phase 4 / Phase 5 | Architecture adopted; nothing enabled. |
| B-10 | **Business-date implementation questions** — invoice date rule, arrival/departure validation basis, shift-to-business-date mapping, basis-checking invariant, staleness threshold | AR-008, ADR-004 | Implementation design needed | Phase 3 | Architecture adopted. |
| B-11 | **Backup/restore mechanics** — manifest storage form, retention exemption for pre-mutation backups, restore location, key custody | AR-006, ADR-007 | Implementation design needed; implementation authorization needed | Phase 9 (or earlier bounded directive) | Target architecture adopted; restore absent. |
| B-12 | **Phase 1 contract defaults** CD-1, CD-3, CD-4 | ADR-002 | Founder confirmation at Phase 1 directive approval | Phase 1 | Defaults apply unless overridden. |

Founder decisions that remain open and gate items above: **MP-D9** (operator
profile; B-2, B-7, B-8), **MP-D4** (persistence engine; B-4, B-9), **MP-D1**,
**MP-D3**, **MP-D6**, **MP-D7**, **MP-D8** (at their phase gates, AR-015), and
the disposition of the eight D11 rows beyond FD-010 (B-3).
