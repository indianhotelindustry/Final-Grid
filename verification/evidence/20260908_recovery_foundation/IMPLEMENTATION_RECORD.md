# Recovery Foundation — Implementation Record

| | |
|---|---|
| Directive | FG-P1-RECOVERY-FOUNDATION-20260908-01 (Founder Resolution Round 2 + bounded Recovery Foundation) |
| Recorded | 2026-09-08 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` — unchanged; **no commit, no push** |
| Authorizes | Recovery infrastructure only (Q-6). **No Phase 1 financial implementation.** |
| Architecture | ADR-007 Backup / Restore Architecture (ADOPTED 2026-09-08); PD-006 Restore Verification (FD-005) |

## 1. Scope

Implement the restore half of the adopted recovery architecture and rehearse it once, in isolation, against a real backup artifact, without touching `instance/pms.db`, any financial row, any schema, or any application code.

## 2. Files changed — exact

| File | Action | Size | SHA-256 (prefix) |
|---|---|---|---|
| `tools/restore_db.py` | **created** | 25,024 B | `1399dc01eba93a80…` |
| `tools/test_restore_db.py` | **created** | 13,420 B | `ee66cdbb25d24a61…` |
| `verification/evidence/20260908_recovery_foundation/` | **created** — this record, `RESTORE_REHEARSAL.md`, `restore_manifest.json`, `backup_manifest.json`, `production_snapshot_byte_diff.json`, `test_results.txt`, `result.json` | — | — |
| `verification/FOUNDER_DECISIONS.md` | **appended** — Founder Resolution Round 2 (Q-1…Q-6) | — | — |
| `tools/backup_db.py` | **unchanged** (`7dac61481905c4cd…`) — it already supplies API backup, `mode=ro` source, before/after hashes, `integrity_check`, row counts and a manifest; nothing needed rewriting | 7,222 B | unchanged |

Outside the repository, by the backup tool's design: `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\db-backups\pms_20260908_193942_recovery_rehearsal.db` (+ `.manifest.json`). Restored file: session scratch directory (isolated, temporary).

**Not touched:** `app/`, `migrations/`, `app/templates/`, `app/static/`, `instance/`, launchers, scheduler, authorization, financial writers, D11 rows, audit rows.

## 3. Design of `tools/restore_db.py`

| Requirement (§6) | Implementation |
|---|---|
| 1 explicit backup artifact | `--source` required; `.db` or `.db.enc` |
| 2 explicit isolated destination | `--dest` required; no default |
| 3 refuse unsafe combinations | Refuses: missing/empty source; source without SQLite header; production DB as source; destination equal to source; destination that is a directory; destination that already exists (unless `--overwrite-dest`, which still cannot name production) |
| 4 never overwrite production by default | `is_production_path()` — destination resolving (realpath, case-insensitive) to `instance/pms.db` or anywhere under `instance/` is refused **before any file is touched; no flag overrides it** |
| 5 verify backup before restoring | SQLite header; SHA-256; agreement with `<source>.manifest.json` (`snapshot_sha256`) when present; `PRAGMA integrity_check` on the read-only source — any failure aborts before restore |
| 6 integrity after restore | `PRAGMA integrity_check` on the restored file (read-only connection) |
| 7 hash of restored artifact | SHA-256 |
| 8 record source and restored hashes | manifest fields `source_sha256`, `restored_sha256` (+ `source_sha256_encrypted` for `.enc`) |
| 9 row counts | every table, source vs restored; key financial tables reported explicitly; "invoices" evaluated as `reservations.invoice_number IS NOT NULL` (no `invoices` table exists) |
| 10 verification results | 16 named checks with ok/detail |
| 11 machine-readable manifest | written beside the destination and, with `--evidence-dir`, into the evidence directory; written on failure as well |
| 12 non-zero on failure | exit 0 pass · 1 verification failure · 2 refusal/usage |

Additional verification beyond the minimum: `PRAGMA foreign_key_check` with `foreign_keys=ON`; required-table presence (11 tables); `sqlite_master` readable; **schema SQL equality** source vs restored; **content digests** (SHA-256 over ordered rows) for **every** table; **byte comparison beyond the 100-byte header** (must be zero differing bytes; sizes equal).

**Whole-file hash is informational, not pass/fail.** SQLite's backup API rewrites file-header bookkeeping (file change counter, schema cookie, version-valid-for) on the destination, so a faithful page copy can hash differently from its source. The tool records the exact differing header offsets and fails on any difference beyond offset 100. This was discovered by the tests, not assumed.

Restore mechanics: source opened `mode=ro`; `sqlite3` backup API into a temporary file inside a scratch directory next to the destination; atomic `os.replace`; scratch directory removed. Encrypted application backups (`*.enc`) are decrypted in memory using the same HKDF/Fernet derivation as `app/backup_manager.py` (duplicated locally so the tool never imports the application package); key material is read from `PII_ENCRYPTION_KEY`/`SECRET_KEY` only and never logged or written.

## 4. Safety controls

- Production path refusal is structural (path normalisation), not advisory.
- Production is never opened by the restore tool; the only production read in this slice was `tools/backup_db.py`'s `mode=ro` connection, whose own before/after hash check proved production unchanged.
- The application is **not** booted (§9 of the directive): `create_app()` runs `_run_pending_migrations`, `init_data()` and starts the scheduler.
- No secrets in any manifest or evidence file (asserted by a test).
- Failure writes a FAIL manifest and exits non-zero; verification criteria were not weakened at any point.

## 5. Tests — `tools/test_restore_db.py` (stdlib `unittest`, 19 cases, all pass)

valid backup restore · missing backup · empty backup · non-SQLite source · production destination refusal (three path forms, case-insensitive) · production-as-source refusal · same-file and directory destination refusal · existing destination refused without flag / replaced with flag · manifest generation and completeness (and no secret leakage) · matching backup manifest · **manifest hash mismatch** fails before restore · **manifest row-count mismatch** detected · **corrupted source** fails `integrity_check` before restore · **FK violation** in a backup reported · missing required table reported · content digest detects a one-row difference counts cannot · encrypted backup round-trip · encrypted backup without key refused · CLI exit codes 0/2/1. Output retained as `test_results.txt`. No production file is opened by any test.

Two defects were found and fixed by the tests during this slice: the byte-identity criterion (above), and `PRAGMA integrity_check` raising `DatabaseError` on a badly malformed file, which would have escaped as a traceback instead of a FAIL manifest.

## 6. Verification procedure executed (once)

`RESTORE_REHEARSAL.md`. Summary: `tools/backup_db.py --label recovery_rehearsal` → `tools/restore_db.py --source <snapshot> --dest <isolated scratch>/restored.db --run-id RR-20260908-01 --evidence-dir verification/evidence/20260908_recovery_foundation` → exit 0, 16/16 checks, production hash identical before, between and after.

## 7. Limitations — stated, not hidden

1. **Database-level verification only.** Application-level equivalence (booting FinalGrid against the restored file and exercising it) is not claimed. The narrow read-only path available (`verification/dbcopy.py :: make_copy()` + `python -m verification inv-run` against a copy of the restored file) was **not** run in this slice because `inv-run` writes evidence packs and boots the application in-process; it is the designated Slice 0/Slice 7 step in the Phase 1 plan.
2. **Encrypted application backups were not rehearsed.** The `.enc` path is covered by a unit round-trip with a synthetic key; a rehearsal from a real `backups/*.enc` artifact would require the deployment's key material and is a follow-up rehearsal.
3. **Retention** for recovery artifacts (`../db-backups/`) is by convention only; the application's 30-day purge applies to its own `backups/` directory, not to this location. A retention rule is BACKLOG B-11.
4. **In-place production restore is not built** (by design of this directive). Restoring *into* `instance/pms.db` remains a separately authorized PD-004 act with its own procedure.
5. `tools/backup_db.py`'s own verification is row-count based; this slice adds the body-identity proof between production and snapshot as evidence (`production_snapshot_byte_diff.json`), not as a change to that tool.

## 8. Rollback

Code rollback: the two new files are untracked additions; removing them (or `git revert` once committed) restores the prior state. No production data was written, so no data rollback is required. The restore tool is not a rollback mechanism for production and must not be used as one.

## 9. Governance recorded alongside

Founder Resolution Round 2 (Q-1/CD-1, Q-2, Q-3, Q-4, Q-5, Q-6) appended to `verification/FOUNDER_DECISIONS.md`. Q-5 is recorded as a **binding Phase 1 implementation requirement** (strict audit coupling incl. the POS ordering defect) and was **not** implemented here. Q-4 (golden-master recapture) is approved and **not** performed here.
