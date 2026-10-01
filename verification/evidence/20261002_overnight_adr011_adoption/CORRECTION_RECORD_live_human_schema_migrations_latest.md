# CORRECTION RECORD — `schema_migrations_latest` in the ADR-011 live HUMAN provenance pack

| | |
|---|---|
| Recorded | 2026-10-02, FG-OVERNIGHT-01 |
| Pack corrected | `verification/evidence/20260930_135930_adr011_live_human_provenance/` (committed at `c703150`) |
| Method | correction record only — the original `RESULT.json` and script are **not modified** (evidence is never overwritten) |

## What is wrong

`RESULT.json` reports `"schema_migrations_latest": "9.0.0"`. That pack's `REPORT.md:53` says the latest migration is `10.0.0`.

Cause: `verify_live_human.py:127` computes `SELECT MAX(version) FROM schema_migrations`. `version` is text, so `MAX` compares strings, and `"9.0.0"` sorts above `"10.0.0"`. The field reports the lexicographically largest version, which is not the latest migration.

## Correct reading

- Migration `10.0.0` **is** recorded in production `schema_migrations`. The authoritative proof is the production application pack `20260930_adr011_production_application/RESULT.json` (`schema_migrations_added`).
- The live check's verdict (HUMAN provenance PASS) does not depend on this field and is unchanged.

## Wider note (for future harnesses)

Any harness that reads "latest migration" with a text `MAX(version)` or `ORDER BY version` has the same defect once versions reach two-digit majors. Compare parsed version tuples instead. No harness code is changed by this record.

Found by: the ADR-011 adoption analysis (`ADR011_ADOPTION_PACKAGE.md`, inconsistency I-5); reconfirmed by reading `verify_live_human.py:127` and `RESULT.json`.
