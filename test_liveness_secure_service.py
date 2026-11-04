import base64
import io
import os
from unittest.mock import patch
from cryptography.fernet import Fernet
from PIL import Image
import db
import avatar_service
import auth_sessions
import liveness_secure_service as service
from bgv_app import Protection
from signzy import liveness_secure_create, liveness_secure_data
from test_segment_efg_routes import RouteTestCase, app_module


class FakeClient:
    calls = []
    pending = False
    mismatch = False
    fail_match = False
    def __init__(self, config):
        pass
    def execute(self, operation, values, **kwargs):
        self.calls.append(operation)
        if operation == 'liveness_secure_create':
            body = {'token': 'synthetic-token', 'consumerId': 'synthetic-consumer',
                'videoUrl': 'https://liveliness-preproduction.signzy.app/consumer/test/token/synthetic-token'}
            summary = liveness_secure_create.summarize(200, body)
        else:
            body = {'result': {'token': 'different' if self.mismatch else 'synthetic-token', 'consumerId': 'synthetic-consumer',
                'isUsed': 0 if self.pending else 1, 'capturedImage': 'https://preproduction-persist.signzy.tech/api/files/test/download/photo.jpg',
                'passiveLiveliness': {'liveness': True}, 'faceMatch': {'verified': not self.fail_match, 'matchPercentage': '99.00%'},
                'status': not self.fail_match, 'additionalChecks': {'status': True}}}
            summary = liveness_secure_data.summarize(200, body)
        kwargs['evidence_sink']({'provider_response': {'http_status': 200, 'json': body}})
        return summary


class HostedLivenessTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.make_user('owner');self.make_user('other')
        self.env = patch.dict(os.environ, {'DHASHU_LIVENESS_SECURE_ENABLED': '1', 'SIGNZY_ENV': 'preproduction',
            'DHASHU_AVATAR_ENABLED': '1', 'SIGNZY_RECEIPT_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        self.env.start();self.addCleanup(self.env.stop)
        FakeClient.calls=[];FakeClient.pending=False;FakeClient.mismatch=False;FakeClient.fail_match=False
        out=io.BytesIO();Image.new('RGB',(160,200),'green').save(out,'JPEG')
        self.photo={'image_base64':base64.b64encode(out.getvalue()).decode(), 'mime_type':'image/jpeg',
            'image_expires_at':'2099-01-01T00:00:00+00:00', 'url':'https://persist.signzy.tech/api/files/test/download/aadhaar.jpg'}
        db.insert_row(self.conn,'DigiLockerSession',{'id':'identity','user_id':'owner','environment':'preproduction',
            'state':'complete','consent_version':'digilocker-screening-v3','created_at':service.stamp(),'updated_at':service.stamp(),
            'expires_at':'2099-01-01','protected_photo':Protection().seal(self.photo)})
    def create(self):
        service.queue_create(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
        self.assertTrue(service.work_one(self.conn,FakeClient,lambda url:self.photo))
        return service.row(self.conn,'owner')['flow_id']
    def finish(self):
        flow=self.create();service.queue_get(self.conn,'owner',flow)
        service.work_one(self.conn,FakeClient,lambda url:self.photo)
    def test_full_flow_snapshot_once_and_selfie_reuse_without_generation(self):
        before=db.fetch_one(self.conn,'User',id='owner')['bgv_status']
        flow=self.create()
        for i in range(3):service.queue_create(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
        self.assertFalse(service.work_one(self.conn,FakeClient))
        self.assertIsNotNone(service.view(self.conn,'owner')['capture_url'])
        service.queue_get(self.conn,'owner',flow);service.queue_get(self.conn,'owner',flow)
        service.work_one(self.conn,FakeClient,lambda url:self.photo)
        self.assertEqual(service.view(self.conn,'owner')['state'],'matched')
        self.assertEqual(service.view(self.conn,'owner')['liveness'],'passed')
        self.assertIsNone(service.view(self.conn,'owner')['capture_url'])
        self.assertEqual(FakeClient.calls,['liveness_secure_create','liveness_secure_data'])
        self.assertIsNotNone(avatar_service.view(self.conn,'owner')['verified_selfie_preview'])
        self.assertIsNone(db.fetch_one(self.conn,'AvatarJob',id='owner'))
        self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['bgv_status'],before)
    def test_pending_cooldown_and_three_get_cap(self):
        from api_contract import ApiError
        flow=self.create();FakeClient.pending=True
        for i in range(3):
            service.queue_get(self.conn,'owner',flow);service.work_one(self.conn,FakeClient)
            if i<2:
                with self.assertRaises(ApiError):service.queue_get(self.conn,'owner',flow)
                with auth_sessions.transaction(self.conn):auth_sessions.sql(self.conn,'UPDATE "LivenessSession" SET next_fetch_at=? WHERE id=?',('2000','owner'))
        self.assertEqual(service.view(self.conn,'owner')['state'],'unknown')
        self.assertFalse(service.work_one(self.conn,FakeClient))
        self.assertEqual(FakeClient.calls.count('liveness_secure_data'),3)
    def test_mismatched_session_and_failed_match_do_not_pass_or_download(self):
        flow=self.create();FakeClient.mismatch=True;service.queue_get(self.conn,'owner',flow)
        service.work_one(self.conn,FakeClient,lambda url:self.fail('must not download'))
        self.assertEqual(service.view(self.conn,'owner')['state'],'unknown')
        self.assertIsNone(service.selfie(self.conn,'owner'))
    def test_failed_match_not_marked_live_identity_verified(self):
        FakeClient.fail_match=True;self.finish()
        view=service.view(self.conn,'owner');self.assertEqual(view['state'],'not_matched');self.assertFalse(view['combined_passed'])
        self.assertIsNone(service.selfie(self.conn,'owner'))
    def test_unknown_create_is_not_replayed(self):
        service.queue_create(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
        def fail(config):raise TimeoutError()
        self.assertTrue(service.work_one(self.conn,fail));self.assertFalse(service.work_one(self.conn,fail))
        self.assertEqual(service.view(self.conn,'owner')['state'],'unknown')
    def test_owner_routes_and_no_other_account_token_access(self):
        from api_contract import ApiError
        flow=self.create()
        self.assertIsNone(service.view(self.conn,'other')['capture_url'])
        with self.assertRaises(ApiError):service.queue_get(self.conn,'other',flow)
        with patch.dict(app_module.app.config,{'AUTH_ENABLED':True}):
            db.insert_row(self.conn,'Account',{'id':'owner','user_id':'owner','email':'owner@example.test','verified_email':1,'auth_enabled':1,'created_at':'test'})
            headers={'Authorization':'Bearer '+auth_sessions.issue(self.conn,'owner')['access_token']}
            self.assertIn(self.client.post('/api/v1/profile/liveness/complete',json={'session_id':flow}).status_code,(401,403))
            response=self.client.post('/api/v1/profile/liveness/complete',json={'session_id':flow},headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['data']['state'],'queued_get')
    def test_delete_preserves_paid_ledger_and_removes_original(self):
        self.finish()
        with auth_sessions.transaction(self.conn):service.clear(self.conn,'owner')
        self.assertIsNone(service.selfie(self.conn,'owner'))
        service.queue_create(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
        self.assertEqual(service.row(self.conn,'owner')['state'],'deleted')
    def test_expiry_removes_image_but_retains_check_summary(self):
        self.finish()
        with auth_sessions.transaction(self.conn):auth_sessions.sql(self.conn,'UPDATE "LivenessSession" SET expires_at=? WHERE id=?',('2000','owner'))
        service.work_one(self.conn,FakeClient)
        self.assertIsNone(service.selfie(self.conn,'owner'))
        self.assertTrue(service.view(self.conn,'owner')['combined_passed'])
