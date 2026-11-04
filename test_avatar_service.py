import base64
import io
import os
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from PIL import Image
from cryptography.fernet import Fernet
import auth_sessions
import avatar_service as service
import db
from api_contract import ApiError
from test_segment_efg_routes import RouteTestCase

class AvatarTests(RouteTestCase):
 def setUp(self):
  super().setUp();self.make_user('owner');self.make_user('other')
  p=patch.dict(os.environ,{'DHASHU_AVATAR_ENABLED':'1','OPENAI_API_KEY':'synthetic','SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()});p.start();self.addCleanup(p.stop)
  b=io.BytesIO();Image.new('RGB',(160,200),'blue').save(b,'JPEG');self.image=service.data_url(b.getvalue())
 def queue(self):
  service.capture(self.conn,'owner',self.image);service.queue(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
 def test_one_run_and_acceptance_public_only(self):
  self.queue();calls=[]
  def provider(key,selfie):calls.append(selfie);return [self.image,self.image]
  self.assertTrue(service.work_one(self.conn,provider));self.assertEqual(len(calls),1)
  self.assertFalse(service.work_one(self.conn,provider));self.assertEqual(service.public(self.conn,'owner'),{})
  service.accept(self.conn,'owner',1);self.assertEqual(service.public(self.conn,'owner')['avatar_status'],'Verification pending')
  self.assertEqual(service.public(self.conn,'other'),{})
  with self.assertRaises(ApiError):service.capture(self.conn,'owner',self.image)
  service.clear(self.conn,'owner');self.assertEqual(service.public(self.conn,'owner'),{})
  with self.assertRaises(ApiError):service.capture(self.conn,'owner',self.image)
 def test_consent_and_duplicate_queue(self):
  service.capture(self.conn,'owner',self.image)
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',{})
  self.assertEqual(service.row(self.conn,'owner')['state'],'draft')
  service.queue(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
  with self.assertRaises(ApiError):service.queue(self.conn,'owner',{'consent':True,'consent_version':service.VERSION})
 def test_unknown_outcome_never_replayed(self):
  self.queue()
  def fail(*args):raise TimeoutError()
  service.work_one(self.conn,fail);self.assertEqual(service.row(self.conn,'owner')['state'],'unknown')
  self.assertFalse(service.work_one(self.conn,lambda *args:self.fail('paid replay')))
 def test_stale_claim_and_expiry(self):
  self.queue()
  with auth_sessions.transaction(self.conn):auth_sessions.sql(self.conn,'UPDATE "AvatarJob" SET state=?,updated_at=? WHERE id=?',('submitting','2000-01-01T00:00:00+00:00','owner'))
  service.work_one(self.conn,lambda *a:self.fail('replay'));self.assertEqual(service.row(self.conn,'owner')['state'],'unknown')
  with auth_sessions.transaction(self.conn):auth_sessions.sql(self.conn,'UPDATE "AvatarJob" SET expires_at=? WHERE id=?',('2000-01-01T00:00:00+00:00','owner'))
  service.work_one(self.conn);self.assertIsNone(service.row(self.conn,'owner')['protected_selfie'])
 def test_provider_uses_only_selfie_and_low_quality(self):
  import json
  raw=base64.b64decode(self.image.split(',')[1]);response=__import__('unittest').mock.MagicMock()
  response.__enter__.return_value.read.return_value=json.dumps({'data':[{'b64_json':base64.b64encode(raw).decode()}]*2}).encode()
  with patch('avatar_service.urllib.request.urlopen',return_value=response) as call:
   service.generate('synthetic',raw)
   payload=json.loads(call.call_args.args[0].data)
  self.assertEqual(len(payload['images']),1);self.assertEqual(payload['n'],2);self.assertEqual(payload['quality'],'low');self.assertEqual(payload['model'],'gpt-image-2')
  self.assertNotIn('aadhaar',json.dumps(payload).lower())

class AvatarRouteTests(AvatarTests):
 def test_authenticated_owner_api(self):
  import test_week_api
  import app as app_module
  with patch.dict(app_module.app.config,{'AUTH_ENABLED':True}):
   for uid in ('owner','other'):
    db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'auth_enabled':1,'verified_email':1,'email':uid+'@test.example','created_at':'test'})
   headers={'Authorization':'Bearer '+auth_sessions.issue(self.conn,'owner')['access_token']}
   other={'Authorization':'Bearer '+auth_sessions.issue(self.conn,'other')['access_token']}
   with self.client as client:
    self.assertEqual(client.get('/api/v1/profile/avatar').status_code,401)
    self.assertEqual(client.post('/api/v1/profile/avatar/selfie',headers=headers,json={'image':self.image}).status_code,200)
    self.assertEqual(client.post('/api/v1/profile/avatar/generate',headers=headers,json={'consent':True,'consent_version':service.VERSION}).status_code,200)
    self.assertEqual(client.get('/api/v1/profile/avatar',headers=other).json['data']['state'],'not_started')
    self.assertEqual(client.post('/api/v1/profile/avatar/accept',headers=other,json={'index':0}).status_code,409)
    self.assertEqual(client.post('/api/v1/profile/avatar/generate',headers=headers,json={'consent':True,'consent_version':service.VERSION}).status_code,409)
