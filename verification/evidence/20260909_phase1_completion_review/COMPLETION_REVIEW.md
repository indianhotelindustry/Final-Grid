# FinalGrid Phase 1 - Completion / Review Gate

| | |
|---|---|
| Directive | FG-P1-COMPLETION-REVIEW-20260909-01 (read-only review) |
| Reviewed | 2026-09-09 |
| Baseline | `aa6d9e91e7294be731383f755d6998acf5f059fc` on `main`, pushed; `origin/main` identical |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` |
| Production anchor | `instance/pms.db` 733,184 B - SHA-256 `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` (unchanged through every Phase 1 step and this review) |
| Method | Read-only. Evidence packs, governance records and the committed tree at `aa6d9e91` were read; the committed `app/` tree was re-scanned with `ast` for financial constructors; no harness command was executed; no file outside this directory was written |
| Result | **PHASE 1 COMPLETION REVIEW PASS - BASELINE aa6d9e91 ASSESSED** |
| Determination | **PHASE 1 COMPLETE WITH CARRY-FORWARD ITEMS** (option B) |

Companion artifacts in this directory: `REQUIREMENT_MATRIX.md` (section 1), `DEFERRED_ITEMS.md` (section 4), `PHASE2_READINESS.md` (section 7), `result.json`.

## 0. Inputs reconciled

| Input | Location | Governs |
|---|---|---|
| Phase 1 execution plan and readiness set | `evidence/20260908_phase1_implementation_readiness/` (S0-S7 in Phase 1; S8-S9 outside; writer inventory W-01..W-24; verification plan) | what Phase 1 had to deliver and how it had to be proven |
| Founder rulings | `FOUNDER_DECISIONS.md` FD-001..FD-019; Round 2 Q-1..Q-6; AR-001..AR-015; ADR-001/002/003/004/005/007/008 ADOPTED | boundaries and required behaviours |
| Golden Master (pre-Phase-1) | `evidence/20260908_golden_master/` + packs `20260909_0056xx` | baseline, known defects K-1..K-20, expected deltas E-1..E-10 / N-1..N-12 |
| Phase 1 execution evidence | `evidence/20260909_phase1_execution/` (44/44 cases) + packs `20260909_0130xx`..`0135xx` | what was delivered and measured |
| W-20 runtime closure | `evidence/20260909_w20_runtime/` (23/23) | runtime proof of the one writer the execution disclosed as vacuous |
| Recovery Foundation | `evidence/20260908_recovery_foundation/` (19/19 tests; RR-20260908-01 PASS) | recovery regression |
| Release history | commits d15d848e, 34307c37, 6cd2ac6d, 95083995, aa6d9e91; `evidence/20260909_five_commit_execution/` | the committed code under review |

## 1. Scope reconciliation - summary

Full matrix in `REQUIREMENT_MATRIX.md`. Of the 18 named assessment points, **18 are DELIVERED**; 4 of them carry a verification-completeness qualification (runtime coverage breadth, new-activity `inv-run`, dataset regression, Phase 2a matrix re-run) that is recorded as carry-forward rather than as a defect.

Independent checks performed by this review against the committed tree (not taken from the reports):

- `ast` scan of every `.py` under `app/` at `aa6d9e91`: **33 `Payment(`/`ExtraCharge(` constructor sites, 33 carry `folio_id=`, 0 without** (routes 11, services 9, seed 5, dev_seed 4, cico 1, noshow 1, pos 1, reports 1). Matches the execution report's T-W01/T-W02 claim.
- `resolve_billing_folio` (services.py:53) is deterministic (letter A of the row's own reservation), fails closed on `None`/unknown reservation, creates a missing folio A inside a SAVEPOINT and writes `folio_auto_created` through the strict helper; `inherit_billing_folio_id` (services.py:147) raises on a NULL original; `audited_financial_write` (services.py:172) flushes and raises `AuditCouplingError` on failure. Matches Q-1, Q-2, Q-5.
- `app/pos.py` diff: charge and audit now flush in one transaction, single commit, rollback + HTTP 500 / flash on any failure. K-6 closed.
- `routes.py` hunks touch exactly `bulk_booking_api`, `new_reservation`, `checkout` (x7 hunks), `add_payment`, `walkin_search_express`, `settle_credit`, `add_overstay_charge`, plus the two new helpers; W-01/W-06/W-07 gained audit rows they lacked (K-5 for touched writers).
- `services.py` hunks touch exactly `run_night_audit`, `convert_overpayment_to_upsell`, `post_cancellation_disposition`, `post_extra_charge_correction`, `post_payment_correction`, `redeem_credit_voucher`, `CheckInService`, plus the foundation block. `reports.py` (`_rerun_skipped_audit`), `noshow_service.py`, `cico_service.py`: one `folio_id=resolve_billing_folio_id(...)` each.
- `NightAuditService.attribution_control()` (night_audit_service.py:716) reports reservation view, folio view and an **own** unattributed bucket, flags misrouting as `danger`, disagreement as `danger`, a non-zero unattributed bucket as `warning`, and never nets D11 into the folio view.
- Boundary: `app/models.py`, `app/folio.py`, `migrations/`, templates unchanged between `e69f2ac` and `aa6d9e91`; `folio_id` still `nullable=True` on both tables; no `PRAGMA foreign_keys` in `app/`; `_FOLIO_ROLES['folio.list_folios']` still `('Admin','Manager')`; `_prune_old_logs` still scheduled. Nothing outside `app/`, `tools/`, `verification/` changed in the five commits.

## 2. Expected vs actual Golden Master deltas

Recorded result (packs `20260909_013003`, `013202`, `013502` - three runs, identical): **158 compared, 157 clean, 4 differences, all on `main.night_audit`**.

| Difference | Master -> current | Attributable to |
|---|---|---|
| `panel_ui.attribution[len]` FIGURE_ADDED | - -> 8 | E-6: the new attribution status row |
| `panel_ui[len]` | 24 -> 25 | same row |
| `panel_ui.warn_conditions` | 1 -> 2 | the eight D11 rows now raise the intended `warning` (attribution_control state) |
| `panel_ui.total_issues` | 1 -> 2 | consequence of the warning |

Assessment: **correctly classified as expected.** All four are on the single surface E-6 predicted, all are consequences of one control, none is `danger`, and no other surface moved (E-10 satisfied). The `warn_conditions` increase is not a regression: it is the control doing what EXPECTED_PHASE1_DELTAS E-6 / the readiness report section 12 required - the unattributed D11 bucket surfaced as a warning, not averaged away. `gm-verify` will report FAIL with these four declared differences until the master is re-baselined at or after `aa6d9e91`; that re-baseline is a verification-only act (Q-4 precedent) and is listed as a Phase 2 gate. The Golden Master was **not** recaptured or modified by this review.

Deviation handled during execution (execution report section 6): the control was first placed inside `folio_control`, which is a replay `NAS_SECTIONS` member, and `replay-verify` reported 320 differences (pack `013008`). It was moved to its own section `attribution_control`, replay returned to PASS 0 differences (packs `013158`, `013458`), and T-N02b/T-N02c pin the placement. This review confirms `attribution_control` is absent from `verification/replay/engines.py::NAS_SECTIONS`. Correct resolution; the consequence (the new figure is outside replay coverage) is recorded as a carry-forward for the ledger, not a defect.

## 3. Invariant status

Recorded post-Phase-1 production result (pack `20260909_013500`): 26 registered - 17 HOLDS - 7 VACUOUS - 2 VIOLATED - INV-R01 NOT_COMMISSIONED - overall FAIL. This review diffed the SUMMARY block against the pre-Phase-1 Golden Master pack (`005620`) and the first post-Phase-1 pack (`013001`): **byte-identical**. N-1 satisfied.

| Item | A. Expected baseline | B. Phase 1 unfinished | C. Deferred by decision | D. New Phase 1 regression |
|---|---|---|---|---|
| INV-A02 VIOLATED 8/8, 4,776.19 | **Yes** - the eight D11 rows are preserved unattributed by FD-010 Option A; AR-001 keeps the invariant universal, so it must keep reporting them | No - unit 1.6 has no authorized action | Disposition beyond FD-010 is a separate Founder decision at Phase 5 (B-3) | **No** - identical to baseline |
| INV-A03 VIOLATED, 476.19 | **Yes** - the two D11 late-checkout charges are unreachable through a folio; same cause | No | as above | **No** |
| INV-R01 NOT_COMMISSIONED | **Yes** - K-19; the engine excludes it from the verdict | No - commissioning is Wave 0 / Phase 6 harness work | Phase 6 | **No** |
| 7 VACUOUS (A06, C01, C05, C06, D02, D05, D07) | **Yes** - populations empty on this database (K-19) | No | Phase 6 (dataset/commissioning) | **No** |
| Overall FAIL | **Yes** - the documented and expected outcome of FD-010 (FD-010 consequence paragraph; EXPECTED_PHASE1_DELTAS N-1) | No | An invariant population declaration / amendment is a separate Founder decision explicitly **not** made by FD-010 or AR-001 | **No** |

**D is empty.** No invariant moved. What Phase 1 was expected to change on a *new-activity copy* (E-9: INV-A02/A03 HOLDS) is evidenced indirectly (T-N01..T-N08 show the folio and reservation views reconcile and the only unattributed rows are D11) but the invariant engine itself was not run on a new-activity copy - carried forward (section 6, CF-2).

## 4. Known defects and deferred items

Full classification in `DEFERRED_ITEMS.md`. Headline: K-4, K-5 (touched writers), K-6 CLOSED BY PHASE 1; K-1/K-2/K-3 NO ACTION REQUIRED at Phase 1 (expected baseline under FD-010) with the eight-row disposition DEFERRED TO PHASE 5 / Founder decision B-3; K-7 (business date), K-9, K-11 (scheduler) DEFERRED TO PHASE 3; K-10 (audit pruning, exposure ~2026-11-07) REMAINS OPEN pending ADR-012 / B-6; K-12 (FK), K-13 (NOT NULL), K-14 (migration mechanism) DEFERRED TO PHASE 4/5; K-15 (authorization) DEFERRED TO PHASE 4; K-16 (FD-015 `list_folios`) REMAINS OPEN - decided, awaiting a bounded implementation directive; K-17 (encrypted backup restore) REMAINS OPEN under B-11; K-18/K-19/K-20 NO ACTION REQUIRED for Phase 1. Maker-checker DEFERRED TO PHASE 2b (B-2 ADR needed).

## 5. Phase 1 boundary - confirmed

| Must not have happened | Evidence | Result |
|---|---|---|
| Schema migration | `migrations/` unchanged; `app/models.py` unchanged; schema fingerprint `a7428da6...` unchanged (execution report); this session's own fingerprint identical across 9 readings | **Not done** |
| `folio_id NOT NULL` | `models.py:772`, `:806` still `nullable=True` | **Not done** |
| FK enforcement migration | no `PRAGMA foreign_keys` in `app/`; only ORM `foreign_keys=` relationship arguments match | **Not done** |
| Broad authorization changes | `_FOLIO_ROLES` unchanged; no route decorator changes in the diff; FD-015 still unimplemented | **Not done** |
| Maker-checker workflow | no approval path added | **Not done** |
| Business-date redesign | wall-clock sites W-08/09/10/11/17/20/22/23 unchanged (W-20 closure section 11.3 confirms `now.date()` still used) | **Not done** |
| Destructive audit pruning change | `_prune_old_logs` present and unchanged | **Not done** (and, correctly, not "fixed" either) |
| Historical D11 mutation | ids/amounts/`folio_id NULL` identical in every pack; anchor unchanged | **Not done** |
| Level 3 split billing | resolver hard-codes letter A; never selects B; no company routing | **Not done** |

No contrary evidence found. One in-scope behaviour change beyond attribution is noted for completeness: `add_overstay_charge`'s reservation-level `overstay_charged` audit row, previously written after `commit()` and discarded, now survives. This is the Q-5 coupling applied to a touched writer (execution report section 1 "Also fixed, in scope"); it changes audit-log volume on that path only and is proven by W20-10.

## 6. Regression review

| Check | Finding |
|---|---|
| New failures | None. 44/44 Phase 1 cases; 23/23 W-20; 19/19 recovery suite re-run at execution; app boots with 298 routes (baseline 298) |
| Unexplained Golden Master differences | None - four differences, all enumerated and attributed (section 2) |
| Replay drift | None in the final state - PASS 10/10, 0 differences (`013158`, `013458`). The intermediate 320-difference FAIL (`013008`) was caused by the first placement of the control and was corrected before commit; it is fully explained in the execution report |
| Financial-row duplication | No evidence of any: T-R02 (night-audit rerun posts nothing); W20-17/18 (billed window never re-billed; no duplicate folio). The W-20 repeat call *did* create a second charge for the *new* elapsed window - recorded as pre-existing route semantics untouched by Phase 1 (billing arithmetic byte-identical), not duplication |
| Audit mismatch | None: T-A01..T-A04 and W20-13..16 prove rollback of both row and audit on injected failure; W20-07..09 prove the audit row carries the same folio and amount as the charge |
| Folio mismatch | None: T-L06 (B never selected), T-N07 (0 misrouted), T-N08 (control proven capable of failing on a misrouted row), W20-04..06 |
| Changed production data | None - anchor `51dd83b7...` / 733,184 B identical at every checkpoint, including this review |
| Changed schema | None (section 5) |
| Changed D11 state | None - payments 1-6 (800/400/1500/1000/500/100), charges 1-2 (380.95/95.24), total 4,776.19, all `folio_id NULL`, in every pack and in this session's readings |

**W-20 assessed separately, as runtime verification of the actual route.** The execution report disclosed T-W20 as vacuous (fixture never met the Hourly-only precondition). The closure exercised `POST /reservation/6/overstay-charge` through the real handler on a copy with a corrected fixture, reproduced the vacuous condition as a negative case (W20-01), and proved attribution (folio 6 = A of reservation 6), audit coupling (row + audit committed together; injected failure commits neither and returns 500), marker semantics and D11/production safety. No application code changed. Three limitations are recorded honestly: repeat-call bills the newly elapsed hour (product rule, out of scope), the waive path's audit-after-commit is untouched (not a financial writer), and the charge date is wall-clock (K-7, Q-3). The vacuous gap is closed; the closure introduces no new finding against Phase 1.

**Verification-completeness gaps found by this review (carry-forward, not regressions):**

| # | Gap | Plan reference | Why it is not blocking |
|---|---|---|---|
| CF-1 | Only 6 of 24 writers were exercised at runtime (W-05, W-08, W-13, W-15, W-20, W-21); the other 18 are proven by the `ast` sweep (33/33) and by the resolver's own 14 lifecycle cases. Audit-failure injection covered W-05, W-15, W-20 only. | VERIFICATION_PLAN section 2 T-P01..T-P12 / T-C01..T-C09, T-A01 "at each touched writer"; T-R03 (upsell) and the skipped-audit rerun have no runtime case | Every site is a one-argument call into the same resolver; the static proof is exhaustive and the resolver is fail-closed. Residual risk is a per-site wiring error (e.g. wrong reservation object passed) that only a runtime case would catch |
| CF-2 | `inv-run` was not executed on a new-activity copy to show INV-A02/A03 (and B01-B03 after a close) HOLD | VERIFICATION_PLAN section 2 slice 4, section 3, section 6; EXPECTED_PHASE1_DELTAS E-9 | T-N01..T-N08 and T-R01 establish the same facts by direct query on the copy |
| CF-3 | `ds-run` / `ds-coverage` over the six D6 datasets not run; Q14 parity not recorded | VERIFICATION_PLAN section 4, slice 7 gate | Datasets measure fixtures, not production; seed fixtures were brought under contract (CD-4) |
| CF-4 | Phase 2a 29-case matrix not re-run at `aa6d9e91` | Standing rule G-3 / Gate B | `app/folio.py` byte-identical; no role or endpoint changed; risk is indirect only |
| CF-5 | T-N02 (unauthorized role per writer -> refused, no row) not evidenced | VERIFICATION_PLAN slice 3 negative tests | No authorization changed; today's role sets are unchanged by construction |
| CF-6 | `attribution_control` is outside replay `NAS_SECTIONS`, so the new figure has no historical-replay coverage | execution report section 6 | Deliberate, to avoid rewriting the stored ledger (Phase 6 work) |
| CF-7 | Governance index not extended: `FOUNDER_DECISIONS.md` ends at Round 2; FG-P1-EXEC-20260909-01, the Golden Master directive, the W-20 closure and the release-history directives exist only as evidence directories; Phase 1 acceptance is not recorded | FD-018 durable governance records; MASTER_PLAN overlays end at section 16 | This review is forbidden from editing governance records; the commits and evidence are durable in git |

## 7. Phase 2 readiness

Determination: **B - COMPLETE WITH EXPLICIT CARRY-FORWARD ITEMS.** Gates in `PHASE2_READINESS.md`. Phase 2 implementation is **not** authorized by this review.

## 8. PARTNER — HAVE A LOOK AT:

1. **Phase 1 is committed and pushed, not deployed.** The production anchor is unchanged, which also means the *running* instance (if any) still executes pre-Phase-1 code and would keep writing NULL-`folio_id` rows until the release is installed. Any such rows created before deployment become "legitimate existing data" that would need the MIGRATION_AND_DATA_PLAN section 3 classification. Release timing is a Founder call (MP-D3 / PD-* controls), not a Phase 1 debt.
2. **Verification breadth (CF-1..CF-5).** The plan called for a runtime case per writer, `inv-run` on a new-activity copy, the six datasets and the Phase 2a matrix. Delivered evidence is strong but narrower. Decide whether the static 33/33 proof plus six runtime writers is accepted as Phase 1's completion standard, or whether a bounded verification-completion directive runs before Phase 2. This review recommends the latter (read-only, copies only, no code).
3. **Golden Master re-baseline at `aa6d9e91`.** `gm-verify` now carries four permanent declared differences. A verification-only recapture (Q-4 precedent) would give Phase 2 a clean Gate G. Needs an authorization; no code or data change.
4. **Audit-log pruning exposure date (~2026-11-07).** Unchanged by Phase 1 and correctly so, but FD-008 makes it non-compliant and ADR-012 / B-6 still has no implementation directive. The date is now about two months away on a running instance.
5. **W-20 repeat-call semantics.** An immediate second click bills a further rounded-up hour. Pre-existing, untouched, recorded in the closure. A product-rule question, not a Phase 1 defect.
6. **Governance index (CF-7).** The four 2026-09-09 directives and the five-commit release are not indexed in `FOUNDER_DECISIONS.md` / `MASTER_PLAN.md`. Recording Phase 1 acceptance there is the natural place to close this review.

Not raised, because existing rulings settle them: the eight D11 rows (FD-010, Q-2; next decision belongs to Phase 5 / B-3), business-date defects (Q-3 -> Phase 3), FK / NOT NULL (Phase 4/5), FD-015 (decided; implementation directive pending), scheduler controls (B-1, Phase 3/4), maker-checker (B-2, Phase 2b), MP-D9 (standing open decision that is Phase 2b's own entry condition).

## 9. What this review did not do

No harness command (`inv-run`, `gm-verify`, `replay-verify`, `ds-run`, test suite) was executed; results are taken from the retained packs and cross-checked for internal consistency. No application code, schema, database, fixture, ledger, Golden Master, governance record, ADR or git object was modified. Nothing was committed or pushed. This directory is untracked.
