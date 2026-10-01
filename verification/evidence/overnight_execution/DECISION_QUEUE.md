# DECISION QUEUE — FG-OVERNIGHT-01

Non-blocking founder queue. Each entry is executable. Full packages live in the cited files; this queue is the index plus the essentials. A decision listed here is **not** acted on until the founder rules. Questions are never re-asked: if the founder has answered, the answer is recorded in `verification/FOUNDER_DECISIONS.md` and the entry here is marked RULED with the citation.

Priority: **P1** unblocks a G3 item or a production risk · **P2** unblocks preparation/gates · **P3** governance record completeness.

| DQ | Pri | Workstream | Question (one line) | Package | Status |
|---|---|---|---|---|---|
| DQ-01 | P1 | SR-1 | Exact INV-B06 text for payments dated before arrival: which classes (advance / booking-time voucher redemption / corrections of those), and what lead bound (none / N days / anchor)? | `20261002_overnight_sr1/SR1_DECISION_REQUIRED.md` SR1-D1 | OPEN |
| DQ-02 | P1 | SR-1 | How INV-B06 treats cancellation refunds and correction pairs dated outside the stay (exclude / inherit window / bounded by cancellation with explicit basis / unchanged)? | same, SR1-D2 | OPEN |
| DQ-03 | P1 | SR-1 | Which negative seeds/scenarios the amended INV-B06 must fail on? | same, SR1-D3 | OPEN |
| DQ-04 | P2 | SR-1 × K-7 | SR-1 before K-7 (basis-independent clauses), after K-7, or split? | same, SR1-D4 | OPEN |
| DQ-05 | P3 | SR-1 governance | Does the SR-1 directive itself carve out Phase 6 "Not touched: invariant semantics" (as SR-2 implicitly did)? | same, SR1-D5 | OPEN |
| DQ-07 | P3 | ADR-011 | Adopt ADR-011 now (qualified, as ADR-005/007), in part, keep PROPOSED, or supersede? | `20261002_overnight_adr011_adoption/ADR011_FORMAL_ADOPTION_REQUIRED.md` A11-D1 | OPEN |
| DQ-08 | P3 | ADR-011 | Does a SYSTEM row with NULL `staff_user_id` (+ required mechanism) satisfy ADR item 4 "never NULL and never admin"? | same, A11-D2 | OPEN |
| DQ-09 | P3 | ADR-011 | Confirm the four implementer readings (unknown actor refused; unauthenticated = SYSTEM `web:unauthenticated`; history = HUMAN; role/shift/mechanism not reconstructed) | same, A11-D3 | OPEN |
| DQ-10 | P3 | Governance record | Record the in-session ADR-011 authorizations (branch-only delivery, 10.0.0 production application, boot-time mechanism use, rollback path, live check) in `FOUNDER_DECISIONS.md` (`:1290` still says "not implemented") | same, A11-D4 | OPEN |
| DQ-11 | P2 | ADR-011 × webhook | Are the webhook audit gaps in ADR-011 scope and do they block adoption? | same, A11-D5 (see also webhook package) | OPEN |
| DQ-12 | P3 | ADR-011 | Is a failed login recorded as HUMAN naming the targeted account (`app/auth.py:110-117`, pre-existing) acceptable? | same, A11-D6 | OPEN |
| DQ-13 | P1 | G3 | May G3 PASS with K-7 delivered as Phase 3 unit 3.1 while G6 stays open? | `20261002_overnight_gates_g3_g6/GATES_DECISION_REQUIRED.md` GT-D1 | OPEN |
| DQ-14 | P2 | Gates A–H | Restate Gates A–H, retire them in favour of G1–G12, or have each directive state its gates? (definitions unrecoverable) | same, GT-D5; `G6_GATE_DEFINITIONS_MISSING.md` | OPEN |
| DQ-15 | P1 | Phase 3 / K-7 | Phase 3 directive scope: units, K-7 sites, `get_business_date()` fallback, B-10 items, reports, re-baselining, fresh-install `night_audit_enabled` default | same, GT-D6 (detail in K-7 package) | OPEN |
| DQ-16 | P1 | Production business date | How and when the stale production business date is brought current relative to any K-7 deploy | same, GT-D7 (detail in business-date package) | OPEN |
| DQ-17 | P2 | G10 | Golden Master WARN 156/158 recapture/declare; "replay 0" vs governed Q06-H2 deltas; record new production anchor `21dc0e97…` (SC-1 still names `51dd83b7…`) | same, GT-D8 | OPEN |
| DQ-18 | P2 | G1/G5 | Which ADRs the first release exercises; webhook gaps in G5? | same, GT-D9 (overlaps DQ-07, DQ-11) | OPEN |
| DQ-19 | P3 | Governance record | Durably record the CF-10/CF-11 directive and the Q06-H2/CF closures (register at `FOUNDER_DECISIONS.md:1250` still lists them OPEN) | same, GT-D10 (overlaps DQ-10) | OPEN |
| DQ-20 | P2 | B-4 / G7 | Resolve B-4 now, or record migration 10.0.0 as an exception to "decide B-4 before the first schema change" | same, GT-D11 (detail in B-4 package) | OPEN |
| DQ-21 | P2 | Phase 3 × maker-checker | With a single Admin, how do night-audit override (3.3) and reopen (3.4) meet FD-P2-07? | same, GT-D12 | OPEN |
| DQ-22 | P2 | G3 | Does G3 include "reconciliation views agree" (bringing in the Q17/Q20 divergences)? | same, GT-D13 | OPEN |
| DQ-23 | P2 | Release | Name the release-candidate tag (no gate can PASS without one) | same, GT-D14 | OPEN |
| DQ-24 | P2 | G8 | Issue the FD-P2-04 recovery-hardening directive (backups still `shutil.copy2`, `app/backup_manager.py:208`) | same, GT-D15 | OPEN |
| DQ-25 | P3 | G9 | Execute the FD-017 launcher CRLF fix | same, GT-D16 | OPEN |
| DQ-26 | P1 | B-4 | Single schema authority (inline registry / Alembic / new); fate of the SQLite column fixer, table bootstrap and `update.bat` patch | `20261002_overnight_b4_postgresql/B4_DECISION_PACKAGE.md` B4-D1 | OPEN |
| DQ-27 | P1 | B-4 | May migrations keep running automatically at startup, or flag-gated / separate command with read-only boot? | same, B4-D2 (overlaps DQ-20) | OPEN |
| DQ-28 | P2 | B-4 | Stop the automatic boot-time data writes (seeds, owner promotion, `ota_channel` fill)? | same, B4-D3 | OPEN |
| DQ-29 | P1 | B-4 / G8 | Tie every migration to a verified pre-migration backup (which path); exempt pre-update backups from the 30-day purge? | same, B4-D4 | OPEN |
| DQ-30 | P2 | B-4 | Move the production database out of the application working tree? | same, B4-D5 | OPEN |
| DQ-31 | P1 | B-4 / B-1 | Should startup keep registering every scheduled job, including guest messaging gated only by credentials? | same, B4-D6 | OPEN |
| DQ-32 | P2 | PostgreSQL | Is PostgreSQL a first-release target, or NOT APPLICABLE until MP-D4? | `20261002_overnight_b4_postgresql/POSTGRESQL_VERIFICATION_BLOCKER.md` PG-D1 | OPEN |
| DQ-33 | P2 | PostgreSQL | Which server (18 @5432 / 13 @5433 / new), owner, throwaway role+DB, credential hand-over (env only), verification venv with pinned `psycopg[binary]` | same, PG-D2…PG-D4 | OPEN |
| DQ-34 | P2 | PostgreSQL | Verification levels L1–L4, acceptance criteria, authority to port the SQLite-bound harness | same, PG-D5 | OPEN |
| DQ-35 | P1 | Host security | Separate read-only review of two PostgreSQL services listening on all interfaces (0.0.0.0/::) on the production host | same, PG-D6 | OPEN |
| DQ-36 | P2 | G11 | May a non-certifying dry-run rehearsal (M-DRY) happen before G3/G5/G6/G8/G9 pass? | `20261002_overnight_g11_g12_prep/G11_G12_DECISION_REQUIRED.md` GD-D1 | OPEN |
| DQ-37 | P1 | G11 / G8 | Source database for the rehearsal copy; authorize a read-only `tools/backup_db.py` run against the live folder? (**No verified backup of current production state `21dc0e97…` exists**; newest recovery point `12ba7b7e…` predates the founder's logins and the 2026-09-30 notification retry) | same, GD-D2 (overlaps live-data retention) | OPEN |
| DQ-38 | P2 | G11 | Rehearsal machine, clone vs worktree (worktrees share the live `.git`; precedent harness loads the live `.env`), key material | same, GD-D3 | OPEN |
| DQ-39 | P2 | G11 | Upgrade mechanism (git ff / signed web updater / `update.bat` — unsigned, continues on failed backup) and signing-key custody | same, GD-D5 | OPEN |
| DQ-40 | P2 | G11 | Fresh-install path in scope? install artefact (`setup.bat` missing); FD-P2-05 on fresh install (BUG FG-ON-01) | same, GD-D6 | OPEN |
| DQ-41 | P2 | G11 / G6 | Multi-day run N, pass criteria for reopen and interrupted close; daily-close entry point (close vs `advance-date`) | same, GD-D7, GD-D8 (overlaps DQ-16) | OPEN |
| DQ-42 | P2 | G11 | In-place restore (PD-004 act) pre-authorized? Is data rollback after go-live allowed at all? | same, GD-D11 | OPEN |
| DQ-43 | P2 | G11 / B-1 | Which standing scheduler jobs may run during rehearsal/go-live; are their start-up mutations accepted? | same, GD-D12 (overlaps DQ-31) | OPEN |
| DQ-44 | P2 | G12 | D11 declared-exception comparison on the 8 objects or the 10 (invariant, object) pairs (INV-A03 ×2 on extra_charges 1–2)? | same, GD-D13 | OPEN |
| DQ-45 | **P1** | Privacy | A real production guest phone number (masked `62xxxxxx95`) is **still in the current tree** (10 occurrences: `20260909_phase1_verification_completion/writers_setA.txt` ×6, `writers_setD.txt` ×4) and in 34 commits on all four remote branches. Forward-only redaction now / redaction now + rewrite later / rewrite now / no action? | `20261002_overnight_webhook_privacy_copies/GIT_HISTORY_PRIVACY_DECISION.md` GH-D1 | OPEN |
| DQ-46 | P2 | Privacy | If history is rewritten: how evidence hashes are re-anchored (185 files, 5 "Governed HEAD" lines) and how the production folder's `.git` is handled | same, GH-D2 | OPEN |
| DQ-47 | P1 | Privacy | Control to stop harnesses leaking guest data into evidence (synthetic guests/stubs, pre-commit scan, masking in app) | same, GH-D3 | OPEN |
| DQ-48 | P2 | Webhook / Q5-P1 | Are webhook reservation/folio/status writes "financial mutations" under Q5-P1? Which audit behaviour per path (strict / same-txn / none)? | `20261002_overnight_webhook_privacy_copies/WEBHOOK_DECISION_REQUIRED.md` WH-D1, WH-D2 (overlaps DQ-11) | OPEN |
| DQ-49 | P2 | Webhook / ADR-011 | Operator-triggered retry (`/ota/webhook/retry`) recorded as SYSTEM with no user — should it be HUMAN? | same, WH-D3 | OPEN |
| DQ-50 | P1 | Webhook / production | Does the production webhook stay armed (API key set) while the audit gaps are open? | same, WH-D4 | OPEN |
| DQ-51 | P2 | Webhook | Authorize a bounded runtime check on a copy (post-ADR-011 audit-failure case, lost `webhook_logs` row, retry provenance) | same, WH-D5 | OPEN |
| DQ-52 | P2 | Webhook | Must an OTA webhook cancellation go through the cancellation-disposition path (`routes.py:8853-8879`)? | same, WH-D6 | OPEN |
| DQ-53 | P1 | Live-data copies | Which artifacts are the retained recovery points, where is the recovery store, is a fresh backup of `21dc0e97…` needed? | `20261002_overnight_webhook_privacy_copies/LIVE_DATA_RETENTION_DECISION.md` LD-D1 (overlaps DQ-37) | OPEN |
| DQ-54 | P2 | Live-data copies | Keep or dispose of the 15 derived working copies; the three identical `99505a47` backups; location/access/encryption/retention of kept copies (all hold guest personal data, unencrypted) | same, LD-D2, LD-D3, LD-D5 | OPEN |
| DQ-55 | P2 | Live-data copies | What is `SukoonPMS.zip` (120 MB, 2026-09-19, unreferenced); may its entry names be listed; keep? | same, LD-D4 | OPEN |
| DQ-56 | **P1** | Q06-H1 protection | While the business date is 2026-08-10, an operator Reopen of 2026-08-09 would mutate the sealed Q06-H1 record (BUG FG-ON-20). Accept the exposure until the date advances, require an operating instruction (no reopen of 2026-08-09), or authorize a code guard? | `20261002_overnight_k7_analysis/BUSINESS_DATE_PRODUCTION_DECISION.md`; `BUG_INDEX.md` FG-ON-20 | OPEN |
| DQ-57 | P1 | K-7 / Phase 3 | Issue a Phase 3 directive for unit 3.1 (alone / with 3.5–3.6 / whole phase); waive or require the B-1 scheduler ADR (`MASTER_PLAN.md:370`) and Gates A–H | `20261002_overnight_k7_analysis/K7_DECISION_REQUIRED.md` K7-D1 (overlaps DQ-15) | OPEN |
| DQ-58 | P1 | K-7 | Sites in scope (core 8 writers, voucher issue/expiry, 3 secondary calendar fallbacks, late checkout + preview, void/shift UTC-day mapping, documents, reports) | same, K7-D2, K7-D4, K7-D5, K7-D6 | OPEN |
| DQ-59 | P1 | K-7 | `get_business_date()` fail-closed vs calendar; replacement for `date.today` model defaults (NULL / UTC-table-default hazard, `app/__init__.py:1794`) | same, K7-D3 | OPEN |
| DQ-60 | P2 | K-7 | Evidence standard; basis-checking invariant (B-10 #4); frozen suites superseded or re-baselined (Golden Master cannot detect K-7) | same, K7-D7 | OPEN |
| DQ-61 | P1 | K-7 deploy | May K-7 deploy before the business date is current? (separate production authorization either way) | same, K7-D8 (overlaps DQ-16) | OPEN |
| DQ-62 | P2 | K-7 / night audit | Close-path divergence (panel Run+Complete posts no room rent / no-shows; `run_night_audit` does both and posts rent for every checked-in reservation with no date condition) — in 3.1, 3.2, or accepted? | same, K7-D10 | OPEN |
| DQ-63 | P2 | Defects | Register and route defect candidates N-7 (UTC invoice/GST dates), N-8 (GSTR-1 credit-note bound), N-10 (no-show TypeError) | same, K7-D11; `BUG_INDEX.md` FG-ON-21…23 | OPEN |
| DQ-64 | **P1** | Business date | When: bring current now / on the first trading day / after Phase 3 units 3.5–3.6 | `BUSINESS_DATE_PRODUCTION_DECISION.md` BD-D1 (= DQ-16 detail) | OPEN |
| DQ-65 | P1 | Business date | Mechanism: panel close ×53 / `run_night_audit` ×53 / close 2026-08-10 then Force Close / Force Close all (no snapshot, no AuditLog — FG-ON-13) / direct SQL | same, BD-D2 | OPEN |
| DQ-66 | P1 | Business date / D11 | May 2026-08-10 (five D11 rows) be closed or marked Skipped under FD-010 / FD-P2-03? | same, BD-D3 | OPEN |
| DQ-67 | P2 | Business date | Target date, time-of-day for closes, interim staleness rule (B-10 #5) | same, BD-D4 | OPEN |
| DQ-68 | P1 | Business date | Authorization path (PD-004/PD-005, FD-P2-04 conditions 1–7, 9, 10), full rehearsal on a copy, read-only pre-checks incl. `notification_queue` statuses before any start | same, BD-D5 (overlaps DQ-37) | OPEN |
| — | — | duplicates | K7-D9 = DQ-13 (G3 on unit 3.1) |
| — | — | duplicates | GD-D4 = DQ-23 (release tag) · GD-D9 = DQ-17 (G10 baselines) · GD-D10 = DQ-27 (B-4) |
| — | — | duplicates | B4-D7 = handled by correction record (`20261002_overnight_adr011_adoption/CORRECTION_RECORD_…`); remaining question "change version checks going forward" folded into DQ-26 |
| — | — | duplicates | GT-D2 = DQ-01…DQ-04 · GT-D3 = DQ-05 · GT-D4 = DQ-06 (not re-asked) | — | — |
| DQ-06 | P3 | Governance record | Record the founder's authorization to push/merge SR-2 to `origin/main` (Round 7, `FOUNDER_DECISIONS.md:1354`, still says "Push and merge remain separately unauthorised", but `origin/main` = `c9eeff0` contains it) | this file, below | OPEN |

---

## DQ-06 — Missing governance record of SR-2 integration

- **DECISION ID:** DQ-06
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** governance record (FD-018 durable governance records)
- **QUESTION:** Will the founder record (or have recorded) the authorization under which `sr2-inv-d02` (`94cb87a..c9eeff0`) was pushed and integrated into `origin/main`?
- **WHY REQUIRED:** Round 7's last line (`FOUNDER_DECISIONS.md:1354`) says push and merge are unauthorized. The remote state shows integration, and directive FG-OVERNIGHT-01 §3 states "SR-2 = integrated into remote main". Without a record, an auditor reading the repository alone sees an unauthorized push.
- **OPTIONS:** (a) founder dictates a short Round 8 entry (date, scope: push of `sr2-inv-d02` and fast-forward of `origin/main` to `c9eeff0`; live checkout not updated); (b) treat directive FG-OVERNIGHT-01 §3 as the record and cite it.
- **EVIDENCE:** `git log origin/main` shows `94cb87a…c9eeff0` dated 2026-09-30/10-01; `FOUNDER_DECISIONS.md:1328,1354`.
- **DEPENDENCIES:** none.
- **WHAT IS BLOCKED:** nothing technical.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** append the dictated entry verbatim to `FOUNDER_DECISIONS.md` in a governance-record commit.

---

(Entries from the K-7, gates, G11/G12, B-4/PostgreSQL, webhook/privacy/copies and ADR-011 workstreams are appended as each package is reviewed.)
