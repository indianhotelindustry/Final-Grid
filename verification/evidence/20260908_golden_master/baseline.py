"""Read-only database + financial baseline for the Golden Master (FG-P1-GOLDEN-MASTER-20260908-01).
Opens instance/pms.db with mode=ro&immutable=1 only; hashes before and after."""
import sys, os, json, hashlib, sqlite3, datetime

SP = sys.argv[1]
p = 'instance/pms.db'
h0 = hashlib.sha256(open(p, 'rb').read()).hexdigest()
c = sqlite3.connect('file:' + p + '?mode=ro&immutable=1', uri=True)
c.row_factory = sqlite3.Row


def q(s):
    return [dict(r) for r in c.execute(s).fetchall()]


def digest(t):
    h = hashlib.sha256()
    cols = [r['name'] for r in q(f'pragma table_info("{t}")')]
    h.update(('|'.join(cols) + '\n').encode())
    for row in c.execute(f'select * from "{t}" order by rowid'):
        h.update(repr(tuple(row)).encode()); h.update(b'\n')
    return h.hexdigest()


tables = [r['name'] for r in q("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
schema = q("select type,name,tbl_name,sql from sqlite_master order by type,name")
counts = {t: q(f'select count(*) n from "{t}"')[0]['n'] for t in tables}
c.execute('pragma foreign_keys=ON')
fk = [tuple(r) for r in c.execute('pragma foreign_key_check')]
db = {
    'directive': 'FG-P1-GOLDEN-MASTER-20260908-01',
    'captured_at': datetime.datetime.now().isoformat(timespec='seconds'),
    'method': 'read-only sqlite3 connection (mode=ro&immutable=1); file SHA-256 taken before and after',
    'path': os.path.abspath(p), 'sha256': h0, 'size_bytes': os.path.getsize(p),
    'integrity_check': q('pragma integrity_check')[0]['integrity_check'],
    'foreign_key_check_violations': fk,
    'schema': {
        'objects': len(schema), 'tables': len(tables),
        'indexes': sum(1 for r in schema if r['type'] == 'index'),
        'fingerprint_sha256': hashlib.sha256(repr([tuple(r.values()) for r in schema]).encode()).hexdigest(),
        'fingerprint_method': 'sha256 of repr(ordered sqlite_master rows: type,name,tbl_name,sql)',
        'schema_version_pragma': q('pragma schema_version')[0]['schema_version'],
        'user_version': q('pragma user_version')[0]['user_version'],
        'page_size': q('pragma page_size')[0]['page_size'],
        'page_count': q('pragma page_count')[0]['page_count'],
        'journal_mode': q('pragma journal_mode')[0]['journal_mode'],
        'schema_migrations': q('select max(version) v,count(*) n from schema_migrations')[0],
        'alembic_version_table': bool(q("select name from sqlite_master where name='alembic_version'")),
        'folio_id_nullable': {t: [r['notnull'] == 0 for r in q(f'pragma table_info({t})') if r['name'] == 'folio_id'][0] for t in ('payments', 'extra_charges')},
    },
    'table_inventory': tables, 'row_counts': counts, 'total_rows': sum(counts.values()),
    'content_digests': {t: digest(t) for t in tables},
    'business_date': q('select "current_date" d,is_locked,updated_at from business_date'),
    'night_audit': {'logs': q('select id,audit_date,status,run_at,completed_at,snapshot_valid,override_used,substr(snapshot_hash,1,16) snapshot_hash_prefix from night_audit_logs'),
                    'reopen_logs': counts.get('night_audit_reopen_logs')},
    'settings_identity': q("select key,value from settings where key in ('app_name','hotel_name','property_id','invoice_counter','night_audit_enabled','night_audit_time')"),
    'users': q('select id,username,role,is_active from users'),
}
json.dump(db, open(f'{SP}/DATABASE_BASELINE.json', 'w', encoding='utf-8'), indent=2, sort_keys=True, default=str)

pays = q('select * from payments order by id')
chgs = q('select * from extra_charges order by id')
d11_ids = {'payments': [1, 2, 3, 4, 5, 6], 'extra_charges': [1, 2]}
fin = {
    'directive': 'FG-P1-GOLDEN-MASTER-20260908-01',
    'captured_at': db['captured_at'], 'db_sha256': h0,
    'payments': {'count': len(pays), 'rows': pays, 'sum_amount': sum(r['amount'] for r in pays),
                 'null_folio_ids': [r['id'] for r in pays if r['folio_id'] is None],
                 'voided': sum(1 for r in pays if r['is_voided']), 'corrections': sum(1 for r in pays if r['is_correction']),
                 'by_purpose': q('select payment_purpose,count(*) n,sum(amount) s from payments group by 1')},
    'extra_charges': {'count': len(chgs), 'rows': chgs, 'sum_amount': sum(r['amount'] for r in chgs),
                      'null_folio_ids': [r['id'] for r in chgs if r['folio_id'] is None],
                      'by_charge_type': q('select charge_type,count(*) n,sum(amount) s from extra_charges group by 1'),
                      'corrections': sum(1 for r in chgs if r['is_correction'])},
    'folios': {'count': counts['folios'],
               'rows': q('select id,reservation_id,folio_letter,label,company_id,is_closed,created_at from folios order by id'),
               'attributed_payments': q('select count(*) n from payments where folio_id is not null')[0]['n'],
               'attributed_charges': q('select count(*) n from extra_charges where folio_id is not null')[0]['n']},
    'reservations': {'count': counts['reservations'],
                     'rows': q('select id,status,arrival_date,departure_date,rate_per_night,invoice_number,guest_id,room_id,created_at from reservations order by id'),
                     'reservation_to_folio': q('select r.id reservation_id,f.id folio_id,f.folio_letter from reservations r left join folios f on f.reservation_id=r.id order by r.id')},
    'invoices': {'basis': 'reservations.invoice_number IS NOT NULL (no invoices table exists)',
                 'count': q('select count(*) n from reservations where invoice_number is not null')[0]['n'],
                 'numbers': [r['invoice_number'] for r in q('select invoice_number from reservations where invoice_number is not null order by invoice_number')],
                 'invoice_counter': q("select value from settings where key='invoice_counter'")[0]['value'],
                 'tax_lines': counts['tax_lines'],
                 'tax_lines_by_source': q('select charge_source_type,count(*) n,sum(tax_amount) tax from tax_lines group by 1')},
    'checkin_records': q('select id,reservation_id,billing_responsibility,company_id,company_credit_posted,staff_user_id from checkin_records order by id'),
    'companies': counts['companies'],
    'night_rates': q('select id,reservation_id,stay_date,final_rate,is_posted,is_locked,posted_charge_id from reservation_night_rates order by id'),
    'audit_logs': {'count': counts['audit_logs'], 'by_entity_type': q('select entity_type,count(*) n from audit_logs group by 1'),
                   'financial_entities': q("select id,entity_type,entity_id,action,staff_user_id,ip_address,timestamp from audit_logs where entity_type in ('Payment','ExtraCharge','Folio','Reservation','NightAuditLog') order by id"),
                   'min_timestamp': q('select min(timestamp) t from audit_logs')[0]['t'], 'max_timestamp': q('select max(timestamp) t from audit_logs')[0]['t']},
    'other_financial_tables': {t: counts.get(t) for t in ('void_requests', 'credit_notes', 'no_show_logs', 'overpayment_logs', 'cico_charge_logs', 'ota_payouts', 'shifts', 'credit_vouchers', 'credit_voucher_redemptions', 'loyalty_transactions')},
    'null_folio_population': {'payments': [r['id'] for r in pays if r['folio_id'] is None],
                              'extra_charges': [r['id'] for r in chgs if r['folio_id'] is None],
                              'total_amount': round(sum(r['amount'] for r in pays if r['folio_id'] is None) + sum(r['amount'] for r in chgs if r['folio_id'] is None), 2)},
    'd11': {'classification': 'HISTORICAL COMMISSIONING / TEST ACTIVITY — PROTECTED',
            'ruling_factual': 'D11-F2 (2026-09-05)', 'ruling_treatment': 'FD-010 Option A (2026-09-08)',
            'architecture': 'AR-001: INV-A02 universal; these rows are a known historical exception in data, not an exemption',
            'ids': d11_ids,
            'rows': {'payments': [r for r in pays if r['id'] in d11_ids['payments']],
                     'extra_charges': [r for r in chgs if r['id'] in d11_ids['extra_charges']]},
            'total': 4776.19, 'must_not_change_in_phase_1': True},
}
fin['null_folio_population']['equals_d11_set'] = (
    fin['null_folio_population']['payments'] == d11_ids['payments']
    and fin['null_folio_population']['extra_charges'] == d11_ids['extra_charges'])
fin['aggregates'] = {'gross_payments': fin['payments']['sum_amount'], 'gross_extra_charges': fin['extra_charges']['sum_amount'],
                     'room_rent_rows': sum(1 for r in chgs if r['charge_type'] == 'room_rent'),
                     'nightly_rate_rows_posted': sum(1 for r in fin['night_rates'] if r['is_posted'])}
json.dump(fin, open(f'{SP}/FINANCIAL_BASELINE.json', 'w', encoding='utf-8'), indent=2, sort_keys=True, default=str)
c.close()
print('db sha unchanged after read:', hashlib.sha256(open(p, 'rb').read()).hexdigest() == h0)
print('tables', len(tables), 'rows', db['total_rows'], 'integrity', db['integrity_check'], 'fk violations', len(fk), 'schema fp', db['schema']['fingerprint_sha256'][:16])
print('payments', fin['payments']['count'], 'sum', fin['payments']['sum_amount'], 'charges', fin['extra_charges']['count'], 'sum', fin['extra_charges']['sum_amount'], 'folios', fin['folios']['count'], 'invoices', fin['invoices']['count'], 'audit', fin['audit_logs']['count'])
print('NULL folio population == D11 set:', fin['null_folio_population']['equals_d11_set'], fin['null_folio_population'])
print('business_date:', db['business_date'])
