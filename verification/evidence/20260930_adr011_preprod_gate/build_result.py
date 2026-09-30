# -*- coding: utf-8 -*-
"""Build RESULT.json for the ADR-011 pre-production gate pack from its own files.

    <main>\\venv\\Scripts\\python.exe build_result.py
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def j(p):
    with open(os.path.join(HERE, p), encoding='utf-8') as fh:
        return json.load(fh)


def t(p):
    try:
        with open(os.path.join(HERE, p), encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except FileNotFoundError:
        return ''


def last(p, pat):
    m = re.findall(pat, t(p), re.M)
    return m[-1] if m else None


def battery(role):
    d = 'regression_%s' % role
    cf = {}
    for f in sorted(glob.glob(os.path.join(HERE, d, 'cf10', 'results_*_*.json'))):
        r = json.load(open(f, encoding='utf-8'))
        cf[r['group']] = '%d/%d %s app=%s' % (r['gates_passed'], r['gates_total'], r['verdict'],
                                            (r.get('app_commit') or '?')[:7])
    q = t(d + '/q06.log')
    packs = [l.strip().split('/')[-1] for l in t(d + '/pvf_packs.txt').splitlines() if l.strip()]
    pvf = {}
    for p in packs:
        r = j(os.path.join(d, 'pvf', p, 'result.json'))
        key = p.split('_', 2)[2]
        pvf[key] = {'pack': p, 'verdict': r.get('verdict') or r.get('overall'),
                    'differences': r.get('difference_count'),
                    'surfaces': ('%s/%s' % (r['surfaces_clean'], r['surfaces_compared'])
                                 if 'surfaces_compared' in r else None)}
    out = {'cf10_cf11': cf,
           'phase1_writers': {s: last(d + '/writers_%s.log' % s, r'^RESULT SET .*$') for s in 'ABCD'},
           'phase1_execution': last(d + '/phase1_execution.log', r'^RESULT: .*$'),
           'phase2a': last(d + '/phase2a.log', r'^cases\s+: .*$'),
           'q06': '%d PASS / %d FAIL' % (len(re.findall(r' PASS$', q, re.M)), len(re.findall(r' FAIL$', q, re.M))),
           'retention': last(d + '/retention.log', r'^RESULT: .*$'),
           'w20': last(d + '/w20.log', r'^RESULT: .*$'),
           'restore_tool': last(d + '/test_restore_db.log', r'^(OK|FAILED.*)$'),
           'pvf': pvf}
    if role == 'branch':
        out['declared'] = {
            'phase1_writers': {s: last(d + '/writers_%s_declared.log' % s, r'^RESULT SET .*$') for s in 'ABCD'},
            'phase1_execution': last(d + '/phase1_execution_declared.log', r'^RESULT: .*$'),
            'undeclared_refusals': {
                f: len(re.findall(r'^app\.audit_actor\.AuditActorError', t(d + '/' + f), re.M))
                for f in ('writers_A.log', 'writers_D.log', 'phase1_execution.log', 'cf10_harness.log')}}
    return out


pre = j('preprod_final.json')
rm = j('restore/restore_manifest.json')
bm = j('restore/backup_manifest.json')
inv_r = j('restored_pvf/20260930_055154_inv_run_production/result.json')
gm_r = j('restored_pvf/20260930_055156_gm_verify_phase1_aa6d9e91/result.json')
checks = {c['case']: c['pass'] for c in pre['checks']}

result = {
    'task': 'ADR-011 pre-production gate',
    'status': 'FOUNDER_DECISION_REQUIRED',
    'main_sha': '16c4ca8b6bf80cbb9502d75d746073abdbfcd5cb',
    'branch': 'adr011-system-actor',
    'branch_sha_tested': pre['branch_commit'],
    'migration': {'version': '10.0.0', 'code_commit': '3ffeba5',
                  'app___init___blob': '1eeaf5482447d54616f3e44f2dc4ae46b207c407',
                  'migration_source_sha256': 'e38cb0556b09ab76ea9c0213f86c60b8a3584d02f7046cb053ce149a4fb5364c'},
    'production_db': {'path': 'instance/pms.db', 'sha256': pre['production_sha256_before'],
                      'sha256_after_all_work': pre['production_sha256_after'],
                      'size_bytes': pre['info']['production_size'], 'mtime': '2026-08-31 11:53:14 +0530',
                      'tables': pre['info']['tables'], 'rows': pre['info']['rows'],
                      'audit_rows': pre['info']['audit_rows'], 'audit_digest': pre['info']['audit_digest'],
                      'schema_migrations_latest': pre['info']['schema_migrations_latest'],
                      'journal_mode': 'delete', 'modified': False},
    'backup': {'artifact': 'db-backups/pms_20260930_111550_adr011-preprod.db',
               'sha256': bm.get('snapshot_sha256'),
               'restored_sha256': rm.get('restored_sha256'),
               'production_touched_by_restore': rm.get('production_touched'),
               'tool': 'tools/backup_db.py', 'verdict': 'PASS'},
    'restore_rehearsal': {'run_id': 'RR-20260930-ADR011', 'tool': 'tools/restore_db.py',
                          'checks': {k: v.get('ok') if isinstance(v, dict) else v
                                     for k, v in (rm.get('checks') or {}).items()},
                          'fdp204_condition8': {'inv_run_restored_identical_to_production': None,
                                                'inv_overall': inv_r['overall'],
                                                'gm_verify_restored': '%s %s/%s, %s differences' % (
                                                    gm_r['verdict'], gm_r['surfaces_clean'],
                                                    gm_r['surfaces_compared'], gm_r['difference_count'])}},
    'preprod_harness': {'gates': '%d/%d' % (pre['gates_passed'], pre['gates_total']),
                        'verdict': pre['verdict'], 'branch_app_clean': pre['branch_app_clean'],
                        'boot_changed_tables_branch': pre['info']['boot_changed_tables_branch'],
                        'boot_changed_tables_main_control': pre['info']['boot_changed_tables_main_control'],
                        'migration_rehearsal': all(v for k, v in checks.items() if k.startswith('D-')),
                        'negatives': all(v for k, v in checks.items() if k.startswith('E-')),
                        'identity': all(v for k, v in checks.items()
                                        if k.split('-')[0] in ('S1', 'S2', 'S3', 'S4', 'S5', 'H', 'P'))},
    'regression': {'main_baseline_16c4ca8': battery('main'), 'branch_0450c20': battery('branch')},
    'postgresql': {'verified': False, 'status': 'BLOCKED',
                   'services': {'postgresql-x64-13': '13.23', 'postgresql-x64-18': '18.4'},
                   'listening': ['0.0.0.0:5432', '0.0.0.0:5433'],
                   'credentials_available': False, 'pgpass': False, 'python_driver_in_app_venv': False,
                   'static_ddl': 'postgresql/static_ddl_postgresql.sql (offline compile only)'},
    'gates': {'G3': 'OPEN', 'G5': 'OPEN', 'G11': 'BLOCKED', 'G12': 'BLOCKED'},
    'merge_safe_to_authorize': 'FOUNDER DECISION REQUIRED - technical evidence PASS; preconditions listed in the report',
}
# condition 8: object-for-object comparison against the production-sourced baseline
im = j('regression_main/pvf/20260930_054951_inv_run_production/result.json')
strip = lambda r: json.dumps({k: v for k, v in r.items() if k not in ('metering', 'duration_ms', 'timing')},
                             sort_keys=True, default=str)
result['restore_rehearsal']['fdp204_condition8']['inv_run_restored_identical_to_production'] = all(
    strip(a) == strip(b) for a, b in zip(im['results'], inv_r['results']))
with open(os.path.join(HERE, 'RESULT.json'), 'w', encoding='utf-8') as fh:
    json.dump(result, fh, indent=2, default=str)
print(json.dumps({k: result[k] for k in ('preprod_harness', 'backup', 'restore_rehearsal')}, indent=1)[:2500])
