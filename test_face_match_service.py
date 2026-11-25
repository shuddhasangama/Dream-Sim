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
 def test_aadhaar_readiness_does_not_depend_on_selfie(self):
  self.conn.execute('UPDATE "AvatarJob" SET protected_selfie=NULL');self.conn.commit()
  view=service.view(self.conn,'owner');self.assertTrue(view['reference_ready']);self.assertFalse(view['selfie_ready']);self.assertFalse(view['can_request'])
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


class FaceImageOriginTests(FaceFlowTests):
 """c-facematch: the provider only ever receives image links on an allowed origin."""
 PROD='https://dream-sim-production.up.railway.app'
 def capture(self):
  calls=[]
  class Client:
   def __init__(inner,cfg):pass
   def execute(inner,operation,inputs,**kwargs):
    calls.append(inputs);kwargs['evidence_sink']({'synthetic':True})
    return {'face_match_passed':True,'match_percentage':99,'liveness_checked':False}
  return calls,Client
 def clean_env(self,**extra):
  env={k:v for k,v in os.environ.items() if not k.startswith('RAILWAY_') and k not in ('DHASHU_PUBLIC_API_ORIGIN','DHASHU_PROCESS_ROLE','DATABASE_URL','AUTH_PUBLIC_ORIGIN','ADMIN_PUBLIC_ORIGIN','AUTH_ENABLED')}
  env.update(extra);return patch.dict(os.environ,env,clear=True)
 def test_local_default_sends_only_local_links(self):
  with self.clean_env():
   self.assertEqual(service.face_image_origin(),'http://127.0.0.1:5000')
   service.queue(self.conn,'owner',self.body());calls,Client=self.capture()
   self.assertTrue(service.work_one(self.conn,Client))
  self.assertEqual(len(calls),1)
  for key in ('firstImage','secondImage'):
   self.assertTrue(calls[0][key].startswith('http://127.0.0.1:5000/sandbox/face-image/'),calls[0][key])
  self.assertNotIn('railway.app',str(calls))
 def test_local_refuses_production_origins_and_never_calls_the_provider(self):
  for origin in (self.PROD,self.PROD+'/','https://anything.up.railway.app','https://x.railway.app'):
   with self.subTest(origin=origin),self.clean_env(DHASHU_PUBLIC_API_ORIGIN=origin):
    with self.assertRaisesRegex(ValueError,'production'):service.face_image_origin()
  with self.clean_env(DHASHU_PUBLIC_API_ORIGIN=self.PROD):
   service.queue(self.conn,'owner',self.body());calls,Client=self.capture()
   self.assertTrue(service.work_one(self.conn,Client))
  self.assertEqual(calls,[])  # no provider call at all
  self.assertEqual(service.view(self.conn,'owner')['state'],'unknown')
  lease=db.fetch_all(self.conn,'FaceImageLease')[0];self.assertEqual((lease['revoked'],lease['protected_images']),(1,''))
 def test_origin_must_be_an_origin_only(self):
  for bad in ('ftp://host','http://user:pw@127.0.0.1:5000','http://127.0.0.1:5000/path','http://127.0.0.1:5000?x=1','not a url'):
   with self.subTest(bad=bad),self.clean_env(DHASHU_PUBLIC_API_ORIGIN=bad):
    with self.assertRaises(ValueError):service.face_image_origin()
  with self.clean_env(DHASHU_PUBLIC_API_ORIGIN='https://my-tunnel.example.org'):
   self.assertEqual(service.face_image_origin(),'https://my-tunnel.example.org')
 def test_deployed_keeps_the_legacy_default_and_requires_approval(self):
  with self.clean_env(RAILWAY_ENVIRONMENT='production'):
   self.assertEqual(service.face_image_origin(),self.PROD)  # unchanged behaviour when unset
  with self.clean_env(RAILWAY_ENVIRONMENT='production',DHASHU_PUBLIC_API_ORIGIN='https://evil.example'):
   with self.assertRaisesRegex(ValueError,'Unapproved'):service.face_image_origin()
  with self.clean_env(RAILWAY_ENVIRONMENT='production',DHASHU_PUBLIC_API_ORIGIN='http://127.0.0.1:5000'):
   with self.assertRaisesRegex(ValueError,'Unapproved'):service.face_image_origin()
  with self.clean_env(RAILWAY_ENVIRONMENT='production',DHASHU_PUBLIC_API_ORIGIN='https://api.dhashu.example',DHASHU_APPROVED_PUBLIC_ORIGINS='https://api.dhashu.example'):
   self.assertEqual(service.face_image_origin(),'https://api.dhashu.example')
