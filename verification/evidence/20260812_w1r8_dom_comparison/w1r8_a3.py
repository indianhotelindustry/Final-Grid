"""W1-R8 A1/A3 — prove the restored banner fires under a real hash mismatch.

Runs against a throwaway copy of the production DB. Never touches instance/.
"""
import os
import shutil
import sys

REPO = r"c:\Users\SIPL Server\Downloads\DSS\SukoonPMS\SukoonPMS"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "instance", "pms.db")
TMP = os.path.join(SCRATCH, "w1r8_tamper.db")

shutil.copy2(SRC, TMP)
os.environ["DATABASE_URL"] = "sqlite:///" + TMP.replace(os.sep, "/")
sys.path.insert(0, REPO)

from app import create_app                      # noqa: E402
from app.models import db, NightAuditLog, User  # noqa: E402
from app.services import verify_snapshot_integrity as vsi  # noqa: E402

app = create_app()
KEYS = ("has_hash", "matches", "version_match")

with app.app_context():
    assert str(db.engine.url).endswith("w1r8_tamper.db"), \
        f"REFUSING TO RUN: not pointed at the copy ({db.engine.url})"

    log = (NightAuditLog.query
           .filter(NightAuditLog.snapshot_json.isnot(None),
                   NightAuditLog.snapshot_hash.isnot(None))
           .order_by(NightAuditLog.audit_date.desc())
           .first())
    if not log:
        print("NO SNAPSHOT WITH A HASH IN THIS DATA — A3 cannot run")
        sys.exit(2)

    audit_date = log.audit_date.isoformat()
    print(f"target: audit_date={audit_date} id={log.id} status={log.status}")

    uid = User.query.filter(User.is_active == True).first().id  # noqa: E712
    client = app.test_client()

    def render(tag):
        with client.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_fresh"] = True
        out = {}
        for tab in ("dashboard", "analytics", "history", "settings"):
            r = client.get(f"/night-audit?tab={tab}&date={audit_date}")
            html = r.get_data(as_text=True)
            out[tab] = (r.status_code,
                        "Snapshot integrity warning" in html,
                        "Re-run Audit" in html)
        print(f"  [{tag}] integrity={ {k: vsi(log)[k] for k in KEYS} }")
        for tab, (code, banner, rerun) in out.items():
            print(f"      tab={tab:10} http={code}  banner={banner!s:5}  rerun_button={rerun}")
        return out

    clean = render("CLEAN — null control")

    log.snapshot_json = log.snapshot_json + " "   # FLT-D02's exact mutation
    db.session.commit()
    tampered = render("TAMPERED — seeded fault")

    print()
    ok = True
    for tab in clean:
        if clean[tab][1]:
            print(f"FAIL: banner present on {tab} with an intact snapshot "
                  f"(false positive)")
            ok = False
        if not tampered[tab][1]:
            print(f"FAIL: banner absent on {tab} with a tampered snapshot "
                  f"(the control does not fire)")
            ok = False
    print("A1/A3 VERDICT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
