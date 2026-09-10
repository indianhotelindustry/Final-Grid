# Golden Master Re-baseline at `aa6d9e91` - verification-only capture

Directive FG-P1-VERIFICATION-COMPLETION-20260909-01, section 9. Performed **after** every verification step above passed without a new Phase-1-caused regression. No application code, schema, data or historical evidence changed.

## 1. What was done

| Step | Command | Result | Evidence pack |
|---|---|---|---|
| Capture | `python -m verification gm-capture --tag phase1_aa6d9e91 --quiet` | 158 surfaces captured; frozen clock 2026-08-10T12:00:00; business date 2026-08-10; app v2.2.18; 5 surfaces classed unhealthy by the framework (same five as the pre-Phase-1 capture: non-200 responses captured as rendered); FINANCIAL 80; read-only verified | `20260909_160149_gm_capture_phase1_aa6d9e91` |
| Masters written | new set **`verification/masters/phase1_aa6d9e91/`** (index + 158 surface files) | new, untracked directory | - |
| Reproducibility | `gm-verify --tag phase1_aa6d9e91 --quiet` | **158 / 158 clean, 0 differences, 0 blocking - PASS** | `20260909_160158_gm_verify_phase1_aa6d9e91` |
| Historical master re-check | `gm-verify --tag production --quiet` | 157 / 158 clean, **4 differences, all on `main.night_audit`**: `panel_ui.attribution[len]` added (8), `panel_ui[len]` 24->25, `panel_ui.warn_conditions` 1->2, `panel_ui.total_issues` 1->2 - **identical to the Phase 1 execution's declared E-6 set** | `20260909_160212_gm_verify_production` |

## 2. Historical evidence preserved

- The tracked master set `verification/masters/production/` (captured 2026-09-09T00:56:05 at `e69f2ac`, committed in `95083995`) was **not overwritten, not deleted, not modified**: `git status --porcelain verification/masters/` shows only the new untracked `phase1_aa6d9e91/` directory.
- The pre-Phase-1 baseline documents in `evidence/20260908_golden_master/` and the packs `20260909_0056xx` are untouched.
- The new tag is a **separate** set. Using a new tag instead of re-capturing `production` is what keeps the historical set intact while still establishing the clean post-Phase-1 baseline.

## 3. E-6 confirmation

The four differences reported by the historical master are exactly the E-6 reconciliation row and its two consequences (a warning for the eight unattributed D11 rows and the resulting issue count), on the one surface E-6 predicted, with no other surface moved. They **remain correctly classified as expected**. Against the new master they are 0 differences by construction, which is the point of the re-baseline: Phase 2's Gate G can start from `phase1_aa6d9e91` with a clean 158/158 instead of carrying four declared differences.

## 4. Caveats

1. The new master reproduces only while the production database is at anchor `51dd83b7...` and the clock freeze resolves to business date 2026-08-10; any legitimate database change moves date-scoped surfaces (as `GOLDEN_MASTER.md` section 7 already states).
2. `gm-verify` is a change detector, not an attributor.
3. HTML only (V5); Excel/PDF branches and the 121 non-GET catalogue entries remain uncovered, unchanged from the pre-Phase-1 capture.
4. The new master set is **untracked**. Whether it is committed (and whether the `production` tag is retired or re-pointed) is a Founder decision; this directive forbids commits.
