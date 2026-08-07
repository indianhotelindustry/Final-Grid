"""
Historical replay support for invariants.

The three questions the charter asks
------------------------------------
1. Was this invariant true on the business date?
2. Is it still true today?
3. If not, where is the earliest point of divergence?

What can honestly be answered
-----------------------------
The database holds one state: the present one. There is no archive of
what it looked like on 27 May, so "was this invariant true then" cannot
mean "restore the database to that night and evaluate". Claiming
otherwise would be the most damaging kind of false evidence, because it
would look exactly like the real thing.

What *can* be done, and what this module does, is three things that are
each true statements:

* **As of the date.** Evaluate the invariant scoped to that business date
  with the clock frozen to noon on it. This is the current data seen
  through that day's window, and it is what the system would say today if
  asked about that day.

* **As of today.** Evaluate the same date-scoped invariant with the clock
  frozen to the *current* business date. Anything that differs between
  the two is clock-dependence: a present-tense query inside a date-scoped
  rule. That is the same defect class D3 reports as as-at drift, found
  here at the level of an obligation rather than a figure.

* **Against the frozen record.** Where a night audit closed the day, the
  snapshot is genuine historical state — written that night by the code
  of that night. INV-B03 compares against it, so an invariant failing on
  a date whose snapshot still matches is a different animal from one
  failing on a date whose snapshot has moved, and the report says which.

**Earliest divergence** is the earliest date in the replayed timeline at
which the invariant stops holding. It is reported with the population at
that date, because "first failed on 3 May" means something quite
different when 3 May had four hundred rows than when it had none.
"""
from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass, field

from verification.config import PRODUCTION_DB
from verification.dbcopy import (
    assert_production_untouched, make_copy, sqlalchemy_url,
)
from verification.golden.capture import FREEZE_TIME
from verification.invariants import registry
from verification.invariants.context import Context, Scope
from verification.invariants.engine import evaluate_one, _utcnow
from verification.invariants.model import Mode, Status


@dataclass
class DateOutcome:
    date: str
    status_as_of_date: str = ''
    status_as_of_today: str = ''
    population_as_of_date: int = 0
    violations_as_of_date: int = 0
    violations_as_of_today: int = 0
    clock_dependent: bool = False
    is_closed: bool = False


@dataclass
class InvariantHistory:
    invariant_id: str
    title: str
    severity: str
    blocking: str
    dates: list = field(default_factory=list)
    earliest_divergence: str = ''
    earliest_divergence_population: int = 0
    clock_dependent_dates: list = field(default_factory=list)
    holds_today: bool = False
    evaluated_dates: int = 0

    @property
    def ever_violated(self) -> bool:
        return any(d.status_as_of_date == Status.VIOLATED for d in self.dates)


@dataclass
class HistoryRun:
    started_at: str
    finished_at: str = ''
    duration_seconds: float = 0.0
    app_version: str = ''
    pvf_version: str = ''
    business_date: str = ''
    first_date: str = ''
    source_db: str = ''
    source_hash_before: str = ''
    source_hash_after: str = ''
    read_only_verified: bool = False
    dates_replayed: int = 0
    invariants: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    total_writes: int = 0

    @property
    def diverged(self) -> list:
        return [h for h in self.invariants if h.earliest_divergence]

    @property
    def clock_dependent(self) -> list:
        return [h for h in self.invariants if h.clock_dependent_dates]

    @property
    def verdict(self) -> str:
        if not self.read_only_verified or self.total_writes:
            return 'UNVERIFIED'
        if self.clock_dependent:
            return 'FAIL'
        if self.diverged:
            return 'FAIL'
        if not self.invariants:
            return 'INCOMPLETE'
        return 'PASS'


def _app_version() -> str:
    try:
        from app import APP_VERSION
        return APP_VERSION
    except Exception:                                    # noqa: BLE001
        return 'unknown'


def run_history(source: str = PRODUCTION_DB,
                ids: list | None = None,
                from_date: _dt.date | None = None,
                to_date: _dt.date | None = None,
                quiet: bool = False) -> HistoryRun:
    """Replay every date-capable invariant across the dataset's history."""
    import os

    from verification import __version__ as PVF_VERSION
    from verification.replay import timeline as tl
    from verification.replay.replay import _Clock, _reset_session

    started = _utcnow()
    t0 = time.perf_counter()

    handle = make_copy(name='pvf_inv_history.db', source=source)
    line = tl.discover(handle.copy_path, from_date, to_date)
    days = [e.date for e in line.dates]
    closed = {e.date for e in line.dates if e.is_closed}
    business_date = _dt.date.fromisoformat(line.business_date)

    candidates = registry.select(ids=ids)
    replayable = [i for i in candidates
                  if i.supports(Mode.HISTORICAL_REPLAY)
                  or i.supports(Mode.BUSINESS_DATE)]
    skipped = [{'invariant_id': i.invariant_id,
                'reason': (f'declares modes {", ".join(i.modes)}; none of '
                           f'them is date-scoped, so it has no historical '
                           f'form and is not replayed')}
               for i in candidates if i not in replayable]

    run = HistoryRun(
        started_at=started, pvf_version=PVF_VERSION,
        business_date=line.business_date, first_date=days[0] if days else '',
        source_db=handle.source_path,
        source_hash_before=handle.source_hash_before,
        dates_replayed=len(days), skipped=skipped)

    if not quiet:
        print(f'[inv-history] dates      : {len(days)} '
              f'({days[0]} .. {days[-1]})' if days else '[inv-history] no dates')
        print(f'[inv-history] invariants : {len(replayable)} date-capable, '
              f'{len(skipped)} without a historical form')

    os.environ['DATABASE_URL'] = sqlalchemy_url(handle)
    os.environ.setdefault('FLASK_ENV', 'production')

    clock = _Clock()
    histories = {i.invariant_id: InvariantHistory(
        invariant_id=i.invariant_id, title=i.title, severity=i.severity,
        blocking=i.blocking) for i in replayable}
    try:
        clock.freeze(business_date)
        from app import create_app
        app = create_app()
        clock.freeze(business_date)
        run.app_version = _app_version()

        with app.app_context():
            # -- pass one: each date asked as of itself -----------------
            for index, day in enumerate(days, 1):
                clock.freeze(_dt.date.fromisoformat(day))
                _reset_session()
                ctx = Context(handle.copy_path, app=app,
                              scope=Scope(mode=Mode.HISTORICAL_REPLAY,
                                          business_date=day,
                                          replay_context={'asked_as_of': day}),
                              business_date=day)
                ctx.install_sqlalchemy_meter()
                try:
                    for inv in replayable:
                        result = evaluate_one(inv, ctx)
                        history = histories[inv.invariant_id]
                        history.dates.append(DateOutcome(
                            date=day, status_as_of_date=result.status,
                            population_as_of_date=result.population,
                            violations_as_of_date=result.violation_count,
                            is_closed=day in closed))
                        run.total_writes += result.metering.db_writes
                finally:
                    ctx.close()
                if not quiet and (index % 10 == 0 or index == len(days)):
                    print(f'[inv-history] as-of-date: {index}/{len(days)}')

            # -- pass two: each date asked as of today ------------------
            clock.freeze(business_date)
            for index, day in enumerate(days, 1):
                _reset_session()
                ctx = Context(handle.copy_path, app=app,
                              scope=Scope(mode=Mode.HISTORICAL_REPLAY,
                                          business_date=day,
                                          replay_context={
                                              'asked_as_of':
                                                  line.business_date}),
                              business_date=day)
                ctx.install_sqlalchemy_meter()
                try:
                    for inv in replayable:
                        result = evaluate_one(inv, ctx)
                        history = histories[inv.invariant_id]
                        outcome = next(d for d in history.dates
                                       if d.date == day)
                        outcome.status_as_of_today = result.status
                        outcome.violations_as_of_today = result.violation_count
                        outcome.clock_dependent = (
                            outcome.status_as_of_date != result.status
                            or outcome.violations_as_of_date
                            != result.violation_count)
                        run.total_writes += result.metering.db_writes
                finally:
                    ctx.close()
                if not quiet and (index % 10 == 0 or index == len(days)):
                    print(f'[inv-history] as-of-today: {index}/{len(days)}')
    finally:
        clock.release()

    for history in histories.values():
        history.evaluated_dates = len(history.dates)
        for outcome in history.dates:
            if outcome.status_as_of_date == Status.VIOLATED and \
                    not history.earliest_divergence:
                history.earliest_divergence = outcome.date
                history.earliest_divergence_population = \
                    outcome.population_as_of_date
            if outcome.clock_dependent:
                history.clock_dependent_dates.append(outcome.date)
        last = history.dates[-1] if history.dates else None
        history.holds_today = bool(
            last and last.status_as_of_date == Status.HOLDS)
    run.invariants = [histories[i.invariant_id] for i in replayable]

    run.source_hash_after = assert_production_untouched(handle)
    run.read_only_verified = (
        run.source_hash_after == run.source_hash_before)
    run.finished_at = _utcnow()
    run.duration_seconds = round(time.perf_counter() - t0, 2)
    return run
