import json,sys
R=json.load(open(sys.argv[1],encoding='utf-8'));T=R['tests']
print('label',R['label'],'| source unchanged',R['source_unchanged'],'| live unchanged',R.get('live_db_unchanged'),'| boot changed copy',R['boot_changed_copy'],'| sched running',R['scheduler_running_after_shutdown'])
t=T['T-01_reopen_protected_admin'];print('T-01',t['response']['status'],t['response']['flash'][:1],'row_unchanged',t['row_unchanged'],'status',t['status_after'],'valid',t['snapshot_valid_after'],'reopenlog+',t['reopen_logs_delta'],'audit+',t['audit_logs_delta'],'bd',t['business_date_before'],'->',t['business_date_after'])
print('T-04/05',T['T-04_T-05_lock_after_reopen_attempt'])
for k,v in T['T-02_run_protected_roles'].items(): print('T-02',k,v['response']['status'],(v['response']['flash'] or [''])[0][:70],'row_unchanged',v['row_unchanged'],v.get('sentinel_total_revenue_after'))
t=T['T-03_chain_protected'];print('T-03',[ (s['status'],(s['flash'] or [''])[0][:60]) for s in t['steps']]);print('   row_unchanged',t['row_unchanged'],'snap',t['snapshot_sha256_before'][:12],'->',(t['snapshot_sha256_after'] or '')[:12],'taxable',t['total_taxable_before'],'->',t['total_taxable_after'],'status',t['status_before'],'->',t['status_after'],'bd',t['business_date_after'])
t=T['T-09_role_matrix_protected']
for r in ('FrontDesk','Housekeeping','Accountant','Manager'): print('T-09',r,'run',t[r]['run']['status'],(t[r]['run']['flash'] or [''])[0][:50],'| reopen',t[r]['reopen']['status'],(t[r]['reopen']['flash'] or [''])[0][:50])
print('T-09 after',t['protected_row_after'],t['business_date_after'])
for k,v in T['T-08_ui_protected'].items(): print('T-08',k,v)
t=T['T-06_other_day_close_reopen_close']
for k in ('run_1','complete_1','reopen','run_2','complete_2'): print('T-06',k,t[k]['status'],(t[k]['flash'] or [''])[0][:70])
for k in ('after_complete_1','after_reopen','after_complete_2'): print('T-06',k,t[k])
for k in ('ui_other_closed','ui_other_closed_drift'): print('T-08b',k,t[k])
print('T-06 protected unchanged',t['protected_row_unchanged_throughout'])
print('T-07',T['T-07_run_other_closed_day'])
print('T-10a',T['T-10a_guard_function'])
