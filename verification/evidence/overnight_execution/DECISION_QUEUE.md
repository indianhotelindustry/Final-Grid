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
