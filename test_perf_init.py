"""perf-init: schema DDL runs once per process per database, never per request."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import db
import service_entrypoint
from test_segment_efg_routes import RouteTestCase


def _fresh_ready():
    return mock.patch.object(db, '_SCHEMA_READY', set())


class RequestPathTests(RouteTestCase):
    def traced(self):
        """Patch get_connection so every request connection records its SQL."""
        statements, real = [], db.get_connection

        def connect(*args, **kwargs):
            conn = real(*args, **kwargs)
            conn.set_trace_callback(statements.append)
            return conn
        patcher = mock.patch.object(db, 'get_connection', connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        return statements

    def test_a_normal_request_runs_no_create_table(self):
        self.make_user('owner')
        with _fresh_ready(), mock.patch.dict(os.environ, {'DHASHU_SCHEMA_INIT': 'once'}):
            statements = self.traced()
            self.assertEqual(self.client.get('/pool').status_code, 200)   # first use of this DB
            self.assertTrue(any('CREATE TABLE' in s.upper() for s in statements))
            statements.clear()
            for _ in range(3):
                self.assertEqual(self.client.get('/pool').status_code, 200)
            ddl = [s for s in statements if s.lstrip().upper().startswith(('CREATE ', 'ALTER ', 'DROP '))]
            self.assertEqual(ddl, [])
            self.assertTrue(statements)  # the requests did use the database

    def test_legacy_per_request_mode_still_available(self):
        with _fresh_ready(), mock.patch.dict(os.environ, {'DHASHU_SCHEMA_INIT': 'per_request'}):
            statements = self.traced()
            self.client.get('/pool'); self.client.get('/pool')
        self.assertGreaterEqual(sum('CREATE TABLE' in s.upper() for s in statements), 2)


class EnsureSchemaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def connect(self, name):
        conn = db.get_connection(self.dir / name)
        self.addCleanup(conn.close)
        return conn

    def test_once_per_database_and_each_new_database_is_initialised(self):
        with _fresh_ready(), mock.patch.dict(os.environ, {'DHASHU_SCHEMA_INIT': 'once'}):
            a1, a2, b = self.connect('a.db'), self.connect('a.db'), self.connect('b.db')
            self.assertTrue(db.ensure_schema(a1))
            self.assertFalse(db.ensure_schema(a2))       # same database, other connection
            self.assertTrue(db.ensure_schema(b))         # different database
            self.assertFalse(db.ensure_schema(b))
            for conn in (a2, b):                         # schema really exists
                self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE name='User'").fetchone())

    def test_startup_mode_never_runs_ddl_from_requests(self):
        with _fresh_ready(), mock.patch.dict(os.environ, {'DHASHU_SCHEMA_INIT': 'startup'}), \
                mock.patch.object(db, 'init_db') as init:
            self.assertFalse(db.ensure_schema(self.connect('s.db')))
        init.assert_not_called()

    def test_unknown_mode_falls_back_to_once(self):
        with mock.patch.dict(os.environ, {'DHASHU_SCHEMA_INIT': 'sometimes'}):
            self.assertEqual(db.schema_init_mode(), 'once')

    def test_concurrent_first_use_initialises_exactly_once(self):
        calls = []

        def slow_init(conn, schema_path=None):
            calls.append(1)
            time.sleep(0.05)
        conn = self.connect('c.db')
        with _fresh_ready(), mock.patch.dict(os.environ, {'DHASHU_SCHEMA_INIT': 'once'}), \
                mock.patch.object(db, 'init_db', slow_init), \
                mock.patch.object(db, '_schema_key', return_value=('sqlite', 'shared')):
            threads = [threading.Thread(target=db.ensure_schema, args=(conn,)) for _ in range(8)]
            for t in threads: t.start()
            for t in threads: t.join()
        self.assertEqual(len(calls), 1)


class EntrypointTests(unittest.TestCase):
    def test_web_start_initialises_schema_unless_disabled(self):
        with mock.patch.object(db, 'get_connection') as connect, mock.patch.object(db, 'init_db') as init:
            with mock.patch.dict(os.environ, {'DHASHU_INIT_DB_ON_START': '1'}):
                self.assertTrue(service_entrypoint.init_schema())
            init.assert_called_once()
            connect.return_value.close.assert_called_once()
            init.reset_mock()
            with mock.patch.dict(os.environ, {'DHASHU_INIT_DB_ON_START': '0'}):
                self.assertFalse(service_entrypoint.init_schema())
            init.assert_not_called()


if __name__ == '__main__':
    unittest.main()
