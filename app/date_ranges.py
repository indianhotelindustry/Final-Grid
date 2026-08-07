"""
Date-range utilities for KPI Command Center (and anything else that needs
preset → (from, to) logic).

Anchor: *all* callers pass the current business date (not ``date.today()``)
so night-audit rollover behaviour stays consistent across the app.

No Flask / SQLAlchemy imports — these are pure date helpers, cheap to unit
test in isolation.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Tuple, List

# Canonical preset identifiers used by the KPI Command Center UI.
# Keeping this in one place means the API validator and the template
# <select> can never silently drift apart.
PRESETS = frozenset({
    'today',
    'yesterday',
    'last_7_days',
    'last_30_days',
    'mtd',
    'last_month',
    'same_month_last_year',
    'custom',
})

TREND_MODES = frozenset({'6m', '12m', 'fy'})


@dataclass(frozen=True)
class ResolvedRange:
    date_from: Optional[date]
    date_to:   Optional[date]
    preset:    str           # may differ from requested if fallback kicked in
    error:     Optional[str] # human-readable reason when range is unusable


def resolve_range(preset: str,
                  business_date: date,
                  date_from: Optional[date] = None,
                  date_to:   Optional[date] = None) -> ResolvedRange:
    """Turn a preset + optional custom dates into a concrete (from, to).

    Contract:
      - Unknown / empty preset → silently falls back to 'today' (never crashes).
      - preset='custom' without both dates → ``error`` is set; caller should
        surface to UI as an empty-state / validation message rather than a 500.
      - date_from > date_to → same treatment (error, caller decides UX).
    """
    if preset == 'custom':
        if not date_from or not date_to:
            return ResolvedRange(None, None, 'custom',
                                 'Custom preset requires both date_from and date_to.')
        if date_from > date_to:
            return ResolvedRange(None, None, 'custom',
                                 'date_from must be on or before date_to.')
        return ResolvedRange(date_from, date_to, 'custom', None)

    if preset == 'today':
        return ResolvedRange(business_date, business_date, 'today', None)

    if preset == 'yesterday':
        y = business_date - timedelta(days=1)
        return ResolvedRange(y, y, 'yesterday', None)

    if preset == 'last_7_days':
        return ResolvedRange(business_date - timedelta(days=6), business_date,
                             'last_7_days', None)

    if preset == 'last_30_days':
        return ResolvedRange(business_date - timedelta(days=29), business_date,
                             'last_30_days', None)

    if preset == 'mtd':
        return ResolvedRange(business_date.replace(day=1), business_date, 'mtd', None)

    if preset == 'last_month':
        first_this = business_date.replace(day=1)
        last_prev  = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return ResolvedRange(first_prev, last_prev, 'last_month', None)

    if preset == 'same_month_last_year':
        # Phase 5 refinement: this preset is a *comparison mode* — the current
        # window is THIS year's current month (MTD-capped so we don't include
        # future days), and `comparison_range` produces the same date range
        # last year. Showing last year's month on its own is not operationally
        # useful; comparing this year to last year is.
        first_this = business_date.replace(day=1)
        return ResolvedRange(first_this, business_date,
                             'same_month_last_year', None)

    # Unknown preset — fail-soft to 'today' so the UI still renders.
    return ResolvedRange(business_date, business_date, 'today', None)


def prior_period(start: date, end: date) -> Tuple[date, date]:
    """Immediately-preceding window of equal length.

    Example: start=Apr 1, end=Apr 10  →  (Mar 22, Mar 31).
    Used for period-over-period compare toggles.
    """
    n = (end - start).days + 1
    new_end = start - timedelta(days=1)
    new_start = new_end - timedelta(days=n - 1)
    return new_start, new_end


@dataclass(frozen=True)
class ComparisonWindow:
    date_from:      Optional[date]
    date_to:        Optional[date]
    previous_from:  Optional[date]
    previous_to:    Optional[date]
    comparison_type: str
    error:          Optional[str] = None


def _first_of(d: date) -> date:
    return d.replace(day=1)


def _last_of(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def _month_shift(d: date, months: int) -> Tuple[date, date]:
    """Return (first, last) of the calendar month offset by ``months`` from d."""
    y = d.year + (d.month - 1 + months) // 12
    m = ((d.month - 1 + months) % 12) + 1
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def comparison_range(preset: str,
                     business_date: date,
                     date_from: Optional[date] = None,
                     date_to:   Optional[date] = None) -> ComparisonWindow:
    """Given a preset + resolved current window, return the comparison window
    the dashboard should use by default.

    Meeting-relevant rules (locked here, the Phase-5 API delegates entirely):
      * ``today``       → yesterday
      * ``yesterday``   → day before yesterday
      * ``last_7_days`` / ``last_30_days`` → immediately preceding window
      * ``mtd``         → same day-range of last month (1..N last month),
                          capped at last month's last day so Mar 31 → Feb 28
      * ``last_month``  → month before last (calendar month)
      * ``same_month_last_year`` → same month two years ago
      * ``custom``      → prior period of equal length

    Unknown preset → prior period of equal length. Never raises.
    """
    # Make sure we have a concrete current window.
    if not date_from or not date_to:
        return ComparisonWindow(None, None, None, None, 'none',
                                error='Current range not resolved.')

    if preset == 'today':
        y = business_date - timedelta(days=1)
        return ComparisonWindow(date_from, date_to, y, y, 'today_vs_yesterday')

    if preset == 'yesterday':
        y2 = business_date - timedelta(days=2)
        return ComparisonWindow(date_from, date_to, y2, y2,
                                'yesterday_vs_prior_day')

    if preset == 'mtd':
        # N = days elapsed in current month. Previous window = 1..min(N, last-day-prev) of previous month.
        n = business_date.day
        prev_first, prev_last_full = _month_shift(business_date, -1)
        prev_day_cap = min(n, prev_last_full.day)
        prev_last = date(prev_first.year, prev_first.month, prev_day_cap)
        return ComparisonWindow(date_from, date_to, prev_first, prev_last,
                                'mtd_vs_last_month')

    if preset == 'last_month':
        prev_first, prev_last = _month_shift(business_date, -2)
        return ComparisonWindow(date_from, date_to, prev_first, prev_last,
                                'last_month_vs_month_before')

    if preset == 'same_month_last_year':
        # Current is THIS year's MTD (1..business_date.day). Previous is
        # the same day-range last year, with a leap-year guard so Feb 29
        # gracefully maps to Feb 28 of the prior year.
        prev_y = business_date.year - 1
        try:
            prev_first = date(prev_y, date_from.month, 1)
        except ValueError:
            return ComparisonWindow(date_from, date_to, None, None,
                                    'same_month_last_year',
                                    error='Invalid previous-year date.')
        last_day_prev_year = monthrange(prev_y, date_from.month)[1]
        prev_to_day = min(date_to.day, last_day_prev_year)
        prev_last  = date(prev_y, date_from.month, prev_to_day)
        return ComparisonWindow(date_from, date_to, prev_first, prev_last,
                                'mtd_vs_same_month_last_year')

    # last_7_days / last_30_days / custom / unknown → prior period of equal length.
    pstart, pend = prior_period(date_from, date_to)
    label = ('prior_period_7d'  if preset == 'last_7_days'  else
            'prior_period_30d' if preset == 'last_30_days' else
            'prior_period')
    return ComparisonWindow(date_from, date_to, pstart, pend, label)


def month_window(mode: str, business_date: date) -> List[Tuple[int, int]]:
    """List of (year, month) tuples for the Monthly-Trend widget.

    mode:
      '6m'  → last 6 months ending with business_date's month, chronological.
      '12m' → last 12 months (same ordering).
      'fy'  → April → business_date.month of the Indian financial year that
              contains business_date. (Hotel books use FY Apr–Mar.)
    Unknown mode → falls back to '6m'.
    """
    if mode == 'fy':
        if business_date.month >= 4:
            fy_start = date(business_date.year, 4, 1)
        else:
            fy_start = date(business_date.year - 1, 4, 1)
        out: List[Tuple[int, int]] = []
        y, m = fy_start.year, fy_start.month
        while (y, m) <= (business_date.year, business_date.month):
            out.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return out

    count = 12 if mode == '12m' else 6
    out = []
    y, m = business_date.year, business_date.month
    for _ in range(count):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))
