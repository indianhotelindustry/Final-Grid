"""Commission the repaired unbacked-claims cross-check.

The bug was a check that could never find evidence. Repairing it so that it
always finds evidence would be the same defect wearing the opposite sign,
so the repaired check is exercised against three evidence states and
required to give three different answers.

Production is never touched: every case points EVIDENCE_DIR at a throwaway
directory.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.getcwd())

from verification import config                      # noqa: E402
from verification.datasets import registry           # noqa: E402

KEY = 'DS-ACT-INHOUSE@1.0'
results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print('%-4s %-52s got %-9s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def with_evidence(packs):
    """Run the cross-check with EVIDENCE_DIR holding exactly *packs*."""
    root = tempfile.mkdtemp(prefix='ev_')
    try:
        for name, payload in packs.items():
            os.makedirs(os.path.join(root, name))
            if payload is not None:
                with open(os.path.join(root, name, 'result.json'), 'w') as fh:
                    json.dump(payload, fh)
        original = config.EVIDENCE_DIR
        config.EVIDENCE_DIR = root
        try:
            return registry.unbacked_commissioning_claims()
        finally:
            config.EVIDENCE_DIR = original
    finally:
        shutil.rmtree(root, ignore_errors=True)


PASSED = {'outcomes': [{'key': KEY, 'checks': {'BUILD': True,
                                               'POSITIVE': True,
                                               'PERTURBATION': True,
                                               'DISCRIMINATION': True,
                                               'ACTIVATION': True,
                                               'ISOLATION': True}}]}
FAILED = {'outcomes': [{'key': KEY, 'checks': {'BUILD': True,
                                               'POSITIVE': False,
                                               'PERTURBATION': True,
                                               'DISCRIMINATION': True,
                                               'ACTIVATION': True,
                                               'ISOLATION': True}}]}

print('== the repaired check must give three different answers ==')

# 1. No evidence at all -> the claim is unbacked.
findings, pack = with_evidence({})
check('no evidence on the machine reports the claim', len(findings), 1)

# 2. A tagged pack in which the dataset passed -> backed.
findings, pack = with_evidence(
    {'20260808_072941_ds_commission_step2_inhouse': PASSED})
check('a tagged pack that passed backs the claim', len(findings), 0)
check('  and it is the pack that was read', pack.endswith('step2_inhouse'),
      True)

# 3. A tagged pack in which the dataset FAILED -> unbacked. This is the
#    case the original suffix match could never reach, and the reason the
#    repair is not simply "make it find something".
findings, pack = with_evidence(
    {'20260808_072941_ds_commission_step2_inhouse': FAILED})
check('a tagged pack that failed reports the claim', len(findings), 1)

# 4. The most recent pack wins, not the friendliest one.
findings, pack = with_evidence({
    '20260801_000000_ds_commission_old': PASSED,
    '20260808_072941_ds_commission_step2_inhouse': FAILED,
})
check('the latest pack decides, even when an older one passed',
      len(findings), 1)
findings, pack = with_evidence({
    '20260801_000000_ds_commission_old': FAILED,
    '20260808_072941_ds_commission_step2_inhouse': PASSED,
})
check('  and the same in the other direction', len(findings), 0)

# 5. A ds_registry pack must not be mistaken for a commissioning pack.
findings, pack = with_evidence(
    {'20260808_072951_ds_registry_step2_inhouse': PASSED})
check('a ds_registry pack is not read as commissioning evidence',
      len(findings), 1)

print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
