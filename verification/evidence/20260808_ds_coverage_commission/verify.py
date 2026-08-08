"""Commission the coverage ledger.

The ledger reported AS_DECLARED on the first dataset it was pointed at.
That is the answer it was built to give, which is exactly why it is not
evidence yet: a classifier that says AS_DECLARED unconditionally would
produce the same output, and would be decoration (P9).

So the classifier is driven against synthetic snapshots and required to
give different answers. No database is touched — this is a test of
``compare()``, not of any hotel's data.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

from verification.datasets.coverage import Snapshot, compare  # noqa: E402

results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print('%-4s %-58s got %-7s want %s'
          % ('OK' if ok else 'FAIL', label, got, want))


def snap(label, surfaces, invariants):
    return Snapshot(label=label, surfaces=set(surfaces),
                    invariants=dict(invariants))


BASE = snap('production',
            {'a__x', 'b__y', 'c__z'},
            {'INV-1': ('HOLDS', 10),
             'INV-2': ('VIOLATED', 5),
             'INV-3': ('HOLDS', 3),
             'INV-4': ('VACUOUS', 0)})

print('== the ledger must distinguish four kinds of movement ==')

# 1. Nothing moves, nothing declared -> clean.
delta = compare(BASE, BASE, {}, {})
check('identical snapshots are AS_DECLARED', delta.clean, True)
check('  and report no movement', delta.added_count + delta.lost_count, 0)

# 2. An UNDECLARED ADDITION is reported. Additions are the benign
#    direction and are still not allowed to pass silently: an unexpected
#    gain means the dataset does something nobody described.
after = snap('ds', {'a__x', 'b__y', 'c__z', 'NEW__r'}, BASE.invariants)
delta = compare(BASE, after, {}, {})
check('undeclared addition is not clean', delta.clean, False)
check('  and is listed as added', delta.surfaces_added, ['NEW__r'])

# 3. An UNDECLARED LOSS is reported. This is the case the ledger exists
#    for — DS-ACT-INHOUSE lost four surfaces nobody noticed.
after = snap('ds', {'a__x', 'b__y'}, BASE.invariants)
delta = compare(BASE, after, {}, {})
check('undeclared loss is not clean', delta.clean, False)
check('  and is listed as lost', delta.surfaces_lost, ['c__z'])

# 4. A DECLARED loss is clean.
delta = compare(BASE, after, {'surfaces_lost': ('c__z',)}, {})
check('declared loss is AS_DECLARED', delta.clean, True)

# 5. Declaring a movement that does NOT happen is also a failure. A
#    dataset claiming it resolves a surface and not resolving it has made
#    a claim the ledger cannot support.
delta = compare(BASE, BASE, {'surfaces_added': ('never__happens',)}, {})
check('declared-but-absent is not clean', delta.clean, False)
check('  and is reported separately from unexpected',
      [i['target'] for i in delta.expected_but_absent], ['never__happens'])
check('  with nothing in unexpected', delta.unexpected, [])

print()
print('== population, not status, decides whether a rule is covered ==')

# A rule that still HOLDS but over nobody has stopped covering anything.
after = snap('ds', BASE.surfaces,
             {**BASE.invariants, 'INV-1': ('HOLDS', 0)})
delta = compare(BASE, after, {}, {})
check('HOLDS over 0 counts as deactivated', delta.invariants_deactivated,
      ['INV-1'])
check('  even though the status did not move',
      after.invariants['INV-1'][0], BASE.invariants['INV-1'][0])

# And the converse: a VACUOUS rule that gains a population is activated.
after = snap('ds', BASE.surfaces,
             {**BASE.invariants, 'INV-4': ('HOLDS', 7)})
delta = compare(BASE, after, {'invariants_activated': ('INV-4',)}, {})
check('a population appearing counts as activated',
      delta.invariants_activated, ['INV-4'])
check('  and declaring it is enough to be clean', delta.clean, True)

print()
print('== a status change is read against expectations.invariants ==')

# INV-2 is VIOLATED on production and HOLDS on the dataset. If the dataset
# already declared INV-2: HOLDS, that is not a surprise.
after = snap('ds', BASE.surfaces,
             {**BASE.invariants, 'INV-2': ('HOLDS', 5)})

delta = compare(BASE, after, {}, {'INV-2': 'HOLDS'})
check('a declared status change is clean', delta.clean, True)

delta = compare(BASE, after, {}, {})
check('an undeclared status change is not', delta.clean, False)
check('  and names the invariant',
      [i['target'] for i in delta.unexpected
       if i['movement'] == 'invariant_status_changed'], ['INV-2'])

delta = compare(BASE, after, {}, {'INV-2': 'VIOLATED'})
check('declaring the WRONG status does not excuse it', delta.clean, False)

print()
print('== population movement without status movement is Changed, not Lost ==')
after = snap('ds', BASE.surfaces,
             {**BASE.invariants, 'INV-3': ('HOLDS', 1)})
delta = compare(BASE, after, {}, {})
check('a shrunken population is reported as changed',
      [c['invariant'] for c in delta.invariants_changed], ['INV-3'])
check('  and is not counted as a loss', delta.invariants_deactivated, [])
check('  and does not by itself fail the ledger', delta.clean, True)

print()
print('%d checks, %d failed' % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
