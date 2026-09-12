"""Optional PostgreSQL integration; runs only against an explicit localhost test DSN file."""
import concurrent.futures
import os
from pathlib import Path
import unittest
import uuid

import auth_sessions as sessions
import db


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresAuthenticationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
        self.psycopg, self.sql, self.rows = psycopg, sql, dict_row
        self.dsn = Path(os.environ['AUTH_TEST_POSTGRES_DSN_FILE']).read_text().strip()
        if conninfo_to_dict(self.dsn).get('host') != '127.0.0.1':
            raise RuntimeError('Authentication integration tests require a localhost-only test database.')
        self.schema = 'auth_test_' + uuid.uuid4().hex
        self.conn = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)
        self.conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.cleanup)
        self.conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
        db.init_db(self.conn)
        self.conn.execute('INSERT INTO "User" (id, journey_state) VALUES (%s, %s)', ('owner', 'dating'))
        self.conn.execute('INSERT INTO "Account" (id, user_id, email, created_at, auth_enabled) VALUES (%s,%s,%s,%s,1)',
                          ('account-owner', 'owner', 'owner@example.test', 'test'))

    def cleanup(self):
        try:
            self.conn.rollback()
            self.conn.execute(self.sql.SQL('DROP SCHEMA {} CASCADE').format(self.sql.Identifier(self.schema)))
        finally:
            self.conn.close()

    def connect(self):
        conn = self.psycopg.connect(self.dsn, row_factory=self.rows)
        conn.execute(self.sql.SQL('SET search_path TO {}').format(self.sql.Identifier(self.schema)))
        conn.commit()
        return conn

    def test_sessions_refresh_replay_and_revocation(self):
        tokens = sessions.issue(self.conn, 'owner')
        self.assertEqual(sessions.authenticate(self.conn, tokens['access_token'])['user_id'], 'owner')
        refreshed = sessions.refresh(self.conn, tokens['refresh_token'])
        self.assertIsNotNone(refreshed)
        self.assertIsNone(sessions.authenticate(self.conn, tokens['access_token']))
        self.assertIsNone(sessions.refresh(self.conn, tokens['refresh_token']))
        self.assertIsNone(sessions.authenticate(self.conn, refreshed['access_token']))
        second = sessions.issue(self.conn, 'owner')
        sessions.revoke(self.conn, second['session_id'], 'owner', True)
        self.assertIsNone(sessions.authenticate(self.conn, second['access_token']))

    def test_concurrent_refresh_has_one_winner_and_revokes_replayed_family(self):
        tokens = sessions.issue(self.conn, 'owner')
        def refresh():
            conn = self.connect()
            try:
                return sessions.refresh(conn, tokens['refresh_token'])
            finally:
                conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: refresh(), range(2)))
        winners = [result for result in results if result]
        self.assertEqual(len(winners), 1)
        self.assertIsNone(sessions.authenticate(self.conn, winners[0]['access_token']))

    def test_atomic_throttle_shared_by_connections(self):
        def attempt():
            conn = self.connect()
            try:
                return sessions.throttle(conn, ['shared-limit'], 3, 60)
            finally:
                conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: attempt(), range(6)))
        self.assertEqual(sum(results), 3)

    def test_code_redemption_and_legacy_schema_upgrade(self):
        from unittest import mock
        import auth
        import auth_delivery
        from flask import Flask
        app = Flask(__name__)
        app.secret_key = 'test-secret-for-isolated-postgres'
        with app.test_request_context('/api/v1/auth/request'), \
             mock.patch.object(auth_delivery, 'configured', return_value=True), \
             mock.patch.object(auth_delivery, 'start', return_value='VE' + 'a' * 32), \
             mock.patch.object(auth_delivery, 'check', return_value=True):
            challenge, error = auth.start_challenge(self.conn, 'email', 'owner@example.test', 'mobile')
            self.assertIsNone(error)
            tokens = auth.verify_challenge(self.conn, challenge['challenge_id'], '123456', 'mobile')
            self.assertIsNotNone(tokens)
            self.assertIsNone(auth.verify_challenge(self.conn, challenge['challenge_id'], '123456', 'mobile'))
        self.conn.execute('ALTER TABLE "Account" DROP COLUMN auth_enabled')
        db.init_db(self.conn)
        account = db.fetch_one(self.conn, 'Account', user_id='owner')
        self.assertEqual(account['auth_enabled'], 0)
        self.assertEqual(account['email'], 'owner@example.test')

    def test_concurrent_code_redemption_issues_only_one_session(self):
        import threading
        from unittest import mock
        import auth
        import auth_delivery
        from flask import Flask
        app = Flask(__name__)
        app.secret_key = 'test-secret-for-isolated-postgres'
        barrier = threading.Barrier(2)
        with app.test_request_context('/api/v1/auth/request'), \
             mock.patch.object(auth_delivery, 'configured', return_value=True), \
             mock.patch.object(auth_delivery, 'start', return_value='VE' + 'a' * 32):
            challenge, error = auth.start_challenge(self.conn, 'email', 'owner@example.test', 'mobile')
            self.assertIsNone(error)
        def provider_check(*args):
            barrier.wait(timeout=15)
            return True
        def verify():
            conn = self.connect()
            try:
                with app.test_request_context('/api/v1/auth/verify'):
                    return auth.verify_challenge(conn, challenge['challenge_id'], '123456', 'mobile')
            finally:
                conn.close()
        with mock.patch.object(auth_delivery, 'check', side_effect=provider_check), \
             concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: verify(), range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(db.fetch_all(self.conn, 'AuthSession')), 1)
