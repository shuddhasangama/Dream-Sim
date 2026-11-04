"""Real PostgreSQL regression; set TEST_AVATAR_POSTGRES_URL to a local test DB."""
import io
import os
import unittest
import uuid
from unittest.mock import patch
from PIL import Image
from cryptography.fernet import Fernet
import auth_sessions
import avatar_service as avatars
import db


@unittest.skipUnless(os.getenv('TEST_AVATAR_POSTGRES_URL'), 'Local PostgreSQL URL required')
class AvatarPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.conn = psycopg.connect(os.environ['TEST_AVATAR_POSTGRES_URL'], row_factory=dict_row)
        self.schema = 'avatar_test_' + uuid.uuid4().hex
        self.conn.execute('CREATE SCHEMA ' + self.schema)
        self.conn.execute('SET search_path TO ' + self.schema)
        self.conn.commit()
        db.init_db(self.conn)
        self.env = patch.dict(os.environ, {'DHASHU_AVATAR_ENABLED': '1', 'OPENAI_API_KEY': 'synthetic',
            'SIGNZY_RECEIPT_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        self.env.start()
        db.insert_row(self.conn, 'User', {'id': 'owner', 'journey_state': 'dating'})
        out = io.BytesIO()
        Image.new('RGB', (160, 200), 'blue').save(out, 'JPEG')
        self.image = avatars.data_url(out.getvalue())

    def tearDown(self):
        self.env.stop()
        self.conn.rollback()
        self.conn.execute('DROP SCHEMA ' + self.schema + ' CASCADE')
        self.conn.commit()
        self.conn.close()

    def test_capture_queue_generate_accept_on_postgres(self):
        avatars.capture(self.conn, 'owner', self.image)
        self.assertEqual(avatars.view(self.conn, 'owner')['state'], 'draft')
        avatars.queue(self.conn, 'owner', {'consent': True, 'consent_version': avatars.VERSION})
        calls = []
        def provider(*args):
            calls.append(True)
            return [self.image, self.image]
        self.assertTrue(avatars.work_one(self.conn, provider))
        self.assertFalse(avatars.work_one(self.conn, provider))
        avatars.accept(self.conn, 'owner', 0)
        self.assertEqual(avatars.view(self.conn, 'owner')['state'], 'accepted')
        self.assertEqual(len(calls), 1)

    def test_legacy_helper_write_rolls_back_with_outer_transaction(self):
        with self.assertRaisesRegex(RuntimeError, 'rollback'):
            with auth_sessions.transaction(self.conn):
                db.insert_row(self.conn, 'User', {'id': 'rolled-back', 'journey_state': 'dating'})
                raise RuntimeError('rollback')
        self.assertIsNone(db.fetch_one(self.conn, 'User', id='rolled-back'))

