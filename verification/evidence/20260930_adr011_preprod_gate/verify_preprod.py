# -*- coding: utf-8 -*-
"""ADR-011 pre-production gate - isolated rehearsal on the RESTORED copy.

Nothing here touches production: ``instance/pms.db`` is only hashed and read
(``mode=ro``). Every database written below is a copy of the file restored
by ``tools/restore_db.py`` (run RR-20260930-ADR011) in an isolated folder
outside the repository. Application code is imported from git worktrees:
the branch (``adr011-system-actor``) and, for control boots, unchanged
``main``. Each application boot runs in its own subprocess.

    <main>\\venv\\Scripts\\python.exe verify_preprod.py --restored <restored.db> --iso <dir> --main-wt <dir> [phase ...]

Phases: char (B), mig (D 1-12), ident (D 13-22), neg (E)
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')
ANCHOR = '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2'
ORIG_COLS = ('id', 'entity_type', 'entity_id', 'action', 'before_state', 'after_state',
             'staff_user_id', 'ip_address', 'timestamp')
FINANCIAL = ('payments', 'extra_charges', 'folios', 'invoices', 'tax_lines', 'credit_vouchers',
             'credit_voucher_redemptions', 'night_audit_logs', 'reservations', 'credit_notes',
             'cico_charge_logs', 'business_date', 'shifts', 'users')

results = []


def check(case, area, what, expect, got, note='', gate=True):
    ok = expect == got
    results.append({'case': case, 'area': area, 'what': what, 'expect': repr(expect),
                    'got': repr(got), 'pass': ok, 'severity': 'gate' if gate else 'finding',
                    'note': note})
    print('%-5s %-18s %-70s %s' % ('OK' if ok else ('FAIL' if gate else 'NOTE'), case, what[:70],
                                   ('' if ok else 'expect=%r got=%r ' % (expect, got))[:300] + note[:160]))
    return ok


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def ro(path):
    return sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)


def table_digests(path):
    """{table: (rows, sha256 over rows ordered by rowid)} for every table."""
    c = ro(path)
    out = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        h = hashlib.sha256()
        n = 0
        for r in c.execute('SELECT * FROM "%s" ORDER BY rowid' % t):
            h.update(json.dumps(list(r), default=str).encode() + b'\n')
            n += 1
        out[t] = (n, h.hexdigest())
    c.close()
    return out


def audit_state(path):
    """(rows, digest of the nine pre-ADR011 columns, audit_logs DDL)."""
    c = ro(path)
    h = hashlib.sha256()
    rows = c.execute('SELECT %s FROM audit_logs ORDER BY id' % ', '.join(ORIG_COLS)).fetchall()
    for r in rows:
        h.update(json.dumps(list(r), default=str, sort_keys=True).encode() + b'\n')
    ddl = c.execute("SELECT sql FROM sqlite_master WHERE name='audit_logs'").fetchone()[0]
    c.close()
    return len(rows), h.hexdigest(), ddl


def backup_copy(src, dst):
    for s in ('', '-journal', '-wal', '-shm'):
        if os.path.exists(dst + s):
            os.remove(dst + s)
    a, b = ro(src), sqlite3.connect(dst)
    a.backup(b)
    a.close()
    b.close()
    return dst


def boot(app_root, db, pre='', env_extra=None):
    """Boot the application of *app_root* against *db* in a fresh process."""
    code = '\n'.join([
        'import os, sys',
        'sys.path.insert(0, %r)' % app_root,
        'from dotenv import load_dotenv; load_dotenv(%r, override=False)' % os.path.join(MAIN, '.env'),
        'os.environ["DATABASE_URL"] = %r' % ('sqlite:///' + db.replace('\\', '/')),
        'os.environ["FLASK_ENV"] = "production"',
        pre,
        'from app import create_app',
        'app = create_app()',
        'from app.services import scheduler',
        'print("JOB", scheduler.get_job("night_audit_job"))',
        'scheduler.shutdown(wait=False) if scheduler.running else None',
    ])
    env = dict(os.environ, PYTHONIOENCODING='utf-8', **(env_extra or {}))
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


# ===========================================================================
def phase_char(a):
    print('=== B  characterisation: production vs restored')
    ph0 = sha(PROD)
    check('B-00', 'production', 'production SHA-256 == anchor (read-only)', ANCHOR, ph0)
    pd, rd = table_digests(PROD), table_digests(a.restored)
    check('B-01', 'restore', 'restored: same tables as production', sorted(pd), sorted(rd))
    check('B-02', 'restore', 'restored: every table row count and content digest == production',
          pd, rd, '%d tables, %d rows' % (len(pd), sum(v[0] for v in pd.values())))
    pa, ra = audit_state(PROD), audit_state(a.restored)
    check('B-03', 'restore', 'audit_logs: 23 rows; digest and DDL == production', (23, pa), (ra[0], ra))
    c = ro(a.restored)
    users = c.execute('SELECT id, role, is_active FROM users ORDER BY id').fetchall()
    actors = c.execute('SELECT staff_user_id, COUNT(*) FROM audit_logs GROUP BY 1').fetchall()
    migs = [r[0] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version')]
    integ = c.execute('PRAGMA integrity_check').fetchone()[0]
    c.close()
    check('B-04', 'restore', 'restored: users, audit actors, integrity, 10.0.0 not applied',
          ([(1, 'Admin', 1)], [(1, 23)], 'ok', False),
          (users, actors, integ, '10.0.0' in migs), 'schema_migrations max=%s' % migs[-1])
    return {'production_sha256': ph0, 'production_size': os.path.getsize(PROD),
            'restored_sha256': sha(a.restored), 'tables': len(pd),
            'rows': sum(v[0] for v in pd.values()), 'audit_rows': pa[0], 'audit_digest': pa[1],
            'audit_ddl_before': pa[2], 'users': users, 'audit_actors': actors,
            'schema_migrations_latest': migs[-1]}


# ===========================================================================
def phase_mig(a):
    print('=== D 1-12  migration rehearsal on copies of the restored file')
    pre = table_digests(a.restored)
    pre_audit = audit_state(a.restored)
    mb = backup_copy(a.restored, os.path.join(a.iso, 'mig_branch.db'))
    mm = backup_copy(a.restored, os.path.join(a.iso, 'mig_main_control.db'))
    rc_b, out_b = boot(WT, mb)
    rc_m, out_m = boot(a.main_wt, mm)
    check('D-01', 'migration', 'branch boot on restored copy completes; main control boot completes',
          (0, 0), (rc_b, rc_m), (out_b if rc_b else out_m)[-300:] if (rc_b or rc_m) else '')
    post_b, post_m = table_digests(mb), table_digests(mm)
    c = sqlite3.connect(mb)
    ver = c.execute("SELECT description FROM schema_migrations WHERE version='10.0.0'").fetchall()
    info = {r[1]: r for r in c.execute('PRAGMA table_info(audit_logs)')}
    kinds = c.execute('SELECT actor_kind, actor_mechanism, actor_role, actor_shift_id, COUNT(*) '
                      'FROM audit_logs GROUP BY 1,2,3,4').fetchall()
    zero = c.execute('SELECT COUNT(*) FROM audit_logs WHERE staff_user_id = 0').fetchone()[0]
    integ = c.execute('PRAGMA integrity_check').fetchone()[0]
    c.execute('PRAGMA foreign_keys=ON')
    fkv = c.execute('PRAGMA foreign_key_check').fetchall()
    idx = c.execute("SELECT sql FROM sqlite_master WHERE name='idx_audit_entity'").fetchone()
    leftovers = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%adr011%'").fetchone()[0]
    c.close()
    post_audit = audit_state(mb)
    check('D-02', 'migration', 'migration 10.0.0 recorded (branch); not on the main control',
          (1, False), (len(ver), '10.0.0' in [r for r in _versions(mm)]))
    check('D-04', 'migration', 'all 23 historical audit rows present', 23, post_audit[0])
    check('D-05/06', 'migration', 'carried-over columns: digest identical to the restored source',
          pre_audit[1], post_audit[1])
    check('D-07/08', 'migration', 'actor_kind: all historical rows HUMAN (user 1), no mechanism/role/shift',
          [('HUMAN', None, None, None, 23)], kinds, 'historical rows are carried, not reconstructed')
    check('D-09', 'migration', 'no SYSTEM rows exist before any system action', 0,
          sum(k[4] for k in kinds if k[0] == 'SYSTEM'))
    check('D-10', 'migration', 'no audit row names users.id 0', 0, zero)
    check('D-11', 'migration', 'constraints: staff_user_id nullable; 3 CHECKs; FK users + shifts; index',
          (0, 3, 2, True),
          (info['staff_user_id'][3],
           sum(post_audit[2].count(x) for x in ('ck_audit_actor_kind', 'ck_audit_actor_identity',
                                                'ck_audit_actor_not_zero')),
           post_audit[2].count('REFERENCES'), idx is not None))
    check('D-11b', 'migration', 'integrity_check ok; foreign_key_check empty (FK on); no leftover table',
          ('ok', [], 0), (integ, fkv, leftovers))
    changed_b = sorted(t for t in pre if post_b.get(t) != pre[t])
    changed_m = sorted(t for t in pre if post_m.get(t) != pre[t])
    differ = sorted(t for t in set(post_b) | set(post_m)
                    if post_b.get(t) != post_m.get(t) and t not in ('audit_logs', 'schema_migrations'))
    check('D-12a', 'migration', 'tables changed by boot: branch == main control + audit_logs/schema_migrations',
          sorted(set(changed_m) | {'audit_logs', 'schema_migrations'}),
          sorted(set(changed_b) | {'audit_logs', 'schema_migrations'}),
          'branch changed=%s; main changed=%s' % (changed_b, changed_m))
    check('D-12b', 'migration', 'after boot, every other table identical between branch and main control',
          [], differ)
    fin = [t for t in FINANCIAL if t in pre]
    check('D-12c', 'migration', 'financial tables identical to the restored source after migration',
          {t: pre[t] for t in fin}, {t: post_b[t] for t in fin}, ', '.join(fin))
    # Idempotence: boot twice more; nothing may change.
    snap = table_digests(mb)
    for i in (2, 3):
        rc, out = boot(WT, mb)
        check('D-03.%d' % i, 'migration', 'repeat boot %d: completes; every table unchanged' % i,
              (0, snap), (rc, table_digests(mb)), out[-200:] if rc else '')
    check('D-JOB', 'scheduler', 'night_audit_job not registered after boot (setting false)', True,
          'JOB None' in out_b)
    return {'mig_branch_sha256': sha(mb), 'boot_changed_tables_branch': changed_b,
            'boot_changed_tables_main_control': changed_m}


def _versions(db):
    c = ro(db)
    v = [r[0] for r in c.execute('SELECT version FROM schema_migrations')]
    c.close()
    return v


# ===========================================================================
def _impl_module(a):
    os.environ['CF10_APP_ROOT'] = WT
    spec = importlib.util.spec_from_file_location(
        'adr011impl', os.path.join(WT, 'verification', 'evidence', '20260930_adr011_implementation',
                                   'verify_adr011_impl.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from verification.dbcopy import make_copy
    mod.H.make_copy = functools.partial(make_copy, source=a.restored)   # restored lineage
    mod.H.results = results
    mod.results = results
    mod.check = check
    mod.H.check = check
    return mod


def phase_ident(a, mod=None):
    print('=== D 13-22  identity on copies of the restored file (branch app)')
    mod = mod or _impl_module(a)
    E = mod.H.Env('preprod_ident')
    check('D-13.src', 'isolation', 'working copy made from the restored file, not production',
          os.path.normcase(a.restored), os.path.normcase(E.handle.source_path))
    for g in ('sys', 'human', 'prov'):
        getattr(mod, 'group_' + g)(E)
    src_after = mod.H.assert_production_untouched(E.handle)
    check('D-13.srcro', 'isolation', 'restored source unchanged by the run', E.handle.source_hash_before,
          src_after)
    return mod


# ===========================================================================
def audit_snapshot(E):
    with E.app.app_context():
        rows = E.db.session.execute(E.db.text(
            'SELECT id, entity_type, entity_id, action, staff_user_id, actor_kind, actor_mechanism '
            'FROM audit_logs ORDER BY id')).fetchall()
    return len(rows), hashlib.sha256(json.dumps([list(r) for r in rows], default=str).encode()).hexdigest()


def phase_neg(a, mod=None):
    print('=== E  negative testing (financial rolled back AND audit unchanged)')
    mod = mod or _impl_module(a)
    E = mod.H.Env('preprod_neg')
    m, db = E.m, E.db
    import app.services as svc
    from app.audit_actor import system_action, AuditActorError
    with E.app.app_context():
        for k, v in (('noshow_fee_enabled', 'true'), ('noshow_fee_mode', 'fixed'),
                     ('noshow_fee_amount', '500')):
            row = db.session.query(m.Settings).filter_by(key=k).first()
            if row is None:
                db.session.add(m.Settings(key=k, value=v))
            else:
                row.value = v
        db.session.commit()
    sched = lambda: svc.scheduled_night_audit(E.app)
    d, ih, nsr = mod.fixtures(E, 'neg')

    def attempt(case, what, fn, cm_list):
        fin0, aud0 = mod.day(E, d), audit_snapshot(E)
        from contextlib import ExitStack
        with ExitStack() as st:
            for cm in cm_list:
                st.enter_context(cm)
            err = mod.run(fn)
        check(case, 'negative', what + ': refused; financial rolled back; audit unchanged',
              (True, fin0, aud0), (err is not None, mod.day(E, d), audit_snapshot(E)), str(err)[:160])

    attempt('E-01', 'invalid human user (FK on, users.id 999999)', sched,
            [mod.FK(E), mod.ForcedActor(999999)])
    attempt('E-02', 'user 0 as actor (FK off)', sched, [mod.ForcedActor(0)])
    attempt('E-06', 'unknown actor: no operator, no declared mechanism',
            lambda: svc.run_night_audit(E.app), [])
    for kind in ('F1', 'F2'):
        attempt('E-07-%s' % kind, 'failed audit write %s (room rent)' % kind, sched,
                [E.fault(kind, only=lambda et, ac: et == 'ExtraCharge')])
    # Rows written around the application, and via the ORM without an actor.
    aud0 = audit_snapshot(E)
    raw_cases = (('E-03', 'HUMAN without user', None, 'HUMAN', None),
                 ('E-04', 'SYSTEM with a user', E.admin_id, 'SYSTEM', 'x'),
                 ('E-05', 'SYSTEM without mechanism', None, 'SYSTEM', None),
                 ('E-02r', 'user 0 (raw SQL)', 0, 'HUMAN', None))
    with E.app.app_context():
        raw = db.engine.raw_connection()
        try:
            cur = raw.cursor()
            for case, what, uid, kind, mech in raw_cases:
                try:
                    cur.execute("INSERT INTO audit_logs (entity_type, entity_id, action, staff_user_id, "
                                "actor_kind, actor_mechanism) VALUES ('Neg', 1, 'raw', ?, ?, ?)",
                                (uid, kind, mech))
                    outcome = 'accepted'
                except sqlite3.IntegrityError as exc:
                    outcome = 'rejected: %s' % str(exc)[:60]
                check(case, 'negative', '%s via raw SQL: rejected by CHECK' % what, True,
                      outcome.startswith('rejected'), outcome)
            raw.rollback()
        finally:
            raw.close()
    with E.app.app_context():
        try:
            db.session.add(m.AuditLog(entity_type='Neg', entity_id=1, action='orm', actor_kind='SYSTEM'))
            db.session.flush()
            outcome = 'accepted'
        except Exception as exc:
            outcome = exc.__class__.__name__
        db.session.rollback()
    check('E-05o', 'negative', 'SYSTEM without mechanism via ORM: refused by the insert listener',
          'AuditActorError', outcome)
    with E.app.app_context():
        try:
            db.session.add(m.AuditLog(entity_type='Neg', entity_id=1, action='orm0', staff_user_id=0))
            db.session.flush()
            got = db.session.execute(db.text(
                "SELECT staff_user_id, actor_kind FROM audit_logs WHERE action='orm0'")).fetchall()
        except Exception as exc:
            got = exc.__class__.__name__
        db.session.rollback()
    check('E-02o', 'negative', 'ORM row with staff_user_id=0 and no operator/mechanism: refused',
          'AuditActorError', got)
    check('E-AUD', 'negative', 'audit table unchanged after all rejected rows', aud0, audit_snapshot(E))
    E.finish()

    # ---- migration negatives (subprocess boots on copies of the restored file)
    def scenario(name, mutate=None):
        p = backup_copy(a.restored, os.path.join(a.iso, 'neg_%s.db' % name))
        if mutate:
            c = sqlite3.connect(p)
            mutate(c)
            c.commit()
            c.close()
        return p, table_digests(p)

    def unchanged(case, what, p, before, rc, out, expect_rc_nonzero=True, needle=None):
        after = table_digests(p)
        c = ro(p)
        integ = c.execute('PRAGMA integrity_check').fetchone()[0]
        left = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%adr011%'").fetchone()[0]
        c.close()
        check(case, 'migration-negative', what,
              (True, True, before, 'ok', 0, False),
              (rc != 0 if expect_rc_nonzero else True, (needle in out) if needle else True,
               after, integ, left, '10.0.0' in _versions(p)),
              ('rc=%s ' % rc) + (out.strip().splitlines()[-1][:150] if out.strip() else ''))

    p, before = scenario('validation')
    tamper = ('import app as _A\n_o=_A._audit_rows_digest\n_n=[0]\n'
              'def _f(conn):\n    _n[0]+=1\n    r=_o(conn)\n    return r if _n[0]==1 else (r[0], "tampered")\n'
              '_A._audit_rows_digest=_f')
    rc, out = boot(WT, p, pre=tamper)
    unchanged('E-10', 'failed migration validation (digest mismatch injected): boot refused, DB unchanged',
              p, before, rc, out, needle='audit rows changed during migration')

    for name, rows in (('zero', [(0,)]), ('dangling', [(999,)]), ('mixed', [(1,), (0,), (999,)])):
        def mut(c, rows=rows):
            for (uid,) in rows:
                c.execute("INSERT INTO audit_logs (entity_type, entity_id, action, staff_user_id, timestamp) "
                          "VALUES ('Hist', 1, 'invalid_history', ?, '2026-08-10 00:00:00')", (uid,))
        p, before = scenario('hist_' + name, mut)
        rc, out = boot(WT, p)
        unchanged('E-11-%s' % name, 'invalid historical actor (%s): boot refused, DB unchanged' % name,
                  p, before, rc, out, needle='migration refused')

    for stmt in ('DROP TABLE audit_logs', 'ALTER TABLE audit_logs__adr011 RENAME'):
        p, before = scenario('interrupt_' + stmt.split()[0].lower())
        kill = ('import os\nfrom sqlalchemy.engine import Connection as _C\n_o=_C.exec_driver_sql\n'
                'def _k(self, s, *a, **k):\n    r=_o(self, s, *a, **k)\n'
                '    if str(s).strip().startswith(%r):\n        os._exit(3)\n    return r\n'
                '_C.exec_driver_sql=_k' % stmt)
        rc, out = boot(WT, p, pre=kill)
        journal = os.path.exists(p + '-journal')
        # Opening read-write rolls back the hot journal, as the next start would.
        c = sqlite3.connect(p)
        c.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
        c.close()
        unchanged('E-13-%s' % stmt.split()[0].lower(),
                  'process killed after "%s" inside the migration: rolled back to the pre-migration DB'
                  % stmt, p, before, rc, out)
        check('E-13j-%s' % stmt.split()[0].lower(), 'migration-negative',
              'kill left a hot rollback journal (rc 3)', (3, True), (rc, journal))
        rc2, out2 = boot(WT, p)
        check('E-13r-%s' % stmt.split()[0].lower(), 'migration-negative',
              'next start migrates cleanly; carried-over digest intact', (0, audit_state(a.restored)[:2]),
              (rc2, audit_state(p)[:2]), out2[-200:] if rc2 else '')


# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--restored', required=True)
    ap.add_argument('--iso', required=True)
    ap.add_argument('--main-wt', required=True)
    ap.add_argument('--label', default='run')
    ap.add_argument('phases', nargs='*', default=['char', 'mig', 'ident', 'neg'])
    a = ap.parse_args()
    a.restored, a.iso, a.main_wt = (os.path.abspath(x) for x in (a.restored, a.iso, a.main_wt))
    for p in (a.restored, a.iso):
        assert not os.path.normcase(p).startswith(os.path.normcase(os.path.join(MAIN, 'instance'))), p
    prod_before = sha(PROD)
    info = {}
    mod = None
    for ph in a.phases:
        if ph in ('ident', 'neg'):
            mod = mod or _impl_module(a)
            r = globals()['phase_' + ph](a, mod)
        else:
            r = globals()['phase_' + ph](a)
        if isinstance(r, dict):
            info.update(r)
    prod_after = sha(PROD)
    check('P-00', 'production', 'production SHA-256 unchanged across the run (== anchor)',
          (ANCHOR, ANCHOR), (prod_before, prod_after))
    gates = [x for x in results if x['severity'] == 'gate']
    passed = sum(1 for x in gates if x['pass'])
    commit = subprocess.check_output(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
    main_commit = subprocess.check_output(['git', '-C', a.main_wt, 'rev-parse', 'HEAD']).decode().strip()
    dirty = subprocess.check_output(['git', '-C', WT, 'status', '--porcelain', '--', 'app']).decode().strip()
    out = {'task': 'ADR-011 pre-production gate rehearsal', 'phases': a.phases,
           'branch_commit': commit, 'branch_app_clean': dirty == '', 'main_control_commit': main_commit,
           'restored': a.restored, 'finished': datetime.now().isoformat(timespec='seconds'),
           'production_sha256_before': prod_before, 'production_sha256_after': prod_after,
           'info': info, 'gates_total': len(gates), 'gates_passed': passed,
           'verdict': 'PASS' if passed == len(gates) else 'FAIL', 'checks': results}
    with open(os.path.join(HERE, 'preprod_%s.json' % a.label), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, default=str)
    print('PREPROD %s: %d/%d gates -> %s' % (a.phases, passed, len(gates), out['verdict']))
    return 0 if out['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
