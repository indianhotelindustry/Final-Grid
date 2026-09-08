# Founder Decisions — FinalGrid

Durable record of Founder rulings that govern implementation sequencing.
Created 2026-09-05 under the Founder's D11 ruling directive, which
authorized this file as a governance/documentation change and nothing else.

A ruling recorded here is authoritative for engineering. A ruling that is
**not** recorded here exists only in a session transcript or a published
artifact and should be treated as provenance, not as a committed rule,
until the Founder authorizes its entry.

Standing rule for this file: entries are append-only. A ruling is never
edited after entry; a later ruling that changes it is added beneath it and
cross-referenced.

---

## D11-F2 — Historical folio attribution: factual ruling

| | |
|---|---|
| Ruled | 2026-09-05 |
| Ruling | **COMMISSIONING / TEST ACTIVITY** |
| Kind | Factual ruling only. Not an accounting-treatment ruling. |
| Recorded at | HEAD `237db2ad0fa8df143f04aaca82441f0f54781969`, branch `main` |
| Database at recording | `instance/pms.db` SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, 733,184 bytes, unchanged by this recording |

### Ruling text, verbatim

> D11-F2 — COMMISSIONING / TEST ACTIVITY.
>
> The Founder rules that the eight financial rows associated with the four
> August reservations were commissioning/engineering/test activity rather
> than genuine hotel trading.
>
> Important: This is a factual ruling only. It does not authorize deletion,
> reversal, modification, folio attribution, GST invoice alteration,
> night-audit alteration, or any other production-data mutation.
>
> Preserve all eight financial rows exactly as they currently exist.

### The rows this ruling names

All eight carry `folio_id NULL` and are preserved exactly as found. Nothing
in this ruling changes them.

| Row | Reservation | Amount | Business date | Created (UTC) | Day status at ruling |
|---|---|---|---|---|---|
| payments 1 | 1 | 800.00 | 2026-08-09 | 2026-08-10 09:14:10 | closed (night audit 2026-08-09, Completed) |
| payments 2 | 1 | 400.00 | 2026-08-09 | 2026-08-10 09:16:50 | closed |
| extra_charges 1 | 1 | 380.95 | 2026-08-09 | 2026-08-10 09:16:50 | closed |
| payments 3 | 2 | 1,500.00 | 2026-08-10 | 2026-08-11 06:25:23 | open (business date 2026-08-10, unlocked) |
| payments 4 | 3 | 1,000.00 | 2026-08-10 | 2026-08-11 06:26:22 | open |
| payments 5 | 4 | 500.00 | 2026-08-10 | 2026-08-11 06:30:40 | open |
| payments 6 | 4 | 100.00 | 2026-08-10 | 2026-08-11 06:32:20 | open |
| extra_charges 2 | 4 | 95.24 | 2026-08-10 | 2026-08-11 06:32:20 | open |

Total: 4,776.19. This is the population INV-A02 reports as violated
(8 of 8) and the population Phase 2a's case T29 froze by identity.

### Evidence the ruling rested on

Gathered read-only on 2026-09-05 and reported to the Founder before the
ruling. Recorded here so the ruling's basis survives the session.

- The live database was reset by the production initialization tool on
  2026-08-08 (`PRODUCTION_INITIALIZATION_REPORT.md`; pre-reset snapshot
  `backups/pms_PRE_TXN_RESET_20260809_104630.db`). All eight rows postdate
  the reset.
- The four reservations were created on 10 and 11 August 2026, during the
  DEF-004 / DEF-005 night-audit engineering sprint (commits `2dc8a61`,
  `d8dca24`), and each was checked in and out within seconds to minutes.
- Every row carries staff user `admin` and IP `127.0.0.1`. Session
  transcripts for the creation windows contain no automated request or
  script; the rows were entered by a person at the local console.
- Reopen reasons on the 2026-08-09 audit typed by a person: "testing",
  "testing", "test", "dfhd". Override reason on its completion: "cvnvhm".
  The one reopen performed by engineering names "DEF-004 recovery".
- Two of the four guest records carry the repository owner's contact email.
- Counter-indicators, also recorded: realistic guest names and phone
  numbers; GST invoices `INV-2026-000029` to `INV-2026-000032` finalised in
  the live numbering sequence; rooms left in Dirty status after checkout.

### What this ruling does and does not settle

- **Settled:** the eight rows are commissioning activity, not trading.
- **Not settled:** the accounting treatment of the eight rows. The D11
  options (A attribute, B forward-only, C declared exemption, Other) remain
  open and are the Founder's to choose. No option is authorized by this
  entry.
- **Not authorized:** any mutation of the eight rows, of the four
  reservations, of the four GST invoices, or of the 2026-08-09 night-audit
  record and its snapshot hash.
- **Unchanged:** INV-A02 and INV-A03 keep their definitions and keep
  reporting these rows. No invariant exemption exists.

### Consequences for sequencing

- Phase 1 unit 1.6 (historical row disposition) remains gated on the D11
  accounting-treatment ruling **and** on PD-4, PD-5, PD-6 with a rehearsed
  restore record, per the Founder's D10 ruling of 2026-09-05.
- Phase 1 unit 1.8 (re-verify INV-A02 and INV-A03) cannot report HOLDS in
  whole-database mode until the treatment ruling is made.
- The 53-entry finding register (published artifact, not committed) should
  carry D11-F2 against its D11 entry. Standing control SC-5 requires that
  update to be made under this ruling, not by engineering judgement.

### Provenance

- D11 was surfaced by the FinalGrid Implementation Master Plan Round 0
  (2026-08-31, published artifact `34821b10-b65f-45de-8695-5da3b541cd1d`),
  §03 and §11.
- The Founder accepted D11 as a required decision in the Master Plan ruling
  of 2026-08-31: "historical NULL folio attribution must not be chosen by
  engineering. Do not alter existing historical NULL attribution until the
  accounting treatment is explicitly decided."
- Phase 2a (`verification/evidence/20260831_phase2a_folio_authz/`) proved
  the eight rows untouched by identity (case T29).
- The Founder Decision Pack for D5 / D10 / D11 and the factual evidence
  dossier were delivered on 2026-09-05 in the Claude Code session
  `e69ac489-cdc9-4071-bbfd-3e52d9d2c080`; the ruling was issued in the same
  session.

---

## Related rulings from the same Founder record — reproduced for provenance

The D11 ruling directive of 2026-09-05 authorized the durable recording of
D11 only. The two rulings below were issued by the Founder in the same
decision record (2026-09-05) and are the basis on which the Phase 0.2
contract and the Phase 1 directive were prepared. They are reproduced here
verbatim so that D11-F2's context is complete. **They stand as recorded
rulings only if the Founder confirms this entry; until then treat them as
provenance.**

### D5 — Financial / folio floor

> Proposed ruling: LEVEL 2
>
> Folio attribution remains a foundational financial requirement of
> FinalGrid, independent of whether itemised split billing is exposed as a
> product feature.

### D10 — Backup / restore gate

> Proposed ruling: RE-SCOPE TO UNIT 1.6 / FIRST PRODUCTION DATA MIGRATION
>
> Phase 1 code work on disposable copies does not require completed D9.
> Any production-data mutation, including historical folio attribution,
> requires the applicable PD-4 / PD-5 / PD-6 controls and a rehearsed
> restore record before execution.

---

## Rulings known to exist but not yet recorded here

Listed so the gap is visible. Each exists in the 2026-08-31 session
transcript (`47bae5bd-0e38-4319-8000-980550f72777`) and nowhere in the
repository.

| Ruling | Date | Subject |
|---|---|---|
| FOUNDER-DIR-FINALGRID-BASELINE-RECON-003 | 2026-08-31 | Register corrections B-1 to B-5; R7 reclassified presently reachable; V9 |
| Master Plan Round 0 ruling | 2026-08-31 | Plan accepted; PD-1 (Phase 2a before Phase 1); D11 required; no Phase 1 schema migration; PD-6; phase reassignments F14/N4/N9 to 5, V3/V5 to 6, V8 to 3 |
| Phase 2a authorization | 2026-08-31 | Directive approved; defaults applied for its four decisions |
| End-of-day checkpoint | 2026-08-31 | Remote migration and checkpoint commit `237db2a` |

---

## FG-GOV-20260908-01 — Authoritative repository designation

| | |
|---|---|
| Ruled | 2026-09-08 |
| Ruling | **`C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` is the authoritative FinalGrid working repository** |
| Kind | Repository governance. Not an implementation authorization. |
| Directive | FG-GOV-20260908-01 |
| Recorded at | HEAD `237db2ad0fa8df143f04aaca82441f0f54781969`, branch `main` |
| Database at recording | `instance/pms.db` SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, 733,184 bytes, unchanged by this recording |

### Why the designation was needed

On 2026-09-08 two filesystem copies of FinalGrid were found to exist side by
side, each a complete Git repository carrying the same history and its own
copy of the production database at the frozen anchor. Nothing in either copy
recorded which one was authoritative, and both carry the same `origin`, so
either could push. This entry closes that ambiguity.

### The ruling

| | |
|---|---|
| **Authoritative working repository** | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` |
| **Preserved legacy / evidence duplicate** | `C:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS` |

- The two repositories were independently verified as identical before this
  designation was made.
- All subsequent FinalGrid work is performed against the authoritative path
  only. The legacy path is a preserved evidence copy, not a parallel working
  repository.
- The legacy copy must not be deleted, renamed, moved, archived, reset,
  cleaned, committed to, re-pointed, or otherwise modified without a
  separately authorized neutralization/archive action.
- **This designation is a governance decision. It does not authorize
  application implementation, schema change, data migration, Phase 0.2,
  Phase 1, or Phase 2b.**

### Historical evidence paths are preserved exactly as recorded

`verification/evidence/20260831_phase2a_folio_authz/result.json` records
`production_db` as the **legacy** path, because that is where Phase 2a was
executed on 2026-08-31. That record is correct as history and has **not**
been rewritten to make paths look consistent with this designation. The
Phase 2a evidence chain is unchanged: same three files, same contents, same
committed blobs, same frozen anchor. Any future evidence produced under this
designation will name the authoritative path; the difference is explained by
this entry, not by an edit to the earlier record.

### Verification supporting this entry

`verification/evidence/20260908_repo_identity_designation/`

---

## D5 — Financial / folio floor: confirmed ruling

| | |
|---|---|
| Ruled | 2026-09-05 · **confirmed 2026-09-08** under FG-GOV-20260908-01 |
| Ruling | **LEVEL 2** |
| Kind | Financial requirement. Not an implementation authorization. |
| Status | Confirmed Founder ruling. Authoritative for engineering. |

### Ruling text, verbatim

> D5 = Level 2.
>
> Every Payment and ExtraCharge must ultimately have a non-null `folio_id`,
> subject to the accepted implementation/data-migration sequencing.
>
> INV-A02 and INV-A03 remain in force.
>
> Level 3 split billing is a separate downstream decision and is **not**
> authorized by this directive.

### What this settles

- **Settled:** folio attribution is a foundational financial requirement of
  FinalGrid, independent of whether itemised split billing is ever exposed
  as a product feature. The end state is a non-null `folio_id` on every
  `Payment` and `ExtraCharge`.
- **Unchanged:** `INV-A02` (every financial row belongs to a folio,
  HIGH / certification-blocking) and `INV-A03` (charges summed over folios
  equal charges summed over reservations, HIGH / release-blocking) keep
  their definitions and keep reporting. No invariant exemption is created.
- **Not authorized:** Level 3 split billing, which remains a separate
  downstream decision.
- **Not authorized:** any production-data mutation. "Ultimately" is subject
  to the accepted sequencing, which for the historical rows means D11's
  accounting-treatment ruling and the D10 gate below.

### Relationship to the 2026-09-05 provenance entry

This entry **confirms** the D5 text reproduced under *"Related rulings from
the same Founder record — reproduced for provenance"* above. That section's
qualifier — that the two rulings stand as recorded rulings only if the
Founder confirms the entry — is satisfied for D5 by FG-GOV-20260908-01. Per
this file's append-only rule the earlier section is left exactly as written;
this entry supersedes its provisional status and is the operative record.

---

## D10 — Backup / restore gate: confirmed ruling

| | |
|---|---|
| Ruled | 2026-09-05 · **confirmed 2026-09-08** under FG-GOV-20260908-01 |
| Ruling | **RE-SCOPED TO UNIT 1.6 / FIRST PRODUCTION DATA MIGRATION** |
| Kind | Sequencing gate. Not an implementation authorization. |
| Status | Confirmed Founder ruling. Authoritative for engineering. |

### Ruling text, verbatim

> D10 is re-scoped to Unit 1.6 / the first production data migration.
>
> Phase 1 units 1.1-1.5 and 1.7 are not blocked by the former D9
> deliverable.
>
> Any production data mutation remains subject to PD-4, PD-5, PD-6 and a
> rehearsed restore record before execution.

### What this settles

- **Settled:** the D9 gate no longer blocks Phase 1 units 1.1-1.5 and 1.7.
  Phase 1 code work on disposable copies may proceed once separately
  authorized.
- **Still gated:** unit 1.6 (historical row disposition) and any first
  production data migration. Each remains subject to the applicable PD-4,
  PD-5 and PD-6 controls **and** a rehearsed restore record completed
  before execution.
- **D9 is not complete.** The D9 deliverable remains **Backup Restore
  Verification**. It is recorded as *Not started* in
  `verification/README.md` and *Blocked* in `verification/WAVE0_STATUS.md`,
  blocked at the schema because `backup_logs` carries no checksum column.
  Nothing in this ruling completes, closes, or waives D9.
- **No restore rehearsal was performed** under FG-GOV-20260908-01. The
  rehearsed restore record does not yet exist.
- **Not authorized:** any production-data mutation, and any Phase 1 unit.
  This entry removes a blocker; it does not start work.

### Relationship to the 2026-09-05 provenance entry

As with D5 above, this entry confirms the D10 text reproduced in the
provenance section and supersedes its provisional status. The earlier
section is left exactly as written.

---

## D11-F2 — reconfirmed, unchanged

Verified 2026-09-08 under FG-GOV-20260908-01. The D11-F2 entry recorded on
2026-09-05 at the top of this file is intact and was **not** edited.

Reconfirmed read-only against `instance/pms.db` (immutable connection;
SHA-256 identical before and after the read):

| Check | Result |
|---|---|
| `payments` with `folio_id IS NULL` | ids 1, 2, 3, 4, 5, 6 — 800.00, 400.00, 1500.00, 1000.00, 500.00, 100.00 |
| `extra_charges` with `folio_id IS NULL` | ids 1, 2 — 380.95, 95.24 |
| Population | 8 rows, total 4,776.19 — matches the D11-F2 table exactly |
| Database anchor | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, unchanged |

D11-F2 remains a **factual classification only**. It does not authorize
deletion, reversal, modification, folio attribution, GST invoice alteration,
night-audit alteration, or any other production-data mutation. The eight rows
remain untouched. `INV-A02` and `INV-A03` remain in force.

The **accounting treatment** of the eight rows (D11 options A / B / C /
Other) remains open and is the Founder's to choose. It is not settled by this
directive.

### Gap statement still accurate

The table *"Rulings known to exist but not yet recorded here"* above remains
correct as written. FG-GOV-20260908-01 did not authorize recording those four
2026-08-31 rulings, and they are still absent from this repository.

---

# Governance Resolution Round 1 — FG-P0-GOV-RECORD-20260908-01

| | |
|---|---|
| Recorded | 2026-09-08 |
| Directive | FG-P0-GOV-RECORD-20260908-01 — Founder Governance Resolution Recording |
| Preceded by | FG-P0-READINESS-20260908-01 (Phase 0 readiness baseline); FG-P0-GOV-RESOLUTION-20260908-01 (resolution pack, delivered in-session, not a repository record) |
| Recorded at | HEAD `237db2ad0fa8df143f04aaca82441f0f54781969`, branch `main` |
| Database at recording | `instance/pms.db` SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`, 733,184 bytes, unchanged by this recording |
| Scope | **Durable governance documentation only.** Nothing below authorizes application code, schema, data, database, scheduler, authorization, launcher, backup/restore or migration changes. Implementation of any decision requires a later explicit directive. |

The nineteen entries below are Founder-approved resolutions. They are
recorded verbatim where the Founder supplied wording. Each is appended
under this file's standing append-only rule; no earlier entry is edited.

## Namespace note, applying from this section onward

FD-001 adopts three namespaces. Their relationship to identifiers that
already appear in this file and in committed evidence is recorded here so
that no historical text needs to be rewritten:

| Historical identifier | Where it appears | Historical meaning | Treatment |
|---|---|---|---|
| `D5`, `D10`, `D11` (this file, entries above) | Founder rulings of 2026-09-05 / 2026-09-08 | Founder decisions | Remain as written. Aliases: D5 → FD-011 (Level 2), D10 → FD-006/FD-007 context (re-scope), D11 → D11-F2 (fact) + FD-010 (treatment). |
| `D1`–`D10` in `README.md`, `WAVE0_STATUS.md`, `ENGINEERING_GUIDE.md` | Wave 0 deliverables | Framework deliverables (D9 = Backup Restore Verification) | Remain as written. Never renamed. |
| `D1`–`D11` in the Implementation Master Plan (artifact) | Master Plan decision matrix | Planning decisions (D9 = operator profile) | Cited as **MP-D1…MP-D11** in repository text from now on. The artifact is not edited. |
| `PD-1` at line 164 above and in the Phase 2a completion report | Master Plan §11 "Deviations declared" | Plan deviation: run Phase 2a before Phase 1 | Historical. Not a member of the new PD-### namespace. |
| `PD-4`, `PD-5`, `PD-6` at lines 100, 150, 289, 299 above | Master Plan §08 "Production-data safety controls" | Production-data safety controls | Historical references. Their operative definitions are now **PD-004, PD-005, PD-006** under FD-005 below. |
| `PD-1`, `PD-2`, `PD-3` (Master Plan §08 sense) | Master Plan §08 | Never a dev target; anchor verification; evidence-pack policy | Not re-issued under FD-005. Remain provenance; their substance is carried by standing controls SC-1, SC-2 and SC-4 in `verification/MASTER_PLAN.md`. PD-001…PD-003 are **reserved and unassigned** in the new namespace. |

---

## FD-001 — Decision namespace

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance convention |

> Adopt:
>
> FD-### = Founder Decision
> PD-### = Production/Mutation Directive
> ADR-### = Architecture Decision Record
>
> Existing historical D# identifiers remain historical identifiers and must not be rewritten.

Consequences: new Founder rulings are numbered FD-###. Production or
mutation directives are numbered PD-###. Architecture Decision Records
live under `verification/adr/` and are numbered ADR-###; any ADR numbering
proposed before this ruling (including the provisional list in the
in-session resolution pack) is superseded and carries no authority.

---

## FD-002 — Master Plan authority

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Planning baseline |

> Adopt the Implementation Master Plan as the planning baseline.
>
> The repository must become the operational source of truth by recording the approved Master Plan durably.
>
> Claude artifact/transcript material remains provenance/reference material and is not itself the repository's authoritative implementation record.
>
> Do not invent or silently modify Master Plan content.

Recorded at `verification/MASTER_PLAN.md`, which transcribes the plan from
artifact `34821b10-b65f-45de-8695-5da3b541cd1d` (2026-08-31) and states
explicitly which parts are completed, adopted, proposed, blocked or not
started. The artifact remains provenance only.

---

## FD-003 — System-of-record boundary

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Product / financial architecture |

> Adopt:
>
> Reservation = stay unit
> Folio = billing unit
> Invoice = reservation-level document under current Level 2 decision
>
> Level 3 split billing remains outside the current scope.
>
> Corporate billing remains reservation-level unless separately redesigned and approved.

Evidence at recording: `Reservation.invoice_number` (`app/models.py:345`)
and the invoice route (`app/routes.py:3994`) are reservation-keyed;
company billing lives on `checkin_records.company_id`; `Folio.company_id`
is inert. This ruling makes that state the intended state under Level 2.
Architecture: ADR-001.

---

## FD-004 — Verification authority

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance |

> Adopt the following authority chain:
>
> Founder Decision → Governance/ADR → Implementation Directive → Code/Data Mutation → Verification Evidence
>
> Verification PASS does not independently authorize a production mutation.

---

## FD-005 — Production mutation controls

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Production safety controls — definitions |

> Adopt the following definitions:
>
> **PD-004 — Production Mutation Authorization**
> Explicit Founder authorization for a defined production schema/data mutation.
>
> **PD-005 — Production Mutation Protocol**
> Required sequence:
> backup → backup verification → recovery plan/rehearsal → execute mutation → post-mutation verification → invariant verification → evidence
>
> **PD-006 — Restore Verification**
> A rehearsed restore proving that the recovery artifact can actually restore the system to a verified state.
>
> These are mandatory production gates.
>
> Important: Recording these definitions does not authorize any production mutation.

State at recording, so the gate's satisfiability is on record: no restore
capability exists in `app/` or `tools/` (exhaustive search, 2026-09-08);
`backup_logs` carries no checksum column (`app/models.py:1463-1476`);
the application backup path uses `shutil.copy2`
(`app/backup_manager.py:206-208`). PD-006 therefore cannot currently be
satisfied. Architecture: ADR-006, ADR-007.

---

## FD-006 — D9 restore verification

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Deliverable definition (Wave 0 D9) |

> D9 is formally:
>
> Backup Restore Verification
>
> Backup creation alone does not satisfy D9.
>
> D9 remains a mandatory production-readiness gate.

"D9" here is the Wave 0 deliverable (`verification/README.md`,
`WAVE0_STATUS.md`), not Master Plan decision MP-D9 (operator profile).

---

## FD-007 — Migration authority

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance |

> No production schema/data migration may occur merely because engineering considers the implementation complete.
>
> Production migration requires:
>
> Founder-approved migration intent/scope;
> applicable PD-004 authorization;
> PD-005 execution protocol;
> verified PD-006 recovery capability;
> pre-mutation snapshot/hash;
> pre-mutation invariant state;
> controlled execution;
> post-mutation verification;
> post-mutation invariant state;
> retained evidence;
> defined recovery/rollback path.

State at recording: `_run_pending_migrations()` executes unattended at
every `create_app()` (`app/__init__.py:486`) and on updater restart
(`app/updater.py:589`); Alembic is present but has no caller and no
`alembic_version` table exists; `update.bat` globs `run_migration_*.py`.
Which mechanism is the single schema authority is **not decided by this
ruling** — see ADR-006 (unresolved item).

---

## FD-008 — Audit-log retention

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance |

> Adopt:
>
> Audit history must not be automatically deleted until a formally designed archival/retention mechanism has been approved and implemented.
>
> Do not modify or delete existing audit records as part of this directive.

State at recording: `_prune_old_logs` (`app/__init__.py:547-566`),
scheduled daily at 04:00, deletes `audit_logs` rows older than 90 days.
The oldest `audit_logs` row is dated 2026-08-09; the job would first
delete audit history on or about 2026-11-07 if the application is running.
This ruling makes that behaviour non-compliant; **it does not change it**.
A separate implementation directive is required. Architecture: ADR-012.
No audit row was read for modification or modified under this directive.

---

## FD-009 — Unattended scheduler

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance |

> No unattended process may perform a financially material production mutation unless that mutation path has explicitly satisfied the same applicable authorization, auditability, temporal, recovery, and verification controls required for an operator action.
>
> Do not implement this policy now.

State at recording: `night_audit_job` (posts room-rent charges, writes
`NightAuditLog`, advances the business date) is gated only by the
`night_audit_enabled` setting; `log_pruning_job` deletes audit rows;
both start with `create_app()`. Not changed.

---

## FD-010 — D11 accounting treatment: Option A

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | **Accounting-treatment decision.** Distinct from D11-F2, which is the factual classification recorded 2026-09-05 above. |

> Founder explicitly selects:
>
> **A — Preserve the eight D11 rows as historical commissioning/test records.**
>
> Record the following boundaries:
>
> The eight rows remain physically present.
> They remain untouched at this stage.
> They are classified as commissioning/test activity.
> No deletion is authorized.
> No rewriting is authorized.
> No artificial reversal/correction entry is authorized by this decision.
> No folio attribution is authorized by this decision.
> No invoice/GST modification is authorized.
> No night-audit modification is authorized.
> Existing immutable history remains preserved.
> Any future accounting treatment beyond this classification requires a separate Founder decision.

**D11-F2 is the factual classification. FD-010 is the Founder
accounting-treatment decision.** They are not the same ruling and must not
be conflated.

Rows governed (reconfirmed read-only at recording, database SHA-256
identical before and after): `payments` ids 1, 2, 3, 4, 5, 6 and
`extra_charges` ids 1, 2 — eight rows, ₹4,776.19, all `folio_id NULL`.

Disambiguation of the letter "A": the Implementation Master Plan §03 and
the in-session resolution pack labelled their option lists differently
(there, "(a)" / "A" meant *attribute the historical rows*). **FD-010's
"Option A" is defined solely by the Founder's text above — preserve,
untouched, classified as commissioning — and not by any earlier option
lettering.**

Consequence recorded, not decided: with the eight rows preserved
unattributed and no exemption declared, `INV-A02` continues to report
VIOLATED 8 of 8 (₹4,776.19) and `INV-A03` VIOLATED on the production
database, and the whole-database `inv-run` verdict remains FAIL. That is
the expected outcome of FD-010, not a defect. Whether an invariant
population declaration or constitutional amendment should follow is a
**separate Founder decision** that this entry does not make. Phase 1
unit 1.6 (historical row disposition) has no authorized action under
FD-010.

---

## FD-011 — Folio contract

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Financial architecture (Level 2 floor) |

> Adopt the Level 2 financial floor:
>
> Every Payment and ExtraCharge must ultimately have a non-null folio_id.
>
> Financial-originating writers must resolve the correct billing folio.
>
> Reversal/refund/replacement operations must preserve traceability.
>
> Level 3 split billing remains outside scope.
>
> The eight D11 rows are governed by FD-010 and must not be modified by this directive.

Confirms and extends D5 (Level 2) above. Architecture: ADR-002. The
Folio Ownership & Creation Contract (Phase 0 unit 0.2, artifact
`ea374fdc-c1ec-4c7d-9385-af33e486df74`, 2026-09-05) is the drafted
specification and is provenance until adopted through ADR-002.

---

## FD-012 — Room-rent ownership

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Architectural principle |

> Adopt the architectural principle that room-rent financial activity must ultimately participate consistently in the financial attribution model rather than remain a special un-attributed financial path.
>
> The exact implementation model requires an ADR.
>
> Do not implement it now.

State at recording: the night audit posts `room_rent` as `ExtraCharge`
rows with `folio_id NULL` (`app/services.py:148-156`, acknowledged at
`:2365`); `calculate_folio_total` excludes room rent by design
(`:2358-2370`); room revenue also exists as `ReservationNightRate` rows.
Architecture: ADR-003.

---

## FD-013 — Business-date authority

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Architectural principle |

> Adopt:
>
> Business date is the authoritative financial/operational accounting date.
>
> System clock timestamps may remain technical timestamps.
>
> Do not implement the date-authority refactor now.

State at recording: `Payment.payment_date` and `ExtraCharge.charge_date`
default to `date.today` at the model (`app/models.py:806-812`, `:775`);
the night audit stamps `charge_date` with the business date. Architecture:
ADR-004.

---

## FD-014 — Operator identity / profile

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Architectural principle |

> Adopt the architectural principle that financial accountability must distinguish:
>
> authenticated operator;
> role;
> operational responsibility;
> timestamp;
> business date;
> applicable workstation/IP provenance;
> maker/checker identity where required.
>
> Detailed implementation fields require ADR/design work.

Architecture: ADR-011. Master Plan decision MP-D9 (intended operator
profile) remains **open**; this entry adopts the accountability
principle, not the profile.

---

## FD-015 — `list_folios` read scope

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Authorization scope (read-only) |

> Founder approves:
>
> | Role | list_folios |
> |---|---|
> | Admin | Read |
> | Manager | Read |
> | Accountant | Read |
> | Front Desk | Read |
> | Other roles | No |
>
> This is read-only visibility.
>
> It does not grant mutation authority.
>
> Existing Phase 2a mutation authorization must not be weakened.

State at recording: `app/folio.py:47-52` `_FOLIO_ROLES['folio.list_folios']`
is `('Admin', 'Manager')`. The code is **not changed** by this recording;
the approved scope is a governance decision awaiting an implementation
directive. The three mutating endpoints (`create_folio`,
`transfer_charge`, `transfer_payment`) stay `('Admin', 'Manager')`
unchanged. This resolves the "For confirmation" item in
`verification/evidence/20260831_phase2a_folio_authz/COMPLETION_REPORT.md`
§2 in favour of the Phase 2a directive's recommended read scope.

---

## FD-016 — Application-wide authorization

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Architectural principle |

> Adopt:
>
> Authentication establishes identity.
> Authorization establishes whether that identity may perform the operation.
>
> The Phase 2a folio authorization work remains complete/frozen.
>
> Broader application authorization is future work and must be implemented progressively without reopening or weakening the completed Phase 2a gate.

Architecture: ADR-008, ADR-009, ADR-010.

---

## FD-017 — Launcher CRLF exemption

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Bounded reliability exemption |

> Approve a narrowly scoped mechanical reliability correction for the identified LF-only .bat launchers, provided that:
>
> it changes line endings only;
> application behavior is unchanged;
> the correction is separately verified;
> it is not bundled into unrelated implementation work.
>
> Do not perform the correction under this directive.

Files identified (all LF-only, zero CRLF, verified 2026-09-08):
`start.bat`, `start_pms.bat`, `stop.bat`, `update.bat`, `app_mode.bat`,
`enable_lan.bat`, `disable_lan.bat`, `reset_pms.bat`, `start_hidden.vbs`.
**Not corrected under this directive.** Register finding V10 remains
UNRESOLVED as to operator-machine reproducibility.

---

## FD-018 — Durable governance records

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance |

> Adopt:
>
> Accepted Founder decisions must become durable repository governance records before downstream implementation relies upon them.
>
> Governance records are append-only.
>
> Historical evidence must not be rewritten to make it appear that a later decision existed earlier.

State at recording: this file and
`verification/evidence/20260908_repo_identity_designation/` are untracked
working-tree files. FD-018 does not itself authorize a commit; commit
authorization is a separate Founder act.

---

## FD-019 — Production execution boundary

| | |
|---|---|
| Ruled | 2026-09-08 |
| Kind | Governance |

> Adopt:
>
> Implementation completion is not production authorization.
>
> No production schema/data mutation may occur without the applicable Founder decision and production safety gates.
>
> This is the final boundary between engineering readiness and production execution.

---

## Items this round did not decide

Recorded so the remaining gaps stay visible.

| Item | Status |
|---|---|
| Recording of the four 2026-08-31 rulings (BASELINE-RECON-003, Master Plan Round 0 ruling, Phase 2a authorization, end-of-day checkpoint) | Still absent from this repository. The gap table above remains accurate. `verification/MASTER_PLAN.md` records their *effects* with provenance, not the rulings themselves. |
| Single schema authority (inline registry vs Alembic) | Not decided. ADR-006 marks it unresolved. |
| Invariant population declaration / constitutional amendment following FD-010 | Not decided. |
| Master Plan decisions MP-D1, MP-D3, MP-D4, MP-D6, MP-D7, MP-D8, MP-D9 | Open. MP-D2 partially answered by the accepted rebrand. |
| Commit of the governance records | Not authorized by this directive. |
| Neutralization / archive of the legacy repository copy | Not authorized; preserved untouched. |
