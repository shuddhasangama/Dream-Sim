"""Owned post-Dating actions, private ROAD, mutual transitions and exit."""
import os
from unittest import mock
import auth_sessions,db,journey,ceremony
import relationship_service as service
import test_week_api
from test_segment_efg_routes import RouteTestCase,app_module


class RelationshipApiTests(RouteTestCase):
    request=test_week_api.WeekApiTests.request
    def setUp(self):
        super().setUp()
        p=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True});p.start();self.addCleanup(p.stop)
        self.headers={}
        for uid in ('owner','partner','stranger'):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'email':uid+'@test.example','auth_enabled':1,'created_at':'test'})
            self.headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
        journey.advance_stage(self.conn,'pair',True,True,today='2026-01-05',user_a_id='owner',user_b_id='partner')
        self.base='/couples/pair'
        self.set_clock(week=1,day='Mon',hour=12)
    def post(self,path,body=None,uid='owner'):
        return self.request(path,method='POST',body=body or {},uid=uid)
    def sign(self,source,uid):
        with mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}):
            for body in ({'step':'playbook'},{'step':'sign','signed_name':uid,'acks':list(ceremony.ack_keys(ceremony.STAGE_GATE))},{'step':'face'}):
                r=self.post(self.base+'/checkpoints/'+source+'/steps',body,uid);self.assertEqual(r.status_code,200,r.json)
    def test_differences_are_private_until_author_consents(self):
        body={'request_id':'diff1','stage':'relationship','text':'My private concern'}
        for _ in range(2):self.assertEqual(self.post(self.base+'/differences',body).status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'Difference')),1)
        self.assertNotIn('My private concern',self.request(self.base,uid='partner').get_data(as_text=True))
        path=self.base+'/differences/owner:diff1'
        self.assertEqual(self.post(path+'/sharing',{'consent':True},'stranger').status_code,404)
        self.assertEqual(self.post(path+'/sharing',{'consent':True},'partner').status_code,404)
        self.assertEqual(self.post(path+'/sharing',{'consent':True}).status_code,200)
        self.assertIn('My private concern',self.request(self.base,uid='partner').get_data(as_text=True))
        self.assertEqual(self.post(path+'/resolve',uid='partner').status_code,403)
        self.assertEqual(self.post(path+'/sharing',{'consent':False}).status_code,200)
        self.assertNotIn('My private concern',self.request(self.base,uid='partner').get_data(as_text=True))
    def test_road_validation_obligations_and_explicit_sharing(self):
        path=self.base+'/road'
        block={'request_id':'block1','category':'free','days':['Mon'],'label':'Private hobby','start':'17:00','end':'20:00'}
        self.assertEqual(self.post(path+'/routine',{**block,'end':'99:00'}).status_code,400)
        for who in ('owner','partner'):
            for _ in range(2):self.assertEqual(self.post(path+'/routine',block,who).status_code,200)
        self.assertEqual(len(db.load_json_field(db.fetch_one(self.conn,'RoadProfile',user_id='owner',couple_id='pair')['routine_json'],[])),1)
        other=self.request(path,uid='partner').json['data'];self.assertEqual(other['partner_shared_slots'],[])
        slots=[{'day':'Mon','start':'17:00','end':'20:00'}]
        for who in ('owner','partner'):
            r=self.request(path+'/sharing',method='PUT',body={'slots':slots},uid=who);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['data']['overlap'],slots)
        obligation={'request_id':'ob1','type':'obligation','title':'Private appointment','start_date':'2026-01-05','end_date':'2026-01-05','shared':False}
        r=self.post(path+'/obligations',obligation);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['data']['my_availability']['Mon'],[])
        other=self.request(path,uid='partner').json['data']
        self.assertEqual(other['partner_shared_slots'],[]);self.assertEqual(other['partner_shared_obligations'],[])
        self.assertEqual(self.request(path+'/sharing',method='PUT',body={'slots':slots}).status_code,409)
        self.assertEqual(self.request(path+'/obligations/owner:ob1',uid='partner',method='DELETE',body={}).status_code,404)
    def test_stage_scoped_separate_consent_and_history(self):
        self.assertEqual(self.post(self.base+'/checkpoints/relationship/advance').status_code,409)
        self.sign('relationship','owner')
        self.assertEqual(self.post(self.base+'/checkpoints/relationship/advance').status_code,409)
        self.sign('relationship','partner')
        for _ in range(2):self.assertEqual(self.post(self.base+'/checkpoints/relationship/advance').status_code,200)
        self.assertEqual(db.fetch_one(self.conn,'Couple',id='pair')['stage'],'engaged')
        self.assertEqual(self.post(self.base+'/checkpoints/engaged/advance').status_code,409)
        for uid in ('partner','owner'):self.sign('engaged',uid)
        self.assertEqual(self.post(self.base+'/checkpoints/engaged/advance').status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'Playbook',couple_id='pair')),3)
        self.assertEqual(len(db.fetch_all(self.conn,'RoadProfile',couple_id='pair')),2)
        self.assertEqual(self.post(self.base+'/checkpoints/relationship/advance').json['data']['current_stage'],'married')
    def test_cannot_forge_partner_consent_in_legacy_form(self):
        self.login('owner')
        # Secure-mode cookies require real sessions; test the form under the
        # legacy harness too, where the old two-checkbox bypass originated.
        with mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':False}):
            self.client.post('/journey/advance',data={'opt_in_me':'on','opt_in_partner':'on'})
        self.assertEqual(db.fetch_one(self.conn,'Couple',id='pair')['stage'],'relationship')
    def test_exit_feedback_cooloff_and_independent_reentry(self):
        r=self.post(self.base+'/exits',{'stage':'relationship'});self.assertEqual(r.status_code,200,r.json)
        path=self.base+'/exits/'+r.json['data']['id']
        self.assertEqual(self.post(path+'/feedback',{'declined':False,'text':'private'}).status_code,409)
        for uid in ('owner','partner'):self.assertEqual(self.post(path+'/interview',{'acknowledged':True},uid).status_code,200)
        self.assertEqual(self.post(path+'/feedback',{'declined':False,'text':'My private feedback'}).status_code,200)
        self.assertNotIn('My private feedback',self.request(path,uid='partner').get_data(as_text=True))
        self.assertEqual(self.post(path+'/feedback',{'declined':True},'partner').status_code,200)
        self.assertEqual(self.post(path+'/reentry').status_code,409)
        self.set_clock(week=3,day='Mon',hour=12)
        self.assertEqual(self.post(path+'/reentry').status_code,200)
        self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['journey_state'],'dating')
        self.assertEqual(db.fetch_one(self.conn,'User',id='partner')['journey_state'],'cooloff')
        self.assertEqual(self.post(path+'/reentry',uid='partner').status_code,200)
    def test_expense_is_self_report_not_partner_compliance(self):
        b={'request_id':'expense1','stage':'relationship','week':0,'strategy':'equal','compliant':False}
        self.assertEqual(self.post(self.base+'/expense-reports',b).status_code,200)
        self.assertEqual(self.request(self.base,uid='partner').json['data']['my_expense_reports'],[])
    def test_stage_transition_rolls_back_on_failure(self):
        for who in ('owner','partner'):self.sign('relationship',who)
        before=list(self.conn.iterdump())
        with mock.patch.object(journey,'_seed_guru_topics',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):service.advance(self.conn,'owner','pair','relationship',app_module.get_clock(),'2026-01-05')
        self.assertEqual(before,list(self.conn.iterdump()))
