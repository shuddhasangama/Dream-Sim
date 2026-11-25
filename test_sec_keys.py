"""sec-keys: rotation-aware encryption keys and the re-encryption job."""
import os
import sqlite3
import unittest
from unittest import mock

from cryptography.fernet import Fernet, InvalidToken

import crypto_keys
from tools import reencrypt_keys

K0, K1, K2 = (Fernet.generate_key().decode() for _ in range(3))


def env(current, current_id=None, previous=None):
    values = {'TEST_KEY': current}
    if current_id:
        values['TEST_KEY_ID'] = current_id
    if previous is not None:
        values['TEST_KEY_PREVIOUS'] = previous
    return mock.patch.dict(os.environ, values)


class KeyRotationTests(unittest.TestCase):
    def setUp(self):
        for name in ('TEST_KEY', 'TEST_KEY_ID', 'TEST_KEY_PREVIOUS'):
            os.environ.pop(name, None)

    def test_single_key_is_plain_fernet(self):
        with env(K1):
            token = crypto_keys.cipher('TEST_KEY').encrypt(b'secret')
        self.assertEqual(Fernet(K1.encode()).decrypt(token), b'secret')          # old code can read new values
        with env(K1):
            self.assertEqual(crypto_keys.cipher('TEST_KEY').decrypt(Fernet(K1.encode()).encrypt(b'x')), b'x')

    def test_newest_encrypts_older_decrypt(self):
        with env(K1, 'k1'):
            old = crypto_keys.cipher('TEST_KEY').encrypt(b'old value')
        with env(K2, 'k2', f'k1:{K1},k0:{K0}'):
            ring = crypto_keys.cipher('TEST_KEY')
            self.assertEqual(ring.decrypt(old), b'old value')
            new = ring.encrypt(b'new value')
            self.assertEqual(crypto_keys.which('TEST_KEY', new), 'k2')
            self.assertEqual(crypto_keys.which('TEST_KEY', old), 'k1')
            self.assertIsNone(crypto_keys.which('TEST_KEY', Fernet.generate_key() and Fernet(Fernet.generate_key()).encrypt(b'?')))
        with env(K2, 'k2'):                                                      # previous key removed too early
            with self.assertRaises(InvalidToken):
                crypto_keys.cipher('TEST_KEY').decrypt(old)

    def test_bare_previous_keys_get_positional_ids(self):
        with env(K2, None, K1):
            self.assertEqual([i for i, _ in crypto_keys.entries('TEST_KEY')], ['current', 'previous-1'])

    def test_missing_and_bad_keys(self):
        with self.assertRaises(KeyError):
            crypto_keys.cipher('TEST_KEY')
        with self.assertRaises(ValueError):                                      # same object is also a ValueError
            crypto_keys.cipher('TEST_KEY')
        with env('not-a-key'), self.assertRaises(ValueError):
            crypto_keys.cipher('TEST_KEY')

    def test_guru_history_survives_rotation(self):
        import guru_navigator
        with mock.patch.dict(os.environ, {'DHASHU_GURU_ENCRYPTION_KEY': K1}):
            stored = guru_navigator.pack({'topic': 'planning'})
        with mock.patch.dict(os.environ, {'DHASHU_GURU_ENCRYPTION_KEY': K2, 'DHASHU_GURU_ENCRYPTION_KEY_PREVIOUS': 'k1:' + K1}):
            self.assertEqual(guru_navigator.unpack(stored), {'topic': 'planning'})


class ReencryptJobTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.execute('CREATE TABLE "KeyProbe" (id TEXT PRIMARY KEY, v TEXT)')
        old, new = Fernet(K1.encode()), Fernet(K2.encode())
        rows = [('a', old.encrypt(b'1').decode()), ('b', old.encrypt(b'2').decode()),
                ('c', new.encrypt(b'3').decode()), ('d', Fernet(K0.encode()).encrypt(b'lost').decode()), ('e', None)]
        self.conn.executemany('INSERT INTO "KeyProbe" VALUES (?, ?)', rows); self.conn.commit()
        patcher = mock.patch.object(reencrypt_keys, 'registry', return_value={'TEST_KEY': [('KeyProbe', 'id', 'v'), ('Missing', 'id', 'v')]})
        patcher.start(); self.addCleanup(patcher.stop)
        self.env = env(K2, 'k2', 'k1:' + K1)
        self.env.start(); self.addCleanup(self.env.stop)

    def values(self):
        return dict(self.conn.execute('SELECT id, v FROM "KeyProbe"').fetchall())

    def test_dry_run_reports_and_changes_nothing(self):
        before = self.values()
        summary = reencrypt_keys.run(self.conn, out=lambda *_: None)
        self.assertEqual(summary[('TEST_KEY', 'KeyProbe', 'v')], {'counts': {'k1': 2, 'k2': 1, 'unreadable': 1}, 'reencrypted': 0})
        self.assertEqual(self.values(), before)

    def test_apply_moves_old_values_to_the_current_key_and_keeps_plaintext(self):
        before = self.values()
        summary = reencrypt_keys.run(self.conn, apply=True, batch=1, out=lambda *_: None)
        self.assertEqual(summary[('TEST_KEY', 'KeyProbe', 'v')]['reencrypted'], 2)
        after = self.values()
        self.assertEqual(after['c'], before['c'])                       # already current: untouched
        self.assertEqual(after['d'], before['d'])                       # unreadable: never touched
        self.assertIsNone(after['e'])
        only_new = Fernet(K2.encode())
        self.assertEqual((only_new.decrypt(after['a'].encode()), only_new.decrypt(after['b'].encode())), (b'1', b'2'))
        again = reencrypt_keys.run(self.conn, out=lambda *_: None)
        self.assertEqual(again[('TEST_KEY', 'KeyProbe', 'v')]['counts'], {'k2': 3, 'unreadable': 1})

    def test_concurrent_change_is_not_overwritten(self):
        real_which = crypto_keys.which
        def which_then_app_writes(name, token):
            result = real_which(name, token)
            if token == self.values().get('a'):
                self.conn.execute('UPDATE "KeyProbe" SET v = ? WHERE id = ?', ('app-wrote-this', 'a'))
            return result
        with mock.patch.object(crypto_keys, 'which', side_effect=which_then_app_writes):
            reencrypt_keys.run(self.conn, apply=True, out=lambda *_: None)
        self.assertEqual(self.values()['a'], 'app-wrote-this')


class RegistryTests(unittest.TestCase):
    def test_every_registered_column_exists_in_the_schema(self):
        import re
        from pathlib import Path
        text = Path('schema_postgres.sql').read_text(encoding='utf-8') + Path('admin_dashboard/schema.sql').read_text(encoding='utf-8')
        tables = {m.group(1): m.group(2) for m in re.finditer(r'CREATE TABLE IF NOT EXISTS "(\w+)" \((.*?)\n\);', text, re.S)}
        for name, columns in reencrypt_keys.registry().items():
            for table, id_col, col in columns:
                self.assertIn(table, tables, name)
                for column in (id_col, col):
                    self.assertRegex(tables[table], rf'\b{column}\b', f'{table}.{column}')

if __name__ == '__main__':
    unittest.main()
