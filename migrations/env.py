"""Alembic environment, dual-mode (v2.2.13 hardening — Phase 1).

Supports BOTH invocation paths:

  1. Flask-Migrate mode  — `flask db upgrade` inside a Flask app context.
     This is the historical path used by `installer/_alembic_upgrade.py`
     and any direct `flask db ...` command. current_app provides the
     engine + metadata.

  2. Standalone CLI mode — `alembic -c migrations/alembic.ini upgrade head`
     invoked directly from cmd / PowerShell without any Flask boot. This
     is the operator recovery path: when patch_apply.bat aborts mid-flight,
     the operator can run this command alone to advance migrations from a
     production shell without needing to know how to boot the Flask app.
     In this mode env.py reads sqlalchemy.url from alembic.ini and imports
     model metadata directly from app.models.

The mode is auto-detected at import time. If we are inside a Flask app
context AND the 'migrate' extension is registered, we use the Flask path;
otherwise we use the standalone path.
"""
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


# ── Detect mode ───────────────────────────────────────────────────────
def _detect_flask_context():
    """Return True iff a Flask app context with the migrate extension is active."""
    try:
        from flask import current_app, has_app_context
        if not has_app_context():
            return False
        return 'migrate' in current_app.extensions
    except Exception:
        return False


_USE_FLASK = _detect_flask_context()


# ── Standalone-mode imports (only needed when Flask isn't available) ──
def _bootstrap_standalone():
    """Make app.models importable from the migrations/ directory."""
    _env_dir  = os.path.dirname(os.path.abspath(__file__))
    _app_root = os.path.dirname(_env_dir)
    if _app_root not in sys.path:
        sys.path.insert(0, _app_root)


# ── Flask-mode helpers (existing behaviour) ───────────────────────────
def _flask_get_engine():
    from flask import current_app
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def _flask_get_engine_url():
    eng = _flask_get_engine()
    try:
        return eng.url.render_as_string(hide_password=False).replace('%', '%%')
    except AttributeError:
        return str(eng.url).replace('%', '%%')


# ── Resolve target metadata + engine URL ──────────────────────────────
if _USE_FLASK:
    from flask import current_app
    # Override the .ini url with the Flask-configured one. This preserves
    # historical behaviour for `flask db ...` invocations.
    config.set_main_option('sqlalchemy.url', _flask_get_engine_url())
    _target_db = current_app.extensions['migrate'].db
else:
    # Standalone CLI path: rely on the URL declared in alembic.ini, and
    # import the metadata directly from app.models (no Flask app boot).
    _bootstrap_standalone()
    from app.models import db as _target_db
    logger.info('alembic env.py: STANDALONE mode (no Flask context detected)')


def get_metadata():
    if hasattr(_target_db, 'metadatas'):
        return _target_db.metadatas[None]
    return _target_db.metadata


# ── Online vs offline migration runners ───────────────────────────────
def run_migrations_offline():
    """Offline mode: configure with URL only, emit SQL to stdout."""
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Online mode: build an engine, run migrations in a transaction."""

    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    if _USE_FLASK:
        from flask import current_app
        conf_args = current_app.extensions['migrate'].configure_args
        if conf_args.get('process_revision_directives') is None:
            conf_args['process_revision_directives'] = process_revision_directives
        connectable = _flask_get_engine()
    else:
        # Build a fresh engine from the .ini URL.
        from sqlalchemy import engine_from_config, pool
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix='sqlalchemy.',
            poolclass=pool.NullPool,
        )
        conf_args = {'process_revision_directives': process_revision_directives}

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
