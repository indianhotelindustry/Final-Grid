# FinalGrid — Dual-Instance Identity Verification & Authoritative Path Designation

**Directive:** FG-GOV-20260908-01
**Verified:** 2026-09-08 09:05:55 +0530
**Kind:** Governance / evidence. Read-only verification. No implementation.
**Verdict:** the two repository copies were **identical** at verification time.

---

## 1. What was verified and why

Two filesystem copies of the FinalGrid repository were found to exist side by
side, each a complete Git repository with its own copy of the production
database at the frozen anchor. Neither recorded which was authoritative, and
both carry the same `origin`, so either could push. This record establishes
that they were identical at the moment of designation, and fixes the
authoritative path.

| Role | Path |
|---|---|
| **Authoritative working repository** | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` |
| **Preserved legacy / evidence duplicate** | `C:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS` |

---

## 2. Identity, side by side

| Dimension | Authoritative | Legacy | Match |
|---|---|---|---|
| Git repository | yes, `.git` directory at root | yes, `.git` directory at root | ✅ |
| Branch | `main` | `main` | ✅ |
| HEAD SHA | `237db2ad0fa8df143f04aaca82441f0f54781969` | `237db2ad0fa8df143f04aaca82441f0f54781969` | ✅ |
| Origin | `https://github.com/indianhotelindustry/Final-Grid.git` | same | ✅ |
| Refs (6) | `main`, `phase-2a-folio-authz`, `origin/main` all at `237db2a`; 3 tags | identical | ✅ |
| Tags | `v2.2.18-preWave1`, `v2.2.18-wave0.5`, `v2.2.18-wave0.5-frozen` | identical | ✅ |
| Reflog | 54 lines, SHA-256 `412d4ab3788d2b27cd92cf2bf3fbfeefe1ed9020f8763faaec6adf77295691e5` | identical SHA-256 | ✅ |
| Working-tree status | 46 entries — 28 `D`, 1 `M`, 17 `??` | 46 entries — 28 `D`, 1 `M`, 17 `??` | ✅ |
| Tracked index | 920 entries, manifest SHA-256 `fcc96b86bf47566e8cb721d49524437021dd5a3bc4a3d1eab5779b857ea2ee53` | identical | ✅ |
| Working-tree content | 1,989 files, manifest SHA-256 `ee97d3ab10dd1f8f542da2b42ee4805c1aa28870ca0d2b60c0a9d7325c2e8618` | identical | ✅ |
| `version.txt` | `2.2.18` | `2.2.18` | ✅ |
| Database size | 733,184 bytes | 733,184 bytes | ✅ |
| Database SHA-256 | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` | identical | ✅ |
| HEAD vs `origin/main` | 0 behind, 0 ahead | 0 behind, 0 ahead | ✅ |

**Remote agrees.** `git ls-remote origin` returned
`237db2ad0fa8df143f04aaca82441f0f54781969` for both `HEAD` and
`refs/heads/main` — the GitHub remote is at the same commit as both copies.

**Content-manifest method.** The 1,989-file manifest is the SHA-256 of every
regular file under each repository root, excluding `.git/`, `venv/`,
`__pycache__/`, `*.pyc` and `logs/`. Both manifests hash to the same value,
so every tracked file, every untracked file and the production database are
byte-identical between the two copies. Git internals were compared separately
via refs, reflog and the tracked index manifest.

---

## 3. Working-tree state — 46 entries, preserved

The dirty state is intentional evidence and was **not** cleaned, reset,
restored or regenerated.

| Group | Count |
|---|---|
| Deleted May ledger files, `2026-05-01` … `2026-05-28` | 28 |
| Modified `verification/ledgers/production/index.json` (May basis → August basis) | 1 |
| `_audit_stage_src.tgz` | 1 |
| `package-lock.json` | 1 |
| Untracked August evidence directories (2 × `inv_run`, 2 × `replay`) | 4 |
| Untracked August ledger dates, `2026-08-01` … `2026-08-10` | 10 |
| `verification/FOUNDER_DECISIONS.md` | 1 |
| **Total** | **46** |

The 46th entry relative to the 45-entry state at the 2026-08-31 checkpoint is
`verification/FOUNDER_DECISIONS.md`, created 2026-09-05 under the D11 ruling
directive. It was the only file in the repository modified after 2026-09-01.

---

## 4. Relationship to the Phase 2a checkpoint and evidence chain

This record **extends** the existing evidence chain. It does not replace or
rewrite any part of it.

| Item | State at this verification |
|---|---|
| Checkpoint commit | `237db2ad0fa8df143f04aaca82441f0f54781969` — *FinalGrid checkpoint: rebrand and Phase 2a authorization hardening*, tree `2f42277615b092d1b1ac1074b4d0aa63a3b80b2e`, authored 2026-08-31T21:49:00+05:30 |
| Commits after the checkpoint | **0** — HEAD *is* the checkpoint |
| History rewritten or rebased | **No** — reflog byte-identical across both copies, object pack identical |
| `app/folio.py` | unchanged from the checkpoint (`git diff` against `237db2a` empty) |
| `verification/evidence/20260831_phase2a_folio_authz/` | unchanged — `COMPLETION_REPORT.md`, `result.json`, `verify.py`, all matching their committed blobs |
| Phase 2a verdict | `PASS`, 29 of 29 negative-authorization cases, `anchor_matches: true` |
| Frozen anchor | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` — unchanged since Phase 2a recorded it |

### Historical path recorded in Phase 2a is preserved

`20260831_phase2a_folio_authz/result.json` records `production_db` as
`C:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS\instance\pms.db` —
the **legacy** path, because that is where Phase 2a was executed on
2026-08-31. That is correct as history. It has **not** been edited to match
the new designation. Future evidence will name the authoritative path; the
difference is explained here and in `verification/FOUNDER_DECISIONS.md`, not
by rewriting the earlier record.

---

## 5. D11-F2 population — reconfirmed untouched

Read read-only through an `immutable=1` SQLite connection. The database
SHA-256 was taken before and after the read and was identical, so the
verification itself did not modify the file.

| Table | Rows with `folio_id IS NULL` | Amounts |
|---|---|---|
| `payments` | ids 1, 2, 3, 4, 5, 6 | 800.00, 400.00, 1500.00, 1000.00, 500.00, 100.00 |
| `extra_charges` | ids 1, 2 | 380.95, 95.24 |

**8 rows, total 4,776.19** — exactly the population named in the D11-F2
ruling and frozen by identity in Phase 2a case T29. Untouched.

---

## 6. Legacy copy was not modified

The legacy repository was inspected **read-only only**. Its pre-directive
state was fingerprinted before any write occurred anywhere, and re-verified
after the governance edits:

| Fingerprint | Value |
|---|---|
| Content manifest, 1,989 files | `ee97d3ab10dd1f8f542da2b42ee4805c1aa28870ca0d2b60c0a9d7325c2e8618` |
| `.git/logs/HEAD` | `412d4ab3788d2b27cd92cf2bf3fbfeefe1ed9020f8763faaec6adf77295691e5` |
| `.git/index` | `e914f6e86618ef38a537b5937d653b68ddba4449867ab248f25f68d88b22b380` |
| `git show-ref` output | `38a448156671c5abe2709fa9a534eebec7ef93ef3efc781c3d65047790158812` |

No branch was checked out, no file written, no database touched, no Git
metadata altered, no commit made in the legacy copy.

---

## 7. Conclusion

1. The two copies were **identical** at 2026-09-08 09:05:55 +0530 — same
   history, same refs, same reflog, same working tree, same database, byte
   for byte.
2. `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` is designated the
   **authoritative** FinalGrid working repository.
3. `C:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS` is preserved as a
   **legacy / evidence duplicate** and was not modified. It must not be
   modified without a separately authorized neutralization or archive action.
4. All future FinalGrid work occurs in the authoritative copy only.
5. This designation is governance. **It authorizes no application
   implementation, schema change, data migration, Phase 0.2, Phase 1 or
   Phase 2b.**
6. No commit and no push was made under this directive. The governance
   changes remain reviewable as working-tree changes.
