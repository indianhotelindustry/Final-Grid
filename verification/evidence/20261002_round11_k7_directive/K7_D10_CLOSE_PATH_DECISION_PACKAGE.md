# K7-D10 — The two operator close paths: decision package

| | |
|---|---|
| Prepared | 2026-10-02, at `main` = `0938069`. Analysis only |
| Instruction (Round 11) | "prepare the two close-path alternatives as a separate decision package. Do not perform either path in production." |
| Status | **OPEN. Nothing is chosen. Neither path was run anywhere**: not in production, not on a copy, in preparing this package |
| Relation to K-7 | Separate from `K7_PHASE_3_1_DIRECTIVE.md`. K-7 changes neither path. K7-D2 keeps the close paths out of the K-7 unit unless a concrete dependency is shown (none found) |
| Feeds | the written daily-close procedure (FD-P2-05, G11); the stale-date catch-up mechanism (BD-D2); Phase 3 unit 3.2 scope |

Labels: **VERIFIED** = read in the code at `0938069` this session. **PACK** = from `20261002_overnight_k7_analysis/` and not re-read here. **NOT VERIFIED** = needs a copy experiment.

## 1. Why there is a decision

FD-P2-05 makes a manual, operator-initiated close the first-release model, and requires a written daily-close procedure. The code has two ways for an operator to close a day. They do different things, so the procedure has to name one and state its effects.

Line references in `app/reports.py` after about line 2824 moved by roughly +36 to +40 when the DQ56-R1 guard was added. The numbers below are current.

## 2. The two alternatives

### Alternative 1 — Panel close ("path B")

The Night Audit panel's **Run** then **Complete** buttons.

| Item | Fact |
|---|---|
| Code | `night_audit_run` `app/reports.py:2856`; `night_audit_complete` `:2932` (VERIFIED) |
| Who | Run: Admin, Manager, Accountant. Complete: Admin, Manager (PACK) |
| Day advance | +1 day, only if `bd.current_date == audit_date` (`:3124-3125`, VERIFIED) |
| Room-rent charges | **none** (no `ExtraCharge` constructed in `:2856-3140`, VERIFIED) |
| No-show processing | **none** (no call in `:2856-3140`, VERIFIED) |
| Snapshot | hash and `snapshot_valid` written (`compute_snapshot_hash` near `:3089`, `snapshot_valid` set near `:3114-3118`, VERIFIED present; `_meta` stamp PACK) |
| Blockers | hard blocks can be overridden with a reason (PACK) |
| Audit rows | no `audit_logs` row for the close or the date change (PACK; grep in `:2856-3140` finds no `AuditLog` or `_write_audit`) |
| Reversal | `night_audit_reopen` `:3141`, one day per action, writes `NightAuditReopenLog` (PACK). For 2026-08-09 the DQ56-R1 guard refuses Run and Reopen (`:2874`, `:3162`, VERIFIED) |
| UI | exists and is rendered |

### Alternative 2 — Service close ("path A")

`run_night_audit` (`app/services.py:264`).

| Item | Fact |
|---|---|
| Entry | the scheduler (forbidden in the first release, FD-P2-05) or `POST /night-audit/run` `main.run_night_audit_manual` (`app/routes.py:4921`, VERIFIED). The only form for it is in `app/templates/night_audit.html`, which the pack found no route renders (PACK; reachable today only by a direct POST) |
| Who | Admin, Manager, Accountant (`_deny_role`, VERIFIED) |
| Day advance | +1 day, only when no blockers; otherwise the log is left `Pending` and the date does not move. A repeat run for that date is **silently skipped** while any log exists (`:312-317` area, VERIFIED comment "skip if ANY log already exists") |
| Room-rent charges | **yes**: one `room_rent` `ExtraCharge` per `CheckedIn` reservation, dated the closed day, idempotent per (reservation, type, date) (VERIFIED) |
| In-house filter | `Reservation.status == 'CheckedIn'` with **no stay-date condition** (`:364`, VERIFIED). A checked-in reservation gets rent for every date closed, even dates before its arrival or after its departure |
| No-show processing | **yes**: `process_all_noshows(_bd)` (VERIFIED): reservations `Reserved`/`Confirmed` with `arrival_date <= day`, not exempt, become `NoShow`, the room is freed, and a fee may be posted if `noshow_fee_enabled` (PACK) |
| Snapshot | sealed on auto-complete (PACK) |
| Audit rows | per-charge audit for the postings (`:426`; `noshow_service.py:157`, PACK); none for the close itself (PACK) |
| UI | none today |

## 3. Side by side

| | Alt 1 panel | Alt 2 service |
|---|---|---|
| Rent rows in the ledger | none | one per in-house guest per night |
| No-shows | not processed; the manual no-show route exists (`noshow_service.py:285-315`, PACK) | processed automatically |
| Operator interface | exists | needs a new form or a non-UI call |
| Blockers | override with reason, then Complete | stalls as `Pending`; repeat is silently skipped (BD-F6) |
| Stale-date catch-up (53 days) | 53 × (Run + Complete) = 106 actions | 53 POSTs, each stoppable by blockers |
| Hazard on a stale date | none from rent (posts none) | rent for any `CheckedIn` guest on every closed date |
| Fit with "operator initiates, observable, auditable" | UI-visible, but the close writes no audit row | auditable per posting, but no UI and a direct POST |
| Touches D11 / Q06-H1 | closing 2026-08-10 seals the five D11 rows (BD-D3 applies to both). The guard protects 2026-08-09 only | same |

## 4. What is not known

| # | Question | Status |
|---|---|---|
| U-1 | Do any report, GST computation or invariant depend on `room_rent` `ExtraCharge` rows existing? If Alt 1 never writes them, which figures differ from a day closed by Alt 2? | **NOT VERIFIED** |
| U-2 | Do the two paths seal identical snapshots for the same day? | **NOT VERIFIED** |
| U-3 | `notification_queue` statuses on production (4 rows; any `pending` would be sent by the 5-minute flush on any start) | **NOT VERIFIED**; read-only check on a copy needed before any start |
| U-4 | In-house or reserved stays on production today | **NOT VERIFIED** (the 2026-09-09 evidence says none) |

## 5. Preparation that needs no decision and needs a separate authorization

**Copy experiment C-3.** Run Alt 1 and Alt 2 for the same date on two disposable copies of production, with the clock deliberately different from the business date and no live `.env`. Record rows written per table, snapshot content and hash, `inv-run` after each, and the effect on reports (U-1, U-2). It would be a verification pack under the SR-1 method. It is **not performed**.

## 6. Decisions requested

| # | Question | Options |
|---|---|---|
| D10-1 | Which path does the first-release written daily-close procedure name? | (a) Alt 1; (b) Alt 2, which also needs a form or an authorized non-UI call; (c) decide after C-3 |
| D10-2 | If Alt 1: is a day with no room-rent rows and no automatic no-show processing acceptable, with no-shows handled by the manual route? | (a) accept; (b) not acceptable, so harmonize in Phase 3 unit 3.2; (c) decide after C-3 |
| D10-3 | Does harmonizing the paths (one close, one set of effects, and the in-house date condition at `services.py:364`) belong in unit 3.2? | (a) yes; (b) first release lives with the chosen path |
| D10-4 | Which path would carry the 53-date catch-up (BD-D2)? | decided with BD-D1…BD-D5, not here; the table in §3 is the input |

## 7. Out of scope for this package

Force Close (`night_audit_advance_date`, `app/reports.py:3545`, which sets the date to the calendar at `:3595`), the Skipped-day re-run, and the destructive initialization tool are not operator close paths. They are covered by BD-D2.
