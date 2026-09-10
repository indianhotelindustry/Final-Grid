# Carry-Forward Register — after Founder Resolution Round 3 (2026-09-10)

Carried from `20260910_phase1_acceptance/CARRY_FORWARD_REGISTER.md` and `20260910_phase2_entry/`. Round 3 closes **BACKLOG B-5** and the **MP-D9 interim question for the first release** only. Nothing else is closed.

## Open — preserved exactly

| Item | Subject | Status after Round 3 | Owner / gate |
|---|---|---|---|
| CF-5 | Unauthorized-role verification (T-N02 cases) | OPEN; under FD-P2-01 the roles in use are Admin (+Manager), so the matrix to verify is small; run with Phase 4 or a bounded verification directive | Phase 4 / G10 |
| CF-6 | Replay coverage of `attribution_control` | OPEN (deliberate) | Phase 6 ledger re-baseline |
| CF-9 | Deployment verification — release not deployed; post-release `inv-run` and classification of any pre-release NULL rows not yet possible | OPEN | release decision (MP-D3 / PD controls); G11 |
| CF-10 | Financial mutation audit-coupling normalization at the 12 non-strict writers (Q5-P1) | OPEN — bounded pre-2b directive; Phase 2b entry depends on it | pre-2b package |
| CF-11 | Credit-path defects: `settle_credit`, `redeem_credit_voucher` (`notes=` TypeError since `b5b2514`) | OPEN — bounded defect directive | pre-2b package |
| SR-1 | INV-B06 vs business-dated advances | **RULED (FD-P2-06)**; implementation and verification OPEN | Phase 6 invariant-refinement directive |
| SR-2 | INV-D02 vs cancellation refunds | **RULED (FD-P2-06)**; implementation and verification OPEN | Phase 6 invariant-refinement directive |
| Schema / FK / NOT NULL | ADR-005 requirement; AR-004 staged sequence; B-3 (eight rows), B-9 (FK prerequisites) | OPEN | Phase 4/5 |
| Migration mechanism | B-4 single schema authority; unattended boot-time migration | OPEN; blocking only at the first schema change | Phase 5 |
| Recovery implementation | operating backup path, manifest/hash, `.enc` off-box rehearsal, key custody, retention exemption (B-11) — against the adopted PD-006 definition | OPEN — recovery-hardening directive (FD-P2-04) | G8 / Phase 9 |
| Night-audit implementation / hardening | Phase 3 units 3.1–3.8; K-7 dating; staleness escalation; interrupted-close recovery; B-1 scheduler ADR for any later automation | OPEN — under the manual-mode ruling (FD-P2-05) | Phase 3; G6 / G9 |
| Audit retention implementation | remove `AuditLog` from the prune loop (FD-P2-02); archival/retention design (ADR-012, B-6) | OPEN — bounded directive; design later | G5 |
| D11 certification register | build the declared-exception register into the certification pack (FD-P2-03) | OPEN — at G12 | certification |
| Maker-checker | ADR-010 adoption with the matrix (B-2) under FD-P2-07; Phase 2b implementation | OPEN | 2b entry / 2b |
| Deployment rehearsal | procedure (`docs/RELEASE.md` or successor) + fresh-install, upgrade, launchers (FD-017), day-one business date, N-day manual closes, rollback | OPEN | G11 |
| Final certification | G1–G11 packs at the release tag; Founder certification entry | OPEN | G12 |
| Q06 GST divergence on production | must be explained before any GST figure is certified | OPEN (from the entry assessment, not a Round 3 item) | Phase 3 / 6 |
| W-20 repeat-call hour | product finding | OPEN (non-blocking) | pre-2b or Phase 3 |

## Closed by Round 3

| Item | Closed by |
|---|---|
| BACKLOG B-5 — PD-006 "verified state" definition | FD-P2-04 |
| MP-D9 interim question for the first release | FD-P2-01 (full profile stays OPEN at the Phase 4 gate) |
| SR-1 / SR-2 as *review* items | FD-P2-06 (they continue as implementation/verification items above) |
| The seven open items of `20260910_phase2_entry/BLOCKERS_AND_CARRYFORWARDS.md` (FD-Q1…FD-Q7) | FD-P2-01…FD-P2-07 |

## Still open decisions (unchanged)

MP-D1, MP-D3, MP-D4, MP-D6, MP-D7, MP-D8, MP-D9 (full); B-1, B-2 (ADR text), B-3, B-4, B-6, B-7, B-8, B-9, B-10, B-11.
