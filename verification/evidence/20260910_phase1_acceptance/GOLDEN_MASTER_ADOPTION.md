# Golden Master Adoption — `phase1_aa6d9e91`

Directive FG-P1-ACCEPTANCE-20260910-01 §3 (GM-TAG).

## 1. Decision

`phase1_aa6d9e91` is adopted as the **authoritative post-Phase-1 Golden Master baseline**. The historical master `production` (captured 2026-09-09T00:56:05 at `e69f2ac`, committed in `95083995`) is **not deleted and not replaced**; it remains the provenance for the before/after comparison across Phase 1.

## 2. What the adopted set is

| | |
|---|---|
| Location | `verification/masters/phase1_aa6d9e91/` (index + 158 surface files) |
| Captured | 2026-09-09 16:01:49 UTC by `python -m verification gm-capture --tag phase1_aa6d9e91 --quiet`, app v2.2.18, clock frozen 2026-08-10T12:00:00, business date 2026-08-10, against a backup-API copy of the production anchor `51dd83b7…`; read-only verified |
| Surfaces | 158 (FINANCIAL 80); 5 classed unhealthy by the framework — the same five non-200 responses captured as rendered in the pre-Phase-1 set |
| Reproducibility | `gm-verify --tag phase1_aa6d9e91` → **158/158 clean, 0 differences, PASS** (pack `20260909_160158_gm_verify_phase1_aa6d9e91`) |
| Relation to the historical set | `gm-verify --tag production` at `aa6d9e91` → 157/158, the **four declared E-6 differences** on `main.night_audit` only (`panel_ui.attribution[len]` added; `panel_ui[len]` 24→25; `warn_conditions` 1→2; `total_issues` 1→2) — pack `20260909_160212_gm_verify_production`. These four differences are the entire behavioural delta of Phase 1 as seen by the golden-master layer, and they are what the two sets together preserve. |
| Capture pack | `20260909_160149_gm_capture_phase1_aa6d9e91` |

## 3. Tracking status — a scope residual, recorded not improvised

§11 of the acceptance directive authorizes one commit containing only the governance updates, the four named Phase 1 evidence directories and this directory. The adopted master set `verification/masters/phase1_aa6d9e91/` and the eleven harness packs of 2026-09-09 (`20260909_155816_inv_run_phase1_vc_setA`, `155820_inv_run_phase1_vc_setB` (superseded), `155824_inv_run_phase1_vc_setC`, `155829_phase1_vc_newactivity`, `155832_phase1_vc_production`, `160110_inv_run_phase1_vc_setD`, `160115_phase1_vc_setD`, `160149_gm_capture_phase1_aa6d9e91`, `160158_gm_verify_phase1_aa6d9e91`, `160212_gm_verify_production`, `160407_inv_run_phase1_vc_setB`) are **not** in that list and therefore remain **untracked** after this directive.

Consequence: the adopted baseline is decided in governance but not yet durable in the repository. The repository's own rule (`.gitignore:61`, "Untracked evidence is not evidence") means a **separate commit authorization** is needed for `verification/masters/phase1_aa6d9e91/` and the packs before Phase 2's Gate G can rely on them from history rather than from the working tree. Recommended: one bounded commit, "FinalGrid: adopt phase1_aa6d9e91 golden master", staging exactly those paths.

## 4. Use going forward

- Phase 2 Gate G compares against `phase1_aa6d9e91`; a verifier runs `gm-verify --tag phase1_aa6d9e91` and expects 0 differences until a declared Phase 2 delta document says otherwise.
- The `production` tag is historical: it should not be re-captured, and a `gm-verify --tag production` will keep reporting the four E-6 differences by design.
- Caveats carried from the capture: reproduces only at anchor `51dd83b7…` with the clock freeze resolving to business date 2026-08-10; HTML only (V5); 121 non-GET catalogue gaps; `gm-verify` is a change detector, not an attributor.
