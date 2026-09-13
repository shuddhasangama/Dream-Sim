"""Isolated bearer-only date planning, privacy, retries and web parity."""
import json
import os
from unittest import mock
import ceremony
import date_alignment
import db
import auth_sessions
import planning_service
from test_segment_efg_routes import RouteTestCase, app_module
import test_week_api


class PlanningApiTests(RouteTestCase):
    request = test_week_api.WeekApiTests.request

    def setUp(self):
        super().setUp()
        config = mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True})
        config.start()
        self.addCleanup(config.stop)
        self.headers = {}
        for who in ('owner', 'partner', 'stranger'):
            self.make_user(who)
            db.insert_row(self.conn, 'Account', {'id': who, 'user_id': who, 'email': who+'@test.example',
                'auth_enabled': 1, 'verification_required': 1, 'verified_email': 1, 'created_at': 'test'})
            token = auth_sessions.issue(self.conn, who)
            self.headers[who] = {'Authorization': 'Bearer '+token['access_token']}
        self.set_clock()
        self.make_lockin('owner', 'partner')
        self.base = '/lock-ins/lock-1'
        self.slot = {'day': 'Sat', 'meal_slot': 'dinner'}

    def align(self, uid):
        options = self.request(self.base+'/calendar', uid=uid).json['data']['alignment']['options']
        return self.request(self.base+'/alignment', uid=uid, method='PUT', body={k: options[k][0] if k == 'diet' else [options[k][0]] for k in options})

    def prepare(self):
        for who in ('owner', 'partner'):
            self.assertEqual(self.align(who).status_code, 200)
            r = self.request(self.base+'/availability', uid=who, method='PUT', body={'slots': [self.slot]})
            self.assertEqual(r.status_code, 200, r.json)
        r = self.request(self.base+'/date-plan', method='POST', body=self.slot)
        self.assertEqual(r.status_code, 200, r.json)
        return '/date-plans/'+r.json['data']['id']

    def step(self, path, who, step, **body):
        return self.request(path+'/agreement/steps', uid=who, method='POST', body={'step': step, **body})

    def test_complete_two_actor_flow_and_exact_retries(self):
        path = self.prepare()
        self.assertEqual(self.request(self.base+'/date-plan', method='POST', body=self.slot).json['data']['id'], path.split('/')[-1])
        self.assertEqual(len(db.fetch_all(self.conn, 'DatePlan')), 1)
        with mock.patch.dict(os.environ, {'BETA_DATE_SIMULATION_ENABLED': '1'}), mock.patch.object(app_module.dateplan, 'verify_face', return_value=True):
            for who in ('owner', 'partner'):
                self.assertEqual(self.step(path, who, 'face').status_code, 409)
                self.assertEqual(self.step(path, who, 'playbook').status_code, 200)
                self.assertEqual(self.step(path, who, 'playbook').json['data']['step'], 'sign')
                self.assertEqual(self.step(path, who, 'sign', signed_name='Private '+who, acks=list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))).status_code, 200)
                self.assertEqual(self.step(path, who, 'face').json['data']['step'], 'done')
                before = list(self.conn.iterdump())
                self.assertEqual(self.step(path, who, 'face').status_code, 200)
                self.assertEqual(list(self.conn.iterdump()), before)
        result = self.request(path).json['data']
        self.assertEqual(result['status'], 'confirmed')
        self.assertTrue(result['my_signed'] and result['partner_signed'])
        self.assertEqual(len(db.fetch_all(self.conn, 'Signature')), 2)
        self.assertNotIn('Private partner', json.dumps(self.request(path+'/agreement').json))

    def test_reads_are_read_only_and_foreign_resources_are_hidden(self):
        path = self.prepare()
        before = list(self.conn.iterdump())
        for route in (self.base+'/calendar', path, path+'/agreement'):
            self.assertEqual(self.request(route).status_code, 200)
            self.assertEqual(self.request(route, uid='stranger').status_code, 404)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_alignment_and_overlap_are_required(self):
        self.assertEqual(self.request(self.base+'/date-plan', method='POST', body=self.slot).json['error']['code'], 'alignment_required')
        for who in ('owner', 'partner'):
            self.align(who)
        r = self.request(self.base+'/date-plan', method='POST', body=self.slot)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(len(db.fetch_all(self.conn, 'DatePlan')), 0)

    def test_strict_json_slots_and_fields(self):
        for slots in ([{'day': 'Fri', 'meal_slot': 'breakfast'}], [self.slot, self.slot], ['Sat'], {}, [{'day': ['Sat'], 'meal_slot': 'dinner'}]):
            self.assertEqual(self.request(self.base+'/availability', method='PUT', body={'slots': slots}).status_code, 400)
        self.assertEqual(self.request(self.base+'/availability', method='PUT', body={'slots': [], 'user_id': 'partner'}).status_code, 400)
        self.assertEqual(self.request(self.base+'/alignment', method='PUT', body={'budget': {}, 'diet': [], 'cuisine': 1}).status_code, 400)

    def test_payment_is_required_and_never_granted_by_api(self):
        with mock.patch.dict(os.environ, {'PAYMENTS_ENABLED': '1'}):
            self.assertFalse(self.request(self.base+'/calendar').json['data']['payment']['satisfied'])
            r = self.request(self.base+'/availability', method='PUT', body={'slots': [self.slot]})
            self.assertEqual(r.status_code, 403)
            self.assertEqual(db.fetch_all(self.conn, 'Payment'), [])

    def test_face_simulation_is_opt_in_and_acks_cannot_be_skipped(self):
        path = self.prepare()
        self.assertEqual(self.step(path, 'owner', 'playbook').status_code, 200)
        self.assertEqual(self.step(path, 'owner', 'sign', signed_name='Name', acks=[]).status_code, 400)
        self.assertEqual(self.step(path, 'owner', 'sign', signed_name='Name', acks=list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))).status_code, 200)
        with mock.patch.dict(os.environ, {'BETA_DATE_SIMULATION_ENABLED': '0'}):
            self.assertEqual(self.step(path, 'owner', 'face').status_code, 403)
        self.assertEqual(db.fetch_all(self.conn, 'Signature'), [])

    def test_plan_freezes_inputs_and_rejects_different_confirmation(self):
        path = self.prepare()
        before = list(self.conn.iterdump())
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED':False}):
            self.login('owner')
            self.assertEqual(self.client.post('/calendar/no-overlap',data={'choice':'next_weekend'}).status_code,409)
        self.assertEqual(list(self.conn.iterdump()),before)
        self.assertEqual(self.align('owner').status_code, 409)
        self.assertEqual(self.request(self.base+'/availability', method='PUT', body={'slots': []}).status_code, 409)
        self.assertEqual(self.request(self.base+'/date-plan', method='POST', body={'day': 'Sun', 'meal_slot': 'dinner'}).status_code, 409)
        self.assertEqual(self.request(path+'/selections', method='PUT', body={'dietary': 'Vegan', 'dress': 'Casual'}).status_code, 200)
        self.step(path, 'partner', 'playbook')
        self.step(path, 'partner', 'sign', signed_name='Name', acks=list(ceremony.ack_keys(ceremony.DATE_AGREEMENT)))
        self.assertEqual(self.request(path+'/selections', method='PUT', body={'dietary': '', 'dress': ''}).status_code, 409)

    def test_availability_rolls_back_on_insert_failure(self):
        self.request(self.base+'/availability', method='PUT', body={'slots': [self.slot]})
        before = list(self.conn.iterdump())
        with mock.patch.object(planning_service, 'save', side_effect=RuntimeError('write failed')):
            with self.assertRaises(RuntimeError):
                planning_service.availability(self.conn, 'owner', 'lock-1', [{'day': 'Sun', 'meal_slot': 'lunch'}])
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_html_uses_same_overlap_validation(self):
        for who in ('owner', 'partner'):
            self.align(who)
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': False}):
            self.login('owner')
            r = self.client.post('/calendar/confirm', data=self.slot)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(db.fetch_all(self.conn, 'DatePlan'), [])

    def test_foreign_mutations_and_closed_resources_cannot_change_state(self):
        path = self.prepare()
        before = list(self.conn.iterdump())
        for route, method, body in (
            (self.base+'/availability','PUT',{'slots': [self.slot]}),
            (self.base+'/date-plan','POST',self.slot),
            (path+'/selections','PUT',{'dietary':'x','dress':'x'}),
            (path+'/agreement/steps','POST',{'step':'playbook'})):
            self.assertEqual(self.request(route, uid='stranger', method=method, body=body).status_code,404)
        self.assertEqual(list(self.conn.iterdump()),before)
        self.conn.execute('UPDATE DatePlan SET status=?',('cancelled',))
        self.conn.commit()
        self.assertEqual(self.step(path,'owner','playbook').status_code,409)

    def test_web_signature_and_api_signature_share_confirmation(self):
        path = self.prepare()
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED':False}), mock.patch.object(app_module.dateplan,'verify_face',return_value=True):
            self.login('owner')
            self.assertEqual(self.client.post('/plan/sign',data={key:'on' for key in ceremony.ack_keys(ceremony.DATE_AGREEMENT)}).status_code,302)
        self.assertTrue(self.request(path).json['data']['my_signed'])
        with mock.patch.dict(os.environ, {'BETA_DATE_SIMULATION_ENABLED':'1'}), mock.patch.object(app_module.dateplan,'verify_face',return_value=True):
            self.step(path,'partner','playbook')
            self.step(path,'partner','sign',signed_name='Partner',acks=list(ceremony.ack_keys(ceremony.DATE_AGREEMENT)))
            self.assertEqual(self.step(path,'partner','face').status_code,200)
        self.assertEqual(self.request(path).json['data']['status'],'confirmed')

    def test_json_media_auth_and_invalid_step_types(self):
        path = self.prepare()
        self.assertEqual(self.client.get('/api/v1'+path).status_code,401)
        r=self.client.put('/api/v1'+self.base+'/availability',data='slots=[]',headers=self.headers['owner'])
        self.assertEqual(r.status_code,415)
        for value in ([],{},None,123):
            self.assertEqual(self.step(path,'owner',value).status_code,400)
        self.assertEqual(self.request(path).headers['Cache-Control'],'no-store')
