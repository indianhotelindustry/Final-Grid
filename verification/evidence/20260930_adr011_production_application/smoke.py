# -*- coding: utf-8 -*-
"""ADR-011 minimum production smoke verification (live folder, read-only requests).

Second application start (migration 10.0.0 must be a no-op), then GET requests
to public, read-only endpoints through Flask's test client. No login, no POST.
The caller compares the production SHA-256 before and after.
"""
import json
import os
import sys

LIVE = os.getcwd()
assert 'DATABASE_URL' not in os.environ
sys.path.insert(0, LIVE)
from app import create_app                                     # noqa: E402

app = create_app()
from app.services import scheduler                             # noqa: E402

c = app.test_client()
out = {'night_audit_job': scheduler.get_job('night_audit_job') is not None}
for path in ('/api/health', '/auth/login'):
    r = c.get(path)
    out[path] = {'status': r.status_code, 'bytes': len(r.data),
                 'json': (r.get_json(silent=True) if r.is_json else None)}
r = c.get('/dashboard')                          # protected: must redirect to login
out['/dashboard (unauthenticated)'] = {'status': r.status_code, 'location': r.headers.get('Location')}
if scheduler.running:
    scheduler.shutdown(wait=False)
print('SMOKE ' + json.dumps(out, default=str))
