from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
import os
import logging
import logging.handlers
from dotenv import load_dotenv

load_dotenv()

# Known-compromised SECRET_KEY values that must never be accepted.
# This list is used to fail-closed if an operator keeps a committed/default
# key in place. Add new entries here any time a key is known to have leaked.
_BANNED_SECRET_KEYS = frozenset({
    # Originally committed to .env during development — treated as leaked.
    '7ab6065781689e5d5c8228fb803eca452b8d3036fe02375eaa13dae49e6f63ea',
    # Flask-Migrate / cookie-cutter placeholders we never want in prod.
    'change-this-to-a-long-random-string',
    'dev-secret-key-insecure',
})


def _env_mode():
    """Resolve FLASK_ENV. Anything other than the explicit literal
    'development' is treated as production (fail-closed default)."""
    return 'development' if os.getenv('FLASK_ENV') == 'development' else 'production'


def _read_version():
    _vf = os.path.join(os.path.dirname(__file__), '..', 'version.txt')
    try:
        with open(_vf) as f:
            return f.read().strip()
    except FileNotFoundError:
        return '0.0.0'

APP_VERSION = _read_version()

# ---------------------------------------------------------------------------
# Logging — rotating file in production, stdout in dev
# ---------------------------------------------------------------------------
_log_level = logging.DEBUG if _env_mode() == 'development' else logging.INFO
_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S')
_root = logging.getLogger()
_root.setLevel(_log_level)
# Always keep stdout handler
_sh = logging.StreamHandler()
_sh.setFormatter(_formatter)
_root.addHandler(_sh)
# Add rotating file handler in production
if _env_mode() == 'production':
    _log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    os.makedirs(_log_dir, exist_ok=True)
    _fh = logging.handlers.RotatingFileHandler(
        os.path.join(_log_dir, 'pms.log'),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    _fh.setFormatter(_formatter)
    _root.addHandler(_fh)

logger = logging.getLogger(__name__)

login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")
csrf = CSRFProtect()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    secret_key = (os.getenv('SECRET_KEY') or '').strip()
    is_production = _env_mode() == 'production'

    # Fail-closed: in production we refuse to boot with a missing, short,
    # or known-compromised SECRET_KEY. This prevents a leaked dev key from
    # silently surviving a copy-paste of the repo onto a live server.
    if is_production:
        if not secret_key:
            raise RuntimeError(
                'FATAL: SECRET_KEY is not set. Generate a fresh key with:\n'
                '    python -c "import secrets; print(secrets.token_hex(32))"\n'
                'and add it to .env as SECRET_KEY=... (do NOT commit .env).'
            )
        if secret_key in _BANNED_SECRET_KEYS:
            raise RuntimeError(
                'FATAL: SECRET_KEY matches a known-compromised or placeholder '
                'value. Rotate it with:\n'
                '    python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if len(secret_key) < 32:
            raise RuntimeError(
                'FATAL: SECRET_KEY is too short (minimum 32 characters). '
                'Generate a fresh one with:\n'
                '    python -c "import secrets; print(secrets.token_hex(32))"'
            )

    if not secret_key:
        # Development only — an explicit, unambiguous marker that sessions
        # are insecure. Never reachable in production (see check above).
        logger.warning('SECRET_KEY is not set. Using a temporary, INSECURE dev key.')
        logger.warning('User sessions will not persist across server restarts.')
        secret_key = 'dev-secret-key-insecure'

    app.config['SECRET_KEY'] = secret_key
    app.config['ENV_MODE'] = 'production' if is_production else 'development'

    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        # Default to local SQLite for offline per-hotel deployment
        _db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance')
        os.makedirs(_db_dir, exist_ok=True)
        db_url = f"sqlite:///{os.path.join(_db_dir, 'pms.db')}"
        logger.info('DATABASE_URL not set — using local SQLite: %s', db_url)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TEMPLATES_AUTO_RELOAD'] = _env_mode() == 'development'

    _is_sqlite = db_url.startswith('sqlite')
    if _is_sqlite:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'check_same_thread': False},
        }
        # Operational note: on SQLite, with_for_update() is a no-op. SQLite
        # serialises writes with a DATABASE-WIDE lock, so the race windows
        # we protect with per-row FOR UPDATE locks on PostgreSQL are
        # covered by SQLite's coarser lock — but concurrency is also much
        # lower. Log once at boot so this is visible in production logs.
        if is_production:
            logger.warning(
                'Running on SQLite — row-level locking (with_for_update) '
                'is not enforced. SQLite uses a database-wide write lock; '
                'concurrent writers will serialise. Move to PostgreSQL for '
                'true per-row locking and higher concurrency.'
            )
        else:
            logger.info(
                'SQLite backend detected — row-level locks are no-ops; '
                'DB-wide write lock provides serialisation.'
            )
    else:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10,
        }
    app.config['DB_IS_SQLITE'] = _is_sqlite
    app.config['HOTEL_NAME'] = os.getenv('HOTEL_NAME', 'Sukoon City View')
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB upload limit

    # ── OTA Revenue Intelligence (Phase A) feature flag ────────────────────
    # Append-only enhancement on /ota/ dashboard. Default OFF for the first
    # 24h after deploy so we can validate parity with the existing dashboard
    # before any new aggregates are computed. Toggle on via .env:
    #     OTA_INTELLIGENCE_ENABLED=1
    # Removing the env var (or setting it to anything other than the truthy
    # values below) reverts to pre-S1 behaviour with zero code change.
    app.config['OTA_INTELLIGENCE_ENABLED'] = (
        (os.getenv('OTA_INTELLIGENCE_ENABLED') or '').strip().lower()
        in ('1', 'true', 'yes', 'on')
    )

    # ── Group Stay — multi-room shared reservation (Phase 1) feature flag ──
    # Defined for Release 1 (v2.2.10) but has NO consumers yet. The flag
    # exists so Release 3's UI can branch on it; until then the multi-room
    # creation path does not exist anywhere in the codebase. Setting this
    # to 1 in Release 1/2 has no observable effect. Default OFF.
    # See docs/RELEASE.md §"Group Stay" for the full phased plan.
    app.config['MULTI_ROOM_ENABLED'] = (
        (os.getenv('MULTI_ROOM_ENABLED') or '').strip().lower()
        in ('1', 'true', 'yes', 'on')
    )

    # ── Phase A.3 — Startup security banner ────────────────────────────
    # One-shot summary of the security-sensitive posture at boot. Shows
    # up once in logs/pms.log so an operator can verify the install is
    # running the way they expect.
    try:
        _env = 'production' if is_production else 'development'
        _banner_items = []
        _banner_items.append(('env', _env))
        _banner_items.append(('secret_key',
                              'set (>=32 chars)' if len(secret_key) >= 32
                              else 'DEV-FALLBACK'))

        # Updater signing — public key presence is a boolean signal. The
        # updater itself fails-closed if absent, but surfacing it here
        # makes "why are updates being rejected?" self-diagnosable.
        _pubkey_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    '..', 'installer', 'update_pubkey.pem')
        _banner_items.append(('updater_signing',
                              'ENFORCED' if os.path.isfile(_pubkey_path)
                              else 'NO PUBKEY (updates will be rejected)'))

        # Encryption availability — `cryptography` is both a backup
        # requirement and a PII-column requirement. If it's missing, the
        # operator should know immediately.
        try:
            import cryptography  # noqa: F401
            _crypto = 'available'
        except Exception:
            _crypto = 'MISSING (install cryptography)'
        _banner_items.append(('encryption', _crypto))

        # LAN access — reflects the ALLOW_LAN env var. Actual bind host
        # is chosen by start.bat; this log entry lets the operator know
        # what the app believes its posture to be.
        _allow_lan = (os.getenv('ALLOW_LAN') or '0').strip().lower() in ('1', 'true', 'yes')
        _banner_items.append(('lan_access', 'ENABLED' if _allow_lan
                              else 'disabled (127.0.0.1 only)'))

        # Schema drift posture — strict mode flips boot behaviour.
        _strict = (os.getenv('SCHEMA_STRICT') or '').strip().lower() in ('1', 'true', 'yes')
        _banner_items.append(('schema_drift_mode',
                              'STRICT (boot will abort on drift)' if _strict
                              else 'warn-only'))

        # Put each on its own line so nothing gets truncated by the 120-char
        # console width; pick the right severity — if anything unexpected,
        # use WARNING so it pops in log aggregators.
        _any_warn = _env != 'production' or _crypto.startswith('MISSING') \
                    or 'NO PUBKEY' in _banner_items[2][1] \
                    or _allow_lan  # LAN is not a defect but worth visibility
        # v2.2.12: ASCII-only banner. Unicode box-drawing dashes render
        # badly when operators tail logs/pms.log on Windows consoles or
        # copy fragments into PowerShell / cmd. Plain ASCII keeps the
        # banner legible everywhere.
        logger.log(logging.WARNING if _any_warn else logging.INFO,
                   '------- SECURITY MODE -------')
        for _k, _v in _banner_items:
            logger.log(logging.WARNING if _any_warn else logging.INFO,
                       '  %-18s : %s', _k, _v)
        logger.log(logging.WARNING if _any_warn else logging.INFO,
                   '-----------------------------')
    except Exception as _banner_err:
        # Banner failure must never block boot — we already have the key
        # startup logs above this block.
        logger.debug('security banner failed: %s', _banner_err)

    # Session security
    from datetime import timedelta
    is_https = is_production
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SECURE'] = is_https   # HTTPS only in production
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(hours=12)
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = is_https

    from app.models import db
    db.init_app(app)
    migrate.init_app(app, db)

    # CSRF protection
    csrf.init_app(app)

    # Rate limiter setup
    limiter.init_app(app)

    # Flask-Login setup
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access the system.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    with app.app_context():
        from app import routes
        from app.auth import auth_bp
        from app.booking import booking_bp
        from app.webhook import webhook_bp
        from app.rates import rates_bp
        from app.pos import pos_bp
        from app.maintenance import maintenance_bp
        from app.reports import reports_bp
        from app.portal import portal_bp
        from app.noshow import noshow_bp
        from app.billing import billing_bp
        from app.backup import backup_bp
        from app.feedback import feedback_bp
        from app.ota import ota_bp
        from app.updater import updater_bp
        from app.admin_reset import admin_reset_bp
        from app.folio import folio_bp
        from app.groups import groups_bp
        from app.ai_pricing import ai_pricing_bp
        from app.ai_routes import ai_bp
        app.register_blueprint(routes.bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(booking_bp)      # public: /book
        app.register_blueprint(webhook_bp)      # public: /webhook
        csrf.exempt(webhook_bp)                 # webhook uses X-API-Key, not browser sessions
        # feedback_bp: CSRF enabled for staff routes (send_link, dashboard);
        # only feedback.submit is individually exempted in feedback.py (guest token-auth, no session)
        app.register_blueprint(rates_bp)        # staff: /rates
        app.register_blueprint(pos_bp)          # staff: /pos
        app.register_blueprint(maintenance_bp)  # staff: /maintenance
        app.register_blueprint(reports_bp)      # staff: /reports
        app.register_blueprint(portal_bp)       # public+staff: /portal
        app.register_blueprint(noshow_bp)       # staff: /noshow
        app.register_blueprint(billing_bp)      # staff: /billing (GST + void)
        app.register_blueprint(backup_bp)       # admin: /backup
        app.register_blueprint(feedback_bp)     # public+staff: /feedback
        app.register_blueprint(ota_bp)          # staff: /ota
        app.register_blueprint(updater_bp)      # admin: /admin/update
        app.register_blueprint(admin_reset_bp)  # admin: /admin/reset-transactional-data
        app.register_blueprint(folio_bp)        # staff: /api (folio split billing)
        app.register_blueprint(groups_bp)       # staff: /groups (group reservations)
        app.register_blueprint(ai_pricing_bp)   # staff: /ai/pricing (dynamic pricing)
        app.register_blueprint(ai_bp)           # staff: /ai/forecast, /ai/demand-calendar, /ai/anomalies, /ai/sentiment

        from app.loyalty import loyalty_bp
        app.register_blueprint(loyalty_bp)      # staff: /loyalty (loyalty program)

        from app.grc import grc_bp
        app.register_blueprint(grc_bp)          # staff: /grc (guest registration card)

        # Demo data CLI  (flask seed / flask unseed)
        from app.seed import seed_command, unseed_command
        app.cli.add_command(seed_command)
        app.cli.add_command(unseed_command)

        # Custom error pages (prevent Flask default from leaking debug info)
        from flask import render_template as _rt
        @app.errorhandler(404)
        def not_found(e):
            return _rt('errors/404.html'), 404

        @app.errorhandler(500)
        def server_error(e):
            db.session.rollback()
            logger.error('Internal server error: %s', e, exc_info=True)
            return _rt('errors/500.html'), 500

        @app.errorhandler(403)
        def forbidden(e):
            return _rt('errors/403.html'), 403

        # Generate a fresh per-request CSP nonce (stored on Flask g)
        import secrets as _secrets_mod
        from flask import g as _g

        @app.before_request
        def _generate_csp_nonce():
            _g.csp_nonce = _secrets_mod.token_hex(16)

        # Security headers for every response
        @app.after_request
        def set_security_headers(response):
            nonce = getattr(_g, 'csp_nonce', _secrets_mod.token_hex(16))
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(self)'
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "frame-ancestors 'self';"
            )
            if is_https:
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            return response

        # Context processor — pending badges + now() + version + CSP nonce for templates
        # ── Jinja filters (Apr 2026 — guest-facing rounding) ─────────
        # `inr` renders amounts as whole-rupee strings using commercial
        # rounding (149.50 → 150, 149.49 → 149) with thousands commas.
        # Used on all guest-facing invoice surfaces so paise never bleed
        # through to printed bills.
        def _inr_filter(value, default='0'):
            try:
                v = float(value)
            except (TypeError, ValueError):
                return default
            # Commercial rounding (NOT banker's): add a sign-correct epsilon.
            sign = -1 if v < 0 else 1
            rounded = int(abs(v) + 0.5) * sign
            return f'{rounded:,}'

        def _inr_round_filter(value):
            """Same rounding rule as ``inr`` but returns the integer (not a string)."""
            try:
                v = float(value)
            except (TypeError, ValueError):
                return 0
            sign = -1 if v < 0 else 1
            return int(abs(v) + 0.5) * sign

        app.jinja_env.filters['inr']       = _inr_filter
        app.jinja_env.filters['inr_round'] = _inr_round_filter

        @app.context_processor
        def inject_global_context():
            from datetime import datetime as _dt
            from flask import g as _fg, url_for as _uf, current_app as _ca
            import os as _os
            ctx = {'now': _dt.utcnow, 'pending_void_count': 0,
                   'pending_shift_count': 0, 'app_version': APP_VERSION,
                   'csp_nonce': getattr(_fg, 'csp_nonce', ''),
                   'dev_seed_enabled': (
                       _os.getenv('FLASK_ENV') == 'development'
                       and _os.getenv('ENABLE_DEV_SEED') == '1')}
            try:
                from flask_login import current_user as _cu
                from app.models import VoidRequest as _VR, Shift as _Shift, Settings as _Sett, BusinessDate as _BD
                if _cu.is_authenticated and _cu.role in ('Admin', 'Manager'):
                    ctx['pending_void_count'] = _VR.query.filter_by(status='Pending').count()
                    ctx['pending_shift_count'] = _Shift.query.filter_by(status='PendingApproval').count()
                # Business date — available globally for header/dashboard
                _bd_row = _BD.query.first()
                if _bd_row:
                    ctx['g_business_date'] = _bd_row.current_date
                    ctx['g_business_date_locked'] = _bd_row.is_locked
                # App branding — global product identity + property name
                _an = _Sett.query.filter_by(key='app_name').first()
                _al = _Sett.query.filter_by(key='app_logo_filename').first()
                _hn = _Sett.query.filter_by(key='hotel_name').first()
                # Global app name: use stored app_name, default to "FinalGrid"
                ctx['app_display_name'] = (
                    _an.value.strip() if _an and _an.value and _an.value.strip()
                    else 'FinalGrid'
                )
                ctx['app_logo_url'] = (_uf('static', filename='uploads/' + _al.value) if _al and _al.value else None)
                # Property name: from hotel_name setting, fallback to HOTEL_NAME config
                ctx['property_name'] = (
                    _hn.value.strip() if _hn and _hn.value and _hn.value.strip()
                    else _ca.config.get('HOTEL_NAME', '')
                )
            except Exception:
                ctx.setdefault('app_display_name', 'FinalGrid')
                ctx.setdefault('app_logo_url', None)
                ctx.setdefault('property_name', app.config.get('HOTEL_NAME', ''))
            return ctx

        # ── Schema bootstrap — gated db.create_all() ─────────────────────
        # Silent db.create_all() on every boot hides schema drift: a model
        # added without a matching migration will be created in dev but
        # never in prod, leading to divergent schemas. Gate the call so it
        # only runs when we KNOW it is safe:
        #   - FLASK_ENV=development    (dev convenience)
        #   - DB_AUTO_CREATE=1         (explicit opt-in for fresh install)
        #   - the target DB is empty   (first boot — must bootstrap)
        # Otherwise we skip it and emit a drift warning if any expected
        # table is missing, so operators know a migration is required.
        _auto_create_env = (os.getenv('DB_AUTO_CREATE') or '').strip().lower() in ('1', 'true', 'yes')
        _is_dev = _env_mode() == 'development'
        try:
            from sqlalchemy import inspect as _sa_inspect
            _insp = _sa_inspect(db.engine)
            _existing_tables = set(_insp.get_table_names())
        except Exception as _insp_err:
            logger.warning('Could not inspect DB tables: %s', _insp_err)
            _existing_tables = set()
        _db_is_empty = len(_existing_tables) == 0

        if _is_dev or _auto_create_env or _db_is_empty:
            reason = ('development' if _is_dev else
                      'DB_AUTO_CREATE=1' if _auto_create_env else
                      'empty database (first boot)')
            logger.info('db.create_all() enabled (reason: %s)', reason)
            db.create_all()
        else:
            logger.info(
                'db.create_all() skipped in production. '
                'Use Alembic migrations for schema changes. '
                'Set DB_AUTO_CREATE=1 to force-enable at next boot.'
            )

        _run_pending_migrations(app)  # must run before init_data so new columns exist

        # ── Schema drift detection (post-migration) ──────────────────────
        # Compare what models.py declares vs what the DB actually has.
        # Default: log a WARNING so operators notice without blocking boot.
        # Strict mode (SCHEMA_STRICT=1): raise a RuntimeError so QA /
        # staging environments can't silently start with a stale schema —
        # the CI pipeline fails instead of deploying broken code.
        _strict = (os.getenv('SCHEMA_STRICT') or '').strip().lower() in ('1', 'true', 'yes')
        try:
            from sqlalchemy import inspect as _sa_inspect2
            _insp2 = _sa_inspect2(db.engine)
            _db_tables_now = set(_insp2.get_table_names())
            _model_tables = set(db.metadata.tables.keys())
            _missing_in_db = _model_tables - _db_tables_now
            if _missing_in_db:
                _msg = (
                    f'SCHEMA DRIFT: {len(_missing_in_db)} table(s) in '
                    f'models.py but missing in DB: {sorted(_missing_in_db)}. '
                    f'Run Alembic migrations to sync.'
                )
                if _strict:
                    # Strict mode — refuse to boot. Used in staging/QA
                    # where a missing table = broken deploy.
                    raise RuntimeError(
                        f'{_msg} SCHEMA_STRICT=1 is set — refusing to start. '
                        f'Run `flask db upgrade` or unset SCHEMA_STRICT to '
                        f'downgrade to a warning.'
                    )
                logger.warning(_msg)
        except RuntimeError:
            # Re-raise the strict-mode bail-out.
            raise
        except Exception as _drift_err:
            # Inspection itself failed (e.g. unreachable DB). Strict mode
            # still surfaces that; warn otherwise.
            if _strict:
                raise RuntimeError(
                    f'Schema drift check failed under SCHEMA_STRICT=1: {_drift_err}'
                )
            logger.warning('Schema drift check failed: %s', _drift_err)

        init_data()

        # Setup night audit scheduler with graceful shutdown
        from app.services import setup_night_audit_scheduler, scheduler as _sched
        setup_night_audit_scheduler(app)

        # Setup daily backup scheduler
        from app.backup_manager import setup_backup_scheduler
        setup_backup_scheduler(app, _sched)

        # Notification retry queue — flush pending notifications every 5 minutes
        from app.notifications import flush_notification_queue
        _sched.add_job(
            flush_notification_queue, 'interval', minutes=5,
            args=[app], id='notification_queue_flush',
            replace_existing=True, misfire_grace_time=120,
        )

        # Log table pruning — daily at 04:00, keep 90 days of logs
        def _prune_old_logs():
            with app.app_context():
                from app.models import db, AuditLog, WebhookLog, NotificationLog
                from datetime import datetime, timedelta
                cutoff = datetime.utcnow() - timedelta(days=90)
                try:
                    deleted = 0
                    for LogModel, ts_col in [
                        (AuditLog, AuditLog.timestamp),
                        (WebhookLog, WebhookLog.received_at),
                        (NotificationLog, NotificationLog.sent_at),
                    ]:
                        count = LogModel.query.filter(ts_col < cutoff).delete()
                        deleted += count
                    db.session.commit()
                    if deleted:
                        logger.info('Pruned %d old log entries (older than 90 days)', deleted)
                except Exception as e:
                    db.session.rollback()
                    logger.error('Log pruning failed: %s', e)

        _sched.add_job(
            _prune_old_logs, 'cron', hour=4, minute=0,
            id='log_pruning_job', replace_existing=True,
            misfire_grace_time=3600,
        )

        # Predictive maintenance — daily at 05:00, snapshot health + generate schedules
        def _run_predictive_maintenance():
            with app.app_context():
                try:
                    from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
                    from app.models import db, PreventiveSchedule
                    from datetime import date as _date
                    engine = PredictiveMaintenanceEngine()
                    snap = engine.snapshot_health_scores()
                    logger.info('Predictive maintenance: snapshotted %d health scores', snap)
                    result = engine.generate_preventive_schedules(days_ahead=30)
                    logger.info('Predictive maintenance: %d new schedules, %d existing',
                                result['created'], result['existing'])
                    overdue = PreventiveSchedule.query.filter(
                        PreventiveSchedule.status == 'Pending',
                        PreventiveSchedule.scheduled_date < _date.today(),
                    ).update({'status': 'Overdue'})
                    if overdue:
                        db.session.commit()
                        logger.info('Predictive maintenance: marked %d schedules overdue', overdue)
                except Exception as e:
                    logger.error('Predictive maintenance job failed: %s', e)

        _sched.add_job(
            _run_predictive_maintenance, 'cron', hour=5, minute=0,
            id='predictive_maintenance_job', replace_existing=True,
            misfire_grace_time=3600,
        )

        import atexit
        atexit.register(lambda: _sched.shutdown(wait=False) if _sched.running else None)

    return app

def _run_pending_migrations(app):
    """
    Lightweight schema migration runner.
    Each migration is a (version, description, sql) tuple.
    Applied migrations are tracked in the schema_migrations table.
    Safe to run on every startup — skips already-applied migrations.
    """
    from app.models import db
    _is_sqlite = app.config.get('DB_IS_SQLITE', False)
    # Ensure tracking table exists
    with app.app_context():
        _ts_default = 'CURRENT_TIMESTAMP' if _is_sqlite else 'NOW()'
        db.session.execute(db.text(f"""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(20) PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMP DEFAULT {_ts_default}
            )
        """))
        db.session.commit()

        # --- Migration registry ---
        # Add new migrations here as tuples: (version, description, sql)
        # NOTE: Migrations using DO $$ ... END $$ are PostgreSQL-only and
        # are skipped on SQLite (db.create_all() handles schema there).
        migrations = [
            ('1.0.1', 'Add booking_reference index',
             'CREATE INDEX IF NOT EXISTS idx_reservations_booking_ref ON reservations(booking_reference)'),
            ('1.0.2', 'Add noshow_exempt column if missing',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='noshow_exempt')
                THEN ALTER TABLE reservations ADD COLUMN noshow_exempt BOOLEAN DEFAULT FALSE NOT NULL;
                END IF; END $$"""),
            ('1.0.3', 'Add billing_state_code column if missing',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='billing_state_code')
                THEN ALTER TABLE reservations ADD COLUMN billing_state_code VARCHAR(2);
                END IF; END $$"""),
            ('1.0.4', 'Add ota_booking_id column if missing',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='ota_booking_id')
                THEN ALTER TABLE reservations ADD COLUMN ota_booking_id VARCHAR(100);
                END IF; END $$"""),
            ('1.1.0', 'Add guest_feedback table',
             """CREATE TABLE IF NOT EXISTS guest_feedback (
                id SERIAL PRIMARY KEY,
                reservation_id INTEGER NOT NULL UNIQUE REFERENCES reservations(id),
                rating INTEGER NOT NULL DEFAULT 0,
                cleanliness INTEGER, service INTEGER, food INTEGER, value INTEGER,
                comment TEXT, would_recommend BOOLEAN,
                google_review_pushed BOOLEAN DEFAULT FALSE,
                negative_flag BOOLEAN DEFAULT FALSE,
                source VARCHAR(20) DEFAULT 'whatsapp_link',
                token VARCHAR(64) UNIQUE,
                submitted_at TIMESTAMP DEFAULT NOW(),
                ip_address VARCHAR(45)
             )"""),
            ('1.1.1', 'Add backup_logs table',
             """CREATE TABLE IF NOT EXISTS backup_logs (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(200) NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                backup_type VARCHAR(20) DEFAULT 'manual',
                status VARCHAR(20) DEFAULT 'success',
                error_message TEXT,
                created_by_user_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
             )"""),
            ('1.2.0', 'Add phone length extension for guests',
             """DO $$ BEGIN
                ALTER TABLE guests ALTER COLUMN phone TYPE VARCHAR(20);
             EXCEPTION WHEN others THEN NULL; END $$"""),
            ('1.2.1', 'Seed cloudflare_tunnel_url setting',
             """INSERT INTO settings(key, value, description)
                VALUES('cloudflare_tunnel_url', '', 'Cloudflare tunnel public URL for webhook endpoint')
                ON CONFLICT (key) DO NOTHING"""),
            ('1.2.2', 'Add head_office, business_category, vendor_code_generated to companies',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='companies' AND column_name='head_office')
                THEN ALTER TABLE companies ADD COLUMN head_office VARCHAR(200); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='companies' AND column_name='business_category')
                THEN ALTER TABLE companies ADD COLUMN business_category VARCHAR(100); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='companies' AND column_name='vendor_code_generated')
                THEN ALTER TABLE companies ADD COLUMN vendor_code_generated BOOLEAN DEFAULT FALSE; END IF;
             END $$"""),
            ('1.3.1', 'Add override, cash, and stage tracking fields to night_audit_logs + reopen log table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='started_by_user_id')
                THEN ALTER TABLE night_audit_logs ADD COLUMN started_by_user_id INTEGER REFERENCES users(id); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='started_at')
                THEN ALTER TABLE night_audit_logs ADD COLUMN started_at TIMESTAMP; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='override_used')
                THEN ALTER TABLE night_audit_logs ADD COLUMN override_used BOOLEAN DEFAULT FALSE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='override_reason')
                THEN ALTER TABLE night_audit_logs ADD COLUMN override_reason TEXT; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='expected_cash')
                THEN ALTER TABLE night_audit_logs ADD COLUMN expected_cash NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='actual_cash')
                THEN ALTER TABLE night_audit_logs ADD COLUMN actual_cash NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='cash_variance')
                THEN ALTER TABLE night_audit_logs ADD COLUMN cash_variance NUMERIC(12,2) DEFAULT 0; END IF;
                CREATE TABLE IF NOT EXISTS night_audit_reopen_logs (
                    id SERIAL PRIMARY KEY,
                    audit_log_id INTEGER NOT NULL REFERENCES night_audit_logs(id),
                    audit_date DATE NOT NULL,
                    reopened_by_user_id INTEGER NOT NULL REFERENCES users(id),
                    reopened_at TIMESTAMP DEFAULT NOW(),
                    reason TEXT NOT NULL,
                    previous_status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_nar_audit_date ON night_audit_reopen_logs(audit_date);
             END $$"""),
            ('1.2.3', 'Add performance indexes on hot query paths',
             """DO $$ BEGIN
                -- Reservations: status, date range, room_type (most-queried columns)
                CREATE INDEX IF NOT EXISTS idx_res_status       ON reservations(status);
                CREATE INDEX IF NOT EXISTS idx_res_arrival      ON reservations(arrival_date);
                CREATE INDEX IF NOT EXISTS idx_res_departure    ON reservations(departure_date);
                CREATE INDEX IF NOT EXISTS idx_res_dates        ON reservations(arrival_date, departure_date);
                CREATE INDEX IF NOT EXISTS idx_res_room_type    ON reservations(room_type_id, status);
                -- Payments: date (reconciliation) and voided flag (folio balance)
                CREATE INDEX IF NOT EXISTS idx_pay_date         ON payments(payment_date);
                CREATE INDEX IF NOT EXISTS idx_pay_voided       ON payments(is_voided);
                CREATE INDEX IF NOT EXISTS idx_pay_reservation  ON payments(reservation_id);
                -- Shifts: user + status (cashier lookup)
                CREATE INDEX IF NOT EXISTS idx_shifts_user      ON shifts(user_id, status);
                -- Night audit: audit_date + status (lock guard)
                CREATE INDEX IF NOT EXISTS idx_nal_date_status  ON night_audit_logs(audit_date, status);
                -- Extra charges: charge_date (night audit revenue)
                CREATE INDEX IF NOT EXISTS idx_ec_date          ON extra_charges(charge_date);
             END $$"""),
            ('1.3.2', 'Add overstay_billed_until to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='overstay_billed_until')
                THEN ALTER TABLE reservations ADD COLUMN overstay_billed_until TIMESTAMP;
                END IF; END $$"""),
            ('1.3.3', 'Add invoice_number to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='invoice_number')
                THEN ALTER TABLE reservations ADD COLUMN invoice_number VARCHAR(50);
                END IF;
                CREATE INDEX IF NOT EXISTS idx_res_invoice_no ON reservations(invoice_number);
             END $$"""),
            ('1.3.0', 'Extend night_audit_logs with full audit tracking fields',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='status')
                THEN ALTER TABLE night_audit_logs ADD COLUMN status VARCHAR(20) DEFAULT 'Pending'; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='run_by_user_id')
                THEN ALTER TABLE night_audit_logs ADD COLUMN run_by_user_id INTEGER REFERENCES users(id); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='completed_at')
                THEN ALTER TABLE night_audit_logs ADD COLUMN completed_at TIMESTAMP; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='total_payments')
                THEN ALTER TABLE night_audit_logs ADD COLUMN total_payments NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='outstanding_amount')
                THEN ALTER TABLE night_audit_logs ADD COLUMN outstanding_amount NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='reconciliation_difference')
                THEN ALTER TABLE night_audit_logs ADD COLUMN reconciliation_difference NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='blocker_count')
                THEN ALTER TABLE night_audit_logs ADD COLUMN blocker_count INTEGER DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='warning_count')
                THEN ALTER TABLE night_audit_logs ADD COLUMN warning_count INTEGER DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='reopen_reason')
                THEN ALTER TABLE night_audit_logs ADD COLUMN reopen_reason TEXT; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='snapshot_json')
                THEN ALTER TABLE night_audit_logs ADD COLUMN snapshot_json TEXT; END IF;
             END $$"""),
            ('2.0.0', 'Add tariff adjustment fields to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='standard_tariff')
                THEN ALTER TABLE reservations ADD COLUMN standard_tariff NUMERIC(10,2); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='adjustment_type')
                THEN ALTER TABLE reservations ADD COLUMN adjustment_type VARCHAR(10); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='adjustment_amount')
                THEN ALTER TABLE reservations ADD COLUMN adjustment_amount NUMERIC(10,2) DEFAULT 0; END IF;
             END $$"""),
            ('2.0.1', 'Add discount fields to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='discount_amount')
                THEN ALTER TABLE reservations ADD COLUMN discount_amount NUMERIC(10,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='discount_reason')
                THEN ALTER TABLE reservations ADD COLUMN discount_reason VARCHAR(50); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='discount_authorized_by')
                THEN ALTER TABLE reservations ADD COLUMN discount_authorized_by VARCHAR(100); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='discount_given_by')
                THEN ALTER TABLE reservations ADD COLUMN discount_given_by VARCHAR(100); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='discount_at')
                THEN ALTER TABLE reservations ADD COLUMN discount_at TIMESTAMP; END IF;
             END $$"""),
            ('2.0.2', 'Add checkin_by and checkout_by staff attribution to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='checkin_by')
                THEN ALTER TABLE reservations ADD COLUMN checkin_by VARCHAR(100); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='checkout_by')
                THEN ALTER TABLE reservations ADD COLUMN checkout_by VARCHAR(100); END IF;
             END $$"""),
            ('2.1.0', 'Add expected_tariff and leakage_reason to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='expected_tariff')
                THEN ALTER TABLE reservations ADD COLUMN expected_tariff NUMERIC(10,2); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='leakage_reason')
                THEN ALTER TABLE reservations ADD COLUMN leakage_reason VARCHAR(200); END IF;
             END $$"""),
            ('2.1.1', 'Create revenue_alerts table',
             """DO $$ BEGIN
                CREATE TABLE IF NOT EXISTS revenue_alerts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    reservation_id INTEGER REFERENCES reservations(id),
                    alert_type VARCHAR(30) NOT NULL,
                    severity VARCHAR(10) NOT NULL DEFAULT 'MEDIUM',
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    resolved BOOLEAN NOT NULL DEFAULT FALSE,
                    resolved_at TIMESTAMP,
                    resolved_by_user_id INTEGER REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_rev_alert_user     ON revenue_alerts(user_id);
                CREATE INDEX IF NOT EXISTS idx_rev_alert_type     ON revenue_alerts(alert_type);
                CREATE INDEX IF NOT EXISTS idx_rev_alert_resolved ON revenue_alerts(resolved);
                CREATE INDEX IF NOT EXISTS idx_rev_alert_created  ON revenue_alerts(created_at);
             END $$"""),
            ('2.1.2', 'Create staff_performance_daily table',
             """DO $$ BEGIN
                CREATE TABLE IF NOT EXISTS staff_performance_daily (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    date DATE NOT NULL,
                    rooms_handled INTEGER DEFAULT 0,
                    total_revenue NUMERIC(12,2) DEFAULT 0,
                    total_leakage NUMERIC(12,2) DEFAULT 0,
                    total_discount NUMERIC(12,2) DEFAULT 0,
                    total_upsell NUMERIC(12,2) DEFAULT 0,
                    net_score NUMERIC(12,2) DEFAULT 0,
                    rank INTEGER,
                    flag VARCHAR(20),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_staff_perf_user_date UNIQUE(user_id, date)
                );
                CREATE INDEX IF NOT EXISTS idx_staff_perf_date ON staff_performance_daily(date);
                CREATE INDEX IF NOT EXISTS idx_staff_perf_user ON staff_performance_daily(user_id);
             END $$"""),
            ('2.1.3', 'Seed Revenue Intelligence Engine config settings',
             """INSERT INTO settings(key, value, description) VALUES
                ('MAX_DISCOUNT_WITHOUT_APPROVAL', '1000',
                 'Max discount (₹) allowed without verifying manager/admin authoriser')
                ON CONFLICT (key) DO NOTHING;
                INSERT INTO settings(key, value, description) VALUES
                ('LEAKAGE_ALERT_THRESHOLD', '3000',
                 'Single-reservation leakage (₹) that fires a HIGH_LEAKAGE alert')
                ON CONFLICT (key) DO NOTHING;
                INSERT INTO settings(key, value, description) VALUES
                ('DISCOUNT_ALERT_THRESHOLD', '1000',
                 'Single discount (₹) that fires a HIGH_DISCOUNT alert')
                ON CONFLICT (key) DO NOTHING;
                INSERT INTO settings(key, value, description) VALUES
                ('REPEAT_DISCOUNT_COUNT', '3',
                 'How many discounts by same user within the time window triggers REPEATED_DISCOUNT')
                ON CONFLICT (key) DO NOTHING;
                INSERT INTO settings(key, value, description) VALUES
                ('REPEAT_TIME_WINDOW_MINUTES', '120',
                 'Sliding time window (minutes) for repeat-discount detection')
                ON CONFLICT (key) DO NOTHING;
             """),
            ('2.2.0', 'Add extended fields to rooms table for Rooms Master',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='room_name')
                THEN ALTER TABLE rooms ADD COLUMN room_name VARCHAR(100); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='wing')
                THEN ALTER TABLE rooms ADD COLUMN wing VARCHAR(50); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='max_adults')
                THEN ALTER TABLE rooms ADD COLUMN max_adults INTEGER NOT NULL DEFAULT 2; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='max_children')
                THEN ALTER TABLE rooms ADD COLUMN max_children INTEGER NOT NULL DEFAULT 2; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='extra_bed_allowed')
                THEN ALTER TABLE rooms ADD COLUMN extra_bed_allowed BOOLEAN NOT NULL DEFAULT FALSE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='is_active')
                THEN ALTER TABLE rooms ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='is_sellable')
                THEN ALTER TABLE rooms ADD COLUMN is_sellable BOOLEAN NOT NULL DEFAULT TRUE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='is_out_of_order')
                THEN ALTER TABLE rooms ADD COLUMN is_out_of_order BOOLEAN NOT NULL DEFAULT FALSE; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='maintenance_note')
                THEN ALTER TABLE rooms ADD COLUMN maintenance_note TEXT; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='sort_order')
                THEN ALTER TABLE rooms ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='created_at')
                THEN ALTER TABLE rooms ADD COLUMN created_at TIMESTAMP DEFAULT NOW(); END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='rooms' AND column_name='updated_at')
                THEN ALTER TABLE rooms ADD COLUMN updated_at TIMESTAMP DEFAULT NOW(); END IF;
             END $$"""),
            ('2.2.1', 'Add is_gst_inclusive to room_types for GST-inclusive pricing support',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='room_types' AND column_name='is_gst_inclusive')
                THEN ALTER TABLE room_types ADD COLUMN is_gst_inclusive BOOLEAN NOT NULL DEFAULT FALSE; END IF;
             END $$"""),
            ('2.3.0', 'Add notification_queue table for offline retry',
             """CREATE TABLE IF NOT EXISTS notification_queue (
                id SERIAL PRIMARY KEY,
                channel VARCHAR(20) NOT NULL,
                recipient VARCHAR(200) NOT NULL,
                subject VARCHAR(200),
                body TEXT NOT NULL,
                message_type VARCHAR(50) NOT NULL,
                reservation_id INTEGER REFERENCES reservations(id),
                status VARCHAR(20) DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 10,
                next_retry_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
             )"""),
            ('2.3.1', 'Add unique index on reservation invoice_number',
             """CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_invoice_number
                ON reservations(invoice_number)"""),
            ('2.4.0', 'Add net_revenue, total_discount, accrual_revenue to night_audit_logs',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='net_revenue')
                THEN ALTER TABLE night_audit_logs ADD COLUMN net_revenue NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='total_discount')
                THEN ALTER TABLE night_audit_logs ADD COLUMN total_discount NUMERIC(12,2) DEFAULT 0; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='night_audit_logs' AND column_name='accrual_revenue')
                THEN ALTER TABLE night_audit_logs ADD COLUMN accrual_revenue NUMERIC(12,2) DEFAULT 0; END IF;
             END $$"""),
            ('2.5.0', 'Add charge_category to extra_charges for GST calculation',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='extra_charges' AND column_name='charge_category')
                THEN ALTER TABLE extra_charges ADD COLUMN charge_category VARCHAR(30); END IF;
             END $$"""),
            ('2.6.0', 'Add account lockout fields to users table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='failed_login_count')
                THEN
                    ALTER TABLE users ADD COLUMN failed_login_count INTEGER DEFAULT 0 NOT NULL;
                    ALTER TABLE users ADD COLUMN locked_until TIMESTAMP;
                END IF;
             END $$"""),
            ('2.6.1', 'Add FK constraint on checkin_records.staff_user_id',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name='fk_checkin_staff_user')
                THEN
                    ALTER TABLE checkin_records ADD CONSTRAINT fk_checkin_staff_user
                        FOREIGN KEY (staff_user_id) REFERENCES users(id);
                END IF;
             END $$"""),
            ('3.0.0', 'Add folios table and folio_id to extra_charges and payments for split billing',
             """DO $$ BEGIN
                -- Create folios table
                CREATE TABLE IF NOT EXISTS folios (
                    id SERIAL PRIMARY KEY,
                    reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                    folio_letter VARCHAR(1) NOT NULL DEFAULT 'A',
                    label VARCHAR(50) DEFAULT 'Guest',
                    company_id INTEGER REFERENCES companies(id),
                    is_closed BOOLEAN DEFAULT FALSE,
                    closed_at TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_folio_letter UNIQUE(reservation_id, folio_letter)
                );
                CREATE INDEX IF NOT EXISTS idx_folio_reservation_id ON folios(reservation_id);
                -- Add folio_id to extra_charges
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='extra_charges' AND column_name='folio_id')
                THEN ALTER TABLE extra_charges ADD COLUMN folio_id INTEGER REFERENCES folios(id);
                END IF;
                -- Add folio_id to payments
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='payments' AND column_name='folio_id')
                THEN ALTER TABLE payments ADD COLUMN folio_id INTEGER REFERENCES folios(id);
                END IF;
             END $$"""),
            ('3.1.0', 'Add group_blocks table and group_block_id to reservations',
             """DO $$ BEGIN
                CREATE TABLE IF NOT EXISTS group_blocks (
                    id SERIAL PRIMARY KEY,
                    group_name VARCHAR(200) NOT NULL,
                    group_code VARCHAR(20) NOT NULL UNIQUE,
                    contact_name VARCHAR(100),
                    contact_phone VARCHAR(20),
                    contact_email VARCHAR(100),
                    company_id INTEGER REFERENCES companies(id),
                    arrival_date DATE NOT NULL,
                    departure_date DATE NOT NULL,
                    total_rooms INTEGER NOT NULL DEFAULT 1,
                    group_rate NUMERIC(10,2),
                    status VARCHAR(20) DEFAULT 'Tentative',
                    billing_instructions TEXT,
                    notes TEXT,
                    created_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT ck_group_status CHECK (status IN ('Tentative','Confirmed','Cancelled','Completed'))
                );
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='group_block_id')
                THEN ALTER TABLE reservations ADD COLUMN group_block_id INTEGER REFERENCES group_blocks(id);
                END IF;
             END $$"""),
            ('3.2.0', 'Add credit_notes table and credit_note_counter setting',
             """CREATE TABLE IF NOT EXISTS credit_notes (
                id SERIAL PRIMARY KEY,
                credit_note_number VARCHAR(30) NOT NULL UNIQUE,
                reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                original_invoice_number VARCHAR(50) NOT NULL,
                reason VARCHAR(200) NOT NULL,
                taxable_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                cgst_amount NUMERIC(10,2) DEFAULT 0,
                sgst_amount NUMERIC(10,2) DEFAULT 0,
                igst_amount NUMERIC(10,2) DEFAULT 0,
                total_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                issued_by_user_id INTEGER NOT NULL REFERENCES users(id),
                issued_at TIMESTAMP DEFAULT NOW(),
                notes TEXT
             );
             CREATE INDEX IF NOT EXISTS idx_creditnote_reservation ON credit_notes(reservation_id);
             CREATE INDEX IF NOT EXISTS idx_creditnote_issued_at ON credit_notes(issued_at);
             INSERT INTO settings(key, value, description)
                VALUES('credit_note_counter', '0', 'Running sequential credit note counter')
                ON CONFLICT (key) DO NOTHING"""),
            ('3.3.0', 'Add VIP and market segment fields',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='guests' AND column_name='vip_level')
                THEN
                    ALTER TABLE guests ADD COLUMN vip_level VARCHAR(5);
                    ALTER TABLE guests ADD COLUMN loyalty_number VARCHAR(30);
                    ALTER TABLE guests ADD COLUMN guest_notes TEXT;
                    ALTER TABLE guests ADD COLUMN total_stays INTEGER DEFAULT 0;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='market_segment')
                THEN
                    ALTER TABLE reservations ADD COLUMN market_segment VARCHAR(30);
                END IF;
             END $$"""),
            ('4.0.0', 'Add equipment table for predictive maintenance',
             """CREATE TABLE IF NOT EXISTS equipment (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                name VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                manufacturer VARCHAR(100),
                model_number VARCHAR(100),
                install_date DATE,
                expected_life_years FLOAT DEFAULT 10.0,
                last_service_date DATE,
                service_interval_days INTEGER DEFAULT 180,
                is_active BOOLEAN DEFAULT TRUE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
             );
             CREATE INDEX IF NOT EXISTS idx_equipment_room_cat ON equipment(room_id, category)"""),
            ('4.0.1', 'Add preventive_schedules table',
             """CREATE TABLE IF NOT EXISTS preventive_schedules (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                equipment_id INTEGER REFERENCES equipment(id),
                category VARCHAR(50) NOT NULL,
                task_description TEXT NOT NULL,
                scheduled_date DATE NOT NULL,
                status VARCHAR(15) DEFAULT 'Pending',
                priority VARCHAR(10) DEFAULT 'Medium',
                risk_level VARCHAR(10),
                predicted_failure_probability FLOAT,
                assigned_to VARCHAR(100),
                completed_at TIMESTAMP,
                notes TEXT,
                source VARCHAR(20) DEFAULT 'auto',
                created_at TIMESTAMP DEFAULT NOW()
             );
             CREATE INDEX IF NOT EXISTS idx_prev_sched_date_status ON preventive_schedules(scheduled_date, status);
             CREATE INDEX IF NOT EXISTS idx_prev_sched_room ON preventive_schedules(room_id)"""),
            ('4.0.2', 'Add equipment_health_logs table',
             """CREATE TABLE IF NOT EXISTS equipment_health_logs (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                equipment_id INTEGER REFERENCES equipment(id),
                health_score FLOAT NOT NULL,
                category VARCHAR(50),
                risk_factors TEXT,
                snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT NOW()
             );
             CREATE INDEX IF NOT EXISTS idx_health_room_date ON equipment_health_logs(room_id, snapshot_date)"""),
            ('4.0.3', 'Add cost_estimate to maintenance_requests',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='maintenance_requests' AND column_name='cost_estimate')
                THEN ALTER TABLE maintenance_requests ADD COLUMN cost_estimate DECIMAL(10,2);
                END IF;
             END $$"""),
            ('5.0.0', 'Create loyalty_config table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='loyalty_config') THEN
                CREATE TABLE loyalty_config (
                    id SERIAL PRIMARY KEY,
                    tier_name VARCHAR(20) NOT NULL UNIQUE,
                    tier_order INTEGER NOT NULL DEFAULT 0,
                    min_points INTEGER NOT NULL DEFAULT 0,
                    earn_per_night INTEGER NOT NULL DEFAULT 10,
                    earn_per_100_rupees INTEGER NOT NULL DEFAULT 1,
                    direct_booking_bonus_pct INTEGER DEFAULT 20,
                    redemption_value DECIMAL(10,2) DEFAULT 0.50,
                    late_checkout_points INTEGER DEFAULT 500,
                    early_checkin_points INTEGER DEFAULT 300,
                    color_hex VARCHAR(7) DEFAULT '#6c757d',
                    is_active BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT ck_loyalty_tier_order_pos CHECK (tier_order > 0),
                    CONSTRAINT ck_loyalty_min_points_pos CHECK (min_points >= 0)
                );
                INSERT INTO loyalty_config (tier_name,tier_order,min_points,earn_per_night,earn_per_100_rupees,direct_booking_bonus_pct,redemption_value,late_checkout_points,early_checkin_points,color_hex)
                VALUES
                    ('Silver',1,0,10,1,10,0.25,500,300,'#6c757d'),
                    ('Gold',2,5000,15,2,15,0.40,400,250,'#ffc107'),
                    ('Platinum',3,15000,25,3,20,0.50,300,200,'#6f42c1');
                END IF;
             END $$"""),
            ('5.0.1', 'Create loyalty_milestones table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='loyalty_milestones') THEN
                CREATE TABLE loyalty_milestones (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    trigger_type VARCHAR(20) NOT NULL,
                    trigger_value INTEGER NOT NULL,
                    bonus_points INTEGER NOT NULL DEFAULT 100,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_recurring BOOLEAN DEFAULT FALSE
                );
                INSERT INTO loyalty_milestones (name,trigger_type,trigger_value,bonus_points,is_recurring)
                VALUES
                    ('5th Stay Bonus','stays',5,200,false),
                    ('10th Stay Bonus','stays',10,500,false),
                    ('20th Stay Bonus','stays',20,1000,false);
                END IF;
             END $$"""),
            ('5.0.2', 'Create loyalty_transactions table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='loyalty_transactions') THEN
                CREATE TABLE loyalty_transactions (
                    id SERIAL PRIMARY KEY,
                    guest_id INTEGER NOT NULL REFERENCES guests(id),
                    reservation_id INTEGER REFERENCES reservations(id),
                    txn_type VARCHAR(20) NOT NULL,
                    points INTEGER NOT NULL,
                    description VARCHAR(200) NOT NULL,
                    reference_amount DECIMAL(10,2),
                    tier_at_time VARCHAR(20),
                    created_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX idx_loyalty_txn_guest ON loyalty_transactions(guest_id);
                CREATE INDEX idx_loyalty_txn_reservation ON loyalty_transactions(reservation_id);
                CREATE INDEX idx_loyalty_txn_type ON loyalty_transactions(txn_type);
                CREATE INDEX idx_loyalty_txn_created ON loyalty_transactions(created_at);
                END IF;
             END $$"""),
            ('5.0.3', 'Create loyalty_redemptions table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='loyalty_redemptions') THEN
                CREATE TABLE loyalty_redemptions (
                    id SERIAL PRIMARY KEY,
                    guest_id INTEGER NOT NULL REFERENCES guests(id),
                    reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                    redemption_type VARCHAR(20) NOT NULL,
                    points_used INTEGER NOT NULL,
                    rupee_value DECIMAL(10,2) DEFAULT 0,
                    status VARCHAR(15) DEFAULT 'Applied',
                    transaction_id INTEGER REFERENCES loyalty_transactions(id),
                    applied_by_user_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                END IF;
             END $$"""),
            ('5.0.4', 'Add loyalty_tier column to guests',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='guests' AND column_name='loyalty_tier')
                THEN ALTER TABLE guests ADD COLUMN loyalty_tier VARCHAR(20) DEFAULT 'Silver';
                END IF;
             END $$"""),
            ('6.0.0', 'Add GRC guest fields (dob, gender, purpose)',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='guests' AND column_name='date_of_birth')
                THEN
                    ALTER TABLE guests ADD COLUMN date_of_birth DATE;
                    ALTER TABLE guests ADD COLUMN gender VARCHAR(10);
                    ALTER TABLE guests ADD COLUMN purpose_of_visit VARCHAR(50);
                END IF;
             END $$"""),
            ('6.0.1', 'Add GRC tracking fields to checkin_records',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='checkin_records' AND column_name='grc_generated_at')
                THEN
                    ALTER TABLE checkin_records ADD COLUMN grc_generated_at TIMESTAMP;
                    ALTER TABLE checkin_records ADD COLUMN grc_declaration_accepted BOOLEAN DEFAULT FALSE;
                    ALTER TABLE checkin_records ADD COLUMN grc_signature_ip VARCHAR(45);
                    ALTER TABLE checkin_records ADD COLUMN grc_signature_timestamp TIMESTAMP;
                END IF;
             END $$"""),
            ('6.0.2', 'Create foreign_national_info table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='foreign_national_info') THEN
                CREATE TABLE foreign_national_info (
                    id SERIAL PRIMARY KEY,
                    guest_id INTEGER NOT NULL UNIQUE REFERENCES guests(id),
                    nationality VARCHAR(60) NOT NULL,
                    passport_number VARCHAR(500),
                    passport_issue_place VARCHAR(100),
                    passport_issue_date DATE,
                    passport_expiry_date DATE,
                    visa_number VARCHAR(50),
                    visa_type VARCHAR(30),
                    visa_issue_date DATE,
                    visa_expiry_date DATE,
                    visa_issue_place VARCHAR(100),
                    arrival_from VARCHAR(100),
                    next_destination VARCHAR(100),
                    purpose_of_visit VARCHAR(100),
                    employed_in_india BOOLEAN DEFAULT FALSE,
                    employer_name VARCHAR(200),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                END IF;
             END $$"""),
            ('6.1.0', 'Add first_name and last_name to guests',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='guests' AND column_name='first_name')
                THEN
                    ALTER TABLE guests ADD COLUMN first_name VARCHAR(50);
                    ALTER TABLE guests ADD COLUMN last_name VARCHAR(50);
                END IF;
             END $$"""),
            ('6.2.0', 'Make reservation guest_id nullable for group blocks',
             """DO $$ BEGIN
                ALTER TABLE reservations ALTER COLUMN guest_id DROP NOT NULL;
             EXCEPTION WHEN others THEN NULL;
             END $$"""),
            ('6.3.0', 'Add pricing_mode column to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='pricing_mode')
                THEN
                    ALTER TABLE reservations ADD COLUMN pricing_mode VARCHAR(20) DEFAULT 'standard';
                END IF;
             END $$"""),
            ('7.1.0', 'Add category and code to payment_modes',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='payment_modes' AND column_name='category')
                THEN
                    ALTER TABLE payment_modes ADD COLUMN category VARCHAR(20) DEFAULT 'direct_payment' NOT NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='payment_modes' AND column_name='code')
                THEN
                    ALTER TABLE payment_modes ADD COLUMN code VARCHAR(30);
                END IF;
             END $$"""),
            ('7.1.1', 'Add ota_payment_status to reservations',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='ota_payment_status')
                THEN
                    ALTER TABLE reservations ADD COLUMN ota_payment_status VARCHAR(20) DEFAULT 'pay_at_hotel';
                END IF;
             END $$"""),
            ('7.2.0', 'Add is_app_owner flag to users table',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='is_app_owner')
                THEN
                    ALTER TABLE users ADD COLUMN is_app_owner BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
             END $$"""),
            ('7.3.0', 'Add ota_channel to reservations (authoritative storage)',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='reservations' AND column_name='ota_channel')
                THEN
                    ALTER TABLE reservations ADD COLUMN ota_channel VARCHAR(40);
                END IF;
             END $$"""),
            ('7.4.0', 'Create ota_payouts table for reconciliation',
             """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                    WHERE table_name='ota_payouts')
                THEN
                    CREATE TABLE ota_payouts (
                        id SERIAL PRIMARY KEY,
                        ota_channel VARCHAR(40) NOT NULL,
                        payout_date DATE NOT NULL,
                        reference_number VARCHAR(100),
                        gross_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                        commission_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                        tax_deducted NUMERIC(12,2) NOT NULL DEFAULT 0,
                        net_paid NUMERIC(12,2) NOT NULL DEFAULT 0,
                        remarks TEXT,
                        created_by_user_id INTEGER REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT NOW(),
                        CONSTRAINT ck_payout_gross_nonneg CHECK (gross_amount >= 0),
                        CONSTRAINT ck_payout_commission_nonneg CHECK (commission_amount >= 0),
                        CONSTRAINT ck_payout_tax_nonneg CHECK (tax_deducted >= 0),
                        CONSTRAINT ck_payout_net_nonneg CHECK (net_paid >= 0),
                        CONSTRAINT ck_payout_net_le_gross CHECK (net_paid <= gross_amount)
                    );
                    CREATE INDEX idx_payout_channel_date ON ota_payouts (ota_channel, payout_date);
                END IF;
             END $$"""),
            ('7.0.0', 'Create reservation_night_rates table',
             """CREATE TABLE IF NOT EXISTS reservation_night_rates (
                id SERIAL PRIMARY KEY,
                reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                stay_date DATE NOT NULL,
                room_type_id INTEGER REFERENCES room_types(id),
                room_id INTEGER REFERENCES rooms(id),
                standard_rate NUMERIC(12,2) NOT NULL,
                resolved_rate NUMERIC(12,2) NOT NULL,
                final_rate NUMERIC(12,2) NOT NULL,
                discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                rate_source VARCHAR(30) NOT NULL,
                rate_plan_id INTEGER REFERENCES rate_plans(id),
                rate_plan_name VARCHAR(100),
                pricing_mode VARCHAR(20),
                manual_override BOOLEAN NOT NULL DEFAULT FALSE,
                tax_rate NUMERIC(5,2),
                is_posted BOOLEAN NOT NULL DEFAULT FALSE,
                posted_charge_id INTEGER REFERENCES extra_charges(id),
                is_locked BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(reservation_id, stay_date)
             )"""),
            # ── 8.0.0 — Week 2 hot-path indexes (SQLite + Postgres) ─────
            # Uses plain CREATE INDEX IF NOT EXISTS so the block applies on
            # BOTH engines (no DO $$ guard — that would be skipped on SQLite).
            # Covers the columns identified by the data-integrity audit:
            # reservation dates, payment_date, charge_date, folio linkages,
            # and audit-log status. Every statement is idempotent.
            ('8.0.0', 'Week 2 hot-path indexes',
             """CREATE INDEX IF NOT EXISTS idx_reservation_arrival_date   ON reservations(arrival_date);
                CREATE INDEX IF NOT EXISTS idx_reservation_departure_date ON reservations(departure_date);
                CREATE INDEX IF NOT EXISTS idx_reservation_status         ON reservations(status);
                CREATE INDEX IF NOT EXISTS idx_payment_payment_date       ON payments(payment_date);
                CREATE INDEX IF NOT EXISTS idx_payment_is_voided          ON payments(is_voided);
                CREATE INDEX IF NOT EXISTS idx_payment_folio_id           ON payments(folio_id);
                CREATE INDEX IF NOT EXISTS idx_extra_charge_charge_date   ON extra_charges(charge_date);
                CREATE INDEX IF NOT EXISTS idx_extra_charge_folio_id      ON extra_charges(folio_id);
                CREATE INDEX IF NOT EXISTS idx_extra_charge_charge_type   ON extra_charges(charge_type);
                CREATE INDEX IF NOT EXISTS idx_folio_reservation_id       ON folios(reservation_id);
                CREATE INDEX IF NOT EXISTS idx_night_audit_status         ON night_audit_logs(status)"""),
            # ── 8.0.1 — Payment idempotency UNIQUE index ────────────────
            # Defence-in-depth over the row-lock idempotency check in
            # add_payment: a DB-level partial UNIQUE on rows where
            # reference_number starts with 'idem:' makes a duplicate
            # idempotency-key insert a hard CONSTRAINT VIOLATION rather
            # than relying entirely on application logic.
            # Partial unique indexes are supported by both SQLite (>=3.8)
            # and PostgreSQL, so the same DDL applies on both.
            # NOTE: scope of uniqueness is restricted to 'idem:%' so
            # non-idempotent payments (which may legitimately share a
            # blank reference_number or an OTA booking ref collision) are
            # unaffected.
            ('8.0.1', 'Partial unique index for payment idempotency keys',
             """CREATE UNIQUE INDEX IF NOT EXISTS ux_payment_idem_ref
                    ON payments(reference_number)
                    WHERE reference_number LIKE 'idem:%'"""),
            ('9.0.0', 'Create credit_vouchers + credit_voucher_redemptions tables',
             """CREATE TABLE IF NOT EXISTS credit_vouchers (
                    id SERIAL PRIMARY KEY,
                    voucher_code VARCHAR(30) UNIQUE NOT NULL,
                    guest_id INTEGER NOT NULL REFERENCES guests(id),
                    issued_amount NUMERIC(10,2) NOT NULL CHECK (issued_amount > 0),
                    redeemed_amount NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (redeemed_amount >= 0),
                    issued_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    expiry_date DATE,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    issued_from_reservation_id INTEGER REFERENCES reservations(id),
                    issued_by_user_id INTEGER REFERENCES users(id),
                    fully_redeemed_at TIMESTAMP,
                    expired_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    notes VARCHAR(300),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_voucher_guest ON credit_vouchers(guest_id);
                CREATE INDEX IF NOT EXISTS idx_voucher_status ON credit_vouchers(status);
                CREATE TABLE IF NOT EXISTS credit_voucher_redemptions (
                    id SERIAL PRIMARY KEY,
                    voucher_id INTEGER NOT NULL REFERENCES credit_vouchers(id),
                    reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                    amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
                    redeemed_at TIMESTAMP DEFAULT NOW(),
                    redeemed_by_user_id INTEGER REFERENCES users(id),
                    payment_id INTEGER REFERENCES payments(id),
                    notes VARCHAR(300)
                );
                CREATE INDEX IF NOT EXISTS idx_voucher_redeem_voucher ON credit_voucher_redemptions(voucher_id);
                CREATE INDEX IF NOT EXISTS idx_voucher_redeem_reservation ON credit_voucher_redemptions(reservation_id);"""),
        ]

        applied = {row[0] for row in db.session.execute(
            db.text('SELECT version FROM schema_migrations')
        ).fetchall()}

        for version, description, sql in migrations:
            if version in applied:
                continue
            # Skip PostgreSQL-only PL/pgSQL migrations on SQLite
            # (db.create_all() already creates all tables from models)
            if _is_sqlite and 'DO $$' in sql:
                logger.info('Migration %s skipped (PG-only, SQLite uses models): %s', version, description)
                try:
                    db.session.execute(
                        db.text('INSERT INTO schema_migrations(version, description) VALUES (:v, :d)'),
                        {'v': version, 'd': description}
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                continue
            try:
                # Replace NOW() with CURRENT_TIMESTAMP for SQLite compatibility
                _sql = sql.replace('DEFAULT NOW()', 'DEFAULT CURRENT_TIMESTAMP') if _is_sqlite else sql
                # Replace SERIAL with INTEGER for SQLite
                if _is_sqlite:
                    _sql = _sql.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
                # SQLite only supports one statement per execute(); split on ';'
                if _is_sqlite and ';' in _sql.strip().rstrip(';'):
                    for _stmt in _sql.split(';'):
                        _stmt = _stmt.strip()
                        if _stmt:
                            db.session.execute(db.text(_stmt))
                else:
                    db.session.execute(db.text(_sql))
                db.session.execute(
                    db.text('INSERT INTO schema_migrations(version, description) VALUES (:v, :d)'),
                    {'v': version, 'd': description}
                )
                db.session.commit()
                logger.info('Migration %s applied: %s', version, description)
            except Exception as e:
                db.session.rollback()
                logger.error('Migration %s FAILED: %s', version, e)

        # ── SQLite column fixer ──────────────────────────────────────────
        # db.create_all() creates new TABLES but cannot add columns to
        # existing tables. This block detects and adds missing columns.
        #
        # SQL identifiers (table names, column names, type declarations)
        # cannot be passed as bound parameters, so we enforce an allowlist:
        # every identifier is validated against a strict regex before being
        # interpolated into the DDL. This is defence-in-depth — the source
        # list is already a constant, but the guard ensures that any future
        # edit which accidentally reads an identifier from config / env /
        # user input will fail closed.
        if _is_sqlite:
            import re as _re_ident
            _IDENT_RE = _re_ident.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
            _TYPE_RE = _re_ident.compile(
                r'^(VARCHAR|CHAR|TEXT|INTEGER|INT|BIGINT|NUMERIC|DECIMAL|'
                r'BOOLEAN|DATE|DATETIME|TIMESTAMP|FLOAT|REAL)'
                r'(\s*\(\s*\d+(\s*,\s*\d+)?\s*\))?$',
                _re_ident.IGNORECASE,
            )
            # Defaults are whitelisted to: numeric literals, SQL booleans,
            # or single-quoted strings with no embedded quotes/backslashes.
            _DEFAULT_RE = _re_ident.compile(
                r"^(TRUE|FALSE|NULL|-?\d+(\.\d+)?|'[^'\\]*')$",
                _re_ident.IGNORECASE,
            )

            _sqlite_cols_to_add = [
                # (table, column, sql_type, default)
                ('guests', 'first_name', 'VARCHAR(50)', None),
                ('guests', 'last_name', 'VARCHAR(50)', None),
                ('guests', 'loyalty_tier', "VARCHAR(20)", "'Silver'"),
                ('guests', 'date_of_birth', 'DATE', None),
                ('guests', 'gender', 'VARCHAR(10)', None),
                ('guests', 'purpose_of_visit', 'VARCHAR(50)', None),
                ('checkin_records', 'grc_generated_at', 'TIMESTAMP', None),
                ('checkin_records', 'grc_declaration_accepted', 'BOOLEAN', 'FALSE'),
                ('checkin_records', 'grc_signature_ip', 'VARCHAR(45)', None),
                ('checkin_records', 'grc_signature_timestamp', 'TIMESTAMP', None),
                ('checkin_records', 'company_credit_posted', 'NUMERIC(12,2)', '0'),
                ('reservations', 'pricing_mode', "VARCHAR(20)", "'standard'"),
                ('reservations', 'ota_payment_status', "VARCHAR(20)", "'pay_at_hotel'"),
                ('payment_modes', 'category', "VARCHAR(20)", "'direct_payment'"),
                ('payment_modes', 'code', "VARCHAR(30)", None),
                ('users', 'is_app_owner', 'BOOLEAN', 'FALSE'),
                ('reservations', 'ota_channel', 'VARCHAR(40)', None),
                # Individual credit checkout (Apr 2026)
                ('reservations', 'credit_amount', 'NUMERIC(10,2)', '0'),
                ('reservations', 'credit_reason', 'VARCHAR(200)', None),
                ('reservations', 'credit_approved_by_user_id', 'INTEGER', None),
                ('reservations', 'credit_approved_at', 'TIMESTAMP', None),
                # Credit loop closure (Apr 2026 hardening pass)
                ('reservations', 'credit_settled_amount', 'NUMERIC(10,2)', '0'),
                ('reservations', 'credit_settled_at', 'TIMESTAMP', None),
                # Post-audit correction entries (Apr 2026 hardening pass)
                ('payments',       'is_correction',     'BOOLEAN',     '0'),
                ('payments',       'is_reversal',       'BOOLEAN',     '0'),
                ('payments',       'corrects_id',       'INTEGER',     None),
                ('payments',       'correction_reason', 'VARCHAR(300)', None),
                ('extra_charges',  'is_correction',     'BOOLEAN',     '0'),
                ('extra_charges',  'is_reversal',       'BOOLEAN',     '0'),
                ('extra_charges',  'corrects_id',       'INTEGER',     None),
                ('extra_charges',  'correction_reason', 'VARCHAR(300)', None),
                # Advance/settlement/credit-recovery accounting separation (Apr 2026)
                ('payments',       'payment_purpose',   'VARCHAR(20)',  None),
                # Advance booking cancellation disposition (Apr 2026 hardening pass)
                ('reservations', 'cancellation_disposition',          'VARCHAR(20)',  None),
                ('reservations', 'cancellation_amount_refunded',      'NUMERIC(10,2)', '0'),
                ('reservations', 'cancellation_amount_forfeited',     'NUMERIC(10,2)', '0'),
                ('reservations', 'cancellation_amount_credit_voucher','NUMERIC(10,2)', '0'),
                ('reservations', 'cancellation_reason',               'VARCHAR(300)', None),
                ('reservations', 'cancellation_processed_by_user_id', 'INTEGER',      None),
                ('reservations', 'cancellation_processed_at',         'TIMESTAMP',    None),
                ('reservations', 'cancellation_refund_payment_id',    'INTEGER',      None),
                # Advance Receipt number sequence (Apr 2026 polish)
                ('reservations', 'advance_receipt_number',             'VARCHAR(20)',  None),
                ('reservations', 'advance_receipt_date',               'TIMESTAMP',    None),
                # Snapshot validity flag (Apr 2026 critical correction)
                ('night_audit_logs', 'snapshot_valid',                 'BOOLEAN',      'TRUE'),
                # Source-captured leakage classification (Apr 2026)
                ('reservations', 'leakage_type',                       'VARCHAR(20)',  None),
                ('reservations', 'leakage_authorized_by_user_id',      'INTEGER',      None),
                ('reservations', 'leakage_created_at',                 'TIMESTAMP',    None),
                # Invoice rounding-snapshot reconciliation (Apr 2026)
                ('reservations', 'invoice_taxable_total',              'NUMERIC(12,2)', None),
                ('reservations', 'invoice_gst_total',                  'NUMERIC(12,2)', None),
                ('reservations', 'invoice_unrounded_grand_total',      'NUMERIC(12,2)', None),
                ('reservations', 'invoice_rounded_grand_total',        'NUMERIC(12,2)', None),
                ('reservations', 'invoice_round_off_amount',           'NUMERIC(10,2)', None),
                ('reservations', 'invoice_finalised_at',               'TIMESTAMP',    None),
                # Snapshot tamper-detection (Apr 2026 final tightening)
                ('night_audit_logs', 'snapshot_hash',                  'VARCHAR(64)',  None),
                ('night_audit_logs', 'snapshot_version',               'VARCHAR(20)',  None),
                # Leakage intent classification (Apr 2026 final tightening)
                ('reservations', 'leakage_intent',                     'VARCHAR(15)',  None),
            ]
            for _tbl, _col, _type, _default in _sqlite_cols_to_add:
                # Fail-closed validation: reject any identifier or type that
                # does not match the strict allowlist regex. This keeps the
                # safe interpolation auditable — nothing else can reach DDL.
                if not _IDENT_RE.match(_tbl):
                    logger.error('Refusing DDL: invalid table identifier %r', _tbl)
                    continue
                if not _IDENT_RE.match(_col):
                    logger.error('Refusing DDL: invalid column identifier %r', _col)
                    continue
                if not _TYPE_RE.match(_type):
                    logger.error('Refusing DDL: invalid type %r for %s.%s',
                                 _type, _tbl, _col)
                    continue
                if _default is not None and not _DEFAULT_RE.match(str(_default).strip()):
                    logger.error('Refusing DDL: invalid default %r for %s.%s',
                                 _default, _tbl, _col)
                    continue
                try:
                    # Table name is now guaranteed to match [A-Za-z_][A-Za-z0-9_]*,
                    # so interpolation into PRAGMA / ALTER TABLE is safe.
                    existing = [r[1] for r in db.session.execute(
                        db.text(f'PRAGMA table_info({_tbl})')).fetchall()]
                    if _col not in existing:
                        _dflt = f' DEFAULT {_default}' if _default else ''
                        db.session.execute(db.text(
                            f'ALTER TABLE {_tbl} ADD COLUMN {_col} {_type}{_dflt}'))
                        db.session.commit()
                        logger.info('SQLite: added column %s.%s', _tbl, _col)
                except Exception as _col_err:
                    db.session.rollback()
                    logger.warning('SQLite column add %s.%s failed: %s', _tbl, _col, _col_err)

            # ── SQLite new-table bootstrap (Apr 2026 hardening pass) ──
            # db.create_all() picks these up in dev / on first boot. For
            # existing SQLite installs that boot without DB_AUTO_CREATE,
            # this block creates the new tables idempotently so prod
            # deploys don't need a separate migration step.
            _sqlite_tables_to_create = [
                ('credit_vouchers', """
                    CREATE TABLE IF NOT EXISTS credit_vouchers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        voucher_code VARCHAR(30) UNIQUE NOT NULL,
                        guest_id INTEGER NOT NULL REFERENCES guests(id),
                        issued_amount NUMERIC(10,2) NOT NULL CHECK (issued_amount > 0),
                        redeemed_amount NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (redeemed_amount >= 0),
                        issued_date DATE NOT NULL DEFAULT (date('now')),
                        expiry_date DATE,
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        issued_from_reservation_id INTEGER REFERENCES reservations(id),
                        issued_by_user_id INTEGER REFERENCES users(id),
                        fully_redeemed_at TIMESTAMP,
                        expired_at TIMESTAMP,
                        cancelled_at TIMESTAMP,
                        notes VARCHAR(300),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """),
                ('credit_voucher_redemptions', """
                    CREATE TABLE IF NOT EXISTS credit_voucher_redemptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        voucher_id INTEGER NOT NULL REFERENCES credit_vouchers(id),
                        reservation_id INTEGER NOT NULL REFERENCES reservations(id),
                        amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
                        redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        redeemed_by_user_id INTEGER REFERENCES users(id),
                        payment_id INTEGER REFERENCES payments(id),
                        notes VARCHAR(300)
                    )
                """),
            ]
            _sqlite_indexes_to_create = [
                'CREATE INDEX IF NOT EXISTS idx_voucher_guest ON credit_vouchers(guest_id)',
                'CREATE INDEX IF NOT EXISTS idx_voucher_status ON credit_vouchers(status)',
                'CREATE INDEX IF NOT EXISTS idx_voucher_redeem_voucher ON credit_voucher_redemptions(voucher_id)',
                'CREATE INDEX IF NOT EXISTS idx_voucher_redeem_reservation ON credit_voucher_redemptions(reservation_id)',
            ]
            for _tname, _ddl in _sqlite_tables_to_create:
                if not _IDENT_RE.match(_tname):
                    logger.error('Refusing CREATE TABLE: invalid name %r', _tname)
                    continue
                try:
                    db.session.execute(db.text(_ddl))
                    db.session.commit()
                    logger.info('SQLite: ensured table %s exists', _tname)
                except Exception as _t_err:
                    db.session.rollback()
                    logger.warning('SQLite table create %s failed: %s', _tname, _t_err)
            for _idx_ddl in _sqlite_indexes_to_create:
                try:
                    db.session.execute(db.text(_idx_ddl))
                    db.session.commit()
                except Exception as _i_err:
                    db.session.rollback()
                    logger.warning('SQLite index create failed: %s', _i_err)


def init_data():
    from app.models import db, RoomType, Room, PaymentMode, BusinessDate, Settings, User, POSItem
    from datetime import date
    
    # Initialize business date
    if not BusinessDate.query.first():
        bd = BusinessDate(current_date=date.today())
        db.session.add(bd)
    
    # Initialize room types
    if not RoomType.query.filter_by(name='Standard').first():
        standard = RoomType(name='Standard', base_rate=1000, description='Standard room with GST included')
        db.session.add(standard)
    
    # Initialize payment modes (Settlement Heads)
    # Direct payment modes — money received from guest at the hotel
    _direct_modes = [
        ('Cash', 'CASH'),
        ('UPI', 'UPI'),
        ('Card', 'CARD'),
    ]
    for name, code in _direct_modes:
        pm = PaymentMode.query.filter_by(name=name).first()
        if not pm:
            db.session.add(PaymentMode(name=name, code=code, category='direct_payment'))
        else:
            # Backfill code/category on pre-existing rows
            if not pm.code:
                pm.code = code
            if not pm.category:
                pm.category = 'direct_payment'

    # OTA receivable heads — revenue settled via OTA, pending payout to hotel
    _ota_heads = [
        ('MMT Paid',         'MMT_PAID'),
        ('Goibibo Paid',     'GOIBIBO_PAID'),
        ('Booking.com Paid', 'BOOKING_PAID'),
        ('Agoda Paid',       'AGODA_PAID'),
        ('Expedia Paid',     'EXPEDIA_PAID'),
        ('Airbnb Paid',      'AIRBNB_PAID'),
        ('Yatra Paid',       'YATRA_PAID'),
        ('EaseMyTrip Paid',  'EASEMYTRIP_PAID'),
        ('Other OTA Paid',   'OTHER_OTA_PAID'),
    ]
    for name, code in _ota_heads:
        if not PaymentMode.query.filter_by(name=name).first():
            db.session.add(PaymentMode(
                name=name, code=code, category='ota_receivable'))
    
    # Initialize settings
    import secrets
    settings_data = [
        ('night_audit_enabled', 'true', 'Enable automatic night audit'),
        ('night_audit_time', '02:00', 'Night audit run time (HH:MM)'),
        ('webhook_api_key', secrets.token_hex(24), 'API key for channel manager webhook calls'),
        ('noshow_fee_enabled', 'false', 'Enable automatic no-show fee posting'),
        ('noshow_fee_mode', 'fixed', 'No-show fee mode: fixed or percent (of first night)'),
        ('noshow_fee_amount', '0', 'No-show fee amount (INR) or percentage'),
        ('noshow_ota_auto_process', 'false', 'Auto-post no-show fee for OTA bookings'),
        # GST settings
        ('hotel_gstin',         '',      'Hotel GST Identification Number (15 characters)'),
        ('hotel_state_code',    '07',    'Hotel state GST code (07=Delhi, 27=Maharashtra, etc.)'),
        ('hotel_address',       '',      'Hotel address for invoice header'),
        ('hotel_cin',           '',      'Hotel CIN / Company Reg number (optional)'),
        # Payment void settings
        ('void_window_hours',       '2',  'Hours within which Manager can void a payment'),
        ('admin_void_window_hours', '24', 'Hours within which Admin can void a payment'),
        # Backup settings
        ('backup_time',             '03:00', 'Daily automatic backup time (HH:MM)'),
        # Feedback settings
        ('google_review_url',       '',   'Google Maps review URL for post-stay push'),
        # High demand threshold
        ('high_demand_threshold',   '85', 'Occupancy % to show high-demand alert'),
        # OTA / Channel Manager
        ('cloudflare_tunnel_url',   '',   'Cloudflare tunnel public URL for webhook endpoint'),
        # App branding
        ('app_name',                '',   'App display name in navbar (leave blank to use Hotel Name)'),
        ('app_logo_filename',       '',   'Uploaded app logo filename'),
        # Invoice customization
        ('invoice_title',           'TAX INVOICE', 'Invoice page title shown on printout'),
        ('invoice_prefix',          'INV',         'Invoice number prefix (e.g. INV, SKN, HT)'),
        ('invoice_location_code',   '',            'Location code in invoice number (e.g. JBP, DEL)'),
        ('invoice_pan',             '',            'Hotel PAN number for invoice'),
        ('invoice_thankyou',        'Thank you for choosing us. We look forward to welcoming you again!',
                                                   'Thank-you message printed at bottom of invoice'),
        ('invoice_terms',           '',            'Terms and conditions printed on invoice'),
        ('invoice_show_logo',           'true',  'Show hotel logo on invoice'),
        ('invoice_show_signatory',      'true',  'Show Authorized Signatory block on invoice'),
        ('invoice_show_guest_address',  'true',  'Show guest address on invoice'),
        ('invoice_show_booking_type',   'true',  'Show booking type (Regular/Hourly) on invoice'),
        ('invoice_show_payment_summary','true',  'Show payment summary section on invoice'),
        ('invoice_show_gst_breakdown',  'true',  'Show GST breakdown table on invoice'),
        ('invoice_show_terms',          'true',  'Show terms and conditions on invoice'),
        ('invoice_show_balance_badge',  'true',  'Show Settled/Partial/Unsettled badge on invoice'),
        ('invoice_show_cg_note',        'true',  'Show computer-generated invoice disclaimer'),
        ('invoice_show_rate_breakdown', 'false', 'Include Rate Breakdown transparency block on the PDF (HTML view always shows it collapsed)'),
        ('invoice_layout',              'a4',    'Invoice print layout: a4 or compact'),
        ('invoice_counter',             '0',     'Running sequential invoice number counter'),
        ('credit_note_counter',         '0',     'Running sequential credit note counter'),
        # OTA payout cycles (Phase 2 reconciliation) — days from a
        # receivable posting to the expected channel-manager payout.
        # Editable from Settings UI later; defaults below match the
        # public payout policies of each channel as of 2026-04.
        ('ota_cycle_default',           '30',    'Default OTA payout cycle in days'),
        ('ota_cycle_booking_com',       '15',    'Booking.com payout cycle (days)'),
        ('ota_cycle_makemytrip',        '30',    'MakeMyTrip payout cycle (days)'),
        ('ota_cycle_goibibo',           '30',    'Goibibo payout cycle (days)'),
        ('ota_cycle_agoda',             '45',    'Agoda payout cycle (days)'),
        ('ota_cycle_expedia',           '30',    'Expedia payout cycle (days)'),
        ('ota_cycle_airbnb',            '30',    'Airbnb payout cycle (days)'),
        ('ota_cycle_yatra',             '30',    'Yatra payout cycle (days)'),
        ('ota_cycle_easemytrip',        '30',    'EaseMyTrip payout cycle (days)'),
    ]
    for key, value, desc in settings_data:
        if not Settings.query.filter_by(key=key).first():
            s = Settings(key=key, value=value, description=desc)
            db.session.add(s)
    
    db.session.commit()

    # Seed loyalty tiers and milestones (only on first run)
    from app.models import LoyaltyConfig, LoyaltyMilestone
    if LoyaltyConfig.query.count() == 0:
        db.session.add_all([
            LoyaltyConfig(tier_name='Silver', tier_order=1, min_points=0, earn_per_night=10,
                          earn_per_100_rupees=1, direct_booking_bonus_pct=10, redemption_value=0.25,
                          late_checkout_points=500, early_checkin_points=300, color_hex='#6c757d'),
            LoyaltyConfig(tier_name='Gold', tier_order=2, min_points=5000, earn_per_night=15,
                          earn_per_100_rupees=2, direct_booking_bonus_pct=15, redemption_value=0.40,
                          late_checkout_points=400, early_checkin_points=250, color_hex='#ffc107'),
            LoyaltyConfig(tier_name='Platinum', tier_order=3, min_points=15000, earn_per_night=25,
                          earn_per_100_rupees=3, direct_booking_bonus_pct=20, redemption_value=0.50,
                          late_checkout_points=300, early_checkin_points=200, color_hex='#6f42c1'),
        ])
        db.session.commit()
    if LoyaltyMilestone.query.count() == 0:
        db.session.add_all([
            LoyaltyMilestone(name='5th Stay Bonus', trigger_type='stays', trigger_value=5, bonus_points=200),
            LoyaltyMilestone(name='10th Stay Bonus', trigger_type='stays', trigger_value=10, bonus_points=500),
            LoyaltyMilestone(name='20th Stay Bonus', trigger_type='stays', trigger_value=20, bonus_points=1000),
        ])
        db.session.commit()

    # Seed sample POS items (only on first run)
    if not POSItem.query.first():
        sample_items = [
            ('Continental Breakfast', 'Restaurant', 250),
            ('Masala Tea / Coffee', 'Restaurant', 60),
            ('Mineral Water (1L)', 'Minibar', 40),
            ('Soft Drinks', 'Minibar', 80),
            ('Laundry — Shirt', 'Laundry', 70),
            ('Laundry — Trouser', 'Laundry', 90),
            ('Laundry — Suit', 'Laundry', 200),
            ('Airport Transfer', 'Other', 500),
        ]
        for name, category, price in sample_items:
            db.session.add(POSItem(name=name, category=category, price=price))
        db.session.commit()

    # Admin account: created via /setup wizard (browser-based first-run setup)
    # If no admin exists, the setup wizard at /setup handles account creation
    if not User.query.first():
        logger.info('No admin user found. Visit /setup in browser to complete first-time setup.')

    # Ensure at least one admin is app_owner (upgrade path for existing installs)
    if not User.query.filter_by(is_app_owner=True).first():
        _first_admin = User.query.filter_by(role='Admin', is_active=True).order_by(User.id).first()
        if _first_admin:
            _first_admin.is_app_owner = True
            db.session.commit()
            logger.info('Promoted user %s to app_owner (first-run upgrade).', _first_admin.username)

    # ── Backfill Reservation.ota_channel for legacy rows (Phase A→B) ──
    # The ota_channel column was added in migration 7.3.0. Existing OTA
    # reservations created before the upgrade have NULL — populate them
    # using the same inference rules so the dashboard / journey / CEO
    # KPIs see a consistent channel everywhere. Idempotent: skips rows
    # that already have a non-null value, so it can run on every boot
    # until the table is fully populated.
    try:
        from app.models import Reservation
        from app.ota import _infer_ota_source
        _legacy = (Reservation.query
                   .filter(Reservation.source == 'OTA',
                           Reservation.ota_channel.is_(None))
                   .all())
        if _legacy:
            _filled = 0
            for _res in _legacy:
                # _infer_ota_source falls back to prefix inference when
                # ota_channel is NULL — exactly what we want here.
                _res.ota_channel = _infer_ota_source(_res)
                _filled += 1
            db.session.commit()
            logger.info('Backfilled ota_channel on %d legacy OTA reservations.', _filled)
    except Exception as _bf_err:
        db.session.rollback()
        logger.warning('ota_channel backfill skipped: %s', _bf_err)

    # Rooms: no default rooms seeded. Use Masters → Rooms → Bulk Add to create rooms.
