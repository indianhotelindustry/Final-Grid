# FinalGrid Phase 1 — Financial Foundation · Completion Report

| | |
|---|---|
| Directive | FG-P1-EXEC-20260909-01 |
| Executed | 2026-09-09 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| Starting HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` |
| Ending HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` — **unchanged; no commit, no push** |
| Production database | `instance/pms.db` — 733,184 B · `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` — byte-identical before and after |
| Verdict | **PHASE 1 PASS — READY FOR REVIEW** |
| Authorization consumed | Slices S0, S2–S7. **S8 (FK enforcement) and S9 (NOT NULL) not executed** — outside this authorization. |

---

## 1. What changed

One architectural idea, applied at every financial writer:

> **Reservation operational ownership + folio financial ownership.** The
> reservation remains the operational source for the stay and the room-rate
> entitlement; the resulting financial transaction belongs to the
> reservation's billing folio.

| Change | Detail |
|---|---|
| Attribution foundation | `app/services.py` — `resolve_billing_folio()` / `resolve_billing_folio_id()`. Deterministic (always folio A of the row's own reservation), idempotent, concurrency-safe (SAVEPOINT + `uq_folio_letter`), **fail closed** (raises `FolioResolutionError`; never returns `None`), and auditable when it must create the folio. |
| Missing-folio lifecycle (Q-1) | A valid reservation with no folio A — reachable only via raw SQL or an import — gets one created under the same rule as the ORM listener, with a `folio_auto_created` audit row in the same transaction. If it cannot be established safely, the posting fails. |
| Correction inheritance (R-3) + Q-2 | `inherit_billing_folio_id()`. Corrections inherit the original's folio; a correction of an **unattributed** original is **refused**. On production the only unattributed originals are the eight D11 rows, so this enforces FD-010 in code as well as by rule. |
| Strict audit coupling (Q-5) | `audited_financial_write()` raises `AuditCouplingError` when the audit row does not reach the session; `routes._write_audit_strict()` wraps it. The shared `_write_audit` is **unchanged** for every other caller — the stricter rule is applied only to Phase 1 financial writers, the pattern Phase 2a established. |
| POS ordering (Q-5) | `app/pos.py` — the charge was committed first and the audit attempted afterwards with its exception swallowed. Charge and audit now flush in one transaction and commit together; on failure everything rolls back and the caller is told, instead of seeing a success. |
| Room revenue (AR-002) | Night audit, skipped-audit recovery and overpayment→upsell now attribute their `room_rent` / `room_upsell` rows. Idempotency, business dates and folio-balance semantics unchanged. |
| Reconciliation (unit 1.7) | `NightAuditService.attribution_control()` — the folio-attributed view of the money beside the reservation-level view, with the unattributed (D11) rows in their **own** bucket, never netted in and never shown as compliant folio activity. Surfaced as a night-audit status row. |
| Fixtures (CD-4) | `app/seed.py` attributes its rows, so a seeded database is no longer a standing counterexample to INV-A02. |
| Also fixed, in scope | `add_overstay_charge` wrote its audit row **after** `commit()`, into a session that was never committed again — the row was discarded at teardown. Both audit rows now precede the commit. |

## 2. Files changed — exact

**554 insertions, 45 deletions across 8 application files.** No schema, no migration, no template, no static asset, no `instance/`, no launcher.

| File | ± | What |
|---|---|---|
| `app/services.py` | +258/-8 | Foundation (resolver, inheritance rule, strict audit helper); 7 writers attributed |
| `app/routes.py` | +142/-24 | `_billing_folio_id` / `_write_audit_strict` helpers; 11 writers attributed + coupled |
| `app/night_audit_service.py` | +116 | `attribution_control()` + status row |
| `app/pos.py` | +57/-13 | Attribution + atomic charge/audit commit |
| `app/seed.py` | +15 | `_folio()` helper; 5 fixture sites |
| `app/reports.py` | +5 | Recovered room rent attributed |
| `app/noshow_service.py` | +3 | No-show fee attributed |
| `app/cico_service.py` | +3/-1 | Early/late charge attributed |

New evidence (untracked): `verification/evidence/20260909_phase1_execution/` — `verify.py`, `result.json`, `existing_data_classification.json`, this report.

> **Line-ending note.** `app/routes.py` is CRLF in the repository. An intermediate step normalised it to LF, which made the whole file appear changed; it was restored to CRLF, so the diff now shows only the 41 edited lines. No other file's line endings were altered.

## 3. Writer coverage — all 24, none silently omitted

Re-enumerated from the current tree with `ast` (not text matching, so the `Payment(...)` mention inside `voucher_redeem`'s docstring is not miscounted as a writer). **33 financial constructor call sites across 14 modules — every one sets `folio_id`.**

| ID | Site | Disposition |
|---|---|---|
| W-01 | `routes.py` `bulk_booking_api` | **Updated** — R-1 + audit row added (had none) |
| W-02 | `routes.py` `new_reservation` | **Updated** — R-1 + strict |
| W-03 | `routes.py` `checkout` (OTA settlement) | **Updated** — R-1 + strict |
| W-04 | `routes.py` `checkout` (settlement loop) | **Updated** — R-1 + strict |
| W-05 | `routes.py` `add_payment` | **Updated** — R-1 + strict |
| W-06 | `routes.py` `walkin_search_express` | **Updated** — R-1 + audit row added (had none) |
| W-07 | `routes.py` `settle_credit` | **Updated** — R-1 + audit row added (had none) |
| W-08/09 | `services.py` `post_payment_correction` | **Updated** — R-3 inherit + Q-2 refusal |
| W-10 | `services.py` `post_cancellation_disposition` (refund) | **Updated** — R-4 / CD-3 |
| W-11 | `services.py` `redeem_credit_voucher` | **Updated** — R-1 |
| W-12 | `services.py` `complete_full_checkin` (deposit) | **Updated** — R-1 |
| W-13 | `cico_service.py` `post_charge` | **Updated** — R-1 |
| W-14 | `noshow_service.py` `process_reservation_noshow` | **Updated** — R-1 |
| W-15 | `pos.py` `post_charge` | **Updated** — R-1 + ordering fixed |
| W-16 | `reports.py` `_rerun_skipped_audit` | **Updated** — R-2 |
| W-17 | `routes.py` `checkout` (extra charge) | **Updated** — R-1 + strict |
| W-18 | `routes.py` `checkout` (tip) | **Updated** — R-1 + strict |
| W-19 | `routes.py` `checkout` (other income) | **Updated** — R-1 + strict |
| W-20 | `routes.py` `add_overstay_charge` | **Updated** — R-1 + strict; post-commit audit fixed |
| W-21 | `services.py` `run_night_audit` (room rent) | **Updated** — R-2 |
| W-22/23 | `services.py` `post_extra_charge_correction` | **Updated** — R-3 + Q-2 |
| W-24 | `services.py` `convert_overpayment_to_upsell` | **Updated** — R-2 |
| F-01 | `folio.py` `create_folio` | **Untouched** — Phase 2a, frozen |
| L-01 | `models.py` listener | **Untouched** — remains the creation point |
| — | `seed.py` ×5, `dev_seed.py` ×4 | **Updated / already compliant** (CD-4) |

Intentionally exempt: none. Blocked/escalated: none.

## 4. Verification — 44/44 Phase 1 cases pass

`verify.py`, run against a `make_copy()` disposable copy; production hashed before and after.

| Group | Cases | Result |
|---|---|---|
| S2 lifecycle | T-L01…T-L15 (14) | Existing folio returned; id accepted; idempotent under repetition; folio B never selected; missing folio created **and audited**; second call reuses it; `None`/unknown reservation fail closed; audit helper persists and fails closed |
| S3a coverage | T-W01, T-W02 | Every enumerated writer sets `folio_id`; **33 sites scanned, 0 without it** |
| S3b runtime | T-W05, T-W13, T-W15, T-W20, T-W08, T-Q02 | `add_payment`, CICO, POS attribute to folio A; correction inherits; **correction of a D11 row refused** |
| S3c audit coupling | T-A01…T-A04 | Injected audit failure → payment **not** committed, POS charge **not** committed, both callers receive a failure status |
| S4 room rent | T-R01, T-R02, T-R04 | Night audit posts room rent attributed to folio A on the business date; rerun posts no duplicate; folio balance still excludes room revenue |
| S5 reconciliation | T-N01…T-N08 | Control present as its own section; `folio_control` keys unchanged; views reconcile; unattributed bucket **is exactly** the D11 ids; flagged `warning`, not clean; ₹4,776.19 reported separately; 0 misrouted; **control proven capable of failing** (misrouted row → `danger`) |
| D11 + production | T-D01…T-D04, T-P01 | Id sets and amounts unchanged; production hash unchanged |

Regression: recovery-tool suite **19/19 OK**; application boots with **298 routes** (baseline 298).

## 5. Production verification results

| Check | Result | Expected? |
|---|---|---|
| `selfcheck` | READ-ONLY VERIFIED | ✅ |
| `inv-run` | **FAIL** — 26 registered · 17 HOLDS · 7 VACUOUS · 2 VIOLATED · INV-A02 8/8 ₹4,776.19 · INV-A03 ₹476.19 · INV-R01 NOT_COMMISSIONED | ✅ **Identical to the Golden Master baseline.** N-1: the eight rows are untouched, so production stays FAIL by design |
| `replay-verify` | **PASS** — 10 dates, 10 clean, **0 differences** | ✅ N-12 |
| `gm-verify` | FAIL — **157/158 surfaces clean, 4 differences, all on `main.night_audit`** | ✅ E-6/E-10 |
| `foreign_key_check` (diagnostic) | 0 violations | ✅ |
| Schema fingerprint | `a7428da6840e79dd…` unchanged | ✅ N-6 |

### Golden-master delta analysis — every difference accounted for

| Key | Master → current | Cause |
|---|---|---|
| `panel_ui.attribution[len]` | — → 8 | The new attribution status row (E-6) |
| `panel_ui[len]` | 24 → 25 | Same row |
| `panel_ui.warn_conditions` | 1 → 2 | The eight unattributed D11 rows now raise a review note — the intended §12 behaviour |
| `panel_ui.total_issues` | 1 → 2 | Consequence of the above |

**No unexpected differences.** All four are on the single surface `EXPECTED_PHASE1_DELTAS.md` E-6 predicted, are non-blocking review notes (not `danger`), and no other surface moved.

## 6. One deviation found and corrected during execution

The reconciliation control was first added as a key **inside** `folio_control()`. `replay-verify` then reported **320 differences** across all 10 dates — 310 `ENGINE_FIGURE_ADDED` plus 10 `folio_control[len]` 23→24. No stored figure changed *value*; the D3 replay ledger captures the sections named in `verification/replay/engines.py::NAS_SECTIONS`, and `folio_control` is one of them, so adding a key changed every historical figure set. That contradicted declared delta **N-12** ("the 10 stored August dates reconstruct identically").

Rather than re-baselining the replay ledger — which would rewrite stored evidence and is Phase 6 work — the control was moved to its **own** report section (`attribution_control`), which is not in `NAS_SECTIONS`. Replay returned to **PASS, 0 differences**, and the figure still reaches the night-audit screen. Tests T-N02b and T-N02c now pin this invariant so it cannot regress.

## 7. D11 — before and after

| | Before | After |
|---|---|---|
| `payments` with `folio_id IS NULL` | ids 1–6 — 800, 400, 1500, 1000, 500, 100 | **identical** |
| `extra_charges` with `folio_id IS NULL` | ids 1, 2 — 380.95, 95.24 | **identical** |
| Total | ₹4,776.19 | **identical** |

No folio assigned, no reversal, no correction, no deletion, no invoice or GST change. The Q-2 rule now makes a correction of these rows **impossible in code**. The S6 classification pack (`existing_data_classification.json`, read-only) records the finding conclusively: the database holds 8 financial rows in total, all eight are the D11 set, so the **legitimate existing-data migration population is empty** — Stage D/E are null operations and unit 1.6 has no authorized action.

## 8. Rollback position

| Layer | Position |
|---|---|
| Code | Uncommitted working-tree changes across 8 files. Reverting is `git checkout -- <files>`; after a commit, `git revert`. **High confidence.** |
| Schema | No change — nothing to roll back |
| Production data | **No production row was written.** Nothing to roll back |
| Detection | Golden master (declared 4-difference set), `inv-run`, `replay-verify`, the 44-case suite |
| Recovery | Restore capability exists and is rehearsed (RR-20260908-01); the backup artifact and manifest are retained |

## 9. Unresolved / not done

1. **W-20 overstay was not exercised at runtime** — the route's own preconditions were not met by the fixture, so `T-W20` passed vacuously ("no charge posted"). Its attribution is proven statically (T-W01/T-W02) and its code path is identical in shape to the other charge writers, but it has no runtime case. Recorded, not hidden.
2. **Business-date defects untouched** (Q-3) — the eight wall-clock/model-default dating sites remain Phase 3.
3. **S8 FK enforcement / S9 `NOT NULL`** — not executed; outside this authorization. Stage G still blocked by B-3 (eight-row disposition) and B-4 (migration mechanism).
4. **FD-015 `list_folios` widening** — still recorded-not-implemented; §19 forbade touching it.
5. **Production `inv-run` remains FAIL** — by design, until a Founder decision on the eight rows.
6. Backlog items B-1, B-2, B-6 (scheduler controls, maker-checker matrix, audit retention) untouched.

## 10. Candidate commit scope — exact, isolated

**Phase 1 changes only** (8 modified + 1 new evidence directory):

```
app/cico_service.py  app/night_audit_service.py  app/noshow_service.py
app/pos.py  app/reports.py  app/routes.py  app/seed.py  app/services.py
verification/evidence/20260909_phase1_execution/
```

**Must NOT be staged** — pre-existing dirty state (46 entries from before this session) and other rounds' work: the 28 May ledger deletions, `verification/ledgers/production/index.json`, the 10 August ledgers, `_audit_stage_src.tgz`, `package-lock.json`, the earlier evidence directories, `tools/restore_db.py` + `tools/test_restore_db.py` (Recovery Foundation — its own scope), `verification/adr/*`, and the recaptured `verification/masters/production/**` (Golden Master — its own scope).

Three separately-scoped bodies of work are therefore uncommitted side by side: Recovery Foundation, Golden Master recapture, and Phase 1. They must be committed as three commits, not one.

## 11. Boundary confirmation

No schema change · no migration executed · no production data mutation · no FK enforcement enabled · no `NOT NULL` · no Level 3 split billing · Phase 2a untouched (`app/folio.py` byte-identical to the checkpoint) · no report-authorization or role change · no scheduler change · no audit-retention change · no unrelated refactoring · no unrelated dirty file cleaned · **no commit, no push**.
