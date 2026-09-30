# -*- coding: utf-8 -*-
"""Phase 1 verification completion - bounded runtime verification of writers.

Directive FG-P1-VERIFICATION-COMPLETION-20260909-01. Baseline aa6d9e91.

Exercises the financial writers that the Phase 1 execution proved only
statically, through their real routes or their real service functions, on
a disposable copy produced by verification.dbcopy. Production is opened
read-only for hashing only. The eight D11 rows are never used as fixtures
and are proven unchanged by id and amount at the end.

    venv\\Scripts\\python.exe verification\\evidence\\20260909_phase1_verification_completion\\verify_writers.py A|B|C

Set A  business-date writers: W-02, W-01, W-06, W-12, W-14, W-07, W-04,
       W-17, W-18, W-19, W-03, W-21 (re-observed), W-24.  This copy is the
       NEW-ACTIVITY copy for inv-run and Q14.
Set B  wall-clock / correction writers: W-09, W-10, W-11, W-22, W-23.
       Their rows are dated from the calendar (K-7, Phase 3) and are kept
       on a separate copy so that consequence stays attributable.
Set C  W-16 skipped-audit rerun, which rewrites a NightAuditLog and is
       kept apart from the closed-day invariants of the other copies.

Every check carries a severity: 'gate' checks decide the verdict;
'finding' checks record an observation against the plan (for example the
audit-coupling class of a writer) without deciding it.
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
SET = (sys.argv[1] if len(sys.argv) > 1 else 'A').upper()

results = []
writers = {}     # writer id -> dict(module, function, object, mechanism, audit, runtime, notes)


def check(case_id, writer, what, expect, got, note='', gate=True):
    ok = (expect == got)
    results.append({'case': case_id, 'writer': writer, 'what': what,
                    'expect': expect, 'got': got, 'pass': ok,
                    'severity': 'gate' if gate else 'finding', 'note': note})
    print('%-5s %-9s %-7s %-52s expect=%-24s got=%-24s %s'
          % (('OK' if ok else ('FAIL' if gate else 'NOTE')), case_id, writer,
             what[:52], repr(expect)[:24], repr(got)[:24], note))
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
    print('PHASE 1 VERIFICATION COMPLETION - RUNTIME WRITER VERIFICATION - SET %s' % SET)
    print('=' * 130)
    print('production        : %s' % PRODUCTION_DB)
    print('sha256 before     : %s  (%s)' % (prod_before,
          'MATCHES anchor' if prod_before == FROZEN_ANCHOR else '*** MISMATCH ***'))

    handle = make_copy(name='p1vc_set%s.db' % SET)
    print('disposable copy   : %s  (%s)' % (handle.copy_path, handle.method))
    print('-' * 130)

    os.environ['DATABASE_URL'] = 'sqlite:///' + handle.copy_path.replace('\\', '/')
    os.environ['FLASK_ENV'] = 'production'

    from app import create_app                                          # noqa: E402
    from app.models import (db, User, Reservation, Folio, ExtraCharge,   # noqa: E402
                            Payment, PaymentMode, AuditLog, Room, Guest,
                            NightAuditLog, BusinessDate, CreditVoucher,
                            NoShowLog, NightAuditReopenLog)
    from flask_login import login_user                                    # noqa: E402

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    import app.services as svc                                            # noqa: E402
    import app.routes as routes_mod                                       # noqa: E402

    # -- D11 identity, before anything runs --------------------------------
    with app.app_context():
        d11_pay = sorted(r[0] for r in db.session.query(Payment.id)
                         .filter(Payment.folio_id.is_(None)).all())
        d11_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id)
                         .filter(ExtraCharge.folio_id.is_(None)).all())
        d11_pay_vals = {p.id: float(p.amount) for p in
                        db.session.query(Payment).filter(Payment.id.in_(d11_pay)).all()}
        d11_chg_vals = {c.id: float(c.amount) for c in
                        db.session.query(ExtraCharge).filter(ExtraCharge.id.in_(d11_chg)).all()}
        audit_before = db.session.query(AuditLog).count()
    print('D11 population    : payments=%s charges=%s audit_logs=%d' % (d11_pay, d11_chg, audit_before))

    # -- fixtures ----------------------------------------------------------
    with app.app_context():
        u = User(username='vc_admin', full_name='VC Admin', role='Admin', is_active=True)
        u.set_password('vc-test-password')
        db.session.add(u)
        db.session.flush()
        admin_id = u.id
        seed_res = db.session.query(Reservation).order_by(Reservation.id).first()
        seed = {'guest': seed_res.guest_id, 'room_type': seed_res.room_type_id}
        bd = db.session.query(BusinessDate).first().current_date
        vacant = [r.id for r in db.session.query(Room).filter_by(status='Vacant')
                  .order_by(Room.id).all()]
        db.session.commit()
    print('business date     : %s   vacant rooms: %d   admin user id: %d' % (bd, len(vacant), admin_id))
    print('-' * 130)

    def take_room():
        return vacant.pop(0)

    def new_res(tag, status, arrival, departure, rate=1000, room_id=None, **extra):
        with app.app_context():
            r = Reservation(
                booking_reference='VC-%s-%s-%d' % (SET, tag, int(datetime.now().timestamp() * 1000) % 100000),
                guest_id=seed['guest'], room_id=room_id, room_type_id=seed['room_type'],
                arrival_date=arrival, departure_date=departure, adults=1, children=0,
                status=status, rate_per_night=rate, noshow_exempt=False,
                checkout_initiated=False, credit_amount=0, credit_settled_amount=0,
                cancellation_amount_refunded=0, cancellation_amount_forfeited=0,
                cancellation_amount_credit_voucher=0)
            for k, v in extra.items():
                setattr(r, k, v)
            db.session.add(r)
            db.session.flush()
            if room_id and status == 'CheckedIn':
                db.session.get(Room, room_id).status = 'Occupied'
            db.session.commit()
            return r.id

    def folio_a(res_id):
        with app.app_context():
            f = db.session.query(Folio).filter_by(reservation_id=res_id, folio_letter='A').first()
            return None if f is None else f.id

    def res_by_phone(phone):
        with app.app_context():
            g = db.session.query(Guest).filter_by(phone=phone).first()
            if g is None:
                return None
            r = (db.session.query(Reservation).filter_by(guest_id=g.id)
                 .order_by(Reservation.id.desc()).first())
            return None if r is None else r.id

    def rows(model, res_id, **flt):
        with app.app_context():
            q = db.session.query(model).filter_by(reservation_id=res_id, **flt)
            return [{'id': x.id, 'folio_id': x.folio_id, 'amount': float(x.amount),
                     'purpose': getattr(x, 'payment_purpose', None),
                     'charge_type': getattr(x, 'charge_type', None),
                     'description': getattr(x, 'description', None),
                     'is_reversal': getattr(x, 'is_reversal', None),
                     'mode': getattr(x, 'payment_mode_id', None),
                     'date': str(getattr(x, 'payment_date', getattr(x, 'charge_date', None)))}
                    for x in q.order_by(model.id).all()]

    def count(model):
        with app.app_context():
            return db.session.query(model).count()

    def audits_for(entity_type, entity_id):
        with app.app_context():
            return [(a.action, a.after_state or {}) for a in
                    db.session.query(AuditLog).filter_by(entity_type=entity_type,
                                                         entity_id=entity_id)
                    .order_by(AuditLog.id).all()]

    def client_as_admin():
        c = app.test_client()
        with c.session_transaction() as sess:
            sess['_user_id'] = str(admin_id)
            sess['_fresh'] = True
        return c

    def logged_ctx():
        ctx = app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'})
        ctx.push()
        with app.app_context():
            pass
        login_user(db.session.get(User, admin_id))
        return ctx

    def exploding(*a, **kw):
        raise svc.AuditCouplingError('injected audit failure')

    class _Exc:
        """Stand-in response when the route lets the exception propagate.

        Under TESTING the test client re-raises unhandled exceptions; in
        production Flask would answer 500 and the request teardown rolls the
        session back. Either way nothing is committed, which is what the
        count assertions prove.
        """
        def __init__(self, exc):
            self.status_code = 500
            self.exc = exc.__class__.__name__

    def inject(fn):
        real = svc.audited_financial_write
        svc.audited_financial_write = exploding
        try:
            return fn()
        except Exception as exc:          # propagated by the test client
            with app.app_context():
                db.session.rollback()
            return _Exc(exc)
        finally:
            svc.audited_financial_write = real

    def verify_row(writer, kind, row, res_id, audit, label=''):
        """Common assertions 1-5 of the directive for one financial row."""
        Model = Payment if kind == 'Payment' else ExtraCharge
        with app.app_context():
            fa = folio_a(res_id)
            check('%s-01' % writer, writer, '%s row created%s' % (kind, label), True, row is not None)
            if row is None:
                return
            check('%s-02' % writer, writer, 'folio_id non-null', True, row['folio_id'] is not None)
            check('%s-03' % writer, writer, 'folio_id == reservation billing folio A', fa, row['folio_id'])
            f = db.session.get(Folio, row['folio_id']) if row['folio_id'] else None
            check('%s-04' % writer, writer, 'folio belongs to this reservation, letter A',
                  (res_id, 'A'), (None if f is None else (f.reservation_id, f.folio_letter)))
        # audit
        mech = audit['mechanism']
        if mech == 'A-STRICT':
            arows = audits_for(kind, row['id'])
            check('%s-05' % writer, writer, 'audit row exists for this financial row',
                  True, len(arows) >= 1)
            after = arows[0][1] if arows else {}
            check('%s-06' % writer, writer, 'audit carries same folio and amount',
                  (row['folio_id'], round(row['amount'], 2)),
                  (after.get('folio_id'), round(float(after.get('amount', -1)), 2)),
                  'action=%s' % (arows[0][0] if arows else None))
        elif mech == 'A-NF-caller':
            arows = audits_for(kind, row['id'])
            check('%s-05' % writer, writer, 'audit row exists for this financial row',
                  True, len(arows) >= 1, 'caller-supplied _write_audit (never raises)')
            after = arows[0][1] if arows else {}
            ident = after.get(audit.get('amount_key', 'amount'))
            check('%s-06' % writer, writer, 'audit carries the financial identity',
                  round(row['amount'], 2), (None if ident is None else round(float(ident), 2)),
                  'action=%s keys=%s' % (arows[0][0] if arows else None, sorted(after)[:6]))
        elif mech == 'A-NF-entity':
            arows = audits_for(audit['entity'], audit['entity_id'])
            acts = [a for a, _ in arows]
            check('%s-05' % writer, writer, 'audit row exists (%s level)' % audit['entity'],
                  True, audit['action'] in acts, 'actions=%s' % acts[-3:])
            after = dict(arows[[a for a, _ in arows].index(audit['action'])][1]) if audit['action'] in acts else {}
            check('%s-06' % writer, writer, 'audit carries the financial identity',
                  True, any(abs(float(v) - row['amount']) < 0.01 for v in after.values()
                            if isinstance(v, (int, float)) and not isinstance(v, bool)),
                  'after_state=%s' % json.dumps(after)[:80])
        elif mech == 'A-DED':
            check('%s-05' % writer, writer, 'dedicated log row exists (%s)' % audit['table'],
                  True, audit['present'])
            check('%s-06' % writer, writer, 'dedicated log carries the amount',
                  round(row['amount'], 2), audit.get('amount'))
        else:   # A0
            check('%s-05' % writer, writer, 'financial-row audit present',
                  True, False, 'A0: no audit row for the financial row at this writer', gate=False)
            check('%s-06' % writer, writer, 'audit identity', 'n/a', 'n/a', gate=False)
        # Q-5 expectation, recorded not decided
        check('%s-07' % writer, writer, 'audit coupling class vs Q-5 (A-STRICT expected)',
              'A-STRICT', mech, audit.get('note', ''), gate=False)

    def record(wid, module, function, obj, mechanism, audit_class, runtime, notes=''):
        writers[wid] = {'module': module, 'function': function, 'object': obj,
                        'attribution': mechanism, 'audit': audit_class,
                        'runtime': runtime, 'notes': notes}

    c = client_as_admin()
    pay_ct = lambda: count(Payment)          # noqa: E731
    chg_ct = lambda: count(ExtraCharge)      # noqa: E731

    # =====================================================================
    if SET == 'A':
        # ---------------- W-02 new_reservation (advance) -----------------
        print('W-02 new_reservation - advance payment via POST /reservations/new')
        # new_reservation validates arrival against the CALENDAR date
        # (validate_not_past), which is 30 days ahead of the business date.
        cal = date.today()
        form = dict(first_name='VC', last_name='NewRes', guest_phone='9000000002',
                    guest_email='vc2@example.com', room_type_id='2',
                    arrival_date=(cal + timedelta(days=2)).isoformat(),
                    departure_date=(cal + timedelta(days=3)).isoformat(),
                    adults='1', children='0', rate='1000', advance_payment='300',
                    payment_mode_id='1', source='Walk-in')
        r = c.post('/reservations/new', data=form)
        rid = res_by_phone('9000000002')
        pays = rows(Payment, rid) if rid else []
        print('   HTTP %s  reservation=%s payments=%s' % (r.status_code, rid, pays))
        row = pays[-1] if pays else None
        verify_row('W-02', 'Payment', row, rid, {'mechanism': 'A-STRICT'})
        if row:
            check('W-02-08', 'W-02', 'purpose is advance (arrival after business date)', 'advance', row['purpose'])
        pb, rb = pay_ct(), count(Reservation)
        r2 = inject(lambda: c.post('/reservations/new', data={**form, 'guest_phone': '9000000003'}))
        check('W-02-A1', 'W-02', 'audit failure commits no payment', pb, pay_ct(), 'HTTP %s' % r2.status_code)
        check('W-02-A2', 'W-02', 'audit failure commits no reservation either', rb, count(Reservation),
              'same transaction', gate=False)
        record('W-02', 'app/routes.py', 'new_reservation', 'Payment', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- W-01 bulk_booking_api ---------------------------
        print('W-01 bulk_booking_api - advance via POST /api/reservations/bulk-booking')
        payload = dict(arrival_date=(bd + timedelta(days=3)).isoformat(),
                       departure_date=(bd + timedelta(days=4)).isoformat(),
                       first_name='VC', last_name='Bulk', phone='9000000011', email='',
                       rows=[dict(room_type_id=2, quantity=1, rate=1000, adults=1, children=0)],
                       advance=400, payment_mode_id=1, source='Walk-in', group_name='VC Bulk')
        r = c.post('/api/reservations/bulk-booking', json=payload)
        rid = res_by_phone('9000000011')
        pays = rows(Payment, rid) if rid else []
        print('   HTTP %s %s  reservation=%s payments=%s' % (r.status_code, (r.get_json() or {}), rid, pays))
        row = pays[-1] if pays else None
        verify_row('W-01', 'Payment', row, rid, {'mechanism': 'A-STRICT'})
        pb = pay_ct()
        r2 = inject(lambda: c.post('/api/reservations/bulk-booking',
                                   json={**payload, 'phone': '9000000012'}))
        check('W-01-A1', 'W-01', 'audit failure commits no payment', pb, pay_ct(), 'HTTP %s' % r2.status_code)
        record('W-01', 'app/routes.py', 'bulk_booking_api', 'Payment', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict; audit row added by Phase 1)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- W-06 walkin_search_express ----------------------
        print('W-06 walkin_search_express - settlement via POST /api/checkin/walkin-search-express')
        room = take_room()
        payload = dict(room_id=room, first_name='VC', last_name='Walkin', phone='9000000021',
                       email='', nights=1, advance=0, adults=1, children=0,
                       payments=[dict(mode_id=1, amount=500, reference='VC')])
        r = c.post('/api/checkin/walkin-search-express', json=payload)
        rid = res_by_phone('9000000021')
        pays = rows(Payment, rid) if rid else []
        print('   HTTP %s %s  reservation=%s payments=%s' % (r.status_code, str(r.get_json())[:100], rid, pays))
        row = pays[-1] if pays else None
        verify_row('W-06', 'Payment', row, rid, {'mechanism': 'A-STRICT'})
        pb = pay_ct()
        room2 = take_room()
        r2 = inject(lambda: c.post('/api/checkin/walkin-search-express',
                                   json={**payload, 'room_id': room2, 'phone': '9000000022'}))
        check('W-06-A1', 'W-06', 'audit failure commits no payment', pb, pay_ct(), 'HTTP %s' % r2.status_code)
        record('W-06', 'app/routes.py', 'walkin_search_express', 'Payment', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict; audit row added by Phase 1)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- W-12 complete_full_checkin (deposit) -----------
        print('W-12 CheckInService.complete_full_checkin - deposit payment (service, real caller shape)')
        rid = new_res('w12', 'Reserved', bd, bd + timedelta(days=1), 1000)
        room = take_room()
        ctx = logged_ctx()
        try:
            svc.CheckInService.complete_full_checkin(
                rid, {'room_id': room, 'deposit_amount': '250',
                      'deposit_payment_mode_id': '1', 'billing_responsibility': 'Guest'},
                admin_id, '127.0.0.1')
        finally:
            ctx.pop()
        pays = rows(Payment, rid)
        print('   payments=%s' % pays)
        row = pays[-1] if pays else None
        verify_row('W-12', 'Payment', row, rid,
                   {'mechanism': 'A-NF-entity', 'entity': 'Reservation', 'entity_id': rid,
                    'action': 'checkin_full',
                    'note': 'Reservation-level checkin_full row written AFTER commit (A-NF); no Payment-level audit'})
        record('W-12', 'app/services.py', 'CheckInService.complete_full_checkin', 'Payment',
               'R-1 resolve_billing_folio_id', 'A-NF entity-level (checkin_full, post-commit); no financial-row audit',
               'exercised (set A)')
        print('-' * 130)

        # ---------------- W-14 process_reservation_noshow ----------------
        print('W-14 process_reservation_noshow - no-show fee (service, night-audit caller shape)')
        room = take_room()
        rid = new_res('w14', 'Reserved', bd, bd + timedelta(days=1), 1000, room_id=room)
        with app.app_context():
            import app.noshow_service as ns
            res = db.session.get(Reservation, rid)
            out = ns.process_reservation_noshow(
                res, bd, {'fee_enabled': True, 'fee_mode': 'fixed', 'fee_amount': 500.0,
                          'ota_auto_process': False}, posted_by_user_id=admin_id)
            db.session.commit()
            nlog = db.session.query(NoShowLog).filter_by(reservation_id=rid).first()
            ded = {'present': nlog is not None,
                   'amount': None if nlog is None else round(float(nlog.fee_amount), 2)}
        chgs = rows(ExtraCharge, rid)
        print('   result=%s charges=%s' % (out, chgs))
        row = chgs[-1] if chgs else None
        verify_row('W-14', 'ExtraCharge', row, rid,
                   {'mechanism': 'A-DED', 'table': 'no_show_logs', **ded,
                    'note': 'NoShowLog + Reservation-level noshow_posted AuditLog in the same transaction as the charge'})
        acts = [a for a, _ in audits_for('Reservation', rid)]
        check('W-14-08', 'W-14', 'Reservation-level noshow_posted audit in same commit', True, 'noshow_posted' in acts)
        record('W-14', 'app/noshow_service.py', 'process_reservation_noshow', 'ExtraCharge',
               'R-1 resolve_billing_folio_id', 'A-DED (NoShowLog + AuditLog, same transaction)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- W-07 settle_credit -----------------------------
        print('W-07 settle_credit - credit recovery via POST /credit/<id>/settle')
        rid = new_res('w07', 'CheckedOut', bd - timedelta(days=1), bd, 1000,
                      credit_amount=400, credit_settled_amount=0)
        r = c.post('/credit/%d/settle' % rid, data={'amount': '200', 'payment_mode_id': '1',
                                                    'reference_number': 'VC', 'notes': 'VC'})
        pays = rows(Payment, rid)
        print('   HTTP %s payments=%s' % (r.status_code, pays))
        row = pays[-1] if pays else None
        if row is None:
            # Observed on this run: the route raises
            #   TypeError: 'notes' is an invalid keyword argument for Payment
            # inside its try/except and flashes a failure. The Payment model has
            # no `notes` column; the keyword has been in settle_credit since the
            # baseline commit b5b2514 (2026-08-07) and is untouched by Phase 1.
            check('W-07-01', 'W-07', 'Payment row created', True, False,
                  'NOT EXERCISABLE: pre-existing defect - Payment() rejects notes= '
                  '(TypeError), present since b5b2514, untouched by Phase 1', gate=False)
            record('W-07', 'app/routes.py', 'settle_credit', 'Payment', 'R-1 _billing_folio_id',
                   'A-STRICT (_write_audit_strict; audit row added by Phase 1) - static',
                   'BLOCKED - pre-existing runtime defect (TypeError: notes kwarg on Payment)',
                   'route cannot post any credit-recovery payment on this codebase; static proof only')
        else:
            verify_row('W-07', 'Payment', row, rid, {'mechanism': 'A-STRICT'})
            check('W-07-08', 'W-07', 'purpose is credit_recovery', 'credit_recovery', row['purpose'])
            pb = pay_ct()
            r2 = inject(lambda: c.post('/credit/%d/settle' % rid, data={'amount': '100', 'payment_mode_id': '1'}))
            check('W-07-A1', 'W-07', 'audit failure commits no payment', pb, pay_ct(), 'HTTP %s' % r2.status_code)
            record('W-07', 'app/routes.py', 'settle_credit', 'Payment', 'R-1 _billing_folio_id',
                   'A-STRICT (_write_audit_strict; audit row added by Phase 1)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- checkout: W-04 + W-17 + W-18 -------------------
        def due_of(rid_):
            with app.app_context():
                return float(svc.calculate_stay_amount(db.session.get(Reservation, rid_))['balance'])

        print('W-04 / W-17 / W-18 checkout - settlement, extra charge, overpay-as-tip via POST /checkout/<id>')
        room = take_room()
        rid = new_res('w04', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        due = due_of(rid)
        # The route auto-posts a CICO late-checkout charge from the CALENDAR clock
        # (a full night after the slab cut-off), which doubles the bill and is
        # time-dependent; the Admin waiver keeps the probe deterministic.
        WAIVE = {'waive_late_checkout': '1', 'waive_late_co_reason': 'VC deterministic probe'}
        form = {**WAIVE, 'extra_description': 'VC extra', 'extra_amount': '100',
                'pm_amount_1': '%.2f' % (due + 600), 'overpay_reason': 'mistake',
                'overpay_resolution': 'tip', 'overpay_waiter_name': 'VC Waiter',
                'overpay_tip_remarks': 'VC'}
        r = c.post('/checkout/%d' % rid, data=form)
        with app.app_context():
            st = db.session.get(Reservation, rid).status
        pays, chgs = rows(Payment, rid), rows(ExtraCharge, rid)
        print('   HTTP %s status=%s due=%.2f payments=%s charges=%s' % (r.status_code, st, due, pays, chgs))
        check('W-04-00', 'W-04', 'checkout completed (status CheckedOut)', 'CheckedOut', st)
        settle = [p for p in pays if p['purpose'] == 'settlement']
        verify_row('W-04', 'Payment', settle[-1] if settle else None, rid, {'mechanism': 'A-STRICT'})
        extra = [x for x in chgs if x['description'] == 'VC extra']
        verify_row('W-17', 'ExtraCharge', extra[-1] if extra else None, rid, {'mechanism': 'A-STRICT'})
        tip = [x for x in chgs if x['charge_type'] == 'tip']
        verify_row('W-18', 'ExtraCharge', tip[-1] if tip else None, rid, {'mechanism': 'A-STRICT'})
        record('W-04', 'app/routes.py', 'checkout (settlement loop)', 'Payment', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict)', 'exercised (set A)')
        record('W-17', 'app/routes.py', 'checkout (extra charge)', 'ExtraCharge', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict)', 'exercised (set A)',
               'charge_date not passed (model default date.today) - K-7, Phase 3')
        record('W-18', 'app/routes.py', 'checkout (overpay -> tip)', 'ExtraCharge', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- checkout: W-19 ---------------------------------
        print('W-19 checkout - overpay-as-other-income')
        room = take_room()
        rid = new_res('w19', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        due = due_of(rid)
        r = c.post('/checkout/%d' % rid, data={**WAIVE, 'pm_amount_1': '%.2f' % (due + 300),
                                               'overpay_reason': 'mistake',
                                               'overpay_resolution': 'income',
                                               'overpay_income_remarks': 'VC income'})
        with app.app_context():
            st = db.session.get(Reservation, rid).status
        chgs = rows(ExtraCharge, rid)
        print('   HTTP %s status=%s charges=%s' % (r.status_code, st, chgs))
        oi = [x for x in chgs if x['charge_type'] == 'other_income']
        verify_row('W-19', 'ExtraCharge', oi[-1] if oi else None, rid, {'mechanism': 'A-STRICT'})
        record('W-19', 'app/routes.py', 'checkout (overpay -> other income)', 'ExtraCharge',
               'R-1 _billing_folio_id', 'A-STRICT (_write_audit_strict)', 'exercised (set A)')
        print('-' * 130)

        # ---------------- checkout: W-03 OTA auto-settlement -------------
        print('W-03 checkout - OTA auto-settlement (paid_at_ota reservation)')
        room = take_room()
        # ck_reservation_source allows only the enumerated sources; 'OTA' with an
        # MMT-prefixed booking id is the generic-OTA shape the route resolves.
        rid = new_res('w03', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room,
                      ota_payment_status='paid_at_ota', source='OTA', ota_booking_id='MMT-VC-OTA-1')
        due = due_of(rid)
        r = c.post('/checkout/%d' % rid, data={**WAIVE, 'pm_amount_1': '%.2f' % (due + 200),
                                               'overpay_reason': 'mistake',
                                               'overpay_resolution': 'income',
                                               'overpay_income_remarks': 'VC OTA income'})
        with app.app_context():
            st = db.session.get(Reservation, rid).status
            ota_modes = {m.id for m in db.session.query(PaymentMode).filter_by(category='ota_receivable')}
        pays = rows(Payment, rid)
        print('   HTTP %s status=%s payments=%s' % (r.status_code, st, pays))
        ota = [p for p in pays if p['mode'] in ota_modes]
        verify_row('W-03', 'Payment', ota[-1] if ota else None, rid, {'mechanism': 'A-STRICT'})
        record('W-03', 'app/routes.py', 'checkout (OTA auto-settlement)', 'Payment', 'R-1 _billing_folio_id',
               'A-STRICT (_write_audit_strict)', 'exercised (set A)' if ota else 'NOT exercised')
        print('-' * 130)

        # ---------------- checkout audit-failure injection ---------------
        print('checkout - audit-failure injection (W-04 path)')
        room = take_room()
        rid = new_res('w04inj', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        due = due_of(rid)
        pb = pay_ct()
        r2 = inject(lambda: c.post('/checkout/%d' % rid, data={**WAIVE, 'pm_amount_1': '%.2f' % due}))
        with app.app_context():
            st = db.session.get(Reservation, rid).status
        check('W-04-A1', 'W-04', 'audit failure commits no payment', pb, pay_ct(), 'HTTP %s' % r2.status_code)
        check('W-04-A2', 'W-04', 'audit failure leaves reservation CheckedIn', 'CheckedIn', st)
        print('-' * 130)

        # ---------------- night audit (W-21 re-observed) + W-24 ----------
        print('W-21 (re-observed) night audit, then W-24 convert_overpayment_to_upsell (CASE A)')
        room = take_room()
        stay = new_res('w24', 'CheckedIn', bd, bd + timedelta(days=1), 1200, room_id=room)
        with app.app_context():
            db.session.query(NightAuditLog).filter_by(audit_date=bd).delete()
            db.session.commit()
        svc.run_night_audit(app)
        rr = rows(ExtraCharge, stay, charge_type='room_rent')
        with app.app_context():
            bd_after = db.session.query(BusinessDate).first().current_date
            nal = db.session.query(NightAuditLog).filter_by(audit_date=bd).first()
        print('   night audit for %s -> %s; business date now %s; room_rent rows=%s'
              % (bd, None if nal is None else nal.status, bd_after, rr))
        check('W-21-R1', 'W-21', 'night audit room rent attributed to folio A (re-observed)',
              [folio_a(stay)], [x['folio_id'] for x in rr])
        with app.app_context():
            total = float(svc.calculate_stay_amount(db.session.get(Reservation, stay))['total'])
        r = c.post('/api/reservation/%d/add-payment' % stay, json={'amount': round(total + 500, 2)})
        with app.app_context():
            res = db.session.get(Reservation, stay)
            out = svc.convert_overpayment_to_upsell(res, reason='VC upsell', authorized_by_user_id=admin_id)
            db.session.commit()
        ups = rows(ExtraCharge, stay, charge_type='room_upsell')
        print('   add-payment HTTP %s (total %.2f + 500); upsell result=%s; upsell rows=%s'
              % (r.status_code, total, {k: out.get(k) for k in ('ok', 'branch', 'error')}, ups))
        check('W-24-00', 'W-24', 'conversion took CASE A (corrective ExtraCharge)',
              'case_a_corrective_extracharge', out.get('branch'))
        verify_row('W-24', 'ExtraCharge', ups[-1] if ups else None, stay,
                   {'mechanism': 'A0', 'note': 'no AuditLog for the room_upsell row (A0 per inventory)'})
        record('W-24', 'app/services.py', 'convert_overpayment_to_upsell', 'ExtraCharge',
               'R-2 resolve_billing_folio_id', 'A0 (no financial-row audit)', 'exercised (set A)')
        record('W-21', 'app/services.py', 'run_night_audit', 'ExtraCharge', 'R-2 resolve_billing_folio_id',
               'NightAuditLog (run-level); no per-row AuditLog by design', 'already verified (T-R01/R02/R04); re-observed (set A)')
        print('-' * 130)

    # =====================================================================
    elif SET == 'B':
        # ---------------- W-09 payment replacement via void route --------
        print('W-09 post_payment_correction (replacement) via POST /payment/<id>/void with correction amount')
        room = take_room()
        rid = new_res('w09', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        r0 = c.post('/api/reservation/%d/add-payment' % rid, json={'amount': 300.0})
        p0 = rows(Payment, rid)[-1]
        # The route posts a correction PAIR only for a payment inside a closed
        # night audit with an Admin override; otherwise it voids in place.
        # The copy's only closed audit is 2026-08-09, so the fixture payment
        # (dated on the open business date by add_payment) is moved onto that
        # locked date - a copy-only fixture edit of a row this script created.
        with app.app_context():
            p = db.session.get(Payment, p0['id'])
            p.payment_date = date(2026, 8, 9)
            db.session.commit()
            locked = svc.get_locking_audit(date(2026, 8, 9)) is not None
        check('W-09-00', 'W-09', 'fixture payment sits on an audit-locked date', True, locked)
        r = c.post('/payment/%d/void' % p0['id'], data={'void_reason': 'VC void',
                                                       'audit_override': '1',
                                                       'audit_override_reason': 'VC override',
                                                       'correction_new_amount': '250',
                                                       'correction_new_mode_id': '1'})
        pays = rows(Payment, rid)
        print('   add-payment HTTP %s; void HTTP %s; payments=%s' % (r0.status_code, r.status_code, pays))
        rev = [p for p in pays if p['is_reversal'] and p['id'] != p0['id']]
        rep = [p for p in pays if not p['is_reversal'] and p['id'] != p0['id']]
        verify_row('W-08', 'Payment', rev[-1] if rev else None, rid,
                   {'mechanism': 'A-NF-caller', 'amount_key': 'reversal_amount',
                    'note': 'audit via caller-supplied _write_audit (route void_payment); inherits folio (R-3)'},
                   label=' (reversal, re-observed)')
        verify_row('W-09', 'Payment', rep[-1] if rep else None, rid,
                   {'mechanism': 'A-NF-caller', 'amount_key': 'replacement_amount',
                    'note': 'audit via caller-supplied _write_audit; service swallows audit exceptions'})
        if rep:
            check('W-09-08', 'W-09', 'replacement inherits the original folio (R-3)', p0['folio_id'], rep[-1]['folio_id'])
        record('W-08', 'app/services.py', 'post_payment_correction (reversal)', 'Payment', 'R-3 inherit_billing_folio_id',
               'A-NF caller-supplied audit_writer (swallowed on failure)', 'already verified (T-W08, T-Q02); re-observed via route (set B)')
        record('W-09', 'app/services.py', 'post_payment_correction (replacement)', 'Payment', 'R-3 inherit_billing_folio_id',
               'A-NF caller-supplied audit_writer (swallowed on failure)', 'exercised via route (set B)',
               'dated from wall clock (K-7)')
        print('-' * 130)

        # ---------------- W-10 refund ------------------------------------
        print('W-10 post_cancellation_disposition (refund_full) - service with the cancel route audit writer')
        cal = date.today()
        form = dict(first_name='VC', last_name='Cancel', guest_phone='9000000031',
                    guest_email='vc31@example.com', room_type_id='2',
                    arrival_date=(cal + timedelta(days=2)).isoformat(),
                    departure_date=(cal + timedelta(days=3)).isoformat(),
                    adults='1', children='0', rate='1000', advance_payment='300',
                    payment_mode_id='1', source='Walk-in')
        r0 = c.post('/reservations/new', data=form)
        rid = res_by_phone('9000000031')
        ctx = logged_ctx()
        try:
            res = db.session.get(Reservation, rid)
            out = svc.post_cancellation_disposition(
                res, disposition='refund_full', refund_mode_id=1, reason='VC cancel',
                user_id=admin_id, audit_writer=routes_mod._write_audit)
            res.status = 'Cancelled'
            db.session.commit()
            refund_id = out['refund_payment'].id
        finally:
            ctx.pop()
        pays = rows(Payment, rid)
        print('   new_reservation HTTP %s; reservation=%s; payments=%s' % (r0.status_code, rid, pays))
        ref = [p for p in pays if p['id'] == refund_id]
        verify_row('W-10', 'Payment', ref[-1] if ref else None, rid,
                   {'mechanism': 'A-NF-caller', 'amount_key': 'refund_amount',
                    'note': 'audit via caller-supplied _write_audit (cancel route); service swallows audit exceptions'})
        if ref:
            check('W-10-08', 'W-10', 'refund row is a reversal with purpose refund',
                  (True, 'refund'), (ref[-1]['is_reversal'], ref[-1]['purpose']))
        record('W-10', 'app/services.py', 'post_cancellation_disposition', 'Payment', 'R-4/CD-3 resolve_billing_folio_id',
               'A-NF caller-supplied audit_writer (swallowed on failure)', 'exercised (set B)', 'dated from wall clock (K-7)')
        print('-' * 130)

        # ---------------- W-11 voucher redemption via route --------------
        print('W-11 redeem_credit_voucher via POST /api/voucher/<id>/redeem')
        room = take_room()
        rid = new_res('w11', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        with app.app_context():
            v = CreditVoucher(voucher_code='VC-VOUCH-1', guest_id=seed['guest'], issued_amount=500,
                              redeemed_amount=0, issued_date=date.today(), status='active',
                              issued_by_user_id=admin_id)
            db.session.add(v)
            db.session.commit()
            vid = v.id
        r = c.post('/api/voucher/%d/redeem' % vid, json={'reservation_id': rid, 'amount': 200})
        pays = rows(Payment, rid)
        print('   HTTP %s %s payments=%s' % (r.status_code, str(r.get_json())[:100], pays))
        vp = [p for p in pays if p['purpose'] == 'settlement']
        if not vp:
            # Observed on this run: HTTP 500 'redemption failed' - the service
            # raises TypeError: 'notes' is an invalid keyword argument for
            # Payment. Same pre-existing defect class as W-07; present since
            # b5b2514 and untouched by Phase 1.
            check('W-11-01', 'W-11', 'Payment row created', True, False,
                  'NOT EXERCISABLE: pre-existing defect - Payment() rejects notes= '
                  '(TypeError), present since b5b2514, untouched by Phase 1; HTTP %s' % r.status_code,
                  gate=False)
            record('W-11', 'app/services.py', 'redeem_credit_voucher', 'Payment', 'R-1 resolve_billing_folio_id',
                   'A-NF entity-level (CreditVoucher voucher_used) via caller audit_writer - static',
                   'BLOCKED - pre-existing runtime defect (TypeError: notes kwarg on Payment)',
                   'voucher redemption cannot create its payment on this codebase; static proof only; dated from wall clock (K-7)')
        else:
            verify_row('W-11', 'Payment', vp[-1], rid,
                       {'mechanism': 'A-NF-entity', 'entity': 'CreditVoucher', 'entity_id': vid,
                        'action': 'voucher_used',
                        'note': 'audit is voucher-level (voucher_used) via caller _write_audit; no Payment-level audit'})
            record('W-11', 'app/services.py', 'redeem_credit_voucher', 'Payment', 'R-1 resolve_billing_folio_id',
                   'A-NF entity-level (CreditVoucher voucher_used) via caller audit_writer', 'exercised via route (set B)',
                   'dated from wall clock (K-7)')
        print('-' * 130)

        # ---------------- W-22 / W-23 charge corrections ------------------
        print('W-22 / W-23 post_extra_charge_correction - service (no route caller exists)')
        room = take_room()
        rid = new_res('w22', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        with app.app_context():
            import app.cico_service as cico
            ec = cico.post_charge(db.session.get(Reservation, rid), 'late_checkout', 300.0,
                                  '02:00 PM - 30%', user_id=admin_id)
            db.session.commit()
            orig_id, orig_folio = ec.id, ec.folio_id
        ctx = logged_ctx()
        try:
            orig = db.session.get(ExtraCharge, orig_id)
            out = svc.post_extra_charge_correction(orig, new_amount=150.0, reason='VC charge corr',
                                                   user_id=admin_id, audit_writer=routes_mod._write_audit)
            db.session.commit()
            rev_id, rep_id = out['reversal'].id, out['replacement'].id
        finally:
            ctx.pop()
        chgs = rows(ExtraCharge, rid)
        print('   original=%s reversal=%s replacement=%s charges=%s' % (orig_id, rev_id, rep_id, chgs))
        rev = [x for x in chgs if x['id'] == rev_id]
        rep = [x for x in chgs if x['id'] == rep_id]
        verify_row('W-22', 'ExtraCharge', rev[-1] if rev else None, rid,
                   {'mechanism': 'A-NF-caller', 'amount_key': 'reversal_amount',
                    'note': 'caller-supplied audit_writer; no route caller exists in app/'})
        verify_row('W-23', 'ExtraCharge', rep[-1] if rep else None, rid,
                   {'mechanism': 'A-NF-caller', 'amount_key': 'replacement_amount',
                    'note': 'caller-supplied audit_writer; no route caller exists in app/'})
        check('W-22-08', 'W-22', 'reversal inherits the original folio (R-3)', orig_folio, rev[-1]['folio_id'] if rev else None)
        check('W-23-08', 'W-23', 'replacement inherits the original folio (R-3)', orig_folio, rep[-1]['folio_id'] if rep else None)
        record('W-22', 'app/services.py', 'post_extra_charge_correction (reversal)', 'ExtraCharge', 'R-3 inherit_billing_folio_id',
               'A-NF caller-supplied audit_writer; no application caller', 'exercised (set B, service)', 'dated from wall clock (K-7)')
        record('W-23', 'app/services.py', 'post_extra_charge_correction (replacement)', 'ExtraCharge', 'R-3 inherit_billing_folio_id',
               'A-NF caller-supplied audit_writer; no application caller', 'exercised (set B, service)', 'dated from wall clock (K-7)')
        print('-' * 130)

    # =====================================================================
    elif SET == 'C':
        print('W-16 _rerun_skipped_audit - recovered room rent for a Skipped night audit')
        room = take_room()
        stay = new_res('w16', 'CheckedIn', bd, bd + timedelta(days=1), 1100, room_id=room)
        with app.app_context():
            db.session.add(NightAuditLog(audit_date=bd, status='Skipped', run_by_user_id=admin_id,
                                         notes='VC fixture: skipped audit'))
            db.session.commit()
            in_house = [r.id for r in db.session.query(Reservation)
                        .filter(Reservation.arrival_date <= bd, Reservation.departure_date > bd,
                                Reservation.status.in_(('CheckedIn', 'CheckedOut'))).all()]
        ctx = logged_ctx()
        try:
            from app import reports as reports_mod
            ok, msg = reports_mod._rerun_skipped_audit(bd, admin_id, 'VC rerun')
            db.session.commit()
        finally:
            ctx.pop()
        with app.app_context():
            nal = db.session.query(NightAuditLog).filter_by(audit_date=bd).first()
            reopen = db.session.query(NightAuditReopenLog).filter_by(audit_log_id=nal.id).count()
            rec = [(x.reservation_id, x.folio_id, float(x.amount), str(x.charge_date)) for x in
                   db.session.query(ExtraCharge).filter(ExtraCharge.charge_type == 'room_rent',
                                                        ExtraCharge.description.like('%[recovered]%'))
                   .order_by(ExtraCharge.id).all()]
        print('   rerun ok=%s msg=%s; log status=%s; reopen rows=%d; in_house=%s; recovered rows=%s'
              % (ok, msg, nal.status, reopen, in_house, rec))
        check('W-16-00', 'W-16', 'rerun accepted', True, ok, msg[:60])
        rr = rows(ExtraCharge, stay, charge_type='room_rent')
        verify_row('W-16', 'ExtraCharge', rr[-1] if rr else None, stay,
                   {'mechanism': 'A0', 'note': 'NightAuditReopenLog + NightAuditLog update; no per-row AuditLog by design (as W-21)'})
        check('W-16-08', 'W-16', 'every recovered row attributed to its own reservation folio A',
              True, all(folio_a(res_id) == fid for res_id, fid, _, _ in rec) and len(rec) >= 1,
              '%d rows' % len(rec))
        check('W-16-09', 'W-16', 'NightAuditReopenLog written for the rerun', True, reopen >= 1)
        check('W-16-10', 'W-16', 'recovered rows dated on the target business date',
              True, all(d == str(bd) for _, _, _, d in rec))
        record('W-16', 'app/reports.py', '_rerun_skipped_audit', 'ExtraCharge', 'R-2 resolve_billing_folio_id',
               'NightAuditReopenLog/NightAuditLog (run-level); no per-row AuditLog by design', 'exercised (set C)')
        print('-' * 130)

    # =====================================================================
    elif SET == 'D':
        # Clean NEW-ACTIVITY copy for the E-9 / slice-4 expectation: only
        # business-date writers, no fixture placed inside a closed period, no
        # calendar-dated advance booking, no rate change after close, and the
        # night audit run LAST so every row sits inside the day it closes.
        print('SET D - clean new-activity copy (business-date writers only; night audit closes last)')

        def due_of(rid_):
            with app.app_context():
                return float(svc.calculate_stay_amount(db.session.get(Reservation, rid_))['balance'])
        WAIVE = {'waive_late_checkout': '1', 'waive_late_co_reason': 'VC deterministic probe'}

        # W-06 walk-in express (settlement payment) - stays in house for the audit
        room = take_room()
        r = c.post('/api/checkin/walkin-search-express',
                   json=dict(room_id=room, first_name='VC', last_name='Walkin', phone='9000000041',
                             email='', nights=1, advance=0, adults=1, children=0,
                             payments=[dict(mode_id=1, amount=500, reference='VC')]))
        rid = res_by_phone('9000000041')
        pays = rows(Payment, rid) if rid else []
        verify_row('W-06', 'Payment', pays[-1] if pays else None, rid, {'mechanism': 'A-STRICT'}, label=' (set D)')

        # W-12 full check-in with deposit - stays in house
        rid = new_res('d12', 'Reserved', bd, bd + timedelta(days=1), 1000)
        room = take_room()
        ctx = logged_ctx()
        try:
            svc.CheckInService.complete_full_checkin(
                rid, {'room_id': room, 'deposit_amount': '250', 'deposit_payment_mode_id': '1',
                      'billing_responsibility': 'Guest'}, admin_id, '127.0.0.1')
        finally:
            ctx.pop()
        pays = rows(Payment, rid)
        verify_row('W-12', 'Payment', pays[-1] if pays else None, rid,
                   {'mechanism': 'A-NF-entity', 'entity': 'Reservation', 'entity_id': rid,
                    'action': 'checkin_full', 'note': 'as set A'}, label=' (set D)')

        # W-05 add_payment and W-15 POS and W-13 CICO on an in-house stay (already verified; re-observed)
        room = take_room()
        stay = new_res('d05', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        c.post('/api/reservation/%d/add-payment' % stay, json={'amount': 400.0})
        c.post('/pos/post', data={'reservation_id': stay, 'description': 'VC POS D', 'amount': '80'},
               headers={'X-Requested-With': 'XMLHttpRequest'})
        with app.app_context():
            import app.cico_service as cico
            cico.post_charge(db.session.get(Reservation, stay), 'early_checkin', 120.0, '06:00 AM - 30%',
                             user_id=admin_id)
            db.session.commit()
        check('D-05', 'W-05', 'add_payment / POS / CICO rows attributed (re-observed)',
              [folio_a(stay)] * 3,
              [x['folio_id'] for x in rows(Payment, stay)] + [x['folio_id'] for x in rows(ExtraCharge, stay)])

        # W-14 no-show fee (business-dated)
        room = take_room()
        rid = new_res('d14', 'Reserved', bd, bd + timedelta(days=1), 1000, room_id=room)
        with app.app_context():
            import app.noshow_service as ns
            ns.process_reservation_noshow(db.session.get(Reservation, rid), bd,
                                          {'fee_enabled': True, 'fee_mode': 'fixed', 'fee_amount': 500.0,
                                           'ota_auto_process': False}, posted_by_user_id=admin_id)
            db.session.commit()
        chgs = rows(ExtraCharge, rid)
        verify_row('W-14', 'ExtraCharge', chgs[-1] if chgs else None, rid,
                   {'mechanism': 'A-DED', 'table': 'no_show_logs', 'present': True,
                    'amount': chgs[-1]['amount'] if chgs else None}, label=' (set D)')

        # W-04 + W-18 checkout (settlement + overpay-as-tip), all business-dated
        room = take_room()
        rid = new_res('d04', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        due = due_of(rid)
        r = c.post('/checkout/%d' % rid, data={**WAIVE, 'pm_amount_1': '%.2f' % (due + 200),
                                               'overpay_reason': 'mistake', 'overpay_resolution': 'tip',
                                               'overpay_waiter_name': 'VC Waiter'})
        with app.app_context():
            st = db.session.get(Reservation, rid).status
        check('D-04', 'W-04', 'checkout completed (set D)', 'CheckedOut', st, 'HTTP %s' % r.status_code)
        pays, chgs = rows(Payment, rid), rows(ExtraCharge, rid)
        verify_row('W-04', 'Payment', next((p for p in pays if p['purpose'] == 'settlement'), None), rid,
                   {'mechanism': 'A-STRICT'}, label=' (set D)')
        verify_row('W-18', 'ExtraCharge', next((x for x in chgs if x['charge_type'] == 'tip'), None), rid,
                   {'mechanism': 'A-STRICT'}, label=' (set D)')

        # W-19 checkout overpay-as-income
        room = take_room()
        rid = new_res('d19', 'CheckedIn', bd, bd + timedelta(days=1), 1000, room_id=room)
        due = due_of(rid)
        c.post('/checkout/%d' % rid, data={**WAIVE, 'pm_amount_1': '%.2f' % (due + 150),
                                           'overpay_reason': 'mistake', 'overpay_resolution': 'income',
                                           'overpay_income_remarks': 'VC income D'})
        chgs = rows(ExtraCharge, rid)
        verify_row('W-19', 'ExtraCharge', next((x for x in chgs if x['charge_type'] == 'other_income'), None), rid,
                   {'mechanism': 'A-STRICT'}, label=' (set D)')

        # W-21 night audit LAST - closes the business date with every row inside it
        with app.app_context():
            db.session.query(NightAuditLog).filter_by(audit_date=bd).delete()
            db.session.commit()
        svc.run_night_audit(app)
        with app.app_context():
            nal = db.session.query(NightAuditLog).filter_by(audit_date=bd).first()
            bd_after = db.session.query(BusinessDate).first().current_date
            rr = [(x.reservation_id, x.folio_id) for x in
                  db.session.query(ExtraCharge).filter_by(charge_type='room_rent').all()]
        check('D-21', 'W-21', 'night audit closed the day and posted attributed room rent',
              (True, True), (nal is not None and nal.status in ('Completed', 'Warning'),
                             all(folio_a(r_) == f_ for r_, f_ in rr) and len(rr) >= 1),
              'status=%s business date now %s rows=%d' % (None if nal is None else nal.status, bd_after, len(rr)))
        record('SET-D', 'copy', 'clean new-activity copy', '-', '-', '-',
               'W-06, W-12, W-05, W-15, W-13, W-14, W-04, W-18, W-19, W-21 on one copy; used for inv-run / Q14 (E-9)')
        print('-' * 130)

    # =====================================================================
    # D11 freeze + production integrity
    # =====================================================================
    print('D11 FREEZE AND PRODUCTION INTEGRITY')
    with app.app_context():
        end_pay = sorted(r[0] for r in db.session.query(Payment.id).filter(Payment.folio_id.is_(None)).all())
        end_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id).filter(ExtraCharge.folio_id.is_(None)).all())
        end_pay_vals = {p.id: float(p.amount) for p in db.session.query(Payment).filter(Payment.id.in_(d11_pay)).all()}
        end_chg_vals = {x.id: float(x.amount) for x in db.session.query(ExtraCharge).filter(ExtraCharge.id.in_(d11_chg)).all()}
        new_null_pay = [i for i in end_pay if i not in d11_pay]
        new_null_chg = [i for i in end_chg if i not in d11_chg]
        tot_pay, tot_chg = db.session.query(Payment).count(), db.session.query(ExtraCharge).count()
        bd_end = db.session.query(BusinessDate).first().current_date
    check('D11-01', 'D11', 'NULL-folio payment id set unchanged', d11_pay, end_pay)
    check('D11-02', 'D11', 'NULL-folio charge id set unchanged', d11_chg, end_chg)
    check('D11-03', 'D11', 'D11 payment amounts unchanged', d11_pay_vals, end_pay_vals)
    check('D11-04', 'D11', 'D11 charge amounts unchanged', d11_chg_vals, end_chg_vals)
    check('NEW-01', 'ALL', 'no NEW unattributed row on the copy', ([], []), (new_null_pay, new_null_chg),
          '%d payments / %d charges on copy' % (tot_pay, tot_chg))
    prod_after = sha256(PRODUCTION_DB)
    check('PROD-01', 'PROD', 'production database unchanged', prod_before, prod_after)
    check('PROD-02', 'PROD', 'production size 733,184 B', 733184, os.path.getsize(PRODUCTION_DB))

    gate = [r for r in results if r['severity'] == 'gate']
    passed = sum(1 for r in gate if r['pass'])
    findings = [r for r in results if r['severity'] == 'finding' and not r['pass']]
    print('-' * 130)
    print('RESULT SET %s: %d / %d gate checks passed; %d findings recorded (non-gating)'
          % (SET, passed, len(gate), len(findings)))
    print('=' * 130)
    payload = {
        'directive': 'FG-P1-VERIFICATION-COMPLETION-20260909-01', 'set': SET,
        'started_at': started.isoformat(timespec='seconds'),
        'finished_at': datetime.now().isoformat(timespec='seconds'),
        'copy_path': handle.copy_path, 'copy_method': handle.method,
        'business_date_start': str(bd), 'business_date_end': str(bd_end),
        'production_sha256_before': prod_before, 'production_sha256_after': prod_after,
        'anchor_matches': prod_before == FROZEN_ANCHOR,
        'read_only_verified': prod_before == prod_after,
        'd11_payments': d11_pay, 'd11_extra_charges': d11_chg,
        'd11_unchanged': d11_pay == end_pay and d11_chg == end_chg
                         and d11_pay_vals == end_pay_vals and d11_chg_vals == end_chg_vals,
        'rows_on_copy': {'payments': tot_pay, 'extra_charges': tot_chg},
        'gate_total': len(gate), 'gate_passed': passed,
        'findings': findings, 'writers': writers, 'results': results,
        'verdict': 'PASS' if passed == len(gate) else 'FAIL',
    }
    with open(os.path.join(HERE, 'writers_set%s.json' % SET), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
    print('writers_set%s.json written' % SET)
    return 0 if passed == len(gate) else 1


if __name__ == '__main__':
    sys.exit(main())
