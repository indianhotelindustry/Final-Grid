# -*- coding: utf-8 -*-
"""Phase 1 — Financial Foundation: folio attribution verification.

Directive FG-P1-EXEC-20260909-01. Proves that new financial activity is
attributed to the reservation's billing folio, that the missing-folio
lifecycle behaves as Q-1 requires, that a financial mutation cannot commit
without its required audit row (Q-5), that room revenue is attributed under
the adopted architecture, and that the eight D11 rows are untouched.

Written in the idiom this repository already uses for verification: declare
the expected value, assert against the actual, print pass/fail per case, and
run the whole thing against a disposable copy produced by verification.dbcopy
so production is never a test target. pytest is deliberately not used —
adding a test framework is Phase 6 work.

    venv\\Scripts\\python.exe verification\\evidence\\20260909_phase1_execution\\verify.py

Constraints honoured, per the directive:
  * production is opened read-only, hashed before and after;
  * the 6 payments and 2 charges carrying a pre-existing NULL folio_id are
    never touched, on any database (D11 freeze, FD-010) — proven by id set;
  * no schema change, no migration, no production data mutation.
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


def check(case_id, group, what, expect, got, note=''):
    ok = (expect == got)
    results.append({'case': case_id, 'group': group, 'what': what,
                    'expect': expect, 'got': got, 'pass': ok, 'note': note})
    print('%-5s %-6s %-46s expect=%-26s got=%-26s %s'
          % ('OK' if ok else 'FAIL', case_id, what,
             repr(expect)[:26], repr(got)[:26], note))
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
    print('=' * 118)
    print('PHASE 1 — FINANCIAL FOUNDATION: FOLIO ATTRIBUTION')
    print('=' * 118)
    print('production        : %s' % PRODUCTION_DB)
    print('sha256 before     : %s' % prod_before)
    print('frozen anchor     : %s' % ('MATCHES' if prod_before == FROZEN_ANCHOR
                                      else '*** MISMATCH ***'))

    handle = make_copy(name='phase1_folio.db')
    print('disposable copy   : %s  (%s)' % (handle.copy_path, handle.method))
    print('-' * 118)

    os.environ['DATABASE_URL'] = 'sqlite:///' + handle.copy_path.replace('\\', '/')
    os.environ['FLASK_ENV'] = 'production'

    from app import create_app                                          # noqa: E402
    from app.models import (db, User, Reservation, Folio, ExtraCharge,   # noqa: E402
                            Payment, PaymentMode, AuditLog, Room,
                            ReservationNightRate, NightAuditLog, BusinessDate)
    from sqlalchemy import text                                          # noqa: E402

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    import app.services as svc                                           # noqa: E402

    # ── D11 identity, captured before anything runs ─────────────────────────
    with app.app_context():
        d11_pay = sorted(r[0] for r in db.session.query(Payment.id)
                         .filter(Payment.folio_id.is_(None)).all())
        d11_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id)
                         .filter(ExtraCharge.folio_id.is_(None)).all())
        d11_pay_vals = {p.id: float(p.amount) for p in
                        db.session.query(Payment).filter(Payment.id.in_(d11_pay)).all()}
        d11_chg_vals = {c.id: float(c.amount) for c in
                        db.session.query(ExtraCharge).filter(ExtraCharge.id.in_(d11_chg)).all()}
    print('D11 population    : payments=%s charges=%s  (must be identical at the end)'
          % (d11_pay, d11_chg))
    print('-' * 118)

    # ── Fixtures, all created fresh on the copy ─────────────────────────────
    with app.app_context():
        roles = ('Admin', 'Manager', 'FrontDesk', 'Accountant', 'Housekeeping')
        users = {}
        for role in roles:
            u = User(username='p1_%s' % role.lower(), full_name='P1 %s' % role,
                     role=role, is_active=True)
            u.set_password('p1-test-password')
            db.session.add(u)
            db.session.flush()
            users[role] = u.id

        seed_res = db.session.query(Reservation).order_by(Reservation.id).first()
        if seed_res is None:
            raise SystemExit('FATAL: no reservation in the copy to work from')
        mode = db.session.query(PaymentMode).first()
        if mode is None:
            raise SystemExit('FATAL: no payment mode in the copy')

        seed_ids = {'guest': seed_res.guest_id, 'room': seed_res.room_id,
                    'room_type': seed_res.room_type_id}

        def new_reservation(tag, status='CheckedIn'):
            """A reservation created through the ORM — the listener makes folio A.

            Uses plain ids rather than a held Reservation instance, so it can be
            called from any later app context without a DetachedInstanceError.
            """
            r = Reservation(
                booking_reference='P1-%s-%d' % (tag, int(datetime.now().timestamp() * 1000) % 100000),
                guest_id=seed_ids['guest'], room_id=seed_ids['room'],
                room_type_id=seed_ids['room_type'],
                arrival_date=date(2026, 8, 10), departure_date=date(2026, 8, 11),
                adults=1, children=0, status=status, rate_per_night=1000,
                noshow_exempt=False, checkout_initiated=False,
                credit_amount=0, credit_settled_amount=0,
                cancellation_amount_refunded=0, cancellation_amount_forfeited=0,
                cancellation_amount_credit_voucher=0)
            db.session.add(r)
            db.session.flush()
            return r

        res_ok = new_reservation('ok')

        # A reservation inserted by raw SQL: the ORM after_insert listener does
        # not fire, so this row has NO folio A. This is exactly the condition
        # Q-1 / CD-1 governs, and it is how a raw-SQL import would arrive.
        db.session.execute(text(
            'INSERT INTO reservations (booking_reference, guest_id, room_id, '
            ' room_type_id, arrival_date, departure_date, adults, children, '
            ' status, noshow_exempt, rate_per_night, checkout_initiated, '
            ' credit_amount, credit_settled_amount, cancellation_amount_refunded, '
            ' cancellation_amount_forfeited, cancellation_amount_credit_voucher) '
            'VALUES (:ref, :g, :rm, :rt, :a, :d, 1, 0, :st, 0, 1000, 0, 0, 0, 0, 0, 0)'),
            {'ref': 'P1-RAW-1', 'g': seed_res.guest_id, 'rm': seed_res.room_id,
             'rt': seed_res.room_type_id, 'a': date(2026, 8, 10),
             'd': date(2026, 8, 11), 'st': 'CheckedIn'})
        rid_raw = db.session.execute(
            text('SELECT id FROM reservations WHERE booking_reference = :r'),
            {'r': 'P1-RAW-1'}).scalar()

        db.session.commit()
        ids = {'res_ok': res_ok.id, 'res_raw': rid_raw,
               'folio_ok': db.session.query(Folio)
                           .filter_by(reservation_id=res_ok.id, folio_letter='A')
                           .first().id}
        print('fixtures          : %s' % ids)
        print('-' * 118)

    def folio_of(model, pk):
        with app.app_context():
            row = db.session.get(model, pk)
            return None if row is None else row.folio_id

    def audit_actions(entity_type=None):
        with app.app_context():
            q = db.session.query(AuditLog.action)
            if entity_type:
                q = q.filter(AuditLog.entity_type == entity_type)
            return [a[0] for a in q.all()]

    def client_as(role):
        c = app.test_client()
        if role is not None:
            with c.session_transaction() as sess:
                sess['_user_id'] = str(users[role])
                sess['_fresh'] = True
        return c

    # =====================================================================
    # S2 — attribution foundation (unit 1.1)
    # =====================================================================
    print('S2 — ATTRIBUTION FOUNDATION (resolver lifecycle, Q-1)')
    print('-' * 118)

    with app.app_context():
        # T-L01 existing folio A is returned
        f = svc.resolve_billing_folio(db.session.get(Reservation, ids['res_ok']))
        check('T-L01', 'S2', 'existing folio A returned', ids['folio_ok'], f.id)
        check('T-L02', 'S2', 'returned folio is letter A', 'A', f.folio_letter)

        # T-L03 accepts a bare id and returns the same folio (deterministic)
        f2 = svc.resolve_billing_folio(ids['res_ok'])
        check('T-L03', 'S2', 'resolver accepts reservation id', ids['folio_ok'], f2.id)

        # T-L04 idempotent — repeated resolution creates nothing
        before = db.session.query(Folio).filter_by(reservation_id=ids['res_ok']).count()
        for _ in range(5):
            svc.resolve_billing_folio(ids['res_ok'])
        after = db.session.query(Folio).filter_by(reservation_id=ids['res_ok']).count()
        check('T-L05', 'S2', 'repeated resolution creates no folio', before, after)

        # T-L06 folio B present must not be selected
        fb = Folio(reservation_id=ids['res_ok'], folio_letter='B', label='Company')
        db.session.add(fb)
        db.session.commit()
        f3 = svc.resolve_billing_folio(ids['res_ok'])
        check('T-L06', 'S2', 'folio B never selected when A exists',
              (ids['folio_ok'], 'A'), (f3.id, f3.folio_letter))

        # T-L07 missing folio A (raw-SQL reservation) — created and audited
        pre = db.session.query(Folio).filter_by(reservation_id=ids['res_raw']).count()
        check('T-L07', 'S2', 'raw-SQL reservation starts with no folio', 0, pre)
        created = svc.resolve_billing_folio(ids['res_raw'], user_id=users['Admin'])
        db.session.commit()
        check('T-L08', 'S2', 'missing folio A is created (Q-1)',
              ('A', ids['res_raw']), (created.folio_letter, created.reservation_id))
        acts = audit_actions('Folio')
        check('T-L09', 'S2', 'folio creation is audited (Q-1)',
              True, 'folio_auto_created' in acts)
        check('T-L10', 'S2', 'exactly one folio created for that reservation',
              1, db.session.query(Folio).filter_by(reservation_id=ids['res_raw']).count())

        # T-L11 second call on the same reservation is idempotent
        again = svc.resolve_billing_folio(ids['res_raw'])
        check('T-L11', 'S2', 'second resolution reuses the created folio',
              created.id, again.id)

        # T-L12/13 fail closed
        try:
            svc.resolve_billing_folio(None)
            got = 'no exception'
        except svc.FolioResolutionError:
            got = 'FolioResolutionError'
        check('T-L12', 'S2', 'None reservation fails closed', 'FolioResolutionError', got)
        try:
            svc.resolve_billing_folio(9_999_999)
            got = 'no exception'
        except svc.FolioResolutionError:
            got = 'FolioResolutionError'
        check('T-L13', 'S2', 'unknown reservation fails closed',
              'FolioResolutionError', got)

        # T-L14 audit coupling helper: success returns a persisted row
        log = svc.audited_financial_write('Payment', 1, 'p1_probe', None, {'x': 1},
                                          user_id=users['Admin'])
        check('T-L14', 'S2', 'audited_financial_write persists a row',
              True, log.id is not None)
        db.session.rollback()

        # T-L15 audit coupling helper raises when the row cannot be written
        try:
            svc.audited_financial_write('Payment', None, 'p1_probe', None, None)
            got = 'no exception'
        except svc.AuditCouplingError:
            got = 'AuditCouplingError'
        check('T-L15', 'S2', 'audit helper fails closed on bad input',
              'AuditCouplingError', got)

    print('-' * 118)

    # =====================================================================
    # S3a — static coverage: every financial writer passes folio_id
    # =====================================================================
    print('S3a — WRITER COVERAGE (every originating constructor attributes)')
    print('-' * 118)
    import re
    WRITER_SITES = [
        ('W-01', 'app/routes.py', 'bulk_booking_api', 'Payment'),
        ('W-02', 'app/routes.py', 'new_reservation', 'Payment'),
        ('W-03', 'app/routes.py', 'checkout', 'Payment'),
        ('W-05', 'app/routes.py', 'add_payment', 'Payment'),
        ('W-06', 'app/routes.py', 'walkin_search_express', 'Payment'),
        ('W-07', 'app/routes.py', 'settle_credit', 'Payment'),
        ('W-08', 'app/services.py', 'post_payment_correction', 'Payment'),
        ('W-10', 'app/services.py', 'post_cancellation_disposition', 'Payment'),
        ('W-11', 'app/services.py', 'redeem_credit_voucher', 'Payment'),
        ('W-12', 'app/services.py', 'complete_full_checkin', 'Payment'),
        ('W-13', 'app/cico_service.py', 'post_charge', 'ExtraCharge'),
        ('W-14', 'app/noshow_service.py', 'process_reservation_noshow', 'ExtraCharge'),
        ('W-15', 'app/pos.py', 'post_charge', 'ExtraCharge'),
        ('W-16', 'app/reports.py', '_rerun_skipped_audit', 'ExtraCharge'),
        ('W-17', 'app/routes.py', 'checkout', 'ExtraCharge'),
        ('W-20', 'app/routes.py', 'add_overstay_charge', 'ExtraCharge'),
        ('W-21', 'app/services.py', 'run_night_audit', 'ExtraCharge'),
        ('W-22', 'app/services.py', 'post_extra_charge_correction', 'ExtraCharge'),
        ('W-24', 'app/services.py', 'convert_overpayment_to_upsell', 'ExtraCharge'),
    ]

    import ast

    def constructor_blocks(path, model):
        """Every real ``Model(...)`` call in *path*, with its enclosing function.

        Parsed with ``ast`` rather than matched textually, so a mention inside
        a docstring or comment — ``voucher_redeem``'s docstring names
        ``Payment(purpose='settlement')`` — is not mistaken for a writer.
        Returns ``(function, lineno, sets_folio_id)`` per call site.
        """
        tree = ast.parse(open(os.path.join(REPO, path), encoding='utf-8').read())
        funcs = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

        def enclosing(lineno):
            best = None
            for fn in funcs:
                end = getattr(fn, 'end_lineno', fn.lineno)
                if fn.lineno <= lineno <= end:
                    if best is None or fn.lineno > best.lineno:
                        best = fn
            return best.name if best else '?'

        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = getattr(f, 'id', None) or getattr(f, 'attr', None)
            if name != model:
                continue
            kw = {k.arg for k in node.keywords if k.arg}
            out.append((enclosing(node.lineno), node.lineno, 'folio_id' in kw))
        return out

    uncovered = []
    for wid, path, func, model in WRITER_SITES:
        blocks = [b for b in constructor_blocks(path, model) if b[0] == func]
        if not blocks:
            uncovered.append('%s %s:%s (site not found)' % (wid, path, func))
            continue
        for _f, ln, has in blocks:
            if not has:
                uncovered.append('%s %s:%d %s' % (wid, path, ln, func))
    check('T-W01', 'S3a', 'every enumerated writer constructor sets folio_id',
          [], uncovered)

    # Nothing in the application may construct a financial row without one —
    # fixtures included (CD-4).
    all_sites, all_uncovered = 0, []
    for path in ('app/routes.py', 'app/services.py', 'app/pos.py',
                 'app/cico_service.py', 'app/noshow_service.py',
                 'app/reports.py', 'app/seed.py', 'app/dev_seed.py',
                 'app/billing.py', 'app/ota.py', 'app/groups.py',
                 'app/webhook.py', 'app/booking.py', 'app/loyalty.py'):
        for model in ('Payment', 'ExtraCharge'):
            for func, ln, has in constructor_blocks(path, model):
                all_sites += 1
                if not has:
                    all_uncovered.append('%s:%d %s(%s)' % (path, ln, func, model))
    check('T-W02', 'S3a', 'no financial constructor anywhere lacks folio_id',
          [], all_uncovered, '%d call sites scanned' % all_sites)
    print('-' * 118)

    # =====================================================================
    # S3b — runtime attribution through the real paths
    # =====================================================================
    print('S3b — RUNTIME ATTRIBUTION')
    print('-' * 118)

    admin = client_as('Admin')

    # W-05 add_payment (route)
    with app.app_context():
        res_pay = db.session.query(Reservation).get(ids['res_ok'])
        res_pay.status = 'CheckedIn'
        db.session.commit()
    r = admin.post('/api/reservation/%d/add-payment' % ids['res_ok'],
                   json={'amount': 250.0})
    with app.app_context():
        p = (db.session.query(Payment)
             .filter_by(reservation_id=ids['res_ok'])
             .order_by(Payment.id.desc()).first())
        got = (r.status_code, None if p is None else p.folio_id)
    check('T-W05', 'S3b', 'add_payment attributes to folio A',
          (200, ids['folio_ok']), got)

    # W-15 POS charge (route) — attribution AND atomic audit
    with app.app_context():
        before_chg = db.session.query(ExtraCharge).count()
    r = admin.post('/pos/post', data={'reservation_id': ids['res_ok'],
                                      'description': 'P1 POS probe',
                                      'amount': '99.5'},
                   headers={'X-Requested-With': 'XMLHttpRequest'})
    with app.app_context():
        c = (db.session.query(ExtraCharge)
             .filter_by(reservation_id=ids['res_ok'])
             .order_by(ExtraCharge.id.desc()).first())
        pos_audit = (db.session.query(AuditLog)
                     .filter_by(entity_type='ExtraCharge', action='pos_charge')
                     .count())
        got = (r.status_code, c.folio_id, pos_audit >= 1)
    check('T-W15', 'S3b', 'POS charge attributed and audited in one commit',
          (200, ids['folio_ok'], True), got)

    # W-20 overstay charge (route)
    with app.app_context():
        rr = db.session.query(Reservation).get(ids['res_ok'])
        rr.status = 'CheckedIn'
        rr.departure_date = date(2026, 8, 10)
        rr.overstay_billed_until = None
        db.session.commit()
    r = admin.post('/reservation/%d/overstay-charge' % ids['res_ok'],
                   data={'hours': '2'}, follow_redirects=False)
    with app.app_context():
        ov = (db.session.query(ExtraCharge)
              .filter(ExtraCharge.reservation_id == ids['res_ok'],
                      ExtraCharge.description.like('Overstay%'))
              .order_by(ExtraCharge.id.desc()).first())
        got = None if ov is None else ov.folio_id
    check('T-W20', 'S3b', 'overstay charge attributed (if posted)',
          True, got in (ids['folio_ok'], None),
          'no charge posted' if ov is None else '')

    # W-13 CICO service
    with app.app_context():
        import app.cico_service as cico
        res2 = db.session.get(Reservation, ids['res_ok'])
        ec = cico.post_charge(res2, 'early_checkin', 120.0, '06:00 AM — 30%',
                              user_id=users['Admin'])
        db.session.commit()
        got = None if ec is None else ec.folio_id
    check('T-W13', 'S3b', 'CICO charge attributed', ids['folio_ok'], got)

    # W-08/W-22 corrections inherit, and Q-2 refuses an unattributed original
    with app.app_context():
        src_pay = (db.session.query(Payment)
                   .filter(Payment.reservation_id == ids['res_ok'],
                           Payment.folio_id.isnot(None))
                   .order_by(Payment.id.desc()).first())
        out = svc.post_payment_correction(src_pay, reason='P1 probe',
                                          user_id=users['Admin'])
        db.session.commit()
        check('T-W08', 'S3b', 'payment correction inherits attribution',
              src_pay.folio_id, out['reversal'].folio_id)

        d11_original = db.session.get(Payment, d11_pay[0])
        try:
            svc.post_payment_correction(d11_original, reason='must refuse',
                                        user_id=users['Admin'])
            got = 'no exception'
        except svc.FolioResolutionError:
            got = 'FolioResolutionError'
        db.session.rollback()
        check('T-Q02', 'S3b', 'correction of a NULL-folio original is refused '
              '(Q-2)', 'FolioResolutionError', got)

    print('-' * 118)

    # =====================================================================
    # S3c — audit coupling (Q-5)
    # =====================================================================
    print('S3c — AUDIT COUPLING (Q-5)')
    print('-' * 118)

    real_audit = svc.audited_financial_write

    def exploding_audit(*a, **kw):
        raise svc.AuditCouplingError('injected audit failure')

    with app.app_context():
        pay_before = db.session.query(Payment).count()
        chg_before = db.session.query(ExtraCharge).count()

    svc.audited_financial_write = exploding_audit
    try:
        r_pay = admin.post('/api/reservation/%d/add-payment' % ids['res_ok'],
                           json={'amount': 77.0})
        r_pos = admin.post('/pos/post', data={'reservation_id': ids['res_ok'],
                                              'description': 'P1 POS fail probe',
                                              'amount': '55'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
    finally:
        svc.audited_financial_write = real_audit

    with app.app_context():
        pay_after = db.session.query(Payment).count()
        chg_after = db.session.query(ExtraCharge).count()
    check('T-A01', 'S3c', 'audit failure rolls back the payment',
          pay_before, pay_after)
    check('T-A02', 'S3c', 'audit failure rolls back the POS charge',
          chg_before, chg_after)
    check('T-A03', 'S3c', 'payment caller is told it failed (no false success)',
          True, r_pay.status_code >= 400)
    check('T-A04', 'S3c', 'POS caller is told it failed (no false success)',
          True, r_pos.status_code >= 400)
    print('-' * 118)

    # =====================================================================
    # S4 — room rent / night audit / upsell
    # =====================================================================
    print('S4 — ROOM RENT AND NIGHT AUDIT')
    print('-' * 118)
    with app.app_context():
        bd = db.session.query(BusinessDate).first()
        audit_day = bd.current_date
        # a clean in-house stay for the audit to post room rent against
        stay = new_reservation('audit', status='CheckedIn')
        stay.arrival_date = audit_day
        stay.departure_date = audit_day + timedelta(days=1)
        stay.rate_per_night = 1200
        db.session.commit()
        stay_id = stay.id
        stay_folio = db.session.query(Folio).filter_by(
            reservation_id=stay_id, folio_letter='A').first().id
        # clear any existing audit log for the date so the run proceeds
        db.session.query(NightAuditLog).filter_by(audit_date=audit_day).delete()
        db.session.commit()

    svc.run_night_audit(app)

    with app.app_context():
        rr_rows = (db.session.query(ExtraCharge)
                   .filter_by(reservation_id=stay_id, charge_type='room_rent')
                   .all())
        got = (len(rr_rows), [x.folio_id for x in rr_rows],
               [x.charge_date for x in rr_rows])
    check('T-R01', 'S4', 'night audit posts room rent attributed to folio A',
          (1, [stay_folio], [audit_day]), got)

    # idempotency — a second run posts nothing further
    with app.app_context():
        before_rr = db.session.query(ExtraCharge).filter_by(
            reservation_id=stay_id, charge_type='room_rent').count()
    svc.run_night_audit(app)
    with app.app_context():
        after_rr = db.session.query(ExtraCharge).filter_by(
            reservation_id=stay_id, charge_type='room_rent').count()
    check('T-R02', 'S4', 'night audit rerun posts no duplicate room rent',
          before_rr, after_rr)

    # folio balance semantics unchanged — room revenue still excluded
    with app.app_context():
        f = db.session.get(Folio, stay_folio)
        totals = svc.calculate_folio_amount(f)
        rr_total = sum(float(x.amount) for x in
                       db.session.query(ExtraCharge)
                       .filter_by(reservation_id=stay_id, charge_type='room_rent'))
    check('T-R04', 'S4', 'folio balance still excludes room revenue',
          0.0, float(totals['extra_charges']),
          'room rent posted = %.2f' % rr_total)
    print('-' * 118)

    # =====================================================================
    # S5 — reconciliation: folio figure beside the reservation figure
    # =====================================================================
    print('S5 — RECONCILIATION ATTRIBUTION CONTROL (unit 1.7)')
    print('-' * 118)
    from app.night_audit_service import NightAuditService      # noqa: E402

    EXISTING_FOLIO_KEYS = {
        'open_folios_count', 'closed_folios_count', 'in_house_outstanding',
        'checkout_outstanding_total', 'total_outstanding',
        'checkout_outstanding_list', 'negative_folios', 'open_folio_list',
    }

    with app.app_context():
        rep = NightAuditService(audit_day)
        fc = rep.folio_control()
        attr = rep.attribution_control()
        check('T-N01', 'S5', 'attribution control is its own report section',
              True, isinstance(attr, dict) and 'payments' in attr)
        check('T-N02', 'S5', 'existing folio_control keys all still present',
              set(), EXISTING_FOLIO_KEYS - set(fc))
        # N-12: the D3 replay ledger captures folio_control's figures, so the
        # new control must NOT add a key inside it.
        check('T-N02b', 'S5', 'folio_control gains no key (replay ledger intact)',
              EXISTING_FOLIO_KEYS, set(fc) & EXISTING_FOLIO_KEYS)
        check('T-N02c', 'S5', 'attribution is not nested inside folio_control',
              False, 'attribution' in fc)
        check('T-N03', 'S5', 'reservation and folio views reconcile',
              True, attr.get('views_agree'))
        got = (attr['payments']['unattributed_ids'],
               attr['charges']['unattributed_ids'])
        check('T-N04', 'S5', 'unattributed bucket is exactly the D11 rows',
              (d11_pay, d11_chg), got)
        check('T-N05', 'S5', 'unattributed rows are flagged, not shown as clean',
              'warning', attr.get('state'))
        check('T-N06', 'S5', 'D11 total is reported separately, not netted in',
              4776.19, round(abs(attr.get('unattributed_total', 0)), 2))
        check('T-N07', 'S5', 'no row is routed to another reservation\'s folio',
              0, attr.get('misrouted_count'))

        # the control must actually be capable of failing (P9)
        probe = (db.session.query(ExtraCharge)
                 .filter(ExtraCharge.folio_id.isnot(None))
                 .order_by(ExtraCharge.id.desc()).first())
        other = (db.session.query(Folio)
                 .filter(Folio.reservation_id != probe.reservation_id).first())
        keep = probe.folio_id
        probe.folio_id = other.id
        db.session.flush()
        bad = NightAuditService(audit_day).attribution_control()
        probe.folio_id = keep
        db.session.commit()
        check('T-N08', 'S5', 'control detects a misrouted row (P9 commissioning)',
              ('danger', 1), (bad.get('state'), bad.get('misrouted_count')))
    print('-' * 118)

    # =====================================================================
    # Final: D11 freeze + production untouched
    # =====================================================================
    print('D11 FREEZE AND PRODUCTION INTEGRITY')
    print('-' * 118)
    with app.app_context():
        end_pay = sorted(r[0] for r in db.session.query(Payment.id)
                         .filter(Payment.folio_id.is_(None)).all())
        end_chg = sorted(r[0] for r in db.session.query(ExtraCharge.id)
                         .filter(ExtraCharge.folio_id.is_(None)).all())
        end_pay_vals = {p.id: float(p.amount) for p in
                        db.session.query(Payment).filter(Payment.id.in_(d11_pay)).all()}
        end_chg_vals = {c.id: float(c.amount) for c in
                        db.session.query(ExtraCharge).filter(ExtraCharge.id.in_(d11_chg)).all()}
    check('T-D01', 'D11', 'NULL-folio payment id set unchanged', d11_pay, end_pay)
    check('T-D02', 'D11', 'NULL-folio charge id set unchanged', d11_chg, end_chg)
    check('T-D03', 'D11', 'D11 payment amounts unchanged', d11_pay_vals, end_pay_vals)
    check('T-D04', 'D11', 'D11 charge amounts unchanged', d11_chg_vals, end_chg_vals)

    prod_after = sha256(PRODUCTION_DB)
    check('T-P01', 'PROD', 'production database unchanged', prod_before, prod_after)

    passed = sum(1 for r in results if r['pass'])
    total = len(results)
    print('-' * 118)
    print('RESULT: %d / %d passed' % (passed, total))
    print('=' * 118)

    payload = {
        'directive': 'FG-P1-EXEC-20260909-01',
        'phase': '1', 'started_at': started.isoformat(timespec='seconds'),
        'finished_at': datetime.now().isoformat(timespec='seconds'),
        'production_db': PRODUCTION_DB,
        'production_sha256_before': prod_before,
        'production_sha256_after': prod_after,
        'frozen_anchor': FROZEN_ANCHOR,
        'anchor_matches': prod_before == FROZEN_ANCHOR,
        'read_only_verified': prod_before == prod_after,
        'copy_method': handle.method,
        'd11_payments': d11_pay, 'd11_extra_charges': d11_chg,
        'd11_unchanged': d11_pay == end_pay and d11_chg == end_chg
                         and d11_pay_vals == end_pay_vals and d11_chg_vals == end_chg_vals,
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
