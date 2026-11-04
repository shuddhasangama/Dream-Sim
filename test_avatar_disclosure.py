import io
import os
from unittest.mock import patch
from cryptography.fernet import Fernet
from PIL import Image
import db
import avatar_service as avatars
from test_match_check_routes import MatchCheckRouteTests

class AvatarDisclosureTests(MatchCheckRouteTests):
 def test_only_accepted_avatar_in_profile_match_and_comparison_payload(self):
  with patch.dict(os.environ,{'SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DHASHU_AVATAR_ENABLED':'1'}):
   b=io.BytesIO();Image.new('RGB',(160,200),'green').save(b,'JPEG');photo=avatars.data_url(b.getvalue())
   for uid in ('owner','partner'):
    db.insert_row(self.conn,'AvatarJob',{'id':uid,'state':'ready','protected_options':avatars.Protection().seal({'options':[photo,photo]}),
     'protected_selfie':avatars.Protection().seal({'image':'PRIVATE-ORIGINAL'}),'created_at':avatars.stamp(),'updated_at':avatars.stamp(),'expires_at':'2099-01-01T00:00:00+00:00'})
   mid=self.match('owner','partner');self.set_clock(day='Mon',hour=12)
   self.assertFalse(self.request('/matches/'+mid).json['data']['candidate'].get('avatar'))
   avatars.accept(self.conn,'owner',0);avatars.accept(self.conn,'partner',1)
   personal=self.request('/profile/personal').json['data'];self.assertEqual(personal['photo'],photo)
   match=self.request('/matches/'+mid).json['data'];self.assertEqual(match['candidate']['photo'],photo);self.assertTrue(match['candidate']['avatar'])
   self.assertEqual(match['viewer_avatar']['photo'],photo);self.assertEqual(match['candidate']['avatar_status'],'Verification pending')
   self.assertNotIn('PRIVATE-ORIGINAL',str(match));self.assertEqual(self.request('/matches/'+mid,uid='stranger').status_code,404)
   avatars.clear(self.conn,'partner');self.assertFalse(self.request('/matches/'+mid).json['data']['candidate'].get('avatar'))
