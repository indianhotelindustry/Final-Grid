# FinalGrid — Phase 2 Founder Decision Resolution Pack (technical analysis)

| | |
|---|---|
| Directive | FG-P2-FOUNDER-DECISION-PACK-20260910-01 (read-only analysis) |
| Prepared | 2026-09-10 |
| Baseline | `a84566ae471786955283d107a9f2ad9e800bfcd4` = `origin/main`; tree clean; production anchor `51dd83b7…` / 733,184 B unchanged |
| Sources | `MASTER_PLAN.md`, `FOUNDER_DECISIONS.md` (FD-001…FD-019, Q-1…Q-6, P1-ACC), `adr/` (twelve ADRs, `BACKLOG.md`), Phase 0 records (`20260908_architecture_resolution_round1`), Phase 1 acceptance and verification packs, `20260910_phase2_entry/`, `masters/phase1_aa6d9e91`, invariant sources `verification/invariants/rules_b.py` / `rules_d.py`, and `app/` code where cited |
| Status | **PHASE 2 FOUNDER DECISION PACK PASS — DECISIONS READY FOR FOUNDER GATE** |

Nothing here alters an existing Founder decision. Every recommendation is a proposal for a *future* ruling and, where it touches an invariant, is a constitutional amendment that only a Founder ruling can make (Master Plan §07, SC-5). No implementation occurs.

---

## FD-P2-01 — MP-D9 operator profile (and the separate D9 recovery gate)

**Two different "D9"s.** *MP-D9* is Master Plan decision 9, the **intended operator profile**: who runs the property and with which roles. *D9* is Wave 0 deliverable 9, **Backup Restore Verification** (FD-006). The directive title joins them; they are analysed separately and the recovery gate is answered in FD-P2-04.

**What MP-D9 currently requires.** The role model is fixed by the database (`users.role IN Admin, Manager, FrontDesk, Housekeeping, Accountant`) but no ruling says which of these the property will actually staff, whether one person can hold Admin and approve their own requests, or which reports each role may read. Three architecture items are parked on it: ADR-009 report classification and default role sets, ADR-010's self-approval policy ("a one-person hotel has no second approver"), and ADR-011's accountability envelope. The Master Plan marks it OPEN with an **interim Admin/Manager default** applied in Phase 2a "deliberately matching `payment_void_service.can_approve_void()`".

**Why Phase 2b depends on it.** 2b is the maker-checker phase. Maker ≠ checker cannot be enforced without knowing whether a second person exists; the operation matrix (B-2) cannot set self-approval rules without it.

**What has already been built.** Phase 2a: fail-closed role map on the four folio endpoints (Admin/Manager), audit on every mutation, 29/29 negative matrix, frozen (FD-016). Void/refund maker-checker: request FrontDesk/Manager/Admin → approve Admin/Manager, `direct_void` for privileged roles (N2, preserved). Shift close: auto-approve within a variance threshold (default ₹50) else Manager approval. Cancellation forfeit above threshold: Admin approval with written reason. Individual credit above threshold: Admin. FD-014 accountability principle and FD-015 read scope ruled. Production today: **one user, `admin`, role Admin.**

**What remains unverified.** ≥26 of 49 report routes and several writer routes (`new_reservation`, `bulk_booking`, `checkout`, `walkin_search_express`) are reachable by any authenticated role (R6, Phase 4). CF-5 unauthorized-role cases for writers were not run. None of this has ever been exercised with a non-Admin account on production because none exists.

**Is an interim extension safe?** For the property as it stands — one Admin account — yes, provided the extension states its own boundary. The risk appears only when a FrontDesk/Accountant/Housekeeping account is created before Phase 4 unit 4.2 closes the report and writer routes; at that moment Housekeeping could read financial reports and post checkouts. An extension must therefore be conditional on the account set, not on time.

**Production impact.** With one Admin: nil. With staffed roles: report confidentiality and writer authorization are open (G4 becomes blocking).

**Options.**
- A. *Enforce MP-D9 immediately* — rule the full profile now. Cleanest, but it forces ADR-009/010/011 decisions before Phase 3, which does not need them.
- B. *Narrow interim extension* — extend the Phase 2a Admin/Manager default to Phase 2b and Phase 3 with four conditions: (1) roles in production use are Admin, optionally Manager, until MP-D9 is ruled; (2) Admin may act as both maker and checker **only when no other approver-role account exists**, with a mandatory reason and an audit row flagged `self_approved`; (3) creating any FrontDesk, Accountant or Housekeeping account before Phase 4 unit 4.2 is an event that re-opens this decision (recorded in the day-one procedure); (4) report routes and writer routes stay as they are until Phase 4. This is what Phase 2a already did, made explicit.
- C. *Rule MP-D9 minimally as "single-operator property"* — a business fact the Founder may simply know; it would collapse B's conditions into a ruling.

**Recommendation: B**, or C if the Founder can state the staffing fact now. Not A.

---

## FD-P2-02 — Audit-log pruning exemption

**What is pruned.** `_prune_old_logs` (`app/__init__.py:547-566`), cron daily 04:00, no switch, deletes rows older than 90 days from **three** tables: `audit_logs` (`AuditLog.timestamp`), `webhook_logs`, `notification_logs`. The first two are operational logs; `audit_logs` is the financial provenance record — every Phase 1 strict-coupling row, every Phase 2a folio mutation, every night-audit override reason, and the evidence by which the eight D11 rows were classified as commissioning activity.

**Why it conflicts.** FD-008 ("audit history must not be automatically deleted until a formally designed archival/retention mechanism has been approved and implemented"), AR-007 ("must be addressed before production certification"), Constitution P7/P12/P14 (append-only closed periods, historical immutability, provenance). Q-5 makes audit rows *part of* the financial mutation; deleting them later undoes at day 91 what strict coupling guaranteed at day 1. No invariant detects the loss.

**Timing.** Oldest row 2026-08-09 → first deletion on or about **2026-11-07** on any running instance.

**Storage reality.** Measured on the production copy: 23 rows averaging ≈153 bytes of payload. A busy small property writing 500 audit rows a day adds ≈75 KB/day, ≈27 MB/year — against a 733 KB database and SQLite's practical range in the tens of gigabytes. Storage is not a reason to prune.

**Safest production treatment.** Stop deleting `audit_logs`; keep pruning `webhook_logs` and `notification_logs` (no provenance value). Defer archival, retention classes and any archive-then-delete design to ADR-012 proper. Add later, under Phase 6, a detection invariant that the minimum `audit_logs.timestamp` never advances (ADR-012 item 4) so the control is capable of failing.

**Recommendation.** Approve a **bounded exemption directive now** (the ADR-012 "immediate" item, same shape as FD-017): one function edited, one test proving rows older than 90 days survive a prune run on a copy, scheduler job list otherwise unchanged. Pruning of `audit_logs` stays disabled until the archival design is approved — not "pending", but explicitly *off*.

---

## FD-P2-03 — D11 certification verdict

**Facts.** Eight rows: payments 1–6 (800 / 400 / 1500 / 1000 / 500 / 100) and extra_charges 1–2 (380.95 / 95.24), ₹4,776.19, `folio_id NULL`, reservations 1–4, invoices INV-2026-000029…32. D11-F2 classifies them as commissioning/test activity; FD-010 Option A preserves them untouched and authorizes nothing further; AR-001 keeps INV-A02 universal; Q-2 refuses any correction of them in code. Consequence: production `inv-run` reads **OVERALL FAIL** (INV-A02 8/8 certification-blocking; INV-A03 ₹476.19 release-blocking) *by design*, and every production-derived copy inherits it; Q14 diverges by exactly ₹476.19.

**The certification problem.** G12 cannot be recorded on a verdict that says FAIL, and neither the invariant nor the data may be changed to make it say PASS. Four treatments were evaluated:

| Treatment | Effect | Assessment |
|---|---|---|
| Attribute the rows to folios 1–4 | verdict PASS; history rewritten | forbidden by FD-010 and Q-2; rejected |
| Reverse or delete them | verdict PASS; invoices/GST history altered | forbidden by FD-010; rejected |
| Change INV-A02/A03 (population declaration inside the invariant) | verdict PASS; the invariant no longer universal | contradicts AR-001; rejected |
| **Declared-exception register at the certification layer** | invariant unchanged, data unchanged; the certification step compares the *set of violating objects* with a Founder-declared exception set; equal → recorded as **PASS WITH DECLARED HISTORICAL EXCEPTION**; any extra object → FAIL | consistent with FD-010, AR-001, Q-2; the control remains capable of failing (P9) |

**How D11 should appear in certification.** A dated register entry listing the eight rows by table, id, amount, reservation and invoice, citing D11-F2 / FD-010 / AR-001, and stating: preserved exactly; INV-A02 and INV-A03 continue to report them; no folio, reversal, deletion, invoice or GST change; correction refused in code; any additional unattributed row is a certification failure. The certification record then reads: *"Invariant verdict FAIL is composed solely of the declared historical exception (8 objects, ₹4,776.19); no undeclared violation; certified PASS-WITH-DECLARED-EXCEPTION."* Until D7 (certification engine) exists the set comparison is performed and evidenced manually in the certification pack.

**Recommendation.** Adopt the declared-exception treatment as the certification rule. It is the only option that keeps every existing ruling intact. Disposition of the rows themselves stays a later decision (B-3, Phase 5), exactly as FD-010 reserved.

---

## FD-P2-04 — PD-006 "verified state"

**Backup exists ≠ restored and verified.** Today: the application writes a `BackupLog` row with filename, size, type, status — no hash, no integrity check, no manifest; the file is a `shutil.copy2` of a live SQLite database, encrypted with a key derived from `PII_ENCRYPTION_KEY`/`SECRET_KEY` in `.env`, purged after 30 days. A file on disk proves nothing about recoverability. `tools/restore_db.py` (Recovery Foundation) already proves the other side for tool-made artifacts with 16 checks (RR-20260908-01 PASS), and shows that a byte-identical whole-file hash is *not* the right criterion (SQLite's backup API rewrites header bookkeeping bytes 26–27, 43, 94–95).

**Proposed PD-006 definition — a restoration state is VERIFIED when all of the following are recorded in a single manifest for a named run id:**

| # | Condition | Objective check | Exists today |
|---|---|---|---|
| 1 | Backup identity | SHA-256 of the artifact (and of the decrypted plaintext for `.enc`) equals the value recorded when the backup was made and in `<artifact>.manifest.json` | tool path yes; app path **no manifest** |
| 2 | Restore completion | restore tool exits 0 into a fresh, isolated destination that is never `instance/` | yes (structural refusal) |
| 3 | SQLite integrity | `PRAGMA integrity_check` = `ok` on source and on restored file | yes |
| 4 | Foreign keys | `PRAGMA foreign_key_check` on the restored file = 0 rows (or identical to the source's) | yes |
| 5 | Schema identity | `sqlite_master` SQL identical to the source, and its fingerprint equals the release tag's expected fingerprint | yes (source equality); tag fingerprint to be recorded per release |
| 6 | Data identity | per-table row counts equal source and backup manifest; per-table content digests equal; body bytes identical beyond the 100-byte header; financial tables (`payments`, `extra_charges`, `folios`, `reservations`, `night_audit_logs`, `audit_logs`, invoices via `reservations.invoice_number`) named explicitly | yes (16 checks) |
| 7 | Whole-file hash | recorded; **informational**, may differ in header bookkeeping only | yes |
| 8 | Functional equivalence | `inv-run` on a `make_copy()` of the restored file gives verdicts identical, object for object, to the pre-backup pack (declared-exception aware); `gm-verify` against the adopted master = 0 differences with the clock frozen to the same business date | **not yet run** in any rehearsal (deferred as Slice 0/7) |
| 9 | Evidence manifest | machine-readable manifest with run id, source and restored paths, hashes, timestamps (UTC), app version, business date, all check results, the failing check if any; retained under `verification/evidence/` and committed | yes (`restore_manifest.json`) |
| 10 | Operator / accountability | who ran it, on which machine, under which directive; an Admin-signed record | partially (run id only) |
| 11 | Key custody for encrypted backups | the restore of an `.enc` artifact performed **on a different machine** from the one that made it, using only the key held under a documented custody procedure (where it is, who holds it, how it is rotated); the key never written into evidence | **not yet rehearsed** (unit round-trip only) |
| 12 | Retention | the artifact used is exempt from the 30-day purge or copied to the retained recovery store before verification | convention only (B-11) |

**Minimum for any production mutation (PD-005 step 3):** conditions 1–7, 9, 10 against the current anchor. **Minimum for D9 / gate G8 certification:** all twelve, on an application-made encrypted backup, off-box.

**Recommendation.** Adopt the twelve conditions as the PD-006 definition (this confirms and extends ADR-006's proposal: identical integrity + manifest + `inv-run` verdicts, not whole-file hash). It resolves BACKLOG B-5. Nothing is implemented; the app-path manifest and the off-box rehearsal become the recovery-hardening directive.

---

## FD-P2-05 — Night-audit operating mode

**What the night audit does** (`app/services.py :: run_night_audit`): under a row lock on `BusinessDate`, creates one `NightAuditLog` per business date (idempotent — a second run for a date that already has any log is skipped), posts `room_rent` for every in-house reservation (attributed since Phase 1, idempotent per reservation × date, locks the night rate), computes the control sections, and if there are no blockers (pending checkouts, open shifts, zero-rate rooms) completes and **advances the business date**; with blockers it stays Pending/Warning for a person to resolve.

**Two invocation paths.** (a) *Scheduler*: cron at `night_audit_time` (02:00 default), only when `night_audit_enabled = true` — **false on production**. (b) *Manual*: `POST /night-audit/run` by Admin/Manager/Accountant (`reports.py:2823`, `routes.py:4908`), same function, `run_by_user_id` recorded. Reopen: Admin/Manager with mandatory reason (`reports.py:3104`).

**Evaluation.**

| Criterion | Automated (scheduler) | Controlled manual invocation |
|---|---|---|
| Business-date authority | advances the date unattended at 02:00 regardless of whether the day's work is done | advanced by an accountable person when the day is actually closed |
| Financial mutation risk | posts room rent for every in-house stay with no operator present; FD-009 says an unattended process may not make a financially material mutation until it meets the same controls as an operator (authorization, provenance, business date, audit, idempotency, failure handling, verification) — the B-1 ADR does not exist | the operator is the authorization and the provenance; audit rows carry the user |
| Unattended execution risk | blockers at 02:00 leave the audit Pending with nobody to resolve it; a 02:00 run on a night with late arrivals posts before the day's activity is complete | blockers are visible at the moment the operator tries to close |
| Recovery | an interrupted unattended close (Phase 3 unit 3.5) has no witness | interrupted close is seen and reported immediately |
| Idempotency | proven either way (T-R02; W-16) | same |
| Operational simplicity (single property) | "it just runs" — but it does not when blocked, and the blocked state is silent | one daily action, already how the property has operated (one close on 2026-08-09, manual) |
| Consequence of a missed close | none (it ran) | the business date goes stale; K-7 wall-clock writers then date rows to the calendar day (Phase 3 unit 3.6 staleness escalation is the mitigation) |

**Recommendation.** **Controlled manual invocation** for the first production release, formalised: `night_audit_enabled` remains `false`; a written daily-close procedure (who, when, blocker resolution, reopen rule); staleness escalation and interrupted-close recovery delivered by Phase 3 (units 3.5, 3.6); automation reconsidered only after the AR-013 / B-1 scheduler ADR exists. This is also the only mode consistent with FD-009 today.

---

## FD-P2-06 — INV-B06 and INV-D02 semantics

### INV-B06 — advance payments

| | |
|---|---|
| Rule as coded (`rules_b.py:607-700`) | for every payment, `arrival_date ≤ payment_date ≤ departure_date + 30 days`; the 30-day tail is declared ("post-checkout credit recovery is legitimate"); **no leading window** before arrival |
| Business behaviour | `new_reservation` and `bulk_booking_api` post the deposit with `payment_purpose='advance'` dated on the **booking-day business date** (comment: "payment is a LIABILITY (guest deposit) on the booking date"); refunds of that advance at cancellation are dated at cancellation, also before arrival |
| Evidence | set A: payments 7 (300, stay 2026-09-11) and 8 (400, stay 2026-08-13) dated 2026-08-10 → reported "outside the window"; production never showed it because it has no advance |
| Classification | **invariant design gap**, not an implementation defect: the rule's own text anticipates the post-stay case and simply omits the pre-stay one. A deposit before arrival is the normal hotel business flow. |
| Financial / GST | none: an advance is a liability, not revenue; GST attaches at invoicing. Reporting: the *cash* of the booking day is correct as dated; the rule misreports it |
| Recommendation | **Refine the invariant, keep behaviour.** Amendment (Founder ruling): payments with `payment_purpose='advance'` may be dated on or before arrival; refunds linked to a cancelled reservation (`reservations.cancellation_refund_payment_id`) may be dated on or before the cancellation; all other purposes keep the current window. Severity/blocking unchanged. Commission the amended rule with a negative seed (an advance dated 400 days before arrival still fails). Phase 6 implements after the ruling. |

### INV-D02 — cancellation refunds

| | |
|---|---|
| Rule as coded (`rules_d.py:97-195`) | every `payments`/`extra_charges` row with `is_correction=1` or `is_reversal=1` must carry a `corrects_id` that resolves in the same table |
| Business behaviour | `post_cancellation_disposition` posts the refund as `payment_purpose='refund'`, `is_reversal=True`, `corrects_id` **NULL**, `correction_reason='Cancellation refund | …'`; the reservation records the link the other way round in `reservations.cancellation_refund_payment_id`; correction pairs (W-08/09/22/23) set `corrects_id` correctly |
| Evidence | set B: payment 11 (refund 300) flagged; `DS-ACT-VOIDCN` already *declares* INV-D02 VIOLATED for its credit-note refund — the platform has known this shape since D6 |
| Classification | **business-semantics ambiguity**: a cancellation refund reverses the reservation's *advance balance* (possibly several payments), not one payment row, so a single `corrects_id` is not well defined; the traceable link exists but on the reservation. The flag `is_reversal` is used for sign convention (`signed_payment_amount`), not to assert a one-to-one correction. |
| Financial / GST | none: refund of an unearned advance; no invoice; sign handling correct. Reporting: `reports.revenue`, `gst_report` unaffected (no revenue row) |
| Options | (a) change behaviour — refunds stop using `is_reversal` (touches sign logic and reports; not now); (b) populate `corrects_id` with one of the advance payments (false precision when several); **(c) refine the invariant**: a reversal row is compliant if it carries `corrects_id` **or** is referenced by `reservations.cancellation_refund_payment_id` (a resolvable pointer, just on the other side) |
| Recommendation | **Refine the invariant (option c), keep behaviour.** Amendment (Founder ruling); negative seed: a refund row referenced by no reservation still fails. `DS-ACT-VOIDCN`'s declaration is then updated to HOLDS in the same Phase 6 directive. |

Both: **retain unchanged until ruled**; neither is a Phase 1 regression; neither has a GST consequence.

---

## FD-P2-07 — Maker-checker operation matrix (minimum before Phase 2b)

**Existing controls to build on** (all preserved; N2 is a strength): void/refund request→approve; shift-close variance threshold (₹50 default) → Manager approval; forfeit above `get_forfeit_approval_threshold()` → Admin with reason; individual credit above threshold → Admin with reason; night-audit override / reopen → Admin/Manager with reason; audit-lock override for correction pairs → Admin with reason; folio create/transfer → Admin/Manager single-actor with audit (Phase 2a); alert thresholds `DISCOUNT_ALERT_THRESHOLD` 1000, `LEAKAGE_ALERT_THRESHOLD` 3000 (informational).

**Proposed matrix structure (four tiers + emergency control).**

| Tier | Meaning | Operations |
|---|---|---|
| **MC — maker-checker required** (irreversible, crosses a closed period, or above materiality) | request by maker, approval by a distinct checker before execution; both recorded | void / refund of a payment (exists); correction pair on an **audit-locked** date (today: Admin override, single actor); folio **transfer** of a charge or payment above threshold T1; folio **close** (future); billing-responsibility change on a checked-in stay (2b.2); night-audit **reopen** of a completed day; cancellation forfeit above the forfeit threshold (exists as Admin approval); individual credit above the credit threshold (exists as Admin) |
| **RA — role authorization only** (reversible, inside the open day, audited) | one authorized actor; strict audit row | posting payments and charges (all 24 writers), POS, CICO, check-in, checkout, new reservation, folio create, folio transfer below T1, discounts below threshold, shift open/close within variance, night-audit run |
| **INFO — informational** | no gate; alert or report | discount alerts, leakage alerts, repeat-discount counts, staleness warnings |
| **EMERGENCY / admin override** | Admin only; mandatory reason; audit row flagged `override`; listed on the next night audit's control section for review | audit-lock override, forced void (`direct_void`), night-audit override when blocked, self-approval where no checker exists (FD-P2-01 condition 2) |

**Audit requirements for every MC transition:** request row (maker, role, target, before/after, reason, business date, IP) → approval/rejection row (checker ≠ maker unless emergency, role, reason) → execution row; all three coupled to the mutation (strict). Reason validation: non-empty and not a placeholder (the record already contains "cvnvhm", "dfhd").

**Genuine Founder choices** (everything else follows from ADR-010 and the existing code):
1. **Materiality threshold T1** for folio transfers (a rupee figure; the existing shift ₹50 / discount ₹1,000 / leakage ₹3,000 settings are reference points).
2. **Self-approval policy** for a single-operator property (linked to FD-P2-01).
3. Whether **night-audit reopen** becomes maker-checker or stays Admin/Manager-with-reason (recommendation: maker-checker where a second approver exists, emergency override otherwise).
4. Whether the three approval models (void, shift, folio) converge on one request/approval table — a Phase 2b design question the Founder may leave to the ADR.

**Recommendation.** Adopt the four-tier structure and the assignment above as the B-2 operation matrix by adopting ADR-010 with this content; rule T1 and the self-approval policy; leave convergence to design. This is the minimum that lets Phase 2b start.

---

## Evidence sufficiency

All seven decisions are supported by repository evidence; none is BLOCKED. Two items rest on Founder business facts rather than evidence (staffing profile in FD-P2-01; the rupee threshold in FD-P2-07) — those are the genuine choices, listed as such in `RECOMMENDATIONS.md`.
