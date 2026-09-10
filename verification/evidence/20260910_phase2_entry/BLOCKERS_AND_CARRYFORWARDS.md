# Blockers, Non-Blocking Carry-Forwards, Founder Decisions

Directive FG-P2-ENTRY-READINESS-20260910-01, section 8. Short, evidence-based. Inventory ids refer to `PRODUCTION_READINESS_INVENTORY.md`.

## PRODUCTION BLOCKERS — must be resolved before deployment

| # | Blocker | Why it blocks | Resolution path | Gate |
|---|---|---|---|---|
| PB-1 | Destructive `audit_logs` pruning (AD-2) | FD-008 / AR-007: non-compliant "before production certification"; provenance of every financial row and of the D11 classification is deleted on a rolling 90-day basis from ~2026-11-07 | P2-A3 minimal fix (ADR-012 item 1) | G5 |
| PB-2 | Business-date integrity at financial writers (FI-3, K-7) | rows dated from the wall clock or model default break closed-day protection (INV-B01/B04/B06) and day totals on any live day where the close lags midnight; FD-013 adopted | Phase 3 unit 3.1 | G6 |
| PB-3 | Night-audit operational semantics and rehearsal (FI-4, RL-2) | the close is the financial control; never operated nightly; interrupted-close recovery and reopen semantics unproven; day-one business-date procedure undefined | Phase 3 units 3.2–3.6, 3.8; G11 multi-day rehearsal | G6, G11 |
| PB-4 | Verified recovery for the operating backup path (RC-1, RC-3, RC-6) | FD-005 PD-006 and FD-006 D9 are mandatory gates; the backups the running system makes (`shutil.copy2`, encrypted, purged at 30 days, no checksum) have never been restored | ADR-007 items 1–3 for the app path; `.enc` off-box rehearsal; key custody; B-5 | G8 |
| PB-5 | Two non-functional credit paths (FI-9, CF-11) | credit settlement and voucher redemption cannot post; money cannot be booked through them | P2-A2 | G3 |
| PB-6 | Strict audit coupling at 12 writers (FI-2, CF-10) | Founder sequencing (pre-2b) and Q-5 target; corrections/refunds can commit with no audit row | P2-A1 | G3, G5 |
| PB-7 | Launcher reproducibility (RL-3, V10) | the shipped start/stop/update launchers may not execute on the operator machine; FD-017 fix approved | P2-A5 + G11 launcher rehearsal | G9, G11 |
| PB-8 | Q06 GST taxable-base divergence on production (FI-10) | two engines disagree by a factor of two on real data; a GST figure cannot be certified until one is shown correct | analysis directive (read-only first); fix if a defect | G3 |
| PB-9 | Deployment and rollback procedure and rehearsal (RL-7, VF-8) | none exists (`docs/RELEASE.md` absent); never rehearsed | write + rehearse (G11) | G11 |
| PB-10 | D11 verdict for certification (FI-12) | `inv-run` reads OVERALL FAIL by design; a certification cannot be recorded on an unreadable verdict | Founder: disposition (B-3) or population declaration (reserved by FD-010/AR-001) | G12 |
| PB-11 | Role authorization for writers and reports (AU-1, AU-2) — **conditional** | blocks only if the property will run more than the Admin role (MP-D9); with one Admin user it is advisory | MP-D9 → Phase 4 unit 4.2 | G4 |

Everything else in class A of the inventory maps onto one of these eleven.

## NON-BLOCKING CARRY-FORWARDS — may remain after deployment, with rationale

| Item | Rationale |
|---|---|
| `folio_id NOT NULL` (DB-2) | attribution is enforced fail-closed in code and monitored by INV-A02; blocked by the D11 decision anyway |
| FK enforcement ON (DB-1) | 0 orphans; invariants detect orphan financial rows; enabling changes delete behaviour and needs its own verification — better done under Phase 4/5 discipline than rushed |
| Migration mechanism (DB-3) | no schema change in the release; becomes blocking at the first schema change |
| Maker-checker for folio mutations (AU-3) | void/refund maker-checker exists; folio mutations are Admin/Manager with coupled audit; a one-operator property has no second approver until MP-D9 |
| Operator-accountability envelope (AU-4) | coupled audit rows give operator + IP today; role/business-date fields are an improvement, not a control gap once PB-6 lands |
| FD-015 read scope (AU-5) | convenience |
| Audit archival design (AD-3) | needed for long-run retention, not to stop the immediate loss (PB-1) |
| Replay coverage of `attribution_control` (CF-6), sixth dataset, Excel/PDF masters, INV-R01 commissioning, D7/D8/D10 tooling | verification-platform completeness; certification can be evidenced manually |
| W-20 repeat-call hour (FI-11) | visible and reversible; product rule |
| Concurrency model (RL-4), central services (RL-6), observability (RL-5) | single-property LAN operation; no integrity consequence |
| Guest-identity wording (Phase 7), dormant subsystems (Phase 8) | no financial consequence; Phase 8 needs real operation first |
| CF-5 unauthorized-role cases | today's single role; folded into Phase 4's matrix |

## FOUNDER DECISIONS — only those genuinely required

| # | Decision | Why now | Gates it unlocks |
|---|---|---|---|
| FD-Q1 | **MP-D9 operator profile** (roles the property will run; self-approval rule for a single operator) — or an explicit extension of the interim Admin/Manager default | gates Phase 2b (ADR-010), Phase 4 (ADR-009/011), and whether PB-11 is a blocker | G4, 2b entry |
| FD-Q2 | **Audit-pruning exemption placement** — confirm P2-A3 as a bounded exemption now (as FD-017 was) rather than Phase 4 | ~2026-11-07 exposure | G5 |
| FD-Q3 | **D11 certification verdict** — disposition of the eight rows (B-3, Phase 5 territory) or a population declaration / constitutional note explicitly reserved by FD-010 and AR-001 | G12 cannot be recorded on OVERALL FAIL | G12 |
| FD-Q4 | **"Verified state" definition for PD-006** (B-5; ADR-006 proposal: identical hash, or identical integrity + manifest + `inv-run` verdicts) | G8 needs an acceptance criterion | G8 |
| FD-Q5 | **Night-audit operating mode for the first release** — manual close (current production setting) accepted as the interim control until the B-1 scheduler ADR | G9 needs a ruling, not an assumption | G9 |
| FD-Q6 | **SR-1 / SR-2 semantics** (advance dating vs INV-B06; refund rows vs INV-D02) | real-day invariant verdicts are otherwise unreadable | G3, G10 |
| FD-Q7 | **B-2 maker-checker operation matrix** (ADR-010 adoption) | Phase 2b entry | 2b |

Not required now (settled or at a later gate): FD-010 D11 treatment itself, Q-3 dating scope (Phase 3 will implement it), FK/NOT NULL (Phase 4/5), B-4 schema authority (first schema change), MP-D1/D3/D4/D6/D7/D8 (their phase gates, AR-015), Level 3 (FD-003).
