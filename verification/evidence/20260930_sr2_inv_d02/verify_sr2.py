# -*- coding: utf-8 -*-
"""SR-2 / INV-D02 targeted verification (Founder rule, 2026-09-30).

Each case seeds one situation into its OWN disposable copy of production
(``verification.dbcopy.make_copy`` - production opened read-only, copied with
the SQLite backup API) and evaluates INV-D02 alone through the invariant
engine (``engine.evaluate_database``), one process per case. ``verification``
and ``app`` come from this worktree.

Expected results encode the Founder's rule text (recorded in
FOUNDER_DECISIONS.md, SR-2):
  - an ordinary correction/reversal must identify its originating
    transaction (corrects_id resolving, same reservation);
  - a cancellation refund is linked through the valid, identifiable
    cancellation that generated it;
  - a reservation, guest, folio or amount match alone is not lineage.

Revision 2 (Founder, 2026-10-01): a legitimate refund does not depend on the
reservation's status today; the cancellation snapshot (disposition,
cancellation_processed_at, pointer) is the historical record; the audit trail
is supporting evidence only; amount equality is a separately named
consistency check; later void/correction activity does not change lineage.

    <main>\\venv\\Scripts\\python.exe verify_sr2.py [--label L]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')
sys.path.insert(0, WT)

import verification.config as vc                                   # noqa: E402
vc.PRODUCTION_DB = PROD
from verification.dbcopy import make_copy, assert_production_untouched   # noqa: E402

results = []


def check(case, what, expect, got, note=''):
    ok = expect == got
    results.append({'case': case, 'what': what, 'expect': expect, 'got': got, 'pass': ok,
                    'note': note})
    print('%-4s %-9s %-78s expect=%-9s got=%-9s %s' % ('OK' if ok else 'FAIL', case, what[:78],
                                                         expect, got, note[:120]))


# ---------------------------------------------------------------------------
def evaluate(db):
    """INV-D02 on *db*, in a fresh process; returns (status, [violation dicts])."""
    code = ('import os,sys,json; sys.path.insert(0,%r); '
            'from dotenv import load_dotenv; load_dotenv(%r, override=False); '
            'from verification.invariants import engine; '
            'r=engine.evaluate_database(%r, ids=["INV-D02"])[0]; '
            'print("D02JSON "+json.dumps({"status":r.status,"violations":[getattr(v,"__dict__",v) for v in (r.violations or [])]},default=str))'
            % (WT, os.path.join(MAIN, '.env'), db))
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    line = [l for l in p.stdout.splitlines() if l.startswith('D02JSON ')]
    if not line:
        return 'ERROR', [(p.stdout + p.stderr)[-400:]]
    d = json.loads(line[0][8:])
    return d['status'], d['violations']


def objects(viol):
    out = []
    for v in viol:
        if isinstance(v, dict):
            out.append(str(v.get('object_id') or v.get('object') or v.get('id') or v)[:60])
        else:
            out.append(str(v)[:60])
    return out


def base(name):
    h = make_copy(name='sr2_%s.db' % name)
    return h, h.copy_path


def one(conn, sql, *args):
    return conn.execute(sql, args).fetchone()


def new_reservation(c, like_id=1, guest_id=None, status='CheckedOut'):
    """Clone reservation *like_id* into a new row (fresh booking reference)."""
    cols = [r[1] for r in c.execute('PRAGMA table_info(reservations)') if r[1] != 'id']
    unique = {'invoice_number': 'NULL', 'advance_receipt_number': 'NULL',
              'booking_reference': "'SR2-TMP-' || abs(random())"}
    dst = ', '.join('"%s"' % x for x in cols)
    src = ', '.join(unique.get(x, '"%s"' % x) for x in cols)
    c.execute('INSERT INTO reservations (%s) SELECT %s FROM reservations WHERE id = ?' % (dst, src),
              (like_id,))
    rid = c.execute('SELECT last_insert_rowid()').fetchone()[0]
    c.execute("UPDATE reservations SET booking_reference = 'SR2-' || ?, status = ?, "
              "cancellation_refund_payment_id = NULL, cancellation_disposition = NULL, "
              "cancellation_amount_refunded = 0, cancellation_processed_at = NULL WHERE id = ?",
              (rid, status, rid))
    if guest_id is not None:
        c.execute('UPDATE reservations SET guest_id = ? WHERE id = ?', (guest_id, rid))
    return rid


def pay(c, rid, amount, purpose='settlement', is_rev=0, is_corr=0, corrects=None, reason=None):
    mode = one(c, 'SELECT MIN(id) FROM payment_modes')[0]
    c.execute('INSERT INTO payments (reservation_id, payment_mode_id, amount, payment_date, created_at, '
              'is_voided, is_correction, is_reversal, corrects_id, correction_reason, payment_purpose) '
              "VALUES (?, ?, ?, '2026-08-10', '2026-08-10 12:00:00', 0, ?, ?, ?, ?, ?)",
              (rid, mode, amount, is_corr, is_rev, corrects, reason, purpose))
    return c.execute('SELECT last_insert_rowid()').fetchone()[0]


def charge(c, rid, amount, is_rev=0, is_corr=0, corrects=None):
    c.execute('INSERT INTO extra_charges (reservation_id, description, amount, charge_date, created_at, '
              'is_correction, is_reversal, corrects_id) '
              "VALUES (?, 'SR2 charge', ?, '2026-08-10', '2026-08-10 12:00:00', ?, ?, ?)",
              (rid, amount, is_corr, is_rev, corrects))
    return c.execute('SELECT last_insert_rowid()').fetchone()[0]


def cancel(c, rid, refund_id, amount, disposition='refund_full', status='Cancelled',
           processed_at='2026-08-10 12:00:00'):
    c.execute('UPDATE reservations SET status = ?, cancellation_disposition = ?, '
              'cancellation_amount_refunded = ?, cancellation_refund_payment_id = ?, '
              'cancellation_processed_at = ? WHERE id = ?',
              (status, disposition, amount, refund_id, processed_at, rid))


# ---------------------------------------------------------------------------
CASES = []
#: cases whose failure must carry a specific name (consistency vs lineage)
KIND = {'N3': 'recorded refund', 'N5': 'no processed cancellation is identifiable',
        'V3': 'corrects_id is NULL'}


def case(cid, what, expect):
    def deco(fn):
        CASES.append((cid, what, expect, fn))
        return fn
    return deco


@case('T1a', 'payment correction pair: reversal + replacement identify the original', 'HOLDS')
def _t1a(c):
    r = new_reservation(c)
    p = pay(c, r, 500)
    pay(c, r, 500, 'settlement', is_rev=1, is_corr=1, corrects=p, reason='SR2 reversal')
    pay(c, r, 450, 'settlement', is_rev=0, is_corr=1, corrects=p, reason='SR2 replacement')


@case('T1b', 'charge correction pair identifies the original charge', 'HOLDS')
def _t1b(c):
    r = new_reservation(c)
    x = charge(c, r, 200)
    charge(c, r, 200, is_rev=1, is_corr=1, corrects=x)
    charge(c, r, 150, is_corr=1, corrects=x)


@case('T2a', 'cancellation refund generated by a valid cancellation (seeded exactly as the writer builds it)', 'HOLDS')
def _t2a(c):
    r = new_reservation(c, status='Reserved')
    pay(c, r, 300, 'advance')
    f = pay(c, r, 300, 'refund', is_rev=1, reason='Cancellation refund | SR2')
    cancel(c, r, f, 300)


@case('T2b', 'refund_partial cancellation refund', 'HOLDS')
def _t2b(c):
    r = new_reservation(c, status='Reserved')
    pay(c, r, 500, 'advance')
    f = pay(c, r, 200, 'refund', is_rev=1, reason='Cancellation refund | SR2')
    cancel(c, r, f, 200, disposition='refund_partial')


@case('T3a', 'same reservation, unrelated: a second refund on a cancelled reservation not generated by it', 'FAIL')
def _t3a(c):
    r = new_reservation(c, status='Reserved')
    pay(c, r, 300, 'advance')
    f = pay(c, r, 300, 'refund', is_rev=1)
    pay(c, r, 300, 'refund', is_rev=1)                  # not the cancellation's refund
    cancel(c, r, f, 300)


@case('T3b', 'same reservation, unrelated: reversal with no original on a reservation that has payments', 'FAIL')
def _t3b(c):
    r = new_reservation(c)
    pay(c, r, 500)
    pay(c, r, 500, is_rev=1, is_corr=1)


@case('T4', 'same guest, unrelated: refund on another reservation of the guest whose cancellation refunded', 'FAIL')
def _t4(c):
    r = new_reservation(c, status='Reserved')
    g = one(c, 'SELECT guest_id FROM reservations WHERE id = ?', r)[0]
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300)
    r2 = new_reservation(c, guest_id=g, status='Reserved')
    pay(c, r2, 300, 'refund', is_rev=1)


@case('T5', 'same amount, unrelated: reversal equal to an existing payment, no original named', 'FAIL')
def _t5(c):
    r = new_reservation(c)
    pay(c, r, 777)
    r2 = new_reservation(c)
    pay(c, r2, 777, is_rev=1, is_corr=1)


@case('T6', 'orphan refund: no original, reservation not cancelled', 'FAIL')
def _t6(c):
    r = new_reservation(c)
    pay(c, r, 300, 'refund', is_rev=1)


@case('T7a', 'cross-reservation payment reference: corrects_id resolves to another reservation', 'FAIL')
def _t7a(c):
    r1, r2 = new_reservation(c), new_reservation(c)
    p = pay(c, r1, 400)
    pay(c, r2, 400, is_rev=1, is_corr=1, corrects=p)


@case('T7b', 'cross-reservation charge reference', 'FAIL')
def _t7b(c):
    r1, r2 = new_reservation(c), new_reservation(c)
    x = charge(c, r1, 120)
    charge(c, r2, 120, is_rev=1, is_corr=1, corrects=x)


@case('T7c', 'cancellation pointer on another reservation than the refund', 'FAIL')
def _t7c(c):
    r1, r2 = new_reservation(c, status='Reserved'), new_reservation(c, status='Reserved')
    f = pay(c, r2, 300, 'refund', is_rev=1)
    cancel(c, r1, f, 300)


@case('T8', 'missing original: corrects_id does not resolve', 'FAIL')
def _t8(c):
    r = new_reservation(c)
    pay(c, r, 500, is_rev=1, is_corr=1, corrects=999999)


@case('N1', 'cancellation record stamped, reservation status later NOT Cancelled (status is not lineage)', 'HOLDS')
def _n1(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300, status='Reserved')


@case('N1b', 'same, status later CheckedOut', 'HOLDS')
def _n1b(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300, status='CheckedOut')


@case('N5', 'pointer + refund disposition but NO cancellation_processed_at (no processed cancellation identifiable)', 'FAIL')
def _n5(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300, processed_at=None)


@case('V1', 'refund voided AFTER the cancellation (subsequent activity, lineage unchanged)', 'HOLDS')
def _v1(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300)
    c.execute("UPDATE payments SET is_voided = 1, voided_at = '2026-08-11 09:00:00', "
              "void_reason = 'SR2 later void' WHERE id = ?", (f,))


@case('V2', 'refund later corrected: a correction reversal names the refund; the refund keeps its lineage', 'HOLDS')
def _v2(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300)
    pay(c, r, 300, 'refund', is_rev=1, is_corr=1, corrects=f, reason='SR2 later correction')


@case('V3', 'a correction that names no original is still a failure (only the correction row)', 'FAIL')
def _v3(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300)
    pay(c, r, 300, 'refund', is_rev=1, is_corr=1, corrects=None, reason='SR2 orphan correction')


@case('N2', 'cancellation pointer, but disposition generates no refund (forfeit)', 'FAIL')
def _n2(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 300, disposition='forfeit')


@case('N3', 'lineage established, but refund amount differs from the recorded refund (consistency check)', 'FAIL')
def _n3(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'refund', is_rev=1)
    cancel(c, r, f, 250)


@case('N4', 'row pointed to by a cancellation is a correction, not a refund', 'FAIL')
def _n4(c):
    r = new_reservation(c, status='Reserved')
    f = pay(c, r, 300, 'settlement', is_rev=1, is_corr=1)
    cancel(c, r, f, 300)


# ---------------------------------------------------------------------------
def app_refund_case():
    """T2-APP: a refund produced by the REAL writer (post_cancellation_disposition)."""
    h, db = base('t2app')
    code = r'''
import os, sys, json
sys.path.insert(0, %r)
from dotenv import load_dotenv; load_dotenv(%r, override=False)
os.environ['DATABASE_URL'] = 'sqlite:///' + %r.replace('\\', '/')
os.environ['FLASK_ENV'] = 'production'
from app import create_app
from app import models as m
from app.services import scheduler, post_cancellation_disposition
app = create_app()
if scheduler.running: scheduler.shutdown(wait=False)
with app.app_context():
    db = m.db
    seed = db.session.query(m.Reservation).order_by(m.Reservation.id).first()
    import datetime as dt
    r = m.Reservation(booking_reference='SR2-APP', guest_id=seed.guest_id, room_type_id=seed.room_type_id,
        arrival_date=dt.date(2026, 9, 20), departure_date=dt.date(2026, 9, 21), adults=1, children=0,
        status='Reserved', rate_per_night=1000, noshow_exempt=False, checkout_initiated=False,
        credit_amount=0, credit_settled_amount=0, cancellation_amount_refunded=0,
        cancellation_amount_forfeited=0, cancellation_amount_credit_voucher=0)
    db.session.add(r); db.session.flush()
    from app.services import resolve_billing_folio_id, audited_financial_write
    mode = db.session.query(m.PaymentMode).order_by(m.PaymentMode.id).first()
    adv = m.Payment(reservation_id=r.id, folio_id=resolve_billing_folio_id(r, user_id=1), payment_mode_id=mode.id,
                    amount=300, payment_date=dt.date(2026, 8, 10), payment_purpose='advance')
    db.session.add(adv); db.session.flush()
    audited_financial_write('Payment', adv.id, 'posted', {}, {'amount': 300, 'flow': 'sr2_fixture'}, user_id=1)
    res = post_cancellation_disposition(r, disposition='refund_full', refund_mode_id=mode.id,
                                        reason='SR2 real writer', user_id=1)
    r.status = 'Cancelled'
    db.session.commit()
    rp = res['refund_payment']
    audit = db.session.execute(db.text(
        "SELECT action, COUNT(*) FROM audit_logs WHERE (entity_type='Payment' AND entity_id=:p) "
        "OR (entity_type='Reservation' AND entity_id=:r) GROUP BY action"),
        {'p': rp.id, 'r': r.id}).fetchall()
    print('APPJSON ' + json.dumps({'reservation': r.id, 'refund_id': rp.id, 'corrects_id': rp.corrects_id,
                                   'is_reversal': rp.is_reversal, 'pointer': r.cancellation_refund_payment_id,
                                   'processed_at_stamped': r.cancellation_processed_at is not None,
                                   'refund_created_at_le_processed_at': (rp.created_at <= r.cancellation_processed_at),
                                   'audit_supporting_rows': {a: n for a, n in audit}}, default=str))
''' % (WT, os.path.join(MAIN, '.env'), db)
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    line = [l for l in p.stdout.splitlines() if l.startswith('APPJSON ')]
    info = json.loads(line[0][8:]) if line else {'error': (p.stdout + p.stderr)[-400:]}
    status, viol = evaluate(db)
    check('T2-APP', 'cancellation refund produced by the real post_cancellation_disposition writer',
          'HOLDS', status, json.dumps(info))
    check('T2-APP-stamp', 'the real writer stamps cancellation_processed_at (the historical record the rule relies on)',
          True, info.get('processed_at_stamped'))
    # Same copy, status moved away from Cancelled afterwards: lineage must hold.
    cx = sqlite3.connect(db)
    cx.execute("UPDATE reservations SET status = 'Reserved' WHERE id = ?", (info['reservation'],))
    cx.commit()
    cx.close()
    status2, viol2 = evaluate(db)
    check('T2-APP-status', 'real-writer refund, reservation status later no longer Cancelled', 'HOLDS', status2,
          '; '.join(objects(viol2)))
    return assert_production_untouched(h)


def voidcn_case():
    """T9: DS-ACT-VOIDCN - classified synthetic/unreachable; INV-D02 not silently accepted."""
    from verification.datasets import registry, builder
    d = [x for x in registry.all_datasets() if x.dataset_id == 'DS-ACT-VOIDCN'][0]
    reach = getattr(d, 'reachability', None)
    declared = d.expectations.invariants.get('INV-D02') if hasattr(d.expectations, 'invariants') else None
    m = builder.build(d)
    try:
        path = getattr(m, 'db_path', None) or getattr(m, 'path', None)
        status, viol = evaluate(path)
    finally:
        builder.discard(m)
    check('T9a', 'VOIDCN is classified synthetic/unreachable in its dataset declaration',
          'synthetic-unreachable', reach, str(getattr(d, 'reachability_reason', ''))[:120])
    check('T9b', 'VOIDCN INV-D02 is VIOLATED, not silently accepted (declared and evaluated)',
          ('VIOLATED', 'VIOLATED'), (declared, status), '; '.join(objects(viol)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', default='run')
    a = ap.parse_args()
    prod_before = vc and __import__('hashlib').sha256(open(PROD, 'rb').read()).hexdigest()
    for cid, what, expect, fn in CASES:
        h, db = base(cid.lower())
        c = sqlite3.connect(db)
        fn(c)
        c.commit()
        c.close()
        status, viol = evaluate(db)
        got = 'HOLDS' if status == 'HOLDS' else ('FAIL' if status == 'VIOLATED' else status)
        check(cid, what, expect, got, '; '.join(objects(viol)))
        if cid in KIND:
            sub = KIND[cid]
            blob = json.dumps(viol, default=str)
            check(cid + 'k', 'failure is named as: ' + sub, True, sub in blob)
        assert_production_untouched(h)
    app_refund_case()
    voidcn_case()
    prod_after = __import__('hashlib').sha256(open(PROD, 'rb').read()).hexdigest()
    check('P-00', 'production unchanged across the run', prod_before, prod_after)
    commit = subprocess.check_output(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
    dirty = subprocess.check_output(['git', '-C', WT, 'status', '--porcelain', '--',
                                     'verification/invariants', 'verification/datasets', 'app']).decode().strip()
    out = {'task': 'SR-2 / INV-D02 targeted verification', 'label': a.label, 'worktree_commit': commit,
           'code_tree_clean': dirty == '', 'code_tree_status': dirty,
           'finished': datetime.now().isoformat(timespec='seconds'),
           'production_sha256': prod_after, 'passed': sum(r['pass'] for r in results),
           'total': len(results), 'results': results}
    with open(os.path.join(HERE, 'sr2_%s.json' % a.label), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, default=str)
    print('SR2 %s: %d/%d' % (a.label, out['passed'], out['total']))


if __name__ == '__main__':
    main()
