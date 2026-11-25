"""sec-enc: member fields encrypted at rest; phone found by blind index; batch migration."""
import os
import sqlite3
import unittest
from unittest import mock

from cryptography.fernet import Fernet

import db
import member_crypto
from test_segment_efg_routes import RouteTestCase
from tools import encrypt_member_fields

KEYS = {'DHASHU_DATA_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        'DHASHU_BLIND_INDEX_KEY': 'b' * 40, 'DHASHU_FIELD_ENCRYPTION': '0'}
ON = {**KEYS, 'DHASHU_FIELD_ENCRYPTION': '1'}
QUIET = lambda *_: None  # noqa: E731


class FieldCipherTests(unittest.TestCase):
    def test_round_trip_off_by_default_never_double(self):
        with mock.patch.dict(os.environ, KEYS):
            self.assertEqual(member_crypto.seal('hello'), 'hello')           # switch off: plain
        with mock.patch.dict(os.environ, ON):
            sealed = member_crypto.seal('nandri, thanks நன்றி')
            self.assertTrue(sealed.startswith('enc1:'))
            self.assertNotIn('thanks', sealed)
            self.assertEqual(member_crypto.seal(sealed), sealed)
            self.assertEqual(member_crypto.open_value(sealed), 'nandri, thanks நன்றி')
            self.assertEqual(member_crypto.open_value('plain'), 'plain')
            self.assertIsNone(member_crypto.seal(None))
        with mock.patch.dict(os.environ, {**ON, 'DHASHU_DATA_ENCRYPTION_KEY': Fernet.generate_key().decode()}):
            with self.assertRaises(member_crypto.Unreadable):
                member_crypto.open_value(sealed)
            self.assertEqual(member_crypto.open_quiet(sealed, 'x'), 'x')

    def test_blind_index_is_canonical_and_keyed(self):
        with mock.patch.dict(os.environ, KEYS):
            a = member_crypto.blind_index('+919876543210')
            self.assertEqual(a, member_crypto.blind_index('919876543210'))   # stored digits form
            self.assertEqual(a, member_crypto.blind_index(member_crypto.force_seal('+919876543210')))
            self.assertNotEqual(a, member_crypto.blind_index('+919876543211'))
            self.assertRegex(a, r'^[0-9a-f]{64}$')
        with mock.patch.dict(os.environ, {**KEYS, 'DHASHU_BLIND_INDEX_KEY': 'c' * 40}):
            self.assertNotEqual(a, member_crypto.blind_index('+919876543210'))
        with mock.patch.dict(os.environ, {'DHASHU_BLIND_INDEX_KEY': 'short'}):
            self.assertIsNone(member_crypto.blind_index('+919876543210'))


class StorageTests(RouteTestCase):
    def raw(self, table, column, row_id):
        return self.conn.execute(f'SELECT {column} FROM "{table}" WHERE id = ?', (row_id,)).fetchone()[0]

    def test_lookup_by_phone_finds_encrypted_rows(self):
        self.make_user('owner')
        with mock.patch.dict(os.environ, ON):
            db.insert_row(self.conn, 'Account', {'id': 'acc1', 'user_id': 'owner', 'phone': '+919876543210', 'created_at': '1'})
            self.conn.commit()
            self.assertEqual([a['id'] for a in db.fetch_all(self.conn, 'Account', phone='+919876543210')], ['acc1'])
            self.assertEqual(db.fetch_all(self.conn, 'Account', phone='+919876543211'), [])

    def test_fields_are_encrypted_on_disk_and_plain_to_callers(self):
        self.make_user('owner')
        with mock.patch.dict(os.environ, ON):
            db.insert_row(self.conn, 'ProfilePhoto', {'id': 'owner', 'data_url': 'data:image/png;base64,AAAA'})
            db.insert_row(self.conn, 'Account', {'id': 'acc1', 'user_id': 'owner', 'phone': '+919876543210', 'created_at': '1'})
            self.conn.commit()
            for table, column, row_id in (('ProfilePhoto', 'data_url', 'owner'), ('Account', 'phone', 'acc1')):
                self.assertTrue(self.raw(table, column, row_id).startswith('enc1:'), table)
            self.assertEqual(db.fetch_one(self.conn, 'ProfilePhoto', id='owner')['data_url'], 'data:image/png;base64,AAAA')
            account = db.fetch_one(self.conn, 'Account', id='acc1')
            self.assertEqual(account['phone'], '+919876543210')
            self.assertEqual(account['phone_index'], member_crypto.blind_index('+919876543210'))

    def test_same_phone_cannot_be_registered_twice_when_encrypted(self):
        self.make_user('owner'); self.make_user('other')
        with mock.patch.dict(os.environ, ON):
            db.insert_row(self.conn, 'Account', {'id': 'acc1', 'user_id': 'owner', 'phone': '+919876543210', 'created_at': '1'})
            self.conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.insert_row(self.conn, 'Account', {'id': 'acc2', 'user_id': 'other', 'phone': '919876543210', 'created_at': '1'})
        self.conn.rollback()

    def test_admin_approval_sign_in_lookup_and_admin_search_with_encryption(self):
        import auth
        import auth_admin
        from admin_dashboard import reports
        self.make_user('owner')
        with mock.patch.dict(os.environ, ON):
            auth_admin.manage(self.conn, 'owner', 'enable', phone='+919876543210', apply=True)
            raw = self.conn.execute('SELECT * FROM "Account" WHERE user_id = ?', ('owner',)).fetchone()
            self.assertTrue(raw['phone'].startswith('enc1:'))
            self.assertEqual(raw['phone_index'], member_crypto.blind_index('+919876543210'))
            rows = self.conn.execute('SELECT * FROM "Account"').fetchall()      # sign-in's raw scan
            self.assertEqual([r['user_id'] for r in rows
                              if auth.normalize('phone', r['phone'], stored=True) == '+919876543210'], ['owner'])
            found = reports.users(self.conn, query='+91 98765 43210')['rows']
            self.assertEqual([(r['user_id'], r['phone']) for r in found], [('owner', '•••• 3210')])


class BatchMigrationTests(RouteTestCase):
    def test_dry_run_apply_idempotent_and_rollback(self):
        legacy = {'DHASHU_FIELD_ENCRYPTION': '0', 'DHASHU_BLIND_INDEX_KEY': ''}
        with mock.patch.dict(os.environ, legacy):                # rows written before any key existed
            self.make_user('owner')
            db.insert_row(self.conn, 'Account', {'id': 'acc1', 'user_id': 'owner', 'phone': '+919876543210', 'created_at': '1'})
            db.insert_row(self.conn, 'ProfilePhoto', {'id': 'owner', 'data_url': 'data:image/png;base64,AAAA'})
            self.conn.commit()
        with mock.patch.dict(os.environ, KEYS):
            dry = encrypt_member_fields.run(self.conn, out=QUIET)
            self.assertEqual(dry[('Account', 'phone')], {'plain': 1, 'encrypted': 0, 'changed': 0})
            self.assertEqual(self.conn.execute('SELECT phone FROM "Account"').fetchone()[0], '+919876543210')
            done = encrypt_member_fields.run(self.conn, apply=True, out=QUIET)
            self.assertEqual(done[('ProfilePhoto', 'data_url')]['changed'], 1)
            self.assertEqual(done['phone_index'], {'missing': 1, 'filled': 1})
            raw = self.conn.execute('SELECT phone, phone_index FROM "Account"').fetchone()
            self.assertTrue(raw[0].startswith('enc1:'))
            self.assertEqual(raw[1], member_crypto.blind_index('+919876543210'))
            self.assertEqual(db.fetch_one(self.conn, 'Account', id='acc1')['phone'], '+919876543210')
            again = encrypt_member_fields.run(self.conn, apply=True, out=QUIET)
            self.assertEqual(again[('Account', 'phone')], {'plain': 0, 'encrypted': 1, 'changed': 0})
            encrypt_member_fields.run(self.conn, apply=True, decrypt=True, out=QUIET)
            self.assertEqual(self.conn.execute('SELECT phone FROM "Account"').fetchone()[0], '+919876543210')


if __name__ == '__main__':
    unittest.main()
