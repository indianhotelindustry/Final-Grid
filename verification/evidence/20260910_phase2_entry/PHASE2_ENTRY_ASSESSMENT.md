# FinalGrid — Phase 2 Entry & Production-Readiness Assessment

| | |
|---|---|
| Directive | FG-P2-ENTRY-READINESS-20260910-01 (read-only planning / assessment) |
| Assessed | 2026-09-10 |
| Baseline | `a84566ae471786955283d107a9f2ad9e800bfcd4` on `main` = `origin/main`; 0 ahead / 0 behind; index and working tree clean |
| Chain | `e69f2ac2` → five Phase 1 commits → `aa6d9e91` (Phase 1 baseline) → `d71a2fb7` (acceptance) → `a84566ae` (Golden Master evidence) |
| Confirmed from the repository | `FOUNDER_DECISIONS.md` § "Phase 1 Formal Acceptance — FG-P1-ACCEPTANCE-20260910-01" (P1-ACC, Q5-P1, GM-TAG, CF-11, SR-1/2); `MASTER_PLAN.md` §17; `verification/masters/phase1_aa6d9e91/` tracked (158 surfaces); packs `20260909_160149/160158/160212` tracked |
| Production anchor | `instance/pms.db` 733,184 B · `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` · business date 2026-08-10 (unlocked) · `night_audit_enabled=false` · one user (`admin`, Admin) · 6 payments / 2 charges (all D11) · 23 audit rows |
| Result | **PHASE 2 ENTRY ASSESSMENT PASS** |
| Recommendation | **B. PHASE 2 ENTRY WITH PREREQUISITES** (section 6) |

Companion documents: `PRODUCTION_READINESS_INVENTORY.md`, `PHASE2_SCOPE.md`, `CERTIFICATION_GATES.md`, `BLOCKERS_AND_CARRYFORWARDS.md`, `WORK_ESTIMATE.md`, `result.json`. Nothing here authorizes implementation; no code, schema, data, fixture, ledger, master, governance record or ADR was changed; nothing committed or pushed.

## 1. The six questions, answered in one place

| Question | Answer |
|---|---|
| What remains before production certification? | Twelve gates (G1–G12, `CERTIFICATION_GATES.md`). Today **G1 Architecture, G2 Governance and G10 Regression verification pass**; G3 Financial integrity is partial (attribution done; audit coupling, dating and two broken credit paths open); **G5 Auditability, G6 Business-date integrity, G8 Recovery, G11 Deployment rehearsal and G12 Certification are not passable yet**; G4 Authorization, G7 Database integrity and G9 Reliability are partial. |
| What belongs in Phase 2? | Under the Master Plan, "Phase 2" now means **Phase 2b — Folio Auditability & Maker-Checker** (2b.1–2b.4), preceded by the **bounded pre-2b package** the Founder already designated for CF-10, into which the other small, already-decided items fit (CF-11 fix, audit-pruning exemption, FD-015, FD-017). `PHASE2_SCOPE.md`. |
| What belongs in later phases? | Business-date / night-audit integrity (Phase 3), broad and reporting authorization plus reliability (Phase 4), schema authority / FK / NOT NULL / migration mechanics (Phase 5), verification tooling (Phase 6), guest identity (Phase 7), dormant subsystems (Phase 8, evidence-gated), central services and scheduled restore verification (Phase 9). |
| What blocks production? | Eleven items, listed in `BLOCKERS_AND_CARRYFORWARDS.md`: destructive audit pruning, business-date integrity at the financial writers, night-audit operational controls and rehearsal, verified recovery for the *operating* backup path, two broken credit paths, CF-10 coupling (by Founder sequencing), launcher reproducibility, the Q06 GST-report divergence (must be explained), a deployment/rollback procedure and rehearsal, the D11 verdict question for certification, and — conditionally on MP-D9 — report/role authorization. |
| What can safely remain deferred? | `folio_id NOT NULL` and FK enforcement (code-level attribution is enforced and monitored), Level 3 split billing, dormant-subsystem triage, Excel/PDF masters, replay coverage of the new control, guest-identity wording, D7/D8/D10 tooling (manual certification is possible), concurrency re-engineering (MP-D4), central services. |
| Which verification gates must pass before deployment? | G10 (regression: Golden Master `phase1_aa6d9e91` 0 differences, replay 0 differences, invariants with only *declared* movement, five datasets, Phase 2a matrix, Q14 as declared) plus G8 recovery rehearsal on the operating backup path, G11 deployment rehearsal (fresh-install and upgrade paths, multi-day night-audit run on a copy, rollback exercised), and the invariant/GM/replay runs on the rehearsal copy after that run. |

## 2. Master Plan reconciliation — eleven phases

| Phase | Original purpose | Current state (repository) | Remaining work | Production impact |
|---|---|---|---|---|
| **0** Architecture & Decision Lock | Convert the vision into implementation-ready contracts; no code | **IN PROGRESS.** ADR-001/002/003/004/005/007/008 ADOPTED; ADR-006/010/012 PROPOSED, ADR-009/011 PROPOSED FOR ADOPTION; FD-001…FD-019, AR-001…AR-015, Q-1…Q-6, P1-ACC recorded. Open: MP-D1, D3, D4, D6, D7, D8, D9; four 2026-08-31 rulings unrecovered (AR-014); commit policy 0.5 partially adopted (SC-4/SC-6 practised) | Decisions at their phase gates (AR-015); B-2 maker-checker ADR; B-1 scheduler ADR; B-4 schema authority; B-5 "verified state"; B-6 retention design | Decisions gate Phases 2b, 3, 4, 5, 9 — none blocks Phase 3 |
| **2a** Folio Authorization Hardening | Close R7 before Phase 1 | **COMPLETED, FROZEN** (FD-016); 29/29 re-verified at `aa6d9e91` | FD-015 `list_folios` widening — decided, not implemented | Low (read scope only) |
| **1** Financial Foundation | Canonical folio attribution; INV-A02/A03 for the declared population | **COMPLETE, ACCEPTED** (P1-ACC, 2026-09-10) at `aa6d9e91`; 22/24 writers runtime-verified; unit 1.6 no action (FD-010) | CF-10 audit coupling at 12 writers (pre-2b); CF-11 two credit paths; SR-1/SR-2; CF-5/6/9 | Attribution risk closed for new activity; production verdict FAIL by design until the D11 question is settled |
| **2b** Folio Auditability & Maker-Checker | Sensitive-mutation control model; billing-responsibility governance; `Folio.company_id` vs `CheckInRecord.company_id`; complete AuditLog coverage | **NOT STARTED.** Entry: Phase 1 complete ✔ · MP-D9 ✗ (OPEN, interim Admin/Manager default) · MP-D5 ✔ · B-2 operation-matrix ADR ✗ | 2b.1–2b.4 after prerequisites; pre-2b package (CF-10 etc.) | Medium — void/refund maker-checker already exists (N2); folio mutations single-actor with audit |
| **3** Night Audit & Business-Day Integrity | Single business-date source; close idempotency; override/reopen semantics; interrupted-close recovery; staleness; V8; multi-day sequence (N7) | **NOT STARTED.** Entry condition ("Phase 1 complete") is **met today** — this is the only unstarted phase whose entry is satisfied | 3.1–3.8; K-7 wall-clock writers; scheduler controls (AR-013 / B-1) for `night_audit_job`; SR-1 | **HIGH** — the night audit is the financial close; R8 "never operated nightly"; production business date 30 days stale |
| **4** Operational Reliability | R5 concurrency, R6 authorization (27 report routes), F5 ADR derivation, N5 health check, V4 detector visibility, N8 logging, V10 launchers | **NOT STARTED.** Entry: Phase 3 ✗, MP-D4 ✗, MP-D9 ✗ | 4.1–4.7; ADR-009 adoption; FD-017 launcher fix (approved, not performed) | HIGH for authorization if multi-role operation (MP-D9); launchers affect deployability |
| **5** Migration & Schema Governance | Single schema authority; drift detection; version stamping; installer gate; reproducible schema | **NOT STARTED.** Entry: MP-D4 ✗, MP-D1 ✗, Phase 4 ✗ | 5.1–5.6; B-4; then FK (S8) and NOT NULL (S9, after B-3) | Blocks any production schema change; not needed for a no-schema-change release |
| **6** Verification Expansion | Layer-2 suite, V3 console, V5 Excel/PDF masters, docs (`docs/RELEASE.md` absent), VACUOUS visibility | **PARTIAL.** Layer-2 evidence scripts exist per phase (no framework); D1–D5 complete; D6 five datasets; D7/D8/D10 not built; D9 blocked at schema | 6.1–6.5; DS-CORE-WALKIN; CF-5, CF-6; INV-R01 commissioning; fault-run INCOMPLETE until D7/D9 | Medium — certification can be evidenced manually; tooling gaps raise effort, not risk |
| **7** Guest / Property Identity | V1 guest messaging; statutory identity | **NOT STARTED** (may run in parallel; entry Phase 0 only) | 7.1–7.3 | Medium (guest-visible wording), no financial impact |
| **8** Dormant Subsystem Reconciliation | Six-question triage of 28 dormant tables | **EVIDENCE-GATED** (needs real operation from Phase 3) | 8.1–8.4 | None before operation |
| **9** Central Services & Verified Recovery | Backup checksum, scheduled verified restore, D9, telemetry | **PARTIAL.** Recovery Foundation delivered `tools/restore_db.py` + rehearsal RR-20260908-01 (Q-6, pre-Phase-1 deviation); application backup path still `shutil.copy2`, encrypted, 30-day purge, no checksum; D9 still Blocked | 9.1–9.4; app-path manifest/hash; `.enc` restore rehearsal with key custody; scheduled verification; B-5, B-11 | **HIGH** — PD-006 / D9 are mandatory production gates (FD-005/FD-006) |

The eleven-phase sequence is unchanged. One reading of the dependency graph matters for planning and is stated here without altering the plan: **Phase 3 depends on Phase 1 only**, so it is enterable now, whereas Phase 2b waits on MP-D9 and B-2. Phase 3 is also on the production-critical path (G6, G9).

## 3. What the Phase 1 baseline gives Phase 2

- Every financial writer attributes to folio A through one fail-closed resolver; corrections inherit; D11 correction refused. 33/33 sites, 22/24 at runtime.
- Strict audit coupling at 12 writers (routes-level and POS) with the `audited_financial_write` / `_write_audit_strict` pattern available for the rest (CF-10).
- Reconciliation control `attribution_control` on the night audit.
- Recovery: a rehearsed restore tool for backup-API artifacts; PD-006 satisfiable for that path.
- Regression apparatus at a clean zero: Golden Master `phase1_aa6d9e91` 158/158, replay 10/10, five datasets, Phase 2a matrix, invariant baseline with only the D11 exception.

## 4. What Phase 1 did not give — carried into this assessment

Audit coupling at 12 writers (CF-10) · two non-functional credit paths (CF-11) · wall-clock dating at eight sites plus the calendar-clock late-checkout auto-charge (K-7, Q-3) · night audit never operated nightly (R8) and disabled on production · destructive audit pruning with exposure ~2026-11-07 · 27 report routes and several writers reachable by any authenticated role (R6) · application backup path unverified (D9) · FK off, `folio_id` nullable (by decision) · migration mechanism undecided (B-4) · D1 parity divergences on populated copies (Q04/06/07/12/15/18) — of which **Q06 diverges on production itself** (`gst_report` vs `tax_snapshot` by a factor of two) and must be explained before any GST figure is certified.

## 5. Phase 2b entry conditions

| Prerequisite | State | Readiness |
|---|---|---|
| Phase 1 complete | accepted 2026-09-10 | **READY** |
| MP-D5 settled | Level 2 floor adopted (FD-011); Level 3 out of scope (FD-003) | **READY** |
| MP-D9 operator profile | OPEN; interim Admin/Manager default applied in Phase 2a; FD-014 principle adopted; FD-015 read scope ruled | **NOT READY** — a Founder decision (or an explicit extension of the interim default to 2b, including the self-approval question for a single-operator property) |
| Maker-checker operation-matrix ADR (B-2) | ADR-010 PROPOSED; sensitive-mutation list is a candidate input; thresholds, self-approval, convergence of the three approval models, reason validation unresolved | **NOT READY** — depends on MP-D9 |
| CF-10 audit-coupling normalization | designated pre-2b by Q5-P1; not implemented | **NOT READY** — bounded implementation directive required |
| Authorization / accountability prerequisites | ADR-008 adopted; ADR-009 and ADR-011 PROPOSED FOR ADOPTION (storage location, system actor, route classification open) | **PARTIALLY READY** — 2b.4 "complete AuditLog coverage" needs ADR-011's storage decision only if the envelope goes into schema; the coupled-audit-row option needs no schema |
| Recovery prerequisites | restore tool + rehearsal exist for backup-API artifacts; PD-006 satisfiable for a schema-free 2b; "verified state" (B-5) unconfirmed; `.enc` path unrehearsed | **PARTIALLY READY** — sufficient for code-only 2b; insufficient for any 2b schema change |
| Schema / migration prerequisites | B-4 undecided; boot-time unattended migration; no `alembic_version` | **NOT READY for schema change** — 2b must stay schema-free (request/approval rows would need PD-004; ADR-010 notes the existing `void_requests` / `PendingApproval` tables as reference shapes) |

Net: Phase 2b implementation cannot start today; its prerequisites are a Founder decision (MP-D9), one ADR (B-2) and one bounded implementation (CF-10). None of them is engineering-blocked.

## 6. Recommendation

**B. PHASE 2 ENTRY WITH PREREQUISITES.**

- Prerequisites for Phase 2b proper: MP-D9 ruled or the interim default explicitly extended; B-2 operation-matrix ADR adopted; CF-10 delivered and verified; 2b scoped schema-free unless PD-004 is issued.
- Enterable now under existing decisions, without new architecture: the **bounded pre-2b package** (CF-10; CF-11 fix; ADR-012 item 1 "remove `AuditLog` from the prune loop" — needs the Founder to confirm it as a bounded exemption per ADR-012's own open question; FD-015; FD-017) and **Phase 3**, whose entry condition is met and which sits on the production-critical path.
- What the recommendation is not: an authorization. Every item above requires its own directive under FD-004's authority chain.

## 7. Method and limits

Sources: the repository at `a84566ae` only — `MASTER_PLAN.md`, `FOUNDER_DECISIONS.md`, all twelve ADRs and `BACKLOG.md`, the Phase 0 records (`20260908_repo_identity_designation`, `20260908_architecture_resolution_round1`, `20260908_phase1_implementation_readiness`), every Phase 1 pack, `WAVE0_STATUS.md`, `KNOWN_DEFECTS.md`, the acceptance and carry-forward registers; the production copy read only for settings, users and the business date. No harness command was executed; verification figures are those recorded on 2026-09-09. Effort figures are ranges (`WORK_ESTIMATE.md`), not commitments; no deployment date is given.
