"""
Seeded-fault commissioning for the Historical Replay Framework.

Constitutional basis: Principle 9 — a control that cannot fail is not a
control — and Principle 11 — silence is never evidence.

A replay that has only ever reported "history reconciles" has not been
shown to detect anything. It might be comparing a number to itself, or
reconciling two views of the same rows that would move together under any
fault. That last risk is specific to this deliverable and is taken
seriously below: several of the seeds exist precisely to make the LEDGER
and the ENGINE disagree, rather than to make them both move.

Five classes of proof, because they fail independently:

A. **Data faults on a CLOSED day.** A posting back-dated into a closed
   period must be detected. What detects it varies by fault and is named
   per seed — that is the point of declaring ``must_*`` expectations
   rather than accepting any change at all.

B. **Reconciliation faults.** A fault engineered so that the primary
   record and the application genuinely disagree. Without these, every
   reconciliation rule could be tautological: both sides reading the same
   rows through the same filter, agreeing forever.

C. **Comparator faults.** A stored replay is mutated field by field and
   the comparison must report exactly the expected kind at exactly the
   expected severity — including the case that must NOT block, because a
   gate that blocks on the current business date moving is a gate nobody
   will keep.

D. **The as-at control.** The retroactivity comparison is proven live by
   removing its one declared exclusion and requiring the drift it was
   masking to be reported. If the two passes were not really running
   under different clocks, nothing would appear.

E. **Null controls.** Identical data must produce zero differences, and a
   stored replay compared against itself must be clean. A framework that
   flagged everything would pass every other test in this file.

Every seeded replay runs in a separate process. The clock patch and the
Flask application both hold module-level state, and a measurement that
inherited the previous one's state would be worthless.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field

from verification.config import PROJECT_ROOT, PVF_WORK_DIR, Severity
from verification.dbcopy import make_copy
from verification.replay import reconcile as rec


class SeedDidNotApply(RuntimeError):
    """A seed's SQL ran cleanly but changed no rows.

    Inherited from D2's commissioning, where exactly this produced a
    false alarm: an ``INSERT ... SELECT`` matched nothing, succeeded, and
    the suite reported "fault not detected" — a statement about the seed
    read as a statement about the framework. Rowcount is asserted so a
    seed that did not bite is reported as a broken seed.
    """


# ---------------------------------------------------------------------------
# A / B — data and reconciliation faults
# ---------------------------------------------------------------------------

@dataclass
class DataSeed:
    seed_id: str
    kind: str
    description: str
    sql: list
    #: Ledger paths that MUST move on the seeded date.
    must_move_ledger: list = field(default_factory=list)
    #: Engine paths that MUST move on the seeded date.
    must_move_engine: list = field(default_factory=list)
    #: Reconciliation rules that MUST become UNRECONCILED.
    must_break: list = field(default_factory=list)
    #: History-drift entries that MUST appear.
    must_history_drift: list = field(default_factory=list)
    #: The snapshot integrity control MUST report a failure.
    must_snapshot_fail: bool = False


DATA_SEEDS: list[DataSeed] = [
    DataSeed(
        seed_id='S-RP-BACKDATE',
        kind='DATA FAULT',
        description=('Post a 555.00 cash settlement INTO a closed business '
                     'day. The books for that day now differ from what was '
                     'reported at close; the replay must say so.'),
        sql=["INSERT INTO payments "
             "(reservation_id, folio_id, payment_mode_id, amount, "
             " payment_date, is_voided, is_correction, is_reversal, "
             " payment_purpose) "
             "SELECT p.reservation_id, p.folio_id, "
             "  (SELECT id FROM payment_modes "
             "    WHERE category='direct_payment' ORDER BY id LIMIT 1), "
             "  555.00, '{date}', 0, 0, 0, 'settlement' "
             "FROM payments p WHERE p.payment_date='{date}' "
             "ORDER BY p.id LIMIT 1"],
        must_move_ledger=['payments.direct.non_voided', 'payments.gross',
                          'payments.rows'],
        must_move_engine=['kpi.cash_revenue',
                          'nas.payment_summary.total_collected'],
        must_history_drift=[
            'nas.payment_summary.total_collected vs '
            'snapshot.payments.total_collected'],
    ),

    DataSeed(
        seed_id='S-RP-PAISA',
        kind='DATA FAULT',
        description=('Move a single closed-day payment by ONE PAISA. The '
                     'framework claims no tolerance band on history; this is '
                     'the test of that claim. A rounding-tolerant replay '
                     'would let a systematic sub-rupee drift through on '
                     'every day at once.'),
        sql=["UPDATE payments SET amount = amount + 0.01 "
             "WHERE id = (SELECT MIN(p.id) FROM payments p "
             "            JOIN payment_modes m ON m.id = p.payment_mode_id "
             "            WHERE p.payment_date='{date}' AND p.is_voided = 0 "
             "              AND m.category='direct_payment')"],
        must_move_ledger=['payments.direct.non_voided'],
        must_move_engine=['kpi.cash_revenue'],
        must_history_drift=[
            'nas.payment_summary.total_collected vs '
            'snapshot.payments.total_collected'],
    ),

    DataSeed(
        seed_id='S-RP-VOID',
        kind='DATA FAULT',
        description=('Void a payment that belongs to a closed day. Voiding '
                     'after the close removes money from a period that has '
                     'already been reported and reconciled.'),
        sql=["UPDATE payments SET is_voided = 1 "
             "WHERE id = (SELECT MIN(p.id) FROM payments p "
             "            JOIN payment_modes m ON m.id = p.payment_mode_id "
             "            WHERE p.payment_date='{date}' AND p.is_voided = 0 "
             "              AND m.category='direct_payment')"],
        must_move_ledger=['payments.direct.non_voided', 'payments.voided'],
        must_move_engine=['kpi.cash_revenue',
                          'nas.payment_summary.payment_count'],
        must_history_drift=[
            'nas.payment_summary.total_collected vs '
            'snapshot.payments.total_collected'],
    ),

    DataSeed(
        seed_id='S-RP-CHARGE',
        kind='DATA FAULT',
        description=('Post a 222.00 charge into the closed day. Accrual '
                     'revenue for a reported period must not be able to '
                     'change without the replay noticing.'),
        sql=["INSERT INTO extra_charges "
             "(reservation_id, folio_id, description, amount, charge_date, "
             " charge_type, charge_category, is_correction, is_reversal) "
             "SELECT r.id, NULL, 'SEEDED backdated charge', 222.00, "
             "  '{date}', 'food', 'Restaurant', 0, 0 "
             "FROM reservations r ORDER BY r.id LIMIT 1"],
        must_move_ledger=['charges.non_room_rent', 'charges.gross',
                          'charges.rows'],
        must_move_engine=['kpi.accrual_extras', 'kpi.total_revenue'],
    ),

    DataSeed(
        seed_id='S-RP-RATE',
        kind='DATA FAULT',
        description=('Raise the priced rate of one room night that belongs '
                     'to the closed day by 111.00. The nightly rate record '
                     'is the closest thing the schema has to an immutable '
                     'statement of what a room was sold for.'),
        sql=["UPDATE reservation_night_rates "
             "SET final_rate = final_rate + 111.00 "
             "WHERE id = (SELECT MIN(id) FROM reservation_night_rates "
             "            WHERE stay_date='{date}')"],
        must_move_ledger=['night_rates.final'],
    ),

    DataSeed(
        seed_id='S-RP-STORED',
        kind='DATA FAULT',
        description=('Rewrite the stored close total for the audited day. '
                     'The night audit log is the hotel\'s own statement '
                     'about the day; altering it must not be quiet.'),
        sql=["UPDATE night_audit_logs "
             "SET total_revenue = total_revenue + 999.00 "
             "WHERE audit_date = '{date}'"],
        must_history_drift=[
            'nas.payment_summary.total_collected vs stored.total_revenue'],
    ),

    DataSeed(
        seed_id='S-RP-SNAPSHOT',
        kind='DATA FAULT',
        description=('Tamper with the frozen snapshot without touching its '
                     'hash. The application claims a tamper-detection '
                     'control here; this proves the claim, and proves the '
                     'replay surfaces it.'),
        sql=["UPDATE night_audit_logs "
             "SET snapshot_json = snapshot_json || ' ' "
             "WHERE audit_date = '{date}' AND snapshot_json IS NOT NULL"],
        must_snapshot_fail=True,
    ),

    DataSeed(
        seed_id='S-RP-ORPHAN-MODE',
        kind='RECONCILIATION FAULT',
        description=(
            'Point one closed-day payment at a payment mode that does not '
            'exist. This is the seed that proves the reconciliations are not '
            'tautological: the night audit defaults a missing mode to DIRECT '
            'cash (night_audit_service.py:537), while kpi_helpers inner-joins '
            'PaymentMode and drops the row entirely. The two application '
            'views therefore disagree about the same rupees, and the ledger '
            '— which counts the row as neither direct nor OTA — is what '
            'reveals which of them moved.\n'
            '        The first attempt at this seed used an unknown mode '
            'CATEGORY and was rejected by ck_payment_mode_category. The '
            'schema forbidding that fault is a real control and is recorded '
            'as such; the orphan reaches the same disagreement by a route '
            'the schema does not close, because foreign keys are not '
            'enforced on this database.'),
        sql=["UPDATE payments SET payment_mode_id = 999999 "
             "WHERE id = (SELECT MIN(p.id) FROM payments p "
             "            JOIN payment_modes m ON m.id = p.payment_mode_id "
             "            WHERE p.payment_date='{date}' AND p.is_voided = 0 "
             "              AND m.category='direct_payment')"],
        must_move_ledger=['payments.uncategorised.non_voided',
                          'payments.direct.non_voided'],
        must_move_engine=['kpi.cash_revenue'],
        must_break=['RC11'],
    ),
]


# ---------------------------------------------------------------------------
# C — comparator faults
# ---------------------------------------------------------------------------

@dataclass
class ComparatorSeed:
    seed_id: str
    description: str
    mutate: object                 # mutate(record_dict) -> None
    expect_kind: str
    expect_severity: str = ''
    #: When set, the run must report NOTHING of ``expect_kind`` at BLOCK.
    expect_not_blocking: bool = False
    #: Which side of the comparison the fault is injected into. Most
    #: faults describe the stored set drifting away from the release;
    #: a date DISAPPEARING can only be expressed on the current side,
    #: because a date missing from the stored set is an addition, not a
    #: removal. Getting this backwards is how the first version of this
    #: seed reported DATE_ADDED and looked like a comparator defect.
    side: str = 'stored'


def _closed_date(stored: dict) -> str:
    for date in sorted(stored):
        if stored[date].get('is_closed'):
            return date
    raise RuntimeError('no closed date in the stored replay to mutate')


def _business_date(stored: dict) -> str:
    for date in sorted(stored):
        if stored[date].get('is_business_date'):
            return date
    raise RuntimeError('no business date in the stored replay to mutate')


def _comparator_seeds(stored: dict) -> list:
    from verification.replay.compare import Kind

    closed = _closed_date(stored)
    today = _business_date(stored)

    def move_ledger(s):
        figures = s[closed]['ledger']
        figures['payments.direct.non_voided'] = str(
            float(figures.get('payments.direct.non_voided', 0)) + 0.01)

    def move_engine(s):
        s[closed]['engine']['kpi.cash_revenue'] = str(
            float(s[closed]['engine'].get('kpi.cash_revenue', 0)) + 1)

    def move_recorded(s):
        s[closed]['recorded']['stored.total_revenue'] = '1.00'

    def break_integrity(s):
        s[closed]['snapshot_integrity']['matches'] = False

    def reopen(s):
        s[closed]['is_closed'] = False
        s[closed]['audit_status'] = 'Reopened'

    def drop_date(s):
        del s[closed]

    def backdate(s):
        earliest = min(s)
        s.pop(earliest)

    def break_reconciliation(s):
        for entry in s[closed]['reconciliations']:
            if entry['rule_id'] == 'RC01':
                entry['status'] = rec.Status.UNRECONCILED

    def add_order_mismatch(s):
        s[closed]['order_mismatch'] = ['kpi.cash_revenue']

    def move_today(s):
        s[today]['ledger']['payments.direct.non_voided'] = str(
            float(s[today]['ledger'].get('payments.direct.non_voided', 0)) + 5000)

    return [
        ComparatorSeed('S-RP-CMP-LEDGER',
                       f'The primary record for the closed day {closed} moved '
                       f'by one paisa.',
                       move_ledger, Kind.LEDGER_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-ENGINE',
                       f'The application now reports a different cash figure '
                       f'for the closed day {closed}.',
                       move_engine, Kind.ENGINE_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-RECORDED',
                       f'The frozen close for {closed} was rewritten.',
                       move_recorded, Kind.RECORDED_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-INTEGRITY',
                       f'The snapshot integrity verdict for {closed} changed.',
                       break_integrity, Kind.SNAPSHOT_INTEGRITY_CHANGED,
                       Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-CLOSURE',
                       f'{closed} was reopened after being closed.',
                       reopen, Kind.CLOSURE_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-DATE-GONE',
                       f'{closed} is present in the stored replay but the '
                       f'release no longer produces it — a day of trading '
                       f'that has disappeared.',
                       drop_date, Kind.DATE_REMOVED, Severity.BLOCK,
                       side='current'),
        ComparatorSeed('S-RP-CMP-BACKDATED',
                       'A date appears that is earlier than any the stored '
                       'replay knows about — a posting back-dated into a '
                       'period that did not exist.',
                       backdate, Kind.BACKDATED_DAY, Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-RECON',
                       f'A reconciliation that held on {closed} now fails.',
                       break_reconciliation, Kind.RECONCILIATION_CHANGED,
                       Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-ORDER',
                       f'A figure on {closed} became dependent on the order '
                       f'the dates were replayed in.',
                       add_order_mismatch, Kind.ORDER_MISMATCH_CHANGED,
                       Severity.BLOCK),
        ComparatorSeed('S-RP-CMP-TODAY',
                       f'The CURRENT business date {today} took 5,000 more in '
                       f'cash. The hotel is trading; this must be reported '
                       f'and must NOT block. A gate that fails every day is '
                       f'a gate that gets switched off.',
                       move_today, Kind.LEDGER_CHANGED,
                       expect_not_blocking=True),
    ]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    seed_id: str
    kind: str
    description: str
    detected: bool = False
    note: str = ''
    rows_changed: int = 0
    evidence: list = field(default_factory=list)


def _replay_in_subprocess(db_path: str, env_extra: dict | None = None) -> dict:
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, '-m', 'verification', '_replay_json', '--db', db_path],
        cwd=PROJECT_ROOT, capture_output=True, text=True, env=env)
    if '---REPLAY-JSON---' not in proc.stdout:
        raise RuntimeError(
            f'Replay subprocess produced no result.\n'
            f'stdout tail: {proc.stdout[-1500:]}\n'
            f'stderr tail: {proc.stderr[-1500:]}')
    return json.loads(proc.stdout.split('---REPLAY-JSON---', 1)[1].strip())


def _apply(db_path: str, statements: list, date: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        changed = 0
        for statement in statements:
            cur = conn.execute(statement.replace('{date}', date))
            changed += max(cur.rowcount, 0)
        conn.commit()
    finally:
        conn.close()
    if changed == 0:
        raise SeedDidNotApply(
            'seed SQL affected 0 rows — the fault was never injected, so '
            '"not detected" would be a statement about the seed, not about '
            'the framework')
    return changed


def _closed_date_of(digest: dict) -> str:
    for date in sorted(digest['dates']):
        if digest['dates'][date]['is_closed']:
            return date
    raise RuntimeError(
        'The dataset contains no closed business day. Replay commissioning '
        'seeds faults INTO a closed period, so without one the suite would '
        'be measuring nothing.')


def _moved(base: dict, other: dict, date: str, section: str) -> list:
    a = base['dates'].get(date, {}).get(section, {})
    b = other['dates'].get(date, {}).get(section, {})
    return sorted(path for path in set(a) | set(b) if a.get(path) != b.get(path))


def _check_data_seed(seed: DataSeed, base: dict, seeded: dict,
                     date: str) -> tuple[bool, str, list]:
    """Did the seeded fault produce every effect the seed declared?"""
    evidence: list[str] = []
    missing: list[str] = []

    ledger_moved = _moved(base, seeded, date, 'ledger')
    engine_moved = _moved(base, seeded, date, 'engine')
    evidence.append(f'ledger figures moved: {len(ledger_moved)}')
    evidence.append(f'engine figures moved: {len(engine_moved)}')

    for path in seed.must_move_ledger:
        if path not in ledger_moved:
            missing.append(f'ledger {path}')
    for path in seed.must_move_engine:
        if path not in engine_moved:
            missing.append(f'engine {path}')

    base_status = base['dates'].get(date, {}).get('reconciliations', {})
    seeded_status = seeded['dates'].get(date, {}).get('reconciliations', {})
    for rule_id in seed.must_break:
        if seeded_status.get(rule_id) != rec.Status.UNRECONCILED:
            missing.append(f'{rule_id} still '
                           f'{seeded_status.get(rule_id)!r}')
        else:
            evidence.append(f'{rule_id}: {base_status.get(rule_id)} -> '
                            f'{seeded_status.get(rule_id)}')

    base_drift = set(base['dates'].get(date, {}).get('history_drift', []))
    seeded_drift = set(seeded['dates'].get(date, {}).get('history_drift', []))
    for path in seed.must_history_drift:
        if path not in seeded_drift or path in base_drift:
            missing.append(f'history drift {path}')
    new_drift = sorted(seeded_drift - base_drift)
    if new_drift:
        evidence.append(f'new history drift: {", ".join(new_drift)}')

    if seed.must_snapshot_fail:
        was = base['dates'].get(date, {}).get('snapshot_matches')
        now = seeded['dates'].get(date, {}).get('snapshot_matches')
        if not (was and not now):
            missing.append(f'snapshot integrity {was} -> {now}')
        else:
            evidence.append('snapshot integrity: True -> False')

    nothing_declared = not (seed.must_move_ledger or seed.must_move_engine
                            or seed.must_break or seed.must_history_drift
                            or seed.must_snapshot_fail)
    if nothing_declared:
        detected = bool(ledger_moved or engine_moved)
        return detected, ('no declared expectation; any movement counts'
                          if detected else 'NOT DETECTED — nothing moved'), \
            evidence

    if missing:
        return False, ('declared effects that did NOT occur: '
                       + '; '.join(missing)), evidence
    return True, 'every declared effect occurred', evidence


def commission(verbose: bool = True) -> int:
    """Run the whole commissioning suite. Returns 0 only if all pass."""
    from verification.replay.replay import read_ledgers
    from verification.replay.compare import compare, Kind
    from verification.config import Severity as _Sev

    os.makedirs(PVF_WORK_DIR, exist_ok=True)
    outcomes: list[Outcome] = []

    if verbose:
        print('=' * 100)
        print('PVF D3 — HISTORICAL REPLAY COMMISSIONING')
        print('Principle 9: a control must be capable of failing.')
        print('Principle 11: silence is never evidence.')
        print('=' * 100)

    base_handle = make_copy(name='pvf_replay_commission_base.db')
    if verbose:
        print(f'baseline copy : {base_handle.copy_path}')
        print('replaying clean baseline (subprocess)...')
    baseline = _replay_in_subprocess(base_handle.copy_path)
    closed = _closed_date_of(baseline)
    if verbose:
        print(f'baseline      : {len(baseline["dates"])} dates, '
              f'closed day {closed}')
        print()

    # -- E. Null control -------------------------------------------------
    if verbose:
        print('[E] NULL CONTROL — identical data must produce zero differences')
    null_copy = os.path.join(PVF_WORK_DIR, 'pvf_replay_seed_NULL.db')
    shutil.copy2(base_handle.copy_path, null_copy)
    null_digest = _replay_in_subprocess(null_copy)
    spurious: list[str] = []
    for date in sorted(set(baseline['dates']) | set(null_digest['dates'])):
        for section in ('ledger', 'engine', 'recorded'):
            for path in _moved(baseline, null_digest, date, section):
                spurious.append(f'{date} {section}.{path}')
    outcomes.append(Outcome(
        seed_id='S-RP-NULL', kind='NULL CONTROL',
        description='Same data, no fault. Any difference is a false positive.',
        detected=(not spurious),
        note=('no false positives across all dates' if not spurious
              else f'{len(spurious)} figures moved with no fault applied: '
                   + ', '.join(spurious[:6])),
        evidence=spurious[:20]))
    if verbose:
        print(f'    {"PASS" if not spurious else "FAIL"} — '
              f'{len(spurious)} spurious differences')
        print()

    # -- A / B. Data and reconciliation faults ---------------------------
    if verbose:
        print(f'[A/B] DATA AND RECONCILIATION FAULTS — seeded into the '
              f'closed day {closed}')
    for seed in DATA_SEEDS:
        seeded_db = os.path.join(PVF_WORK_DIR,
                                 f'pvf_replay_seed_{seed.seed_id}.db')
        if os.path.exists(seeded_db):
            os.remove(seeded_db)
        shutil.copy2(base_handle.copy_path, seeded_db)
        out = Outcome(seed_id=seed.seed_id, kind=seed.kind,
                      description=seed.description)
        try:
            out.rows_changed = _apply(seeded_db, seed.sql, closed)
            seeded = _replay_in_subprocess(seeded_db)
            detected, note, evidence = _check_data_seed(
                seed, baseline, seeded, closed)
            out.detected = detected
            out.note = f'{out.rows_changed} row(s) changed; {note}'
            out.evidence = evidence
        except SeedDidNotApply as exc:
            out.detected = False
            out.note = f'SEED BROKEN — {exc}'
        except Exception as exc:                        # noqa: BLE001
            out.detected = False
            out.note = f'{type(exc).__name__}: {exc}'
        outcomes.append(out)
        if verbose:
            print(f'    {"PASS" if out.detected else "FAIL"} '
                  f'{out.seed_id:<20} {out.note}')
    if verbose:
        print()

    # -- D. The as-at control --------------------------------------------
    if verbose:
        print('[D] AS-AT CONTROL — the retroactivity comparison must be live')
    outcomes.append(_commission_asat())
    if verbose:
        last = outcomes[-1]
        print(f'    {"PASS" if last.detected else "FAIL"} '
              f'{last.seed_id:<20} {last.note}')
        print()

    # -- C. Comparator faults --------------------------------------------
    if verbose:
        print('[C] COMPARATOR FAULTS — the diff engine must classify correctly')
    try:
        index, stored = read_ledgers('production')
    except FileNotFoundError as exc:
        outcomes.append(Outcome(
            seed_id='S-RP-CMP-*', kind='COMPARATOR FAULT',
            description='Comparator commissioning', detected=False,
            note=str(exc).splitlines()[0]))
        stored = None

    if stored:
        current = _stored_as_run(stored, index)

        clean = compare(current, stored, index, 'production')
        outcomes.append(Outcome(
            seed_id='S-RP-CMP-NULL', kind='COMPARATOR FAULT',
            description='Stored replay compared against itself.',
            detected=(not clean.differences),
            note=('clean' if not clean.differences
                  else f'{len(clean.differences)} spurious differences: '
                       + ', '.join(f'{d.date} {d.kind} {d.key}'
                                   for d in clean.differences[:5]))))
        if verbose:
            print(f'    {"PASS" if not clean.differences else "FAIL"} '
                  f'S-RP-CMP-NULL        '
                  f'{len(clean.differences)} differences comparing a set to '
                  f'itself')

        for seed in _comparator_seeds(stored):
            mutated = copy.deepcopy(stored)
            out = Outcome(seed_id=seed.seed_id, kind='COMPARATOR FAULT',
                          description=seed.description)
            try:
                seed.mutate(mutated)
                if seed.side == 'current':
                    result = compare(_stored_as_run(mutated, index), stored,
                                     index, 'production')
                else:
                    result = compare(current, mutated, index, 'production')
                matching = [d for d in result.differences
                            if d.kind == seed.expect_kind]
                if seed.expect_not_blocking:
                    out.detected = bool(matching) and not any(
                        d.severity == _Sev.BLOCK for d in matching)
                    out.note = (f'reported {len(matching)} '
                                f'{seed.expect_kind} at severities '
                                f'{sorted({d.severity for d in matching})}'
                                if matching else
                                f'expected {seed.expect_kind}, got nothing')
                else:
                    out.detected = bool(matching)
                    if out.detected and seed.expect_severity:
                        severities = {d.severity for d in matching}
                        if seed.expect_severity not in severities:
                            out.detected = False
                            out.note = (f'detected but at {sorted(severities)}, '
                                        f'expected {seed.expect_severity}')
                    if not out.note:
                        out.note = (f'reported {seed.expect_kind} at '
                                    f'{seed.expect_severity or "any severity"}'
                                    if out.detected else
                                    f'expected {seed.expect_kind}, got '
                                    f'{sorted({d.kind for d in result.differences}) or "nothing"}')
            except Exception as exc:                    # noqa: BLE001
                out.detected = False
                out.note = f'{type(exc).__name__}: {exc}'
            outcomes.append(out)
            if verbose:
                print(f'    {"PASS" if out.detected else "FAIL"} '
                      f'{out.seed_id:<20} {out.note}')
    if verbose:
        print()

    passed = sum(1 for o in outcomes if o.detected)
    total = len(outcomes)
    if verbose:
        print('=' * 100)
        print(f'COMMISSIONING RESULT: {passed}/{total} '
              f'{"PASS" if passed == total else "FAIL"}')
        print('=' * 100)
        for o in outcomes:
            print(f'  {"PASS" if o.detected else "FAIL"}  [{o.kind:<22}] '
                  f'{o.seed_id}')
            print(f'        {o.description}')
            print(f'        {o.note}')
        print()
        if passed != total:
            print('The framework is NOT commissioned. A replay that cannot be '
                  'shown to detect a seeded fault provides no assurance about '
                  'history, and must not be used as a release gate.')

    _write_evidence(outcomes, passed, total, closed)
    return 0 if passed == total else 1


def _stored_as_run(stored: dict, index: dict):
    """Rehydrate a stored replay into something ``compare`` accepts.

    The "current" side of every comparator seed is the stored set itself,
    so that the difference reported is entirely attributable to the seed
    and not to two runs having legitimately drifted.
    """
    from verification.replay.replay import DateReplay, ReplayRun

    run = ReplayRun(started_at=index.get('started_at', ''),
                    app_version=index.get('app_version', ''),
                    business_date=index.get('business_date', ''))
    fields = DateReplay.__dataclass_fields__
    for date in sorted(stored):
        record = stored[date]
        entry = DateReplay(**{k: v for k, v in record.items()
                              if k in fields and k != 'reconciliations'})
        entry.reconciliations = [
            rec.Reconciliation(**r) for r in record.get('reconciliations', [])]
        run.dates.append(entry)
    return run


def _commission_asat() -> Outcome:
    """Prove the retroactivity comparison is live, not decorative.

    The framework masks exactly one path from the as-at comparison —
    ``nas.audit_header.generated_at``, which records when the report was
    produced. Removing that mask must make the drift appear. If it does
    not, the two passes were not really taken under different clocks, and
    every "no as-at drift" result the framework has ever reported would
    have been vacuous.
    """
    from verification.replay import replay as rp

    out = Outcome(
        seed_id='S-RP-ASAT', kind='AS-AT CONTROL',
        description=(
            'Remove the one declared as-at exclusion and require the drift '
            'it was masking to be reported. This is the proof that PASS A '
            'and PASS C really ran under different clocks and that the '
            'comparator compares them.'))
    saved = list(rp.ASAT_EXCLUSIONS)
    try:
        rp.ASAT_EXCLUSIONS.clear()
        run = rp.run_replay(prove_order=False, quiet=True)
        drifted = [d for d in run.dates if d.asat_drift]
        paths = sorted({item['path'] for d in drifted for item in d.asat_drift})
        expected = 'nas.audit_header.generated_at'
        out.detected = expected in paths
        out.evidence = paths[:20]
        out.note = (f'{len(drifted)} past date(s) reported drift on '
                    f'{len(paths)} path(s) once unmasked'
                    if out.detected else
                    f'unmasking produced {paths or "nothing"}; the as-at '
                    f'comparison is not measuring what it claims to')
    except Exception as exc:                            # noqa: BLE001
        out.detected = False
        out.note = f'{type(exc).__name__}: {exc}'
    finally:
        rp.ASAT_EXCLUSIONS.clear()
        rp.ASAT_EXCLUSIONS.extend(saved)
    return out


def _write_evidence(outcomes: list, passed: int, total: int,
                    closed: str) -> str:
    import datetime as _dt
    from dataclasses import asdict
    from verification.replay import report as rpreport

    started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    payload = {
        'commissioned': passed == total,
        'passed': passed,
        'total': total,
        'seeded_closed_date': closed,
        'outcomes': [asdict(o) for o in outcomes],
    }
    lines = ['=' * 100,
             'FINALGRID — HISTORICAL REPLAY COMMISSIONING',
             'Wave 0 Deliverable 3 — Principle 9 / Principle 11',
             '=' * 100,
             f'Result: {passed}/{total} '
             f'{"COMMISSIONED" if passed == total else "NOT COMMISSIONED"}',
             f'Faults seeded into closed business day: {closed}',
             '']
    for o in outcomes:
        lines.append(f'[{"PASS" if o.detected else "FAIL"}] {o.seed_id}  '
                     f'({o.kind})')
        lines.append(f'    {o.description}')
        lines.append(f'    {o.note}')
        for item in o.evidence[:12]:
            lines.append(f'      - {item}')
        lines.append('')
    text = '\n'.join(lines) + '\n'
    return rpreport.write_pack(payload, text, 'replay_commission', started)
