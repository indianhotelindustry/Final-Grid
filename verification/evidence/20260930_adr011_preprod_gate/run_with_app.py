# -*- coding: utf-8 -*-
"""Run an existing verification suite of the main repository against the
application code of a chosen checkout (``--app-root``; default: this one).

Copied from 20260930_adr011_implementation/run_with_branch_app.py (unchanged
there) and extended with ``--app-root`` and ``--source``. ``--source`` points
``verification.config.PRODUCTION_DB`` at another database (the restored copy)
before any other verification module is imported - test process only; the
verification package is not modified.

    <main>\\venv\\Scripts\\python.exe run_with_branch_app.py script <path-to-script.py> [args...]
    <main>\\venv\\Scripts\\python.exe run_with_branch_app.py module verification <args...>

``app`` is imported from this worktree before the suite starts, so the
suite's own ``sys.path.insert(0, <main repo>)`` still resolves
``verification`` (production path, copy mechanism, masters) from the main
repository while ``app`` stays the branch's. The main repository's ``.env``
is loaded into this process only (never copied), as the application itself
does when run from the main repository.
"""
import os
import runpy
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
_argv = sys.argv[1:]
if _argv[:1] == ['--app-root']:
    WT, _argv = os.path.abspath(_argv[1]), _argv[2:]
_source = None
if _argv[:1] == ['--source']:
    _source, _argv = os.path.abspath(_argv[1]), _argv[2:]
sys.argv = [sys.argv[0]] + _argv
MAIN = os.path.dirname(os.path.abspath(subprocess.check_output(
    ['git', '-C', WT, 'rev-parse', '--git-common-dir']).decode().strip()))

from dotenv import load_dotenv                                     # noqa: E402
load_dotenv(os.path.join(MAIN, '.env'), override=False)

sys.path.insert(0, WT)
import app                                                          # noqa: E402,F401
assert os.path.abspath(app.__file__).startswith(os.path.join(WT, 'app')), app.__file__
sys.path.remove(WT)
sys.path.insert(0, MAIN)
print('[branch-app] app from %s ; verification from %s' % (os.path.dirname(app.__file__), MAIN))
if _source:
    import verification.config as _vc
    _vc.PRODUCTION_DB = _source
    print('[branch-app] verification source database: %s' % _source)

args = sys.argv[1:]
mechanism = None
if args[0] == '--system-mechanism':
    # The suite's own no-operator calls (e.g. run_night_audit(app) standing
    # in for the scheduler) are declared as a SYSTEM action of this name.
    # Rows with a user or a logged-in operator stay HUMAN: the resolver
    # prefers a human actor over any declared mechanism.
    mechanism, args = args[1], args[2:]
kind, target, rest = args[0], args[1], args[2:]
sys.argv = [target] + rest
from contextlib import nullcontext                                  # noqa: E402
if mechanism:
    from app.audit_actor import system_action                       # branch code only
with (system_action(mechanism) if mechanism else nullcontext()):
    if mechanism:
        print('[branch-app] undeclared no-operator calls run as SYSTEM %r' % mechanism)
    if kind == 'script':
        runpy.run_path(target, run_name='__main__')
    else:
        runpy.run_module(target, run_name='__main__', alter_sys=True)
