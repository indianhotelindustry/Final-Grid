"""
Materialisation — turning a declaration into a database file.

The build, start to finish:

  1. **Copy** production through the SQLite backup API, ``mode=ro`` at the
     source. The dataset inherits the real schema and the hotel's real
     master configuration.
  2. **Strip** every transactional table in FK-safe order, children
     first, then guests.
  3. **Insert** the declared rows in declaration order.
  4. **Set** the business date the narrative declares.
  5. **Fingerprint** the result, and verify production never moved.

Why the copy rather than a fresh schema
---------------------------------------
See ``schema.py``. In one line: a synthetic schema stops being the
production schema at the next migration, and a dataset that no longer
matches production is worse than no dataset, because it reports passes
over rows that could not exist.

Determinism
-----------
A dataset must build byte-identically every time, or its content hash is
meaningless and its certificate certifies nothing. Two things would break
that and both are handled: SQLite rowids are made explicit by declaring
``id`` in the rows, and nothing in a build reads the clock — every
timestamp is declared, never stamped. ``build()`` therefore takes no
current time and a dataset that wants "created 3 days before arrival"
declares the literal datetime.

The content hash covers the transactional layer and the business date. It
deliberately does **not** cover the preserved master tables: those come
from production and change when the hotel reconfigures itself, which must
not invalidate every dataset certificate at once. What it means is
therefore precise — *this narrative, realised exactly this way* — and a
master-data change is caught by re-running the expectations rather than
by a hash mismatch nobody can interpret.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time

from verification.config import PRODUCTION_DB, PVF_WORK_DIR
from verification.dbcopy import make_copy, production_fingerprint
from verification.datasets import schema
from verification.datasets.model import Materialisation

#: Where materialised datasets live. Separate from D5's arena so a stray
#: file is obviously a dataset rather than a fault's copy.
DATASET_DIR = os.path.join(PVF_WORK_DIR, 'datasets')


class MaterialisationError(RuntimeError):
    """The dataset could not be built. Never swallowed.

    A dataset that half-built would be evaluated as though it were the
    narrative it claims to be, and every expectation measured against it
    would be measuring something nobody declared.
    """


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = OFF')   # strip order is declared
    return conn


def strip(conn: sqlite3.Connection) -> int:
    """Delete every transactional row. Returns rows removed."""
    removed = 0
    for table in schema.strip_order():
        try:
            cursor = conn.execute(f'DELETE FROM "{table}"')
        except sqlite3.OperationalError as exc:
            if 'no such table' in str(exc):
                continue
            raise
        removed += max(cursor.rowcount, 0)
    # Reset AUTOINCREMENT counters so declared ids are the only ids and
    # two builds cannot differ by where the sequence happened to be.
    try:
        conn.execute('DELETE FROM sqlite_sequence')
    except sqlite3.OperationalError:
        pass                                    # no AUTOINCREMENT tables
    return removed


def insert_rows(conn: sqlite3.Connection, rows: tuple) -> tuple:
    """Apply declared rows. Returns ``(inserted, tables_touched)``.

    Each entry is ``(table, columns, values_tuples)``. A missing NOT NULL
    column is reported by name before the insert is attempted, rather
    than surfacing as an opaque IntegrityError — the failure that cost
    D5 a commissioning run.
    """
    inserted = 0
    touched = []
    for table, columns, values in rows:
        required = set(schema.required_columns(conn, table))
        missing = sorted(required - set(columns))
        if missing:
            raise MaterialisationError(
                f'{table}: the declared row omits NOT NULL column(s) with no '
                f'default: {", ".join(missing)}. The insert would raise '
                f'IntegrityError and the dataset would never be built, so '
                f'every expectation measured against it would be measuring '
                f'an empty table.')
        unknown = sorted(set(columns) - set(schema.table_columns(conn, table)))
        if unknown:
            raise MaterialisationError(
                f'{table}: declared column(s) that do not exist on this '
                f'schema: {", ".join(unknown)}. The schema has moved and the '
                f'dataset has not.')
        placeholders = ', '.join('?' for _ in columns)
        column_list = ', '.join(f'"{c}"' for c in columns)
        statement = (f'INSERT INTO "{table}" ({column_list}) '
                     f'VALUES ({placeholders})')
        for value_row in values:
            if len(value_row) != len(columns):
                raise MaterialisationError(
                    f'{table}: a declared row has {len(value_row)} values for '
                    f'{len(columns)} columns')
            try:
                conn.execute(statement, value_row)
            except sqlite3.Error as exc:
                raise MaterialisationError(
                    f'{table}: {type(exc).__name__}: {exc}\n'
                    f'  columns: {columns}\n  values : {value_row}') from None
            inserted += 1
        touched.append(table)
    return inserted, tuple(touched)


def set_business_date(conn: sqlite3.Connection, business_date: str) -> None:
    """Point the singleton business date at the narrative's date.

    ``business_date`` is a preserved master row, so it survives the strip
    carrying production's date. A dataset evaluated under the wrong
    business date would have every date-scoped invariant looking at the
    wrong day and reporting VACUOUS — which is exactly the result this
    deliverable exists to eliminate.
    """
    row = conn.execute('SELECT id FROM business_date ORDER BY id '
                       'LIMIT 1').fetchone()
    if row is None:
        conn.execute('INSERT INTO business_date (id, "current_date") '
                     'VALUES (1, ?)', (business_date,))
        return
    conn.execute('UPDATE business_date SET "current_date" = ? WHERE id = ?',
                 (business_date, row[0]))


def content_hash(conn: sqlite3.Connection) -> str:
    """A deterministic digest of the transactional layer.

    Covers every transactional table's full contents in a stable order,
    plus the business date. Master tables are excluded on purpose (see
    the module docstring).
    """
    digest = hashlib.sha256()
    for table in sorted(schema.TRANSACTIONAL_TABLES_IN_DELETE_ORDER
                        + schema.GUEST_TABLES):
        try:
            columns = schema.table_columns(conn, table)
        except sqlite3.Error:
            continue
        if not columns:
            continue
        column_list = ', '.join(f'"{c}"' for c in columns)
        try:
            rows = conn.execute(
                f'SELECT {column_list} FROM "{table}" '
                f'ORDER BY {column_list}').fetchall()
        except sqlite3.Error:
            continue
        digest.update(f'\n##{table}\n'.encode())
        for row in rows:
            digest.update(('|'.join('' if v is None else str(v)
                                    for v in row) + '\n').encode())
    date_row = conn.execute('SELECT "current_date" FROM business_date '
                            'ORDER BY id LIMIT 1').fetchone()
    digest.update(f'\n##business_date\n{date_row[0] if date_row else ""}'
                  .encode())
    return digest.hexdigest()


def build(dataset, source: str = PRODUCTION_DB,
          slot: str = '') -> Materialisation:
    """Materialise *dataset* into its own database file."""
    started = time.perf_counter()
    result = Materialisation()

    if dataset.not_materialisable_reason:
        result.error = dataset.not_materialisable_reason
        return result

    production_before, _size = production_fingerprint(source)
    os.makedirs(DATASET_DIR, exist_ok=True)
    safe = ''.join(c if c.isalnum() or c in '._-' else '_'
                   for c in f'{dataset.dataset_id}_{dataset.version}{slot}')
    # make_copy removes any stale copy itself and honours PVF_WORK_SUFFIX,
    # so the destination is whatever it reports rather than a path
    # recomputed here — which would diverge the moment a probe sets a
    # suffix.
    handle = make_copy(name=os.path.join('datasets', f'{safe}.db'),
                       source=source)
    result.db_path = handle.copy_path

    conn = _connect(result.db_path)
    try:
        schema.assert_classified(result.db_path)
        result.rows_removed = strip(conn)
        result.rows_inserted, result.tables_touched = insert_rows(
            conn, dataset.rows)
        set_business_date(conn, dataset.business_date)
        conn.commit()
        result.business_date = dataset.business_date
        result.content_hash = content_hash(conn)
    except Exception as exc:                                 # noqa: BLE001
        result.error = f'{type(exc).__name__}: {exc}'
    finally:
        conn.close()

    production_after, _size = production_fingerprint(source)
    result.production_unchanged = production_after == production_before
    if not result.production_unchanged:
        result.error = ('PRODUCTION CHANGED while materialising '
                        f'{dataset.key}. Every result from this build is '
                        f'void.')
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


def discard(materialisation: Materialisation) -> bool:
    """Delete a materialised dataset and verify it is gone."""
    path = materialisation.db_path
    if not path:
        return True
    for suffix in ('', '-wal', '-shm', '-journal'):
        target = path + suffix
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                return False
    return not os.path.exists(path)


def perturb(db_path: str, statements: tuple) -> int:
    """Apply a commissioning perturbation. Returns rows changed.

    Refuses a zero-change perturbation for the same reason D5 refuses a
    zero-change injection: a perturbation that altered nothing would show
    the dataset's expectations "surviving" it, and the dataset would be
    credited with a discrimination it never demonstrated.
    """
    conn = _connect(db_path)
    try:
        changed = 0
        for statement in statements:
            cursor = conn.execute(statement)
            changed += max(cursor.rowcount, 0)
        conn.commit()
    finally:
        conn.close()
    if changed == 0:
        raise MaterialisationError(
            'the declared perturbation affected 0 rows, so the dataset was '
            'never actually perturbed and its expectations cannot be shown '
            'to discriminate')
    return changed
