"""perf-pool: pooled PostgreSQL connections are reused, returned clean, never
leaked, and a full pool fails fast. Postgres tests use the isolated test DB."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import db


def _dsn():
    path = os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE')
    return Path(path).read_text(encoding='ascii').strip() if path else None


class FallbackTests(unittest.TestCase):
    def test_no_pool_without_postgres_or_when_switched_off(self):
        with mock.patch.dict(os.environ, {'DATABASE_URL': ''}):
            self.assertFalse(db.pool_enabled())
        with mock.patch.dict(os.environ, {'DATABASE_URL': 'postgresql://u@localhost/x', 'DHASHU_DB_POOL': '0'}):
            self.assertFalse(db.pool_enabled())
        with mock.patch.dict(os.environ, {'DATABASE_URL': 'postgresql://u@localhost/x', 'DHASHU_DB_POOL': '1'}):
            self.assertTrue(db.pool_enabled())

    def test_sqlite_acquire_release_opens_and_closes(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'p.db'
        with mock.patch.dict(os.environ, {'DATABASE_URL': ''}), \
                mock.patch.object(db, 'get_connection', lambda *a, **k: db.sqlite3.connect(path)):
            conn = db.acquire()
            conn.execute('SELECT 1')
            db.release(conn)
        with self.assertRaises(db.sqlite3.ProgrammingError):
            conn.execute('SELECT 1')   # really closed (no Windows file lock left)
        db.release(None)               # harmless

    def test_settings_are_clamped(self):
        with mock.patch.dict(os.environ, {'DHASHU_DB_POOL_MIN': '5', 'DHASHU_DB_POOL_MAX': '2', 'DHASHU_DB_POOL_TIMEOUT': '999'}):
            self.assertEqual(db.pool_settings(), {'min_size': 5, 'max_size': 5, 'timeout': 60.0})
        with mock.patch.dict(os.environ, {'DHASHU_DB_POOL_MIN': 'x', 'DHASHU_DB_POOL_MAX': '-3'}):
            settings = db.pool_settings()
        self.assertEqual((settings['min_size'], settings['max_size']), (1, 1))


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresPoolTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'DATABASE_URL': _dsn(), 'DHASHU_DB_POOL': '1', 'DHASHU_DB_POOL_MIN': '1',
                                           'DHASHU_DB_POOL_MAX': '3', 'DHASHU_DB_POOL_TIMEOUT': '1'})
        env.start()
        self.addCleanup(env.stop)
        db.close_pools()
        self.addCleanup(db.close_pools)

    def backend_pid(self, conn):
        return conn.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']

    def single_connection_pool(self):
        """Pool of exactly one connection: a borrow always gets the same physical one."""
        db.close_pools()
        patcher = mock.patch.dict(os.environ, {'DHASHU_DB_POOL_MIN': '1', 'DHASHU_DB_POOL_MAX': '1'})
        patcher.start(); self.addCleanup(patcher.stop)
        db.get_pool().wait(timeout=5)

    def settled(self):
        """Stats once returns finished (the pool resets returned connections)."""
        import time
        pool = db.get_pool()
        deadline = time.monotonic() + 3
        while True:
            stats = pool.get_stats()
            if stats['pool_available'] == stats['pool_size'] or time.monotonic() > deadline:
                return stats
            time.sleep(0.02)

    def test_connections_are_reused_not_reopened(self):
        db.get_pool().wait(timeout=5)
        for _ in range(3):                                      # warm up
            conn = db.acquire(); conn.execute('SELECT 1'); conn.commit(); db.release(conn)
        opened = self.settled().get('connections_num', 0)
        pids = set()
        for _ in range(30):
            conn = db.acquire(); pids.add(self.backend_pid(conn)); conn.commit(); db.release(conn)
        # 30 borrows never open more than the cap (3) in total: connections are reused.
        # (The pool may grow up to the cap while returned connections are being reset.)
        self.assertLessEqual(self.settled().get('connections_num', 0), 3)
        self.assertGreaterEqual(opened, 1)
        self.assertLessEqual(len(pids), 3)                      # served by the few pooled ones

    def test_no_leak_after_many_borrows(self):
        for _ in range(50):
            conn = db.acquire()
            conn.execute('SELECT 1')
            db.release(conn)
        stats = self.settled()
        self.assertLessEqual(stats['pool_size'], 3)
        self.assertEqual(stats['pool_available'], stats['pool_size'])   # everything came back
        self.assertEqual(stats.get('requests_waiting', 0), 0)

    def test_open_transaction_is_rolled_back_on_return(self):
        self.single_connection_pool()
        conn = db.acquire()
        pid = self.backend_pid(conn)
        conn.execute('CREATE TEMP TABLE IF NOT EXISTS leak_probe (v int)')
        conn.execute('INSERT INTO leak_probe VALUES (1)')       # never committed
        db.release(conn)
        conn = db.acquire()
        self.assertEqual(self.backend_pid(conn), pid)          # same physical connection
        exists = conn.execute("SELECT to_regclass('pg_temp.leak_probe') AS t").fetchone()['t']
        self.assertIsNone(exists)                              # the uncommitted work is gone
        conn.commit(); db.release(conn)

    def test_committed_session_settings_are_reset_on_return(self):
        # A committed SET survives a rollback; only the pool's RESET ALL clears it.
        self.single_connection_pool()
        conn = db.acquire()
        pid = self.backend_pid(conn)
        conn.execute("SET statement_timeout = '1234ms'")
        conn.execute("SET search_path = pg_catalog")
        conn.commit()
        db.release(conn)
        conn = db.acquire()
        self.assertEqual(self.backend_pid(conn), pid)
        self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'], '0')
        self.assertNotEqual(conn.execute('SHOW search_path').fetchone()['search_path'], 'pg_catalog')
        conn.commit(); db.release(conn)

    def test_full_pool_fails_fast_instead_of_hanging(self):
        from psycopg_pool import PoolTimeout
        held = [db.acquire() for _ in range(3)]
        try:
            import time
            start = time.monotonic()
            with self.assertRaises(PoolTimeout):
                db.acquire()
            self.assertLess(time.monotonic() - start, 3)
        finally:
            for conn in held:
                db.release(conn)
        conn = db.acquire(); db.release(conn)                  # usable again afterwards

    def test_broken_connection_is_discarded(self):
        self.single_connection_pool()
        conn = db.acquire()
        pid = self.backend_pid(conn); conn.commit()
        killer = db.get_connection()
        killer.execute('SELECT pg_terminate_backend(%s)', (pid,)); killer.commit(); killer.close()
        db.release(conn)
        conn = db.acquire()
        self.assertNotEqual(self.backend_pid(conn), pid)       # checked on checkout, replaced
        conn.commit(); db.release(conn)

    def test_concurrent_borrowers_never_share_a_connection(self):
        seen, lock, errors = [], threading.Lock(), []

        def work():
            try:
                for _ in range(10):
                    conn = db.acquire()
                    try:
                        with lock:
                            self.assertNotIn(id(conn), [s for s in seen])
                            seen.append(id(conn))
                        conn.execute('SELECT pg_sleep(0.005)')
                        with lock:
                            seen.remove(id(conn))
                        conn.commit()
                    finally:
                        db.release(conn)
            except Exception as exc:   # noqa: BLE001
                errors.append(exc)
        threads = [threading.Thread(target=work) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors, [])
        stats = self.settled()
        self.assertEqual(stats['pool_available'], stats['pool_size'])


if __name__ == '__main__':
    unittest.main()
