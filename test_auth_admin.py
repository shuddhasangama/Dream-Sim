"""Operator-only beta approval and recovery behavior."""
import unittest

import auth_admin
import auth_sessions as sessions
import db
from test_segment_efg_routes import RouteTestCase


class BetaAccountTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.make_user('owner')
        self.make_user('other')

    def test_dry_run_does_not_create_account(self):
        auth_admin.manage(self.conn, 'owner', 'enable', email='owner@example.test')
        self.assertIsNone(db.fetch_one(self.conn, 'Account', user_id='owner'))

    def test_enable_existing_profile_and_revoke_on_disable(self):
        auth_admin.manage(self.conn, 'owner', 'enable', email='OWNER@example.test', phone='+919876543210', apply=True)
        row = db.fetch_one(self.conn, 'Account', user_id='owner')
        self.assertEqual(row['email'], 'owner@example.test')
        self.assertEqual(row['auth_enabled'], 1)
        self.assertEqual(row['verified_email'], 0)
        self.assertEqual(row['verified_phone'], 0)
        tokens = sessions.issue(self.conn, 'owner')
        auth_admin.manage(self.conn, 'owner', 'disable', apply=True)
        self.assertIsNone(sessions.authenticate(self.conn, tokens['access_token']))
        self.assertIsNone(sessions.refresh(self.conn, tokens['refresh_token']))

    def test_reapproval_invalidates_credentials_and_contact_verification(self):
        auth_admin.manage(self.conn, 'owner', 'enable', email='owner@example.test', apply=True)
        tokens = sessions.issue(self.conn, 'owner')
        self.conn.execute('UPDATE Account SET verified_email = 1 WHERE user_id = ?', ('owner',))
        self.conn.commit()
        auth_admin.manage(self.conn, 'owner', 'enable', email='new@example.test', apply=True)
        row = db.fetch_one(self.conn, 'Account', user_id='owner')
        self.assertEqual(row['verified_email'], 0)
        self.assertIsNone(sessions.authenticate(self.conn, tokens['access_token']))

    def test_canonical_contact_collision_is_rejected(self):
        auth_admin.manage(self.conn, 'owner', 'enable', email='owner@example.test', phone='+919876543210', apply=True)
        for kwargs in ({'email': 'OWNER@example.test'}, {'phone': '919876543210'}):
            with self.assertRaises(ValueError):
                auth_admin.manage(self.conn, 'other', 'enable', apply=True, **kwargs)
        self.assertIsNone(db.fetch_one(self.conn, 'Account', user_id='other'))

    def test_missing_profile_and_missing_contact_fail(self):
        with self.assertRaises(ValueError):
            auth_admin.manage(self.conn, 'missing', 'enable', email='owner@example.test', apply=True)
        with self.assertRaises(ValueError):
            auth_admin.manage(self.conn, 'owner', 'enable', apply=True)
