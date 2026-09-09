# FinalGrid — Pre-Phase-1 Golden Master

| | |
|---|---|
| Directive | FG-P1-GOLDEN-MASTER-20260908-01 (Founder decision Q-4) |
| Captured | 2026-09-09 06:25–06:28 local (evidence packs stamped `20260909_0056xx` UTC) |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` — unchanged; **no commit, no push** |
| Production database | `instance/pms.db` — **733,184 B · SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2`** — byte-identical before, between and after every step |
| Convention followed | The repository's own D2 Golden Master Framework (`verification/golden/`, master set `verification/masters/production/`), not a competing structure. This directory adds the database, financial, behavioural, defect and delta baselines around it. |
| Scope | **READ-ONLY.** No application code, schema, migration, template, static file, scheduler, folio/payment/charge logic, audit, business-date, invoice, GST or D11 change. |

## 1. What was captured, and with what

| Layer | Tool / method | Artifact | Result |
|---|---|---|---|
| Read-only proof | `python -m verification selfcheck` | (console) | READ-ONLY VERIFIED |
| Previous master (superseded) | fingerprint of `verification/masters/production/` as committed at `e69f2ac` | `previous_master_manifest.json` | 158 surfaces, frozen **2026-05-28**, pvf 0.2.0 — captured 2026-08-03 against the **pre-reset May dataset**; preserved in git history |
| **Golden master recapture** | `python -m verification gm-capture --tag production` — app booted **against a `make_copy()` copy**, clock frozen to the copy's business date, production hashed before/after | `verification/masters/production/` (rewritten: 151 modified, 6 removed, 6 added — date-scoped report surfaces moved from May to August) · pack `20260909_005605_gm_capture_production` | 158 surfaces; frozen `2026-08-10T12:00:00`; business date 2026-08-10; app 2.2.18; pvf 0.5.0; principal `admin` (Admin); `read_only_verified: true`; 7.03 s |
| Reproducibility proof | `python -m verification gm-verify --tag production` | pack `20260909_005614_gm_verify_production` | **PASS — 158/158 clean, 0 differences, 0 blocking** |
| Financial invariant baseline | `python -m verification inv-run --tag production` | pack `20260909_005620_inv_run_production` | `overall: FAIL` (expected) — 26 registered · 17 HOLDS · 7 VACUOUS · 2 VIOLATED · INV-R01 NOT_COMMISSIONED; read-only / freeze / determinism / order-independence all proven |
| Historical replay baseline | `python -m verification replay-verify --tag production` | pack `20260909_005622_replay_verify_production` | **PASS — 10 dates, 0 differences** |
| Database baseline | read-only `sqlite3` (`mode=ro&immutable=1`), hash before/after | `DATABASE_BASELINE.json` | integrity ok · 0 FK violations · 53 tables · 299 rows · schema fingerprint `a7428da6840e79dd…` |
| Financial baseline | same connection | `FINANCIAL_BASELINE.json` | every payment and charge row, folios, NULL population, D11 identity |

Harness logs are retained in this directory (`gm_capture.log`, `gm_verify.log`, `inv_run.log`, `replay_verify.log`).

## 2. The four things this baseline keeps apart

| Category | Where recorded | Summary |
|---|---|---|
| **Current expected behaviour** | `BEHAVIOR_BASELINE.md` §1–§3; master set; invariants that HOLD | What the system does today and must keep doing unless a Phase 1 delta names it |
| **Known existing defects** | `KNOWN_DEFECTS.md` | Conditions present at capture that are **not** golden-master failures and must not be "fixed" by a recapture |
| **D11 historical commissioning/test data** | `FINANCIAL_BASELINE.json → d11`; §4 below | Eight rows, protected; the entire NULL-`folio_id` population |
| **Behaviour Phase 1 is expected to change** | `EXPECTED_PHASE1_DELTAS.md` | Exactly which values, verdicts and surfaces are expected to move, and which are not |

## 3. Database baseline — summary

| Item | Value |
|---|---|
| Hash / size | `51dd83b7…30bc2` / 733,184 B |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` (with `foreign_keys=ON`) | 0 violations |
| Schema | 144 objects (53 tables, 91 indexes); fingerprint `a7428da6840e79dd6b99c286b4b07d2cbeea14dc4221cade1c54070a8c42aee7` (sha256 of ordered `sqlite_master`); `schema_version` 123; page 4096 × 179; `journal_mode=delete`; `schema_migrations` 57 rows, max `9.0.0`; no `alembic_version` table; `folio_id` nullable on `payments` and `extra_charges` |
| Rows | 299 across 53 tables; per-table counts and per-table content digests in `DATABASE_BASELINE.json` |
| Business date | 2026-08-10, unlocked (updated 2026-08-11 12:42:48) |
| Night audit | 1 log — 2026-08-09, Completed, `snapshot_valid=1`, `override_used=1`; 5 reopen logs |
| Identity | `hotel_name` Sukoon Pearl Inn · `app_name` blank (→ FinalGrid default) · `property_id` sukoon-pearl-inn · `invoice_counter` 32 · `night_audit_enabled` true |
| Users | 1 — `admin` (Admin), active |

## 4. Financial baseline — summary

| Population | Value |
|---|---|
| Payments | **6 rows, ₹4,300.00**, all `payment_purpose='settlement'`, none voided, none corrections; **all `folio_id NULL`** |
| Extra charges | **2 rows, ₹476.19**, both `late_checkout`; **both `folio_id NULL`** |
| Folios | 4 — one Folio A ("Guest") per reservation; `company_id` NULL; none closed; **0 payments and 0 charges attributed** |
| Reservations → folio | 1→1, 2→2, 3→3, 4→4 (all letter A) |
| Invoices | 4 (`INV-2026-000029`…`000032`, on `reservations.invoice_number`; counter 32); 12 `tax_lines` |
| Check-in records | 4, all `billing_responsibility='Guest'`, `company_id` NULL, `company_credit_posted=0`; 0 companies |
| Room revenue | 0 `room_rent` charge rows; 4 `reservation_night_rates` rows, none posted/locked |
| Audit log | 23 rows (Auth 8, Reservation 6, NightAuditLog 5, ReservationRoom 4); 2026-08-09 12:16 → 2026-08-30 06:20 |
| Other financial tables | void_requests 0 · credit_notes 0 · no_show_logs 0 · overpayment_logs 0 · cico_charge_logs 2 · ota_payouts 0 · shifts 0 |
| **NULL-`folio_id` population** | **payments [1,2,3,4,5,6] + extra_charges [1,2] = ₹4,776.19 — equals the D11 set exactly (`equals_d11_set: true`)** |

### The eight D11 rows — HISTORICAL COMMISSIONING / TEST ACTIVITY — PROTECTED

| Row | Reservation | Amount | Date | `folio_id` |
|---|---|---|---|---|
| payment 1 | 1 | 800.00 | 2026-08-09 | NULL |
| payment 2 | 1 | 400.00 | 2026-08-09 | NULL |
| payment 3 | 2 | 1,500.00 | 2026-08-10 | NULL |
| payment 4 | 3 | 1,000.00 | 2026-08-10 | NULL |
| payment 5 | 4 | 500.00 | 2026-08-10 | NULL |
| payment 6 | 4 | 100.00 | 2026-08-10 | NULL |
| charge 1 | 1 | 380.95 | 2026-08-09 | NULL |
| charge 2 | 4 | 95.24 | 2026-08-10 | NULL |

D11-F2 (factual, 2026-09-05) · FD-010 Option A (treatment, 2026-09-08) · AR-001 (INV-A02 stays universal; these are a known historical exception in data). **Not modified by this capture; must not be modified by Phase 1.** Full row contents in `FINANCIAL_BASELINE.json`.

## 5. Invariant baseline (per-invariant, from `20260909_005620_inv_run_production`)

HOLDS: A01, A04, A05, B01, B02, B03, B04, B05, B06, C02, C03, C04, D01, D03, D04, D06, R01 (R01 evaluates HOLDS but is NOT_COMMISSIONED and excluded from the verdict). VACUOUS: A06, C01, C05, C06, D02, D05, D07. **VIOLATED: INV-A02 (8 of 8, ₹4,776.19 — certification-blocking), INV-A03 (₹476.19 — release-blocking).** Overall FAIL. Identical to the 2026-08-31 baseline pack — no drift.

## 6. Golden-master surface baseline

158 surfaces: FINANCIAL 80 · OPERATIONAL 49 · ADVISORY 23 · PUBLIC 6. Framework health: 153 healthy / 5 unhealthy. HTTP status histogram as captured: 200 × 146 · 302 × 7 · 400 × 3 · 404 × 2. Non-200 surfaces are **captured as rendered** (e.g. `auth.login` 302 for a logged-in principal, `main.setup_wizard` 404 once an admin exists, `booking.availability_api` 400 without parameters) and are part of the expected baseline, not defects; the list is in `BEHAVIOR_BASELINE.md` §4. 121 catalogue entries are non-GET or POST-only and are recorded as capture gaps by the framework (unchanged from prior captures). Known limitation V5: HTML only; Excel/PDF branches are not captured.

## 7. Reproducibility

Commands, in order, from the repository root with the venv interpreter and `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` (the console is cp1252 — Register V3):

```
venv\Scripts\python.exe -m verification selfcheck
venv\Scripts\python.exe -m verification gm-capture --tag production --quiet
venv\Scripts\python.exe -m verification gm-verify  --tag production --quiet
venv\Scripts\python.exe -m verification inv-run    --tag production --quiet
venv\Scripts\python.exe -m verification replay-verify --tag production --quiet
python <this dir>/baseline.py <output dir>          # DATABASE_BASELINE.json, FINANCIAL_BASELINE.json
```

What was measured: the production file at anchor `51dd83b7…` through `make_copy()` copies (harness) and an immutable read-only connection (baseline script). What was intentionally excluded: `ds-run`/`ds-coverage` (six datasets — not run here; they measure fixtures, not production, and are a Slice 0/7 item), `fault-run` (INCOMPLETE until D7/D9 by design), `compare` (D1 parity — no baseline tag was declared for it in this directive). Values expected to change after Phase 1 are enumerated in `EXPECTED_PHASE1_DELTAS.md`.

**Reproducibility caveats:** a future `gm-verify` reproduces this master only while the production database is at the same anchor and the clock-freeze resolves to the same business date; any database change legitimately moves date-scoped report surfaces. `gm-verify` is a change detector, not an attributor (README §"D2_GOLDEN") — it says *that* a surface changed, not why.

## 8. Safety verification (§12) — performed after capture

Production hash and size unchanged at every checkpoint (selfcheck, capture, verify, inv-run, replay, baseline script); schema fingerprint unchanged; D11 rows unchanged; `audit_logs` 23 unchanged; no financial row changed; `git diff` over `app/`, `migrations/`, templates, static, `instance/`, launchers empty; no unrelated dirty entry cleaned; legacy repository fingerprints unchanged. Details in `result.json` and the final report.

## 9. Gate

**GOLDEN MASTER PASS — READY FOR PHASE 1 AUTHORIZATION.** Phase 1 does not begin on this PASS; it requires a separate Phase 1 execution authorization.
