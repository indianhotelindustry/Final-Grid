"""
Golden master capture and storage.

A capture run:

  1. takes a disposable copy of production (``verification.dbcopy``) and
     fingerprints the original;
  2. reads the business date straight out of the copy with sqlite3 —
     before any application code loads — and freezes the clock to noon
     on that date;
  3. builds a Flask application bound to the copy;
  4. resolves the capture identity and the pinned entity ids;
  5. requests every catalogued surface twice: once authenticated, once
     anonymous;
  6. records status, redirect target, rendered templates, numeric
     figures and a normalised body hash for each;
  7. re-verifies that production is byte-identical;
  8. writes the master set, or compares against a stored one.

Noon is chosen for the frozen instant because it sits inside the normal
operating day: away from the midnight rollover that the night audit
straddles and away from the early-morning window some shift logic
treats specially. It is recorded in the index, so it is an input to the
master, not an assumption hidden in the code.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict

from verification.config import PRODUCTION_DB, PROJECT_ROOT, Severity
from verification.dbcopy import (
    CopyHandle, assert_production_untouched, make_copy, sqlalchemy_url,
)
from verification.golden import catalogue as cat
from verification.golden import client as gmclient
from verification.golden import normalize as norm
from verification.golden.freeze import install_proven

MASTERS_DIR = os.path.join(PROJECT_ROOT, 'verification', 'masters')

#: Time of day the clock is frozen to. See module docstring.
FREEZE_TIME = _dt.time(12, 0, 0)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

class BusinessDateMismatch(RuntimeError):
    """The pre-read business date disagrees with the application's own.

    Raised rather than warned: everything downstream — the frozen clock,
    every date-scoped report, every master — is derived from that date,
    so continuing would produce a consistent-looking master set for the
    wrong day.
    """


@dataclass
class SurfaceCapture:
    surface_id: str
    url: str
    endpoint: str
    category: str
    severity: str
    origin: str
    note: str = ''
    params: dict = field(default_factory=dict)

    status: int = 0
    content_type: str = ''
    location: str = ''
    templates: list = field(default_factory=list)
    figures: dict = field(default_factory=dict)
    figure_source: str = 'none'
    truncations: list = field(default_factory=list)
    body_sha256: str = ''
    body_bytes: int = 0
    normalisation_hits: dict = field(default_factory=dict)

    anon_status: int = 0
    anon_location: str = ''

    error: str = ''
    duration_ms: int = 0

    @property
    def healthy(self) -> bool:
        return 200 <= self.status < 400 and not self.error


@dataclass
class CaptureRun:
    started_at: str
    finished_at: str = ''
    duration_seconds: float = 0.0
    app_version: str = ''
    pvf_version: str = ''
    frozen_at: str = ''
    freeze_override: str = ''
    freeze_proof: dict = field(default_factory=dict)
    business_date: str = ''
    principal: dict = field(default_factory=dict)
    source_db: str = ''
    source_hash_before: str = ''
    source_hash_after: str = ''
    read_only_verified: bool = False
    copy_method: str = ''
    surfaces: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    normalisation_rules: list = field(default_factory=list)

    @property
    def unhealthy(self) -> list:
        return [s for s in self.surfaces if not s.healthy]

    @property
    def counts(self) -> dict:
        out = {'total': len(self.surfaces), 'healthy': 0, 'unhealthy': 0}
        for s in self.surfaces:
            out['healthy' if s.healthy else 'unhealthy'] += 1
        for s in self.surfaces:
            out[s.category] = out.get(s.category, 0) + 1
        return out


# ---------------------------------------------------------------------------
# Application build
# ---------------------------------------------------------------------------

def read_business_date(db_path: str) -> _dt.date:
    """Business date from the copy, read with sqlite3 before any app import.

    Deliberately not via ``app.services.get_business_date()``: the clock
    has to be frozen *before* application modules import ``datetime``,
    and that means knowing the date before the application exists.
    """
    conn = sqlite3.connect(db_path)
    try:
        # The column MUST be quoted. Unquoted, SQLite parses
        # ``current_date`` as its built-in CURRENT_DATE keyword and
        # returns the wall-clock date, which silently froze the clock to
        # the wrong day the first time this ran.
        row = conn.execute(
            'SELECT "current_date" FROM business_date ORDER BY id LIMIT 1'
        ).fetchone()
    except sqlite3.Error:
        row = None
    finally:
        conn.close()
    if not row or not row[0]:
        raise RuntimeError(
            'No business date in the dataset. Golden master capture needs '
            'one: without it the clock would have to be frozen to an '
            'arbitrary instant and every date-scoped report would be '
            'measuring a day the hotel never traded.')
    return _dt.date.fromisoformat(str(row[0])[:10])


def build_app(handle: CopyHandle):
    os.environ['DATABASE_URL'] = sqlalchemy_url(handle)
    os.environ.setdefault('FLASK_ENV', 'production')
    from app import create_app
    app = create_app()
    # CSRF stays ENABLED. Capture only issues GETs, and leaving it on
    # keeps the rendered output identical to what a user receives.
    return app


def _app_version() -> str:
    try:
        from app import APP_VERSION
        return APP_VERSION
    except Exception:
        return 'unknown'


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def _capture_one(app, auth_client, anon_client, surface: cat.Surface,
                 template_sink: list) -> SurfaceCapture:
    rec = SurfaceCapture(
        surface_id=surface.surface_id, url=surface.url,
        endpoint=surface.endpoint, category=surface.category,
        severity=surface.severity, origin=surface.origin,
        note=surface.note, params=surface.params)

    t0 = time.perf_counter()
    template_sink.clear()
    try:
        resp = auth_client.get(surface.url)
    except Exception as exc:
        rec.error = f'{type(exc).__name__}: {exc}'
        rec.duration_ms = int((time.perf_counter() - t0) * 1000)
        return rec

    rec.status = resp.status_code
    rec.content_type = (resp.headers.get('Content-Type') or '').split(';')[0]
    rec.location = resp.headers.get('Location', '')
    rec.templates = [name for name, _ in template_sink]

    body = resp.get_data()
    rec.body_sha256, rec.normalisation_hits, rec.body_bytes = norm.body_digest(body)

    if rec.content_type == 'application/json':
        rec.figures, rec.truncations = norm.figures_from_json(body)
        rec.figure_source = 'json'
    elif template_sink:
        # Last template wins: with Jinja inheritance the signal fires for
        # the child template with the full context.
        merged: dict = {}
        for _name, context in template_sink:
            merged.update(context)
        rec.figures, rec.truncations = norm.figures_from_context(merged)
        rec.figure_source = 'context'
    else:
        rec.figure_source = 'none'

    try:
        anon = anon_client.get(surface.url)
        rec.anon_status = anon.status_code
        rec.anon_location = anon.headers.get('Location', '')
    except Exception as exc:
        rec.anon_status = -1
        rec.anon_location = f'{type(exc).__name__}: {exc}'

    rec.duration_ms = int((time.perf_counter() - t0) * 1000)
    return rec


def run_capture(source: str = PRODUCTION_DB, quiet: bool = False) -> CaptureRun:
    """Execute a full capture against a disposable copy of *source*."""
    from verification import __version__ as PVF_VERSION

    started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    t0 = time.perf_counter()

    handle = make_copy(name='pvf_golden.db', source=source)
    business_date = read_business_date(handle.copy_path)
    freeze_date = business_date

    # Commissioning-only override. Used by the seeded-fault harness to
    # prove that moving the clock IS detected — that is, that freezing it
    # is load-bearing rather than decorative. Never set in normal use;
    # when set, it is recorded in the run so no evidence pack can be
    # mistaken for an ordinary capture.
    override = os.environ.get('PVF_GM_FREEZE_DATE')
    if override:
        freeze_date = _dt.date.fromisoformat(override)

    instant = _dt.datetime.combine(freeze_date, FREEZE_TIME)

    if not quiet:
        print(f'[gm] working copy : {handle.copy_path} ({handle.method})')
        print(f'[gm] source sha256: {handle.source_hash_before}')
        print(f'[gm] business date: {business_date}')
        print(f'[gm] clock frozen : {instant.isoformat()}')

    freeze, proof = install_proven(instant)
    try:
        app = build_app(handle)
        # Rebind again: application modules imported during create_app()
        # captured the fakes at import time, but this is cheap insurance
        # and its count appears in the proof.
        freeze.rebind_loaded_modules()
        proof = freeze.prove()

        from flask import template_rendered
        sink: list = []

        def _record(sender, template, context, **extra):
            sink.append((template.name, dict(context)))

        template_rendered.connect(_record, app)

        run = CaptureRun(
            started_at=started,
            app_version=_app_version(),
            pvf_version=PVF_VERSION,
            frozen_at=instant.isoformat(),
            freeze_override=override or '',
            freeze_proof=proof,
            business_date=business_date.isoformat(),
            source_db=handle.source_path,
            source_hash_before=handle.source_hash_before,
            copy_method=handle.method,
            normalisation_rules=[{'name': n, 'pattern': p.pattern, 'why': w}
                                 for n, p, _r, w in norm.RULES],
        )

        with app.app_context():
            # Cross-check the pre-read against the application's own
            # answer. The pre-read happens before any app code exists,
            # so nothing else would catch it being wrong — and a clock
            # frozen to the wrong day produces masters that look
            # perfectly stable while measuring a day the hotel did not
            # trade.
            from app.services import get_business_date
            app_business_date = get_business_date()
            if app_business_date != business_date:
                raise BusinessDateMismatch(
                    f'Pre-read business date {business_date} does not match '
                    f'the application\'s get_business_date() '
                    f'{app_business_date}. The clock would have been frozen '
                    f'to the wrong day. Capture aborted.')

            principal = gmclient.resolve_principal()
            run.principal = {'user_id': principal.user_id,
                             'username': principal.username,
                             'role': principal.role}
            surfaces, gaps = cat.build(app, business_date)
            run.gaps = gaps
            if not quiet:
                print(f'[gm] identity     : {principal.username} '
                      f'({principal.role})')
                print(f'[gm] surfaces     : {len(surfaces)} '
                      f'({len(gaps)} declared gaps)')

        auth_client = gmclient.authenticated_client(app, principal)
        anon_client = gmclient.anonymous_client(app)

        for i, surface in enumerate(surfaces, 1):
            rec = _capture_one(app, auth_client, anon_client, surface, sink)
            run.surfaces.append(rec)
            if not quiet and (i % 20 == 0 or i == len(surfaces)):
                print(f'[gm]   {i}/{len(surfaces)} captured')

        template_rendered.disconnect(_record, app)
    finally:
        freeze.uninstall()

    run.source_hash_after = assert_production_untouched(handle)
    run.read_only_verified = run.source_hash_after == run.source_hash_before
    run.finished_at = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    run.duration_seconds = round(time.perf_counter() - t0, 2)
    return run


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _safe_name(surface_id: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in surface_id)


def master_dir(tag: str) -> str:
    return os.path.join(MASTERS_DIR, tag)


def write_masters(run: CaptureRun, tag: str) -> str:
    """Persist a capture as the golden master set *tag*."""
    out_dir = master_dir(tag)
    surf_dir = os.path.join(out_dir, 'surfaces')
    os.makedirs(surf_dir, exist_ok=True)

    # Remove masters for surfaces that no longer exist, so the stored set
    # always equals the captured set. A stale file would otherwise be
    # reported as a removed surface forever.
    keep = {_safe_name(s.surface_id) + '.json' for s in run.surfaces}
    for existing in os.listdir(surf_dir):
        if existing.endswith('.json') and existing not in keep:
            os.remove(os.path.join(surf_dir, existing))

    for s in run.surfaces:
        path = os.path.join(surf_dir, _safe_name(s.surface_id) + '.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(asdict(s), fh, indent=2, sort_keys=True)
            fh.write('\n')

    index = {k: v for k, v in asdict(run).items() if k != 'surfaces'}
    index['surface_index'] = [
        {'surface_id': s.surface_id, 'url': s.url, 'category': s.category,
         'severity': s.severity, 'status': s.status,
         'figure_count': len(s.figures), 'body_sha256': s.body_sha256}
        for s in run.surfaces]
    index['counts'] = run.counts
    with open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8') as fh:
        json.dump(index, fh, indent=2, sort_keys=True)
        fh.write('\n')
    return out_dir


def read_masters(tag: str) -> tuple[dict, dict]:
    """Return ``(index, {surface_id: master_record})``."""
    out_dir = master_dir(tag)
    index_path = os.path.join(out_dir, 'index.json')
    if not os.path.isfile(index_path):
        raise FileNotFoundError(
            f'No golden master set named {tag!r}. Capture one first:\n'
            f'    python -m verification gm-capture --tag {tag}')
    with open(index_path, encoding='utf-8') as fh:
        index = json.load(fh)
    surf_dir = os.path.join(out_dir, 'surfaces')
    masters = {}
    for name in sorted(os.listdir(surf_dir)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(surf_dir, name), encoding='utf-8') as fh:
            rec = json.load(fh)
        masters[rec['surface_id']] = rec
    return index, masters
