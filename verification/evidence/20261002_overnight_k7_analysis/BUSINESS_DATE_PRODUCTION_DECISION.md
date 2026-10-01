# BUSINESS DATE — PRODUCTION DECISION (stale by 53 days)

| | |
|---|---|
| Prepared | 2026-10-02, FG-OVERNIGHT-01, analysis only |
| Code | `C:/wtov` at `c9eeff0` (`app/` = live `c703150`, verified by empty `git diff --stat c703150 c9eeff0 -- app/`) |
| Production | not opened by this work. Facts: orchestrator read-only observation 2026-10-02 00:40 IST, and committed evidence cited per line |
| Status | Advancing the production business date: **NOT AUTHORIZED**. This document frames the decision; it selects nothing |

> **This is a separate production decision. Business-date advancement must not be bundled into a K-7 deployment.** The two are different production operations with different risks, evidence and rollback, and each needs its own authorizing reference (SC-6, `verification/MASTER_PLAN.md:44`; FD-019, `verification/FOUNDER_DECISIONS.md:848-850`).

---

## 1. Current state

| Item | Value | Source |
|---|---|---|
| Business date | **2026-08-10** | orchestrator, `business_date` row id 1 |
| Last updated | 2026-08-11 12:42:48 (`updated_at`, written with `datetime.utcnow()` — UTC) | orchestrator; writers `app/reports.py:3091`, `app/services.py:522` |
| Calendar | **2026-10-02** | — |
| Difference | **53 days** (51 on 2026-09-30) | `verification/evidence/overnight_execution/OVERNIGHT_STATE.md` |
| Dates to close to reach 2026-10-02 | **53**: 2026-08-10 … 2026-10-01 inclusive | arithmetic |
| Closed days | one: 2026-08-09, Completed, sealed, hash-valid; Q06-H1 historical record | `FOUNDER_DECISIONS.md:1219-1227`; `night_audit_logs` = 1 row (`verification/evidence/20260930_adr011_production_application/prod_post_state.json`) |
| Open day content | 2026-08-10 holds D11 rows payments 3, 4, 5, 6 and extra_charges 2 (₹3,195.24) | `FOUNDER_DECISIONS.md:52-56` |
| Activity after 2026-08-10 | none recorded in the financial tables (financial tables unchanged by the ADR-011 application, `prod_post_state.json` `checks.financial_tables_unchanged`); a reservation date of 2026-08-11 exists ("a future booking", `verification/ledgers/production/index.json` `timeline_excluded`) | NOT VERIFIED today |
| In-house guests | "production has none" at 2026-09-09 | `verification/evidence/20260909_phase1_verification_completion/Q14_PARITY.md:25` — NOT VERIFIED today |
| Shifts | 0 rows | `prod_post_state.json` |
| `notification_queue` | 4 rows (statuses unknown) | `prod_post_state.json` — NOT VERIFIED |
| Scheduler | `night_audit_enabled='false'`, `night_audit_time='02:00'`; application stopped | orchestrator; FD-P2-05 `FOUNDER_DECISIONS.md:1175` |
| Night-audit sequence invariant | INV-B05 HOLDS today (only 2026-08-09 closed; the business date's own day is excluded) | rule `verification/invariants/rules_b.py:495-515` (ANALYSIS) |

---

## 2. Which transaction types are affected while the date is stale, and how

Detailed in `K7_PRODUCTION_RISK.md` §§1–2. Summary (application started, unchanged code):

| Type | Effect of a 2026-08-10 business date on a 2026-10-0x calendar day |
|---|---|
| Advance, settlement, deposit, credit recovery, POS, CICO, tip, other income, upsell, no-show fee (16 writers) | dated 2026-08-10; land in the same open day as five D11 rows |
| Corrections, refunds, voucher redemption, overstay, checkout extra (8 writers) + voucher issue | dated on the calendar → after the business date → INV-B04 VIOLATED (`rules_b.py:395-404`) |
| Walk-in check-in | stay created as 2026-08-10 → 2026-08-1x (`app/routes.py:2407`, `:2477`, `:2714`, `:2732`, `:7393`); room nights and room tax lines in August |
| Advance reservations | must arrive ≥ calendar today (`app/validators.py:101`); payments dated 2026-08-10 → before arrival → INV-B06 VIOLATED |
| Late checkout | calendar ≥ departure: always true for August-dated walk-ins → fee by time of day (`app/routes.py:3206-3209`) |
| Overstay (Hourly) | elapsed hours since an August departure (`app/routes.py:8018-8048`) |
| GST | extras' TaxLines dated August (`app/gst_service.py:541`, `:563`) while invoices are dated by October checkout (`app/gstr_export.py:192-193`) |
| Reports | calendar-range defaults show October; business-dated rows sit in August (`K7_WRITER_INVENTORY.md` §7) |

---

## 3. Consequences of leaving the date stale

| If the application stays stopped | If the application is used without advancing |
|---|---|
| No financial effect. The lag grows by one day per calendar day; each day adds one more close (or one more Skipped row) to any later catch-up | every row in §2 above; INV-B04/INV-B06 violations accumulate; the first close of 2026-08-10 would seal all activity since restart plus the five D11 rows into one day |
| Q06-H1 exposure persists: `night_audit_reopen` accepts 2026-08-09 while the business date is 2026-08-10 (guard `bd.current_date == audit_date + 1`, `app/reports.py:3186-3189`; status check `:3137`) and would set the sealed record to `Reopened`, `snapshot_valid=False` (`:3152-3161`), contrary to "shall not be … mutated" (`FOUNDER_DECISIONS.md:1223`). The path exists in the panel (`app/templates/night_audit_panel.html:1028`) | same |
| G6 stays FAIL ("production date … stale", `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:36`); G11's day-one procedure ("set the business date … run the first close", `:21`, `:41`) cannot be rehearsed against the real starting point | same |

---

## 4. Consequences of advancing — what each available mechanism actually does

All mechanisms that move `business_date.current_date` at `c9eeff0` (exhaustive grep, `K7_ARCHITECTURE_ANALYSIS.md` §3):

| | A. `run_night_audit` ×53 | B. Panel Run + Complete ×53 | D. Force Close (once) | S. Direct SQL `UPDATE` | T. `tools/production_initialize.py` |
|---|---|---|---|---|---|
| Entry | scheduler (forbidden in first release, FD-P2-05 `FOUNDER_DECISIONS.md:1172`; FD-009 `:575-583`) or direct POST `/night-audit/run` (`main.run_night_audit_manual`, `app/routes.py:4921-4927`; no rendered form) | panel forms `app/templates/night_audit_panel.html:172`, `:978` → `app/reports.py:2824`, `:2896` | panel modal `night_audit_panel.html:1107-1117` → `app/reports.py:3505` | outside the application | CLI |
| Who | Admin/Manager/Accountant (`app/routes.py:4923`) | Run: Admin/Manager/Accountant; Complete: Admin/Manager (`app/reports.py:2826`, `:2898`) | Admin (`:3509`) | DB access | operator |
| Days per action | 1, only if no blockers (pending checkouts, open shifts, zero-rate in-house — `app/services.py:457-469`); otherwise log left `Pending`, date unchanged, and a repeat run for the same date is **silently skipped** (`:312-317`) | 1, only if `bd.current_date == audit_date` (`app/reports.py:3088`); hard blocks need an override reason (`:2934-2966`) | all 53 at once, to `date.today()` (`:3522`, `:3555`) | any | any |
| **Posts charges** | **Yes**: `room_rent` for every `CheckedIn` reservation, dated the closed day, with **no stay-date condition** (`app/services.py:364`, `:413-421`); no-show fee if `noshow_fee_enabled` (`app/noshow_service.py:45-50`, `:145-151`) | No | No | No | deletes all activity |
| **Marks no-shows** | **Yes**: every `Reserved/Confirmed` reservation with `arrival_date <= day`, not exempt → `NoShow`, room set Vacant (`app/noshow_service.py:66-82`, `:124-139`) | No | No | No | — |
| **Seals snapshot** | Yes on auto-complete (hash) (`app/services.py:487-512`) | Yes (hash + `_meta`) (`app/reports.py:3048-3078`) | **No**; inserted rows carry `snapshot_valid=True` by model default (`app/models.py:937`) — `FORCE_CLOSE_INVESTIGATION.md` §5.1 | No `NightAuditLog` rows at all | — |
| Locks the day | Yes (Completed) | Yes (Completed/Warning) | Yes — `Skipped` counts as locked (`app/services.py:1013-1016`) | No | — |
| Guest notifications | none — no notification call in `run_night_audit` or `noshow_service` (grep of `notify_*` callers: `app/booking.py:202`, `app/routes.py:2656`, `:3823`, `:8894`, `app/webhook.py:269`, `:331`) | none | none | none | — |
| `audit_logs` row for the close / date change | **none** for the close itself; per-row audit for each room-rent and no-show posting (`app/services.py:426`; `app/noshow_service.py:157`, `:190-207`) | **none** (no `_write_audit` / `AuditLog` in `app/reports.py:2824-3101`) | **none** (`FORCE_CLOSE_INVESTIGATION.md` §3) | none | — |
| Invariant effect | INV-B01…B05 examine each closed day normally | same | INV-B05 satisfied by the rows' existence while INV-B01/B02/B03 exclude `Skipped` (`FORCE_CLOSE_INVESTIGATION.md` §5.2) | INV-B05 VIOLATED (53-day gap) | — |
| In-app reversal | reopen, −1 day per action (`app/reports.py:3186-3189`) | same | none for a multi-day jump (`FORCE_CLOSE_INVESTIGATION.md` §7.5); per-day "Fix Skipped Day" rewrites the log in place and posts room rent (`app/reports.py:3218-3445`) | SQL | — |
| Governance fit | excluded as scheduler; as a direct POST it is a non-UI path | the FD-P2-05 manual model ("authorized operator initiates the close", `FOUNDER_DECISIONS.md:1172`) | "Use this only in an emergency" (panel text `night_audit_panel.html:1120-1131`); fabricates closure records (investigation verdict "NOT SAFE") | ungoverned data mutation (FD-019) | destroys the D11 rows protected by FD-010 / FD-P2-03 — **NOT APPLICABLE** |

Answers to the specific questions:

1. **Does closing/advancing post charges?** Path A: yes (room rent, no-show fees). Path B: no. Force Close: no.
2. **Does it seal snapshots?** A and B: yes, hashed. Force Close: no, but flags rows valid.
3. **Does it mark no-shows?** Only path A.
4. **Does it notify guests?** No path calls a notification. *But any application start* registers `notification_queue_flush` every 5 minutes (`app/__init__.py:538-545`), which sends every `pending` queued WhatsApp/e-mail whose retry time has passed (`app/notifications.py:209-255`). Production holds 4 queue rows of unknown status: starting the application to perform a close may send stale guest messages. NOT VERIFIED — needs a read-only status check before any start.
5. **Does any route advance the date without running the close?** Yes — Force Close (D). Path B advances after a close that posts nothing.
6. **Is there a "skip" or "set date" path?** "Skip" = Force Close. No "set date" route exists; the only arbitrary setter is the destructive initialization tool (T).
7. **Is advancing itself a financial/business operation?** ANALYSIS: **yes.** It creates closure records, freezes figures into hashed snapshots that are later served as the historical record (Q06-H1 rationale, `FOUNDER_DECISIONS.md:1225`), locks days against payments, voids and checkouts (`K7_ARCHITECTURE_ANALYSIS.md` §5), may post charges and change reservation statuses (path A), and determines the date of every later posting. FD-P2-05 requires that the "business date is explicitly controlled" and "financial mutations must be auditable" (`FOUNDER_DECISIONS.md:1172`). It is a production data mutation under FD-019 (`:850`) and PD-004/PD-005 (`:477-482`).

Additional facts relevant to the choice:

- **D11 interplay.** Closing 2026-08-10 by A or B seals payments 3–6 and extra_charges 2 into a hashed snapshot and locks the day; voiding them afterwards needs an Admin override and a correction pair, which Q-2 refuses for NULL-folio rows (`app/services.py:1221`). FD-010 records "No night-audit modification is authorized" for these rows (`FOUNDER_DECISIONS.md:593` section). Whether an ordinary close of their day is such a modification is **not ruled** (BD-D3).
- **Q06-H1 interplay.** Advancing the date by one or more days removes the in-app path to reopen 2026-08-09 (`bd == audit_date + 1` no longer holds). Restoring a pre-advance backup brings that exposure back.
- **Snapshot content.** Q06-H2 is in the code (`app/night_audit_service.py:1126-1166`), so new snapshots use the corrected taxable base; the 2026-08-09 snapshot keeps its historical value.
- **Close readiness of 2026-08-10.** The 2026-08-31 replay ledger (app 2.2.18) shows `can_close True`, 0 blockers, reconciliation difference −0.02 within tolerance 1 (`verification/ledgers/production/dates/2026-08-10.json`, `index.json`). Under `c9eeff0` code this is **NOT VERIFIED**; it must be proven on a copy.
- **Path A in-house filter.** If any reservation is `CheckedIn` at the time of a catch-up by path A, it receives one `room_rent` row per closed day regardless of its stay dates (`app/services.py:364`), i.e. up to 53 charges dated before its arrival.
- **Locking on SQLite.** `with_for_update()` is inert on SQLite (`FORCE_CLOSE_INVESTIGATION.md` §6); concurrency safety rests on a single operator.

---

## 5. Backup required before any advance

FD-P2-04 minimum for a production mutation: **conditions 1–7, 9, 10** (`FOUNDER_DECISIONS.md:1163`):

| # | Condition |
|---|---|
| 1 | artifact and plaintext hash equal the values recorded at backup time and in the manifest |
| 2 | restore completes into a fresh isolated path, never `instance/` |
| 3 | `PRAGMA integrity_check` ok on source and restored |
| 4 | `foreign_key_check` = 0 (or equal to source) |
| 5 | `sqlite_master` identical to source and equal to the release tag's fingerprint |
| 6 | per-table row counts and content digests equal, body bytes identical beyond the 100-byte header, financial tables named |
| 7 | whole-file hash recorded (informational) |
| 9 | machine-readable manifest: run id, paths, hashes, UTC timestamps, app version, **business date**, all checks — retained and committed |
| 10 | operator, machine and directive recorded |

Protocol: PD-005 "backup → backup verification → recovery plan/rehearsal → execute mutation → post-mutation verification → invariant verification → evidence" (`FOUNDER_DECISIONS.md:480-482`). Precedent for tools and evidence shape: `verification/evidence/20260930_adr011_production_application/` (`tools/backup_db.py`, `tools/restore_db.py`, pre/post state digests, inv-run, gm-verify).

---

## 6. Rollback implications

| Mechanism | In-app reversal | Clean reversal |
|---|---|---|
| A / B | `night_audit_reopen` one day at a time (`app/reports.py:3105-3199`): each writes an immutable `NightAuditReopenLog`, sets `snapshot_valid=False`, rolls the date back one day. Undoing 53 closes this way leaves 53 reopen trails and 53 invalidated snapshots — not an undo | restore of the verified pre-advance backup (§5), valid only while no trading has occurred since; loses everything after it |
| D | none for the jump; per-day "Fix Skipped Day" converts rows in place and may post room rent | restore |
| S | SQL | restore |

Constraints on any rollback:

- **INV-B01** (`rules_b.py:36-60`): once a day is closed, any row later created into it is a CRITICAL / RELEASE violation; a reopen-and-reclose cycle with new postings must be evidenced.
- **Sealed snapshots**: every closed day's snapshot becomes the served historical view; Q06-H1/H3 establish "supersede, never overwrite" for historical correction (`FOUNDER_DECISIONS.md:1239-1250`).
- **Q06-H1 (2026-08-09)**: any advance leaves it untouched; a restore re-exposes it to the reopen path (§3).
- **K-7 independence**: a business-date rollback must not require a code rollback, and vice versa (K7-D8).

---

## 7. Decision entries

### BD-D1 — Whether and when to bring the production business date current

- **DECISION ID:** BD-D1
- **DATE DISCOVERED:** 2026-10-02 (staleness recorded since 2026-08-31; 29 days at `MASTER_PLAN.md:151`, 30 at `CERTIFICATION_GATES.md:36`, 51 on 2026-09-30, 53 today)
- **WORKSTREAM:** Production operations / Phase 3 (3.6 staleness)
- **QUESTION:** Should the production business date be brought current, and if so when — now, immediately before the first day of real trading, or not until Phase 3 controls (3.5/3.6) exist?
- **WHY REQUIRED:** every financial posting takes its date from it (§2); leaving it stale while trading violates INV-B04/INV-B06 and mis-dates GST; advancing is itself a production mutation (§4 Q7). FD-P2-05 requires the business date to be "explicitly controlled" (`FOUNDER_DECISIONS.md:1172`); no staleness rule exists (B-10 #5, `verification/adr/BACKLOG.md:21`).
- **OPTIONS:**
  - (a) Advance now (application otherwise idle), under PD-004/PD-005.
  - (b) Advance as the first act of the first trading day, inside the deployment rehearsal's day-one procedure (G11, `CERTIFICATION_GATES.md:21`).
  - (c) Leave stale until Phase 3 units 3.5/3.6 are implemented; keep the application stopped meanwhile.
  - (d) Leave stale and trade (not supported by this analysis: §2).
- **EVIDENCE:** §§1–4; `K7_PRODUCTION_RISK.md`.
- **DEPENDENCIES:** BD-D2 (mechanism), BD-D3 (D11), BD-D5 (authorization).
- **WHAT IS BLOCKED:** any production trading; G11 day-one rehearsal against the real starting point; K-7 deployment under K7-D8 option A.
- **WHAT CAN CONTINUE:** rehearsal of every mechanism on copies (BD-D5 action 1); K-7 code once K7-D1 is ruled.
- **EXACT ACTION AFTER DECISION:** record the ruling as a Founder entry; if (a) or (b), proceed to BD-D2/BD-D5 actions.

### BD-D2 — Mechanism

- **DECISION ID:** BD-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** Production operations
- **QUESTION:** By which mechanism is the date advanced?
- **WHY REQUIRED:** the mechanisms differ in postings, no-show processing, snapshots, invariant visibility and reversibility (§4).
- **OPTIONS:**
  - B53. Panel Run + Complete for each of the 53 dates (manual model; 53 sealed snapshots; no postings, no no-shows).
  - A53. `run_night_audit` per date via the manual POST (postings and no-shows; blockers stall it; scheduler stays off).
  - B1+D. Close 2026-08-10 properly (B), then Force Close 2026-08-11 … 2026-10-01 (52 `Skipped` rows, no snapshots, INV-B05 silenced — `FORCE_CLOSE_INVESTIGATION.md` §5.2).
  - D53. Force Close everything (53 `Skipped` rows incl. 2026-08-10 with its D11 rows, locked without a snapshot).
  - S. Direct SQL (not an application path; INV-B05 gap).
- **EVIDENCE:** §4 table; `verification/FORCE_CLOSE_INVESTIGATION.md` (2026-08-08, line numbers since moved: route now `app/reports.py:3505-3565`).
- **DEPENDENCIES:** BD-D1; K7-D10 (which close path the first release uses); read-only pre-checks (BD-D5 action 2).
- **WHAT IS BLOCKED:** the written catch-up procedure.
- **WHAT CAN CONTINUE:** copy rehearsals of every option, measuring rows written, snapshot sizes, invariant results.
- **EXACT ACTION AFTER DECISION:** write the step-by-step catch-up procedure for the chosen mechanism into the PD-004 authorization request.

### BD-D3 — Closing the day that holds five D11 rows

- **DECISION ID:** BD-D3
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** Governance (FD-010 / FD-P2-03 interpretation)
- **QUESTION:** May business day 2026-08-10, which holds D11 payments 3–6 and extra_charges 2, be closed and sealed (A or B), or marked `Skipped` (D)?
- **WHY REQUIRED:** FD-010 "No night-audit modification is authorized" for the D11 rows (`FOUNDER_DECISIONS.md:593` section); FD-P2-03 "This ruling does not authorize financial mutation" (`:1146-1155`). A close does not change the rows but seals them into a hashed snapshot and locks their day.
- **OPTIONS:** (a) an ordinary close is permitted and is not a "night-audit modification"; (b) the close is permitted only with the D11 rows named in the close evidence as the declared exception; (c) not permitted — the day stays open (then no later day can be closed by A/B, because each advances only from the current date).
- **EVIDENCE:** `FOUNDER_DECISIONS.md:47-56`.
- **DEPENDENCIES:** BD-D2.
- **WHAT IS BLOCKED:** every mechanism except S (and T, which is excluded).
- **WHAT CAN CONTINUE:** copy rehearsals.
- **EXACT ACTION AFTER DECISION:** record the interpretation; include the D11 rows by identity in the close evidence if (b).

### BD-D4 — Target date, timing and interim staleness rule

- **DECISION ID:** BD-D4
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** Production operations / Phase 3 (3.6)
- **QUESTION:** To which date is the business date brought (calendar today, or the first trading day), at what time of day is each close performed, and what interim rule applies until unit 3.6 exists?
- **WHY REQUIRED:** the date grows by one per calendar day; a close before midnight sets the business date ahead of the calendar, which dates today's wall-clock writers into a sealed day (`K7_ARCHITECTURE_ANALYSIS.md` §5); B-10 #5 undefined.
- **OPTIONS:** (a) target = calendar date of execution, closes performed after midnight; (b) target = first trading day; (c) an interim written rule (e.g. "no trading if business date ≠ calendar date") pending 3.6.
- **EVIDENCE:** as cited.
- **DEPENDENCIES:** BD-D1.
- **WHAT IS BLOCKED:** procedure text.
- **WHAT CAN CONTINUE:** rehearsal.
- **EXACT ACTION AFTER DECISION:** state the target date and timing in the authorization.

### BD-D5 — Authorization, rehearsal and evidence standard

- **DECISION ID:** BD-D5
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** Production safety
- **QUESTION:** Which authorization and evidence are required, and is a full multi-day rehearsal on a copy a precondition?
- **WHY REQUIRED:** production data mutation (FD-019 `:850`; PD-004/005 `:477-482`); FD-P2-04 minimum conditions (`:1163`); application start side effects (notification flush, §4 Q4).
- **OPTIONS:** (a) PD-004 authorization + PD-005 + FD-P2-04 1–7, 9, 10 + full rehearsal of the chosen mechanism on a copy (which also yields N7 / G11 multi-day evidence); (b) same without full rehearsal (rehearse first and last day only).
- **EVIDENCE:** precedent `verification/evidence/20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md`.
- **DEPENDENCIES:** BD-D1…BD-D4.
- **WHAT IS BLOCKED:** execution.
- **WHAT CAN CONTINUE:** everything in "exact action" items 1–2.
- **EXACT ACTION AFTER DECISION:**
  1. Rehearse the chosen mechanism end-to-end on a `make_copy()` copy at `c703150` code; record rows written per table, snapshots and sizes, `inv-run` after each close (INV-B01…B05), `gm-verify` and replay at the end.
  2. Read-only pre-checks on a copy of production: reservation statuses (any `CheckedIn`; any `Reserved/Confirmed` with arrival ≤ target), open shifts, `noshow_fee_enabled`, CICO settings, `notification_queue` statuses (any `pending` must be resolved or the flush risk accepted before any start), `night_audit_logs` rows.
  3. Fresh backup + restore rehearsal meeting conditions 1–7, 9, 10; pre-state digests.
  4. Execute exactly the rehearsed steps; stop at the first divergence from the rehearsal.
  5. Post-state digests (only `night_audit_logs`, `business_date` and — for A — the rehearsed postings may change), `inv-run`, evidence pack, Founder record.

---

## 8. Findings from this analysis relevant to the decision (not previously recorded as such)

| # | Finding | Citation |
|---|---|---|
| BD-F1 | The panel's close (path B) posts no room rent and processes no no-shows; path A does | `app/reports.py:2896-3101`; `app/services.py:353`, `:413-421` |
| BD-F2 | Path A posts room rent for every `CheckedIn` reservation without a stay-date condition | `app/services.py:364` |
| BD-F3 | No close path writes an `audit_logs` row for the close or for the business-date change | `app/reports.py:2824-3101`, `:3505-3565`; `app/services.py:264-533` |
| BD-F4 | While the business date is 2026-08-10, the reopen path can mutate the Q06-H1 sealed record of 2026-08-09 | `app/reports.py:3137`, `:3152-3161`, `:3186-3189` |
| BD-F5 | Any application start can send queued guest notifications (4 rows on production, status unknown) | `app/__init__.py:538-545`; `app/notifications.py:209-255` |
| BD-F6 | A stalled path-A run (blockers) leaves a `Pending` log that makes later path-A runs for that date silently skip | `app/services.py:312-317`, `:470-479` |
