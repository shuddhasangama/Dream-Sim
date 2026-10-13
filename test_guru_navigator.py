"""Guru privacy, stage relevance and asynchronous consensus regressions."""
import os
from unittest import mock
from cryptography.fernet import Fernet
import db
import guru_navigator as guru
from test_date_cycle_api import DateCycleApiTests


class GuruNavigatorTests(DateCycleApiTests):
    def setUp(self):
        super().setUp()
        patch=mock.patch.dict(os.environ,{'DHASHU_GURU_ENABLED':'1','DHASHU_GURU_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        patch.start();self.addCleanup(patch.stop)
        # Isolate Guru from unrelated date readiness; real stage-aware home has its own tests.
        self.guidance={'topic_stage':'planning','headline':'Choose date','body':'Choose an overlapping slot.'}

    def req(self,path='',body=None,uid='owner'):
        return self.request('/guru/'+path,uid=uid,method='POST' if body is not None else 'GET',body=body)

    def topic(self):
        return self.req('state').json['data']['topics'][0]['id']

    def test_mixed_intentions_shared_discussion_does_not_accept_date(self):
        self.mixed()
        state=self.req('state').json['data']
        self.assertIn('intentions',[t['id'] for t in state['shared_topics']])
        d=self.req('discussions',{'topic':'intentions'}).json['data']['discussions'][0]
        d=self.change(d,'accept','partner').json['data']['discussions'][0]
        d=self.change(d,'perspective',text='I want to understand our pace').json['data']['discussions'][0]
        d=self.change(d,'perspective','partner','I would like more time').json['data']['discussions'][0]
        d=self.change(d,'propose',text='Let us consider another date').json['data']['discussions'][0]
        d=self.change(d,'confirm').json['data']['discussions'][0]
        d=self.change(d,'confirm','partner').json['data']['discussions'][0]
        self.assertEqual(d['status'],'agreed')
        self.assertEqual(db.fetch_all(self.conn,'DateResolution'),[])
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['week'],1)

    def test_private_encryption_memory_and_partner_isolation(self):
        topic=self.topic()
        r=self.req('private',{'action':'message','topic':topic,'text':'private concern','request_id':'once'})
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(len(r.json['data']['history']),2)
        self.assertNotIn('private concern',db.fetch_one(self.conn,'GuruPrivate',id='owner')['payload'])
        self.assertNotIn('private concern',self.req('state',uid='partner').get_data(as_text=True))
        self.req('private',{'action':'message','topic':topic,'text':'private concern','request_id':'once'})
        self.assertEqual(len(self.req('state').json['data']['history']),2)
        self.assertEqual(self.req('private',{'action':'save_memory','text':'I prefer quiet'}).status_code,409)
        self.req('private',{'action':'memory_setting','enabled':True})
        r=self.req('private',{'action':'save_memory','text':'I prefer quiet'})
        mid=r.json['data']['memories'][0]['id']
        self.req('private',{'action':'save_memory','memory_id':mid,'text':'I prefer walks'})
        self.assertNotIn('walks',self.req('state',uid='partner').get_data(as_text=True))
        self.req('private',{'action':'memory_setting','enabled':False})
        self.assertEqual(self.req('state').json['data']['memories'],[])
        self.req('private',{'action':'clear_history'})
        self.assertEqual(self.req('state').json['data']['history'],[])

    def invite(self):
        topics=self.req('state').json['data']['shared_topics']
        r=self.req('discussions',{'topic':topics[0]['id']})
        self.assertEqual(r.status_code,200,r.json)
        return r.json['data']['discussions'][0]

    def change(self,d,action,uid='owner',text=None):
        return self.req('discussions/'+d['id'],{'action':action,'revision':d['revision'],**({'text':text} if text is not None else {})},uid)

    def test_shared_requires_invitation_and_both_confirm_latest_proposal(self):
        d=self.invite()
        self.assertEqual(self.change(d,'perspective',text='too early').status_code,409)
        self.assertEqual(self.change(d,'accept').status_code,409)
        self.assertEqual(self.change(d,'accept','stranger').status_code,404)
        d=self.change(d,'accept','partner').json['data']['discussions'][0]
        d=self.change(d,'perspective',text='More notice please').json['data']['discussions'][0]
        self.assertEqual(self.change(d,'propose',text='New plan').status_code,409)
        d=self.change(d,'perspective','partner','I need flexibility').json['data']['discussions'][0]
        d=self.change(d,'propose',text='Choose a time together on Friday').json['data']['discussions'][0]
        stale=d.copy()
        d=self.change(d,'confirm').json['data']['discussions'][0]
        self.assertEqual(d['status'],'active')
        self.assertEqual(self.change(stale,'confirm','partner').status_code,409)
        d=self.change(d,'propose','partner','Choose on Saturday').json['data']['discussions'][0]
        self.assertFalse(d['partner_confirmed'])
        d=self.change(d,'confirm','partner').json['data']['discussions'][0]
        d=self.change(d,'confirm').json['data']['discussions'][0]
        self.assertEqual(d['status'],'agreed')
        self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['journey_state'],'dating')
        self.assertEqual(self.req('state',uid='stranger').json['data']['discussions'],[])

    def test_pause_needs_both_resume_and_leave_erases_shared_only(self):
        d=self.invite();d=self.change(d,'accept','partner').json['data']['discussions'][0]
        d=self.change(d,'perspective',text='Shared concern').json['data']['discussions'][0]
        d=self.change(d,'pause').json['data']['discussions'][0]
        self.assertEqual(self.change(d,'perspective','partner','Ignored pause').status_code,409)
        d=self.change(d,'resume').json['data']['discussions'][0];self.assertEqual(d['status'],'paused')
        d=self.change(d,'resume','partner').json['data']['discussions'][0];self.assertEqual(d['status'],'active')
        d=self.change(d,'leave','partner').json['data']['discussions'][0]
        self.assertEqual(d['status'],'closed');self.assertEqual(d['partner_perspective'],'')
        self.assertNotIn('Shared concern',self.req('state').get_data(as_text=True))

    def test_reassigned_account_and_released_pair_cannot_read_old_content(self):
        topic=self.topic()
        self.req('private',{'action':'message','topic':topic,'text':'Old owner secret','request_id':'old'})
        d=self.invite()
        account=db.fetch_one(self.conn,'Account',user_id='owner');account['phone']='+15559999999';db.insert_row(self.conn,'Account',account)
        data=self.req('state').json['data'];self.assertEqual(data['history'],[]);self.assertEqual(data['discussions'],[])
        self.assertEqual(self.req('state',uid='partner').json['data']['discussions'],[])
        self.assertEqual(self.change(d,'leave').status_code,404)

    def test_stage_validation_safety_and_no_cache(self):
        self.assertEqual(self.req('private',{'action':'message','topic':'not_a_topic','text':'test','request_id':'bad'}).status_code,409)
        r=self.req('private',{'action':'message','topic':self.topic(),'text':'I feel unsafe','request_id':'safe'})
        self.assertIn('safety comes first',r.json['data']['history'][-1]['text'])
        self.assertEqual(r.headers['Cache-Control'],'no-store')
        pair=db.fetch_one(self.conn,'LockIn',id='lock-1');pair['status']='released';db.insert_row(self.conn,'LockIn',pair)
        self.assertEqual(self.req('state').json['data']['shared_topics'],[])

    def test_ai_needs_opt_in_and_deleted_notes_do_not_reappear_in_flight(self):
        topic=self.topic()
        with mock.patch('guru_provider.available',return_value=True),mock.patch('guru_provider.reply',return_value='A useful reply') as reply:
            self.req('private',{'action':'message','topic':topic,'text':'A question','request_id':'no-consent'})
            reply.assert_not_called()
            self.req('private',{'action':'ai_setting','enabled':True})
            r=self.req('private',{'action':'message','topic':topic,'text':'Another question','request_id':'consent'})
            self.assertEqual(r.json['data']['history'][-1]['mode'],'ai')
            self.assertEqual(reply.call_count,1)
            def delete_while_waiting(*args):
                with guru.write(self.conn):
                    value=guru.private(self.conn,'owner');value.pop('pending',None);value['history']=[]
                    guru.save_private(self.conn,'owner',value)
                return 'Late answer'
            reply.side_effect=delete_while_waiting
            r=self.req('private',{'action':'message','topic':topic,'text':'Third question','request_id':'inflight'})
            self.assertEqual(r.status_code,409)
            self.assertEqual(self.req('state').json['data']['history'],[])

    def test_relationship_topics_do_not_appear_during_dating_gate(self):
        self.assertEqual(guru.stage_guidance({'journey_state':'dating'},{'topic_stage':'relationship'})['topic_stage'],'gate')
        self.assertEqual(guru.stage_guidance({'journey_state':'relationship'},{'topic_stage':'planning'})['topic_stage'],'relationship')
        self.assertNotIn('expenses',guru.STAGES['gate'])
        self.assertIn('expenses',guru.STAGES['relationship'])

    def test_guidance_tracks_history_without_claiming_partner_intent(self):
        a=guru.respond('Hello','differences',[],self.guidance)
        b=guru.respond('Hello','differences',[{'role':'user','topic':'differences'}],self.guidance)
        self.assertNotEqual(a,b)
        self.assertIn('Choose date',guru.respond('What next?','planning',[],self.guidance))
