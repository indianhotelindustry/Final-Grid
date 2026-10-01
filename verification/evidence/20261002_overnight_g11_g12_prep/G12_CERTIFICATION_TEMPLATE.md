# G12 Production Certification — EMPTY TEMPLATE

> **This is a blank template prepared on 2026-10-02 (FG-OVERNIGHT-01). It records no certification, no verdict and no readiness.** Every result field is empty and must be filled only from committed evidence packs at the named release tag, under a Founder directive. G12 status today: NOT REACHED (`verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:42`).

Sources of the template's structure:
- Deployment condition — `CERTIFICATION_GATES.md:5`.
- Dimensions table of the gate document — `CERTIFICATION_GATES.md:9-25`.
- Gates G1–G12 — `CERTIFICATION_GATES.md:29-42`; scoring rule `:50`.
- Declared-exception register — FD-P2-03 (`verification/FOUNDER_DECISIONS.md:1146-1155`), rows named in D11-F2 (`:47-58`) and FD-010 (`:622-624`).
- Certification record — "a Founder-signed certification entry in `FOUNDER_DECISIONS.md` naming the tag, the anchor, the gates and their packs" (`CERTIFICATION_GATES.md:25`); durable-record rule FD-018 (`FOUNDER_DECISIONS.md:817-835`).

Allowed values in result fields: PASS / FAIL / BLOCKED / OPEN / NOT VERIFIED / NOT AUTHORIZED / NOT APPLICABLE, plus — for the `inv-run` verdict only — PASS-WITH-DECLARED-EXCEPTION as defined by FD-P2-03 (`FOUNDER_DECISIONS.md:1154`).

---

## 1. Identification

| Field | Value |
|---|---|
| Certification directive id |  |
| Release tag |  |
| Release commit SHA (full) |  |
| `version.txt` at tag |  |
| Production database anchor at certification: path |  |
| Production database anchor: SHA-256 |  |
| Production database anchor: size (bytes) |  |
| Production business date at certification |  |
| `night_audit_enabled` at certification |  |
| Latest applied migration at certification |  |
| Schema fingerprint expected for the tag |  |
| Schema fingerprint observed |  |
| Database engine (SQLite / PostgreSQL) |  |
| Operator model in force (FD-P2-01 or later ruling) |  |
| Date / time of certification (IST, UTC) |  |
| Prepared by |  |
| Reviewed by |  |

## 2. Deployment condition (`CERTIFICATION_GATES.md:5`)

| # | Condition | Evidence pack(s) | Result |
|---|---|---|---|
| DC-1 | All production-blocking gates PASS |  |  |
| DC-2 | No unexplained regression |  |  |
| DC-3 | Recovery rehearsal PASS |  |  |
| DC-4 | Deployment rehearsal PASS |  |  |
| DC-5 | Formal production certification recorded |  |  |

## 3. Gates (`CERTIFICATION_GATES.md:29-42`)

A gate is PASS only with a committed evidence pack at the release tag (`:50`). "Blocking" column copied from the gate document; MP-D9 rule for G4 (`:34`, `:50`).

| Gate | Required condition (abridged; see source line) | Blocking | Evidence pack path(s) at the tag | Pack commit | Result | Notes / declared items |
|---|---|---|---|---|---|---|
| G1 Architecture | every ADR the release exercises ADOPTED (`:31`) | yes |  |  |  |  |
| G2 Governance | decisions durable; evidence committed; no rewrite (`:32`) | yes |  |  |  |  |
| G3 Financial integrity | attribution; coupling 24/24; K-7 dating; CF-11; Q06; SR-1/SR-2 (`:33`) | yes |  |  |  |  |
| G4 Authorization | matrix for roles in use; negative matrix (`:34`) | yes if multi-role |  |  |  |  |
| G5 Auditability | strict coupling; no `audit_logs` deletion; ADR-011 envelope (`:35`) | yes |  |  |  |  |
| G6 Business-date integrity | single derivation; close/reopen/interrupted-close; staleness; N7 (`:36`) | yes |  |  |  |  |
| G7 Database integrity | FK check 0; fingerprint = tag; no pending migration; B-4 before schema change (`:37`) | yes (fingerprint, no-pending-migration) |  |  |  |  |
| G8 Recovery | backup API + integrity record; `.enc` off-box restore; FD-P2-04 verified state; retention (`:38`) | yes |  |  |  |  |
| G9 Reliability | scheduler jobs documented; night audit manual by ruling; launchers reproducible (`:39`) | yes (launchers, scheduler settings) |  |  |  |  |
| G10 Regression | GM 0 undeclared; replay 0; invariants declared movement only; datasets; 2a matrix; Q14; anchor (`:40`) | yes |  |  |  |  |
| G11 Deployment rehearsal | upgrade, fresh install, launchers, day-one, N-day close, rollback; G10 after each (`:41`) | yes |  |  |  |  |
| G12 Certification | G1–G11 as required; D11 verdict ruled; Founder entry (`:42`) | yes |  |  |  |  |

## 4. FD-P2-03 declared-exception register

### 4.1 Ruling (verbatim, `FOUNDER_DECISIONS.md:1148-1150`)

> CERTIFY THE EIGHT D11 COMMISSIONING/TEST FINANCIAL ROWS AS A DECLARED HISTORICAL EXCEPTION. Preserve all eight rows exactly; do not delete, reverse or reattribute; do not alter invoices/GST history; do not exempt the universal invariant itself; certification must explicitly identify the eight-row D11 exception; any additional unexplained exception is a certification failure. This ruling does not authorize financial mutation.

Implementation consequence (`:1154`): the G12 pack "carries a declared-exception register naming the eight objects and asserts that the `inv-run` violation set equals it; the verdict is then recordable as PASS-WITH-DECLARED-EXCEPTION. Until a certification engine exists the comparison is performed and evidenced manually."

### 4.2 Declared set D (the eight objects — declaration, not observation)

Declared values are copied from D11-F2 (`FOUNDER_DECISIONS.md:47-58`) and FD-P2-03 (`:1152`). Observed columns are blank.

| # | Object | Declared amount (₹) | Declared business date | Declared reservation | Declared `folio_id` | Observed: present | Observed: amount | Observed: business date | Observed: `folio_id` | Observed: row digest | Unchanged since FD-010 recording? | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| D-1 | `payments` id 1 | 800.00 | 2026-08-09 | 1 | NULL |  |  |  |  |  |  |  |
| D-2 | `payments` id 2 | 400.00 | 2026-08-09 | 1 | NULL |  |  |  |  |  |  |  |
| D-3 | `payments` id 3 | 1,500.00 | 2026-08-10 | 2 | NULL |  |  |  |  |  |  |  |
| D-4 | `payments` id 4 | 1,000.00 | 2026-08-10 | 3 | NULL |  |  |  |  |  |  |  |
| D-5 | `payments` id 5 | 500.00 | 2026-08-10 | 4 | NULL |  |  |  |  |  |  |  |
| D-6 | `payments` id 6 | 100.00 | 2026-08-10 | 4 | NULL |  |  |  |  |  |  |  |
| D-7 | `extra_charges` id 1 | 380.95 | 2026-08-09 | 1 | NULL |  |  |  |  |  |  |  |
| D-8 | `extra_charges` id 2 | 95.24 | 2026-08-10 | 4 | NULL |  |  |  |  |  |  |  |
| | **Total** | **4,776.19** | | | | | | | | | | |

Related records preserved by ruling (not exception objects; recorded for completeness): GST invoices `INV-2026-000029` … `INV-2026-000032` (`FOUNDER_DECISIONS.md:1152`); the sealed `NightAuditLog` for `audit_date = 2026-08-09` (Q06-H1, `:1219-1227`).

| Related record | Observed unchanged? | Evidence | Result |
|---|---|---|---|
| Invoices INV-2026-000029 … 000032 |  |  |  |
| Sealed NightAuditLog 2026-08-09 (snapshot hash) |  |  |  |

### 4.3 Observed violation set V (from the certification `inv-run`)

| Field | Value |
|---|---|
| `inv-run` pack path |  |
| Database the run read (path, SHA-256) |  |
| Commit of the invariant engine |  |
| OVERALL VERDICT printed by the engine |  |
| Registered / HOLDS / VIOLATED / VACUOUS / NOT_APPLICABLE / ERROR / Uncommissioned |  |

| # | Invariant | Tier | Object | Amount | In D? |
|---|---|---|---|---|---|
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

Reference only (not a pre-filled observation): at the last recorded production run (2026-09-30, post-migration 10.0.0, `20260930_adr011_production_application/post_inv.log:99-236`) the engine reported **INV-A02** VIOLATED on the eight D objects and **INV-A03** VIOLATED on `extra_charge` 1 and 2 (the two D objects that are charges) — 10 (invariant, object) pairs over 8 distinct objects. The comparison key below therefore needs a ruling (GD-D13).

### 4.4 Assertion: violation set equals declared set

Compute both forms; the ruled form (GD-D13) decides the result.

| Form | Definition | V | D | V \ D (must be empty) | D \ V (must be empty) | Equal? |
|---|---|---|---|---|---|---|
| A — object level | V = distinct objects appearing in any VIOLATED invariant |  | {D-1 … D-8} |  |  |  |
| B — (invariant, object) level | V = all (invariant, object) pairs; D' = the declared pairs ruled under GD-D13 |  |  |  |  |  |

| Field | Value |
|---|---|
| Comparison form ruled (A / B / other) and ruling reference |  |
| Any violation outside D (FD-P2-03: "certification failure") |  |
| Any D object no longer violating (would indicate the row changed — FD-010 forbids change) |  |
| Invariants VACUOUS at certification (listed, never shown as green — `MASTER_PLAN.md:262`) |  |
| `inv-run` verdict recorded (PASS-WITH-DECLARED-EXCEPTION only if the assertion holds) |  |
| Performed manually? (FD-P2-03: manual until a certification engine exists) |  |
| Performed by / reviewed by |  |

## 5. Other declared / ruled items to carry into the record

| Item | Ruling | What the certification must state | Evidence | Result |
|---|---|---|---|---|
| Q06 replay deltas (2026-08-09 BLOCK 2285.7→1142.85; 2026-08-10 INFO 5904.76→2952.38) — stored replay baseline not re-frozen | Q06-H1/H2/H3 (`FOUNDER_DECISIONS.md:1219-1246`); `20260923_q06_fix/Q06_REGRESSION.md:36-45` | how G10 "replay 0" is read at the tag (GD-D9) |  |  |
| Cross-implementation divergences (15 AGREED / 4 DIVERGED / 1 SINGLE_SOURCE / 2 VACUOUS, pre-existing at 2026-09-30) | none specific | explained / declared / open | `ADR011_PRE_PRODUCTION_GATE_REPORT.md:66` |  |
| INV-D02 population VACUOUS on production; refunds predating snapshot fields unsupported | SR2-REV2 limitations (`FOUNDER_DECISIONS.md:1345-1350`) | stated as limitation |  |  |
| ADR011-SA live HUMAN provenance | `20260930_135930_adr011_live_human_provenance/REPORT.md` | referenced |  |  |
| Notification-queue rows mutated by the scheduler on 2026-09-30 | disclosed, not reverted (`20260930_135930…/REPORT.md:50-55`) | referenced |  |  |

## 6. Regression evidence at the tag (G10 detail)

| Suite | Expected (gate text / ruling) | Pack path | Observed | Result |
|---|---|---|---|---|
| Golden Master `phase1_aa6d9e91` | 0 undeclared differences |  |  |  |
| Replay | 0 (see §5 / GD-D9) |  |  |  |
| Invariants | declared movement only (§4) |  |  |  |
| Five datasets | PASS |  |  |  |
| Phase 2a matrix | 29/29 |  |  |  |
| Q14 | as declared |  |  |  |
| Production anchor | unchanged during the runs |  |  |  |

## 7. Carry-forwards and backlog items at certification

Each row needs an explicit disposition (CLOSED with pack / OPEN non-blocking with ruling reference / BLOCKING). Register sources: `FOUNDER_DECISIONS.md:1200-1202`, `:1248-1250`; `20260910_phase2_founder_resolution/CARRY_FORWARD_REGISTER.md`; `verification/adr/BACKLOG.md`.

| Item | Disposition | Evidence / ruling | Blocking? |
|---|---|---|---|
| CF-5 unauthorized-role verification |  |  |  |
| CF-6 replay coverage of `attribution_control` |  |  |  |
| CF-9 deployment verification |  |  |  |
| CF-10 audit-coupling normalization |  |  |  |
| CF-11 credit-path defects |  |  |  |
| SR-1 INV-B06 |  |  |  |
| SR-2 INV-D02 |  |  |  |
| K-7 business-date dating |  |  |  |
| Q06-H2 forward correction |  |  |  |
| B-1 scheduler controls ADR |  |  |  |
| B-3 D11 row disposition (Phase 5) |  |  |  |
| B-4 migration mechanism |  |  |  |
| B-6 audit retention design |  |  |  |
| B-11 backup/restore mechanics |  |  |  |
| FD-P2-07 maker-checker (policy only) |  |  |  |
| Webhook audit gaps |  |  |  |
| PostgreSQL verification |  |  |  |
| Guest data in git history |  |  |  |
| Other: |  |  |  |

## 8. Founder certification entry — skeleton for `FOUNDER_DECISIONS.md`

To be written only by a Founder directive; append-only (FD-018). Every field blank.

```
# Production Certification — <directive id>

| | |
|---|---|
| Recorded | <date> |
| Release tag | <tag> (<full SHA>) |
| Production anchor | instance/pms.db <SHA-256>, <bytes> B, business date <date> |
| Gates | G1 <result, pack> · G2 <…> · G3 <…> · G4 <…> · G5 <…> · G6 <…> · G7 <…> · G8 <…> · G9 <…> · G10 <…> · G11 <…> |
| D11 | declared-exception register <pack path>; assertion form <A/B>; inv-run verdict <…> |
| Declared items | <list> |
| Open non-blocking items | <list with rulings> |
| Kind | <Founder wording> |

> <Founder certification text>
```

## 9. Signatures

| Role | Name | Signature / reference | Date |
|---|---|---|---|
| Founder |  |  |  |
| Preparer |  |  |  |
| Reviewer |  |  |  |
