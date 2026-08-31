# -*- coding: utf-8 -*-
"""Phase 2a — negative authorization matrix for the folio blueprint.

Finding R7. Proves that every unauthorized role is refused on every folio
endpoint, that a refusal changes no data, that authorized mutations are
recorded, and that a mutation whose audit record fails does not commit.

Written in the idiom this repository already uses for verification: declare the
expected value, assert against the actual, print pass/fail per case, and run
the whole thing against a disposable copy produced by verification.dbcopy so
production is never a test target. pytest is deliberately not used — adding a
test framework is Phase 6 work and installing dependencies is out of scope.

    venv\\Scripts\\python.exe verification\\evidence\\20260831_phase2a_folio_authz\\verify.py

Constraints honoured, per the Phase 2a directive:
  * production is opened read-only, hashed before and after;
  * the 6 payments and 2 charges carrying a pre-existing NULL folio_id are
    never touched, on any database (D11 freeze) — fixtures are created fresh;
  * no schema change, no migration.
"""
from __future__ import annotations

import io
import json
import os
import sys
import hashlib
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from verification.dbcopy import make_copy                      # noqa: E402
from verification.config import PRODUCTION_DB                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN_ANCHOR = '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2'

ROLES = ('Admin', 'Manager', 'FrontDesk', 'Accountant', 'Housekeeping')
ALLOWED = ('Admin', 'Manager')          # every folio endpoint, per the directive

results = []            # (case_id, endpoint, actor, expect, got, effect_ok, ok)


def check(case_id, endpoint, actor, expect_status, got_status,
          effect_expected, effect_actual):
    ok = (got_status == expect_status) and (effect_expected == effect_actual)
    results.append({
        'case': case_id, 'endpoint': endpoint, 'actor': actor,
        'expect_status': expect_status, 'got_status': got_status,
        'expect_effect': effect_expected, 'got_effect': effect_actual,
        'pass': ok,
    })
    print('%-5s %-4s %-24s %-16s expect=%-3s got=%-3s  %s'
          % ('OK' if ok else 'FAIL', case_id, endpoint, actor,
             expect_status, got_status,
             'no-change' if effect_actual == effect_expected
             else 'EFFECT MISMATCH: %r vs %r' % (effect_expected, effect_actual)))
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
    print('=' * 100)
    print('PHASE 2a — FOLIO AUTHORIZATION MATRIX')
    print('=' * 100)
    print('production        : %s' % PRODUCTION_DB)
    print('sha256 before     : %s' % prod_before)
    print('frozen anchor     : %s' % ('MATCHES' if prod_before == FROZEN_ANCHOR
                                      else '*** MISMATCH ***'))

    handle = make_copy(name='phase2a_authz.db')
    print('disposable copy   : %s  (%s)' % (handle.copy_path, handle.method))
    print('-' * 100)

    os.environ['DATABASE_URL'] = 'sqlite:///' + handle.copy_path.replace('\\', '/')
    os.environ['FLASK_ENV'] = 'production'

    from app import create_app                                  # noqa: E402
    from app.models import (db, User, Reservation, Folio, ExtraCharge,   # noqa: E402
                            Payment, PaymentMode, AuditLog)

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    # ── Fixtures, all created fresh on the copy ──────────────────────────────
    with app.app_context():
        # Capture the exact identities of the pre-existing unattributed rows.
        # D11 freezes these specific rows; a count comparison would not notice
        # one being attributed while a fixture became NULL in its place.
        orig_null_pay = sorted(r_[0] for r_ in db.session.query(Payment.id)
                               .filter(Payment.folio_id.is_(None)).all())
        orig_null_chg = sorted(r_[0] for r_ in db.session.query(ExtraCharge.id)
                               .filter(ExtraCharge.folio_id.is_(None)).all())
        untouched_pay = len(orig_null_pay)
        untouched_chg = len(orig_null_chg)
        print('pre-existing NULL folio_id  payments=%d charges=%d  (D11 freeze — '
              'must be identical at the end)' % (untouched_pay, untouched_chg))

        users = {}
        for role in ROLES:
            u = User(username='p2a_%s' % role.lower(), full_name='P2A %s' % role,
                     role=role, is_active=True)
            u.set_password('p2a-test-password')
            db.session.add(u)
            db.session.flush()
            users[role] = u.id

        folio_a = Folio.query.order_by(Folio.id).first()
        if folio_a is None:
            raise SystemExit('FATAL: no folio in the copy to work from')
        rid = folio_a.reservation_id

        folio_b = Folio.query.filter_by(reservation_id=rid,
                                        folio_letter='B').first()
        if folio_b is None:
            folio_b = Folio(reservation_id=rid, folio_letter='B', label='Company')
            db.session.add(folio_b)
            db.session.flush()

        fix_charge = ExtraCharge(reservation_id=rid, description='P2A fixture',
                                 amount=100, folio_id=None)
        mode = PaymentMode.query.first()
        fix_payment = Payment(reservation_id=rid, payment_mode_id=mode.id,
                              amount=50, folio_id=None)
        db.session.add_all([fix_charge, fix_payment])
        db.session.commit()

        ids = {'reservation': rid, 'folio_a': folio_a.id, 'folio_b': folio_b.id,
               'charge': fix_charge.id, 'payment': fix_payment.id}
        print('fixtures          : %s' % ids)
        print('-' * 100)

    def client_as(role):
        c = app.test_client()
        if role is not None:
            with c.session_transaction() as sess:
                sess['_user_id'] = str(users[role])
                sess['_fresh'] = True
        return c

    def folio_id_of(model, pk):
        with app.app_context():
            row = db.session.get(model, pk)
            return None if row is None else row.folio_id

    def audit_count():
        with app.app_context():
            return db.session.query(AuditLog).count()

    EP = [
        ('list_folios', 'GET', '/api/reservation/%d/folios' % ids['reservation'], None),
        ('create_folio', 'POST', '/api/reservation/%d/folios' % ids['reservation'],
         {'label': 'Probe', 'folio_letter': 'Z'}),
        ('transfer_charge', 'POST', '/api/folio/%d/transfer-charge' % ids['folio_b'],
         {'charge_id': ids['charge']}),
        ('transfer_payment', 'POST', '/api/folio/%d/transfer-payment' % ids['folio_b'],
         {'payment_id': ids['payment']}),
    ]

    n = 0
    print('NEGATIVE MATRIX — 4 endpoints x 5 roles')
    print('-' * 100)
    for name, method, url, payload in EP:
        for role in ROLES:
            # Only unauthorized roles run here; authorized ones are exercised
            # afterwards so a successful mutation cannot mask a later refusal.
            if role in ALLOWED:
                continue
            n += 1
            before_c = folio_id_of(ExtraCharge, ids['charge'])
            before_p = folio_id_of(Payment, ids['payment'])
            c = client_as(role)
            r = c.get(url) if method == 'GET' else c.post(url, json=payload)
            after_c = folio_id_of(ExtraCharge, ids['charge'])
            after_p = folio_id_of(Payment, ids['payment'])
            check('T%02d' % n, name, role, 403, r.status_code,
                  (before_c, before_p), (after_c, after_p))

    print('-' * 100)
    print('UNAUTHENTICATED — 4 cases')
    print('-' * 100)
    for name, method, url, payload in EP:
        n += 1
        before = (folio_id_of(ExtraCharge, ids['charge']),
                  folio_id_of(Payment, ids['payment']))
        c = client_as(None)
        r = c.get(url) if method == 'GET' else c.post(url, json=payload)
        after = (folio_id_of(ExtraCharge, ids['charge']),
                 folio_id_of(Payment, ids['payment']))
        check('T%02d' % n, name, 'unauthenticated', 401, r.status_code,
              before, after)

    print('-' * 100)
    print('AUTHORIZED PATHS — 8 cases (behaviour must be unchanged)')
    print('-' * 100)
    for role in ALLOWED:
        n += 1
        c = client_as(role)
        r = c.get('/api/reservation/%d/folios' % ids['reservation'])
        check('T%02d' % n, 'list_folios', role, 200, r.status_code, True,
              isinstance(r.get_json(), dict) and 'folios' in r.get_json())

    # transfer_charge / transfer_payment, authorized: the fixture rows move and
    # an audit row is written. The pre-existing NULL rows are never used here.
    n += 1
    a0 = audit_count()
    c = client_as('Manager')
    r = c.post('/api/folio/%d/transfer-charge' % ids['folio_b'],
               json={'charge_id': ids['charge']})
    moved = folio_id_of(ExtraCharge, ids['charge']) == ids['folio_b']
    check('T%02d' % n, 'transfer_charge', 'Manager (authorized)', 200,
          r.status_code, True, moved)
    n += 1
    check('T%02d' % n, 'transfer_charge', 'audit row written', True, True,
          True, audit_count() == a0 + 1)

    n += 1
    a0 = audit_count()
    r = c.post('/api/folio/%d/transfer-payment' % ids['folio_b'],
               json={'payment_id': ids['payment']})
    moved = folio_id_of(Payment, ids['payment']) == ids['folio_b']
    check('T%02d' % n, 'transfer_payment', 'Manager (authorized)', 200,
          r.status_code, True, moved)
    n += 1
    check('T%02d' % n, 'transfer_payment', 'audit row written', True, True,
          True, audit_count() == a0 + 1)

    n += 1
    a0 = audit_count()
    r = c.post('/api/reservation/%d/folios' % ids['reservation'],
               json={'label': 'Agent', 'folio_letter': 'Y'})
    check('T%02d' % n, 'create_folio', 'Manager (authorized)', 201,
          r.status_code, True, audit_count() == a0 + 1)

    print('-' * 100)
    print('CONTROL PROPERTIES')
    print('-' * 100)

    # Refusal is recorded.
    n += 1
    with app.app_context():
        d0 = db.session.query(AuditLog).filter_by(
            action='folio_access_denied').count()
    client_as('Housekeeping').post(
        '/api/folio/%d/transfer-charge' % ids['folio_b'],
        json={'charge_id': ids['charge']})
    with app.app_context():
        d1 = db.session.query(AuditLog).filter_by(
            action='folio_access_denied').count()
    check('T%02d' % n, 'denial recorded', 'Housekeeping', True, True,
          True, d1 == d0 + 1)

    # Fail-closed: an endpoint absent from the role map is denied to everyone,
    # including Admin. This is the property that protects routes added later.
    n += 1
    from app import folio as folio_mod
    saved = dict(folio_mod._FOLIO_ROLES)
    folio_mod._FOLIO_ROLES.pop('folio.list_folios')
    r = client_as('Admin').get('/api/reservation/%d/folios' % ids['reservation'])
    folio_mod._FOLIO_ROLES.clear()
    folio_mod._FOLIO_ROLES.update(saved)
    check('T%02d' % n, 'fail-closed', 'Admin, endpoint unmapped', 403,
          r.status_code, True, True)

    # Guard commissioning (Principle 9): with the guard neutralised the very
    # same request succeeds, which proves the refusals above were produced by
    # the guard and not by something incidental.
    n += 1
    saved_roles = dict(folio_mod._FOLIO_ROLES)
    folio_mod._FOLIO_ROLES.update(
        {k: ROLES for k in saved_roles})       # temporarily allow every role
    r = client_as('Housekeeping').get(
        '/api/reservation/%d/folios' % ids['reservation'])
    folio_mod._FOLIO_ROLES.clear()
    folio_mod._FOLIO_ROLES.update(saved_roles)
    check('T%02d' % n, 'guard commissioned', 'Housekeeping, guard relaxed', 200,
          r.status_code, True, True)

    # Audit coupling: if the audit row cannot be written the mutation must not
    # commit. _audited is forced to fail for one call.
    n += 1
    fresh_charge_id = None
    with app.app_context():
        fc = ExtraCharge(reservation_id=ids['reservation'],
                         description='P2A audit-coupling fixture',
                         amount=25, folio_id=None)
        db.session.add(fc)
        db.session.commit()
        fresh_charge_id = fc.id
    real_audited = folio_mod._audited
    folio_mod._audited = lambda *a, **k: False
    r = client_as('Manager').post(
        '/api/folio/%d/transfer-charge' % ids['folio_b'],
        json={'charge_id': fresh_charge_id})
    folio_mod._audited = real_audited
    still_null = folio_id_of(ExtraCharge, fresh_charge_id) is None
    check('T%02d' % n, 'audit coupling', 'audit fails -> rollback', 500,
          r.status_code, True, still_null)

    # NULL-source tolerance is unchanged: an authorized transfer of a row whose
    # folio_id is NULL still behaves exactly as before.
    n += 1
    with app.app_context():
        nc = ExtraCharge(reservation_id=ids['reservation'],
                         description='P2A null-source fixture',
                         amount=10, folio_id=None)
        db.session.add(nc)
        db.session.commit()
        null_charge_id = nc.id
    r = client_as('Admin').post(
        '/api/folio/%d/transfer-charge' % ids['folio_b'],
        json={'charge_id': null_charge_id})
    check('T%02d' % n, 'NULL-source transfer', 'Admin (authorized)', 200,
          r.status_code, True,
          folio_id_of(ExtraCharge, null_charge_id) == ids['folio_b'])

    # ── D11 freeze: the pre-existing NULL rows must be exactly as they were ──
    print('-' * 100)
    n += 1
    with app.app_context():
        still_null_pay = sorted(r_[0] for r_ in db.session.query(Payment.id)
                                .filter(Payment.id.in_(orig_null_pay),
                                        Payment.folio_id.is_(None)).all())
        still_null_chg = sorted(r_[0] for r_ in db.session.query(ExtraCharge.id)
                                .filter(ExtraCharge.id.in_(orig_null_chg),
                                        ExtraCharge.folio_id.is_(None)).all())
    check('T%02d' % n, 'D11 freeze', 'pre-existing NULLs untouched',
          (orig_null_pay, orig_null_chg), (still_null_pay, still_null_chg),
          True, True)
    print('  payment ids frozen NULL : %s -> %s' % (orig_null_pay, still_null_pay))
    print('  charge  ids frozen NULL : %s -> %s' % (orig_null_chg, still_null_chg))

    # ── Production untouched ────────────────────────────────────────────────
    prod_after = sha256(PRODUCTION_DB)
    passed = sum(1 for r_ in results if r_['pass'])
    total = len(results)

    print('=' * 100)
    print('sha256 after      : %s' % prod_after)
    print('read-only         : %s' % ('VERIFIED — production byte-identical'
                                      if prod_before == prod_after
                                      else '*** PRODUCTION CHANGED ***'))
    print('cases             : %d passed / %d total' % (passed, total))
    print('VERDICT           : %s' % ('PASS' if passed == total
                                      and prod_before == prod_after else 'FAIL'))
    print('=' * 100)

    payload = {
        'phase': '2a',
        'finding': 'R7',
        'started_at': started.isoformat(timespec='seconds'),
        'finished_at': datetime.now().isoformat(timespec='seconds'),
        'production_db': PRODUCTION_DB,
        'production_sha256_before': prod_before,
        'production_sha256_after': prod_after,
        'frozen_anchor': FROZEN_ANCHOR,
        'anchor_matches': prod_before == FROZEN_ANCHOR,
        'read_only_verified': prod_before == prod_after,
        'copy_method': handle.method,
        'role_map': {k: list(v) for k, v in
                     __import__('app.folio', fromlist=['x'])._FOLIO_ROLES.items()},
        'cases_total': total,
        'cases_passed': passed,
        'verdict': 'PASS' if passed == total and prod_before == prod_after else 'FAIL',
        'results': results,
    }
    with io.open(os.path.join(HERE, 'result.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write('\n')
    print('wrote result.json')
    return 0 if payload['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
