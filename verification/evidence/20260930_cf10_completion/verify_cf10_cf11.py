# -*- coding: utf-8 -*-
"""CF-10 / CF-11 hardening - runtime verification of financial write / audit coupling.

Revision 2 (20260930_cf10_completion). Extends the 20260929 harness, which
stays unchanged next to the results it produced, with:
  * groups ``na`` (W-16 / W-21 night-audit room-rent writers), ``voucher``
    (CreditVoucher issuance on the W-10 cancellation path) and ``actor``
    (system-actor behaviour under FK-enforced SQLite);
  * the application commit and app root recorded in every result file;
  * ``CF10_APP_ROOT``: import ``app`` from another checkout (a git worktree
    at a baseline commit) so a RED run never modifies the working tree.
    ``verification`` is always imported from this repository, so the
    production path and the copy mechanism are the same in both runs.

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

APP_ROOT = os.path.abspath(os.environ.get('CF10_APP_ROOT') or REPO)
if not os.path.isfile(os.path.join(APP_ROOT, 'app', '__init__.py')):
    raise SystemExit('CF10_APP_ROOT %s has no app package' % APP_ROOT)
if APP_ROOT != REPO:
    sys.path.insert(0, APP_ROOT)          # ``app`` resolves here; verification already imported
import app as _app_pkg                                                    # noqa: E402
if not os.path.normcase(os.path.abspath(_app_pkg.__file__)).startswith(
        os.path.normcase(os.path.join(APP_ROOT, 'app'))):
    raise SystemExit('app resolved to %s, not under %s' % (_app_pkg.__file__, APP_ROOT))


def _git(*args):
    try:
        return subprocess.check_output(['git', '-C', APP_ROOT] + list(args),
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


APP_COMMIT = _git('rev-parse', 'HEAD')
APP_DIRTY = _git('status', '--porcelain', '--', 'app')

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('CF10_OUT_DIR') or HERE
FROZEN_ANCHOR = '51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2'
GROUPS = ['cf11', 'corr', 'w10', 'voucher', 'w12', 'w13', 'w14', 'w24', 'na', 'actor']

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
            return [{'action': a.action, 'before': a.before_state or {},
                     'after': a.after_state or {}, 'actor': a.staff_user_id}
                    for a in q.order_by(m.AuditLog.id).all()]

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
    def fault(self, kind, only=None):
        """Inject F1 or F2. ``only(entity_type, action)`` narrows the fault to
        the matching audit rows, so a test can fail exactly the audit it is
        about rather than an earlier, unrelated one in the same request."""
        AuditLog = self.m.AuditLog
        hit = (lambda et, ac: True) if only is None else only
        if kind == 'F1':
            real = AuditLog.__init__

            def boom(obj, *a, **kw):
                if hit(kw.get('entity_type'), kw.get('action')):
                    raise RuntimeError('injected F1: audit row could not be constructed')
                return real(obj, *a, **kw)
            AuditLog.__init__ = boom
            try:
                yield
            finally:
                AuditLog.__init__ = real
        elif kind == 'F2':
            from sqlalchemy import event

            def boom(mapper, conn, target):
                if not hit(target.entity_type, target.action):
                    return
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
        for tname, pred in (('any', None), ('payment', lambda et, ac: et == 'Payment')):
            before = (len(E.rows(m.Payment, rid)), float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
            with E.fault(kind, only=pred):
                r = E.call(lambda: c.post('/credit/%d/settle' % rid,
                                          data={'amount': '100', 'payment_mode_id': str(mode_id),
                                                'notes': 'under fault'}))
            after = (len(E.rows(m.Payment, rid)), float(E.get(m.Reservation, rid, 'credit_settled_amount') or 0))
            check('CF11-S2-%s-%s' % (kind, tname), 'CF-11',
                  'settle, %s on %s audit: no payment, credit unchanged' % (kind, tname),
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
        for tname, pred in (('any', None),
                            ('payment', lambda et, ac: et == 'Payment'),
                            ('voucher_used', lambda et, ac: ac == 'voucher_used')):
            before = vstate()
            with E.fault(kind, only=pred):
                r = E.call(lambda: c.post('/api/voucher/%d/redeem' % vid,
                                          json={'reservation_id': rid, 'amount': 50}))
            check('W11-R2-%s-%s' % (kind, tname), 'W-11',
                  'redeem, %s on %s audit: no payment/redemption/balance change' % (kind, tname),
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

    for n, (kind, tname, pred) in enumerate((('F1', 'any', None),
                                             ('F1', 'payment', lambda et, ac: et == 'Payment'),
                                             ('F2', 'voucher_used', lambda et, ac: ac == 'voucher_used'))):
        res_before, bal_before = E.count(m.Reservation), vstate()[2]
        with E.fault(kind, only=pred):
            r = E.call(lambda: c.post('/reservations/new', data=booking('90000011%02d' % (n + 2))))
        check('W11-B2-%s-%s' % (kind, tname), 'W-11',
              'booking+voucher, %s on %s audit: no booking, no voucher use' % (kind, tname),
              (res_before, bal_before), (E.count(m.Reservation), vstate()[2]),
              'HTTP %s %s' % (status(r), getattr(r, 'exc', '')))
        check('W11-B3-%s-%s' % (kind, tname), 'W-11',
              'booking+voucher, %s on %s audit: form re-rendered, not HTTP 500' % (kind, tname),
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
            for tname in ('any', 'payment_reversed', 'payment_corrected'):
                pred = None if tname == 'any' else (lambda et, ac, t=tname: ac == t)
                rid2, p2 = locked_payment('corr%s%s%s' % (tag, kind, tname[8:11]), 200.0)
                before = E.rows(m.Payment, rid2)
                with E.fault(kind, only=pred):
                    r = E.call(lambda: c.post(url % p2['id'], data=form))
                check('W08-%s-B-%s-%s' % (tag, kind, tname), 'W-08/09',
                      'correction, %s on %s audit: nothing posted, original intact' % (kind, tname),
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
        with E.fault(kind, only=lambda et, ac: et == 'ExtraCharge'), E.logged_ctx():
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

        cases = [(k, d, t) for k in ('F1', 'F2')
                 for d, ts in (('refund_full', ('any', 'cancellation_refund',
                                                'cancellation_disposition', 'cancelled')),
                               ('forfeit', ('any', 'forfeit_approved', 'cancelled')))
                 for t in ts]
        for n, (kind, disp, tname) in enumerate(cases):
            pred = None if tname == 'any' else (lambda et, ac, t=tname: ac == t)
            rid = booked('900000%04d' % (1200 + n))
            before = (E.get(m.Reservation, rid, 'status'), E.rows(m.Payment, rid),
                      float(E.get(m.Reservation, rid, 'cancellation_amount_forfeited') or 0))
            with E.fault(kind, only=pred):
                r = E.call(lambda: c.post('/reservation/%d/cancel' % rid,
                                          data={'cancel_disposition': disp,
                                                'cancel_reason': 'CF10 under fault',
                                                'cancel_refund_mode_id': '1'}))
            after = (E.get(m.Reservation, rid, 'status'), E.rows(m.Payment, rid),
                     float(E.get(m.Reservation, rid, 'cancellation_amount_forfeited') or 0))
            check('W10-B-%s-%s-%s' % (kind, disp, tname), 'W-10',
                  '%s, %s on %s audit: not cancelled, nothing posted' % (disp, kind, tname),
                  before, after, 'HTTP %s' % status(r))
    finally:
        notif.notify_booking_cancelled = real_notify


# ===========================================================================
# Group w12 - deposit inside CheckInService.complete_full_checkin
# ===========================================================================

def group_w12(E):
    m, db, svc = E.m, E.db, E.svc

    def reserved(tag):
        return E.new_res(tag, 'Reserved', E.bd, E.bd + timedelta(days=1), 1000)

    def state(rid, room):
        with E.app.app_context():
            r = db.session.get(m.Reservation, rid)
            return {'status': r.status, 'room_status': db.session.get(m.Room, room).status,
                    'payments': db.session.query(m.Payment).filter_by(reservation_id=rid).count(),
                    'checkin_records': db.session.query(m.CheckInRecord)
                    .filter_by(reservation_id=rid).count()}

    def checkin(rid, room, deposit, mode='1'):
        form = {'room_id': str(room), 'deposit_amount': deposit, 'deposit_payment_mode_id': mode,
                'billing_responsibility': 'Guest'}
        with E.logged_ctx():
            try:
                svc.CheckInService.complete_full_checkin(rid, form, E.admin_id, '127.0.0.1')
                return None
            except Exception as exc:
                return '%s: %s' % (exc.__class__.__name__, str(exc)[:90])

    print('W-12 complete_full_checkin with a deposit')
    rid, room = reserved('w12'), E.take_room()
    err = checkin(rid, room, '500')
    st = state(rid, room)
    check('W12-01', 'W-12', 'check-in completes', (None, 'CheckedIn', 'Occupied'),
          (err, st['status'], st['room_status']))
    pays = E.rows(m.Payment, rid)
    check('W12-02', 'W-12', 'one deposit Payment of 500 on folio A', [(500.0, E.folio_a(rid))],
          [(x['amount'], x['folio_id']) for x in pays])
    au = E.audits('Payment', pays[0]['id'], 'posted') if pays else []
    check('W12-03', 'W-12', 'strict audit row on the deposit Payment', 1, len(au))
    a = au[0] if au else {'after': {}, 'actor': None}
    check('W12-04', 'W-12', 'deposit audit carries amount, folio, flow',
          (500.0, E.folio_a(rid), 'checkin_deposit'),
          (a['after'].get('amount'), a['after'].get('folio_id'), a['after'].get('flow')))
    check('W12-05', 'W-12', 'deposit audit actor is the operator', E.admin_id, a['actor'])
    ci = E.audits('Reservation', rid, 'checkin_full')
    check('W12-06', 'W-12', 'checkin_full audit on the reservation', (1, 500.0),
          (len(ci), ci[0]['after'].get('deposit') if ci else None))

    print('W-12 complete_full_checkin without a deposit')
    rid, room = reserved('w12nd'), E.take_room()
    err = checkin(rid, room, '0', mode='')
    st = state(rid, room)
    check('W12-07', 'W-12', 'no-deposit check-in completes, no payment, audited',
          (None, 'CheckedIn', 0, 1),
          (err, st['status'], st['payments'], len(E.audits('Reservation', rid, 'checkin_full'))))

    # Untargeted faults are caught by the earlier folio auto-creation audit,
    # so the targeted ones are what isolate this writer's own audit rows.
    targets = (('any', None),
               ('deposit', lambda et, ac: et == 'Payment'),
               ('checkin_full', lambda et, ac: ac == 'checkin_full'))
    for kind in ('F1', 'F2'):
        for tname, pred in targets:
            rid, room = reserved('w12%s%s' % (kind, tname[:3])), E.take_room()
            before = state(rid, room)
            with E.fault(kind, only=pred):
                err = checkin(rid, room, '500')
            check('W12-B-%s-%s' % (kind, tname), 'W-12',
                  'deposit check-in, %s fails on %s audit: refused, nothing persisted' % (kind, tname),
                  (True, before), (err is not None, state(rid, room)), str(err))

    for label, dep, mode in (('negative deposit', '-5', '1'), ('inactive/unknown mode', '500', '99999')):
        rid, room = reserved('w12inv'), E.take_room()
        before = state(rid, room)
        err = checkin(rid, room, dep, mode)
        check('W12-D-%s' % label.split()[0], 'W-12', '%s refused, nothing persisted' % label,
              (True, before), (err is not None, state(rid, room)), str(err))


# ===========================================================================
# Group w13 - cico_service.post_charge (early check-in / late check-out)
# ===========================================================================

def group_w13(E):
    m, db = E.m, E.db
    import app.cico_service as cico

    def in_house(tag):
        room = E.take_room()
        return E.new_res(tag, 'CheckedIn', E.bd - timedelta(days=1), E.bd, 1000, room_id=room)

    def like_checkout(rid, user_id, fault=None, only=None):
        """What routes.checkout / walkin check-in do: call post_charge inside
        try/except that logs and CONTINUES, then commit the rest of the
        request. A sentinel change made in the same transaction must survive."""
        err = None
        cm = E.fault(fault, only=only) if fault else _null()
        with cm, E.logged_ctx():
            res = db.session.get(m.Reservation, rid)
            res.checkout_initiated = True                       # sentinel
            try:
                cico.post_charge(res, 'late_checkout', 300.0, '02:00 PM - 30%',
                                 user_id=user_id, pct=30, actual_time_str='14:00')
            except Exception as exc:                            # swallowed like the route
                err = '%s: %s' % (exc.__class__.__name__, str(exc)[:80])
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                err = (err or '') + ' | COMMIT FAILED %s' % exc.__class__.__name__
        return err

    def st(rid):
        with E.app.app_context():
            return {'charges': db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).count(),
                    'cico_logs': db.session.query(m.CICOChargeLog).filter_by(reservation_id=rid).count(),
                    'sentinel': bool(db.session.get(m.Reservation, rid).checkout_initiated)}

    print('W-13 post_charge, operator actor, checkout-style caller')
    rid = in_house('w13')
    err = like_checkout(rid, E.admin_id)
    s = st(rid)
    check('W13-01', 'W-13', 'charge + CICO log posted, rest of request committed',
          (None, 1, 1, True), (err, s['charges'], s['cico_logs'], s['sentinel']))
    with E.app.app_context():
        ec = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).first()
        ecid, ecamt, ecf = (ec.id, round(float(ec.amount), 2), ec.folio_id) if ec else (None, None, None)
        lg = db.session.query(m.CICOChargeLog).filter_by(reservation_id=rid).first()
        lg_ec = lg.extra_charge_id if lg else None
    au = E.audits('ExtraCharge', ecid, 'posted') if ecid else []
    check('W13-02', 'W-13', 'strict posted audit on the charge row', 1, len(au))
    a = au[0] if au else {'after': {}, 'actor': None}
    check('W13-03', 'W-13', 'charge audit: amount, folio, charge_type, flow',
          (ecamt, ecf, 'late_checkout', 'cico'),
          (a['after'].get('amount'), a['after'].get('folio_id'), a['after'].get('charge_type'),
           a['after'].get('flow')))
    check('W13-04', 'W-13', 'charge audit actor is the operator', E.admin_id, a['actor'])
    ra = E.audits('Reservation', rid, 'auto_late_checkout_charge')
    check('W13-05', 'W-13', 'reservation audit names the charge row', (1, ecid, E.admin_id),
          (len(ra), ra[0]['after'].get('extra_charge_id') if ra else None, ra[0]['actor'] if ra else None))
    check('W13-06', 'W-13', 'CICO log links the charge row', ecid, lg_ec)

    print('W-13 repeat: idempotent')
    err = like_checkout(rid, E.admin_id)
    check('W13-C', 'W-13', 'second post for same type adds nothing', (None, 1), (err, st(rid)['charges']))

    print('W-13 missing actor inside an operator request')
    rid = in_house('w13na')
    err = like_checkout(rid, None)
    s = st(rid)
    with E.app.app_context():
        ec = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).first()
        ecid = ec.id if ec else None
    au = E.audits('ExtraCharge', ecid, 'posted') if ecid else []
    ra = E.audits('Reservation', rid, 'auto_late_checkout_charge')
    check('W13-E1', 'W-13', 'user_id=None: posted, both audits attributed to the logged-in operator',
          (None, 1, E.admin_id, E.admin_id),
          (err, s['charges'], au[0]['actor'] if au else None, ra[0]['actor'] if ra else None))

    targets = (('any', None),
               ('charge', lambda et, ac: et == 'ExtraCharge'),
               ('reservation', lambda et, ac: ac == 'auto_late_checkout_charge'))
    for kind in ('F1', 'F2'):
        for tname, pred in targets:
            rid = in_house('w13%s%s' % (kind, tname[:3]))
            err = like_checkout(rid, E.admin_id, fault=kind, only=pred)
            check('W13-B-%s-%s' % (kind, tname), 'W-13',
                  '%s on %s audit: no charge/log; rest of request commits' % (kind, tname),
                  {'charges': 0, 'cico_logs': 0, 'sentinel': True}, st(rid), str(err))

    rid = in_house('w13zero')
    with E.logged_ctx():
        out = cico.post_charge(db.session.get(m.Reservation, rid), 'late_checkout', 0.0, 'zero',
                               user_id=E.admin_id)
        db.session.commit()
    check('W13-D', 'W-13', 'zero amount: nothing posted', (None, 0), (out, st(rid)['charges']))


@contextmanager
def _null():
    yield


# ===========================================================================
# Group w14 - noshow_service.process_reservation_noshow
# ===========================================================================

def group_w14(E):
    m, db = E.m, E.db
    import app.noshow_service as ns
    with E.app.app_context():
        for k, v in (('noshow_fee_enabled', 'true'), ('noshow_fee_mode', 'fixed'),
                     ('noshow_fee_amount', '500')):
            row = db.session.query(m.Settings).filter_by(key=k).first()
            if row is None:
                db.session.add(m.Settings(key=k, value=v))
            else:
                row.value = v
        db.session.commit()

    def reserved(tag):
        return E.new_res(tag, 'Reserved', E.bd, E.bd + timedelta(days=1), 1000)

    def st(rid):
        with E.app.app_context():
            return {'status': db.session.get(m.Reservation, rid).status,
                    'fees': db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).count(),
                    'logs': db.session.query(m.NoShowLog).filter_by(reservation_id=rid).count()}

    def manual(rid):
        with E.logged_ctx():
            r = ns.manual_noshow(rid, E.admin_id, 'CF10 manual')
            return (getattr(r, 'success', None), str(getattr(r, 'message', ''))[:90])

    print('W-14 manual no-show with a fee')
    rid = reserved('w14')
    ok, msg = manual(rid)
    s = st(rid)
    check('W14-01', 'W-14', 'no-show posted with one fee and one log', (True, 'NoShow', 1, 1),
          (ok, s['status'], s['fees'], s['logs']), msg)
    with E.app.app_context():
        ec = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).first()
        ecid, ecamt, ecf = (ec.id, round(float(ec.amount), 2), ec.folio_id) if ec else (None, None, None)
    au = E.audits('ExtraCharge', ecid, 'posted') if ecid else []
    check('W14-02', 'W-14', 'strict posted audit on the fee row', 1, len(au))
    a = au[0] if au else {'after': {}, 'actor': None}
    check('W14-03', 'W-14', 'fee audit: amount, folio, flow, business date',
          (500.0, ecf, 'noshow_fee', str(E.bd)),
          (a['after'].get('amount'), a['after'].get('folio_id'), a['after'].get('flow'),
           a['after'].get('business_date')))
    check('W14-04', 'W-14', 'fee audit actor is the operator', E.admin_id, a['actor'])
    ra = E.audits('Reservation', rid, 'noshow_posted')
    check('W14-05', 'W-14', 'noshow_posted audit names the fee row', (1, ecid),
          (len(ra), ra[0]['after'].get('extra_charge_id') if ra else None))

    ok, msg = manual(rid)
    check('W14-C', 'W-14', 'repeat: refused, still one fee', (False, 1), (ok, st(rid)['fees']), msg)

    targets = (('any', None),
               ('fee', lambda et, ac: et == 'ExtraCharge'),
               ('noshow_posted', lambda et, ac: ac == 'noshow_posted'))
    for kind in ('F1', 'F2'):
        for tname, pred in targets:
            rid = reserved('w14%s%s' % (kind, tname[:3]))
            before = st(rid)
            with E.fault(kind, only=pred):
                ok, msg = manual(rid)
            check('W14-B-%s-%s' % (kind, tname), 'W-14',
                  '%s on %s audit: not a no-show, no fee, no log' % (kind, tname),
                  (False, before), (bool(ok), st(rid)), msg)

    print('W-14 automated (night-audit style) call: no operator, no request')
    rid = reserved('w14auto')
    with E.app.app_context():
        res = db.session.get(m.Reservation, rid)
        ns.process_reservation_noshow(res, E.bd, ns._get_noshow_config(), posted_by_user_id=None)
        db.session.commit()
        ec = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).first()
        ecid = ec.id if ec else None
        users0 = db.session.query(m.User).filter_by(id=0).count()
    au = E.audits('ExtraCharge', ecid, 'posted') if ecid else []
    check('W14-E1', 'W-14', 'automated: fee posted and strictly audited', (1, 1),
          (st(rid)['fees'], len(au)))
    check('W14-E2', 'W-14', 'automated: audit actor (system convention)', 0,
          au[0]['actor'] if au else None,
          'staff_user_id=0 with users.id=0 present: %d - FK-enforcing engines reject this; '
          'system identity is an open founder decision (AR-013 / ADR-011)' % users0, gate=False)


# ===========================================================================
# Group w24 - convert_overpayment_to_upsell (CASE A and CASE B), admin caller
# ===========================================================================

def group_w24(E):
    m, db, svc = E.m, E.db, E.svc
    c = E.client()

    def overpaid(tag, case_a):
        room = E.take_room()
        rid = E.new_res(tag, 'CheckedIn', E.bd - timedelta(days=1), E.bd + timedelta(days=1), 1000,
                        room_id=room)
        with E.app.app_context():
            res = db.session.get(m.Reservation, rid)
            fid = svc.resolve_billing_folio_id(res)
            if case_a:        # a night already posted by the night audit
                db.session.add(m.ExtraCharge(reservation_id=rid, folio_id=fid, amount=1000.0,
                                             description='Room Rent (CF10 fixture)',
                                             charge_date=E.bd - timedelta(days=1),
                                             charge_type='room_rent', charge_category='Room'))
            db.session.add(m.Payment(reservation_id=rid, folio_id=fid, payment_mode_id=1,
                                     amount=5000.0, payment_date=E.bd))
            db.session.commit()
        return rid

    def state(rid):
        with E.app.app_context():
            r = db.session.get(m.Reservation, rid)
            return {'rate': round(float(r.rate_per_night or 0), 2), 'adj': r.adjustment_type,
                    'upsell_rows': db.session.query(m.ExtraCharge)
                    .filter_by(reservation_id=rid, charge_type='room_upsell').count()}

    def convert(rid):
        return E.call(lambda: c.post('/admin/reservation/%d/convert-overpay-to-upsell' % rid,
                                     data={'reason': 'CF10 upsell', 'next': '/'}))

    for case_a in (True, False):
        case = 'A' if case_a else 'B'
        print('W-24 CASE %s via the admin route' % case)
        rid = overpaid('w24%s' % case, case_a)
        before = state(rid)
        r = convert(rid)
        after = state(rid)
        check('W24-%s-01' % case, 'W-24', 'conversion applied: rate raised, UPSELL stamped',
              (True, 'UPSELL'), (after['rate'] > before['rate'], after['adj']), 'HTTP %s' % status(r))
        check('W24-%s-02' % case, 'W-24', 'room_upsell rows (CASE A posts one, CASE B none)',
              1 if case_a else 0, after['upsell_rows'])
        ra = E.audits('Reservation', rid, 'overpayment_converted_to_upsell')
        check('W24-%s-03' % case, 'W-24', 'strict audit of the state transition on the reservation',
              1, len(ra))
        a = ra[0]['after'] if ra else {}
        check('W24-%s-04' % case, 'W-24', 'transition audit records old/new rate and branch',
              (before['rate'], after['rate'], True),
              ((ra[0]['before'].get('rate_per_night') if ra else None), a.get('rate_per_night'),
               str(a.get('branch', '')).startswith('case_%s' % case.lower())))
        check('W24-%s-05' % case, 'W-24', 'transition audit actor is the operator', E.admin_id,
              ra[0]['actor'] if ra else None)
        if case_a:
            with E.app.app_context():
                ch = (db.session.query(m.ExtraCharge).filter_by(reservation_id=rid, charge_type='room_upsell')
                      .first())
                chg = None if ch is None else (ch.id, round(float(ch.amount), 2), ch.folio_id)
            ca = E.audits('ExtraCharge', chg[0], 'posted') if chg else []
            check('W24-A-06', 'W-24', 'strict posted audit on the room_upsell charge', 1, len(ca))
            check('W24-A-07', 'W-24', 'charge audit carries amount and folio',
                  (chg[1], chg[2]) if chg else None,
                  ((ca[0]['after'].get('amount'), ca[0]['after'].get('folio_id')) if ca else None))
            check('W24-A-08', 'W-24', 'charge amount == pretax increment in the transition audit',
                  chg[1] if chg else None, a.get('pretax_increment'))
        adm = E.audits('Reservation', rid, 'admin_convert_overpay_to_upsell')
        check('W24-%s-09' % case, 'W-24', "admin route audit persisted (was added after the last commit)",
              1, len(adm))

    # The checkout caller converts inside the checkout's own transaction; its
    # audit rows must be committed by that checkout, not by anything later.
    def checkout_upsell(rid):
        return E.call(lambda: c.post('/checkout/%d' % rid,
                                     data={'overpay_resolution': 'upsell',
                                           'overpay_reason': 'upsell',
                                           'overpay_upsell_remarks': 'CF10 checkout upsell',
                                           'waive_late_checkout': '1',
                                           'waive_late_co_reason': 'CF10'}))

    def co_state(rid):
        s = state(rid)
        s['status'] = E.get(m.Reservation, rid, 'status')
        s['transition_audits'] = len(E.audits('Reservation', rid, 'overpayment_converted_to_upsell'))
        return s

    for case_a in (True, False):
        case = 'A' if case_a else 'B'
        print('W-24 CASE %s via POST /checkout (overpay_resolution=upsell)' % case)
        rid = overpaid('w24co%s' % case, case_a)
        r = checkout_upsell(rid)
        s = co_state(rid)
        ra = E.audits('Reservation', rid, 'overpayment_converted_to_upsell')
        a = ra[0] if ra else {'after': {}, 'actor': None}
        check('W24-CO-%s-01' % case, 'W-24',
              'checkout: checked out, UPSELL, one transition audit (branch, actor) committed',
              ('CheckedOut', 'UPSELL', 1, True, E.admin_id),
              (s['status'], s['adj'], s['transition_audits'],
               str(a['after'].get('branch', '')).startswith('case_%s' % case.lower()), a['actor']),
              'HTTP %s' % status(r))
        if case_a:
            with E.app.app_context():
                ch = (db.session.query(m.ExtraCharge)
                      .filter_by(reservation_id=rid, charge_type='room_upsell').first())
                chid = ch.id if ch else None
            check('W24-CO-A-02', 'W-24', 'checkout CASE A: room_upsell charge has its posted audit',
                  (True, 1), (chid is not None, len(E.audits('ExtraCharge', chid, 'posted')) if chid else 0))
        rid = overpaid('w24coF%s' % case, case_a)
        before = co_state(rid)
        with E.fault('F1', only=lambda et, ac: ac == 'overpayment_converted_to_upsell'):
            r = checkout_upsell(rid)
        check('W24-CO-%s-B' % case, 'W-24',
              'checkout, F1 on the transition audit: not checked out, nothing converted',
              before, co_state(rid), 'HTTP %s' % status(r))

    targets = (('any', None),
               ('transition', lambda et, ac: ac == 'overpayment_converted_to_upsell'),
               ('charge', lambda et, ac: et == 'ExtraCharge'),
               ('admin', lambda et, ac: ac == 'admin_convert_overpay_to_upsell'))
    for kind in ('F1', 'F2'):
        for case_a in (True, False):
            for tname, pred in targets:
                if tname == 'charge' and not case_a:
                    continue
                case = 'A' if case_a else 'B'
                rid = overpaid('w24%s%s%s' % (kind, case, tname[:3]), case_a)
                before = state(rid)
                with E.fault(kind, only=pred):
                    r = convert(rid)
                check('W24-B-%s-%s-%s' % (kind, case, tname), 'W-24',
                      'CASE %s, %s on %s audit: nothing converted' % (case, kind, tname),
                      before, state(rid), 'HTTP %s' % status(r))

    # The checkout caller (routes.checkout) calls the service inside its
    # outer try whose except rolls back. What it relies on is that the
    # service RAISES when an audit cannot be written - proven here directly.
    print('W-24 service contract relied on by the checkout caller')
    for kind in ('F1', 'F2'):
        rid = overpaid('w24svc%s' % kind, True)
        before = state(rid)
        raised = None
        with E.fault(kind, only=lambda et, ac: ac == 'overpayment_converted_to_upsell'), E.logged_ctx():
            try:
                svc.convert_overpayment_to_upsell(db.session.get(m.Reservation, rid), reason='svc',
                                                  authorized_by_user_id=E.admin_id)
                db.session.flush()
            except Exception as exc:
                raised = exc.__class__.__name__
            db.session.rollback()        # what checkout's outer except does
        check('W24-S-%s' % kind, 'W-24', 'service raises under %s; caller rollback leaves nothing' % kind,
              (True, before), (raised is not None, state(rid)), str(raised))

    print('W-24 no overpayment: refused, nothing written')
    room = E.take_room()
    rid = E.new_res('w24none', 'CheckedIn', E.bd, E.bd + timedelta(days=1), 1000, room_id=room)
    before = state(rid)
    r = convert(rid)
    check('W24-D', 'W-24', 'no overpayment: nothing converted, no transition audit', (before, 0),
          (state(rid), len(E.audits('Reservation', rid, 'overpayment_converted_to_upsell'))),
          'HTTP %s' % status(r))


# ===========================================================================
# Group voucher - CreditVoucher issuance on the W-10 cancellation path
# ===========================================================================

def group_voucher(E):
    """A credit voucher is a liability. The business rule that a failed
    issuance does not block the cancellation is kept; what is proven is
    that no voucher can commit without its audit row, and that a failure
    is itself on record."""
    m, db = E.m, E.db
    c = E.client()
    cal = date.today()
    import app.notifications as notif
    real_notify = notif.notify_booking_cancelled
    notif.notify_booking_cancelled = lambda *a, **kw: None

    def booked(phone):
        form = dict(first_name='CF10', last_name='Voucher', guest_phone=phone,
                    guest_email='cfv%s@example.com' % phone[-3:], room_type_id='2',
                    arrival_date=(cal + timedelta(days=2)).isoformat(),
                    departure_date=(cal + timedelta(days=3)).isoformat(),
                    adults='1', children='0', rate='1000', advance_payment='300',
                    payment_mode_id='1', source='Walk-in')
        c.post('/reservations/new', data=form)
        return E.res_by_phone(phone)

    def cancel(rid):
        return E.call(lambda: c.post('/reservation/%d/cancel' % rid,
                                     data={'cancel_disposition': 'credit_voucher',
                                           'cancel_reason': 'CF10 voucher',
                                           'cancel_voucher_amount': '300'}))

    def vouchers(rid):
        with E.app.app_context():
            return [(v.id, round(float(v.issued_amount), 2)) for v in
                    db.session.query(m.CreditVoucher).filter_by(issued_from_reservation_id=rid)
                    .order_by(m.CreditVoucher.id).all()]

    try:
        print('VOUCHER success: credit_voucher cancellation')
        rid = booked('9000003001')
        r = cancel(rid)
        vs = vouchers(rid)
        check('V-01', 'W-10v', 'cancelled, one voucher issued for 300',
              ('Cancelled', 1, 300.0), (E.get(m.Reservation, rid, 'status'), len(vs),
                                        vs[0][1] if vs else None), 'HTTP %s' % status(r))
        vid = vs[0][0] if vs else None
        au = E.audits('CreditVoucher', vid, 'voucher_created') if vid else []
        check('V-02', 'W-10v', 'strict voucher_created audit on the voucher', 1, len(au))
        a = au[0] if au else {'after': {}, 'actor': None}
        check('V-03', 'W-10v', 'voucher audit: amount, source reservation, actor',
              (300.0, rid, E.admin_id),
              (a['after'].get('issued_amount'), a['after'].get('issued_from_reservation_id'),
               a['actor']))
        da = E.audits('Reservation', rid, 'cancellation_disposition')
        check('V-04', 'W-10v', 'cancellation_disposition audit names the voucher row', vid,
              da[0]['after'].get('voucher_id') if da else None)

        print('VOUCHER audit failure: voucher rolled back, cancellation proceeds, failure recorded')
        for n, kind in enumerate(('F1', 'F2')):
            rid = booked('900000%d10%d' % (3, n))
            with E.fault(kind, only=lambda et, ac: ac == 'voucher_created'):
                r = cancel(rid)
            fa = E.audits('Reservation', rid, 'voucher_issue_failed')
            check('V-B-%s' % kind, 'W-10v',
                  '%s on voucher_created: no voucher, cancelled, voucher_issue_failed audited' % kind,
                  ([], 'Cancelled', 1, 300.0),
                  (vouchers(rid), E.get(m.Reservation, rid, 'status'), len(fa),
                   float(E.get(m.Reservation, rid, 'cancellation_amount_credit_voucher') or 0)),
                  'HTTP %s' % status(r))

        print('VOUCHER: failure AND its record fail -> whole cancellation rolled back')
        for n, kind in enumerate(('F1', 'F2')):
            rid = booked('900000%d20%d' % (3, n))
            before = (E.get(m.Reservation, rid, 'status'), E.rows(m.Payment, rid))
            with E.fault(kind, only=lambda et, ac: ac in ('voucher_created', 'voucher_issue_failed')):
                r = cancel(rid)
            check('V-C-%s' % kind, 'W-10v',
                  '%s on voucher_created + voucher_issue_failed: not cancelled, no voucher' % kind,
                  (before, []), ((E.get(m.Reservation, rid, 'status'), E.rows(m.Payment, rid)),
                                 vouchers(rid)), 'HTTP %s' % status(r))
    finally:
        notif.notify_booking_cancelled = real_notify


# ===========================================================================
# Group na - W-21 services.run_night_audit and W-16 reports._rerun_skipped_audit
# ===========================================================================

def group_na(E):
    m, db = E.m, E.db
    import app.services as svc
    import app.reports as rep
    c = E.client()

    def na_state(bd):
        with E.app.app_context():
            return {'logs': db.session.query(m.NightAuditLog).filter_by(audit_date=bd).count(),
                    'rent': db.session.query(m.ExtraCharge).filter_by(
                        charge_type='room_rent', charge_date=bd).count(),
                    'bd': db.session.query(m.BusinessDate).first().current_date}

    # No-show fees off, so the only ExtraCharge audits in a run are room rent
    # and an ExtraCharge-targeted fault cannot be absorbed by a fee's audit.
    with E.app.app_context():
        row = db.session.query(m.Settings).filter_by(key='noshow_fee_enabled').first()
        if row is None:
            db.session.add(m.Settings(key='noshow_fee_enabled', value='false'))
        else:
            row.value = 'false'
        db.session.commit()

    # Two in-house guests staying past the business date: two charges tonight.
    bd = E.bd
    rids = [E.new_res('na%d' % i, 'CheckedIn', bd - timedelta(days=1), bd + timedelta(days=2),
                      1000 + 100 * i, room_id=E.take_room()) for i in range(2)]

    print('W-21 audit failure: the whole run rolls back (manual route and scheduler call)')
    before = na_state(bd)
    for kind in ('F1', 'F2'):
        for tname, pred in (('any', None), ('charge', lambda et, ac: et == 'ExtraCharge')):
            with E.fault(kind, only=pred):
                r = E.call(lambda: c.post('/night-audit/run'))
            check('W21-B-%s-%s' % (kind, tname), 'W-21',
                  'route, %s on %s audit: no log, no charge, date unchanged' % (kind, tname),
                  before, na_state(bd), 'HTTP %s' % status(r))
        raised = None
        with E.fault(kind, only=lambda et, ac: et == 'ExtraCharge'):
            try:
                svc.run_night_audit(E.app)
            except Exception as exc:
                raised = exc.__class__.__name__
        check('W21-S-%s' % kind, 'W-21', 'scheduler-style call, %s: raises, nothing persisted' % kind,
              (True, before), (raised is not None, na_state(bd)), str(raised))

    print('W-21 success via POST /night-audit/run')
    r = c.post('/night-audit/run')
    after = na_state(bd)
    check('W21-01', 'W-21', 'one log, a room_rent charge per in-house guest',
          (1, before['rent'] + 2), (after['logs'], after['rent']), 'HTTP %s' % status(r))
    with E.app.app_context():
        log = db.session.query(m.NightAuditLog).filter_by(audit_date=bd).first()
        log_id, run_by = (log.id, log.run_by_user_id) if log else (None, None)
        charges = [(x.id, x.reservation_id, round(float(x.amount), 2), x.folio_id) for x in
                   db.session.query(m.ExtraCharge).filter(
                       m.ExtraCharge.reservation_id.in_(rids),
                       m.ExtraCharge.charge_type == 'room_rent',
                       m.ExtraCharge.charge_date == bd).order_by(m.ExtraCharge.id).all()]
    check('W21-02', 'W-21', 'run_by_user_id is the operator', E.admin_id, run_by)
    for i, (cid, rid, amt, fid) in enumerate(charges):
        au = E.audits('ExtraCharge', cid, 'posted')
        a = au[0] if au else {'after': {}, 'actor': None}
        check('W21-03.%d' % i, 'W-21', 'charge %d: one strict audit naming amount, folio, log, actor' % i,
              (1, amt, fid, 'room_rent', log_id, 'night_audit', E.admin_id),
              (len(au), a['after'].get('amount'), a['after'].get('folio_id'),
               a['after'].get('charge_type'), a['after'].get('night_audit_log_id'),
               a['after'].get('flow'), a['actor']))
    with E.app.app_context():
        all_rent = [x.id for x in db.session.query(m.ExtraCharge).filter_by(
            charge_type='room_rent', charge_date=bd).all()]
    check('W21-04', 'W-21', 'every room_rent charge for the date has exactly one posted audit',
          [1] * len(all_rent), [len(E.audits('ExtraCharge', x, 'posted')) for x in all_rent],
          '%d charges' % len(all_rent))

    # A completed run advances the business date, so a second run audits the
    # next day; the audited date must not be touched again.
    r = c.post('/night-audit/run')
    again = na_state(bd)
    check('W21-C', 'W-21', 'second run: nothing re-posted for the audited date',
          (after['logs'], after['rent']), (again['logs'], again['rent']),
          'HTTP %s; business date now %s' % (status(r), again['bd']))
    nxt = after['bd']
    with E.app.app_context():
        nxt_rent = [x.id for x in db.session.query(m.ExtraCharge).filter_by(
            charge_type='room_rent', charge_date=nxt).all()]
    check('W21-C2', 'W-21', 'next-day run: every room_rent charge has one posted audit',
          [1] * len(nxt_rent), [len(E.audits('ExtraCharge', x, 'posted')) for x in nxt_rent],
          '%s: %d charges' % (nxt, len(nxt_rent)))

    # ---- W-16 ------------------------------------------------------------
    target = bd - timedelta(days=5)

    def skipped(tag):
        rid = E.new_res(tag, 'CheckedOut', target - timedelta(days=1), target + timedelta(days=1), 1500)
        with E.app.app_context():
            if db.session.query(m.NightAuditLog).filter_by(audit_date=target).first() is None:
                db.session.add(m.NightAuditLog(audit_date=target, status='Skipped',
                                               notes='CF10 fixture'))
            db.session.commit()
        return rid

    def w16_state(rid):
        with E.app.app_context():
            log = db.session.query(m.NightAuditLog).filter_by(audit_date=target).first()
            return {'status': log.status if log else None,
                    'rent': db.session.query(m.ExtraCharge).filter_by(
                        reservation_id=rid, charge_type='room_rent', charge_date=target).count(),
                    'reopen': db.session.query(m.NightAuditReopenLog).filter_by(
                        audit_date=target).count()}

    def rerun():
        return E.call(lambda: c.post('/reports/night-audit/rerun-skipped',
                                     data={'audit_date': target.isoformat(),
                                           'reason': 'CF10 recovery'}))

    print('W-16 audit failure: the rerun rolls back')
    rid = skipped('w16')
    before = w16_state(rid)
    for kind in ('F1', 'F2'):
        for tname, pred in (('any', None), ('charge', lambda et, ac: et == 'ExtraCharge')):
            with E.fault(kind, only=pred):
                r = rerun()
            check('W16-B-%s-%s' % (kind, tname), 'W-16',
                  '%s on %s audit: still Skipped, no charge, no reopen row' % (kind, tname),
                  before, w16_state(rid), 'HTTP %s' % status(r))

    print('W-16 success via POST /reports/night-audit/rerun-skipped')
    r = rerun()
    s = w16_state(rid)
    check('W16-01', 'W-16', 'rerun: Completed/Warning, charge posted, reopen row',
          (True, 1, 1), (s['status'] in ('Completed', 'Warning'), s['rent'], s['reopen']),
          'HTTP %s' % status(r))
    with E.app.app_context():
        ec = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid, charge_type='room_rent',
                                                      charge_date=target).first()
        log = db.session.query(m.NightAuditLog).filter_by(audit_date=target).first()
        ecid, amt, fid = (ec.id, round(float(ec.amount), 2), ec.folio_id) if ec else (None, None, None)
        log_id = log.id if log else None
    au = E.audits('ExtraCharge', ecid, 'posted') if ecid else []
    a = au[0] if au else {'after': {}, 'actor': None}
    check('W16-02', 'W-16', 'one strict audit naming amount, folio, log, flow, actor',
          (1, amt, fid, log_id, 'night_audit_rerun', E.admin_id),
          (len(au), a['after'].get('amount'), a['after'].get('folio_id'),
           a['after'].get('night_audit_log_id'), a['after'].get('flow'), a['actor']))
    r = rerun()
    check('W16-C', 'W-16', 'repeat: refused (not Skipped), no duplicate', s, w16_state(rid),
          'HTTP %s' % status(r))


# ===========================================================================
# Group actor - audit identity under FK-enforced SQLite (ADR-005 target)
# ===========================================================================

def group_actor(E):
    """``audit_logs.staff_user_id`` is NOT NULL REFERENCES users(id). The
    application never enables ``PRAGMA foreign_keys`` (ADR-005), so the
    system convention ``staff_user_id = 0`` is accepted today although no
    user 0 exists. Here FK enforcement is switched on for this copy only,
    to show what an FK-enforcing engine (SQLite with the pragma, or
    PostgreSQL) does with each class of actor."""
    m, db = E.m, E.db
    import app.services as svc
    import app.noshow_service as ns
    from sqlalchemy import event

    with E.app.app_context():
        engine = db.engine
        users0 = db.session.query(m.User).filter_by(id=0).count()
        fk_violations = len(db.session.execute(db.text('PRAGMA foreign_key_check')).fetchall())
    check('A-00', 'actor', 'copy: no user 0, no FK violation before enforcement', (0, 0),
          (users0, fk_violations))

    def fk_on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA foreign_keys=ON')
        cur.close()
    event.listen(engine, 'connect', fk_on)
    engine.dispose()                      # every new connection enforces FKs
    with E.app.app_context():
        on = db.session.execute(db.text('PRAGMA foreign_keys')).scalar()
    check('A-01', 'actor', 'FK enforcement active on the copy', 1, on)

    with E.app.app_context():
        for k, v in (('noshow_fee_enabled', 'true'), ('noshow_fee_mode', 'fixed'),
                     ('noshow_fee_amount', '500')):
            row = db.session.query(m.Settings).filter_by(key=k).first()
            if row is None:
                db.session.add(m.Settings(key=k, value=v))
            else:
                row.value = v
        db.session.commit()

    def ns_state(rid):
        with E.app.app_context():
            return (db.session.get(m.Reservation, rid).status,
                    db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).count())

    print('ACTOR operator path (manual no-show) under FK enforcement')
    rid = E.new_res('act-man', 'Reserved', E.bd, E.bd + timedelta(days=1), 1000)
    with E.logged_ctx():
        r = ns.manual_noshow(rid, E.admin_id, 'CF10 actor')
    check('A-02', 'actor', 'operator actor: no-show + fee posted, audits accepted',
          ('NoShow', 1), ns_state(rid), str(getattr(r, 'message', ''))[:80])

    print('ACTOR automated path (no operator, no request) under FK enforcement')
    rid = E.new_res('act-auto', 'Reserved', E.bd, E.bd + timedelta(days=1), 1000)
    before = ns_state(rid)
    raised = None
    with E.app.app_context():
        try:
            res = db.session.get(m.Reservation, rid)
            ns.process_reservation_noshow(res, E.bd, ns._get_noshow_config(),
                                          posted_by_user_id=None)
            db.session.commit()
        except Exception as exc:
            raised = '%s: %s' % (exc.__class__.__name__, str(exc)[:90])
            db.session.rollback()
    check('A-03', 'actor', 'automated no-show: fails closed, nothing partial persisted',
          before, ns_state(rid), str(raised))
    check('A-04', 'actor', 'automated no-show can complete under FK enforcement', None, raised,
          'system actor 0 is rejected - AR-013 / ADR-011 unresolved', gate=False)

    print('ACTOR scheduler night audit (no operator) under FK enforcement')
    rid2 = E.new_res('act-na', 'CheckedIn', E.bd - timedelta(days=1), E.bd + timedelta(days=2), 1000,
                     room_id=E.take_room())
    with E.app.app_context():
        n_logs = db.session.query(m.NightAuditLog).filter_by(audit_date=E.bd).count()
        n_rent = db.session.query(m.ExtraCharge).filter_by(charge_type='room_rent',
                                                           charge_date=E.bd).count()
    raised = None
    try:
        svc.run_night_audit(E.app)
    except Exception as exc:
        raised = '%s: %s' % (exc.__class__.__name__, str(exc)[:90])
    with E.app.app_context():
        after = (db.session.query(m.NightAuditLog).filter_by(audit_date=E.bd).count(),
                 db.session.query(m.ExtraCharge).filter_by(charge_type='room_rent',
                                                           charge_date=E.bd).count(),
                 db.session.query(m.BusinessDate).first().current_date)
    check('A-05', 'actor', 'scheduler run: fails closed, no log, no charge, date unchanged',
          (n_logs, n_rent, E.bd), after, str(raised))
    check('A-06', 'actor', 'scheduler night audit can complete under FK enforcement', None, raised,
          'system actor 0 is rejected - AR-013 / B-1 unresolved; scheduler disabled for the '
          'first release (FD-P2-05)', gate=False)

    print('ACTOR manual night audit (operator) under FK enforcement, with a no-show pending')
    c = E.client()
    rid3 = E.new_res('act-na-ns', 'Reserved', E.bd, E.bd + timedelta(days=1), 1000)
    r = E.call(lambda: c.post('/night-audit/run'))
    with E.app.app_context():
        logs = db.session.query(m.NightAuditLog).filter_by(audit_date=E.bd).count()
        rent = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid2,
                                                         charge_type='room_rent').count()
    check('A-07', 'actor', 'manual run with a no-show: all-or-nothing (log and charges agree)',
          True, (logs == 0 and rent == 0) or (logs == 1 and rent == 1), 'logs=%d rent=%d' % (logs, rent))
    check('A-08', 'actor', 'manual night audit with a pending no-show completes under FK enforcement',
          (1, 1, 'NoShow'), (logs, rent, ns_state(rid3)[0]),
          'FD-P2-05 first-release model: every audit row of an operator run names the operator')
    na = E.audits('Reservation', rid3, 'noshow_posted')
    check('A-09', 'actor', "operator run: noshow_posted actor is the operator, origin still 'night_audit'",
          (1, E.admin_id, 'night_audit'),
          (len(na), na[0]['actor'] if na else None, na[0]['after'].get('posted_by') if na else None))
    event.remove(engine, 'connect', fk_on)
    engine.dispose()


# ===========================================================================
# Driver
# ===========================================================================

def run_group(group):
    started = datetime.now()
    prod_before = sha256(PRODUCTION_DB)
    print('=' * 140)
    print('CF-10 / CF-11 HARDENING - GROUP %s' % group)
    print('app root %s  commit %s  app/ clean: %s' % (APP_ROOT, APP_COMMIT, APP_DIRTY == ''))
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
           'app_root': APP_ROOT, 'app_commit': APP_COMMIT,
           'app_tree_clean': (APP_DIRTY == ''), 'harness': os.path.relpath(__file__, REPO),
           'copy': E.handle.copy_path, 'copy_method': E.handle.method,
           'production_sha256_before': prod_before, 'production_sha256_after': prod_after,
           'gates_total': len(gates), 'gates_passed': passed,
           'verdict': 'PASS' if passed == len(gates) else 'FAIL', 'checks': results}
    label = os.environ.get('CF10_RUN_LABEL', 'run')
    with open(os.path.join(OUT_DIR, 'results_%s_%s.json' % (label, group)), 'w', encoding='utf-8') as fh:
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
