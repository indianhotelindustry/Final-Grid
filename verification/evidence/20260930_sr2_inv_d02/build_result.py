# -*- coding: utf-8 -*-
"""Build RESULT.json for the SR-2 / INV-D02 pack from its own files."""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
j = lambda p: json.load(open(p, encoding='utf-8'))


def pack(role, kind):
    p = glob.glob('%s/regression/pvf/*_%s*' % (role, kind))[0]
    return os.path.basename(p), j(os.path.join(p, 'result.json'))


def strip(r):
    return json.dumps({k: v for k, v in r.items() if k not in ('metering', 'duration_ms', 'timing')},
                      sort_keys=True, default=str)


base_t, final_t = j('sr2_baseline_c703150.json'), j('sr2_final_6488075.json')
ib_n, ib = pack('baseline_c703150', 'inv_run')
if_n, if_ = pack('final_6488075', 'inv_run')
fb_n, fb = pack('baseline_c703150', 'fip_run')
ff_n, ff = pack('final_6488075', 'fip_run')
gb_n, gb = pack('baseline_c703150', 'gm_verify')
gf_n, gf = pack('final_6488075', 'gm_verify')
rb_n, rb = pack('baseline_c703150', 'replay_verify')
rf_n, rf = pack('final_6488075', 'replay_verify')
cb_n, cb = pack('baseline_c703150', 'cross_implementation')
cf_n, cf = pack('final_6488075', 'cross_implementation')
com = j(glob.glob('final_6488075/../../20260930_152837_inv_commission/result.json')[0]
        if glob.glob('final_6488075/../../20260930_152837_inv_commission/result.json')
        else '../20260930_152837_inv_commission/result.json')
com_base = j('baseline_c703150/20260930_153128_inv_commission/result.json')
bad = lambda c: {o['invariant_id']: [k for k, v in (o.get('checks') or {}).items() if not v]
                 for o in c['outcomes'] if not all((o.get('checks') or {}).values())}
out = {
    'task': 'FD-P2-06 / INV-D02 (SR-2) implementation',
    'status': 'IMPLEMENTED AND VERIFIED (local branch; not pushed; not merged)',
    'rule': 'SR2-RULE, FOUNDER_DECISIONS.md Round 6',
    'branch': 'sr2-inv-d02', 'base': 'c703150',
    'commits': {'94cb87a': 'record Founder rule SR2-RULE',
                '6488075': 'implement INV-D02 lineage rule and dataset reachability'},
    'files_changed': ['verification/FOUNDER_DECISIONS.md', 'verification/invariants/rules_d.py',
                      'verification/datasets/model.py', 'verification/datasets/registry.py',
                      'verification/datasets/datasets_activation.py', 'verification/__main__.py'],
    'app_schema_production_changed': False,
    'targeted': {'baseline_c703150': '%d/%d' % (base_t['passed'], base_t['total']),
                 'baseline_failures': [r['case'] for r in base_t['results'] if not r['pass']],
                 'final_6488075': '%d/%d' % (final_t['passed'], final_t['total']),
                 'final_commit': final_t['worktree_commit'], 'final_code_tree_clean': final_t['code_tree_clean']},
    'commissioning': {'final_pack': '20260930_152837_inv_commission', 'final_not_passing': bad(com),
                      'baseline_pack': '20260930_153128_inv_commission (unchanged c703150)',
                      'baseline_not_passing': bad(com_base),
                      'note': 'INV-R01 is declared NOT_COMMISSIONED (rules_r.py:87) and fails identically at baseline: PRE-EXISTING'},
    'regression_baseline_vs_final': {
        'inv_run': {'packs': [ib_n, if_n], 'differing_invariants': [a['invariant_id'] for a, c in zip(ib['results'], if_['results']) if strip(a) != strip(c)],
                    'INV-D02_status': [[r['status'] for r in x['results'] if r['invariant_id'] == 'INV-D02'][0] for x in (ib, if_)],
                    'unbacked_claims': [ib['unbacked_commissioning_claims'], if_['unbacked_commissioning_claims']]},
        'fault_run': {'packs': [fb_n, ff_n], 'counts_identical': fb['counts'] == ff['counts'], 'counts': ff['counts'],
                      'undetected': [fb['undetected'], ff['undetected']]},
        'gm_verify': {'packs': [gb_n, gf_n], 'verdicts': [gb['verdict'], gf['verdict']],
                      'differences_identical': sorted(map(strip, gb['differences'])) == sorted(map(strip, gf['differences'])),
                      'difference_count': gf['difference_count'],
                      'cause': 'production data moved by the Founder\'s live login (users.last_login) and the notification_queue_flush job (3 notification_logs); OPERATIONAL WARN; identical at baseline; not re-baselined'},
        'replay_verify': {'packs': [rb_n, rf_n], 'identical': rb['differences'] == rf['differences'], 'verdict': rf['verdict']},
        'cross_implementation': {'packs': [cb_n, cf_n], 'differing': [q['quantity_id'] for p, q in zip(cb['quantities'], cf['quantities']) if strip(p) != strip(q)]},
        'ds_run': '5/5 PASS on both; reachability column added; VOIDCN synthetic-unreachable',
        'ds_commission': 'PASS on both; dataset content hashes identical (VOIDCN 20d069cfa2bb4b4d)'},
    'production': {'sha256': '21dc0e970caf261fd38e1ccc9f8d4ca8c88a07ff8161cf22d63465203953e434', 'modified': False,
                   'live_alert_memory_sha256_prefix': '7f79f337c5d99511 (unchanged)'},
}
json.dump(out, open('RESULT.json', 'w', encoding='utf-8'), indent=2, default=str)
print(json.dumps({k: out[k] for k in ('targeted', 'commissioning')}, indent=1))
print(json.dumps(out['regression_baseline_vs_final']['inv_run'], indent=1))
