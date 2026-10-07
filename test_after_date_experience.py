"""Regression coverage for asynchronous, private, two-person after-date flows."""
import os
from unittest import mock
import db,ceremony,gate_conversation
import test_evolution_api as fixtures
from test_segment_efg_routes import RouteTestCase

class AfterDateExperienceTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        import auth_sessions
        from test_segment_efg_routes import app_module
        p=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True});p.start();self.addCleanup(p.stop)
        self.headers={}
        for uid in ('owner','partner','stranger'):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'email':uid+'@test.example','phone':'+15550000'+str(len(uid)),'auth_enabled':1,'created_at':'test'})
            self.headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
        self.make_lockin('owner','partner')
        row=db.fetch_one(self.conn,'LockIn',id='lock-1');row['dates_completed']=1;db.insert_row(self.conn,'LockIn',row)
        self.base='/lock-ins/lock-1'

    request=fixtures.EvolutionApiTests.request
    post=fixtures.EvolutionApiTests.post
    sign=fixtures.EvolutionApiTests.sign

    def test_empty_and_text_only_report_does_not_claim_alignment(self):
        self.assertFalse(gate_conversation.report([],{}, {})['complete'])
        report=gate_conversation.report(['relationship_meaning'],{'relationship_meaning':'A'},{'relationship_meaning':'B'})
        self.assertTrue(report['complete'])
        self.assertNotIn('same place',report['headline'])

    def test_custom_question_private_answers_and_both_reflections_required(self):
        self.post(self.base+'/gate/raise')
        r=self.post(self.base+'/gate/ask',{'round':1,'question_keys':[],'custom_question':'What pace feels right?'})
        self.assertEqual(r.status_code,200,r.json)
        key=r.json['data']['asked'][0]['key']
        self.assertEqual(self.post(self.base+'/gate/ask',{'round':1,'question_keys':[],'custom_question':'What pace feels right?'}).status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'GateAsk')),1)
        self.post(self.base+'/gate/answer',{'round':1,'question_key':key,'value':'private first response'})
        r=self.request(self.base+'/gate',uid='partner')
        self.assertNotIn('private first response',r.get_data(as_text=True))
        self.assertFalse(r.json['data']['report']['complete'])
        with mock.patch('async_rehearsal.enabled',return_value=True),mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}):
            self.assertEqual(self.post(self.base+'/gate/reflection-ready',{'round':1}).status_code,409)
            self.post(self.base+'/gate/answer',{'round':1,'question_key':key,'value':'second response'},'partner')
            r=self.post(self.base+'/gate/reflection-ready',{'round':1})
            self.assertEqual(r.status_code,200,r.json)
            self.assertFalse(r.json['data']['may_confirm'])
            r=self.post(self.base+'/gate/reflection-ready',{'round':1},'partner')
            self.assertTrue(r.json['data']['may_confirm'])
            self.assertEqual(self.post(self.base+'/gate/reflection-ready',{'round':1},'stranger').status_code,404)
            # Changing an answer resets both acknowledgements and the pause.
            r=self.post(self.base+'/gate/answer',{'round':1,'question_key':key,'value':'revised response'})
            self.assertFalse(r.json['data']['may_confirm'])
        self.assertEqual(self.post(self.base+'/gate/reflection-ready',{'round':1}).status_code,403)

    def test_social_handle_requires_acceptance_and_both_agreements(self):
        r=self.post(self.base+'/contact-requests',{'channel':'instagram'})
        rid=r.json['data']['contact_requests'][0]['id']
        path=self.base+'/contact-requests/'+rid+'/response'
        self.sign(ceremony.CONTACT_SHARE,'partner')
        self.assertEqual(self.post(path,{'response':'accepted'},'partner').status_code,400)
        self.assertEqual(self.post(path,{'response':'accepted','contact_value':'@privatehandle'},'partner').status_code,200)
        self.assertNotIn('@privatehandle',self.request(self.base+'/after-date').get_data(as_text=True))
        self.sign(ceremony.CONTACT_SHARE,'owner')
        self.assertIn('@privatehandle',self.request(self.base+'/after-date').get_data(as_text=True))
        self.assertEqual(self.request(self.base+'/after-date',uid='stranger').status_code,404)

    def test_async_two_partner_relationship_entry_without_advancing_shared_clock(self):
        import chemistry,vision
        for uid in ('owner','partner'):
            user=db.fetch_one(self.conn,'User',id=uid)
            stats=db.load_json_field(user['stats_json'],{})
            stats.update({k:'present' for k in vision.MANDATORY_STATS_FIELDS if not stats.get(k)})
            user['stats_json']=db.json_field(stats);db.insert_row(self.conn,'User',user)
            db.insert_row(self.conn,'VisionEntry',{'id':uid,'user_id':uid,'element_key':'children','detail_text':'Discuss','added_at':'test'})
            for key in (*chemistry.MANDATORY_KEYS,*chemistry.INTIMACY_MANDATORY_KEYS):
                if key!='health_openness':
                    db.insert_row(self.conn,'ChemistryEntry',{'id':uid+key,'user_id':uid,'key':key,'value':'slow' if key=='intimacy_pace' else 'yes','updated_at':'test','updated_at_hours':99999})
        self.post(self.base+'/gate/raise')
        self.post(self.base+'/gate/ask',{'round':1,'question_keys':['exclusivity_check']})
        for uid in ('owner','partner'):
            self.post(self.base+'/gate/answer',{'round':1,'question_key':'exclusivity_check','value':'exclusive'},uid)
        with mock.patch('async_rehearsal.enabled',return_value=True),mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}):
            self.assertEqual(self.request('/profile/chemistry/entries/health_openness',method='PUT',body={'value':'when_relevant'}).status_code,409)
            for uid in ('owner','partner'):
                self.assertEqual(self.post(self.base+'/gate/reflection-ready',{'round':1},uid).status_code,200)
            for uid in ('owner','partner'):
                r=self.request('/profile/chemistry/entries/health_openness',method='PUT',body={'value':'when_relevant'},uid=uid)
                self.assertEqual(r.status_code,200,r.json)
                self.assertEqual(self.post(self.base+'/gate/confirm',{'round':1},uid).status_code,200)
                self.assertEqual(self.post(self.base+'/gate/exclusivity-ack',{'round':1,'acknowledged':True},uid).status_code,200)
            self.sign(ceremony.RELATIONSHIP_ENTRY,'owner')
            self.assertEqual(self.post(self.base+'/gate/enter-relationship',{'round':1}).status_code,409)
            self.sign(ceremony.RELATIONSHIP_ENTRY,'partner')
            r=self.post(self.base+'/gate/enter-relationship',{'round':1})
            self.assertEqual(r.status_code,200,r.json)
            self.assertTrue(r.json['data']['advanced'])
            self.assertEqual(len(db.fetch_all(self.conn,'Couple')),1)

    def test_shared_topics_and_opt_in_answers_preserve_old_privacy(self):
        self.post(self.base+'/gate/raise')
        body={'round':1,'question_keys':['relationship_meaning']}
        self.assertEqual(self.post(self.base+'/gate/ask',body).status_code,200)
        r=self.post(self.base+'/gate/ask',body,'partner')
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['data']['asked'][0]['origin'],'both')
        self.assertEqual(len(db.fetch_all(self.conn,'GateAsk')),1)
        answer={'round':1,'question_key':'relationship_meaning','value':'My private answer'}
        self.post(self.base+'/gate/answer',answer)
        self.post(self.base+'/gate/answer',{**answer,'value':'Partner answer','share_with_partner':True},'partner')
        self.assertNotIn('My private answer',self.request(self.base+'/gate',uid='partner').get_data(as_text=True))
        own=self.request(self.base+'/gate').json['data']
        self.assertEqual(own['partner_answers'],{'relationship_meaning':'Partner answer'})
        self.post(self.base+'/gate/answer',{**answer,'share_with_partner':True})
        partner=self.request(self.base+'/gate',uid='partner').json['data']
        self.assertEqual(partner['partner_answers'],{'relationship_meaning':'My private answer'})
        self.post(self.base+'/gate/answer',answer)
        self.assertEqual(self.request(self.base+'/gate',uid='partner').json['data']['partner_answers'],{})
        self.assertEqual(self.request(self.base+'/gate',uid='stranger').status_code,404)

    def test_shared_answer_waits_for_other_answer(self):
        self.post(self.base+'/gate/raise')
        self.post(self.base+'/gate/ask',{'round':1,'question_keys':['relationship_meaning']})
        self.post(self.base+'/gate/answer',{'round':1,'question_key':'relationship_meaning','value':'Hidden until answered','share_with_partner':True})
        self.assertNotIn('Hidden until answered',self.request(self.base+'/gate',uid='partner').get_data(as_text=True))

    def test_new_social_channels_use_the_same_explicit_release_gates(self):
        for channel in ('facebook','snapchat'):
            response=self.post(self.base+'/contact-requests',{'channel':channel})
            self.assertEqual(response.status_code,200,response.json)
            rid=next(r['id'] for r in response.json['data']['contact_requests'] if r['channel']==channel)
            self.sign(ceremony.CONTACT_SHARE,'partner')
            path=self.base+'/contact-requests/'+rid+'/response'
            self.assertEqual(self.post(path,{'response':'accepted'},'partner').status_code,400)
            self.assertEqual(self.post(path,{'response':'accepted','contact_value':'@private_'+channel},'partner').status_code,200)
        self.assertNotIn('@private_',self.request(self.base+'/after-date').get_data(as_text=True))
        self.sign(ceremony.CONTACT_SHARE,'owner')
        result=self.request(self.base+'/after-date').get_data(as_text=True)
        self.assertIn('@private_facebook',result)
        self.assertIn('@private_snapchat',result)

    def test_existing_contact_requests_survive_channel_schema_upgrade(self):
        # Emulate the old deployed constraint with a real accepted request.
        self.conn.execute('DROP TABLE ContactRequest')
        sql=db.SQLITE_SCHEMA_PATH.read_text(encoding='utf-8')
        start=sql.index('CREATE TABLE IF NOT EXISTS "ContactRequest"')
        statement=sql[start:sql.index(';',start)+1].replace(", 'facebook', 'snapchat'",'')
        self.conn.execute(statement)
        db.insert_row(self.conn,'ContactRequest',{'id':'old','pair_id':'lock-1','requester_id':'owner','channel':'instagram','week':1,'status':'accepted','requested_at':'test','shared_contact':'@preserve'})
        before=db.fetch_one(self.conn,'ContactRequest',id='old')
        db.init_db(self.conn)
        db.init_db(self.conn)
        self.assertEqual(db.fetch_one(self.conn,'ContactRequest',id='old'),before)
        r=self.post(self.base+'/contact-requests',{'channel':'facebook'})
        self.assertEqual(r.status_code,200,r.json)

    def test_guru_uses_only_own_debrief_and_all_chemistry_buckets(self):
        import dating_guidance
        from clock import SimulationClock
        for uid in ('owner','partner'):
            row=db.fetch_one(self.conn,'User',id=uid)
            db.insert_row(self.conn,'User',{**row,'skills_json':db.json_field({'activities':{'Music':'good','Cooking':'improve','Hiking':'maybe','Dancing':'no'}})})
        self.make_plan('lock-1',status='completed')
        for uid in ('owner','partner'):
            db.insert_row(self.conn,'DateFeedback',{'id':uid,'dateplan_id':'plan-1','user_id':uid,'payload_json':db.json_field({'flags':{'green_flags':[uid+' memory'],'red_flags':[]}})})
        result=dating_guidance.context(self.conn,'owner',db.fetch_one(self.conn,'LockIn',id='lock-1'),None,SimulationClock.at(1,'Wed',18))
        self.assertEqual(len(result['prompts']),5)
        self.assertIn('owner memory',str(result))
        self.assertNotIn('partner memory',str(result))
        self.assertEqual(result['date_number'],2)
