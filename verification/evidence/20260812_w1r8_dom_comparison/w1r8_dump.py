"""Dump Night Audit HTML for before/after DOM comparison.

Usage: python w1r8_dump.py <outdir>
Read-only against production data.
"""
import os
import re
import sys

REPO = r"c:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS"
sys.path.insert(0, REPO)

outdir = sys.argv[1]
os.makedirs(outdir, exist_ok=True)

from app import create_app          # noqa: E402
from app.models import User         # noqa: E402

app = create_app()
with app.app_context():
    uid = User.query.filter(User.is_active == True).first().id  # noqa: E712

client = app.test_client()
with client.session_transaction() as s:
    s["_user_id"] = str(uid)
    s["_fresh"] = True

SURFACES = {
    "panel_dashboard": "/night-audit?tab=dashboard",
    "panel_analytics": "/night-audit?tab=analytics",
    "panel_history":   "/night-audit?tab=history",
    "panel_settings":  "/night-audit?tab=settings",
    "panel_default":   "/night-audit",
    "report_print":    "/reports/night-audit?format=print",
    "report_json":     "/reports/night-audit?format=json",
    "audit_history":   "/reports/night-audit/history",
    "audit_snapshot":  "/reports/night-audit/1",
}

# Per-render nonces/tokens are not DOM: D2 normalises exactly these three.
SCRUB = [
    (re.compile(r'nonce="[A-Za-z0-9+/=_-]{8,}"'), 'nonce="X"'),
    (re.compile(r'(<meta[^>]*name="csrf-token"[^>]*content=")[^"]+(")'), r'\1X\2'),
    (re.compile(r'(name="csrf_token"[^>]*value=")[^"]+(")'), r'\1X\2'),
]

for name, path in SURFACES.items():
    r = client.get(path)
    body = r.get_data(as_text=True)
    for pat, rep in SCRUB:
        body = pat.sub(rep, body)
    with open(os.path.join(outdir, f"{name}.html"), "w", encoding="utf-8") as fh:
        fh.write(f"<!-- HTTP {r.status_code} {path} -->\n")
        fh.write(body)
    print(f"  {r.status_code}  {path:42} -> {name}.html ({len(body)} bytes)")
