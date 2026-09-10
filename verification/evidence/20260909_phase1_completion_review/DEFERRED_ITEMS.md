# Phase 1 - Known Defects, Findings and Deferred Items (baseline `aa6d9e91`)

Directive FG-P1-COMPLETION-REVIEW-20260909-01. Sources: `20260908_golden_master/KNOWN_DEFECTS.md` (K-1..K-20), `adr/BACKLOG.md` (B-1..B-12), execution report section 9, W-20 closure section 11, readiness report section 22, Founder rulings. Classifications use the directive's vocabulary. "FOUNDER DECISION REQUIRED" is used only where no existing ruling settles the matter.

## 1. K-series defects

| # | Item | Governance | Phase 1 effect | Classification |
|---|---|---|---|---|
| K-1 | INV-A02 VIOLATED 8/8 (4,776.19) on production | AR-001, FD-010 | Unchanged by design; HOLDS for new activity | **NO ACTION REQUIRED** at Phase 1 (expected baseline). Eight-row disposition: **DEFERRED TO LATER PHASE** (Phase 5, B-3; FD-010 says a separate Founder decision is needed *then*) |
| K-2 | INV-A03 VIOLATED (476.19) | as K-1 | Unchanged | as K-1 |
| K-3 | Eight D11 NULL-folio rows | D11-F2, FD-010 Option A, Q-2 | Untouched; correction now refused in code | **NO ACTION REQUIRED** (protected); see K-1 for disposition |
| K-4 | Folio attribution absent at every originating writer | Register R1, ADR-002 | All 24 writers attributed | **CLOSED BY PHASE 1** |
| K-5 | Audit atomicity gap | Q-5, ADR-008 | Closed for every touched financial writer; W-01/06/07 gained audit rows; shared `_write_audit` unchanged for non-financial callers by design | **CLOSED BY PHASE 1** for financial writers. The A-NF behaviour of `_write_audit` for *non-financial* callers **REMAINS OPEN** as an architecture item (not in Phase 1 scope; no ruling requires it yet) |
| K-6 | POS audit ordering | Q-5 | Charge + audit atomic | **CLOSED BY PHASE 1** |
| K-7 | Wall-clock / model-default dating at W-08/09/10/11/17/20/22/23; model defaults `date.today` | FD-013, ADR-004, **Q-3** | Untouched (verified: W-20 still `now.date()`) | **DEFERRED TO PHASE 3** (Q-3 explicit) |
| K-8 | Night-audit room rent NULL by design; folio balance excludes rent | ADR-003 | Attribution changed; balance semantics unchanged | **CLOSED BY PHASE 1** (attribution). Balance semantics: NO ACTION REQUIRED (adopted architecture) |
| K-9 | Business date stale; night audit never operated nightly | Register R8 | Untouched | **DEFERRED TO PHASE 3** |
| K-10 | Destructive audit-log pruning scheduled (`_prune_old_logs`, 90 d); first deletion ~2026-11-07 on a running instance | FD-008, ADR-012 PROPOSED, B-6 | Untouched (correctly - not in scope) | **REMAINS OPEN** - policy ruled (FD-008); architecture design (ADR-012 / B-6) and a bounded implementation directive still needed; **time-bound** |
| K-11 | Unattended scheduler is a financial writer without AR-013 controls | FD-009, AR-013, B-1 | Output now attributed; authority/timing unchanged | **DEFERRED TO PHASE 3 / 4** (B-1 ADR needed) |
| K-12 | FK enforcement off | ADR-005 ADOPTED (requirement), B-9 | Untouched; `foreign_key_check` still 0 | **DEFERRED TO LATER PHASE** (Phase 4/5; execution plan S8) |
| K-13 | `folio_id` nullable on both tables | AR-004 Stage G, B-3 | Untouched | **DEFERRED TO LATER PHASE** (Phase 5; S9; blocked by B-3 eight-row decision and B-4 mechanism) |
| K-14 | Migration mechanism undecided; inline registry at boot; Alembic orphaned, `alembic.ini` points at production | AR-005, ADR-006 PROPOSED, B-4 | Untouched | **DEFERRED TO LATER PHASE** (Phase 5) - an architecture decision (B-4) is required there; not needed for Phase 1 or Phase 2b code |
| K-15 | Authorization outside Phase 2a (seven guard idioms; 26 or more report routes reachable by any authenticated role) | Register R6, ADR-008/009, B-7 | Untouched; negative tests would use today's role sets | **DEFERRED TO PHASE 4** (ADR-009 awaits MP-D9 and route review) |
| K-16 | `list_folios` still `('Admin','Manager')` in code | **FD-015 approved** (Admin/Manager/Accountant/FrontDesk read) | Untouched (section 19 forbade it) | **REMAINS OPEN** - decision exists; needs a bounded implementation directive. Not a Founder decision. |
| K-17 | Restore from encrypted application backups not rehearsed; app backup path `shutil.copy2` | ADR-007, B-11 | Recovery Foundation covers `.db` restore (RR-20260908-01) and `.enc` by unit round-trip only | **REMAINS OPEN** (B-11); not a Phase 2 blocker |
| K-18 | Golden master HTML only (V5); 121 non-GET gaps; 5 unhealthy surfaces | Phase 6 | Unchanged | **NO ACTION REQUIRED** for Phase 1; Phase 6 |
| K-19 | INV-R01 NOT_COMMISSIONED; 7 VACUOUS | Wave 0 / Phase 6 | Unchanged | **NO ACTION REQUIRED** for Phase 1; Phase 6 |
| K-20 | Launchers LF-only | FD-017 exemption | Unchanged | **NO ACTION REQUIRED** |

## 2. Directive-named attention items

| Item | Classification | Basis |
|---|---|---|
| Business-date integrity | **DEFERRED TO PHASE 3** | Q-3; ADR-004 adopted; B-10 implementation design |
| Audit atomicity | **CLOSED BY PHASE 1** for financial writers; shared helper for non-financial callers REMAINS OPEN (architecture, unscheduled) | Q-5; K-5 |
| Maker-checker | **DEFERRED TO PHASE 2b** | ADR-010 PROPOSED; B-2 operation-matrix ADR needed; depends on MP-D9 |
| Authorization / reporting authorization | **DEFERRED TO PHASE 4** | ADR-008 adopted (architecture); ADR-009 PROPOSED FOR ADOPTION; B-7; MP-D9 |
| Audit retention | **REMAINS OPEN (time-bound, ~2026-11-07)** | FD-008 ruled; ADR-012 PROPOSED; B-6 |
| Scheduler controls | **DEFERRED TO PHASE 3 / 4** | FD-009 ruled; AR-013; B-1 ADR needed |
| Migration mechanism | **DEFERRED TO LATER PHASE (5)** - architecture decision B-4 required at that gate | K-14 |
| FK enforcement | **DEFERRED TO LATER PHASE (4/5)** | ADR-005 adopted as requirement; B-9; S8 |
| `folio_id NOT NULL` | **DEFERRED TO LATER PHASE (5)** | B-3; S9 |
| D11 historical exception | **NO ACTION REQUIRED** now; disposition beyond FD-010 **DEFERRED TO PHASE 5** where a separate Founder decision (B-3) is already flagged | FD-010, Q-2, AR-001 |
| Backup/restore limitations | **REMAINS OPEN** (B-11; K-17); PD-006 definition (B-5) needed before any production mutation | ADR-007 adopted; Recovery Foundation delivered the restore half |
| FD-015 / folio read access | **REMAINS OPEN** - implement under a bounded directive | FD-015 |
| Historical attribution gap (the eight rows) | **NO ACTION REQUIRED** at Phase 1 (unit 1.6 has no authorized action); **DEFERRED TO PHASE 5 / B-3** | FD-010, MP-D11 RULED |

## 3. Phase 1 execution findings (execution report section 9, W-20 closure section 11)

| Finding | Classification |
|---|---|
| T-W20 vacuous | **CLOSED BY PHASE 1** (W-20 runtime closure, 23/23) |
| Business-date defects untouched | DEFERRED TO PHASE 3 (Q-3) |
| S8 FK / S9 NOT NULL not executed | DEFERRED TO LATER PHASE (by design of the authorization) |
| FD-015 widening not implemented | REMAINS OPEN (bounded directive) |
| Production `inv-run` FAIL by design | NO ACTION REQUIRED (FD-010 consequence) |
| B-1, B-2, B-6 untouched | DEFERRED (Phase 3/4, 2b) / REMAINS OPEN (B-6, time-bound) |
| W-20 repeat call bills the newly elapsed hour | REMAINS OPEN as a **product-rule question**; pre-existing; not a Phase 1 defect (see COMPLETION_REVIEW section 8) |
| W-20 waive path audit-after-commit | NO ACTION REQUIRED for Phase 1 (not a financial writer); REMAINS OPEN under the general `_write_audit` item |
| `attribution_control` outside replay `NAS_SECTIONS` | REMAINS OPEN for Phase 6 ledger extension (deliberate) |

## 4. New carry-forward items raised by this review (not previously recorded)

| # | Item | Classification | Proposed owner |
|---|---|---|---|
| CF-1 | Runtime cases for the 18 static-only writers; audit-failure injection beyond W-05/W-15/W-20 | REMAINS OPEN - verification completion, or Founder acceptance of the static standard | bounded verification directive (copies only) |
| CF-2 | `inv-run` on a new-activity copy (A02/A03 HOLD; B01-B03 after a close) | REMAINS OPEN - verification completion | same |
| CF-3 | `ds-run` / `ds-coverage` six datasets; Q14 parity | REMAINS OPEN - verification completion | same |
| CF-4 | Phase 2a 29-case matrix re-run at `aa6d9e91` | REMAINS OPEN - verification completion | same |
| CF-5 | T-N02 unauthorized-role-per-writer negative cases | REMAINS OPEN - verification completion (low risk) | same |
| CF-6 | Replay ledger does not capture `attribution_control` | DEFERRED TO PHASE 6 | ledger re-baseline directive |
| CF-7 | Governance index: FG-P1-EXEC-20260909-01, Golden Master, W-20, precommit/commit/push directives and Phase 1 acceptance not recorded in `FOUNDER_DECISIONS.md` / `MASTER_PLAN.md` | REMAINS OPEN - documentation (governance records may not be edited under this review) | Founder acceptance entry |
| CF-8 | Golden Master carries 4 permanent declared differences until re-baselined at/after `aa6d9e91` | REMAINS OPEN - verification-only recapture (Q-4 precedent) needs authorization | bounded recapture directive |
| CF-9 | Phase 1 code not yet deployed to the live instance; pre-deployment live activity would create new NULL rows outside D11 | AWARENESS - release governed separately (MP-D3 / PD-*) | Founder |
