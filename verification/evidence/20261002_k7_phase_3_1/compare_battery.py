# -*- coding: utf-8 -*-
"""Compare the regression battery of the control (base) against the branch.

    python compare_battery.py <base out dir> <branch out dir> <result json>

Everything that differs at VERDICT level is listed; timing, paths, ids and column padding are
normalised away. The caller (the report) classifies each listed difference against the
declared-delta list; this script classifies nothing.
"""
import glob
import json
import os
import re
import sys

BASE, BR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
res = {'exit_codes': {}, 'pvf': {}, 'inv_statuses': {}, 'json_diffs': {}, 'notes': []}


def codes(d):
    f = os.path.join(d, 'exit_codes.txt')
    return dict(l.split(' rc=') for l in open(f).read().split('\n') if ' rc=' in l) if os.path.exists(f) else {}


cb, cr = codes(BASE), codes(BR)
for k in sorted(set(cb) | set(cr)):
    res['exit_codes'][k] = {'base': cb.get(k), 'branch': cr.get(k), 'same': cb.get(k) == cr.get(k)}


def norm(t):
    t = re.sub(r'[A-Za-z]:[\\/][^\s\'"]*', '<P>', t)
    t = re.sub(r'\d{8}_\d{6}', '<TS>', t)
    t = re.sub(r'\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(\.\d+)?', '<DT>', t)
    t = re.sub(r'\b\d+(\.\d+)?\s*ms\b', '<ms>', t)
    t = re.sub(r'(base|branch|control|k7reg|_work|pp_\w+)', '<X>', t)
    return [re.sub(r'\s+', ' ', re.sub(r'[\d.,]+', '#', l)).strip() for l in t.splitlines() if l.strip()]


for name in ('inv_run', 'ds_run', 'ds_commission', 'fault_run', 'gm_verify', 'replay_verify',
             'cross_implementation', 'inv_registry', 'inv_commission'):
    fb, fr = os.path.join(BASE, name + '.log'), os.path.join(BR, name + '.log')
    if not (os.path.exists(fb) and os.path.exists(fr)):
        res['pvf'][name] = 'missing'
        continue
    a = norm(open(fb, encoding='utf-8', errors='replace').read())
    b = norm(open(fr, encoding='utf-8', errors='replace').read())
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    res['pvf'][name] = {'lines_base': len(a), 'lines_branch': len(b), 'verdict_level_differences': len(diffs) + abs(len(a) - len(b)),
                        'sample': [[x[:140], y[:140]] for x, y in diffs[:4]]}


def inv_rows(path):
    rows = {}
    if os.path.exists(path):
        for l in open(path, encoding='utf-8', errors='replace'):
            m = re.match(r'^(INV-\w+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)', l)
            if m:
                rows[m.group(1)] = (m.group(2), m.group(3), m.group(4))   # status, population, violations
    return rows


ib, ir = inv_rows(os.path.join(BASE, 'inv_run.log')), inv_rows(os.path.join(BR, 'inv_run.log'))
res['inv_statuses'] = {k: {'base': ib.get(k), 'branch': ir.get(k)} for k in sorted(set(ib) | set(ir)) if ib.get(k) != ir.get(k)}
res['inv_statuses_compared'] = len(set(ib) | set(ir))


def flatten(o, path=''):
    out = {}
    if isinstance(o, dict):
        if 'case' in o and ('got' in o or 'pass' in o):
            out[(path + '/' + str(o['case']))] = {'expect': o.get('expect'), 'got': o.get('got'), 'pass': o.get('pass')}
        for k, v in o.items():
            if k in ('copy_path', 'copy', 'started_at', 'finished_at', 'started', 'finished', 'run_id', 'app_root',
                     'worktree', 'app_commit', 'harness', 'wall_seconds', 'elapsed', 'duration'):
                continue
            out.update(flatten(v, path + '/' + str(k) if not isinstance(v, list) else path + '/' + str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(flatten(v, path))
    return out


for sub in ('cf10', 'legacy'):
    for fb in sorted(glob.glob(os.path.join(BASE, sub, '*.json'))):
        name = os.path.basename(fb)
        fr = os.path.join(BR, sub, name.replace('_base', '_branch'))
        if not os.path.exists(fr):
            fr = os.path.join(BR, sub, name)
        if not os.path.exists(fr):
            # CF-10 files carry the run label in the name
            alt = glob.glob(os.path.join(BR, sub, name.replace('base', 'branch')))
            fr = alt[0] if alt else fr
        if not os.path.exists(fr):
            res['json_diffs'][sub + '/' + name] = 'no counterpart'
            continue
        a = flatten(json.load(open(fb, encoding='utf-8')))
        b = flatten(json.load(open(fr, encoding='utf-8')))
        d = []
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                d.append({'case': k, 'base': a.get(k), 'branch': b.get(k)})
        res['json_diffs'][sub + '/' + name] = {'cases_base': len(a), 'cases_branch': len(b), 'differences': d}
json.dump(res, open(OUT, 'w', encoding='utf-8'), indent=2, default=str)
print('exit codes differing:', [k for k, v in res['exit_codes'].items() if not v['same']])
print('PVF verdict-level differences:', {k: (v if isinstance(v, str) else v['verdict_level_differences']) for k, v in res['pvf'].items()})
print('INV status/pop/violation differences:', len(res['inv_statuses']), 'of', res['inv_statuses_compared'])
print('legacy/cf10 result files with differences:', {k: len(v['differences']) for k, v in res['json_diffs'].items() if isinstance(v, dict) and v['differences']})
