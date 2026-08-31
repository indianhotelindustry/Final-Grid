# FinalGrid

**FinalGrid by Infuture Technologies** — a front-office Property Management
System for independent hotels.

FinalGrid is the software product. It is not the name of any hotel.

## Product identity vs property identity

Two distinct identities live in this repository, and they must never be
collapsed into one another.

| | Identity | Where it lives | Example |
|---|---|---|---|
| **Product** | `FinalGrid` | `app_name` setting; falls back to the `FinalGrid` default in `app/__init__.py` | the navbar's primary line, browser title, CLI banners |
| **Property** | the operating hotel | `hotel_name` setting; falls back to the `HOTEL_NAME` env/config value | the navbar's secondary line, invoices, guest-facing pages |

Rendered together the pattern is:

```
FinalGrid — Sukoon Pearl Inn
```

`Sukoon Pearl Inn` (and `Sukoon City View`, which appears as the configured
default and in example configuration) are **hotel/property names**. They are
customer data. They are never renamed to `FinalGrid`.

A hotel may override the displayed product name under **Settings → App
Branding**; the stored `app_name` wins over the built-in default.

## Retained legacy identifiers

The product was previously named *DSBC Frontline* and, before that, *Sukoon
PMS*. Those names are gone from every product-facing surface. A small number
of **technical identifiers** deliberately keep their legacy spelling, because
renaming them would break existing installations. They are internal only and
are never shown as the product name.

| Identifier | Where | Why it is retained |
|---|---|---|
| `SukoonPMS` (Windows firewall rule name) | `enable_lan.bat`, `disable_lan.bat`, `.env.example` | `disable_lan.bat` deletes the rule *by name*. Renaming it would strand an open inbound port on every existing install. |
| `sukoon_pms` (gunicorn `proc_name`) | `gunicorn.conf.py` | Deployment/process identifier that external process managers and monitoring may key on. |
| `sukoon-pms` (Cloudflare tunnel name) | `cloudflare/config.yml`, `cloudflare/SETUP_GUIDE.md` | The tunnel is registered with Cloudflare under this name. Renaming it invalidates existing tunnel credentials and DNS routes. |
| `pms.db`, `pms.log`, `pms_*.db` backups, `pms-static-v*` caches | throughout | Filesystem, log, backup and service-worker cache names. Renaming orphans existing databases, backups and caches. |
| `SukoonPMS-<date>-<tag>.bundle` | `verification/ENGINEERING_GUIDE.md` | Existing repository backup bundles already carry this prefix; a split naming scheme in one directory is worse than a legacy one. |
| `hey sukoon` / `sukoon` (voice wake-word aliases) | `app/ai_voice.py` | Filler-word strip list for spoken commands. Staff already say these; removing them changes command parsing. |
| `SukoonPMS` in the install directory path | recorded in verification evidence and ledgers | The install root's directory name. Recorded paths in evidence are historical fact and are not rewritten. |

Historical audit evidence under `verification/evidence/`, `verification/ledgers/`
and `verification/masters/`, and the dated completion reports under
`verification/`, retain whatever product name was current when they were
written. Rewriting them would falsify the record.

## Version

See `version.txt`. The rebrand did not change the versioning scheme.

## Running

```
start.bat          # start the server (Windows install)
stop.bat           # stop it
update.bat         # apply an update package
```

`verification/README.md` documents the Production Verification Framework, which
measures the application from the outside and contains no production code.
