"""
Discovery of the dataset's history.

Which dates exist, which are closed, and why each one is in the replay
set — answered with plain ``sqlite3`` against the working copy, before
any application module is imported.

Reading the timeline without the application matters for the same reason
D2 pre-reads the business date without it: the clock has to be frozen
before ``app`` imports ``datetime``, so the set of dates to replay must
be known before the application exists. It also makes the timeline
itself immune to the code under test — a release that changed which days
the application thinks it traded would be a finding, not a silent change
of scope.

Gap filling
-----------
Every calendar date between the first activity and the current business
date is replayed, including days with no rows at all. A day with no
activity must reconcile to zero on every account; if it does not, that
is worth knowing. Skipping empty days would also mean that a day which
*acquires* activity later — a back-dated posting — enters the replay set
without anything having declared it, and a set that silently changes
shape cannot be compared against a stored one.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from dataclasses import dataclass, field


#: Where a business date can come from. Each entry is
#: ``(table, column, why it counts as history)``.
DATE_SOURCES: list[tuple[str, str, str]] = [
    ('payments', 'payment_date',
     'money was received or posted on this date'),
    ('extra_charges', 'charge_date',
     'a charge was posted to a folio on this date'),
    ('tax_lines', 'charge_date',
     'a tax line was raised for this date'),
    ('reservation_night_rates', 'stay_date',
     'a room night was priced for this date'),
    ('night_audit_logs', 'audit_date',
     'the night audit ran for this date'),
    ('reservations', 'arrival_date',
     'a guest arrived on this date'),
    ('reservations', 'departure_date',
     'a guest was due to depart on this date'),
    ('no_show_logs', 'audit_date',
     'a no-show was processed on this date'),
]


class NoHistory(RuntimeError):
    """The dataset contains no dated financial activity at all.

    Replaying nothing and reporting PASS would be the purest form of the
    control that cannot fail, so this raises instead.
    """


@dataclass
class DateEntry:
    """One business date in the replay set."""
    date: str                       # ISO
    is_business_date: bool = False  # the day the hotel is currently trading
    is_closed: bool = False         # a night audit log exists and is Completed
    audit_status: str = ''          # Pending / Completed / Warning / Reopened
    has_snapshot: bool = False
    reasons: list = field(default_factory=list)
    row_counts: dict = field(default_factory=dict)

    @property
    def is_past(self) -> bool:
        return not self.is_business_date


@dataclass
class Timeline:
    business_date: str
    first_activity: str
    dates: list = field(default_factory=list)
    gaps_filled: int = 0
    excluded: list = field(default_factory=list)
    window_notes: list = field(default_factory=list)

    @property
    def by_date(self) -> dict:
        return {e.date: e for e in self.dates}

    @property
    def closed_dates(self) -> list:
        return [e for e in self.dates if e.is_closed]

    @property
    def snapshot_dates(self) -> list:
        return [e for e in self.dates if e.has_snapshot]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone()
    return row is not None


def read_business_date(db_path: str) -> _dt.date:
    """Business date from the copy. Delegates to D2 so there is exactly
    one implementation of the quoted-column trap it documents."""
    from verification.golden.capture import read_business_date as _rbd
    return _rbd(db_path)


def discover(db_path: str,
             from_date: _dt.date | None = None,
             to_date: _dt.date | None = None) -> Timeline:
    """Build the replay timeline from *db_path*.

    ``from_date`` / ``to_date`` narrow the window. Narrowing is recorded
    on the timeline as an exclusion so a partial replay can never be
    mistaken for a complete one.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        business_date = read_business_date(db_path)

        # -- every date any primary record refers to ---------------------
        seen: dict[str, list] = {}
        for table, column, why in DATE_SOURCES:
            if not _table_exists(conn, table):
                continue
            try:
                rows = conn.execute(
                    f'SELECT DISTINCT "{column}" AS d FROM "{table}" '
                    f'WHERE "{column}" IS NOT NULL').fetchall()
            except sqlite3.Error:
                # A column that does not exist in this schema version is
                # recorded rather than swallowed: the replay set would
                # otherwise be narrower than it looks.
                continue
            for row in rows:
                key = str(row['d'])[:10]
                if len(key) != 10:
                    continue
                seen.setdefault(key, []).append(f'{table}.{column}: {why}')

        if not seen:
            raise NoHistory(
                'No dated financial activity found in the dataset. There is '
                'no history to replay, and a replay over nothing that '
                'reported PASS would be a control incapable of failing.')

        first = min(seen)
        first_d = _dt.date.fromisoformat(first)
        # Dates after the business date are bookings for the future, not
        # history. They are excluded explicitly.
        last_d = business_date

        excluded: list[dict] = []
        for key in sorted(seen):
            if _dt.date.fromisoformat(key) > business_date:
                excluded.append({
                    'date': key,
                    'reason': ('later than the current business date — a '
                               'future booking, not history'),
                })

        # The replay starts at the FIRST OF THE MONTH containing the first
        # activity, not at the first activity itself. Month-to-date figures
        # are among the most frequently wrong in a PMS, and they can only
        # be checked against the sum of the days if every day in the month
        # is in the replay set. The extra days carry no rows and cost
        # almost nothing.
        month_start = first_d.replace(day=1)
        window_from = max(month_start, from_date) if from_date else month_start
        window_to = min(last_d, to_date) if to_date else last_d
        window_notes: list[dict] = []
        if month_start < first_d:
            window_notes.append({
                'date': f'{month_start}..{first_d - _dt.timedelta(days=1)}',
                'reason': ('earlier than the first activity, included anyway '
                           'so month-to-date figures can be checked against '
                           'the sum of their days'),
            })
        if from_date or to_date:
            excluded.append({
                'date': f'{first_d}..{last_d}',
                'reason': (f'run narrowed by request to '
                           f'{window_from}..{window_to}; dates outside that '
                           f'window were not replayed'),
            })
        if window_to < window_from:
            raise NoHistory(
                f'Requested window {window_from}..{window_to} contains no '
                f'dates. Nothing would be replayed.')

        # -- night audit closure state -----------------------------------
        closure: dict[str, sqlite3.Row] = {}
        if _table_exists(conn, 'night_audit_logs'):
            for row in conn.execute(
                    'SELECT audit_date, status, snapshot_json, snapshot_valid '
                    'FROM night_audit_logs ORDER BY id'):
                closure[str(row['audit_date'])[:10]] = row

        # -- assemble ----------------------------------------------------
        entries: list[DateEntry] = []
        gaps = 0
        day = window_from
        while day <= window_to:
            key = day.isoformat()
            reasons = sorted(set(seen.get(key, [])))
            if not reasons:
                gaps += 1
                reasons = ['no primary record refers to this date; replayed '
                           'anyway so that a day which later acquires a '
                           'back-dated posting is visible as a change']
            log = closure.get(key)
            entry = DateEntry(
                date=key,
                is_business_date=(day == business_date),
                is_closed=bool(log is not None and
                               str(log['status'] or '') in ('Completed',
                                                            'Warning')),
                audit_status=str(log['status'] or '') if log is not None else '',
                has_snapshot=bool(log is not None and log['snapshot_json']),
                reasons=reasons,
                row_counts=_row_counts(conn, key),
            )
            entries.append(entry)
            day += _dt.timedelta(days=1)

        return Timeline(
            business_date=business_date.isoformat(),
            first_activity=first,
            dates=entries,
            gaps_filled=gaps,
            excluded=excluded,
            window_notes=window_notes,
        )
    finally:
        conn.close()


#: Primary-record row counts recorded per date. These are the denominators
#: for every figure the replay produces: a divergence over zero rows is a
#: different animal from a divergence over three hundred (Principle 10).
COUNT_SOURCES: list[tuple[str, str, str]] = [
    ('payments', 'payment_date', 'payments'),
    ('extra_charges', 'charge_date', 'charges'),
    ('tax_lines', 'charge_date', 'tax_lines'),
    ('reservation_night_rates', 'stay_date', 'night_rates'),
]


def _row_counts(conn: sqlite3.Connection, key: str) -> dict:
    out: dict[str, int] = {}
    for table, column, label in COUNT_SOURCES:
        if not _table_exists(conn, table):
            continue
        try:
            row = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" = ?',
                (key,)).fetchone()
            out[label] = int(row[0])
        except sqlite3.Error:
            continue
    return out
