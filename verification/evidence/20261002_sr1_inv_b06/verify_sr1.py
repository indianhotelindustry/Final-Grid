# -*- coding: utf-8 -*-
"""SR-1 / INV-B06 targeted verification (Founder Round 10: SR1-RULE, SR1-INT).

Each case seeds one situation into its OWN disposable copy of production
(``verification.dbcopy.make_copy``: production opened read-only and copied
with the SQLite backup API), then evaluates INV-B06 alone through the
invariant engine (``engine.evaluate_database``), one process per case.
``verification`` and ``app`` both come from ``--worktree``, so the same
expectations run against the control code (RED) and the branch (GREEN).

The live ``.env`` is NOT loaded. Messaging/AI variables are stripped and a
throwaway SECRET_KEY is required from the caller.

Expected results encode the Founder's ruling:
  - an advance may be dated from 30 calendar days before arrival up to the
    general tail (departure + 30); earlier is a violation;
  - every other payment keeps arrival .. departure + 30;
  - a correction (corrects_id) inherits the VERDICT of the transaction it
    corrects; its own date is not checked;
  - a cancellation refund (SR2-REV2 lineage) inherits the VERDICT of its
    reservation's non-voided advance payments: it fails if any is outside
    its window; its own date is not checked;
  - a stale business date is not an exemption.

Implementer readings, reported for confirmation (not founder text):
  - a correction whose original cannot be resolved, or a refund with no
    identifiable cancellation or no non-voided advance, has no origin to
    inherit from and is checked on its own date by the general rule
    (scenario N-5 of the founder-adopted set expects exactly this).

    <live venv python> verify_sr1.py --worktree <wt> --label <L>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument('--worktree', required=True)
ap.add_argument('--label', required=True)
ARGS = ap.parse_args()

WT = os.path.abspath(ARGS.worktree)
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')
assert os.path.basename(MAIN) == 'SukoonPMS', MAIN

STRIP = ('ULTRAMSG_TOKEN', 'ULTRAMSG_INSTANCE', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER',
         'SMTP_PASS', 'SMTP_FROM', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'FRONTDESK_WHATSAPP',
         'DATABASE_URL', 'WHATSAPP_API_KEY')
for k in STRIP:
    os.environ.pop(k, None)
assert os.environ.get('SECRET_KEY'), 'export a throwaway SECRET_KEY'
CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', FLASK_ENV='production')

sys.path.insert(0, WT)
import verification.config as vc                                   # noqa: E402
assert os.path.abspath(vc.__file__).startswith(os.path.join(WT, 'verification')), vc.__file__
vc.PRODUCTION_DB = PROD
from verification.dbcopy import make_copy, assert_production_untouched   # noqa: E402

A = date(2026, 9, 20)        # scenario arrival
D = date(2026, 9, 22)        # scenario departure
results = []


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def check(case, what, expect, got, note=''):
    ok = expect == got
    results.append({'case': case, 'what': what, 'expect': expect, 'got': got,
                    'pass': ok, 'note': note})
    print('%-4s %-6s %-74s expect=%-24s got=%-24s %s' % (
        'OK' if ok else 'FAIL', case, what[:74], str(expect)[:24], str(got)[:24], note[:100]))


# ---------------------------------------------------------------------------
def evaluate(db, mode='ENTIRE_DATABASE', business_date=''):
    """INV-B06 on *db* in a fresh process from WT -> (status, [violations])."""
    code = ('import os,sys,json; sys.path.insert(0,%r); os.chdir(%r); '
            'from verification.invariants import engine; '
            'r=engine.evaluate_database(%r, mode=%r, business_date=%r, ids=["INV-B06"])[0]; '
            'print("B06JSON "+json.dumps({"status":r.status,"violations":'
            '[getattr(v,"__dict__",v) for v in (r.violations or [])]},default=str))'
            % (WT, WT, db, mode, business_date))
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       env=CHILD_ENV)
    line = [l for l in p.stdout.splitlines() if l.startswith('B06JSON ')]
    if not line:
        return 'ERROR', [(p.stdout + p.stderr)[-600:]]
    d = json.loads(line[0][8:])
    return d['status'], d['violations']


def flagged(viol):
    return sorted(int(v['object_id']) for v in viol
                  if isinstance(v, dict) and v.get('object_type') == 'payment')


def new_reservation(c, arrival=A, departure=D, like_id=1):
    cols = [r[1] for r in c.execute('PRAGMA table_info(reservations)') if r[1] != 'id']
    unique = {'invoice_number': 'NULL', 'advance_receipt_number': 'NULL',
              'booking_reference': "'SR1-TMP-' || abs(random())"}
    c.execute('INSERT INTO reservations (%s) SELECT %s FROM reservations WHERE id = ?' % (
        ', '.join('"%s"' % x for x in cols), ', '.join(unique.get(x, '"%s"' % x) for x in cols)),
        (like_id,))
    rid = c.execute('SELECT last_insert_rowid()').fetchone()[0]
    c.execute("UPDATE reservations SET booking_reference = 'SR1-' || ?, status = 'Reserved', "
              'arrival_date = ?, departure_date = ?, cancellation_refund_payment_id = NULL, '
              'cancellation_disposition = NULL, cancellation_amount_refunded = 0, '
              'cancellation_processed_at = NULL WHERE id = ?',
              (rid, arrival.isoformat(), departure.isoformat(), rid))
    return rid


def pay(c, rid, amount, purpose, on, is_rev=0, is_corr=0, corrects=None, voided=0):
    mode = c.execute('SELECT MIN(id) FROM payment_modes').fetchone()[0]
    c.execute('INSERT INTO payments (reservation_id, payment_mode_id, amount, payment_date, '
              'created_at, is_voided, is_correction, is_reversal, corrects_id, payment_purpose) '
              "VALUES (?, ?, ?, ?, '2026-10-02 06:00:00', ?, ?, ?, ?, ?)",
              (rid, mode, amount, on.isoformat(), voided, is_corr, is_rev, corrects, purpose))
    return c.execute('SELECT last_insert_rowid()').fetchone()[0]


def correction_pair(c, rid, original, amount, on):
    rev = pay(c, rid, amount, None, on, is_rev=1, is_corr=1, corrects=original)
    rep = pay(c, rid, amount, None, on, is_rev=0, is_corr=1, corrects=original)
    return rev, rep


def cancel(c, rid, refund_id, amount, disposition='refund_full'):
    c.execute("UPDATE reservations SET status = 'Cancelled', cancellation_disposition = ?, "
              'cancellation_amount_refunded = ?, cancellation_refund_payment_id = ?, '
              "cancellation_processed_at = '2026-10-02 06:00:00' WHERE id = ?",
              (disposition, amount, refund_id, rid))


# ---------------------------------------------------------------------------
# Each case: (id, description, expected status, fn(c) -> expected flagged ids, mode)
CASES = []


def case(cid, what, expect, mode='ENTIRE_DATABASE'):
    def deco(fn):
        CASES.append((cid, what, expect, fn, mode))
        return fn
    return deco


# --- the 13 targeted scenarios (SR1_DECISION_REQUIRED.md section 6),
#     expectations re-derived under SR1-RULE / SR1-INT ----------------------
@case('P-1', 'advance at booking, 20 days before arrival', 'HOLDS')
def _p1(c):
    r = new_reservation(c); pay(c, r, 500, 'advance', A - timedelta(20)); return []


@case('P-2', 'advance at booking, 400 days before arrival (DQ-01: beyond 30 days)', 'VIOLATED')
def _p2(c):
    r = new_reservation(c); return [pay(c, r, 500, 'advance', A - timedelta(400))]


@case('P-3', 'booking-time voucher application (purpose settlement), 20 days before arrival', 'VIOLATED')
def _p3(c):
    r = new_reservation(c); return [pay(c, r, 500, 'settlement', A - timedelta(20))]


@case('P-4', 'correction pair of a valid advance, posted 10 days before arrival', 'HOLDS')
def _p4(c):
    r = new_reservation(c); a = pay(c, r, 500, 'advance', A - timedelta(20))
    correction_pair(c, r, a, 500, A - timedelta(10)); return []


@case('P-5', 'cancellation refund (SR2-REV2 lineage) of a valid advance', 'HOLDS')
def _p5(c):
    r = new_reservation(c); pay(c, r, 500, 'advance', A - timedelta(20))
    f = pay(c, r, 500, 'refund', A - timedelta(15), is_rev=1); cancel(c, r, f, 500); return []


@case('P-6', 'settlement inside the stay', 'HOLDS')
def _p6(c):
    r = new_reservation(c); pay(c, r, 500, 'settlement', A + timedelta(1)); return []


@case('P-7', 'credit recovery 10 days after departure', 'HOLDS')
def _p7(c):
    r = new_reservation(c); pay(c, r, 500, 'credit_recovery', D + timedelta(10)); return []


@case('N-2', 'settlement 5 days before arrival (non-exempt pre-arrival)', 'VIOLATED')
def _n2(c):
    r = new_reservation(c); return [pay(c, r, 500, 'settlement', A - timedelta(5))]


@case('N-3', 'advance 31 days after departure (post-departure)', 'VIOLATED')
def _n3(c):
    r = new_reservation(c); return [pay(c, r, 500, 'advance', D + timedelta(31))]


@case('N-4', 'advance 31 days before arrival (one day beyond the window)', 'VIOLATED')
def _n4(c):
    r = new_reservation(c); return [pay(c, r, 500, 'advance', A - timedelta(31))]


@case('N-5', 'refund with no cancellation lineage, 5 days before arrival', 'VIOLATED')
def _n5(c):
    r = new_reservation(c); pay(c, r, 500, 'advance', A - timedelta(20))
    return [pay(c, r, 500, 'refund', A - timedelta(5), is_rev=1)]


@case('N-6', 'stale-business-date check-in deposit (NULL purpose), 53 days before arrival', 'VIOLATED')
def _n6(c):
    r = new_reservation(c); return [pay(c, r, 500, None, A - timedelta(53))]


# --- supplementary: DQ-03 coverage, boundaries, SR1-INT consequences --------
@case('S-01', 'advance exactly 30 days before arrival (inclusive boundary)', 'HOLDS')
def _s01(c):
    r = new_reservation(c); pay(c, r, 500, 'advance', A - timedelta(30)); return []


@case('S-02', 'settlement 31 days after departure (invalid post-departure)', 'VIOLATED')
def _s02(c):
    r = new_reservation(c); return [pay(c, r, 500, 'settlement', D + timedelta(31))]


@case('S-03', 'settlement exactly 30 days after departure (tail boundary)', 'HOLDS')
def _s03(c):
    r = new_reservation(c); pay(c, r, 500, 'settlement', D + timedelta(30)); return []


@case('S-04', 'correction pair whose original advance is 45 days before arrival', 'VIOLATED')
def _s04(c):
    r = new_reservation(c); a = pay(c, r, 500, 'advance', A - timedelta(45))
    rev, rep = correction_pair(c, r, a, 500, A - timedelta(10)); return [a, rev, rep]


@case('S-05', 'cancellation refund whose only advance is 45 days before arrival', 'VIOLATED')
def _s05(c):
    r = new_reservation(c); a = pay(c, r, 500, 'advance', A - timedelta(45))
    f = pay(c, r, 500, 'refund', A - timedelta(10), is_rev=1); cancel(c, r, f, 500); return [a, f]


@case('S-06', 'cancellation refund drawn from one valid and one out-of-window advance', 'VIOLATED')
def _s06(c):
    r = new_reservation(c); pay(c, r, 300, 'advance', A - timedelta(20))
    bad = pay(c, r, 200, 'advance', A - timedelta(45))
    f = pay(c, r, 500, 'refund', A - timedelta(10), is_rev=1); cancel(c, r, f, 500); return [bad, f]


@case('S-07', 'correction of a valid settlement posted 45 days after departure (verdict, ADR-004)', 'HOLDS')
def _s07(c):
    r = new_reservation(c); s = pay(c, r, 500, 'settlement', A + timedelta(1))
    correction_pair(c, r, s, 500, D + timedelta(45)); return []


@case('S-08', 'correction of a correction whose root advance is 45 days before arrival', 'VIOLATED')
def _s08(c):
    r = new_reservation(c); a = pay(c, r, 500, 'advance', A - timedelta(45))
    rev, rep = correction_pair(c, r, a, 500, A - timedelta(10))
    rev2, rep2 = correction_pair(c, r, rep, 500, A - timedelta(5)); return [a, rev, rep, rev2, rep2]


@case('S-09', 'correction of a valid advance dated 400 days before arrival (own date unchecked)', 'HOLDS')
def _s09(c):
    r = new_reservation(c); a = pay(c, r, 500, 'advance', A - timedelta(20))
    correction_pair(c, r, a, 500, A - timedelta(400)); return []


@case('S-10', 'correction naming a missing original, 5 days before arrival (no origin: own date)', 'VIOLATED')
def _s10(c):
    r = new_reservation(c)
    return [pay(c, r, 500, None, A - timedelta(5), is_rev=1, is_corr=1, corrects=99999999)]


@case('S-11', 'cancellation refund whose only advance is voided (no origin: own date, before arrival)', 'VIOLATED')
def _s11(c):
    r = new_reservation(c); pay(c, r, 500, 'advance', A - timedelta(20), voided=1)
    f = pay(c, r, 500, 'refund', A - timedelta(5), is_rev=1); cancel(c, r, f, 500); return [f]


@case('S-12', 'S-04 evaluated for the correction\'s business date only (origin out of scope)',
      'VIOLATED', mode='BUSINESS_DATE')
def _s12(c):
    r = new_reservation(c); a = pay(c, r, 500, 'advance', A - timedelta(45))
    rev, rep = correction_pair(c, r, a, 500, A - timedelta(10)); return [rev, rep]


SCOPE_DATE = {'S-12': (A - timedelta(10)).isoformat()}


# ---------------------------------------------------------------------------
def seed_case():
    """N-1: the INV-B06 negative seed exactly as registered in WT."""
    code = ('import sys,json; sys.path.insert(0,%r); '
            'from verification.invariants import registry; '
            'registry.load_all(); inv=registry.get("INV-B06"); '
            'print("SEEDJSON "+json.dumps(list(inv.negative_seed)))' % WT)
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=CHILD_ENV)
    line = [l for l in p.stdout.splitlines() if l.startswith('SEEDJSON ')]
    if not line:
        check('N-1', 'registered negative seed', 'readable', 'ERROR', (p.stdout + p.stderr)[-200:])
        return
    seed = json.loads(line[0][9:])
    h = make_copy(name='sr1_n1.db')
    c = sqlite3.connect(h.copy_path)
    for stmt in seed:
        c.execute(stmt)
    c.commit(); c.close()
    status, viol = evaluate(h.copy_path)
    check('N-1', 'registered negative seed applied to a production copy', 'VIOLATED', status,
          'seed=%s flagged=%s' % (' ; '.join(seed)[:80], flagged(viol)))
    assert_production_untouched(h)


def baseline_case():
    """P-00: the unseeded production copy."""
    h = make_copy(name='sr1_p00.db')
    status, viol = evaluate(h.copy_path)
    check('P-00', 'unseeded production copy', 'HOLDS', status, 'flagged=%s' % flagged(viol))
    assert_production_untouched(h)


def real_writer_case():
    """APP-1/APP-2: corrections and a cancellation refund produced by the REAL
    writers (post_payment_correction, post_cancellation_disposition) on a copy.
    The writers date these rows by the calendar today (K-7 sites W-08..W-10)."""
    h = make_copy(name='sr1_app.db')
    code = r'''
import os, sys, json, datetime as dt
sys.path.insert(0, %r); os.chdir(%r)
os.environ['DATABASE_URL'] = 'sqlite:///' + %r.replace('\\', '/')
from app import create_app
from app import models as m
from app.services import scheduler, post_cancellation_disposition, post_payment_correction
from app.services import resolve_billing_folio_id
app = create_app()
if scheduler.running: scheduler.shutdown(wait=False)
with app.app_context():
    db = m.db
    seed = db.session.query(m.Reservation).order_by(m.Reservation.id).first()
    mode = db.session.query(m.PaymentMode).order_by(m.PaymentMode.id).first()
    today = dt.date.today()
    def res(ref, arr, dep):
        r = m.Reservation(booking_reference=ref, guest_id=seed.guest_id, room_type_id=seed.room_type_id,
            arrival_date=arr, departure_date=dep, adults=1, children=0, status='Reserved',
            rate_per_night=1000, noshow_exempt=False, checkout_initiated=False, credit_amount=0,
            credit_settled_amount=0, cancellation_amount_refunded=0, cancellation_amount_forfeited=0,
            cancellation_amount_credit_voucher=0)
        db.session.add(r); db.session.flush(); return r
    # APP-1: advance 20 days before arrival, then the real cancellation refund.
    r1 = res('SR1-APP1', today + dt.timedelta(days=20), today + dt.timedelta(days=22))
    a1 = m.Payment(reservation_id=r1.id, folio_id=resolve_billing_folio_id(r1, user_id=1),
                   payment_mode_id=mode.id, amount=300, payment_date=today, payment_purpose='advance')
    db.session.add(a1); db.session.flush()
    out = post_cancellation_disposition(r1, disposition='refund_full', refund_mode_id=mode.id,
                                        reason='SR1 real writer', user_id=1)
    r1.status = 'Cancelled'
    # APP-2: settlement of a stay that ended 2026-08-11, corrected today by the real writer.
    r2 = res('SR1-APP2', dt.date(2026, 8, 10), dt.date(2026, 8, 11))
    s2 = m.Payment(reservation_id=r2.id, folio_id=resolve_billing_folio_id(r2, user_id=1),
                   payment_mode_id=mode.id, amount=400, payment_date=dt.date(2026, 8, 10),
                   payment_purpose='settlement')
    db.session.add(s2); db.session.flush()
    pair = post_payment_correction(s2, new_amount=350, reason='SR1 real writer', user_id=1)
    db.session.commit()
    rp = out['refund_payment']
    print('APPJSON ' + json.dumps({
        'today': today, 'app1_advance': [a1.id, a1.payment_date], 'app1_refund': [rp.id, rp.payment_date],
        'app2_settlement': [s2.id, s2.payment_date],
        'app2_reversal': [pair['reversal'].id, pair['reversal'].payment_date],
        'app2_replacement': [pair['replacement'].id, pair['replacement'].payment_date]}, default=str))
''' % (WT, WT, h.copy_path)
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=CHILD_ENV)
    line = [l for l in p.stdout.splitlines() if l.startswith('APPJSON ')]
    info = json.loads(line[0][8:]) if line else {'error': (p.stdout + p.stderr)[-500:]}
    status, viol = evaluate(h.copy_path)
    check('APP', 'real writers: refund of a 20-day advance; correction of a past stay posted today',
          ('HOLDS', []), (status, flagged(viol)), json.dumps(info, default=str)[:300])
    results[-1]['writer_rows'] = info
    assert_production_untouched(h)


def main():
    prod_before = sha(PROD)
    print('[sr1] worktree %s  label %s  production %s' % (WT, ARGS.label, prod_before[:16]))
    baseline_case()
    seed_case()
    for cid, what, expect, fn, mode in CASES:
        h = make_copy(name='sr1_%s.db' % cid.lower().replace('-', ''))
        c = sqlite3.connect(h.copy_path)
        want = sorted(fn(c))
        c.commit(); c.close()
        status, viol = evaluate(h.copy_path, mode=mode, business_date=SCOPE_DATE.get(cid, ''))
        check(cid, what, (expect, want), (status, flagged(viol)))
        assert_production_untouched(h)
    real_writer_case()
    prod_after = sha(PROD)
    check('PROD', 'production pms.db unchanged across the run', prod_before, prod_after)
    commit = subprocess.check_output(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
    dirty = subprocess.check_output(['git', '-C', WT, 'status', '--porcelain', '--',
                                     'verification/invariants', 'app']).decode().strip()
    out = {'task': 'SR-1 / INV-B06 targeted verification', 'label': ARGS.label,
           'worktree': WT, 'worktree_commit': commit, 'code_tree_status': dirty,
           'finished': datetime.now().isoformat(timespec='seconds'),
           'scenario_window': {'arrival': A.isoformat(), 'departure': D.isoformat()},
           'production_sha256_before': prod_before, 'production_sha256_after': prod_after,
           'passed': sum(r['pass'] for r in results), 'total': len(results), 'results': results}
    with open(os.path.join(HERE, 'sr1_%s.json' % ARGS.label), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, default=str)
    print('SR1 %s: %d/%d' % (ARGS.label, out['passed'], out['total']))


if __name__ == '__main__':
    main()
