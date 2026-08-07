"""
The RECORDED account — what the system froze at close time.

When the night audit completes for a business date the application writes
a ``NightAuditLog`` row with that day's totals and, since v2.2, a
``snapshot_json`` blob holding the whole report, a SHA-256 of that blob
and the application version that produced it. That is the hotel's own
statement about the day, made by the code as it existed on the night.

It is the only account in this framework that is *not* recomputed. That
is precisely its value: comparing it with today's ENGINE account answers
the question a golden master cannot, because a master is recaptured after
every intended change and history is not.

Snapshot integrity
------------------
The application already claims a tamper-detection control here —
``services.verify_snapshot_integrity`` re-hashes the stored blob and
compares. The replay calls that helper rather than reimplementing the
hash, for two reasons: a second implementation would drift, and if the
application's own control is broken this is the run that should say so.
The result is recorded as evidence on every replay, not only when it
fails, because a control that only speaks up when unhappy leaves you
unable to tell "verified" from "never ran" (Principle 11).
"""
from __future__ import annotations

import json

from verification.golden import normalize as norm


#: Columns of ``NightAuditLog`` recorded as the frozen close position.
#: Narrative and provenance columns (notes, reasons, user ids) are not
#: figures and are excluded; the ones that carry money or counts are all
#: here, so a release that stops populating one of them is visible.
STORED_COLUMNS = (
    'total_revenue',
    'net_revenue',
    'total_discount',
    'accrual_revenue',
    'occupancy_count',
    'pending_checkouts',
    'total_payments',
    'outstanding_amount',
    'reconciliation_difference',
    'blocker_count',
    'warning_count',
    'expected_cash',
    'actual_cash',
    'cash_variance',
    'override_used',
    'snapshot_valid',
)


def _log_for(day) -> object | None:
    from app.models import NightAuditLog
    return (NightAuditLog.query
            .filter_by(audit_date=day)
            .order_by(NightAuditLog.id.desc())
            .first())


def capture(day) -> tuple[dict, dict, list]:
    """Return ``(figures, integrity, notes)`` for the recorded close.

    ``figures`` is empty when the date was never closed. That is not an
    error — most dates in a young dataset have no audit log — but the
    caller must be able to tell "closed and matching" from "never
    closed", so the absence is reported in *notes* rather than by an
    empty dict alone.
    """
    from app.services import verify_snapshot_integrity

    log = _log_for(day)
    if log is None:
        return {}, {'has_log': False}, [
            'no night audit log for this date — the day was never closed, '
            'so there is no frozen statement to compare against']

    figures: dict[str, str] = {}
    notes: list[str] = []

    stored: dict = {}
    for column in STORED_COLUMNS:
        stored[column] = getattr(log, column, None)
    walked, trunc = norm.figures_from_context({'stored': stored})
    figures.update(walked)
    notes.extend(trunc)
    figures['stored.status'] = str(log.status or '')

    integrity = verify_snapshot_integrity(log)
    integrity['has_log'] = True

    snapshot_text = getattr(log, 'snapshot_json', None)
    if snapshot_text:
        try:
            payload = json.loads(snapshot_text)
        except Exception as exc:                        # noqa: BLE001
            notes.append(f'snapshot_json is not valid JSON: '
                         f'{type(exc).__name__}: {exc}')
        else:
            walked, trunc = norm.figures_from_context({'snapshot': payload})
            figures.update(walked)
            notes.extend(trunc)
    else:
        notes.append('audit log exists but carries no snapshot_json; only '
                     'the stored column totals can be compared')

    if not integrity.get('matches', True):
        notes.append(
            'SNAPSHOT INTEGRITY FAILURE — the stored hash does not match the '
            'stored snapshot. The frozen statement for this date has been '
            'altered since it was written, or the application changed how it '
            'serialises the snapshot without re-hashing.')
    if integrity.get('has_snapshot') and not integrity.get('has_hash'):
        notes.append(
            'snapshot present but no hash was stored, so tampering with this '
            'date\'s frozen statement would not be detectable by the '
            'application\'s own control')
    if not integrity.get('version_match', True):
        notes.append(
            f'snapshot was written by application v'
            f'{integrity.get("stored_version")} and is being read by v'
            f'{integrity.get("app_version")}')

    return dict(sorted(figures.items())), integrity, notes
