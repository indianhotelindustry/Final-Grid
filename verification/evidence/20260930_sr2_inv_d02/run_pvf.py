# -*- coding: utf-8 -*-
"""Run the PVF CLI with BOTH ``verification`` and ``app`` from this worktree.

The only thing pointed outside the worktree is the source database:
``verification.config.PRODUCTION_DB`` is set to the live production file,
which PVF opens read-only and copies with the SQLite backup API before any
evaluation. Evidence packs are written to this worktree's
``verification/evidence``. The live folder's ``instance/`` is never used as
an application root, so the live ``alert_memory.json`` is not touched.

    <main>\\venv\\Scripts\\python.exe run_pvf.py <pvf subcommand> [args...]
"""
import os
import runpy
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))
PROD = os.path.join(MAIN, 'instance', 'pms.db')

from dotenv import load_dotenv                                     # noqa: E402
load_dotenv(os.path.join(MAIN, '.env'), override=False)
os.chdir(WT)
sys.path.insert(0, WT)
import verification.config as vc                                   # noqa: E402
assert os.path.abspath(vc.__file__).startswith(os.path.join(WT, 'verification')), vc.__file__
vc.PRODUCTION_DB = PROD
import app                                                          # noqa: E402,F401
assert os.path.abspath(app.__file__).startswith(os.path.join(WT, 'app')), app.__file__
print('[sr2] app + verification from %s ; source (read-only) %s' % (WT, PROD))
sys.argv = ['verification'] + sys.argv[1:]
runpy.run_module('verification', run_name='__main__', alter_sys=True)
