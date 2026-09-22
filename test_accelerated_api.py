"""Real authenticated API reads, isolated SQLite, no provider calls."""
from unittest import mock
import auth_sessions
import db
from test_segment_efg_routes import RouteTestCase, app_module
from test_accelerated_clock import ENV


class AcceleratedApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for uid in ('owner','partner','stranger'):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':'acc-'+uid,'user_id':uid,
                'phone':'+1555000'+str(len(uid))+'111', 'auth_enabled':1,
                'verification_required':1,'verified_phone':1,'created_at':'test'})
        self.headers={uid:{'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
                      for uid in ('owner','partner','stranger')}
        patch=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True})
        patch.start(); self.addCleanup(patch.stop)

    def test_shared_clock_does_not_disclose_or_mutate_pair_data(self):
        self.make_lockin('owner','partner')
        self.make_plan('lock-1',status='confirmed')
        before=list(self.conn.iterdump())
        with mock.patch.dict('os.environ',ENV), mock.patch('accelerated_clock.position',return_value=(1,7,1260)):
            responses=[self.client.get('/api/v1/journey/status',headers=self.headers[uid]) for uid in self.headers]
            for r in responses: self.assertEqual(r.status_code,200,r.json)
            self.assertEqual([r.json['data']['clock'] for r in responses],
                             [{'mode':'simulation','week':1,'day':'Sat','hour':20}]*3)
            stranger=responses[-1].json['data']
            self.assertIsNone(stranger['current_date_plan'])
            self.assertIsNone(stranger['current_lock_in'])
            self.assertTrue(stranger['accelerated_test']['enabled'])
        self.assertEqual(list(self.conn.iterdump()),before)

    def test_manual_clock_denied_while_automatic_run_is_active(self):
        with mock.patch.dict('os.environ',ENV):
            response=self.client.post('/api/v1/simulated-clock',json={'advance_hours':24},headers=self.headers['owner'])
            self.assertEqual(response.status_code,409,response.json)
            self.assertEqual(response.json['error']['code'],'accelerated_clock_active')
            self.assertEqual(self.client.get('/api/v1/journey/status').status_code,401)

    def test_real_time_deployment_ignores_acceleration_setting(self):
        with mock.patch.dict('os.environ',{**ENV,'DHASHU_SIMULATED_CLOCK':'false'}):
            response=self.client.get('/api/v1/journey/status',headers=self.headers['owner'])
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(response.json['data']['clock']['mode'],'real_time')
            self.assertIsNone(response.json['data']['accelerated_test'])
