# Production-Readiness Inventory — every remaining item, classified

Directive FG-P2-ENTRY-READINESS-20260910-01, section 3. Baseline `a84566ae`. Classes: **A** must complete before production · **B** must verify before production · **C** should complete before production · **D** safe to defer after production · **E** Founder decision required. Impact is assessed on the actual operating and financial consequence, not on the mere existence of a finding. Where an item has two classes, the second is the decision or verification that accompanies it.

## 1. Financial integrity

| # | Item | Current state (evidence) | Operational / financial impact | Class | Phase / owner |
|---|---|---|---|---|---|
| FI-1 | Universal folio attribution | 33/33 sites; 22/24 writers at runtime; resolver fail-closed; D11 correction refused | Closed for new activity; the only unattributed rows are the eight D11 rows | **B** (re-verify on the deployment rehearsal copy) | done — G10 |
| FI-2 | Strict audit coupling at the 12 non-strict writers (CF-10) | A-STRICT at 12; caller-supplied/swallowed at W-08/09/10/22/23; entity-level W-11/12; dedicated W-13/14; run-level W-16/21; none W-24 | A correction, refund, voucher or upsell can commit with its audit row silently missing; provenance gap on exactly the rows a dispute would ask about | **A** (Founder sequencing: pre-2b) | pre-2b package |
| FI-3 | Business-date integrity at financial writers (K-7): W-08/09/22/23 `today`, W-10, W-11, W-20 wall clock, W-17 model default; `date.today` model defaults; calendar-clock late-checkout auto-charge at checkout | Untouched by Phase 1 (Q-3); production business date 30 days behind the calendar; INV-B04/B06 fire on copies with such rows | On a live day: rows dated to the calendar day rather than the open business day whenever the close lags midnight; corrections into closed days (INV-B01); day totals and GST report mis-stated; late-checkout charges computed from the wrong clock | **A** | Phase 3 (3.1) |
| FI-4 | Night audit as the financial close — idempotency, override/reopen semantics, interrupted-close recovery, staleness escalation, multi-day sequence | R8 "never operated nightly"; one Completed audit (08-09) with override reason "cvnvhm"; five test reopens; `night_audit_enabled=false` on production; idempotency proven on copies (T-R02) | The close is the mechanism that fixes daily revenue, locks days and advances the date; an unrecovered interrupted close or a double close corrupts history | **A** (3.2–3.5) + **B** (multi-day rehearsal, N7) | Phase 3 |
| FI-5 | Reconciliation | `attribution_control` delivered; D11 in its own bucket; replay coverage absent (CF-6) | Works; the control is outside the replay ledger only | **D** (CF-6) | Phase 6 |
| FI-6 | Refunds — cancellation-refund semantics (SR-2: `is_reversal` without `corrects_id`, INV-D02 fires) | Pre-existing design; attributed correctly | Invariant verdict on a real property with refunds would show a RELEASE_BLOCKING violation that is really a semantics mismatch | **E** (resolve the semantics) + **B** | review track (Phase 6 / 2b) |
| FI-7 | Advance payments — SR-1 (INV-B06 fires on business-dated advances for later stays) | Pre-existing; W-01/W-02 date the deposit on the booking day by design | Same category: an MEDIUM/OPERATIONAL warning on every advance booking would make the invariant report noise | **E** + **B** | review track (Phase 3 / 6) |
| FI-8 | Cancellation semantics beyond the refund row (forfeit thresholds, voucher issue) | Working per Phase 1 runtime (W-10 exercised); forfeit approval threshold exists | No new defect found | **B** | deployment rehearsal |
| FI-9 | Credit recovery and voucher redemption (CF-11: `settle_credit`, `redeem_credit_voucher`) | Both crash (`TypeError`, `notes=` on `Payment`) since `b5b2514`; routes non-functional | A property cannot record an individual-credit settlement or redeem a voucher at all; if either feature is in use, money cannot be booked | **A** (small bounded fix) | pre-2b package |
| FI-10 | GST / invoice integrity | Q06 **DIVERGED on production**: `gst_service.get_gst_report` 1,142.85 / 2,952.38 vs `NightAuditService.tax_snapshot` 2,285.70 / 5,904.76 (factor 2); Q07 live vs stored TaxLine diverges once in-house stays exist; INV-A05 (stored tax lines) HOLDS; invoice numbering unchanged | Two engines disagree on the taxable base by a factor of two on real production data; one of them is wrong or is measuring a different thing; a GST return built from the wrong one is a statutory error | **B** (must be explained before certification; becomes **A** if a defect) | Phase 6 parity review / Phase 3 |
| FI-11 | W-20 overstay repeat-call bills a further rounded-up hour | Pre-existing, recorded | Double-click over-bills one hour; visible, reversible by correction | **C** (small) | pre-2b package or Phase 3 |
| FI-12 | D11 eight rows and the production `inv-run` verdict | FAIL by design (FD-010); INV-A02/A03 VIOLATED 8/8 | No operational impact; but a certification gate cannot read "OVERALL FAIL" without an explicit ruling on what the verdict means for this population | **E** (disposition B-3, or an invariant population declaration — both explicitly reserved by FD-010 / AR-001) | before G12 |
| FI-13 | Level 3 split billing, company routing | Out of scope (FD-003) | none | **D** | — |

## 2. Authorization / accountability

| # | Item | Current state | Impact | Class | Phase |
|---|---|---|---|---|---|
| AU-1 | Broad authorization coverage (R6: seven guard idioms; `new_reservation`, `bulk_booking`, `checkout`, `walkin` login-only) | Phase 2a frozen and re-verified; rest unchanged | With one Admin user today, nil; with Housekeeping/FrontDesk accounts, any login can post settlements and check guests out | **A if multi-role operation is intended (MP-D9)**, otherwise **C** | Phase 4 (4.2) |
| AU-2 | Reporting authorization (≥26 of 49 report routes login-only) | ADR-009 PROPOSED FOR ADOPTION; classification not done | Financial reports readable by any role | same as AU-1 | Phase 4 |
| AU-3 | Maker-checker (2b.1–2b.4) | void/refund control exists (N2 strength); shift-close approval exists; folio mutations single-actor with audit; ADR-010 PROPOSED | Irreversible folio mutations (transfers, future close) have no second person; for a one-operator property no second person exists | **C** + **E** (MP-D9, B-2) | Phase 2b |
| AU-4 | Operator accountability (ADR-011): rows carry no operator/role/shift; audit rows carry user + IP, not role/business date | Principle adopted (FD-014); storage open | Attribution of a posting to a person requires cross-referencing audit rows; adequate while audit rows exist and are coupled (see FI-2, AD-1) | **C** + **E** (storage: schema vs coupled audit row) | Phase 2b / 3 |
| AU-5 | FD-015 `list_folios` read scope (Accountant, FrontDesk) | Decided, not implemented | Front desk cannot see folios; workflow friction, no integrity impact | **C** (small; already decided) | pre-2b package |
| AU-6 | Scheduler financial actions (AR-013 / FD-009 / B-1): `night_audit_job` posts room rent and advances the date under one setting; `log_pruning_job` deletes audit rows with no switch | No ADR; `night_audit_enabled=false` on production | Unattended financial writer; policy non-compliant | **E** (accept manual night audit as the interim control until B-1) + **A** for the pruning job (see AD-2) | Phase 3 / 4 |

## 3. Database / schema

| # | Item | Current state | Impact | Class | Phase |
|---|---|---|---|---|---|
| DB-1 | SQLite FK enforcement (ADR-005 adopted as requirement; B-9) | OFF in `app/`; 0 orphans on production; explicitly OFF in `production_initialize.py` and the dataset builder | Orphans can only arise through deletes; application deletes are rare and audited; invariants C03/D01/D03/D04 detect orphan financial rows | **C** (with orphan scan + `inv-run` under ON before enabling) | Phase 4/5 (S8) |
| DB-2 | `folio_id NOT NULL` (AR-004 step 5; B-3) | nullable by decision; blocked by the D11 rows | Code-level attribution is fail-closed and INV-A02 monitors; the constraint is belt-and-braces | **D** (after B-3) | Phase 5 (S9) |
| DB-3 | Migration mechanism / single schema authority (B-4): inline registry runs unattended at every boot; Alembic orphaned; `alembic.ini` points at production | Undecided | For a release with **no schema change** (Phase 1 has none) boot is a no-op; for any future schema change, unattended boot-time migration violates FD-007 | **E** (B-4) → **A before the first schema change** | Phase 5 |
| DB-4 | Schema migration rehearsal (PD-005 sequence, PD-006) | Procedure defined (FD-005); no schema migration pending | Not required for a schema-free deployment | **B** (rehearse the *no-op* boot on a copy as part of G11) | deployment rehearsal |
| DB-5 | Production data migration controls (PD-004/005/006; "verified state" B-5) | Definitions in force; "verified state" unconfirmed | No data migration is pending (unit 1.6 has no action) | **E** (B-5) before any mutation; **D** for the release | Phase 5 / 9 |
| DB-6 | Startup safety: `create_app()` runs `_run_pending_migrations`, `init_data()`, starts the scheduler | Structural | See DB-3 and AU-6; a production start is also an unattended writer start | **B** (document and rehearse; confirm no pending migration at the release tag) | deployment rehearsal |

## 4. Recovery

| # | Item | Current state | Impact | Class | Phase |
|---|---|---|---|---|---|
| RC-1 | Backup — operating path | `app/backup_manager.py`: `shutil.copy2` on the live file, encrypted, purged after 30 days, no checksum; `backup_logs` has no integrity column | A hot `copy2` of a live SQLite file can be torn; nothing proves a backup is restorable | **A** (backup-API mechanism + manifest/hash for the operating path — ADR-007 items 1–2) | Phase 9 (or bounded earlier, as Q-6 was) |
| RC-2 | Restore | `tools/restore_db.py` exists (19 tests) for `.db` and `.enc` artifacts; refuses production paths structurally | Restore of a tool-made backup is proven | **B** (re-rehearse at the release tag) | G8 |
| RC-3 | Restore rehearsal | RR-20260908-01 PASS 16/16 for a `tools/backup_db.py` artifact; **no rehearsal of an application-made `.enc` backup** | The backups the operating system will actually have are the untested ones | **A** (rehearse the `.enc` application path with real key custody) | G8 |
| RC-4 | Recovery artifact retention | pre-mutation / pre-update backups subject to the 30-day purge; `../db-backups/` by convention only (B-11) | The backup you need at month two may have been purged | **C** (retention exemption) | Phase 9 |
| RC-5 | Exact historical recovery | tool restore is page-faithful (header bookkeeping bytes only); "verified state" definition (B-5) unconfirmed | Recovery proof exists but its acceptance criterion is not Founder-confirmed | **E** (B-5) + **B** | G8 |
| RC-6 | Encrypted backup considerations | `.enc` keyed from `PII_ENCRYPTION_KEY`/`SECRET_KEY`; restore on another machine needs key custody; `.env` is untracked and was once found inside an archive (secret remediation) | Loss of the key = loss of every encrypted backup | **A** (documented key custody and an off-box restore rehearsal) | G8 |

## 5. Audit

| # | Item | Current state | Impact | Class | Phase |
|---|---|---|---|---|---|
| AD-1 | Strict atomicity | 12/24 writers strict (FI-2) | see FI-2 | **A** | pre-2b |
| AD-2 | Destructive pruning: `_prune_old_logs` deletes `audit_logs` older than 90 days daily at 04:00; first deletion ~2026-11-07 on a running instance | FD-008 / AR-007 make it non-compliant "before production certification"; ADR-012 item 1 proposes the minimal fix (remove `AuditLog` from the loop) — its placement is an open Founder question | Financial provenance deleted on a rolling basis; Phase 2a and D11 evidence rest on these rows | **A** (minimal fix) + **E** (confirm it as a bounded exemption now rather than Phase 4) | bounded directive |
| AD-3 | Audit retention / archival strategy (classes, periods, archive, detection invariant) | ADR-012 PROPOSED; B-6 | Needed for a long-running property; not needed to stop the immediate loss | **C** | Phase 4 / 6 |
| AD-4 | Audit of unattended actors (system identity) | `staff_user_id=0` convention; AR-013 open | Machine postings distinguishable only by the 0 convention | **C** | Phase 3 / ADR-011 |

## 6. Reliability / operations

| # | Item | Current state | Impact | Class | Phase |
|---|---|---|---|---|---|
| RL-1 | Unattended scheduler (night audit, backup, pruning, notification flush, predictive maintenance) starts with `create_app()` | night audit off on production; pruning always on; backup per `setup_backup_scheduler` | see AU-6, AD-2, RC-1 | **A** (pruning) / **E** (night-audit automation vs manual) / **B** (document each job's production setting) | Phase 3/4 |
| RL-2 | Business-date handling at start of operations | production business date 2026-08-10 (unlocked); calendar 2026-09-10 | Day one of operation must set/advance the business date deliberately; every closed-day invariant is anchored to it | **B** (start-of-operations procedure in the deployment rehearsal) + FI-3 | Phase 3 / G11 |
| RL-3 | Startup / deployment safety | `start*.bat`, `update.bat` (pre-update backup, signed update packages with Ed25519 pubkey), installer stamp check that "can never pass" (5.5), nine LF-only launchers (V10, FD-017 exemption approved) | Launchers that may not execute on the operator machine; installer gate defect | **A** (FD-017 fix — tiny; rehearse launchers) + **C** (5.5) | G11 |
| RL-4 | Concurrency (R5: `with_for_update` no-op on SQLite; database-wide write lock) | Documented | Single-property LAN use with few operators serialises correctly; no lost-update evidence | **E** (MP-D4) / **D** for a single small property | Phase 4 |
| RL-5 | Observability (N8 file-log-only; N5 shallow health endpoint polled by the updater; V4 detector failure invisible) | Unchanged | Operational blindness, not integrity | **C** | Phase 4 |
| RL-6 | Offline / central-service implications (MP-D3, Phase 9) | Deployment model undecided; single-box LAN today | No central dependency exists; nothing offline-specific to verify beyond RL-3 | **E** (MP-D3) / **D** | Phase 9 |
| RL-7 | Documentation (`docs/RELEASE.md` cited by code, absent; F7/R9) | absent | Operator cannot follow a release/rollback procedure that does not exist | **A** (deployment + rollback procedure written and rehearsed) | G11 |

## 7. Verification

| # | Item | Current state | Class | Phase |
|---|---|---|---|---|
| VF-1 | Writer coverage | 22/24 runtime; W-07/W-11 after CF-11 fix | **B** (re-run after CF-10/CF-11 on the release tag) | pre-2b |
| VF-2 | Unauthorized-role verification (CF-5) | not run | **B** (run with Phase 4 role sets; today's single role makes it low risk) | Phase 4 / G10 |
| VF-3 | Replay verification | PASS 10/10; control outside ledger (CF-6) | **B** each gate; **D** for CF-6 | G10 |
| VF-4 | Golden Master | `phase1_aa6d9e91` 158/158 adopted; HTML only (V5) | **B** each gate; **C** for Excel/PDF | G10 / Phase 6 |
| VF-5 | Invariants | 26 registered; production 17 HOLDS / 7 VACUOUS / 2 VIOLATED (D11) / INV-R01 NOT_COMMISSIONED | **B** — declared movement only; **C** commission INV-R01 and lift VACUOUS where the rehearsal produces populations | G10 / Phase 6 |
| VF-6 | Six datasets | five registered, all PASS; DS-CORE-WALKIN never declared | **B** (five) / **D** (sixth) | G10 |
| VF-7 | Q14 | AGREED on datasets; DIVERGED by the D11 amount elsewhere | **B** as declared; depends on FI-12 for the production reading | G10 |
| VF-8 | Deployment rehearsal (fresh install, upgrade from the current instance, launchers, boot with no pending migration, multi-day operation with nightly close on a copy, rollback) | never performed | **A** (G11) | G11 |
| VF-9 | Recovery rehearsal (operating backup path, `.enc`, off-box) | RR-20260908-01 only (tool path) | **A** (G8) | G8 |
| VF-10 | Fault injection `fault-run` INCOMPLETE until D7/D9; D7/D8/D10 not built | tooling | **C** (manual certification acceptable) + **E** (accept manual G12 without D7/D10) | Phase 6 |

## 8. Existing defects and findings (K-series and later)

| Item | Assessment | Class |
|---|---|---|
| CF-11 `settle_credit` / `redeem_credit_voucher` | non-functional routes; money cannot be booked through them | **A** |
| W-20 repeat call | one extra rounded hour on a double click | **C** |
| INV-B06 (SR-1) | semantics; invariant noise on real advances | **E** + **B** |
| INV-D02 (SR-2) | semantics; RELEASE_BLOCKING noise on real refunds | **E** + **B** |
| K-1/K-2/K-3 D11 | by decision; certification-verdict question | **E** (FI-12) |
| K-5 non-financial `_write_audit` never raises | architecture, unscheduled | **C** |
| K-7 dating | **A** (FI-3) | Phase 3 |
| K-9 stale business date / audit never nightly | **A** (FI-4, RL-2) | Phase 3 |
| K-10 pruning | **A** (AD-2) | bounded |
| K-11 scheduler | **E** interim manual + **C** | Phase 3/4 |
| K-12 FK | **C** | Phase 4/5 |
| K-13 NOT NULL | **D** | Phase 5 |
| K-14 migration mechanism | **E** → **A** before first schema change | Phase 5 |
| K-15 authorization | **A/C** by MP-D9 | Phase 4 |
| K-16 FD-015 | **C** | pre-2b |
| K-17 `.enc` restore | **A** (RC-3/RC-6) | G8 |
| K-18 masters HTML only | **C** | Phase 6 |
| K-19 INV-R01 / VACUOUS | **C** | Phase 6 |
| K-20 launchers | **A** (tiny, approved) | G11 |
| Q06 GST divergence on production | **B** → possibly **A** | Phase 3/6 |
| DS-CORE-WALKIN | **D** | Phase 6 |
| Governance: four 2026-08-31 rulings unrecovered; AR namespace | **C** (record when the Founder confirms) | Phase 0 |

## 9. Class totals

| Class | Count | Items |
|---|---|---|
| **A** must complete | 12 | FI-2, FI-3, FI-4, FI-9, AD-2, RC-1, RC-3, RC-6, RL-3 (FD-017), RL-7, VF-8, VF-9 (+ AU-1/AU-2 conditional on MP-D9; DB-3 conditional on a schema change) |
| **B** must verify | 14 | FI-1, FI-8, FI-10, DB-4, DB-6, RC-2, RC-5, RL-2, VF-1…VF-7 |
| **C** should complete | 14 | FI-11, AU-3, AU-4, AU-5, DB-1, RC-4, AD-3, AD-4, RL-5, K-5, K-18, K-19, VF-10, governance record |
| **D** safe to defer | 7 | FI-5, FI-13, DB-2, DB-5 (release), RL-4/RL-6 (single property), VF-6 sixth dataset |
| **E** Founder decision | 9 | FI-6/FI-7 semantics, FI-12 D11 verdict, AU-6 interim night-audit mode, AD-2 placement, DB-3 (B-4), DB-5 (B-5), MP-D9, MP-D3/MP-D4, VF-10 manual certification |
