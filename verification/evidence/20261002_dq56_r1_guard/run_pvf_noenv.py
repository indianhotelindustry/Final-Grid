# -*- coding: utf-8 -*-
"""Run the PVF CLI with BOTH ``verification`` and ``app`` from one worktree,
WITHOUT the live ``.env``.

Derived from ``20260930_sr2_inv_d02/run_pvf.py``. Difference: the live
folder's ``.env`` is not loaded, so no messaging (WhatsApp/SMTP) or external
AI credential exists in the process; ``SECRET_KEY`` / ``FLASK_ENV`` come from
the caller's environment (``run_regression.sh`` sets a throwaway key, shared
by the baseline and branch runs so environmental effects are symmetric).

The only path pointed outside the worktree is the source database:
``verification.config.PRODUCTION_DB`` is set to the live production file,
which PVF opens read-only and copies with the SQLite backup API before any
evaluation. Evidence packs are written into this worktree's
``verification/evidence`` and moved by the caller.

    <python> run_pvf_noenv.py <worktree> <pvf subcommand> [args...]
"""
import os
import runpy
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')

for k in ('ULTRAMSG_TOKEN', 'ULTRAMSG_INSTANCE', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER',
          'SMTP_PASS', 'SMTP_FROM', 'GEMINI_API_KEY', 'GEMINI_MODEL',
          'FRONTDESK_WHATSAPP', 'DATABASE_URL'):
    os.environ.pop(k, None)
assert os.environ.get('SECRET_KEY'), 'caller must export a throwaway SECRET_KEY'

os.chdir(WT)
sys.path.insert(0, WT)
import verification.config as vc                                   # noqa: E402
assert os.path.abspath(vc.__file__).startswith(os.path.join(WT, 'verification')), vc.__file__
vc.PRODUCTION_DB = PROD
import app                                                          # noqa: E402,F401
assert os.path.abspath(app.__file__).startswith(os.path.join(WT, 'app')), app.__file__
print('[dq56] app + verification from %s ; source (read-only) %s ; live .env NOT loaded' % (WT, PROD))
sys.argv = ['verification'] + sys.argv[2:]
runpy.run_module('verification', run_name='__main__', alter_sys=True)
