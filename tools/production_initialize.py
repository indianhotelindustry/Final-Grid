"""
Production Initialization Framework — master-preserving reset.

Prepares a FinalGrid database for pilot or production use by preserving
every piece of configuration and removing every piece of business
activity. The result behaves like a freshly installed system that has
already been fully configured.

    python tools/production_initialize.py --dry-run
    python tools/production_initialize.py --confirm

This is **not** a financial correction, a migration or a verification
task. It changes no schema object, no business logic and no application
code. It deletes rows from tables classified as activity and sets the
business date.

What makes it safe
------------------
Five conditions abort the run before anything is written, and a sixth
aborts after:

1. the source database fails ``PRAGMA integrity_check``
2. the backup cannot be taken, or fails its own integrity and row-count
   verification
3. **any live table is not classified** — there is no catch-all and no
   default
4. a MASTER table declares a foreign key into a TRANSACTION table, which
   means the classification or the schema is wrong
5. ``--confirm`` was not given
6. after the reset: ``PRAGMA foreign_key_check`` reports a violation, or
   integrity fails, or a preserved table lost rows

Condition 3 is the one that matters most, and it is the defect this tool
exists to not repeat. ``reset_transactional_data.py`` — the utility that
ships with the application — classifies tables for the same purpose and
has **no dynamic catch-all**, so four tables it does not name survive a
reset, leaving 28 orphaned room allocations behind. See
``initialization_classification`` for the full note.

Determinism and idempotency
---------------------------
Deletion order is **derived from the live foreign-key graph**, not
hand-maintained, so a new child table cannot be deleted out of order by
someone forgetting to update a list. The graph contains a genuine cycle
(``reservations`` → ``payments`` → ``reservations``), which is broken
deterministically by table name and recorded in the manifest; correctness
does not rest on the order, because ``PRAGMA foreign_key_check`` is run
afterwards and the run aborts if it reports anything.

Running the tool twice is safe. The second run removes zero rows, resets
the business date to the same value, and reports ``ALREADY INITIALIZED``.

What it deliberately does not do
--------------------------------
It does not run the application, seed defaults, or write to ``app/``. The
boot check in phase 6 runs against a **copy** of the result, because
``create_app()`` commits — migrations, the SQLite column fixer and
``init_data()`` all write — and a verification step that mutated the
delivered database would not be a verification step.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.initialization_classification import (            # noqa: E402
    ACTION, CLASSIFICATION, CLEARED_WITH_WARNING, MASTER, SYSTEM,
    TEMPORARY, TRANSACTION, action_for, cleared_classes,
)

DEFAULT_DB = os.path.join(ROOT, 'instance', 'pms.db')
BACKUP_ROOT = os.path.join(os.path.dirname(ROOT), 'db-backups',
                           'initialization')


class InitializationAborted(RuntimeError):
    """A safety condition failed. Nothing further is attempted."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_only(path: str) -> sqlite3.Connection:
    return sqlite3.connect('file:' + path.replace('\\', '/') + '?mode=ro',
                           uri=True)


def live_tables(conn: sqlite3.Connection) -> list:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def row_counts(conn: sqlite3.Connection) -> dict:
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in live_tables(conn)}


def fk_edges(conn: sqlite3.Connection) -> dict:
    """table -> set of tables it references. Self-references dropped."""
    out = {}
    for t in live_tables(conn):
        refs = {r[2] for r in conn.execute(f'PRAGMA foreign_key_list("{t}")')}
        out[t] = {r for r in refs if r != t}
    return out


def integrity_ok(conn: sqlite3.Connection) -> tuple:
    rows = [r[0] for r in conn.execute('PRAGMA integrity_check')]
    return (rows == ['ok'], rows)


# ---------------------------------------------------------------------------
# Phase 2 — classification
# ---------------------------------------------------------------------------

def verify_classification(conn: sqlite3.Connection) -> dict:
    """Classify every live table, or abort.

    Two mechanical checks back the declared list: nothing unclassified,
    and no MASTER depending on a TRANSACTION.
    """
    tables = live_tables(conn)
    unknown = sorted(t for t in tables if t not in CLASSIFICATION)
    if unknown:
        raise InitializationAborted(
            f'{len(unknown)} live table(s) are not classified: '
            f'{", ".join(unknown)}.\n'
            f'There is no default and no catch-all, by design: a default '
            f'is how a table nobody classified gets silently preserved or '
            f'silently destroyed. Classify them in '
            f'tools/initialization_classification.py, with a reason, '
            f'before running this again.')

    stale = sorted(t for t in CLASSIFICATION if t not in tables)
    edges = fk_edges(conn)
    transactional = {t for t in tables
                     if CLASSIFICATION[t][0] in cleared_classes()}

    contradictions = []
    for table in tables:
        if CLASSIFICATION[table][0] != MASTER:
            continue
        depends = sorted(edges.get(table, set()) & transactional)
        if depends:
            contradictions.append((table, depends))
    if contradictions:
        detail = '; '.join(f'{t} -> {", ".join(d)}' for t, d in contradictions)
        raise InitializationAborted(
            f'{len(contradictions)} MASTER table(s) declare a foreign key '
            f'into a table that will be cleared: {detail}.\n'
            f'Configuration must not depend on activity. Either the '
            f'classification is wrong or the schema is, and both are worth '
            f'stopping for.')

    summary = {}
    for table in tables:
        cls, reason = CLASSIFICATION[table]
        summary[table] = {'classification': cls, 'reason': reason,
                          'action': action_for(table)}
    return {'tables': summary, 'stale_declarations': stale}


def deletion_order(conn: sqlite3.Connection, targets: set) -> tuple:
    """Children before parents, derived from the live FK graph.

    Returns ``(order, broken_cycles)``. Cycles are broken by table name so
    two runs on the same schema produce the same order.
    """
    edges = {t: (fk_edges(conn).get(t, set()) & targets) for t in targets}
    order, placed, broken = [], set(), []
    remaining = set(targets)
    while remaining:
        free = sorted(t for t in remaining
                      if not (edges[t] - placed) - {t})
        if not free:
            # A cycle. Break it deterministically.
            victim = sorted(remaining)[0]
            broken.append(victim)
            free = [victim]
        for t in free:
            order.append(t)
            placed.add(t)
            remaining.discard(t)
    # Children first: a table that references others must be deleted before
    # them, so reverse the dependency-resolved order.
    return list(reversed(order)), broken


# ---------------------------------------------------------------------------
# Phase 1 — safety
# ---------------------------------------------------------------------------

def take_backup(db_path: str, stamp: str, backup_root: str = '') -> dict:
    """Snapshot through the SQLite backup API and verify it. Or abort."""
    target_dir = os.path.join(backup_root or BACKUP_ROOT, stamp)
    os.makedirs(target_dir, exist_ok=True)
    backup_path = os.path.join(target_dir, 'pms_before_initialize.db')

    src = read_only(db_path)
    try:
        ok, detail = integrity_ok(src)
        if not ok:
            raise InitializationAborted(
                f'Source database failed integrity_check: {detail}. '
                f'Nothing was backed up and nothing was changed.')
        source_counts = row_counts(src)
        dst = sqlite3.connect(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    if not os.path.exists(backup_path):
        raise InitializationAborted('Backup file was not created.')

    check = read_only(backup_path)
    try:
        ok, detail = integrity_ok(check)
        if not ok:
            raise InitializationAborted(
                f'Backup failed its own integrity_check: {detail}. '
                f'Refusing to continue without a good backup.')
        backup_counts = row_counts(check)
    finally:
        check.close()

    mismatched = {t: (source_counts.get(t), backup_counts.get(t))
                  for t in set(source_counts) | set(backup_counts)
                  if source_counts.get(t) != backup_counts.get(t)}
    if mismatched:
        raise InitializationAborted(
            f'Backup row counts do not match the source: {mismatched}. '
            f'Refusing to continue.')

    manifest = {
        'created_at': dt.datetime.now().isoformat(timespec='seconds'),
        'source_path': os.path.abspath(db_path),
        'backup_path': os.path.abspath(backup_path),
        'source_sha256': sha256_of(db_path),
        'backup_sha256': sha256_of(backup_path),
        'source_bytes': os.path.getsize(db_path),
        'backup_bytes': os.path.getsize(backup_path),
        'tables': len(source_counts),
        'total_rows': sum(source_counts.values()),
        'row_counts': source_counts,
        'integrity_check': 'ok',
        'row_counts_match': True,
        'note': ('The two SHA-256 values are recorded, not compared. The '
                 'backup API produces a logically identical database that '
                 'need not be byte-identical — page layout may differ. '
                 'Equivalence is established by integrity_check plus a '
                 'per-table row-count match, which is the stronger claim.'),
    }
    with open(os.path.join(target_dir, 'manifest.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=1)
    return {'dir': target_dir, 'path': backup_path, 'manifest': manifest}


# ---------------------------------------------------------------------------
# Phases 4 and 5 — reset and reinitialize
# ---------------------------------------------------------------------------

def reset_and_reinitialize(db_path: str, order: list,
                           business_date: dt.date) -> dict:
    """Delete activity, then set the first production day. One transaction."""
    conn = sqlite3.connect(db_path)
    removed = {}
    try:
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.execute('BEGIN')
        for table in order:
            cur = conn.execute(f'DELETE FROM "{table}"')
            removed[table] = max(cur.rowcount, 0)

        # Reset AUTOINCREMENT so a fresh environment starts at id 1 and two
        # initializations of the same database produce the same next ids.
        try:
            for table in order:
                conn.execute('DELETE FROM sqlite_sequence WHERE name = ?',
                             (table,))
        except sqlite3.OperationalError:
            pass                      # no AUTOINCREMENT tables in schema

        # Phase 5 — the first production day.
        row = conn.execute('SELECT id FROM business_date '
                           'ORDER BY id LIMIT 1').fetchone()
        iso = business_date.isoformat()
        if row is None:
            conn.execute('INSERT INTO business_date (id, "current_date") '
                         'VALUES (1, ?)', (iso,))
        else:
            conn.execute('UPDATE business_date SET "current_date" = ? '
                         'WHERE id = ?', (iso, row[0]))
        _set_if_present(conn, 'business_date', 'is_locked', 0)
        _set_if_present(conn, 'business_date', 'updated_at',
                        dt.datetime.now().isoformat(sep=' '))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return removed


def _set_if_present(conn, table, column, value) -> None:
    cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
    if column in cols:
        conn.execute(f'UPDATE "{table}" SET "{column}" = ?', (value,))


# ---------------------------------------------------------------------------
# Phase 6 — verification
# ---------------------------------------------------------------------------

def verify_result(db_path: str, classification: dict, before: dict,
                  business_date: dt.date, boot_check: bool,
                  cleared_targets: set) -> dict:
    """Verify the result against what was actually asked for.

    ``cleared_targets`` is the set the run really cleared, which is not
    always every table of a cleared class — ``--preserve-guests`` removes
    ``guests`` from it. The first version of this function checked residue
    against the classification instead, and therefore failed its own
    supported option: it demanded that a table it had been told to keep be
    empty. Verifying against the intent rather than the taxonomy is the
    fix.
    """
    checks = []

    def check(name, passed, detail=''):
        checks.append({'check': name, 'passed': bool(passed),
                       'detail': detail})

    conn = read_only(db_path)
    try:
        after = row_counts(conn)

        residue = {t: after[t] for t in cleared_targets if after.get(t)}
        check('no transactional rows remain', not residue,
              f'{len(cleared_targets)} table(s) cleared'
              if not residue else f'residue: {residue}')

        retained = [t for t, m in classification['tables'].items()
                    if m['classification'] in cleared_classes()
                    and t not in cleared_targets]
        if retained:
            kept = {t: after.get(t) for t in retained}
            check('deliberately retained tables are intact',
                  all(after.get(t) == before.get(t) for t in retained),
                  f'retained by request: {kept}')

        masters = [t for t, m in classification['tables'].items()
                   if m['classification'] == MASTER]
        lost = {t: (before.get(t), after.get(t)) for t in masters
                if before.get(t) != after.get(t)}
        check('master tables preserved', not lost,
              f'{len(masters)} master table(s), '
              f'{sum(after.get(t, 0) for t in masters)} rows'
              if not lost else f'changed: {lost}')

        check('schema_migrations preserved',
              after.get('schema_migrations') ==
              before.get('schema_migrations'),
              f'{after.get("schema_migrations")} rows')

        violations = list(conn.execute('PRAGMA foreign_key_check'))
        check('foreign keys valid', not violations,
              'no orphan references'
              if not violations else f'{len(violations)} violation(s)')

        ok, detail = integrity_ok(conn)
        check('integrity check passes', ok, ', '.join(detail))

        bd_row = conn.execute('SELECT "current_date" FROM business_date '
                              'ORDER BY id LIMIT 1').fetchone()
        check('business date initialized',
              bd_row and str(bd_row[0])[:10] == business_date.isoformat(),
              f'business date = {bd_row[0] if bd_row else "MISSING"}')

        bd_rows = conn.execute('SELECT COUNT(*) FROM business_date'
                               ).fetchone()[0]
        check('exactly one business date row', bd_rows == 1,
              f'{bd_rows} row(s)')
    finally:
        conn.close()

    if boot_check:
        passed, detail = _boot_check(db_path)
        check('application boots successfully', passed, detail)
    else:
        check('application boots successfully', True,
              'skipped (--no-boot-check)')

    return {'checks': checks,
            'passed': all(c['passed'] for c in checks),
            'row_counts_after': after}


def _boot_check(db_path: str) -> tuple:
    """Boot the application against a COPY of the result.

    A copy, because ``create_app()`` writes: migrations, the SQLite column
    fixer and ``init_data()`` seeding all commit. Booting the delivered
    database to verify it would change the thing being verified.
    """
    work = tempfile.mkdtemp(prefix='init_boot_')
    probe = os.path.join(work, 'pms.db')
    try:
        shutil.copy2(db_path, probe)
        script = (
            'import os, sys\n'
            'sys.path.insert(0, %r)\n'
            'os.environ["DATABASE_URL"] = "sqlite:///" + %r\n'
            'os.environ.setdefault("FLASK_ENV", "production")\n'
            'from app import create_app\n'
            'app = create_app()\n'
            'with app.app_context():\n'
            '    from app.models import BusinessDate\n'
            '    bd = BusinessDate.query.first()\n'
            '    print("BOOT-OK", bd.current_date if bd else "NO-DATE")\n'
        ) % (ROOT, probe.replace('\\', '/'))
        proc = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                              capture_output=True, text=True, timeout=300,
                              env={**os.environ,
                                   'PYTHONIOENCODING': 'utf-8'})
        if 'BOOT-OK' in proc.stdout:
            return True, proc.stdout.strip().splitlines()[-1]
        tail = (proc.stderr or proc.stdout or '').strip().splitlines()
        return False, tail[-1] if tail else 'no output'
    except Exception as exc:                                 # noqa: BLE001
        return False, f'{type(exc).__name__}: {exc}'
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 7 — report
# ---------------------------------------------------------------------------

def render_report(payload: dict) -> str:
    L = []
    add = L.append
    cls = payload['classification']['tables']
    before = payload['row_counts_before']
    after = payload['verification']['row_counts_after']

    add('# Production Initialization Report')
    add('')
    add(f'Generated {payload["started_at"]} — '
        f'`{os.path.basename(payload["database"])}`')
    add('')
    add(f'**Result: {payload["result"]}**')
    add('')
    if payload['target_is_default_production']:
        add('**Target: the default production database.**')
    else:
        add('**Target: NOT the default production database** — this report '
            'describes a run against `' + payload['database'] + '`, which '
            'is a copy. It is a specimen of what the tool produces, not a '
            'record of production having been initialized.')
    add('')
    add('| | |')
    add('|---|---|')
    add(f'| Database | `{payload["database"]}` |')
    add(f'| Business date set to | **{payload["business_date"]}** |')
    add(f'| Tables classified | {len(cls)} |')
    add(f'| Tables preserved | {payload["counts"]["preserved_tables"]} |')
    add(f'| Tables cleared | {payload["counts"]["cleared_tables"]} |')
    add(f'| Rows removed | **{payload["counts"]["rows_removed"]}** |')
    add(f'| Rows preserved | **{payload["counts"]["rows_preserved"]}** |')
    add(f'| Execution time | {payload["duration_seconds"]}s |')
    add('')

    add('## Backup')
    add('')
    b = payload['backup']['manifest']
    add('| | |')
    add('|---|---|')
    add(f'| Snapshot | `{payload["backup"]["path"]}` |')
    add(f'| Source SHA-256 | `{b["source_sha256"]}` |')
    add(f'| Backup SHA-256 | `{b["backup_sha256"]}` |')
    add(f'| Source bytes | {b["source_bytes"]:,} |')
    add(f'| Backup bytes | {b["backup_bytes"]:,} |')
    add(f'| Integrity | {b["integrity_check"]} |')
    add(f'| Row counts match | {b["row_counts_match"]} |')
    add(f'| Rows captured | {b["total_rows"]:,} across {b["tables"]} tables |')
    add('')
    add(b['note'])
    add('')

    add('## Verification')
    add('')
    add('| Check | Result | Detail |')
    add('|---|---|---|')
    for c in payload['verification']['checks']:
        add(f'| {c["check"]} | {"PASS" if c["passed"] else "**FAIL**"} '
            f'| {c["detail"]} |')
    add('')

    if payload['warnings']:
        add('## Warnings')
        add('')
        for w in payload['warnings']:
            add(f'- **{w["table"]}** ({w["rows"]} rows removed) — {w["note"]}')
        add('')

    add('## Every table')
    add('')
    add('| Table | Classification | Action | Rows before | Rows after | '
        'Reason |')
    add('|---|---|---|---|---|---|')
    for table in sorted(cls):
        meta = cls[table]
        add(f'| `{table}` | {meta["classification"]} | {meta["action"]} '
            f'| {before.get(table, 0)} | {after.get(table, 0)} '
            f'| {meta["reason"]} |')
    add('')

    if payload['classification']['stale_declarations']:
        add('## Declared but not present in this database')
        add('')
        add('Harmless, but reported: a name here that the schema does not '
            'have means the classification is drifting from the schema.')
        add('')
        for t in payload['classification']['stale_declarations']:
            add(f'- `{t}`')
        add('')

    add('## Rollback')
    add('')
    add('```')
    add('# stop the application first')
    add(f'copy "{payload["backup"]["path"]}" "{payload["database"]}"')
    add('```')
    add('')
    add('The snapshot is a complete database, verified by `integrity_check` '
        'and a per-table row-count match at the moment it was taken. '
        'Restoring it returns the system to the exact state before this '
        'run.')
    return '\n'.join(L) + '\n'


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def initialize(db_path: str, confirm: bool, business_date: dt.date,
               preserve_guests: bool = False, boot_check: bool = True,
               quiet: bool = False, backup_root: str = '') -> dict:
    started = time.perf_counter()
    started_at = dt.datetime.now().isoformat(timespec='seconds')
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')

    def say(msg):
        if not quiet:
            print(msg)

    if not os.path.exists(db_path):
        raise InitializationAborted(f'Database not found: {db_path}')

    # -- Phase 2 first: classify before touching anything ----------------
    say('[1/7] classifying tables ...')
    conn = read_only(db_path)
    try:
        classification = verify_classification(conn)
        before = row_counts(conn)
        targets = {t for t, m in classification['tables'].items()
                   if m['classification'] in cleared_classes()}
        if preserve_guests:
            targets.discard('guests')
        order, broken = deletion_order(conn, targets)
    finally:
        conn.close()
    say(f'      {len(classification["tables"])} tables, '
        f'{len(targets)} to clear, 0 unclassified')

    rows_to_remove = sum(before.get(t, 0) for t in targets)
    preserved_tables = len(classification['tables']) - len(targets)
    rows_preserved = sum(v for t, v in before.items() if t not in targets)

    if not confirm:
        say('')
        say('DRY RUN — nothing was changed. Re-run with --confirm to apply.')
        say(f'  would remove   {rows_to_remove} rows from {len(targets)} '
            f'tables')
        say(f'  would preserve {rows_preserved} rows in {preserved_tables} '
            f'tables')
        say(f'  would set business date to {business_date.isoformat()}')
        return {'result': 'DRY RUN', 'classification': classification,
                'row_counts_before': before, 'deletion_order': order,
                'would_remove_rows': rows_to_remove,
                'would_preserve_rows': rows_preserved}

    # -- Phase 1: safety --------------------------------------------------
    say('[2/7] backing up ...')
    backup = take_backup(db_path, stamp, backup_root)
    say(f'      {backup["path"]}')
    say(f'      integrity ok, row counts match, '
        f'{backup["manifest"]["total_rows"]} rows captured')

    # -- Phases 4 and 5 ---------------------------------------------------
    say(f'[3/7] clearing {len(order)} tables ...')
    removed = reset_and_reinitialize(db_path, order, business_date)
    say(f'      {sum(removed.values())} rows removed')
    say(f'[4/7] business date set to {business_date.isoformat()}, unlocked')

    # -- Phase 6 ----------------------------------------------------------
    say('[5/7] verifying ...')
    verification = verify_result(db_path, classification, before,
                                 business_date, boot_check, targets)
    for c in verification['checks']:
        say(f'      {"PASS" if c["passed"] else "FAIL"}  {c["check"]}'
            f'{"  — " + c["detail"] if c["detail"] else ""}')

    warnings = [{'table': t, 'rows': removed.get(t, 0), 'note': note}
                for t, note in sorted(CLEARED_WITH_WARNING.items())
                if t in removed]

    already = rows_to_remove == 0
    result = ('ALREADY INITIALIZED' if already and verification['passed']
              else 'SUCCESS' if verification['passed'] else 'VERIFICATION FAILED')

    payload = {
        'result': result,
        'target_is_default_production':
            os.path.abspath(db_path) == os.path.abspath(DEFAULT_DB),
        'started_at': started_at,
        'database': os.path.abspath(db_path),
        'business_date': business_date.isoformat(),
        'preserve_guests': preserve_guests,
        'backup': backup,
        'classification': classification,
        'deletion_order': order,
        'cycles_broken_at': broken,
        'rows_removed_by_table': removed,
        'row_counts_before': before,
        'verification': verification,
        'warnings': warnings,
        'counts': {
            'preserved_tables': preserved_tables,
            'cleared_tables': len(targets),
            'rows_removed': sum(removed.values()),
            'rows_preserved': rows_preserved,
        },
        'duration_seconds': round(time.perf_counter() - started, 2),
    }

    say('[6/7] writing report ...')
    report = render_report(payload)
    with open(os.path.join(backup['dir'], 'report.md'), 'w',
              encoding='utf-8') as fh:
        fh.write(report)
    with open(os.path.join(ROOT, 'PRODUCTION_INITIALIZATION_REPORT.md'), 'w',
              encoding='utf-8') as fh:
        fh.write(report)
    with open(os.path.join(backup['dir'], 'result.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(payload, fh, indent=1, default=str)
    say(f'      {backup["dir"]}')
    say(f'[7/7] {result}')

    if not verification['passed']:
        raise InitializationAborted(
            'Verification failed after the reset. The database has been '
            f'changed. Restore it from {backup["path"]} before using this '
            f'system.')
    return payload


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog='production_initialize',
        description='Preserve configuration, remove business activity, and '
                    'set the first production day.')
    p.add_argument('--db', default=DEFAULT_DB,
                   help='database to initialize (default: instance/pms.db)')
    p.add_argument('--confirm', action='store_true',
                   help='actually apply. Without this the tool is a dry run')
    p.add_argument('--dry-run', action='store_true',
                   help='explicit no-op, the default behaviour')
    p.add_argument('--business-date', default='',
                   help='ISO date for the first production day '
                        '(default: today)')
    p.add_argument('--preserve-guests', action='store_true',
                   help='keep the guests table for CRM continuity')
    p.add_argument('--no-boot-check', action='store_true',
                   help='skip booting the application against a copy')
    p.add_argument('--backup-dir', default='',
                   help='where to write the pre-run snapshot (default: '
                        '../db-backups/initialization). Point this '
                        'elsewhere when initializing a copy, so test runs '
                        'do not accumulate in the production backup store')
    p.add_argument('--quiet', action='store_true')
    args = p.parse_args(argv)

    if args.business_date:
        business_date = dt.date.fromisoformat(args.business_date)
    else:
        business_date = dt.date.today()

    confirm = args.confirm and not args.dry_run
    try:
        result = initialize(args.db, confirm, business_date,
                            preserve_guests=args.preserve_guests,
                            boot_check=not args.no_boot_check,
                            quiet=args.quiet, backup_root=args.backup_dir)
    except InitializationAborted as exc:
        print()
        print('ABORTED')
        print(str(exc))
        return 2
    return 0 if result.get('result') in ('SUCCESS', 'ALREADY INITIALIZED',
                                         'DRY RUN') else 1


if __name__ == '__main__':
    sys.exit(main())
