# BUG FG-ON-01 — Fresh install seeds `night_audit_enabled='true'`, contradicting FD-P2-05

| | |
|---|---|
| Discovered | 2026-10-02, FG-OVERNIGHT-01 (gates analysis, inconsistency 9); reconfirmed by reading the code |
| Severity | MEDIUM (governance/configuration) — not production-affecting today |
| Affected area | `app/__init__.py` settings initialisation |
| Production affected | **No.** Production holds `settings.night_audit_enabled = 'false'` (read-only, 2026-10-02 00:40). The seed inserts only when the key is missing. |
| Fix status | **Not fixed — outside the overnight directive's authorized scope** (no `app/` change is authorized) |

## Reproduction (static)

`app/__init__.py:1896-1898` (at `c9eeff0`):

```python
settings_data = [
    ('night_audit_enabled', 'true', 'Enable automatic night audit'),
    ('night_audit_time', '02:00', 'Night audit run time (HH:MM)'),
```

On a new installation (or any database missing the key), the initialiser seeds the unattended 02:00 night audit as **enabled**.

## Why it matters

FD-P2-05 (`verification/FOUNDER_DECISIONS.md:1168-1176`) makes manual controlled close the first-release operating model: "the first-release configuration keeps `night_audit_enabled=false`", "unattended scheduler execution is NOT the first-release operating model". FD-009 forbids unattended, financially material mutation without operator-equivalent controls. A fresh deployment (new property, rebuilt database, restore into an empty schema followed by seeding) would therefore start posting room rent unattended at 02:00.

## Possible fix (for a later bounded directive)

Change the seed default to `'false'`. Add a G9/G11 checklist item asserting `night_audit_enabled='false'` after install. No schema change.

## Dependency

A bounded `app/` directive (it fits Phase 3 or the G9/G11 work). G11 rehearsal checklist item: `20261002_overnight_g11_g12_prep/` (verify the setting after install).
