"""
Seeded-fault commissioning for the Financial Parity Harness.

Constitutional basis: Principle 9 — no assurance mechanism may be trusted
until it has been demonstrated to fail under a deliberately seeded fault.
A parity harness that has only ever reported the divergences already
present in production has not been shown to *detect*; it may simply be
describing.

Method
------
For each seed:
  1. Take a fresh disposable copy of production.
  2. Apply a single, surgical data mutation to that copy.
  3. Measure all quantities in a SEPARATE PROCESS.
  4. Assert the target quantity's verdict changed as predicted.

Each seed runs in its own process because ``create_app()`` touches
module-level application state (the APScheduler instance among others).
Process isolation guarantees that seed N cannot influence seed N+1, which
is what makes the results trustworthy rather than merely encouraging.

Scope note
----------
This module commissions D1 ONLY. The general Fault Injection Framework —
which will seed faults across every verification layer, not just parity —
is Wave 0 deliverable D5 and is not started.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field

from verification.config import EVIDENCE_DIR, PVF_WORK_DIR, Verdict
from verification.dbcopy import make_copy, assert_production_untouched

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Seed:
    """One deliberately injected fault."""
    seed_id: str
    target: str                 # quantity id expected to react
    description: str
    sql: list[str]              # mutations applied to the working copy
    expect_from: str            # verdict before the seed
    expect_to: str              # verdict required after the seed


@dataclass
class SeedOutcome:
    seed_id: str
    target: str
    description: str
    baseline_verdict: str = ''
    seeded_verdict: str = ''
    detected: bool = False
    note: str = ''


# ---------------------------------------------------------------------------
# Seed catalogue
# ---------------------------------------------------------------------------
# Each seed introduces the SPECIFIC class of defect the target quantity
# exists to catch. A seed that produces divergence for an incidental
# reason would prove nothing about the quantity's real sensitivity.

SEEDS: list[Seed] = [
    Seed(
        seed_id='S-Q03',
        target='Q03',
        description=(
            'Post a room_rent ledger row for one reservation. This is the '
            'exact condition under which the three room-revenue definitions '
            'stop agreeing — the trap Wave 1 disarms.'),
        sql=[
            "INSERT INTO extra_charges "
            "(reservation_id, description, amount, charge_date, charge_type, "
            " charge_category, is_correction, is_reversal) "
            "SELECT id, 'SEEDED Room Rent', 999.00, arrival_date, 'room_rent', "
            "'Room', 0, 0 FROM reservations ORDER BY id LIMIT 1",
        ],
        expect_from=Verdict.AGREED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q04',
        target='Q04',
        description=(
            'Same room_rent posting seen at date level: the ledger-posted '
            'implementation becomes non-zero and must be compared.'),
        sql=[
            "INSERT INTO extra_charges "
            "(reservation_id, description, amount, charge_date, charge_type, "
            " charge_category, is_correction, is_reversal) "
            "SELECT id, 'SEEDED Room Rent', 999.00, arrival_date, 'room_rent', "
            "'Room', 0, 0 FROM reservations ORDER BY id LIMIT 1",
        ],
        expect_from=Verdict.AGREED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q09',
        target='Q09',
        description=(
            'Insert a payment reversal row. Raw summation adds it; signed '
            'summation subtracts it. This is the 29-of-31 defect.'),
        sql=[
            "INSERT INTO payments "
            "(reservation_id, payment_mode_id, amount, payment_date, "
            " is_voided, is_correction, is_reversal, payment_purpose) "
            "SELECT p.reservation_id, p.payment_mode_id, 500.00, "
            "p.payment_date, 0, 1, 1, 'settlement' "
            "FROM payments p ORDER BY p.id LIMIT 1",
        ],
        expect_from=Verdict.AGREED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q02',
        target='Q02',
        description=(
            'Insert an extra-charge reversal row — the charge-side twin of '
            'S-Q09.'),
        sql=[
            "INSERT INTO extra_charges "
            "(reservation_id, description, amount, charge_date, charge_type, "
            " charge_category, is_correction, is_reversal) "
            "SELECT reservation_id, 'SEEDED reversal', 250.00, charge_date, "
            "NULL, 'Other', 1, 1 FROM extra_charges ORDER BY id LIMIT 1",
        ],
        expect_from=Verdict.AGREED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q07',
        target='Q07',
        description=(
            'Corrupt one stored tax line. Stored tax must then disagree '
            'with live recomputation — an invoice-versus-balance gap.'),
        sql=[
            "UPDATE tax_lines SET tax_amount = tax_amount + 250.00 "
            "WHERE id = (SELECT MIN(id) FROM tax_lines)",
        ],
        expect_from=Verdict.AGREED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q15',
        target='Q15',
        description=(
            'Tamper with a stored night-audit total. The recomputation must '
            'no longer match what was frozen.'),
        sql=[
            "UPDATE night_audit_logs SET accrual_revenue = accrual_revenue + 5000 "
            "WHERE id = (SELECT MIN(id) FROM night_audit_logs)",
        ],
        expect_from=Verdict.AGREED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q22',
        target='Q22',
        description=(
            'Record an OTA payout. Gross outstanding ignores it; net '
            'outstanding must fall. Proves the receivable comparison is live.'),
        sql=[
            "INSERT INTO ota_payouts "
            "(ota_channel, payout_date, gross_amount, commission_amount, "
            " tax_deducted, net_paid) "
            "VALUES ('MakeMyTrip', '2026-05-28', 1000.00, 0, 0, 1000.00)",
        ],
        expect_from=Verdict.DIVERGED, expect_to=Verdict.DIVERGED,
    ),
    Seed(
        seed_id='S-Q14',
        target='Q14',
        description=(
            'Route one charge to a folio. The folio partition sum must move '
            'toward the reservation sum, proving the partition check reads '
            'live routing rather than a constant.'),
        sql=[
            "UPDATE extra_charges SET folio_id = "
            "(SELECT f.id FROM folios f WHERE f.reservation_id = "
            " extra_charges.reservation_id LIMIT 1) "
            "WHERE id = (SELECT MIN(id) FROM extra_charges)",
        ],
        expect_from=Verdict.DIVERGED, expect_to=Verdict.DIVERGED,
    ),
]


#: Quantities that CANNOT be commissioned by data mutation, with the
#: reason. This list is evidence in its own right: it records where two
#: named implementations are already structurally equivalent, so their
#: agreement is tautological rather than verified.
NOT_SEEDABLE = {
    'Q01': 'Census quantity — single source by design, nothing to compare.',
    'Q05': ('Both implementations apply the same room_rent exclusion filter '
            'over the same rows. Agreement is structural; no data mutation '
            'can separate them. Divergence would require a code change.'),
    'Q06': 'Already DIVERGED on production data — detection demonstrated live.',
    'Q08': ('Discount suppression only triggers when nightly rows or '
            'room_rent rows exist; covered indirectly by S-Q03.'),
    'Q10': ('kpi_helpers and the ORM aggregation read identical rows with '
            'identical filters. Structural agreement.'),
    'Q11': 'VACUOUS — requires refund/void regression data (Wave 0 D6).',
    'Q12': 'Already DIVERGED on production data — detection demonstrated live.',
    'Q13': 'Already DIVERGED on production data — detection demonstrated live.',
    'Q16': ('Implemented in D2. The flash report delegates to the same '
            'canonical helpers it is compared against, so no data mutation '
            'can separate them — a divergence would require a code change. '
            'Structural agreement.'),
    'Q17': 'Already DIVERGED on production data — detection demonstrated live.',
    'Q18': 'Already DIVERGED on production data — detection demonstrated live.',
    'Q19': ('Both implementations delegate to occupancy_engine, which is '
            'already the converged canonical source (Phase 2 §3).'),
    'Q20': 'Already DIVERGED on production data — detection demonstrated live.',
    'Q21': 'VACUOUS — requires shift regression data (Wave 0 D6).',
}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _measure_in_subprocess(db_path: str) -> dict:
    """Measure a prepared database in an isolated process."""
    proc = subprocess.run(
        [sys.executable, '-m', 'verification', '_measure', '--db', db_path],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
    )
    if '---PVF-JSON---' not in proc.stdout:
        raise RuntimeError(
            f'Measurement subprocess produced no result.\n'
            f'stdout tail: {proc.stdout[-1500:]}\n'
            f'stderr tail: {proc.stderr[-1500:]}')
    payload = proc.stdout.split('---PVF-JSON---', 1)[1].strip()
    return json.loads(payload)


def _apply(db_path: str, statements: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def commission(verbose: bool = True) -> int:
    """Run the full seeded-fault commissioning suite.

    Returns 0 when every seed was detected, 1 otherwise.
    """
    os.makedirs(PVF_WORK_DIR, exist_ok=True)

    # Clean baseline copy, measured once.
    base_handle = make_copy(name='pvf_commission_base.db')
    if verbose:
        print('=' * 100)
        print('PVF D1 — SEEDED-FAULT COMMISSIONING')
        print('Constitutional basis: Principle 9 — a control must be capable '
              'of failing')
        print('=' * 100)
        print(f'baseline copy : {base_handle.copy_path}')
        print('measuring clean baseline...')

    baseline = _measure_in_subprocess(base_handle.copy_path)
    if verbose:
        print(f'baseline measured: {len(baseline)} quantities')
        print()

    outcomes: list[SeedOutcome] = []

    for seed in SEEDS:
        seeded_db = os.path.join(PVF_WORK_DIR, f'pvf_seed_{seed.seed_id}.db')
        if os.path.exists(seeded_db):
            os.remove(seeded_db)
        shutil.copy2(base_handle.copy_path, seeded_db)

        out = SeedOutcome(seed_id=seed.seed_id, target=seed.target,
                          description=seed.description)
        try:
            _apply(seeded_db, seed.sql)
            seeded = _measure_in_subprocess(seeded_db)
            out.baseline_verdict = baseline.get(seed.target, {}).get('verdict', '?')
            out.seeded_verdict = seeded.get(seed.target, {}).get('verdict', '?')

            base_div = baseline.get(seed.target, {}).get('divergences', 0)
            seed_div = seeded.get(seed.target, {}).get('divergences', 0)
            base_impl = baseline.get(seed.target, {}).get('implementations', {})
            seed_impl = seeded.get(seed.target, {}).get('implementations', {})

            if out.baseline_verdict == Verdict.DIVERGED:
                # Already diverging. The verdict cannot change and the
                # divergence COUNT may not either — a quantity that emits
                # one aggregate divergence keeps emitting exactly one
                # while its magnitude moves. Detection therefore requires
                # the measured VALUES to respond to the seed.
                moved = {k: (base_impl.get(k), v)
                         for k, v in seed_impl.items()
                         if base_impl.get(k) != v}
                out.detected = bool(moved) or seed_div != base_div
                out.note = (
                    f'already DIVERGED; divergence count {base_div} -> '
                    f'{seed_div}; values moved: '
                    + (', '.join(f'{k}: {a} -> {b}' for k, (a, b) in
                                 sorted(moved.items())) if moved else 'none'))
            else:
                values_moved = any(base_impl.get(k) != v
                                   for k, v in seed_impl.items())
                out.detected = (out.seeded_verdict == seed.expect_to
                                and values_moved)
                out.note = (f'divergence count {base_div} -> {seed_div}; '
                            f'values moved: {values_moved}')
        except Exception as exc:                      # pragma: no cover
            out.note = f'ERROR: {exc}'
            out.detected = False

        outcomes.append(out)
        if verbose:
            mark = 'DETECTED' if out.detected else '*** MISSED ***'
            print(f'[{seed.seed_id}] target {seed.target}: '
                  f'{out.baseline_verdict} -> {out.seeded_verdict}   {mark}')
            print(f'          {out.note}')

    # The commissioning run must not have disturbed production either.
    prod_hash = assert_production_untouched(base_handle)

    detected = sum(1 for o in outcomes if o.detected)
    total = len(outcomes)
    all_pass = detected == total

    if verbose:
        print()
        print('-' * 100)
        print(f'SEEDS DETECTED   : {detected} / {total}')
        print(f'NOT SEEDABLE     : {len(NOT_SEEDABLE)} quantities '
              '(reasons recorded in evidence)')
        print(f'PRODUCTION HASH  : {prod_hash} (unchanged)')
        print(f'COMMISSIONING    : {"PASS" if all_pass else "FAIL"}')
        print('-' * 100)
        if not all_pass:
            print('The harness FAILED to detect a fault it was built to catch.')
            print('It must not be used as a release gate until this is fixed.')

    _write_commission_evidence(outcomes, baseline, prod_hash, all_pass)
    return 0 if all_pass else 1


def _write_commission_evidence(outcomes, baseline, prod_hash, all_pass) -> str:
    import datetime as _dt
    stamp = _dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(EVIDENCE_DIR, f'{stamp}_commission')
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        'kind': 'PVF D1 seeded-fault commissioning',
        'constitutional_basis': 'Principle 9',
        'generated_at': _dt.datetime.utcnow().isoformat(timespec='seconds'),
        'production_hash_after': prod_hash,
        'production_untouched': True,
        'result': 'PASS' if all_pass else 'FAIL',
        'seeds_detected': sum(1 for o in outcomes if o.detected),
        'seeds_total': len(outcomes),
        'baseline_verdicts': baseline,
        'seeds': [
            {'seed_id': o.seed_id, 'target': o.target,
             'description': o.description,
             'baseline_verdict': o.baseline_verdict,
             'seeded_verdict': o.seeded_verdict,
             'detected': o.detected, 'note': o.note}
            for o in outcomes],
        'not_seedable': NOT_SEEDABLE,
    }
    with open(os.path.join(out_dir, 'commission.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write('\n')
    return out_dir
