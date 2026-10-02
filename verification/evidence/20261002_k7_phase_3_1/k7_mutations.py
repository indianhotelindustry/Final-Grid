# -*- coding: utf-8 -*-
"""N-6 mutation proof (frozen directive section 7.3): revert each K-7 change on a scratch worktree
of the GREEN commit and show that the matching harness scenarios turn RED.

    python k7_mutations.py <mutation worktree (detached at the tested commit)> <out json>

Each mutation edits ONE spot in the worktree's app/ (EOL-preserving, anchor-asserted), runs only the
named scenarios with verify_k7.py (role=branch, i.e. the GREEN expectations), expects at least one
assertion to FAIL, then restores app/ with git. The mutation worktree is disposable.
"""
import json
import os
import re
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
OUT = sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS\venv\Scripts\python.exe"

M = [
 ('M01 W-08/W-09 correction pair from the calendar', 'app/services.py',
  "    today = get_business_date()       # K-7 / BR-2: one business date for the whole pair\n\n    # R-3 / Q-2 — the pair inherits",
  "    today = date.today()\n\n    # R-3 / Q-2 — the pair inherits", ['S-08-09', 'S-08-09-route']),
 ('M02 W-22/W-23 charge correction from the calendar', 'app/services.py',
  "    today = get_business_date()       # K-7 / BR-2: one business date for the whole pair\n    desc_prefix = '[REVERSAL] '",
  "    today = date.today()\n    desc_prefix = '[REVERSAL] '", ['S-22-23']),
 ('M03 W-10 refund from the calendar', 'app/services.py',
  "        _posting_date = get_business_date()\n        # R-4 / CD-3",
  "        _posting_date = date.today()\n        # R-4 / CD-3", ['S-10']),
 ('M04 voucher issue date and expiry anchor from the calendar', 'app/services.py',
  "    issue_date = issue_date or get_business_date()\n",
  "    issue_date = date.today()\n", ['S-VI', 'DDL-2']),
 ('M05 W-11 redemption payment from the calendar', 'app/services.py',
  "            payment_date     = _bd,\n", "            payment_date     = date.today(),\n", ['S-11']),
 ('M06 voucher status derivation from the calendar (services.py:2009 site)', 'app/services.py',
  "        if voucher.expiry_date < (as_of or get_business_date()):\n",
  "        if voucher.expiry_date < date.today():\n", ['V-1', 'V-3', 'V-4']),
 ('M07 repeated redemption expiry test from the calendar (services.py:2077 site)', 'app/services.py',
  "    if voucher.expiry_date is not None and voucher.expiry_date < _bd:\n",
  "    if voucher.expiry_date is not None and voucher.expiry_date < date.today():\n", ['V-3']),
 ('M08 W-17 checkout extra from the calendar', 'app/routes.py',
  "                    charge_date=get_business_date()                   # K-7 W-17\n",
  "                    charge_date=date.today()\n", ['S-17', 'S-TL']),
 ('M09 W-20 overstay row from the wall clock', 'app/routes.py',
  "        charge_date=get_business_date()                               # K-7 W-20: row date only; billing hours stay on physical time\n",
  "        charge_date=now.date()\n", ['S-20', 'S-TL']),
 ('M10 model defaults back to date.today', 'app/models.py',
  "    charge_date = db.Column(db.Date, default=_business_date_at_insert)",
  "    charge_date = db.Column(db.Date, default=date.today)", ['D-1']),
 ('M10b Payment default back to date.today', 'app/models.py',
  "    payment_date = db.Column(db.Date, default=_business_date_at_insert)",
  "    payment_date = db.Column(db.Date, default=date.today)", ['D-1', 'D-2']),
 ('M10c CreditVoucher default back to date.today', 'app/models.py',
  "nullable=False, default=_business_date_at_insert)", "nullable=False, default=date.today)", ['D-1']),
 ('M11 get_business_date falls back to the calendar', 'app/services.py',
  "    if bd is None or bd.current_date is None:\n        _bd_log.error('Business date unavailable: no business_date row (or NULL '\n                      'current_date); refusing to substitute the calendar date')\n        raise BusinessDateUnavailable(\n            'business date unavailable: no business_date row')\n    return bd.current_date\n",
  "    return bd.current_date if bd else date.today()\n", ['F-1', 'F-2-corr', 'F-2-refund', 'F-2-redeem']),
 ('M12 run_night_audit stays silent', 'app/services.py',
  "                _na_logger.error('Business date unavailable: night audit not run '\n                                 '(no business_date row); the calendar date is not substituted')\n",
  "", ['F-3d']),
 ('M13 occupancy label falls back to the calendar', 'app/occupancy_engine.py',
  "                     type(exc).__name__, exc)\n    return None\n",
  "                     type(exc).__name__, exc)\n    return _date.today()\n", ['F-3a']),
 ('M14 KPI governance block defaults to the calendar', 'app/kpi_command_center.py',
  "    today = ctx.get('business_date')\n    if not today:\n",
  "    today = ctx.get('business_date') or date.today()\n    if False:\n", ['F-3b']),
 ('M15 night-audit view falls back to the calendar', 'app/routes.py',
  "    bd = get_business_date()          # K-7 / BR-5: fails closed (logged), never the calendar\n",
  "    bd = business_date.current_date if business_date else date.today()\n", ['F-3c']),
]


def apply(path, old, new):
    p = os.path.join(WT, path)
    b = open(p, 'rb').read().decode('utf-8')
    if '\r\n' in b:
        old = old.replace('\n', '\r\n'); new = new.replace('\n', '\r\n')
    n = b.count(old)
    if n != 1:
        raise SystemExit('anchor matched %d times in %s: %r' % (n, path, old[:70]))
    open(p, 'wb').write(b.replace(old, new).encode('utf-8'))


CHECK_ONLY = len(sys.argv) > 3 and sys.argv[3] == '--check'
res = []
for name, path, old, new, scen in M:
    if CHECK_ONLY:
        subprocess.run(['git', '-C', WT, 'checkout', '--', 'app'], check=True)
        apply(path, old, new)
        print('anchor ok:', name)
        continue
    subprocess.run(['git', '-C', WT, 'checkout', '--', 'app'], check=True)
    apply(path, old, new)
    p = subprocess.run([PY, os.path.join(HERE, 'verify_k7.py'), '--worktree', WT, '--role', 'branch',
                        '--label', 'mut_' + name.split()[0], '--only', ','.join(scen)],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    fails = [l for l in p.stdout.splitlines() if l.startswith('FAIL')]
    if 'assertions as registered' not in p.stdout:
        raise SystemExit('harness did not complete for %s: %s' % (name, (p.stdout + p.stderr)[-800:]))
    child_err = 'CHILD FAILED' in p.stdout
    r = {'mutation': name, 'file': path, 'scenarios': scen, 'turned_red': bool(fails), 'failed_assertions': len(fails),
         'sample': [re.sub(r'\s+', ' ', f)[:150] for f in fails[:3]], 'child_error': child_err}
    res.append(r)
    print('%-3s %-70s failed=%d %s' % ('RED' if fails else 'NOT-RED', name[:70], len(fails), 'CHILD-ERROR' if child_err else ''))
subprocess.run(['git', '-C', WT, 'checkout', '--', 'app'], check=True)
if CHECK_ONLY:
    sys.exit(0)
json.dump({'worktree': WT, 'results': res, 'all_turned_red': all(r['turned_red'] for r in res)},
          open(OUT, 'w', encoding='utf-8'), indent=2)
print('N-6: %d/%d mutations turned the matching scenarios RED' % (sum(r['turned_red'] for r in res), len(res)))
