# -*- coding: utf-8 -*-
"""Retention control (FD-P2-02) - focused verification on a disposable copy.

Proves that the daily ``log_pruning_job`` no longer deletes ``audit_logs``
rows while it still prunes ``webhook_logs`` and ``notification_logs``, that
the job's identity and schedule are unchanged, that it still executes, and
that ordinary audit writing is unaffected. Includes a negative control that
re-creates the pre-change loop and shows it WOULD have deleted the old audit
row, so the assertion is capable of failing.

    venv\\Scripts\\python.exe verification\\evidence\\20260910_retention_control\\verify_retention.py

Production is opened read-only for hashing only; every mutation happens on
the ``make_copy()`` copy. The eight D11 rows are proven unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from verification.dbcopy import make_copy                      # noqa: E402
from verification.config import PRODUCTION_DB                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN_ANCHOR = '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2'
results = []


def check(case_id, what, expect, got, note=''):
    ok = (expect == got)
    results.append({'case': case_id, 'what': what, 'expect': expect, 'got': got,
                    'pass': ok, 'note': note})
    print('%-5s %-8s %-62s expect=%-22s got=%-22s %s'
          % ('OK' if ok else 'FAIL', case_id, what[:62], repr(expect)[:22], repr(got)[:22], note))
    return ok


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    started = datetime.now()
    prod_before = sha256(PRODUCTION_DB)
    print('=' * 130)
    print('RETENTION CONTROL (FD-P2-02) - FOCUSED VERIFICATION')
    print('=' * 130)
    print('production        : %s' % PRODUCTION_DB)
    print('sha256 before     : %s  (%s)' % (prod_before, 'MATCHES anchor' if prod_before == FROZEN_ANCHOR else '*** MISMATCH ***'))
    handle = make_copy(name='retention_control.db')
    print('disposable copy   : %s  (%s)' % (handle.copy_path, handle.method))
    print('-' * 130)

    os.environ['DATABASE_URL'] = 'sqlite:///' + handle.copy_path.replace('\\', '/')
    os.environ['FLASK_ENV'] = 'production'
    from app import create_app                                           # noqa: E402
    from app.models import (db, AuditLog, WebhookLog, NotificationLog,    # noqa: E402
                            Payment, ExtraCharge, Reservation, User)
    from app.services import scheduler                                    # noqa: E402
    from sqlalchemy import Integer, String, Text, Boolean, DateTime       # noqa: E402

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    route_count = len(list(app.url_map.iter_rules()))
    print('routes            : %d' % route_count)

    def mk(Model, **known):
        """Construct a row filling every NOT NULL column without a default."""
        kw = dict(known)
        for col in Model.__table__.columns:
            if col.name in kw or col.primary_key or col.nullable or col.default is not None \
                    or col.server_default is not None:
                continue
            t = col.type
            if isinstance(t, (String, Text)):
                kw[col.name] = 'rc_probe'
            elif isinstance(t, Integer):
                kw[col.name] = 1
            elif isinstance(t, Boolean):
                kw[col.name] = False
            elif isinstance(t, DateTime):
                kw[col.name] = datetime.utcnow()
            else:
                kw[col.name] = 'rc_probe'
        return Model(**kw)

    old = datetime.utcnow() - timedelta(days=100)
    new = datetime.utcnow()

    # -- D11 identity + fixtures ----------------------------------------
    with app.app_context():
        d11_pay = sorted(r[0] for r in db.session.query(Payment.id).filter(Payment.folio_id.is_(None)).all())
        d11_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id).filter(ExtraCharge.folio_id.is_(None)).all())
        d11_vals = {'p:%d' % p.id: float(p.amount) for p in db.session.query(Payment).filter(Payment.id.in_(d11_pay))}
        d11_vals.update({'c:%d' % c.id: float(c.amount) for c in db.session.query(ExtraCharge).filter(ExtraCharge.id.in_(d11_chg))})
        audit_baseline = db.session.query(AuditLog).count()
        admin = db.session.query(User).filter_by(role='Admin').first()
        admin_id = admin.id
        a_old = mk(AuditLog, entity_type='RetentionProbe', entity_id=1, action='rc_old',
                   before_state=None, after_state={'probe': 'old'}, staff_user_id=admin.id, timestamp=old)
        a_new = mk(AuditLog, entity_type='RetentionProbe', entity_id=2, action='rc_new',
                   before_state=None, after_state={'probe': 'new'}, staff_user_id=admin.id, timestamp=new)
        w_old = mk(WebhookLog, source='rc', event_type='rc_old', received_at=old)
        w_new = mk(WebhookLog, source='rc', event_type='rc_new', received_at=new)
        n_old = mk(NotificationLog, sent_at=old)
        n_new = mk(NotificationLog, sent_at=new)
        db.session.add_all([a_old, a_new, w_old, w_new, n_old, n_new])
        db.session.commit()
        ids = {'a_old': a_old.id, 'a_new': a_new.id, 'w_old': w_old.id, 'w_new': w_new.id,
               'n_old': n_old.id, 'n_new': n_new.id}
        min_ts_before = db.session.query(db.func.min(AuditLog.timestamp)).scalar()
        counts_before = {'audit': db.session.query(AuditLog).count(),
                         'webhook': db.session.query(WebhookLog).count(),
                         'notification': db.session.query(NotificationLog).count()}
    print('D11 population    : payments=%s charges=%s   audit_logs baseline=%d' % (d11_pay, d11_chg, audit_baseline))
    print('fixtures          : %s  counts=%s' % (ids, counts_before))
    print('-' * 130)

    # -- job identity ---------------------------------------------------
    job = scheduler.get_job('log_pruning_job')
    job_ids = sorted(j.id for j in scheduler.get_jobs())
    check('RC-01', 'log_pruning_job is registered', True, job is not None, 'jobs=%s' % job_ids)
    fields = {f.name: str(f) for f in job.trigger.fields} if job is not None else {}
    check('RC-02', 'job trigger unchanged: cron hour=4 minute=0',
          ('4', '0'), (fields.get('hour'), fields.get('minute')))
    check('RC-03', 'job misfire_grace_time unchanged (3600)', 3600, getattr(job, 'misfire_grace_time', None))
    check('RC-04', 'job function is the _prune_old_logs closure', '_prune_old_logs',
          getattr(job.func, '__name__', None))

    # -- run the real job function once ---------------------------------
    err = None
    try:
        job.func()
    except Exception as exc:              # pragma: no cover - must not happen
        err = '%s: %s' % (exc.__class__.__name__, exc)
    check('RC-05', 'pruning job executes without raising', None, err)

    with app.app_context():
        a_old_alive = db.session.get(AuditLog, ids['a_old']) is not None
        a_new_alive = db.session.get(AuditLog, ids['a_new']) is not None
        w_old_alive = db.session.get(WebhookLog, ids['w_old']) is not None
        w_new_alive = db.session.get(WebhookLog, ids['w_new']) is not None
        n_old_alive = db.session.get(NotificationLog, ids['n_old']) is not None
        n_new_alive = db.session.get(NotificationLog, ids['n_new']) is not None
        counts_after = {'audit': db.session.query(AuditLog).count(),
                        'webhook': db.session.query(WebhookLog).count(),
                        'notification': db.session.query(NotificationLog).count()}
        min_ts_after = db.session.query(db.func.min(AuditLog.timestamp)).scalar()
    check('RC-06', 'audit_logs row older than 90 days SURVIVES the prune', True, a_old_alive)
    check('RC-07', 'audit_logs row count unchanged by the prune', counts_before['audit'], counts_after['audit'])
    check('RC-08', 'MIN(audit_logs.timestamp) did not advance', min_ts_before, min_ts_after)
    check('RC-09', 'old webhook row is still pruned', False, w_old_alive)
    check('RC-10', 'old notification row is still pruned', False, n_old_alive)
    check('RC-11', 'recent rows all survive', (True, True, True), (a_new_alive, w_new_alive, n_new_alive))
    check('RC-12', 'webhook / notification counts each dropped by exactly one',
          (counts_before['webhook'] - 1, counts_before['notification'] - 1),
          (counts_after['webhook'], counts_after['notification']))

    # -- ordinary audit writing unaffected --------------------------------
    with app.app_context():
        r1 = db.session.query(Reservation).order_by(Reservation.id).first()
        r1.status = 'CheckedIn'
        db.session.commit()
        rid = r1.id
        posted_before = db.session.query(AuditLog).filter_by(entity_type='Payment', action='posted').count()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True
    r = c.post('/api/reservation/%d/add-payment' % rid, json={'amount': 10.0})
    with app.app_context():
        posted_after = db.session.query(AuditLog).filter_by(entity_type='Payment', action='posted').count()
    check('RC-13', 'strict audit coupling still writes its row (add_payment)',
          (200, posted_before + 1), (r.status_code, posted_after))

    # -- negative control: the PRE-CHANGE loop would have deleted it -------
    with app.app_context():
        alive_before_legacy = db.session.get(AuditLog, ids['a_old']) is not None
        cutoff = datetime.utcnow() - timedelta(days=90)
        legacy_deleted = 0
        for LogModel, ts_col in [(AuditLog, AuditLog.timestamp),
                                 (WebhookLog, WebhookLog.received_at),
                                 (NotificationLog, NotificationLog.sent_at)]:
            legacy_deleted += LogModel.query.filter(ts_col < cutoff).delete()
        db.session.commit()
        alive_after_legacy = db.session.get(AuditLog, ids['a_old']) is not None
    check('RC-N1', 'NEGATIVE CONTROL: pre-change loop deletes the old audit row',
          (True, False, 1), (alive_before_legacy, alive_after_legacy, legacy_deleted),
          'proves RC-06 is capable of failing')

    # -- D11 / production -------------------------------------------------
    with app.app_context():
        end_pay = sorted(r[0] for r in db.session.query(Payment.id).filter(Payment.folio_id.is_(None)).all())
        end_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id).filter(ExtraCharge.folio_id.is_(None)).all())
        end_vals = {'p:%d' % p.id: float(p.amount) for p in db.session.query(Payment).filter(Payment.id.in_(d11_pay))}
        end_vals.update({'c:%d' % c.id: float(c.amount) for c in db.session.query(ExtraCharge).filter(ExtraCharge.id.in_(d11_chg))})
    check('D11-01', 'D11 id sets unchanged', (d11_pay, d11_chg), (end_pay, end_chg))
    check('D11-02', 'D11 amounts unchanged', d11_vals, end_vals)
    prod_after = sha256(PRODUCTION_DB)
    check('PROD-01', 'production database unchanged', prod_before, prod_after)
    check('PROD-02', 'production size 733,184 B', 733184, os.path.getsize(PRODUCTION_DB))

    passed = sum(1 for x in results if x['pass'])
    print('-' * 130)
    print('RESULT: %d / %d passed   routes=%d' % (passed, len(results), route_count))
    print('=' * 130)
    payload = {'directive': 'FinalGrid Phase 2 retention control (FD-P2-02)',
               'started_at': started.isoformat(timespec='seconds'),
               'finished_at': datetime.now().isoformat(timespec='seconds'),
               'copy_path': handle.copy_path, 'copy_method': handle.method,
               'route_count': route_count, 'job_ids': job_ids,
               'production_sha256_before': prod_before, 'production_sha256_after': prod_after,
               'anchor_matches': prod_before == FROZEN_ANCHOR, 'read_only_verified': prod_before == prod_after,
               'd11_payments': d11_pay, 'd11_extra_charges': d11_chg,
               'cases_total': len(results), 'cases_passed': passed,
               'verdict': 'PASS' if passed == len(results) else 'FAIL', 'results': results}
    with open(os.path.join(HERE, 'retention_test_result.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
    print('retention_test_result.json written')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
