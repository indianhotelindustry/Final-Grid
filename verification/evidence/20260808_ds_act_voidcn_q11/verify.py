"""Did DS-ACT-VOIDCN lift Q11?

Half this dataset's justification is that it activates Q11 — the parity
quantity separating refunds from voids, VACUOUS on production because the
hotel has never voided or refunded anything.

**The coverage ledger cannot confirm it.** `coverage.py` measures D2
surfaces and D4 invariants only; D1 is a stated gap, because a coverage
delta over per-quantity parity needs a definition of "covered" that module
would have to invent. So the claim is measured here, by hand, the same way
DS-ACT-INHOUSE's D2 claim had to be.

Predicted in advance, in
evidence/20260808_ds_act_voidcn_prediction/prediction.md.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())

from verification.config import PRODUCTION_DB, PROJECT_ROOT   # noqa: E402
from verification.datasets import builder, registry           # noqa: E402
from verification.dbcopy import make_copy, production_fingerprint  # noqa: E402

results = []


def check(label, got, want):
    ok = str(got) == str(want)
    results.append(ok)
    print('%-4s %-52s got %-16s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def parity(db_path):
    proc = subprocess.run(
        [sys.executable, '-m', 'verification', '_measure',
         '--db', os.path.abspath(db_path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    marker = '---PVF-JSON---'
    if marker not in proc.stdout:
        raise RuntimeError('no result:\n' + proc.stdout[-1500:]
                           + '\n' + proc.stderr[-1500:])
    return json.loads(proc.stdout.split(marker, 1)[1].strip())


before, _size = production_fingerprint(PRODUCTION_DB)

print('== Q11 on production ==')
baseline_handle = make_copy(name='q11_baseline.db', source=PRODUCTION_DB)
prod = parity(baseline_handle.copy_path)
prod_q11 = (prod or {}).get('Q11') or {}
check('production verdict', prod_q11.get('verdict'), 'VACUOUS')

print()
print('== Q11 on DS-ACT-VOIDCN ==')
d = registry.get('DS-ACT-VOIDCN')
m = builder.build(d, slot='_q11')
try:
    ds = parity(m.db_path)
finally:
    builder.discard(m)

ds_q11 = (ds or {}).get('Q11') or {}
print('   raw entry: %s' % json.dumps(ds_q11)[:400])
check('dataset verdict is no longer VACUOUS',
      ds_q11.get('verdict') != 'VACUOUS', True)

after, _size = production_fingerprint(PRODUCTION_DB)
print()
check('production byte-identical throughout', before == after, True)
print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
