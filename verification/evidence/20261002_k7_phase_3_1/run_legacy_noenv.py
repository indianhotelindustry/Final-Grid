# -*- coding: utf-8 -*-
"""Run an established suite (CF-10/CF-11, Phase 1, Phase 2a, Q06, retention, W-20) against the
application code of ONE worktree, WITHOUT the live ``.env``.

Derived from 20260930_adr011_preprod_gate/run_with_app.py. Differences: the live folder's ``.env``
is NOT loaded (no messaging or AI credential exists in the process); ``app`` AND ``verification``
both come from the worktree; the production database is only the read-only copy source
(``verification.config.PRODUCTION_DB`` is set before any suite module is imported).

    <python> run_legacy_noenv.py <worktree> [--system-mechanism NAME] script <path> [args...]
"""
import os
import runpy
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')
for k in ('ULTRAMSG_TOKEN', 'ULTRAMSG_INSTANCE', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS',
          'SMTP_FROM', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'FRONTDESK_WHATSAPP', 'DATABASE_URL',
          'WHATSAPP_API_KEY'):
    os.environ.pop(k, None)
assert os.environ.get('SECRET_KEY'), 'caller must export a throwaway SECRET_KEY'
os.chdir(WT)
sys.path.insert(0, WT)
import verification.config as vc                                        # noqa: E402
assert os.path.abspath(vc.__file__).startswith(os.path.join(WT, 'verification')), vc.__file__
vc.PRODUCTION_DB = PROD
import app                                                               # noqa: E402
assert os.path.abspath(app.__file__).startswith(os.path.join(WT, 'app')), app.__file__
print('[k7-legacy] app + verification from %s ; source (read-only) %s ; live .env NOT loaded' % (WT, PROD))
args = sys.argv[2:]
mechanism = None
if args[:1] == ['--system-mechanism']:
    mechanism, args = args[1], args[2:]
kind, target, rest = args[0], args[1], args[2:]
sys.argv = [target] + rest
from contextlib import nullcontext                                       # noqa: E402
if mechanism:
    from app.audit_actor import system_action                             # noqa: E402
with (system_action(mechanism) if mechanism else nullcontext()):
    if mechanism:
        print('[k7-legacy] undeclared no-operator calls run as SYSTEM %r' % mechanism)
    runpy.run_path(target, run_name='__main__')
