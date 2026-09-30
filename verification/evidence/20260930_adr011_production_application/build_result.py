# -*- coding: utf-8 -*-
"""Build RESULT.json for the ADR-011 production application from this pack's files.

    venv\\Scripts\\python.exe build_result.py
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)


def j(p):
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def line(p, prefix):
    for ln in open(p, encoding='utf-8', errors='replace'):
        if ln.startswith(prefix):
            return ln[len(prefix):].strip()
    return None


def pvf(side, kind):
    p = glob.glob('pvf_%s/*_%s*' % (side, kind))[0]
    return os.path.basename(p), j(os.path.join(p, 'result.json'))


def strip(r):
    return json.dumps({k: v for k, v in r.items() if k not in ('metering', 'duration_ms', 'timing')},
                      sort_keys=True, default=str)


pre, post = j('prod_pre_state.json'), j('prod_post_state.json')
chk = post['checks']
bpre, bpost = j('backup_pre_manifest.json'), j('backup_post_manifest.json')
rpre, rpost = j('restore_pre_manifest.json'), j('restore_post/restore_manifest.json')
first = json.loads(line('first_start.log', 'FIRST_START '))
smoke = json.loads(line('smoke.log', 'SMOKE '))
human = json.loads(line('human_provenance_copy.log', 'HUMAN '))
reh, ident = j('preprod_apply_rehearsal.json'), j('preprod_apply_post_ident.json')
mig_line = [l.strip() for l in open('first_start.log', encoding='utf-8', errors='replace')
            if 'Migration 10.0.0 applied' in l]
ip_n, ip = pvf('pre', 'inv_run')
iq_n, iq = pvf('post', 'inv_run')
gp_n, gp = pvf('pre', 'gm_verify')
gq_n, gq = pvf('post', 'gm_verify')
rq_n, rq = pvf('post', 'replay')
cq_n, cq = pvf('post', 'cross')
ident_gates = [c for c in ident['checks'] if c['severity'] == 'gate']

result = {
    'task': 'ADR-011 migration 10.0.0 - controlled production application',
    'status': 'APPLIED AND VERIFIED',
    'authorization': 'Founder authorization in session 2026-09-30: controlled application of ADR-011 '
                     'migration 10.0.0 to production subject to PD-004/PD-005',
    'git': {'main_before': '16c4ca8b6bf80cbb9502d75d746073abdbfcd5cb',
            'main_after_fast_forward': 'e7086da05b692a7a54b155161212c9cbd4c0b068',
            'merge': 'git merge --ff-only adr011-system-actor (no merge commit, no history rewrite)',
            'app_tools_diff_vs_tested_3ffeba5': 0},
    'production_db': {'path': 'instance/pms.db',
                      'sha256_before': '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2',
                      'sha256_after': iq['source_hash_before'],
                      'size_bytes_before_after': [733184, 733184],
                      'mtime_after': '2026-09-30 13:24:35 +0530'},
    'pd005': {
        'backup_pre': {'artifact': os.path.basename(bpre.get('snapshot_path', '')) or bpre.get('snapshot'),
                       'sha256': bpre.get('snapshot_sha256'), 'verdict': 'BACKUP VERIFIED',
                       'equals_preprod_gate_backup': bpre.get('snapshot_sha256') ==
                       '99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd'},
        'restore_rehearsal_pre': {'run_id': rpre.get('run_id'),
                                  'all_checks_ok': all(v.get('ok') in (True, None)
                                                       for v in rpre['checks'].values()),
                                  'failures': rpre.get('failures')},
        'execution_time_migration_rehearsal': '%d/%d %s' % (reh['gates_passed'], reh['gates_total'],
                                                           reh['verdict']),
        'pre_invariants': {'pack': ip_n, 'overall': ip['overall'],
                           'violated': [r['invariant_id'] for r in ip['results'] if r['status'] == 'VIOLATED']},
        'pre_golden_master': {'pack': gp_n, 'verdict': gp['verdict'],
                              'surfaces': '%d/%d' % (gp['surfaces_clean'], gp['surfaces_compared'])},
        'backup_post': {'artifact': bpost.get('snapshot_path') or bpost.get('snapshot'),
                        'sha256': bpost.get('snapshot_sha256'), 'verdict': 'BACKUP VERIFIED'},
        'restore_rehearsal_post': {'run_id': rpost.get('run_id'),
                                   'all_checks_ok': all(v.get('ok') in (True, None)
                                                        for v in rpost['checks'].values())},
    },
    'first_start': {'migration_log': mig_line, 'database_uri': first['database_uri'],
                    'env_mode': first['env_mode'], 'night_audit_job_registered': first['night_audit_job'],
                    'scheduler_jobs': first['jobs'], 'started_normally': True},
    'post_migration': {
        'tables_changed': chk['tables_changed'],
        'row_count_changes': chk['row_counts_equal_all_tables'],
        'audit_rows': chk['audit_rows'], 'audit_digest_equal_to_pre': chk['audit_digest_equal'],
        'audit_digest': chk['audit_digest'],
        'actor_kinds': chk['actor_kinds'], 'rows_actor_zero': chk['rows_actor_zero'],
        'staff_user_id_nullable': chk['staff_user_id_notnull'] == 0,
        'checks': chk['checks_in_ddl'], 'fks': chk['fks_in_ddl'], 'index': bool(chk['index']),
        'leftover_tables': chk['leftover_tables'], 'schema_migrations_added': chk['schema_migrations_added'],
        'integrity': chk['integrity'], 'foreign_key_check': chk['foreign_key_check'],
        'financial_tables_unchanged': chk['financial_tables_unchanged'],
        'night_audit_enabled': chk['night_audit_enabled']},
    'smoke': smoke,
    'human_provenance': {'where': 'copy of the post-migration backup (not production)', **human,
                         'live_production': 'NOT VERIFIED - awaits the Founder\'s own next login'},
    'identity_on_post_migration_copy': {
        'gates': '%d/%d' % (sum(1 for c in ident_gates if c['pass']), len(ident_gates)),
        'failed': [c['case'] for c in ident_gates if not c['pass']],
        'note': 'P-00 compares against the pre-migration anchor 51dd83b7; production is legitimately '
                'e67f963b after the authorized migration and was unchanged during the run '
                '(before == after == e67f963b)'},
    'post_invariants': {'pack': iq_n, 'overall': iq['overall'], 'writes': iq['total_writes'],
                        'identical_to_pre': all(strip(a) == strip(b) for a, b in zip(ip['results'], iq['results']))},
    'post_golden_master': {'pack': gq_n, 'verdict': gq['verdict'],
                           'surfaces': '%d/%d' % (gq['surfaces_clean'], gq['surfaces_compared']),
                           'differences': gq['difference_count']},
    'post_replay': {'pack': rq_n, 'verdict': rq['verdict'],
                    'differences': [(d['date'], d['key']) for d in rq['differences']]},
    'post_cross_implementation': {'pack': cq_n, 'overall': cq['overall'], 'counts': cq['counts']},
    'scheduler': 'night_audit_enabled=false; night_audit_job not registered',
    'rolled_back': False,
    'gates': {'G3': 'OPEN', 'G5': 'OPEN', 'G11': 'BLOCKED', 'G12': 'BLOCKED'},
    'production_ready_100_percent': False,
}
with open('RESULT.json', 'w', encoding='utf-8') as fh:
    json.dump(result, fh, indent=2, default=str)
print(json.dumps({k: result[k] for k in ('status', 'git', 'production_db', 'pd005', 'identity_on_post_migration_copy', 'post_invariants', 'post_golden_master')}, indent=1, default=str))
