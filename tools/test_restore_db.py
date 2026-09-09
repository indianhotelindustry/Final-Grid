"""Focused tests for tools/restore_db.py.

Standard-library ``unittest`` only: the repository deliberately has no test
framework yet (Phase 6). Every test works on throw-away SQLite files created
in a temporary directory. The production database is never opened; the only
reference to it is the path string used to prove the tool refuses it.

Run::

    python tools/test_restore_db.py
    python -m unittest tools.test_restore_db      # from the repository root
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import restore_db as rdb  # noqa: E402


def _make_db(path: str, rows: int = 3) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute('PRAGMA journal_mode=DELETE')
        for t in rdb.REQUIRED_TABLES:
            if t == 'reservations':
                conn.execute('CREATE TABLE reservations (id INTEGER PRIMARY KEY, invoice_number TEXT)')
            elif t == 'payments':
                conn.execute('CREATE TABLE payments (id INTEGER PRIMARY KEY, '
                             'reservation_id INTEGER NOT NULL REFERENCES reservations(id), '
                             'folio_id INTEGER REFERENCES folios(id), amount NUMERIC)')
            elif t == 'folios':
                conn.execute('CREATE TABLE folios (id INTEGER PRIMARY KEY, '
                             'reservation_id INTEGER NOT NULL REFERENCES reservations(id))')
            else:
                conn.execute(f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, v TEXT)')
        for i in range(1, rows + 1):
            conn.execute('INSERT INTO reservations VALUES (?, ?)', (i, f'INV-{i:06d}' if i % 2 else None))
            conn.execute('INSERT INTO folios VALUES (?, ?)', (i, i))
            conn.execute('INSERT INTO payments VALUES (?, ?, ?, ?)', (i, i, i, 100.0 * i))
            conn.execute('INSERT INTO audit_logs VALUES (?, ?)', (i, f'a{i}'))
        conn.commit()
    finally:
        conn.close()


def _write_manifest(db_path: str, **overrides) -> str:
    conn = sqlite3.connect('file:' + db_path.replace('\\', '/') + '?mode=ro', uri=True)
    try:
        counts = rdb.row_counts(conn)
    finally:
        conn.close()
    m = {'snapshot_sha256': rdb.sha256_file(db_path), 'source_sha256_before': 'x',
         'method': 'sqlite-backup-api', 'created_at': 't', 'row_counts': counts}
    m.update(overrides)
    p = db_path + '.manifest.json'
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(m, fh)
    return p


class RestoreDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='restore_test_')
        self.src = os.path.join(self.tmp, 'backup.db')
        _make_db(self.src)
        self.dest = os.path.join(self.tmp, 'out', 'restored.db')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- success paths ------------------------------------------------------

    def test_successful_isolated_restore(self):
        res = rdb.restore(self.src, self.dest, quiet=True)
        self.assertEqual(res['verification_status'], 'PASS')
        self.assertTrue(os.path.isfile(self.dest))
        self.assertEqual(res['restored_sha256'], rdb.sha256_file(self.dest))
        self.assertTrue(res['checks']['restored_integrity_check']['ok'])
        self.assertTrue(res['checks']['restored_foreign_key_check']['ok'])
        self.assertTrue(res['checks']['required_tables_present']['ok'])
        self.assertTrue(res['checks']['schema_sql_equal']['ok'])
        self.assertTrue(res['checks']['row_counts_equal']['ok'])
        self.assertTrue(res['checks']['content_digests_equal_all_tables']['ok'])
        self.assertTrue(res['checks']['body_identical_beyond_header']['ok'])
        self.assertEqual(res['byte_comparison']['diff_bytes_beyond_header'], 0)
        self.assertTrue(res['byte_comparison']['size_equal'])
        # whole-file hash equality is informational: the backup API may rewrite header fields
        self.assertIn(res['checks']['whole_file_sha256_identical']['ok'], (None,))
        self.assertEqual(res['row_counts']['key_tables']['payments'], {'source': 3, 'restored': 3})
        self.assertEqual(res['row_counts']['invoices']['restored'], 2)
        self.assertFalse(res['production_touched'])

    def test_manifest_is_generated_and_complete(self):
        ev = os.path.join(self.tmp, 'evidence')
        res = rdb.restore(self.src, self.dest, run_id='unit-run', evidence_dir=ev, quiet=True)
        beside = self.dest + '.restore_manifest.json'
        self.assertTrue(os.path.isfile(beside))
        self.assertTrue(os.path.isfile(os.path.join(ev, 'restore_manifest.json')))
        with open(beside, encoding='utf-8') as fh:
            m = json.load(fh)
        for k in ('run_id', 'started_at', 'source_path', 'source_sha256', 'restored_path',
                  'restored_sha256', 'checks', 'row_counts', 'verification_status', 'failures'):
            self.assertIn(k, m)
        self.assertEqual(m['run_id'], 'unit-run')
        self.assertEqual(m['verification_status'], 'PASS')
        self.assertNotIn('SECRET_KEY', json.dumps(m))

    def test_valid_backup_with_matching_manifest(self):
        _write_manifest(self.src)
        res = rdb.restore(self.src, self.dest, quiet=True)
        self.assertTrue(res['checks']['source_matches_backup_manifest']['ok'])
        self.assertTrue(res['checks']['row_counts_match_backup_manifest']['ok'])

    def test_overwrite_isolated_destination_only_with_flag(self):
        rdb.restore(self.src, self.dest, quiet=True)
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(self.src, self.dest, quiet=True)
        res = rdb.restore(self.src, self.dest, overwrite_dest=True, quiet=True)
        self.assertEqual(res['verification_status'], 'PASS')

    # -- refusals: nothing written -----------------------------------------

    def test_missing_backup_is_refused(self):
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(os.path.join(self.tmp, 'nope.db'), self.dest, quiet=True)
        self.assertFalse(os.path.exists(self.dest))

    def test_empty_backup_is_refused(self):
        empty = os.path.join(self.tmp, 'empty.db')
        open(empty, 'wb').close()
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(empty, self.dest, quiet=True)

    def test_production_destination_is_refused(self):
        for bad in (rdb.PRODUCTION_DB,
                    os.path.join(rdb.INSTANCE_DIR, 'anything.db'),
                    os.path.join(rdb.INSTANCE_DIR, 'sub', 'x.db')):
            with self.assertRaises(rdb.RestoreRefused, msg=bad):
                rdb.restore(self.src, bad, quiet=True)
        self.assertTrue(rdb.is_production_path(rdb.PRODUCTION_DB.upper()))

    def test_production_as_source_is_refused(self):
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(rdb.PRODUCTION_DB, self.dest, quiet=True)

    def test_same_file_and_directory_destination_refused(self):
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(self.src, self.src, quiet=True)
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(self.src, self.tmp, quiet=True)

    def test_non_sqlite_source_fails_before_restore(self):
        junk = os.path.join(self.tmp, 'junk.db')
        with open(junk, 'wb') as fh:
            fh.write(b'not a database at all' * 10)
        with self.assertRaises(rdb.RestoreFailed):
            rdb.restore(junk, self.dest, quiet=True)
        self.assertFalse(os.path.exists(self.dest))

    # -- verification failures --------------------------------------------

    def test_manifest_hash_mismatch_fails_before_restore(self):
        _write_manifest(self.src, snapshot_sha256='0' * 64)
        with self.assertRaises(rdb.RestoreFailed):
            rdb.restore(self.src, self.dest, quiet=True)
        self.assertFalse(os.path.exists(self.dest))
        with open(self.dest + '.restore_manifest.json', encoding='utf-8') as fh:
            m = json.load(fh)
        self.assertEqual(m['verification_status'], 'FAIL')
        self.assertFalse(m['checks']['source_matches_backup_manifest']['ok'])

    def test_manifest_row_count_mismatch_is_detected(self):
        p = _write_manifest(self.src)
        with open(p, encoding='utf-8') as fh:
            m = json.load(fh)
        m['row_counts']['payments'] = 99
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(m, fh)
        with self.assertRaises(rdb.RestoreFailed):
            rdb.restore(self.src, self.dest, quiet=True)
        with open(self.dest + '.restore_manifest.json', encoding='utf-8') as fh:
            out = json.load(fh)
        self.assertFalse(out['checks']['row_counts_match_backup_manifest']['ok'])

    def test_corrupted_source_fails_integrity_before_restore(self):
        # keep the file header intact, destroy the header of page 2 (a b-tree
        # page). Corruption inside *unused* page space is invisible to
        # integrity_check by design, so the damage must hit structure.
        with open(self.src, 'r+b') as fh:
            fh.seek(4096)
            fh.write(b'\xff' * 64)
        with self.assertRaises(rdb.RestoreFailed):
            rdb.restore(self.src, self.dest, quiet=True)
        self.assertFalse(os.path.exists(self.dest))
        with open(self.dest + '.restore_manifest.json', encoding='utf-8') as fh:
            out = json.load(fh)
        self.assertFalse(out['checks']['source_integrity_check']['ok'])

    def test_foreign_key_violation_in_backup_is_reported(self):
        conn = sqlite3.connect(self.src)
        conn.execute('INSERT INTO payments VALUES (42, 999, NULL, 1.0)')  # orphan reservation
        conn.commit(); conn.close()
        with self.assertRaises(rdb.RestoreFailed):
            rdb.restore(self.src, self.dest, quiet=True)
        with open(self.dest + '.restore_manifest.json', encoding='utf-8') as fh:
            out = json.load(fh)
        self.assertFalse(out['checks']['restored_foreign_key_check']['ok'])
        self.assertTrue(out['foreign_key_check_violations'])

    def test_missing_required_table_is_reported(self):
        conn = sqlite3.connect(self.src)
        conn.execute('DROP TABLE audit_logs'); conn.commit(); conn.close()
        with self.assertRaises(rdb.RestoreFailed):
            rdb.restore(self.src, self.dest, quiet=True)
        with open(self.dest + '.restore_manifest.json', encoding='utf-8') as fh:
            out = json.load(fh)
        self.assertIn('audit_logs', out['checks']['required_tables_present']['detail'])

    def test_content_digest_detects_row_difference(self):
        a = os.path.join(self.tmp, 'a.db'); b = os.path.join(self.tmp, 'b.db')
        _make_db(a); _make_db(b)
        conn = sqlite3.connect(b)
        conn.execute('UPDATE payments SET amount = amount + 1 WHERE id = 1'); conn.commit(); conn.close()
        ca = sqlite3.connect(a); cb = sqlite3.connect(b)
        try:
            self.assertEqual(rdb.row_counts(ca)['payments'], rdb.row_counts(cb)['payments'])
            self.assertNotEqual(rdb.content_digest(ca, 'payments'), rdb.content_digest(cb, 'payments'))
        finally:
            ca.close(); cb.close()

    # -- encrypted application backups -------------------------------------

    def test_encrypted_backup_roundtrip(self):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest('cryptography not installed')
        os.environ['PII_ENCRYPTION_KEY'] = 'unit-test-key-material-not-a-secret'
        try:
            fernet = rdb._derive_fernet()
            enc = self.src + '.enc'
            with open(self.src, 'rb') as fh, open(enc, 'wb') as out:
                out.write(fernet.encrypt(fh.read()))
            res = rdb.restore(enc, self.dest, quiet=True)
            self.assertEqual(res['verification_status'], 'PASS')
            self.assertTrue(res['source_encrypted'])
            self.assertEqual(res['source_sha256'], rdb.sha256_file(self.src))
            self.assertTrue(res['checks']['body_identical_beyond_header']['ok'])
            self.assertNotIn('unit-test-key-material', json.dumps(res))
        finally:
            os.environ.pop('PII_ENCRYPTION_KEY', None)

    def test_encrypted_backup_without_key_is_refused(self):
        for k in ('PII_ENCRYPTION_KEY', 'SECRET_KEY'):
            os.environ.pop(k, None)
        enc = self.src + '.enc'
        shutil.copyfile(self.src, enc)
        with self.assertRaises(rdb.RestoreRefused):
            rdb.restore(enc, self.dest, quiet=True)

    # -- CLI -----------------------------------------------------------------

    def test_cli_exit_codes(self):
        self.assertEqual(rdb.main(['--source', self.src, '--dest', self.dest, '--quiet']), 0)
        self.assertEqual(rdb.main(['--source', self.src, '--dest', self.dest, '--quiet']), 2)  # exists
        self.assertEqual(rdb.main(['--source', self.src, '--dest', rdb.PRODUCTION_DB, '--quiet']), 2)
        _write_manifest(self.src, snapshot_sha256='1' * 64)
        d2 = os.path.join(self.tmp, 'out2.db')
        self.assertEqual(rdb.main(['--source', self.src, '--dest', d2, '--quiet']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
