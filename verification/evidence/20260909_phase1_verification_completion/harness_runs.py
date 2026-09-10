# -*- coding: utf-8 -*-
"""Run the existing invariant engine or the D1 parity run against a given
SQLite file (a disposable copy), writing the harness's own evidence pack.

    venv\\Scripts\\python.exe harness_runs.py inv    <source.db> <tag>
    venv\\Scripts\\python.exe harness_runs.py parity <source.db> <tag>

Both harness entry points already accept ``source``; the CLI simply does
not expose it. Nothing here changes how the engine evaluates - it makes
its own copy of *source* and proves it read-only, exactly as `inv-run`
and `run` do for production.
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
HERE = os.path.dirname(os.path.abspath(__file__))

mode, source, tag = sys.argv[1], sys.argv[2], sys.argv[3]

if mode == 'inv':
    from verification.invariants.engine import run as inv_run
    from verification.invariants import report as invreport

    run = inv_run(source=source, prove_determinism=True, quiet=True)
    text = invreport.render_run(run)
    print(text)
    evidence = invreport.write_pack(invreport.run_payload(run), text,
                                    'inv_run_%s' % tag, run.started_at)
    print('[inv] evidence pack: %s' % evidence)
    summary = {r.invariant_id: {'status': r.status, 'population': r.population,
                                'violations': r.violation_count,
                                'affected': list(r.evidence.affected_objects)[:12]}
               for r in run.results}
    out = {'tag': tag, 'source': source, 'overall': run.overall,
           'read_only_verified': run.read_only_verified,
           'determinism_proven': run.determinism_proven,
           'order_independence_proven': run.order_independence_proven,
           'business_date': run.business_date, 'evidence_pack': evidence,
           'counts': {k: sum(1 for v in summary.values() if v['status'] == k)
                      for k in ('HOLDS', 'VIOLATED', 'VACUOUS', 'NOT_APPLICABLE', 'ERROR')},
           'commissioning_gaps': list(run.commissioning_gaps),
           'invariants': summary}
elif mode == 'parity':
    from verification.runner import run as parity_run
    from verification.config import Mode
    from verification.evidence import render_report

    result, evidence = parity_run(mode=Mode.CROSS_IMPLEMENTATION, source=source, tag=tag)
    print(render_report(result))
    print('[pvf] evidence pack: %s' % evidence)
    qs = {q.quantity_id: {'verdict': q.verdict, 'divergences': len(q.divergences),
                          'implementations': {k: str(v) for k, v in sorted(q.implementations.items())},
                          'detail': getattr(q, 'detail', None)}
          for q in result.quantities}
    out = {'tag': tag, 'source': source, 'overall': result.overall,
           'evidence_pack': evidence, 'quantities': qs, 'Q14': qs.get('Q14')}
else:
    raise SystemExit('mode must be inv or parity')

with open(os.path.join(HERE, '%s_%s.json' % (mode, tag)), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=2, sort_keys=True, default=str)
print('%s_%s.json written' % (mode, tag))
