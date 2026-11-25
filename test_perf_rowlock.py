"""perf-rowlock: job claims skip rows another worker holds; one active lock-in per
member is enforced by the database; row locks never block unrelated members."""
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

import bgv_app
import db
import test_auth_postgres as pg


class LockInIndexSqliteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.conn = db.get_connection(Path(tmp.name) / 'l.db'); self.addCleanup(self.conn.close)
        db.init_db(self.conn)
        for uid in ('a', 'b', 'c'):
            self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (?,?,?)', (uid, 'dating', 'verified'))
        self.conn.commit()

    def lockin(self, lid, a, b, status='active'):
        self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (?,?,?,1,?,?)',
                          (lid, a, b, 'Mon:12', status))
        self.conn.commit()

    def test_second_active_lockin_in_the_same_position_is_rejected(self):
        self.lockin('l1', 'a', 'b')
        with self.assertRaises(sqlite3.IntegrityError):
            self.lockin('l2', 'a', 'c')
        self.conn.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.lockin('l3', 'c', 'b')
        self.conn.rollback()
        self.lockin('l4', 'a', 'c', status='released')    # history is fine
        names = {r[1] for r in self.conn.execute("PRAGMA index_list('LockIn')")}
        self.assertTrue({'uq_lockin_active_user_a', 'uq_lockin_active_user_b'} <= names)


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresClaimTests(unittest.TestCase):
    connect = pg.PostgresAuthenticationTests.connect
    cleanup = pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        for i in range(3):
            self.conn.execute('''INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at)
                                 VALUES (%s,'owner','current_employer','preproduction','queued','x',%s,%s)''',
                              (f'job-{i}', f'2026-11-25T12:00:0{i}+00:00', f'2026-11-25T12:00:0{i}+00:00'))

    def test_two_workers_never_claim_the_same_job_and_never_wait(self):
        first = self.connect(); second = self.connect()
        try:
            with first.transaction():
                claimed = bgv_app.claim_candidates(first, 'preproduction')
                self.assertEqual([r['id'] for r in claimed], ['job-0', 'job-1', 'job-2'])
                result = {}

                def other_worker():
                    start = time.monotonic()
                    with second.transaction():
                        result['rows'] = bgv_app.claim_candidates(second, 'preproduction')
                    result['seconds'] = time.monotonic() - start
                t = threading.Thread(target=other_worker); t.start(); t.join(timeout=5)
                self.assertFalse(t.is_alive(), 'second worker waited on the first worker\'s claim')
                self.assertEqual(result['rows'], [])            # skipped, not shared
                self.assertLess(result['seconds'], 2)
                first.execute('UPDATE "BgvRequest" SET state=%s WHERE id=%s', ('processing', 'job-0'))
            with second.transaction():                          # after commit: job-0 is gone for good
                ids = [r['id'] for r in bgv_app.claim_candidates(second, 'preproduction')]
            self.assertEqual(ids, ['job-1', 'job-2'])
        finally:
            first.close(); second.close()

    def test_postgres_rejects_a_second_active_lockin_for_a_member(self):
        import psycopg
        for uid in ('partner', 'stranger'):
            self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)', (uid, 'dating', 'verified'))
        self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,1,%s,%s)',
                          ('l1', 'owner', 'partner', 'Mon:12', 'active'))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,1,%s,%s)',
                              ('l2', 'owner', 'stranger', 'Mon:12', 'active'))


if __name__ == '__main__':
    unittest.main()
