# FinalGrid — Five-Commit Staging Plan

| | |
|---|---|
| Directive | FG-PRECOMMIT-STAGE-20260909-01 |
| Supersedes | the three-commit plan in `20260909_phase1_execution/COMPLETION_REPORT.md` §10 |
| Basis | Pre-Commit Audit FG-PRECOMMIT-AUDIT-20260909-01 (blocking finding: DO NOT COMMIT AS THREE COMMITS) |
| Prepared | 2026-09-09 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` — **unchanged; no commit, no push, no amend, no reset of HEAD** |
| `origin/main` | `e69f2ac2…` — identical to local HEAD; nothing unpushed |
| Status | **PRE-COMMIT STAGING PASS — FIVE COMMIT BOUNDARIES VERIFIED** |

## 1. Why three commits was wrong

The Phase 1 completion report proposed three commits (Recovery, Golden Master,
Phase 1) and classified everything else as *"pre-existing dirty state … must
NOT be staged."* The audit found that classification unsafe on two counts.

**1. It orphaned 77 legitimate paths.** The ledger recapture (47 paths) and the
governance / ADR adoption baseline (30 paths) are not dirt. They are
release-gate inputs and the architectural basis the other three bodies cite.

**2. It would have produced a self-inconsistent repository.** `verification/ledgers/`
is a tracked release-gate input, deliberately un-ignored at `.gitignore:61`
under the repository's own rule *"Untracked evidence is not evidence."*
`verification/replay/replay.py:58` reads exactly this set. Committing the August
**masters** while leaving the May **ledgers** at HEAD would have shipped, in both
the Golden Master and Phase 1 commits, evidence asserting `replay-verify PASS,
10 dates, 0 differences` into a tree whose ledger set is 28 May dates — a claim
its own contents contradict.

Two artifacts were separately confirmed as genuine junk and deleted:
`_audit_stage_src.tgz` (contained `.env`; see `SECRET_REMEDIATION.md`) and
`package-lock.json`.

## 2. The five bodies of work

Chronology is established by file mtimes and corroborated by each directive's
own recorded date.

| # | Commit | Purpose | When (mtime) | Paths |
|---|---|---|---|---|
| 1 | **Ledger recapture** | D3 stored replay re-based May → August, so replay evidence is reproducible | 2026-08-30 / 08-31 | 47 |
| 2 | **Governance / ADR adoption** | 12 ADRs DRAFT → ADOPTED, `BACKLOG.md` B-1…B-9, Architecture Resolution Round 1, Phase 1 readiness | 2026-09-08 09:09–16:30 | 30 |
| 3 | **Recovery Foundation** | `tools/restore_db.py` + 19-case suite, rehearsal RR-20260908-01, Founder Resolution Round 2 | 2026-09-08 19:38–19:42 | 10 |
| 4 | **Golden Master recapture** | Authoritative pre-Phase-1 master, 158 surfaces frozen 2026-08-10 | 2026-09-09 06:26–06:34 | 184 |
| 5 | **Phase 1 + W-20** | Folio attribution at every financial writer; W-20 runtime closure | 2026-09-09 06:52–08:08 | 34 |

Sum of scope lines 305; **distinct paths 304**, equal to the working tree.
`verification/FOUNDER_DECISIONS.md` is the single path appearing twice (commits
2 and 3), by the split described in §4. **Every changed path is covered exactly
once, except that one file. Nothing is orphaned.**

## 3. Dependency order — mandatory, not stylistic

Each link is a hard content dependency, verified against blob contents rather
than asserted:

| Link | Proof |
|---|---|
| 1 → 4 | The Golden Master's `replay-verify PASS (10 dates, 0 differences)` is only reproducible against the August ledger set. Its log names the stored replay `2026-08-31T04:35:44`, matching packs `20260831_043518/043544` and the ledger mtimes (04:35 UTC = 10:05 IST). |
| 2 → 3 | Recovery implements ADR-007, adopted in commit 2. |
| 3 → 4 | The Golden Master's authorizing decision is **Q-4**, which lives in Founder Resolution Round 2 — shipped by commit 3. `## Q-4` appears **0×** at HEAD and **1×** in the working tree. Committing 4 before 3 would make it unauthorized on its own record. |
| 4 → 5 | Phase 1's `gm-verify` result (157/158 clean, 4 differences) is measured against the **recaptured** master and predicted by `EXPECTED_PHASE1_DELTAS.md` E-6. |
| 3 → 5 | Phase 1 cites the recovery-tool suite (19/19 OK) as regression evidence. |
| 5 → W-20 | `20260909_w20_runtime/verify.py:270` patches `app.services.audited_financial_write` — a symbol appearing **0×** at HEAD and **2×** in the working tree. W-20 cannot import before Phase 1. |

Do not reorder. Do not combine.

## 4. Boundary decision — `verification/FOUNDER_DECISIONS.md` is split

The file is a pure append: HEAD 867 lines, working tree 1,051, no deletions, and
the working tree is byte-prefixed by HEAD. The appended 184 lines carry **two
different directives' material**:

| File lines | Content | Commit |
|---|---|---|
| 868–982 (115 lines) | Architecture Resolution Round 1 index entry; ADR Adoption Baseline `FG-P0-ADR-ADOPTION-20260908-01` | **2** |
| 983–1051 (69 lines) | Founder Resolution Round 2 `FG-P1-RECOVERY-FOUNDATION-20260908-01`, Q-1/CD-1 … Q-6 | **3** |

The split point is clean: line 982 is blank, line 983 is the Round 2 heading.
The file is pure LF throughout; no line-ending change is introduced.

Staging was performed **by content**, not by line number: each half was
materialised as a blob and installed into the index with
`git update-index --cacheinfo`, then the resulting blob was read back and
asserted against §15. `git add -p` was not usable because this environment
provides no interactive stdin; the blob method is deterministic and produces an
identical index state.

| | Commit 2 blob `ab3e3aed…` | Commit 3 blob `8a5a3656…` |
|---|---|---|
| Lines | 982 | 1,051 (= working tree exactly) |
| `Founder Resolution Round 2` | 0 ✅ | 1 ✅ |
| `## Q-1` … `## Q-6` | 0 each ✅ | 1 each ✅ |
| `Architecture Resolution Round 1` | 1 | 1 — **not duplicated** ✅ |
| `ADR Adoption Baseline` | 1 | 1 — **not duplicated** ✅ |
| Commit-3 increment over commit 2 | — | `@@ -980,3 +980,72 @@` — **69 added, 0 removed** ✅ |

No duplicate Founder Decision heading was introduced (19 `FD-xxx` headings in
both blobs; repeat mentions of `FD-010` and similar are cross-references in
prose).

**Consequence for path counts.** The audit's targets counted this file once, in
the governance bucket. Splitting it necessarily places it in two commits, so
commit 3 measures **10 paths against a target of 9**. This is the arithmetic of
the split, not leakage — the other 9 paths of commit 3 match exactly. Recorded
under §14 ("if actual path counts differ, inspect the difference") rather than
forced to match.

## 5. Boundary decision — `verification/MASTER_PLAN.md` committed whole

Staged **whole** in commit 2, per §16. This is intentional.

| Section | Nature |
|---|---|
| §14 Architecture Resolution Round 1 — status overlay | governance / architecture |
| §15 ADR adoption baseline — status overlay | governance / architecture |
| §16 Phase 1 implementation readiness — overlay | **Phase 1 readiness planning** |

§16 is *planning* written during the 2026-09-08 governance session (file mtime
16:30, the same session as the readiness evidence), not Phase 1 implementation.
The Phase 1 **code** and its **execution evidence** remain in commit 5. Treating
all three sections as one governance/planning baseline keeps the file whole and
avoids a second hunk split for no verification benefit. No attempt was made to
split §16 out.

## 6. Not assigned to any commit

`verification/evidence/20260909_precommit_staging/` — this directory — is
meta-evidence *about* the five commits and is created after they are defined.
It is therefore not a member of any of the five scopes and remains untracked.
Whether it is committed alongside commit 5 or as a separate governance commit
is a **Founder decision**; §12 forbids inventing a sixth functional commit, so
no scope was created for it here.

## 7. Execution sequence, when a commit is authorized

Staging was verified one scope at a time from an empty index, using
`git read-tree HEAD` between scopes (index-only; it cannot move HEAD and does
not touch the working tree). **The index was left empty.**

```
1  git add -A verification/ledgers/ \
       verification/evidence/20260830_101236_inv_run_production \
       verification/evidence/20260830_101251_inv_run_production \
       verification/evidence/20260831_043518_replay_production \
       verification/evidence/20260831_043544_replay_production

2  git add verification/adr/ verification/MASTER_PLAN.md \
       verification/evidence/20260908_repo_identity_designation \
       verification/evidence/20260908_architecture_resolution_round1 \
       verification/evidence/20260908_phase1_implementation_readiness
   git add -p verification/FOUNDER_DECISIONS.md    # take file lines 868-982 ONLY

3  git add tools/restore_db.py tools/test_restore_db.py \
       verification/evidence/20260908_recovery_foundation
   git add -p verification/FOUNDER_DECISIONS.md    # take file lines 983-1051 (Round 2)

4  git add -A verification/masters/ \
       verification/evidence/20260908_golden_master \
       verification/evidence/20260909_005605_gm_capture_production \
       verification/evidence/20260909_005614_gm_verify_production \
       verification/evidence/20260909_005620_inv_run_production \
       verification/evidence/20260909_005622_replay_verify_production

5  git add app/cico_service.py app/night_audit_service.py app/noshow_service.py \
       app/pos.py app/reports.py app/routes.py app/seed.py app/services.py \
       verification/evidence/20260909_013001_inv_run_production \
       verification/evidence/20260909_013003_gm_verify_production \
       verification/evidence/20260909_013008_replay_verify_production \
       verification/evidence/20260909_013158_replay_verify_production \
       verification/evidence/20260909_013200_inv_run_production \
       verification/evidence/20260909_013202_gm_verify_production \
       verification/evidence/20260909_013458_replay_verify_production \
       verification/evidence/20260909_013500_inv_run_production \
       verification/evidence/20260909_013502_gm_verify_production \
       verification/evidence/20260909_phase1_execution \
       verification/evidence/20260909_w20_runtime
```

`git add -A` is required for scopes 1 and 4 because both contain tracked
deletions (28 May ledgers, 6 May report surfaces). Plain `git add` would stage
the additions and silently leave the deletions behind.

Per-commit gate — `git status --porcelain | wc -l` must fall:
**252 → 205 → 176 → 167 → (−183) → 0 changed paths + 1 untracked evidence dir.**
Any other number means a boundary leaked.

## 8. Limitations

1. **Staging/boundary audit only.** No `inv-run`, `gm-verify`, `replay-verify`
   or test suite was re-executed. The reproducibility argument in §3 is
   structural — derived from ledger and master contents — not a re-run.
2. **Scopes were verified independently**, each from an empty index against
   HEAD. A real sequential commit run would show commit 3's
   `FOUNDER_DECISIONS.md` diff as 69 lines; verified here as the blob-to-blob
   increment `ab3e3aed…` → `8a5a3656…`.
3. **No commit was created**, so no commit hash, tree hash or message is
   recorded and none was validated.
4. **`SECRET_KEY` rotation was not performed** and is not required by this
   finding; see `SECRET_REMEDIATION.md` §1.
