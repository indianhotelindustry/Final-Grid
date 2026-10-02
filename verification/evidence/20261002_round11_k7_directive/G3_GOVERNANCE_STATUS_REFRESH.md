# G3 GOVERNANCE STATUS REFRESH at `0938069`

| | |
|---|---|
| Prepared | 2026-10-02, after Founder Round 11 |
| Supersedes as status input | `20261002_overnight_gates_g3_g6/G3_MATRIX.md` (written at `c9eeff0`) and `overnight_execution/DECISION_QUEUE.md`, both on branch `overnight-20261002`. Those packs are preserved unedited (SC-4). Where they disagree with this file on a status, this file is the later record |
| Why | The existing G3 documentation is stale: it predates SR-1, DQ-56/R1, and Round 11. This file also corrects statements that are no longer true |
| Authority for status words | exact statuses only: PASS · FAIL · BLOCKED · OPEN · NOT VERIFIED · NOT AUTHORIZED · NOT APPLICABLE · plus DONE / RULED where a record exists |

## 1. State of record, verified 2026-10-02

| Item | Value |
|---|---|
| `main` = `origin/main` | **`0938069`**. `main` working tree clean |
| Local-only branches | `round11-k7-directive` (this pack, unpushed) · `overnight-20261002` local `5accb2f` is 1 commit ahead of origin `20959c6` · `dq56-q06h1-guard` local `28e6b63`, origin's branch ref `e310c66`: the branch ref lags, but all its commits are in `main` |
| Pushed | `sr1-inv-b06` = `0938069` · `sr2-inv-d02` = `c9eeff0` (in `main`) |
| Registered worktrees | main · `C:/wq06h1` · `C:/wtov` · `C:/wtsr1` · `C:/wtsr2` · `C:/wr11` (this pack). All clean except `C:/wr11` |
| Production `instance/pms.db` | `21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434`, byte-identical to the state recorded in committed evidence; this session did not open it |
| Application | **STOPPED**. No Python process, port 5000 free |
| Business date | 2026-08-10 per committed evidence (database unchanged since 2026-09-30); calendar 2026-10-02: **53 days behind**. NOT re-read from production |
| Recovery point | `FinalGrid/db-backups/pms_20261002_093338_dq56-apply-pre.db`, SHA-256 `5c78edb2…8dfa8e`: `tools/backup_db.py`, source `21dc0e97…` before and after, restore-rehearsed 15/15 (`RR-20261002-DQ56-APPLY`). Plaintext, off-repo, holds guest personal data. FD-P2-04 condition 11 (encrypted off-box restore) remains NOT VERIFIED |

## 2. SR-1 / INV-B06: integrated

| Item | State |
|---|---|
| Rule | Founder Round 10: `SR1-RULE`, `SR1-INT` (DQ-01…DQ-05 RULED). 30-day advance lead; corrections and refunds inherit the origin's verdict; a cancellation refund inherits its reservation's non-voided advances |
| Code | `362535d`: `verification/invariants/rules_b.py`, function `_b06` only (AST diff: no other top-level object changed) |
| Evidence | `verification/evidence/20261002_sr1_inv_b06/` (`0938069`). Targeted scenarios **28/28** (control `28e6b63`: 18/28). Regression battery: no status, population or violation difference between control and branch; INV-B06 HOLDS on production's 6 payments |
| Gate re-run before push (2026-10-02) | same results on a fresh run from `0938069`: 28/28 and 18/28; battery with **0 verdict-level differences** against the committed logs; production SHA-256 equal before and after |
| Integration | `sr1-inv-b06` pushed; `main` fast-forwarded `e310c66` → `0938069` (6 commits, no merge, no squash, no force). The three DQ-56 evidence commits (`7f19d54`, `2e19974`, `28e6b63`) entered with it |
| Files entering `main` | 76, all under `verification/`: 74 added evidence files, `FOUNDER_DECISIONS.md` (+77, 0 deletions), `rules_b.py` |
| Founder-confirmed readings | R-1 to R-4 confirmed by the Founder in session on 2026-10-02 (not yet in `FOUNDER_DECISIONS.md`; see §6) |
| Deployed | not applicable: no `app/` change. The live checkout's `verification/` files moved with the fast-forward; the application did not run |
| G3 row | **SR-1: DONE (integrated)** |

## 3. DQ-56 / Q06-H1 R1 guard: applied; application stopped

| Item | State |
|---|---|
| Decision | Round 8 `DQ56-R1`: protect only business date 2026-08-09 by refusing Run and Reopen and hiding those controls. DQ-56d (Run on other closed days) **not adopted** |
| Code | `46c4aab`: `app/reports.py` (+40), `app/templates/night_audit_panel.html`, `app/templates/reports/night_audit.html`; 3 files, +75/−5. The guard is `Q06_H1_PROTECTED_AUDIT_DATES = frozenset({date(2026, 8, 9)})` (`app/reports.py:2831`), enforced at `:2874` (Run) and `:3162` (Reopen) |
| Application to production | Round 9 `DQ56e`: backup + restore rehearsal 15/15; `origin/main` and the live checkout's `main` fast-forwarded to the R1 head (`e310c66`); no start. A controlled production start (about 35 seconds, 09:43:38-09:44:13) was run once under an in-session authorization: R1 loaded, database byte-identical, no jobs or messages, then stopped (`20261002_dq56_r1_production_start/`) |
| UI check | Run on a **copy** (port 5001), 11:03-11:10. Archived outside the repository at `C:/FinalGrid-archive/20261002_dq56_sr1/` (byte-identical copies verified; scanned clean for phone, email and guest names). The normal-date page shows Run, Reopen and Complete forms; the 2026-08-09 page shows **no Run and no Reopen form**, Complete is retained, and the page carries four sealed/protected-record markers. Not committed. The production UI has not been exercised |
| Side facts of that check | The copy's scheduler started and ran `flush_notification_queue` once (11:08:45; log shows normal execution, no send lines). The check used a `.env` copy carrying the production `SECRET_KEY`; it was shredded and removed on 2026-10-02 after an in-memory comparison (values never printed). Whether it carried messaging credentials is unknown |
| Q06-H1 | Unchanged by anything since. The sealed 2026-08-09 record is protected at the application layer |
| DQ-56 family | DQ-56 / DQ-56a: superseded by R1. DQ-56b: **RULED R1**. DQ-56c: **RULED {2026-08-09}**. DQ-56d: **not adopted** |

## 4. G3 matrix, refreshed

| # | Item | State at `0938069` | Change from `G3_MATRIX.md` |
|---|---|---|---|
| 1 | Attribution universal | DONE | none |
| 2 | CF-10 strict coupling 24/24 | DONE. Re-run at the release tag | the old note "`app/` identical to `3ffeba5`" no longer holds for `main`: R1 changed 3 files |
| 3 | CF-11 credit/voucher paths | DONE | none |
| 4 | Q06 / GST engines | DONE | none |
| 5 | SR-2 INV-D02 | DONE | now also in `main` and on `origin`; the missing push authorization record is a gap (§6) |
| 6 | **SR-1 INV-B06** | **DONE, integrated at `0938069`** | was OPEN |
| 7 | **K-7 dating at all writers** | **OPEN. Directive prepared as a DRAFT for review (`K7_PHASE_3_1_DIRECTIVE.md`); implementation NOT AUTHORIZED until activation** | was "no directive". GT-D1 now RULED: the item closes when Phase 3.1 is completely implemented and evidenced |
| 8 | Evidence pack at the release tag | NOT VERIFIED; no release tag exists | none |
| 9 | "Reconciliation views agree" scope (GT-D13) | OPEN | none |
| 10 | Rulings | SR-1 and SR-2 both RULED and delivered | was SR-1 OPEN |

**G3 is OPEN, not PASS.** K-7 is the only remaining engineering item. Governance and scoring items remain: the GT-D13 scope, a named release tag, and the G3 pack at that tag (scoring rule, `CERTIFICATION_GATES.md:50`). Round 4's last Founder statement on G3 ("not-PASS") has not been superseded by any later round.

## 5. Decision queue, reconciled

Mapping: GT-D1 = DQ-13 · GT-D5 = DQ-14 · GT-D6 = DQ-15 · K7-D1 = DQ-57 · K7-D2/D4/D5/D6 = DQ-58 · K7-D3 = DQ-59 · K7-D7 = DQ-60 · K7-D8 = DQ-61 · K7-D10 = DQ-62.

| DQ | Status now | By |
|---|---|---|
| DQ-01…DQ-05 | **RULED** | Round 10 |
| DQ-13 | **RULED** | Round 11 GT-D1 |
| DQ-14 | **PARTLY RULED**: Gates A–H are outside the K-7 directive and the directive is validated against G3, G6, G10. Their meaning for later phases stays OPEN | Round 11 |
| DQ-15 | **PARTLY RULED**: unit 3.1 for K-7; the K-7 site list and fallback rule; B-10 #1/#2/#3 and reports out of K-7. Still OPEN: units 3.2-3.8, B-10 #4 and #5, fresh-install `night_audit_enabled` default, authority to re-baseline frozen suites (not granted; the directive uses superseding packs), push/merge (not authorized) | Round 11 |
| DQ-57 | **RULED** (a dedicated 3.1 directive; B-1 and Gates A–H outside) | Round 11 |
| DQ-58 | **RULED**: the in-scope list; late checkout, reports, void/shift mapping, invoice UTC dating out unless a concrete dependency is shown. Whether late checkout's calendar basis is "retained as ruled" or deferred to a later B-10 directive is **not ruled** | Round 11 |
| DQ-59 | **RULED**: fail closed with a logged error; defaults resolve or raise | Round 11 |
| DQ-60 | **PARTLY RULED**: RED/GREEN harness, clock ≠ business date, copies, full battery, declared-delta list, no new invariant. How superseded frozen suites are treated is proposed in directive §7.6 and awaits review | Round 11 |
| (K7-D4) | **OPEN, package prepared** (`K7_D4_VOUCHER_BASIS_DECISION.md`) | |
| DQ-62 (K7-D10) | **OPEN, package prepared** (`K7_D10_CLOSE_PATH_DECISION_PACKAGE.md`) | |
| DQ-56, 56a, 56b, 56c, 56d | RESOLVED / RULED / not adopted (see §3) | Rounds 8-9 |
| DQ-37, DQ-53 | **PARTLY SUPERSEDED**: a verified, restore-rehearsed recovery point of `21dc0e97…` exists (§1). Still open: encrypted off-box copy, retention, location and access of copies | |
| DQ-06 | OPEN (SR-2 push authorization record) and joined by new record gaps (§6) | |
| DQ-16, 61, 64-68 | OPEN: stale business date, K-7 deploy sequencing | |
| All others (DQ-07…12, 17…36, 38…55, 63) | OPEN, unchanged | |

## 6. Governance-record gaps, for the Founder to dictate

`FOUNDER_DECISIONS.md` is append-only. These facts exist in session or in evidence but not in the file. None is a decision I may make; each needs a Founder entry or an explicit instruction to cite another record.

| # | Gap | What the record currently says | What happened |
|---|---|---|---|
| G-1 | Confirmation of SR-1 readings R-1…R-4 | nothing | the Founder confirmed all four in session on 2026-10-02 |
| G-2 | Authorization to push and merge SR-1 | Round 10: "No production changes, no merge to main, and no deployment are authorized" | `sr1-inv-b06` pushed and `main` fast-forwarded to `0938069` on the Founder's later in-session instruction |
| G-3 | Authorization of the DQ-56 controlled production start | Round 9: "Do not start the live application until I separately authorize the production-start step" | one controlled start ran 09:43:38-09:44:13 under an in-session authorization |
| G-4 | Push and merge of SR-2 (DQ-06 / GT-D4) | Round 7: "Push and merge remain separately unauthorised" | `origin/main` contained it at `c9eeff0` |
| G-5 | GT-D10: ADR-011 production application, CF-10/CF-11 directive, Q06-H2 | the carry-forward register still lists them open | all done and evidenced |
| G-6 | GT-D3 for INV-D02 | Round 10 item 5 records the Phase 6 carve-out for INV-B06 only | SR-2 changed INV-D02 under Rounds 6-7 with no overlay |
| G-7 | The three DQ-56 evidence commits entered `main` with SR-1 | Round 9 covers the R1 head | six commits were fast-forwarded together, as the Founder described them |

## 7. Statements in earlier packs that are no longer accurate

| Where | Statement | Now |
|---|---|---|
| `G3_MATRIX.md` header, row 6, §4 | SR-1 OPEN; `rules_b.py` untouched | integrated; `_b06` changed |
| `G3_MATRIX.md` row 2 | `app/` byte-identical `3ffeba5`…`c9eeff0` | `main` `app/` differs from `c9eeff0` by the R1 guard (3 files) |
| `DECISION_QUEUE.md` | DQ-01…05 OPEN; DQ-56 family OPEN; DQ-37/53 "no verified backup" | see §5 |
| K-7 pack, `BUSINESS_DATE_PRODUCTION_DECISION.md`, `G6_DEPENDENCY_MAP.md` | `app/reports.py` line numbers after about 2824 (e.g. reopen `:3105`, Force Close `:3505-3565`, `bd.current_date = today` `:3555`, `voucher_ledger` `:6429`) | shifted by +36 to +40: reopen `:3141`, Force Close `:3545`, `:3595`, `voucher_ledger` `:6469`. Lines in `services.py`, `routes.py`, `models.py` are unchanged and every K-7 writer site matches the inventory |
| `BUSINESS_DATE_PRODUCTION_DECISION.md` §3, BD-F4 | the reopen path can mutate the sealed 2026-08-09 record | guarded by R1 at the application layer |
| K-7 pack `K7_DEPENDENCY_MAP.md` E-11 | SR-1's refund clause "waits for K-7's refund-date ruling" | resolved by Round 10: refunds and corrections inherit the verdict; no K-7 dependency |

## 8. What remains, and the exact next blockers

1. **Founder review of this package.** Then an activation entry for the K-7 directive that answers items F-1…F-6 (`K7_PHASE_3_1_DIRECTIVE.md` §5). F-1, the K7-D4 voucher basis, gates only the voucher sites.
2. **K-7 implementation** (not authorized before step 1) and its evidence pack. This is the only G3 engineering item.
3. **Not needed to start K-7 code, needed before real use:** the stale 53-day business date and its decisions (BD-D1…BD-D5, including whether the day with the five D11 rows may be closed); K7-D10 and the close-path choice; units 3.5 and 3.6; K-7 deployment sequencing (K7-D8).
4. **Gate scoring items:** GT-D13 scope, a named release tag (GT-D14), Golden Master and replay re-baselines at G10 (GT-D8), the G3 pack at the tag.
5. **Independent P1 items that are not K-7 prerequisites:** the guest phone number in the tree and in remote history (DQ-45), the production webhook (DQ-50), start-up scheduled jobs (DQ-31).

## 9. Boundaries of this document

Nothing here was implemented, pushed, merged or deployed. The application was not started, the production database was not opened, and the business date was not touched.
