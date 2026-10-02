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

---

# Architecture Resolution Round 1 — FG-P0-ARCH-RESOLUTION-20260908-01 (index entry)

| | |
|---|---|
| Recorded | 2026-09-08 |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` |
| Record | `verification/evidence/20260908_architecture_resolution_round1/RECORD.md` and `result.json` |
| Kind | Founder architecture resolutions AR-001…AR-015. **Not an implementation authorization.** |

The fifteen resolutions are recorded verbatim in the record above and are
not repeated here. Cross-references for this file:

- **AR-001** keeps `INV-A02` universal; the eight D11 rows are a historical known exception in data, not an exemption. This closes the open item "Invariant population declaration / constitutional amendment following FD-010" in the Round 1 table above: **no declaration or amendment is made**; the production verdict remains FAIL by design.
- **AR-002** room-rent ownership: substance recorded; the model label ("M3") does not match the ADR-003 candidate labels and **requires Founder confirmation**.
- **AR-014**: the four 2026-08-31 rulings were searched for in repository and git history only. **None was recovered verbatim.** Fragments and effects are recorded with sources. The gap table above remains accurate. Each is marked NOT RECOVERED — REQUIRES FOUNDER CONFIRMATION.
- **Namespace note:** the directive introduces the identifier `AR-###` (Architecture Resolution). FD-001 adopted `FD-###`, `PD-###` and `ADR-###` only. `AR-###` is used here exactly as issued and is not promoted to a namespace by this entry; the Founder may adopt it or fold future architecture resolutions into `FD-###`.
- **ADR status changes:** six ADRs moved DRAFT → PROPOSED FOR ADOPTION (001, 002, 004, 005, 007, 008); six moved DRAFT → PROPOSED (003, 006, 009, 010, 011, 012). **None is ADOPTED.**
- `verification/MASTER_PLAN.md` gains an appended §14 overlay; the eleven-phase sequence is unchanged.

No application code, schema, database, migration, authorization,
backup/restore, scheduler, reporting, folio, audit or financial change was
made. No commit, no push.

---

# ADR Adoption Baseline — FG-P0-ADR-ADOPTION-20260908-01

| | |
|---|---|
| Recorded | 2026-09-08 |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` |
| Record | `verification/evidence/20260908_architecture_resolution_round1/ADR_ADOPTION_READINESS.md` and `.json` |
| Kind | Architecture closure and ADR adoption. **Not an implementation authorization.** |

## AR-002 — final semantic architecture

The Founder-approved room-rent architecture is authoritative by its
definition: *the reservation remains the operational source for
determining the stay and room-rate entitlement; the resulting room-rent
financial transaction belongs to the reservation's billing folio.* It is
named **Reservation operational ownership + folio financial ownership**.
The historical option labels M1/M2/M3 in ADR-003 are **retired**; the
letter "M3" in AR-002 is not equivalent to ADR-003's retired M3, and it is
not claimed that the Founder approved the retired M1. Level 2 remains; no
split billing is implied.

## AR-014 — closure

The four 2026-08-31 rulings (BASELINE-RECON-003; Master Plan Round 0
ruling; Phase 2a authorization; end-of-day checkpoint) are each closed as
**CLOSED — HISTORICAL EVIDENCE GAP**:

> Historical Founder ruling not recoverable from authoritative repository evidence. No reconstruction permitted.

The historical record is incomplete, but no unresolved present-day
architecture depends on reconstructing the missing wording: their
present-day substance is governed by FD-002 (plan adopted), FD-010/AR-001
(D11), FD-015/FD-016/AR-009 (Phase 2a frozen; read scope), and
FG-GOV-20260908-01 (repository designation). `FOUNDER-DIR-FINALGRID-REBRAND-001`
remains an observed evidence gap; its content is not invented. The gap
table above remains accurate as a record of absence.

**Governance principle recorded:** *Current authoritative Founder
decisions govern current architecture. Missing historical wording must not
be reconstructed merely to make the historical record appear complete.*
Historical provenance gaps are evidence-quality issues, not permission to
manufacture history.

## ADRs adopted

Under the Founder's target baseline, subject to evidence consistency
(verified in the readiness record):

| ADR | Status | What is adopted |
|---|---|---|
| ADR-001 | **ADOPTED** | System-of-record boundary (FD-003) |
| ADR-002 | **ADOPTED** | Level 2 folio attribution contract (FD-011, AR-001) |
| ADR-003 | **ADOPTED** | Reservation operational ownership + folio financial ownership (AR-002) |
| ADR-004 | **ADOPTED** | Business-date authority (FD-013, AR-008) |
| ADR-005 | **ADOPTED** | Architecture requirement: FK enforcement on every application connection (AR-003) — not enabled |
| ADR-007 | **ADOPTED** | Target recovery architecture (AR-006) — restore not implemented |
| ADR-008 | **ADOPTED** | Authentication → Role/Permission → Operation → Audit (AR-009); Phase 2a frozen; FD-015 recorded, not implemented |
| ADR-009 | PROPOSED FOR ADOPTION | awaits MP-D9 and route review |
| ADR-011 | PROPOSED FOR ADOPTION | awaits storage/system-actor mechanics |
| ADR-006, ADR-010, ADR-012 | PROPOSED | material choices open (see `verification/adr/BACKLOG.md`) |

**Architecture adopted; implementation remains separately authorized
work.** Adopted ADRs are append-only from this entry.

## Final governance statements

**D11 / INV-A02.** D5 = Level 2. `INV-A02` remains universal. The eight
historical D11 rows are preserved under FD-010 Option A as historical
commissioning/test activity; their existence creates no invariant
exemption; no historical folio attribution is authorized merely to satisfy
the invariant; future financial writers must create correctly attributed
transactions. The rows are unaltered.

**FD-015.** `list_folios` read-only access: Admin, Manager, Accountant,
Front Desk — allowed; other roles — not allowed. *This is a Founder-approved
authorization decision and is not yet implemented.* The endpoint is
unchanged.

## Boundary

No application code, template, migration, schema, database, financial
row, audit record, scheduler, authorization, report, backup/restore,
business-date, maker-checker or posting behaviour changed. No commit, no
push. Implementation authorization will be issued separately.

---

# Founder Resolution Round 2 — FG-P1-RECOVERY-FOUNDATION-20260908-01

| | |
|---|---|
| Recorded | 2026-09-08 |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` |
| Context | Answers the six questions in `verification/evidence/20260908_phase1_implementation_readiness/FOUNDER_DECISION_GATE.md`. Identifiers are the existing ones (Q-1…Q-6; CD-1); no new FD numbers are assigned by this entry. |
| Evidence for Q-6 | `verification/evidence/20260908_recovery_foundation/` |
| Kind | Founder decisions. **Q-6 authorizes recovery infrastructure only.** Nothing below authorizes Phase 1 financial implementation. |

## Q-1 / CD-1 — Missing folio at posting

> APPROVED: Create the required folio and audit it.
>
> If a financial operation has valid reservation context but the required billing folio does not yet exist: create/obtain the required folio through the authoritative lifecycle; ensure the resulting financial transaction is attributed to that folio; ensure the operation is auditable; fail closed if the required folio cannot be safely established.
>
> Do not silently create arbitrary or ambiguous folios.
>
> This decision does not authorize implementation of the financial writer changes.

## Q-2 — Correction of a NULL-folio original

> APPROVED: Refuse correction/attribution of the historical NULL-folio original.
>
> The eight D11 historical commissioning/test rows remain protected under FD-010 Option A. Do not: assign folios to them; alter them; reverse them; create corrective financial entries; rewrite invoices/GST records.
>
> A future correction operation must not silently mutate historical NULL-folio records merely to satisfy INV-A02.

## Q-3 — Phase 1 attribution scope

> APPROVED: Phase 1 focuses on financial folio attribution.
>
> Do not broaden Phase 1 into the general business-date correction program. Known wall-clock/business-date defects remain primarily a Phase 3 concern unless a Phase 1 writer cannot safely operate without a minimum business-date dependency explicitly identified in its implementation design.
>
> Do not use this decision to permit unrelated date refactoring.

## Q-4 — Golden Master

> APPROVED: Recapture the Golden Master baseline before Phase 1 financial implementation.
>
> The baseline must be captured before financial behavior is changed. It must distinguish, where applicable: existing expected behavior; existing known defects; D11 historical test data; Phase 1-intended behavioral changes.
>
> Do not alter the Golden Master during this Recovery Foundation implementation unless the recovery work itself legitimately requires it.

State at recording: approved, **not performed** under this directive; the golden master remains the 2026-08-03 capture.

## Q-5 — Strict audit coupling

> APPROVED: Strict audit coupling for Phase 1 financial writers that are touched by implementation.
>
> For affected financial operations: financial mutation and its required audit record must succeed or the operation must fail/roll back according to the transaction boundary.
>
> Include the identified POS ordering defect in the Phase 1 implementation requirement.
>
> Do not implement this during the Recovery Foundation slice. Record it as a binding Phase 1 implementation requirement.

**Recorded as a binding Phase 1 implementation requirement** (readiness report R-AUD-1/2/3; POS `app/pos.py:110-134` ordering defect included). **Not implemented** under this directive; `app/` unchanged.

## Q-6 — Recovery Foundation before Phase 1

> APPROVED: Authorize a bounded Recovery Foundation implementation before broader Phase 1 implementation.
>
> This is a prerequisite slice. It authorizes recovery infrastructure only. It does NOT authorize: folio attribution; payment changes; extra-charge changes; room-rent changes; night-audit changes; financial audit coupling changes; FK enforcement; NOT NULL migration; data migration; invoice changes; GST changes.

Executed under this directive: `tools/restore_db.py` and `tools/test_restore_db.py` created (19 tests pass); one isolated restore rehearsal `RR-20260908-01` — **PASS**, 16/16 checks, production `instance/pms.db` byte-identical before and after (`51dd83b7…30bc2`, 733,184 B); D11 rows untouched; `tools/backup_db.py` unchanged. Evidence: `verification/evidence/20260908_recovery_foundation/`. **Uncommitted, unpushed**, pending review.

## Consequence for the Phase 1 gate

`PHASE 1 NOT READY FOR EXECUTION AUTHORIZATION` (readiness report, 2026-09-08) had three conversion conditions: Q-1…Q-6 ruled (**done**); a Slice 1 directive with a rehearsal record (**done, pending review**); adoption of `PHASE1_EXECUTION_PLAN.md` as the Phase 1 implementation directive (**not yet done**). Per this directive's next-step rule, Phase 1 financial implementation does **not** begin until: Recovery Foundation is reviewed; PD-006 is verified; the golden-master requirement (Q-4) is reviewed; a separate Phase 1 execution authorization is issued.

---

# Phase 1 Formal Acceptance — FG-P1-ACCEPTANCE-20260910-01

| | |
|---|---|
| Recorded | 2026-09-10 |
| Governed HEAD | `aa6d9e91e7294be731383f755d6998acf5f059fc` — the published Phase 1 baseline (`e69f2ac2` → `d15d848e` → `34307c37` → `6cd2ac6d` → `95083995` → `aa6d9e91`, `origin/main` aligned) |
| Kind | Founder decisions: **formal acceptance of Phase 1** and the carry-forward dispositions below. Identifiers are those of the acceptance package (`P1-ACC`, `Q5-P1`, `GM-TAG`, `CF-nn`, `SR-n`, `DEF-n`); no new FD numbers are assigned by this entry. |
| Evidence | `verification/evidence/20260909_phase1_completion_review/` · `20260909_phase1_verification_completion/` · `20260909_phase1_acceptance_prep/` · `20260909_five_commit_execution/` · `20260910_phase1_acceptance/` |
| Not authorized by this entry | production deployment or activation · Phase 2 implementation · closure of any open carry-forward, pre-existing defect or semantic review item · any code, schema, data or ADR change |

## P1-ACC — Phase 1 formally accepted

> FORMALLY ACCEPT:
> Phase 1 implementation = COMPLETE
> Phase 1 verification = COMPLETE WITH DOCUMENTED LIMITATIONS
> Phase 1 acceptance = ACCEPTED
>
> Phase 1 is accepted as a completed implementation phase at published baseline aa6d9e91, with documented carry-forward items. Acceptance does NOT mean production deployment, production activation, closure of all future carry-forward items, closure of pre-existing defects, closure of semantic review items, or authorization for Phase 2 implementation.

State at recording: implementation units 1.1–1.5, 1.7, 1.8 delivered at `aa6d9e91` (unit 1.6 has no action under FD-010); verification: 22 of 24 financial writers runtime-exercised with no attribution failure, 33/33 constructor sites attributed statically, five registered datasets PASS, Q14 AGREED on datasets and diverging elsewhere by exactly the D11 ₹476.19, Phase 2a matrix 29/29, no Phase 1 attribution regression on any population; production `instance/pms.db` unchanged at `51dd83b7…30bc2` / 733,184 B; D11 rows unchanged. **Phase 1 is accepted, not deployed.**

## Q5-P1 — Audit coupling retained universally

> ALL FINANCIAL MUTATIONS SHOULD SATISFY STRICT AUDIT COUPLING. Do NOT weaken Q-5.

Q-5 (Round 2) stands unchanged as the architectural requirement for every financial mutation. Delivered at `aa6d9e91`: strict coupling proven at 12 of 24 writers (routes-level writers and POS). The 12 non-strict writers (W-08, W-09, W-10, W-22, W-23 caller-supplied; W-11, W-12 entity-level; W-13, W-14 dedicated log; W-16, W-21 run-level; W-24 none) become **CF-10 — Financial Mutation Audit-Coupling Normalization**, carried forward to the bounded pre-Phase-2b work. **Not implemented under this directive.**

## GM-TAG — Post-Phase-1 Golden Master adopted

> ADOPT `phase1_aa6d9e91` as the authoritative post-Phase-1 Golden Master baseline. Do NOT delete or replace the historical Golden Master; it remains provenance for the before/after comparison.

State at recording: `verification/masters/phase1_aa6d9e91/` — 158 surfaces, `gm-verify` 158/158 clean (packs `20260909_160149_gm_capture_phase1_aa6d9e91`, `20260909_160158_gm_verify_phase1_aa6d9e91`); historical `verification/masters/production/` untouched and still reporting the four declared E-6 differences (`20260909_160212_gm_verify_production`). The adopted master set and its packs are not within the commit scope authorized by §11 of this directive and remain untracked pending a separate commit authorization (see `20260910_phase1_acceptance/GOLDEN_MASTER_ADOPTION.md`).

## CF-11 — Pre-existing credit defects deferred

> Keep `settle_credit` and `redeem_credit_voucher` as pre-existing defects. They are NOT Phase 1 regressions. Do NOT fix them now. They require a separate bounded defect directive later.

State at recording: both pass `notes=` to `Payment(...)`, which has no such column (`TypeError`); present since baseline commit `b5b2514` (2026-08-07); untouched by Phase 1; surfaced by bounded runtime verification (W-07, W-11). No code prepared.

## SR-1 / SR-2 — Semantic reviews retained

> INV-B06 (advance-payment / business-date semantics) and INV-D02 (cancellation-refund semantics): SEMANTIC REVIEW REQUIRED — NO PHASE 1 REGRESSION ESTABLISHED. Do NOT modify INV-B06, INV-D02, payment behaviour, refund behaviour, business-date behaviour or cancellation behaviour until resolved. Assigned to the architecture/business-semantics review track.

## Carry-forward register — preserved

Open, exactly as established by the completion review and the verification completion: **CF-5** unauthorized-role verification · **CF-6** replay coverage of the new reconciliation control · **CF-9** deployment verification · **CF-10** strict audit-coupling normalization · **CF-11** pre-existing credit defects · **SR-1** INV-B06 · **SR-2** INV-D02. None is closed by this entry. **CF-7** (governance acceptance entry) is closed by this entry. CF-1, CF-2, CF-3, CF-4 and CF-8 were closed by the verification completion, each with retained evidence.

## Deployment

> Phase 1 is ACCEPTED but NOT RELEASED/DEPLOYED. Release timing remains a separate operational decision.

No deployment, rollout, production configuration change or production data mutation was performed or authorized.

## Consequence for the Phase 2 gate

Phase 2b entry conditions (Master Plan §05: Phase 1 complete; MP-D9 and MP-D5 settled; maker-checker operation-matrix ADR B-2) are now met as to "Phase 1 complete" only. MP-D9 remains OPEN and B-2 remains undefined. Phase 2 implementation scope is unchanged and **not authorized** by this entry.

---

# Founder Resolution Round 3 — Phase 2 Production Readiness — FG-P2-FOUNDER-RESOLUTION-20260910-01

| | |
|---|---|
| Recorded | 2026-09-10 |
| Governed HEAD | `a84566ae471786955283d107a9f2ad9e800bfcd4` (Phase 1 accepted at `aa6d9e91`; Golden Master `phase1_aa6d9e91` adopted) |
| Kind | Founder decisions FD-P2-01 … FD-P2-07, answering the seven open items of `verification/evidence/20260910_phase2_entry/` as analysed in `verification/evidence/20260910_phase2_founder_decisions/`. **Governance recording only.** No implementation, schema, database, invariant, scheduler, night-audit, role or deployment change is made or authorized by this entry; each decision names the *later* bounded directive it permits. |
| Identifiers | `FD-P2-nn` as issued by the directive; no new `FD-###` numbers are assigned by this entry |
| Evidence | `verification/evidence/20260910_phase2_founder_resolution/` |
| Production | `instance/pms.db` `51dd83b7…30bc2`, 733,184 B, D11 rows and `audit_logs` (23) unchanged — verified read-only before and after recording |

## FD-P2-01 — Initial staffing profile

> **Decision:** SINGLE-OPERATOR / ADMIN MODEL FOR FIRST PRODUCTION RELEASE.
>
> The first production release is governed around the existing Admin-capable operator model. This is an initial release boundary, not a permanent statement that FinalGrid is single-role software. Multi-role staffing and authorization remain subject to the later authorization/maker-checker work. The Admin assumption is valid only within this explicitly defined first-release boundary.

- **Rationale:** production holds one user (`admin`, Admin); the Phase 2a Admin/Manager interim default has been the working rule since 2026-08-31; broader route authorization is Phase 4 work (R6, ADR-009).
- **Governance effect:** resolves the **MP-D9 interim question for the first release only**. MP-D9 as a full operator-profile decision remains OPEN for Phase 4 and later (AR-015). The interim default of Phase 2a is confirmed, bounded to this release.
- **Implementation consequence:** permits Phase 2b scoping under the Admin model (with FD-P2-07); the day-one procedure must record that creating any FrontDesk, Accountant or Housekeeping account before Phase 4 unit 4.2 re-opens this boundary. Does not authorize any role, route or matrix change.
- **Implementation status:** none required; no role change made.

## FD-P2-02 — Audit retention

> **Decision:** STOP DESTRUCTIVE AUDIT-LOG PRUNING.
>
> Until an archival design is formally adopted: audit records must not be destructively deleted; existing audit history must be preserved; other non-audit log retention is not changed by this ruling. This ruling authorizes a later bounded retention-control implementation.

- **Rationale:** `_prune_old_logs` (`app/__init__.py:547-566`) deletes `audit_logs` rows older than 90 days daily at 04:00; first deletion ~2026-11-07; FD-008 and AR-007 already make this non-compliant; measured storage cost is negligible (~153 B per row).
- **Implementation consequence:** permits a **bounded retention-control directive** — remove `AuditLog` from the prune loop, leave `WebhookLog`/`NotificationLog` pruning unchanged, test on a copy — the ADR-012 "immediate" item. Archival/retention design (ADR-012 classes, periods, archive custody, detection invariant) remains a separate later decision.
- **Implementation status:** **not implemented**; the pruning job is unchanged at this recording; no audit row was read for modification.

## FD-P2-03 — D11 certification

> **Decision:** CERTIFY THE EIGHT D11 COMMISSIONING/TEST FINANCIAL ROWS AS A DECLARED HISTORICAL EXCEPTION.
>
> Preserve all eight rows exactly; do not delete, reverse or reattribute; do not alter invoices/GST history; do not exempt the universal invariant itself; certification must explicitly identify the eight-row D11 exception; any additional unexplained exception is a certification failure. This ruling does not authorize financial mutation.

- **Rows governed:** `payments` 1–6 (800 / 400 / 1,500 / 1,000 / 500 / 100) and `extra_charges` 1–2 (380.95 / 95.24), ₹4,776.19, `folio_id NULL`, reservations 1–4, invoices INV-2026-000029…000032. D11-F2 (classification) and FD-010 Option A (treatment) stand unchanged; AR-001 (INV-A02 universal) stands unchanged; Q-2 (correction refused) stands unchanged.
- **Rationale:** attribution, reversal, deletion and an in-invariant population declaration were each rejected as contradicting FD-010, Q-2 or AR-001; a declared-exception register at the certification layer keeps every ruling intact and keeps the control capable of failing.
- **Implementation consequence:** the production certification pack (gate G12) carries a declared-exception register naming the eight objects and asserts that the `inv-run` violation set equals it; the verdict is then recordable as PASS-WITH-DECLARED-EXCEPTION. Until a certification engine exists the comparison is performed and evidenced manually. Disposition of the rows themselves remains the separate future decision reserved by FD-010 (BACKLOG B-3, Phase 5).
- **Implementation status:** none required now; rows and invariants unchanged.

## FD-P2-04 — PD-006 verified state

> **Decision:** ADOPT THE TWELVE-CONDITION VERIFIED-STATE DEFINITION proposed in the Phase 2 Founder Decision Pack.
>
> The definition must distinguish "backup exists" from "backup has been successfully restored and verified", and must cover: backup identity; successful restoration; SQLite integrity; FK verification; schema identity; dataset/data checks; cryptographic identity where applicable; evidence manifest; timestamp; operator/accountability; encrypted-backup key custody; reproducible verification evidence.

- **Definition adopted** (`20260910_phase2_founder_decisions/FOUNDER_DECISION_PACK.md`, FD-P2-04): (1) artifact and plaintext hash equal the values recorded at backup time and in the manifest; (2) restore completes into a fresh isolated path, never `instance/`; (3) `PRAGMA integrity_check` ok on source and restored; (4) `foreign_key_check` = 0 (or equal to source); (5) `sqlite_master` identical to source and equal to the release tag's fingerprint; (6) per-table row counts and content digests equal, body bytes identical beyond the 100-byte header, financial tables named; (7) whole-file hash recorded, informational; (8) `inv-run` on a copy of the restored file identical object-for-object to the pre-backup pack (declared-exception aware) and `gm-verify` 0 differences at the same frozen business date; (9) machine-readable manifest with run id, paths, hashes, UTC timestamps, app version, business date, all checks, retained and committed; (10) operator, machine and directive recorded; (11) encrypted artifacts restored on a different machine using only custody-held key material under a documented custody procedure, key never written into evidence; (12) the artifact exempt from purge or retained in the recovery store. Minimum for a production mutation (PD-005 step 3): conditions 1–7, 9, 10. Minimum for Wave 0 D9 / gate G8: all twelve on an application-made encrypted backup.
- **Governance effect:** confirms and extends the ADR-006 proposal (integrity + manifest + `inv-run` equivalence, not whole-file hash); **closes BACKLOG B-5**. ADR-006 and ADR-007 reconciliation is recorded here and applied to those files at their next adoption review; they are not edited by this entry.
- **Implementation consequence:** permits the **recovery-hardening directive** (operating backup path via backup API with manifest/hash, off-box encrypted restore rehearsal, key-custody procedure). Does not authorize any production mutation or a scheduled restore service.
- **Implementation status:** not implemented; `tools/restore_db.py` (Recovery Foundation) already satisfies conditions 2–7 and 9 for tool-made artifacts (RR-20260908-01).

## FD-P2-05 — Night audit

> **Decision:** MANUAL / CONTROLLED OPERATOR EXECUTION FOR FIRST PRODUCTION RELEASE.
>
> An authorized operator initiates the close; business date is explicitly controlled; execution must be observable; financial mutations must be auditable; recovery must be available; unattended scheduler execution is NOT the first-release operating model. Automation may be considered later after unattended financial-action controls are implemented and verified.

- **Rationale:** FD-009 forbids unattended financially material mutation without operator-equivalent controls and no AR-013 / B-1 scheduler ADR exists; a 02:00 unattended run leaves blockers silent; the manual route (`Admin`, `Manager`, `Accountant`) records `run_by_user_id`; production already has `night_audit_enabled=false`.
- **Implementation consequence:** the first-release configuration keeps `night_audit_enabled=false`; a written daily-close procedure is required (deployment rehearsal G11); Phase 3 units 3.5 (interrupted-close recovery) and 3.6 (staleness escalation) are the controls that make manual mode safe and are scoped accordingly. Scheduler automation requires the B-1 ADR and its verification first.
- **Implementation status:** no night-audit or scheduler code changed; setting unchanged.

## FD-P2-06 — INV-B06 / INV-D02

> **Decision:** REFINE THE INVARIANTS TO REPRESENT LEGITIMATE BUSINESS SEMANTICS.
>
> INV-B06 must not treat a legitimate business-dated advance payment as an automatic integrity failure. INV-D02 must not treat a legitimate cancellation refund as an automatic integrity failure. The underlying payment/refund/business-date financial behaviour is NOT changed by this ruling. The refinement must preserve detection of genuinely incorrect activity. This becomes a later bounded constitutional/invariant amendment and requires verification evidence.

- **Findings ruled on:** INV-B06 (`rules_b.py:607-700`) bounds `payment_date` to `[arrival, departure+30d]` with no leading window, so a deposit (`payment_purpose='advance'`) dated on the booking business date before arrival is reported; INV-D02 (`rules_d.py:97-195`) requires `corrects_id` on every `is_reversal` row, so a cancellation refund (`is_reversal=True`, `corrects_id NULL`, linked instead through `reservations.cancellation_refund_payment_id`) is reported. Neither has a GST or revenue consequence.
- **Governance effect:** a **constitutional amendment** under Master Plan §07 Layer 1 is authorized in principle for these two rules only; the amendment's exact text, negative seeds and commissioning are the content of the later directive. SR-1 and SR-2 move from "semantic review required" to "ruled — implementation and verification pending".
- **Implementation consequence:** permits a **Phase 6 invariant-refinement directive** confined to `verification/invariants/` and dataset declarations (`DS-ACT-VOIDCN` expectation), with `inv-commission` proof that the refined rules still fail on genuinely wrong dates and on untraceable reversals. Does not authorize any change under `app/`.
- **Implementation status:** invariants unchanged at this recording.

## FD-P2-07 — Maker-checker

> **Decision:** INITIAL CONTROL THRESHOLD = ₹10,000.
>
> No user may approve their own maker-checker action; transactions/operations meeting the applicable threshold require a second authorized person; operation-specific controls may require maker-checker regardless of amount; emergency/admin operations require explicit auditability. At minimum the operation matrix must separately consider: voids; closed-day corrections; reopening a closed business day; large transfers; large forfeits/credits; other financially material corrections. The ₹10,000 threshold is the initial release policy and may be refined later through a governed Founder decision.

- **Rationale:** AR-010 adopts maker-checker as a control principle and requires the operation matrix in a dedicated ADR before implementation (BACKLOG B-2); the void/refund control (N2) and shift-close approval already exist as reference implementations.
- **Governance effect:** the threshold and the no-self-approval rule are Founder policy for the first release; the four-tier structure proposed in the decision pack (maker-checker required / role authorization only / informational / emergency override with mandatory reason and audit) is the basis for ADR-010's adoption content. Read with FD-P2-01: under the single-operator model a maker-checker operation above threshold **cannot be completed by the sole Admin alone** — the second authorized person is required; where none exists the operation waits or proceeds only through the explicitly audited emergency/admin control defined by the matrix.
- **Implementation consequence:** permits adoption of ADR-010 with the matrix (B-2) and, with CF-10 delivered, Phase 2b entry. Does not implement maker-checker; existing void/refund and shift-close controls are unchanged.
- **Implementation status:** not implemented.

## Carry-forward register — preserved open

CF-5 unauthorized-role verification · CF-6 replay coverage of the reconciliation control · CF-9 deployment verification · **CF-10** audit-coupling normalization at the 12 non-strict writers · **CF-11** credit-path defects (`settle_credit`, `redeem_credit_voucher`) · SR-1 / SR-2 implementation and verification (now ruled, FD-P2-06) · schema / FK / `NOT NULL` work (Phase 4/5; B-3, B-4, B-9) · migration mechanism (B-4) · recovery implementation (FD-P2-04) · night-audit implementation and hardening (Phase 3; FD-P2-05) · deployment rehearsal (G11) · final certification (G12). None is closed by this entry. Closed by this entry: **BACKLOG B-5** ("verified state" definition) and the **MP-D9 interim question for the first release**.

## Consequence for the Phase 2 gate

Phase 2b entry now requires: CF-10 delivered and verified; ADR-010 adopted with the operation matrix under FD-P2-07; scope declared schema-free or a PD-004 authorization. Phase 3 entry conditions are met (Phase 1 complete) and Phase 3 is scoped under FD-P2-05. **No phase implementation is authorized by this entry.**

# Founder Resolution Round 4 — Q06 GST Taxable-Base Defect — FG-P2-FOUNDER-RESOLUTION-20260923-01

| | |
|---|---|
| Recorded | 2026-09-23 |
| Governed HEAD | `b0d30542ff6b3cdbbc269fd8c17679c80ed9f718` (audit-retention fix; FD-P2-02 implemented) |
| Kind | Founder decisions Q06-H1 … Q06-H3, ruling on the Q06 GST taxable-base defect established by forensic analysis and downstream-impact tracing. **Governance recording only.** No code, schema, database, invariant or evidence-pack change is made or authorized by this entry; the forward code correction (Q06-H2) names a *later* bounded implementation directive it permits. |
| Identifiers | `Q06-Hn` as issued by the directive; no new `FD-###` numbers are assigned by this entry |
| Evidence | `verification/evidence/20260923_q06_analysis/`, `verification/evidence/20260923_q06_downstream/`, `verification/evidence/20260923_q06_founder_resolution/` |
| Production | `instance/pms.db` `51dd83b7…30bc2`, 733,184 B — verified read-only before and after recording |

## Q06-H1 — Historical record preservation

> **Decision:** PRESERVE THE EXISTING SEALED HISTORICAL RECORD EXACTLY AS RECORDED.
>
> The sealed `NightAuditLog` record for `audit_date = 2026-08-09` shall not be deleted, rewritten, recalculated in place, mutated, re-sealed with a corrected value, or silently replaced. It is designated a historical record containing the now-confirmed Q06 taxable-base defect. The historical value remains evidence of what the system recorded at that time.

- **Rationale:** the forensic and downstream-impact analyses established that `NightAuditService.tax_snapshot()` double-counts taxable base for intrastate charges (CGST/SGST `TaxLine` rows each carry the full base; no charge-level dedup, unlike `get_gst_report()`), and that this specific sealed record (`snapshot_json`, hash-sealed, `snapshot_valid=1`) already carries the buggy `total_taxable = 2285.7`. `routes.py:4786-4808` serves closed audit-date records frozen, not recomputed — consistent with how other pre-existing defects (e.g. CF-11) have been handled: disclosed and preserved, not silently altered.
- **Governance effect:** no retroactive production data correction is authorized by this ruling. If a future requirement arises to present a corrected historical figure, it must be represented as a separate correction/superseding record with explicit provenance, never by overwriting the original sealed snapshot. No such mechanism is authorized or required at this time.
- **Implementation status:** none required; no record read for modification; no production write performed.

## Q06-H2 — Forward correction (authorization to implement later)

> **Decision:** CORRECT `NightAuditService.tax_snapshot()` FOR FUTURE CALCULATIONS using the established charge-level deduplication semantics already implemented by `get_gst_report()`.
>
> This is a forward-looking correction only. It does not authorize alteration of historical production records (Q06-H1 stands). `get_gst_report()` itself requires no change; the actual GST/e-invoice filing path (`app/gst_einvoice.py`) already sources exclusively from it and is unaffected by this defect.

- **Rationale:** downstream-impact tracing found no compensation anywhere in `app/` or `verification/` for the inflated value, no ripple into other calculations (`self._tax_lines` is otherwise read only by `revenue_summary()`, which uses `tax_amount`, unaffected), and the fix is mechanically isolated to `total_taxable`/`by_rate` inside `tax_snapshot()`.
- **Governance effect:** permits a **later bounded implementation directive** confined to `app/night_audit_service.py :: NightAuditService.tax_snapshot()`, applying the same dedup key `get_gst_report()` uses, with regression evidence (Golden Master, replay, `inv-run`, and the existing `q06()` invariant check in `verification/quantities.py:496-532`) confirming the divergence closes and nothing else moves.
- **Implementation status:** **not implemented**; `tax_snapshot()` is unchanged at this recording.

## Q06-H3 — Historical correction model

> **Decision:** NO RETROACTIVE PRODUCTION DATA CORRECTION IS AUTHORIZED BY THIS RULING.
>
> If a future requirement arises to present a corrected historical figure for the affected date(s), it must be represented as a separate correction/superseding record with explicit provenance rather than overwriting the original sealed snapshot. No such correction mechanism is authorized or required at this time.

- **Governance effect:** establishes the model (supersede, never overwrite) for any future historical-correction need arising from this or a similar defect, without building or requiring that mechanism now.
- **Implementation status:** not applicable; no mechanism built.

## Carry-forward register — preserved open

CF-5 unauthorized-role verification · CF-6 replay coverage of the reconciliation control · CF-9 deployment verification · CF-10 audit-coupling normalization at the 12 non-strict writers · CF-11 credit-path defects · SR-1 / SR-2 implementation and verification · schema / FK / `NOT NULL` work · migration mechanism (B-4) · recovery implementation · night-audit implementation and hardening · deployment rehearsal (G11) · final certification (G12) · maker-checker (policy-only, FD-P2-07) · remaining authorization work (Phase 4). **New this round: Q06 code correction (Q06-H2) — OPEN, pending a separate implementation directive.** None of the above is closed by this entry. **Closed/settled by this entry:** the governance treatment of the Q06 historical record is now decided (Q06-H1/H3 — preserve, never overwrite; no correction mechanism authorized) — this is a disposition ruling, not an implementation.

## Consequence for the Phase 2 gate

Gate G3 (financial integrity) and G5 (auditability) remain not-PASS pending CF-10 and the Q06-H2 implementation; this entry does not move either gate. **No implementation, schema, database, or production-record change is authorized by this entry.**

# Founder Resolution Round 5 — ADR-011 System Actor Representation — FG-P2-FOUNDER-RESOLUTION-20260930-01

| | |
|---|---|
| Recorded | 2026-09-30 |
| Governed HEAD | `cfec0c8c45171dded80bc687a65a567d5e120d2c` (ADR-011 decision package `verification/evidence/20260930_adr011_system_action_provenance/`, outcome DECISION_REQUIRED) |
| Kind | Founder architecture decision answering item 1 of `ADR011_DECISION_REQUIRED.md` §5 (system-actor representation). **Governance recording only.** No code, schema, database, setting, FK mode or scheduler change is made by this entry. |
| Identifier | `ADR011-SA` |
| Source | Ruling given in session by the Founder on 2026-09-30, in reply to the decision package; recorded verbatim below |
| Production | `instance/pms.db` `51dd83b7…30bc2`, 733,184 B — unchanged by this recording |

## ADR011-SA — System actor representation

> **Decision:**
>
> FinalGrid shall distinguish a human actor from a system actor at the audit/provenance layer. System actions shall not impersonate a human user and shall not use a fabricated users.id = 0.
>
> audit_logs shall explicitly represent the actor kind and retain sufficient provenance to distinguish:
>
> human/operator initiated action;
> system/scheduled action;
> execution mechanism;
> relevant operator role/shift where applicable.
>
> Human audit records shall continue referencing the authenticated user.
>
> System audit records shall not require a fabricated human users row merely to satisfy the audit FK.
>
> Scheduler activation remains a separate authorization and is not enabled by this decision.

- **Option selected** (in the terms of the decision package §4): the explicit actor-kind representation in `audit_logs` (Option B). Option A (seeded system `users` row, including a seeded id 0) is excluded ("shall not impersonate a human user", "shall not use a fabricated users.id = 0", "shall not require a fabricated human users row"). Option C's delegated human identity for system actions is excluded ("System actions shall not impersonate a human user").
- **Governance effect:** resolves ADR-011 item 4 ("system-actor representation — UNRESOLVED") and the actor-kind part of the ADR-011 storage question: actor kind, execution mechanism and, where applicable, operator role/shift are carried by `audit_logs`. A system audit row need not reference `users` (its `staff_user_id` may therefore be empty); human rows keep referencing the authenticated user. The `0` system convention (`services.resolve_audit_actor`, `webhook._write_audit`, `routes._write_audit`, `services_group_stay._resolve_actor`) is non-compliant with this decision. ADR-011 is not edited by this entry; the reconciliation is applied to it at its adoption review (precedent: FD-P2-04 for ADR-006/ADR-007).
- **Scheduler:** unchanged. FD-P2-05 stands; `night_audit_enabled` stays `false`; activation needs the AR-013 / B-1 controls and a separate authorization.
- **Not addressed by this ruling (recorded, not decided):** the delivery of the `audit_logs` schema change — which migration artefact carries it and whether it may run through the existing unattended boot-time registry (`app/__init__.py::_run_pending_migrations`, invoked at every application start; BACKLOG B-4 lists "end of unattended boot-time execution" as undecided) — and the application of that change to the production database (PD-005 / PD-006 verified-state backup). Because `instance/pms.db` lives in the application working tree, a boot-time migration committed to `main` would be applied to production at the next application start.
- **Implementation status:** not implemented.

# Founder Resolution Round 6 — SR-2 / INV-D02 refund and credit-note lineage — FG-P2-FOUNDER-RESOLUTION-20260930-02

| | |
|---|---|
| Recorded | 2026-09-30 |
| Governed HEAD | `c703150a06fd29547e575536d63f9ee2a3af4f7a` |
| Kind | Founder rule text for the FD-P2-06 INV-D02 amendment (SR-2), and two scope answers given in session. Recorded verbatim; implemented under the "FD-P2-06 / INV-D02 (SR-2) implementation directive" of the same date |
| Identifier | `SR2-RULE` |
| Context | The first rule text of the directive excluded reservation-level links. The only application refund writer (`post_cancellation_disposition`) records no transaction-level link, so legitimate refunds would have kept failing, contrary to FD-P2-06. Implementation stopped (`INV_D02_STOP_REPORT.md`, outside the repository), and the Founder issued the text below |

## SR2-RULE — INV-D02: refund / credit-note lineage

> A refund or credit-note transaction is compliant when it has an explicit, traceable relationship to the financial transaction or business transaction that it reverses.
>
> For an ordinary payment/charge correction, the reversal must identify its originating financial transaction.
>
> For a cancellation refund, the cancellation disposition is the originating reversal transaction. A refund created as the direct financial consequence of that cancellation is therefore considered explicitly linked through the cancellation/reservation transaction, provided that the cancellation itself is a valid, identifiable transaction and the refund is the refund generated by that cancellation.
>
> A reservation, guest, folio, or amount match by itself is not sufficient evidence of lineage.
>
> This rule does not require changing the existing cancellation-refund data model and does not require payment-level allocation of the refund.

## Scope answers (in session, 2026-09-30)

- **Population:** INV-D02 keeps its current population — the `is_correction` / `is_reversal` rows of `payments` and `extra_charges`. A credit note's refund is checked through its refund payment row. `credit_notes` rows remain INV-D05's population; no other invariant changes.
- **DS-ACT-VOIDCN:** classified through a dataset-level reachability field (`reachable` by default; `synthetic-unreachable` for VOIDCN, with its reason), shown in `ds-run` output. VOIDCN keeps INV-D02 = VIOLATED; nothing is re-baselined.

## Effect

Resolves the FD-P2-06 statement "INV-D02 must not treat a legitimate cancellation refund as an automatic integrity failure" through the cancellation/reservation link, without changing application behaviour, the data model or the refund amount allocation. SR-1 (INV-B06), K-7 and all other open items are unaffected.

# Founder Resolution Round 7 — SR-2 / INV-D02 Revision 2 — FG-P2-FOUNDER-RESOLUTION-20261001-01

| | |
|---|---|
| Recorded | 2026-10-01 |
| Governed HEAD | `c703150a06fd29547e575536d63f9ee2a3af4f7a` (`main`); implementation on local branch `sr2-inv-d02`, not pushed, not merged |
| Kind | Founder confirmation of the revised SR-2 / INV-D02 interpretation (Revision 2), with governance wording. Refines the operationalisation of `SR2-RULE` (Round 6); `SR2-RULE` itself is unchanged |
| Identifier | `SR2-REV2` |
| Context | The first implementation required the refund's reservation to be `Cancelled` today and treated amount equality as part of lineage. The Founder asked for a rule independent of current status, with audit as supporting evidence only. Revision 2 was implemented and verified (`verification/evidence/20260930_sr2_inv_d02/REVISION_2_REPORT.md`) and is confirmed below |

## SR2-REV2 — Founder interpretation

1. A legitimate cancellation refund is **not** required to have the reservation's current status equal to `Cancelled`.
2. Cancellation lineage is established from the existing cancellation-processing snapshot: exactly one reservation names the refund; it is the refund's own reservation; the disposition is `refund_full` or `refund_partial`; and `cancellation_processed_at` is present.
3. `cancellation_processed_at` is **not** described as proof of historical reservation status. It is the application's durable evidence that the cancellation-processing event occurred and generated the refund.
4. Audit rows are supporting provenance evidence only. INV-D02 does not depend on the existence of an audit row.
5. Refund amount equality (`cancellation_amount_refunded` against the refund amount) remains a separate **consistency** check. A consistency failure is not represented as a lineage failure.
6. A later reservation-status change, refund void, or correction does not retroactively invalidate the historical cancellation lineage.
7. No ordering check between the refund's `created_at` and `cancellation_processed_at` is added. That absence is outside this ruling.
8. The direct-database-forgery limitation is acknowledged as a limitation of the current architecture. No schema or application change is made to address it under this directive.
9. Refunds predating the cancellation snapshot fields are outside the current supported verification population.

## Recorded limitations (not decisions)

- The application keeps no reservation status history; the rule does not claim to establish historical status.
- The snapshot is write-once by application code, not by the database; a direct database write could forge it and the rule would accept it (item 8).
- No `created_at` / `cancellation_processed_at` ordering check (item 7).
- Refunds predating the snapshot fields are not supported (item 9). Production holds no correction or refund rows, so INV-D02 is VACUOUS there; other installations were not examined.

## Effect

`SR2-RULE` stands. Revision 2 fixes how it is operationalised in `verification/invariants/rules_d.py` (INV-D02) only. No change to `app/`, the schema, production, K-7, SR-1 or any other rule. Push and merge remain separately unauthorised; the local branch is the only authorised delivery location.

# Founder Resolution Round 8 — DQ-56 / Q06-H1 sealed record protection (R1) — FG-P2-FOUNDER-RESOLUTION-20261002-01

| | |
|---|---|
| Recorded | 2026-10-02 |
| Governed HEAD | `c9eeff0` (`origin/main`); decision package `verification/evidence/20261002_dq56_sealed_record/DQ56_SEALED_RECORD_DECISION_PACKAGE.md` (branch `overnight-20261002`, commit `5accb2f`) |
| Kind | Founder implementation directive for remediation option R1 of the DQ-56 package. Recorded verbatim. Implementation on a local branch only |
| Identifier | `DQ56-R1` |
| Source | Ruling given in session by the Founder on 2026-10-02, in reply to the DQ-56 decision package |

## DQ56-R1 — Directive, verbatim

> Proceed with DQ-56 R1 exactly as decided: protect only business date 2026-08-09. Block Run and Reopen for that date and hide/disable those UI actions. Do not modify the database, schema, general closed-day Run semantics, business-date logic, SR-1, K-7, or any other production behavior. Work only on a disposable/copy environment. Run the supplied DQ-56 tests and relevant regression tests. Produce a complete evidence report. Do not push, merge, start production, or modify production until I separately authorize the production application. Stop at the production decision boundary.

## Effect

- Resolves DQ-56b (option **R1**) and DQ-56c (protected set = **{2026-08-09} only**). DQ-56d (Run on other closed days) is **not** adopted: general closed-day Run semantics stay unchanged.
- Q06-H1 (`:1219-1227`) stands; this directive adds an application-level guard for that one record.
- Not authorized: push, merge, production start, production application, any database/schema change, or any change to business-date logic, SR-1 or K-7.

# Founder Resolution Round 9 — DQ-56e production application of DQ56-R1 — FG-P2-FOUNDER-RESOLUTION-20261002-02

| | |
|---|---|
| Recorded | 2026-10-02 |
| Governed HEAD | `e310c66` (branch `dq56-q06h1-guard`; code `46c4aab` tested in `verification/evidence/20261002_dq56_r1_guard/`) |
| Kind | Founder production authorization for DQ56-R1, recorded verbatim. Production application **excludes** application start |
| Identifier | `DQ56e` |
| Source | Ruling given in session by the Founder on 2026-10-02, in reply to the DQ56-R1 implementation report |

## DQ56e — Authorization, verbatim

> AUTHORIZE DQ-56e: Apply R1 to production.
> Proceed systematically:
> 1. Take and verify a fresh production backup and perform the required isolated restore rehearsal.
> 2. Verify Git/branch/working-tree/process/port/production-hash preconditions.
> 3. Push the R1 branch and fast-forward main exactly as authorized.
> 4. Do NOT start the production application yet.
> 5. Produce a pre-start production gate report and STOP.
> R1 scope remains strictly limited to protecting business date 2026-08-09: block Run and Reopen and hide/disable those controls. Do not modify Complete, other dates, business-date logic, SR-1, K-7, schema, database data, or general closed-day Run behavior.
> Do not perform any other queued work. Do not start the live application until I separately authorize the production-start step.

## Effect

- Authorizes: fresh backup and isolated restore rehearsal; push of `dq56-q06h1-guard`; fast-forward of `origin/main` and of the live checkout's `main` to the R1 head.
- Not authorized: starting the live application (a separate production-start authorization is required); any other queued work; any database, schema or behaviour change beyond DQ56-R1.
- Execution evidence: `verification/evidence/20261002_dq56_r1_production_application/`.

# Founder Resolution Round 10 — SR-1 / INV-B06 rule text — FG-P2-FOUNDER-RESOLUTION-20261002-03

| | |
|---|---|
| Recorded | 2026-10-02 |
| Governed HEAD | `28e6b63` (branch `dq56-q06h1-guard`; `app/` and `verification/` code identical to `origin/main` `e310c66`); implementation on local branch `sr1-inv-b06` |
| Kind | Founder rule text for the FD-P2-06 INV-B06 amendment (SR-1), answering DQ-01…DQ-05, plus two interpretation answers given in session. Recorded verbatim |
| Identifier | `SR1-RULE` (directive) and `SR1-INT` (interpretation answers) |
| Context | FD-P2-06 adopted the principle and reserved "the amendment's exact text, negative seeds and commissioning" to a later directive. Decision package: `verification/evidence/20261002_overnight_sr1/SR1_DECISION_REQUIRED.md` (branch `overnight-20261002`) |

## SR1-RULE — Founder Directive — SR-1 / INV-B06, verbatim

> Founder Directive — SR-1 / INV-B06
> Proceed with SR-1 using the following founder decisions:
> 1. DQ-01: Pre-arrival advances are permitted up to 30 calendar days before the reservation arrival date. Advances earlier than 30 days are violations.
> 2. DQ-02: Refunds inherit the temporal validity of their originating transaction. Corrections inherit the temporal validity of the transaction they correct. Do not introduce cancellation-date/business-date refund logic in SR-1; that belongs to the K-7 dependency.
> 3. DQ-03: Add negative coverage for advances beyond 30 days, non-exempt pre-arrival payments, stale-business-date deposits, invalid post-departure transactions, and refund/correction lineage whose originating transaction is outside the permitted window.
> 4. DQ-04: Implement SR-1 before K-7 using basis-independent rules. Do not modify K-7, business-date logic, application financial writers, or production.
> 5. DQ-05: Record FD-P2-06 as the explicit Phase 6 carve-out authorizing refinement of INV-B06 despite the general "invariants not touched" statement.
> 6. The production business date being 53 days stale is not an exemption from INV-B06 and must remain a separate K-7/production issue.
> 7. No production changes, no merge to main, and no deployment are authorized by this directive.
> 8. First record these decisions verbatim in FOUNDER_DECISIONS.md as the next SR-1 decision round.
> 9. Then implement only INV-B06 verification/invariant changes on an isolated branch.
> 10. Run the targeted 13 scenarios and the appropriate regression suite against a disposable production copy.
> 11. Do not re-baseline unrelated failures. Report baseline-versus-implementation differences explicitly.
> 12. Stop after the evidence package is complete and wait for separate authorization to merge/push

## SR1-INT — Interpretation answers (in session, 2026-10-02), verbatim

Asked before implementation because DQ-02 admits two readings with different results.

> **Q1.** DQ-02 says refunds and corrections "inherit the temporal validity" of their originating transaction. Which reading: inherit the *verdict* (a refund or correction is valid exactly when its originating transaction is valid; its own date is not checked) or inherit the *window* (it must itself be dated inside its originating transaction's permitted window)?
>
> **Founder answer:** "Inherit the verdict"

> **Q2.** A cancellation refund has no link to a single payment row; the application computes it from all non-voided `'advance'` payments on the reservation (`app/services.py` `advance_summary`). SR2-RULE names the cancellation disposition as its origin for lineage purposes, but that has no date SR-1 may use. Does the refund inherit from its reservation's advances, or from the cancellation disposition (no INV-B06 date check)?
>
> **Founder answer:** "Its reservation's advances" — the refund's originating transactions are the non-voided advance payments it was drawn from; under the verdict reading the refund fails if any of those advances is outside its window.

## DQ-05 — Phase 6 carve-out (as directed in item 5)

FD-P2-06 (this file, `:1178-1187`) is recorded as the explicit carve-out from Master Plan Phase 6 "Not touched: invariant semantics" that authorizes the refinement of INV-B06. Phase 6 stands for every other invariant.

## Effect

- DQ-01…DQ-05 (overnight queue) are RULED by this round.
- Authorizes: on an isolated branch, changes to INV-B06 in `verification/invariants/rules_b.py` (rule, metadata, negative seed); the 13 targeted scenarios and the regression battery on disposable copies of production.
- Not authorized: any change to `app/`, the schema, K-7, business-date logic, financial writers, production, other invariants, baselines of unrelated failures; push, merge or deployment.

# Founder Resolution Round 11 — GT-D1 / K7-D1…D10 — Phase 3.1 K-7 directive — FG-P2-FOUNDER-RESOLUTION-20261002-04

| | |
|---|---|
| Recorded | 2026-10-02 |
| Governed HEAD | `0938069` (`main` = `origin/main`; SR-1 integrated); recorded on local branch `round11-k7-directive` |
| Kind | Founder rulings GT-D1, K7-D1/GT-D5, K7-D2, K7-D3, K7-D7; instructions on K7-D4 and K7-D10; instruction to refresh the stale G3 governance documentation. Recorded verbatim |
| Identifier | `R11-GT-D1`, `R11-K7-D1`, `R11-K7-D2`, `R11-K7-D3`, `R11-K7-D4`, `R11-K7-D7`, `R11-K7-D10` |
| Source | Founder message of 2026-10-02 in session, in reply to the K-7 / G3 decision package |
| Decision inputs | `verification/evidence/20261002_overnight_k7_analysis/` and `20261002_overnight_gates_g3_g6/` (branch `overnight-20261002`) |
| Deliverables | `verification/evidence/20261002_round11_k7_directive/`: `K7_PHASE_3_1_DIRECTIVE.md` (draft, not in force), `K7_D4_VOUCHER_BASIS_DECISION.md`, `K7_D10_CLOSE_PATH_DECISION_PACKAGE.md`, `G3_GOVERNANCE_STATUS_REFRESH.md` |

## Round 11 — Founder directive, verbatim

> Proceed with Round 11 governance only.
> Record the following Founder rulings in FOUNDER_DECISIONS.md and produce the Phase 3.1 K-7 directive. Do not implement, push, merge, start the application, modify production data, or advance the business date.
> GT-D1: G3's K-7 item closes when Phase 3.1 is completely implemented and evidenced.
> K7-D1 / GT-D5: Authorize a dedicated Phase 3.1 directive for K-7. B-1 and the undefined Gates A–H are explicitly outside this directive's scope; validate the directive against G3, G6 and G10.
> K7-D2 — Scope: Include:
> - W-08, W-09, W-10, W-11, W-17, W-20, W-22, W-23;
> - voucher issued_date and expiry anchor;
> - relevant model defaults;
> - business-date fallback paths.
> Keep late checkout, report ranges, void/shift-day mapping and invoice/credit-note UTC dating outside K-7 unless a concrete dependency is demonstrated. The package identifies these as the remaining B-10 scope.
> K7-D3 — Fallback/default behaviour: fail closed with a logged error where the business date cannot be resolved; defaults must resolve the business date at insertion or raise rather than silently using the wall clock.
> K7-D4 — Voucher expiry basis: before implementation, present the exact alternatives and consequences for Founder confirmation. Do not silently choose a liability/expiry basis. Production currently has zero vouchers, so this does not block the present data state.
> K7-D7 — Evidence: use a dedicated RED/GREEN harness with the system clock deliberately different from the production business date, disposable production copies, full regression battery, and a declared-delta list. Do not create a new invariant merely for K-7.
> K7-D10: prepare the two close-path alternatives as a separate decision package. Do not perform either path in production.
> Also update the governance package to identify the already-completed SR-1 integration and DQ-56/R1 status, because the existing G3 documentation is stale.
> STOP after producing the Round 11 decision/directive package. Do not begin K-7 implementation until the Founder has reviewed the resulting package.

Note on the text: the Founder's message carried two interface paste-markers (`Pasted markdown(20261002-115512)`), one after the K7-D2 paragraph and one after the final governance paragraph. They are omitted above and are not part of the ruling. Nothing else was changed.

## Effect

- **RULED:** GT-D1 (overnight queue DQ-13); K7-D1 / GT-D5 for this directive (DQ-57; DQ-14 in part); K7-D2 (DQ-58); K7-D3 (DQ-59); K7-D7 (DQ-60, evidence standard and no new invariant).
- **Instructions executed as preparation only:** K7-D4 (alternatives presented, **not chosen**; awaiting Founder confirmation), K7-D10 (close-path decision package prepared, **no decision**; neither path was run anywhere), refresh of the stale G3 governance documentation.
- **Not ruled by this round:** the K7-D4 voucher basis; K7-D10; K7-D5 and K7-D6 beyond "outside K-7"; K7-D8 / DQ-61 (deployment sequencing); GT-D7 / BD-D1…BD-D5 (the 53-day stale business date); B-10 #4 and #5; any other open DQ or GT item.
- **Not authorized:** K-7 implementation (it begins only after the Founder has reviewed the package and records an activation entry naming `FG-P3-1-K7-DIRECTIVE-01`); push; merge; deployment; an application start; any production data change; advancing the business date.
- **Status of record (facts, not decisions):** SR-1 / INV-B06 is integrated; `main` = `origin/main` = `0938069`. DQ-56 / DQ56-R1 is applied to the live checkout (`app/` guard for 2026-08-09; production application stopped). Detail and the list of governance-record gaps for the Founder to dictate are in `G3_GOVERNANCE_STATUS_REFRESH.md`.

# Founder Resolution Round 12 — K-7 activation rulings — FG-P2-FOUNDER-RESOLUTION-20261002-05

| | |
|---|---|
| Recorded | 2026-10-02 |
| Governed HEAD | `0938069` (`main` = `origin/main`). Recorded on the local branch `k7-phase-3-1`, which carries Round 11 (`545eae1`) and the review pack (`beb8e15`) on top of `0938069`; `app/` and the verification code are identical to `0938069` |
| Kind | Founder rulings F-1 to F-6, K7-D4, BD-D1; K7-D10 left undecided; instruction on governance entries G-1 to G-7; corrections C-1 to C-3; activation of `FG-P3-1-K7-DIRECTIVE-01`. Recorded verbatim |
| Identifier | `R12-F1`, `R12-F2`, `R12-F3`, `R12-F4`, `R12-F5`, `R12-F6`, `R12-K7-D4`, `R12-BD-D1`, `R12-ACTIVATION` |
| Source | Founder message of 2026-10-02 in session, in reply to the K-7 Founder Decision Review Pack (`verification/evidence/20261002_round11_k7_directive/K7_FOUNDER_DECISION_REVIEW_PACK.md`) |

## Round 12 — Founder rulings and directive, verbatim

> Round 12 — K-7 Founder rulings.
> I accept the following:
> F-1 — Voucher basis: A
> - Use the business date throughout for voucher issue/expiry semantics.
> - While the business date is stale, do not issue new vouchers.
> - Do not alter existing production vouchers; production currently has none.
> F-2 — Seed row: leave unchanged.
> F-3 — Silent business-date readers:
> - Do not expand K-7 scope to Complete/Reopen.
> - Do not change their semantics under this directive.
> - Record them explicitly as residual Phase 3.2/3.4 items.
> - run_night_audit may receive the logged-error handling specified in the K-7 directive, provided it does not silently substitute the wall-clock date.
> F-4 — DDL default: leave the existing DDL unchanged. Record the corrected finding that production's existing credit_vouchers.issued_date has no DDL default.
> F-5 — Read-only displays: accept the proposed error/None behavior, provided it is deterministic, logged and does not substitute the system calendar date.
> F-6 — Authorization boundary: K-7 activation authorizes implementation and evidence generation on the local branch only. It does NOT authorize push, merge, deployment, production start, business-date change or trading.
> K7-D4: adopt voucher basis A as above.
> BD-D1: adopt sequence S1: complete K-7 implementation/evidence first; address the stale business date separately and time its remediation to go-live. No trading while the business date remains stale.
> K7-D10: remains undecided and outside this directive.
> Governance entries G-1 through G-7: do not invent missing authorization wording. Prepare them for later Founder review, but do not treat them as ruled by this Round.
> C-1 through C-3: record the corrections from the review pack, without silently expanding K-7 scope.
> Now:
> 1. append these rulings as Round 12 to FOUNDER_DECISIONS.md;
> 2. activate FG-P3-1-K7-DIRECTIVE-01;
> 3. freeze the directive after activation;
> 4. begin K-7 implementation and RED/GREEN verification on the local branch only;
> 5. run the required regression battery and declared-delta checks;
> 6. produce the complete K-7 implementation/evidence report.
> Hard boundary: absolutely no push, merge, production deployment, production start, database modification, migration, business-date change, or trading.
> Stop after the local implementation and evidence package is complete and report the exact commit, test results, changed files, declared deltas, and any remaining Founder decisions.

## Activation of `FG-P3-1-K7-DIRECTIVE-01`

- **Status:** ACTIVE and FROZEN from this entry.
- **Frozen text:** `verification/evidence/20261002_k7_phase_3_1/K7_PHASE_3_1_DIRECTIVE_FROZEN.md`, SHA-256 `28413d8e381fcefced8e6d9f0fc7798a1ef682e3f6d4e39025d0502ae4589f95`. It is the Round 11 draft (`20261002_round11_k7_directive/K7_PHASE_3_1_DIRECTIVE.md`, left unedited) with exactly the answers above and corrections C-1 to C-3 applied. Any later deviation is recorded in the implementation report; the frozen file is not edited.
- **Branch:** `k7-phase-3-1`, local only. **Base for code:** `0938069`.

## Corrections C-1 to C-3 (recorded as stated in the review pack §2.7; scope not expanded)

- **C-1 (corrected finding):** production's `credit_vouchers.issued_date` is `DATE NOT NULL` with no DDL default; `payments.payment_date`, `extra_charges.charge_date` and `business_date.current_date` have none. The DDL defaults at `app/__init__.py:1794` (`DEFAULT (date('now'))`) and `:1577` (`DEFAULT CURRENT_DATE`) exist only in code that creates fresh tables. Source: the schema of the verified recovery point `pms_20261002_093338_dq56-apply-pre.db`, read 2026-10-02.
- **C-2:** the two voucher expiry tests (`app/services.py:2009`, `:2077`) must follow one basis; `refresh_voucher_status` persists the derived status and `expired_at` and runs on redemption, on the lookup API and when the voucher ledger report is opened.
- **C-3:** the direct readers of the business-date row are the nine listed in the review pack §2.2. `get_business_date()` has 115 call sites that all raise when the row is absent once it fails closed.

## Residuals recorded (F-3)

Residual Phase 3.2 / 3.4 items, not changed by K-7: `app/reports.py:3121-3125` (Complete marks the day Completed and silently skips the date advance when the row is absent) and `app/reports.py:3225-3229` (Reopen silently skips the roll-back). `app/reports.py:3557-3560` (Force Close) already refuses with a message.

## Effect

- **RULED:** F-1 (voucher basis **A**; no new vouchers while the date is stale), F-2, F-3, F-4, F-5, F-6, K7-D4 = A, BD-D1 = **S1** (K-7 first; stale-date remediation separate and timed to go-live; no trading while stale).
- **Left undecided and outside this directive:** K7-D10 (close-path alternatives).
- **Not ruled by this round:** governance entries G-1 to G-7. They are prepared in the review pack §4 for later Founder review; no missing authorization wording was supplied or invented, and none is treated as ruled. BD-D2 to BD-D5, K7-D5 and every other open item are unchanged.
- **Authorizes:** K-7 implementation and evidence generation on the local branch `k7-phase-3-1`, under the frozen directive.
- **Not authorized:** push, merge, tag, deployment, production start, any production data change, a database modification outside disposable copies, a migration, a business-date change, trading.
