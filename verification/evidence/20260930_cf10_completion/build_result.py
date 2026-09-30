# -*- coding: utf-8 -*-
"""Build RESULT.json for this pack from the result files it contains.

Numbers in CF10_COMPLETION.md are copied from the RESULT.json this writes,
never typed by hand.

    venv\\Scripts\\python.exe verification\\evidence\\20260930_cf10_completion\\build_result.py
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)


def load(p):
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def harness(prefix, root=HERE):
    out = {}
    for f in sorted(glob.glob(os.path.join(root, 'results_%s_*.json' % prefix))):
        d = load(f)
        out[d['group']] = {
            'file': os.path.relpath(f, HERE).replace(os.sep, '/'),
            'app_commit': d.get('app_commit'), 'app_tree_clean': d.get('app_tree_clean'),
            'gates_passed': d['gates_passed'], 'gates_total': d['gates_total'],
            'verdict': d['verdict'],
            'failed_gates': [c['case'] for c in d['checks'] if c['severity'] == 'gate' and not c['pass']],
            'findings': [c['case'] for c in d['checks'] if c['severity'] != 'gate' and not c['pass']],
            'production_sha256_after': d['production_sha256_after']}
    tot = (sum(v['gates_passed'] for v in out.values()), sum(v['gates_total'] for v in out.values()))
    return {'groups': out, 'gates_passed': tot[0], 'gates_total': tot[1]}


def probe(label, root=HERE):
    p = os.path.join(root, 'probe_savepoint_%s.json' % label)
    if not os.path.exists(p):
        return None
    d = load(p)
    return {'file': os.path.relpath(p, HERE).replace(os.sep, '/'), 'app_commit': d['app_commit'],
            'app_tree_clean': d.get('app_tree_clean'), 'verdict': d['verdict'],
            'cases': {c['scenario']: c['pass'] for c in d['cases']}}


def log_line(name, pattern):
    p = os.path.join(HERE, 'regression_logs', name)
    with open(p, encoding='utf-8', errors='replace') as fh:
        s = fh.read()
    m = re.findall(pattern, s, re.M)
    return m[-1] if m else None


PVF = {'gm_verify': '20260930_024153_gm_verify_phase1_aa6d9e91',
       'replay_verify': '20260930_024158_replay_verify_production',
       'inv_run': '20260930_024200_inv_run_production',
       'cross_implementation': '20260930_024202_cross_implementation'}


def pvf():
    out = {}
    g = load(os.path.join(EV, PVF['gm_verify'], 'result.json'))
    out['gm_verify'] = {'pack': PVF['gm_verify'], 'verdict': g['verdict'],
                        'surfaces': '%d/%d' % (g['surfaces_clean'], g['surfaces_compared']),
                        'differences': g['difference_count'], 'read_only': g['read_only_verified']}
    r = load(os.path.join(EV, PVF['replay_verify'], 'result.json'))
    out['replay_verify'] = {'pack': PVF['replay_verify'], 'verdict': r['verdict'],
                            'differences': [(x['date'], x['key'], x['stored'], x['current'], x['severity'])
                                            for x in r['differences']],
                            'read_only': r['read_only_verified']}
    i = load(os.path.join(EV, PVF['inv_run'], 'result.json'))
    out['inv_run'] = {'pack': PVF['inv_run'], 'overall': i['overall'], 'counts': i['counts'],
                      'release_blocking': i['release_blocking'], 'total_writes': i['total_writes'],
                      'not_holds': {x['invariant_id']: x['status'] for x in i['results']
                                    if x['status'] != 'HOLDS'},
                      'read_only': i['read_only_verified']}
    c = load(os.path.join(EV, PVF['cross_implementation'], 'result.json'))
    out['cross_implementation'] = {'pack': PVF['cross_implementation'], 'overall': c['overall'],
                                   'counts': c['counts'],
                                   'not_agreed': {q['quantity_id']: q['verdict'] for q in c['quantities']
                                                  if q['verdict'] != 'AGREED'},
                                   'read_only': c['read_only_verified']}
    return out


result = {
    'pack': '20260930_cf10_completion',
    'start_head': 'd9fa55f', 'code_head': '61286b7',
    'harness': 'verify_cf10_cf11.py (revision 2)',
    'production_anchor': '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2',
    'green_61286b7': harness('green_61286b7'),
    'baseline_d9fa55f': harness('base_d9fa55f'),
    'baseline_683db72': harness('base_683db72'),
    'per_commit': {c: harness('commit_%s' % c, os.path.join(HERE, 'per_commit'))
                   for c in ('d34d15a', '5847920', 'c4edc7b')},
    'savepoint_probe': {'683db72': probe('base_683db72'), 'd9fa55f': probe('base_d9fa55f'),
                        'd34d15a': probe('commit_d34d15a', os.path.join(HERE, 'per_commit')),
                        '61286b7': probe('green_61286b7')},
    'regression_61286b7': {
        'verify_writers_setA': log_line('verify_writers_setA.log', r'^RESULT SET A: .*$'),
        'verify_writers_setB': log_line('verify_writers_setB.log', r'^RESULT SET B: .*$'),
        'verify_writers_setC': log_line('verify_writers_setC.log', r'^RESULT SET C: .*$'),
        'verify_writers_setD': log_line('verify_writers_setD.log', r'^RESULT SET D: .*$'),
        'phase2a_verify': log_line('phase2a_verify.log', r'^cases\s+: .*$'),
        'verify_q06_fix': '%s PASS / %s FAIL' % (
            len(re.findall(r' PASS$', open(os.path.join(HERE, 'regression_logs', 'verify_q06_fix.log'),
                                          encoding='utf-8', errors='replace').read(), re.M)),
            len(re.findall(r' FAIL$', open(os.path.join(HERE, 'regression_logs', 'verify_q06_fix.log'),
                                          encoding='utf-8', errors='replace').read(), re.M))),
        'verify_retention': log_line('verify_retention.log', r'^RESULT: .*$'),
        'phase1_execution_verify': log_line('phase1_execution_verify.log', r'^RESULT: .*$'),
        'w20_runtime_verify': log_line('w20_runtime_verify.log', r'^RESULT: .*$'),
        'tools_test_restore_db': log_line('test_restore_db.log', r'^(OK|FAILED.*)$'),
    },
    'pvf_61286b7': pvf(),
}
with open(os.path.join(HERE, 'RESULT.json'), 'w', encoding='utf-8') as fh:
    json.dump(result, fh, indent=2)
print(json.dumps({k: (v.get('gates_passed'), v.get('gates_total')) for k, v in result.items()
                  if isinstance(v, dict) and 'gates_total' in v}))
print(json.dumps(result['regression_61286b7'], indent=1))
print(json.dumps({k: v['verdict'] if v else None for k, v in result['savepoint_probe'].items()}))
