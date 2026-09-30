#!/usr/bin/env bash
# SR-2 regression battery for one worktree (baseline c703150 or implementation).
#   bash run_regression.sh <worktree> <output dir>
# Both verification and app come from <worktree> (run_pvf.py); production is
# only the read-only source. Packs the commands write into <worktree>'s
# evidence root are moved into <output dir>/pvf afterwards.
set -u
WT=$1; OUT=$2
PY="C:/Users/SIPL Server/Downloads/DSS/FinalGrid/SukoonPMS/venv/Scripts/python.exe"
RUN="$WT/verification/evidence/20260930_sr2_inv_d02/run_pvf.py"
export PYTHONIOENCODING=utf-8
export SECRET_KEY=$("$PY" -c "import secrets;print(secrets.token_hex(32))")
mkdir -p "$OUT/pvf"
ls "$WT/verification/evidence" > "$OUT/packs_before.txt"
for c in "inv-run --tag production:inv_run" "ds-run:ds_run" "ds-commission:ds_commission" \
         "fault-run:fault_run" "gm-verify --tag phase1_aa6d9e91:gm_verify" \
         "replay-verify --tag production:replay_verify" "run:cross_implementation" "inv-registry:inv_registry"; do
  "$PY" "$RUN" ${c%%:*} > "$OUT/${c##*:}.log" 2>&1
  echo "${c##*:} rc=$?" >> "$OUT/exit_codes.txt"
done
ls "$WT/verification/evidence" | comm -13 "$OUT/packs_before.txt" - > "$OUT/pvf_packs.txt"
while read -r p; do mv "$WT/verification/evidence/$p" "$OUT/pvf/"; done < "$OUT/pvf_packs.txt"
rm -f "$OUT/packs_before.txt"
echo "done $WT"
