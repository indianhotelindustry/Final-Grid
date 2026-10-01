# B-4 — Decision package: schema migration mechanism and boot-time execution

| | |
|---|---|
| Recorded | 2026-10-02, overnight session, by Claude (Claude Code agent) |
| Code | `C:/wtov` @ `c9eeff0` (= `origin/main`); live checkout `c703150`, same `app/` |
| Basis | `B4_STARTUP_MIGRATION_ANALYSIS.md` (this folder). Static only; the application was not started |
| Nature | **Decision package only.** Nothing here is a Founder decision, and nothing recommends changing behaviour now. No code, schema, setting, launcher or database was changed. Options are listed with consequences; the choice belongs to the Founder. |
| Backlog | B-4 (`verification/adr/BACKLOG.md:15`): Architecture decision needed; gates ADR-006 adoption; Phase 5 |

---

## 1. Governance already in force (FACT)

| Ref | What it says | Location |
|---|---|---|
| FD-005 | PD-004 authorization; PD-005 sequence (backup → backup verification → recovery plan/rehearsal → execute → post-verification → invariants → evidence); PD-006 restore verification. Mandatory gates | `verification/FOUNDER_DECISIONS.md:468-498` |
| FD-007 | No production schema/data migration merely because engineering is complete. Requires an approved scope, PD-004, PD-005, verified PD-006, pre- and post-mutation snapshots and invariants, controlled execution, evidence and a rollback path. State note: the registry runs **unattended at every `create_app()`** and on updater restart; the mechanism is **not decided** | `:520-550` |
| FD-009 | No unattended financially material production mutation without operator-equivalent controls | `:575-591` |
| FD-019 | Implementation completion is not production authorization | `:839-852` |
| ADR011-SA note | The delivery mechanism, and whether the unattended boot-time registry may be used, were not addressed. "Because `instance/pms.db` lives in the application working tree, a boot-time migration committed to `main` would be applied to production at the next application start." | `:1289` |
| ADR-006 | Execute step: "never at boot time unattended". Unattended boot-time migration is the current behaviour and "must change under a separate directive". Unresolved: single schema authority; whether boot-time migration is acceptable at all; scope of "production migration" (treated as **any** schema **or data** mutation) | `verification/adr/ADR-006-production-mutation-controls.md:39,51-57,70` |
| Master Plan Phase 5 | 5.1 single schema authority; 5.2 column-level drift detection; 5.3 version stamping; 5.4 correct the boot log; 5.5 installer gate; 5.6 reproducible schema. Entry: MP-D4 and MP-D1 settled; Phase 4 complete | `verification/MASTER_PLAN.md:160-166` |
| MP-D4 | "SQLite as system of record" — OPEN | `verification/MASTER_PLAN.md:70,248`; `BACKLOG.md:26` |

Precedent (FACT): `10.0.0` reached production only because the Founder authorized it explicitly and the operator controlled both the merge and the first start (fast-forward, then `first_start.py`), wrapped in PD-005/PD-006 (`verification/evidence/20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:10,22-36`). The mechanism stayed unattended. The control was procedural.

---

## 2. Option set used by the decisions below

| Opt | Description | Consequences |
|---|---|---|
| **O-A Keep** | Keep the boot-time registry and boot-time seeding as they are; control by procedure (who may merge, who may start) | No engineering cost. Every merge to `main` that adds a registry entry, column-fixer entry or seed **is** a production mutation at the next start (ADR011-SA note). FD-007 / ADR-006 "never at boot time unattended" stay unmet in mechanism. A refused boot loops under `start.bat:127-134`. G11's upgrade rehearsal must cover "boot = migrate". |
| **O-B Gate** | Boot runs migrations only when an explicit operator flag is set (environment or one-shot file). Without the flag, pending work makes boot **refuse** (fail-closed) or **warn and continue** (sub-choice) | A small change in `app/__init__.py`. A forgotten flag is the new failure mode. Every migration still runs inside the web-server process; the backup is still external to it. Refuse-on-pending interacts with the `start.bat` restart loop (a pending migration loops). |
| **O-C Command** | Separate migration command (CLI or `tools/` script) that: takes and verifies a backup (`tools/backup_db.py`), checks the expected pre-state (schema fingerprint and `schema_migrations` set; not `MAX(version)`, see F-1), applies, records, verifies post-state, writes evidence. Boot becomes **read-only**: it checks schema version or fingerprint and refuses on mismatch | Matches PD-005 step by step and keeps boot free of writes. Needs design (where state is recorded, how a refused boot is surfaced to a non-technical operator). Update paths (`update.bat`, in-app updater, `installer/*`) must call the command instead of booting. Largest change; overlaps Master Plan 5.1–5.6. |
| **O-D Relocate DB** | Move the production database out of the application working tree (e.g. a data directory set by an absolute `DATABASE_URL`), so a checkout or merge cannot point a new start at production by default | Independent of O-A/B/C; combinable. Changes `instance/` assumptions in `tools/backup_db.py`, `tools/restore_db.py`, `migrations/alembic.ini:26`, the `update.bat` protected list (`update.bat:111-114`), `start.bat:52-56` and the verification harness. Is itself a production configuration change (PD-004 scope). Does not by itself stop boot writes. |
| **O-E Alembic** | Make Alembic the single authority (retire the registry, stamp production) | Base revision drops `schema_migrations` (`migrations/versions/e2a21139b806…py:21`); production has no `alembic_version`. SQLite batch-mode rebuilds and the 38 + 1 columns with no delivery path (analysis F-10) need handling. `installer/_alembic_upgrade.py:47-49` boots the app first, so O-E needs O-B or O-C to be meaningful. |

---

## 3. Decision entries

### B4-D1

- **DECISION ID:** B4-D1
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** B-4 schema migration mechanism (Master Plan 5.1; ADR-006)
- **QUESTION:** Which version-controlled artefact is the single schema authority for production: the inline registry in `app/__init__.py`, the Alembic tree in `migrations/versions/`, or a new mechanism? What happens to the others: the SQLite column fixer, the SQLite table bootstrap, and the `update.bat` inline `ALTER`?
- **WHY REQUIRED:** Three to five mechanisms change schema today (analysis §2: M-1…M-7, X-1…X-3). `schema_migrations` does not faithfully state applied DDL (F-3). The same schema is reached by different paths on SQLite and PostgreSQL, and 39 model columns have no PostgreSQL / Alembic path (F-10). AR-005 settled the principle that repository files are authoritative, not the artefact (`ADR-006…md:69-70`).
- **OPTIONS:** (a) inline registry authoritative; retire Alembic and the fixer by folding them into registry entries. (b) Alembic authoritative (O-E); retire the registry after stamping. (c) A new explicit migration mechanism (with O-C). (d) Defer to Phase 5 as planned and record that the status quo continues until then.
- **EVIDENCE:** `B4_STARTUP_MIGRATION_ANALYSIS.md` §2, §6, F-3, F-10, F-11; `ADR-006…md:19,55,70`; `FOUNDER_DECISIONS.md:543-548`; `BACKLOG.md:15`.
- **DEPENDENCIES:** MP-D4 (persistence engine; `BACKLOG.md:26`). MP-D1 (Phase 5 entry; `MASTER_PLAN.md:161`). B4-D2.
- **WHAT IS BLOCKED:** ADR-006 adoption; Master Plan 5.1–5.6; any **schema** change that needs a delivery path: B-3 `folio_id NOT NULL`, ADR-005 FK enforcement prerequisites, B-6 retention schema, B-11 backup manifest/checksum column, remaining ADR-011 fields; PostgreSQL as a target (F-10).
- **WHAT CAN CONTINUE:** read-only analysis; verification on copies; K-7 work that changes **code only** (no schema); G3/G6 code work; decision packages.
- **EXACT ACTION AFTER DECISION:** record the ruling verbatim in `FOUNDER_DECISIONS.md` (FD-018); update `BACKLOG.md` B-4 status; draft the ADR-006 amendment for adoption review; scope Phase 5 unit 5.1 as a bounded directive. No code until that directive exists.

### B4-D2

- **DECISION ID:** B4-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** B-4 — end of unattended boot-time execution
- **QUESTION:** May production schema/data migrations continue to execute automatically when the application starts? If not, which model replaces it: **O-B Gate** (sub-choice: refuse vs warn when pending) or **O-C Command** with a read-only boot?
- **WHY REQUIRED:** ADR-006 states boot-time unattended execution must change under a separate directive (`ADR-006…md:39`) and records "whether boot-time unattended migration is acceptable at all" as undecided (`:56`). The ADR011-SA note records the consequence: merge equals mutation at next start (`FOUNDER_DECISIONS.md:1289`). Starting the app writes with no backup and no confirmation (F-2). A refused boot loops (`start.bat:127-134`).
- **OPTIONS:** O-A Keep (procedural control only); O-B Gate (refuse); O-B Gate (warn-and-continue); O-C Command plus read-only boot; O-C plus O-D.
- **EVIDENCE:** analysis §0, §1, §5, §8, §10; F-2, F-5, F-6, F-7; ADR-011 precedent (`ADR011_PRODUCTION_APPLICATION_REPORT.md:22-36`).
- **DEPENDENCIES:** B4-D1 (which artefact the command or gate runs); B4-D4 (backup coupling); B-5 / PD-006 "verified state" definition (`BACKLOG.md:16`) for O-C's pre/post checks.
- **WHAT IS BLOCKED:** G11 upgrade-path rehearsal design ("pre-update backup → signed package → boot → checks", `verification/evidence/20260910_phase2_entry/CERTIFICATION_GATES.md:41`). The boot step means different things under O-A and O-C, so the written procedure cannot be finalised. Any new registry entry merged to `main` is blocked in practice: it would execute at the next start without authorization (FD-007/FD-019).
- **WHAT CAN CONTINUE:** the G11 procedure sections that do not depend on the boot step (fresh install, launchers, day-one business date, rollback). Code work that adds **no** registry, fixer or seed entry. Copy-based verification.
- **EXACT ACTION AFTER DECISION:** record the ruling. If O-B or O-C: issue a bounded implementation directive naming the files (`app/__init__.py:452-528,739-1842`, `update.bat`, `app/updater.py:585-603`, `installer/_run_legacy_migrations.py`, `installer/_alembic_upgrade.py`), the tests (boot on a pending-migration copy refuses or migrates as decided; steady-state boot digest-identical; restart-loop behaviour), and PD-005 evidence for its first production use. If O-A: record it as an accepted risk with the procedural controls named (who may merge `main`, who may start the app, mandatory pre-start backup).

### B4-D3

- **DECISION ID:** B4-D3
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** B-4 / ADR-006 scope; FD-009; ADR011-SA
- **QUESTION:** Are the boot-time **data** writes outside the registry within B-4 and PD-004 scope, so that they must stop being automatic? Each needs a disposition: keep, move to the migration command, move to first-run setup only, or remove. The writes are:
  - default settings (including the regenerated `webhook_api_key`);
  - master seeds (`Standard` room type; payment modes, with backfill);
  - first-run seeds (business date from the wall clock; loyalty; POS);
  - `is_app_owner` promotion;
  - `ota_channel` backfill.
- **WHY REQUIRED:** ADR-006 treats "production migration" as any production schema **or data** mutation (`ADR-006…md:57`). These writes run unattended at every start, with no audit row or system actor (analysis §10 W-10…W-19), which conflicts with ADR011-SA's system-actor model (`FOUNDER_DECISIONS.md:1271-1282`). Some re-create rows an operator deliberately renamed or deleted (W-11, W-13, W-14). The business-date seed uses `date.today()` (W-10; FD-013 / K-7 family).
- **OPTIONS:** (a) out of B-4 scope, keep as is; (b) in scope, freeze: no new boot-time seeds without a migration entry, existing ones unchanged; (c) in scope, move all to an explicit first-run or setup step; existing databases untouched at boot; (d) per-item disposition.
- **EVIDENCE:** analysis §10 (W-10…W-19), F-12; `app/__init__.py:1845-2044`.
- **DEPENDENCIES:** B4-D2; FD-013 / Phase 3 unit 3.1 for W-10; B-1 / FD-009 materiality for W-19.
- **WHAT IS BLOCKED:** a complete statement of "what a start may write" for G11 and G12; ADR-011 "remaining provenance envelope" for unattended writes (G5).
- **WHAT CAN CONTINUE:** everything else; the current production state triggers none of these writes (steady-state no-op, `ADR011_PRODUCTION_APPLICATION_REPORT.md:54,58`).
- **EXACT ACTION AFTER DECISION:** record the ruling. If (b)–(d): add the per-item disposition to the B4-D2 implementation directive. Add a G11 check "steady-state boot is digest-identical" (already demonstrated once, `ADR011_PRODUCTION_APPLICATION_REPORT.md:58`).

### B4-D4

- **DECISION ID:** B4-D4
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** B-4 × PD-005 / PD-006 × B-11 (backup mechanics)
- **QUESTION:** Must every production migration be mechanically coupled to a verified pre-migration backup, so that it refuses to run without one? Which backup path is authoritative: the application's `run_backup` (`shutil.copy2`, no checksum) or `tools/backup_db.py` (backup API, verified, used for `10.0.0`)? Are pre-migration and pre-update backups exempt from the 30-day purge?
- **WHY REQUIRED:** No automatic boot path takes a backup (analysis §8). `update.bat` boots the app **before** its pre-update backup and continues when the backup fails (`update.bat:80-99`; F-7). Its multi-line `python -c` blocks may not execute at all (`installer/_alembic_upgrade.py:3-9`; NOT VERIFIED). `_purge_old_backups` deletes pre-update backups after 30 days (`app/backup_manager.py:330-344`); the retention exemption is unresolved (`ADR-007…md:35`).
- **OPTIONS:** (a) procedure only (operator runs `tools/backup_db.py` first, as for `10.0.0`); (b) the migration command (O-C) runs and verifies the backup itself and refuses otherwise; (c) (b) plus a retention exemption for `pre-*` backups; (d) defer to B-11 / Phase 9.
- **EVIDENCE:** analysis §8, F-7; FD-005 state note (`FOUNDER_DECISIONS.md:489-494`); `ADR011_PRODUCTION_APPLICATION_REPORT.md:23-24,64-65`.
- **DEPENDENCIES:** B4-D2; B-5 (verified-state definition); B-11 (manifest storage, key custody).
- **WHAT IS BLOCKED:** G8 recovery on the **operating** backup path; G11 upgrade rehearsal (pre-update backup step); the `update.bat` launcher rehearsal (PB-7 / FD-017).
- **WHAT CAN CONTINUE:** ad-hoc verified backups with `tools/backup_db.py` under existing authorizations; restore rehearsals on copies.
- **EXACT ACTION AFTER DECISION:** record the ruling; fold the backup coupling into the B4-D2 directive or a B-11 directive; add a G11 check "pre-update backup exists, verifies, and precedes the first boot of new code".

### B4-D5

- **DECISION ID:** B4-D5
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** B-4 × deployment model (MP-D3) × production boundary
- **QUESTION:** Should the production database stay at `instance/pms.db` inside the application working tree (the git checkout), or move to a location outside it (O-D)?
- **WHY REQUIRED:** The ADR011-SA note identifies the working-tree location as the reason a merge arms a production migration (`FOUNDER_DECISIONS.md:1289`). The default URL is derived from the package path (`app/__init__.py:114-121`). `alembic.ini` targets it (`migrations/alembic.ini:26`). In-place verification runs have already touched a sibling live file, `alert_memory.json` (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:77`). `.env.example:23` documents a relative URL that depends on the working directory (F-15).
- **OPTIONS:** (a) keep; (b) move to a dedicated data directory with an absolute `DATABASE_URL`; (c) keep the location but have the live folder run from a release copy rather than a git checkout (MP-D3 territory).
- **EVIDENCE:** as above; `update.bat:111-114` (protected paths); `tools/restore_db.py` (refuses in-place restore, `ADR011_PRODUCTION_APPLICATION_REPORT.md:85`).
- **DEPENDENCIES:** MP-D3 (deployment model); B4-D2 (with O-C the location matters less for "merge = mutation", but still matters for in-place tooling).
- **WHAT IS BLOCKED:** nothing immediately; it shapes the G11 procedure and the launcher rehearsal.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the ruling. If (b) or (c): PD-004 authorization for the move itself; PD-005 sequence (backup, move, digest equality, boot check); update tools and launchers under a bounded directive.

### B4-D6

- **DECISION ID:** B4-D6
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** B-1 / FD-009 (scheduler) × B-4 (what a start does)
- **QUESTION:** Should starting the application continue to start the scheduler unconditionally? In particular, should `notification_queue_flush` keep sending WhatsApp and e-mail to guests on a 5-minute interval, gated only by environment credentials, or be gated by an explicit setting and suppressed for verification and maintenance starts? The scheduler also runs the daily backup, log pruning and predictive-maintenance writers.
- **WHY REQUIRED:** Every start, including the boots that `update.bat`, the installer helpers and verification runs perform, starts the scheduler (`app/services.py:579-582`). Within 5 minutes it can send messages to guests from `notification_queue` (`app/notifications.py:209-258`; F-13). Only `night_audit_job` is gated by a setting (FD-P2-05). The 03:00–05:00 jobs delete files and rows (`app/backup_manager.py:330-344`; `app/__init__.py:547-571`) and write maintenance rows (`:574-600`). B-1 already lists scheduler controls (`BACKLOG.md:12`), but message-sending is not named there.
- **OPTIONS:** (a) leave to B-1 unchanged; (b) extend B-1's scope explicitly to every boot-registered job, including external messaging; (c) an interim ruling that maintenance and verification starts must run with the scheduler suppressed (requires a mechanism; none exists today).
- **EVIDENCE:** analysis §11; `ADR011_PRODUCTION_APPLICATION_REPORT.md:36` (standing jobs registered at the controlled start, scheduler stopped afterwards).
- **DEPENDENCIES:** B-1 ADR; FD-009; privacy and notification workstream.
- **WHAT IS BLOCKED:** G9 reliability; a safe definition of "controlled start" for G11 rehearsals on copies (copies carry `notification_queue` rows with real guest contacts).
- **WHAT CAN CONTINUE:** verification on copies with notification credentials absent from the environment (the senders return "not configured", `app/notifications.py:57,99`).
- **EXACT ACTION AFTER DECISION:** record the ruling; amend `BACKLOG.md` B-1 scope if (b); include in the B-1 ADR or an interim directive if (c).

### B4-D7

- **DECISION ID:** B4-D7
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** Evidence integrity (FD-018) × B-4 version stamping (Master Plan 5.3)
- **QUESTION:** How should the incorrect `"schema_migrations_latest": "9.0.0"` in `verification/evidence/20260930_135930_adr011_live_human_provenance/RESULT.json:211` (lexicographic `MAX(version)` on a database that holds `10.0.0`) be corrected on record? And is "latest migration" to be defined as something other than `MAX(version)` from now on (e.g. membership of an expected set, or a numeric version sort)?
- **WHY REQUIRED:** The machine-readable field contradicts its own report (`REPORT.md:53`) and the production application report (`ADR011_PRODUCTION_APPLICATION_REPORT.md:42`). Evidence packs are not edited in place (precedent: "Corrections to earlier evidence (not edited in place)", `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:151`). Any O-C pre-state check built on `MAX(version)` would mis-state production from now on.
- **OPTIONS:** (a) a correction note in a new evidence pack (this folder's analysis F-1 may serve) and nothing else; (b) (a) plus a governance-record line; (c) (a) plus a rule for future version checks (no `MAX`/`ORDER BY` on version strings).
- **EVIDENCE:** analysis §3, F-1.
- **DEPENDENCIES:** none.
- **WHAT IS BLOCKED:** nothing technical.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record per the chosen option; if (c), add the rule to `verification/ENGINEERING_GUIDE.md` under a governance-record commit.

---

## 4. Effect of the options on dependent work

| Work item | O-A Keep | O-B Gate | O-C Command (+ read-only boot) | O-D Relocate |
|---|---|---|---|---|
| **G11** deployment rehearsal (`CERTIFICATION_GATES.md:41`; currently FAIL / never performed) | Rehearse "boot = migrate" on a copy; procedure must forbid starting new code before the backup | Rehearse flag set and unset, pending-refuse, restart loop | Rehearse command → verify → read-only boot; refused-boot operator path | Rehearse the move once; paths in launchers/tools |
| **K-7** business-date dating (Phase 3, Q-3; `20260908_golden_master/KNOWN_DEFECTS.md:13`) | If K-7 needs any data correction or schema change, it would run at boot unattended | Same as O-B behaviour | Delivered by the command with PD-005 evidence | Neutral |
| **B-3** `folio_id NOT NULL` (SQLite table rebuild) | Rebuild at boot (as `10.0.0` was): possible only with full procedural control | Same, gated | Natural fit (rebuild with pre/post manifests) | Neutral |
| **ADR-005** FK enforcement | Pragma is per-connection code, not a migration; orphan cleanup would be a data migration | — | Data cleanup via the command | Neutral |
| **B-6 / B-11** retention, backup checksum column | Schema change at boot | Gated | Via the command | Neutral |
| **PostgreSQL** (MP-D4) | 39 columns lack a PG path (F-10); registry PG branch untested | Same | The command must handle both engines or MP-D4 must exclude PG | Neutral |
| **FD-007 compliance in mechanism** | Not met (procedure only) | Partly (explicit act, still in the web process) | Met by design (subject to implementation verification) | Not by itself |

---

## 5. Status

| Item | Status |
|---|---|
| B4-D1 … B4-D7 | OPEN (Founder) |
| Any behaviour change | NOT AUTHORIZED |
| Runtime verification of analysis findings | NOT VERIFIED |
