# -*- coding: utf-8 -*-
"""ADR-011 / AR-013 - characterisation of the CURRENT system-action model.

Verification only: nothing under app/ is changed and no option is
implemented. It records, on disposable copies, how every path that writes
an audit row without an authenticated human behaves today, so the Founder
can decide the representation with evidence (directive sections 9, 10).

Classes (directive section 10), per system writer:
  GREEN     FK enforcement off (production configuration): mutation + audit commit
  RED       audit row fails (F1 construct / F2 insert): the mutation rolls back
  FK-RED    FK enforcement on, actor 0 (no such user): FK failure, mutation rolled back
  HUMAN     the operator-run equivalent names the authenticated operator (FK off and on)
Provenance (directive section 8) is recorded per system audit row as
answerable / not answerable from the row itself.

Reuses the CF-10 harness (20260930_cf10_completion/verify_cf10_cf11.py) for
the disposable-copy environment and the F1/F2 fault seams; production is
opened read-only for hashing only.

    venv\\Scripts\\python.exe verification\\evidence\\20260930_adr011_system_action_provenance\\verify_adr011_current.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
_spec = importlib.util.spec_from_file_location(
    'cf10h', os.path.join(REPO, 'verification', 'evidence', '20260930_cf10_completion',
                          'verify_cf10_cf11.py'))
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
check, results = H.check, H.results

WEBHOOK_KEY = 'adr011-test-key'          # test process only, disposable copy
os.environ['WEBHOOK_API_KEY'] = WEBHOOK_KEY


class FK:
    """Switch SQLite FK enforcement on for every new connection of the copy."""

    def __init__(self, E):
        self.E = E
        from sqlalchemy import event
        self.event = event
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


def main():
    E = H.Env('adr011')
    m, db = E.m, E.db
    import app.services as svc
    import app.noshow_service as ns
    c = E.client()

    with E.app.app_context():
        users = [(u.id, u.role, bool(u.is_active)) for u in db.session.query(m.User).order_by(m.User.id)]
        fkv = len(db.session.execute(db.text('PRAGMA foreign_key_check')).fetchall())
        for k, v in (('noshow_fee_enabled', 'true'), ('noshow_fee_mode', 'fixed'),
                     ('noshow_fee_amount', '500')):
            row = db.session.query(m.Settings).filter_by(key=k).first()
            if row is None:
                db.session.add(m.Settings(key=k, value=v))
            else:
                row.value = v
        db.session.commit()
    check('C-00', 'contract', 'copy: no user id 0; FK check clean', (False, 0),
          (any(u[0] == 0 for u in users), fkv), 'users=%s' % users)

    def bd():
        with E.app.app_context():
            return db.session.query(m.BusinessDate).first().current_date

    def day(d):
        with E.app.app_context():
            return {'logs': db.session.query(m.NightAuditLog).filter_by(audit_date=d).count(),
                    'rent': db.session.query(m.ExtraCharge).filter_by(charge_type='room_rent',
                                                                      charge_date=d).count(),
                    'fees': db.session.query(m.ExtraCharge).filter(
                        m.ExtraCharge.charge_date == d,
                        m.ExtraCharge.description.like('No-Show Fee%')).count(),
                    'bd': db.session.query(m.BusinessDate).first().current_date}

    def fixtures(tag):
        """One in-house guest (room rent tonight) and one arrival due today
        (a no-show candidate), for the current business date."""
        d = bd()
        a = E.new_res(tag + 'ih', 'CheckedIn', d - timedelta(days=1), d + timedelta(days=2), 1000,
                      room_id=E.take_room())
        b = E.new_res(tag + 'ns', 'Reserved', d, d + timedelta(days=1), 1000)
        return d, a, b

    def scheduler_run():
        try:
            svc.run_night_audit(E.app)
            return None
        except Exception as exc:
            return '%s: %s' % (exc.__class__.__name__, str(exc)[:100])

    # ------------------------------------------------------------------ RED
    print('S-1 scheduler night audit - RED (audit failure, FK off)')
    d, ih, nsr = fixtures('red')
    before = day(d)
    for kind in ('F1', 'F2'):
        for tname, pred in (('room_rent', lambda et, ac: et == 'ExtraCharge'),
                            ('noshow_posted', lambda et, ac: ac == 'noshow_posted')):
            with E.fault(kind, only=pred):
                err = scheduler_run()
            check('S1-RED-%s-%s' % (kind, tname), 'W-21/W-14 sched',
                  '%s on %s audit: run rolled back (no log, rent, fee; date unchanged)' % (kind, tname),
                  before, day(d), str(err))

    # --------------------------------------------------------------- FK-RED
    print('S-1 scheduler night audit - FK-RED (actor 0 under FK enforcement)')
    with FK(E):
        err = scheduler_run()
        check('S1-FKRED', 'W-21/W-14 sched', 'FK on: actor 0 rejected, run rolled back atomically',
              (True, before), (err is not None, day(d)), str(err))

    # ---------------------------------------------------------------- GREEN
    print('S-1 scheduler night audit - GREEN (FK off, production configuration)')
    err = scheduler_run()
    after = day(d)
    check('S1-GREEN', 'W-21/W-14 sched', 'FK off: run commits (log, rent, no-show fee)',
          (None, 1, True, True), (err, after['logs'], after['rent'] > before['rent'],
                                  after['fees'] > before['fees']))
    with E.app.app_context():
        log = db.session.query(m.NightAuditLog).filter_by(audit_date=d).first()
        rent_ids = [x.id for x in db.session.query(m.ExtraCharge).filter_by(
            charge_type='room_rent', charge_date=d)]
        fee = (db.session.query(m.ExtraCharge).filter_by(reservation_id=nsr)
               .filter(m.ExtraCharge.description.like('No-Show Fee%')).first())
        nslog = db.session.query(m.NoShowLog).filter_by(reservation_id=nsr).first()
        run_by = log.run_by_user_id if log else 'no log'
        nslog_by = nslog.posted_by_user_id if nslog else 'no log'
    rows = [E.audits('ExtraCharge', i, 'posted') for i in rent_ids]
    rows += [E.audits('ExtraCharge', fee.id, 'posted') if fee else []]
    rows += [E.audits('Reservation', nsr, 'noshow_posted')]
    actors = sorted({r[0]['actor'] for r in rows if r})
    check('S1-GREEN-audit', 'W-21/W-14 sched', 'every system financial row has exactly one audit row',
          [1] * len(rows), [len(r) for r in rows])
    check('S1-ACTOR', 'W-21/W-14 sched', 'system audit rows name an existing user', True,
          all(a in [u[0] for u in users] for a in actors),
          'actors=%s; NightAuditLog.run_by_user_id=%s; NoShowLog.posted_by_user_id=%s'
          % (actors, run_by, nslog_by), gate=False)

    # Provenance (section 8), from a scheduler room-rent audit row alone.
    a = rows[0][0] if rows and rows[0] else {'after': {}, 'actor': None, 'action': None}
    prov = {
        'what (action)': a.get('action') == 'posted',
        'when (technical timestamp)': True,
        'which entity': True,
        'which amount': a['after'].get('amount') is not None,
        'why (flow / run)': a['after'].get('flow') == 'night_audit' and
                            a['after'].get('night_audit_log_id') is not None,
        'business date': a['after'].get('charge_date') == d.isoformat(),
        'human or system (explicit)': False,
        'execution path (scheduler vs manual)': False,
    }
    for k, v in prov.items():
        check('S1-PROV-%s' % k.split(' ')[0], 'provenance', 'answerable from the row: %s' % k, True, v,
              'actor=%s flow=%s' % (a.get('actor'), a['after'].get('flow')),
              gate=k not in ('human or system (explicit)', 'execution path (scheduler vs manual)'))

    # ----------------------------------------------------------- HUMAN GREEN
    print('S-1 human equivalent: POST /night-audit/run (FK off, then FK on)')
    for fk in (False, True):
        d, ih, nsr = fixtures('hum%d' % fk)
        cm = FK(E) if fk else H._null()
        with cm:
            r = E.call(lambda: c.post('/night-audit/run'))
            s = day(d)
        with E.app.app_context():
            log = db.session.query(m.NightAuditLog).filter_by(audit_date=d).first()
            rid = [x.id for x in db.session.query(m.ExtraCharge).filter_by(
                reservation_id=ih, charge_type='room_rent', charge_date=d)]
            fee = (db.session.query(m.ExtraCharge).filter_by(reservation_id=nsr)
                   .filter(m.ExtraCharge.description.like('No-Show Fee%')).first())
        acts = sorted({x['actor'] for grp in ([E.audits('ExtraCharge', i, 'posted') for i in rid]
                                              + [E.audits('ExtraCharge', fee.id, 'posted') if fee else []]
                                              + [E.audits('Reservation', nsr, 'noshow_posted')])
                       for x in grp})
        check('S1-HUMAN-%s' % ('FK' if fk else 'noFK'), 'W-21/W-14 manual',
              'operator run commits; every audit row names the operator; run_by recorded',
              (1, [E.admin_id], E.admin_id), (s['logs'], acts, log.run_by_user_id if log else None),
              'HTTP %s' % H.status(r))

    # ----------------------------------------------- S-2 automated no-show
    print('S-2 automated no-show outside a night audit (no operator, no request)')

    def auto_noshow(rid):
        with E.app.app_context():
            try:
                ns.process_reservation_noshow(db.session.get(m.Reservation, rid), bd(),
                                              ns._get_noshow_config(), posted_by_user_id=None)
                db.session.commit()
                return None
            except Exception as exc:
                db.session.rollback()
                return '%s: %s' % (exc.__class__.__name__, str(exc)[:90])

    def ns_state(rid):
        with E.app.app_context():
            return (db.session.get(m.Reservation, rid).status,
                    db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).count(),
                    db.session.query(m.NoShowLog).filter_by(reservation_id=rid).count())

    for kind in ('F1', 'F2'):
        rid = E.new_res('ns%s' % kind, 'Reserved', bd(), bd() + timedelta(days=1), 1000)
        b = ns_state(rid)
        with E.fault(kind):
            err = auto_noshow(rid)
        check('S2-RED-%s' % kind, 'W-14 auto', '%s on any audit: not a no-show, no fee, no log' % kind,
              b, ns_state(rid), str(err))
    rid = E.new_res('nsfk', 'Reserved', bd(), bd() + timedelta(days=1), 1000)
    b = ns_state(rid)
    with FK(E):
        err = auto_noshow(rid)
    check('S2-FKRED', 'W-14 auto', 'FK on: actor 0 rejected, nothing persisted', (True, b),
          (err is not None, ns_state(rid)), str(err))
    rid = E.new_res('nsgr', 'Reserved', bd(), bd() + timedelta(days=1), 1000)
    err = auto_noshow(rid)
    fa = E.audits('Reservation', rid, 'noshow_posted')
    check('S2-GREEN', 'W-14 auto', 'FK off: no-show, fee and log commit with audit',
          (None, ('NoShow', 1, 1), 1), (err, ns_state(rid), len(fa)))
    check('S2-ACTOR', 'W-14 auto', 'system audit row names an existing user', True,
          (fa[0]['actor'] if fa else None) in [u[0] for u in users],
          'actor=%s' % (fa[0]['actor'] if fa else None), gate=False)

    # ------------------------------------------------- S-3 webhook modify
    print('S-3 webhook modify_booking (unattended, non-financial row, rate change)')

    def ota_res(tag):
        rid = E.new_res(tag, 'Reserved', bd() + timedelta(days=60), bd() + timedelta(days=62), 1000)
        with E.app.app_context():
            db.session.get(m.Reservation, rid).ota_booking_id = 'ADR011-%s' % tag
            db.session.commit()
        return rid

    def modify(tag):
        return E.call(lambda: c.post('/webhook/booking', json={
            'event': 'modify_booking', 'ota_booking_id': 'ADR011-%s' % tag,
            'rate_per_night': 1500}, headers={'X-API-Key': WEBHOOK_KEY}))

    def wh_state(rid):
        return (round(float(E.get(m.Reservation, rid, 'rate_per_night')), 2),
                len(E.audits('Reservation', rid, 'webhook_modify')))

    rid = ota_res('whg')
    r = modify('whg')
    s = wh_state(rid)
    wa = E.audits('Reservation', rid, 'webhook_modify')
    check('S3-GREEN', 'webhook', 'FK off: rate changed and audited', (1500.0, 1), s, 'HTTP %s' % H.status(r))
    check('S3-ACTOR', 'webhook', 'webhook audit row names an existing user', True,
          (wa[0]['actor'] if wa else None) in [u[0] for u in users],
          'actor=%s' % (wa[0]['actor'] if wa else None), gate=False)
    for kind in ('F1', 'F2'):
        rid = ota_res('wh%s' % kind)
        with E.fault(kind):
            r = modify('wh%s' % kind)
        s = wh_state(rid)
        check('S3-RED-%s' % kind, 'webhook', '%s on the audit: rate change not committed unaudited' % kind,
              True, s in ((1000.0, 0), (1500.0, 1)), 'state=%s HTTP %s (swallowing _write_audit)'
              % (s, H.status(r)), gate=False)
    rid = ota_res('whfk')
    with FK(E):
        r = modify('whfk')
    s = wh_state(rid)
    check('S3-FKRED', 'webhook', 'FK on: all-or-nothing (no unaudited rate change)', True,
          s in ((1000.0, 0), (1500.0, 1)), 'state=%s HTTP %s' % (s, H.status(r)))
    check('S3-FK-completes', 'webhook', 'FK on: OTA modification can complete', (1500.0, 1), s,
          'HTTP %s' % H.status(r), gate=False)

    # --------------------------------------------------------------- finish
    prod_after = E.finish()
    check('P-01', 'prod', 'production database unchanged (sha256 == anchor)', H.FROZEN_ANCHOR, prod_after)
    gates = [x for x in results if x['severity'] == 'gate']
    passed = sum(1 for x in gates if x['pass'])
    out = {'task': 'ADR-011 current-model characterisation', 'app_commit': H.APP_COMMIT,
           'app_tree_clean': H.APP_DIRTY == '', 'finished': datetime.now().isoformat(timespec='seconds'),
           'copy': E.handle.copy_path, 'production_sha256_after': prod_after,
           'gates_total': len(gates), 'gates_passed': passed,
           'verdict': 'PASS' if passed == len(gates) else 'FAIL',
           'findings': [x for x in results if x['severity'] == 'finding' and not x['pass']],
           'checks': results}
    with open(os.path.join(HERE, 'characterisation_%s.json' % (H.APP_COMMIT or 'unknown')[:7]), 'w',
              encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, default=str)
    print('ADR-011 characterisation: %d/%d gates -> %s; %d findings'
          % (passed, len(gates), out['verdict'], len(out['findings'])))
    return 0 if out['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
