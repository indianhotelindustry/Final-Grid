# -*- coding: utf-8 -*-
"""DQ56-R1 verification harness — Q06-H1 sealed record (2026-08-09) guard.

Runs the DQ-56 package tests (T-01 … T-10, package §7) against ONE application
root on DISPOSABLE COPIES only:

    python verify_dq56.py --app-root <worktree> --source <db to copy from>
                          --work <scratch dir> --out <result.json> --label <name>

Safety (enforced, not assumed):
- the source database is opened read-only (``mode=ro``) and copied with the
  SQLite backup API; its SHA-256 is recorded before and after and must match;
- the application is created against a copy in ``--work`` (asserted before
  any request); ``--work`` must not be inside the live application folder;
- the live ``.env`` is never loaded; outbound credentials (WhatsApp, SMTP,
  Gemini) are removed from the environment; ``SECRET_KEY`` is a throwaway;
- the in-process APScheduler is shut down immediately after ``create_app``;
- every test resets the copy from a pristine master copy;
- no snapshot JSON, guest field or page body is written to the result —
  only hashes, counts, statuses, booleans and the snapshot's
  ``total_taxable`` figure.

Run against an unchanged control worktree it records today's behaviour (RED);
against the DQ56-R1 branch it records the guarded behaviour (GREEN).
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
from datetime import date, datetime

PROTECTED = '2026-08-09'
OTHER = '2026-08-10'
SENTINEL = -12345.0
OUTBOUND_ENV = ('ULTRAMSG_TOKEN', 'ULTRAMSG_INSTANCE', 'SMTP_HOST', 'SMTP_PORT',
                'SMTP_USER', 'SMTP_PASS', 'SMTP_FROM', 'GEMINI_API_KEY',
                'GEMINI_MODEL', 'FRONTDESK_WHATSAPP', 'DATABASE_URL')


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sha_text(t):
    return hashlib.sha256((t or '').encode('utf-8')).hexdigest()


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', required=True)
    ap.add_argument('--live-root', required=True,
                    help='live application folder; asserted never used as DB')
    a = ap.parse_args()

    app_root = os.path.abspath(a.app_root)
    work = os.path.abspath(a.work)
    live_root = os.path.abspath(a.live_root)
    live_db = os.path.join(live_root, 'instance', 'pms.db')
    assert not work.lower().startswith(live_root.lower()), 'work dir inside live folder'
    assert not app_root.lower().startswith(live_root.lower()), 'app root is the live folder'
    os.makedirs(work, exist_ok=True)

    R = {'label': a.label, 'app_root': app_root, 'started_utc': datetime.utcnow().isoformat(),
         'source': a.source, 'tests': {}, 'checks': []}
    R['source_sha256_before'] = sha_file(a.source)
    if os.path.exists(live_db):
        R['live_db_sha256_before'] = sha_file(live_db)

    master = os.path.join(work, 'master.db')
    testdb = os.path.join(work, 'test.db')
    for p in (master, testdb):
        if os.path.exists(p):
            os.remove(p)
    src = sqlite3.connect('file:%s?mode=ro' % a.source.replace('\\', '/'), uri=True)
    dst = sqlite3.connect(master)
    src.backup(dst)
    dst.close()
    src.close()
    R['source_sha256_after_copy'] = sha_file(a.source)
    assert R['source_sha256_after_copy'] == R['source_sha256_before'], 'source changed by copy'
    R['master_copy_sha256'] = sha_file(master)
    shutil.copyfile(master, testdb)

    # ── environment: no live .env, no outbound credentials ────────────────
    for k in OUTBOUND_ENV:
        os.environ.pop(k, None)
    os.environ['SECRET_KEY'] = secrets.token_hex(32)
    os.environ['FLASK_ENV'] = 'production'
    os.environ['DATABASE_URL'] = 'sqlite:///' + testdb.replace('\\', '/')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

    os.chdir(app_root)
    sys.path.insert(0, app_root)
    import app as app_pkg
    assert os.path.abspath(app_pkg.__file__).startswith(os.path.join(app_root, 'app')), app_pkg.__file__
    flask_app = app_pkg.create_app()
    from app.services import scheduler
    try:
        scheduler.shutdown(wait=False)
    except Exception as e:                                       # noqa: BLE001
        R['checks'].append('scheduler shutdown: %r' % e)
    R['scheduler_running_after_shutdown'] = bool(getattr(scheduler, 'running', False))
    uri = flask_app.config['SQLALCHEMY_DATABASE_URI']
    assert uri.replace('\\', '/').lower().endswith(testdb.replace('\\', '/').lower()), uri
    assert 'instance/pms.db' not in uri.replace('\\', '/').lower(), uri
    R['db_uri_is_copy'] = True
    R['boot_changed_copy'] = sha_file(testdb) != R['master_copy_sha256']
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['TESTING'] = True

    from app.models import db, User, NightAuditLog
    from app import services as S

    run_url = '/reports/night-audit/run'
    reopen_url = '/reports/night-audit/reopen'
    complete_url = '/reports/night-audit/complete'

    def reset(perturb=None):
        with flask_app.app_context():
            db.session.remove()
            db.engine.dispose()
        shutil.copyfile(master, testdb)
        ids = {}
        with flask_app.app_context():
            for role in ('Admin', 'Manager', 'Accountant', 'FrontDesk', 'Housekeeping'):
                u = User(username='dq56_' + role.lower(), full_name='DQ56 test ' + role,
                         role=role, is_active=True)
                u.set_password(secrets.token_hex(16))
                db.session.add(u)
                db.session.flush()
                ids[role] = u.id
            db.session.commit()
            db.session.remove()
            db.engine.dispose()
        if perturb:
            c = sqlite3.connect(testdb)
            c.execute(perturb[0], perturb[1])
            c.commit()
            c.close()
        return ids

    def state():
        with flask_app.app_context():
            db.session.remove()
            db.engine.dispose()
        c = sqlite3.connect(testdb)
        c.row_factory = sqlite3.Row
        out = {}
        for d in (PROTECTED, OTHER):
            rows = [dict(r) for r in c.execute(
                'SELECT * FROM night_audit_logs WHERE audit_date = ? ORDER BY id', (d,))]
            summ = []
            for r in rows:
                sj = r.pop('snapshot_json', None)
                tt = None
                if sj:
                    try:
                        tt = find_key(json.loads(sj), 'total_taxable')
                    except ValueError:
                        tt = 'unparseable'
                r['snapshot_json_sha256'] = sha_text(sj) if sj else None
                r['snapshot_total_taxable'] = tt
                summ.append(r)
            out[d] = {'rows': summ,
                      'row_sha256': sha_text(json.dumps(summ, sort_keys=True, default=str))}
        # "current_date" must be quoted: unquoted it is SQLite's CURRENT_DATE keyword
        # (today's UTC date), not the column (harness defect found in RED v1).
        out['business_date'] = c.execute('SELECT "current_date" FROM business_date').fetchone()[0]
        for t in ('night_audit_logs', 'night_audit_reopen_logs', 'audit_logs', 'payments',
                  'extra_charges'):
            out['count_' + t] = c.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
        c.close()
        return out

    def client_as(uid):
        cl = flask_app.test_client()
        with cl.session_transaction() as s:
            s['_user_id'] = str(uid)
            s['_fresh'] = True
        return cl

    def post(cl, url, data):
        r = cl.post(url, data=data, follow_redirects=False)
        with cl.session_transaction() as s:
            fl = [m for _, m in s.get('_flashes', [])]
            s.pop('_flashes', None)
        return {'status': r.status_code, 'flash': fl}

    def page_flags(cl, url):
        r = cl.get(url)
        html = r.get_data(as_text=True)
        return {'status': r.status_code,
                'run_form': ('action="%s"' % run_url) in html,
                'reopen_form': ('action="%s"' % reopen_url) in html,
                'reopen_modal': 'id="reopenModal"' in html,
                'reopen_button': 'data-bs-target="#reopenModal"' in html,
                'protected_note': 'q06h1-protected-note' in html,
                'drift_banner': 'Snapshot captured under an older app version' in html}

    def locked(d):
        with flask_app.app_context():
            r = S.is_date_locked(date.fromisoformat(d))
            db.session.remove()
            return r

    def record(name, data):
        R['tests'][name] = data
        print('[%s] %s done' % (a.label, name), flush=True)

    # ── T-01 / T-04 / T-05 — Admin reopen of the protected date ───────────
    ids = reset()
    before = state()
    resp = post(client_as(ids['Admin']), reopen_url,
                {'audit_date': PROTECTED, 'reason': 'DQ56 test T-01'})
    after = state()
    record('T-01_reopen_protected_admin', {
        'response': resp, 'before': before, 'after': after,
        'row_unchanged': before[PROTECTED]['row_sha256'] == after[PROTECTED]['row_sha256'],
        'status_after': [r['status'] for r in after[PROTECTED]['rows']],
        'snapshot_valid_after': [r['snapshot_valid'] for r in after[PROTECTED]['rows']],
        'reopen_logs_delta': after['count_night_audit_reopen_logs'] - before['count_night_audit_reopen_logs'],
        'audit_logs_delta': after['count_audit_logs'] - before['count_audit_logs'],
        'business_date_before': before['business_date'],
        'business_date_after': after['business_date']})
    record('T-04_T-05_lock_after_reopen_attempt', {
        'is_date_locked_protected': locked(PROTECTED),
        'business_date': state()['business_date']})

    # ── T-02 — Run of the protected date by Admin / Manager / Accountant ──
    t02 = {}
    for role in ('Admin', 'Manager', 'Accountant'):
        ids = reset(("UPDATE night_audit_logs SET total_revenue = ? WHERE audit_date = ?",
                     (SENTINEL, PROTECTED)))
        before = state()
        resp = post(client_as(ids[role]), run_url, {'audit_date': PROTECTED})
        after = state()
        t02[role] = {'response': resp,
                     'row_unchanged': before[PROTECTED]['row_sha256'] == after[PROTECTED]['row_sha256'],
                     'sentinel_total_revenue_after': [r['total_revenue'] for r in after[PROTECTED]['rows']],
                     'status_after': [r['status'] for r in after[PROTECTED]['rows']]}
    # unperturbed Run by Admin as well (values may coincide; row hash shows any write that changed bytes)
    ids = reset()
    before = state()
    resp = post(client_as(ids['Admin']), run_url, {'audit_date': PROTECTED})
    after = state()
    t02['Admin_unperturbed'] = {'response': resp,
                                'row_unchanged': before[PROTECTED]['row_sha256'] == after[PROTECTED]['row_sha256']}
    record('T-02_run_protected_roles', t02)

    # ── T-03 — Reopen → Run → Complete chain on the protected date ────────
    ids = reset()
    before = state()
    cl = client_as(ids['Admin'])
    steps = [post(cl, reopen_url, {'audit_date': PROTECTED, 'reason': 'DQ56 test T-03'}),
             post(cl, run_url, {'audit_date': PROTECTED}),
             post(cl, complete_url, {'audit_date': PROTECTED, 'override_reason': 'DQ56 test T-03'})]
    after = state()
    b0 = before[PROTECTED]['rows'][0]
    a0 = after[PROTECTED]['rows'][0]
    record('T-03_chain_protected', {
        'steps': steps,
        'row_unchanged': before[PROTECTED]['row_sha256'] == after[PROTECTED]['row_sha256'],
        'snapshot_sha256_before': b0['snapshot_json_sha256'],
        'snapshot_sha256_after': a0['snapshot_json_sha256'],
        'snapshot_hash_column_before': b0.get('snapshot_hash'),
        'snapshot_hash_column_after': a0.get('snapshot_hash'),
        'total_taxable_before': b0['snapshot_total_taxable'],
        'total_taxable_after': a0['snapshot_total_taxable'],
        'status_before': b0['status'], 'status_after': a0['status'],
        'business_date_after': after['business_date']})

    # ── T-09 — role matrix on the protected date ─────────────────────────
    ids = reset()
    t09 = {}
    for role in ('FrontDesk', 'Housekeeping', 'Accountant', 'Manager'):
        cl = client_as(ids[role])
        t09[role] = {'run': post(cl, run_url, {'audit_date': PROTECTED}),
                     'reopen': post(cl, reopen_url, {'audit_date': PROTECTED, 'reason': 'DQ56 T-09'})}
    after = state()
    t09['protected_row_after'] = {'status': [r['status'] for r in after[PROTECTED]['rows']],
                                  'snapshot_valid': [r['snapshot_valid'] for r in after[PROTECTED]['rows']]}
    t09['business_date_after'] = after['business_date']
    record('T-09_role_matrix_protected', t09)

    # ── T-08 — UI on the protected date (normal and version-drift) ───────
    ids = reset()
    before = state()
    cl = client_as(ids['Admin'])
    panel = '/night-audit?date=%s' % PROTECTED
    report = '/reports/night-audit?date=%s&format=dq56-deprecated' % PROTECTED
    ui = {'panel': page_flags(cl, panel), 'report': page_flags(cl, report)}
    saved = app_pkg.APP_VERSION
    app_pkg.APP_VERSION = saved + '-dq56drift'
    ui['panel_drift'] = page_flags(cl, panel)
    ui['report_drift'] = page_flags(cl, report)
    app_pkg.APP_VERSION = saved
    ui['protected_row_unchanged_by_gets'] = (before[PROTECTED]['row_sha256'] ==
                                             state()[PROTECTED]['row_sha256'])
    record('T-08_ui_protected', ui)

    # ── T-06 / T-07 / T-08b — non-protected day keeps today's behaviour ──
    ids = reset()
    cl = client_as(ids['Admin'])
    seq = {}
    seq['run_1'] = post(cl, run_url, {'audit_date': OTHER})
    seq['complete_1'] = post(cl, complete_url, {'audit_date': OTHER, 'override_reason': 'DQ56 test T-06'})
    s1 = state()
    seq['after_complete_1'] = {'status': [r['status'] for r in s1[OTHER]['rows']],
                               'business_date': s1['business_date']}
    seq['ui_other_closed'] = {'panel': page_flags(cl, '/night-audit?date=%s' % OTHER),
                              'report': page_flags(cl, '/reports/night-audit?date=%s&format=dq56-deprecated' % OTHER)}
    saved = app_pkg.APP_VERSION
    app_pkg.APP_VERSION = saved + '-dq56drift'
    seq['ui_other_closed_drift'] = {'panel': page_flags(cl, '/night-audit?date=%s' % OTHER),
                                    'report': page_flags(cl, '/reports/night-audit?date=%s&format=dq56-deprecated' % OTHER)}
    app_pkg.APP_VERSION = saved
    seq['reopen'] = post(cl, reopen_url, {'audit_date': OTHER, 'reason': 'DQ56 test T-06'})
    s2 = state()
    seq['after_reopen'] = {'status': [r['status'] for r in s2[OTHER]['rows']],
                           'snapshot_valid': [r['snapshot_valid'] for r in s2[OTHER]['rows']],
                           'business_date': s2['business_date']}
    seq['run_2'] = post(cl, run_url, {'audit_date': OTHER})
    seq['complete_2'] = post(cl, complete_url, {'audit_date': OTHER, 'override_reason': 'DQ56 test T-06 b'})
    s3 = state()
    seq['after_complete_2'] = {'status': [r['status'] for r in s3[OTHER]['rows']],
                               'snapshot_valid': [r['snapshot_valid'] for r in s3[OTHER]['rows']],
                               'business_date': s3['business_date']}
    seq['protected_row_unchanged_throughout'] = (s3[PROTECTED]['row_sha256'] ==
                                                 state()[PROTECTED]['row_sha256'])
    record('T-06_other_day_close_reopen_close', seq)

    c = sqlite3.connect(testdb)
    c.execute('UPDATE night_audit_logs SET total_revenue = ? WHERE audit_date = ?', (SENTINEL, OTHER))
    c.commit()
    c.close()
    resp = post(cl, run_url, {'audit_date': OTHER})
    s4 = state()
    record('T-07_run_other_closed_day', {
        'response': resp,
        'status_after': [r['status'] for r in s4[OTHER]['rows']],
        'sentinel_overwritten': all(r['total_revenue'] != SENTINEL for r in s4[OTHER]['rows'])})

    # ── T-10a — guard function unit checks (branch only) ─────────────────
    try:
        from app.reports import is_q06h1_protected_date as f
        R['tests']['T-10a_guard_function'] = {
            'date_2026_08_09': f(date(2026, 8, 9)),
            'datetime_2026_08_09': f(datetime(2026, 8, 9, 23, 59)),
            'str_2026_08_09': f('2026-08-09'),
            'date_2026_08_10': f(date(2026, 8, 10)),
            'date_2026_08_08': f(date(2026, 8, 8)),
            'none': f(None), 'bad_str': f('not-a-date'), 'empty': f('')}
    except ImportError:
        R['tests']['T-10a_guard_function'] = 'not present (control)'

    R['source_sha256_after'] = sha_file(a.source)
    R['source_unchanged'] = R['source_sha256_after'] == R['source_sha256_before']
    if os.path.exists(live_db):
        R['live_db_sha256_after'] = sha_file(live_db)
        R['live_db_unchanged'] = R['live_db_sha256_after'] == R['live_db_sha256_before']
    R['finished_utc'] = datetime.utcnow().isoformat()
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(R, f, indent=2, sort_keys=True, default=str)
    print('[%s] written %s' % (a.label, a.out), flush=True)


if __name__ == '__main__':
    main()
