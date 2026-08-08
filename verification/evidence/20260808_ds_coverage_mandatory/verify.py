"""Commission the mandatory-coverage-ledger gate.

`ds-registry` reports "Datasets without a passing ledger : 0". That is the
answer the gate was built to give, and a gate that returned it
unconditionally would print the same line (P9). It is also the exact
failure this registry already shipped once: `unbacked_commissioning_claims`
matched pack names by suffix and could therefore never find evidence, and
nobody noticed until a dataset first declared COMMISSIONED.

So the gate is driven against fabricated evidence directories and required
to give different answers. Production is never touched and no real pack is
read.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.getcwd())

from verification import config                      # noqa: E402
from verification.datasets import registry           # noqa: E402

results = []
KEYS = sorted(d.key for d in registry.all_datasets())
ONE = KEYS[0]


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print('%-4s %-58s got %-6s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def pack(dataset, verdict):
    return {'dataset': dataset, 'ledger': {'verdict': verdict}}


def with_evidence(packs):
    """Run the gate with EVIDENCE_DIR holding exactly *packs*."""
    root = tempfile.mkdtemp(prefix='cov_')
    try:
        for name, payload in packs.items():
            os.makedirs(os.path.join(root, name))
            if payload is not None:
                with open(os.path.join(root, name, 'result.json'), 'w') as fh:
                    json.dump(payload, fh)
        original = config.EVIDENCE_DIR
        config.EVIDENCE_DIR = root
        try:
            return registry.datasets_without_coverage_ledger()
        finally:
            config.EVIDENCE_DIR = original
    finally:
        shutil.rmtree(root, ignore_errors=True)


def flagged(findings):
    return sorted(f['key'] for f in findings)


print('== the gate must distinguish five evidence states ==')
print('   datasets in the registry: %d' % len(KEYS))

# 1. No evidence at all -> every dataset is reported.
findings, _p = with_evidence({})
check('no ledgers on the machine flags every dataset',
      flagged(findings), KEYS)

# 2. A passing ledger for every dataset -> clean.
findings, _p = with_evidence({
    f'2026080{i}_00000{i}_ds_coverage_t{i}': pack(k, 'AS_DECLARED')
    for i, k in enumerate(KEYS, start=1)})
check('a passing ledger for each backs them all', flagged(findings), [])

# 3. A ledger that reported UNDECLARED_MOVEMENT does NOT back its dataset.
#    This is the case the gate exists for.
one_bad = {f'2026080{i}_00000{i}_ds_coverage_t{i}': pack(k, 'AS_DECLARED')
           for i, k in enumerate(KEYS, start=1)}
one_bad['20260809_000009_ds_coverage_bad'] = pack(ONE, 'UNDECLARED_MOVEMENT')
findings, _p = with_evidence(one_bad)
check('an UNDECLARED_MOVEMENT ledger flags its dataset',
      flagged(findings), [ONE])

# 4. Per-dataset recency, in both directions. A ledger is per-dataset, so
#    "the latest pack" would condemn every dataset but the one measured
#    last — the bug this deliberately avoids.
findings, _p = with_evidence({
    '20260801_000001_ds_coverage_old': pack(ONE, 'UNDECLARED_MOVEMENT'),
    '20260809_000002_ds_coverage_new': pack(ONE, 'AS_DECLARED'),
    **{f'2026080{i}_00000{i}_ds_coverage_t{i}': pack(k, 'AS_DECLARED')
       for i, k in enumerate(KEYS[1:], start=3)}})
check('a later passing ledger supersedes an earlier failure',
      flagged(findings), [])
findings, _p = with_evidence({
    '20260801_000001_ds_coverage_old': pack(ONE, 'AS_DECLARED'),
    '20260809_000002_ds_coverage_new': pack(ONE, 'UNDECLARED_MOVEMENT'),
    **{f'2026080{i}_00000{i}_ds_coverage_t{i}': pack(k, 'AS_DECLARED')
       for i, k in enumerate(KEYS[1:], start=3)}})
check('  and a later failure supersedes an earlier pass',
      flagged(findings), [ONE])

# 5. A ledger for one dataset does not back another.
findings, _p = with_evidence(
    {'20260809_000001_ds_coverage_only': pack(ONE, 'AS_DECLARED')})
check('one dataset\'s ledger does not cover the others',
      flagged(findings), [k for k in KEYS if k != ONE])

# 6. A commissioning pack is not mistaken for a coverage ledger. The two
#    live in the same directory and differ only by name.
findings, _p = with_evidence(
    {'20260809_000001_ds_commission_x': pack(ONE, 'AS_DECLARED')})
check('a ds_commission pack is not read as a ledger',
      flagged(findings), KEYS)

# 7. An unreadable pack is not silently treated as a pass.
findings, _p = with_evidence({'20260809_000001_ds_coverage_broken': None})
check('a pack with no result.json backs nothing', flagged(findings), KEYS)

print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
