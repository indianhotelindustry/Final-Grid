# Phase 1 — Migration and Data Plan

**Directive:** FG-P1-IMPLEMENTATION-READINESS-20260908-01 · **HEAD:** `e69f2ac` · **Status:** PLAN ONLY. No migration, no data mutation, no schema change is authorized or performed.

## 1. Three populations

| Population | Definition | Live database (2026-09-08, read-only) |
|---|---|---|
| **Historical D11** | `payments` 1–6 and `extra_charges` 1–2, classified commissioning/test (D11-F2), treatment FD-010 Option A | 8 rows, ₹4,776.19, all `folio_id NULL`. Protected. |
| **Legitimate existing** | Any other `payments`/`extra_charges` row created before Phase 1 deployment that represents genuine trading | **Empty.** `payments` has exactly 6 rows, `extra_charges` exactly 2; there is no ninth financial row. |
| **Future-state** | Every row created after Phase 1 deployment | Governed by ADR-002; must be attributed at insert. |

The directive's caution — do not assume every NULL row is D11 — is honoured by *counting*, not assuming: total financial rows = 8 = D11 set, so the legitimate-existing population is empty on this database by arithmetic, not by classification.

## 2. Corroborating evidence for the eight rows (read-only)

| Attribute | Evidence |
|---|---|
| Reservations | 1–4, all `CheckedOut`, arrival 2026-08-09/10, departure next day; created 2026-08-10 09:14 and 2026-08-11 06:25–06:30 |
| Invoices | `INV-2026-000029` … `000032`; `settings.invoice_counter = 32` |
| Billing | all `checkin_records.billing_responsibility = 'Guest'`, `company_id NULL`; 0 companies |
| Actor | every financial row traced to `admin` (user 1) via `audit_logs` (`checkout`, `auto_late_checkout_charge`), IP `127.0.0.1` |
| Night audit | one log, 2026-08-09, Completed, `override_used=1`, 5 reopens with test reasons |
| Room rent | never posted (`reservation_night_rates.is_posted = 0` for all 4; no `room_rent` charge rows) — the two charges are `late_checkout` |
| Other financial tables | `void_requests` 0, `credit_notes` 0, `no_show_logs` 0, `overpayment_logs` 0, `cico_charge_logs` 2 (the two late-checkout charges) |

## 3. Classification method (for this and any other database)

To be executed read-only on a `make_copy()` copy and recorded as an evidence pack before any migration is considered:

1. **Enumerate** all `payments` and `extra_charges` rows with `folio_id IS NULL`; total, ids, amounts, dates.
2. **Match** against the D11 identity set (ids, amounts, `created_at`, reservation) — a row is D11 only if it matches on all four.
3. **Remainder** = candidate legitimate rows. For each: reservation status and invoice; `audit_logs` actor and action; `checkin_records` billing; shift/cashier context if any; night-audit inclusion (`INV-B01`: created into a closed date?); correction linkage (`corrects_id`).
4. **Classify** each remainder row as LEGITIMATE (attribute under Stage E), COMMISSIONING (candidate for a Founder factual ruling like D11-F2), or UNRESOLVED (blocks migration).
5. **Declare** the expected invariant movement per figure before Stage E (ENGINEERING_GUIDE §5).
6. If any row is UNRESOLVED → `BLOCKED — classification incomplete`.

On the live database step 3 yields an empty remainder. On the pre-reset backups (`backups/pms_PRE_TXN_RESET_20260809_104630.db`, `pms_pre_DEF004_…`, `pms_pre_v2.2.18_upgrade.db`) the Register records 58 payments / 7 charges NULL; those files are **archival** and outside every Phase 1 population; they are never touched under any option (ADR-002 §D).

## 4. Staged `folio_id NOT NULL` strategy (AR-004) mapped to slices

| Stage | Content | Slice | Status for live DB |
|---|---|---|---|
| A | Fix all originating writers | S2, S3, S4 | Planned |
| B | Establish FK integrity | S8 (Phase 4/5) | Orphans: 0 today; declarations present; enforcement off |
| C | Classify existing financial rows | S6 | **Conclusive: population = D11** |
| D | Authorized disposition of legitimate existing NULL rows | — | **Null operation** (no legitimate NULL rows) |
| E | Authorized data migration | — | **Not required** for the live DB; would require PD-004/005/006 on any other DB |
| F | Zero unresolved legitimate NULL rows | S7 evidence | Satisfied by construction; **the eight D11 rows remain NULL and do not satisfy F by attribution** |
| G | Enforce `NOT NULL` | S9 (Phase 5) | **Blocked**: eight NULL rows under FD-010 (B-3), migration mechanism (B-4), PD-006 |
| H | Verify application behaviour after constraint | S9 | — |

The eight D11 rows cannot be assigned folios to satisfy Stage F. Their disposition before Stage G is a separate Founder decision (BACKLOG B-3); nothing in Phase 1 depends on it.

## 5. FK enforcement design (ADR-005 — every connection, not caller-dependent)

| Connection mechanism | Path | How enforcement would apply | Required behaviour |
|---|---|---|---|
| SQLAlchemy engine (Flask-SQLAlchemy) | `create_app()` → `SQLALCHEMY_DATABASE_URI` sqlite, `SQLALCHEMY_ENGINE_OPTIONS.connect_args` (`app/__init__.py:121-154`) | **One `connect` event listener** on the engine issuing `PRAGMA foreign_keys=ON` per DBAPI connection | Covers web requests, APScheduler jobs (same app context), `flask seed/unseed`, `reset_transactional_data.py` (`create_app()`), `desktop_window.py`, and every harness boot against a copy |
| Alembic | `migrations/alembic.ini` → its own engine; `env.py` may use `current_app` under `flask db` | Must set the pragma itself; **note `alembic.ini` points at production** | Decision B-4 governs; until then Alembic must not be run |
| `tools/backup_db.py` | direct `sqlite3`, source `mode=ro`, dest plain | Read-only source; dest is a copy — pragma irrelevant to integrity | None |
| `tools/production_initialize.py` | direct `sqlite3`, sets `foreign_keys=OFF` deliberately (`:296`) | A production-mutation tool; runs under PD-004 only | Re-enable ON and run `foreign_key_check` before commit — implementation design item |
| `verification/dbcopy.py`, `datasets/builder.py` (OFF at `:68`), `faults/injection.py`, `commission.py` | direct `sqlite3` on **copies** | Copies only; builders rely on OFF for strip order | Keep OFF locally; document; add `foreign_key_check` at the end of each build |
| Any future direct connection | — | Must go through a shared helper that sets the pragma | Guardrail: a verification check that greps for `sqlite3.connect(` outside the allowed list |

Prerequisite evidence at enablement (Phase 4/5): `foreign_key_check` on a copy (0 today), `ds-run` six datasets, `fault-run`, `inv-run` under ON; review of every delete path for cascade semantics; rollback = remove the listener (no data change).

## 6. Migration mechanism — option analysis (B-4) — **FOUNDER / ARCHITECTURE DECISION REQUIRED**

| Criterion | Inline registry (`_run_pending_migrations`) | Alembic (`migrations/`) | New purpose-built SQLite migrator |
|---|---|---|---|
| Repository compatibility | Live; 57 entries; called at boot and by updater | Present; 7 revisions, head `f7a8b9c0d1e2`; installer stamp/upgrade helpers; **no caller**; `verify_schema.py` expects it | None exists |
| Current schema state | `schema_migrations` 57 rows | `alembic_version` **absent**; stamp-check would stamp `c4d5e6f7a8b9` | — |
| Reproducibility | Low for SQLite: `DO $$` entries are PG-only and skipped; SQLite shape comes from `create_all()` + column fixer (Register N9) | High when applied; batch mode enables SQLite table rebuilds (`render_as_batch` — NOT VERIFIED in `env.py`) | Would be designed for it |
| Rollback | No down-migrations | Down-revisions exist per file | Design choice |
| Operational complexity | Lowest today; unattended at boot (non-compliant with AR-005/FD-007) | Medium; needs stamping, gating, removal of the permanently failing `verify_schema` gate | Highest |
| Risk | Cannot express a table rebuild; boot-time execution | Stamping a live DB incorrectly replays the PG-targeted base revision (documented failure mode) | Untested |
| Fit with SQLite | Poor for constraints | Good (batch) | Good |
| Fit with FinalGrid | Familiar; installer already half-built for Alembic | Aligns with `verify_schema.py`, installer scripts, Register R2 corrected reading | — |
| Evidence needed | — | Rehearsal on a copy: stamp → `upgrade head` → `verify_schema` PASS; `render_as_batch` confirmed | Prototype |
| Recommendation | Retain for existing entries; **do not use for Stage G** | Engineering evidence favours Alembic (batch) for Stage G after a rehearsed stamp on a copy and after boot-time execution is removed | Not recommended |

Because a choice here changes how production schema evolves and retires a live mechanism: **FOUNDER / ARCHITECTURE DECISION REQUIRED** (B-4). Not needed for any Phase 1 code slice.

## 7. Rollback per mutation class

| Class | Mechanism | Demonstrated? |
|---|---|---|
| Code (Slices 2–5) | `git revert` per slice commit; branch `phase-1-folio-attribution` | Yes (Phase 2a precedent) |
| Schema (Slice 9) | Migration-specific down path **or** restore | No — mechanism undecided |
| Data (Stage E; none on live DB) | Restore from a rehearsed snapshot; a transactional reversal of recorded ids is acceptable only with the id list captured before mutation and proven on a copy | No — restore does not exist |
| Production recovery | `RECOVERY_GATE_PLAN.md` | No |

No rollback confidence is claimed beyond code.

## 8. Explicit non-actions

No migration was run; no row, folio, invoice, GST, audit or scheduler record was changed; the eight D11 rows are byte-identical; the database hash is unchanged.
