#!/usr/bin/env bash
# ADR-011 pre-production gate - Phase F regression battery.
#
#   bash run_regression.sh <role: branch|main> <app worktree> <output dir>
#
# Runs every established suite against the application code of <app worktree>
# on disposable copies (production opened read-only), from a git-ignored
# scratch directory of the main repository so the verbatim suite copies cannot
# overwrite any committed pack. Nothing runs "in place": the app root is always
# a worktree carrying its own copies of instance/alert_memory.json and the one
# backups/backup_*.enc file the /backup/ surface lists.
#
# role=branch: suites whose own no-operator calls stand in for the scheduler
# (Phase 1 writers, Phase 1 execution, CF-10 w14) are ALSO run with those calls
# declared as a system action (ADR011-SA refuses undeclared unattended calls);
# role=main runs everything exactly as established.
set -u
ROLE=$1; APP=$2; OUT=$3
MAIN="C:/Users/SIPL Server/Downloads/DSS/FinalGrid/SukoonPMS"
PY="$MAIN/venv/Scripts/python.exe"
RUN="C:/wt_adr011/verification/evidence/20260930_adr011_preprod_gate/run_with_app.py"
CF10="$MAIN/verification/evidence/20260930_cf10_completion/verify_cf10_cf11.py"
S="$MAIN/verification/_work/pp_$ROLE"
export PYTHONIOENCODING=utf-8
export SECRET_KEY=$("$PY" -c "import secrets;print(secrets.token_hex(32))")
mkdir -p "$OUT/cf10" "$S"
cp "$MAIN"/verification/evidence/20260930_cf10_completion/reg_*.py "$S/"
cd "$MAIN"
APPW=$(cygpath -w "$APP"); OUTW=$(cygpath -w "$OUT/cf10")
r() { "$PY" "$RUN" --app-root "$APP" "$@"; }

# CF-10 / CF-11 harness, one group per process
for g in cf11 corr w10 voucher w12 w13 w14 w24 na actor; do
  CF10_APP_ROOT="$APPW" CF10_OUT_DIR="$OUTW" CF10_RUN_LABEL=$ROLE "$PY" "$CF10" $g >> "$OUT/cf10_harness.log" 2>&1
done
if [ "$ROLE" = branch ]; then
  CF10_APP_ROOT="$APPW" CF10_OUT_DIR="$OUTW" CF10_RUN_LABEL=${ROLE}declared \
    "$PY" "$RUN" --app-root "$APP" --system-mechanism verification:cf10_w14 script "$CF10" w14 > "$OUT/cf10_w14_declared.log" 2>&1
fi

# Phase 1 writers A-D and Phase 1 execution
for s in A B C D; do
  r script "$S/reg_verify_writers.py" $s > "$OUT/writers_$s.log" 2>&1; mv "$S/writers_set$s.json" "$OUT/writers_set$s.json" 2>/dev/null
  if [ "$ROLE" = branch ]; then
    r --system-mechanism verification:verify_writers script "$S/reg_verify_writers.py" $s > "$OUT/writers_${s}_declared.log" 2>&1
    mv "$S/writers_set$s.json" "$OUT/writers_set${s}_declared.json" 2>/dev/null
  fi
done
r script "$S/reg_phase1_execution_verify.py" > "$OUT/phase1_execution.log" 2>&1; mv "$S/result.json" "$OUT/phase1_execution_result.json" 2>/dev/null
if [ "$ROLE" = branch ]; then
  r --system-mechanism verification:phase1_execution script "$S/reg_phase1_execution_verify.py" > "$OUT/phase1_execution_declared.log" 2>&1
  mv "$S/result.json" "$OUT/phase1_execution_declared_result.json" 2>/dev/null
fi

# Phase 2a, Q06, retention, W-20
r script "$S/reg_phase2a_verify.py" > "$OUT/phase2a.log" 2>&1; mv "$S/result.json" "$OUT/phase2a_result.json" 2>/dev/null
r script "$S/reg_verify_q06_fix.py" > "$OUT/q06.log" 2>&1; mv "$S/q06_fix_regression_result.json" "$OUT/" 2>/dev/null
r script "$S/reg_verify_retention.py" > "$OUT/retention.log" 2>&1; mv "$S/retention_test_result.json" "$OUT/" 2>/dev/null
r script "$S/reg_w20_runtime_verify.py" > "$OUT/w20.log" 2>&1; mv "$S/result.json" "$OUT/w20_result.json" 2>/dev/null

# Restore tool (tools/ of the app worktree)
(cd "$APP" && "$PY" tools/test_restore_db.py > "$OUT/test_restore_db.log" 2>&1)

# PVF layers; packs are written to the main repository's evidence folder and
# moved into $OUT/pvf afterwards (listed in $OUT/pvf_packs.txt)
ls -d verification/evidence/20260930_* > "$S/packs_before.txt"
for c in "gm-verify --tag phase1_aa6d9e91:gm" "replay-verify --tag production:replay" "inv-run --tag production:inv" "run:cross"; do
  r module verification ${c%%:*} > "$OUT/pvf_${c##*:}.log" 2>&1
done
mkdir -p "$OUT/pvf"
ls -d verification/evidence/20260930_* | comm -13 "$S/packs_before.txt" - > "$OUT/pvf_packs.txt"
while read -r p; do mv "$p" "$OUT/pvf/"; done < "$OUT/pvf_packs.txt"
echo "done $ROLE"
