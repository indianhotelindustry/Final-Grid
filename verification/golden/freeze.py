"""
Deterministic clock for golden master capture.

Why this exists
---------------
A golden master is only useful if a difference means "something
changed". The application reads the wall clock in ~150 places
(``datetime.now()``, ``date.today()``, ``datetime.utcnow()``): aging
buckets, default report ranges, "as at" stamps, forecast windows. Left
alone, every master would differ from itself the following day, the
framework would cry wolf daily, and the first thing an engineer under
deadline pressure would do is switch it off.

So the clock is pinned to a declared instant, recorded in the master
index, and reported on every run. Time becomes an input to the capture
rather than an uncontrolled variable.

How
---
Two patches, because the application binds ``datetime`` two different
ways:

1. ``datetime.datetime`` / ``datetime.date`` are replaced *on the
   datetime module itself*. This covers the function-local imports
   (``def f(): from datetime import date``) that a namespace patch can
   never reach, and every module imported after the patch.

2. Already-imported module namespaces are rescanned and any binding
   that *is* the real class is rebound. This covers aliases
   (``from datetime import datetime as _dt``) in modules imported before
   the freeze.

The fakes subclass the real classes so ``isinstance`` keeps working, and
carry a metaclass whose ``__instancecheck__`` delegates to the real
class so that ``isinstance(a_real_date, date)`` also keeps working after
the patch. Getting that wrong silently changes application behaviour
under test, which would make the harness lie.

This process is never the production process. The patch is installed by
the capture harness, applies only to it, and ``uninstall()`` restores
the originals.

Principle 11
------------
``prove()`` is the positive evidence that the freeze took effect, tested
through both binding paths. If it cannot be proven, capture aborts
rather than producing masters that quietly rot.
"""
from __future__ import annotations

import datetime as _dtmod
import sys

_real_datetime = _dtmod.datetime
_real_date = _dtmod.date


class _RealInstanceCheck(type):
    """Make ``isinstance``/``issubclass`` behave as if unpatched.

    Without this, patching ``datetime.date`` breaks every
    ``isinstance(x, date)`` in the application for values that are real
    dates — which is most of them, since they come out of the database.
    """

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls._real)


class FrozenDateTime(_real_datetime, metaclass=_RealInstanceCheck):
    _real = _real_datetime
    _frozen: _real_datetime = _real_datetime(1970, 1, 1)

    @classmethod
    def _make(cls, v: _real_datetime):
        return cls(v.year, v.month, v.day, v.hour, v.minute, v.second,
                   v.microsecond, v.tzinfo)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls._make(cls._frozen)
        # The frozen instant is naive and interpreted as local time; a
        # tz-aware request gets it attached, not shifted, because the
        # application's own naive/aware handling is what we are
        # measuring, not the harness's opinion about zones.
        return cls._make(cls._frozen.replace(tzinfo=tz))

    @classmethod
    def utcnow(cls):
        return cls._make(cls._frozen)

    @classmethod
    def today(cls):
        return cls._make(cls._frozen)


class FrozenDate(_real_date, metaclass=_RealInstanceCheck):
    _real = _real_date
    _frozen: _real_date = _real_date(1970, 1, 1)

    @classmethod
    def today(cls):
        f = cls._frozen
        return cls(f.year, f.month, f.day)


class ClockFreeze:
    """Install / remove the frozen clock. Not reentrant by design."""

    def __init__(self, instant: _real_datetime):
        if not isinstance(instant, _real_datetime):
            raise TypeError('freeze instant must be a datetime')
        self.instant = instant
        self._installed = False
        self._rebound: list[tuple[object, str, object]] = []

    # -- install ---------------------------------------------------------

    def install(self) -> 'ClockFreeze':
        if self._installed:
            raise RuntimeError('clock freeze already installed')
        FrozenDateTime._frozen = self.instant
        FrozenDate._frozen = self.instant.date()

        _dtmod.datetime = FrozenDateTime
        _dtmod.date = FrozenDate
        self._installed = True
        self.rebind_loaded_modules()
        return self

    def rebind_loaded_modules(self, prefixes: tuple[str, ...] = ('app',)) -> int:
        """Rebind real-class references already imported into namespaces.

        Matches on identity, not on name, so aliases such as
        ``from datetime import datetime as _dt`` are covered too.
        """
        count = 0
        for mod_name, mod in list(sys.modules.items()):
            if mod is None:
                continue
            if not (mod_name in prefixes or
                    any(mod_name.startswith(p + '.') for p in prefixes)):
                continue
            for attr, value in list(vars(mod).items()):
                if value is _real_datetime:
                    setattr(mod, attr, FrozenDateTime)
                    self._rebound.append((mod, attr, _real_datetime))
                    count += 1
                elif value is _real_date:
                    setattr(mod, attr, FrozenDate)
                    self._rebound.append((mod, attr, _real_date))
                    count += 1
        return count

    # -- proof -----------------------------------------------------------

    def prove(self) -> dict:
        """Positive evidence that the freeze is in force.

        Tests both binding paths, because they fail independently:
        a module-level ``from datetime import datetime`` resolved before
        the patch, and a function-local import resolved after it.
        """
        expect_dt = self.instant.replace(microsecond=self.instant.microsecond)
        expect_d = self.instant.date()

        # Path 1 — fresh import, the common case in application code.
        from datetime import datetime as dt_fresh, date as d_fresh
        p1_now = dt_fresh.now()
        p1_today = d_fresh.today()

        # Path 2 — the datetime module accessed as a module attribute.
        p2_now = _dtmod.datetime.now()
        p2_utc = _dtmod.datetime.utcnow()

        # Path 3 — an application module's own binding, which is the one
        # that actually matters. Chosen because app.services is imported
        # by nearly every financial path.
        p3 = None
        svc = sys.modules.get('app.services')
        if svc is not None and hasattr(svc, 'datetime'):
            p3 = svc.datetime.now()

        checks = {
            'fresh_import_datetime_now': p1_now == expect_dt,
            'fresh_import_date_today': p1_today == expect_d,
            'module_attr_datetime_now': p2_now == expect_dt,
            'module_attr_datetime_utcnow': p2_utc == expect_dt,
            'isinstance_real_date_still_true':
                isinstance(_real_date(2000, 1, 1), _dtmod.date),
            'isinstance_real_datetime_still_true':
                isinstance(_real_datetime(2000, 1, 1), _dtmod.datetime),
        }
        if p3 is not None:
            checks['app_services_binding'] = (p3 == expect_dt)

        return {
            'frozen_to': self.instant.isoformat(),
            'rebound_names': len(self._rebound),
            'checks': checks,
            'proven': all(checks.values()),
        }

    # -- remove ----------------------------------------------------------

    def uninstall(self) -> None:
        if not self._installed:
            return
        for mod, attr, original in reversed(self._rebound):
            try:
                setattr(mod, attr, original)
            except Exception:
                pass
        self._rebound.clear()
        _dtmod.datetime = _real_datetime
        _dtmod.date = _real_date
        self._installed = False


class FreezeNotProven(RuntimeError):
    """The clock freeze could not be demonstrated to be in force.

    Capture aborts rather than writing masters that would drift with the
    wall clock — a master that silently expires is worse than no master,
    because it trains people to ignore the alarm.
    """


def install_proven(instant: _real_datetime) -> tuple[ClockFreeze, dict]:
    """Freeze the clock and refuse to continue unless it is provable."""
    freeze = ClockFreeze(instant).install()
    proof = freeze.prove()
    if not proof['proven']:
        freeze.uninstall()
        failed = [k for k, v in proof['checks'].items() if not v]
        raise FreezeNotProven(
            'Clock freeze did not take effect. Failing checks: '
            + ', '.join(failed))
    return freeze, proof
