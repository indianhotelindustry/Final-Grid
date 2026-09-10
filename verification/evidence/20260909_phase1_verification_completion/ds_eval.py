# -*- coding: utf-8 -*-
"""Evaluate the six registered D6 datasets against their own declarations
(the existing `ds-run` path) and record, per dataset, what the directive
asks for: setup, writers exercised, folio result, audit result,
reconciliation result, invariant result, verdict and evidence.

    venv\\Scripts\\python.exe ds_eval.py

Every dataset is materialised by the registered builder from a disposable
copy of production; production is only ever read. The built copy is
inspected read-only after evaluation and then discarded, as `ds-run` does.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
HERE = os.path.dirname(os.path.abspath(__file__))

from verification.datasets import builder, evaluate, registry          # noqa: E402
from verification.dbcopy import production_fingerprint                 # noqa: E402
from verification.config import PRODUCTION_DB                          # noqa: E402


def inspect(db_path):
    con = sqlite3.connect('file:%s?mode=ro' % db_path.replace('\\', '/'), uri=True)
    q = con.execute
    out = {}
    out['payments'] = q('select count(*) from payments').fetchone()[0]
    out['extra_charges'] = q('select count(*) from extra_charges').fetchone()[0]
    out['null_folio_payments'] = [r[0] for r in q('select id from payments where folio_id is null order by id')]
    out['null_folio_charges'] = [r[0] for r in q('select id from extra_charges where folio_id is null order by id')]
    out['audit_logs'] = q('select count(*) from audit_logs').fetchone()[0]
    out['audit_actions'] = dict(q('select action, count(*) from audit_logs group by action').fetchall())
    # reconciliation: reservation view vs folio view of charges (INV-A03 shape)
    res_view = q('select coalesce(sum(amount),0) from extra_charges').fetchone()[0]
    folio_view = q('select coalesce(sum(e.amount),0) from extra_charges e join folios f on f.id = e.folio_id').fetchone()[0]
    unattributed = q('select coalesce(sum(amount),0) from extra_charges where folio_id is null').fetchone()[0]
    misrouted = q('select count(*) from extra_charges e join folios f on f.id = e.folio_id '
                  'where f.reservation_id != e.reservation_id').fetchone()[0]
    mis_pay = q('select count(*) from payments p join folios f on f.id = p.folio_id '
                'where f.reservation_id != p.reservation_id').fetchone()[0]
    out['reconciliation'] = {'reservation_view': round(float(res_view), 2),
                             'folio_view': round(float(folio_view), 2),
                             'unattributed': round(float(unattributed), 2),
                             'views_agree': abs(float(res_view) - float(folio_view) - float(unattributed)) < 0.01,
                             'misrouted_charges': misrouted, 'misrouted_payments': mis_pay}
    out['business_date'] = q('select current_date from business_date').fetchone()[0] \
        if q("select name from sqlite_master where name='business_date'").fetchone() else None
    con.close()
    return out


def main():
    before, _ = production_fingerprint(PRODUCTION_DB)
    datasets = registry.all_datasets()
    print('registered datasets: %s' % [d.key for d in datasets])
    report = []
    for d in datasets:
        t0 = time.perf_counter()
        print('=' * 100)
        print('[ds] %s - %s' % (d.key, d.title))
        m = builder.build(d)
        try:
            res = evaluate.evaluate(d, m)
            facts = inspect(m.db_path) if m.ok else {}
        finally:
            builder.discard(m)
        outcomes = [{'element': o.element, 'target': o.target, 'expected': o.expected,
                     'observed': o.observed, 'status': o.status, 'detail': o.detail}
                    for o in res.outcomes]
        inv = {o['target']: (o['expected'], o['observed'], o['status'])
               for o in outcomes if o['element'] == 'invariants'}
        par = {o['target']: (o['expected'], o['observed'], o['status'])
               for o in outcomes if o['element'] == 'parity'}
        events = [{'date': e.date, 'description': e.description, 'tables': list(e.tables), 'amount': e.amount}
                  for e in getattr(d, 'events', ()) or ()]
        entry = {
            'key': d.key, 'title': d.title, 'description': getattr(d, 'description', ''),
            'purpose': getattr(d, 'purpose', ''), 'verdict': res.verdict, 'error': res.error,
            'met': len(res.met), 'unmet': len(res.unmet), 'not_run': len(res.not_run),
            'layers_run': list(res.layers_run),
            'activated_invariants': list(res.activated_invariants),
            'still_vacuous': list(res.still_vacuous),
            'materialisation': {'rows_inserted': m.rows_inserted, 'rows_removed': m.rows_removed,
                                'tables_touched': list(m.tables_touched),
                                'business_date': m.business_date,
                                'production_unchanged': m.production_unchanged},
            'events': events, 'facts': facts, 'invariants': inv, 'parity': par,
            'unmet_detail': [o for o in outcomes if o['status'] == 'UNMET'],
            'outcomes': outcomes, 'duration_s': round(time.perf_counter() - t0, 1),
        }
        report.append(entry)
        print('  verdict=%s met=%d unmet=%d not_run=%d  A02=%s A03=%s Q14=%s  null_folio=%s/%s  recon=%s'
              % (res.verdict, len(res.met), len(res.unmet), len(res.not_run),
                 inv.get('INV-A02'), inv.get('INV-A03'), par.get('Q14'),
                 facts.get('null_folio_payments'), facts.get('null_folio_charges'),
                 facts.get('reconciliation')))
        for o in entry['unmet_detail']:
            print('  UNMET %s %s expected=%s observed=%s %s' % (o['element'], o['target'], o['expected'], o['observed'], o['detail'][:120]))
    after, _ = production_fingerprint(PRODUCTION_DB)
    payload = {'production_sha256_before': before, 'production_sha256_after': after,
               'production_unchanged': before == after,
               'datasets': report,
               'all_pass': all(e['verdict'] == 'PASS' for e in report)}
    with open(os.path.join(HERE, 'datasets.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
    print('=' * 100)
    print('ALL PASS: %s   production unchanged: %s' % (payload['all_pass'], before == after))
    print('datasets.json written')
    return 0 if payload['all_pass'] and before == after else 1


if __name__ == '__main__':
    sys.exit(main())
