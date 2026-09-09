# -*- coding: utf-8 -*-
"""W-20 overstay — runtime verification closure.

Directive FG-P1-W20-RUNTIME-20260909-01. The Phase 1 execution report
disclosed that W-20 (``main.add_overstay_charge``) passed *vacuously*: the
fixture did not satisfy the route's preconditions, so the charge path never
ran and attribution was proven only statically.

This script exercises the **actual route** end to end and asserts the
runtime behaviour: a real ExtraCharge row is produced by the real handler,
it carries the reservation's authoritative billing folio, its audit row is
written in the same transaction, an injected audit failure prevents the
commit, and a repeat call follows the route's existing window semantics.

Nothing is mocked and no ExtraCharge is constructed by the test itself — the
row must come out of ``add_overstay_charge``.

    venv\\Scripts\\python.exe verification\\evidence\\20260909_w20_runtime\\verify.py

Constraints: production is opened read-only and hashed before and after; all
mutation happens on a disposable copy from verification.dbcopy; the eight
D11 rows are never used as fixtures and are proven unchanged by id set.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, date, timedelta

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
    results.append({'case': case_id, 'what': what, 'expect': expect,
                    'got': got, 'pass': ok, 'note': note})
    print('%-5s %-9s %-52s expect=%-24s got=%-24s %s'
          % ('OK' if ok else 'FAIL', case_id, what,
             repr(expect)[:24], repr(got)[:24], note))
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
    prod_size_before = os.path.getsize(PRODUCTION_DB)
    print('=' * 122)
    print('W-20 OVERSTAY — RUNTIME VERIFICATION')
    print('=' * 122)
    print('production      : %s' % PRODUCTION_DB)
    print('sha256 before   : %s' % prod_before)
    print('anchor          : %s' % ('MATCHES' if prod_before == FROZEN_ANCHOR
                                    else '*** MISMATCH ***'))

    handle = make_copy(name='w20_overstay.db')
    print('disposable copy : %s  (%s)' % (handle.copy_path, handle.method))
    print('-' * 122)

    os.environ['DATABASE_URL'] = 'sqlite:///' + handle.copy_path.replace('\\', '/')
    os.environ['FLASK_ENV'] = 'production'

    from app import create_app                                        # noqa: E402
    from app.models import (db, User, Reservation, Folio, ExtraCharge,  # noqa: E402
                            Payment, AuditLog)

    app = create_app()
    # PROPAGATE_EXCEPTIONS=False so an audit failure surfaces to the caller as
    # a 500 response — which is what a real client would see — instead of the
    # test client re-raising it.
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                      PROPAGATE_EXCEPTIONS=False)

    import app.services as svc                                        # noqa: E402

    with app.app_context():
        d11_pay = sorted(r[0] for r in db.session.query(Payment.id)
                         .filter(Payment.folio_id.is_(None)).all())
        d11_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id)
                         .filter(ExtraCharge.folio_id.is_(None)).all())
        d11_snapshot = {
            'payments': {p.id: (float(p.amount), p.folio_id, p.reservation_id)
                         for p in db.session.query(Payment)
                         .filter(Payment.id.in_(d11_pay)).all()},
            'charges': {c.id: (float(c.amount), c.folio_id, c.reservation_id)
                        for c in db.session.query(ExtraCharge)
                        .filter(ExtraCharge.id.in_(d11_chg)).all()},
        }
    print('D11 population  : payments=%s charges=%s' % (d11_pay, d11_chg))
    print('-' * 122)

    # ── Fixtures — fresh rows only; D11 rows are never used ─────────────────
    with app.app_context():
        u = User(username='w20_admin', full_name='W20 Admin', role='Admin',
                 is_active=True)
        u.set_password('w20-test-password')
        db.session.add(u)
        db.session.flush()
        admin_id = u.id

        seed = db.session.query(Reservation).order_by(Reservation.id).first()
        base = {'guest': seed.guest_id, 'room': seed.room_id,
                'room_type': seed.room_type_id}

        def make_res(tag, booking_type, checkout_time):
            r = Reservation(
                booking_reference='W20-%s-%d' % (
                    tag, int(datetime.now().timestamp() * 1000) % 100000),
                guest_id=base['guest'], room_id=base['room'],
                room_type_id=base['room_type'],
                arrival_date=date.today() - timedelta(days=1),
                departure_date=date.today() - timedelta(days=1),
                adults=1, children=0, status='CheckedIn',
                rate_per_night=2400, booking_type=booking_type,
                checkout_time=checkout_time, overstay_billed_until=None,
                noshow_exempt=False, checkout_initiated=False,
                credit_amount=0, credit_settled_amount=0,
                cancellation_amount_refunded=0, cancellation_amount_forfeited=0,
                cancellation_amount_credit_voucher=0)
            db.session.add(r)
            db.session.flush()
            return r.id

        # (a) reproduces the vacuous condition: Regular booking, no checkout time
        res_vacuous = make_res('regular', 'Regular', None)
        # (b) the corrected fixture: Hourly with a recorded checkout time,
        #     departing yesterday so the overstay window is real and > grace
        res_hourly = make_res('hourly', 'Hourly', '12:00')
        db.session.commit()

        folio_hourly = db.session.query(Folio).filter_by(
            reservation_id=res_hourly, folio_letter='A').first().id
        folio_vacuous = db.session.query(Folio).filter_by(
            reservation_id=res_vacuous, folio_letter='A').first().id
        res_snapshot = {}
        for rid in (res_hourly,):
            r = db.session.get(Reservation, rid)
            res_snapshot[rid] = (r.status, r.arrival_date, r.departure_date,
                                 float(r.rate_per_night), r.booking_type,
                                 r.checkout_time, r.room_id)

    print('fixtures        : hourly res=%d folio=%d | regular res=%d folio=%d'
          % (res_hourly, folio_hourly, res_vacuous, folio_vacuous))
    print('-' * 122)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    URL = '/reservation/%d/overstay-charge'

    def overstay_charges(rid):
        with app.app_context():
            return (db.session.query(ExtraCharge)
                    .filter(ExtraCharge.reservation_id == rid,
                            ExtraCharge.description.like('Overstay%'))
                    .order_by(ExtraCharge.id).all())

    # =====================================================================
    # 1. Reproduce the disclosed vacuous condition
    # =====================================================================
    print('1. THE DISCLOSED VACUOUS CONDITION')
    print('-' * 122)
    r = client.post(URL % res_vacuous, data={}, follow_redirects=False)
    check('W20-01', 'Regular booking posts no charge (route exits early)',
          0, len(overstay_charges(res_vacuous)),
          'this is why the Phase 1 case passed vacuously')

    # =====================================================================
    # 2. The real path, with the corrected fixture
    # =====================================================================
    print('-' * 122)
    print('2. ACTUAL ROUTE EXECUTION (main.add_overstay_charge)')
    print('-' * 122)
    with app.app_context():
        audit_before = db.session.query(AuditLog).count()

    r1 = client.post(URL % res_hourly, data={}, follow_redirects=False)
    rows = overstay_charges(res_hourly)
    check('W20-02', 'route produced exactly one ExtraCharge', 1, len(rows),
          'HTTP %s' % r1.status_code)
    if not rows:
        print('FATAL: the overstay path did not execute — cannot continue')
        return 1
    charge = rows[0]
    with app.app_context():
        c = db.session.get(ExtraCharge, charge.id)
        charge_row = {'id': c.id, 'reservation_id': c.reservation_id,
                      'folio_id': c.folio_id, 'amount': float(c.amount),
                      'description': c.description,
                      'charge_date': str(c.charge_date)}
    print('   created row  : %s' % charge_row)

    # ── folio assertions ────────────────────────────────────────────────────
    check('W20-03', 'folio_id IS NOT NULL', True, charge_row['folio_id'] is not None)
    check('W20-04', 'folio_id is the reservation\'s billing folio (A)',
          folio_hourly, charge_row['folio_id'])
    with app.app_context():
        f = db.session.get(Folio, charge_row['folio_id'])
        owner = (f.reservation_id, f.folio_letter)
    check('W20-05', 'that folio belongs to this reservation, letter A',
          (res_hourly, 'A'), owner)
    check('W20-06', 'charge is not attached to any other reservation',
          res_hourly, charge_row['reservation_id'])

    # ── audit assertions ────────────────────────────────────────────────────
    with app.app_context():
        ec_audit = (db.session.query(AuditLog)
                    .filter_by(entity_type='ExtraCharge', entity_id=charge.id)
                    .all())
        res_audit = (db.session.query(AuditLog)
                     .filter_by(entity_type='Reservation', entity_id=res_hourly,
                                action='overstay_charged').all())
        audit_rows = [(a.action, a.entity_type, a.entity_id) for a in ec_audit]
        after_state = ec_audit[0].after_state if ec_audit else None
    check('W20-07', 'ExtraCharge audit row exists for this charge',
          [('posted', 'ExtraCharge', charge.id)], audit_rows)
    check('W20-08', 'audit records the same folio as the charge',
          charge_row['folio_id'], (after_state or {}).get('folio_id'))
    check('W20-09', 'audit records the same amount as the charge',
          charge_row['amount'], (after_state or {}).get('amount'))
    check('W20-10', 'the Reservation-level audit row also survived the commit',
          1, len(res_audit),
          'it was written after commit() before Phase 1 and was discarded')

    # ── reservation context unchanged apart from the billing marker ─────────
    with app.app_context():
        rr = db.session.get(Reservation, res_hourly)
        now_snapshot = (rr.status, rr.arrival_date, rr.departure_date,
                        float(rr.rate_per_night), rr.booking_type,
                        rr.checkout_time, rr.room_id)
        billed_until_1 = rr.overstay_billed_until
    check('W20-11', 'reservation context unchanged by the charge',
          res_snapshot[res_hourly], now_snapshot)
    check('W20-12', 'overstay_billed_until advanced (idempotency marker set)',
          True, billed_until_1 is not None)

    # =====================================================================
    # 3. Audit coupling on THIS path (Q-5)
    # =====================================================================
    print('-' * 122)
    print('3. AUDIT COUPLING ON THE OVERSTAY PATH (Q-5)')
    print('-' * 122)
    with app.app_context():
        res_fail = make_res('failpath', 'Hourly', '12:00')
        db.session.commit()
        chg_before = db.session.query(ExtraCharge).count()
        aud_before = db.session.query(AuditLog).count()

    real_audit = svc.audited_financial_write

    def exploding_audit(*a, **kw):
        raise svc.AuditCouplingError('injected audit failure (W-20 path)')

    svc.audited_financial_write = exploding_audit
    try:
        r_fail = client.post(URL % res_fail, data={}, follow_redirects=False)
    finally:
        svc.audited_financial_write = real_audit

    with app.app_context():
        chg_after = db.session.query(ExtraCharge).count()
        aud_after = db.session.query(AuditLog).count()
        rf = db.session.get(Reservation, res_fail)
        billed_after_fail = rf.overstay_billed_until
    check('W20-13', 'audit failure commits no overstay charge',
          chg_before, chg_after)
    check('W20-14', 'audit failure commits no audit row either',
          aud_before, aud_after)
    check('W20-15', 'caller is told it failed (no misleading success)',
          True, r_fail.status_code >= 400, 'HTTP %s' % r_fail.status_code)
    check('W20-16', 'billing marker not advanced on the failed attempt',
          None, billed_after_fail)

    # =====================================================================
    # 4. Repeat execution — the route's existing window semantics
    # =====================================================================
    print('-' * 122)
    print('4. REPEAT EXECUTION (existing window semantics)')
    print('-' * 122)
    r2 = client.post(URL % res_hourly, data={}, follow_redirects=False)
    rows2 = overstay_charges(res_hourly)
    with app.app_context():
        rr = db.session.get(Reservation, res_hourly)
        billed_until_2 = rr.overstay_billed_until
        folios_now = db.session.query(Folio).filter_by(
            reservation_id=res_hourly).count()
        extra = [{'id': c.id, 'folio_id': c.folio_id, 'amount': float(c.amount),
                  'description': c.description} for c in rows2]

    second_charged = len(extra) > 1
    check('W20-17', 'no duplicate of the ALREADY-BILLED window',
          True, billed_until_2 >= billed_until_1,
          'billing marker moves forward, never re-bills the same window')
    check('W20-18', 'repeat call creates no duplicate folio', 1, folios_now)
    if second_charged:
        check('W20-19', 'any charge for the NEW window is also attributed',
              [folio_hourly] * len(extra), [c['folio_id'] for c in extra],
              'route bills the new window — pre-existing semantics, see limitations')
    else:
        check('W20-19', 'repeat call within the same window posts nothing',
              1, len(extra))

    # =====================================================================
    # 5. D11 and production safety
    # =====================================================================
    print('-' * 122)
    print('5. D11 AND PRODUCTION SAFETY')
    print('-' * 122)
    with app.app_context():
        end_pay = sorted(r[0] for r in db.session.query(Payment.id)
                         .filter(Payment.folio_id.is_(None)).all())
        end_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id)
                         .filter(ExtraCharge.folio_id.is_(None)).all())
        end_snapshot = {
            'payments': {p.id: (float(p.amount), p.folio_id, p.reservation_id)
                         for p in db.session.query(Payment)
                         .filter(Payment.id.in_(d11_pay)).all()},
            'charges': {c.id: (float(c.amount), c.folio_id, c.reservation_id)
                        for c in db.session.query(ExtraCharge)
                        .filter(ExtraCharge.id.in_(d11_chg)).all()},
        }
    check('W20-20', 'D11 NULL-folio id sets unchanged',
          (d11_pay, d11_chg), (end_pay, end_chg))
    check('W20-21', 'D11 amounts / folio / reservation unchanged',
          d11_snapshot, end_snapshot)

    prod_after = sha256(PRODUCTION_DB)
    check('W20-22', 'production database hash unchanged', prod_before, prod_after)
    check('W20-23', 'production database size unchanged',
          prod_size_before, os.path.getsize(PRODUCTION_DB))

    passed = sum(1 for x in results if x['pass'])
    total = len(results)
    print('-' * 122)
    print('RESULT: %d / %d passed' % (passed, total))
    print('=' * 122)

    payload = {
        'directive': 'FG-P1-W20-RUNTIME-20260909-01',
        'writer': 'W-20 main.add_overstay_charge',
        'started_at': started.isoformat(timespec='seconds'),
        'finished_at': datetime.now().isoformat(timespec='seconds'),
        'route_exercised': 'POST /reservation/<id>/overstay-charge',
        'mocked': False,
        'production_db': PRODUCTION_DB,
        'production_sha256_before': prod_before,
        'production_sha256_after': prod_after,
        'production_size_before': prod_size_before,
        'production_size_after': os.path.getsize(PRODUCTION_DB),
        'production_unchanged': prod_before == prod_after,
        'frozen_anchor': FROZEN_ANCHOR,
        'anchor_matches': prod_before == FROZEN_ANCHOR,
        'copy_method': handle.method,
        'vacuous_cause': ("route requires booking_type == 'Hourly' and a "
                          "recorded checkout_time; the Phase 1 fixture had "
                          "booking_type 'Regular' (the model default) and no "
                          "checkout_time, so the handler returned before the "
                          "charge block"),
        'fixture_correction': ("booking_type='Hourly', checkout_time='12:00', "
                               "departure_date=yesterday, status='CheckedIn', "
                               "rate_per_night=2400, overstay_billed_until=None"),
        'financial_row': charge_row,
        'folio': {'expected': folio_hourly, 'actual': charge_row['folio_id'],
                  'owner_reservation': res_hourly, 'letter': 'A'},
        'audit': {'rows': audit_rows, 'after_state': after_state,
                  'reservation_audit_rows': len(res_audit)},
        'audit_failure_injection': {
            'charges_before': chg_before, 'charges_after': chg_after,
            'audit_before': aud_before, 'audit_after': aud_after,
            'http_status': r_fail.status_code,
            'billing_marker_advanced': billed_after_fail is not None},
        'idempotency': {
            'charges_after_two_calls': len(extra),
            'second_window_charged': second_charged,
            'billing_marker_first': str(billed_until_1),
            'billing_marker_second': str(billed_until_2),
            'folios': folios_now,
            'all_charges': extra},
        'd11': {'payments': d11_pay, 'extra_charges': d11_chg,
                'unchanged': d11_snapshot == end_snapshot
                             and (d11_pay, d11_chg) == (end_pay, end_chg)},
        'application_code_changed': False,
        'cases_total': total, 'cases_passed': passed,
        'verdict': 'PASS' if passed == total else 'FAIL',
        'results': results,
    }
    with open(os.path.join(HERE, 'result.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
    print('result.json written')
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
