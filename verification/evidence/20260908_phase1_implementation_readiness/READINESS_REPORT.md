# FinalGrid — Phase 1 Implementation Readiness Report

| | |
|---|---|
| Directive | FG-P1-IMPLEMENTATION-READINESS-20260908-01 |
| Recorded | 2026-09-08 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| Governed HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` (unchanged) |
| Database | `instance/pms.db` 733,184 B · `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` (unchanged) |
| Status | **PLANNING ONLY. Implementation authorized: NO. Production mutation authorized: NO.** |
| Companion artifacts | `FINANCIAL_WRITER_INVENTORY.md` · `PHASE1_EXECUTION_PLAN.md` · `MIGRATION_AND_DATA_PLAN.md` · `RECOVERY_GATE_PLAN.md` · `VERIFICATION_PLAN.md` · `FOUNDER_DECISION_GATE.md` · `result.json` |

## 1. Governance baseline applied

Adopted ADRs 001, 002, 003, 004, 005, 007, 008 (`verification/adr/README.md`); FD-001…FD-019; AR-001…AR-015; Master Plan §05 Phase 1 (units 1.1–1.8; **no schema migration**; unit 1.6 gated); FD-010 Option A; PD-004/005/006; Phase 2a frozen at `237db2ad`. No conflict with an adopted ADR was found. Three places where evidence sharpens the plan beyond the earlier artifacts are called out in §3.

## 2. What Phase 1 must and must not accomplish

**Must (Master Plan units, Level 2 only):** 1.1 folio lifecycle contract proven for every reservation-creation path · 1.2 attribution at source for every `ExtraCharge` writer · 1.3 attribution for every `Payment` writer including refund and corrections · 1.4 room-rent and room-upsell posting attributed under the adopted architecture *reservation operational ownership + folio financial ownership* · 1.5 U-1 (no permitted unattributed class) recorded and fixtures under contract · 1.7 reconciliation reads the folio-level figure beside the reservation figure and asserts equality · 1.8 INV-A02/INV-A03 re-verified per population.

**Must not:** touch the eight D11 rows (FD-010); assign historical folios; change schema, add a migration, make `folio_id` NOT NULL; enable FK enforcement in code (Phase 4/5); change business-date behaviour (Phase 3) unless ruled otherwise; create Folio B, route by company, or implement split billing (Level 3); add maker-checker (Phase 2b); reopen Phase 2a; rebase the golden master silently.

## 3. Findings from the code and data — what changed the plan

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | **The entire NULL-`folio_id` population on the live database is the eight D11 rows.** `payments` has 6 rows, `extra_charges` 2, all NULL, all created 2026-08-10/11, reservations 1–4, invoices 000029–000032, all `billing_responsibility='Guest'`, no companies, no void/credit-note/no-show/overpayment rows. | read-only queries, this review | The "legitimate existing financial data" migration population is **empty** on this database. Stage C is an evidence pack, Stage D/E are null operations, Stage F is satisfied by construction. Stage G (NOT NULL) stays blocked by the eight rows under FD-010. |
| F2 | **`PRAGMA foreign_key_check` returns 0 orphans across all 53 tables**; FK declarations exist on `payments` (5), `extra_charges` (3), `folios` (2); 42 of 53 tables declare FKs. | read-only pragma | ADR-005's orphan-scan prerequisite is met on the live file today; it must be re-run on a copy at enablement time. FK enforcement itself remains Phase 4/5. |
| F3 | **Audit atomicity gap confirmed** (§12). | `routes.py:312-334`, `pos.py:110-134` | Becomes a Phase 1 implementation requirement for every financial writer Phase 1 touches (Phase 2a `_audited` pattern). |
| F4 | **Business-date defects at seven sites** (corrections ×4, refund, voucher, overstay) plus one model-default site (checkout extra). | inventory | Recorded; **not** fixed in Phase 1 by default — dating changes move report figures and belong to Phase 3 (Founder to confirm, `FOUNDER_DECISION_GATE.md` Q-3). |
| F5 | **Application boot has side effects**: `create_app()` runs `_run_pending_migrations`, `init_data()`, and starts the scheduler (`app/__init__.py:486-604`). | code | "Application-open verification" of a restored database must use the verification harness's copy discipline (`dbcopy.make_copy()` + `inv-run`), never a plain boot against the restored file. Recorded in `RECOVERY_GATE_PLAN.md`. |
| F6 | **Alembic's `alembic.ini` points at production** (`sqlite:///…/instance/pms.db`, line 26) while no `alembic_version` table exists; the installer stamp-check would stamp to `c4d5e6f7a8b9`. Inline registry entries using `DO $$` are PostgreSQL-only and skipped on SQLite; SQLite schema evolution has in practice been `db.create_all()` on empty databases plus the column fixer. | `migrations/alembic.ini`, `app/__init__.py:616-640`, `installer/_alembic_stamp_check.py` | No mechanism can perform the SQLite table rebuild Stage G needs without new work. `MIGRATION_AND_DATA_PLAN.md` §6 — **FOUNDER / ARCHITECTURE DECISION REQUIRED** (B-4). Not needed for Phase 1 code. |
| F7 | Golden master captured 2026-08-03; `gm-verify` already FAILs (3,342 declared differences). | `evidence/20260831_160040_gm_verify_production` | Gate G cannot detect Phase 1 regressions against a stale master. Rebaseline is Phase 6 work; the plan asks the Founder to allow a pre-Phase-1 recapture as a verification-only action (Q-4). |
| F8 | Backup tooling `tools/backup_db.py` already provides API backup, `mode=ro` source, before/after hash, `integrity_check`, row-count comparison and a JSON manifest — i.e. six of ADR-007's seven target components. **Restore does not exist**; the application's own backup path (`shutil.copy2`, 30-day purge, encrypted) is weaker. | `tools/backup_db.py` | The recovery gate is closer than the readiness baseline implied, but still unsatisfied: no restore, no rehearsal, no restore record. |
| F9 | Eight report/other routes are reachable by any authenticated role (login only); `checkout` is login-only apart from an override check. | inventory | Not changed by Phase 1 (R6, Phase 4); negative tests define "unauthorized" against *today's* roles. |

## 4. Attribution design (all 24 writers)

One service-layer resolver, `resolve_billing_folio(reservation)` (name provisional), applying ADR-002 O-1/C-2/R-1:

| Question | Answer, applying to every writer unless noted |
|---|---|
| Reservation available? | **Yes at all 24 sites** (object or id). No writer is blocked. |
| Billing folio resolution | `Folio` where `reservation_id = reservation.id and folio_letter = 'A'`. Under Level 2 the billing folio is Folio A; letters B+ (creatable only via Phase 2a-guarded `create_folio`) are **never** selected by the resolver — no routing decision exists at Level 2. |
| Resolvable before creation? | Yes; the resolver runs inside the caller's transaction and the id is passed to the constructor (R-6). No post-insert update. |
| No folio exists | CD-1 default: create Folio A under the listener's rule, write an `AuditLog` row `folio_auto_created`, continue. Alternative (refuse) is the Founder's to choose (Q-1). |
| Multiple candidate folios | Not a case at Level 2: exactly one letter A per reservation (`uq_folio_letter`). If A is absent but B exists, that is a data fault → CD-1 path creates A and audits; it does not pick B. |
| Invalid reservation | Writers already validate/404; the resolver raises on a missing reservation and the posting fails inside the transaction (R-6). |
| Lookup failure | Exception → rollback → posting fails. **Fail-closed.** |
| Corrections/reversals (W-08/09/22/23) | Inherit (R-3). **If the original row's `folio_id` is NULL the correction is refused** — fail-closed, and it independently enforces FD-010 (the only NULL originals are the eight protected rows). Engineering default; Founder may override (Q-2). |
| Refund (W-10) | Attribute to the reservation's billing folio (R-4 / CD-3 default). |
| Verification | Per-writer Layer 2 test asserting `folio_id == Folio A id of the row's reservation`; INV-A02/A03 HOLD on the new-activity copy; negative test that a row constructed without the resolver fails the suite. |

## 5. Room-rent posting (adopted architecture)

- **Calculated:** per night from `ReservationNightRate.final_rate` (fallback `reservation.rate_per_night`) — reservation-owned operational truth (`services.py:120-146`).
- **Created:** `ExtraCharge(charge_type='room_rent')` by `run_night_audit` (W-21) per in-house reservation per business date; by `_rerun_skipped_audit` (W-16) for a missed date; `room_upsell` by `convert_overpayment_to_upsell` (W-24).
- **Folio:** resolver → Folio A of the reservation (R-2). Folio *balance* semantics (`calculate_folio_amount` excludes room revenue) are **unchanged** — an attribution change, not a balance change.
- **Night audit is the writer** for W-21; it runs unattended (scheduler) or manually (`routes.py:4835`). AR-013 controls are not yet designed; Phase 1 does not alter its trigger, authority or timing.
- **Duplicates:** existing idempotency (reservation × `room_rent` × `charge_date`, and `ReservationNightRate.is_posted`) is preserved verbatim; a rerun skips posted nights.
- **Business date:** `_bd` / `target_date` — already correct.
- **Audit:** `NightAuditLog` remains the audit of the run; per-row AuditLog is **not** added in Phase 1 (would change closed-day evidence volume); recorded as an AR-013 item.
- **INV-A02/A03:** proven on a disposable copy where a fresh stay is night-audited (T-R01).

## 6–11. Data treatment, staged NOT NULL, FK, recovery, backup/restore, migration mechanism

See `MIGRATION_AND_DATA_PLAN.md` and `RECOVERY_GATE_PLAN.md`. Headlines: classification method defined and, for the live database, already conclusive (population = D11); Stages A–H mapped to slices with Stage G outside Phase 1; FK enforcement designed at the SQLAlchemy engine `connect` event so that every application connection (web, scheduler, CLI `seed`, `reset_transactional_data.py`, desktop wrapper — all go through `create_app()`) is covered, with the direct-`sqlite3` tools listed and their required behaviour stated; recovery gate unsatisfied; migration mechanism decision required for Stage G only.

## 12. Audit atomicity — confirmed gap

| Pattern | Where | Sequence | Can audit failure be ignored? | Rollback includes audit? | Partial state possible? |
|---|---|---|---|---|---|
| A-NF | all `routes.py` writers using `_write_audit` (W-02/03/04/05/12/17/18/19/20) | mutation → `_write_audit` (flush; exceptions caught and logged) → `db.session.commit()` | **Yes** — the helper is documented "never raises"; the commit proceeds | Same session, so a rollback would include it — but nothing triggers a rollback on audit failure | **Yes**: committed financial row, no audit row |
| A-POST | W-15 POS | `ExtraCharge` → **commit** → `AuditLog` → commit, `except: pass` | **Yes** | **No** — the charge is already committed | **Yes**, by construction |
| A0 | W-01, W-06, W-07, W-10, W-11, W-16, W-24 | no AuditLog in the writing function (some callers may audit at a higher level — NV) | n/a | n/a | Audit absent |
| A-DED | W-13, W-14 | dedicated log row added to the same session; caller commits | Only if the dedicated row fails silently — NV | Yes | Low |
| A-STRICT | F-01 and the two transfers | `_audited` proves the row reached the session; else rollback + 500 | **No** | Yes | No |

**Phase 1 requirement R-AUD-1:** every financial writer modified by Phase 1 adopts the A-STRICT pattern for its financial audit row (prove-in-session, rollback on failure), without changing the shared helper's behaviour for other callers (Phase 2a precedent). **R-AUD-2:** W-15 is re-ordered so the charge and its audit commit together. **R-AUD-3:** writers currently A0 gain an audit row of the same shape as their siblings (`payment_create` / `charge_create` with before/after). Whether strictness is applied is a control change; the Founder confirmed the same rule for Phase 2a (default #3) — confirmation requested for Phase 1 (Q-5).

## 13. Business date per writer

Controlled business date: W-01–07, W-12–16, W-18, W-19, W-21, W-24. Wall clock: W-08, W-09, W-22, W-23 (`today`), W-10 (`_date.today()`), W-11 (`_d.today()`), W-20 (`now.date()`). Model default: W-17. Midnight behaviour: wall-clock sites can date a row into a business date that is already closed if the business date lags the calendar (it lags by 29 days today) — INV-B01 would then report it. Night-audit rerun: W-16 dates to `target_date` correctly. **Implementation changes required later (Phase 3 unless Q-3 says otherwise):** pass `get_business_date()` at the seven wall-clock sites and at W-17; consider making the model defaults raise rather than default.

## 14. Authorization per writer

Recorded in the inventory. Phase 1 adds no endpoint, changes no role, and inherits Gate B from Phase 2a (29-case matrix re-run every slice). Maker-checker does not apply to any Phase 1 writer (no new approval paths; void/refund N2 control untouched). Automated writers W-21/W-14 depend on the AR-013 ADR (B-1) for provenance — recorded as a dependency that does not block attribution.

## 15. Recovery gate

**Unsatisfied.** PD-006 cannot be met: no restore capability, no rehearsal, no restore record. Consequence, per the directive: **no production data migration is schedulable.** For Phase 1 specifically this bites only Stage E (empty on the live DB) and Stage G (Phase 5). Phase 1 code slices write no production row and are reverted by `git revert`; but deploying attribution code to the live system without a rehearsed restore means the first real operating day after deployment has **no demonstrated data rollback** — which is why the plan places the Recovery Foundation first and asks the Founder to accept it as a pre-Phase-1 deviation from Phase 9 (Q-6).

## 16–21. Backup/restore planning, migration mechanism, slices, verification, zero-NULL criteria, rollback

In the companion artifacts. Zero-NULL criteria (§20 of the directive):

| Population | Criterion |
|---|---|
| Future writes | Every Phase-1-compliant originating writer produces a non-null `folio_id` equal to Folio A of its reservation; proven per writer on copies (Layer 2) and by INV-A02/A03 HOLDS on the new-activity copy. |
| Existing legitimate data | On the live database this population is **empty** (F1). For any other database (e.g. a restored backup), the classification method in `MIGRATION_AND_DATA_PLAN.md` §3 must be applied before any migration; rows classified legitimate need attribution under an authorized PD-004 migration, or an explicit disposition. |
| Historical D11 data | Eight rows remain NULL and byte-identical; every evidence pack proves it by id set (T29 shape). |
| Final schema | `folio_id NOT NULL` enforced only after Stages A–F and after a Founder decision on the eight rows (B-3); not in Phase 1. |

## 22. Blockers

| # | Blocker | Evidence-supported? | Blocks |
|---|---|---|---|
| B1 | Restore capability absent → PD-006 unsatisfiable → recovery gate unsatisfied | Yes (F8) | Any production data mutation; demonstrated data rollback for a Phase 1 deployment |
| B2 | Backup integrity evidence — application backup path has none; `tools/backup_db.py` has it but is manual and unencrypted | Yes | Same as B1 |
| B3 | Migration mechanism (B-4) undecided; none can do a SQLite table rebuild today | Yes (F6) | Stage G only (Phase 5) — **not Phase 1 code** |
| B4 | D11 / legitimate NULL-folio classification | **Resolved for the live DB** (F1); method defined for other DBs | Nothing in Phase 1 |
| B5 | `folio_id NOT NULL` mechanics | Yes (B-3) | Stage G only |
| B6 | Scheduler financial writers lack AR-013 controls | Yes | Not attribution; dependency recorded |
| B7 | Maker-checker | Not applicable to Phase 1 writers | — |
| B8 | Audit atomicity gap | Yes (F3) | Must be closed by Phase 1 for touched writers (R-AUD-1/2/3); Founder confirmation Q-5 |
| B9 | Business-date defects | Yes (F4) | Not attribution; Q-3 decides scope |
| B10 | Golden master stale | Yes (F7) | Gate G effectiveness; Q-4 |
| B11 | Founder decisions Q-1…Q-6 | Yes | Execution authorization |
| B12 | No durable Phase 1 implementation directive in the repository (the 2026-09-05 directive is an artifact) | Yes | Execution authorization — `PHASE1_EXECUTION_PLAN.md` is the candidate |

## 27. Final readiness gate

The slices are specified, dependencies are understood, migration/data treatment is defined (and, for the live database, conclusive), verification and rollback are defined, and no adopted-architecture conflict exists. But the recovery gate is **unsatisfied**, the audit-atomicity control change and three scope questions need Founder confirmation, and no implementation directive exists in the repository.

### `PHASE 1 NOT READY FOR EXECUTION AUTHORIZATION`

**What converts it to READY:** Founder answers Q-1…Q-6 (`FOUNDER_DECISION_GATE.md`); a bounded implementation directive for Slice 1 (Recovery Foundation) is issued and its rehearsal record exists; the Phase 1 execution plan is adopted as the directive. Nothing else in this report requires new architecture.
