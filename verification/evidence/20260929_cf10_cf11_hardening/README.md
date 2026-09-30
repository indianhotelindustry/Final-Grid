# 20260929_cf10_cf11_hardening — provenance of the result files

Recorded 2026-09-30, when these result files were first committed (they had been left untracked by the session that produced commits `74dee9b` … `d9fa55f`). Nothing in this directory was edited; this note is the only file added.

- `verify_cf10_cf11.py` is the harness revision committed at `74dee9b` and extended by the later commits of that chain. It does not record which application commit it ran against.
- `results_red_*.json` were produced against the `683db72` application files; `results_green_*.json` against the working tree during the chain. The harness gained targeted fault variants mid-chain (`7ee43c7`), so files with the same group name can come from different harness revisions — for example `results_red_cf11.json` (38 gates) versus `results_red_targeted_cf11.json` (48 gates). The `results_green_cf11/corr/w10` files were re-run at the time of `7ee43c7`.
- Superseded by `../20260930_cf10_completion/`. That pack re-runs every group with one harness revision against clean git worktrees at `683db72` and `d9fa55f` and at the final code commit, and records the application commit in every result file. Its numbers reproduce this directory's final RED counts for cf11 / corr / w10 / w12 / w13 / w14 exactly.
