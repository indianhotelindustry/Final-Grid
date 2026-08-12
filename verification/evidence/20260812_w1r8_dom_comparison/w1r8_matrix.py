"""W1-R8 A4 — pin every Night Audit route to the template it renders.

Read-only against production data. Also proves the step-3 deprecation
warning fires when the unreachable fallthrough is forced.
"""
import logging
import os
import sys

REPO = r"c:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS"
sys.path.insert(0, REPO)

from flask import template_rendered            # noqa: E402
from app import create_app                     # noqa: E402
from app.models import User                    # noqa: E402

app = create_app()
with app.app_context():
    uid = User.query.filter(User.is_active == True).first().id  # noqa: E712

client = app.test_client()
with client.session_transaction() as s:
    s["_user_id"] = str(uid)
    s["_fresh"] = True

rendered = []


def _record(sender, template, context, **extra):
    rendered.append(template.name)


# blinker holds receivers weakly: a lambda would be collected immediately
# and every surface would silently report "(none)".
template_rendered.connect(_record, app)

# Capture the deprecation warning emitted by reports.night_audit.
class _Catch(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


catch = _Catch()
_root = logging.getLogger()
_root.addHandler(catch)
_root.setLevel(logging.WARNING)
logging.getLogger("app.reports").setLevel(logging.WARNING)
logging.getLogger("app.reports").propagate = True

EXPECTED = [
    ("/night-audit",                        200, "night_audit_panel.html"),
    ("/night-audit?tab=analytics",          200, "night_audit_panel.html"),
    ("/night-audit?tab=history",            200, "night_audit_panel.html"),
    ("/night-audit?tab=settings",           200, "night_audit_panel.html"),
    ("/reports/night-audit",                302, "(redirect)"),
    ("/reports/night-audit?format=html",    302, "(redirect)"),
    ("/reports/night-audit?format=print",   200, "reports/night_audit_print.html"),
    ("/reports/night-audit?format=json",    200, "(json)"),
    ("/reports/night-audit/history",        200, "reports/night_audit_history.html"),
    ("/reports/night-audit/1",              200, "reports/night_audit_snapshot.html"),
]

print(f"{'ROUTE':44} {'HTTP':>4}  TEMPLATE")
print("-" * 100)
ok = True
html_renderers = set()

for path, want_code, want_tpl in EXPECTED:
    rendered.clear()
    r = client.get(path)
    got_tpl = rendered[0] if rendered else (
        "(redirect)" if r.status_code == 302 else
        "(json)" if "json" in (r.content_type or "") else "(none)")
    flag = ""
    if r.status_code != want_code or got_tpl != want_tpl:
        flag, ok = "   <-- MISMATCH", False
    if got_tpl.endswith(".html"):
        html_renderers.add(got_tpl)
    print(f"{path:44} {r.status_code:>4}  {got_tpl}{flag}")

print()
print("HTML-rendering templates reachable by a real caller:")
for t in sorted(html_renderers):
    print(f"   {t}")

# A4: exactly one HTML *page* per surface, and the panel is the only one
# reachable from the /reports/night-audit route family's html branch.
print()
print("--- step 3: force the unreachable fallthrough ---")
catch.msgs.clear()
rendered.clear()
r = client.get("/reports/night-audit?format=__unrecognised__")
dep = [m for m in catch.msgs if "Deprecated template rendered" in m]
print(f"  http={r.status_code}  template={rendered[0] if rendered else '(none)'}")
print(f"  deprecation warning emitted: {bool(dep)}")
if dep:
    print(f"    {dep[0][:150]}")
if not dep:
    ok = False
    print("  FAIL: fallthrough rendered without logging — A5 would be vacuous")

print()
print("A4 VERDICT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
