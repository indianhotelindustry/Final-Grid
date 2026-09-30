# -*- coding: utf-8 -*-
"""Probe: does a SAVEPOINT-scoped financial write survive the OUTER rollback?

pysqlite (Python's sqlite3 in its default, legacy transaction mode) emits
BEGIN only before INSERT/UPDATE/DELETE. A ``session.begin_nested()`` issued
while no such statement has run yet sends SAVEPOINT with no transaction
open; SQLite then treats the savepoint as the outermost transaction, and
its RELEASE commits. Whatever was written inside it survives a later
rollback of the caller's "transaction".

Runs on a disposable copy made by verification.dbcopy; production is
opened read-only for hashing only.

    venv\\Scripts\\python.exe verification\\evidence\\20260930_cf10_completion\\probe_savepoint.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta, datetime

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
APP_ROOT = os.path.abspath(os.environ.get('CF10_APP_ROOT') or REPO)
sys.path.insert(0, REPO)
from verification.dbcopy import make_copy, assert_production_untouched   # noqa: E402
if APP_ROOT != REPO:
    sys.path.insert(0, APP_ROOT)

import subprocess                                                        # noqa: E402

h = make_copy(name='sp_probe.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + h.copy_path.replace(os.sep, '/')
os.environ['FLASK_ENV'] = 'production'

from app import create_app                                               # noqa: E402
from app import models as m                                              # noqa: E402
import app.cico_service as cico                                          # noqa: E402

app = create_app()
app.config.update(TESTING=True)
db = m.db
commit = subprocess.check_output(['git', '-C', APP_ROOT, 'rev-parse', 'HEAD']).decode().strip()


def new_in_house(tag):
    with app.app_context():
        bd = db.session.query(m.BusinessDate).first().current_date
        seed = db.session.query(m.Reservation).order_by(m.Reservation.id).first()
        room = db.session.query(m.Room).filter_by(status='Vacant').order_by(m.Room.id).first()
        r = m.Reservation(
            booking_reference='SPPROBE-%s' % tag, guest_id=seed.guest_id, room_id=room.id,
            room_type_id=seed.room_type_id, arrival_date=bd - timedelta(days=1),
            departure_date=bd, adults=1, children=0, status='CheckedIn', rate_per_night=1000,
            noshow_exempt=False, checkout_initiated=False, credit_amount=0,
            credit_settled_amount=0, cancellation_amount_refunded=0,
            cancellation_amount_forfeited=0, cancellation_amount_credit_voucher=0)
        db.session.add(r)
        room.status = 'Occupied'
        db.session.commit()
        return r.id


dirty = subprocess.check_output(['git', '-C', APP_ROOT, 'status', '--porcelain', '--', 'app']).decode().strip()
out = {'app_root': APP_ROOT, 'app_commit': commit, 'app_tree_clean': dirty == '',
       'started': datetime.now().isoformat(timespec='seconds'), 'cases': []}
with app.app_context():
    uid = db.session.query(m.User).order_by(m.User.id).first().id

for scenario in ('no_prior_dml', 'prior_dml'):
    rid = new_in_house(scenario)
    with app.app_context():
        res = db.session.get(m.Reservation, rid)
        if scenario == 'prior_dml':
            res.checkout_initiated = True
            db.session.flush()                  # an UPDATE -> pysqlite emits BEGIN
        cico.post_charge(res, 'late_checkout', 300.0, 'probe', user_id=uid)
        db.session.rollback()                   # the caller abandons its transaction
    with app.app_context():
        n_charge = db.session.query(m.ExtraCharge).filter_by(reservation_id=rid).count()
        n_audit = db.session.query(m.AuditLog).filter_by(
            entity_type='Reservation', entity_id=rid, action='auto_late_checkout_charge').count()
    case = {'scenario': scenario, 'charges_after_outer_rollback': n_charge,
            'reservation_audits_after_outer_rollback': n_audit,
            'expected': 0, 'pass': n_charge == 0 and n_audit == 0}
    out['cases'].append(case)
    print(case)

# Folio auto-creation (services.resolve_billing_folio, Q-1): reachable for a
# reservation whose folio A is missing, e.g. one inserted by raw SQL.
import app.services as svc                                               # noqa: E402
rid = new_in_house('folio')
with app.app_context():
    db.session.execute(db.text('DELETE FROM folios WHERE reservation_id = :r'), {'r': rid})
    db.session.commit()
with app.app_context():
    svc.resolve_billing_folio(rid, user_id=uid)
    db.session.rollback()
with app.app_context():
    n_folio = db.session.query(m.Folio).filter_by(reservation_id=rid).count()
    n_audit = db.session.query(m.AuditLog).filter_by(action='folio_auto_created').filter(
        m.AuditLog.after_state.isnot(None)).all()
    n_audit = sum(1 for a in n_audit if (a.after_state or {}).get('reservation_id') == rid)
case = {'scenario': 'folio_auto_create_no_prior_dml', 'folios_after_outer_rollback': n_folio,
        'folio_audits_after_outer_rollback': n_audit, 'expected': 0,
        'pass': n_folio == 0 and n_audit == 0}
out['cases'].append(case)
print(case)

out['production_sha256_after'] = assert_production_untouched(h)
out['verdict'] = 'PASS' if all(c['pass'] for c in out['cases']) else 'FAIL'
label = os.environ.get('CF10_RUN_LABEL', 'run')
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'probe_savepoint_%s.json' % label), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=2)
print('verdict', out['verdict'], 'prod', out['production_sha256_after'][:8], 'commit', commit[:7])
