# PHASE GATES A–H — DEFINITIONS MISSING

| | |
|---|---|
| Prepared | 2026-10-02, analysis only, `C:/wtov` at `c9eeff0` |
| Outcome | **Definitions not recoverable.** No file in the working tree and no commit in git history contains the definitions of Gates A–H. This file therefore exists in place of `PHASE_GATES_A_H.md` |
| Rule followed | No meaning is invented. Everything under §4 is labelled **INFERENCE** and is not a definition |
| Decision | GT-D5 in `GATES_DECISION_REQUIRED.md` |

## 1. Source of the gates (FACT)

- `verification/MASTER_PLAN.md:13`: "Prepared under | `FOUNDER-DIR-FINALGRID-TARGET-001` — **not present in this repository**; its §8, §10, §17, §18, §19, §21 and Gates A–H are cited by the plan and are unrecovered".
- `verification/MASTER_PLAN.md:347`: "The text of `FOUNDER-DIR-FINALGRID-TARGET-001`, its Gates A–H and its §8/§10/§17/§18/§19/§21. Unrecovered. Gate letters are transcribed as cited."
- `verification/evidence/20260908_phase1_implementation_readiness/VERIFICATION_PLAN.md:40`: "Gates A–H are cited as the Master Plan cites them; their source text (TARGET-001) is unrecovered."
- AR-014 closed the related 2026-08-31 rulings as "CLOSED — HISTORICAL EVIDENCE GAP … No reconstruction permitted" (`verification/FOUNDER_DECISIONS.md:917-937`). It records the principle: "Missing historical wording must not be reconstructed merely to make the historical record appear complete" (`:933-935`).
- The certification gates G1–G12 (`verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md`) are a **separate model**. No document maps A–H onto G1–G12. `20260910_phase2_founder_decisions/PRODUCTION_IMPACT.md:3` says "Gate letters refer to `20260910_phase2_entry/CERTIFICATION_GATES.md`", meaning G1–G12, not A–H.

## 2. Search performed (method)

| Scope | Method | Result |
|---|---|---|
| Working tree `C:/wtov` (all file types, tracked and untracked; `venv/`, `python/`, `.git/`, `node_modules` excluded) | grep for `Gate A`…`Gate H`, `Gates A`, `Gates:`, `gate letters`, `TARGET-001`, `FINALGRID-TARGET`, `Gate G reference`, `gates A–H`/`A-H`, `phase gate` (case-insensitive where sensible) | references only; no definition |
| Git history, all refs (88 commits) | `git log --all -S` for each of `Gate A`…`Gate H`, `TARGET-001`, `Gates A`, `Gates:** `, `Gate letters`; `git log -p -G` for gate-letter patterns; `git log --all --grep`; `git fsck --unreachable --no-reflogs` (9 unreachable commits, 5 blobs) | **no removed (`-`) line in any commit**; every occurrence was added and never deleted. A definition never existed in history |
| Outside the repository (read-only) | `FinalGrid/g3_decision_package/`, `FinalGrid/adr011_apply`, `adr011_preprod`, `db-backups` (non-`.db` files only); legacy copy `DSS/SukoonPMS/SukoonPMS` (`.md`/`.txt`/`.json` only). The live folder `FinalGrid/SukoonPMS` was **not** opened | references only (the legacy copy holds an identical Phase 2a report) |

Pickaxe hits (`git log --all -S`): "Gate A" → `34307c3`; "Gate B" → `d71a2fb`, `34307c3`, `d85ec2f`; "Gate C" → `34307c3`, `d85ec2f`; "Gate D" → only `e7086da` (false positive: "ADR-011 Production Gate Directive"); "Gate E" → none; "Gate F" → `d85ec2f` (plus false positives `d452524`, `b5b2514`: "Release Gate Framework"); "Gate G" → `805ee0d`, `d71a2fb`, `34307c3`, `e69f2ac`, `d85ec2f` (plus false positive `683db72`: "Gate G3"); "Gate H" → `34307c3`; "TARGET-001" → `34307c3`, `e69f2ac`, `d85ec2f`.

## 3. Every place Gates A–H are referenced

### 3.1 Per-phase gate lists (`verification/MASTER_PLAN.md` §05)

| Line | Phase | Gates |
|---|---|---|
| 116 | 0 Architecture & Decision Lock | H |
| 124 | 2a Folio Authorization Hardening | B, F, G, H |
| 134 | 1 Financial Foundation | A, C, F, G, H — "B inherited from Phase 2a" |
| 143 | 2b Folio Auditability & Maker-Checker | B, C, F, G, H |
| **150** | **3 Night Audit & Business-Day Integrity** | **A, C, D, E, F, G, H** |
| 157 | 4 Operational Reliability | A, B, E, F, G, H |
| 164 | 5 Migration & Schema Governance | A, E, F, G, H |
| 172 | 6 Verification Expansion | F, G, H |
| 179 | 7 Guest / Property Identity | A, G, H |
| 185 | 8 Dormant Subsystem Reconciliation | H |
| 191 | 9 Central Services & Verified Recovery | A, E, F, G, H |

Letter frequency: H in every phase; D only in Phase 3; E in 3, 4, 5, 9; B in 2a, 2b, 4 (and "inherited" in 1).

### 3.2 Other references in `MASTER_PLAN.md`

- `:13`, `:347` — unrecovered (quoted in §1).
- `:227` — "N2 | Void / refund maker-checker | … STRENGTH. Preserve unchanged. Gate G regression subject".
- `:448` — "Golden Master | `phase1_aa6d9e91` adopted as the post-Phase-1 Gate G reference (158/158)".

### 3.3 Phase 2a completion report — the only place letters carry names

`verification/evidence/20260831_phase2a_folio_authz/COMPLETION_REPORT.md`:
- `:3` "**Directive:** FOUNDER-DIR-FINALGRID-TARGET-001, Phase 2a"
- `:56` "### Gate B — Security · **PASS**" (body: the 29-case authorization matrix)
- `:75` "### Gate C — Financial · **PASS (stability)**"; `:77` "For Phase 2a the financial gate is that nothing moved, not that anything improved."
- `:95` "### Gate F — Verification framework · **PASS**"
- `:102` "### Gate G — Regression · **PASS, with a stale master declared**"
- `:162` "| Verification passed | Gates B, C, F, G, H |"
- There is no Gate H heading.

Commit `d85ec2f` (2026-08-31, "Phase 2a (4/4): completion report and gate evidence") message: "Gates B, C, F, G, H satisfied. B 29/29 authorization cases pass … C invariant results identical to the frozen baseline — for this phase the financial gate is stability, not improvement … F read-only VERIFIED, zero writes, invariant semantics untouched … G gm-verify FAILs on a master captured 2026-08-03 … H this report … Authorized by: FOUNDER-DIR-FINALGRID-TARGET-001 Phase 2a directive."

**Status of these names:** they were written by the engineer applying the gates, not taken from the directive's text. They are **evidence of how gates were applied once**, not definitions.

### 3.4 Phase 1 verification plan — artifact-to-gate mapping

`verification/evidence/20260908_phase1_implementation_readiness/VERIFICATION_PLAN.md:31-38`:
- "Layer 2 test record for every creation site | Gate A, F"
- "Phase 2a matrix re-run | Gate B (inherited), G"
- "`inv-run` production before/after — identical | Gate C, F"
- "`inv-run` new-activity copy — A02/A03 HOLD, B01–B03 HOLD | Gate C, D"
- "`ds-run` + `ds-coverage` six datasets green | Gate C, F"
- "Parity: Q14 AGREED on datasets and new-activity copy; no other quantity moves | Gate C, G"
- "`gm-verify` and `replay-verify` — declared differences only | Gate G"
- "Completion report with §18 answerability, D11 freeze by id, baseline integrity record | Gate H, SC-1"

**Inconsistency (FACT):** `:34` assigns Gate D to a Phase 1 artifact, but `MASTER_PLAN.md:134` does not list D for Phase 1.

### 3.5 Other usages (Gate G / Gate B / Gate C)

All under `verification/evidence/`:
- `20260908_phase1_implementation_readiness/READINESS_REPORT.md:33` ("Gate G cannot detect Phase 1 regressions against a stale master"), `:87` ("inherits Gate B from Phase 2a"), `:117`.
- `20260908_phase1_implementation_readiness/PHASE1_EXECUTION_PLAN.md:9`; `FOUNDER_DECISION_GATE.md:9` (Q-3, "complicates Gate C declaration"), `:10` (Q-4, "Gate G is blind …").
- `20260909_phase1_acceptance_prep/FOUNDER_DECISION_ITEMS.md:11`; `result.json:48` ("adopt phase1_aa6d9e91 as Phase 2 Gate G reference").
- `20260909_phase1_completion_review/REQUIREMENT_MATRIX.md:21`; `PHASE2_READINESS.md:23`; `COMPLETION_REVIEW.md:114` ("Standing rule G-3 / Gate B"), `:127`.
- `20260909_phase1_verification_completion/GOLDEN_MASTER_REBASELINE.md:22`; `PHASE2A_MATRIX.md:11`.
- `20260910_phase1_acceptance/GOLDEN_MASTER_ADOPTION.md:24`, `:28`.
- `20260910_phase2_entry/PHASE2_SCOPE.md:38` ("Golden Master `phase1_aa6d9e91` … at 0 differences as the Gate G reference").
- Outside the repository: `FinalGrid/g3_decision_package/G3_DECISION_PACKAGE.md:297`, `G3_DEPENDENCY_MAP.md:62` (both state the gap).

## 4. What can be inferred — INFERENCE, not definition

| Letter | Inference | Basis | Confidence |
|---|---|---|---|
| A | possibly functional / Layer-2 behavioural tests of the changed application behaviour | VERIFICATION_PLAN `:31` ("Layer 2 test record … Gate A, F"). A appears in the phases that change application behaviour (1, 3, 4, 5, 7, 9) and not in 2a, 2b, 6, 0, 8 | weak |
| B | authorization / security (negative authorization matrix) | COMPLETION_REPORT `:56`; MASTER_PLAN `:311` "negative-authorization test record (2a, 2b, 4)" matches exactly the phases listing B | moderate |
| C | financial (invariants: stability or declared change) | COMPLETION_REPORT `:75,77`; VERIFICATION_PLAN `:33-36` | moderate |
| D | possibly new-activity invariant behaviour and/or replay | D appears only in Phase 3. MASTER_PLAN `:311` lists "replay evidence (3)" only for Phase 3. VERIFICATION_PLAN `:34` maps the new-activity `inv-run` to "C, D" | weak |
| E | unknown. No usage anywhere. Phases 3, 4, 5, 9 (night audit, reliability, migration, recovery) might suggest operational / recovery / migration safety | pattern only | speculative |
| F | verification-framework self-checks (read-only, zero writes, semantics untouched) | COMPLETION_REPORT `:95-100`; d85ec2f message | moderate |
| G | regression (Golden Master, replay) | COMPLETION_REPORT `:102`; MASTER_PLAN `:227,448`; VERIFICATION_PLAN `:37` | strong usage, still not a definition |
| H | completion report / answerability / baseline-integrity record | d85ec2f message "H this report"; VERIFICATION_PLAN `:38`. H is in every phase; MASTER_PLAN `:311` "Phase completion report (every phase) … baseline integrity record (every gate)" | moderate |

**Specific gaps for Phase 3 (A, C, D, E, F, G, H):** D and E have no named usage anywhere. Phase 3 is the only phase that lists D. Without a ruling, a Phase 3 directive cannot be checked against D or E at all, and against A, C, F, G, H only by inference.

**ANALYSIS — overlap with G1–G12, not a mapping.** By content, B overlaps G4, C overlaps G3, G overlaps G10, H overlaps G2/SC-1, and F has no G-equivalent (verification-framework self-checks). This is **not** a claim that the letters mean those gates.

## 5. Exact Founder decision needed (GT-D5)

One of:

- **OPTION 1 — Restate Gates A–H.** The Founder issues, as a new `FOUNDER_DECISIONS.md` entry, the operative meaning and pass criterion of each of A–H. This is a present-day definition, not a reconstruction of TARGET-001; AR-014 forbids reconstruction (`FOUNDER_DECISIONS.md:923`). If the Founder chooses to adopt the inferred meanings in §4, the entry must say so explicitly.
- **OPTION 2 — Retire Gates A–H in favour of G1–G12.** The Founder rules that phase directives from Phase 3 onward are checked against named certification gates (e.g. Phase 3 → G3 K-7 item, G6, G10) and the Master Plan "Gates:" lines are historical. That needs an appended `MASTER_PLAN.md` overlay; the plan text itself is not edited (FD-002 `:419`).
- **OPTION 3 — Per-directive gates.** Each phase directive (starting with Phase 3) states its own acceptance gates explicitly. Letters A–H are kept as historical citations only.

**What is blocked without it:** checking a Phase 3 directive and its completion against "Gates: A, C, D, E, F, G, H" (`MASTER_PLAN.md:150`). **What is not blocked:** G1–G12 evaluation, which has its own definitions (`CERTIFICATION_GATES.md:29-42`), and drafting the Phase 3 directive's content.
