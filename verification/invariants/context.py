"""
The evaluation context and the scope it is evaluated over.

One context is built per run and handed to every invariant. It owns:

* a **read-only** ``sqlite3`` connection to the working copy, which is
  how most invariants read the primary record;
* the Flask application bound to that same copy, for the invariants that
  must go through a canonical engine rather than around it;
* the scope — which business date, which reservation, which mode;
* the metering, so every read and every write is counted rather than
  assumed.

Why both a raw connection and the application
---------------------------------------------
An invariant that checks whether the books add up must read the books,
not ask the application whether it thinks they do — otherwise a defect in
the application hides itself. An invariant that checks whether the
canonical engine agrees with the books has to call the canonical engine.
Both are legitimate; each invariant declares which it uses in
``canonical_engine``, and the two are never mixed silently.

Metering
--------
Every statement is counted and classified. ``db_writes`` must be zero,
and it is measured on both paths: statements issued through this context
and statements issued by SQLAlchemy on the application's behalf. The
listener is installed *after* ``create_app()`` has finished, because
application boot legitimately writes to the copy — migrations, the
column fixer and ``init_data()`` all commit — and counting those would
make the measurement meaningless rather than strict.
"""
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from dataclasses import dataclass, field

from verification.invariants.model import Metering, Mode

#: Leading keywords that mean a statement changed something.
_WRITE_RE = re.compile(
    r'^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|TRUNCATE|VACUUM)\b',
    re.IGNORECASE)


class ScopeError(ValueError):
    """A scope is incomplete for the mode it declares."""


@dataclass
class Scope:
    """What a run is evaluating over."""
    mode: str = Mode.ENTIRE_DATABASE
    business_date: str = ''          # ISO, for date-scoped modes
    reservation_id: int = 0
    dataset: str = ''                # regression dataset / master set tag
    replay_context: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode in (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT,
                         Mode.HISTORICAL_REPLAY) and not self.business_date:
            raise ScopeError(
                f'{self.mode} requires a business date. Without one the '
                f'invariants would silently widen to the whole database and '
                f'report coverage they do not have.')
        if self.mode == Mode.SINGLE_RESERVATION and not self.reservation_id:
            raise ScopeError('SINGLE_RESERVATION requires a reservation id')

    @property
    def label(self) -> str:
        if self.business_date:
            return f'{self.mode}:{self.business_date}'
        if self.reservation_id:
            return f'{self.mode}:reservation {self.reservation_id}'
        if self.dataset:
            return f'{self.mode}:{self.dataset}'
        return self.mode


class Context:
    """Everything an invariant is allowed to reach."""

    def __init__(self, db_path: str, app=None, scope: Scope | None = None,
                 business_date: str = ''):
        self.db_path = db_path
        self.app = app
        self.scope = scope or Scope()
        self.business_date = business_date or self.scope.business_date
        self.metering = Metering()

        uri = 'file:' + db_path.replace('\\', '/') + '?mode=ro'
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row
        self._sa_listener_installed = False
        self._cache: dict = {}

    # -- scope helpers ---------------------------------------------------

    @property
    def date(self) -> str:
        """The date under evaluation, or '' for whole-database scope."""
        return self.scope.business_date

    @property
    def reservation_id(self) -> int:
        return self.scope.reservation_id

    # -- reads -----------------------------------------------------------

    def sql(self, query: str, params: tuple = ()) -> list:
        """Run a read query against the working copy.

        Refuses to issue a write. The connection is already ``mode=ro``
        so SQLite would reject it anyway; the explicit check exists so
        the failure names the invariant's intent rather than surfacing as
        an opaque "attempt to write a readonly database".
        """
        if _WRITE_RE.match(query):
            self.metering.db_writes += 1
            raise RuntimeError(
                f'An invariant attempted a write: {query.strip()[:80]}. '
                f'The invariant engine proves the system is correct; it '
                f'never changes it.')
        self.metering.db_reads += 1
        rows = self._conn.execute(query, params).fetchall()
        self.metering.rows_examined += len(rows)
        return rows

    def scalar(self, query: str, params: tuple = (), default=None):
        rows = self.sql(query, params)
        if not rows:
            return default
        value = rows[0][0]
        return default if value is None else value

    def count(self, query: str, params: tuple = ()) -> int:
        return int(self.scalar(query, params, default=0))

    def cached(self, key: str, builder):
        if key not in self._cache:
            self._cache[key] = builder()
        return self._cache[key]

    def table_exists(self, table: str) -> bool:
        return bool(self.sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)))

    # -- application ------------------------------------------------------

    def require_app(self, invariant_id: str):
        """The Flask application, or a clear failure.

        An invariant that needs a canonical engine and cannot reach one
        must ERROR rather than fall back to reading the tables itself.
        The fallback would silently turn a cross-check into a
        self-check — the invariant would compare the books with the
        books and always agree.
        """
        if self.app is None:
            raise RuntimeError(
                f'{invariant_id} needs the canonical engine but the run was '
                f'built without an application. Refusing to fall back to a '
                f'direct table read: that would turn a cross-check into a '
                f'self-check and it would always pass.')
        return self.app

    # -- metering ---------------------------------------------------------

    def install_sqlalchemy_meter(self) -> None:
        """Count statements SQLAlchemy issues on the application's behalf.

        Installed after ``create_app()`` so that application boot writes
        — which land on the disposable copy by design — are not counted
        against the invariant run.
        """
        if self.app is None or self._sa_listener_installed:
            return
        from sqlalchemy import event
        from app.models import db

        engine = db.engine
        metering = self.metering

        def _before(conn, cursor, statement, parameters, ctx, executemany):
            if _WRITE_RE.match(statement or ''):
                metering.db_writes += 1
            else:
                metering.db_reads += 1

        event.listen(engine, 'before_cursor_execute', _before)
        self._sa_meter = (engine, _before)
        self._sa_listener_installed = True

    def remove_sqlalchemy_meter(self) -> None:
        if not self._sa_listener_installed:
            return
        from sqlalchemy import event
        engine, handler = self._sa_meter
        event.remove(engine, 'before_cursor_execute', handler)
        self._sa_listener_installed = False

    def snapshot_metering(self) -> Metering:
        m = self.metering
        return Metering(duration_ms=m.duration_ms, db_reads=m.db_reads,
                        db_writes=m.db_writes,
                        memory_peak_kb=m.memory_peak_kb,
                        rows_examined=m.rows_examined)

    def reset_metering(self) -> None:
        self.metering.duration_ms = 0
        self.metering.db_reads = 0
        self.metering.db_writes = 0
        self.metering.memory_peak_kb = 0
        self.metering.rows_examined = 0

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self.remove_sqlalchemy_meter()
        try:
            self._conn.close()
        except Exception:                                # noqa: BLE001
            pass

    # -- common populations -----------------------------------------------

    def business_date_value(self) -> str:
        """The dataset's current business date, read from the copy."""
        return self.cached('business_date', lambda: str(self.scalar(
            'SELECT "current_date" FROM business_date ORDER BY id LIMIT 1',
            default='')) [:10])

    def closed_dates(self) -> list:
        """Business dates whose night audit reached a terminal state."""
        def build():
            if not self.table_exists('night_audit_logs'):
                return []
            return [str(r['audit_date'])[:10] for r in self.sql(
                "SELECT audit_date FROM night_audit_logs "
                "WHERE status IN ('Completed','Warning') ORDER BY audit_date")]
        return self.cached('closed_dates', build)

    def reservation_ids(self) -> list:
        def build():
            if self.reservation_id:
                return [self.reservation_id]
            return [int(r[0]) for r in self.sql(
                'SELECT id FROM reservations ORDER BY id')]
        return self.cached('reservation_ids', build)

    @staticmethod
    def today_iso() -> str:
        return _dt.date.today().isoformat()
