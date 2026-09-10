# FinalGrid - Final Verification (after Commit 5)

Directive FG-COMMIT-EXECUTION-20260909-01 - verified 2026-09-09 after `aa6d9e91e7294be731383f755d6998acf5f059fc`.

| # | Directive check | Result | Evidence |
|---|---|---|---|
| 1 | Record final HEAD | PASS | `aa6d9e91e7294be731383f755d6998acf5f059fc` on `main` |
| 2 | Five new commits in chronological order | PASS | d15d848e (17:19:10) -> 34307c37 (17:20:16) -> 6cd2ac6d (17:21:07) -> 95083995 (17:21:31) -> aa6d9e91 (17:21:55) |
| 3 | Parent/child relationships | PASS | each commit has exactly one parent; chain e69f2ac2 -> d15d848e -> 34307c37 -> 6cd2ac6d -> 95083995 -> aa6d9e91 |
| 4 | `origin/main` has NOT moved | PASS | `origin/main` = `e69f2ac242f7fdc3e0c042ceb40dc0393280134b`; its reflog top entry predates this session |
| 5 | Unpushed count | PASS (expected local-ahead) | `origin/main...HEAD` = 0 behind / **5 ahead**. Origin was not advanced, so 5 unpushed commits is the expected and correct state |
| 6 | Working tree status | PASS | `git status --porcelain` = 0 entries (before this evidence dir was created); `-uall` = 0 |
| 7 | Index empty | PASS | `git diff --cached --name-only` = 0 |
| 8 | No unintended paths remain | PASS | `git diff HEAD` = 0; all 312 dirty paths from the staging baseline are now tracked; `.env` and `instance/pms.db` untracked and ignored; `app/folio.py` untouched in all five commits; tracked `.pyc`/`__pycache__`/`.env`/`.tgz`/`.db` in HEAD tree = 0 |
| 9 | Production DB SHA-256 | PASS | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` |
| 10 | Production DB size | PASS | 733,184 bytes; mtime 2026-08-31 11:53:14 IST (predates session); no -wal/-shm/-journal sidecars |
| 11 | D11 rows | PASS | payments 1-6 = 800, 400, 1500, 1000, 500, 100; extra_charges 1-2 = 380.95, 95.24; total 4,776.19; identical across 7 readings (baseline, after each commit, final) |
| 12 | Schema unchanged | PASS | 144 sqlite_master objects; fingerprint `e38454ba3c4ad27f7d6ef24168aefd30facf21ba8c68a1feab461063f2390fb0` identical across 7 readings; integrity_check ok; audit_logs 23 unchanged |
| 13 | No push occurred | PASS | HEAD reflog shows 5 `commit:` entries and no push; `origin/main` reflog unchanged; no `git push` was executed |

## Path accounting

| Commit | Paths | Manifest match |
|---|---|---|
| d15d848e | 55 (47 + 8 precommit-staging) | identical |
| 34307c37 | 30 | identical |
| 6cd2ac6d | 10 | identical (10-vs-9 approved) |
| 95083995 | 184 | identical |
| aa6d9e91 | 34 | identical |
| Sum / distinct | 313 / 312 | FOUNDER_DECISIONS.md in commits 2 and 3 only |

## FOUNDER_DECISIONS.md split, as committed

| | Commit 2 (`34307c37`) | Commit 3 (`6cd2ac6d`) |
|---|---|---|
| Blob | `ab3e3aed640035a3094b9bcb4bd54e3234f63a5a` | `8a5a36569d29f19f09f4b386230437a3a96c5f99` |
| Lines | 982 | 1051 |
| Hunk vs parent | `@@ -865,3 +865,118 @@` (+115/-0) | `@@ -980,3 +980,72 @@` (+69/-0) |
| Founder Resolution Round 2 | 0 | 1 |
| `## Q-1` .. `## Q-6` | 0 each | 1 each |
| Architecture Resolution Round 1 / ADR Adoption Baseline | 1 / 1 | 1 / 1 (not duplicated) |
| FD-xxx headings | 19 | 19 |

## Integrity

`git fsck --no-dangling` exit 0, no output.

## Observations (not findings)

- Rename display: `git diff --cached --name-status` initially showed four `R091` rows in commit 1 (May->August ledger files with 91% similarity). With `--no-renames` the set matched the manifest exactly. Content is identical either way.
- Porcelain counts: the staging plan's `252 -> 205 -> ...` gate counted paths; `git status --porcelain` collapses untracked dirs. Per-file counts (`-uall`) were 312 -> 257 -> 228 -> 218 -> 34 -> 0, matching each scope exactly.
- `installer/update_pubkey.pem`: pre-existing tracked public key (since `b5b2514`, 2026-08-07); not touched by the five commits; outside this directive.

## Raw output

```
FINAL HEAD: aa6d9e91e7294be731383f755d6998acf5f059fc
branch: main

--- five new commits, chronological (oldest first) ---
d15d848e2694adbe2560aabd359a9f9c85fdb6d2 e69f2ac242f7fdc3e0c042ceb40dc0393280134b 2026-09-09 17:19:10 +0530 FinalGrid: recapture production ledger baseline
34307c37858991c21ec2a13d995db8416819bf69 d15d848e2694adbe2560aabd359a9f9c85fdb6d2 2026-09-09 17:20:16 +0530 FinalGrid governance: adopt architecture baseline
6cd2ac6d2f90c59cae5070236d614c717659bc04 34307c37858991c21ec2a13d995db8416819bf69 2026-09-09 17:21:07 +0530 FinalGrid: establish recovery foundation
9508399500be7d5051ddd4a73b0d53b12ac59d40 6cd2ac6d2f90c59cae5070236d614c717659bc04 2026-09-09 17:21:31 +0530 FinalGrid: freeze Phase 1 golden master
aa6d9e91e7294be731383f755d6998acf5f059fc 9508399500be7d5051ddd4a73b0d53b12ac59d40 2026-09-09 17:21:55 +0530 FinalGrid: implement Phase 1 financial foundation

--- chain check ---
commit 1 d15d848e2694adbe2560aabd359a9f9c85fdb6d2 parent=e69f2ac242f7fdc3e0c042ceb40dc0393280134b expected=e69f2ac242f7fdc3e0c042ceb40dc0393280134b OK parents=1
commit 2 34307c37858991c21ec2a13d995db8416819bf69 parent=d15d848e2694adbe2560aabd359a9f9c85fdb6d2 expected=d15d848e2694adbe2560aabd359a9f9c85fdb6d2 OK parents=1
commit 3 6cd2ac6d2f90c59cae5070236d614c717659bc04 parent=34307c37858991c21ec2a13d995db8416819bf69 expected=34307c37858991c21ec2a13d995db8416819bf69 OK parents=1
commit 4 9508399500be7d5051ddd4a73b0d53b12ac59d40 parent=6cd2ac6d2f90c59cae5070236d614c717659bc04 expected=6cd2ac6d2f90c59cae5070236d614c717659bc04 OK parents=1
commit 5 aa6d9e91e7294be731383f755d6998acf5f059fc parent=9508399500be7d5051ddd4a73b0d53b12ac59d40 expected=9508399500be7d5051ddd4a73b0d53b12ac59d40 OK parents=1
new commit count: 5 (expect 5)

--- origin ---
origin/main: e69f2ac242f7fdc3e0c042ceb40dc0393280134b (expect e69f2ac2... unmoved)
ahead/behind (origin/main...HEAD): 0	5  (expect 0 5)
unpushed (origin/main..HEAD): 5
packed/loose ref origin/main: e69f2ac242f7fdc3e0c042ceb40dc0393280134b
origin/main reflog (last 3):
e69f2ac refs/remotes/origin/main@{0}: update by push
237db2a refs/remotes/origin/main@{1}: update by push
push in HEAD reflog: 0 (expect 0)
HEAD reflog (last 6):
aa6d9e9 HEAD@{0}: commit: FinalGrid: implement Phase 1 financial foundation
9508399 HEAD@{1}: commit: FinalGrid: freeze Phase 1 golden master
6cd2ac6 HEAD@{2}: commit: FinalGrid: establish recovery foundation
34307c3 HEAD@{3}: commit: FinalGrid governance: adopt architecture baseline
d15d848 HEAD@{4}: commit: FinalGrid: recapture production ledger baseline
e69f2ac HEAD@{5}: commit: FinalGrid governance: record Founder Resolution Round 1

--- working tree / index ---
porcelain entries: 0 (expect 0)
porcelain -uall: 0 (expect 0)
index staged: 0 (expect 0)
worktree vs HEAD: 0 (expect 0)
ignored-but-present sensitive files (must remain untracked):
  .env exists=yes tracked=no
  instance/pms.db exists=yes tracked=no
tracked junk in HEAD tree: 1 (expect 0)
app/folio.py changed in new commits: 0 (expect 0)

--- path accounting ---
  d15d848: 55
  34307c3: 30
  6cd2ac6: 10
  9508399: 184
  aa6d9e9: 34
  sum: 313 (expect 55+30+10+184+34=313)
  distinct paths touched: 312 (expect 304+8=312)
  FOUNDER_DECISIONS.md appears in: 6cd2ac6 34307c3  (expect 2 commits)

--- fsck ---
fsck exit: 0
```

### Final DB reading
```json
{
 "sha256": "51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2",
 "sha_ok": true,
 "size": 733184,
 "size_ok": true,
 "d11_payment_ids": [
  1,
  2,
  3,
  4,
  5,
  6
 ],
 "d11_payment_amounts": {
  "1": 800.0,
  "2": 400.0,
  "3": 1500.0,
  "4": 1000.0,
  "5": 500.0,
  "6": 100.0
 },
 "d11_charge_ids": [
  1,
  2
 ],
 "d11_charge_amounts": {
  "1": 380.95,
  "2": 95.24
 },
 "d11_total": 4776.19,
 "d11_total_ok": true,
 "schema_objects": 144,
 "schema_fingerprint": "e38454ba3c4ad27f7d6ef24168aefd30facf21ba8c68a1feab461063f2390fb0",
 "integrity": "ok",
 "audit_logs": 23
}
```
