# Wave 1 Implementation Blueprint

DSBC Frontline v2.2.18. Written 2026-08-08 at the close of Wave 0.8.

**No production code was written to produce this document, and none may be
written against it until the gate in §9 is passed.**

Every defect below was found and evidenced during Wave 0. Nothing here is
rediscovered. The one piece of new analysis is the **silence census** (§3),
which is a classification of existing findings rather than a search for
new ones, and it is measured:
`evidence/20260808_wave1_silence_census/`.

---

## 1. Verdict on Wave 0

**Wave 0 is engineering-complete for diagnosis and for silent
remediation. It is NOT complete as chartered, and the specific
incompleteness has a specific consequence.**

The charter says Wave 1 may not begin until all ten deliverables are
complete and commissioned. Measured against that:

| | State | Consequence for Wave 1 |
|---|---|---|
| D1–D5 | Complete, commissioned | Diagnosis is sound |
| D6 | 5 datasets commissioned; 2 of 4 VACUOUS invariants activated | Two controls still unexercised |
| D7 Certification Engine | **Does not exist** | **No release can be certified** |
| D8 CI/CD pipeline | **Does not exist** | Every gate is run by hand |
| D9 Backup restore verification | **Blocked at the schema** | **Rollback of a data migration is unproven** |
| D10 Release gate | **Does not exist** | No mechanical go/no-go |

### The consequence, stated precisely

This is not "four deliverables are missing, therefore stop". Three of the
four bite differently:

**D9 is the one that blocks material work.** A change that restates
existing rows can only be rolled back by restoring a backup, and
`backup_logs` stores filename, size and status but **no checksum**, so the
system cannot tell whether a backup is restorable. `FLT-D04` and `FLT-D05`
remain UNCOVERED for exactly this reason. There is one manually verified
snapshot (`../db-backups/`, `integrity_check ok`, row counts matched across
53 tables) and a procedure to make more — `python tools/backup_db.py
--label <name>` — but a procedure proven once by hand is not a control.

**D7 and D10 block the claim, not the work.** Without them a change can be
made and measured but not *certified*; no artefact can say "this release
passed the gate". That matters for audit sign-off, not for engineering
safety.

**D8 blocks nothing** except human error, and it can be built in parallel.

### Therefore

> **Silent remediation (§4, releases W1-R1 and W1-R2) may proceed under the
> existing Wave 0 gate.** Every figure is provably unchanged, so rollback
> is `git revert` plus a re-run of the same measurement.
>
> **Material remediation (W1-R3 onward) may not begin until D9 exists**,
> because its rollback path is a database restore that has never been
> mechanically verified.

That is the honest reading, and it is stricter than "Wave 0 is done" and
looser than "nothing may start".

---

## 2. Readiness of every defect against the six criteria

| # | Defect | Evidence | Canonical impl. identified | Migration | Rollback | Verification | Risk class |
|---|---|---|---|---|---|---|---|
| W1-01 | Financial rows with no folio | ✅ D4 §11.1, ₹40,374.14 | ✅ write-path; no derivation to consolidate | ✅ backfill | ✅ restore | ✅ INV-A02, Q14, FLT-B02 | MATERIAL-attribution |
| W1-02 | Folio view sees no charges | ✅ D4 §11.2 | ✅ consequence of W1-01 | ✅ with W1-01 | ✅ | ✅ INV-A03, FLT-C03 | MATERIAL-attribution |
| W1-03 | Closed day recomputes differently | ✅ D3 §8.1, D4 §11.3, ₹199.99 | ✅ `NightAuditService.folio_control` | ⚠ **see §6** | ✅ restore | ✅ INV-B03, FLT-D03, RC-set | **MATERIAL-historical** |
| W1-04 | Walk-in on OTA receivable | ✅ D4 §11.4, ₹7,977.92 | ✅ write-path | ⚠ **see §6** | ✅ restore | ✅ INV-C01, FLT-A01 | **MATERIAL-historical** |
| W1-05 | OTA posting with no agent | ✅ D4 §11.5 | ✅ write-path | ⚠ with W1-04 | ✅ | ✅ INV-C05 | MATERIAL-historical |
| W1-06 | Room-night sold twice | ✅ D4 §11.6 | ✅ operational data | ⚠ **see §6** | ✅ | ✅ INV-C04, FLT-A08 | MATERIAL-operational |
| W1-07 | ADR/RevPAR/occupancy ignore date | ✅ D1 Q20, D3 §8.2 | ✅ `occupancy_engine` vs `get_adr`/`get_revpar` | ✅ read-path | ✅ revert | ✅ Q20, Q17, Q18, FLT-C04 | MATERIAL-reporting |
| W1-08 | MIS disagrees with flash and dashboard | ✅ D2 §8.3, ₹3,230.28 | ✅ canonical helpers | ✅ read-path | ✅ revert | ✅ Q17, Q18 | MATERIAL-reporting |
| W1-09 | Q18/Q20 diverge on extra charges | ✅ coverage ledger, 5 datasets | ✅ narrowed to extras handling | ✅ read-path | ✅ revert | ✅ Q18, Q20 | MATERIAL-reporting |
| W1-10 | Night-audit taxable base doubled | ✅ D1 Q06, 2.00× exactly | ✅ `tax_lines` component repetition | ✅ read-path | ✅ revert | ✅ Q06, FLT-C09 | MATERIAL-reporting |
| W1-11 | Two balance definitions | ✅ D1 Q12/Q13 | ✅ `calculate_stay_amount` | ✅ read-path | ✅ revert | ✅ Q12, Q13 | MATERIAL-reporting |
| W1-12 | OTA receivable never nets payouts | ✅ D1 Q22 | ✅ `ota_reconciliation` | ✅ read-path | ✅ revert | ✅ Q22, FLT-C07 | MATERIAL-reporting |
| W1-13 | 8 surfaces return HTTP 500 | ✅ D2 §8.1 | ✅ template / route defects | ✅ code only | ✅ revert | ✅ D2 capture | **SILENT** |
| W1-14 | Revenue alert detector dead | ✅ D2 §8.2 | ✅ `alert_engine` | ✅ code only | ✅ revert | ✅ D2 capture | **SILENT** |
| W1-20 | `room_rent` double count | ✅ R-2, ~₹37,217 latent | ✅ exclusion already in `kpi_helpers` | ✅ code only | ✅ revert | ✅ probes, FLT-C08 | **SILENT (dormant)** |
| W1-21 | GST taxes reversed money | ✅ `evidence/20260808_gst_reversal_defect`, ₹180 | ✅ `signed_extra_charge_amount` exists and is not called | ✅ code only | ✅ revert | ✅ DS-ACT-CORRECTION, INV-C02 | **SILENT (dormant)** |
| W1-22 | Refund sets no `corrects_id` | ✅ DS-ACT-VOIDCN | ✅ `post_cancellation_disposition` | ✅ code only | ✅ revert | ✅ INV-D02, DS-ACT-VOIDCN | **SILENT (dormant)** |
| W1-23 | Night audit calls voids refunds | ✅ Q11, ₹1,286 vs ₹236 | ✅ `night_audit_service` | ✅ code only | ✅ revert | ✅ Q11, DS-ACT-VOIDCN | **SILENT (dormant)** |
| W1-24 | Orphan payment mode counted twice | ✅ D3 §8.4, D4 §11.8 | ✅ two disagreeing readers | ✅ code + FK | ✅ revert | ✅ INV-D03, FLT-A06 | **SILENT (dormant)** |
| W1-25 | `tax_lines` cannot express a reversal | ✅ DS-ACT-CORRECTION | ⚠ **no canonical answer exists** | ❌ schema | ✅ revert | ⚠ none yet | **SILENT — NOT READY** |
| W1-26 | No master-account routing | ✅ DS-ACT-GROUP | ⚠ **feature absent, not defective** | ❌ design | n/a | ⚠ none yet | **SILENT — NOT READY** |
| W1-27 | Receivable can go negative | ✅ D1 §7 observation | ⚠ **judgement, not measurement** | ❌ | n/a | ⚠ none yet | **SILENT — NOT READY** |
| W1-28 | Invoice number uniqueness | ✅ FLT-B04 UNCOVERED | ✅ trivial | ✅ | ✅ | ❌ **no invariant exists** | **SILENT — NOT READY** |

### Four items are NOT ready, and this is the honest finding of the review

**W1-25, W1-26, W1-27 and W1-28 fail at least one criterion** and must not
enter a release until they pass:

- **W1-25** — `tax_lines` has no `is_reversal` and no `corrects_id`. There
  is no canonical answer for how a reversed taxed charge unwinds its tax
  line, and inventing one during implementation would be designing under
  deadline. **Needs a design decision first.**
- **W1-26** — master-account routing is an *absent feature*, not a broken
  one. `billing_instructions` is free text and nothing implements it.
  Building it is a Wave 2 feature, not a Wave 1 remediation.
- **W1-27** — "a receivable that can go negative is arguably defective"
  (D1 §7). Arguably is not a specification. **Needs a business rule.**
- **W1-28** — invoice number uniqueness has no invariant, so there is no
  verification strategy. `FLT-B04` is UNCOVERED for exactly this reason.
  **A D4 invariant must be declared and commissioned before the fix**, or
  the fix ships with nothing able to prove it worked. This is D4 work and
  it is the one prerequisite this blueprint asks for.

---

## 3. The silence census — the ordering principle

Measured 2026-08-08 against production, read-only, production
byte-identical. **13 of 21 defects have no live population.**

```
MATERIAL — a fix restates figures that exist today
  W1-01  financial rows with no folio                      40 rows
  W1-02  charges invisible to the folio view                5 rows
  W1-03  closed night audits recomputable differently       1 audit
  W1-04  walk-in payments on OTA receivable heads           5 payments
  W1-05  OTA postings with no agent reference               5 payments
  W1-06  room-nights sold twice                             1 night
  W1-07  extra charges (the Q18/Q20 population)             5 charges
  W1-08  reservations with an approved credit               1

SILENT — the rows a fix would change do not exist
  W1-20  room-rent charges posted into extra_charges        0
  W1-21  correction or reversal rows                        0
  W1-22  refund payments                                    0
  W1-23  voided payments                                    0
  W1-24  credit notes / void requests                       0
  W1-26  payments on a non-existent payment mode            0
  W1-27  group blocks                                       0
  W1-28  companies / corporate bookings                     0
  W1-29  shifts                                             0
  W1-30  reservations overpaid beyond ₹1.00                 0
  W1-31  duplicate invoice numbers                          0
  W1-32  OTA payouts                                        0
```

**Why this is the ordering principle.** A silent fix can be shipped and
*proved* neutral: every D1 quantity, every invariant and every financial
probe reads identically before and after, and any movement is a defect in
the change. That is the strongest form of evidence this project can
produce, and it is available for more than half the backlog.

A material fix cannot be proved that way, because it is *supposed* to move
figures. Its evidence is a declared expected movement, which is weaker and
which is why it belongs later — after the team has shipped several changes
under the framework and knows the gate behaves.

### One item is misclassified by intuition and the census corrects it

**W1-01, the folio backfill, is MATERIAL on attribution and SILENT on every
money total.** No probe, no invariant and no D1 quantity sums money *by
folio* except `Q14`, which exists to measure exactly this. Setting
`folio_id` on 40 rows moves `Q14`, `INV-A02` and `INV-A03` and **nothing
else**.

Its severity reads like a large restatement. It is not one: not a rupee of
revenue, tax, collections or outstanding moves. That is a strong argument
for promoting it far earlier than its ₹40,374.14 headline suggests, and
§5 does so.

---

## 4. The releases

Grouped by risk and blast radius, not by which Wave 0 deliverable found
them.

---

### W1-R1 — Surfaces that do not render

**Objective.** Make the eight HTTP 500 surfaces render and the dead alert
detector run. No financial figure changes; six of the eight are financial
*reports* that nobody can currently open.

| | |
|---|---|
| Canonical implementation | none — these are template and route defects, not derivations |
| Obsolete implementations to retire | none |
| Affected reports | `reports.daily_reconciliation`, `other_income_report`, `refund_report`, `tip_report`, `ar_aging`, `guest_report`, `auth.shifts`, `api/tab/reservations` |
| Affected services | `alert_engine._detect_revenue_alerts` |
| Migration requirements | **none** — no data touched |
| Rollback | `git revert`. No data to restore |
| Expected invariant movement | **none.** All 25 unchanged |
| Expected D1 movement | **none.** 11 AGREED / 1 SINGLE_SOURCE / 8 DIVERGED / 2 VACUOUS, unchanged |
| Datasets required | none new; all 5 must still pass |
| Fault injections required | none new; `fault-run` unchanged |
| Historical replay | D3 unchanged — no engine touched |
| Certification evidence | D2 capture showing 8 surfaces moving 500 → 200, and the alert detector producing output |

**Why first.** Four of the eight share one Jinja incompatibility, which
D2 read as a library upgrade never re-verified against the templates. It is
the lowest-risk work in the backlog and it restores six financial reports
the hotel currently cannot open at all.

---

### W1-R2 — Dormant financial correctness

**Objective.** Fix five defects whose populations do not yet exist, so
that the first time they do, the system is already right. Every one is
provably silent today.

| | |
|---|---|
| Canonical implementation | `services.signed_extra_charge_amount` (already exists and is simply not called by `gst_service.compute_stay_gst`); the `charge_type <> 'room_rent'` exclusion already in `kpi_helpers.get_accrual_extras`; `post_payment_correction`'s `corrects_id` pattern |
| Obsolete implementations to retire | the unsigned extras loop at `gst_service.py:492`; the night audit's conflation of voided payments with refunds; `night_audit_service.py:537` treating a missing payment mode as direct cash |
| Affected reports | `billing.gst_report`, `reports.revenue`, `reports.refund_report`, night audit payment summary, every surface downstream of `calculate_stay_amount` |
| Affected services | `gst_service`, `night_audit_service`, `services.post_cancellation_disposition`, `kpi_helpers` |
| Migration requirements | **none** — code only. No backfill, because there is nothing to backfill |
| Rollback | `git revert`. Neutrality is re-provable by measurement |
| Expected invariant movement | **none on production.** On `DS-ACT-CORRECTION`, `INV-C02` VIOLATED → HOLDS. On `DS-ACT-VOIDCN`, `INV-D02` VIOLATED → HOLDS |
| Expected D1 movement | **none on production.** On the datasets, `Q11` DIVERGED → AGREED |
| Datasets required | `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN` — **both already commissioned.** Their declared expectations must be **re-declared** after the fix: they currently pin the defective behaviour deliberately |
| Fault injections required | `FLT-C08`, `FLT-C09`, `FLT-A06`, `FLT-B09` |
| Historical replay | D3 unchanged — no historical figure moves |
| Certification evidence | before/after D1 + D4 + probe runs on production showing **zero movement**, plus the dataset expectations flipping from VIOLATED to HOLDS |

**The re-declaration is the point, not an inconvenience.** `DS-ACT-CORRECTION`
declares `INV-C02: VIOLATED` and `DS-ACT-VOIDCN` declares `INV-D02:
VIOLATED` because that is what the system does today. When the fix lands,
those datasets **must fail**, and that failure is the proof the fix
worked. A dataset that stayed green through this release would mean
nothing changed.

---

### W1-R3 — Folio routing

**Objective.** Every payment and every extra charge belongs to a folio.

| | |
|---|---|
| Canonical implementation | the write paths that create `payments` and `extra_charges` rows; folio selection belongs in the service layer (P5) |
| Obsolete implementations to retire | none — this is an omission, not a duplicate derivation |
| Affected reports | `main.reservation_folio`, `billing.gst_report`, `reports.daily_reconciliation`, night audit folio control, `reports.revenue` |
| Affected services | payment posting, charge posting, `folio.py`, split-billing |
| Migration requirements | **backfill 40 rows** — 35 payments and 5 charges — to the folio of their reservation. Every affected reservation has exactly one folio today, so the mapping is unambiguous. **That will not be true once split billing is used**, which is an argument for doing it now rather than later |
| Rollback | restore from a verified snapshot taken immediately before (`tools/backup_db.py --label pre-W1R3`). The backfill is also independently reversible: `UPDATE ... SET folio_id = NULL` for the 40 recorded ids |
| Expected invariant movement | `INV-A02` VIOLATED(40) → **HOLDS**; `INV-A03` VIOLATED(5) → **HOLDS**. Registry-wide: VIOLATED 6 → 4, HOLDS 15 → 17, release-blocking 2 → 1 |
| Expected D1 movement | `Q14` DIVERGED → **AGREED**. **No other quantity moves, and no money total changes** — see §3 |
| Datasets required | `DS-ACT-INHOUSE`, `DS-ACT-CORRECTION`, `DS-ACT-VOIDCN`, `DS-ACT-GROUP`, `DS-ACT-SHIFT` — all five already route every row to a folio, so all five must stay green |
| Fault injections required | `FLT-B02` (payment with no folio) must still be detected; `FLT-C03`, `FLT-B05` |
| Historical replay | re-replay all 28 dates. **Expected: no reconciliation moves** — the ledger does not group by folio |
| Certification evidence | the 40 row ids before and after; D1 showing only `Q14` moving; D4 showing only `INV-A02`/`INV-A03` moving; D3 showing nothing moving |

---

### W1-R4 — Derivation consolidation, read-path

**Objective.** One date-scoped definition of occupancy, ADR and RevPAR,
consumed by every surface. This is the P1/P3 consolidation the constitution
requires.

| | |
|---|---|
| Canonical implementation | `occupancy_engine.occupancy_snapshot` (the only date-capable one), extended to serve ADR and RevPAR |
| Obsolete implementations to retire | `get_occupancy`, `get_occupied_count`, `get_adr`, `get_revpar`, `get_sellable_room_count` in their un-dated forms; the MIS surface's private aggregates; the dashboard tiles' private aggregates |
| Affected reports | `main.dashboard`, `reports.front_office_mis`, `reports.flash`, `reports.occupancy`, `reports.revenue`, night audit occupancy |
| Affected services | `kpi_helpers`, `occupancy_engine`, `mis_service`, `ceo_kpis`, `kpi_command_center` |
| Migration requirements | none — read-path only. **No stored figure changes; what changes is what a historical query returns** |
| Rollback | `git revert` |
| Expected invariant movement | none directly. `INV-C04`'s reported occupancy becomes date-correct, which may change its evidence text but not its verdict |
| Expected D1 movement | `Q17` DIVERGED → AGREED; `Q18` DIVERGED → AGREED; `Q20` DIVERGED → AGREED; `Q06` unchanged. **Three of the eight production divergences close in one release** |
| Datasets required | all five. `DS-ACT-INHOUSE` and `DS-ACT-SHIFT` currently declare `Q18`/`Q20` AGREED and the other three do not — **that split is the regression test for this release**, and it is the finding the coverage ledger produced |
| Fault injections required | `FLT-C04` (cash engine ignores its date), `FLT-C05` (present-tense occupancy leakage), `FLT-C01` |
| Historical replay | **the primary evidence.** D3 §8.2 records 57 figures that do not vary with the date; after this release the occupancy, ADR and RevPAR members of that census must vary |
| Certification evidence | the D3 census before and after; `Q17`/`Q18`/`Q20` closing; the five datasets' parity declarations re-declared |

**This is where the Q18/Q20 finding earns its keep.** The ledger established
that those two diverge on *extra charges*, not occupancy — so this release
must fix the extras handling in the tile and ADR definitions, not merely
add a date parameter. Without that evidence the obvious fix would have been
the wrong one.

---

### W1-R5 — Closed-period integrity

**Objective.** A closed day recomputes to what it reported. Requires
`NightAuditService` to read as-at state rather than present-tense state
(P4, P8).

| | |
|---|---|
| Canonical implementation | `NightAuditService`, reading `folio_control` from as-at reconstruction |
| Obsolete implementations to retire | the `Reservation.status` bucketing in `folio_control`, and the six other entry points D3 §8.3 lists as having no historical form |
| Affected reports | night audit, `reports.revenue`, `reports.daily_reconciliation` |
| Affected services | `night_audit_service`, `occupancy_engine` |
| Migration requirements | **none to stored data.** The stored snapshot is not rewritten — that would be falsifying the record (P12). What changes is the *recomputation* |
| Rollback | `git revert`. No data migration |
| Expected invariant movement | `INV-B03` VIOLATED(1) → **HOLDS**. Release-blocking **1 → 0**; certification-blocking 3 → 2 |
| Expected D1 movement | `Q12`, `Q13` expected to close; `Q06` unaffected |
| Datasets required | a **new** dataset carrying a closed night audit — none of the five has one. See §8 |
| Fault injections required | `FLT-D03` (which `INV-B03` currently fails to detect — see §7), `FLT-D02`, `FLT-C05`, `FLT-D10` |
| Historical replay | **all 28 dates, and this is the release's whole verification.** RC-set must reconcile LEDGER, ENGINE and RECORDED for every date |
| Certification evidence | the 27 May recomputation matching its frozen ₹0.16 rather than ₹200.15 |

---

### W1-R6 — OTA receivable restatement

**Objective.** ₹7,977.92 currently booked as owed by an agent that does not
exist is either recognised as cash taken at the desk or written off.

| | |
|---|---|
| Canonical implementation | the settlement write path; `ota_reconciliation` for the netting |
| Obsolete implementations to retire | the OTA receivable gross view that never nets payouts (`Q22`) |
| Affected reports | `reports.ota_reconciliation`, `reports.ota_settlement`, `reports.ar_aging`, `reports.flash`, night audit payment summary |
| Affected services | `ota.py`, `ota_reconciliation`, `ota_settlement_service`, payment posting |
| Migration requirements | **5 payments reclassified.** This changes what the hotel says it is owed |
| Rollback | verified snapshot immediately before; the 5 payment ids are recorded |
| Expected invariant movement | `INV-C01` VIOLATED(5) → HOLDS; `INV-C05` VIOLATED(5) → HOLDS (`INV-C05` is OPERATIONAL and counts toward neither gate). Certification-blocking **2 → 1**, given W1-R3 and W1-R5 have run |
| Expected D1 movement | `Q22` DIVERGED → AGREED |
| Datasets required | a **new** OTA dataset — none of the five carries an OTA payment. See §8 |
| Fault injections required | `FLT-A01`, `FLT-C07` |
| Historical replay | all 28 dates; the 27 May night audit's ₹4,747.64 "OTA settled" is part of this population and will move |
| Certification evidence | **auditor sign-off (§6)**, plus the per-payment before/after |

---

### W1-R7 — Operational data remediation

**Objective.** Room 21 on 2026-05-28 is recorded as sold to two
reservations. Determine which is correct and correct the record.

| | |
|---|---|
| Canonical implementation | none — this is a data correction, not a code change |
| Migration requirements | one room-night reassigned or one reservation corrected |
| Rollback | verified snapshot; single row |
| Expected invariant movement | `INV-C04` VIOLATED(1) → HOLDS. Certification-blocking **1 → 0** |
| Expected D1 movement | occupancy-derived quantities for that night; `Q20` if not already closed by W1-R4 |
| Datasets required | none new |
| Fault injections required | `FLT-A08` (room move without releasing the old room) |
| Historical replay | 2026-05-28 specifically |
| Certification evidence | **management sign-off** on which booking was real; occupancy, ADR and RevPAR for that night restated |

---

### W1-R8 — Night Audit HTML consolidation

**Objective.** One HTML Night Audit page instead of two, with the snapshot
integrity warning moved onto the page operators actually open. No financial
figure changes; nothing is deleted until a release has proved it unreachable.

| | |
|---|---|
| Canonical implementation | `main.night_audit` → `night_audit_panel.html`, as the `# Redirect HTML to the centralized Night Audit module` comment at `reports.py:2383` always intended |
| Obsolete implementations to retire | `reports/night_audit.html` (3,975 lines) and the `render_template` fallthrough at `reports.py:2735` — **after** one release of deprecation logging, not before |
| Affected reports | `reports.night_audit` (HTML branch only; `json` / `excel` / `print` unchanged), `main.night_audit` |
| Affected services | none. `services.verify_snapshot_integrity` is called, not modified |
| Migration requirements | **none** — no data touched |
| Rollback | `git revert`. No data to restore |
| Expected invariant movement | **none.** `INV-B02` already HOLDS and keeps holding — this release changes who can *see* it, not whether it fires |
| Expected D1 movement | **none.** No derivation touched |
| Datasets required | none new |
| Fault injections required | none new. `FLT-D02` already edits a frozen snapshot and asserts `INV-B02` fires; W1-R8 adds the requirement that the **panel renders the warning** under that same fault |
| Historical replay | D3 unchanged — no engine touched |
| Certification evidence | D2 capture of the panel under `FLT-D02` showing the banner present, plus a route-level test matrix pinning each `format` to its template |

**The defect, stated precisely.** `fmt` defaults to `'html'` at
`reports.py:2381`, and the `fmt == 'html'` branch at `reports.py:2383-2389`
redirects to `main.night_audit`. The branches run `json` → `excel` → `html`
→ `print`, so the render at `reports.py:2735` is reachable **only** by an
unrecognised `format` value. No template, JS or Python passes one. The stale
`# --- HTML (default) and Print ---` comment sitting *below* the redirect is
the fingerprint: the redirect was inserted above a block that used to serve
HTML, and the block was left behind.

**What is actually lost is narrower than it first appears.** Snapshot tamper
*detection* is live and fault-proven: `INV-B02` is CRITICAL and
`Blocking.RELEASE`, declares
`canonical_engine='app.services.verify_snapshot_integrity'` so it calls the
application's own helper rather than re-implementing the hash, and `FLT-D02`
appends a space to `snapshot_json` and asserts it fires. P11 is satisfied at
the verification layer. What is unreachable is the **operator-facing**
surface: the red "Snapshot integrity warning — hash mismatch" banner at
`reports/night_audit.html:391` and the Re-run Audit button it gates. The
panel has no integrity surface at all — its one `shield-exclamation` is the
"Money at Risk" section icon.

**Why that still matters: nothing runs the invariant engine on a schedule.**
`app/__init__.py:530-535` schedules the night audit and the daily backup.
There is no invariant job. `INV-B02` fires only when someone runs the
verification runner by hand, so between runs a tampered snapshot is visible
to no one. This is the one part of W1-R8 that is not cosmetic.

**Sequence. The ordering is the substance of this release.**

1. **Restore the surface first.** Compute
   `snapshot_integrity = verify_snapshot_integrity(current_log)` in
   `main.night_audit` beside the existing context at `routes.py:4764`, and
   port the banner block from `reports/night_audit.html:385-410` into
   `night_audit_panel.html`. Silent, no gate beyond Wave 0.
2. **Make the panel the single HTML authority.** Route keeps four branches:
   panel (HTML), print, JSON, Excel.
3. **Instrument before deleting.** Leave the fallthrough in place for one
   release with a `log.warning("Deprecated template rendered")`. If nothing
   logs, the reachability argument is proved by measurement rather than by
   grep.
4. **Schedule verification.** Night Audit → snapshot → verification job →
   dashboard warning → audit status, so the control does not depend on
   anybody remembering. This is the largest improvement in the release and
   it closes the gap for the other 24 invariants too, not just `INV-B02`.
5. **Delete** `reports/night_audit.html`, its `render_template`, and the
   HTML fallthrough — only after step 3 has come back silent.
6. **Regression tests** pinning each branch to its template: `/night-audit`
   → `night_audit_panel.html`; `?format=print` → print template;
   `?format=json` → JSON; `?format=excel` → Excel; and a hash mismatch
   → warning rendered. These are what stop the situation reappearing.

Step 5 without steps 1–2 would delete the surface rather than restore it.

**Acceptance criteria.** Signed off against evidence, not against opinion.
Every row is checkable by someone who did not write the change.

| # | Criterion | Expected result | How it is evidenced | Step |
|---|---|---|---|---|
| A1 | Active Night Audit panel displays snapshot integrity | PASS | `GET /night-audit` on a date whose snapshot hash mismatches renders the banner | 1 |
| A2 | `INV-B02` continues to HOLD | PASS | `inv-run` before and after, unchanged verdict. **Any movement fails this release** | 1–6 |
| A3 | `FLT-D02` displays operator warning | PASS | Fault injected, panel captured showing the banner, fault cleaned up | 1 |
| A4 | HTML panel becomes sole HTML implementation | PASS | Route matrix: exactly one branch returns an HTML page; `json` / `excel` / `print` unchanged | 2 |
| A5 | Legacy template rendered during observation period | **0 occurrences** | `Deprecated template rendered` absent from a full release of logs | 3 |
| A6 | Legacy template removed after observation release | PASS | `reports/night_audit.html`, its `render_template` and the fallthrough all gone; A4 still passes | 5 |
| A7 | Route-to-template bindings pinned by test | PASS | Four tests green: panel / print / JSON / Excel, plus the A1 mismatch case | 6 |
| A8 | No financial figure moves | PASS | D1 parity and D4 invariant runs identical before and after | 1–6 |

A5 is the only criterion that cannot be satisfied by inspection: it is a
measurement over a release, and it is what licenses A6. If A5 records even
one occurrence, the reachability argument is wrong and step 5 does not
proceed — the correct response is to find the caller, not to lower the bar.

A2 and A8 are the release's safety rails. This is a routing and presentation
change; if either moves, something outside the stated scope was touched.

---

### Platform note — verification scheduling exceeds this release

Step 4 is written into W1-R8 because that is where the gap surfaced, but its
scope is the platform, not the Night Audit. Today:

```
Application → data changes → nothing
                                 ↓
              developer remembers to run verification by hand
```

The architecture this should become:

```
Application → data changes → verification scheduler → invariant engine
                                                            ↓
                                                   dashboard / alerts
```

The difference is not convenience. Every Wave 0 control is currently an
*on-demand* control: 25 invariants and 40 faults that fire only when a human
invokes them, with an unbounded window in between. `INV-B02` is where this
became visible because its only operator-facing surface was also missing —
two independent silences stacked on the same control — but the scheduling
gap belongs to all 25.

Track it as a platform item. If it is delivered before W1-R8, step 4 reduces
to subscribing the Night Audit panel to something that already exists.

**Note for whoever picks this up.** `reports/night_audit.html` carries an
Aug 2026 `.dash-corp` wrapper around its Daily Financial Summary call. It is
correct and currently a no-op, kept so the panel is not the only styled
render site if the view is ever revived. Its presence is not evidence the
page is reachable.

---

### W1-R9 — Night Audit reconciliation basis correction

**Specification only. No code changed under this heading.**

**Objective.** Correct the accounting basis used when Night Audit compares
revenue against payments. Not a pricing change, not a CI/CO change, not a
revenue calculation change.

| | |
|---|---|
| Canonical implementation | `revenue_summary()['accrual_gross']` — already computed at `night_audit_service.py:477`, already exposed at `:500`. Nothing new is calculated |
| Obsolete implementations to retire | none. Two operands change basis; no code is removed |
| Affected reports | Night Audit reconciliation block and `can_close` only |
| Affected services | `NightAuditService.final_control()` — **nothing else** |
| Migration requirements | **none.** Historical `NightAuditLog` rows keep the old basis. Migration is out of scope |
| Rollback | `git revert`. Two operands; no data written |
| Expected invariant movement | none of the 25 asserts reconciliation today. **A new invariant must be registered before implementation** (D4 standing rule) |
| Expected D1 movement | `quantities.py:853` compares stored vs recomputed `reconciliation_difference`. Historical closed days will **DIVERGE** after the cutover. That divergence is correct and must be declared in advance |
| Datasets required | one new: a fully-settled GST-bearing day. No existing dataset covers this |
| Fault injections required | none new |
| Historical replay | D3 unchanged — no engine touched |
| Certification evidence | the before/after table below, reproduced on the target build |

#### Root cause

`final_control()` compares a pre-tax accrual against tax-inclusive cash:

```
night_audit_service.py:1021   accrual_net    = rev['accrual_net']      # pre-tax
night_audit_service.py:1022   total_payments = pay['total_collected']  # tax-inclusive
night_audit_service.py:1027   today_outstanding = max(0, accrual_net - total_payments)
night_audit_service.py:1032   recon_diff = accrual_net - total_payments - today_outstanding
```

The residual is the GST. Every fully-settled GST-bearing day reports a
reconciliation gap equal to that day's tax.

#### Exact lines to change

Two operands, both in `final_control()`. `accrual_net` → `accrual_gross`:

```python
# add beside the existing reads at :1021-1022
accrual_gross = rev['accrual_gross']

# :1027
today_outstanding = max(0, accrual_gross - total_payments)

# :1032
recon_diff = accrual_gross - total_payments - today_outstanding
```

**Both lines must change together.** Changing only `:1032` and leaving
`:1027` on the net basis produces, on any partially-settled day,
`recon_diff = accrual_gross - accrual_net = tax`, i.e. a *positive* false
gap on exactly the days that are currently clean. A half-applied fix is
worse than no fix.

`total_posted_revenue` stays `accrual_net` at `:1045` — revenue reporting
remains net of tax. Only the cash comparison moves to gross.

#### Before vs after — measured, not projected

Business date 2026-08-09, reservation 1, reproduced against a copy of
`instance/pms.db` by recomputing both formulas from the same
`revenue_summary()` / `payment_summary()` the service itself returns.

| Input | Value |
|---|---|
| `accrual_net` (pre-tax) | 1142.85 |
| `tax_amount` | 57.14 |
| `accrual_gross` (incl tax) | 1199.99 |
| `total_collected` (cash) | 1200.00 |

| | `today_outstanding` | `recon_diff` | blocks close at 1.00? |
|---|---|---|---|
| **Old** | 0.00 | **−57.15** | **yes** |
| **New** | 0.00 | **−0.01** | no |

The old value is confirmed against the live service, which returns
`-57.15000000000009` for this date. The residual −0.01 is per-line tax
rounding, not a basis error.

#### Tolerance — the evidence says leave it at 1.00

The brief asked whether `:1041` should move from `1.00` to `2.00`. **It
should not.** `tax_amount` sums `TaxLine` rows each quantised to 0.01, so
worst-case drift is `n × 0.005` for `n` lines in the day. Breaching 1.00
requires **200 tax lines on one date**. The property has 39 rooms; the
busiest date on record carries 4 tax lines, a worst case of 0.02 — a factor
of fifty of headroom. Raising the tolerance would widen the blind spot for
no measured benefit.

Revisit only if a single date ever exceeds ~150 tax lines. Record the count
alongside the reconciliation figure so the question is answerable from
evidence rather than re-derived.

#### Deliberately NOT fixed in this release

`today_outstanding = max(0, accrual - payments)` makes the subtraction at
`:1032` collapse: when `accrual ≥ payments` the result is identically 0, and
otherwise it is negative. **`recon_diff` can never be positive**, so the
comment at `:1030` — *"Positive = unposted revenue or missing payments for
today"* — describes a state the arithmetic cannot produce. The control
cannot fire in the one direction that would indicate missing revenue.

This is a **semantic** change, not a basis change: letting the sign carry
meaning changes what `total_outstanding` reports. It is a different risk
class and is **out of scope for W1-R9 by decision, not by oversight**.

Mitigating fact established during investigation: `today_outstanding` is
**not persisted**. `NightAuditLog.outstanding_amount` is written from
`folio['total_outstanding']` (the lifetime figure) at `reports.py:2824` and
`:2960`. The only control value persisted from this block is
`reconciliation_difference` at `reports.py:2961`. W1-R9 therefore changes
exactly one stored column.

#### Regression requirements

| Case | Expected |
|---|---|
| Fully-settled GST booking | recon ≈ 0 within tolerance |
| Manual tariff override (res 1) | Rate Mismatch **380.96, unchanged** |
| CI/CO surcharge | late checkout **380.95, unchanged** |
| Revenue reports | byte identical |
| ADR / RevPAR / Occupancy | no movement |
| Night audit closure | not blocked by GST alone |
| Partially-settled day | recon ≈ 0 — guards the half-applied-fix failure above |

The last row is not in the original brief and is the one that catches the
most likely implementation error.

#### Confirmed unchanged

`apply_tariff_adjustment()`, `sync_reservation_nightly_rates()`, leakage
detection, rate-override detection and CI/CO surcharge posting are **not
touched**. The ₹381 Rate Mismatch on res 1 is correct: room type 2 "Deluxe"
carries `base_rate` 1142.86 (₹1200 inclusive at 5%) and the guest was
checked in at 761.90 (₹800 inclusive) under `pricing_mode='total_stay'`
with `tariff_modified_manually=1`. The stored `leakage_reason` reads
*"Rate ₹762 below standard ₹1,143"*. That the ₹400 discount and the ₹400
late-checkout fee are both 380.9x pre-tax is a numeric coincidence, not a
shared cause.

**Open master-data question, not code:** if the property actually sells that
room at ₹800, `room_types.base_rate` for Deluxe is stale and every booking
will flag as leakage indefinitely. Room type 1 "Standard" also looks
misconfigured — `base_rate` 1000 with `gst_rate` 0.

#### Financial impact

No guest was misbilled and no revenue was lost. The stay settled correctly
at ₹1200 (761.90 + 380.95 + 57.15 GST) against payments of ₹800 + ₹400.

The impact is operational: `:1041` appends a close reason when
`abs(recon_diff) > 1.0`, driving `can_close = False`. Night Audit reports a
false reconciliation gap, equal to that day's GST, on any day where settled
cash exceeds pre-tax accrual — that is, any ordinary trading day. The
durable cost is that operators learn to override a control that is wrong by
construction.

#### Risks

1. Historical `NightAuditLog` rows remain on the previous basis; migration
   is out of scope and the cutover applies to newly generated records only.
2. D1 `quantities.py:853` will DIVERGE on historical rows. Declare before
   implementing, as `DS-ACT-CORRECTION` declares its own expected failure.
3. `can_close` becomes stricter in the other direction — a day currently
   passing at a coincidental 0 may surface a genuine gap. That is the
   control starting to work, but it will read as a new failure.
4. GST-exempt configurations see no change, so a green run in an exempt
   environment is not evidence. State this in the test plan.
5. Wave 0 forbids Night Audit modification. W1-R9 cannot begin until Wave 1
   is formally entered and its invariant is registered.

---

## 5. Re-evaluated ordering, and where it differs from the original

The original Wave 1 ordering followed discovery: D1's findings, then D2's,
then D3's. **Wave 0 produced three pieces of evidence that change it.**

| Original position | Revised | Why the evidence changed it |
|---|---|---|
| Folio routing late, because ₹40,374.14 reads as the largest restatement | **W1-R3, third** | The silence census shows it moves **no money total** — only attribution, `Q14`, `INV-A02` and `INV-A03`. It is far safer than its headline, and it gets harder later: the backfill is unambiguous only while every reservation has exactly one folio |
| Dormant defects last, because nothing is broken today | **W1-R2, second** | Provable silence is the strongest evidence available, and W1-R2 is five defects that can all be shipped under it. Deferring them means the first correction, refund or void the hotel ever posts lands on defective code |
| The 500 surfaces treated as cosmetic | **W1-R1, first** | Six are financial reports nobody can open. Zero accounting risk, immediate operational value |
| ADR/RevPAR fix scoped as "add a date parameter" | **W1-R4, with extras in scope** | The coverage ledger established `Q18`/`Q20` diverge on **extra charges, not occupancy**. Date-scoping alone would have left them DIVERGED and looked like a failed fix |
| Night audit fix bundled with the folio fix | **split: W1-R3 and W1-R5** | `INV-B03` is the only invariant enforcing P4 and it has a **demonstrated detection gap** (`FLT-D03`). Bundling would mean shipping a change to closed-period behaviour behind a control known not to fire |

### The resulting order

```
W1-R1  surfaces that do not render          SILENT      no gate beyond Wave 0
W1-R8  night audit HTML, steps 1-4          SILENT      no gate beyond Wave 0
W1-R2  dormant financial correctness        SILENT      no gate beyond Wave 0
        ---- D9 required below this line ----
W1-R3  folio routing                        attribution only
W1-R4  derivation consolidation             reporting
W1-R5  closed-period integrity              HISTORICAL — approval required
W1-R6  OTA receivable restatement           HISTORICAL — approval required
W1-R7  operational data remediation         approval required
W1-R8  night audit HTML, steps 5-6          deletion — one release after step 3
W1-R9  night audit reconciliation basis     SILENT to the guest — see below
```

**W1-R9 sits with W1-R5, not with the silent releases.** It moves no guest
figure and no revenue report, so it is silent in the accounting sense. But
it changes a persisted `NightAuditLog` column and makes historical D1
quantity checks diverge, which is closed-period behaviour and belongs
behind the same D9 gate as W1-R5.

**W1-R8 appears twice deliberately.** Its first four steps are silent and
belong beside W1-R1: both are surfaces the hotel cannot reach, and neither
moves a figure. Its deletion step cannot run in the same release as its
instrumentation step, because the whole point of step 3 is to spend a
release proving by measurement what step 5 then acts on.

`certification_blocking` counts violated invariants whose blocking is
RELEASE **or** CERTIFICATION, so it is a superset of the release count and
the two fall together:

| After | VIOLATED | Release-blocking | Cert-blocking |
|---|---|---|---|
| today | 6 | 2 | 5 |
| W1-R3 | 4 | 1 | 3 |
| W1-R4 | 4 | 1 | 3 |
| W1-R5 | 3 | **0** | 2 |
| W1-R6 | 1 | 0 | 1 |
| W1-R7 | **0** | **0** | **0** |

**The backlog reaches zero violated invariants**, and the last
release-blocking one closes at W1-R5. That is the shape of the plan in one
table: nothing after W1-R5 blocks a release, and nothing after W1-R7
blocks a certificate — assuming D7 exists to issue one.

---

## 6. Changes that permanently alter historical accounting

**These three require explicit management or auditor approval before
implementation. They are not engineering decisions.**

### W1-R5 — closed-period recomputation

A night audit signed off on 27 May currently recomputes to ₹200.15 against
the ₹0.16 it froze. Fixing it means **the recomputation of every closed day
changes**. The stored snapshots are not rewritten — P12 forbids that — but
anyone reprinting a historical night audit after this release gets a
different answer from one printed before it.

*The decision:* is the frozen figure or the corrected recomputation the
authoritative record of that day?

### W1-R6 — OTA receivable reclassification

₹7,977.92 moves from "owed by an agent" to either cash or a write-off. That
changes receivables, changes the 27 May night audit's ₹4,747.64 OTA
settlement line, and may change a tax position depending on how the
reclassification is booked.

*The decision:* was the cash taken at the desk and misposted, or never
taken? Engineering cannot answer this; it is a question about what happened
at a front desk in May.

### W1-R7 — the double-sold room night

One of reservations 20 and 27 did not occupy room 21 on 28 May. Correcting
it restates occupancy, ADR and RevPAR for that night.

*The decision:* which booking was real.

### Explicitly NOT requiring approval

W1-R1, W1-R2 and W1-R3 change **no historical accounting figure**. W1-R3
changes attribution only, and the census proves no money total moves. They
should not be routed through an approval process they do not need — doing
so would slow the safest work in the backlog and dilute the meaning of
approval for the three that genuinely need it.

---

## 7. Prerequisites this blueprint asks for

Strictly the ones without which a release above cannot be verified. **These
are verification-framework work, permitted here only because they are hard
prerequisites for production implementation.**

| Prerequisite | Blocks | Why it is strict |
|---|---|---|
| **D9, backup restore verification** | W1-R3 onward | Rollback of a data migration is a restore, and the system cannot tell whether a backup is restorable. Requires the `backup_logs` checksum column — a production schema change, and the recorded exception Wave 0 deferred |
| **A D4 invariant for invoice number uniqueness** | W1-28 | `FLT-B04` is UNCOVERED. Without it the fix ships with nothing able to prove it worked |
| **`INV-B03` must detect `FLT-D03`** | W1-R5 | `INV-B03` is the sole invariant enforcing P4 **and does not move** when an audited day's stored close total is rewritten. Shipping a closed-period change behind a control with a demonstrated gap is the one sequencing error this blueprint most wants to avoid |
| **A dataset with a closed night audit** | W1-R5 | None of the five has one; all five decline to model it precisely because `INV-B02` and `INV-B03` would have to be satisfied by a hand-written snapshot |
| **A dataset with an OTA payment** | W1-R6 | None of the five carries one; `INV-C01`/`C05` are therefore exercised on production data only |

The last two are ordinary D6 work and are not blocked by anything.

---

## 8. What Wave 0 still does not cover

Stated so the blueprint is not read as a claim of completeness.

- **`INV-A06`** remains VACUOUS pending **R-5**, a governance decision.
- **`INV-C06`** remains VACUOUS pending the **`companies` /
  `content_hash`** master-data identity question.
- **D3 has one closed business day.** Every closed-period conclusion rests
  on a single date.
- **20 of ~220 engine figures per date** are reconciled against the primary
  record; the rest are compared between runs only.
- **The coverage ledger does not measure D3**, deliberately.
- **Four faults remain UNCOVERED**: `FLT-B04`, `FLT-D04`, `FLT-D05`,
  `FLT-D07`.
- **No invariant runs without a human.** `app/__init__.py:530-535` schedules
  the night audit and the daily backup; nothing schedules the invariant
  engine. Every Wave 0 control is therefore an *on-demand* control, and the
  window between runs is unbounded. `INV-B02` is where this was found — see
  W1-R8 step 4 and the platform note beneath it — but the gap is not
  specific to it and closing it for one invariant closes it for all 25.
  **This is a platform limitation, not a Night Audit one**, and it is the
  single largest gap in this list.
- **Reachability is not tested.** Nothing asserts which template a route
  renders, which is how a 3,975-line Night Audit view became unreachable
  without any check failing. W1-R8 step 6 addresses this for one route; the
  general case is untested.

---

## 9. The gate for beginning production remediation

**Wave 0 engineering is declared complete for diagnosis and for silent
remediation.** The evidence is D1–D5 commissioned, D6 with five
commissioned datasets each carrying a passing coverage ledger, 25
invariants all commissioned, 40 faults with 36 commissioned, and 146
retained evidence packs.

Production has not been written to at any point: `instance/pms.db` and all
68 `app/*.py` files are byte-identical to the Wave 0.5 freeze.

### To begin W1-R1 or W1-R2 (silent)

1. `selfcheck` — READ-ONLY VERIFIED.
2. Capture a full baseline: `compare`, `gm-verify`, `replay-verify`,
   `inv-run`, `ds-run`, `ds-coverage` for all five datasets.
3. Declare the expected movement. **For a silent release the declaration is
   "nothing moves on production", and any movement fails the release.**
4. Implement.
5. Re-run all six. Diff.
6. Retain the evidence pack.

**No further deliverable is required.** These two releases are gated by
what Wave 0 already provides.

### To begin W1-R3 or later (material)

All of the above, **plus**:

7. **D9 exists and is commissioned**, or a recorded exception is granted
   for a specific release with a manually verified snapshot taken
   immediately before it.
8. The expected movement is declared **per figure, per invariant, per
   quantity** — not "some figures will change".
9. For W1-R5, W1-R6 and W1-R7: **written management or auditor approval**
   naming the figures that will change and the amounts.
10. The prerequisites in §7 for that specific release are met.

### What may not be claimed

**No release may be described as certified.** D7 does not exist, `inv-run`
reports FAIL with release-blocking violations, and `fault-run` reports
INCOMPLETE and will until D7 and D9 exist. A release can be *measured,
evidenced and approved*. It cannot be *certified* until the Certification
Engine exists to issue the certificate and the Release Gate exists to
withhold it.
