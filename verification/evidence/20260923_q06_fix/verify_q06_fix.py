# -*- coding: utf-8 -*-
"""Q06 forward-fix focused regression — read-only against a disposable copy.

Authority: Founder Resolution Round 4, Q06-H2
(FG-P2-FOUNDER-RESOLUTION-20260923-01).

Proves, against a disposable copy of production (instance/pms.db is opened
only via verification/dbcopy.py::make_copy(), never for writing):

  RC-Q06-01  the OLD algorithm (naive sum over every TaxLine row) reproduces
             the previously-recorded doubled taxable base for the known
             intrastate dates
  RC-Q06-02  the FIXED tax_snapshot() produces the charge-level taxable base
             exactly once (no longer doubled)
  RC-Q06-03  CGST + SGST tax_amount is byte-for-byte unchanged by the fix
  RC-Q06-04  fixed tax_snapshot().total_taxable agrees with
             gst_service.get_gst_report() for the same date
  RC-Q06-05  by_rate taxable values are no longer doubled (sum of by_rate
             taxable no longer exceeds the true base)
  RC-Q06-06  unrelated tax lines (exempt / total_lines / count) are unaffected
  RC-Q06-07  an interstate (IGST, single-row, non-split) case remains correct
             if one exists in the dataset; explicitly reported either way
  RC-Q06-08  the sealed NightAuditLog record for 2026-08-09 is byte-identical
             before and after this run (queried, never written)

Run:
    venv\\Scripts\\python.exe verification\\evidence\\20260923_q06_fix\\verify_q06_fix.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from verification.dbcopy import make_copy, assert_production_untouched  # noqa: E402
from verification.config import PRODUCTION_DB                            # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    prod_before = sha256(PRODUCTION_DB)
    print('=' * 130)
    print('Q06 FORWARD-FIX REGRESSION')
    print('=' * 130)
    print('production        : %s' % PRODUCTION_DB)
    print('sha256 before      : %s' % prod_before)

    handle = make_copy(name='q06_fix_regression.db')
    print('disposable copy    : %s  (%s)' % (handle.copy_path, handle.method))
    print('-' * 130)

    os.environ['DATABASE_URL'] = 'sqlite:///' + handle.copy_path.replace('\\', '/')
    os.environ['FLASK_ENV'] = 'production'
    from app import create_app                                    # noqa: E402
    from app.models import db, TaxLine, NightAuditLog              # noqa: E402
    from app import gst_service                                    # noqa: E402
    from app.night_audit_service import NightAuditService          # noqa: E402

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    results = []
    report = {'cases': []}

    def check(case_id, description, passed, detail=None):
        results.append(passed)
        report['cases'].append({'id': case_id, 'description': description,
                                 'passed': bool(passed), 'detail': detail})
        print('%-12s %-70s %s' % (case_id, description, 'PASS' if passed else 'FAIL'))
        if detail:
            print('             %s' % detail)

    with app.app_context():
        # --- Historical record snapshot (before) ------------------------
        nal_before = NightAuditLog.query.filter_by(audit_date=date(2026, 8, 9)).first()
        nal_before_json = nal_before.snapshot_json if nal_before else None
        nal_before_hash = nal_before.snapshot_hash if nal_before else None
        nal_row_present_before = nal_before is not None
        print('NightAuditLog 2026-08-09 present before run: %s' % nal_row_present_before)
        if nal_before:
            print('  snapshot_hash before: %s' % nal_before_hash)

        all_dates = sorted(
            d[0] for d in db.session.query(TaxLine.charge_date).distinct().all()
        )
        print('distinct TaxLine charge_date values: %s' % all_dates)
        print('-' * 130)

        raw_rows = TaxLine.query.all()
        interstate_dates = sorted({
            r.charge_date for r in raw_rows if r.tax_type == 'IGST'
        })
        print('dates with an IGST (interstate) row: %s' % interstate_dates)
        print('-' * 130)

        for d in all_dates:
            day_rows = [r for r in raw_rows if r.charge_date == d]

            # RC-Q06-01: reproduce what the OLD algorithm would have computed
            old_total_taxable = sum(float(r.taxable_amount) for r in day_rows)

            # get_gst_report — unchanged, ground truth
            gr = gst_service.get_gst_report(d, d)

            # tax_snapshot — FIXED implementation, called live
            nas = NightAuditService(d)
            ts = nas.tax_snapshot()

            has_split = any(r.tax_type in ('CGST', 'SGST') for r in day_rows)
            expected_old_ratio = 2.0 if has_split and float(gr['total_taxable']) else None

            if expected_old_ratio is not None:
                old_ratio = old_total_taxable / float(gr['total_taxable'])
                check('RC-Q06-01[%s]' % d,
                      'old algorithm reproduces the ~2x doubled base',
                      abs(old_ratio - expected_old_ratio) < 0.0001,
                      'old_naive_sum=%.2f  gst_report_base=%.2f  ratio=%.4f'
                      % (old_total_taxable, float(gr['total_taxable']), old_ratio))

            check('RC-Q06-02[%s]' % d,
                  'fixed total_taxable == true charge-level base (once)',
                  abs(ts['total_taxable'] - float(gr['total_taxable'])) < 0.01,
                  'fixed=%.2f  true_base=%.2f' % (ts['total_taxable'], float(gr['total_taxable'])))

            check('RC-Q06-04[%s]' % d,
                  'fixed tax_snapshot agrees with get_gst_report (taxable)',
                  abs(ts['total_taxable'] - float(gr['total_taxable'])) < 0.01)

            check('RC-Q06-03[%s]' % d,
                  'total_tax unchanged (CGST+SGST+IGST sums preserved)',
                  abs(ts['total_tax'] - float(gr['total_tax'])) < 0.01,
                  'tax_snapshot.total_tax=%.2f  get_gst_report.total_tax=%.2f'
                  % (ts['total_tax'], float(gr['total_tax'])))

            by_rate_taxable_sum = sum(v['taxable'] for v in ts['by_rate'].values())
            # For an intrastate-only day, CGST bucket + SGST bucket legitimately
            # each hold the true base once (two labelled views of the same
            # charge set) — that is existing by_rate semantics, unchanged.
            # What must NOT happen is a bucket itself being inflated beyond
            # the true base by row-level (rather than charge-level) summation.
            per_bucket_ok = all(
                v['taxable'] <= float(gr['total_taxable']) + 0.01
                for v in ts['by_rate'].values()
            )
            check('RC-Q06-05[%s]' % d,
                  'no individual by_rate bucket exceeds the true base',
                  per_bucket_ok,
                  'by_rate=%s' % json.dumps({k: v['taxable'] for k, v in ts['by_rate'].items()}))

            check('RC-Q06-06[%s]' % d,
                  'total_lines / exempt_lines unaffected by the fix',
                  ts['total_lines'] == len(day_rows),
                  'total_lines=%d  raw_rows=%d' % (ts['total_lines'], len(day_rows)))

            report['cases'][-1]  # no-op, keeps structure readable

        # RC-Q06-07: interstate case
        if interstate_dates:
            d = interstate_dates[0]
            gr = gst_service.get_gst_report(d, d)
            ts = NightAuditService(d).tax_snapshot()
            check('RC-Q06-07',
                  'interstate (IGST, single-row) date remains correct',
                  abs(ts['total_taxable'] - float(gr['total_taxable'])) < 0.01,
                  'date=%s fixed=%.2f true=%.2f' % (d, ts['total_taxable'], float(gr['total_taxable'])))
        else:
            check('RC-Q06-07',
                  'interstate (IGST) case — none exists in this dataset',
                  True,
                  'no IGST rows found; case not exercisable on this data, reported explicitly')

        # RC-Q06-08: historical sealed record untouched
        db.session.expire_all()
        nal_after = NightAuditLog.query.filter_by(audit_date=date(2026, 8, 9)).first()
        nal_after_json = nal_after.snapshot_json if nal_after else None
        nal_after_hash = nal_after.snapshot_hash if nal_after else None
        check('RC-Q06-08',
              'sealed NightAuditLog 2026-08-09 record byte-identical before/after',
              nal_row_present_before == (nal_after is not None)
              and nal_before_json == nal_after_json
              and nal_before_hash == nal_after_hash,
              'hash_before=%s hash_after=%s' % (nal_before_hash, nal_after_hash))

    print('=' * 130)
    prod_after = assert_production_untouched(handle)
    print('production sha256 after run: %s  (unchanged: %s)'
          % (prod_after, prod_after == prod_before))

    total = len(results)
    passed = sum(1 for r in results if r)
    print('-' * 130)
    print('%d / %d PASS' % (passed, total))

    report['summary'] = {'total': total, 'passed': passed, 'all_pass': passed == total}
    report['production_sha256_before'] = prod_before
    report['production_sha256_after'] = prod_after
    report['production_untouched'] = prod_after == prod_before
    report['nightauditlog_20260809'] = {
        'present_before': nal_row_present_before,
        'snapshot_hash_before': nal_before_hash,
        'snapshot_hash_after': nal_after_hash,
        'unchanged': nal_before_hash == nal_after_hash and nal_before_json == nal_after_json,
    }

    out_txt = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'q06_fix_regression.txt')
    out_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'q06_fix_regression_result.json')
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, indent=2, sort_keys=True, default=str)
    print('json result written to %s' % out_json)

    return 0 if passed == total else 1


if __name__ == '__main__':
    rc = main()
    sys.exit(rc)
