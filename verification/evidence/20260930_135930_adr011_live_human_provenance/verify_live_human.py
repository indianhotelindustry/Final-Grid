# -*- coding: utf-8 -*-
"""ADR-011 live HUMAN provenance verification - READ-ONLY.

Opens production (``instance/pms.db``) and the verified post-migration backup
with ``mode=ro`` only. Writes nothing to either; writes RESULT.json here.
Recipient/body/error columns of notification tables are never copied out.

    venv\\Scripts\\python.exe verification\\evidence\\20260930_135930_adr011_live_human_provenance\\verify_live_human.py
"""
import hashlib
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PROD = os.path.join(REPO, 'instance', 'pms.db')
POST_BACKUP = os.path.join(os.path.dirname(REPO), 'db-backups', 'pms_20260930_132529_adr011-apply-post.db')
POST_BACKUP_SHA = '12ba7b7eb8004b43492829b5c1f153e0010f777e0b2c146f86b423cb39c8fac6'
MIGRATED_SHA = 'e67f963b87e4004cee4f5f4abd6b97a07e07763faf328256397d8246e49ec569'
ORIG = ('id', 'entity_type', 'entity_id', 'action', 'before_state', 'after_state',
        'staff_user_id', 'ip_address', 'timestamp')
SAFE = {'users': ('id', 'username', 'role', 'is_active', 'last_login', 'failed_login_count', 'locked_until'),
        'notification_queue': ('id', 'channel', 'message_type', 'reservation_id', 'status', 'attempts',
                               'max_attempts', 'next_retry_at', 'created_at'),
        'notification_logs': ('id', 'channel', 'message_type', 'reservation_id', 'status', 'sent_at')}


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def ro(p):
    return sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)


def digests(c):
    out = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        h = hashlib.sha256()
        n = 0
        for r in c.execute('SELECT * FROM "%s" ORDER BY rowid' % t):
            h.update(json.dumps(list(r), default=str).encode() + b'\n')
            n += 1
        out[t] = (n, h.hexdigest())
    return out


prod_sha_before = sha(PROD)
assert sha(POST_BACKUP) == POST_BACKUP_SHA, 'post-migration backup does not match its manifest digest'
P, B = ro(PROD), ro(POST_BACKUP)
P.row_factory = sqlite3.Row
new_rows = [dict(r) for r in P.execute('SELECT * FROM audit_logs WHERE id > 23 ORDER BY id')]
P.row_factory = None

user_role = dict(P.execute('SELECT id, role FROM users').fetchall())
open_shift = {uid: P.execute("SELECT id FROM shifts WHERE user_id=? AND status='Open' ORDER BY id DESC LIMIT 1",
                             (uid,)).fetchone() for uid in user_role}


def human_ok(r):
    uid = r['staff_user_id']
    exp_shift = open_shift.get(uid)[0] if open_shift.get(uid) else None
    checks = {
        'actor_kind is HUMAN': r['actor_kind'] == 'HUMAN',
        'staff_user_id references a real user': uid in user_role,
        'staff_user_id is not 0 / not NULL': bool(uid),
        'actor_role equals the user\'s role': r['actor_role'] == user_role.get(uid),
        'actor_shift_id equals the user\'s open shift (none -> NULL)': r['actor_shift_id'] == exp_shift,
        'actor_mechanism is web (authenticated request)': r['actor_mechanism'] == 'web',
        'ip_address recorded': bool(r['ip_address']),
    }
    return checks, all(checks.values())


rows_eval = []
for r in new_rows:
    checks, ok = human_ok(r)
    rows_eval.append({'row': r, 'checks': checks, 'satisfies_human_model': ok})

# Whole-database comparison with the verified post-migration backup.
dp, db_ = digests(P), digests(B)
changed = sorted(t for t in set(dp) | set(db_) if dp.get(t) != db_.get(t))
diff = {}
for t in changed:
    if t == 'audit_logs':
        continue
    cols = [x[1] for x in P.execute('PRAGMA table_info(%s)' % t)]
    safe = SAFE.get(t, ('id',))
    a = {r[0]: dict(zip(cols, r)) for r in B.execute('SELECT * FROM %s' % t)}
    b = {r[0]: dict(zip(cols, r)) for r in P.execute('SELECT * FROM %s' % t)}
    rows = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            if k not in a:
                rows.append({'id': k, 'new': {c: b[k][c] for c in safe if c in b[k]}})
            else:
                rows.append({'id': k, 'changed': {c: [a[k][c], b[k][c]] for c in cols
                                                  if a[k][c] != b[k][c] and c in safe},
                             'changed_non_public_columns': [c for c in cols if a[k][c] != b[k][c]
                                                            and c not in safe]})
    diff[t] = rows
audit_old = {r[0]: r for r in B.execute('SELECT * FROM audit_logs')}
audit_now = {r[0]: r for r in P.execute('SELECT * FROM audit_logs')}
h = hashlib.sha256()
for r in P.execute('SELECT %s FROM audit_logs WHERE id <= 23 ORDER BY id' % ', '.join(ORIG)):
    h.update(json.dumps(list(r), default=str, sort_keys=True).encode() + b'\n')
fail_reasons = sorted({(e or '')[:120] for (e,) in P.execute('SELECT error_message FROM notification_logs WHERE id > 5')})
out = {
    'task': 'ADR-011 live HUMAN provenance verification (read-only)',
    'production_sha256_before': prod_sha_before,
    'production_sha256_at_migration': MIGRATED_SHA,
    'baseline': 'verified post-migration backup %s (%s)' % (os.path.basename(POST_BACKUP), POST_BACKUP_SHA),
    'new_audit_rows': rows_eval,
    'audit_rows_existing_unchanged': all(audit_now.get(k) == v for k, v in audit_old.items()),
    'historical_23_original_column_digest': h.hexdigest(),
    'audit_counts_system_zero_null': P.execute(
        "SELECT SUM(actor_kind='SYSTEM'), SUM(staff_user_id=0), SUM(staff_user_id IS NULL) FROM audit_logs").fetchone(),
    'tables_changed_vs_post_migration': changed,
    'non_audit_changes': diff,
    'notification_failure_reasons': fail_reasons,
    'integrity_check': P.execute('PRAGMA integrity_check').fetchone()[0],
    'schema_migrations_latest': P.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0],
    'night_audit_enabled': P.execute("SELECT value FROM settings WHERE key='night_audit_enabled'").fetchone()[0],
}
P.close()
B.close()
out['production_sha256_after'] = sha(PROD)
with open(os.path.join(HERE, 'RESULT.json'), 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=2, default=str)
print(json.dumps({k: out[k] for k in ('tables_changed_vs_post_migration', 'audit_rows_existing_unchanged',
                                      'audit_counts_system_zero_null', 'integrity_check')}, default=str))
for e in rows_eval:
    print(e['row']['id'], e['row']['action'], e['row']['timestamp'], e['satisfies_human_model'])
print('prod before/after equal:', out['production_sha256_before'] == out['production_sha256_after'])
