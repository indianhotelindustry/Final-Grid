# Known Pre-Phase-1 Defects — present at capture, NOT golden-master failures

These conditions exist in the baseline by fact and by ruling. A verifier comparing against this Golden Master must not read them as regressions, and a recapture must not "correct" them. Each names its governance source.

| # | Defect / condition | Evidence at capture | Governance | Phase 1 disposition |
|---|---|---|---|---|
| K-1 | **INV-A02 VIOLATED — every financial row belongs to a folio** | 8 of 8 rows, ₹4,776.19; certification-blocking | AR-001 (invariant stays universal); FD-010 (rows preserved) | **Expected to remain VIOLATED on production after Phase 1** (the eight rows are untouched); expected HOLDS on datasets and on new-activity copies |
| K-2 | **INV-A03 VIOLATED — folio view ≠ reservation view of charges** | ₹476.19 (the two late-checkout charges are unreachable through a folio); release-blocking | as K-1 | as K-1 |
| K-3 | **Eight D11 NULL-`folio_id` historical rows** | payments 1–6, extra_charges 1–2 — the *entire* NULL population | D11-F2 factual; FD-010 Option A; Q-2 (corrections of these originals are refused) | **Must not change.** Every Phase 1 evidence pack proves identity by id set (T29 shape) |
| K-4 | **Folio attribution absent at every originating writer** | 24 writers; only the 4 correction paths set `folio_id`, by inheritance; `calculate_folio_amount` = 0 on every folio | Register R1 (CRITICAL); ADR-002 ADOPTED | **The Phase 1 objective** — see deltas |
| K-5 | **Audit atomicity gap** | `_write_audit` never raises, flush-only; commit proceeds on audit failure at every routes-level writer; W-01/06/07/10/11/16/24 write no audit row | Q-5 binding requirement; ADR-008 | Expected to change for **touched** writers only |
| K-6 | **POS audit ordering** | `app/pos.py:110-134` commits the charge, then audits, swallowing errors | Q-5 (explicitly included) | Expected to change |
| K-7 | **Wall-clock / business-date defects** | W-08/09/22/23 (`today`), W-10 (`_date.today()`), W-11 (`_d.today()`), W-20 (`now().date()`), W-17 (model default); `Payment.payment_date`/`ExtraCharge.charge_date` default `date.today`; business date 30 days behind calendar | FD-013 / AR-008 architecture; **Q-3: Phase 3 concern** | **Not expected to change in Phase 1** (unless a writer's implementation design names a minimum business-date dependency) |
| K-8 | **Night-audit room rent posted with `folio_id NULL` by design**; folio balance excludes room rent | `app/services.py:147-165`, `:2358-2370`; 0 room-rent rows on production today | AR-002 / ADR-003 ADOPTED (reservation operational ownership + folio financial ownership) | Attribution expected to change (unit 1.4); balance semantics not |
| K-9 | **Business date stale / night audit never operated nightly** | 2026-08-10 vs calendar 2026-09-09; one audit, override reason "cvnvhm"; 5 test reopens | Register R8; Phase 3 | Not Phase 1 |
| K-10 | **Destructive audit-log pruning scheduled** (`_prune_old_logs`, 90 days, 04:00) | oldest audit row 2026-08-09 → first deletion ~2026-11-07 if running | FD-008 / AR-007; ADR-012 PROPOSED; BACKLOG B-6 | Not Phase 1; certification blocker |
| K-11 | **Unattended scheduler is a financial writer without AR-013 controls** | `night_audit_job` gated only by `night_audit_enabled` | AR-013; BACKLOG B-1 | Not Phase 1 (attribution of its output changes; its authority/timing does not) |
| K-12 | **FK enforcement off** (declarations present, 0 orphans) | no `PRAGMA foreign_keys=ON` in `app/` | ADR-005 ADOPTED as requirement; BACKLOG B-9 | Not Phase 1 |
| K-13 | **`folio_id` nullable on both tables** | schema | AR-004 staged; BACKLOG B-3 | Not Phase 1 |
| K-14 | **Migration mechanism undecided**; inline registry runs unattended at boot; Alembic orphaned, `alembic.ini` points at production | Register R2/N4/N9; AR-005; BACKLOG B-4 | Not Phase 1 |
| K-15 | **Authorization outside Phase 2a**: seven guard idioms; ≥26 report routes and several writers reachable by any authenticated role | Register R6; ADR-008/009 | Not Phase 1 (negative tests use today's role sets) |
| K-16 | **`list_folios` still Admin/Manager in code** | `app/folio.py:47-52` | FD-015 approved, not implemented | Not authorized by Phase 1 unless its directive says so |
| K-17 | **Restore from encrypted application backups not rehearsed**; app backup path uses `shutil.copy2` | Recovery Foundation record | ADR-007; BACKLOG B-11 | Not Phase 1 |
| K-18 | **Golden master captures HTML only** (V5); 121 non-GET catalogue gaps; five surfaces classed unhealthy by the framework | capture pack | Phase 6 | Baseline limitation, not a Phase 1 change |
| K-19 | **INV-R01 NOT_COMMISSIONED**; 7 invariants VACUOUS on this population | inv-run | Wave 0 / Phase 6 | Unchanged |
| K-20 | **Launchers LF-only** (V10) | 9 files | FD-017 exemption granted, not performed | Not Phase 1 |

Historical accounting-behaviour changes reserved for explicit approval (`WAVE1_BLUEPRINT.md` §6 — W1-R5/R6/R7) are outside Phase 1 and unchanged.
