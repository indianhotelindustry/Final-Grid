# -*- coding: utf-8 -*-
"""Verdict-level and recorded-date comparison of the legacy suite logs, control against branch.

    python compare_logs.py <base out dir> <branch out dir> <result json>

1. verdict lines (OK / FAIL <case>) are compared in order: any status difference is listed;
2. every line that records row dates ('date': 'YYYY-MM-DD') is compared by its date list: these are
   the outcomes K-7 is EXPECTED to move; each is listed for the declared-delta table;
3. everything else (tracebacks of injected audit failures, paths, line numbers, timings) is ignored
   by construction and counted.
"""
import glob, json, os, re, sys
B, R, OUT = sys.argv[1:4]
V = re.compile(r'^(OK|FAIL)\s+(\S+)')
D = re.compile(r"'date': '(\d{4}-\d\d-\d\d)'")
CD = re.compile(r"(payment_date|charge_date|issued_date|expiry_date)\W+(\d{4}-\d\d-\d\d)")
res = {}
logs = sorted(set(os.path.relpath(f, B) for f in glob.glob(os.path.join(B, 'legacy', '*.log')) + glob.glob(os.path.join(B, 'cf10*.log'))))
for rel in logs:
    fb, fr = os.path.join(B, rel), os.path.join(R, rel)
    if not os.path.exists(fr):
        res[rel] = 'no counterpart'; continue
    a = open(fb, encoding='utf-8', errors='replace').read().splitlines()
    b = open(fr, encoding='utf-8', errors='replace').read().splitlines()
    va = [(m.group(2), m.group(1)) for l in a for m in [V.match(l)] if m]
    vb = [(m.group(2), m.group(1)) for l in b for m in [V.match(l)] if m]
    vdiff = [(x, y) for x, y in zip(va, vb) if x != y]
    da = [(re.sub(r'\s+', ' ', l)[:90], D.findall(l) + [x[1] for x in CD.findall(l)]) for l in a if D.search(l) or CD.search(l)]
    db = [(re.sub(r'\s+', ' ', l)[:90], D.findall(l) + [x[1] for x in CD.findall(l)]) for l in b if D.search(l) or CD.search(l)]
    ddiff = [{'context': x[0], 'base_dates': x[1], 'branch_dates': y[1]} for x, y in zip(da, db) if x[1] != y[1]]
    res[rel] = {'verdict_lines': (len(va), len(vb)), 'verdict_differences': vdiff,
                'date_lines': (len(da), len(db)), 'date_differences': ddiff}
    print('%-34s verdict lines %s differing %d | date lines %s differing %d' % (rel, (len(va), len(vb)), len(vdiff) + abs(len(va) - len(vb)), (len(da), len(db)), len(ddiff) + abs(len(da) - len(db))))
json.dump(res, open(OUT, 'w', encoding='utf-8'), indent=1)
