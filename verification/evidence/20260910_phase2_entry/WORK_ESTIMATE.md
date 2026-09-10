# Work Estimate — ranges, dependencies, no date

Directive FG-P2-ENTRY-READINESS-20260910-01, section 9. Units are **engineering-days of the pattern practised in this repository**: one bounded directive → implementation on copies → per-directive verification pack (`verify.py` in the Phase 1 idiom, `inv-run`, `gm-verify`, `replay-verify`, datasets, matrix) → review → commit. Calibration: Phase 1 (24 writers, 8 files, 44 cases) took one session for implementation plus one for the W-20 closure, one for the completion review and one for the verification completion; Recovery Foundation took one session. Ranges are wide on purpose; a directive that surfaces a defect (as W-07/W-11 did) extends its own range.

## 1. Implementation effort

| Package | Content | Range (days) | Dependency that can extend it |
|---|---|---|---|
| Pre-2b package | P2-A1 CF-10 (12 writers), P2-A2 CF-11, P2-A3 pruning exemption, P2-A4 FD-015, P2-A5 launchers | **3 – 6** | decision on per-row audit for W-16/W-21 (changes closed-day evidence volume → Golden Master and replay declarations); Founder confirmation for P2-A3 |
| Phase 3 — business date & night audit | 3.1 single derivation at the eight K-7 sites and model defaults; 3.2–3.6 close/reopen/interrupted-close/staleness; 3.7 V8 template; 3.8 multi-day sequence; scheduler controls for `night_audit_job` per B-1 or the interim manual ruling; SR-1/SR-2 outcomes | **8 – 15** | B-1 scheduler ADR if automation is wanted; SR rulings; every date change moves report figures → Golden Master re-baseline with declared deltas; replay ledger interaction (N7) |
| Recovery hardening (Phase 9 units 9.1–9.3 brought forward as a bounded directive, Q-6 precedent) | backup-API mechanism + manifest/hash for the operating path; retention exemption; `.enc` restore rehearsal off-box; key custody procedure; scheduled verification (optional for the first release) | **3 – 6** | B-5 "verified state"; manifest-as-column would be a schema change (PD-004) — manifest-as-file avoids it |
| Phase 4 authorization (unit 4.2 only) | route classification (49 report routes), fail-closed `reports_bp` guard, writer-route guards, negative matrix per role | **4 – 8** (only if MP-D9 makes it blocking) | MP-D9; ADR-009 adoption; Housekeeping scope (F13/MP-D6) |
| Q06 GST analysis | read-only comparison of `gst_service.get_gst_report` vs `tax_snapshot`; fix if a defect | **1 – 3** | may reveal a reporting defect with its own Golden Master delta |
| Phase 2b proper | 2b.0 ADR; 2b.1–2b.4 schema-free | **6 – 12** | MP-D9; B-2; PD-004 if a new table is unavoidable; ADR-011 storage decision |
| Other class-C items (FD-015 done above; W-20 rule; FK-ON prep; archival design; observability) | | **4 – 10**, deferrable | — |

Implementation subtotal for the production-blocking path (pre-2b + Phase 3 + recovery + Q06, excluding Phase 4 and 2b): **15 – 30 days**. With Phase 4 unit 4.2 (multi-role property): **19 – 38**. Phase 2b proper is not on the production-blocking path unless the Founder makes maker-checker a certification condition.

## 2. Verification effort

| Activity | Range (days) | Note |
|---|---|---|
| Per-directive packs (each package above) | **0.5 – 1 per directive**, ~6–10 directives → **4 – 8** | already the practised pattern; Phase 1 runtime script is reusable |
| Golden Master re-baselines with declared-delta documents (Phase 3 and any date change will move surfaces) | **1 – 2 per re-baseline**, expect 2–3 → **2 – 5** | Q-4 precedent |
| Replay ledger re-baseline (Phase 6 item forced by Phase 3 date semantics) | **1 – 2** | rewrites stored evidence — needs its own authorization |
| Multi-day night-audit rehearsal on a copy (N7): 5–10 consecutive closes, one reopen, one interrupted close | **2 – 3** | reusable as part of G11 |
| Unauthorized-role matrix for the roles in use (CF-5, Phase 4) | **1 – 2** | only if multi-role |
| Q06 / parity review of the eight diverging quantities | **1 – 2** | read-only |

Verification subtotal: **10 – 20 days**, largely interleaved with implementation.

## 3. Deployment rehearsal (G11)

| Activity | Range (days) |
|---|---|
| Write `docs/RELEASE.md` (or successor): install, upgrade, pre-update backup, signed package verification, post-start checks, rollback, day-one business-date procedure, scheduler settings table | **1 – 2** |
| Fresh-install rehearsal on a clean machine from the release tag | **1** |
| Upgrade rehearsal from a copy of the current production instance (pre-update backup → `update.bat` → boot → G10 on the rehearsal copy) | **1 – 2** |
| Rollback rehearsal to the previous tag + pre-update backup, G10 again | **1** |
| Launcher execution on the operator machine (FD-017) | **0.5** |
| Recovery rehearsal G8 from an application `.enc` backup, off-box | **1** (after the recovery package) |

Subtotal: **5 – 8 days**, after the blocking implementation is in.

## 4. Final certification (G12)

| Activity | Range |
|---|---|
| Release-tag verification set (G10 + G8 + G11 packs) committed | **1 – 2 days** |
| Founder review of gates and rulings FD-Q3 (D11 verdict), FD-Q4, FD-Q5 | Founder time, not engineering |
| Certification entry in `FOUNDER_DECISIONS.md` + evidence commit | **0.5 day** |

## 5. Totals and the critical path

| Path | Range |
|---|---|
| Engineering + verification to a certifiable single-role release (pre-2b, Phase 3, recovery, Q06, G11, G12) | **≈ 30 – 60 engineering-days** |
| Add Phase 4 unit 4.2 for a multi-role property | **+ 5 – 10** |
| Add Phase 2b proper | **+ 8 – 15**, off the blocking path unless ruled otherwise |

**Critical path:** Founder rulings FD-Q2/FD-Q5/FD-Q6 → pre-2b package → Phase 3 (longest single item; every date change ripples into Golden Master and replay re-baselines) → recovery hardening (can run in parallel with Phase 3) → G11 rehearsal → FD-Q3/FD-Q4 → G12.

**Dependencies that can extend the schedule:** any Phase 3 change that alters closed-day figures (forces replay-ledger re-baseline, a Phase 6 act needing authorization); a Q06 defect; discovery of further latent route defects when the remaining routes are exercised (the CF-11 pattern); MP-D9 arriving late (turns PB-11 from advisory to blocking at the end); key-custody findings for encrypted backups; the `.env`/secret hygiene already flagged during staging.

**No deployment date is given.** The ranges assume one engineer working in the repository's bounded-directive rhythm with Founder rulings available at the gates.
