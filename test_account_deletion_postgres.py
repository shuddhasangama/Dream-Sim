"""feat-purge on PostgreSQL 16: catalogue introspection, foreign-key order, full scan.
Opt-in localhost-only; never a live database."""
import json
import os
import unittest
import uuid
from unittest import mock

import account_deletion
import auth_sessions as sessions
import db


@unittest.skipUnless(os.getenv('ADMIN_TEST_POSTGRES_URL'), 'No isolated PostgreSQL test configured')
class PostgresPurgeTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        base = os.environ['ADMIN_TEST_POSTGRES_URL']
        if conninfo_to_dict(base).get('host') != '127.0.0.1':
            raise ValueError('Tests require isolated localhost PostgreSQL.')
        self.control = psycopg.connect(base, autocommit=True); self.addCleanup(self.control.close)
        self.schema = 'purge_' + uuid.uuid4().hex[:12]
        self.control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(lambda: self.control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema))))
        env = mock.patch.dict(os.environ, {'DATABASE_URL': base + '?options=-csearch_path%3D' + self.schema})
        env.start(); self.addCleanup(env.stop)
        self.c = db.get_connection(); self.addCleanup(self.c.close)
        db.init_db(self.c)
        for uid in ('owner', 'partner'):
            db.insert_row(self.c, 'User', {'id': uid, 'journey_state': 'dating', 'stats_json': json.dumps({'city': 'Bangalore'})})
            db.insert_row(self.c, 'Account', {'id': 'acc-' + uid, 'user_id': uid, 'phone': '+91987650001' + str(len(uid)),
                                              'auth_enabled': 1, 'created_at': '1'})
        db.insert_row(self.c, 'LockIn', {'id': 'lock-1', 'user_a': 'owner', 'user_b': 'partner', 'week': 1, 'status': 'active',
                                         'created_at': 'W1', 'dates_completed': 0})
        db.insert_row(self.c, 'Payment', {'id': 'pay-1', 'user_id': 'owner', 'purpose': 'agreement', 'scope_id': 'x', 'amount_inr': 499,
                                          'status': 'paid', 'reference': 'r', 'created_at': '1'})
        db.insert_row(self.c, 'GuruPrivate', {'id': 'owner', 'binding': 'b', 'payload': 'opaque'})
        self.c.commit()
        sessions.issue(self.c, 'owner')

    def test_purge_on_postgres_leaves_no_trace(self):
        account_deletion.request_deletion(self.c, 'owner')
        with mock.patch('auth_sessions.now', return_value=sessions.now() + 31 * 86400):
            counts = account_deletion.purge(self.c, 'owner')
        self.assertGreater(counts['deleted'], 3)
        leaks = []
        for table in sorted(db.TABLES):
            for row in self.c.execute(f'SELECT * FROM "{table}"').fetchall():
                leaks += [(table, k) for k, v in dict(row).items() if isinstance(v, str) and ('owner' in v and 'deleted_' not in v or '+919876500015' in v)]
        self.assertEqual(leaks, [])
        tomb = account_deletion.tombstone_id('owner')
        self.assertEqual(db.fetch_one(self.c, 'LockIn', id='lock-1')['user_a'], tomb)
        self.assertEqual(db.fetch_one(self.c, 'Payment', id='pay-1')['user_id'], tomb)
        self.assertIsNone(account_deletion.purge(self.c, 'owner'))


if __name__ == '__main__':
    unittest.main()
