"""
Seeded-fault commissioning for the Golden Master Framework.

Constitutional basis: Principle 9 and Principle 11 — a control that
cannot fail is not a control, and silence is never evidence. A golden
master that has only ever reported "no differences" has not been shown
to detect anything; it may simply be comparing a constant to itself.

Four classes of proof, because they fail independently:

A. DATA FAULTS — a surgical mutation to a copy of the data, captured in
   a separate process, must move the figures on the surfaces that
   present that data. This is the end-to-end proof: data → route →
   template → figure → detection.

B. CLOCK FAULT — the same data captured with the clock frozen one day
   later must differ. This proves the freeze is load-bearing. If moving
   the clock changed nothing, the freeze would be decorative and the
   masters would silently be measuring "whenever".

C. COMPARATOR FAULTS — a stored master is mutated field by field and the
   comparison must report exactly the expected kind of difference. This
   reaches the failure modes no data mutation can reach: a route losing
   its authentication, a template being swapped, a surface disappearing.

D. NULL CONTROL — the same data with no fault at all must report zero
   differences. Without this, a framework that flagged everything would
   pass every other test in this file. A control that always fires is as
   useless as one that never does.

Every seed runs its capture in a separate process, because the clock
patch and the Flask application both hold module-level state that must
not leak between runs.
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

from verification.config import PVF_WORK_DIR, PROJECT_ROOT, Severity
from verification.dbcopy import make_copy


# ---------------------------------------------------------------------------
# A — data faults
# ---------------------------------------------------------------------------

@dataclass
class DataSeed:
    seed_id: str
    description: str
    sql: list
    #: Surfaces that MUST react. Detection elsewhere is welcome but does
    #: not count: a seed that only moved an unrelated page would prove
    #: the framework noisy, not sensitive.
    must_react: list


DATA_SEEDS: list[DataSeed] = [
    DataSeed(
        seed_id='S-GM-PAYMENT',
        description=('Post a 777.00 settlement payment on the business date. '
                     'Every cash-basis surface must move.'),
        sql=["INSERT INTO payments "
             "(reservation_id, payment_mode_id, amount, payment_date, "
             " is_voided, is_correction, is_reversal, payment_purpose) "
             "SELECT p.reservation_id, p.payment_mode_id, 777.00, "
             "(SELECT \"current_date\" FROM business_date ORDER BY id LIMIT 1), "
             "0, 0, 0, 'settlement' FROM payments p ORDER BY p.id LIMIT 1"],
        must_react=['reports.payment_collection', 'main.dashboard'],
    ),
    DataSeed(
        seed_id='S-GM-CHARGE',
        description=('Post a 333.00 food charge to the SAME reservation the '
                     'folio and invoice surfaces are pinned to. This tests '
                     'attribution, not just global sensitivity: the charge '
                     'must appear on that guest\'s documents, not merely '
                     'somewhere in a total.'),
        sql=["INSERT INTO extra_charges "
             "(reservation_id, description, amount, charge_date, charge_type, "
             " charge_category, is_correction, is_reversal) "
             "SELECT id, 'SEEDED Food', 333.00, "
             "(SELECT \"current_date\" FROM business_date ORDER BY id LIMIT 1), "
             "'food', 'Restaurant', 0, 0 "
             "FROM reservations WHERE status='CheckedOut' ORDER BY id LIMIT 1"],
        must_react=['main.reservation_folio__checked_out_reservation',
                    'main.invoice__checked_out_reservation'],
    ),
    DataSeed(
        seed_id='S-GM-TAX',
        description=('Corrupt one stored tax line by 100.00. The GST and '
                     'invoice surfaces must move; a tax figure that could be '
                     'altered without any surface reacting would mean GST is '
                     'recomputed for display and the stored line is dead.'),
        sql=["UPDATE tax_lines SET tax_amount = tax_amount + 100.00 "
             "WHERE id = (SELECT MIN(id) FROM tax_lines)"],
        must_react=['billing.gst_report'],
    ),
    DataSeed(
        seed_id='S-GM-ROOM',
        description=('Flip one vacant room to Dirty. Housekeeping and room '
                     'status surfaces must move.'),
        sql=["UPDATE rooms SET status='Dirty' "
             "WHERE id = (SELECT MIN(id) FROM rooms WHERE status='Vacant')"],
        must_react=['reports.room_status_report'],
    ),
    DataSeed(
        seed_id='S-GM-RESERVATION',
        description=('Raise one reservation nightly rate by 1234.00. Revenue '
                     'and receivable surfaces must move.'),
        sql=["UPDATE reservations SET rate_per_night = rate_per_night + 1234.00 "
             "WHERE id = (SELECT MIN(id) FROM reservations)"],
        must_react=['reports.revenue'],
    ),
    DataSeed(
        seed_id='S-GM-PAISA',
        description=('Move a single reservation total by ONE PAISA (0.01). '
                     'The framework claims no tolerance band; this is the '
                     'test of that claim. A rounding-tolerant comparison '
                     'would let a systematic sub-rupee drift through on '
                     'every surface at once.'),
        sql=["UPDATE reservations SET rate_per_night = rate_per_night + 0.01 "
             "WHERE id = (SELECT MIN(id) FROM reservations)"],
        must_react=[],          # any reaction counts; sensitivity is the point
    ),
]


# ---------------------------------------------------------------------------
# C — comparator faults
# ---------------------------------------------------------------------------

@dataclass
class ComparatorSeed:
    seed_id: str
    description: str
    #: mutate(master_record) -> None, applied to a deep copy
    mutate: object
    expect_kind: str
    expect_severity: str = ''


def _pick(masters: dict, category: str) -> str:
    """Lowest surface_id in *category* that returned 200 — deterministic."""
    for sid in sorted(masters):
        rec = masters[sid]
        if rec.get('category') == category and rec.get('status') == 200:
            return sid
    raise RuntimeError(f'No healthy {category} surface to mutate')


def _comparator_seeds(masters: dict) -> list:
    from verification.golden.compare import Kind

    fin = _pick(masters, 'FINANCIAL')
    ops = _pick(masters, 'OPERATIONAL')

    def set_status(m):
        m[fin]['status'] = 500

    def set_anon(m):
        m[fin]['anon_status'] = 200

    def move_figure(m):
        figures = m[fin]['figures']
        key = sorted(figures)[0]
        figures[key] = str(float(figures[key] or 0) + 0.01) \
            if _numeric(figures[key]) else 'MUTATED'

    def drop_figure(m):
        figures = m[fin]['figures']
        del figures[sorted(figures)[0]]

    def swap_template(m):
        m[fin]['templates'] = ['some/other_template.html']

    def break_body(m):
        m[fin]['body_sha256'] = '0' * 64

    def remove_surface(m):
        del m[ops]

    return [
        ComparatorSeed('S-GM-CMP-STATUS',
                       f'Master says {fin} returned 500; it returns 200.',
                       set_status, Kind.STATUS_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-GM-CMP-ANON',
                       f'Master says {fin} served anonymous callers 200 — an '
                       f'authorisation regression.',
                       set_anon, Kind.ANON_STATUS_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-GM-CMP-FIGURE',
                       f'One figure on {fin} moved by 0.01.',
                       move_figure, Kind.FIGURE_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-GM-CMP-FIGURE-GONE',
                       f'{fin} now renders a figure the master does not have '
                       f'— a release that added a number to a financial page.',
                       drop_figure, Kind.FIGURE_ADDED, Severity.BLOCK),
        ComparatorSeed('S-GM-CMP-TEMPLATE',
                       f'{fin} is rendered by a different template.',
                       swap_template, Kind.TEMPLATES_CHANGED, Severity.BLOCK),
        ComparatorSeed('S-GM-CMP-BODY',
                       f'{fin} renders different HTML with identical figures — '
                       f'a presentation-only change.',
                       break_body, Kind.BODY_CHANGED, Severity.WARN),
        ComparatorSeed('S-GM-CMP-SURFACE',
                       f'{ops} exists in the release but not in the master '
                       f'set — a route added without a master.',
                       remove_surface, Kind.SURFACE_ADDED, Severity.WARN),
    ]


def _numeric(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


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
    reacting_surfaces: list = field(default_factory=list)


def _capture_in_subprocess(db_path: str, env_extra: dict | None = None) -> dict:
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, '-m', 'verification', '_gm_capture_json',
         '--db', db_path],
        cwd=PROJECT_ROOT, capture_output=True, text=True, env=env)
    if '---GM-JSON---' not in proc.stdout:
        raise RuntimeError(
            f'Capture subprocess produced no result.\n'
            f'stdout tail: {proc.stdout[-1500:]}\n'
            f'stderr tail: {proc.stderr[-1500:]}')
    return json.loads(proc.stdout.split('---GM-JSON---', 1)[1].strip())


def _digest_diff(base: dict, other: dict) -> list:
    """Surfaces whose captured digest moved, with what moved."""
    moved = []
    for sid in sorted(set(base) | set(other)):
        b, o = base.get(sid), other.get(sid)
        if b is None or o is None:
            moved.append((sid, 'surface presence'))
            continue
        reasons = []
        if b['status'] != o['status']:
            reasons.append('status')
        if b['anon_status'] != o['anon_status']:
            reasons.append('anon_status')
        if b['figures'] != o['figures']:
            changed = [k for k in set(b['figures']) | set(o['figures'])
                       if b['figures'].get(k) != o['figures'].get(k)]
            reasons.append(f'{len(changed)} figures')
        if b['body_sha256'] != o['body_sha256']:
            reasons.append('body')
        if reasons:
            moved.append((sid, ', '.join(reasons)))
    return moved


class SeedDidNotApply(RuntimeError):
    """A seed's SQL ran cleanly but changed no rows.

    This is the most dangerous failure mode in a commissioning suite. An
    ``INSERT ... SELECT ... WHERE status='CheckedIn'`` against a dataset
    with no checked-in guests inserts nothing, succeeds, and the run then
    reports "fault not detected" — which reads as a defect in the thing
    being commissioned rather than in the seed. That is a false alarm in
    the one place where false alarms are least affordable, and the first
    version of this suite produced exactly that.

    So rowcount is asserted. A seed that did not bite is a broken seed
    and says so.
    """


def _apply(db_path: str, statements: list) -> int:
    """Apply seed SQL and return the number of rows actually changed."""
    conn = sqlite3.connect(db_path)
    try:
        changed = 0
        for stmt in statements:
            cur = conn.execute(stmt)
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


def commission(verbose: bool = True) -> int:
    """Run the whole commissioning suite. Returns 0 only if all pass."""
    from verification.golden.capture import read_masters
    from verification.golden.compare import compare

    os.makedirs(PVF_WORK_DIR, exist_ok=True)
    outcomes: list[Outcome] = []

    if verbose:
        print('=' * 100)
        print('PVF D2 — GOLDEN MASTER COMMISSIONING')
        print('Principle 9: a control must be capable of failing.')
        print('Principle 11: silence is never evidence.')
        print('=' * 100)

    base_handle = make_copy(name='pvf_gm_commission_base.db')
    if verbose:
        print(f'baseline copy : {base_handle.copy_path}')
        print('capturing clean baseline (subprocess)...')
    baseline = _capture_in_subprocess(base_handle.copy_path)
    if verbose:
        print(f'baseline captured: {len(baseline)} surfaces')
        print()

    # -- D. Null control ------------------------------------------------
    if verbose:
        print('[D] NULL CONTROL — identical data must produce zero differences')
    null_copy = os.path.join(PVF_WORK_DIR, 'pvf_gm_seed_NULL.db')
    shutil.copy2(base_handle.copy_path, null_copy)
    null_capture = _capture_in_subprocess(null_copy)
    null_moved = _digest_diff(baseline, null_capture)
    outcomes.append(Outcome(
        seed_id='S-GM-NULL', kind='NULL CONTROL',
        description='Same data, no fault. Any difference is a false positive.',
        detected=(len(null_moved) == 0),
        note=('no false positives' if not null_moved
              else f'{len(null_moved)} surfaces moved with no fault applied: '
                   + ', '.join(s for s, _ in null_moved[:8])),
        reacting_surfaces=[s for s, _ in null_moved]))
    if verbose:
        print(f'    {"PASS" if not null_moved else "FAIL"} — '
              f'{len(null_moved)} spurious differences')
        print()

    # -- A. Data faults -------------------------------------------------
    if verbose:
        print('[A] DATA FAULTS — a mutation to the data must reach the surface')
    for seed in DATA_SEEDS:
        seeded_db = os.path.join(PVF_WORK_DIR, f'pvf_gm_seed_{seed.seed_id}.db')
        if os.path.exists(seeded_db):
            os.remove(seeded_db)
        shutil.copy2(base_handle.copy_path, seeded_db)
        out = Outcome(seed_id=seed.seed_id, kind='DATA FAULT',
                      description=seed.description)
        try:
            rows = _apply(seeded_db, seed.sql)
            out.rows_changed = rows
            seeded = _capture_in_subprocess(seeded_db)
            moved = _digest_diff(baseline, seeded)
            moved_ids = [s for s, _ in moved]
            out.reacting_surfaces = moved_ids
            missing = [s for s in seed.must_react if s not in moved_ids]
            if not moved:
                out.detected = False
                out.note = (f'NOT DETECTED — {rows} row(s) changed and no '
                            f'surface reacted')
            elif missing:
                out.detected = False
                out.note = (f'{len(moved)} surfaces reacted but these were '
                            f'required and did not: {", ".join(missing)}')
            else:
                out.detected = True
                out.note = f'{rows} row(s) changed, {len(moved)} surfaces reacted'
        except SeedDidNotApply as exc:
            out.detected = False
            out.note = f'SEED BROKEN — {exc}'
        except Exception as exc:
            out.detected = False
            out.note = f'{type(exc).__name__}: {exc}'
        outcomes.append(out)
        if verbose:
            print(f'    {"PASS" if out.detected else "FAIL"} {out.seed_id:<18} '
                  f'{out.note}')
    if verbose:
        print()

    # -- B. Clock fault -------------------------------------------------
    if verbose:
        print('[B] CLOCK FAULT — the frozen clock must be load-bearing')
    clock_db = os.path.join(PVF_WORK_DIR, 'pvf_gm_seed_CLOCK.db')
    shutil.copy2(base_handle.copy_path, clock_db)
    out = Outcome(
        seed_id='S-GM-CLOCK', kind='CLOCK FAULT',
        description=('Same data, clock frozen one day later. If nothing moves, '
                     'freezing the clock is decorative and the masters are '
                     'silently measuring "whenever the run happened".'))
    try:
        import datetime as _dt
        from verification.golden.capture import read_business_date
        shifted = read_business_date(clock_db) + _dt.timedelta(days=1)
        clock_capture = _capture_in_subprocess(
            clock_db, {'PVF_GM_FREEZE_DATE': shifted.isoformat()})
        moved = _digest_diff(baseline, clock_capture)
        out.reacting_surfaces = [s for s, _ in moved]
        out.detected = bool(moved)
        out.note = (f'{len(moved)} surfaces moved when the clock moved one day'
                    if moved else
                    'NOT DETECTED — no surface depends on the frozen clock')
    except Exception as exc:
        out.detected = False
        out.note = f'{type(exc).__name__}: {exc}'
    outcomes.append(out)
    if verbose:
        print(f'    {"PASS" if out.detected else "FAIL"} {out.seed_id:<18} '
              f'{out.note}')
        print()

    # -- C. Comparator faults -------------------------------------------
    if verbose:
        print('[C] COMPARATOR FAULTS — the diff engine must classify correctly')
    try:
        index, masters = read_masters('production')
    except FileNotFoundError as exc:
        outcomes.append(Outcome(
            seed_id='S-GM-CMP-*', kind='COMPARATOR FAULT',
            description='Comparator commissioning', detected=False,
            note=str(exc).splitlines()[0]))
        masters = None

    if masters:
        # The "current" side is the stored master set itself, replayed
        # through the capture record type. Comparing a set to itself must
        # be clean; every fault below is injected into the MASTER copy so
        # the difference is entirely attributable to the seed.
        from verification.golden.capture import SurfaceCapture
        current = [SurfaceCapture(**{k: v for k, v in rec.items()
                                     if k in SurfaceCapture.__dataclass_fields__})
                   for rec in masters.values()]

        clean = compare(current, masters, index, 'production')
        outcomes.append(Outcome(
            seed_id='S-GM-CMP-NULL', kind='COMPARATOR FAULT',
            description='Master set compared against itself.',
            detected=(len(clean.differences) == 0),
            note=('clean' if not clean.differences
                  else f'{len(clean.differences)} spurious differences')))
        if verbose:
            print(f'    {"PASS" if not clean.differences else "FAIL"} '
                  f'S-GM-CMP-NULL      '
                  f'{len(clean.differences)} differences comparing a set to itself')

        for seed in _comparator_seeds(masters):
            mutated = copy.deepcopy(masters)
            out = Outcome(seed_id=seed.seed_id, kind='COMPARATOR FAULT',
                          description=seed.description)
            try:
                seed.mutate(mutated)
                result = compare(current, mutated, index, 'production')
                kinds = {d.kind for d in result.differences}
                sevs = {d.kind: d.severity for d in result.differences}
                out.detected = seed.expect_kind in kinds
                if out.detected and seed.expect_severity:
                    actual = sevs.get(seed.expect_kind)
                    if actual != seed.expect_severity:
                        out.detected = False
                        out.note = (f'detected but severity {actual}, '
                                    f'expected {seed.expect_severity}')
                if not out.note:
                    out.note = (f'reported {seed.expect_kind}'
                                if out.detected else
                                f'expected {seed.expect_kind}, got '
                                f'{sorted(kinds) or "nothing"}')
            except Exception as exc:
                out.detected = False
                out.note = f'{type(exc).__name__}: {exc}'
            outcomes.append(out)
            if verbose:
                print(f'    {"PASS" if out.detected else "FAIL"} '
                      f'{out.seed_id:<18} {out.note}')
    if verbose:
        print()

    # -- verdict --------------------------------------------------------
    passed = sum(1 for o in outcomes if o.detected)
    total = len(outcomes)
    if verbose:
        print('=' * 100)
        print(f'COMMISSIONING RESULT: {passed}/{total} '
              f'{"PASS" if passed == total else "FAIL"}')
        print('=' * 100)
        for o in outcomes:
            print(f'  {"PASS" if o.detected else "FAIL"}  [{o.kind:<17}] '
                  f'{o.seed_id}')
            print(f'        {o.description}')
            print(f'        {o.note}')
        print()
        if passed != total:
            print('The framework is NOT commissioned. A golden master that '
                  'cannot be shown to detect a seeded fault provides no '
                  'assurance, and must not be used as a release gate.')

    _write_evidence(outcomes, passed, total)
    return 0 if passed == total else 1


def _write_evidence(outcomes: list, passed: int, total: int) -> str:
    from dataclasses import asdict
    from verification.golden import report as gmreport
    import datetime as _dt

    started = _dt.datetime.utcnow().replace(microsecond=0).isoformat()
    payload = {
        'commissioned': passed == total,
        'passed': passed,
        'total': total,
        'outcomes': [asdict(o) for o in outcomes],
    }
    lines = ['=' * 100,
             'FINALGRID — GOLDEN MASTER COMMISSIONING',
             'Wave 0 Deliverable 2 — Principle 9 / Principle 11',
             '=' * 100,
             f'Result: {passed}/{total} '
             f'{"COMMISSIONED" if passed == total else "NOT COMMISSIONED"}',
             '']
    for o in outcomes:
        lines.append(f'[{"PASS" if o.detected else "FAIL"}] {o.seed_id}  '
                     f'({o.kind})')
        lines.append(f'    {o.description}')
        lines.append(f'    {o.note}')
        if o.reacting_surfaces:
            shown = o.reacting_surfaces[:12]
            lines.append(f'    reacting surfaces ({len(o.reacting_surfaces)}): '
                         + ', '.join(shown)
                         + ('...' if len(o.reacting_surfaces) > 12 else ''))
        lines.append('')
    text = '\n'.join(lines) + '\n'
    return gmreport.write_pack(payload, text, 'gm_commission', started)
