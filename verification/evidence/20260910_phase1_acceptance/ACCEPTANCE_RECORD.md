# FinalGrid Phase 1 — Formal Acceptance Record

| | |
|---|---|
| Directive | FG-P1-ACCEPTANCE-20260910-01 (Founder decision — approved) |
| Recorded | 2026-09-10 |
| Baseline accepted | `aa6d9e91e7294be731383f755d6998acf5f059fc` — published; `origin/main` aligned at recording |
| Production anchor | `instance/pms.db` 733,184 B · SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` · D11 payments 1–6 / extra_charges 1–2 = ₹4,776.19 · audit_logs 23 · schema 144 objects — verified read-only before and after this directive's work |
| Governance records updated | `verification/FOUNDER_DECISIONS.md` (new dated section, append-only) · `verification/MASTER_PLAN.md` (§17 overlay, append-only) |
| ADRs | untouched (ADR-001…ADR-012 not reopened) |
| Commit | this directory is included in the single governance/evidence commit authorized by §11; the commit hash cannot appear inside its own content and is reported in the directive's final report |
| Push | **not performed, not authorized** |

## 1. Decision

**Phase 1 implementation: COMPLETE. Phase 1 verification: COMPLETE WITH DOCUMENTED LIMITATIONS. Phase 1 acceptance: ACCEPTED.**

Phase 1 is accepted as a completed implementation phase at published baseline `aa6d9e91`, with documented carry-forward items. Acceptance does **not** mean production deployment or activation, closure of any future carry-forward item, closure of pre-existing defects, closure of semantic review items, or authorization for Phase 2 implementation.

## 2. What is accepted — the settled facts

| # | Fact | Evidence |
|---|---|---|
| 1 | Five-commit Phase 1 history published: `e69f2ac2` → `d15d848e` → `34307c37` → `6cd2ac6d` → `95083995` → `aa6d9e91` | `20260909_five_commit_execution/` |
| 2 | 33/33 financial constructor sites carry `folio_id`; 24 writers map onto them exactly | `20260909_phase1_completion_review/` |
| 3 | 22/24 writers runtime-exercised; every row attributed to the reservation's folio A; 0 new unattributed rows on any copy | `20260909_phase1_verification_completion/WRITER_COVERAGE.md` |
| 4 | 2 writers (W-07 `settle_credit`, W-11 `redeem_credit_voucher`) not runtime-exercisable because of a pre-existing `TypeError` (`notes=` on `Payment`), since `b5b2514`; untouched by Phase 1 | same, §5 |
| 5 | Five registered datasets PASS; `DS-CORE-WALKIN` never declared | `DATASET_RESULTS.md` |
| 6 | Q14 AGREED on all five datasets; DIVERGED on production-derived copies by exactly ₹476.19 (the D11 charges) — not an attribution regression | `Q14_PARITY.md` |
| 7 | Phase 2a authorization matrix 29/29 at `aa6d9e91` | `PHASE2A_MATRIX.md` |
| 8 | Golden Master `phase1_aa6d9e91` 158/158 clean; historical `production` set intact with the four declared E-6 differences | `GOLDEN_MASTER_REBASELINE.md` |
| 9 | Clean new-activity copy: 18 HOLDS; INV-A02/A03 violated only by the eight D11 rows; INV-B01–B06 and C02 HOLD | pack `20260909_160110_inv_run_phase1_vc_setD` |
| 10 | Production `inv-run` identical to the pre-Phase-1 baseline; replay PASS 10/10 | Phase 1 execution packs |
| 11 | Production DB and D11 unchanged across every directive since the Golden Master capture | every pack; this record's header |

## 3. Decisions recorded alongside acceptance

| Item | Decision |
|---|---|
| Q5-P1 | Q-5 retained universally: all financial mutations should satisfy strict audit coupling; not weakened. The 12 non-strict writers → **CF-10**, bounded pre-Phase-2b work. Not implemented here. |
| GM-TAG | `phase1_aa6d9e91` adopted as the authoritative post-Phase-1 Golden Master; historical master retained as provenance. See `GOLDEN_MASTER_ADOPTION.md`. |
| CF-11 | `settle_credit` / `redeem_credit_voucher` remain pre-existing defects, not Phase 1 regressions, not fixed now; separate bounded defect directive later. No code prepared. |
| SR-1 / SR-2 | INV-B06 and INV-D02 remain SEMANTIC REVIEW REQUIRED; nothing modified; assigned to the architecture/business-semantics review track. |
| Deployment | Accepted but **not released / not deployed**; release timing is a separate operational decision. |
| Carry-forwards | CF-5, CF-6, CF-9, CF-10, CF-11, SR-1, SR-2 preserved open; CF-7 closed by the acceptance entry. See `CARRY_FORWARD_REGISTER.md`. |

## 4. What this directive did and did not do

Did: appended the acceptance section to `FOUNDER_DECISIONS.md`; appended §17 to `MASTER_PLAN.md`; created this directory; staged and committed, in one local commit, only the two governance files, the four previously untracked Phase 1 evidence directories authorized by §11, and this directory.

Did not: change application code, schema, fixtures, ledgers, the production database, any ADR, the historical Golden Master, or the previously committed evidence; did not deploy, reset, rebase, amend, force or push. The post-push evidence in `20260909_five_commit_execution/` is preserved as written on 2026-09-09 (it correctly describes itself as untracked at that time) and is not rewritten.

## 5. Scope residuals (recorded, not improvised)

- The adopted Golden Master set `verification/masters/phase1_aa6d9e91/` and the eleven harness packs created on 2026-09-09 (`20260909_1558xx…1604xx_*`) are **outside the commit scope §11 authorizes** and remain untracked. Under the repository rule "untracked evidence is not evidence" they need a separate commit authorization; see `GOLDEN_MASTER_ADOPTION.md` §3.
- Working copies under `verification/_work/` are disposable and ignored.
