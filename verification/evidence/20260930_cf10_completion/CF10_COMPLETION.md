# CF-10 / CF-11 completion — verification and hardening record

| | |
|---|---|
| Recorded | 2026-09-30 |
| Start HEAD | `d9fa55f` (six CF-10/CF-11 commits ahead of `origin/main` `683db72`) |
| Code HEAD | `61286b7` |
| Authority | Q5-P1 (FOUNDER_DECISIONS.md:1076-1080, strict audit coupling for every financial mutation) · CF-10 · CF-11 · P2-A1 / P2-A2 (`20260910_phase2_entry/PHASE2_SCOPE.md`) · ADR-011 accountability requirement · FD-P2-05 · autonomous continuation directive of 2026-09-30 |
| Production | `instance/pms.db` `51dd83b7…30bc2`, 733,184 B — read-only throughout, SHA-256 identical before and after every run (each result file records it) |
| Numbers | every count here is copied from `RESULT.json`, which `build_result.py` builds from the result files in this directory |

## 1. What was checked

The six commits `74dee9b` → `d9fa55f` were reviewed diff by diff and re-verified from scratch. The harness `verify_cf10_cf11.py` (revision 2 of the 20260929 harness) now:

- runs each group on a disposable copy made by `verification.dbcopy` and records the application commit, whether `app/` was clean, and the production hash in each result file;
- imports `app` from a clean `git worktree` (`CF10_APP_ROOT`) for baseline runs, so the working tree is never swapped; it refuses to run if `app` resolves anywhere else. An early run in this session silently fell back to the repository's own `app` because the worktree path was wrong. The missing commit stamp exposed it, those files were deleted, and the guard was added;
- adds the groups `voucher`, `na` (W-16/W-21) and `actor` (FK-enforced SQLite), plus checkout-route cases for W-24.

| Run | Gates | Result |
|---|---|---|
| `683db72` (pre-CF-10) | 105 / 242 | FAIL — every writer group RED |
| `d9fa55f` (session start) | 220 / 242 | FAIL — `voucher` 5/9, `na` 5/21, `actor` 7/9 |
| `d34d15a` | 220 / 242 | only the savepoint probe changes (below) |
| `5847920` | 224 / 242 | `voucher` 9/9 |
| `c4edc7b` | 240 / 242 | `na` 21/21 |
| **`61286b7`** | **242 / 242** | **PASS** — cf11 48, corr 46, w10 25, voucher 9, w12 16, w13 16, w14 14, w24 38, na 21, actor 9 |

Savepoint probe (`probe_savepoint.py`): FAIL at `683db72` (folio case), FAIL at `d9fa55f` (charge case and folio case), PASS at `d34d15a` and `61286b7` (3/3).

## 2. Defects found and fixed in this session

| Commit | Defect | Class | Fix |
|---|---|---|---|
| `d34d15a` | On SQLite, `session.begin_nested()` issued before any DML sends a SAVEPOINT with no open transaction. SQLite treats it as the outermost transaction, so its RELEASE commits. A W-13 late-checkout charge and both of its audit rows then survived the caller's rollback. That savepoint was **introduced at `d9fa55f`**. The same mechanism let the Phase 1 folio auto-creation commit a folio while its audit rolled back (**pre-existing**). The checkout route calls `post_charge` typically before any DML in its transaction, and later validation failures roll back, so this was reachable in production code. | implementation defect (regression + pre-existing) | `nested_transaction()` opens the real transaction on SQLite before `begin_nested()`; used at both sites |
| `5847920` | A credit voucher (a liability) issued by a `credit_voucher` cancellation was audited through a swallowing `audit_writer`. With the audit failing, the voucher committed unaudited, and the issuance failure itself was never recorded. | residual CF-10 gap (W-10 voucher leg) | strict `voucher_created` inside a savepoint; the existing non-blocking business rule is kept, `voucher_issue_failed` is written strictly, and `cancellation_disposition` names `voucher_id` |
| `c4edc7b` | W-21 `run_night_audit` and W-16 `_rerun_skipped_audit` posted `room_rent` charges with no AuditLog row naming any charge (run-level only) | CF-10 | a strict `posted` audit per charge in the run's single transaction; the manual route passes the operator and records `run_by_user_id` |
| `61286b7` | `noshow_posted` used `staff_user_id = posted_by or 0` even in an operator-initiated night audit. Under FK enforcement the first-release manual close (FD-P2-05) therefore fails whenever a no-show is pending. | accountability / portability defect | `resolve_audit_actor()`, shared with `audited_financial_write`. `posted_by: 'night_audit'` and `NoShowLog.posted_by_user_id` are unchanged. |

No schema change, no data change, no invariant, master or expectation change.

## 3. Writer matrix (directive §6, A–I) at `61286b7`

Every writer: the financial row and its audit rows are flushed in one database transaction, and the audit identifies the financial row by `entity_type` / `entity_id`. Negative paths inject F1 (the AuditLog cannot be constructed) and F2 (the INSERT fails in flush) on a disposable copy only.

| Writer | Financial mutation | Audit rows (strict) | Boundary | Audit failure ⇒ | Positive / negative evidence |
|---|---|---|---|---|---|
| W-08/09 `post_payment_correction` | reversal (+ replacement) Payment | `payment_reversed` / `payment_corrected` on each row | caller route commit | route rolls back, no correction row | corr 46/46 |
| W-22/23 `post_extra_charge_correction` | reversal (+ replacement) ExtraCharge | `charge_reversed` / `charge_corrected` | caller (no app caller exists) | raises | corr |
| W-10 cancellation | refund Payment, disposition stamps, forfeit | `cancellation_refund`, `cancellation_disposition`, `forfeit_approved`, `cancelled` | cancel route single commit | not cancelled, nothing posted | w10 25/25 |
| W-10 voucher leg | CreditVoucher (liability) | `voucher_created`; `voucher_issue_failed` on failure | savepoint inside the cancel transaction | voucher rolled back and failure recorded; if the record also fails, not cancelled | voucher 9/9 |
| W-11 `redeem_credit_voucher` / CF-11 `settle_credit` | Payment, redemption, settled amount | `posted` on the Payment, `voucher_used` | route commit | nothing posted, no HTTP 500 | cf11 48/48 |
| W-12 `complete_full_checkin` | deposit Payment, check-in | `posted` (deposit), `checkin_full` | single commit | check-in refused, rolled back | w12 16/16 |
| W-13 `cico.post_charge` | late/early ExtraCharge + CICOChargeLog | `posted` on the charge; the Reservation row names `extra_charge_id` | savepoint (now SQLite-safe) in the caller's transaction | charge, log and audits rolled back; rest of request commits | w13 16/16, probe 3/3 |
| W-14 no-show | fee ExtraCharge, status | `posted` on the fee; `noshow_posted` names `extra_charge_id` | caller transaction | not a no-show, no fee | w14 14/14, actor A-02/A-03 |
| W-16 rerun skipped | `room_rent` ExtraCharges, log rewrite, reopen row | `posted` per charge (names `night_audit_log_id`) | single commit | stays Skipped, no charge, no reopen row | na W16 |
| W-21 night audit | `room_rent` ExtraCharges, no-shows, NightAuditLog, business date | `posted` per charge (names log, rate source) | single commit | no log, no charge, date unchanged | na W21 |
| W-24 overpayment→upsell | CASE A: rate + `room_upsell` row; CASE B: rate only | `overpayment_converted_to_upsell` in both cases (before/after rate, tariff, branch, charge id); CASE A `posted` on the charge; admin route row before commit | admin route commit / checkout commit | nothing converted (admin); **checkout not completed** (W24-CO-*-B) | w24 38/38, including checkout-route CASE A and B (W24-CO) |

**G. System actor.** Operator paths name the operator at every writer above (`actor` column of each group). Paths with no operator — the scheduler night audit and automated no-shows — resolve to `staff_user_id = 0`. No user 0 exists (production has exactly one user, id 1; all 23 production audit rows carry actor 1).

**F. PostgreSQL semantics.** Every writer uses one transaction plus, at W-13, W-10v and the folio auto-create, a SAVEPOINT that is always inside a real transaction. That is standard PostgreSQL behaviour, and SQLAlchemy savepoints also isolate a failed statement there. **Not executed on PostgreSQL:** no server is installed and the Docker daemon is not running (environmental — NOT-VERIFIED). FK-enforced SQLite is the proxy for the FK behaviour.

## 4. System actor under FK enforcement (directive §8) — `actor` group

| Case | FK-enforced result |
|---|---|
| Operator manual no-show (A-02) | posts; audits accepted |
| Automated no-show, no operator (A-03/A-04) | fails closed with nothing partial; **cannot complete** |
| Scheduler night audit (A-05/A-06) | fails closed, no log, no charge, date unchanged; **cannot complete** |
| Operator manual night audit with a pending no-show (A-08/A-09) | completes after `61286b7`; every audit row names the operator (RED at `d9fa55f`) |

Also relying on the 0 convention outside CF-10, and not exercised here: `routes._write_audit` for unauthenticated requests, `webhook._write_audit` (inbound OTA calls), and `services_group_stay._resolve_actor` (R2A backfill).

**Why this is not fixed here.** Every solution needs a representation decision that ADR-011 item 4 and AR-013 / BACKLOG B-1 leave explicitly **UNRESOLVED**: a seeded non-login system user (a production data insert → PD-004/PD-005), a nullable actor plus an actor-kind column (schema → B-4 migration mechanism, undecided), or a scheduler-controls ADR. None is authorized. FK enforcement itself stays off (ADR-005, not disabled or enabled by this work).

**First-release impact.** With `night_audit_enabled=false` (production, FD-P2-05) and the single-Admin model (FD-P2-01), every financial mutation in the first-release operating model is operator-attributed at `61286b7`, so the open decision does not affect those postings. It does block (a) enabling the scheduler, (b) enabling FK enforcement or moving to PostgreSQL, and (c) the G5 "provenance envelope" condition.

## 5. W-16 / W-21 decision basis (directive §9)

Before the change both writers were atomic by construction: a single commit, with rollback on any exception (code review). There was no charge-level audit row that could fail, however. In the `d9fa55f` baseline runs the injected audit faults found nothing to hit, and the run completed and committed its charges with no AuditLog naming any of them (`na` W21-B/W16-B RED). They were therefore not strict under Q5-P1. P2-A1 left "record as accepted or add per-row rows" to the implementing directive. Per-row rows were chosen as the reading consistent with Q5-P1's "all financial mutations". This adds no policy: closed historical days are untouched, and only future runs write the extra rows (Golden Master and replay unchanged, §6).

## 6. Regression at `61286b7` (Layers 4–8)

| Layer | Result |
|---|---|
| Golden Master `phase1_aa6d9e91` | PASS — 158/158 clean, 0 differences (`20260930_024153_gm_verify_phase1_aa6d9e91`) |
| Replay `production` | FAIL — **expected, governed**: exactly the two Q06-H2 forward-fix deltas (`nas.tax_snapshot.total_taxable` 2026-08-09 BLOCK 2285.7→1142.85, 2026-08-10 INFO 5904.76→2952.38). Identical to `20260923_155240` (the Q06 fix pack). The stored baseline is not re-frozen (Q06-H1/H3). |
| inv-run `production` | FAIL — **declared exception only**: INV-A02 / INV-A03 violating objects are exactly payments 1–6 and extra_charges 1–2 (the FD-P2-03 D11 set). Every invariant is record-identical to `20260923_155256`; 0 writes. |
| cross-implementation | FAIL — 15 AGREED, 4 DIVERGED (Q06, Q14, Q17, Q20), Q01 SINGLE_SOURCE, Q11/Q21 VACUOUS. Record-identical to `20260923_155322`. Q06 per-date divergences are empty (Q06_REGRESSION §6); Q14 is the D11 ₹476.19. |
| Phase 1 writers (`verify_writers.py` A/B/C/D) | 89/89 · 48/48 · 15/15 · 46/46. Its non-gating "A0 / A-NF" notes are hard-coded Phase 1 inventory labels, not measurements; superseded by §3. |
| Phase 2a authorization matrix | 29/29 PASS |
| Q06 fix | 15 PASS / 0 FAIL |
| Retention control (FD-P2-02) | 18/18 |
| Phase 1 execution | 44/44 |
| W-20 runtime | 23/23 (the first run failed on a cp1252 console encoding — an environment defect; re-run with UTF-8 output) |
| `tools/test_restore_db.py` | 19 tests OK |

The regression scripts were run as verbatim copies (`reg_*.py`) from this directory so they could not overwrite their original packs; their outputs are under `regression_logs/`. In `verify_writers_setA.log` and `verify_writers_setD.log`, fields matching production guest records (one phone number, 15 occurrences, from notification warnings) were replaced with `[REDACTED-PRODUCTION-GUEST-FIELD]` after the run. Nothing else in this pack contains a production guest field (scanned against every guest phone, email and name).

## 7. Untracked evidence found at session start

- `20260929_cf10_cf11_hardening/results_*.json` — produced by the previous session, with mixed harness revisions. Committed now with a provenance `README.md`, unedited.
- `20260929_174454_{cross_implementation, gm_verify_phase1_aa6d9e91, inv_run_production, replay_verify_production}` — genuine PVF packs (read-only proven). They were produced at 23:14 IST on 2026-09-29, **before** the first of the six commits (23:22), so they cannot be attributed to any commit. Their results are record-identical to the `20260930_02…` packs. They are committed as **unattributed and superseded** by the `20260930_02…` packs taken at `61286b7`.

## 8. Status after this work

| Item | Status | Basis |
|---|---|---|
| CF-10 | **PASS** — all 12 CF-10 writers plus the voucher leg strict; 24/24 writers strict with runtime evidence | §1, §3 |
| CF-11 | **PASS** — `settle_credit` and `redeem_credit_voucher` functional, audited, fail closed | cf11 48/48 |
| Q06 | code **PASS** (Q06-H2 at `60abea6`); historical record preserved, untouched (Q06-H1/H3) | replay §6 |
| G3 Financial integrity | **OPEN** — coupling, CF-11 and Q06 done; K-7 business-date dating (Phase 3) and SR-1/SR-2 implementation (FD-P2-06 directive) remain | CERTIFICATION_GATES.md G3 |
| G5 Auditability | **BLOCKED** — coupling done, pruning stopped (FD-P2-02); the provenance envelope needs ADR-011 storage and system-actor decisions | §4 |
| G11 Deployment rehearsal | **OPEN** — never performed; depends on G3/G5/G6/G8/G9 | — |
| G12 Certification | **NOT-VERIFIED** — not reachable while G3/G5/G6/G8/G11 are open | — |

## 9. Founder decisions this work surfaces

1. **System actor representation** (ADR-011 item 4, AR-013, B-1): a seeded system user, or an actor-kind column, or another mechanism. It blocks the scheduler, FK enforcement / PostgreSQL, and G5.
2. **ADR-011 storage location** of the provenance envelope (schema columns vs the coupled AuditLog `after_state`). The CF-10 audit rows now provide option (b)'s coupling everywhere; role snapshot and `shift_id` are not captured.

## 10. Files

`verify_cf10_cf11.py` harness · `probe_savepoint.py` · `summarize.py` · `build_result.py` · `RESULT.json` · `results_{base_683db72,base_d9fa55f,green_61286b7}_<group>.json` · `probe_savepoint_*.json` · `per_commit/` (intermediate commits) · `regression_logs/` · `reg_*.py` (verbatim copies of earlier suites).
