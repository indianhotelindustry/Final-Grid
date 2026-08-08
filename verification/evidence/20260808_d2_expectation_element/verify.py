"""Commission the D2 expectation element.

`DS-ACT-INHOUSE` now declares seven golden-master surfaces and all seven
are MET. That is the answer the element was built to give, which is
precisely why it is not evidence yet: an element that reported MET
unconditionally would produce the same output (P9).

So the declaration is deliberately falsified, four ways, and each is
required to be caught. The dataset itself is never modified — a copy of
the declaration is made with `dataclasses.replace`.
"""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.getcwd())

from verification.datasets import builder, evaluate, registry  # noqa: E402
from verification.datasets.model import Status                 # noqa: E402

results = []


def check(label, got, want):
    ok = str(got) == str(want)
    results.append(ok)
    print('%-4s %-56s got %-14s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


d = registry.get('DS-ACT-INHOUSE')
built = builder.build(d, slot='_d2c')
assert built.ok, built.error


def outcomes_for(golden):
    """Evaluate the dataset with a substituted golden declaration."""
    variant = replace(d, expectations=replace(d.expectations, golden=golden))
    result = evaluate.evaluate(variant, built, include_faults=False)
    return {o.target: o for o in result.outcomes if o.element == 'golden'}


try:
    print('== the declaration as it stands ==')
    got = outcomes_for(d.expectations.golden)
    check('all seven surfaces MET',
          sum(1 for o in got.values() if o.status == Status.MET), 7)

    print()
    print('== falsified four ways, each must be caught ==')

    # 1. Claim a surface resolves that does not. This is the case that
    #    matters: it is the shape of a dataset claiming D2 value it has
    #    not got.
    got = outcomes_for({'groups.detail__any_group': 'RESOLVED'})
    check('claiming an UNRESOLVED surface resolves',
          got['groups.detail__any_group'].status, Status.UNMET)
    check('  and the observation says what it really is',
          got['groups.detail__any_group'].observed, 'UNRESOLVED')

    # 2. Claim a surface does not resolve when it does — the shape of a
    #    dataset that has silently gained a population.
    got = outcomes_for({'main.checkout__inhouse_reservation': 'UNRESOLVED'})
    check('claiming a RESOLVED surface does not',
          got['main.checkout__inhouse_reservation'].status, Status.UNMET)

    # 3. A surface nobody captures at all reads UNRESOLVED rather than
    #    erroring, because absence IS the unresolved state.
    got = outcomes_for({'no.such__surface': 'UNRESOLVED'})
    check('an unknown surface is UNRESOLVED, not an error',
          got['no.such__surface'].status, Status.MET)
    got = outcomes_for({'no.such__surface': 'RESOLVED'})
    check('  and claiming it resolves is caught',
          got['no.such__surface'].status, Status.UNMET)

    # 4. The element is actually swept — D2_GOLDEN must appear in the
    #    declared layers, or every expectation above would silently be
    #    NOT_RUN rather than compared. That was the original defect: the
    #    vocabulary existed and the layer was never returned.
    check('D2_GOLDEN is in declared_layers',
          'D2_GOLDEN' in d.expectations.declared_layers(), True)
    empty = replace(d.expectations, golden={})
    check('  and absent when nothing is declared',
          'D2_GOLDEN' in empty.declared_layers(), False)
finally:
    builder.discard(built)

print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
