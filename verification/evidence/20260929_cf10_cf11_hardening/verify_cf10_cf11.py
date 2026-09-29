# -*- coding: utf-8 -*-
"""CF-10 / CF-11 hardening - runtime verification of financial write / audit coupling.

Baseline 683db72. Governing rule: Q-5 as widened by the Founder at Phase 1
acceptance (Q5-P1, FOUNDER_DECISIONS.md:1078): "ALL FINANCIAL MUTATIONS
SHOULD SATISFY STRICT AUDIT COUPLING". CF-10 is the register of the twelve
writers that did not (FOUNDER_DECISIONS.md:1080); CF-11 is the pre-existing
``Payment(notes=...)`` defect in settle_credit / redeem_credit_voucher
(FOUNDER_DECISIONS.md:1090-1092).

Every group runs on its own disposable copy made by verification.dbcopy.
Production is opened read-only for hashing only and must match the frozen
anchor before and after.

    venv\\Scripts\\python.exe verification\\evidence\\20260929_cf10_cf11_hardening\\verify_cf10_cf11.py GROUP
    venv\\Scripts\\python.exe verification\\evidence\\20260929_cf10_cf11_hardening\\verify_cf10_cf11.py all

Fault seams (test-process only; nothing under app/ is modified to create them)
------------------------------------------------------------------------------
F1  the audit row cannot be constructed - ``AuditLog.__init__`` raises.  A
    Python-level failure BEFORE the row reaches the session. This is the
    failure a swallowing audit writer hides: the session stays healthy and
    the financial row commits without its audit record.
F2  the audit INSERT fails inside the flush - a ``before_insert`` listener
    on AuditLog raises. A database-level failure.

Test classes per writer (directive section 14)
  A success        financial mutation persisted AND its audit persisted
  B audit failure  financial mutation rolled back (F1 and F2)
  C repeat         no duplicate financial effect, where applicable
  D invalid input  no partial financial mutation
  E actor          valid audit actor
Every check is a 'gate' (decides the verdict) unless marked 'finding'.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from verification.dbcopy import make_copy, assert_production_untouched   # noqa: E402
from verification.config import PRODUCTION_DB                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN_ANCHOR = '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2'
GROUPS = ['cf11', 'corr', 'w10', 'w12', 'w13', 'w14', 'w24', 'na', 'actor']

results = []


def check(case_id, writer, what, expect, got, note='', gate=True):
    ok = (expect == got)
    results.append({'case': case_id, 'writer': writer, 'what': what,
                    'expect': repr(expect), 'got': repr(got), 'pass': ok,
                    'severity': 'gate' if gate else 'finding', 'note': note})
    print('%-5s %-12s %-7s %-58s expect=%-22s got=%-22s %s'
          % (('OK' if ok else ('FAIL' if gate else 'NOTE')), case_id, writer,
             what[:58], repr(expect)[:22], repr(got)[:22], note))
    return ok


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ===========================================================================
# Environment shared by every group
# ===========================================================================

class Env:
    """App, fixtures and fault seams bound to one disposable copy."""

    def __init__(self, group):
        self.group = group
        self.handle = make_copy(name='cf10_%s.db' % group)
        os.environ['DATABASE_URL'] = 'sqlite:///' + self.handle.copy_path.replace('\\', '/')
        os.environ['FLASK_ENV'] = 'production'

        from app import create_app
        from app import models as m
        import app.services as svc
        import app.routes as routes_mod
        self.m, self.svc, self.routes = m, svc, routes_mod
        self.db = m.db
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

        db = self.db
        with self.app.app_context():
            u = m.User(username='cf10_admin', full_name='CF10 Admin', role='Admin', is_active=True)
            u.set_password('cf10-test-password')
            db.session.add(u)
            db.session.flush()
            self.admin_id = u.id
            seed_res = db.session.query(m.Reservation).order_by(m.Reservation.id).first()
            self.seed = {'guest': seed_res.guest_id, 'room_type': seed_res.room_type_id}
            self.bd = db.session.query(m.BusinessDate).first().current_date
            self.vacant = [r.id for r in db.session.query(m.Room).filter_by(status='Vacant')
                           .order_by(m.Room.id).all()]
            self.audit_before = db.session.query(m.AuditLog).count()
            db.session.commit()
        print('copy=%s  business date=%s  vacant=%d  admin=%d'
              % (self.handle.copy_path, self.bd, len(self.vacant), self.admin_id))
        self._seq = 0

    # -- fixtures -------------------------------------------------------------
    def take_room(self):
        return self.vacant.pop(0)

    def new_res(self, tag, status, arrival, departure, rate=1000, room_id=None, **extra):
        m, db = self.m, self.db
        self._seq += 1
        with self.app.app_context():
            r = m.Reservation(
                booking_reference='CF10-%s-%s-%d' % (self.group, tag, self._seq),
                guest_id=self.seed['guest'], room_id=room_id, room_type_id=self.seed['room_type'],
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
                db.session.get(m.Room, room_id).status = 'Occupied'
            db.session.commit()
            return r.id

    def folio_a(self, res_id):
        with self.app.app_context():
            f = (self.db.session.query(self.m.Folio)
                 .filter_by(reservation_id=res_id, folio_letter='A').first())
            return None if f is None else f.id

    def res_by_phone(self, phone):
        m, db = self.m, self.db
        with self.app.app_context():
            g = db.session.query(m.Guest).filter_by(phone=phone).first()
            if g is None:
                return None
            r = (db.session.query(m.Reservation).filter_by(guest_id=g.id)
                 .order_by(m.Reservation.id.desc()).first())
            return None if r is None else r.id

    def rows(self, model, res_id, **flt):
        with self.app.app_context():
            q = self.db.session.query(model).filter_by(reservation_id=res_id, **flt)
            return [{'id': x.id, 'folio_id': x.folio_id, 'amount': round(float(x.amount), 2),
                     'purpose': getattr(x, 'payment_purpose', None),
                     'charge_type': getattr(x, 'charge_type', None),
                     'is_reversal': getattr(x, 'is_reversal', None),
                     'is_voided': getattr(x, 'is_voided', None)}
                    for x in q.order_by(model.id).all()]

    def count(self, model, **flt):
        with self.app.app_context():
            return self.db.session.query(model).filter_by(**flt).count()

    def get(self, model, pk, attr):
        with self.app.app_context():
            obj = self.db.session.get(model, pk)
            return None if obj is None else getattr(obj, attr)

    def audits(self, entity_type, entity_id, action=None):
        m = self.m
        with self.app.app_context():
            q = self.db.session.query(m.AuditLog).filter_by(entity_type=entity_type,
                                                            entity_id=entity_id)
            if action:
                q = q.filter_by(action=action)
            return [{'action': a.action, 'after': a.after_state or {},
                     'actor': a.staff_user_id} for a in q.order_by(m.AuditLog.id).all()]

    def client(self):
        c = self.app.test_client()
        with c.session_transaction() as sess:
            sess['_user_id'] = str(self.admin_id)
            sess['_fresh'] = True
        return c

    @contextmanager
    def logged_ctx(self):
        from flask_login import login_user
        ctx = self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'})
        ctx.push()
        try:
            login_user(self.db.session.get(self.m.User, self.admin_id))
            yield
        finally:
            self.db.session.remove()
            ctx.pop()

    def call(self, fn):
        """Run a request or service call; an exception the test client
        propagates (TESTING) is caught, the session rolled back, and a
        500 stand-in returned. In production Flask answers 500 and the
        teardown rolls the session back, so nothing is committed either way."""
        try:
            return fn()
        except Exception as exc:
            with self.app.app_context():
                self.db.session.rollback()
            return _Exc(exc)

    # -- fault seams ----------------------------------------------------------
    @contextmanager
    def fault(self, kind):
        AuditLog = self.m.AuditLog
        if kind == 'F1':
            real = AuditLog.__init__

            def boom(obj, *a, **kw):
                raise RuntimeError('injected F1: audit row could not be constructed')
            AuditLog.__init__ = boom
            try:
                yield
            finally:
                AuditLog.__init__ = real
        elif kind == 'F2':
            from sqlalchemy import event

            def boom(mapper, conn, target):
                raise RuntimeError('injected F2: audit insert failed')
            event.listen(AuditLog, 'before_insert', boom)
            try:
                yield
            finally:
                event.remove(AuditLog, 'before_insert', boom)
        else:
            raise ValueError(kind)

    def finish(self):
        prod_after = assert_production_untouched(self.handle)
        return prod_after


class _Exc:
    def __init__(self, exc):
        self.status_code = 500
        self.exc = '%s: %s' % (exc.__class__.__name__, str(exc)[:120])

    def get_json(self):
        return None


def status(r):
    return getattr(r, 'status_code', None)


# ===========================================================================
# Group cf11 - settle_credit and redeem_credit_voucher (CF-11, W-11)
# ===========================================================================

def group_cf11(E):
    m, db = E.m, E.db
    c = E.client()
    with E.app.app_context():
        direct = (db.session.query(m.PaymentMode)
                  .filter_by(is_active=True, category='direct_payment')
                  .order_by(m.PaymentMode.id).first())
        mode_id = direct.id

    # ---- settle_credit ----------------------------------------------------
    print('CF-11 settle_credit via POST /credit/<rid>/settle')
    rid = E.new_res('credit', 'CheckedOut', E.bd - timedelta(days=2), E.bd - timedelta(days=1),
                    1000, credit_amount=1000, credit_settled_amount=0)
    pays0 = len(E.rows(m.Payment, rid))
    r = c.post('/credit/%d/settle' % rid, data={'amount': '400', 'payment_mode_id': str(mode_id),
                                                'reference_number': 'CF11-REF',
                                                'notes': 'CF11 settle note'})
    pays = E.rows(m.Payment, rid, payment_purpose='credit_recovery')
    check('CF11-S1a', 'CF-11', 'settle: HTTP redirect (not a failure page)', 302, status(r))
    check('CF11-S1b', 'CF-11', 'settle: one credit_recovery Payment created', 1, len(pays))
    p = pays[-1] if pays else {}
    check('CF11-S1c', 'CF-11', 'settle: payment amount', 400.0, p.get('amount'))
    check('CF11-S1d', 'CF-11', 'settle: payment on billing folio A', E.folio_a(rid), p.get('folio_id'))
    check('CF11-S1e', 'CF-11', 'settle: credit_settled_amount advanced', 400.0,
          float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
    au = E.audits('Payment', p.get('id'), 'posted') if p else []
    check('CF11-S1f', 'CF-11', 'settle: strict audit row on the Payment', 1, len(au))
    a = au[0] if au else {'after': {}, 'actor': None}
    check('CF11-S1g', 'CF-11', 'settle: operator note preserved in the audit', 'CF11 settle note',
          a['after'].get('notes'))
    check('CF11-S1h', 'CF-11', 'settle: audit actor is the operator', E.admin_id, a['actor'])
    check('CF11-S1i', 'CF-11', 'settle: audit amount matches', 400.0, a['after'].get('amount'))

    for kind in ('F1', 'F2'):
        before = (len(E.rows(m.Payment, rid)), float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
        with E.fault(kind):
            r = E.call(lambda: c.post('/credit/%d/settle' % rid,
                                      data={'amount': '100', 'payment_mode_id': str(mode_id),
                                            'notes': 'under fault'}))
        after = (len(E.rows(m.Payment, rid)), float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
        check('CF11-S2-%s' % kind, 'CF-11', 'settle under %s: no payment, credit unchanged' % kind,
              before, after, 'HTTP %s' % status(r))

    before = (len(E.rows(m.Payment, rid)), float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
    r = c.post('/credit/%d/settle' % rid, data={'amount': '5000', 'payment_mode_id': str(mode_id)})
    after = (len(E.rows(m.Payment, rid)), float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
    check('CF11-S3', 'CF-11', 'settle: amount above remaining refused, nothing written', before, after,
          'HTTP %s' % status(r))

    r = c.post('/credit/%d/settle' % rid, data={'amount': '600', 'payment_mode_id': str(mode_id)})
    pays = E.rows(m.Payment, rid, payment_purpose='credit_recovery')
    check('CF11-S4a', 'CF-11', 'settle: second (final) settlement posts', 2, len(pays), 'HTTP %s' % status(r))
    check('CF11-S4b', 'CF-11', 'settle: credit fully settled', 1000.0,
          float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
    au = E.audits('Payment', pays[-1]['id'], 'posted') if pays else []
    check('CF11-S4c', 'CF-11', 'settle: blank note recorded as None in audit', None,
          (au[0]['after'].get('notes', 'MISSING') if au else 'NO AUDIT'))
    r = c.post('/credit/%d/settle' % rid, data={'amount': '10', 'payment_mode_id': str(mode_id)})
    check('CF11-S4d', 'CF-11', 'settle: settled credit accepts no further payment', 2,
          len(E.rows(m.Payment, rid, payment_purpose='credit_recovery')), 'HTTP %s' % status(r))
    check('CF11-S0', 'CF-11', 'settle: no stray payments on the reservation', pays0 + 2,
          len(E.rows(m.Payment, rid)))

    # ---- redeem_credit_voucher via the voucher API -------------------------
    print('W-11 / CF-11 redeem_credit_voucher via POST /api/voucher/<id>/redeem')
    room = E.take_room()
    rid = E.new_res('w11', 'CheckedIn', E.bd, E.bd + timedelta(days=1), 1000, room_id=room)
    with E.app.app_context():
        v = m.CreditVoucher(voucher_code='CF11-V1', guest_id=E.seed['guest'], issued_amount=500,
                            redeemed_amount=0, issued_date=date.today(), status='active',
                            issued_by_user_id=E.admin_id)
        db.session.add(v)
        db.session.commit()
        vid = v.id

    def vstate():
        return (len(E.rows(m.Payment, rid)), E.count(m.CreditVoucherRedemption, voucher_id=vid),
                round(float(E.get(m.CreditVoucher, vid, 'redeemed_amount') or 0), 2))

    r = c.post('/api/voucher/%d/redeem' % vid,
               json={'reservation_id': rid, 'amount': 200, 'notes': 'CF11 redeem note'})
    js = r.get_json() or {}
    check('W11-R1a', 'W-11', 'redeem: HTTP 200 success', (200, True), (status(r), js.get('success')),
          str(js)[:80])
    pays = E.rows(m.Payment, rid, payment_purpose='settlement')
    check('W11-R1b', 'W-11', 'redeem: one settlement Payment', 1, len(pays))
    p = pays[-1] if pays else {}
    check('W11-R1c', 'W-11', 'redeem: payment amount', 200.0, p.get('amount'))
    check('W11-R1d', 'W-11', 'redeem: payment on billing folio A', E.folio_a(rid), p.get('folio_id'))
    check('W11-R1e', 'W-11', 'redeem: voucher redeemed_amount', 200.0, vstate()[2])
    with E.app.app_context():
        red = (db.session.query(m.CreditVoucherRedemption).filter_by(voucher_id=vid)
               .order_by(m.CreditVoucherRedemption.id.desc()).first())
        red_note = red.notes if red else None
        red_pay = red.payment_id if red else None
        ref = db.session.get(m.Payment, p['id']).reference_number if p else None
    check('W11-R1f', 'W-11', 'redeem: redemption row keeps the note', 'CF11 redeem note', red_note)
    check('W11-R1g', 'W-11', 'redeem: redemption links the payment', p.get('id'), red_pay)
    check('W11-R1h', 'W-11', 'redeem: payment reference carries voucher code', 'VOUCHER:CF11-V1', ref)
    au = E.audits('Payment', p.get('id'), 'posted') if p else []
    check('W11-R1i', 'W-11', 'redeem: strict audit row on the Payment', 1, len(au))
    a = au[0] if au else {'after': {}, 'actor': None}
    check('W11-R1j', 'W-11', 'redeem: payment audit names voucher and amount', ('CF11-V1', 200.0),
          (a['after'].get('voucher_code'), a['after'].get('amount')))
    check('W11-R1k', 'W-11', 'redeem: payment audit actor is the operator', E.admin_id, a['actor'])
    vu = E.audits('CreditVoucher', vid, 'voucher_used')
    check('W11-R1l', 'W-11', 'redeem: voucher_used audit on the voucher', 1, len(vu))

    for kind in ('F1', 'F2'):
        before = vstate()
        with E.fault(kind):
            r = E.call(lambda: c.post('/api/voucher/%d/redeem' % vid,
                                      json={'reservation_id': rid, 'amount': 50}))
        check('W11-R2-%s' % kind, 'W-11', 'redeem under %s: no payment/redemption/balance change' % kind,
              before, vstate(), 'HTTP %s' % status(r))

    before = vstate()
    r = c.post('/api/voucher/%d/redeem' % vid, json={'reservation_id': rid, 'amount': 1000})
    check('W11-R3', 'W-11', 'redeem: amount above balance refused, nothing written', (400, before),
          (status(r), vstate()))

    # ---- redeem_credit_voucher via the booking form -------------------------
    print('W-11 / CF-11 redeem_credit_voucher via POST /reservations/new (voucher applied at booking)')
    cal = date.today()

    def booking(phone):
        return dict(first_name='CF11', last_name='Voucher', guest_phone=phone,
                    guest_email='cf11%s@example.com' % phone[-2:], room_type_id='2',
                    arrival_date=(cal + timedelta(days=2)).isoformat(),
                    departure_date=(cal + timedelta(days=3)).isoformat(),
                    adults='1', children='0', rate='1000', advance_payment='0',
                    payment_mode_id='1', source='Walk-in',
                    voucher_id=str(vid), voucher_redeem_amount='100')
    r = E.call(lambda: c.post('/reservations/new', data=booking('9000001101')))
    brid = E.res_by_phone('9000001101')
    check('W11-B1a', 'W-11', 'booking+voucher: booking saved (redirect)', (302, True),
          (status(r), brid is not None), getattr(r, 'exc', ''))
    bp = E.rows(m.Payment, brid, payment_purpose='settlement') if brid else []
    check('W11-B1b', 'W-11', 'booking+voucher: settlement Payment on the booking', [100.0],
          [x['amount'] for x in bp])
    check('W11-B1c', 'W-11', 'booking+voucher: voucher balance consumed', 300.0, vstate()[2])

    for kind in ('F1',):
        res_before, bal_before = E.count(m.Reservation), vstate()[2]
        with E.fault(kind):
            r = E.call(lambda: c.post('/reservations/new', data=booking('9000001102')))
        check('W11-B2-%s' % kind, 'W-11', 'booking+voucher under %s: no booking, no voucher use' % kind,
              (res_before, bal_before), (E.count(m.Reservation), vstate()[2]),
              'HTTP %s %s' % (status(r), getattr(r, 'exc', '')))
        check('W11-B3-%s' % kind, 'W-11', 'booking+voucher under %s: form re-rendered, not HTTP 500' % kind,
              200, status(r))


# ===========================================================================
# Group corr - post_payment_correction (W-08/09), post_extra_charge_correction (W-22/23)
# ===========================================================================

def group_corr(E):
    m, db, svc = E.m, E.db, E.svc
    c = E.client()
    locked_day = date(2026, 8, 9)       # the copy's closed, sealed audit date

    def locked_payment(tag, amount):
        room = E.take_room()
        rid = E.new_res(tag, 'CheckedIn', E.bd, E.bd + timedelta(days=1), 1000, room_id=room)
        c.post('/api/reservation/%d/add-payment' % rid, json={'amount': amount})
        p0 = E.rows(m.Payment, rid)[-1]
        # Copy-only fixture edit of a row this script created: move it onto
        # the locked date so the void routes take the correction-pair path.
        with E.app.app_context():
            db.session.get(m.Payment, p0['id']).payment_date = locked_day
            db.session.commit()
        return rid, p0

    for route, url, reason_field in (('routes.void_payment', '/payment/%d/void', 'void_reason'),
                                     ('billing.direct_void', '/billing/void/direct/%d', 'reason')):
        print('W-08 / W-09 post_payment_correction via %s' % route)
        tag = 'R' if route.startswith('routes') else 'B'
        rid, p0 = locked_payment('corr' + tag, 300.0)
        with E.app.app_context():
            locked = svc.get_locking_audit(locked_day) is not None
        check('W08-%s-00' % tag, 'W-08', 'fixture payment sits on an audit-locked date', True, locked)
        form = {reason_field: 'CF10 void', 'audit_override': '1',
                'audit_override_reason': 'CF10 override',
                'correction_new_amount': '250', 'correction_new_mode_id': '1'}
        r = c.post(url % p0['id'], data=form)
        pays = E.rows(m.Payment, rid)
        rev = [x for x in pays if x['is_reversal'] and x['id'] != p0['id']]
        rep = [x for x in pays if not x['is_reversal'] and x['id'] != p0['id']]
        check('W08-%s-01' % tag, 'W-08', 'reversal row posted', 1, len(rev), 'HTTP %s' % status(r))
        check('W09-%s-01' % tag, 'W-09', 'replacement row posted', 1, len(rep))
        check('W08-%s-02' % tag, 'W-08', 'original row untouched (not voided)', False,
              E.get(m.Payment, p0['id'], 'is_voided'))
        for wid, rows_, action, key in (('W-08', rev, 'payment_reversed', 'reversal_amount'),
                                        ('W-09', rep, 'payment_corrected', 'replacement_amount')):
            au = E.audits('Payment', rows_[0]['id'], action) if rows_ else []
            check('%s-%s-03' % (wid.replace('-', ''), tag), wid, 'strict audit %s on the row' % action,
                  1, len(au))
            a = au[0] if au else {'after': {}, 'actor': None}
            check('%s-%s-04' % (wid.replace('-', ''), tag), wid, 'audit carries the row amount',
                  rows_[0]['amount'] if rows_ else None, a['after'].get(key))
            check('%s-%s-05' % (wid.replace('-', ''), tag), wid, 'audit actor is the operator',
                  E.admin_id, a['actor'])

        for kind in ('F1', 'F2'):
            rid2, p2 = locked_payment('corr%s%s' % (tag, kind), 200.0)
            before = E.rows(m.Payment, rid2)
            with E.fault(kind):
                r = E.call(lambda: c.post(url % p2['id'], data=form))
            check('W08-%s-B-%s' % (tag, kind), 'W-08/09',
                  'correction under %s: no reversal/replacement, original intact' % kind,
                  before, E.rows(m.Payment, rid2), 'HTTP %s' % status(r))

    # ---- W-22 / W-23 --------------------------------------------------------
    print('W-22 / W-23 post_extra_charge_correction - service only (no application caller)')

    def fixture_charge(tag):
        room = E.take_room()
        rid = E.new_res(tag, 'CheckedIn', E.bd, E.bd + timedelta(days=1), 1000, room_id=room)
        with E.app.app_context():
            res = db.session.get(m.Reservation, rid)
            ec = m.ExtraCharge(reservation_id=rid, folio_id=svc.resolve_billing_folio_id(res),
                               description='CF10 fixture charge', amount=300.0,
                               charge_date=E.bd, charge_type='misc')
            db.session.add(ec)
            db.session.commit()
            return rid, ec.id, ec.folio_id

    rid, orig_id, orig_folio = fixture_charge('w22')
    with E.logged_ctx():
        out = svc.post_extra_charge_correction(db.session.get(m.ExtraCharge, orig_id),
                                               new_amount=150.0, reason='CF10 charge correction',
                                               user_id=E.admin_id, audit_writer=None)
        db.session.commit()
        rev_id, rep_id = out['reversal'].id, out['replacement'].id
    for wid, cid, action, key, amt in (('W-22', rev_id, 'charge_reversed', 'reversal_amount', 300.0),
                                       ('W-23', rep_id, 'charge_corrected', 'replacement_amount', 150.0)):
        n = wid.replace('-', '')
        check('%s-01' % n, wid, 'row posted and inherits the original folio (R-3)', orig_folio,
              E.get(m.ExtraCharge, cid, 'folio_id'))
        au = E.audits('ExtraCharge', cid, action)
        check('%s-02' % n, wid, 'strict audit %s written without any audit_writer' % action, 1, len(au))
        a = au[0] if au else {'after': {}, 'actor': None}
        check('%s-03' % n, wid, 'audit carries the row amount', amt, a['after'].get(key))
        check('%s-04' % n, wid, 'audit actor is the operator', E.admin_id, a['actor'])

    for kind in ('F1', 'F2'):
        rid2, oid2, _ = fixture_charge('w22%s' % kind)
        before = E.count(m.ExtraCharge, reservation_id=rid2)
        raised = None
        with E.fault(kind), E.logged_ctx():
            try:
                svc.post_extra_charge_correction(db.session.get(m.ExtraCharge, oid2), new_amount=100.0,
                                                 reason='CF10 under fault', user_id=E.admin_id)
                db.session.commit()
            except Exception as exc:
                raised = exc.__class__.__name__
                db.session.rollback()
        check('W22-B-%s' % kind, 'W-22/23', 'correction under %s: service raises' % kind, True,
              raised is not None, str(raised))
        check('W22-C-%s' % kind, 'W-22/23', 'correction under %s: no rows persisted' % kind, before,
              E.count(m.ExtraCharge, reservation_id=rid2))

    rid3, oid3, _ = fixture_charge('w22inv')
    before = E.count(m.ExtraCharge, reservation_id=rid3)
    raised = None
    with E.logged_ctx():
        try:
            svc.post_extra_charge_correction(db.session.get(m.ExtraCharge, oid3), new_amount=100.0,
                                             reason='   ', user_id=E.admin_id)
            db.session.commit()
        except ValueError as exc:
            raised = str(exc)
            db.session.rollback()
    check('W22-D', 'W-22/23', 'blank reason refused, no rows', (True, before),
          (raised is not None, E.count(m.ExtraCharge, reservation_id=rid3)))


# ===========================================================================
# Group w10 - refund inside post_cancellation_disposition, via the cancel route
# ===========================================================================

def group_w10(E):
    m, db = E.m, E.db
    c = E.client()
    cal = date.today()
    import app.notifications as notif
    real_notify = notif.notify_booking_cancelled
    # Notifications are replaced by a no-op that never commits, so the test
    # proves the cancellation's audit rows do not depend on the incidental
    # commit a notification helper happens to perform.
    notif.notify_booking_cancelled = lambda *a, **kw: None

    def booked(phone, advance='300'):
        form = dict(first_name='CF10', last_name='Cancel', guest_phone=phone,
                    guest_email='cf10%s@example.com' % phone[-2:], room_type_id='2',
                    arrival_date=(cal + timedelta(days=2)).isoformat(),
                    departure_date=(cal + timedelta(days=3)).isoformat(),
                    adults='1', children='0', rate='1000', advance_payment=advance,
                    payment_mode_id='1', source='Walk-in')
        c.post('/reservations/new', data=form)
        return E.res_by_phone(phone)

    try:
        print('W-10 refund via POST /reservation/<rid>/cancel (refund_full)')
        rid = booked('9000001001')
        r = c.post('/reservation/%d/cancel' % rid,
                   data={'cancel_disposition': 'refund_full', 'cancel_reason': 'CF10 cancel',
                         'cancel_refund_mode_id': '1'})
        refunds = [x for x in E.rows(m.Payment, rid) if x['purpose'] == 'refund']
        check('W10-01', 'W-10', 'refund Payment posted', 1, len(refunds), 'HTTP %s' % status(r))
        check('W10-02', 'W-10', 'reservation cancelled', 'Cancelled', E.get(m.Reservation, rid, 'status'))
        rf = refunds[-1] if refunds else {}
        check('W10-03', 'W-10', 'refund on billing folio A', E.folio_a(rid), rf.get('folio_id'))
        au = E.audits('Payment', rf.get('id'), 'cancellation_refund') if rf else []
        check('W10-04', 'W-10', 'strict audit cancellation_refund on the refund', 1, len(au))
        a = au[0] if au else {'after': {}, 'actor': None}
        check('W10-05', 'W-10', 'audit carries refund amount', 300.0, a['after'].get('refund_amount'))
        check('W10-06', 'W-10', 'audit actor is the operator', E.admin_id, a['actor'])
        ca = E.audits('Reservation', rid, 'cancelled')
        check('W10-07', 'W-10', "reservation 'cancelled' audit persisted without a notification commit",
              1, len(ca))
        check('W10-08', 'W-10', "'cancelled' audit carries the refund amount", 300.0,
              (ca[0]['after'].get('refund_amount') if ca else None))

        print('W-10 forfeit disposition via the cancel route')
        rid = booked('9000001002')
        r = c.post('/reservation/%d/cancel' % rid,
                   data={'cancel_disposition': 'forfeit', 'cancel_reason': 'CF10 forfeit'})
        ca = E.audits('Reservation', rid, 'cancelled')
        check('W10-09', 'W-10', 'forfeit: cancelled, forfeit audit persisted', ('Cancelled', 1, 300.0),
              (E.get(m.Reservation, rid, 'status'), len(ca),
               ca[0]['after'].get('forfeit_amount') if ca else None), 'HTTP %s' % status(r))

        print('W-10 credit_voucher disposition (voucher leg unchanged, still non-blocking)')
        rid = booked('9000001003')
        vbefore = E.count(m.CreditVoucher)
        r = c.post('/reservation/%d/cancel' % rid,
                   data={'cancel_disposition': 'credit_voucher', 'cancel_reason': 'CF10 voucher',
                         'cancel_voucher_amount': '300'})
        with E.app.app_context():
            v = (db.session.query(m.CreditVoucher).filter_by(issued_from_reservation_id=rid)
                 .order_by(m.CreditVoucher.id.desc()).first())
            vamt = None if v is None else round(float(v.issued_amount), 2)
        ca = E.audits('Reservation', rid, 'cancellation_disposition')
        check('W10-10', 'W-10', 'credit_voucher: cancelled, voucher issued, disposition audited',
              ('Cancelled', vbefore + 1, 300.0, 1),
              (E.get(m.Reservation, rid, 'status'), E.count(m.CreditVoucher), vamt, len(ca)),
              'HTTP %s' % status(r))

        for kind in ('F1', 'F2'):
            for disp in ('refund_full', 'forfeit'):
                rid = booked('90000011%s%d' % (kind[-1], 1 if disp == 'refund_full' else 2))
                before = (E.get(m.Reservation, rid, 'status'), E.rows(m.Payment, rid),
                          float(E.get(m.Reservation, rid, 'cancellation_amount_forfeited') or 0))
                with E.fault(kind):
                    r = E.call(lambda: c.post('/reservation/%d/cancel' % rid,
                                              data={'cancel_disposition': disp,
                                                    'cancel_reason': 'CF10 under fault',
                                                    'cancel_refund_mode_id': '1'}))
                after = (E.get(m.Reservation, rid, 'status'), E.rows(m.Payment, rid),
                         float(E.get(m.Reservation, rid, 'cancellation_amount_forfeited') or 0))
                check('W10-B-%s-%s' % (kind, disp), 'W-10',
                      '%s under %s: not cancelled, no refund, no forfeit' % (disp, kind),
                      before, after, 'HTTP %s' % status(r))
    finally:
        notif.notify_booking_cancelled = real_notify


# ===========================================================================
# Driver
# ===========================================================================

def run_group(group):
    started = datetime.now()
    prod_before = sha256(PRODUCTION_DB)
    print('=' * 140)
    print('CF-10 / CF-11 HARDENING - GROUP %s' % group)
    print('production sha256 before: %s (%s)' % (prod_before, 'anchor' if prod_before == FROZEN_ANCHOR
                                                   else '*** MISMATCH ***'))
    print('=' * 140)
    E = Env(group)
    fn = globals().get('group_' + group)
    if fn is None:
        raise SystemExit('unknown group %s' % group)
    fn(E)
    prod_after = E.finish()
    check('P-01', 'prod', 'production database unchanged (sha256 == anchor)', FROZEN_ANCHOR, prod_after)
    gates = [x for x in results if x['severity'] == 'gate']
    passed = sum(1 for x in gates if x['pass'])
    out = {'group': group, 'started': started.isoformat(timespec='seconds'),
           'finished': datetime.now().isoformat(timespec='seconds'),
           'copy': E.handle.copy_path, 'copy_method': E.handle.method,
           'production_sha256_before': prod_before, 'production_sha256_after': prod_after,
           'gates_total': len(gates), 'gates_passed': passed,
           'verdict': 'PASS' if passed == len(gates) else 'FAIL', 'checks': results}
    label = os.environ.get('CF10_RUN_LABEL', 'run')
    with open(os.path.join(HERE, 'results_%s_%s.json' % (label, group)), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2)
    print('-' * 140)
    print('GROUP %s: %d/%d gates passed -> %s' % (group, passed, len(gates), out['verdict']))
    return 0 if out['verdict'] == 'PASS' else 1


def main():
    args = sys.argv[1:] or ['all']
    if args == ['all']:
        rc = 0
        for g in GROUPS:
            if 'group_' + g not in globals():
                print('group %s: not implemented in this revision' % g)
                continue
            rc |= subprocess.call([sys.executable, os.path.abspath(__file__), g])
        return rc
    rc = 0
    for g in args:
        rc |= run_group(g)
    return rc


if __name__ == '__main__':
    sys.exit(main())
