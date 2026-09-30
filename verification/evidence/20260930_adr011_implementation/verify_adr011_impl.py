# -*- coding: utf-8 -*-
"""ADR011-SA implementation verification (branch adr011-system-actor).

Runs the application from THIS checkout (a git worktree) against disposable
copies of production made by the main repository's ``verification.dbcopy``;
production is opened read-only for hashing only. The main repository is
found through ``git rev-parse --git-common-dir``.

    <main>\\venv\\Scripts\\python.exe verification\\evidence\\20260930_adr011_implementation\\verify_adr011_impl.py [group ...]

Groups
  mig     migration on a production copy, idempotence, refusal on invalid
          history, fresh install
  sys     system writers (scheduler night audit, automated no-show, webhook):
          GREEN with FK off and on, RED (F1/F2), invalid-actor RED (FK and
          CHECK), undeclared-actor RED
  human   operator equivalents: HUMAN rows, role and shift snapshots, FK on/off
  prov    directive section 8 provenance questions, answered from the row
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
os.environ['CF10_APP_ROOT'] = WT
os.environ['CF10_OUT_DIR'] = HERE
_spec = importlib.util.spec_from_file_location(
    'cf10h', os.path.join(MAIN, 'verification', 'evidence', '20260930_cf10_completion',
                          'verify_cf10_cf11.py'))
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
check, results = H.check, H.results
WEBHOOK_KEY = 'adr011-test-key'
os.environ['WEBHOOK_API_KEY'] = WEBHOOK_KEY
ORIG_COLS = ('id', 'entity_type', 'entity_id', 'action', 'before_state', 'after_state',
             'staff_user_id', 'ip_address', 'timestamp')


def raw_digest(path):
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    h = hashlib.sha256()
    rows = c.execute('SELECT %s FROM audit_logs ORDER BY id' % ', '.join(ORIG_COLS)).fetchall()
    for r in rows:
        h.update(json.dumps(list(r), default=str, sort_keys=True).encode() + b'\n')
    sql = c.execute("SELECT sql FROM sqlite_master WHERE name='audit_logs'").fetchone()[0]
    c.close()
    return len(rows), h.hexdigest(), sql


class FK:
    def __init__(self, E):
        from sqlalchemy import event
        self.E, self.event = E, event
        with E.app.app_context():
            self.engine = E.db.engine

    @staticmethod
    def _on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA foreign_keys=ON')
        cur.close()

    def __enter__(self):
        self.event.listen(self.engine, 'connect', self._on)
        self.engine.dispose()
        with self.E.app.app_context():
            assert self.E.db.session.execute(self.E.db.text('PRAGMA foreign_keys')).scalar() == 1
        return self

    def __exit__(self, *a):
        self.event.remove(self.engine, 'connect', self._on)
        self.engine.dispose()


class ForcedActor:
    """Force the resolver to return an invalid actor (test process only)."""

    def __init__(self, staff_user_id):
        self.uid = staff_user_id

    def __enter__(self):
        import app.audit_actor as aa
        self.aa, self.real = aa, aa.resolve
        aa.resolve = lambda *a, **k: aa.AuditActor(self.uid, aa.HUMAN, 'test:forced')
        return self

    def __exit__(self, *a):
        self.aa.resolve = self.real


def rows_of(E, pred_sql, params):
    m, db = E.m, E.db
    with E.app.app_context():
        return [dict(r._mapping) for r in db.session.execute(db.text(
            'SELECT id, entity_type, entity_id, action, staff_user_id, actor_kind, '
            'actor_mechanism, actor_role, actor_shift_id FROM audit_logs WHERE ' + pred_sql +
            ' ORDER BY id'), params)]


# ===========================================================================
def group_mig():
    """Migration. Each case boots the branch application in a subprocess on
    its own copy, so each boot starts from the unmigrated production shape."""
    from verification.dbcopy import make_copy, assert_production_untouched
    prod = raw_digest(H.PRODUCTION_DB)
    check('M-00', 'migration', 'production audit_logs: 23 rows, pre-ADR011 schema',
          (23, True), (prod[0], 'actor_kind' not in prod[2]))

    def boot(copy_path):
        code = ('import os,sys; sys.path.insert(0, %r); os.environ["DATABASE_URL"]=%r; '
                'os.environ["FLASK_ENV"]="production"; from app import create_app; '
                'app=create_app(); from app.services import scheduler; '
                'print("JOB", scheduler.get_job("night_audit_job")); '
                'scheduler.shutdown(wait=False) if scheduler.running else None'
                % (WT, 'sqlite:///' + copy_path.replace('\\', '/')))
        p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        return p.returncode, (p.stdout + p.stderr)

    h = make_copy(name='adr011_mig.db')
    rc, out = boot(h.copy_path)
    n, dig, sql = raw_digest(h.copy_path)
    c = sqlite3.connect(h.copy_path)
    info = {r[1]: r for r in c.execute('PRAGMA table_info(audit_logs)')}
    kinds = c.execute('SELECT actor_kind, COUNT(*) FROM audit_logs GROUP BY 1').fetchall()
    ver = c.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='10.0.0'").fetchone()[0]
    integ = c.execute('PRAGMA integrity_check').fetchone()[0]
    c.execute('PRAGMA foreign_keys=ON')
    fkv = c.execute('PRAGMA foreign_key_check').fetchall()
    idx = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='idx_audit_entity'").fetchone()[0]
    c.close()
    check('M-01', 'migration', 'production copy boots and migrates', 0, rc, out[-300:] if rc else '')
    check('M-02', 'migration', 'every pre-existing row carried over unchanged (count + digest)',
          (prod[0], prod[1]), (n, dig))
    check('M-03', 'migration', 'new shape: nullable staff_user_id, 4 actor columns, 3 CHECKs, index',
          (0, True, 3, 1),
          (info['staff_user_id'][3], all(k in info for k in ('actor_kind', 'actor_mechanism',
                                                               'actor_role', 'actor_shift_id')),
           sum(sql.count(x) for x in ('ck_audit_actor_kind', 'ck_audit_actor_identity',
                                      'ck_audit_actor_not_zero')), idx))
    check('M-04', 'migration', 'all historical rows HUMAN; migration recorded; integrity ok; FK clean',
          ([('HUMAN', prod[0])], 1, 'ok', []), (kinds, ver, integ, fkv))
    check('M-05', 'migration', 'scheduler night-audit job not registered (FD-P2-05)', True,
          'JOB None' in out)
    rc2, out2 = boot(h.copy_path)
    check('M-06', 'migration', 'second boot: idempotent, table unchanged', (0, (n, dig, sql)),
          (rc2, raw_digest(h.copy_path)))
    prod_after = assert_production_untouched(h)

    # Refusal on invalid history: a row naming users.id 0 (the retired convention).
    h2 = make_copy(name='adr011_mig_refuse.db')
    c = sqlite3.connect(h2.copy_path)
    c.execute("INSERT INTO audit_logs (entity_type, entity_id, action, staff_user_id, timestamp) "
              "VALUES ('Test', 1, 'legacy_zero_actor', 0, '2026-08-10 00:00:00')")
    c.commit()
    c.close()
    before = raw_digest(h2.copy_path)
    rc3, out3 = boot(h2.copy_path)
    c = sqlite3.connect(h2.copy_path)
    ver3 = c.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='10.0.0'").fetchone()[0]
    left = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='audit_logs__adr011'").fetchone()[0]
    c.close()
    check('M-07', 'migration', 'history naming user 0: boot refused, table untouched, not recorded',
          (True, True, before, 0, 0),
          (rc3 != 0, 'migration refused' in out3, raw_digest(h2.copy_path), ver3, left))

    # Fresh install: an empty database is created from the models.
    fresh = os.path.join(os.path.dirname(h.copy_path), 'adr011_fresh.db')
    if os.path.exists(fresh):
        os.remove(fresh)
    rc4, out4 = boot(fresh)
    c = sqlite3.connect(fresh)
    fsql = c.execute("SELECT sql FROM sqlite_master WHERE name='audit_logs'").fetchone()[0]
    fver = c.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='10.0.0'").fetchone()[0]
    c.close()
    check('M-08', 'migration', 'fresh install: models create the ADR011 shape; migration recorded',
          (0, True, True, 1), (rc4, 'ck_audit_actor_identity' in fsql,
                               'staff_user_id INTEGER NOT NULL' not in fsql, fver), out4[-200:] if rc4 else '')
    return prod_after


# ===========================================================================
def fixtures(E, tag):
    d = bd(E)
    a = E.new_res(tag + 'ih', 'CheckedIn', d - timedelta(days=1), d + timedelta(days=2), 1000,
                  room_id=E.take_room())
    b = E.new_res(tag + 'ns', 'Reserved', d, d + timedelta(days=1), 1000)
    return d, a, b


def bd(E):
    with E.app.app_context():
        return E.db.session.query(E.m.BusinessDate).first().current_date


def day(E, d):
    m, db = E.m, E.db
    with E.app.app_context():
        return {'logs': db.session.query(m.NightAuditLog).filter_by(audit_date=d).count(),
                'rent': db.session.query(m.ExtraCharge).filter_by(charge_type='room_rent',
                                                                  charge_date=d).count(),
                'fees': db.session.query(m.ExtraCharge).filter(
                    m.ExtraCharge.charge_date == d,
                    m.ExtraCharge.description.like('No-Show Fee%')).count(),
                'bd': db.session.query(m.BusinessDate).first().current_date}


def night_rows(E, d, ih, nsr):
    """Audit rows of one night's system financial rows."""
    m, db = E.m, E.db
    with E.app.app_context():
        rent = [x.id for x in db.session.query(m.ExtraCharge).filter_by(
            reservation_id=ih, charge_type='room_rent', charge_date=d)]
        fee = [x.id for x in db.session.query(m.ExtraCharge).filter_by(reservation_id=nsr)
               .filter(m.ExtraCharge.description.like('No-Show Fee%'))]
    ids = rent + fee
    r = rows_of(E, "entity_type='ExtraCharge' AND action='posted' AND entity_id IN (%s)"
                % (','.join(str(i) for i in ids) or '0'), {})
    r += rows_of(E, "entity_type='Reservation' AND action='noshow_posted' AND entity_id=:e", {'e': nsr})
    return len(ids), r


def run(fn):
    try:
        fn()
        return None
    except Exception as exc:
        return '%s: %s' % (exc.__class__.__name__, str(exc)[:300])


def advance_day(E):
    """Move the copy's business date on by one, so the next run audits a day
    with no NightAuditLog (a Pending day blocks any further run of that date)."""
    with E.app.app_context():
        b = E.db.session.query(E.m.BusinessDate).first()
        b.current_date = b.current_date + timedelta(days=1)
        E.db.session.commit()


def group_sys(E):
    m, db = E.m, E.db
    import app.services as svc
    import app.noshow_service as ns
    from app.audit_actor import system_action
    c = E.client()
    with E.app.app_context():
        for k, v in (('noshow_fee_enabled', 'true'), ('noshow_fee_mode', 'fixed'),
                     ('noshow_fee_amount', '500')):
            row = db.session.query(m.Settings).filter_by(key=k).first()
            if row is None:
                db.session.add(m.Settings(key=k, value=v))
            else:
                row.value = v
        db.session.commit()

    sched = lambda: svc.scheduled_night_audit(E.app)          # the registered job function

    # --- RED and invalid-actor RED first (each leaves the date open) --------
    d, ih, nsr = fixtures(E, 'sred')
    before = day(E, d)
    for kind in ('F1', 'F2'):
        for tname, pred in (('room_rent', lambda et, ac: et == 'ExtraCharge'),
                            ('noshow_posted', lambda et, ac: ac == 'noshow_posted')):
            with E.fault(kind, only=pred):
                err = run(sched)
            check('S1-RED-%s-%s' % (kind, tname), 'sched NA', '%s on %s audit: whole run rolled back'
                  % (kind, tname), (True, before), (err is not None, day(E, d)), str(err))
    with FK(E), ForcedActor(999999):
        err = run(sched)
    check('S1-RED-FK', 'sched NA', 'FK on, actor references no user: FK failure, run rolled back',
          (True, before), (err is not None and 'FOREIGN KEY' in err.upper(), day(E, d)), str(err))
    with ForcedActor(0):
        err = run(sched)
    check('S1-RED-ZERO', 'sched NA', 'FK off, forced users.id 0: refused (CHECK), run rolled back',
          (True, before), (err is not None, day(E, d)), str(err))
    err = run(lambda: svc.run_night_audit(E.app))
    check('S1-RED-UNDECLARED', 'sched NA',
          'no operator and no declared mechanism: refused, run rolled back (never mislabelled)',
          (True, before), (err is not None and 'actor' in err.lower(), day(E, d)), str(err))

    # --- GREEN, FK on (the target configuration) -----------------------------
    with FK(E):
        err = run(sched)
        after = day(E, d)
    n, rows = night_rows(E, d, ih, nsr)
    check('S1-GREEN-FK', 'sched NA', 'FK on: scheduled run completes (log, rent, fee)',
          (None, 1, True, True), (err, after['logs'], after['rent'] > before['rent'],
                                  after['fees'] > before['fees']))
    check('S1-GREEN-ROWS', 'sched NA',
          'every system financial row + noshow_posted: one SYSTEM row, no user, scheduler mechanism',
          [('SYSTEM', None, 'scheduler:night_audit_job', None, None)] * (n + 1),
          [(r['actor_kind'], r['staff_user_id'], r['actor_mechanism'], r['actor_role'],
            r['actor_shift_id']) for r in rows])
    with E.app.app_context():
        log = db.session.query(m.NightAuditLog).filter_by(audit_date=d).first()
        nsl = db.session.query(m.NoShowLog).filter_by(reservation_id=nsr).first()
        prov = (log.run_by_user_id if log else 'x', nsl.posted_by_user_id if nsl else 'x')
    check('S1-GREEN-RUNBY', 'sched NA', 'NightAuditLog.run_by / NoShowLog.posted_by empty (no human)',
          (None, None), prov)

    # --- GREEN, FK off (the current production configuration) ---------------
    d2, ih2, nsr2 = fixtures(E, 'sgreen')
    err = run(sched)
    n2, rows2 = night_rows(E, d2, ih2, nsr2)
    check('S1-GREEN-noFK', 'sched NA', 'FK off: run completes, same SYSTEM representation',
          (None, [('SYSTEM', None, 'scheduler:night_audit_job')] * (n2 + 1)),
          (err, [(r['actor_kind'], r['staff_user_id'], r['actor_mechanism']) for r in rows2]))

    # --- S2 automated no-show -----------------------------------------------
    def auto_noshow(rid, mech='scheduler:night_audit_job'):
        with E.app.app_context():
            try:
                cm = system_action(mech) if mech else H._null()
                with cm:
                    ns.process_reservation_noshow(db.session.get(m.Reservation, rid), bd(E),
                                                  ns._get_noshow_config(), posted_by_user_id=None)
                db.session.commit()
                return None
            except Exception as exc:
                db.session.rollback()
                return '%s: %s' % (exc.__class__.__name__, str(exc)[:110])

    def ns_state(rid):
        with E.app.app_context():
            return (db.session.get(m.Reservation, rid).status,
                    db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).count(),
                    db.session.query(m.NoShowLog).filter_by(reservation_id=rid).count())

    def new_ns(tag):
        return E.new_res(tag, 'Reserved', bd(E), bd(E) + timedelta(days=1), 1000)

    for kind in ('F1', 'F2'):
        rid = new_ns('ns%s' % kind)
        b = ns_state(rid)
        with E.fault(kind):
            err = auto_noshow(rid)
        check('S2-RED-%s' % kind, 'auto no-show', '%s: not a no-show, no fee, no log' % kind,
              (True, b), (err is not None, ns_state(rid)), str(err))
    rid = new_ns('nsfk')
    b = ns_state(rid)
    with FK(E), ForcedActor(999999):
        err = auto_noshow(rid)
    check('S2-RED-FK', 'auto no-show', 'FK on, invalid actor: FK failure, nothing persisted',
          (True, b), (err is not None, ns_state(rid)), str(err))
    rid = new_ns('nsund')
    b = ns_state(rid)
    err = auto_noshow(rid, mech=None)
    check('S2-RED-UNDECLARED', 'auto no-show', 'no operator, no mechanism: refused, nothing persisted',
          (True, b), (err is not None, ns_state(rid)), str(err))
    for fk in (True, False):
        rid = new_ns('nsg%d' % fk)
        with (FK(E) if fk else H._null()):
            err = auto_noshow(rid)
        with E.app.app_context():
            fee = (db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).first())
        r = rows_of(E, "(entity_type='ExtraCharge' AND entity_id=:f AND action='posted') OR "
                       "(entity_type='Reservation' AND entity_id=:r AND action='noshow_posted')",
                    {'f': fee.id if fee else 0, 'r': rid})
        check('S2-GREEN-%s' % ('FK' if fk else 'noFK'), 'auto no-show',
              'completes; fee + noshow_posted are SYSTEM rows with no user',
              (None, ('NoShow', 1, 1), [('SYSTEM', None)] * 2),
              (err, ns_state(rid), [(x['actor_kind'], x['staff_user_id']) for x in r]))

    # --- S3 webhook modify ---------------------------------------------------
    def ota_res(tag):
        rid = E.new_res(tag, 'Reserved', bd(E) + timedelta(days=60), bd(E) + timedelta(days=62), 1000)
        with E.app.app_context():
            db.session.get(m.Reservation, rid).ota_booking_id = 'ADR011I-%s' % tag
            db.session.commit()
        return rid

    for fk in (True, False):
        tag = 'wh%d' % fk
        rid = ota_res(tag)
        with (FK(E) if fk else H._null()):
            r = E.call(lambda: c.post('/webhook/booking', json={
                'event': 'modify_booking', 'ota_booking_id': 'ADR011I-%s' % tag,
                'rate_per_night': 1500}, headers={'X-API-Key': WEBHOOK_KEY}))
        rows = rows_of(E, "entity_type='Reservation' AND entity_id=:r AND action='webhook_modify'",
                       {'r': rid})
        check('S3-GREEN-%s' % ('FK' if fk else 'noFK'), 'webhook',
              'modify completes; one SYSTEM row, no user, mechanism webhook',
              (200, 1500.0, [('SYSTEM', None, 'webhook')]),
              (H.status(r), round(float(E.get(m.Reservation, rid, 'rate_per_night')), 2),
               [(x['actor_kind'], x['staff_user_id'], x['actor_mechanism']) for x in rows]))

    # --- unauthenticated request through routes._write_audit -----------------
    import app.routes as routes
    with E.app.test_request_context('/', environ_base={'REMOTE_ADDR': '10.0.0.9'}):
        routes._write_audit('Test', 424242, 'adr011_unauthenticated_probe', {}, {})
        db.session.commit()
        db.session.remove()
    r = rows_of(E, "entity_id=424242 AND action='adr011_unauthenticated_probe'", {})
    check('S4-UNAUTH', 'web', 'unauthenticated request: SYSTEM row, no user, web:unauthenticated',
          [('SYSTEM', None, 'web:unauthenticated')],
          [(x['actor_kind'], x['staff_user_id'], x['actor_mechanism']) for x in r])

    # --- the DB rejects a fabricated actor written around the application ----
    with E.app.app_context():
        raw = db.engine.raw_connection()
        try:
            cur = raw.cursor()
            outcome = []
            for uid, kind, mech in ((0, 'HUMAN', None), (None, 'HUMAN', None), (None, 'SYSTEM', None),
                                    (E.admin_id, 'SYSTEM', 'x')):
                try:
                    cur.execute("INSERT INTO audit_logs (entity_type, entity_id, action, staff_user_id, "
                                "actor_kind, actor_mechanism) VALUES ('Test', 1, 'raw', ?, ?, ?)",
                                (uid, kind, mech))
                    outcome.append('accepted')
                except sqlite3.IntegrityError:
                    outcome.append('rejected')
            raw.rollback()
        finally:
            raw.close()
    check('S5-CHECK', 'schema', 'raw INSERTs: user 0 / HUMAN without user / SYSTEM without '
          'mechanism / SYSTEM with a user -> all rejected by CHECK', ['rejected'] * 4, outcome)


# ===========================================================================
def group_human(E):
    m, db = E.m, E.db
    c = E.client()
    with E.app.app_context():
        sh = m.Shift(user_id=E.admin_id, shift_type='Morning', status='Open', opening_cash=0)
        db.session.add(sh)
        db.session.commit()
        shift_id = sh.id
    for fk in (False, True):
        advance_day(E)
        d, ih, nsr = fixtures(E, 'hum%d' % fk)
        with (FK(E) if fk else H._null()):
            r = E.call(lambda: c.post('/night-audit/run'))
            s = day(E, d)
        n, rows = night_rows(E, d, ih, nsr)
        with E.app.app_context():
            log = db.session.query(m.NightAuditLog).filter_by(audit_date=d).first()
        check('H-NA-%s' % ('FK' if fk else 'noFK'), 'manual NA',
              'operator run: every row HUMAN, the operator, role Admin, open shift, mechanism web',
              (1, [('HUMAN', E.admin_id, 'Admin', shift_id, 'web')] * (n + 1), E.admin_id),
              (s['logs'], [(x['actor_kind'], x['staff_user_id'], x['actor_role'], x['actor_shift_id'],
                            x['actor_mechanism']) for x in rows], log.run_by_user_id if log else None),
              'HTTP %s' % H.status(r))
    with E.app.app_context():
        db.session.get(m.Shift, shift_id).status = 'Closed'
        db.session.commit()
    rid = E.new_res('hns', 'Reserved', bd(E), bd(E) + timedelta(days=1), 1000)
    import app.noshow_service as ns
    with FK(E):
        with E.logged_ctx():
            res = ns.manual_noshow(rid, E.admin_id, 'ADR011 human')
    r = rows_of(E, "entity_type='Reservation' AND entity_id=:r AND action='noshow_posted'", {'r': rid})
    check('H-NS-FK', 'manual no-show', 'FK on: HUMAN row, operator, role Admin, no open shift',
          [('HUMAN', E.admin_id, 'Admin', None)],
          [(x['actor_kind'], x['staff_user_id'], x['actor_role'], x['actor_shift_id']) for x in r],
          str(getattr(res, 'message', ''))[:60])


# ===========================================================================
def group_prov(E):
    """Directive section 8, from the rows alone: scheduler vs manual night audit."""
    import app.services as svc
    c = E.client()
    advance_day(E)
    d1, ih1, ns1 = fixtures(E, 'pv1')
    svc.scheduled_night_audit(E.app)
    _, sys_rows = night_rows(E, d1, ih1, ns1)
    advance_day(E)
    d2, ih2, ns2 = fixtures(E, 'pv2')
    c.post('/night-audit/run')
    _, hum_rows = night_rows(E, d2, ih2, ns2)
    # The room-rent row of each run (a run's no-show fee row, flow noshow_fee,
    # precedes it in id order).
    with E.app.app_context():
        ids = [r['id'] for r in sys_rows + hum_rows]
        full = [r for r in E.db.session.query(E.m.AuditLog).filter(E.m.AuditLog.id.in_(ids))
                .order_by(E.m.AuditLog.id)
                if (r.after_state or {}).get('charge_type') == 'room_rent']
    fs = next(r for r in full if r.id in [x['id'] for x in sys_rows])
    fh = next(r for r in full if r.id in [x['id'] for x in hum_rows])
    answers = {
        'what': bool(fs.action and fh.action),
        'when': fs.timestamp is not None and fh.timestamp is not None,
        'which entity': (fs.entity_type, fh.entity_type) == ('ExtraCharge', 'ExtraCharge'),
        'which amount': fs.after_state.get('amount') is not None and fh.after_state.get('amount') is not None,
        'why': (fs.after_state.get('flow'), fh.after_state.get('flow')) == ('night_audit', 'night_audit'),
        'human or system': (fs.actor_kind, fh.actor_kind) == ('SYSTEM', 'HUMAN'),
        'execution path': (fs.actor_mechanism, fh.actor_mechanism) == ('scheduler:night_audit_job', 'web'),
        'business date': (fs.after_state.get('charge_date'), fh.after_state.get('charge_date'))
                         == (d1.isoformat(), d2.isoformat()),
    }
    for k, v in answers.items():
        check('P-%s' % k.replace(' ', '_'), 'provenance', 'answerable from the row: %s' % k, True, v)


# ===========================================================================
def main():
    groups = sys.argv[1:] or ['mig', 'sys', 'human', 'prov']
    prod_hash = None
    if 'mig' in groups:
        prod_hash = group_mig()
    rest = [g for g in groups if g != 'mig']
    if rest:
        E = H.Env('adr011impl')
        for g in rest:
            print('=== group', g)
            globals()['group_' + g](E)
        prod_hash = E.finish()
    check('P-01', 'prod', 'production database unchanged (sha256 == anchor)', H.FROZEN_ANCHOR, prod_hash)
    gates = [x for x in results if x['severity'] == 'gate']
    passed = sum(1 for x in gates if x['pass'])
    commit = subprocess.check_output(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
    dirty = subprocess.check_output(['git', '-C', WT, 'status', '--porcelain', '--', 'app']).decode().strip()
    out = {'task': 'ADR011-SA implementation verification', 'groups': groups,
           'app_root': WT, 'app_commit': commit, 'app_tree_clean': dirty == '',
           'finished': datetime.now().isoformat(timespec='seconds'),
           'production_sha256_after': prod_hash, 'gates_total': len(gates), 'gates_passed': passed,
           'verdict': 'PASS' if passed == len(gates) else 'FAIL', 'checks': results}
    label = os.environ.get('ADR011_RUN_LABEL', 'run')
    with open(os.path.join(HERE, 'results_%s.json' % label), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, default=str)
    print('ADR011-SA: %d/%d gates -> %s' % (passed, len(gates), out['verdict']))
    return 0 if out['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
