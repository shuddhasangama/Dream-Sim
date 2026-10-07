import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from unittest import mock
import zipfile

from cryptography.fernet import Fernet
from PIL import Image
import auth_sessions
import ceremony
import db
import identity_admin
import identity_capture as identity
import test_evolution_api as fixtures
from test_segment_efg_routes import RouteTestCase, app_module


class IdentityCaptureTests(RouteTestCase):
    request = fixtures.EvolutionApiTests.request
    post = fixtures.EvolutionApiTests.post

    def setUp(self):
        super().setUp()
        patch=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True});patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.dict(os.environ,{'DHASHU_IDENTITY_CAPTURE_ENABLED':'1',
            'DHASHU_IDENTITY_ENCRYPTION_KEY':Fernet.generate_key().decode(), 'BETA_DATE_SIMULATION_ENABLED':'1'})
        patch.start();self.addCleanup(patch.stop)
        self.headers={}
        for index, uid in enumerate(('owner','partner','stranger')):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'phone':f'+1555000000{index}',
                'email':uid+'@test.example','auth_enabled':1,'created_at':'test'})
            self.headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
        self.make_lockin('owner','partner')
        row=db.fetch_one(self.conn,'LockIn',id='lock-1');db.insert_row(self.conn,'LockIn',{**row,'dates_completed':1})
        stream=io.BytesIO();Image.new('RGB',(320,400),'red').save(stream,'JPEG')
        self.image='data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode()
        self.payload={'image':self.image,'consent':True,'consent_version':identity.CONSENT_VERSION}
        self.agreement='/lock-ins/lock-1/agreements/contact_share'

    def upload(self):
        response=self.post('/identity-capture',self.payload)
        self.assertEqual(response.status_code,200,response.json)
        return response.json['data']['capture_id']

    def sign(self):
        self.assertEqual(self.post(self.agreement+'/steps',{'step':'playbook'}).status_code,200)
        response=self.post(self.agreement+'/steps',{'step':'sign','signed_name':'My Name','acks':list(ceremony.ack_keys(ceremony.CONTACT_SHARE))})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['data']

    def test_capture_only_approval_is_scoped_and_records_honest_evidence(self):
        with mock.patch.dict(os.environ, {'DHASHU_IDENTITY_TEST_AUTO_APPROVE':'1',
                'DHASHU_SIMULATED_CLOCK':'true', 'DHASHU_TESTER_NO_OTP':'true',
                'DHASHU_TESTER_USER_IDS':'owner'}):
            self.assertFalse(identity.test_approved(self.conn,'owner'))
            cid=self.upload(); self.sign()
            view=identity.view(self.conn,'owner')
            self.assertTrue(view['can_complete'])
            self.assertTrue(view['test_approved'])
            self.assertFalse(view['verified'])
            self.assertEqual(view['status'],'captured')
            for changes in ({'DHASHU_IDENTITY_TEST_AUTO_APPROVE':'0'},
                            {'DHASHU_SIMULATED_CLOCK':'false'},
                            {'DHASHU_TESTER_USER_IDS':''}):
                with mock.patch.dict(os.environ,changes):
                    self.assertFalse(identity.test_approved(self.conn,'owner'))
                    self.assertEqual(self.post(self.agreement+'/steps',{'step':'face'}).status_code,409)
            response=self.post(self.agreement+'/steps',{'step':'face'})
            self.assertEqual(response.status_code,200,response.json)
            self.assertTrue(response.json['data']['complete'])
            state=db.fetch_one(self.conn,'Ceremony',user_id='owner',kind='contact_share')
            self.assertEqual(state['face_method'],'test_capture')
            self.assertEqual(state['identity_capture_id'],cid)
            self.assertTrue(db.fetch_one(self.conn,'IdentityCapture',id='owner')['image_ciphertext'])
            self.request('/identity-capture',method='DELETE')
            self.assertFalse(identity.test_approved(self.conn,'owner'))

    def test_test_approval_rejects_expired_rejected_and_reassigned_capture(self):
        with mock.patch.dict(os.environ, {'DHASHU_IDENTITY_TEST_AUTO_APPROVE':'1',
                'DHASHU_SIMULATED_CLOCK':'true', 'DHASHU_TESTER_NO_OTP':'true',
                'DHASHU_TESTER_USER_IDS':'owner'}):
            self.upload()
            row=db.fetch_one(self.conn,'IdentityCapture',id='owner')
            for changes in ({'status':'rejected'}, {'image_ciphertext':None},
                            {'image_expires_at':'2000-01-01T00:00:00+00:00'},
                            {'account_binding_sha256':'different'}):
                db.insert_row(self.conn,'IdentityCapture',{**row,**changes})
                self.assertFalse(identity.view(self.conn,'owner')['can_complete'])
            db.insert_row(self.conn,'IdentityCapture',row)
            account=db.fetch_one(self.conn,'Account',user_id='owner')
            db.insert_row(self.conn,'Account',{**account,'auth_enabled':0})
            self.assertFalse(identity.test_approved(self.conn,'owner'))

    def test_private_encrypted_upload_and_idempotence(self):
        cid=self.upload()
        row=db.fetch_one(self.conn,'IdentityCapture',id='owner')
        self.assertNotIn(self.image.split(',')[1],row['image_ciphertext'])
        raw=identity.cipher().decrypt(row['image_ciphertext'].encode())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),row['image_sha256'])
        self.assertEqual(self.upload(),cid)
        self.assertEqual(len(db.fetch_all(self.conn,'IdentityEvent')),1)
        for uid in ('owner','partner','stranger'):
            response=self.request('/identity-capture',uid=uid)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertNotIn('image_ciphertext',response.get_data(as_text=True))
            self.assertNotIn('data:image',response.get_data(as_text=True))
            if uid!='owner':self.assertEqual(response.json['data']['status'],'not_captured')
        self.assertFalse(db.fetch_all(self.conn,'ProfilePhoto'))
        self.assertEqual(self.post('/identity-capture',{**self.payload,'user_id':'partner'}).status_code,400)
        self.assertEqual(self.client.get('/api/v1/identity-capture').status_code,401)

    def test_disabled_consent_and_bad_image_fail_closed(self):
        for changes in ({'consent':False},{'consent':'true'},{'consent_version':'old'},{'image':'data:image/jpeg;base64,bad'}):
            self.assertEqual(self.post('/identity-capture',{**self.payload,**changes}).status_code,400)
        with mock.patch.dict(os.environ,{'DHASHU_IDENTITY_ENCRYPTION_KEY':''}):
            self.assertEqual(self.post('/identity-capture',self.payload).status_code,503)
        with mock.patch.dict(os.environ,{'DHASHU_IDENTITY_CAPTURE_ENABLED':'0'}):
            self.assertEqual(self.post('/identity-capture',self.payload).status_code,403)
        self.assertFalse(db.fetch_all(self.conn,'IdentityCapture'))

    def test_provider_handoff_does_not_verify_until_result_and_never_updates_bgv(self):
        cid=self.upload();self.sign()
        self.assertEqual(self.post(self.agreement+'/steps',{'step':'face'}).status_code,409)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'private.zip'
            identity_admin.export(self.conn,'owner',cid,path)
            with zipfile.ZipFile(path) as bundle:
                manifest=json.loads(bundle.read('manifest.json'))
                self.assertFalse(manifest['liveness_checked'])
                self.assertEqual(manifest['image_sha256'],hashlib.sha256(bundle.read('identity.jpg')).hexdigest())
            with self.assertRaises(FileExistsError):identity_admin.export(self.conn,'owner',cid,path)
            self.assertTrue(path.exists())
        self.assertEqual(identity.view(self.conn,'owner')['status'],'captured')
        with self.assertRaises(ValueError):identity.provider_result(self.conn,'owner',cid,'Vendor','ref','verified')
        identity_admin.submitted(self.conn,'owner',cid,'Vendor','submission-1')
        with self.assertRaises(ValueError):identity.provider_result(self.conn,'owner','stale','Vendor','ref','verified')
        with self.assertRaises(ValueError):identity.provider_result(self.conn,'owner',cid,'Other','ref','verified')
        before=db.fetch_one(self.conn,'User',id='owner')['bgv_status']
        identity.provider_result(self.conn,'owner',cid,'Vendor','result-1','verified')
        response=self.post(self.agreement+'/steps',{'step':'face'})
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(response.json['data']['complete'])
        self.assertFalse(response.json['data']['partner_complete'])
        state=db.fetch_one(self.conn,'Ceremony',user_id='owner',kind='contact_share')
        self.assertEqual(state['identity_capture_id'],cid)
        self.assertEqual(state['face_method'],'provider_result')
        self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['bgv_status'],before)
        self.assertEqual(self.request('/identity-capture',method='DELETE').status_code,200)
        self.assertFalse(identity.verified(self.conn,'owner'))
        self.assertIsNone(db.fetch_one(self.conn,'IdentityCapture',id='owner')['image_ciphertext'])
        self.assertTrue(self.request(self.agreement).json['data']['complete'])
        with self.assertRaises(ValueError):identity.provider_result(self.conn,'owner',cid,'Vendor','late','verified')

    def test_signature_snapshot_real_timestamp_and_retry_immutability(self):
        original=self.request(self.agreement).json['data']
        self.post(self.agreement+'/steps',{'step':'playbook','document_sha256':original['document_sha256']})
        with mock.patch('ceremony.clauses_for',return_value=[{'body':'changed terms'}]):
            self.assertEqual(self.request(self.agreement).json['data']['clauses'],original['clauses'])
        response=self.post(self.agreement+'/steps',{'step':'sign','signed_name':'Name','acks':list(ceremony.ack_keys(ceremony.CONTACT_SHARE)),'document_sha256':'incorrect'})
        self.assertEqual(response.status_code,409)
        data=self.sign();receipt=data['signature_receipt']
        digest=receipt.pop('evidence_sha256')
        canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(),digest)
        self.assertIn('T',receipt['signed_at_utc'])
        self.assertEqual(receipt['authentication'],'authenticated_session')
        again=self.sign()['signature_receipt'];self.assertEqual(again['evidence_sha256'],digest)
        self.assertEqual(self.request(self.agreement,uid='stranger').status_code,404)

    def test_expiry_purge_and_late_provider_response(self):
        cid=self.upload()
        identity_admin.submitted(self.conn,'owner',cid,'Vendor','submission')
        row=db.fetch_one(self.conn,'IdentityCapture',id='owner')
        db.insert_row(self.conn,'IdentityCapture',{**row,'image_expires_at':'2000-01-01T00:00:00+00:00'})
        self.assertEqual(identity.view(self.conn,'owner')['status'],'expired')
        with self.assertRaises(ValueError):identity.provider_result(self.conn,'owner',cid,'Vendor','late','verified')
        self.assertEqual(identity.purge(self.conn),1)
        self.assertEqual(identity.purge(self.conn),0)
        self.assertIsNone(db.fetch_one(self.conn,'IdentityCapture',id='owner')['image_ciphertext'])
        self.assertNotEqual(self.upload(),cid)

    def test_phone_reassignment_invalidates_reuse_and_old_vendor_result(self):
        cid=self.upload()
        identity_admin.submitted(self.conn,'owner',cid,'Vendor','submission')
        identity.provider_result(self.conn,'owner',cid,'Vendor','result','verified')
        self.assertTrue(identity.verified(self.conn,'owner'))
        account=db.fetch_one(self.conn,'Account',user_id='owner')
        db.insert_row(self.conn,'Account',{**account,'phone':'+15551112222'})
        self.assertFalse(identity.verified(self.conn,'owner'))
        self.assertEqual(identity.view(self.conn,'owner')['status'],'expired')
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):identity_admin.export(self.conn,'owner',cid,Path(temp)/'old.zip')
        replacement=self.upload();self.assertNotEqual(cid,replacement)
        with self.assertRaises(ValueError):identity.provider_result(self.conn,'owner',cid,'Vendor','late','verified')

    def test_tester_capture_and_signature_do_not_claim_otp_authentication(self):
        with mock.patch.dict(os.environ,{'DHASHU_TESTER_NO_OTP':'true','DHASHU_TESTER_USER_IDS':'owner'}):
            with auth_sessions.transaction(self.conn):
                session=auth_sessions.issue_in_transaction(self.conn,'owner',tester=True)
            self.headers['owner']={'Authorization':'Bearer '+session['access_token']}
            self.upload()
            self.assertEqual(db.fetch_one(self.conn,'IdentityCapture',id='owner')['authentication'],'tester_without_otp')
            self.assertEqual(self.sign()['signature_receipt']['authentication'],'tester_without_otp')
