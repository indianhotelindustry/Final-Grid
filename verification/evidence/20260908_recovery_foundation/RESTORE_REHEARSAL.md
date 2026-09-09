# Restore Rehearsal — RR-20260908-01 (PD-006 evidence)

| | |
|---|---|
| Directive | FG-P1-RECOVERY-FOUNDATION-20260908-01 |
| Run ID | `RR-20260908-01` |
| Executed | 2026-09-08 19:39:42 (backup) → 19:39:43 (restore verified) |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` |
| Result | **PASS** — 16 of 16 checks; exit code 0 |
| Production touched | **No** |

## 1. Backup artifact (created by the unchanged `tools/backup_db.py`)

| | |
|---|---|
| Snapshot | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\db-backups\pms_20260908_193942_recovery_rehearsal.db` |
| Method | `sqlite-backup-api`; source opened `mode=ro` |
| Source (production) SHA-256 before | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` |
| Source SHA-256 after | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` — `source_unchanged: true` |
| Snapshot SHA-256 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` |
| Size | 733,184 bytes (= production) |
| `integrity_check` | `ok` |
| Tables / rows | 53 / 299, row counts match production across every table |
| Manifest | `backup_manifest.json` (copy of `<snapshot>.manifest.json`) |

**Production ⇄ snapshot byte comparison** (read-only, `production_snapshot_byte_diff.json`): sizes equal; differing bytes **only** at header offsets 26, 27, 43, 94, 95 (file change counter, schema cookie, version-valid-for — SQLite backup-API bookkeeping); **0 differing bytes beyond the 100-byte header.** The snapshot is a faithful page copy of production.

## 2. Restore

| | |
|---|---|
| Tool | `tools/restore_db.py` |
| Destination (isolated, temporary) | `C:\Users\SIPLSE~1\AppData\Local\Temp\claude\…\scratchpad\restore_rehearsal\restored.db` |
| Restore method | `sqlite-backup-api` from the read-only snapshot into a temp file, then atomic rename |
| Restored SHA-256 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` (**identical to the snapshot**) |
| Restored size | 733,184 bytes |
| Manifest | `restore_manifest.json` |

## 3. Verification results

| Check | Result |
|---|---|
| Source has SQLite header | ok |
| Source SHA-256 matches backup manifest `snapshot_sha256` | ok |
| Source `PRAGMA integrity_check` | ok |
| Restored file exists; SQLite header | ok |
| Restored `PRAGMA integrity_check` | **ok** |
| Restored `PRAGMA foreign_key_check` (with `foreign_keys=ON`) | **ok — 0 violations** |
| Required tables present (users, settings, business_date, schema_migrations, reservations, folios, payments, extra_charges, tax_lines, night_audit_logs, audit_logs) | ok — 53 tables |
| `sqlite_master` readable | ok |
| Schema SQL equal (source vs restored) | ok |
| Row counts equal — all 53 tables | ok — 299 = 299 |
| Row counts match backup manifest | ok |
| Content digests equal — all 53 tables | ok |
| Invoice count equal (`reservations.invoice_number IS NOT NULL`) | ok — 4 = 4 |
| Body identical beyond header | ok — 0 differing bytes; sizes equal |
| Whole-file SHA-256 identical | identical (informational) |

### Row counts — key tables

| Table | Source | Restored |
|---|---|---|
| reservations | 4 | 4 |
| folios | 4 | 4 |
| payments | 6 | 6 |
| extra_charges | 2 | 2 |
| invoices (basis above) | 4 | 4 |
| tax_lines | 12 | 12 |
| night_audit_logs | 1 | 1 |
| audit_logs | 23 | 23 |

### Content digests (SHA-256 over ordered rows; prefixes)

reservations `221c648ec6bb…` · folios `6c364aa0ba8c…` · payments `2f8b79899b84…` · extra_charges `89e6e4c0c3ec…` · tax_lines `b0e8446f744f…` · night_audit_logs `77c0457acdb0…` · audit_logs `f89cb501e444…` — identical source vs restored (53 tables compared).

## 4. Production database — before / after

| Point | SHA-256 | Size |
|---|---|---|
| Before backup | `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` | 733,184 |
| After backup | `51dd83b7…30bc2` | 733,184 |
| After restore | `51dd83b7…30bc2` | 733,184 |
| After evidence collection | `51dd83b7…30bc2` | 733,184 |

D11 rows in production after the rehearsal: `payments` 1–6 (800, 400, 1500, 1000, 500, 100) and `extra_charges` 1–2 (380.95, 95.24), all `folio_id NULL` — untouched. `audit_logs` 23 rows — unchanged.

## 5. What this rehearsal proves, and what it does not

**Proves:** a FinalGrid backup produced by the sanctioned backup tool restores into an isolated location as an openable, internally consistent SQLite database whose schema, row counts and row contents are identical to the backup and whose pages are identical to production beyond the file header; and that the procedure is deterministic, auditable and leaves production untouched.

**Does not prove:** application-level behaviour against the restored database (not booted, by design); restoration from an encrypted application backup with real key material; the in-place production restore procedure (not built). See `IMPLEMENTATION_RECORD.md` §7.

## 6. Final result

**RESTORE REHEARSAL: PASS.** PD-006 evidence retained in this directory.
