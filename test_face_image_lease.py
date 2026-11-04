import base64
import hashlib
import os
from unittest.mock import patch
from cryptography.fernet import Fernet
import db
from bgv_app import Protection
from test_segment_efg_routes import RouteTestCase

class LeaseTests(RouteTestCase):
 def test_link_is_expiring_revocable_and_sandbox_only(self):
  token='a'*64;url='/sandbox/face-image/'+token+'/selfie'
  with patch.dict(os.environ,{'SIGNZY_ENV':'preproduction','SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()}):
   db.insert_row(self.conn,'FaceImageLease',{'id':hashlib.sha256(token.encode()).hexdigest(),'user_id':'owner','protected_images':Protection().seal({'selfie':{'base64':base64.b64encode(b'fixture').decode(),'mime':'image/jpeg'}}),'expires_at':'2099-01-01T00:00:00+00:00','revoked':0})
   r=self.client.get(url);self.assertEqual(r.status_code,200);self.assertEqual(r.data,b'fixture');self.assertIn('no-store',r.headers['Cache-Control'])
   self.assertEqual(self.client.get(url.replace(token,'b'*64)).status_code,404)
   self.assertEqual(self.client.get(url.replace('selfie','unknown')).status_code,404)
   with patch.dict(os.environ,{'SIGNZY_ENV':'production'}):self.assertEqual(self.client.get(url).status_code,404)
   self.conn.execute('UPDATE "FaceImageLease" SET revoked=1');self.conn.commit();self.assertEqual(self.client.get(url).status_code,404)
   self.conn.execute('UPDATE "FaceImageLease" SET revoked=0,expires_at=?',('2000-01-01T00:00:00+00:00',));self.conn.commit();self.assertEqual(self.client.get(url).status_code,404)
