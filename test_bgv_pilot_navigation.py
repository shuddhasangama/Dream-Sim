from unittest.mock import patch
import bgv_policy
import db
from test_segment_efg_routes import RouteTestCase

class PilotNavigationTests(RouteTestCase):
    def test_assigned_verified_test_profile_can_open_verify(self):
        self.make_user('pilot');self.make_user('other')
        bgv_policy.seed(self.conn);bgv_policy.assign(self.conn,'pilot','IN','BLR','Explicit sandbox pilot')
        with patch.dict('os.environ',{'DHASHU_BGV_POLICY_ENABLED':'1'}):
            self.login('pilot')
            result=self.client.get('/api/v1/journey/status')
            self.assertEqual(result.status_code,200)
            surface=next(s for s in result.json['data']['surfaces'] if s['key']=='verify')
            self.assertTrue(surface['eligible']);self.assertEqual(surface['request']['path'],'/api/v1/verification')
            self.assertEqual(db.fetch_one(self.conn,'User',id='pilot')['bgv_status'],'verified')
            self.login('other')
            result=self.client.get('/api/v1/journey/status')
            surface=next(s for s in result.json['data']['surfaces'] if s['key']=='verify')
            self.assertFalse(surface['eligible'])
