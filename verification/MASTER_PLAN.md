# FinalGrid Implementation Master Plan — Durable Repository Record

**Status of this document:** adopted planning baseline under **FD-002**
(2026-09-08). This file is the repository's authoritative record of the
plan. It is a transcription with a status overlay; it does not add,
remove or reinterpret plan content.

## Provenance and authority

| | |
|---|---|
| Source | Claude artifact `34821b10-b65f-45de-8695-5da3b541cd1d`, *FinalGrid Implementation Master Plan — Round 0*, 2026-08-31 |
| Prepared under | `FOUNDER-DIR-FINALGRID-TARGET-001` — **not present in this repository**; its §8, §10, §17, §18, §19, §21 and Gates A–H are cited by the plan and are unrecovered |
| Accepted | Master Plan Round 0 ruling, 2026-08-31 — exists in session transcript `47bae5bd-0e38-4319-8000-980550f72777` only; its recorded effects are listed in `FOUNDER_DECISIONS.md` gap table (L164) |
| Adopted as planning baseline | FD-002, 2026-09-08, `verification/FOUNDER_DECISIONS.md` |
| Transcribed | 2026-09-08 at HEAD `237db2ad0fa8df143f04aaca82441f0f54781969`; database anchor `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` unchanged |
| Authority rule | The artifact is provenance. **This file is the repository record.** Where this file and the artifact differ, the difference is an error in this file and is corrected by an appended note, never by editing the artifact. |
| Identifier convention | Master Plan decisions D1–D11 are cited as **MP-D1…MP-D11** (FD-001 namespace note). Plan deviations are cited as **deviation PD-1…PD-4 (§11)**. Production-data safety controls are cited as **§08 PD-1…PD-6**, whose operative successors are **PD-004…PD-006** (FD-005). Wave 0 deliverables D1–D10 are unchanged. |

## Status vocabulary used in the overlay

| Term | Meaning |
|---|---|
| **COMPLETED** | Work performed and evidenced in this repository |
| **ADOPTED** | Founder-ruled, recorded in `FOUNDER_DECISIONS.md` |
| **PROPOSED** | Drafted (artifact or in-session), not adopted |
| **BLOCKED** | Cannot proceed until a named condition is met |
| **NOT STARTED** | No work, no directive |
| **OPEN** | Decision not yet made |

---

## 01 Standing controls

Six controls applying to every phase, checked at the start and end of every session and at every gate.

| ID | Control | Mechanism (as written in the plan) |
|---|---|---|
| SC-1 | The baseline database is read-only for all development. | SHA-256 of `instance/pms.db` verified against `51dd83b7…30bc2` at session start, session end, and every gate. Any drift halts work. |
| SC-2 | All development runs against disposable copies. | Copies made through `verification/dbcopy.py :: make_copy()`. No ad-hoc file copies. |
| SC-3 | No application process may outlive a working session. | Consequence of V9. Port 5000 confirmed clear at session start and end. |
| SC-4 | Historical evidence is append-only. | Existing packs, ledgers, masters and dated reports are never edited. New evidence is added alongside. |
| SC-5 | No finding is reclassified without a Founder ruling. | The 53-entry register is the authority. UNKNOWN stays UNKNOWN. |
| SC-6 | One implementation unit, one commit, one authorizing reference. | Every commit names the finding or decision that authorizes it. No history rewriting. |

Overlay: SC-1 through SC-6 have been practised in every session since 2026-08-31 (Phase 2a evidence, FG-GOV-20260908-01 evidence). They are **ADOPTED** as part of the plan under FD-002.

---

## 02 The ordering conflict and its resolution

The directive's §8 ("activation of a dormant financial subsystem must never precede authorization hardening") contradicted its §21 locked order (Phase 1 before Phase 2) once R7 was reclassified *presently reachable*. The plan proposed splitting Phase 2:

| Unit | Content | Position |
|---|---|---|
| Phase 2a | Authorization hardening only — role guards on four folio endpoints, `AuditLog` on every folio mutation, negative tests. | BEFORE Phase 1 |
| Phase 2b | Full control model — maker-checker on sensitive folio mutations, billing-responsibility changes, reconciliation of the duplicated company linkage (`Folio.company_id` inert vs `CheckInRecord.company_id` live). | AFTER Phase 1 |

Overlay: the split (deviation PD-1) was **accepted** in the 2026-08-31 ruling (transcript-only; effect recorded at `FOUNDER_DECISIONS.md:164`) and **Phase 2a is COMPLETED** — see §05.

---

## 03 Decision gating matrix (MP-D1…MP-D11)

| Decision | Blocks | Does not block | Needed to start Phase 1? | **Overlay 2026-09-08** |
|---|---|---|---|---|
| MP-D1 multi-property | Phase 5 (schema authority shape), Phase 9 | 1, 2a, 2b, 3, 7 | No | OPEN (Register D1 / F2) |
| MP-D2 successor | Nothing — settled by the accepted rebrand | All | No | Partially answered by rebrand; explicit confirmation OPEN |
| MP-D3 deployment | Phase 9 entirely; informs Phase 4 | 1–3 | No | OPEN |
| MP-D4 SQLite | Phase 4 (concurrency), Phase 5 | 1, 2a, 3 | No | OPEN |
| MP-D5 financial depth / split billing | Phase 1 scope; Phase 2b | — | Floor only | **ADOPTED** — Level 2 floor (D5, FD-011); Level 3 outside scope (FD-003) |
| MP-D6 dormant subsystems | Phase 8 | 1–7 | No | OPEN |
| MP-D7 AI positioning | Nothing structural | All | No | OPEN |
| MP-D8 market | Nothing near-term | All | No | OPEN |
| MP-D9 operator profile | Phase 2a role matrix, 2b, 4 (R6) | Phase 1 core | Or interim default | OPEN. Interim Admin/Manager default applied in Phase 2a. `list_folios` read scope ruled by FD-015. Accountability principle adopted by FD-014. |
| MP-D10 W1-R3 gate | Phase 1 start | Phase 2a | Yes | **ADOPTED** — re-scoped to unit 1.6 / first production data migration (D10, 2026-09-05; confirmed 2026-09-08) |
| MP-D11 historical attribution | Phase 1 unit 1.6 | Units 1.1–1.5 | Yes | **RULED** — D11-F2 factual (2026-09-05); **FD-010 Option A** treatment (2026-09-08): preserve, untouched, no attribution. Unit 1.6 has no authorized action. |

### MP-D11 as the plan stated it

> Principle P4 says financial history is immutable and must never be silently rewritten. Phase 1 requires re-establishing `INV-A02`. The frozen baseline holds 6 payments and 2 charges with `folio_id` NULL, and historical backups hold 58 payments and 7 charges in the same state. Is assigning a folio to an existing unattributed row a correction of history, or a completion of it?

The plan listed three positions: (a) attribute historical rows; (b) scope INV-A02 forward; (c) declare the historical population VACUOUS. **The Founder's FD-010 "Option A" is not the plan's "(a)".** FD-010 preserves the rows unattributed and authorizes nothing further; it is closest in effect to leaving the plan's question open on the invariant side while closing it on the data side. See `FOUNDER_DECISIONS.md` FD-010.

---

## 04 Dependency graph

Critical path (each requires the one above); parallel nodes may run once their entry condition is met.

| Node | Phase | Requirement stated by the plan |
|---|---|---|
| P0 | Architecture & Decision Lock | Documents only. Produces the contracts Phases 1–2 implement. |
| P2a | Authorization Hardening | Requires P0 · MP-D9 or interim default. Must precede P1 (deviation PD-1). |
| P1 | Financial Foundation — folio attribution | Requires P2a · MP-D10 · MP-D5 floor · MP-D11 for unit 1.6. No schema migration. |
| P2b | Folio Auditability & Maker-Checker | Requires P1 · MP-D9 · MP-D5. |
| P3 | Night Audit & Business-Day Integrity | Requires P1. Produces the real history Phase 8 needs. |
| P4 | Operational Reliability | Requires P3 · MP-D4 · MP-D9. |
| P5 | Migration & Schema Governance | Requires MP-D4 · MP-D1. First phase where production migration becomes possible. |
| P7 (parallel) | Guest / Property Identity | Requires P0 only. |
| P6 (parallel) | Verification Expansion | Layer-2 tests alongside P1–P5. |
| P8 (parallel) | Dormant Subsystem Reconciliation | Requires evidence from real operation (P3) · MP-D6. Cannot be date-scheduled. |
| P9 (parallel) | Central Services & Verified Recovery | Requires MP-D3 · MP-D1 reporting level. Closes the rollback confidence gap. |

Three structural observations recorded by the plan: Phase 1 requires no schema migration (`folio_id` already exists on both tables); Phase 7 is independent of the financial chain; Phase 8 cannot be scheduled by date.

---

## 05 Phase boundaries — eleven phases, with status overlay

### PHASE 0 — Architecture & Decision Lock — **IN PROGRESS**
- **Objective:** convert the Round 0 vision into an implementation-ready contract. No code.
- **Entry:** frozen baseline verified; this plan accepted.
- **Findings:** F2, F8, F11, F13 (scope), N1 (scope input), MP-D1–D11.
- **Units:** 0.1 decision dossier · 0.2 **financial model contract** (folio ownership, creation points, defensible attribution) · 0.3 **authorization model contract** · 0.4 **historical attribution position paper** resolving MP-D11 · 0.5 evidence, branch and commit-attribution policy.
- **Gates:** H. **Evidence:** four contract documents; no packs. **Not touched:** all application code, database, migrations, configuration, UX, verification logic, historical evidence. **Rollback:** n/a.
- **Overlay:** 0.1 — delivered in-session (Founder Decision Pack, 2026-09-05; resolution pack, 2026-09-08), partially durable through `FOUNDER_DECISIONS.md`. 0.2 — **PROPOSED** (Folio Ownership & Creation Contract artifact `ea374fdc…`, 2026-09-05); governed by FD-011; architecture ADR-002. 0.3 — interim matrix applied in Phase 2a; ADR-008 drafted. 0.4 — resolved by D11-F2 + FD-010 without a position paper; the closed-period invariant test on a copy proposed by the plan was **not performed** (no attribution is authorized, so the test is moot under FD-010). 0.5 — SC-4/SC-6 adopted; commit policy otherwise **OPEN**.

### PHASE 2a — Folio Authorization Hardening — **COMPLETED**
- **Objective:** close R7 before Phase 1 makes folio data worth attacking.
- **Entry:** unit 0.3; MP-D9 settled or interim Admin/Manager default accepted.
- **Findings:** R7 (authorization component).
- **Units:** 2a.1 role guard on all four folio endpoints · 2a.2 `AuditLog` on every folio mutation · 2a.3 negative tests per unauthorized role.
- **Gates:** B, F, G, H.
- **Not touched:** folio attribution logic, the financial model, night audit, any other authorization idiom (R6 is Phase 4).
- **Rollback:** single branch; revert restores exactly current behaviour; no data touched.
- **Overlay — evidence in repository:** branch `phase-2a-folio-authz`, commits `2765702`, `727d6ce`, `b8bc152`, `d85ec2f`, checkpoint `237db2a`; `verification/evidence/20260831_phase2a_folio_authz/` (`COMPLETION_REPORT.md`, `result.json`, `verify.py`) — verdict PASS, 29 of 29, anchor unmoved; `app/folio.py` fail-closed gate, all four endpoints Admin/Manager, JSON 401/403, audit coupling. **Frozen** by FD-016. FD-015 approves widening `list_folios` read scope to Accountant and Front Desk — **not yet implemented**; mutating endpoints unchanged.

### PHASE 1 — Financial Foundation — Folio Attribution — **NOT STARTED · directive PROPOSED · unit 1.6 BLOCKED**
- **Objective:** canonical folio ownership so every legitimate financial transaction carries a defensible attribution, and INV-A02 / INV-A03 hold for the declared population.
- **Entry:** Phase 2a complete ✔ · MP-D10 ruled ✔ · MP-D5 floor confirmed ✔ · MP-D11 required for unit 1.6 only ✔ (ruled; see 1.6).
- **Findings:** R1, F3, N1 (Level 2 component).
- **Units:** 1.1 folio lifecycle contract · 1.2 attribution at source across all `ExtraCharge` construction sites · 1.3 payment creation paths including refund and reversal · 1.4 night-audit posting path (`services.py:2365`) · 1.5 explicit policy for any intentionally unattributed transaction · 1.6 historical row disposition per the D11 ruling · 1.7 reconciliation consumes the canonical relationship · 1.8 re-verify INV-A02 and INV-A03, commissioned not merely passing.
- **Gates:** A, C, F, G, H — B inherited from Phase 2a.
- **Not touched:** authorization (2a/2b), night-audit lifecycle (3), schema mechanism (5), reports beyond reconciliation consumers, dormant subsystems, itemised split-billing routing unless MP-D5 authorizes Level 3. **No schema migration.**
- **Rollback:** branch per unit. Data changes only under 1.6, separately authorized under §08 PD-4 / PD-6 (now PD-004 / PD-006).
- **Overlay:** implementation directive **PROPOSED** (artifact `42e90c62-a5cf-40dd-8db5-5243163920d2`, 2026-09-05; 22 application creation sites; 0 schema changes) — **not authorized**. **Unit 1.6: no action authorized under FD-010**; the eight rows remain preserved. Unit 1.8 whole-database verdict will remain FAIL by design (FD-010 consequence). Architecture prerequisites: ADR-002, ADR-003, ADR-004 (drafts).

### PHASE 2b — Folio Auditability & Maker-Checker — **NOT STARTED**
- **Entry:** Phase 1 complete; MP-D9 and MP-D5 settled.
- **Findings:** R7 (control-model component), N1 (duplicated company linkage).
- **Units:** 2b.1 define sensitive financial mutation; maker-checker where irreversible · 2b.2 govern billing-responsibility changes · 2b.3 reconcile `Folio.company_id` (inert) vs `CheckInRecord.company_id` (live) · 2b.4 complete AuditLog coverage for the mutation set.
- **Gates:** B, C, F, G, H. **Not touched:** R6 (Phase 4); the existing void/refund maker-checker (preserved strength N2).
- **Overlay:** BLOCKED on Phase 1 and MP-D9. Architecture: ADR-010 (draft).

### PHASE 3 — Night Audit & Business-Day Integrity — **NOT STARTED**
- **Entry:** Phase 1 complete.
- **Findings:** R8, N7, V8, R10 (validation constraint).
- **Units:** 3.1 single source of business-date derivation · 3.2 close idempotency · 3.3 blocker/override semantics with approver identity and retained reason · 3.4 bounded, authorized reopen · 3.5 interrupted-close recovery · 3.6 staleness escalation · 3.7 remove control recomputation from `night_audit_panel.html` (V8) · 3.8 multi-day sequence verification (N7).
- **Gates:** A, C, D, E, F, G, H. **Not touched:** folio model, authorization idioms outside night audit, reports, snapshot-hash and closed-period protections.
- **Overlay:** FD-013 adopts business date as authoritative accounting date; ADR-004 (draft). Live business date 2026-08-10 at recording (29 days stale).

### PHASE 4 — Operational Reliability — **NOT STARTED**
- **Entry:** Phase 3 complete; MP-D4 and MP-D9 settled.
- **Findings:** R5, R6, F5, N5, N8, V4, V10.
- **Units:** 4.1 R5 concurrency under MP-D4 · 4.2 R6 one enforceable authorization convention; close the 27 unrestricted report routes · 4.3 F5 consolidate ADR (average daily rate) derivation · 4.4 N5 database-aware post-restart check · 4.5 V4 detector failure visible · 4.6 N8 structured logging · 4.7 V10 launcher reproducibility.
- **Gates:** A, B, E, F, G, H. **Not touched:** migration/schema governance (5), verification tooling (6), structural decomposition of `routes.py`/`reports.py` (§19).
- **Overlay:** FD-016 principle adopted; ADR-008, ADR-009 (drafts). FD-017 grants a bounded CRLF exemption for the nine LF-only launchers (V10) — **not performed**. Note: the plan's "ADR" in F5 means *average daily rate*, not Architecture Decision Record.

### PHASE 5 — Migration & Schema Governance — **NOT STARTED** (reassigned items — deviation PD-2)
- **Entry:** MP-D4 and MP-D1 settled; Phase 4 complete.
- **Findings:** R2, F14, N4, N9.
- **Units:** 5.1 single schema authority; retire or activate the orphaned mechanism deliberately · 5.2 N4 column-level drift detection · 5.3 version stamping and existing-database handling · 5.4 F14 correct the boot log · 5.5 correct the installer gate that can never pass · 5.6 N9 make an existing database's schema stateable and reproducible.
- **Gates:** A, E, F, G, H. **Not touched:** the R2/F14 correction must be preserved; N4 and N9 may not be marked solved as a side effect (ruling B-5).
- **Rollback:** first phase where production migration is possible; every migration requires a separate directive, the PD-5 sequence and PD-6 rehearsal (now PD-004/005/006).
- **Overlay:** FD-007 migration authority adopted; single schema authority **UNRESOLVED** (ADR-006).

### PHASE 6 — Verification Expansion — **NOT STARTED** (reassigned items — deviation PD-3)
- **Entry:** runs alongside Phases 1–5; formally closed after Phase 5.
- **Findings:** R3, V3, V5, R9, F7, F12 (VACUOUS handling).
- **Units:** 6.1 Layer-2 test suite per §07 · 6.2 V3 registry command on default Windows console · 6.3 V5 golden-master capture for Excel and PDF · 6.4 R9/F7 documentation, starting with `docs/RELEASE.md` cited five times in code · 6.5 keep VACUOUS and NOT_COMMISSIONED reporting visible.
- **Gates:** F, G, H. **Not touched:** invariant semantics, VACUOUS classification, fault registry, replay engine.
- **Rollback:** additive only.

### PHASE 7 — Guest / Property Identity Integrity — **NOT STARTED** (may run in parallel)
- **Entry:** Phase 0 complete.
- **Findings:** V1 (open); F1 and V2 (closed — reference only).
- **Units:** 7.1 V1 guest messaging in `guest_database.html` · 7.2 audit every guest-facing surface · 7.3 statutory documents carry property identity exclusively.
- **Gates:** A, G, H. **Not touched:** financial content or statutory format of any document; invoice numbering; GST computation.

### PHASE 8 — Dormant Subsystem Reconciliation — **NOT STARTED · EVIDENCE-GATED**
- **Entry:** cannot be scheduled by date; requires evidence from a real property operating a full cycle (produced by Phase 3).
- **Findings:** F6, F9, F10, F12, F13 (scope), V6, MP-D6.
- **Units:** 8.1 six-question framework per dormant table · 8.2 distinguish dormant features from infrastructure signals · 8.3 record determinations · 8.4 resolve V6.
- **Gates:** H. **Not touched:** no deletion in this phase; determination only.

### PHASE 9 — Central Services & Verified Recovery — **NOT STARTED**
- **Entry:** MP-D3 accepted; MP-D1 reporting level settled.
- **Findings:** V7, N8, MP-D3.
- **Units:** 9.1 checksum column on `backup_logs` · 9.2 verified restore on a schedule · 9.3 the D9-equivalent capability · 9.4 health and version telemetry.
- **Gates:** A, E, F, G, H. **Not touched:** multi-property tenancy, shared configuration, shared database.
- **Overlay:** FD-006 confirms Wave 0 D9 = Backup Restore Verification, mandatory production-readiness gate; FD-005 PD-006 requires a rehearsed restore. **No restore capability exists at recording**; ADR-007 (draft).

---

## 06 Findings → phase map — all 53 register entries

Register severity/status from the frozen Finding Register (artifact `8512df7d-d3f7-4958-800b-a321fe1f993f`, RECON-003, 2026-08-31 12:22:50). Phase and disposition as the plan assigned them.

| ID | Finding (plan short title) | Register | Phase | Disposition |
|---|---|---|---|---|
| R1 | Folio subsystem inert | CRITICAL / CONFIRMED | Phase 1 | Primary objective of Phase 1 |
| R2 | No schema version authority | MEDIUM / REFINED | Phase 5 | Corrected interpretation preserved |
| R3 | No app business-logic test suite | HIGH / REFINED | Phase 6 | Layer 2 only; Layer 1 preserved |
| R4 | Money exactness | LOW / DISPROVED | — | DISPROVED. Struck. Not a remediation target and not a reason to replace SQLite |
| R5 | SQLite locking no-op | HIGH / CONFIRMED | Phase 4 | Behaviour understood and documented even if the engine does not change |
| R6 | Authorization — 7 idioms, 27 open report routes | MEDIUM / CONFIRMED | Phase 4 | Folio-specific portion handled earlier in 2a |
| R7 | Folio endpoints presently reachable | HIGH / CONFIRMED | Phase 2a + 2b | Split: hardening before Phase 1 (**done**), control model after |
| R8 | Night audit never operated | HIGH / CONFIRMED | Phase 3 | Measured evidence retained |
| R9 | Key-person / provenance | MEDIUM / CONFIRMED | Phase 6 | Documentation as knowledge preservation |
| R10 | Sample size of one | MEDIUM / CONFIRMED | — | A validation constraint, not a defect. Gates Phase 8 entry |
| F1 | Product identity absent | INFO / CLOSED | — | CLOSED by the accepted rebrand |
| F2 | No tenant dimension | DECISION / FOUNDER-DECISION | Phase 0 | FOUNDER DECISION MP-D1. Not a defect |
| F3 | INV-A02 / INV-A03 violated | CRITICAL / CONFIRMED | Phase 1 | Exit criterion for Phase 1 (see FD-010 consequence) |
| F4 | Structural concentration | MEDIUM / CONFIRMED | — | Explicitly out of scope per §19. Known cost, declared in §11 |
| F5 | ADR derived four ways | MEDIUM / CONFIRMED | Phase 4 | Follow the canonical occupancy engine pattern |
| F6 | Dual representations | MEDIUM / CONFIRMED | Phase 8 | Depends on data-vintage evidence |
| F7 | Documentation absent | MEDIUM / REFINED | Phase 6 | Partially addressed by the root README |
| F8 | AI labels heuristics | MEDIUM / FOUNDER-DECISION | Phase 0 | FOUNDER DECISION MP-D7 |
| F9 | Legacy naming, dead branch, orphan | LOW / CONFIRMED | Phase 8 | Low severity; bundled with dormant triage |
| F10 | GRC never exercised | LOW / UNRESOLVED | Phase 8 | UNRESOLVED until real operation |
| F11 | C-Form not implemented | LOW / FOUNDER-DECISION | Phase 0 | FOUNDER DECISION MP-D8 |
| F12 | 28 dormant tables, 7 VACUOUS, INV-R01 | HIGH / UNRESOLVED | Phase 8 | UNRESOLVED. VACUOUS reporting preserved |
| F13 | Housekeeping scope | LOW / UNRESOLVED | Phase 8 | UNRESOLVED scope question, routed to MP-D6 |
| F14 | Boot log names the wrong mechanism | MEDIUM / CONFIRMED | Phase 5 | Reassigned from Phase 4 — deviation PD-2 |
| N1 | Company billing works; itemised split does not | MEDIUM / UNIQUE | Phase 0 + 1 + 2b | Scope via MP-D5; duplicated linkage resolved in 2b |
| N2 | Void / refund maker-checker | STRENGTH / UNIQUE | — | STRENGTH. Preserve unchanged. Gate G regression subject |
| N3 | Guest token security | STRENGTH / UNIQUE | — | STRENGTH. Preserve unchanged |
| N4 | Column-level drift invisible | MEDIUM / UNIQUE | Phase 5 | Reassigned — deviation PD-2. Independent of the R2 correction |
| N5 | Updater polls the shallow health endpoint | MEDIUM / REFINED | Phase 4 | Consequence stands; framing refined |
| N6 | Fault injection platform | STRENGTH / UNIQUE | — | STRENGTH. Preserve. Used as evidence throughout |
| N7 | Replay INCOMPLETE over two dates | MEDIUM / UNIQUE | Phase 3 | Resolves as real history accumulates |
| N8 | Observability file-log-only | MEDIUM / UNIQUE | Phase 4 + 9 | Structured logging, then telemetry |
| N9 | Schema not reproducible | MEDIUM / UNIQUE | Phase 5 | Reassigned — deviation PD-2. Independent finding |
| V1 | Guest messages use product identity | HIGH / UNIQUE | Phase 7 | Guest-visible today. May run in parallel |
| V2 | Advance receipt fallback | LOW / CLOSED | — | CLOSED by the accepted rebrand |
| V3 | inv-registry fails on cp1252 console | LOW / UNIQUE | Phase 6 | Reassigned — deviation PD-3 |
| V4 | Detector failure invisible | MEDIUM / UNIQUE | Phase 4 | P11 violation |
| V5 | Golden masters capture HTML only | MEDIUM / UNIQUE | Phase 6 | Reassigned — deviation PD-3. Limitation carried until closed |
| V6 | Four ambiguous W1-R1 surfaces | LOW / UNRESOLVED | Phase 8 | UNRESOLVED |
| V7 | D7–D10 never built; no backup checksum | MEDIUM / UNIQUE | Phase 9 | Engineering fact. Sequencing half is MP-D10 |
| V8 | Night-audit control logic in template | LOW / UNIQUE | Phase 3 | Reassigned — deviation PD-4 |
| V9 | Orphaned process mutated the baseline | MEDIUM / CONFIRMED | — | CONFIRMED and resolved. Now standing control SC-3 |
| V10 | stop.bat could not be executed | MEDIUM / UNRESOLVED | Phase 4 | Stays UNKNOWN until reproducibility is established (FD-017 exemption granted, not performed) |
| D1 | Multi-property scope | DECISION | Phase 0 | FOUNDER DECISION (MP-D1) — OPEN |
| D2 | Renamed or successor | DECISION | Phase 0 | Settled in practice by the rebrand; confirm explicitly |
| D3 | Deployment model | DECISION | Phase 0 | FOUNDER DECISION (MP-D3). Gates Phase 9 — OPEN |
| D4 | SQLite as system of record | DECISION | Phase 0 | FOUNDER DECISION (MP-D4). Exactness argument withdrawn — OPEN |
| D5 | Itemised split billing | DECISION | Phase 0 | FOUNDER DECISION (MP-D5). Level 2 floor **ADOPTED** (D5 / FD-011); Level 3 outside scope (FD-003) |
| D6 | Dormant subsystem scope | DECISION | Phase 0 | FOUNDER DECISION (MP-D6). Gates Phase 8 — OPEN |
| D7 | AI positioning | DECISION | Phase 0 | FOUNDER DECISION (MP-D7) — OPEN |
| D8 | Market | DECISION | Phase 0 | FOUNDER DECISION (MP-D8) — OPEN |
| D9 | Operator profile | DECISION | Phase 0 | FOUNDER DECISION (MP-D9). Gates the Phase 2a role matrix — OPEN; interim default used |
| D10 | W1-R3 blueprint gate | DECISION | Phase 0 | FOUNDER DECISION (MP-D10). Gates Phase 1 start — **ADOPTED** (re-scoped) |

MP-D11 (historical attribution) was surfaced by the plan itself and is not a register entry; it is ruled (D11-F2, FD-010).

---

## 07 Verification requirements

**Layer 1 — constitutional verification (preserve, do not weaken).** 26 invariants, 40 commissioned faults, 5 datasets, replay, isolation hashing, VACUOUS classification and financial-history protections are preserved unchanged. Invariant semantics may not be weakened to obtain a green result. VACUOUS reporting may not be disabled. `INV-R01` remains NOT_COMMISSIONED until genuinely commissioned. A phase outcome requiring an invariant to change is a constitutional amendment requiring a Founder ruling.

**Layer 2 — application business-logic tests (new, additive).**

| Coverage area | Introduced in | Minimum bar |
|---|---|---|
| Folio creation & ownership rules | Phase 1 | Every creation path exercised; ownership rule asserted |
| Charge posting & attribution | Phase 1 | All `ExtraCharge` construction sites covered (plan: 15; Folio Contract enumerates the application sites precisely) |
| Payment posting, refund, reversal | Phase 1 | Includes the refund path, which currently omits `folio_id` |
| Transfer & authorization | Phase 2a / 2b | Negative tests first |
| Night audit, reopen, recovery | Phase 3 | Idempotency and interrupted-close recovery |
| Reconciliation | Phase 1 / 3 | Canonical relationships only |
| Reporting permissions | Phase 4 | The 27 unrestricted report routes |
| Migration behaviour | Phase 5 | Fresh install, upgrade, existing-database paths |

Known limitation carried forward: golden masters capture HTML only (V5).

Overlay: FD-004 adopts the authority chain in which verification evidence is the last link and a PASS does not authorize production mutation.

---

## 08 Production-data safety controls (as written in the plan) and their successors

| Plan ID | Plan text | Successor / carrier |
|---|---|---|
| PD-1 | `instance/pms.db` is never a development target. Every phase works on copies produced by `make_copy()`. | SC-1 / SC-2 (adopted) |
| PD-2 | The baseline hash is verified before and after every session and at every gate (SC-1). A mismatch is treated as an incident. | SC-1 (adopted) |
| PD-3 | Evidence packs are generated only at phase gates, named for the phase, committed as evidence, never edited afterwards. | SC-4 (adopted) |
| PD-4 | No production migration without a separate phase-specific Founder directive naming the migration. | **PD-004** (FD-005) |
| PD-5 | Any authorized production migration follows the §17 sequence in full: backup → verify → migration plan → recovery plan → execute → post-migration verification → invariant verification → evidence capture. | **PD-005** (FD-005) — sequence restated by the Founder without reference to the unrecovered §17 |
| PD-6 | Interim control, in force until Phase 9. Because restore has never been verified, every production migration is additionally preceded by a restore rehearsal on a copy, proving the backup actually restores to an equal state. | **PD-006** (FD-005) — no longer described as interim; a mandatory gate |

---

## 09 Rollback strategy

| Layer | Mechanism | Confidence (plan) | Overlay |
|---|---|---|---|
| Code | One branch per phase, one commit per unit, `git revert`; no history rewriting | High | Practised (Phase 2a) |
| Detection | Golden masters and replay | High | Golden master stale since 2026-08-03 (declared by Phase 2a) |
| Development data | Disposable copies discarded | High | — |
| Production data | Restore from the pre-migration backup | **Low** | **No restore capability exists** (verified 2026-09-08). FD-005/FD-006 make this a mandatory gate. |

The plan's statement stands: production-data rollback rests on backups whose restore has never been verified; `backup_logs` carries no checksum column and had never held a row at the frozen baseline.

---

## 10 Expected evidence artifacts

Phase completion report (every phase) · invariant evidence pack (1, 2b, 3, 5) · golden master diff (1, 3, 4, 7) · replay evidence (3) · fault commissioning record (any phase adding a control) · negative-authorization test record (2a, 2b, 4) · restore rehearsal record (before any production migration) · baseline integrity record (every gate).

Overlay: Phase 2a produced its completion report, negative-authorization record (29 cases), `inv-run` and `gm-verify` packs, and baseline integrity record — all committed.

---

## 11 Deviations declared (five)

| Ref | Directive says | Plan proposes | Reason | Overlay |
|---|---|---|---|---|
| deviation PD-1 | §21 locks Phase 1 before Phase 2 | Split Phase 2; run 2a before Phase 1 | Satisfies §8 given R7 reclassification | **Accepted** (2026-08-31, transcript-only); executed |
| deviation PD-2 | §10 assigns F14, N4, N9 to Phase 4 | Assign to Phase 5 | Migration/schema-governance items belong with the migration phase | Accepted (2026-08-31, transcript-only) |
| deviation PD-3 | §10 assigns V3, V5 to Phase 4 | Assign to Phase 6 | Verification-tooling defects | Accepted (2026-08-31, transcript-only) |
| deviation PD-4 | §10 assigns V8 to Phase 4 | Assign to Phase 3 | Night-audit control logic moves with night-audit work | Accepted (2026-08-31, transcript-only) |
| MP-D11 | §7 requires re-establishing INV-A02; §3 P4 forbids rewriting financial history | Treat historical attribution as a separate Founder decision | Real accounting question | Accepted; ruled D11-F2 + FD-010 |

One constraint acknowledged: §19 forbids broad refactoring; `routes.py` and `reports.py` will be touched function-by-function only, with F4 remaining open at a larger footprint.

---

## 12 Decisions required to proceed (plan §12) — resolution status

| # | Decision | Blocks | Status 2026-09-08 |
|---|---|---|---|
| 1 | deviation PD-1 — Phase 2a before Phase 1 | Everything | Accepted; Phase 2a completed |
| 2 | MP-D10 — does the blueprint's D9 gate still bind? | Phase 1 start | Ruled: re-scoped to unit 1.6 (D10; FD-006/FD-007 context) |
| 3 | MP-D11 — historical attribution | Unit 1.6 | Ruled: D11-F2 factual; FD-010 Option A (preserve) |
| 4 | MP-D5 floor — Level 2 | Phase 1 scope | Ruled: Level 2 (D5; FD-011) |
| 5 | MP-D9 — operator profile or interim default | Phase 2a role matrix | Interim default accepted in practice; profile OPEN; FD-014, FD-015 recorded |
| 6 | deviation PD-2 / PD-3 / PD-4 reassignments | Phases 3, 5, 6 scope | Accepted (2026-08-31, transcript-only) |
| 7 | evidence-pack policy (plan §08 PD-3) | All gates | Carried by SC-4; adoption of the plan under FD-002 |

---

## 13 What this record does not contain

- The text of `FOUNDER-DIR-FINALGRID-TARGET-001`, its Gates A–H and its §8/§10/§17/§18/§19/§21. Unrecovered. Gate letters are transcribed as cited.
- The verbatim 2026-08-31 rulings (BASELINE-RECON-003, Master Plan Round 0 ruling, Phase 2a authorization, end-of-day checkpoint). Their recorded effects appear above with provenance; the rulings themselves remain to be recorded under a Founder authorization.
- The plan's per-phase "Phase 0.1 decision dossier" content beyond what `FOUNDER_DECISIONS.md` now records.
- Any resolution of the open technical questions listed in the ADR drafts under `verification/adr/`.

---

## 14 Architecture Resolution Round 1 — status overlay (appended 2026-09-08)

Source: `verification/evidence/20260908_architecture_resolution_round1/RECORD.md`
(FG-P0-ARCH-RESOLUTION-20260908-01), recorded at governed HEAD `e69f2ac…`.
**Architecture resolution is not implementation authorization.** Nothing
below opens a phase, a unit or a migration. The eleven-phase sequence in
§04–§05 is unchanged.

### Architecture decisions now resolved, by phase

| Phase | Resolved architecture (AR) | What the phase still needs before it can start |
|---|---|---|
| Phase 0 | AR-001 (INV-A02 universal), AR-002 (room rent → folio; **label M3/M1 pending confirmation**), AR-005 (repo migration files authoritative — mechanism open), AR-009 (authz chain), AR-010, AR-011, AR-012, AR-013 principles; AR-014 recovery outcome; AR-015 sequencing rule | Founder confirmation of the AR-002 label and of the four 2026-08-31 rulings; ADR adoption |
| Phase 2a | AR-009 confirms frozen | — (COMPLETED) |
| Phase 1 | AR-001, AR-002, AR-004 steps 1–2 | Phase 1 directive approval; ADR-002/003 adoption; CD-1/3/4 confirmation. **Unit 1.6 stays gated** (FD-010; AR-004 step 3 needs a separate Founder decision on the eight rows) |
| Phase 2b | AR-010 principle | Phase 1 complete; MP-D9; maker-checker operation-matrix ADR |
| Phase 3 | AR-008 (business date), AR-013 (scheduler) principles | Phase 1 complete; ADR-004 adoption; scheduler-controls ADR |
| Phase 4 | AR-009, AR-011 | Phase 3 complete; MP-D4, MP-D9; ADR-008/009 adoption |
| Phase 5 | AR-003 (FK on every connection), AR-004 steps 4–5, AR-005 | MP-D4, MP-D1; schema-mechanism selection (unit 5.1); PD-004/005/006; restore capability (PD-006) |
| Phase 9 | AR-006 (recovery target), AR-007 (retention) | MP-D3; restore capability does not exist |

### Implementation prerequisites that remain (unchanged by this round)

No restore capability (PD-006 unsatisfiable) · `backup_logs` has no integrity record · destructive audit pruning still scheduled (FD-008/AR-007; ~2026-11-07) · FK enforcement off · both `folio_id` columns nullable with 8 NULL rows · originating writers unattributed · `date.today` model defaults · ≥26 report routes unrestricted · `list_folios` still `('Admin','Manager')` in code (FD-015 recorded only) · migration mechanism undecided.

### Statement

Resolved architecture ≠ implemented control ≠ verified production state. Every AR above is the first of the three. Implementation authorization will be issued separately after architecture review/adoption.

---

## 15 ADR adoption baseline — status overlay (appended 2026-09-08)

Source: `verification/evidence/20260908_architecture_resolution_round1/ADR_ADOPTION_READINESS.md`
(FG-P0-ADR-ADOPTION-20260908-01). The eleven-phase sequence in §04–§05 is
unchanged. **Architecture adoption is not permission to begin Phase 1
implementation**; a Phase 1 implementation directive must be separately
approved.

| Layer | Content |
|---|---|
| **Architecture adopted** | ADR-001 system-of-record boundary · ADR-002 folio attribution (Level 2) · ADR-003 room rent — *reservation operational ownership + folio financial ownership* · ADR-004 business-date authority · ADR-005 FK enforcement requirement · ADR-007 target recovery architecture · ADR-008 authorization chain (Phase 2a frozen) |
| **Architecture proposed** | ADR-009 reporting authorization (PFA; awaits MP-D9, route review) · ADR-011 operator accountability (PFA; storage mechanics) · ADR-006 mutation-control mechanics · ADR-010 maker-checker matrix · ADR-012 audit retention design |
| **Implementation prerequisites** (unchanged) | No restore capability (PD-006 unsatisfiable) · `backup_logs` has no integrity record · destructive audit pruning scheduled (~2026-11-07) · FK enforcement off · both `folio_id` columns nullable, 8 NULL rows preserved (FD-010) · originating writers unattributed · `date.today` model defaults · ≥26 report routes unrestricted · `list_folios` still `('Admin','Manager')` in code · migration mechanism undecided (B-4) |
| **Implementation authorization** | **None issued.** Phase 1 directive: prepared (artifact), not approved. Unit 1.6: no authorized action. |

Backlog of decisions the adopted architecture still requires:
`verification/adr/BACKLOG.md` (B-1…B-12).

Historical evidence gaps (AR-014) are **closed** as evidence-quality
issues; §13 of this record remains accurate as a statement of what the
repository does not contain.

---

## 16 Phase 1 implementation readiness — overlay (appended 2026-09-08)

Source: `verification/evidence/20260908_phase1_implementation_readiness/`
(FG-P1-IMPLEMENTATION-READINESS-20260908-01), recorded at governed HEAD
`e69f2ac…`. State: **implementation planning only.**

| Layer | Status |
|---|---|
| Plan completed | Yes — writer inventory (24 financial writers, all reservation-resolvable), execution plan (S0–S7 within Phase 1; S8–S9 outside), migration/data plan, recovery-gate plan, verification plan, Founder decision gate. |
| Plan ready | **PHASE 1 NOT READY FOR EXECUTION AUTHORIZATION** — recovery gate unsatisfied (no restore capability); Founder questions Q-1…Q-6 open; no durable Phase 1 directive in the repository. |
| Implementation authorized | **No.** Production mutation authorized: **No.** |

Evidence that sharpened the plan: the live database's NULL-`folio_id`
population is exactly the eight D11 rows (no other financial rows exist),
so no data migration is required on this database and unit 1.6 has no
authorized action; `PRAGMA foreign_key_check` reports zero orphans; an
audit-atomicity gap is confirmed at every routes-level financial writer
and at POS; eight writers date rows from the wall clock (Phase 3 scope
unless ruled otherwise). The eleven-phase sequence is unchanged; the plan
proposes one accepted-if-ruled deviation (Recovery Foundation before
Phase 1 code, Q-6).
