# FinalGrid Production Certification Model — twelve gates

Directive FG-P2-ENTRY-READINESS-20260910-01, sections 6–7. "100% readiness" means **100% of the agreed production-blocking gates passing**, with evidence, not a percentage of tasks and not a claim of bug-free software.

**Deployment condition:** ALL PRODUCTION-BLOCKING GATES PASS **and** NO UNEXPLAINED REGRESSION **and** RECOVERY REHEARSAL PASS **and** DEPLOYMENT REHEARSAL PASS **and** FORMAL PRODUCTION CERTIFICATION RECORDED.

## What "production ready" means for FinalGrid

Not "the application starts". Production ready means, at a named release tag, all of the following are true and evidenced:

| Dimension | Meaning |
|---|---|
| Application behaviour | the release tag boots on the operator machine through the shipped launchers, with no pending migration, the scheduler starting only the jobs the production settings allow, and the golden-master surfaces reproducing the adopted master with 0 undeclared differences |
| Financial correctness | every financial writer attributes to its folio, couples its audit row atomically, dates its row from the controlled business date; the night audit closes a day idempotently, reopens only under authorized override with retained reason, recovers from an interrupted close; reconciliation views agree; GST/invoice engines agree with each other |
| Data integrity | invariants show only declared movement against the pre-release pack; no orphan financial rows; D11 status explicitly ruled for the certification verdict; schema fingerprint equals the release tag's expectation |
| Authorization | every mutating route and every report route is reachable only by the roles the adopted matrix allows; negative matrix evidenced for the roles the property will actually use (MP-D9) |
| Auditability | financial audit rows cannot be silently lost — neither at write time (strict coupling) nor later (no destructive pruning of `audit_logs`); each row carries operator identity and provenance sufficient to explain it |
| Backup / restore | the *operating* backup path produces transactionally safe artifacts with an integrity record; a restore from an application-made encrypted backup has been rehearsed on another machine with documented key custody and proved to a Founder-confirmed "verified state" |
| Deployment procedure | a written, rehearsed procedure for fresh install and for upgrade of the existing instance, including the pre-update backup, the signed-package verification, the post-start checks, and who does what |
| Rollback procedure | a written, rehearsed procedure that returns the property to the previous tag and the pre-update backup, with the same verification afterwards |
| Operational startup | day-one procedure: set the business date, confirm scheduler settings, confirm users and roles, run the first close |
| Business-date behaviour | one derivation, one authoritative date, staleness escalation, midnight behaviour documented |
| Night audit | multi-day rehearsal on a copy: N consecutive closes, one reopen, one interrupted close recovered, invariants HOLD after each |
| Verification evidence | packs for every gate at the release tag, committed (SC-4), never edited |
| Certification record | a Founder-signed certification entry in `FOUNDER_DECISIONS.md` naming the tag, the anchor, the gates and their packs |

## The gates

| Gate | Required condition | Evidence | Blocking | Current status at `a84566ae` |
|---|---|---|---|---|
| **G1 Architecture** | Every architecture the release relies on is ADOPTED; no ADR the release exercises is still PROPOSED | ADR status table; `FOUNDER_DECISIONS.md` | yes | **PASS for the Phase 1 surface** (ADR-001/002/003/004/005/007/008 adopted). **Open** for what later gates need: ADR-010 (2b), ADR-009/011 (Phase 4 / accountability), ADR-006 (any mutation), ADR-012 (retention) |
| **G2 Governance** | Every decision the release relies on is recorded durably; evidence committed; no rewrite | acceptance entry; commit history; append-only proofs | yes | **PASS** (Phase 1 accepted; evidence committed; four 2026-08-31 rulings still unrecovered — recorded gap, not blocking) |
| **G3 Financial integrity** | attribution universal (done); strict coupling at all 24 writers (CF-10); business-date dating at all writers (K-7); credit/voucher paths functional (CF-11); GST engines agree (Q06 explained); SR-1/SR-2 resolved | writer runtime pack 24/24; Q06 analysis; rulings | yes | **PARTIAL** — attribution PASS; coupling 12/24; dating open; CF-11 open; Q06 unexplained |
| **G4 Authorization** | matrix adopted for the roles in use (MP-D9); folio (done), writers, reports enforced fail-closed; negative matrix per role | Phase 2a matrix (29/29); Phase 4 matrix | **yes if multi-role** (MP-D9); otherwise advisory | **PARTIAL** — folio endpoints PASS; ≥26 report routes and several writers login-only |
| **G5 Auditability** | strict coupling (G3); `audit_logs` never auto-deleted; provenance envelope per ADR-011 | prune test; audit coverage pack | yes | **FAIL** — destructive pruning still scheduled (~2026-11-07); coupling 12/24 |
| **G6 Business-date integrity** | single derivation; no wall-clock financial dating; night-audit close/reopen/interrupted-close semantics; staleness escalation; N7 multi-day sequence | Phase 3 packs; multi-day rehearsal | yes | **FAIL** — Phase 3 not started; production date 30 days stale; audit never nightly |
| **G7 Database integrity** | `foreign_key_check` = 0; schema fingerprint = tag expectation; no pending migration at boot; migration authority decided before any schema change (B-4) | `inv-run`; fingerprint; boot log | yes (fingerprint, no-pending-migration); FK-ON and NOT NULL **not** blocking | **PARTIAL** — 0 orphans, fingerprint stable, no pending migration; FK off (C), NOT NULL deferred (D), B-4 open (E, only bites on a schema change) |
| **G8 Recovery** | operating backup path = backup API + integrity record; restore rehearsed from an application `.enc` artifact off-box with key custody; "verified state" (B-5) confirmed; retention of pre-update backups | rehearsal packs; ADR-007 items 1–3 | yes (FD-005 PD-006, FD-006 D9) | **FAIL** — tool-path rehearsal PASS (RR-20260908-01); app path unverified; B-5 unconfirmed |
| **G9 Reliability** | scheduler jobs documented per production setting; night-audit automation either controlled (B-1) or manual by ruling; launchers reproducible (FD-017); health/observability adequate for the operator | job table; launcher rehearsal | yes (launchers, scheduler settings); observability advisory | **PARTIAL** — night audit disabled on production (interim); pruning uncontrolled; launchers LF-only |
| **G10 Regression verification** | at the release tag on copies: Golden Master 0 undeclared differences; replay 0; invariants declared movement only; five datasets PASS; Phase 2a matrix; Q14 as declared; production anchor unchanged | packs | yes | **PASS at `aa6d9e91`** (`phase1_aa6d9e91` 158/158; replay 10/10; datasets 5/5; 29/29; Q14 declared) — must be re-run at every later tag |
| **G11 Deployment rehearsal** | on a copy of the current instance: upgrade path (pre-update backup → signed package → boot → checks), fresh-install path, launchers on the operator machine, day-one business-date procedure, N-day operation with nightly close, rollback to the previous tag; each followed by G10 on the rehearsal copy | rehearsal packs; written procedure (`docs/RELEASE.md` or successor) | yes | **FAIL** — never performed; procedure document absent |
| **G12 Production certification** | G1–G11 as required; the D11 verdict question ruled (disposition or population declaration) so the `inv-run` verdict is readable; Founder certification entry recorded | `FOUNDER_DECISIONS.md` entry | yes | **NOT REACHED** |

## Gate dependencies

G3 ← P2-A1, P2-A2, Phase 3 (dating), Q06 analysis, SR rulings · G4 ← MP-D9, Phase 4 · G5 ← P2-A3, P2-A1 · G6 ← Phase 3 · G7 ← (B-4 only if schema changes) · G8 ← backup-path hardening + `.enc` rehearsal + B-5 · G9 ← P2-A5, B-1 or interim ruling · G10 ← every code change · G11 ← procedure + rehearsal after G3/G5/G6/G8/G9 · G12 ← all.

## Scoring rule

A gate is PASS only with a committed evidence pack at the release tag. A gate marked "advisory" for a single-operator property becomes blocking the moment a second role is created (MP-D9). No gate may be passed by weakening an invariant, a master, a dataset declaration or a matrix expectation (SC-5, Master Plan §07 Layer 1).
