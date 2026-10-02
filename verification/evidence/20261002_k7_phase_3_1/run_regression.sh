#!/usr/bin/env bash
# K-7 Phase 3.1 regression battery for ONE worktree (control = activation commit, or branch).
#   bash run_regression.sh <worktree> <role> <output dir> <secret key>
# Both worktrees are run with the SAME throwaway <secret key>. Production is only the read-only
# copy source. Live .env never loaded. Output: logs, exit codes, per-suite result files.
set -u
WT=$1; ROLE=$2; OUT=$3
MAIN="C:/Users/SIPL Server/Downloads/DSS/FinalGrid/SukoonPMS"
PY="$MAIN/venv/Scripts/python.exe"
HERE="$(cd "$(dirname "$0")" && pwd)"
PVF="$HERE/run_pvf_noenv.py"; LEG="$HERE/run_legacy_noenv.py"
export PYTHONIOENCODING=utf-8 SECRET_KEY=$4 FLASK_ENV=production
mkdir -p "$OUT/pvf" "$OUT/cf10" "$OUT/legacy"
S="$WT/verification/_work/k7reg"; mkdir -p "$S"
cp "$MAIN"/verification/evidence/20260930_cf10_completion/reg_*.py "$S/"
cp "$MAIN"/verification/evidence/20260930_cf10_completion/verify_cf10_cf11.py "$S/"
WTW=$(cygpath -w "$WT"); CF10OUT=$(cygpath -w "$OUT/cf10")
rc() { echo "$1 rc=$2" >> "$OUT/exit_codes.txt"; }

# 1. PVF layers (same set as SR-1, plus inv-commission)
ls "$WT/verification/evidence" > "$OUT/packs_before.txt"
for c in "inv-run --tag production:inv_run" "ds-run:ds_run" "ds-commission:ds_commission" \
         "fault-run:fault_run" "gm-verify --tag phase1_aa6d9e91:gm_verify" \
         "replay-verify --tag production:replay_verify" "run:cross_implementation" "inv-registry:inv_registry" \
         "inv-commission:inv_commission"; do
  "$PY" "$PVF" "$WT" ${c%%:*} > "$OUT/${c##*:}.log" 2>&1; rc "pvf_${c##*:}" $?
done
ls "$WT/verification/evidence" | comm -13 "$OUT/packs_before.txt" - > "$OUT/pvf_packs.txt"
while read -r p; do mv "$WT/verification/evidence/$p" "$OUT/pvf/"; done < "$OUT/pvf_packs.txt"
rm -f "$OUT/packs_before.txt"

# 2. CF-10 / CF-11 harness, one group per process (+ w14 declared as a system action)
for g in cf11 corr w10 voucher w12 w13 w14 w24 na actor; do
  CF10_APP_ROOT="$WTW" CF10_OUT_DIR="$CF10OUT" CF10_RUN_LABEL=$ROLE "$PY" "$LEG" "$WT" script "$S/verify_cf10_cf11.py" $g >> "$OUT/cf10_harness.log" 2>&1; rc "cf10_$g" $?
done
CF10_APP_ROOT="$WTW" CF10_OUT_DIR="$CF10OUT" CF10_RUN_LABEL=${ROLE}declared "$PY" "$LEG" "$WT" --system-mechanism verification:cf10_w14 script "$S/verify_cf10_cf11.py" w14 > "$OUT/cf10_w14_declared.log" 2>&1; rc cf10_w14_declared $?

# 3. Phase 1 writers A-D and Phase 1 execution (undeclared and declared)
for s in A B C D; do
  "$PY" "$LEG" "$WT" script "$S/reg_verify_writers.py" $s > "$OUT/legacy/writers_$s.log" 2>&1; rc writers_$s $?
  mv "$S/writers_set$s.json" "$OUT/legacy/writers_set$s.json" 2>/dev/null
  "$PY" "$LEG" "$WT" --system-mechanism verification:verify_writers script "$S/reg_verify_writers.py" $s > "$OUT/legacy/writers_${s}_declared.log" 2>&1; rc writers_${s}_declared $?
  mv "$S/writers_set$s.json" "$OUT/legacy/writers_set${s}_declared.json" 2>/dev/null
done
"$PY" "$LEG" "$WT" script "$S/reg_phase1_execution_verify.py" > "$OUT/legacy/phase1_execution.log" 2>&1; rc phase1_execution $?
mv "$S/result.json" "$OUT/legacy/phase1_execution_result.json" 2>/dev/null
"$PY" "$LEG" "$WT" --system-mechanism verification:phase1_execution script "$S/reg_phase1_execution_verify.py" > "$OUT/legacy/phase1_execution_declared.log" 2>&1; rc phase1_execution_declared $?
mv "$S/result.json" "$OUT/legacy/phase1_execution_declared_result.json" 2>/dev/null

# 4. Phase 2a, Q06, retention, W-20, restore tool
"$PY" "$LEG" "$WT" script "$S/reg_phase2a_verify.py" > "$OUT/legacy/phase2a.log" 2>&1; rc phase2a $?; mv "$S/result.json" "$OUT/legacy/phase2a_result.json" 2>/dev/null
"$PY" "$LEG" "$WT" script "$S/reg_verify_q06_fix.py" > "$OUT/legacy/q06.log" 2>&1; rc q06 $?; mv "$S/q06_fix_regression_result.json" "$OUT/legacy/" 2>/dev/null
"$PY" "$LEG" "$WT" script "$S/reg_verify_retention.py" > "$OUT/legacy/retention.log" 2>&1; rc retention $?; mv "$S/retention_test_result.json" "$OUT/legacy/" 2>/dev/null
"$PY" "$LEG" "$WT" script "$S/reg_w20_runtime_verify.py" > "$OUT/legacy/w20.log" 2>&1; rc w20 $?; mv "$S/result.json" "$OUT/legacy/w20_result.json" 2>/dev/null
(cd "$WT" && "$PY" tools/test_restore_db.py > "$OUT/legacy/test_restore_db.log" 2>&1; rc test_restore_db $?)

# 5. DQ56-R1 guard tests (app/reports.py sits next to the K-7 code)
"$PY" "$HERE/../20261002_dq56_r1_guard/verify_dq56.py" --app-root "$WT" --source "$MAIN/instance/pms.db" \
      --work "$WT/verification/_work/k7dq56" --out "$OUT/legacy/dq56_$ROLE.json" --label $ROLE \
      --live-root "$MAIN" > "$OUT/legacy/dq56.log" 2>&1; rc dq56 $?
echo "done $ROLE"
