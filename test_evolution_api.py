"""Three-user tests of profile disclosure, reciprocal sharing and gate entry."""
import os
from unittest import mock
import db,auth_sessions,ceremony,chemistry,vision,stage_gate,gate_conversation
import gate_service
import test_week_api
from test_segment_efg_routes import RouteTestCase,app_module


class EvolutionApiTests(RouteTestCase):
    request=test_week_api.WeekApiTests.request
    def setUp(self):
        super().setUp()
        p=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True});p.start();self.addCleanup(p.stop)
        self.headers={}
        for uid in ('owner','partner','stranger'):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'email':uid+'@test.example','phone':'+15550000'+str(len(uid)),'auth_enabled':1,'created_at':'test'})
            self.headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
        self.make_lockin('owner','partner')
        row=db.fetch_one(self.conn,'LockIn',id='lock-1');row['dates_completed']=1;db.insert_row(self.conn,'LockIn',row)
        self.base='/lock-ins/lock-1'

    def post(self,path,body=None,uid='owner'):
        return self.request(path,method='POST',body=body or {},uid=uid)

    def sign(self,kind,uid):
        with mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}):
            for body in ({'step':'playbook'},{'step':'sign','signed_name':uid,'acks':list(ceremony.ack_keys(kind))},{'step':'face'}):
                r=self.post(self.base+'/agreements/'+kind+'/steps',body,uid)
                self.assertEqual(r.status_code,200,r.json)

    def test_stats_atomic_hold_and_strict_types(self):
        before=list(self.conn.iterdump())
        for fields,status in [({'weight_kg':True},400),({'user_id':'stranger'},400),({'weight_kg':70},409),({'diet':{}},400)]:
            r=self.request('/profile/stats',method='PATCH',body={'fields':fields})
            self.assertEqual(r.status_code,status,r.json)
        self.assertEqual(list(self.conn.iterdump()),before)

    def test_stats_patch_partial_vs_stringified_whole_form(self):
        # round4-fixes-spec.md §1 diagnosis: the client used to PATCH every
        # form field as a string ("38"), which the strict API refuses for
        # numeric stats. Only changed fields, correctly typed, must pass.
        # 'stranger' has no lock-in, so their stats are open to edit.
        r=self.request('/profile/stats',method='PATCH',body={'fields':{'age':'38','diet':'Vegetarian'}},uid='stranger')
        self.assertEqual(r.status_code,400,r.json)
        self.assertIn('age must be a whole number',r.json['error']['message'])
        r=self.request('/profile/stats',method='PATCH',body={'fields':{'diet':'Vegetarian'}},uid='stranger')
        self.assertEqual(r.status_code,200,r.json)
        r=self.request('/profile/stats',method='PATCH',body={'fields':{'age':38}},uid='stranger')
        self.assertEqual(r.status_code,200,r.json)

    def test_existing_children_can_be_edited_and_a_stale_count_never_survives_no(self):
        # round4-fixes-spec.md §5. 'stranger' has no lock-in, so stats are open.
        def patch(fields):
            return self.request('/profile/stats',method='PATCH',body={'fields':fields},uid='stranger')
        def stored():
            return db.load_json_field(db.fetch_one(self.conn,'User',id='stranger')['stats_json'],{})
        self.assertEqual(patch({'has_children':'Yes','children_count':2}).status_code,200)
        self.assertEqual((stored()['has_children'],stored()['children_count']),('Yes',2))
        r=patch({'children_count':11});self.assertEqual(r.status_code,400,r.json)
        r=patch({'has_children':'No'});self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(stored()['has_children'],'No');self.assertNotIn('children_count',stored())
        r=patch({'children_count':1});self.assertEqual(r.status_code,400,r.json)
        self.assertIn('only applies',r.json['error']['message'])
        self.assertNotIn('children_count',stored())

    def test_vision_retry_and_reversal_disclosure(self):
        import json
        row=db.fetch_one(self.conn,'User',id='owner')
        row['vision_json']=json.dumps([{'key':'Intimacy','stance':['Emotional']},{'key':'Travel together','stance':None}])
        db.insert_row(self.conn,'User',row);self.conn.commit()
        b={'request_id':'detail1','pillar':'Kids','sub_selection':'Adoption'}
        # An identical replay returns the same audit row without re-applying.
        for _ in range(2):self.assertEqual(self.post('/profile/vision/details',b).status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'VisionEntry')),1)
        # It actually changed the real vision, not just a note.
        kids=[v for v in json.loads(db.fetch_one(self.conn,'User',id='owner')['vision_json']) if v['key']=='Kids']
        self.assertEqual(kids[0]['stance'],['Adoption'])
        self.assertEqual(self.post('/profile/vision/details',{**b,'sub_selection':'Surrogacy'}).status_code,409)
        # An undisclosed change is refused before anything else is checked.
        r=self.post('/profile/vision/changes',{'request_id':'change1','pillar':'Kids','add':['Surrogacy'],'disclosed_to_partner':False})
        self.assertEqual(r.status_code,409)
        # Disclosed, but outside the Reality Check window: locked, with a reason.
        self.set_clock(day='Wed',hour=12)
        r=self.post('/profile/vision/changes',{'request_id':'change2','pillar':'Kids','add':['Surrogacy'],'disclosed_to_partner':True})
        self.assertEqual(r.status_code,409);self.assertEqual(r.json['error']['code'],'change_window_closed')
        # Inside the window it applies.
        self.set_clock(day='Sun',hour=22)
        r=self.post('/profile/vision/changes',{'request_id':'change3','pillar':'Kids','add':['Surrogacy'],'disclosed_to_partner':True})
        self.assertEqual(r.status_code,200,r.json)
        # The partner's own read shows none of the owner's entries.
        self.assertEqual(self.request('/profile/vision',uid='partner').json['data']['entries'],[])

    def test_chemistry_pacing_and_no_foreign_write(self):
        self.set_clock(day='Mon',hour=12)
        path='/profile/chemistry/entries/'
        for key,value,expected in [('health_openness','yes',409),('intimacy_pace','slow',200),('health_openness','yes',409),('unknown','x',400)]:
            r=self.request(path+key,method='PUT',body={'value':value})
            self.assertEqual(r.status_code,expected,r.json)
        self.set_clock(day='Tue',hour=12)
        self.assertEqual(self.request(path+'health_openness',method='PUT',body={'value':'yes'}).status_code,200)
        self.assertEqual(self.request(path+'intimacy_pace',uid='stranger',method='PUT',body={'value':'slow'}).status_code,403)

    def test_chemistry_activities_round_trip(self):
        # Regression: chemistry_read() used to forward the raw skills_json
        # blob ({"activities": {...}, "by_bucket": {...}}) as `activities`
        # instead of drilling into it, so a save's own re-read never came
        # back looking saved — every activity key was absent from the
        # (wrongly nested) response.
        picks={'Cooking':'good','Hiking':'good','Salsa':'improve','Tennis':'maybe'}
        r=self.request('/profile/chemistry/activities',method='PUT',body={'activities':picks})
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['data']['activities'],picks)
        r=self.request('/profile/chemistry')
        self.assertEqual(r.json['data']['activities'],picks)

    def test_chemistry_activities_below_minimum_rejected(self):
        r=self.request('/profile/chemistry/activities',method='PUT',body={'activities':{'Cooking':'good'}})
        self.assertEqual(r.status_code,400,r.json)

    def test_contact_neutrality_ownership_and_mutual_agreement(self):
        self.assertEqual(self.post(self.base+'/contact-requests',{'channel':'phone'},'stranger').status_code,404)
        r=self.post(self.base+'/contact-requests',{'channel':'phone'})
        self.assertEqual(r.status_code,200,r.json)
        rid=r.json['data']['contact_requests'][0]['id']
        path=self.base+'/contact-requests/'+rid+'/response'
        self.assertEqual(self.post(path,{'response':'accepted'}).status_code,403)
        self.assertEqual(self.post(path,{'response':'accepted'},'partner').status_code,409)
        self.sign(ceremony.CONTACT_SHARE,'partner')
        self.assertEqual(self.post(path,{'response':'accepted'},'partner').status_code,200)
        self.assertIsNone(self.request(self.base+'/after-date').json['data']['contact_requests'][0]['contact'])
        self.sign(ceremony.CONTACT_SHARE,'owner')
        self.assertIsNotNone(self.request(self.base+'/after-date').json['data']['contact_requests'][0]['contact'])

    def test_next_level_reciprocal_and_private_reluctance(self):
        self.assertEqual(self.post(self.base+'/next-level').status_code,200)
        body={'question_key':'reluctance_check','declined':False,'answer_text':'I feel pressured'}
        self.assertEqual(self.post(self.base+'/next-level/answers',body).status_code,200)
        text=self.request(self.base+'/after-date',uid='partner').get_data(as_text=True)
        self.assertNotIn('I feel pressured',text)
        self.assertNotIn('Some of what',text)
        self.assertEqual(self.post(self.base+'/next-level/answers',{'question_key':'reluctance_check','declined':True},'partner').status_code,200)
        self.assertIn('I feel pressured',self.request(self.base+'/after-date',uid='partner').get_data(as_text=True))
        self.assertNotIn('Some of what',self.request(self.base+'/after-date',uid='partner').get_data(as_text=True))
        self.assertEqual(self.post(self.base+'/next-level/answers',{**body,'answer_text':'edit'}).status_code,409)

    def test_home_invite_recipient_acknowledgements_and_free_revocation(self):
        for uid in ('owner','partner'):
            self.sign(ceremony.CONTACT_SHARE,uid)
        for uid in ('owner','partner'):
            self.sign(ceremony.HOME_INVITE,uid)
        body={'request_id':'invite1','proposed_datetime':'2026-01-12T19:00','expectation_flag':'intimacy_expected'}
        r=self.post(self.base+'/home-invites',body);self.assertEqual(r.status_code,200,r.json)
        rid=r.json['data']['home_invites'][0]['id'];path=self.base+'/home-invites/'+rid
        self.assertEqual(self.post(path+'/see-flag').status_code,403)
        self.assertEqual(self.post(path+'/respond',{'response':'accepted'},'partner').status_code,409)
        self.assertEqual(self.post(path+'/see-flag',uid='partner').status_code,200)
        self.assertEqual(self.post(path+'/respond',{'response':'accepted'},'partner').status_code,200)
        ack={'acknowledgement_version':'v1','acknowledged':True}
        with mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}):
            self.assertEqual(self.post(path+'/acknowledge',ack).status_code,409)
            for uid in ('owner','partner'):
                self.assertEqual(self.post(path+'/guidance',uid=uid).status_code,200)
                r=self.post(path+'/acknowledge',ack,uid);self.assertEqual(r.status_code,200,r.json)
        self.assertTrue(r.json['data']['home_invites'][0]['both_acknowledged'])
        self.assertEqual(self.post(path+'/revoke',uid='stranger').status_code,404)
        for _ in range(2):self.assertEqual(self.post(path+'/revoke',uid='partner').status_code,200)
        self.assertEqual(db.fetch_all(self.conn,'ComplianceEvent'),[])

    def prepare_gate(self):
        for uid in ('owner','partner'):
            row=db.fetch_one(self.conn,'User',id=uid)
            stats=db.load_json_field(row['stats_json'],{})
            stats.update({k:'present' for k in vision.MANDATORY_STATS_FIELDS if not stats.get(k)})
            row['stats_json']=db.json_field(stats);db.insert_row(self.conn,'User',row)
            db.insert_row(self.conn,'VisionEntry',{'id':uid,'user_id':uid,'element_key':'children','detail_text':'Discuss','added_at':'test'})
            for key in (*chemistry.MANDATORY_KEYS,*chemistry.INTIMACY_MANDATORY_KEYS):
                db.insert_row(self.conn,'ChemistryEntry',{'id':uid+key,'user_id':uid,'key':key,'value':'slow' if key=='intimacy_pace' else 'yes','updated_at':'test'})
        self.set_clock(day='Mon',hour=12)
        self.assertEqual(self.post(self.base+'/gate/raise').status_code,200)
        self.assertEqual(self.post(self.base+'/gate/ask',{'round':1,'question_keys':['exclusivity_check']}).status_code,200)
        for uid in ('owner','partner'):
            self.assertEqual(self.post(self.base+'/gate/answer',{'round':1,'question_key':'exclusivity_check','value':'exclusive'},uid).status_code,200)
        self.assertEqual(self.post(self.base+'/gate/confirm',{'round':1}).status_code,409)
        self.set_clock(day='Wed',hour=12)
        for uid in ('owner','partner'):
            r=self.post(self.base+'/gate/confirm',{'round':1},uid);self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(self.post(self.base+'/gate/exclusivity-ack',{'round':1,'acknowledged':True},uid).status_code,200)
        for uid in ('owner','partner'):
            self.sign(ceremony.RELATIONSHIP_ENTRY,uid)

    def test_gate_requires_both_and_enters_once(self):
        self.prepare_gate()
        for uid in ('owner','partner','owner'):
            r=self.post(self.base+'/gate/enter-relationship',{'round':1},uid)
            self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(len(db.fetch_all(self.conn,'Couple')),1)
        self.assertEqual(db.fetch_all(self.conn,'Couple')[0]['stage'],'relationship')
        self.assertEqual(self.post(self.base+'/gate/enter-relationship',{'round':1},'stranger').status_code,404)

    def test_gate_entry_rolls_back_all_legacy_helper_writes(self):
        self.prepare_gate();before=list(self.conn.iterdump())
        with mock.patch.object(gate_service.journey,'schedule_weekly_report',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                gate_service.action(self.conn,'owner','lock-1','enter-relationship',{'round':1},app_module.get_clock(),'2026-01-05')
        self.assertEqual(before,list(self.conn.iterdump()))
