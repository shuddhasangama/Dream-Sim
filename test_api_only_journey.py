"""One continuous bearer API journey, no HTML actions or inter-step DB mutation.

Only approved synthetic profiles and controllable simulation time are fixtures.
OTP provider and explicitly enabled face simulation never contact real services.
Enrollment pending-review boundary is exercised separately: no fake BGV API.
"""
import os
from unittest import mock
import db, onboarding, ceremony, chemistry, guru_dating, auth_delivery
from test_segment_efg_routes import RouteTestCase, app_module
from test_enrollment_api import sections


class ApiOnlyJourneyTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.setup_profiles()

    def setup_profiles(self):
        for p in (mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True}),
                mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}),
                mock.patch.object(auth_delivery,'configured',return_value=True),
                mock.patch.object(auth_delivery,'start',return_value='VE'+'b'*32),
                mock.patch.object(auth_delivery,'check',return_value=True)):
            p.start();self.addCleanup(p.stop)
        self.headers={};self.tokens={}
        for uid in ('owner','partner','stranger'):
            data=sections();stats=onboarding.validate_stats(data['stats'])['stats']
            stats.update(age=30,height_cm=170,profession=onboarding.STAT_OPTIONS['profession'][0],
                education=onboarding.STAT_OPTIONS['education'][0],marital_history=onboarding.STAT_OPTIONS['marital_history'][0],languages=[onboarding.STAT_OPTIONS['languages'][0]])
            row=onboarding.build_user_row(uid,'Bangalore','male' if uid=='partner' else 'female',stats,
                onboarding.build_visions(**data['vision']),data['activities'],journey_state='dating' if uid!='stranger' else 'onboarding',bgv_status='verified')
            row['preferences_json']=db.json_field({'fixed':{'dealbreakers':[]},'adjustable':{'distance_km':[0,5000]}})
            db.insert_row(self.conn,'User',row)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'email':uid+'@example.test','auth_enabled':1,'verification_required':1,'created_at':'test'})
        self.set_clock(week=1,day='Mon',hour=12)
    def call(self,path,body=None,uid='owner',method='GET',expected=200):
        r=self.client.open('/api/v1'+path,method=method,json=body,headers=self.headers.get(uid,{}))
        self.assertEqual(r.status_code,expected,(path,r.json))
        self.assertTrue(r.is_json);self.assertEqual(r.headers['Cache-Control'],'no-store')
        return r.json['data']
    def post(self,path,body=None,uid='owner',expected=200):
        return self.call(path,{} if body is None else body,uid,'POST',expected)
    def sign(self,path,kind,uid):
        for body in ({'step':'playbook'},{'step':'sign','signed_name':uid,'acks':list(ceremony.ack_keys(kind))},{'step':'face'}):self.post(path,body,uid)
    def test_two_dates_gate_road_married_and_revoked_tokens(self):
        for uid in ('owner','partner','stranger'):
            challenge=self.post('/auth/request',{'channel':'email','destination':uid+'@example.test'},uid,202)
            tokens=self.post('/auth/verify',{'challenge_id':challenge['challenge_id'],'code':'123456'},uid)
            self.tokens[uid]=tokens;self.headers[uid]={'Authorization':'Bearer '+tokens['access_token']}
            self.assertEqual(self.call('/me',uid=uid)['user_id'],uid)
        self.call('/reach')
        matches={}
        for uid in ('owner','partner'):
            week=self.post('/week/prepare',uid=uid)
            self.assertEqual(len(week['matches']),1)
            matches[uid]=week['matches'][0]['id']
        for uid in ('owner','partner'):
            self.post('/matches/'+matches[uid]+'/actions',{'action':'interest'},uid)
        lid=self.call('/lock-ins/current')['lock_in']['id'];base='/lock-ins/'+lid
        self.call(base+'/calendar',uid='stranger',expected=404)
        plans=[]
        for cycle in (1,2):
            self.set_clock(week=cycle,day='Mon',hour=12)
            for uid in ('owner','partner'):
                options=self.call(base+'/calendar',uid=uid)['alignment']['options']
                values={k:v[0] if k=='diet' else [v[0]] for k,v in options.items()}
                self.call(base+'/alignment',values,uid,'PUT')
                self.call(base+'/availability',{'slots':[{'day':'Sat','meal_slot':'dinner'}]},uid,'PUT')
            plan=self.post(base+'/date-plan',{'day':'Sat','meal_slot':'dinner','cycle':cycle})
            path='/date-plans/'+plan['id'];plans.append(plan['id'])
            for uid in ('owner','partner'):self.sign(path+'/agreement/steps',ceremony.DATE_AGREEMENT,uid)
            self.call(path+'/feedback/flags',{'green_flags':guru_dating.GREEN_FLAGS[:2],'red_flags':[]},method='PUT',expected=409)
            self.set_clock(week=cycle,day='Sat',hour=21)
            for uid in ('partner','owner'):
                self.call(path+'/feedback/flags',{'green_flags':guru_dating.GREEN_FLAGS[:2],'red_flags':[]},uid,'PUT')
                self.post(path+'/feedback/decision',{'decision':'continue'},uid)
            self.post(path+'/feedback/decision',{'decision':'continue'})
            self.assertEqual(self.call('/lock-ins/current')['lock_in']['dates_completed'],cycle)
        self.assertNotEqual(*plans)
        self.call(base+'/after-date')
        for uid in ('owner','partner'):
            self.post('/profile/vision/details',{'request_id':'entry','pillar':'Kids','sub_selection':'Adoption'},uid)
            self.call('/profile/chemistry/entries/intimacy_pace',{'value':'slow'},uid,'PUT')
        self.set_clock(week=3,day='Mon',hour=12)
        for uid in ('owner','partner'):
            for key in (*chemistry.MANDATORY_KEYS,*chemistry.INTIMACY_MANDATORY_KEYS):
                value='namaste' if key=='physical_boundary' else 'slow' if key=='intimacy_pace' else 'yes'
                self.call('/profile/chemistry/entries/'+key,{'value':value},uid,'PUT')
        self.post(base+'/gate/raise')
        self.post(base+'/gate/ask',{'round':1,'question_keys':['exclusivity_check']})
        for uid in ('owner','partner'):self.post(base+'/gate/answer',{'round':1,'question_key':'exclusivity_check','value':'exclusive'},uid)
        self.post(base+'/gate/confirm',{'round':1},expected=409)
        self.set_clock(week=3,day='Wed',hour=12)
        for uid in ('owner','partner'):
            self.post(base+'/gate/confirm',{'round':1},uid)
            self.post(base+'/gate/exclusivity-ack',{'round':1,'acknowledged':True},uid)
        for uid in ('owner','partner'):self.sign(base+'/agreements/relationship_entry/steps',ceremony.RELATIONSHIP_ENTRY,uid)
        self.post(base+'/gate/enter-relationship',{'round':1})
        cid=self.call('/dashboard')['current_couple']['id'];couple='/couples/'+cid
        self.call(couple,uid='stranger',expected=404)
        for uid in ('owner','partner'):
            self.post(couple+'/road/routine',{'request_id':'routine','category':'free','days':['Thu'],'label':'Time','start':'18:00','end':'20:00'},uid)
            self.call(couple+'/road/sharing',{'slots':[{'day':'Thu','start':'18:00','end':'20:00'}]},uid,'PUT')
        self.assertTrue(self.call(couple+'/road')['overlap'])
        for stage in ('relationship','engaged'):
            path=couple+'/checkpoints/'+stage
            self.sign(path+'/steps',ceremony.STAGE_GATE,'owner')
            self.post(path+'/advance',expected=409)
            self.sign(path+'/steps',ceremony.STAGE_GATE,'partner')
            self.post(path+'/advance');self.post(path+'/advance')
        self.assertEqual(self.call('/me')['journey_state'],'married')
        for uid in ('owner','partner'):
            tokens=self.post('/auth/refresh',{'refresh_token':self.tokens[uid]['refresh_token']},uid)
            self.headers[uid]={'Authorization':'Bearer '+tokens['access_token']}
            self.post('/auth/logout-all',uid=uid)
            self.call('/profile',uid=uid,expected=401)
            self.post('/auth/refresh',{'refresh_token':tokens['refresh_token']},uid,401)
