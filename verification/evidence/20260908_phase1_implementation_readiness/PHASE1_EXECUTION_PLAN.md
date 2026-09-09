# Phase 1 — Execution Plan (ordered slices)

**Directive:** FG-P1-IMPLEMENTATION-READINESS-20260908-01 · **HEAD:** `e69f2ac` · **Status:** PLAN ONLY — no slice is authorized. Sequencing authority: `verification/MASTER_PLAN.md` (Phase 1 units 1.1–1.8; no schema migration; unit 1.6 gated). Branch when authorized: `phase-1-folio-attribution` off `main`; one commit per slice; every commit names this plan and the unit (SC-6).

Standing rules for every slice: SC-1 anchor `51dd83b7…30bc2` verified at start, end and gate · SC-2 all work on `verification/dbcopy.py :: make_copy()` copies · SC-3 no orphan process, port 5000 clear · D11 freeze proven by id set (payments 1–6, charges 1–2) in every evidence pack · Phase 2a 29-case matrix re-run in every slice · no schema change · no `instance/` write.

## Dependency order and why it differs from the suggested structure

The suggested order (Recovery → Attribution → Existing-data → Room-rent → FK → NOT NULL → Verification) is kept, with three evidence-driven adjustments: a **Slice 0** baseline is added because Gate G is blind against the stale master; **Slice 3 (existing data)** collapses to an evidence pack because the live population is exactly D11; **FK and NOT NULL** are specified but placed **outside Phase 1** (Master Plan Phases 4/5; AR-004 Stage G blocked by FD-010 and B-4).

```
S0 baseline ─► S1 recovery foundation ─► S2 attribution foundation ─► S3 originating writers ─► S4 room-rent / night audit
                                                                                              └► S5 reconciliation (1.7) ─► S6 existing-data evidence (1.5/1.6) ─► S7 verification & gate (1.8)
Outside Phase 1:  S8 FK enforcement (Phase 4/5) ─► S9 NOT NULL (Phase 5, after B-3 and B-4)
```

---

## Slice 0 — Pre-Phase-1 baseline (verification only)

| | |
|---|---|
| Objective | Capture a reproducible pre-Phase-1 baseline so every later gate compares against a known state; decide the golden-master question. |
| Prerequisites | Founder answer to Q-4 (recapture allowed as verification-only action). |
| Files likely to change | `verification/evidence/<stamp>_phase1_baseline_*/` (new packs); if Q-4 = yes, `verification/golden/` masters (recapture) |
| Database / data impact | None on production (copies only; `selfcheck` proves it). |
| Authorization / audit / business-date impact | None. |
| Verification suite | `selfcheck`, `inv-run --tag production`, `gm-verify`, `replay-verify`, `ds-run` all six datasets, `compare` baseline. |
| Rollback | Delete nothing; packs are additive (SC-4). |
| Exit criteria | Packs retained; `inv-run` shows the known state (26 registered, 17 HOLDS, 7 VACUOUS, 2 VIOLATED, INV-A02 8/8 ₹4,776.19, INV-A03 ₹476.19); D11 ids recorded. |
| Blockers | Q-4 unanswered → skip recapture, proceed with declared-difference discipline (Phase 2a precedent). |

## Slice 1 — Recovery Foundation (bounded implementation, outside `app/`)

| | |
|---|---|
| Objective | Satisfy ADR-007 target components so PD-006 becomes satisfiable: restore procedure, restore verification, rehearsal record, retention of recovery artifacts. |
| Prerequisites | Founder acceptance that this precedes Phase 1 code (deviation from Master Plan Phase 9 placement — Q-6); a bounded implementation directive naming it. |
| Files likely to change | new `tools/restore_db.py`; `tools/backup_db.py` (retention label / manifest fields only if needed); `tools/RECOVERY.md`; `verification/evidence/<stamp>_restore_rehearsal/`. **No `app/` change.** |
| Database / data impact | None on production. Rehearsal restores into a scratch path; verification runs through `make_copy()` + `inv-run`. |
| Authorization / audit / business-date impact | None. |
| Verification suite | `RECOVERY_GATE_PLAN.md` §4 rehearsal protocol; restore record with hash equality, `integrity_check`, row-count manifest, `inv-run` verdict equality. |
| Rollback | Code: `git revert`. No data. |
| Exit criteria | One rehearsed restore record against the current anchor; ADR-007 components 1–7 each evidenced. |
| Blockers | B1, B2; Q-6. Key custody for `.enc` application backups (`PII_ENCRYPTION_KEY`/`SECRET_KEY` HKDF) documented. |

## Slice 2 — Folio Attribution Foundation (unit 1.1)

| | |
|---|---|
| Objective | One resolver in the service layer; lifecycle proof for every reservation-creation path; CD-1 behaviour; correction fail-closed rule. |
| Prerequisites | Slice 0; Q-1, Q-2 answered (defaults acceptable). |
| Files likely to change | `app/services.py` (new `resolve_billing_folio(reservation)`; helper for corrections); `verification/evidence/<stamp>_phase1_s2/verify.py`. **Not** `app/models.py` (listener stays), **not** `app/folio.py`. |
| Database / data impact | None on production. Copies: new reservations + folios only. |
| Authorization | None new. |
| Audit | `folio_auto_created` row on the CD-1 path, A-STRICT coupled. |
| Business date | None. |
| Verification | T-L01 (walk-in, new reservation, bulk, express walk-in, group → exactly one Folio A; resolver returns it); T-L02 raw-SQL reservation without folio → CD-1 path creates + audits (or refuses, per Q-1); T-L03 resolver never returns B when A exists; T-L04 invalid reservation raises. |
| Rollback | `git revert` one commit. |
| Exit criteria | All T-L pass on a copy; anchor unchanged; Phase 2a matrix 29/29. |
| Blockers | none beyond Q-1/Q-2. |

## Slice 3 — Originating writer attribution (units 1.2, 1.3, 1.5)

| | |
|---|---|
| Objective | Apply the resolver at the 18 non-room-revenue originating sites (W-01…W-07, W-10…W-15, W-17…W-20), ratify the four correction sites (W-08/09/22/23) with the fail-closed rule, close the audit-atomicity gap at every touched writer (R-AUD-1/2/3), bring `seed.py` fixtures under contract (CD-4). **No date changes** unless Q-3 says otherwise. |
| Prerequisites | Slice 2; Q-3, Q-5 answered. |
| Files likely to change | `app/routes.py` (11 sites: 1930, 2195, 3055, 3242, 3274, 3390, 3418, 5745, 7448, 7976, 9227 — one keyword argument each plus audit coupling; no restructuring, §19); `app/services.py` (1489, 1785, 2791; 922/953/1007/1041 fail-closed guard); `app/cico_service.py:353`; `app/noshow_service.py:143`; `app/pos.py:110-134` (attribution + audit re-order); `app/seed.py` (307, 327, 357, 373, 377); `verification/evidence/<stamp>_phase1_s3/verify.py`. Untouched: `models.py`, `folio.py`, templates, `migrations/`, `instance/`. |
| Database / data impact | None on production. |
| Authorization | Unchanged; negative tests assert today's role sets (inventory). |
| Audit | A-STRICT at each touched writer; POS becomes atomic. |
| Business date | Unchanged (F4 recorded). |
| Verification | T-P01…T-P12, T-C01…T-C09; negative: NULL construction detected; audit-failure injection rolls back the financial row (T-A01 per writer); POS ordering test (T-A02). |
| Rollback | `git revert` per commit (two commits: charges, payments). |
| Exit criteria | Every touched writer produces `folio_id == Folio A`; INV-A02/A03 HOLD on the new-activity copy; production `inv-run` unchanged (still 8/8 VIOLATED by design). |
| Blockers | Q-3, Q-5. |

## Slice 4 — Room-rent / night-audit / upsell attribution (unit 1.4)

| | |
|---|---|
| Objective | Attribute W-21 (`run_night_audit` room_rent), W-16 (`_rerun_skipped_audit`), W-24 (`convert_overpayment_to_upsell`) to the billing folio under the adopted architecture; preserve idempotency and business-date handling exactly; folio balance semantics unchanged. |
| Prerequisites | Slice 3. |
| Files likely to change | `app/services.py:147-165`, `:2537`; `app/reports.py:3341`; `verification/evidence/<stamp>_phase1_s4/verify.py`. **Not** `calculate_folio_amount`. |
| Database / data impact | None on production. Copies: a fresh stay night-audited on a copy. |
| Authorization | Unchanged. Night audit remains scheduler-triggered or manual (`routes.py:4835`). AR-013 dependency recorded. |
| Audit | `NightAuditLog` unchanged; no per-row AuditLog added. |
| Business date | `_bd` / `target_date` unchanged. |
| Verification | T-R01 fresh stay → attributed `room_rent` rows; rerun posts nothing (T-R02); skipped-audit rerun attributes and stays idempotent; T-R03 upsell attributed; INV-B01/B02/B03 HOLD on the copy after close; `calculate_folio_amount` still excludes room revenue (T-R04); snapshot fields unchanged. |
| Rollback | `git revert`. |
| Exit criteria | INV-A02/A03 HOLD on a copy with a night-audited stay; closed-day invariants unchanged. |
| Blockers | none beyond Slice 3. |

## Slice 5 — Reconciliation reads the canonical relationship (unit 1.7)

| | |
|---|---|
| Objective | Add the folio-level figure beside the reservation-level figure in the night audit's folio control and assert equality; disagreement rendered as a warning row. Reservation figure stays what the snapshot stores. |
| Prerequisites | Slice 4. |
| Files likely to change | `app/night_audit_service.py` (folio control, ~716–740 per the 2026-09-05 directive; exact lines to be confirmed at implementation); template row for the warning (presentation only); `verification/evidence/<stamp>_phase1_s5/`. |
| Database / data impact | None. Snapshot JSON shape unchanged (INV-B03 compared fields unchanged). |
| Verification | T-N01 folio figure == reservation figure for every reservation on the copy; T-N02 snapshot fields unchanged; INV-B03 unchanged for 2026-08-09; golden master: declared difference on the night-audit surfaces only. |
| Rollback | `git revert`. |
| Exit criteria | Equality holds on datasets and the new-activity copy. |
| Blockers | none. |

## Slice 6 — Existing-data classification evidence (units 1.5 / 1.6 boundary)

| | |
|---|---|
| Objective | Produce the Stage C evidence pack: prove by id, amount, date, actor and audit trail that the live NULL-`folio_id` population equals the D11 set; record that Stages D/E are null operations on this database; define the method for other databases. **No migration.** |
| Prerequisites | Slice 0 baseline. |
| Files likely to change | `verification/evidence/<stamp>_phase1_existing_data_classification/` (report + JSON). |
| Database / data impact | None. Read-only queries via `mode=ro&immutable=1`. |
| Verification | The pack itself; anchor before/after; D11 id set. |
| Rollback | n/a. |
| Exit criteria | Classification recorded; unit 1.6 explicitly marked "no authorized action" (FD-010). |
| Blockers | none. |

## Slice 7 — Verification, evidence and gate (unit 1.8)

| | |
|---|---|
| Objective | The eight evidence artifacts; per-population INV-A02/A03 declaration; completion report with §18 answerability; Founder review. |
| Prerequisites | Slices 2–6. |
| Files likely to change | `verification/evidence/<stamp>_phase1_folio_attribution/` (`COMPLETION_REPORT.md`, `result.json`, `verify.py`). |
| Verification | `VERIFICATION_PLAN.md` §6 gate: `inv-run` production (unchanged) and new-activity copy (A02/A03 HOLD, B01–B03 HOLD), `ds-run` six datasets, Q14 AGREED, `gm-verify` declared differences only, `replay-verify`, Phase 2a matrix, D11 by id. |
| Exit criteria | Declared outcome: every post-deployment row attributed; production still VIOLATED 8/8 by design; OVERALL FAIL until a Founder decision on the eight rows. Phase 2b entry is a Founder call. |
| Blockers | none. |

---

## Outside Phase 1 (specified for continuity; not schedulable under a Phase 1 authorization)

### Slice 8 — FK enforcement (ADR-005; Master Plan Phase 4/5)

Objective: `PRAGMA foreign_keys=ON` on every application connection via a SQLAlchemy engine `connect` event registered in `create_app()` (covers web, scheduler, `flask seed`, `reset_transactional_data.py`, desktop wrapper, verification harness boots). Direct-`sqlite3` tools (`tools/backup_db.py`, `tools/production_initialize.py`, `verification/dbcopy.py`, `datasets/builder.py`, `faults/injection.py`, `commission.py`) are enumerated in `MIGRATION_AND_DATA_PLAN.md` §5 with their required behaviour. Prerequisites: orphan scan on a copy (live: 0 orphans today), `ds-run`/`fault-run`/`inv-run` under ON, delete-path review. Rollback: remove the listener. Not Phase 1.

### Slice 9 — `folio_id NOT NULL` (AR-004 Stage G; Phase 5)

Prerequisites: Stages A–F; Founder decision on the eight rows (B-3); migration mechanism (B-4); PD-004 directive; PD-005 sequence; PD-006 rehearsal. SQLite requires a table rebuild for both financial tables. Rollback: rehearsed restore. Not Phase 1.

## Exit of Phase 1 as a whole

Honest and partial, as the Master Plan and the 2026-09-05 directive already state: all new rows attributed; datasets and new-activity copies HOLD; production still reports the eight D11 rows as VIOLATED under FD-010; OVERALL FAIL persists until the Founder rules on the eight rows or an invariant population declaration. That outcome is the plan's expected result, not a failure of it.
