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
