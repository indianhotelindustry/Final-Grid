"""
Class B — Temporal invariants.

Time must behave. These are the invariants that catch a number which was
right becoming wrong: a posting back-dated into a period that has already
been reported, a frozen snapshot that no longer matches its hash, a
business date that has moved sideways, a night audit sequence with a hole
in it.

They are the ones that matter most before a migration, because a
migration is precisely an event that can change what the system says
about the past without anybody asking it to.
"""
from __future__ import annotations

from decimal import Decimal

from verification.invariants.helpers import (
    dec, differs, money, row_violation, summarise, verdict,
)
from verification.invariants.model import (
    Blocking, Category, Commissioning, Confidence, Mode, Severity, Status,
)
from verification.invariants.registry import invariant

WHOLE_DB = (Mode.ENTIRE_DATABASE, Mode.RELEASE_VERIFICATION,
            Mode.REGRESSION_DATASET, Mode.CONTINUOUS_MONITORING)
DATED = (Mode.BUSINESS_DATE, Mode.NIGHT_AUDIT, Mode.HISTORICAL_REPLAY)


# ---------------------------------------------------------------------------
# INV-B01 — closed periods are append-only
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-B01',
    title='No financial row was created into a business date after that date closed',
    category=Category.TEMPORAL,
    business_purpose=(
        'Once a night audit completes, the day has been reported. Someone '
        'has read the figure, banked against it and possibly filed it. A '
        'row inserted into that day afterwards changes a number that has '
        'already been relied upon, and nothing on any screen says so.'),
    business_rule=(
        'For every date with a completed night audit, no payments or '
        'extra_charges row dated to that date has created_at later than the '
        'audit\'s completed_at.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('payments', 'extra_charges', 'night_audit_logs'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'For each closed date, compare the created_at of every row dated to '
        'it against the audit\'s completed_at. Rows with a null created_at '
        'are reported separately: they cannot be judged, and treating them '
        'as compliant would let the whole control be bypassed by not '
        'stamping a row.'),
    evidence_produced=(
        'Per closed date: audit completion time, offending row ids, their '
        'creation times and the money they carry.'),
    failure_message=(
        'A financial row was posted into a business date after that date '
        'was closed. The closed period is not append-only.'),
    likely_root_causes=(
        'A posting route that takes the business date without checking '
        'whether it is closed',
        'A night audit reopened, posted into, and not re-run',
        'Manual data correction against the live database'),
    suggested_investigation=(
        'Read night_audit_reopen_logs for the date',
        'Check whether the posting route validates against '
        'NightAuditLog.status before writing',
        'Re-run the D3 replay for the date and compare against the frozen '
        'snapshot'),
    applicable_releases='all',
    applicable_business_dates='every date with a completed night audit',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P2', 'P7', 'P12'),
    affected_reports=('night audit', 'reports.daily_reconciliation',
                      'billing.gst_report', 'reports.revenue'),
    negative_seed=(
        "INSERT INTO payments "
        "(reservation_id, folio_id, payment_mode_id, amount, payment_date, "
        " created_at, is_voided, is_correction, is_reversal, payment_purpose) "
        "SELECT p.reservation_id, p.folio_id, p.payment_mode_id, 321.00, "
        "  (SELECT audit_date FROM night_audit_logs "
        "    WHERE status IN ('Completed','Warning') ORDER BY audit_date LIMIT 1), "
        "  '2099-01-01 00:00:00', 0, 0, 0, 'settlement' "
        "FROM payments p ORDER BY p.id LIMIT 1",
    ),
    negative_seed_reason=(
        'A payment dated to a closed day but created in 2099 is unambiguously '
        'a posting into a reported period, with no other explanation.'),
)
def _b01(ctx):
    closed = ctx.sql(
        "SELECT audit_date, completed_at, run_at, status FROM night_audit_logs "
        "WHERE status IN ('Completed','Warning') ORDER BY audit_date")
    if ctx.date:
        closed = [r for r in closed if str(r['audit_date'])[:10] == ctx.date]

    violations = []
    population = 0
    undated = 0
    for audit in closed:
        day = str(audit['audit_date'])[:10]
        # completed_at is the moment the day was reported. Where it was
        # never stamped, run_at is the next best evidence; where neither
        # exists the date cannot be judged and is reported as such.
        boundary = audit['completed_at'] or audit['run_at']
        if not boundary:
            violations.append(row_violation(
                'business_date', day,
                expected='a completion timestamp on the night audit',
                observed='neither completed_at nor run_at is set',
                amount=0))
            continue
        for table, date_col in (('payments', 'payment_date'),
                                ('extra_charges', 'charge_date')):
            rows = ctx.sql(
                f'SELECT id, amount, created_at FROM "{table}" '
                f'WHERE "{date_col}" = ? ORDER BY id', (day,))
            population += len(rows)
            for row in rows:
                created = row['created_at']
                if not created:
                    undated += 1
                    violations.append(row_violation(
                        table[:-1], row['id'],
                        expected='a created_at stamp so the rule can be applied',
                        observed='created_at is NULL',
                        amount=dec(row['amount']), business_date=day))
                    continue
                if str(created) > str(boundary):
                    violations.append(row_violation(
                        table[:-1], row['id'],
                        expected=f'created on or before {boundary}',
                        observed=f'created {created}',
                        amount=dec(row['amount']), business_date=day,
                        audit_closed_at=str(boundary)))

    return (verdict(population, violations), population, violations,
            {'expected': 'no row created into a closed date after it closed',
             'observed': summarise('rows in closed periods', population,
                                   violations),
             'inputs': {'closed_dates': len(closed),
                        'rows_examined': population,
                        'rows_without_created_at': undated}})


# ---------------------------------------------------------------------------
# INV-B02 — snapshot integrity
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-B02',
    title='Every frozen night-audit snapshot matches its stored hash',
    category=Category.TEMPORAL,
    business_purpose=(
        'The snapshot is the hotel\'s own frozen statement about a day. Its '
        'hash exists so that a manual database edit, or a change in how the '
        'snapshot is serialised, cannot silently rewrite history. An '
        'unhashed snapshot is a statement nobody can vouch for.'),
    business_rule=(
        'For every night_audit_logs row carrying a snapshot_json: a '
        'snapshot_hash exists and equals SHA-256 of the snapshot text.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('night_audit_logs',),
    canonical_engine='app.services.verify_snapshot_integrity',
    validation_method=(
        'Call the application\'s own integrity helper rather than '
        're-implementing the hash. A second implementation would drift, and '
        'if the application\'s control is broken this is the run that '
        'should say so.'),
    evidence_produced=(
        'Per audited date: whether a snapshot exists, whether a hash exists, '
        'stored hash, recomputed hash, and the version that wrote it.'),
    failure_message=(
        'A frozen night-audit snapshot no longer matches its hash, or was '
        'never hashed. The record of that day cannot be vouched for.'),
    likely_root_causes=(
        'A manual UPDATE against night_audit_logs',
        'A change to how the snapshot dict is serialised, without re-hashing',
        'A close path that writes the snapshot but not the hash'),
    suggested_investigation=(
        'Compare snapshot_version against the current application version',
        'Read night_audit_reopen_logs for the date',
        'Diff the snapshot against a fresh D3 replay of the same date'),
    applicable_releases='v2.2 and later (snapshot_hash was added then)',
    applicable_business_dates='every date with a night audit snapshot',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P2', 'P7', 'P11', 'P12'),
    affected_reports=('night audit', 'reports.night_audit_history'),
    negative_seed=(
        "UPDATE night_audit_logs SET snapshot_json = snapshot_json || ' ' "
        "WHERE snapshot_json IS NOT NULL AND snapshot_hash IS NOT NULL",
    ),
    negative_seed_reason=(
        'Appending one byte to the snapshot without touching the hash is the '
        'exact tamper the control claims to detect.'),
)
def _b02(ctx):
    from app.models import NightAuditLog
    from app.services import verify_snapshot_integrity

    ctx.require_app('INV-B02')
    query = NightAuditLog.query
    logs = query.order_by(NightAuditLog.audit_date).all()
    if ctx.date:
        logs = [log for log in logs if log.audit_date.isoformat() == ctx.date]

    violations = []
    examined = 0
    for log in logs:
        integrity = verify_snapshot_integrity(log)
        if not integrity.get('has_snapshot'):
            continue
        examined += 1
        day = log.audit_date.isoformat()
        if not integrity.get('has_hash'):
            violations.append(row_violation(
                'night_audit', day,
                expected='a stored snapshot_hash',
                observed='snapshot present, no hash stored', amount=0))
            continue
        if not integrity.get('matches'):
            violations.append(row_violation(
                'night_audit', day,
                expected=f'hash {integrity.get("stored_hash")}',
                observed=f'hash {integrity.get("current_hash")}', amount=0,
                stored_version=integrity.get('stored_version'),
                app_version=integrity.get('app_version')))

    return (verdict(examined, violations), examined, violations,
            {'expected': 'every snapshot is hashed and the hash matches',
             'observed': summarise('snapshots', examined, violations),
             'inputs': {'audit_logs': len(logs), 'with_snapshot': examined}})


# ---------------------------------------------------------------------------
# INV-B03 — a closed day still computes what it reported
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-B03',
    title='Recomputing a closed day reproduces the figures it reported',
    category=Category.TEMPORAL,
    business_purpose=(
        'This is the whole point of closing a day. If recomputing 27 May '
        'today gives a different answer from the one reported on the night '
        'of 27 May, then the accounts and the system disagree about a '
        'period that is supposed to be settled, and every downstream '
        'consumer of that figure is now wrong.'),
    business_rule=(
        'For every closed date, the read-only NightAuditService recomputation '
        'equals the frozen snapshot on collected cash, accrual revenue, '
        'occupancy and outstanding balance.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('night_audit_logs', 'payments', 'extra_charges',
                  'reservations'),
    canonical_engine='app.night_audit_service.NightAuditService',
    validation_method=(
        'Recompute the day with the clock frozen to it and compare against '
        'the stored snapshot, field by declared field. Only fields present '
        'on both sides are compared; a field the snapshot never carried is '
        'reported as uncomparable rather than assumed equal.'),
    evidence_produced=(
        'Per closed date and per field: frozen value, recomputed value, '
        'variance.'),
    failure_message=(
        'A closed day no longer computes the figures it reported. History '
        'has changed.'),
    likely_root_causes=(
        'A present-tense field — Reservation.status, Room.status, a credit '
        'balance — used inside a date-scoped report',
        'Data posted into the period after it closed (see INV-B01)',
        'A change to a canonical engine that was never replayed against '
        'history'),
    suggested_investigation=(
        'Run the D3 replay for the date; it attributes the movement to a '
        'dotted path',
        'Check INV-B01 for the same date first — a back-dated posting '
        'explains this without any code being at fault',
        'Look for query filters that use the reservation status rather than '
        'the stay span'),
    applicable_releases='all',
    applicable_business_dates='every closed date with a snapshot',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P2', 'P4', 'P7', 'P8', 'P12'),
    affected_reports=('night audit', 'reports.revenue',
                      'reports.daily_reconciliation'),
    negative_seed=(
        "UPDATE night_audit_logs "
        "SET snapshot_json = REPLACE(snapshot_json, "
        "    '\"total_collected\":', '\"total_collected\": 1.0, \"_seeded\":') "
        "WHERE snapshot_json LIKE '%total_collected%'",
    ),
    negative_seed_reason=(
        'Rewriting the frozen collected figure to 1.00 makes the snapshot '
        'and the recomputation disagree, which is the state the rule '
        'forbids. It also demonstrates that this invariant and INV-B02 are '
        'independent: the hash check fires too, and each names a different '
        'thing that is wrong.'),
)
def _b03(ctx):
    import datetime as _dt
    import json

    from app.models import NightAuditLog
    from app.night_audit_service import NightAuditService

    ctx.require_app('INV-B03')
    logs = NightAuditLog.query.order_by(NightAuditLog.audit_date).all()
    if ctx.date:
        logs = [log for log in logs if log.audit_date.isoformat() == ctx.date]

    #: (label, snapshot path, recomputation accessor)
    FIELDS = (
        ('collected cash', ('payments', 'total_collected'),
         lambda s: s.payment_summary().get('total_collected')),
        ('OTA settled', ('payments', 'total_ota_settled'),
         lambda s: s.payment_summary().get('total_ota_settled')),
        ('payment count', ('payments', 'payment_count'),
         lambda s: s.payment_summary().get('payment_count')),
        ('accrual revenue', ('revenue', 'accrual_net'),
         lambda s: s.revenue_summary().get('accrual_net')),
        ('room revenue', ('revenue', 'room_revenue'),
         lambda s: s.revenue_summary().get('room_revenue')),
        ('tax', ('revenue', 'tax_amount'),
         lambda s: s.revenue_summary().get('tax_amount')),
        ('occupancy', ('occupancy', 'occupied'),
         lambda s: s.occupancy_position().get('occupied')),
        ('outstanding', ('folio', 'total_outstanding'),
         lambda s: s.folio_control().get('total_outstanding')),
    )

    violations = []
    comparisons = 0
    uncomparable = 0
    for log in logs:
        if not log.snapshot_json:
            continue
        try:
            snapshot = json.loads(log.snapshot_json)
        except Exception:                                # noqa: BLE001
            violations.append(row_violation(
                'night_audit', log.audit_date.isoformat(),
                expected='readable snapshot_json',
                observed='snapshot_json is not valid JSON', amount=0))
            continue
        service = NightAuditService(log.audit_date)
        day = log.audit_date.isoformat()
        for label, path, accessor in FIELDS:
            section = snapshot.get(path[0]) or {}
            frozen = section.get(path[1])
            if frozen is None:
                uncomparable += 1
                continue
            now = accessor(service)
            if now is None:
                uncomparable += 1
                continue
            comparisons += 1
            frozen_d, now_d = dec(frozen), dec(now)
            if differs(frozen_d, now_d):
                violations.append(row_violation(
                    'night_audit', f'{day} / {label}',
                    expected=f'{money(frozen_d)} (frozen at close)',
                    observed=f'{money(now_d)} (recomputed today)',
                    amount=abs(now_d - frozen_d),
                    variance=money(now_d - frozen_d), business_date=day))

    return (verdict(comparisons, violations), comparisons, violations,
            {'expected': 'a closed day recomputes to what it reported',
             'observed': summarise('closed-day figures', comparisons,
                                   violations),
             'confidence': (Confidence.PARTIAL if uncomparable
                            else Confidence.PROVEN) if comparisons else
                           Confidence.NONE,
             'inputs': {'closed_dates': len(logs),
                        'fields_compared': comparisons,
                        'fields_not_in_snapshot': uncomparable}})


# ---------------------------------------------------------------------------
# INV-B04 — one business date
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-B04',
    title='Exactly one business date exists and no activity is dated beyond it',
    category=Category.TEMPORAL,
    business_purpose=(
        'The business date is the single temporal basis the whole system '
        'agrees on: reports, night audit, shift close and every "today" '
        'tile. Two of them, or financial activity dated past it, means '
        'different parts of the system are trading on different days.'),
    business_rule=(
        'The business_date table holds exactly one row, and no payment or '
        'charge is dated later than it.'),
    severity=Severity.CRITICAL,
    blocking=Blocking.RELEASE,
    data_sources=('business_date', 'payments', 'extra_charges'),
    canonical_engine='app.services.get_business_date',
    validation_method=(
        'Compare the row count and the canonical engine\'s answer against '
        'the table, then look for dated financial rows beyond it. Future '
        'RESERVATIONS are legitimate and are not counted; future money is '
        'not.'),
    evidence_produced=(
        'Row count, the canonical business date, the table\'s business date, '
        'and any financial row dated beyond it.'),
    failure_message=(
        'The system does not have a single unambiguous business date, or '
        'money is dated beyond it.'),
    likely_root_causes=(
        'A second business_date row inserted by a migration or a reset',
        'A night audit that advanced the date without committing',
        'A posting route that uses the wall clock rather than the business '
        'date'),
    suggested_investigation=(
        'SELECT * FROM business_date — there should be exactly one row',
        'Compare the offending rows\' created_at against the business date',
        'Check whether the posting path calls get_business_date()'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P8', 'P11'),
    affected_reports=('every date-scoped report', 'night audit',
                      'main.dashboard'),
    negative_seed=(
        "INSERT INTO business_date (\"current_date\", is_locked, updated_at) "
        "SELECT DATE(\"current_date\", '+1 day'), 0, updated_at "
        "FROM business_date ORDER BY id LIMIT 1",
    ),
    negative_seed_reason=(
        'A second business_date row is the ambiguity the rule forbids, and '
        'it is a state a careless migration can genuinely produce.'),
)
def _b04(ctx):
    from app.services import get_business_date

    ctx.require_app('INV-B04')
    rows = ctx.sql('SELECT id, "current_date", is_locked FROM business_date '
                   'ORDER BY id')
    violations = []
    if len(rows) != 1:
        violations.append(row_violation(
            'business_date', 'table',
            expected='exactly 1 row', observed=f'{len(rows)} row(s)',
            amount=0,
            dates=[str(r['current_date'])[:10] for r in rows]))

    table_date = str(rows[0]['current_date'])[:10] if rows else ''
    engine_date = get_business_date().isoformat()
    if rows and table_date != engine_date:
        violations.append(row_violation(
            'business_date', 'canonical engine',
            expected=f'get_business_date() = {table_date}',
            observed=engine_date, amount=0))

    if engine_date:
        for table, date_col in (('payments', 'payment_date'),
                                ('extra_charges', 'charge_date')):
            future = ctx.sql(
                f'SELECT id, amount, "{date_col}" AS d FROM "{table}" '
                f'WHERE "{date_col}" > ? ORDER BY id', (engine_date,))
            for row in future:
                violations.append(row_violation(
                    table[:-1], row['id'],
                    expected=f'dated on or before {engine_date}',
                    observed=f'dated {row["d"]}', amount=dec(row['amount'])))

    population = max(len(rows), 1)
    return (verdict(population, violations), population, violations,
            {'expected': 'one business date, no money dated beyond it',
             'observed': (f'{len(rows)} business_date row(s); canonical date '
                          f'{engine_date}'),
             'inputs': {'business_date_rows': len(rows),
                        'canonical_business_date': engine_date,
                        'table_business_date': table_date}})


# ---------------------------------------------------------------------------
# INV-B05 — the night audit sequence has no holes
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-B05',
    title='Night audits form an unbroken sequence up to the business date',
    category=Category.TEMPORAL,
    business_purpose=(
        'Each night audit closes one day. A missing audit is a day nobody '
        'closed: its revenue was never frozen, its cash was never '
        'reconciled, and the figures for it can still move. A gap in the '
        'sequence is a gap in the accounts.'),
    business_rule=(
        'Audit dates are unique, none is later than the business date, and '
        'there is no un-audited date between the first audit and the day '
        'before the business date.'),
    severity=Severity.HIGH,
    blocking=Blocking.CERTIFICATION,
    data_sources=('night_audit_logs', 'business_date'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Walk the calendar from the first audit to the day before the '
        'business date and require an audit for each. The current business '
        'date is excluded: it has not finished, so its audit is not yet '
        'due.'),
    evidence_produced=(
        'First and last audit dates, the business date, the list of missing '
        'dates and any duplicates.'),
    failure_message=(
        'The night audit sequence has a hole. At least one trading day was '
        'never closed.'),
    likely_root_causes=(
        'The audit was skipped on a quiet night and never back-run',
        'A crash mid-audit leaving the log in Pending and never retried',
        'The business date advanced without the audit completing'),
    suggested_investigation=(
        'Check for Pending rows in night_audit_logs on the missing dates',
        'Look for activity on the missing dates — a day with payments and '
        'no audit is materially different from an empty one'),
    applicable_releases='all',
    applicable_business_dates='from the first night audit onwards',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB,
    principles=('P7', 'P8', 'P10'),
    affected_reports=('night audit', 'reports.night_audit_history',
                      'reports.revenue'),
    negative_seed=(
        "UPDATE night_audit_logs SET audit_date = DATE(audit_date, '-5 day') "
        "WHERE id = (SELECT MIN(id) FROM night_audit_logs)",
    ),
    negative_seed_reason=(
        'Moving the earliest audit five days earlier opens a five-day hole '
        'between it and the business date — days that are now un-audited.'),
)
def _b05(ctx):
    import datetime as _dt

    rows = ctx.sql('SELECT audit_date, status FROM night_audit_logs '
                   'ORDER BY audit_date, id')
    business_date = ctx.business_date_value()
    violations = []

    if not rows:
        return (Status.VACUOUS, 0, [],
                {'expected': 'an unbroken night audit sequence',
                 'observed': 'no night audits exist; there is no sequence to '
                             'check, which is not the same as a sequence '
                             'with no holes',
                 'inputs': {'audit_rows': 0,
                            'business_date': business_date}})

    seen: dict[str, int] = {}
    for row in rows:
        day = str(row['audit_date'])[:10]
        seen[day] = seen.get(day, 0) + 1
    for day, count in sorted(seen.items()):
        if count > 1:
            violations.append(row_violation(
                'business_date', day,
                expected='one night audit', observed=f'{count} audits',
                amount=0))
        if business_date and day > business_date:
            violations.append(row_violation(
                'business_date', day,
                expected=f'no audit later than {business_date}',
                observed=f'an audit dated {day}', amount=0))

    first = min(seen)
    last_due = business_date or max(seen)
    cursor = _dt.date.fromisoformat(first)
    end = _dt.date.fromisoformat(last_due)
    population = 0
    while cursor < end:
        population += 1
        key = cursor.isoformat()
        if key not in seen:
            activity = ctx.count(
                'SELECT COUNT(*) FROM payments WHERE payment_date = ?', (key,))
            violations.append(row_violation(
                'business_date', key,
                expected='a night audit closing this day',
                observed=('none — and the day carries '
                          f'{activity} payment row(s)'),
                amount=0, payment_rows=activity))
        cursor += _dt.timedelta(days=1)

    return (verdict(max(population, len(seen)), violations),
            max(population, len(seen)), violations,
            {'expected': 'an audit for every day from the first to yesterday',
             'observed': (f'{len(seen)} audited date(s) between {first} and '
                          f'{last_due}; {len(violations)} problem(s)'),
             'inputs': {'first_audit': first, 'business_date': business_date,
                        'days_in_span': population}})


# ---------------------------------------------------------------------------
# INV-B06 — one temporal basis
# ---------------------------------------------------------------------------

@invariant(
    invariant_id='INV-B06',
    title='A payment is never dated outside the stay it belongs to',
    category=Category.TEMPORAL,
    business_purpose=(
        'A payment carries two times: the business date it is booked to and '
        'the wall-clock moment it was created. When the two disagree wildly, '
        'or when a payment is booked to a day far outside the stay it '
        'settles, the day\'s cash figure stops describing the day\'s '
        'trading, and the shift it is reconciled against is the wrong one.'),
    business_rule=(
        'For every payment: payment_date lies between the reservation\'s '
        'arrival date and 30 days after its departure date.'),
    severity=Severity.MEDIUM,
    blocking=Blocking.OPERATIONAL,
    data_sources=('payments', 'reservations'),
    canonical_engine='none — read directly from the primary record',
    validation_method=(
        'Join every payment to its reservation and bound the payment date by '
        'the stay window. The 30-day tail is declared, not discovered: '
        'post-checkout credit recovery is a legitimate business flow and a '
        'tighter bound would report it as a fault.'),
    evidence_produced=(
        'Per payment: reservation stay window, payment date, days outside '
        'the window, amount.'),
    failure_message=(
        'A payment is booked to a business date outside the stay it settles.'),
    likely_root_causes=(
        'A posting route defaulting the date to the wall clock rather than '
        'the business date',
        'A back-dated correction entered by hand',
        'A long-running credit recovery beyond the declared tail'),
    suggested_investigation=(
        'Compare payment_date against created_at for the offending rows',
        'Check payment_purpose — credit_recovery legitimately lags the stay',
        'Confirm the 30-day tail is still the right business assumption'),
    applicable_releases='all',
    applicable_business_dates='all',
    commissioning_status=Commissioning.COMMISSIONED,
    modes=WHOLE_DB + DATED,
    principles=('P8', 'P10'),
    affected_reports=('reports.flash', 'reports.payment_collection',
                      'shift close', 'night audit'),
    negative_seed=(
        "UPDATE payments SET payment_date = DATE(payment_date, '-400 day') "
        "WHERE id = (SELECT MIN(id) FROM payments)",
    ),
    negative_seed_reason=(
        'A payment booked 400 days before its own stay cannot belong to the '
        'day it is dated to, and it moves that day\'s cash figure.'),
)
def _b06(ctx):
    import datetime as _dt

    TAIL_DAYS = 30
    date_clause, params = ((' AND p.payment_date = ?', (ctx.date,))
                           if ctx.date else ('', ()))
    rows = ctx.sql(
        f'SELECT p.id, p.amount, p.payment_date, p.payment_purpose, '
        f'       r.id AS res_id, r.arrival_date, r.departure_date '
        f'FROM payments p JOIN reservations r ON r.id = p.reservation_id '
        f'WHERE p.payment_date IS NOT NULL{date_clause} ORDER BY p.id', params)

    violations = []
    for row in rows:
        try:
            paid_on = _dt.date.fromisoformat(str(row['payment_date'])[:10])
            arrival = _dt.date.fromisoformat(str(row['arrival_date'])[:10])
            departure = _dt.date.fromisoformat(str(row['departure_date'])[:10])
        except (TypeError, ValueError):
            continue
        latest = departure + _dt.timedelta(days=TAIL_DAYS)
        if arrival <= paid_on <= latest:
            continue
        drift = ((arrival - paid_on).days if paid_on < arrival
                 else (paid_on - latest).days)
        violations.append(row_violation(
            'payment', row['id'],
            expected=f'dated between {arrival} and {latest}',
            observed=f'dated {paid_on}', amount=dec(row['amount']),
            variance=f'{drift} day(s) outside the window',
            reservation_id=row['res_id'],
            payment_purpose=str(row['payment_purpose'] or '')))

    return (verdict(len(rows), violations), len(rows), violations,
            {'expected': f'payment_date within the stay + {TAIL_DAYS} days',
             'observed': summarise('payments', len(rows), violations),
             'inputs': {'payments_examined': len(rows),
                        'declared_tail_days': TAIL_DAYS}})
