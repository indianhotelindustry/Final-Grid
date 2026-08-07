"""
Replay orchestration.

One run, in order:

  1. copy production through the SQLite backup API and fingerprint the
     original (``verification.dbcopy``, unchanged from D1);
  2. read the timeline out of the copy with ``sqlite3``, before any
     application module exists;
  3. build the LEDGER for every date — still without the application, so
     the reference account cannot be influenced by the code under test;
  4. build the Flask application, with the clock frozen to the current
     business date so that ``create_app``'s own writes land on the copy
     exactly as they do in D2;
  5. PASS A — probe the engines for each date with the clock frozen to
     noon on that date, ascending;
  6. PASS B — the same, descending. Two answers that differ mean state
     leaked between dates inside the process, which would make every
     figure in the run suspect;
  7. PASS C — probe each PAST date again with the clock frozen to the
     CURRENT business date. Anything that moves is a present-tense query
     inside a historical report;
  8. read the RECORDED account and the application's own snapshot
     integrity verdict;
  9. rebuild the LEDGER. It must be identical to step 3 — positive
     evidence that nothing in steps 4-8 wrote to the copy;
 10. re-verify that production is byte-identical.

Why the freeze is re-installed per date rather than run per date in a
separate process
----------------------------------------------------------------------
D2 uses one process per capture because it captures once. A replay
touches every date in the history, and a process launch plus a full
``create_app`` per date would put a two-year dataset far outside the
fifteen-minute budget that keeps this framework switched on.

The cost of staying in one process is the risk that state carries from
one date to the next. That risk is not argued away — it is measured, by
PASS B. If any figure depends on the order the dates were replayed in,
the run says so and fails.
"""
from __future__ import annotations

import datetime as _dt
import os
import time
from dataclasses import dataclass, field

from verification.config import PRODUCTION_DB, PROJECT_ROOT
from verification.dbcopy import (
    CopyHandle, assert_production_untouched, make_copy, sqlalchemy_url,
)
from verification.golden.capture import FREEZE_TIME
from verification.golden.freeze import install_proven
from verification.replay import engines, ledger as ledgermod, recorded, timeline
from verification.replay import reconcile as rec

LEDGERS_DIR = os.path.join(PROJECT_ROOT, 'verification', 'ledgers')


#: Engine paths excluded from the as-at comparison, each with the reason.
#: Same discipline as D2's normalisation rules: narrow, named, justified,
#: and reported on every run with its hit count. A rule that stops
#: matching is itself reported, because a masking rule that quietly
#: became inert can only ever hide a real difference.
ASAT_EXCLUSIONS: list[tuple[str, str]] = [
    ('nas.audit_header.generated_at',
     'records when the report was generated, not what happened on the '
     'date. It is SUPPOSED to move when the clock moves.'),
]


class ReplayAborted(RuntimeError):
    """A precondition for a trustworthy replay was not met."""


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class DateReplay:
    date: str
    is_business_date: bool = False
    is_closed: bool = False
    audit_status: str = ''
    has_snapshot: bool = False
    traded: bool = False
    row_counts: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)

    frozen_at: str = ''
    freeze_proven: bool = False

    ledger: dict = field(default_factory=dict)
    engine: dict = field(default_factory=dict)
    engine_errors: dict = field(default_factory=dict)
    engine_truncations: list = field(default_factory=list)

    asat_compared: bool = False
    asat_drift: list = field(default_factory=list)
    asat_exclusion_hits: dict = field(default_factory=dict)

    order_mismatch: list = field(default_factory=list)

    recorded: dict = field(default_factory=dict)
    recorded_notes: list = field(default_factory=list)
    snapshot_integrity: dict = field(default_factory=dict)
    history_drift: list = field(default_factory=list)

    reconciliations: list = field(default_factory=list)
    unreconciled_paths: list = field(default_factory=list)

    duration_ms: int = 0

    # -- verdict inputs ---------------------------------------------------

    @property
    def unreconciled(self) -> list:
        return [r for r in self.reconciliations
                if r.status == rec.Status.UNRECONCILED]

    @property
    def not_comparable(self) -> list:
        """Gaps in verification. ``NO_ACTIVITY`` is deliberately excluded:
        a day on which the hotel did no business is not a hole in the
        measurement."""
        return [r for r in self.reconciliations
                if r.status in (rec.Status.NOT_COMPARABLE, rec.Status.VACUOUS)]

    @property
    def snapshot_intact(self) -> bool:
        return bool(self.snapshot_integrity.get('matches', True))


@dataclass
class ReplayRun:
    started_at: str
    finished_at: str = ''
    duration_seconds: float = 0.0
    app_version: str = ''
    pvf_version: str = ''
    business_date: str = ''
    first_activity: str = ''
    source_db: str = ''
    source_hash_before: str = ''
    source_hash_after: str = ''
    read_only_verified: bool = False
    copy_method: str = ''

    dates: list = field(default_factory=list)
    timeline_excluded: list = field(default_factory=list)
    timeline_window_notes: list = field(default_factory=list)
    date_insensitive: list = field(default_factory=list)
    gaps_filled: int = 0
    not_replayable: list = field(default_factory=list)
    asat_exclusions: list = field(default_factory=list)

    ledger_stable: bool = False
    ledger_instability: list = field(default_factory=list)
    order_proof_run: bool = False
    mtd_checks: list = field(default_factory=list)

    # -- aggregates -------------------------------------------------------

    @property
    def counts(self) -> dict:
        out = {
            'dates': len(self.dates),
            'closed': sum(1 for d in self.dates if d.is_closed),
            'with_snapshot': sum(1 for d in self.dates if d.has_snapshot),
            'traded': sum(1 for d in self.dates if d.traded),
            'reconciled': 0,
            'unreconciled': 0,
            'not_comparable': 0,
            'no_activity': 0,
            'asat_drift': sum(len(d.asat_drift) for d in self.dates),
            'history_drift': sum(len(d.history_drift) for d in self.dates),
            'order_mismatch': sum(len(d.order_mismatch) for d in self.dates),
            'engine_errors': sum(len(d.engine_errors) for d in self.dates),
        }
        for d in self.dates:
            for r in d.reconciliations:
                if r.status == rec.Status.RECONCILED:
                    out['reconciled'] += 1
                elif r.status == rec.Status.UNRECONCILED:
                    out['unreconciled'] += 1
                elif r.status == rec.Status.NO_ACTIVITY:
                    out['no_activity'] += 1
                else:
                    out['not_comparable'] += 1
        return out

    @property
    def blocking(self) -> list:
        """Every finding that must stop a release, as readable lines."""
        out: list[str] = []
        for d in self.dates:
            for r in d.unreconciled:
                out.append(f'{d.date} {r.rule_id} {r.engine_path} '
                           f'!= {r.ledger_expr} (delta {r.delta})')
            for drift in d.asat_drift:
                if d.is_closed:
                    out.append(f'{d.date} ASAT_DRIFT (closed day) '
                               f'{drift["path"]}')
            for drift in d.history_drift:
                out.append(f'{d.date} HISTORY_DRIFT {drift["path"]}')
            for path in d.order_mismatch:
                out.append(f'{d.date} ORDER_DEPENDENT {path}')
            if not d.snapshot_intact:
                out.append(f'{d.date} SNAPSHOT_INTEGRITY_FAILURE')
        if not self.ledger_stable:
            out.append('LEDGER_INSTABILITY — the primary record changed '
                       'during the run')
        for check in self.mtd_checks:
            if check['status'] == rec.Status.UNRECONCILED:
                out.append(f'{check["date"]} RC20 month-to-date '
                           f'{check["engine"]} != {check["ledger"]}')
        return out

    @property
    def overall(self) -> str:
        if any(d.engine_errors for d in self.dates):
            return 'ERROR'
        if self.blocking:
            return 'FAIL'
        if any(d.not_comparable for d in self.dates):
            return 'INCOMPLETE'
        if not self.read_only_verified:
            return 'UNVERIFIED'
        return 'PASS'


# ---------------------------------------------------------------------------
# Application build
# ---------------------------------------------------------------------------

def _build_app(handle: CopyHandle):
    os.environ['DATABASE_URL'] = sqlalchemy_url(handle)
    os.environ.setdefault('FLASK_ENV', 'production')
    from app import create_app
    return create_app()


def _app_version() -> str:
    try:
        from app import APP_VERSION
        return APP_VERSION
    except Exception:
        return 'unknown'


def _utcnow() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat()


class _Clock:
    """Sequential re-installation of D2's proven clock freeze.

    ``ClockFreeze`` is documented as not reentrant. It is not used
    reentrantly here: the previous freeze is uninstalled before the next
    is installed, and each installation is re-proven. The proof per date
    is what makes the sequence trustworthy rather than merely plausible.
    """

    def __init__(self) -> None:
        self._active = None
        self.proofs: dict[str, dict] = {}

    def freeze(self, day: _dt.date) -> dict:
        self.release()
        instant = _dt.datetime.combine(day, FREEZE_TIME)
        self._active, proof = install_proven(instant)
        # Application modules imported since the last install captured the
        # real classes; rebinding is cheap and its count is in the proof.
        self._active.rebind_loaded_modules()
        proof = self._active.prove()
        if not proof['proven']:
            raise ReplayAborted(
                f'Clock freeze for {day} could not be proven after rebinding. '
                f'Replaying a date under an unproven clock would record '
                f'today\'s numbers under a historical heading.')
        self.proofs[day.isoformat()] = proof
        return proof

    def release(self) -> None:
        if self._active is not None:
            self._active.uninstall()
            self._active = None


def _reset_session() -> None:
    """Drop every identity-mapped object between dates.

    Without this, a ``Reservation`` loaded while the clock was frozen to
    one date would be handed back from the session while it is frozen to
    another. Nothing in the application would notice, and the resulting
    figures would be a blend of two days.
    """
    from app.models import db
    db.session.rollback()
    db.session.remove()


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------

def _probe_dates(clock: _Clock, days: list, quiet: bool,
                 label: str) -> tuple[dict, dict]:
    """Probe each date with the clock frozen to that date.

    Returns ``({date: probe_result}, {date: milliseconds})``.
    """
    out: dict[str, tuple] = {}
    timing: dict[str, int] = {}
    for i, day in enumerate(days, 1):
        clock.freeze(_dt.date.fromisoformat(day))
        _reset_session()
        t0 = time.perf_counter()
        out[day] = engines.probe_safely(_dt.date.fromisoformat(day))
        timing[day] = int((time.perf_counter() - t0) * 1000)
        if not quiet and (i % 10 == 0 or i == len(days)):
            print(f'[replay] {label}: {i}/{len(days)} dates')
    return out, timing


def _probe_asat(clock: _Clock, days: list, business_date: _dt.date,
                quiet: bool) -> dict:
    """Probe each past date with the clock frozen to TODAY's business date."""
    clock.freeze(business_date)
    out: dict[str, tuple] = {}
    for i, day in enumerate(days, 1):
        _reset_session()
        out[day] = engines.probe_safely(_dt.date.fromisoformat(day))
        if not quiet and (i % 10 == 0 or i == len(days)):
            print(f'[replay] PASS C (as-at today): {i}/{len(days)} dates')
    return out


def _drift(at_date: dict, at_today: dict) -> tuple[list, dict]:
    """Paths that moved between the two as-at passes, minus exclusions."""
    excluded = {path for path, _why in ASAT_EXCLUSIONS}
    hits: dict[str, int] = {}
    out: list[dict] = []
    for path in sorted(set(at_date) | set(at_today)):
        a, b = at_date.get(path), at_today.get(path)
        if a == b:
            continue
        if path in excluded:
            hits[path] = hits.get(path, 0) + 1
            continue
        out.append({'path': path,
                    'asked_on_the_date': '' if a is None else a,
                    'asked_today': '' if b is None else b})
    return out, hits


def _history_drift(engine: dict, recorded_figures: dict) -> list:
    """Recomputed figures against the frozen close, where both exist.

    Only pairs the framework can map are compared. Comparing the whole
    snapshot against the whole engine account would produce hundreds of
    unmatched paths and drown the handful that mean something.
    """
    pairs = [
        ('nas.payment_summary.total_collected',
         'snapshot.payments.total_collected'),
        ('nas.payment_summary.total_ota_settled',
         'snapshot.payments.total_ota_settled'),
        ('nas.payment_summary.payment_count',
         'snapshot.payments.payment_count'),
        ('nas.revenue_summary.accrual_net', 'snapshot.revenue.accrual_net'),
        ('nas.revenue_summary.room_revenue', 'snapshot.revenue.room_revenue'),
        ('nas.revenue_summary.tax_amount', 'snapshot.revenue.tax_amount'),
        ('nas.revenue_summary.discount_total',
         'snapshot.revenue.discount_total'),
        ('nas.occupancy_position.occupied', 'snapshot.occupancy.occupied'),
        ('nas.occupancy_position.total_rooms',
         'snapshot.occupancy.total_rooms'),
        ('nas.folio_control.total_outstanding',
         'snapshot.folio.total_outstanding'),
        ('nas.final_control.reconciliation_difference',
         'snapshot.final_control.reconciliation_difference'),
        ('nas.payment_summary.total_collected', 'stored.total_revenue'),
        ('nas.revenue_summary.accrual_net', 'stored.accrual_revenue'),
        ('nas.occupancy_position.occupied', 'stored.occupancy_count'),
    ]
    out: list[dict] = []
    for engine_path, recorded_path in pairs:
        now = engine.get(engine_path)
        then = recorded_figures.get(recorded_path)
        if now is None or then is None:
            continue
        try:
            moved = abs(float(now) - float(then)) > 0.005
        except (TypeError, ValueError):
            moved = str(now) != str(then)
        if moved:
            out.append({'path': f'{engine_path} vs {recorded_path}',
                        'frozen_at_close': then,
                        'recomputed_today': now})
    return out


def _date_insensitive(dates: list) -> list:
    """Engine figures that held the same value on every replayed date.

    Reported, never blocking. A figure that never moves is either
    genuinely constant — the room count, the tax rate — or it is not
    date-scoped at all, and the second case is a present-tense number
    published under a historical heading. The framework cannot tell which
    without judgement, so it states the fact and leaves the judgement
    where it belongs.

    The signal is only as strong as the number of days that actually
    differ from each other, which is why the count of replayed dates is
    printed alongside it. Over two days it means very little; over two
    years it is close to conclusive.
    """
    live = [d for d in dates if d.engine]
    if len(live) < 2:
        return []
    shared = set(live[0].engine)
    for d in live[1:]:
        shared &= set(d.engine)
    out: list[dict] = []
    for path in sorted(shared):
        # Container shapes, not figures. A list that is always empty says
        # nothing about whether the value it would contain is date-scoped.
        if path.endswith('[len]') or path.endswith('[type]'):
            continue
        values = {d.engine[path] for d in live}
        if len(values) == 1:
            out.append({'path': path, 'value': live[0].engine[path],
                        'dates': len(live)})
    return out


def _mtd_checks(dates: list) -> list:
    """RC20 — month-to-date collections against the sum of the days.

    Evaluated across dates because that is the only place the claim can
    be tested: a month-to-date figure that is right on every individual
    day and wrong in aggregate is exactly the failure this catches.
    """
    out: list[dict] = []
    by_date = {d.date: d for d in dates}
    for d in dates:
        engine_value = d.engine.get('kpi.monthly_revenue')
        if engine_value is None:
            continue
        day = _dt.date.fromisoformat(d.date)
        total = 0.0
        complete = True
        cursor = day.replace(day=1)
        while cursor <= day:
            other = by_date.get(cursor.isoformat())
            if other is None:
                complete = False
                break
            value = other.ledger.get('payments.direct.non_voided')
            if value is None:
                complete = False
                break
            total += float(value)
            cursor += _dt.timedelta(days=1)
        if not complete:
            out.append({'date': d.date, 'status': rec.Status.NOT_COMPARABLE,
                        'engine': engine_value, 'ledger': '',
                        'note': ('the month-to-date window starts before the '
                                 'replayed range, so the daily sum is not '
                                 'available for every day in it')})
            continue
        status = (rec.Status.RECONCILED
                  if abs(float(engine_value) - total) <= 0.005
                  else rec.Status.UNRECONCILED)
        out.append({'date': d.date, 'status': status,
                    'engine': str(engine_value), 'ledger': f'{total:.6f}',
                    'note': 'month-to-date against the sum of the daily '
                            'direct collections in the ledger'})
    return out


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run_replay(source: str = PRODUCTION_DB,
               from_date: _dt.date | None = None,
               to_date: _dt.date | None = None,
               prove_order: bool = True,
               quiet: bool = False) -> ReplayRun:
    """Execute a full historical replay against a disposable copy."""
    from verification import __version__ as PVF_VERSION

    started = _utcnow()
    t0 = time.perf_counter()

    handle = make_copy(name='pvf_replay.db', source=source)
    line = timeline.discover(handle.copy_path, from_date, to_date)
    days = [e.date for e in line.dates]
    business_date = _dt.date.fromisoformat(line.business_date)

    if not quiet:
        print(f'[replay] working copy : {handle.copy_path} ({handle.method})')
        print(f'[replay] source sha256: {handle.source_hash_before}')
        print(f'[replay] business date: {line.business_date}')
        print(f'[replay] history      : {line.first_activity} .. '
              f'{line.business_date}  ({len(days)} dates, '
              f'{line.gaps_filled} with no activity)')

    # -- step 3: the reference account, built without the application ----
    ledgers_before = ledgermod.build_all(handle.copy_path, days)

    run = ReplayRun(
        started_at=started,
        pvf_version=PVF_VERSION,
        business_date=line.business_date,
        first_activity=line.first_activity,
        source_db=handle.source_path,
        source_hash_before=handle.source_hash_before,
        copy_method=handle.method,
        timeline_excluded=line.excluded,
        timeline_window_notes=line.window_notes,
        gaps_filled=line.gaps_filled,
        not_replayable=[{'entry_point': name, 'reason': why}
                        for name, why in engines.NOT_REPLAYABLE],
        asat_exclusions=[{'path': path, 'why': why}
                         for path, why in ASAT_EXCLUSIONS],
        order_proof_run=prove_order,
    )

    clock = _Clock()
    try:
        # -- step 4: application, built under the current business date --
        clock.freeze(business_date)
        app = _build_app(handle)
        clock.freeze(business_date)          # rebind the modules it imported
        run.app_version = _app_version()

        with app.app_context():
            from app.services import get_business_date
            if get_business_date() != business_date:
                raise ReplayAborted(
                    f'Pre-read business date {business_date} does not match '
                    f'the application\'s get_business_date() '
                    f'{get_business_date()}. Every date in the replay is '
                    f'derived from it, so the whole run would be measuring '
                    f'the wrong window.')

            # -- step 5: PASS A ---------------------------------------
            if not quiet:
                print(f'[replay] PASS A: probing {len(days)} dates '
                      f'at their own date')
            pass_a, pass_a_ms = _probe_dates(clock, days, quiet, 'PASS A')

            # -- step 6: PASS B, reverse order ------------------------
            pass_b: dict = {}
            if prove_order:
                if not quiet:
                    print('[replay] PASS B: same dates, reverse order '
                          '(order-independence proof)')
                pass_b, _ = _probe_dates(clock, list(reversed(days)), quiet,
                                         'PASS B')

            # -- step 7: PASS C, asked today --------------------------
            past = [e.date for e in line.dates if not e.is_business_date]
            if not quiet and past:
                print(f'[replay] PASS C: re-asking {len(past)} past dates '
                      f'with the clock at {business_date}')
            pass_c = _probe_asat(clock, past, business_date, quiet) if past else {}

            # -- step 8: the recorded account -------------------------
            clock.freeze(business_date)
            _reset_session()
            recorded_by_date: dict = {}
            for day in days:
                recorded_by_date[day] = recorded.capture(
                    _dt.date.fromisoformat(day))

            # -- assemble --------------------------------------------
            for entry in line.dates:
                day = entry.date
                figures, errors, trunc = pass_a[day]
                record = DateReplay(
                    date=day,
                    is_business_date=entry.is_business_date,
                    is_closed=entry.is_closed,
                    audit_status=entry.audit_status,
                    has_snapshot=entry.has_snapshot,
                    row_counts=entry.row_counts,
                    reasons=entry.reasons,
                    frozen_at=_dt.datetime.combine(
                        _dt.date.fromisoformat(day), FREEZE_TIME).isoformat(),
                    freeze_proven=bool(
                        clock.proofs.get(day, {}).get('proven')),
                    ledger=ledgers_before[day],
                    engine=figures,
                    engine_errors=errors,
                    engine_truncations=trunc,
                )

                if prove_order and day in pass_b:
                    b_figures = pass_b[day][0]
                    record.order_mismatch = sorted(
                        path for path in set(figures) | set(b_figures)
                        if figures.get(path) != b_figures.get(path))

                if day in pass_c:
                    record.asat_compared = True
                    record.asat_drift, record.asat_exclusion_hits = _drift(
                        figures, pass_c[day][0])

                rec_figures, integrity, notes = recorded_by_date[day]
                record.recorded = rec_figures
                record.snapshot_integrity = integrity
                record.recorded_notes = notes
                if rec_figures:
                    record.history_drift = _history_drift(figures, rec_figures)

                record.traded = any(v for v in entry.row_counts.values())
                record.reconciliations, record.unreconciled_paths = rec.apply(
                    figures, record.ledger, day_traded=record.traded)
                record.duration_ms = pass_a_ms.get(day, 0)
                run.dates.append(record)

            run.mtd_checks = _mtd_checks(run.dates)
            run.date_insensitive = _date_insensitive(run.dates)
    finally:
        clock.release()

    # -- step 9: the ledger must not have moved --------------------------
    ledgers_after = ledgermod.build_all(handle.copy_path, days)
    instability: list[dict] = []
    for day in days:
        before, after = ledgers_before[day], ledgers_after[day]
        for path in sorted(set(before) | set(after)):
            if before.get(path) != after.get(path):
                instability.append({'date': day, 'path': path,
                                    'before': before.get(path, ''),
                                    'after': after.get(path, '')})
    run.ledger_instability = instability
    run.ledger_stable = not instability

    # -- step 10 ---------------------------------------------------------
    run.source_hash_after = assert_production_untouched(handle)
    run.read_only_verified = run.source_hash_after == run.source_hash_before
    run.finished_at = _utcnow()
    run.duration_seconds = round(time.perf_counter() - t0, 2)
    return run


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def ledger_dir(tag: str) -> str:
    return os.path.join(LEDGERS_DIR, tag)


def write_ledgers(run: ReplayRun, tag: str) -> str:
    """Persist a replay as the stored ledger set *tag*."""
    import json
    from dataclasses import asdict

    out_dir = ledger_dir(tag)
    dates_dir = os.path.join(out_dir, 'dates')
    os.makedirs(dates_dir, exist_ok=True)

    keep = {f'{d.date}.json' for d in run.dates}
    for existing in os.listdir(dates_dir):
        if existing.endswith('.json') and existing not in keep:
            os.remove(os.path.join(dates_dir, existing))

    for d in run.dates:
        with open(os.path.join(dates_dir, f'{d.date}.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(asdict(d), fh, indent=2, sort_keys=True, default=str)
            fh.write('\n')

    index = {k: v for k, v in asdict(run).items() if k != 'dates'}
    index['counts'] = run.counts
    index['date_index'] = [
        {'date': d.date, 'is_closed': d.is_closed,
         'has_snapshot': d.has_snapshot,
         'ledger_figures': len(d.ledger), 'engine_figures': len(d.engine),
         'row_counts': d.row_counts}
        for d in run.dates]
    with open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8') as fh:
        json.dump(index, fh, indent=2, sort_keys=True, default=str)
        fh.write('\n')
    return out_dir


def read_ledgers(tag: str) -> tuple[dict, dict]:
    """Return ``(index, {date: stored_record})``."""
    import json

    out_dir = ledger_dir(tag)
    index_path = os.path.join(out_dir, 'index.json')
    if not os.path.isfile(index_path):
        raise FileNotFoundError(
            f'No stored replay named {tag!r}. Capture one first:\n'
            f'    python -m verification replay --tag {tag}')
    with open(index_path, encoding='utf-8') as fh:
        index = json.load(fh)
    dates_dir = os.path.join(out_dir, 'dates')
    stored: dict = {}
    for name in sorted(os.listdir(dates_dir)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(dates_dir, name), encoding='utf-8') as fh:
            record = json.load(fh)
        stored[record['date']] = record
    return index, stored
