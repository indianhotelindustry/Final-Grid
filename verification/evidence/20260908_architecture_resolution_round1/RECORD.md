# FinalGrid — Architecture Resolution Round 1

| | |
|---|---|
| Directive | FG-P0-ARCH-RESOLUTION-20260908-01 |
| Recorded | 2026-09-08 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` (authoritative per FG-GOV-20260908-01) |
| Branch | `main` |
| Governed HEAD at recording | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` (parent `237db2ad…`, the Phase 2a checkpoint) |
| Database at recording | `instance/pms.db` SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, 733,184 bytes — unchanged |
| Scope | **Architecture resolution and durable recording only.** Nothing in this record authorizes or performs application, schema, database, migration, authorization, backup, scheduler, reporting, folio, audit or financial changes. |

## 1. Purpose

Record the Founder's Architecture Resolution Round 1 (AR-001…AR-015) as
the current architectural decisions for FinalGrid; reconcile them against
the governance record (`verification/FOUNDER_DECISIONS.md`), the Master
Plan record (`verification/MASTER_PLAN.md`) and the twelve ADR drafts
(`verification/adr/`); update ADR status only where justified; recover
the four unrecorded 2026-08-31 rulings from repository/history evidence
only; and state what remains unresolved.

## 2. Three things this record keeps separate

| Resolved architecture | Implemented control | Verified production state |
|---|---|---|
| What the Founder has decided the system must become (AR-###) | Code/data/config that exists and enforces it | Evidence that the running system actually exhibits it |

Every AR below is in the first column only. Where the second or third
column is empty, it is stated as such.

---

## 3. Architecture Resolutions — recorded verbatim

### AR-001 — D11 / INV-A02 treatment

> Keep **INV-A02 universal**.
>
> The D11 commissioning/test rows are a **historical known exception in existing data**, not an exemption from the invariant.
>
> The system architecture must continue to target: *Every financial payment/extra-charge transaction requires valid folio attribution.*
>
> Do not weaken, special-case, or redesign INV-A02 merely because the eight historical D11 rows currently have `folio_id = NULL`.
>
> D11 classification and accounting treatment are separate from the future system invariant.

State at recording: `INV-A02` (`verification/invariants/rules_a.py:144-175`) is unchanged and universal; production `inv-run` reports it VIOLATED 8 of 8 (₹4,776.19) — the known historical exception. No population declaration or constitutional amendment is made. **Implemented:** the invariant already is universal. **Verified state:** VIOLATED on production by design of FD-010.

### AR-002 — Room-rent ownership

> Adopt **M3**: *The reservation remains the operational source for determining the stay and room-rate entitlement; the resulting room-rent financial transaction belongs to the reservation's billing folio.*
>
> Interpretation: reservation owns the operational stay/rate context; folio owns the financial billing transaction; room-rent revenue posting is therefore a folio financial transaction; reservation remains the upstream operational source; Level 2 remains the current billing architecture; Level 3 split billing is not being authorized by this decision.
>
> The Founder selected this model as the industry-aligned architecture after review of standard hotel PMS folio/billing models. Do not expand this decision into multi-folio or split-billing functionality.

**The architecture recorded is the Founder's stated definition above.**

**Label discrepancy — REQUIRES FOUNDER CONFIRMATION.** ADR-003 (drafted 2026-09-08, before this round) labelled three candidate models: **M1** = keep posting `room_rent` charge rows and attribute them to the reservation's Folio A; **M2** = reservation-level exemption; **M3** = derive-only, *stop posting* room-rent rows. The Founder's text ("the resulting room-rent financial transaction belongs to the reservation's billing folio… room-rent revenue posting is therefore a folio financial transaction") describes ADR-003's **M1**, not its M3. ADR-003's M3 has no posted transaction to attribute and is incompatible with the text. This record does not resolve the letter; it records the substance and flags the label. ADR-003 is held at PROPOSED until the Founder confirms the mapping.

State at recording: night audit posts `room_rent` `ExtraCharge` rows with `folio_id NULL` (`app/services.py:148-165`); `calculate_folio_total` excludes room rent (`:2358-2370`). **Implemented:** no. **Verified state:** unattributed.

### AR-003 — SQLite foreign-key enforcement

> SQLite foreign-key enforcement must eventually be enabled on **every application database connection**. The implementation must not rely on individual callers remembering to enable it. This is an architecture requirement, not an implementation authorization.

State at recording: no `PRAGMA foreign_keys = ON` anywhere in `app/`; set OFF explicitly by `tools/production_initialize.py:296` and the dataset builder. **Implemented:** no. **Verified state:** FKs not enforced.

### AR-004 — `folio_id` NOT NULL strategy

> Use a **staged enforcement strategy**. Do not immediately impose `NOT NULL`.
>
> Required sequence: (1) establish attribution in every originating financial writer; (2) establish valid FK relationships; (3) backfill/reconcile legitimate existing financial rows under an explicitly authorized data-migration plan; (4) prove population and integrity preconditions; (5) only then enforce `folio_id NOT NULL`.
>
> The exact migration mechanics remain an implementation-phase concern. Historical D11 rows must not be mutated under this architecture-resolution task.

Dependency recorded, not resolved: step 5 cannot be reached while any row is NULL. Under FD-010 the eight D11 rows are preserved unattributed and no attribution is authorized; AR-004 step 3 speaks of *legitimate* existing rows and D11-F2 classifies the eight as commissioning activity, not trading. Whether and how the eight rows are disposed of before step 5 is **a separate future Founder decision** (FD-010 last clause). **Implemented:** no (24 originating writers leave `folio_id` NULL). **Verified state:** both columns nullable; 8 NULL rows.

### AR-005 — Schema authority

> The **repository migration files are authoritative for schema evolution**. The live SQLite database is evidence of current state, not the authoritative definition of future schema evolution.
>
> Schema changes must therefore be: represented in version-controlled migration artifacts; reproducible; reviewable; auditable; executed only through authorized migration procedures. Do not perform any migration now.

Unresolved mechanism, recorded as such: the repository holds two version-controlled migration artefacts — the inline registry in `app/__init__.py` (57 entries, tracked in `schema_migrations`, live) and the Alembic tree `migrations/versions/` (7 revisions, no caller, no `alembic_version` table). AR-005 establishes the principle; **which artefact is the single authority is not decided by AR-005** and is not inferred here (ADR-006 unresolved item; Master Plan Phase 5 unit 5.1). **Implemented:** the inline registry executes unattended at boot (`app/__init__.py:486`, `app/updater.py:589`) — not through an "authorized migration procedure". **Verified state:** non-compliant with the principle.

### AR-006 — Backup / restore architecture

> The target recovery architecture is: SQLite backup API or equivalent transactionally safe database backup mechanism; integrity verification; cryptographic hash; machine-readable backup manifest; retained recovery artifact; rehearsed restore; documented restore verification.
>
> The restore path must be treated as a first-class capability rather than assuming that a backup file existing on disk proves recoverability. No backup/restore implementation is authorized by this directive.

State at recording: application backup uses `shutil.copy2` (`app/backup_manager.py:206-208`); no checksum; **no restore capability exists** in `app/`, `tools/` or any launcher; Wave 0 D9 (Backup Restore Verification) remains Blocked/Not started. **Implemented:** no. **Verified state:** unrecoverable by any evidenced procedure.

### AR-007 — Audit retention

> **No destructive audit-log pruning is authorized until an archival/retention design is established and approved.** The current destructive 90-day pruning behavior is therefore an architecture concern that must be addressed before production certification. Do not modify the scheduler or pruning implementation during this task. Do not delete existing audit records.

State at recording: `_prune_old_logs` (`app/__init__.py:547-566`) still deletes `audit_logs` rows older than 90 days daily at 04:00; oldest row 2026-08-09; first deletion on or about 2026-11-07 if the application runs. **Implemented:** no — pruning remains destructive. **Verified state:** 23 audit rows, none yet eligible.

### AR-008 — Business-date authority

> The **controlled business date** is authoritative for financial and operational accounting. System timestamps remain technical timestamps for: event chronology; diagnostics; infrastructure logging; audit timing.
>
> Financial/operational logic must not silently substitute `date.today()` or equivalent wall-clock assumptions for the controlled business date where business-date semantics apply. No code changes are authorized now.

State at recording: `Payment.payment_date` and `ExtraCharge.charge_date` default to `date.today` at the model (`app/models.py:806-812`, `:775`); refund and correction paths use `date.today()`; night audit uses the business date. **Implemented:** no. **Verified state:** mixed temporal basis in one column.

### AR-009 — Authorization architecture

> The target authorization chain is: **Authentication → Role/Permission → Operation → Audit**. Authentication alone is not sufficient authorization.
>
> Phase 2a authorization hardening remains frozen as completed evidence and must not be reopened or modified during this documentation task. Future authorization work must extend the architecture consistently rather than bypassing the Phase 2a boundary.

State at recording: `app/folio.py` byte-identical to the checkpoint blob; Phase 2a evidence intact. Elsewhere seven guard idioms; ≥26 report routes behind login only. **Implemented:** on `folio_bp` only. **Verified state:** Phase 2a 29/29 PASS; rest unverified.

### AR-010 — Maker-checker

> Adopt **maker-checker as an architectural control principle** for operations where separation of initiation and approval is required. The detailed operation matrix must be defined in a dedicated ADR / implementation decision before implementation. Do not implement or change maker-checker behavior now.

State at recording: void/refund maker-checker exists (preserved strength N2); shift-close approval exists; folio mutations are single-actor with audit. **Implemented:** partially, unaligned. **Verified state:** as above.

### AR-011 — Reporting authorization

> Reports are protected application capabilities and must have appropriate authorization. The future authorization model must explicitly cover report access rather than treating reports as implicitly public merely because they are read-only. Do not change existing report routes now.

State at recording: `app/reports.py` — 49 routes, one `@login_required` `before_request`, 23 inline `_require_accountant()` calls; ≥26 routes unrestricted beyond login. **Implemented:** no. **Verified state:** unrestricted.

### AR-012 — Operator accountability

> Material operational and financial actions must be attributable to: operator identity; operator role; action; relevant business date; provenance/context sufficient to explain the action. Where automated/system actions exist, the architecture must provide equivalent accountability through controlled system identity/provenance. Do not implement this now.

State at recording: `payments`/`extra_charges` carry no operator, role, shift or IP column; `audit_logs` carries `staff_user_id`, `ip_address`, `timestamp` but not role or business date. **Implemented:** partially. **Verified state:** the eight D11 rows could be attributed to a person only by cross-referencing audit and session evidence.

### AR-013 — Financial scheduler actions

> Any scheduler/automation action capable of materially changing financial or operational state must operate under a controlled architecture providing: explicit authorization; identifiable system/operator provenance; business-date authority; auditability; idempotency; failure handling; verification. An unattended scheduler must not become an uncontrolled financial writer. Do not change or re-enable scheduler behavior under this task.

State at recording: one `BackgroundScheduler` (`app/services.py:6`) starts with `create_app()`; `night_audit_job` posts room-rent rows and advances the business date under the `night_audit_enabled` setting only; `log_pruning_job` deletes audit rows with no switch. **Implemented:** no. **Verified state:** non-compliant. No dedicated ADR exists; one is required at the appropriate phase gate (Phase 3 / Phase 4) and is **not created here** (AR-015).

### AR-014 — Four unrecorded 2026-08-31 Founder rulings

See §6. Result: **exact rulings NOT RECOVERED from repository/history; fragments and effects recovered with sources.**

### AR-015 — Remaining Master Plan decisions

> Remaining decision gaps in the Implementation Master Plan should be resolved **at their appropriate phase gates**. Do not prematurely close implementation decisions merely because the architecture is now clearer. The Master Plan remains the sequencing authority. Architecture decisions should be recorded now only where sufficiently settled.

Applied throughout §7 and §8. MP-D1, MP-D3, MP-D4, MP-D6, MP-D7, MP-D8, MP-D9 remain OPEN; MP-D2 partially answered by the rebrand. The eleven-phase sequence is unchanged.

---

## 4. D11 — the distinction, stated explicitly

| Ruling | Kind | Content | Source |
|---|---|---|---|
| **D11-F2** (2026-09-05) | Factual classification | The eight August financial rows (payments 1–6, extra_charges 1–2; ₹4,776.19) are commissioning/test activity, not trading | `verification/FOUNDER_DECISIONS.md` §D11-F2 |
| **FD-010** (2026-09-08; cited as "FD-10" in the directive) | Accounting treatment — Option A | Preserve the rows as historical commissioning/test records; make no corrective financial entries; no deletion, reversal, reclassification-by-mutation, folio assignment, invoice/GST or night-audit alteration | `verification/FOUNDER_DECISIONS.md` §FD-010 |
| **AR-001** (2026-09-08) | Architecture | INV-A02 stays universal; the eight rows are a historical known exception in data, not an exemption | this record |

Consequence: production `INV-A02` remains VIOLATED 8/8 and the whole-database verdict FAIL **by design**, and this is compatible with a universal future-state invariant. Reconfirmed read-only at recording: the eight rows are present, NULL, untouched; the database hash is unchanged.

## 5. FD-015 — `list_folios` read scope (recorded decision, not implemented)

Admin, Manager, Accountant, Front Desk — Read; other roles — No. Read-only visibility; mutation endpoints unchanged. Code at recording: `app/folio.py:47-52` `('Admin','Manager')`. **Not modified.**

---

## 6. AR-014 — recovery of the four 2026-08-31 rulings

**Method.** Searched only authoritative repository/history artefacts: `git log --all -S` for `RECON-003`, `RECON-002`, `BASELINE-RECON`, `TARGET-001`, `REBRAND-001`, `Round 0`, `Master Plan`, `end-of-day`, `checkpoint`; full commit messages of `2765702`, `727d6ce`, `b8bc152`, `d85ec2f`, `237db2a`, `e69f2ac`; tree-wide grep of `.md/.txt/.json/.py` excluding `venv/`, `.git/`, `python/`; `README.md`; `verification/evidence/20260831_*`; `verification/FOUNDER_DECISIONS.md`; `verification/MASTER_PLAN.md`. Claude artifacts and session transcripts were **not** used, per AR-014.

**Finding.** No ruling exists verbatim anywhere in the repository or its history. The only history hits for the ruling identifiers are `e69f2ac` (the 2026-09-08 governance commit, which records their *absence*) and `d85ec2f` (`TARGET-001` as an authorization citation).

| Ruling | Status | Recovered fragments / effects | Source (path · commit) | Relationship to AR-001…015 |
|---|---|---|---|---|
| **FOUNDER-DIR-FINALGRID-BASELINE-RECON-003** (register corrections B-1…B-5; R7 reclassified presently reachable; V9) | **NOT RECOVERED — REQUIRES FOUNDER CONFIRMATION** | Effect only: R7 treated as presently reachable in commit `2765702` ("reachable by any authenticated account… already executed against live data"). Summary line in the gap table, written 2026-09-05, is a description not the ruling. | `verification/FOUNDER_DECISIONS.md` L164 · `2765702add3f…` message | Effects incorporated (Phase 2a completed; AR-009). Ruling text still absent. |
| **Master Plan Round 0 ruling** (plan accepted; deviation PD-1; D11 required; no Phase 1 schema migration; §08 PD-6; reassignments F14/N4/N9→5, V3/V5→6, V8→3) | **NOT RECOVERED — REQUIRES FOUNDER CONFIRMATION** (one verbatim sentence recovered) | Verbatim fragment recorded 2026-09-05: *"historical NULL folio attribution must not be chosen by engineering. Do not alter existing historical NULL attribution until the accounting treatment is explicitly decided."* Effects: plan adopted (FD-002); D11 ruled; Phase 2a executed before Phase 1. | `verification/FOUNDER_DECISIONS.md` L110-114, L164 · `verification/MASTER_PLAN.md` §11-§12 | Superseded in part: FD-002 adopts the plan; FD-010 and AR-001 resolve D11; FD-005 supersedes §08 PD-4/5/6 with PD-004/005/006. Full text still absent. |
| **Phase 2a authorization** (directive approved; four §13 defaults applied) | **NOT RECOVERED — REQUIRES FOUNDER CONFIRMATION** (one verbatim clause recovered) | Verbatim fragment: the authorization said *"proceed exactly within the directive's stated scope and constraints"*. Authorization citations on all five commits: "Authorized by: FOUNDER-DIR-FINALGRID-TARGET-001 Phase 2a directive" / "(accepted)". Defaults applied: read scope Admin/Manager; strict audit; refusals recorded. | `verification/evidence/20260831_phase2a_folio_authz/COMPLETION_REPORT.md` L33-34, L158 · `2765702`, `727d6ce`, `b8bc152`, `d85ec2f`, `237db2a` messages | Still active; Phase 2a frozen by FD-016/AR-009. Default #2 (read scope) superseded by FD-015. |
| **End-of-day checkpoint** (remote migration; checkpoint commit `237db2a`) | **NOT RECOVERED — REQUIRES FOUNDER CONFIRMATION** (artefact recovered; authorization wording not) | The commit itself, its message ("Authorized by: FOUNDER-DIR-FINALGRID-REBRAND-001 (accepted) and FOUNDER-DIR-FINALGRID-TARGET-001 Phase 2a (accepted)"), the reflog fast-forward at 2026-08-31 21:49:03, and `.git/config` `origin = …/Final-Grid.git`. | `237db2ad0fa8df143f04aaca82441f0f54781969` · `.git/logs/HEAD` · `.git/config` · `verification/FOUNDER_DECISIONS.md` L165 | Superseded by FG-GOV-20260908-01 (repository designation) and `e69f2ac`. |

Additional observation: a fifth directive, **FOUNDER-DIR-FINALGRID-REBRAND-001 (accepted)**, is cited in `237db2a`'s message and has no text in the repository either. Recorded; not one of the four.

**Stop-condition handling.** The directive's stop condition ("the four rulings cannot be recovered exactly") is met for all four. AR-014 itself prescribes the recording above for that case, so this round proceeded on every other item and records the recovery outcome without fabrication. The rulings remain to be confirmed by the Founder.

---

## 7. ADR reconciliation

Status vocabulary (recorded in `verification/adr/README.md`): DRAFT → PROPOSED (principle Founder-resolved; material technical choices open) → PROPOSED FOR ADOPTION (Founder-resolved; remaining work is formal review/adoption) → ADOPTED → SUPERSEDED. **No ADR is marked ADOPTED by this round.**

| ADR | Founder resolution(s) | Previous → new status | Justification / what stays open |
|---|---|---|---|
| ADR-001 System-of-record boundary | FD-003, AR-002 | DRAFT → **PROPOSED FOR ADOPTION** | Boundary settled (reservation = stay, folio = billing, invoice reservation-level); residual questions (MP-D4 engine, OTA identity, invoice date) deferred to phase gates under AR-015 |
| ADR-002 Folio attribution contract | FD-011, AR-001, AR-004, AR-002 | DRAFT → **PROPOSED FOR ADOPTION** | INV-A02 universal; NOT NULL staged; CD-2 resolved by AR-002; CD-1/CD-3/CD-4 defaults to be confirmed at Phase 1 directive approval |
| ADR-003 Room-rent ownership | FD-012, AR-002 | DRAFT → **PROPOSED** | Substance resolved; **model label M3/M1 requires Founder confirmation** before PROPOSED FOR ADOPTION |
| ADR-004 Business-date authority | FD-013, AR-008 | DRAFT → **PROPOSED FOR ADOPTION** | Principle and consequences settled; invoice date, arrival validation basis, shift mapping are Phase 3 gate items |
| ADR-005 SQLite FK enforcement | AR-003 | DRAFT → **PROPOSED FOR ADOPTION** | Enable on every connection, not caller-dependent (option E1); orphan scan and re-runs are implementation prerequisites |
| ADR-006 Production mutation controls | FD-005, FD-007, FD-019, AR-005 | DRAFT → **PROPOSED** | PD-004/005/006 and the schema-authority *principle* settled; **migration mechanism (inline registry vs Alembic) and "verified state" definition unresolved** |
| ADR-007 Backup/restore architecture | FD-005, FD-006, AR-006 | DRAFT → **PROPOSED FOR ADOPTION** | Target components enumerated by AR-006 (manifest required); storage form, retention, key custody are implementation mechanics |
| ADR-008 Application authorization | FD-015, FD-016, AR-009 | DRAFT → **PROPOSED FOR ADOPTION** | Chain settled; Phase 2a frozen; HTML refusal shape and map location are implementation-level; MP-D9 deferred |
| ADR-009 Reporting authorization | AR-011 | DRAFT → **PROPOSED** | Principle settled; route classification and role sets unresolved |
| ADR-010 Maker-checker | AR-010, FD-014 | DRAFT → **PROPOSED** | Principle settled; **operation matrix requires a dedicated ADR/decision** (AR-010) |
| ADR-011 Operator accountability | FD-014, AR-012 | DRAFT → **PROPOSED** | Principle settled incl. system identity; storage location unresolved |
| ADR-012 Audit retention | FD-008, AR-007 | DRAFT → **PROPOSED** | No destructive pruning until design approved; **retention design itself not yet approved** |

ADRs that are required but **deliberately not created** in this round (AR-015): financial scheduler controls (AR-013); maker-checker operation matrix (AR-010); `folio_id` NOT NULL migration mechanics (AR-004, Phase 5 gate); schema-mechanism selection (AR-005, Phase 5 unit 5.1).

## 8. Master Plan reconciliation

`verification/MASTER_PLAN.md` gains an appended §14 overlay: AR→phase mapping; phases still gated; implementation prerequisites; the statement that architecture resolution ≠ implementation authorization. The eleven-phase sequence is unchanged. No sequencing dependency in the plan is made unsafe by AR-001…AR-015: Phase 1 still requires no schema migration; unit 1.6 stays gated (FD-010/AR-004); Phase 5 remains the first phase where migration is possible (AR-005); Phase 9 remains the recovery phase (AR-006).

## 9. Architecture consistency check — read-only, 2026-09-08

| Area | Check | Result |
|---|---|---|
| Financial model | D5 Level 2 intact (FD-011); INV-A02/A03 universal (AR-001; `rules_a.py` unchanged vs HEAD); D11 rows historical exception only; AR-002 confined to Level 2 (no multi-folio) | ✅ consistent |
| Governance | FD-010 recorded distinctly from D11-F2; FD-015 recorded; D10 still scoped to unit 1.6 / first production data migration; PD-004/005/006 distinct from plan-deviation PD-1…4 (namespace note, `FOUNDER_DECISIONS.md` L366) | ✅ consistent |
| Recovery | Wave 0 D9 still Blocked/Not started; no restore function in `app/`/`tools/`; AR-006 recorded as target, not as capability | ✅ consistent |
| Audit | `_prune_old_logs` still present and destructive; AR-007 recorded as unresolved implementation concern | ✅ consistent |
| Authorization | `app/folio.py` identical to HEAD blob; FD-015 recorded, code `('Admin','Manager')` unchanged | ✅ consistent |
| Schema | No `PRAGMA foreign_keys=ON` in `app/`; both `folio_id` columns nullable; AR-003/AR-004 recorded as targets | ✅ consistent |
| Scheduler | Scheduler code unchanged; AR-013 recorded as non-compliant current state | ✅ consistent |
| Business date | `date.today` model defaults still present; AR-008 recorded as architecture only | ✅ consistent |
| Repository | Only governance files touched; 46 pre-existing dirty entries preserved; legacy copy fingerprints unchanged | ✅ consistent |
| Label conflict | AR-002 "M3" vs ADR-003 model letters | ⚠️ **flagged — requires Founder confirmation** |
| Namespace | `AR-###` identifier used by the directive is not among the namespaces adopted by FD-001 (FD/PD/ADR) | ⚠️ recorded; Founder may wish to adopt or fold into FD |

## 10. Unresolved items

1. **AR-002 label:** Founder's "M3" ≠ ADR-003's M3; substance = ADR-003's M1. REQUIRES FOUNDER CONFIRMATION.
2. **AR-014:** all four 2026-08-31 rulings NOT RECOVERED verbatim; fragments recorded. REQUIRE FOUNDER CONFIRMATION.
3. **AR-004 step 5 vs FD-010:** NOT NULL unreachable while the eight rows are NULL; disposition of the eight rows is a separate future Founder decision.
4. **AR-005 mechanism:** inline registry vs Alembic — UNRESOLVED (Phase 5 unit 5.1).
5. **AR-006:** "verified state" definition for PD-006 — UNCONFIRMED (ADR-006 proposal).
6. **AR-007:** retention design — not yet designed or approved; deadline pressure ~2026-11-07.
7. **AR-010:** operation matrix — dedicated ADR required.
8. **AR-013:** dedicated scheduler-controls ADR required.
9. **MP-D1, MP-D3, MP-D4, MP-D6, MP-D7, MP-D8, MP-D9** — OPEN at their phase gates (AR-015).
10. **FOUNDER-DIR-FINALGRID-REBRAND-001** text — not in repository.
11. **`AR-###` namespace** — not adopted by FD-001.
12. Phase 1 contract defaults CD-1, CD-3, CD-4 — to be confirmed at Phase 1 directive approval.

## 11. Explicit no-implementation boundary

This round changed governance/architecture documentation only. It did not modify application code, schema, database contents, the eight D11 rows, migrations, FK enforcement, authentication/authorization, report access, audit retention/pruning, backup or restore, scheduler, business-date handling, maker-checker, financial or room-rent posting, or UI. No commit and no push were made; the working tree's pre-existing dirty state is preserved; the legacy repository is untouched. **Implementation authorization will be issued separately after architecture review/adoption.**
