"""mon-health on real PostgreSQL: /api/v1/ready must answer 200 when the database is up.
(The SQLite tests could not catch a PostgreSQL-only syntax error in the readiness query.)"""
import os
import unittest
from unittest import mock

import db
import health_checks


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL configured')
class HealthPostgresTests(unittest.TestCase):
    def connect(self):
        import psycopg
        from psycopg.rows import dict_row
        with open(os.environ['AUTH_TEST_POSTGRES_DSN_FILE'], encoding='ascii') as handle:
            return psycopg.connect(handle.read().strip(), row_factory=dict_row)

    def test_database_ready_on_postgres_and_timeout_stays_transaction_local(self):
        conn = self.connect()
        self.addCleanup(conn.close)
        before = conn.execute('SHOW statement_timeout').fetchone()['statement_timeout']
        conn.rollback()
        with mock.patch.object(db, 'acquire', return_value=conn), mock.patch.object(db, 'release'), \
                self.assertNoLogs('dhashu.health', level='WARNING'):
            self.assertTrue(health_checks.database_ready(timeout_ms=1500))
        self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'], before)


if __name__ == '__main__':
    unittest.main()
