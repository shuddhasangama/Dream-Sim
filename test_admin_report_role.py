"""sec-admin: the admin dashboard reads through a read-only reporting user that
cannot see password hashes, token hashes or authenticator secrets.
Opt-in localhost-only PostgreSQL coverage; never touches a live database."""
import base64
import os
import secrets
import time
import unittest
import uuid
from unittest.mock import patch

from cryptography.fernet import Fernet

import db
from admin_dashboard import reports, security
from admin_dashboard.app import create_app
from admin_dashboard.manage import initialize
from tools import create_report_role


@unittest.skipUnless(os.getenv('ADMIN_TEST_POSTGRES_URL'), 'No isolated PostgreSQL test configured')
class ReportRoleTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        base = os.environ['ADMIN_TEST_POSTGRES_URL']
        if conninfo_to_dict(base).get('host') != '127.0.0.1':
            raise ValueError('Tests require isolated localhost PostgreSQL.')
        self.control = psycopg.connect(base, autocommit=True)
        self.addCleanup(self.control.close)
        self.schema = 'report_role_' + uuid.uuid4().hex[:12]
        self.role = 'report_test_' + uuid.uuid4().hex[:12]
        self.control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop)
        env = patch.dict(os.environ, {'DATABASE_URL': base + '?options=-csearch_path%3D' + self.schema,
                                      'ADMIN_PUBLIC_ORIGIN': 'https://admin.example.test', 'ADMIN_ALLOW_HTTP': '0',
                                      'ADMIN_TOTP_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        env.start(); self.addCleanup(env.stop)
        self.c = db.get_connection(); self.addCleanup(self.c.close)
        db.init_db(self.c); initialize(self.c)
        db.insert_row(self.c, 'User', {'id': 'sample', 'journey_state': 'onboarding'})
        db.insert_row(self.c, 'Account', {'id': 'sample-a', 'user_id': 'sample', 'phone': '+919000000001', 'auth_enabled': 1,
                                          'password_hash': 'pbkdf2:secret-hash', 'created_at': str(int(time.time()))})
        self.c.commit()
        self.secret = base64.b32encode(b'12345678901234567890').decode()
        self.password = 'Synthetic-local-test-password'
        now = int(time.time())
        with patch('time.time', return_value=now - 60):
            security.create_identity(self.c, 'office@example.test', self.password, self.secret,
                                     security.code(self.secret, (now - 60) // 30))
        database = self.control.execute('SELECT current_database()').fetchone()[0]
        role_password = secrets.token_urlsafe(24)
        for statement in create_report_role.statements(database, role_password, role=self.role, schema=self.schema):
            self.control.execute(statement)
        info = conninfo_to_dict(base)
        info.update(user=self.role, password=role_password, options='-csearch_path=' + self.schema)
        self.report_url = make_conninfo(**info)

    def drop(self):
        from psycopg import sql
        self.control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.control.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(self.role)))
        self.control.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(self.role)))

    def test_dashboard_works_through_the_reporting_user_and_secrets_are_unreadable(self):
        import psycopg
        with patch.dict(os.environ, {'ADMIN_REPORT_DATABASE_URL': self.report_url}):
            client = create_app().test_client(); origin = 'https://admin.example.test'
            r = client.post('/api/login', json={'email': 'office@example.test', 'password': self.password,
                                                'code': security.code(self.secret, int(time.time()) // 30)},
                            base_url=origin, headers={'Origin': origin})
            self.assertEqual(r.status_code, 200, r.text)
            for name in ('overview', 'users', 'sessions', 'checks', 'marketing', 'audit'):
                r = client.get('/api/reports/' + name, base_url=origin)
                self.assertEqual(r.status_code, 200, (name, r.text))
            csrf = client.get('/api/session', base_url=origin).get_json()['csrf']
            headers = {'Origin': origin, 'X-CSRF-Token': csrf}
            r = client.post('/api/search/users', json={'q': '+919000000001'}, base_url=origin, headers=headers)
            self.assertEqual(len(r.get_json()['rows']), 1, r.text)
            r = client.post('/api/user-summary', json={'user_id': 'sample'}, base_url=origin, headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            with reports.connection() as conn:
                self.assertEqual(conn.execute('SELECT current_user AS u').fetchone()['u'], self.role)
        with psycopg.connect(self.report_url) as conn:
            for secret_query in ('SELECT password_hash FROM "Account"', 'SELECT protected_totp FROM "AdminIdentity"',
                                 'SELECT password_hash FROM "AdminIdentity"', 'SELECT access_hash FROM "AuthSession"',
                                 'SELECT id FROM "AuthRefresh"', 'SELECT * FROM "AuthChallenge"', 'SELECT * FROM "GuruPrivate"'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=secret_query):
                    conn.execute(secret_query)
                conn.rollback()
            with self.assertRaises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
                conn.execute('UPDATE "User" SET journey_state = \'x\'')


if __name__ == '__main__':
    unittest.main()
