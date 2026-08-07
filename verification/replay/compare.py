"""
Comparison of a replay against a stored one — the release gate.

The question this answers is narrow and important: *since the stored
replay was taken, has anything about a day that was already closed
changed?*

Severity follows the state of the day, not the kind of figure
------------------------------------------------------------
A hotel is a live business. Between two replays the current business date
will legitimately acquire payments, charges and check-outs, and new dates
will appear as time passes. Treating that as a regression would produce a
gate that fails every day and is therefore switched off within a week.

So:

* **Closed dates** — a night audit has been run and the day reported.
  Any movement at all is BLOCK. Nothing about a closed day is allowed to
  change; if it did, either someone posted into a closed period or the
  code changed what the period means.
* **Past dates that were never closed** — WARN. Back-dating into an open
  day is a legitimate operation, but it should be seen.
* **The current business date** — INFO. The hotel is trading; movement
  is the expected state.
* **A date appearing that is EARLIER than the stored history** — BLOCK
  regardless, because that is a posting back-dated into a period the
  stored replay says did not exist.

Two classes never take the state of the day into account:

* the RECORDED account — the frozen close and its hash. Rewriting a
  night audit log is a BLOCK on any date, including today's;
* the framework's own controls — order dependence, ledger instability
  and as-at drift on a closed day.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from verification.config import SEVERITY_RANK, Severity


class Kind:
    DATE_ADDED = 'DATE_ADDED'
    DATE_REMOVED = 'DATE_REMOVED'
    BACKDATED_DAY = 'BACKDATED_DAY'
    CLOSURE_CHANGED = 'CLOSURE_CHANGED'
    LEDGER_CHANGED = 'LEDGER_CHANGED'
    LEDGER_FIGURE_ADDED = 'LEDGER_FIGURE_ADDED'
    LEDGER_FIGURE_REMOVED = 'LEDGER_FIGURE_REMOVED'
    ENGINE_CHANGED = 'ENGINE_CHANGED'
    ENGINE_FIGURE_ADDED = 'ENGINE_FIGURE_ADDED'
    ENGINE_FIGURE_REMOVED = 'ENGINE_FIGURE_REMOVED'
    RECORDED_CHANGED = 'RECORDED_CHANGED'
    SNAPSHOT_INTEGRITY_CHANGED = 'SNAPSHOT_INTEGRITY_CHANGED'
    RECONCILIATION_CHANGED = 'RECONCILIATION_CHANGED'
    ASAT_DRIFT_CHANGED = 'ASAT_DRIFT_CHANGED'
    ORDER_MISMATCH_CHANGED = 'ORDER_MISMATCH_CHANGED'
    ENGINE_ERROR_CHANGED = 'ENGINE_ERROR_CHANGED'


#: Kinds whose severity is BLOCK on every date, whatever its state.
ALWAYS_BLOCK = {
    Kind.RECORDED_CHANGED,
    Kind.SNAPSHOT_INTEGRITY_CHANGED,
    Kind.BACKDATED_DAY,
    Kind.CLOSURE_CHANGED,
    Kind.ORDER_MISMATCH_CHANGED,
    Kind.ENGINE_ERROR_CHANGED,
    Kind.DATE_REMOVED,
}

#: Kinds that are informational on any date: a new day is time passing.
ALWAYS_INFO = {Kind.DATE_ADDED}


@dataclass
class Difference:
    date: str
    day_state: str            # CLOSED / OPEN / BUSINESS_DATE
    kind: str
    severity: str
    key: str = ''
    stored: str = ''
    current: str = ''
    delta: str = ''


@dataclass
class ReplayComparison:
    tag: str
    stored_captured_at: str = ''
    stored_app_version: str = ''
    current_app_version: str = ''
    stored_business_date: str = ''
    current_business_date: str = ''
    dates_compared: int = 0
    dates_clean: int = 0
    differences: list = field(default_factory=list)

    @property
    def blocking(self) -> list:
        return [d for d in self.differences if d.severity == Severity.BLOCK]

    @property
    def by_kind(self) -> dict:
        out: dict = {}
        for d in self.differences:
            out[d.kind] = out.get(d.kind, 0) + 1
        return out

    @property
    def verdict(self) -> str:
        if self.blocking:
            return 'FAIL'
        if self.differences:
            return 'WARN'
        return 'PASS'


def _day_state(record) -> str:
    if isinstance(record, dict):
        closed = record.get('is_closed')
        business = record.get('is_business_date')
    else:
        closed = record.is_closed
        business = record.is_business_date
    if business:
        return 'BUSINESS_DATE'
    return 'CLOSED' if closed else 'OPEN'


def _severity_for(kind: str, state: str) -> str:
    if kind in ALWAYS_BLOCK:
        return Severity.BLOCK
    if kind in ALWAYS_INFO:
        return Severity.INFO
    if state == 'CLOSED':
        return Severity.BLOCK
    if state == 'OPEN':
        return Severity.WARN
    return Severity.INFO


def _delta(stored: str, current: str) -> str:
    try:
        return f'{float(current) - float(stored):+.6f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return ''


def _dict_diff(result, date: str, state: str, kind_changed: str,
               kind_added: str, kind_removed: str,
               stored: dict, current: dict) -> None:
    for key in sorted(set(stored) | set(current)):
        s, c = stored.get(key), current.get(key)
        if s == c:
            continue
        if s is None:
            kind = kind_added
        elif c is None:
            kind = kind_removed
        else:
            kind = kind_changed
        result.differences.append(Difference(
            date=date, day_state=state, kind=kind,
            severity=_severity_for(kind, state), key=key,
            stored='' if s is None else str(s),
            current='' if c is None else str(c),
            delta=_delta(s, c) if kind == kind_changed else ''))


def compare(run, stored: dict, index: dict, tag: str) -> ReplayComparison:
    """Diff a replay run against a stored replay set."""
    result = ReplayComparison(
        tag=tag,
        stored_captured_at=index.get('started_at', ''),
        stored_app_version=index.get('app_version', ''),
        current_app_version=run.app_version,
        stored_business_date=index.get('business_date', ''),
        current_business_date=run.business_date,
    )

    current = {d.date: d for d in run.dates}
    result.dates_compared = len(current)
    stored_first = min(stored) if stored else ''

    for date in sorted(set(current) | set(stored)):
        cur = current.get(date)
        old = stored.get(date)

        if old is None:
            state = _day_state(cur)
            # A date the stored set does not have is normally just time
            # passing. A date EARLIER than the stored history is not: it
            # is a posting back-dated into a period that did not exist.
            kind = (Kind.BACKDATED_DAY
                    if stored_first and date < stored_first
                    else Kind.DATE_ADDED)
            result.differences.append(Difference(
                date=date, day_state=state, kind=kind,
                severity=_severity_for(kind, state),
                current=f'{len(cur.ledger)} ledger figures'))
            continue
        if cur is None:
            result.differences.append(Difference(
                date=date, day_state=_day_state(old), kind=Kind.DATE_REMOVED,
                severity=Severity.BLOCK,
                stored=f'{len(old.get("ledger") or {})} ledger figures'))
            continue

        state = _day_state(cur)
        before = len(result.differences)

        if bool(old.get('is_closed')) != bool(cur.is_closed) or \
                str(old.get('audit_status') or '') != str(cur.audit_status or ''):
            result.differences.append(Difference(
                date=date, day_state=state, kind=Kind.CLOSURE_CHANGED,
                severity=Severity.BLOCK,
                stored=f'closed={old.get("is_closed")} '
                       f'status={old.get("audit_status")!r}',
                current=f'closed={cur.is_closed} '
                        f'status={cur.audit_status!r}'))

        _dict_diff(result, date, state, Kind.LEDGER_CHANGED,
                   Kind.LEDGER_FIGURE_ADDED, Kind.LEDGER_FIGURE_REMOVED,
                   old.get('ledger') or {}, cur.ledger)
        _dict_diff(result, date, state, Kind.ENGINE_CHANGED,
                   Kind.ENGINE_FIGURE_ADDED, Kind.ENGINE_FIGURE_REMOVED,
                   old.get('engine') or {}, cur.engine)
        _dict_diff(result, date, state, Kind.RECORDED_CHANGED,
                   Kind.RECORDED_CHANGED, Kind.RECORDED_CHANGED,
                   old.get('recorded') or {}, cur.recorded)

        old_integrity = old.get('snapshot_integrity') or {}
        for key in ('matches', 'has_snapshot', 'has_hash', 'stored_hash'):
            s, c = old_integrity.get(key), cur.snapshot_integrity.get(key)
            if s != c:
                result.differences.append(Difference(
                    date=date, day_state=state,
                    kind=Kind.SNAPSHOT_INTEGRITY_CHANGED,
                    severity=Severity.BLOCK, key=key,
                    stored='' if s is None else str(s),
                    current='' if c is None else str(c)))

        old_status = {r['rule_id']: r['status']
                      for r in (old.get('reconciliations') or [])}
        cur_status = {r.rule_id: r.status for r in cur.reconciliations}
        for rule_id in sorted(set(old_status) | set(cur_status)):
            if old_status.get(rule_id) != cur_status.get(rule_id):
                result.differences.append(Difference(
                    date=date, day_state=state,
                    kind=Kind.RECONCILIATION_CHANGED,
                    severity=_severity_for(Kind.RECONCILIATION_CHANGED, state),
                    key=rule_id,
                    stored=str(old_status.get(rule_id, '')),
                    current=str(cur_status.get(rule_id, ''))))

        old_drift = {d['path'] for d in (old.get('asat_drift') or [])}
        cur_drift = {d['path'] for d in cur.asat_drift}
        for path in sorted(old_drift ^ cur_drift):
            result.differences.append(Difference(
                date=date, day_state=state, kind=Kind.ASAT_DRIFT_CHANGED,
                severity=_severity_for(Kind.ASAT_DRIFT_CHANGED, state),
                key=path,
                stored='present' if path in old_drift else '',
                current='present' if path in cur_drift else ''))

        old_order = set(old.get('order_mismatch') or [])
        cur_order = set(cur.order_mismatch)
        for path in sorted(old_order ^ cur_order):
            result.differences.append(Difference(
                date=date, day_state=state, kind=Kind.ORDER_MISMATCH_CHANGED,
                severity=Severity.BLOCK, key=path,
                stored='present' if path in old_order else '',
                current='present' if path in cur_order else ''))

        old_errors = set((old.get('engine_errors') or {}))
        cur_errors = set(cur.engine_errors)
        for probe in sorted(old_errors ^ cur_errors):
            result.differences.append(Difference(
                date=date, day_state=state, kind=Kind.ENGINE_ERROR_CHANGED,
                severity=Severity.BLOCK, key=probe,
                stored='errored' if probe in old_errors else 'ok',
                current='errored' if probe in cur_errors else 'ok'))

        if len(result.differences) == before:
            result.dates_clean += 1

    result.differences.sort(
        key=lambda d: (SEVERITY_RANK.get(d.severity, 9), d.date, d.kind, d.key))
    return result
