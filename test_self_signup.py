"""Fresh-account OTP → saved signup → supported market; no real messages/provider IO."""
import json
import os
import uuid
from unittest.mock import patch
from cryptography.fernet import Fernet
import db
import auth_delivery
import onboarding
import self_signup
from test_segment_efg_routes import RouteTestCase,app_module

class SelfSignupTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for p in [patch.dict(app_module.app.config,{'AUTH_ENABLED':True}),patch.dict(os.environ,{'SIGNZY_ENV':'preproduction','DHASHU_BILLING_MODE':'disabled','SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()}),patch.object(auth_delivery,'configured',return_value=True),patch.object(auth_delivery,'start',side_effect=lambda *args:'VE'+uuid.uuid4().hex),patch.object(auth_delivery,'check',return_value=True)]:p.start();self.addCleanup(p.stop)
    def signup(self,phone='+919000000001'):
        r=self.client.post('/api/v1/auth/signup/request',json={'channel':'phone','destination':phone})
        self.assertEqual(r.status_code,202,r.json)
        r=self.client.post('/api/v1/auth/verify',json={'challenge_id':r.json['data']['challenge_id'],'code':'123456'})
        self.assertEqual(r.status_code,200,r.json)
        return r.json['data']['user_id'],{'Authorization':'Bearer '+r.json['data']['access_token']}
    def stats(self,city='Bangalore'):
        return {'name':'SYNTHETIC PERSON','dob':'1990-01-01','gender':'female','city':city,'fields':{'religion':onboarding.STAT_OPTIONS['religion'][:2],'employment_category':'Self-employed'},'health':{'disclosure':'undisclosed','categories':[],'note':'','consent':False}}
    def test_no_account_until_approved_otp_and_contact_resume_not_duplicate(self):
        r=self.client.post('/api/v1/auth/signup/request',json={'channel':'phone','destination':'+919000000001'})
        self.assertIsNone(db.fetch_one(self.conn,'Account',phone='+919000000001'))
        challenge=r.json['data']['challenge_id']
        with patch.object(auth_delivery,'check',return_value=False):self.assertEqual(self.client.post('/api/v1/auth/verify',json={'challenge_id':challenge,'code':'000000'}).status_code,401)
        self.assertIsNone(db.fetch_one(self.conn,'Account',phone='+919000000001'))
        response=self.client.post('/api/v1/auth/verify',json={'challenge_id':challenge,'code':'123456'})
        uid=response.json['data']['user_id']
        self.assertTrue(db.fetch_one(self.conn,'Account',user_id=uid)['verified_phone'])
        self.assertEqual(self.client.post('/api/v1/auth/verify',json={'challenge_id':challenge,'code':'123456'}).status_code,401)
        headers={'Authorization':'Bearer '+response.json['data']['access_token']}
        for path in ['/api/v1/profile','/api/v1/journey/status','/api/v1/signup/state']:
            self.assertEqual(self.client.get(path,headers=headers).status_code,200,path)
    def test_distinct_phone_accounts_and_repeat_signup_preserve_owner(self):
        import auth_sessions
        uid,h=self.signup('+919000000001')
        other,other_headers=self.signup('+919000000002')
        self.assertNotEqual(uid,other)
        self.assertEqual(self.client.get('/api/v1/profile',headers=h).json['data']['user_id'],uid)
        self.assertEqual(self.client.get('/api/v1/profile',headers=other_headers).json['data']['user_id'],other)
        with patch.object(auth_sessions,'throttle',return_value=True):
            again,again_headers=self.signup('+919000000001')
        self.assertEqual(again,uid)
        self.assertEqual(self.client.get('/api/v1/profile',headers=again_headers).json['data']['user_id'],uid)
        self.assertEqual(len([a for a in db.fetch_all(self.conn,'Account') if a.get('phone')=='+919000000001']),1)

    def test_real_signup_never_displays_simulation_name(self):
        uid,h=self.signup()
        journey=self.client.get('/api/v1/journey/status',headers=h).json['data']
        self.assertEqual(journey['user']['display_name'],'Your profile')
        self.assertEqual(self.client.put('/api/v1/signup/stats',headers=h,json=self.stats()).status_code,200)
        journey=self.client.get('/api/v1/journey/status',headers=h).json['data']
        self.assertEqual(journey['user']['display_name'],self.stats()['name'])
        with app_module.app.test_request_context('/'):
            from unittest.mock import patch
            with patch.object(app_module,'get_db',return_value=self.conn):
                self.assertEqual(app_module.with_view_fields({'user_id':uid,'gender':'male','stats':{'signup_version':3}})['name'],'Member')

    def test_three_cities_only_auto_plan_and_saved_resume(self):
        for i,city in enumerate(['Bangalore','Delhi','Mumbai']):
            uid,h=self.signup('+91900000000'+str(i+1))
            r=self.client.put('/api/v1/profile/vision/template',headers=h,json={'schema_version':2,'template':'explore','pillars':{'Intimacy':['Emotional'],'Travel together':[]}})
            self.assertEqual(r.status_code,200,r.json)
            r=self.client.put('/api/v1/signup/stats',headers=h,json=self.stats(city))
            self.assertEqual(r.status_code,200,r.json)
            data=self.client.get('/api/v1/signup/state',headers=h).json['data']
            self.assertEqual(data['next_step'],2);self.assertEqual(data['values']['city'],city)
            row=db.fetch_one(self.conn,'User',id=uid);self.assertTrue(row['active_bgv_case_id'])
            case=db.fetch_one(self.conn,'BgvCase',id=row['active_bgv_case_id'])
            self.assertEqual(case['city_code'],['BLR','DEL','BOM'][i])
            self.assertNotIn('SYNTHETIC PERSON',row['stats_json'])
            r=self.client.put('/api/v1/signup/stats',headers=h,json=self.stats('Chennai'))
            self.assertEqual(r.status_code,400,r.json)
            self.assertEqual(self.client.post('/api/v1/signup/complete',headers=h,json={}).status_code,409)
    def test_optional_claims_health_consent_and_religion_cap(self):
        uid,h=self.signup();body=self.stats()
        body['fields']['religion']=onboarding.STAT_OPTIONS['religion'][:3]
        self.assertEqual(self.client.put('/api/v1/signup/stats',headers=h,json=body).status_code,400)
        body=self.stats();body['health'].update(disclosure='shared',categories=['mobility'])
        self.assertEqual(self.client.put('/api/v1/signup/stats',headers=h,json=body).status_code,400)
        body['health']['consent']=True
        self.assertEqual(self.client.put('/api/v1/signup/stats',headers=h,json=body).status_code,200)
        self.assertTrue(json.loads(db.fetch_one(self.conn,'User',id=uid)['stats_json'])['health_shared']['consent'])
        self.assertEqual(self.client.get('/api/v1/signup/state').status_code,401)
        self.assertEqual(json.loads(db.fetch_one(self.conn,'User',id=uid)['preferences_json'])['adjustable'],{'distance_km':[0,30]})
    def test_matching_admission_requires_current_bound_evidence_not_otp_or_claims(self):
        from bgv_app import Protection
        import verified_identity,auth_sessions
        uid,h=self.signup()
        self.client.put('/api/v1/profile/vision/template',headers=h,json={'schema_version':2,'template':'explore','pillars':{'Intimacy':['Emotional'],'Travel together':[]}})
        self.client.put('/api/v1/signup/stats',headers=h,json=self.stats())
        picks={name:'good' for name in onboarding.ACTIVITIES[:4]}
        self.client.put('/api/v1/profile/chemistry/activities',headers=h,json={'activities':picks})
        self.assertEqual(self.client.post('/api/v1/signup/complete',headers=h,json={}).status_code,409)
        user=db.fetch_one(self.conn,'User',id=uid)
        checks={r['check_definition_id']:r['id'] for r in db.fetch_all(self.conn,'BgvCaseCheck',case_id=user['active_bgv_case_id'])}
        sid=str(uuid.uuid4());identity={'name':'CONFIRMED SYNTHETIC NAME','dob':'1990-01-01','age':36,'age_as_of':'2026-11-05'}
        db.insert_row(self.conn,'DigiLockerSession',{'id':sid,'user_id':uid,'environment':'preproduction','state':'complete','case_check_id':checks['identity_details'],'protected_result':Protection().seal(identity),'consent_version':'synthetic','created_at':'2026-11-05','updated_at':'2026-11-05','expires_at':'2099-01-01'})
        with auth_sessions.transaction(self.conn):verified_identity.apply(self.conn,uid,sid,identity,'preproduction')
        r=self.client.post('/api/v1/signup/complete',headers=h,json={});self.assertEqual(r.status_code,200,r.json)
        self.assertFalse(r.json['data']['admitted'])
        db.insert_row(self.conn,'LivenessSession',{'id':uid,'flow_id':str(uuid.uuid4()),'state':'matched','digilocker_session_id':sid,'next_fetch_at':'2026-11-05','consent_version':'synthetic','consent_at':'2026-11-05','created_at':'2026-11-05','updated_at':'2026-11-05','capture_until':'2099-01-01','expires_at':'2099-01-01'})
        for operation,key in [('individual_result','criminal_court'),('fir_result','fir')]:
            db.insert_row(self.conn,'BgvRequest',{'id':str(uuid.uuid4()),'user_id':uid,'operation':operation,'environment':'preproduction','case_check_id':checks[key],'state':'verified','protected_input':Protection().seal({'synthetic':True}),'created_at':'2026-11-05','updated_at':'2026-11-05'})
        r=self.client.get('/api/v1/signup/state',headers=h)
        self.assertTrue(r.json['data']['admitted'],r.json)
        user=db.fetch_one(self.conn,'User',id=uid)
        self.assertEqual((user['journey_state'],user['bgv_status']),('dating','verified'))
