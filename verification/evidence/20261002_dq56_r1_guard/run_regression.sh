#!/usr/bin/env bash
# DQ56-R1 regression battery for one worktree (control c9eeff0 or branch).
#   bash run_regression.sh <worktree> <output dir> <secret key>
# Same command set as 20260930_sr2_inv_d02/run_regression.sh; the driver is
# run_pvf_noenv.py (live .env NOT loaded; no outbound credentials). Both
# worktrees must be run with the SAME throwaway <secret key>. Production is
# only the read-only source. Packs written into <worktree>'s evidence root are
# moved into <output dir>/pvf afterwards.
set -u
WT=$1; OUT=$2
PY="C:/Users/SIPL Server/Downloads/DSS/FinalGrid/SukoonPMS/venv/Scripts/python.exe"
RUN="$(cd "$(dirname "$0")" && pwd)/run_pvf_noenv.py"
export PYTHONIOENCODING=utf-8
export SECRET_KEY=$3
export FLASK_ENV=production
mkdir -p "$OUT/pvf"
ls "$WT/verification/evidence" > "$OUT/packs_before.txt"
for c in "inv-run --tag production:inv_run" "ds-run:ds_run" "ds-commission:ds_commission" \
         "fault-run:fault_run" "gm-verify --tag phase1_aa6d9e91:gm_verify" \
         "replay-verify --tag production:replay_verify" "run:cross_implementation" "inv-registry:inv_registry"; do
  "$PY" "$RUN" "$WT" ${c%%:*} > "$OUT/${c##*:}.log" 2>&1
  echo "${c##*:} rc=$?" >> "$OUT/exit_codes.txt"
done
ls "$WT/verification/evidence" | comm -13 "$OUT/packs_before.txt" - > "$OUT/pvf_packs.txt"
while read -r p; do mv "$WT/verification/evidence/$p" "$OUT/pvf/"; done < "$OUT/pvf_packs.txt"
rm -f "$OUT/packs_before.txt"
echo "done $WT"
