# FinalGrid — Architecture Closure & ADR Adoption Readiness

| | |
|---|---|
| Directive | FG-P0-ADR-ADOPTION-20260908-01 |
| Recorded | 2026-09-08 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` (unchanged by this task) |
| Database | `instance/pms.db` 733,184 B · SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` (unchanged) |
| Follows | FG-P0-ARCH-RESOLUTION-20260908-01 (`RECORD.md`, `result.json` in this directory — not edited) |
| Scope | Governance/architecture documentation only. **Implementation authorized: NO.** |

Three layers are kept distinct throughout: **architecture adopted** ·
**implemented control** · **verified production state**.

---

## 1. Final status of AR-001…AR-015

| AR | Subject | Status after this task | Carried by |
|---|---|---|---|
| AR-001 | INV-A02 universal; D11 rows a historical known exception | RESOLVED — adopted via ADR-002 | ADR-002 (ADOPTED) |
| AR-002 | Room-rent ownership | RESOLVED — label conflict closed; adopted via ADR-003 | ADR-003 (ADOPTED) |
| AR-003 | FK enforcement on every connection | RESOLVED — adopted as architecture requirement | ADR-005 (ADOPTED); B-9 |
| AR-004 | Staged `folio_id NOT NULL` | RESOLVED — adopted via ADR-002; mechanics in backlog | ADR-002; B-3 |
| AR-005 | Repository migration files authoritative | RESOLVED as principle; mechanism open | ADR-006 (PROPOSED); B-4 |
| AR-006 | Target recovery architecture | RESOLVED — adopted; restore not implemented | ADR-007 (ADOPTED); B-11 |
| AR-007 | No destructive pruning until design approved | RESOLVED as rule; design open | ADR-012 (PROPOSED); B-6 |
| AR-008 | Business-date authority | RESOLVED — adopted | ADR-004 (ADOPTED); B-10 |
| AR-009 | Authentication → Role/Permission → Operation → Audit | RESOLVED — adopted; Phase 2a frozen | ADR-008 (ADOPTED) |
| AR-010 | Maker-checker principle | RESOLVED as principle; matrix open | ADR-010 (PROPOSED); B-2 |
| AR-011 | Reporting authorization principle | RESOLVED as principle; classification open | ADR-009 (PFA); B-7 |
| AR-012 | Operator accountability | RESOLVED as principle; storage open | ADR-011 (PFA); B-8 |
| AR-013 | Scheduler financial-action controls | RESOLVED as principle; no ADR yet | B-1 |
| AR-014 | Four 2026-08-31 rulings | **CLOSED — HISTORICAL EVIDENCE GAP** (§3) | this record; `FOUNDER_DECISIONS.md` |
| AR-015 | Remaining Master Plan decisions at phase gates | APPLIED | `MASTER_PLAN.md` §15; BACKLOG |

## 2. AR-002 — final semantic definition and label reconciliation

**Architecture (authoritative by its definition):**

> The reservation remains the operational source for determining the stay and room-rate entitlement; the resulting room-rent financial transaction belongs to the reservation's billing folio.

**Repository-native name:** **Reservation operational ownership + folio financial ownership.**

**Reconciliation performed in ADR-003:** a *Final architecture* section states the definition and its semantics (reservation owns stay/rate context; folio owns the financial transaction; room-rent posting is an attributed folio transaction under ADR-002 R-1; INV-A02/A03 hold with no charge-type exception; Level 2 only; folio-balance meaning unchanged). A *Retirement of the historical option labels* section retires M1/M2/M3, states that AR-002's letter "M3" is **not** equivalent to the retired M3, and states that it is **not** claimed the Founder approved the retired M1. The historical candidate table is annotated as retired, not rewritten. **ADR-003 status: ADOPTED.** Night-audit posting is unchanged.

## 3. AR-014 — closure without reconstruction

Formal recording for each item: **Historical Founder ruling not recoverable from authoritative repository evidence. No reconstruction permitted.** Status: **CLOSED — HISTORICAL EVIDENCE GAP** — the historical record is incomplete, but no unresolved present-day architecture depends on reconstructing the missing wording.

| Ruling | Evidence that exists | What it proves | What it does not prove | Why exact recovery is unavailable | Present-day governing decision |
|---|---|---|---|---|---|
| FOUNDER-DIR-FINALGRID-BASELINE-RECON-003 | Gap-table summary (`FOUNDER_DECISIONS.md:164`, written 2026-09-05); R7 treated as presently reachable in commit `2765702`'s message | That a ruling with these effects was relied upon on 2026-08-31 | Its wording, its full set of corrections, or that any effect was individually approved | The ruling was issued in a session transcript and never written into the repository; `git log -S` finds no occurrence before 2026-09-08 | FG-GOV-20260908-01 (repository designation); FD-002 (register incorporated in `MASTER_PLAN.md` §06); Phase 2a evidence for R7 |
| Master Plan Round 0 ruling | One quoted sentence (`FOUNDER_DECISIONS.md:110-114`); gap-table summary (L164) | That the plan was accepted with the listed effects and that D11 was required | The verbatim ruling; acceptance wording for each of the seven §12 decisions | Same — transcript only | FD-002 (plan adopted); FD-010 + AR-001 (D11); FD-005 (PD-004/005/006 supersede §08 PD-4/5/6) |
| Phase 2a authorization | One quoted clause (`COMPLETION_REPORT.md:33-34`); "Authorized by" lines on `2765702`, `727d6ce`, `b8bc152`, `d85ec2f`, `237db2a` | That the implementers cited the directive as authority and applied its defaults | Founder wording, and — per this directive — commit messages are not treated as proof of Founder approval | Transcript only; the directive document itself is not in the repository | FD-016 / AR-009 (Phase 2a frozen as completed evidence); FD-015 (read scope, superseding default #2) |
| End-of-day checkpoint | Commit `237db2a` and its message; reflog fast-forward 2026-08-31 21:49:03; `.git/config` origin | That the checkpoint and remote migration occurred | The authorization wording for the act | Transcript only | FG-GOV-20260908-01; `e69f2ac` governance commit |
| *(observed)* FOUNDER-DIR-FINALGRID-REBRAND-001 | Cited "(accepted)" in `237db2a`'s message; rebrand present in the tree | That a rebrand directive was cited | Its content | Not in repository | Recorded as an evidence gap; not one of the four; content not invented |

**Governance principle (recorded in `FOUNDER_DECISIONS.md`):** current authoritative Founder decisions govern current architecture; missing historical wording must not be reconstructed merely to make the historical record appear complete. The architecture gate is **not** held open on this account.

## 4. Current ADR register

| ID | Title | Final status | Reason |
|---|---|---|---|
| ADR-001 | System-of-record boundary | **ADOPTED** | Text is verbatim FD-003; AR-002 consistent; residual questions are phase-gate items, not the boundary |
| ADR-002 | Folio attribution contract | **ADOPTED** | Level 2 rule fully consistent with D5, AR-001, AR-002, AR-004, FD-010; CD-1/3/4 defaults overridable at Phase 1 directive |
| ADR-003 | Room-rent ownership | **ADOPTED** | Semantic architecture recorded; M1/M2/M3 retired; no remaining conflict |
| ADR-004 | Business-date authority | **ADOPTED** | No conflicting architecture; details are Phase 3 design items |
| ADR-005 | SQLite FK enforcement | **ADOPTED (architecture requirement)** | AR-003; every connection, not caller-dependent; prerequisites in backlog; **not enabled** |
| ADR-006 | Production mutation controls | PROPOSED | Migration mechanism and "verified state" unresolved; controls already bind as FD-005 |
| ADR-007 | Backup / restore architecture | **ADOPTED (target architecture)** | AR-006 enumerates the target; **restore not implemented** |
| ADR-008 | Application authorization | **ADOPTED (architecture)** | AR-009 chain; Phase 2a frozen; **FD-015 recorded, not implemented** |
| ADR-009 | Reporting authorization | PROPOSED FOR ADOPTION | Principle settled; route classification not settled and not invented; awaits MP-D9 |
| ADR-010 | Maker-checker | PROPOSED | Operation matrix undefined |
| ADR-011 | Operator accountability | PROPOSED FOR ADOPTION | Architecture settled; storage/system-actor mechanics open |
| ADR-012 | Audit retention | PROPOSED | Retention design not designed or approved; pruning unchanged |

Adopted 7 · Proposed for adoption 2 · Proposed 3 · Draft 0 · Superseded 0.

## 5. Adopted vs proposed — one line each

**Adopted:** reservation = stay unit, folio = billing unit, invoice reservation-level (001) · every new financial row attributed at insert to its reservation's default folio (002) · room rent is a folio financial transaction with the reservation as operational source (003) · business date is the accounting date, wall clock technical (004) · FK enforcement required on every connection (005) · recovery = API backup + integrity + hash + manifest + retained artifact + rehearsed restore + documented verification (007) · Authentication → Role/Permission → Operation → Audit, Phase 2a frozen (008).

**Proposed:** how mutation-control steps are mechanised and which migration artefact rules (006) · report route classification and role sets (009) · maker-checker matrix (010) · accountability storage and system actor (011) · audit retention design (012).

## 6. ADR backlog

`verification/adr/BACKLOG.md`, B-1…B-12: scheduler financial-action controls (architecture) · maker-checker matrix (architecture) · NOT NULL mechanics + eight-row disposition (design + Founder decision + authorization) · schema migration mechanism (architecture) · PD-006 verified-state definition (architecture) · audit retention design (architecture; then bounded authorization) · report classification (design; MP-D9) · accountability storage (design) · FK prerequisites (design; authorization) · business-date implementation questions (design) · backup/restore mechanics (design; authorization) · Phase 1 contract defaults (Founder confirmation).

## 7. Remaining technical decisions

B-3, B-4, B-5, B-7, B-8, B-9, B-10, B-11 above.

## 8. Remaining Founder decisions

MP-D9 (operator profile) · MP-D4 (persistence engine) · MP-D1, MP-D3, MP-D6, MP-D7, MP-D8 at their phase gates (AR-015) · disposition of the eight D11 rows beyond FD-010 before any `NOT NULL` step · confirmation of CD-1/CD-3/CD-4 at Phase 1 directive approval · whether `AR-###` becomes a namespace under FD-001 (recorded, not promoted).

## 9. Implementation blockers (for implementation, not for planning)

| Blocker | Blocks |
|---|---|
| No restore capability → PD-006 unsatisfiable | Any production data/schema mutation (unit 1.6, Phase 5) |
| `backup_logs` has no integrity record; `copy2` backup path | Same |
| Destructive audit pruning scheduled (~2026-11-07) | Production certification (AR-007); audit-trail integrity |
| Migration mechanism undecided (B-4); unattended boot-time migration | Phase 5 |
| MP-D9 open | ADR-009/010/011 adoption; Phase 2b, Phase 4 |
| No implementation directive exists | Everything |

None of these blocks *planning*: the ADRs Phase 1 depends on (001, 002, 003, 004, 005-as-requirement) are adopted, Phase 1 requires no schema migration, and unit 1.6 is explicitly excluded.

## 10. Implementation authorization status

**NOT AUTHORIZED.** Architecture adopted; implementation remains separately authorized work. Target recovery architecture adopted; restore capability is not yet implemented. Authorization architecture adopted; route-by-route implementation remains future work. FK requirement adopted; nothing enabled. `list_folios` scope approved; endpoint unchanged. The eight D11 rows are unaltered.

## 11. Consistency verification (read-only, this task)

HEAD `e69f2ac` unchanged · database hash unchanged · D11 rows unchanged (payments 1–6, charges 1–2, NULL) · `git diff` over `app/`, `migrations/`, `tools/`, templates, static, launchers, `instance/`: empty · Phase 2a evidence and `app/folio.py` identical to checkpoint blobs · scheduler and pruning code unchanged · `audit_logs` 23 rows · 46 pre-existing dirty entries preserved · legacy repository fingerprints unchanged · no commit, no push.

## 12. Gate

**ARCHITECTURE BASELINE READY FOR IMPLEMENTATION PLANNING** — with the implementation blockers in §9 standing and no implementation authorized.
