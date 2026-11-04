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

    def test_face_queue_and_private_image_lease_on_postgres(self):
        import face_match_service as faces
        from bgv_app import Protection
        avatars.capture(self.conn, 'owner', self.image)
        avatars.queue(self.conn, 'owner', {'consent': True, 'consent_version': avatars.VERSION})
        source = avatars.row(self.conn, 'owner')
        reference = ({'id': 'identity'}, {'image_base64': self.image.split(',')[1],
            'mime_type': 'image/jpeg', 'image_expires_at': source['expires_at']})
        with patch.dict(os.environ, {'DHASHU_FACE_MATCH_ENABLED': '1'}), patch.object(faces, 'sources', return_value=(source, reference)):
            faces.queue(self.conn, 'owner', {'consent': True, 'consent_version': faces.VERSION})
        self.assertEqual(db.fetch_one(self.conn, 'FaceMatchJob', id='owner')['state'], 'queued')
        with auth_sessions.transaction(self.conn):
            db.insert_row(self.conn, 'FaceImageLease', {'id': 'lease', 'user_id': 'owner',
                'protected_images': Protection().seal({'synthetic': True}),
                'expires_at': source['expires_at'], 'revoked': 0})
        self.assertEqual(db.fetch_one(self.conn, 'FaceImageLease', id='lease')['revoked'], 0)

    def test_hosted_liveness_full_flow_on_postgres(self):
        import liveness_secure_service as hosted
        import face_match_service as faces
        from test_liveness_secure_service import FakeClient
        FakeClient.calls=[];FakeClient.pending=False;FakeClient.mismatch=False;FakeClient.fail_match=False
        photo={'image_base64':self.image.split(',')[1], 'mime_type':'image/jpeg',
            'image_expires_at':'2099-01-01', 'url':'https://persist.signzy.tech/api/files/test/download/aadhaar.jpg'}
        with patch.dict(os.environ, {'DHASHU_LIVENESS_SECURE_ENABLED':'1','SIGNZY_ENV':'preproduction'}), patch.object(faces,'sources',return_value=(None,({'id':'identity'},photo))):
            hosted.queue_create(self.conn,'owner',{'consent':True,'consent_version':hosted.VERSION})
            hosted.work_one(self.conn,FakeClient,lambda url:photo)
            hosted.queue_get(self.conn,'owner',hosted.row(self.conn,'owner')['flow_id'])
            hosted.work_one(self.conn,FakeClient,lambda url:photo)
            self.assertTrue(hosted.view(self.conn,'owner')['combined_passed'])
            self.assertIsNotNone(avatars.view(self.conn,'owner')['verified_selfie_preview'])

