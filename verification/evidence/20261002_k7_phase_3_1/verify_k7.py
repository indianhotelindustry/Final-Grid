# -*- coding: utf-8 -*-
"""K-7 Phase 3.1 harness (frozen directive FG-P3-1-K7-DIRECTIVE-01, section 7).

    <live venv python> verify_k7.py --worktree <wt> --role base|branch --label <L> [--only S-10,V-3]

Method: one disposable copy of production per scenario (verification.dbcopy.make_copy:
production opened read-only, SQLite backup API), one process per scenario
(k7_child.py), the clock frozen with the proven freezer at an instant whose date
differs from the business date on the copy, expectations read from
expectations.json (registered and committed before the first run), invariants
evaluated in fresh processes. ``verification`` and ``app`` both come from --worktree.

The live ``.env`` is NOT loaded; messaging and AI variables are removed; a throwaway
SECRET_KEY is required from the caller. Run a verbatim copy of this pack from a
scratch directory so committed evidence is never overwritten (results are written
next to this file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--worktree', required=True)
ap.add_argument('--role', required=True, choices=['base', 'branch'])
ap.add_argument('--label', required=True)
ap.add_argument('--only', default='')
ARGS = ap.parse_args()

WT = os.path.abspath(ARGS.worktree)
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')
assert os.path.basename(MAIN) == 'SukoonPMS', MAIN

STRIP = ('ULTRAMSG_TOKEN', 'ULTRAMSG_INSTANCE', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS',
         'SMTP_FROM', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'FRONTDESK_WHATSAPP', 'DATABASE_URL',
         'WHATSAPP_API_KEY')
for k in STRIP:
    os.environ.pop(k, None)
assert os.environ.get('SECRET_KEY'), 'export a throwaway SECRET_KEY'
CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', FLASK_ENV='production')

sys.path.insert(0, WT)
import verification.config as vc                                           # noqa: E402
assert os.path.abspath(vc.__file__).startswith(os.path.join(WT, 'verification')), vc.__file__
vc.PRODUCTION_DB = PROD
from verification.dbcopy import make_copy, assert_production_untouched      # noqa: E402

EXP = json.load(open(os.path.join(HERE, 'expectations.json'), encoding='utf-8'))
CLOCKS = {'F-LAG': EXP['constants']['F_LAG_clock'], 'F-CLOSED': EXP['constants']['F_LAG_clock'],
          'F-CANCEL': EXP['constants']['F_LAG_clock'], 'F-VOUCHER': EXP['constants']['F_LAG_clock'],
          'F-STAY': EXP['constants']['F_LAG_clock'], 'F-NOROW': EXP['constants']['F_LAG_clock'],
          'F-AHEAD': EXP['constants']['F_AHEAD']['clock'], 'F-UTC': EXP['constants']['F_UTC_clock']}
results = []


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def inv(db, ids):
    """Invariant statuses on *db*, evaluated in a fresh process from WT."""
    code = ('import os,sys,json; sys.path.insert(0,%r); os.chdir(%r); '
            'from verification.invariants import engine; '
            'rs=engine.evaluate_database(%r, mode="ENTIRE_DATABASE", business_date="", ids=%r); '
            'print("INVJSON "+json.dumps({r.invariant_id:r.status for r in rs}))' % (WT, WT, db, list(ids)))
    p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=CHILD_ENV)
    line = [l for l in p.stdout.splitlines() if l.startswith('INVJSON ')]
    return json.loads(line[0][8:]) if line else {'ERROR': (p.stdout + p.stderr)[-400:]}


def prep_ahead(path):
    c = sqlite3.connect(path)
    c.execute('UPDATE business_date SET "current_date" = ?', (EXP['constants']['F_AHEAD']['business_date'],))
    c.commit(); c.close()


def prep_ddl2(path):
    t = open(os.path.join(WT, 'app', '__init__.py'), encoding='utf-8').read()
    ddl1 = re.search(r"\('credit_vouchers',\s*\"\"\"(.*?)\"\"\"\)", t, re.S).group(1)
    ddl2 = re.search(r"\('credit_voucher_redemptions',\s*\"\"\"(.*?)\"\"\"\)", t, re.S).group(1)
    c = sqlite3.connect(path)
    assert c.execute('SELECT COUNT(*) FROM credit_vouchers').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM credit_voucher_redemptions').fetchone()[0] == 0
    c.executescript('DROP TABLE credit_voucher_redemptions; DROP TABLE credit_vouchers;' + ddl1 + ';' + ddl2 + ';')
    c.commit(); c.close()


def check(case, key, expect, got):
    ok = expect == got
    results.append({'case': case, 'assert': key, 'expect': expect, 'got': got, 'pass': ok})
    print('%-4s %-14s %-26s expect=%-30s got=%s' % ('OK' if ok else 'FAIL', case, key, json.dumps(expect), json.dumps(got)))


def run_scenario(name, spec):
    fixture = spec['fixture']
    safe = re.sub(r'[^A-Za-z0-9]', '', name).lower()
    h = make_copy(name='k7_%s_%s.db' % (ARGS.role, safe))
    pre = h.copy_path + '.pre'
    if name == 'N-3-AHEAD':
        prep_ahead(h.copy_path)
    if name == 'DDL-2':
        prep_ddl2(h.copy_path)
    p = subprocess.run([sys.executable, os.path.join(HERE, 'k7_child.py'), WT, h.copy_path, name,
                        CLOCKS[fixture], pre], capture_output=True, text=True, env=CHILD_ENV)
    line = [l for l in p.stdout.splitlines() if l.startswith('K7JSON ')]
    if not line:
        obs = {'child_error': (p.stdout + p.stderr)[-1500:]}
        print('CHILD FAILED', name, '\n', obs['child_error'])
    else:
        obs = json.loads(line[0][7:])
    # invariants evaluated by the parent
    if name in ('N-3-AHEAD',) and 'child_error' not in obs:
        after = inv(h.copy_path, ['INV-B01', 'INV-B03'])
        before = inv(pre, ['INV-B01', 'INV-B03'])
        obs['inv_b01_after'] = after.get('INV-B01')
        obs['inv_b03_unchanged'] = before.get('INV-B03') == after.get('INV-B03')
        obs['inv_b03_before_after'] = [before.get('INV-B03'), after.get('INV-B03')]
    if name in ('S-ALL', 'S-ALL-UTC') and 'child_error' not in obs:
        obs['inv_b04_before'] = inv(pre, ['INV-B04']).get('INV-B04')
        obs['inv_b04_after'] = inv(h.copy_path, ['INV-B04']).get('INV-B04')
    # flatten per-op observations for S-ALL so row dates are visible in the JSON
    asserts = dict(EXP['common_asserts_every_scenario'])
    asserts.update(spec['asserts'])
    for key, exp in asserts.items():
        check(name, key, exp[ARGS.role], obs.get(key, '<missing>'))
    results[-1]['obs_digest'] = None
    all_obs[name] = obs
    for suffix in ('', '-journal'):
        pass
    assert_production_untouched(h)
    return obs


all_obs = {}
only = [s for s in ARGS.only.split(',') if s]
prod_before = sha(PROD)
print('[k7] role %s worktree %s label %s production %s' % (ARGS.role, WT, ARGS.label, prod_before[:16]))
commit = subprocess.check_output(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
for name, spec in EXP['scenarios'].items():
    if only and name not in only:
        continue
    run_scenario(name, spec)
prod_after = sha(PROD)
check('PROD', 'production pms.db unchanged', prod_before, prod_after)
dirty = subprocess.check_output(['git', '-C', WT, 'status', '--porcelain', '--', 'app', 'verification/invariants']).decode().strip()
out = {'task': 'K-7 Phase 3.1 harness', 'role': ARGS.role, 'label': ARGS.label, 'worktree': WT,
       'worktree_commit': commit, 'code_tree_status': dirty, 'production_sha256_before': prod_before,
       'production_sha256_after': prod_after, 'passed': sum(r['pass'] for r in results),
       'total': len(results), 'results': results, 'observations': all_obs}
with open(os.path.join(HERE, 'k7_%s.json' % ARGS.label), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=2, default=str)
print('K7 %s: %d/%d assertions as registered' % (ARGS.label, out['passed'], out['total']))
