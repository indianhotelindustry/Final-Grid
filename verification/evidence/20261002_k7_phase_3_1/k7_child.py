# -*- coding: utf-8 -*-
"""K-7 harness child: ONE scenario, ONE process, ONE disposable copy, frozen clock.

    <python> k7_child.py <worktree> <copy.db> <scenario> <clock-iso> <pre-copy-path>

Printed result: a single line ``K7JSON {...}``. The parent (verify_k7.py)
compares it with expectations.json. Nothing here writes outside <copy.db>,
its ``.pre`` snapshot and stdout. The live ``.env`` is never loaded and the
messaging/AI variables are removed by the parent.

Order matters and is part of the method: the proven clock freeze is installed
BEFORE ``app`` is imported, so a ``default=date.today`` bound at import time
binds the frozen class (as verification/golden/capture.py does).
"""
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import datetime as _real_dt

WT, DB, SCEN, CLOCK, PRE = sys.argv[1:6]
os.environ['DATABASE_URL'] = 'sqlite:///' + DB.replace('\\', '/')
os.environ['FLASK_ENV'] = 'production'
assert os.environ.get('SECRET_KEY'), 'throwaway SECRET_KEY required'
sys.path.insert(0, WT)
os.chdir(WT)

from verification.golden.freeze import install_proven            # noqa: E402

INSTANT = _real_dt.datetime.fromisoformat(CLOCK)
FREEZE, PROOF = install_proven(INSTANT)

from app import create_app                                        # noqa: E402
import app as _app_pkg                                            # noqa: E402
assert os.path.abspath(_app_pkg.__file__).startswith(os.path.join(WT, 'app')), _app_pkg.__file__
FREEZE.rebind_loaded_modules()
PROOF = FREEZE.prove()

from datetime import date, datetime, timedelta                    # noqa: E402  (frozen classes)

# ---- capture ERROR records so "logged error" can be asserted -------------------
LOGGED = []


class _H(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            LOGGED.append(record.getMessage())


_h = _H(level=logging.ERROR)
logging.getLogger().addHandler(_h)
logging.getLogger().setLevel(logging.INFO)

app = create_app()
from app.services import scheduler                                # noqa: E402
if scheduler.running:
    scheduler.shutdown(wait=False)
app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, PROPAGATE_EXCEPTIONS=False)

from app import models as m                                       # noqa: E402
import app.services as svc                                        # noqa: E402

db = m.db
BD_CONST = date(2026, 8, 10)


def iso(v):
    return v.isoformat() if v is not None else None


def raw(sql, *a):
    c = sqlite3.connect(DB)
    try:
        return c.execute(sql, a).fetchall()
    finally:
        c.close()


def digest(sql):
    rows = raw(sql)
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()


D11_SQL = ("SELECT * FROM payments WHERE folio_id IS NULL ORDER BY id; ")
D11_Q = ["SELECT * FROM payments WHERE folio_id IS NULL ORDER BY id",
         "SELECT * FROM extra_charges WHERE folio_id IS NULL ORDER BY id"]
SEAL_Q = "SELECT * FROM night_audit_logs WHERE audit_date = '2026-08-09' ORDER BY id"


def protected_state():
    return [digest(q) for q in D11_Q] + [digest(SEAL_Q)]


def counts():
    return {t: raw('SELECT COUNT(*) FROM %s' % t)[0][0]
            for t in ('payments', 'extra_charges', 'credit_vouchers', 'audit_logs',
                      'night_audit_logs')}


def max_ids():
    return {t: (raw('SELECT COALESCE(MAX(id),0) FROM %s' % t)[0][0])
            for t in ('payments', 'extra_charges', 'credit_vouchers')}


def new_rows(before):
    out = []
    for t, col in (('payments', 'payment_date'), ('extra_charges', 'charge_date'),
                   ('credit_vouchers', 'issued_date')):
        for rid, d in raw('SELECT id, %s FROM %s WHERE id > ? ORDER BY id' % (col, t), before[t]):
            out.append({'table': t, 'id': rid, 'date': d})
    return out


def bd_now():
    r = raw('SELECT "current_date" FROM business_date LIMIT 1')
    return r[0][0] if r else None


def snapshot_pre():
    """Copy of the DB after fixtures, before the operations (for invariant 'before')."""
    c = sqlite3.connect(DB)
    d = sqlite3.connect(PRE)
    try:
        c.backup(d)
    finally:
        d.close()
        c.close()


# ---------------------------------------------------------------------------
# fixtures (built through the models, as verify_sr1.py / the CF-10 harness do)
# ---------------------------------------------------------------------------
CTX = {}
_ref = [0]


def setup():
    with app.app_context():
        u = m.User(username='k7_admin', full_name='K7 Admin', role='Admin', is_active=True)
        u.set_password('k7-test-password')
        db.session.add(u)
        db.session.flush()
        seed = db.session.query(m.Reservation).order_by(m.Reservation.id).first()
        mode = db.session.query(m.PaymentMode).order_by(m.PaymentMode.id).first()
        CTX.update(admin_id=u.id, guest_id=seed.guest_id, room_type_id=seed.room_type_id,
                   seed_room_id=seed.room_id, mode_id=mode.id)
        db.session.commit()


def client():
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(CTX['admin_id'])
        s['_fresh'] = True
    return c


def mk_res(status='Reserved', arrival=None, departure=None, rate=1000, room_id=None, **extra):
    _ref[0] += 1
    arrival = arrival or date(2026, 9, 20)
    departure = departure or date(2026, 9, 22)
    r = m.Reservation(
        booking_reference='K7-%s-%d' % (SCEN.replace('_', '-')[:14], _ref[0]),
        guest_id=CTX['guest_id'], room_id=room_id, room_type_id=CTX['room_type_id'],
        arrival_date=arrival, departure_date=departure, adults=1, children=0, status=status,
        rate_per_night=rate, noshow_exempt=False, checkout_initiated=False, credit_amount=0,
        credit_settled_amount=0, cancellation_amount_refunded=0, cancellation_amount_forfeited=0,
        cancellation_amount_credit_voucher=0)
    for k, v in extra.items():
        setattr(r, k, v)
    db.session.add(r)
    db.session.flush()
    return r


def mk_payment(res, amount, pdate, purpose='settlement'):
    p = m.Payment(reservation_id=res.id, folio_id=svc.resolve_billing_folio_id(res, user_id=CTX['admin_id']),
                  payment_mode_id=CTX['mode_id'], amount=amount, payment_date=pdate, payment_purpose=purpose)
    db.session.add(p)
    db.session.flush()
    return p


def mk_voucher(expiry, code):
    v = m.CreditVoucher(voucher_code=code, guest_id=CTX['guest_id'], issued_amount=500, redeemed_amount=0,
                        issued_date=(current_bd_date() or BD_CONST), expiry_date=expiry, status='active')
    db.session.add(v)
    db.session.flush()
    return v


# ---------------------------------------------------------------------------
# operations. Each returns an observation dict; each commits on success.
# ---------------------------------------------------------------------------
def current_bd_date():
    r = raw('SELECT "current_date" FROM business_date LIMIT 1')
    return date.fromisoformat(r[0][0]) if r else None


def op_corr(bd):
    r = mk_res(arrival=bd, departure=bd + timedelta(days=1))
    p = mk_payment(r, 400, bd)
    pair = svc.post_payment_correction(p, new_amount=350, reason='K7 harness', user_id=CTX['admin_id'])
    db.session.commit()
    return {'reversal_date': iso(pair['reversal'].payment_date),
            'replacement_date': iso(pair['replacement'].payment_date)}


def op_corr_route():
    r = mk_res(arrival=date(2026, 8, 9), departure=date(2026, 8, 10))
    p = mk_payment(r, 400, date(2026, 8, 9))
    pid = p.id
    db.session.commit()
    global MAX_BEFORE
    MAX_BEFORE = max_ids()       # measurement mechanic: only rows created by the route are scanned (N-2)
    resp = client().post('/payment/%d/void' % pid, data={
        'void_reason': 'K7 harness', 'audit_override': '1', 'audit_override_reason': 'K7 harness override',
        'correction_new_amount': '350'})
    rows = raw('SELECT payment_date, is_reversal FROM payments WHERE corrects_id = ? ORDER BY id', pid)
    return {'http_status': resp.status_code,
            'reversal_date': next((d for d, rev in rows if rev), None),
            'replacement_date': next((d for d, rev in rows if not rev), None)}


def op_chgcorr(bd):
    r = mk_res(arrival=bd, departure=bd + timedelta(days=1))
    c = m.ExtraCharge(reservation_id=r.id, folio_id=svc.resolve_billing_folio_id(r, user_id=CTX['admin_id']),
                      description='K7 original', amount=500, charge_date=bd)
    db.session.add(c)
    db.session.flush()
    pair = svc.post_extra_charge_correction(c, new_amount=450, reason='K7 harness', user_id=CTX['admin_id'])
    db.session.commit()
    return {'reversal_date': iso(pair['reversal'].charge_date),
            'replacement_date': iso(pair['replacement'].charge_date)}


def op_refund(bd):
    r = mk_res(arrival=bd + timedelta(days=20), departure=bd + timedelta(days=22))
    mk_payment(r, 300, bd, 'advance')
    out = svc.post_cancellation_disposition(r, disposition='refund_full', refund_mode_id=CTX['mode_id'],
                                            reason='K7 harness', user_id=CTX['admin_id'])
    r.status = 'Cancelled'
    db.session.commit()
    return {'refund_date': iso(out['refund_payment'].payment_date)}


def op_voucher_issue(bd):
    r = mk_res(arrival=bd + timedelta(days=20), departure=bd + timedelta(days=22))
    mk_payment(r, 300, bd, 'advance')
    svc.post_cancellation_disposition(r, disposition='credit_voucher', voucher_amount=300,
                                      reason='K7 harness', user_id=CTX['admin_id'])
    r.status = 'Cancelled'
    db.session.commit()
    v = db.session.query(m.CreditVoucher).filter_by(issued_from_reservation_id=r.id).first()
    return {'issued_date': iso(v.issued_date) if v else None,
            'expiry_date': iso(v.expiry_date) if v else None}


def op_redeem(bd, expiry, code):
    r = mk_res(arrival=bd + timedelta(days=5), departure=bd + timedelta(days=6))
    v = mk_voucher(expiry, code)
    db.session.commit()
    obs = {'computed_status': svc.compute_voucher_status(v)}
    try:
        out = svc.redeem_credit_voucher(v, r, 100, user_id=CTX['admin_id'])
        db.session.commit()
        obs['redeem_result'] = 'ok'
        obs['payment_date'] = iso(out['payment'].payment_date) if out.get('payment') else None
    except ValueError as exc:
        db.session.rollback()
        obs['redeem_result'] = 'refused'
        obs['payment_date'] = None
        obs['refusal'] = str(exc)[:80]
    return obs


def op_report(expiry):
    v = mk_voucher(expiry, 'K7-RPT')
    vid = v.id
    db.session.commit()
    resp = client().get('/reports/voucher-ledger')
    return {'http_status': resp.status_code,
            'stored_status_after_report': raw('SELECT status FROM credit_vouchers WHERE id = ?', vid)[0][0]}


def op_checkout(bd):
    room = db.session.query(m.Room).filter_by(status='Vacant').order_by(m.Room.id).first()
    r = mk_res(status='CheckedIn', arrival=bd, departure=bd + timedelta(days=1), room_id=room.id)
    room.status = 'Occupied'
    rid = r.id
    db.session.commit()
    due = float(svc.calculate_stay_amount(db.session.get(m.Reservation, rid))['balance'])
    form = {'waive_late_checkout': '1', 'waive_late_co_reason': 'K7 deterministic probe',
            'extra_description': 'K7 extra', 'extra_amount': '100',
            'pm_amount_1': '%.2f' % (due + 600), 'overpay_reason': 'mistake',
            'overpay_resolution': 'tip', 'overpay_waiter_name': 'K7 Waiter', 'overpay_tip_remarks': 'K7'}
    resp = client().post('/checkout/%d' % rid, data=form)
    st = raw('SELECT status FROM reservations WHERE id = ?', rid)[0][0]
    extra = raw("SELECT charge_date FROM extra_charges WHERE reservation_id = ? AND description = 'K7 extra'", rid)
    tip = raw("SELECT charge_date FROM extra_charges WHERE reservation_id = ? AND charge_type = 'tip'", rid)
    settle = raw("SELECT payment_date FROM payments WHERE reservation_id = ? AND payment_purpose = 'settlement' ORDER BY id", rid)
    return {'http_status': resp.status_code, 'checkout_status': st,
            'extra_date': extra[-1][0] if extra else None,
            'tip_date': tip[-1][0] if tip else None,
            'settlement_date': settle[-1][0] if settle else None}


def op_overstay():
    d = date(INSTANT.year, INSTANT.month, INSTANT.day) - timedelta(days=1)
    r = mk_res(status='CheckedIn', arrival=d, departure=d, rate=2400, room_id=CTX['seed_room_id'],
               booking_type='Hourly', checkout_time='12:00', overstay_billed_until=None)
    rid = r.id
    db.session.commit()
    resp = client().post('/reservation/%d/overstay-charge' % rid, data={})
    rows = raw("SELECT charge_date, amount FROM extra_charges WHERE reservation_id = ? AND description LIKE 'Overstay%' ORDER BY id", rid)
    return {'http_status': resp.status_code, 'charge_rows': len(rows),
            'charge_date': rows[-1][0] if rows else None,
            'charge_amount': float(rows[-1][1]) if rows else None}


def op_defaults():
    r = mk_res(arrival=BD_CONST, departure=BD_CONST + timedelta(days=1))
    fid = svc.resolve_billing_folio_id(r, user_id=CTX['admin_id'])
    p = m.Payment(reservation_id=r.id, folio_id=fid, payment_mode_id=CTX['mode_id'], amount=1)
    c = m.ExtraCharge(reservation_id=r.id, folio_id=fid, description='K7 default', amount=1)
    v = m.CreditVoucher(voucher_code='K7-D1', guest_id=CTX['guest_id'], issued_amount=10, redeemed_amount=0,
                        status='active')
    db.session.add_all([p, c, v])
    db.session.flush()
    obs = {'payment_date': iso(p.payment_date), 'charge_date': iso(c.charge_date),
           'voucher_issued_date': iso(v.issued_date)}
    db.session.commit()
    return obs


def run_ops(names, bd):
    """Run each named operation, collecting a row-date list under one observation."""
    out = {}
    for n in names:
        if n == 'corr':
            out['corr'] = op_corr(bd)
        elif n == 'chgcorr':
            out['chgcorr'] = op_chgcorr(bd)
        elif n == 'refund':
            out['refund'] = op_refund(bd)
        elif n == 'voucher':
            out['voucher'] = op_voucher_issue(bd)
        elif n == 'redeem':
            out['redeem'] = op_redeem(bd, date(2027, 8, 10), 'K7-ALL')
        elif n == 'checkout':
            out['checkout'] = op_checkout(bd)
        elif n == 'overstay':
            out['overstay'] = op_overstay()
    return out


ALL_OPS = ['corr', 'chgcorr', 'refund', 'voucher', 'redeem', 'checkout', 'overstay']


def delete_bd_row():
    db.session.query(m.BusinessDate).delete()
    db.session.commit()


def guarded(fn, *a):
    """Run fn, return ('completed'|'raised', exception class name or None)."""
    try:
        fn(*a)
        return 'completed', None
    except Exception as exc:                       # StatementError wraps BusinessDateUnavailable
        db.session.rollback()
        orig = getattr(exc, 'orig', None)
        return 'raised', (type(orig).__name__ if orig is not None else type(exc).__name__)


# ---------------------------------------------------------------------------
setup()
OBS = {'freeze_proven': bool(PROOF.get('proven')), 'clock': CLOCK}
PROT_BEFORE = protected_state()
MAX_BEFORE = max_ids()
COUNTS_BEFORE = None

with app.app_context():
    if SCEN == 'S-08-09':
        OBS.update(op_corr(current_bd_date()))
    elif SCEN == 'S-08-09-route':
        OBS.update(op_corr_route())
    elif SCEN == 'S-10':
        OBS.update(op_refund(current_bd_date()))
    elif SCEN == 'S-VI':
        OBS.update(op_voucher_issue(current_bd_date()))
    elif SCEN == 'S-11':
        OBS.update(op_redeem(current_bd_date(), date(2027, 8, 10), 'K7-S11'))
    elif SCEN == 'V-1':
        OBS.update(op_redeem(current_bd_date(), date(2026, 8, 10), 'K7-V1'))
    elif SCEN == 'V-2':
        OBS.update(op_redeem(current_bd_date(), date(2026, 8, 9), 'K7-V2'))
    elif SCEN == 'V-3':
        OBS.update(op_redeem(current_bd_date(), date(2026, 9, 15), 'K7-V3'))
    elif SCEN == 'V-4':
        OBS.update(op_report(date(2026, 9, 15)))
    elif SCEN == 'S-17':
        OBS.update(op_checkout(current_bd_date()))
    elif SCEN == 'S-20':
        OBS.update(op_overstay())
    elif SCEN == 'S-TL':
        o1 = op_checkout(current_bd_date())
        o2 = op_overstay()
        ids = [r[0] for r in raw("SELECT id FROM extra_charges WHERE description IN ('K7 extra') OR description LIKE 'Overstay%' ORDER BY id")]
        # tax lines are produced lazily by the supported entry point (invoice / GST summary path)
        from app.gst_service import ensure_all_tax_lines
        for rid in sorted({r[0] for r in raw("SELECT reservation_id FROM extra_charges WHERE description IN ('K7 extra') OR description LIKE 'Overstay%'")}):
            ensure_all_tax_lines(db.session.get(m.Reservation, rid))
        tl = {}
        for cid in ids:
            rows = raw("SELECT charge_date FROM tax_lines WHERE charge_source_type = 'extra_charge' AND charge_source_id = ?", str(cid))
            cd = raw('SELECT charge_date FROM extra_charges WHERE id = ?', cid)[0][0]
            tl[str(cid)] = {'charge_date': cd, 'tax_line_dates': sorted({r[0] for r in rows}), 'tax_line_count': len(rows)}
        OBS['tax_lines'] = tl
        OBS['w17_w20_charges'] = len(ids)
        OBS['tax_lines_follow_row_date'] = bool(tl) and all(v['tax_line_count'] > 0 and v['tax_line_dates'] == [v['charge_date']] for v in tl.values())
        OBS['tax_line_dates'] = sorted({d for v in tl.values() for d in v['tax_line_dates']})
    elif SCEN == 'S-22-23':
        OBS.update(op_chgcorr(current_bd_date()))
    elif SCEN == 'D-1':
        OBS.update(op_defaults())
    elif SCEN == 'DDL-1':
        defaults = {}
        for t, col in (('credit_vouchers', 'issued_date'), ('payments', 'payment_date'),
                       ('extra_charges', 'charge_date'), ('business_date', 'current_date')):
            row = [r for r in raw('PRAGMA table_info(%s)' % t) if r[1] == col][0]
            defaults['%s.%s' % (t, col)] = row[4]
        OBS['column_defaults'] = defaults
        OBS['ddl_defaults_absent'] = all(v is None for v in defaults.values())
    elif SCEN == 'DDL-2':
        row = [r for r in raw('PRAGMA table_info(credit_vouchers)') if r[1] == 'issued_date'][0]
        OBS['ddl_default_present'] = bool(row[4]) and 'date' in str(row[4]).lower()
        OBS.update(op_voucher_issue(current_bd_date()))
    elif SCEN == 'F-1':
        delete_bd_row()
        n0 = len(LOGGED)
        try:
            r = svc.get_business_date()
            OBS['result'] = 'date:' + iso(r)
        except Exception as exc:
            OBS['result'] = 'raises:' + type(exc).__name__
        OBS['error_logged'] = any('business date' in s.lower() for s in LOGGED[n0:])
    elif SCEN.startswith('F-2-') or SCEN == 'D-2':
        bd = current_bd_date()
        # fixtures that need no business date are built first
        if SCEN == 'F-2-corr':
            r = mk_res(arrival=bd, departure=bd + timedelta(days=1)); p = mk_payment(r, 400, bd); db.session.commit()
            action = lambda: (svc.post_payment_correction(p, new_amount=350, reason='K7', user_id=CTX['admin_id']), db.session.commit())
        elif SCEN == 'F-2-chgcorr':
            r = mk_res(arrival=bd, departure=bd + timedelta(days=1))
            c = m.ExtraCharge(reservation_id=r.id, folio_id=svc.resolve_billing_folio_id(r, user_id=CTX['admin_id']),
                              description='K7 orig', amount=500, charge_date=bd)
            db.session.add(c); db.session.commit()
            action = lambda: (svc.post_extra_charge_correction(c, new_amount=450, reason='K7', user_id=CTX['admin_id']), db.session.commit())
        elif SCEN in ('F-2-refund', 'F-2-voucher'):
            r = mk_res(arrival=bd + timedelta(days=20), departure=bd + timedelta(days=22)); mk_payment(r, 300, bd, 'advance'); db.session.commit()
            kw = (dict(disposition='refund_full', refund_mode_id=CTX['mode_id']) if SCEN == 'F-2-refund'
                  else dict(disposition='credit_voucher', voucher_amount=300))
            action = lambda: (svc.post_cancellation_disposition(r, reason='K7', user_id=CTX['admin_id'], **kw), db.session.commit())
        elif SCEN == 'F-2-redeem':
            r = mk_res(arrival=bd + timedelta(days=5), departure=bd + timedelta(days=6)); v = mk_voucher(date(2027, 8, 10), 'K7-F2R'); db.session.commit()
            action = lambda: (svc.redeem_credit_voucher(v, r, 100, user_id=CTX['admin_id']), db.session.commit())
        elif SCEN == 'F-2-checkout':
            room = db.session.query(m.Room).filter_by(status='Vacant').order_by(m.Room.id).first()
            r = mk_res(status='CheckedIn', arrival=bd, departure=bd + timedelta(days=1), room_id=room.id); room.status = 'Occupied'; db.session.commit()
            due = float(svc.calculate_stay_amount(db.session.get(m.Reservation, r.id))['balance'])
            form = {'waive_late_checkout': '1', 'waive_late_co_reason': 'K7', 'extra_description': 'K7 extra', 'extra_amount': '100',
                    'pm_amount_1': '%.2f' % (due + 600), 'overpay_reason': 'mistake', 'overpay_resolution': 'tip',
                    'overpay_waiter_name': 'K7 Waiter', 'overpay_tip_remarks': 'K7'}
            rid = r.id
            action = lambda: client().post('/checkout/%d' % rid, data=form)
        elif SCEN == 'F-2-overstay':
            d = date(INSTANT.year, INSTANT.month, INSTANT.day) - timedelta(days=1)
            r = mk_res(status='CheckedIn', arrival=d, departure=d, rate=2400, room_id=CTX['seed_room_id'],
                       booking_type='Hourly', checkout_time='12:00', overstay_billed_until=None); db.session.commit()
            rid = r.id
            action = lambda: client().post('/reservation/%d/overstay-charge' % rid, data={})
        else:  # D-2
            r = mk_res(arrival=bd, departure=bd + timedelta(days=1)); fid = svc.resolve_billing_folio_id(r, user_id=CTX['admin_id']); db.session.commit()
            def action():
                p = m.Payment(reservation_id=r.id, folio_id=fid, payment_mode_id=CTX['mode_id'], amount=1)
                db.session.add(p); db.session.flush(); db.session.commit()
        delete_bd_row()
        MAX_BEFORE = max_ids()
        COUNTS_BEFORE = counts()
        what, exc = guarded(action)
        after = counts()
        created = sum(after[t] - COUNTS_BEFORE[t] for t in ('payments', 'extra_charges', 'credit_vouchers', 'audit_logs'))
        OBS.update({'raw_outcome': what, 'exception': exc, 'rows_delta': created,
                    'no_rows_created': created == 0,
                    'outcome': ('inserted' if SCEN == 'D-2' and what == 'completed' else
                                'raised' if SCEN == 'D-2' else
                                'completed' if created > 0 else 'refused')})
    elif SCEN == 'F-3a':
        delete_bd_row()
        from app.occupancy_engine import occupancy_debug_record
        n0 = len(LOGGED)
        try:
            OBS['payload_business_date'] = occupancy_debug_record()['business_date']
            OBS['raised'] = None
        except Exception as exc:
            OBS['payload_business_date'] = 'RAISED'
            OBS['raised'] = type(exc).__name__
        OBS['error_logged'] = any('business date' in s.lower() for s in LOGGED[n0:])
    elif SCEN == 'F-3b':
        from app.kpi_command_center import _build_governance_block
        delete_bd_row()
        try:
            res = _build_governance_block({})
            OBS['result'] = 'dict' if isinstance(res, dict) else 'other'
        except Exception as exc:
            OBS['result'] = 'raises:' + type(exc).__name__
    elif SCEN == 'F-3c':
        delete_bd_row()
        n0 = len(LOGGED)
        resp = client().get('/night-audit')
        OBS['http_status'] = resp.status_code
        OBS['error_logged'] = any('business date' in s.lower() for s in LOGGED[n0:])
    elif SCEN == 'F-3d':
        delete_bd_row()
        c0 = counts()['night_audit_logs']
        n0 = len(LOGGED)
        ret = svc.run_night_audit(app)
        OBS['returned'] = str(ret)
        OBS['night_audit_logs_created'] = counts()['night_audit_logs'] - c0
        OBS['error_logged'] = any('business date' in s.lower() for s in LOGGED[n0:])
    elif SCEN in ('N-3-AHEAD', 'S-ALL', 'S-ALL-UTC'):
        bd = current_bd_date()
        if SCEN == 'N-3-AHEAD':
            db.session.add(m.NightAuditLog(audit_date=date(2026, 10, 2), status='Completed',
                                           completed_at=datetime(2026, 10, 2, 23, 0, 0)))
            db.session.commit()
        MAX_BEFORE = max_ids()
        snapshot_pre()
        OBS['ops'] = run_ops(ALL_OPS, bd)
    else:
        raise SystemExit('unknown scenario ' + SCEN)

FINAL_BD = bd_now()
nr = new_rows(MAX_BEFORE)
OBS['bd_in_force'] = FINAL_BD
OBS['new_rows'] = nr
OBS['n2_new_rows_all_on_bd'] = (FINAL_BD is not None) and all(r['date'] == FINAL_BD for r in nr)
OBS['row_dates'] = sorted({r['date'] for r in nr})
OBS['rows_in_sealed_day'] = sum(1 for r in nr if r['date'] == '2026-10-02')
OBS['any_row_in_sealed_day'] = OBS['rows_in_sealed_day'] > 0
OBS['d11_unchanged'] = protected_state()[:2] == PROT_BEFORE[:2]
OBS['sealed_0809_unchanged'] = protected_state()[2] == PROT_BEFORE[2]
OBS['error_log_count'] = len(LOGGED)
print('K7JSON ' + json.dumps(OBS, default=str))
