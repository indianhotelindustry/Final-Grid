# -*- coding: utf-8 -*-
"""HUMAN provenance for the real production user, on a COPY of the migrated
production database (never on production itself).

An action performed here as user 1 would, on production, be an audit row
falsely attributed to the Founder's account; so the check runs on a copy
made from the verified post-migration backup. Live confirmation is the
Founder's own next login (the login audit row).

    cd <live folder> && venv\\Scripts\\python.exe <this file> <restored_post.db> <scratch copy path>
"""
import json
import os
import sqlite3
import sys

src, dst = sys.argv[1], sys.argv[2]
LIVE = os.getcwd()
assert os.path.abspath(dst) != os.path.abspath(os.path.join(LIVE, 'instance', 'pms.db'))
a, b = sqlite3.connect('file:%s?mode=ro' % src.replace('\\', '/'), uri=True), sqlite3.connect(dst)
a.backup(b)
a.close()
b.close()
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath(dst).replace('\\', '/')
sys.path.insert(0, LIVE)
from app import create_app                                     # noqa: E402
from app import models as m                                    # noqa: E402

app = create_app()
from app.services import scheduler                             # noqa: E402
if scheduler.running:
    scheduler.shutdown(wait=False)
import app.routes as routes                                    # noqa: E402
from flask_login import login_user                             # noqa: E402

with app.test_request_context('/', environ_base={'REMOTE_ADDR': '127.0.0.1'}):
    u = m.db.session.get(m.User, 1)
    user = [u.id, u.role]
    login_user(u)
    routes._write_audit('ProvenanceCheck', 1, 'adr011_human_provenance_copy', {}, {'copy': True})
    m.db.session.commit()
    open_shift = m.db.session.execute(m.db.text(
        "SELECT id FROM shifts WHERE user_id=1 AND status='Open' ORDER BY id DESC LIMIT 1")).scalar()
    row = m.db.session.execute(m.db.text(
        "SELECT staff_user_id, actor_kind, actor_mechanism, actor_role, actor_shift_id, ip_address "
        "FROM audit_logs WHERE action='adr011_human_provenance_copy'")).fetchall()
print('HUMAN ' + json.dumps({'database': os.environ['DATABASE_URL'], 'user': user,
                              'open_shift_of_user_1': open_shift, 'rows': [list(r) for r in row]}))
