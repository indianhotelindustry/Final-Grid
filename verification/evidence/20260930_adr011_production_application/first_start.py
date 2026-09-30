# -*- coding: utf-8 -*-
"""ADR-011 controlled first application start (production, live folder).

Boots the application exactly as its launchers do (``create_app()`` with the
production ``.env`` of the live folder; nothing overridden), which applies
pending migrations. Records the database target, the scheduler jobs, then
stops the scheduler. No web server is started; no request is served here.

    cd <live folder> && venv\\Scripts\\python.exe <this file>
"""
import json
import os
import sys

LIVE = os.getcwd()
assert os.path.isfile(os.path.join(LIVE, 'instance', 'pms.db')), LIVE
assert 'DATABASE_URL' not in os.environ, 'DATABASE_URL must come from the production .env only'
sys.path.insert(0, LIVE)

from app import create_app                                     # noqa: E402

app = create_app()
from app.services import scheduler                             # noqa: E402

jobs = sorted((j.id, str(j.trigger)) for j in scheduler.get_jobs())
out = {'app_file': os.path.abspath(sys.modules['app'].__file__),
       'database_uri': app.config['SQLALCHEMY_DATABASE_URI'],
       'env_mode': os.getenv('FLASK_ENV') or os.getenv('APP_ENV'),
       'scheduler_running': scheduler.running,
       'jobs': jobs,
       'night_audit_job': scheduler.get_job('night_audit_job') is not None}
if scheduler.running:
    scheduler.shutdown(wait=False)
print('FIRST_START ' + json.dumps(out))
