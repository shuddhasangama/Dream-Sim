"""Invited enrollment uses real auth boundaries with provider calls mocked locally."""
from unittest import mock
import db, auth_delivery, enrollment_service as service, onboarding
from test_segment_efg_routes import RouteTestCase, app_module


def sections():
    stats = {k:low for k,_l,_u,low,_hi,_p in onboarding.NUMERIC_STATS}
    stats.update({k:opts[0] for k,_l,opts in onboarding.CHOICE_STATS})
    stats.update(city='Bangalore',gender='female',salary=1500000)
    return {'vision': {'intimacy_kinds':['Emotional'],'other_keys':['Cohabitate'],
        # round3-fixes-spec.md §7.1: no travel_style array any more.
        'cohabit_focus':[onboarding.COHABIT_FOCUS[0]],'kids_route':[]},
        'stats': stats, 'activities': {k:'good' for k in onboarding.ACTIVITIES[:4]}}


class EnrollmentApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for patch in (mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True}),
                mock.patch.object(auth_delivery,'configured',return_value=True),
                mock.patch.object(auth_delivery,'start',return_value='VE'+'a'*32),
                mock.patch.object(auth_delivery,'check',return_value=True)):
            patch.start();self.addCleanup(patch.stop)
        self.uid=service.invite(self.conn,'invite@example.test',apply=True)['user_id']
        r=self.client.post('/api/v1/auth/request',json={'channel':'email','destination':'invite@example.test'})
        self.assertEqual(r.status_code,202,r.json)
        r=self.client.post('/api/v1/auth/verify',json={'challenge_id':r.json['data']['challenge_id'],'code':'123456'})
        self.assertEqual(r.status_code,200,r.json)
        self.headers={'Authorization':'Bearer '+r.json['data']['access_token']}
    def read(self):
        return self.client.get('/api/v1/enrollment',headers=self.headers)
    def put(self,key,value,revision):
        return self.client.put('/api/v1/enrollment/sections/'+key,json={'revision':revision,'values':value},headers=self.headers)
    def complete(self,revision):
        return self.client.post('/api/v1/enrollment/complete',json={'revision':revision},headers=self.headers)
    def test_otp_bound_draft_resume_submit_and_no_verification_bypass(self):
        self.assertEqual(self.read().json['data']['status'],'draft')
        self.assertEqual(self.complete(0).status_code,409)
        for rev,(key,value) in enumerate(sections().items()):
            r=self.put(key,value,rev);self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(self.put(key,value,rev).status_code,200)
        self.assertEqual(self.read().json['data']['revision'],3)
        r=self.complete(3);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.complete(3).json,r.json)
        self.assertEqual(r.json['data']['bgv_status'],'pending')
        self.assertNotIn('salary',r.json['data']['draft']['stats'])
        self.assertEqual(db.fetch_one(self.conn,'User',id=self.uid)['journey_state'],'onboarding')
        self.assertEqual(self.client.post('/api/v1/week/prepare',json={},headers=self.headers).status_code,403)
        self.assertEqual(self.put('activities',sections()['activities'],4).status_code,409)
        self.assertEqual(self.client.post('/verify/simulate',headers=self.headers).status_code,404)
    def test_foreign_binding_unknown_fields_and_stale_writes(self):
        self.assertEqual(self.client.get('/api/v1/enrollment').status_code,401)
        self.assertEqual(self.put('vision',sections()['vision'],0).status_code,200)
        self.assertEqual(self.put('stats',sections()['stats'],0).status_code,409)
        self.assertEqual(self.put('stats',{**sections()['stats'],'user_id':'someone'},1).status_code,400)
        for bad in (True,float('inf'),1.2,10**400):
            r=self.put('stats',{**sections()['stats'],'age':bad},1);self.assertEqual(r.status_code,400,r.json)
        self.assertEqual(self.put('vision',{**sections()['vision'],'intimacy_kinds':[{}]},1).status_code,400)
    def test_invite_collision_and_dry_run_do_not_create_an_identity(self):
        before=list(self.conn.iterdump())
        self.assertFalse(service.invite(self.conn,'new@example.test')['applied'])
        with self.assertRaises(ValueError):service.invite(self.conn,'INVITE@example.test',apply=True)
        self.assertEqual(before,list(self.conn.iterdump()))
    def test_simulation_sign_in_cannot_use_secure_enrollment(self):
        with mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':False}):
            self.login(self.uid)
            r=self.read()
            self.assertEqual(r.status_code,403,r.json)
            self.assertEqual(r.json['error']['code'],'secure_auth_required')
    def test_unverified_or_disabled_account_cannot_write(self):
        self.conn.execute('UPDATE Account SET verified_email=0');self.conn.commit()
        self.assertEqual(self.put('vision',sections()['vision'],0).status_code,403)
        self.conn.execute('UPDATE Account SET auth_enabled=0');self.conn.commit()
        self.assertEqual(self.read().status_code,401)
    def test_completion_rolls_back_profile_if_draft_receipt_fails(self):
        for rev,(key,value) in enumerate(sections().items()):self.assertEqual(self.put(key,value,rev).status_code,200)
        before=list(self.conn.iterdump());original=service.save
        def failing(conn,table,row):
            if table=='EnrollmentDraft':raise RuntimeError('injected')
            return original(conn,table,row)
        with mock.patch.object(service,'save',side_effect=failing),self.assertRaises(RuntimeError):service.write(self.conn,self.uid,3)
        self.assertEqual(before,list(self.conn.iterdump()))
