# Production guest phone number in git history

| | |
|---|---|
| Date | 2026-10-02 |
| Kind | Analysis and decision package only. Only read-only git commands were run: `log`, `show`, `grep`, `log -S`, `rev-list`, `merge-base --is-ancestor`, `branch -r --contains`, `for-each-ref`. Nothing was rewritten, redacted, committed or pushed. |
| Reference | `origin/main` = `c9eeff0`. The `overnight-20261002` branch moved to `0ae01bc` during this analysis; both were checked. |
| Masking | The value is written here only as `62xxxxxx95` (first two and last two of ten digits). No raw log line is reproduced. |

## 1. Facts

### 1.1 The value

- One 10-digit Indian mobile number, masked `62xxxxxx95`. It appears without a country code, as the destination in notification log lines: the WARNING "Notification failed [whatsapp → …] checkout_thanks: … not configured" (`app/notifications.py:196`) and the INFO "Queued whatsapp notification to … for retry" (`app/notifications.py:166`).
- It is identified as a **production guest** phone number by the commit message of `a131b86` and by `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:160,162`. This analysis did not open the production database, so the identification is taken from those records. Independent confirmation: **NOT VERIFIED**.
- Root cause, as recorded in `ADR011_DECISION_REQUIRED.md:160,163`: the W-24 checkout harness cases use the production copy's seed guest, the harnesses boot with the production `.env`, and the notification warning logs the destination. No messaging credentials are configured, so no message was sent (`a131b86` message).
- Search variants checked across all 90 reachable commits: digits with spaces or dashes, a `+91` prefix, and commit messages. None found beyond the plain 10-digit form.

### 1.2 Commits that introduced or removed it (`git log --all -S`)

| Commit | Date (+0530) | Subject | Effect |
|---|---|---|---|
| `d71a2fb759815c13b0f91ad179542bd0917f4844` | 2026-09-10 10:24:46 | FinalGrid governance: accept Phase 1 at aa6d9e91 | **Introduced.** `verification/evidence/20260909_phase1_verification_completion/writers_setA.txt`: 6 occurrences (lines 109, 110, 117, 118, 126, 127). `.../writers_setD.txt`: 4 occurrences (lines 31, 32, 39, 40). |
| `3efdd2b53337cc78208b7b2e5658367a66d8d7bf` | 2026-09-30 08:20:14 | FinalGrid: record CF-10 / CF-11 completion evidence | **Introduced again.** 42 occurrences in six logs: `20260930_cf10_completion/per_commit/harness_{5847920,c4edc7b,d34d15a}.log` and `regression_logs/harness_{base_683db72,base_d9fa55f,green_61286b7}.log`. Tree total 52. |
| `a131b86a9b1efb8c2432db22a7b08d5d55443a98` | 2026-09-30 08:50:26 | FinalGrid: redact a production guest identifier from CF-10 harness logs | **Forward-only redaction** of the 42 occurrences in the six logs (token replaced by `[REDACTED-PRODUCTION-GUEST-FIELD]`). It did **not** touch `writers_setA.txt` / `writers_setD.txt`. The message says so ("was already present in the 20260909_phase1_verification_completion pack"). |

The value occurs in eight paths across history: the two `writers_set*.txt` files, present in 34 commits each, and the six CF-10 harness logs, present in one commit each (`3efdd2b`).

### 1.3 Still present in the current tree? **YES**

- At `c9eeff0`: **10 occurrences in 2 files**: `verification/evidence/20260909_phase1_verification_completion/writers_setA.txt` (6) and `writers_setD.txt` (4).
- Same at `0ae01bc` and in the `C:/wtov` working tree.
- Earlier packs recorded that the number "remains in git history … and was already in `writers_setA.txt` and `writers_setD.txt`" (`ADR011_DECISION_REQUIRED.md:162`). None of them states that the number is still in the **current tree**. It is, because only the CF-10 copies were redacted.
- No committed evidence cites the SHA-256 of either file. Both files are named only in `ADR011_DECISION_REQUIRED.md`. A forward redaction therefore breaks no recorded file hash.

### 1.4 Reach

| Item | Value |
|---|---|
| Commits whose tree contains the value | 34 across all refs at the time of analysis: `d71a2fb` and every descendant. That is 32 in `c9eeff0`'s ancestry plus `419852a` and `0ae01bc` on `overnight-20261002`. |
| Remote branches containing `d71a2fb` and `3efdd2b` (`git branch -r --contains`) | `origin/main`, `origin/adr011-system-actor`, `origin/sr2-inv-d02`, `origin/overnight-20261002` (and `origin/HEAD`). That is **every** remote branch. |
| Local branches containing it | `main` (`c703150`, the branch checked out in the **live production install folder**), `adr011-system-actor`, `sr2-inv-d02`, `overnight-20261002`. Not `phase-2a-folio-authz` (`237db2a`). |
| Tags | none (`git tag --contains d71a2fb` is empty; the three `v2.2.18-*` tags predate it) |
| Worktrees sharing this object store (`git worktree list`) | `C:/Users/SIPL Server/Downloads/DSS/FinalGrid/SukoonPMS` (production, `main` @ `c703150`), `C:/wtov`, `C:/wtsr2` |
| Remote | `origin` = GitHub `indianhotelindustry/Final-Grid`. Repository visibility, collaborators and forks: **NOT VERIFIED**. |
| Production working tree | Commit `c703150` contains both files. Whether they exist on disk in the production folder: **NOT VERIFIED** (folder not opened). |

### 1.5 Other phone-number-like values (masked)

Search: standalone 10-digit numbers starting 6–9, optionally with `+91`, not adjacent to letters or digits. This excludes the hex fragments of SHA hashes, which produce many false matches. All reachable commits were searched.

| Group | Distinct values | Where (at `c9eeff0`) | Assessment |
|---|---|---|---|
| `62xxxxxx95` | 1 | the two `writers_set*.txt` files | **production guest** (§1.1) |
| `9000xxxxxx` | 14 | `app/seed.py`, `app/dev_seed.py`, harness scripts, dataset registry results | synthetic patterns (runs of zeros) |
| `9711xxxxxx` | 15 | same kind of files | synthetic (`97111111` + sequence) |
| `9800xxxxxx` | 8 | same kind of files | synthetic (`980000000` + sequence) |
| `9811xxxxxx` | 8 | same kind of files | synthetic (`981100001` + sequence) |
| `9810xxxxxx`, `9820xxxxxx`, `9830xxxxxx` | 3 | same kind of files | synthetic (repeating blocks) |
| `99xxxxxx99` | 1 | `app/webhook.py:118` (payload example comment) and fixtures | synthetic (all nines) |
| **Total** | **50 distinct** (49 at `c9eeff0`; the history-only one is `90xxxxxx02`, synthetic) | | |

There is also one spaced placeholder, `+91 98xxx xxx10`, a well-known example number, at `app/templates/groups/new.html:79`.

The 49 non-guest values are classed as synthetic **by pattern only**. They were not compared against the production `guests` table: **NOT VERIFIED**. Later packs scanned their own logs against every production guest phone, email and name (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:79`; `CF10_COMPLETION.md:99`). The `20260909_phase1_verification_completion` pack has no such recorded scan. Whether it also holds a production guest **name or e-mail** is **NOT VERIFIED**.

### 1.6 Governance state

- Recorded as an open Founder item: `ADR011_DECISION_REQUIRED.md:162` ("Removing it from history needs a history rewrite and force-push, which no directive permits"), `ADR011_PRE_PRODUCTION_GATE_REPORT.md:130`, `ADR011_PRODUCTION_APPLICATION_REPORT.md:105`.
- `verification/FOUNDER_DECISIONS.md` contains no ruling on it.
- Precedent for the forward-only approach: `a131b86`. Precedent for "no history rewrite": `20260909_precommit_staging/SECRET_REMEDIATION.md:63` (no `filter-branch`, no BFG, no force-push), and `20260909_five_commit_execution/REMOTE_PUSH_VERIFICATION.md:39` ("No force push / no history rewrite").

## 2. Consequences of a history rewrite

A rewrite (e.g. `git filter-repo --replace-text`) that removes the value from `d71a2fb` onward has these consequences.

1. **Every commit hash from `d71a2fb` onward changes**: 32 commits in `origin/main` (`d71a2fb` … `c9eeff0`), plus the branch-only commits. Commits before `d71a2fb` keep their hashes, including the Phase 1 baseline `aa6d9e91`, `e69f2ac` and the tags.
2. **Evidence that cites those hashes would point at commits that no longer exist.**
   - At `c9eeff0`, 185 tracked files contain the 7-character prefix of at least one affected commit (prefix match, so approximate): 130 JSON and 25 Markdown files, across 16 evidence packs.
   - These include the `RESULT.json` of `20260930_cf10_completion`, `20260930_adr011_implementation`, `20260930_adr011_preprod_gate`, `20260930_adr011_production_application`, `20260930_adr011_system_action_provenance`, `20260930_sr2_inv_d02`, `20260923_q06_*` and `20260910_retention_control`. They also include the per-commit result files named after tested commits, e.g. `results_commit_5847920_*.json`, `results_base_683db72_*.json`, `results_green_61286b7_*.json` and `results_3ffeba5*.json`.
   - `verification/FOUNDER_DECISIONS.md` cites affected commits as "Governed HEAD": `a84566a` (`:1119`), `b0d3054` (`:1213`), `cfec0c8` (`:1261`), `c703150` (`:1297`, `:1328`).
   - The tested-commit identity of those packs would no longer be checkable with `git show <hash>`, unless an old→new commit map is kept and cited. Keeping the old objects to preserve that check keeps the value too.
3. **Force-push required** to `origin/main`, `origin/adr011-system-actor`, `origin/sr2-inv-d02` and `origin/overnight-20261002`, which is every remote branch. No directive permits this (`ADR011_DECISION_REQUIRED.md:162`).
4. **Every clone and worktree must be re-cloned**, or hard-reset and expired/garbage-collected.
   - The **production install folder** is one of them (`main` @ `c703150`; the preprod gate report says this folder "*is* the production install", `ADR011_PRE_PRODUCTION_GATE_REPORT.md:114`). Touching its `.git` is an act in the live folder that needs its own authorization.
   - `C:/wtov` and `C:/wtsr2` are also affected. Any other clone (other machines, CI, collaborators) is unknown: **NOT VERIFIED**.
   - A clone that is not reset will reintroduce the old history on its next push.
5. **Old objects stay reachable outside our control.** That includes existing clones and forks, reflogs, and the hosting provider's caches and pull-request refs. Removing them from the host normally needs the provider's sensitive-data process. That is general practice; it has **NOT** been checked for this repository.
6. **The current tree must still be redacted.** A rewrite alone would remove the value from `writers_setA.txt` / `writers_setD.txt` in every commit, so the current files change too. The evidence text that describes those logs stays valid. The logs themselves would differ from what was originally recorded.
7. **Concurrent work.** Overnight branches are being committed and pushed while this is written (`419852a`, `0ae01bc`). A rewrite needs every writer stopped and re-based onto the new history.

## 3. Alternative: forward-only removal from the current tree

- A new commit replaces the 10 occurrences in `writers_setA.txt` / `writers_setD.txt` with `[REDACTED-PRODUCTION-GUEST-FIELD]`, token-only, following the `a131b86` precedent.
- No hash changes, no force-push, no re-clone. All evidence citations stay valid. No committed evidence records the SHA-256 of these two files (§1.3).
- **Residual:** the value stays in history (34 commits on all four remote branches, plus `3efdd2b`'s six logs), on `origin`, and in every clone. Anyone with read access to the repository can recover it with `git log -p`.

## 4. Decisions

### GH-D1 — Remediation approach

- **DECISION ID:** GH-D1
- **DATE DISCOVERED:** 2026-10-02. The underlying item has been open since 2026-09-30 (`ADR011_DECISION_REQUIRED.md:162`). This analysis newly establishes that the value is still in the current tree.
- **WORKSTREAM:** privacy / repository hygiene (ADR-011 carry-over "guest data in git history")
- **QUESTION:** How is the production guest phone number (`62xxxxxx95`) to be handled? It is in the current tree (2 files, 10 occurrences) and in history (34 commits, all remote branches).
- **WHY REQUIRED:** It is personal data of a real guest in a remote repository. Removing it from history breaks the commit-hash anchoring of most evidence since 2026-09-10 and needs a force-push. No directive permits either.
- **OPTIONS:**
  - (A) **Forward-only now.** Redact the two remaining files in a new commit and push normally. Record the residual history exposure as an accepted risk.
  - (B) **Forward-only now, rewrite later.** (A) now, then a planned rewrite window under a separate authorization (GH-D2). The window could come, for example, before any widening of repository access or before G12.
  - (C) **Rewrite now.** Rewrite history from `d71a2fb`, force-push all four remote branches, re-clone every clone including the production folder, and re-anchor evidence (GH-D2).
  - (D) **No action.** Record the exposure as accepted, leaving the value in the current tree.
- **EVIDENCE:** §1 and §2 of this file. Commits `d71a2fb`, `3efdd2b`, `a131b86`. `ADR011_DECISION_REQUIRED.md:160-163`.
- **DEPENDENCIES:**
  - Repository visibility and access list on GitHub (**NOT VERIFIED**; the Founder knows this).
  - Any legal or notification obligation towards the guest. That is outside this analysis and is not assessed here.
  - For (B)/(C): GH-D2. For (C): authorization to act on the production folder's `.git`.
- **WHAT IS BLOCKED:** closure of the "guest data in git history" carry-over (`ADR011_PRODUCTION_APPLICATION_REPORT.md:105`).
- **WHAT CAN CONTINUE:** all engineering and verification work. Under (C), all committing and pushing must stop for the rewrite window.
- **EXACT ACTION AFTER DECISION:**
  - (A)/(B): one commit that replaces the 10 occurrences token-only and changes no other byte, with a `git diff --stat` / `git grep` proof of 0 occurrences recorded in an evidence note; normal push.
  - (C): see GH-D2.
  - (D): record the acceptance in `FOUNDER_DECISIONS.md`.

### GH-D2 — Conditions for a history rewrite (only if GH-D1 = B or C)

- **DECISION ID:** GH-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** repository governance / evidence integrity
- **QUESTION:** If history is rewritten, how is evidence anchoring preserved, and which repositories and folders may be touched?
- **WHY REQUIRED:** 185 tracked files and five "Governed HEAD" entries in `FOUNDER_DECISIONS.md` cite affected hashes (§2.2). The production install folder is a worktree of this repository (§1.4).
- **OPTIONS:**
  - (a) Keep the commit map from the rewrite tool (old→new, no content) as a committed evidence file. Each pack stays checkable through the map, and the packs are not edited.
  - (b) As (a), plus an addendum to `FOUNDER_DECISIONS.md` and each affected pack's README naming the new hashes.
  - (c) Re-run verification at the new hashes. This is costly and not needed for content, because only the redacted logs change.
  - Production folder: (i) re-clone it under a PD-004-style authorization in a controlled window, or (ii) leave it until the next governed deployment (G11), accepting that its local history keeps the value.
- **EVIDENCE:** §2.
- **DEPENDENCIES:** GH-D1 = B or C. All concurrent sessions stopped. Force-push authorization.
- **WHAT IS BLOCKED:** a rewrite cannot be planned without this.
- **WHAT CAN CONTINUE:** everything until the window.
- **EXACT ACTION AFTER DECISION:** write a rewrite runbook (freeze, mirror backup kept offline under custody, rewrite, verify with `git grep` of 0 occurrences across `rev-list --all`, force-push, re-clone each listed worktree, commit the map plus addendum), then execute it only within the authorized window.

### GH-D3 — Preventing recurrence (harness privacy)

- **DECISION ID:** GH-D3
- **DATE DISCOVERED:** 2026-10-02. First recorded 2026-09-30 (`ADR011_DECISION_REQUIRED.md:163`).
- **WORKSTREAM:** verification tooling
- **QUESTION:** Which control is required so that harness runs cannot write production guest data into committed evidence again?
- **WHY REQUIRED:** The leak came from harnesses that boot with the production `.env` and reuse production guests, combined with notification logging of destinations (`notifications.py:166,196`). The same mechanism leaked twice (`d71a2fb`, `3efdd2b`). If messaging credentials are ever configured, test runs would message real guests (`ADR011_DECISION_REQUIRED.md:163`).
- **OPTIONS:**
  - (a) Harnesses use synthetic guests and stub notifications. This is a verification-tooling change.
  - (b) A mandatory pre-commit scan of evidence packs against production guest fields, with a recorded result. This is a process change.
  - (c) Both (a) and (b).
  - (d) Mask destinations in the application's notification log lines. This is an `app/` change and would need its own directive.
- **EVIDENCE:** §1.1; `20260930_adr011_implementation/ADR011_REGRESSION.md:55` (36 occurrences redacted before commit in another pack); `ADR011_PRE_PRODUCTION_GATE_REPORT.md:79`.
- **DEPENDENCIES:** none. WH-D5 depends on it.
- **WHAT IS BLOCKED:** safe runtime verification on production copies (WH-D5 and similar).
- **WHAT CAN CONTINUE:** static analysis and governance work.
- **EXACT ACTION AFTER DECISION:** issue a bounded verification-tooling directive for the chosen option(s), with red/green proof that a seeded production-like phone does not reach any committed log.
