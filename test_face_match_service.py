import base64
import os
from unittest.mock import patch
from cryptography.fernet import Fernet
import auth_sessions
import db
import face_match_service as service
from bgv_app import Protection
from api_contract import ApiError
from test_segment_efg_routes import RouteTestCase,app_module

class FaceFlowTests(RouteTestCase):
 def setUp(self):
  super().setUp();self.make_user('owner');self.make_user('other')
  p=patch.dict(os.environ,{'DHASHU_FACE_MATCH_ENABLED':'1','SIGNZY_ENV':'preproduction','SIGNZY_TEST_API_KEY':'synthetic','SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()});p.start();self.addCleanup(p.stop)
  db.insert_row(self.conn,'AvatarJob',{'id':'owner','state':'accepted','protected_selfie':Protection().seal({'image':base64.b64encode(b'original selfie').decode()}),'selfie_sha256':'selfie-hash','created_at':service.stamp(),'updated_at':service.stamp(),'expires_at':'2099-01-01T00:00:00+00:00'})
  db.insert_row(self.conn,'DigiLockerSession',{'id':'identity','user_id':'owner','environment':'preproduction','state':'complete','consent_version':'digilocker-screening-v3','created_at':service.stamp(),'updated_at':service.stamp(),'expires_at':'2099-01-01T00:00:00+00:00','protected_photo':Protection().seal({'image_base64':base64.b64encode(b'original aadhaar').decode(),'mime_type':'image/jpeg','image_expires_at':'2099-01-01T00:00:00+00:00'})})
 def body(self):return {'consent':True,'consent_version':service.VERSION}
 def test_one_shot_original_pair_worker_and_cleanup(self):
  before=db.fetch_one(self.conn,'User',id='owner')['bgv_status'];service.queue(self.conn,'owner',self.body())
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',self.body())
  self.assertEqual(set(Protection().open(db.fetch_one(self.conn,'FaceMatchJob',id='owner')['protected_input'])),{'selfie','aadhaar'})
  calls=[]
  class Client:
   def __init__(inner,cfg):pass
   def execute(inner,operation,inputs,**kwargs):
    calls.append(inputs);self.assertEqual(operation,'face_match');self.assertEqual(inputs['threshold'],.5);self.assertEqual(inputs['detectMask'],[inputs['firstImage']])
    self.assertNotIn('avatar',str(inputs));kwargs['evidence_sink']({'synthetic':True})
    return {'face_match_passed':True,'match_percentage':99,'liveness_checked':False}
  self.assertTrue(service.work_one(self.conn,Client));self.assertEqual(len(calls),1);self.assertFalse(service.work_one(self.conn,Client))
  view=service.view(self.conn,'owner');self.assertEqual(view['state'],'matched');self.assertEqual(view['liveness'],'not_checked');self.assertNotIn(base64.b64encode(b'original selfie').decode(),str(view))
  self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['bgv_status'],before)
  lease=db.fetch_all(self.conn,'FaceImageLease')[0];self.assertEqual(lease['revoked'],1);self.assertEqual(lease['protected_images'],'')
 def test_missing_cross_user_latest_and_expired_sources(self):
  with self.assertRaises(ApiError):service.queue(self.conn,'other',self.body())
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',{'consent':False,'consent_version':service.VERSION})
  db.insert_row(self.conn,'DigiLockerSession',{'id':'newer','user_id':'owner','environment':'preproduction','state':'pending','consent_version':'digilocker-screening-v3','created_at':'2090-01-01','updated_at':service.stamp(),'expires_at':'2099-01-01'})
  self.assertFalse(service.view(self.conn,'owner')['reference_ready'])
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',self.body())
 def test_unknown_not_replayed_and_clear_does_not_restore_allowance(self):
  service.queue(self.conn,'owner',self.body())
  def fail(cfg):raise TimeoutError()
  service.work_one(self.conn,fail);self.assertEqual(service.view(self.conn,'owner')['state'],'unknown');self.assertFalse(service.work_one(self.conn,fail))
  service.clear(self.conn,'owner')
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',self.body())
 def test_stale_worker_and_draft_selfie(self):
  self.conn.execute('UPDATE "AvatarJob" SET state=?',('draft',));self.conn.commit()
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',self.body())
  self.conn.execute('UPDATE "AvatarJob" SET state=?',('ready',));self.conn.commit();service.queue(self.conn,'owner',self.body())
  self.conn.execute('UPDATE "FaceMatchJob" SET state=?,updated_at=?',('submitting','2000-01-01T00:00:00+00:00'));self.conn.commit()
  self.assertFalse(service.work_one(self.conn,lambda cfg:self.fail('replayed')));self.assertEqual(service.view(self.conn,'owner')['state'],'unknown')
 def test_owner_routes(self):
  with patch.dict(app_module.app.config,{'AUTH_ENABLED':True}):
   headers={}
   for uid in ('owner','other'):
    db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'auth_enabled':1,'verified_email':1,'email':uid+'@test.example','created_at':'test'})
    headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
   self.assertEqual(self.client.get('/api/v1/profile/face-match').status_code,401)
   self.assertEqual(self.client.post('/api/v1/profile/face-match',headers=headers['owner'],json=self.body()).status_code,200)
   self.assertEqual(self.client.get('/api/v1/profile/face-match',headers=headers['other']).json['data']['state'],'not_started')
   self.assertEqual(self.client.post('/api/v1/profile/face-match',headers=headers['other'],json=self.body()).status_code,409)
