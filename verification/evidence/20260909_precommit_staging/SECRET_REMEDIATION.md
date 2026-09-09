# Secret Remediation — `_audit_stage_src.tgz`

| | |
|---|---|
| Directive | FG-PRECOMMIT-STAGE-20260909-01 §4, §5 |
| Executed | 2026-09-09 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` — unchanged; no commit, no push |
| Result | **REMEDIATED — both artifacts deleted, neither ever entered Git history** |

> **No secret value is recorded in this file, in any manifest, in `result.json`,
> or in any other artifact of this directive.** Only the fact of exposure, the
> identifier name, and the container's hash are recorded.

## 1. `_audit_stage_src.tgz` — credential-bearing archive

| Property | Value |
|---|---|
| Path | `_audit_stage_src.tgz` (repository root) |
| Size | 5,052,054 B |
| SHA-256 | `45f3ac2dd187e740b7517b486362c1e50b405eb55f1dd0e29e4372f51ea6a453` |
| mtime | 2026-08-29 07:01:54 |
| Git status before deletion | **untracked** (never staged, never committed) |
| Entries | 1,097 |
| Contains `./.env` | **yes** |
| Assignments in that `.env` | 4, one of which is `SECRET_KEY` (**value not recorded here**) |
| Contains `*.db` / `*.db.enc` / `instance/` / `backups/` | **no** (0 matches) |

### Why it was unsafe

`.env` is excluded from version control by `.gitignore:22`. The tarball is a
snapshot of the source tree that **contains `.env` inside an archive**, so the
ignore rule does not apply to it: staging the tarball would have written the
application's `SECRET_KEY` into permanent Git history in a form no `.gitignore`
protects and no later commit can remove.

The exposure is material beyond session signing: `SECRET_KEY` is a fallback
input to the HKDF derivation that encrypts application backups
(`app/backup_manager.py`; see `tools/restore_db.py:242`). A leaked
`SECRET_KEY` is therefore also a backup-decryption key.

**Scope limit — no encrypted backup is at risk through Git.** `backups/` is
ignored (`.gitignore:41`) and holds **0 tracked files**, so no `.db.enc`
artifact exists in the repository for a leaked key to decrypt. This is
credential exposure, not data exposure.

### Action taken

Deleted from the working tree. Deletion was explicitly authorized by §4.

### Verification after deletion

| Check | Result |
|---|---|
| File exists in working tree | **no** |
| Any `*_audit_stage_src*` anywhere in the tree (excl. `venv/`, `python/`) | **0** |
| Present in the Git index | **0** |
| Present in `HEAD` tree | **0** |
| Present anywhere in Git history (`git log --all`) | **0** |
| Present in any of the five prepared commit scopes | **0** |

Because the artifact was never tracked, **no history rewrite is required**. No
`filter-branch`, no BFG, no force-push. Nothing was ever pushed.

### Key rotation — NOT performed, and NOT required by this directive

The `SECRET_KEY` was exposed only on the local filesystem inside an untracked
archive that never reached Git or `origin`. Rotation is therefore **not**
mandated by this finding and was **not** performed (it would alter application
configuration, which §2 forbids). If the tarball was ever copied off this
machine, transmitted, or placed in shared storage, rotation becomes necessary —
that is a Founder determination, recorded here as an open question, not a
completed action.

## 2. `.env` itself — deliberately preserved

Per §4, the finding concerns the **tarball**, not `.env`. The application's own
`.env` was **not** deleted, moved, or modified.

| Check | Result |
|---|---|
| `.env` exists | **yes** |
| `.env` ignored by Git | **yes** (`.gitignore:22`) |
| `.env` tracked | **no** |
| `.env` in any of the five commit scopes | **no** |

## 3. `package-lock.json` — junk, non-secret

| Property | Value |
|---|---|
| Size | 88 B |
| SHA-256 | `176163bec3190b132213479511541702fdccdfc4053e03cc0b7fecae700bba0a` |
| mtime | 2026-08-30 11:47:16 |
| Git status before deletion | **untracked** |
| Content | 6-line stub, `"packages": {}` — no dependencies |
| Corresponding `package.json` | **absent** |

Stray `npm install` residue, unrelated to FinalGrid (a Python/Flask
application). Deleted under §5. Verified absent from the working tree, the
index, `HEAD`, and all history. Not replaced.

## 4. Secret scan of the five prepared commit scopes (§17)

270 distinct files enter the five commits. All were scanned.

| Check | Result |
|---|---|
| `.env` files in scope | **0** |
| Archives (`.tgz .tar .zip .gz .7z .rar`) in scope | **0** |
| Key material (`.pem .key .pfx .p12 .jks .asc .ppk`) in scope | **0** |
| Database files (`.db`, `.db.enc`) in scope | **0** |
| `BEGIN … PRIVATE KEY` blocks | **0** |
| Assigned secret values (`SECRET_KEY=…`, `PASSWORD=…`, `API_KEY=…`, `TOKEN=…`, `AWS_SECRET_ACCESS_KEY=…`) | **0** |

Seven files mention the **identifier** `SECRET_KEY` with no value attached.
Per §17 these are not credential leaks:

| File | Nature of reference |
|---|---|
| `tools/restore_db.py:242,245` | `os.getenv('SECRET_KEY', '')` — environment lookup |
| `tools/test_restore_db.py:117,265` | test asserting `SECRET_KEY` is **absent** from the manifest |
| `verification/evidence/20260908_golden_master/gm_capture.log:22` | runtime WARNING that `PII_ENCRYPTION_KEY` is unset |
| `verification/evidence/20260908_golden_master/gm_verify.log:22` | same WARNING |
| `…/20260908_phase1_implementation_readiness/PHASE1_EXECUTION_PLAN.md:45` | prose, key-custody note |
| `…/20260908_phase1_implementation_readiness/RECOVERY_GATE_PLAN.md:23` | prose, HKDF derivation note |
| `…/20260908_recovery_foundation/IMPLEMENTATION_RECORD.md` | prose, key-custody note |

**No path was withheld from staging for secret reasons.** No STOP condition
under §17 was triggered.
