"""Isolated action-driven rehearsal: delayed partners, state/privacy and rollback."""
from unittest import mock
import concurrent.futures
import ceremony
import auth_sessions
import db
import async_rehearsal as service
import guru_dating
import test_planning_api as planning_tests
from test_segment_efg_routes import RouteTestCase, app_module


class AsyncRehearsalTests(RouteTestCase):
    request = planning_tests.PlanningApiTests.request
    align = planning_tests.PlanningApiTests.align
    prepare = planning_tests.PlanningApiTests.prepare
    step = planning_tests.PlanningApiTests.step

    def setUp(self):
        super().setUp()
        config=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True})
        config.start(); self.addCleanup(config.stop)
        self.headers={}
        for who in ('owner','partner','stranger'):
            self.make_user(who)
            db.insert_row(self.conn,'Account',{'id':who,'user_id':who,'email':who+'@test.example',
                'auth_enabled':1,'verification_required':1,'verified_email':1,'created_at':'test'})
            self.headers[who]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,who)['access_token']}
        self.make_lockin('owner','partner')
        self.base='/lock-ins/lock-1'
        self.slot={'day':'Sat','meal_slot':'dinner'}
        patch = mock.patch.dict('os.environ', {'DHASHU_ASYNC_TEST':'true', 'DHASHU_TEST_START_WEEK':'1',
            'DHASHU_ACCELERATED_TEST':'true', 'DHASHU_TEST_START_UTC':'2026-09-21T04:30:00Z',
            'BETA_DATE_SIMULATION_ENABLED':'1'})
        patch.start(); self.addCleanup(patch.stop)

    def state(self, who='owner'):
        r=self.request('/journey/status',uid=who)
        self.assertEqual(r.status_code,200,r.json)
        return r.json['data']

    def confirmed(self):
        path=self.prepare()
        with mock.patch.object(app_module.dateplan,'verify_face',return_value=True):
            for who in ('owner','partner'):
                for step,body in [('playbook',{}),('sign',{'signed_name':who,'acks':list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))}),('face',{})]:
                    r=self.step(path,who,step,**body)
                    self.assertEqual(r.status_code,200,r.json)
        return path

    def ready(self,path,who,step):
        return self.request('/rehearsal'+path+'/ready',uid=who,method='POST',body={'step':step})

    def test_full_flow_waits_for_both_and_second_date_has_new_readiness(self):
        self.align('owner')
        self.request(self.base+'/availability',method='PUT',body={'slots':[self.slot]})
        before=list(self.conn.iterdump())
        for _ in range(3):
            self.assertEqual(self.state()['async_rehearsal']['stage'],'availability')
        self.assertEqual(list(self.conn.iterdump()),before)
        path=self.confirmed()
        self.assertEqual(self.ready(path,'owner','debrief').status_code,409)
        for stage in ('date','debrief'):
            self.assertEqual(self.ready(path,'owner',stage).status_code,200)
            saved=list(self.conn.iterdump())
            self.assertEqual(self.ready(path,'owner',stage).status_code,200)
            self.assertEqual(saved,list(self.conn.iterdump()))
            self.assertEqual(self.state()['clock'],self.state('partner')['clock'])
            self.assertFalse(self.request(path+'/debrief').json['data']['feedback_open'])
            self.assertEqual(self.ready(path,'partner',stage).status_code,200)
        self.assertTrue(self.request(path+'/debrief').json['data']['feedback_open'])
        for who in ('owner','partner'):
            r=self.request(path+'/feedback/flags',uid=who,method='PUT',body={'green_flags':guru_dating.GREEN_FLAGS[:2],'red_flags':[]})
            self.assertEqual(r.status_code,200,r.json)
            r=self.request(path+'/feedback/decision',uid=who,method='POST',body={'decision':'continue'})
            self.assertEqual(r.status_code,200,r.json)
            if who=='owner':
                self.assertEqual(self.state()['async_rehearsal']['stage'],'debrief')
                self.assertIsNone(self.request(path+'/debrief',uid='partner').json['data']['my_feedback']['decision'])
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],1)
        self.assertEqual(self.state()['clock']['week'],2)
        self.assertEqual(self.ready(path,'owner','date').status_code,409)
        self.assertEqual(self.state()['async_rehearsal']['stage'],'availability')
        self.assertEqual(len(db.fetch_all(self.conn,'DateResolution')),1)
        # A second date preserves the first and cannot reuse its readiness.
        for who in ('owner','partner'):
            self.request(self.base+'/availability',uid=who,method='PUT',body={'slots':[self.slot]})
        next_plan=self.request(self.base+'/date-plan',method='POST',body={**self.slot,'cycle':2})
        self.assertEqual(next_plan.status_code,200,next_plan.json)
        next_path='/date-plans/'+next_plan.json['data']['id']
        with mock.patch.object(app_module.dateplan,'verify_face',return_value=True):
            for who in ('partner','owner'):
                self.step(next_path,who,'playbook')
                self.step(next_path,who,'sign',signed_name=who,acks=list(ceremony.ack_keys(ceremony.DATE_AGREEMENT)))
                self.assertEqual(self.step(next_path,who,'face').status_code,200)
        self.assertEqual(self.state()['async_rehearsal']['stage'],'ready_for_date')
        for stage in ('date','debrief'):
            for who in ('partner','owner'):
                self.assertEqual(self.ready(next_path,who,stage).status_code,200)
        for who in ('partner','owner'):
            self.request(next_path+'/feedback/flags',uid=who,method='PUT',body={'green_flags':guru_dating.GREEN_FLAGS[:2],'red_flags':[]})
            self.assertEqual(self.request(next_path+'/feedback/decision',uid=who,method='POST',body={'decision':'continue'}).status_code,200)
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],2)
        self.assertEqual(len(db.fetch_all(self.conn,'DateResolution')),2)

    def test_foreign_disabled_and_malformed_actions(self):
        path=self.confirmed()
        self.assertEqual(self.ready(path,'stranger','date').status_code,404)
        self.assertEqual(self.ready(path,'owner',[]).status_code,400)
        self.assertEqual(self.request('/rehearsal'+path+'/ready',method='POST',body={'step':'date','user_id':'partner'}).status_code,400)
        self.assertEqual(self.client.post('/api/v1/rehearsal'+path+'/ready',json={'step':'date'}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/journey/status').status_code,401)
        before=list(self.conn.iterdump())
        with mock.patch.dict('os.environ',{'DHASHU_SIMULATED_CLOCK':'false'}):
            self.assertIsNone(self.state()['async_rehearsal'])
            self.assertEqual(self.ready(path,'owner','date').status_code,403)
        with mock.patch.dict('os.environ',{'DHASHU_ASYNC_TEST':'false'}):
            self.assertIsNone(self.state()['async_rehearsal'])
            self.assertTrue(self.state()['accelerated_test']['enabled'])
        self.assertEqual(before,list(self.conn.iterdump()))

    def test_other_pair_does_not_advance_and_pending_agreement_blocks(self):
        path=self.prepare()
        self.assertEqual(self.ready(path,'owner','date').status_code,409)
        self.assertEqual(self.state('stranger')['async_rehearsal']['stage'],'matching')
        self.assertNotIn('plan_id',self.state('stranger')['async_rehearsal'])
        self.assertEqual(self.request('/simulated-clock',method='POST',body={'advance_hours':24}).status_code,409)

    def test_simultaneous_readiness_records_both_once(self):
        path=self.confirmed(); pid=path.split('/')[-1]
        def worker(uid):
            conn=db.get_connection(self.db_path)
            try: service.mark_ready(conn,uid,pid,'date')
            finally: conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker,['owner','partner','owner','partner']))
        self.assertEqual(len(db.fetch_all(self.conn,'RehearsalReady')),2)
        self.assertEqual(self.state()['async_rehearsal']['stage'],'date')

    def test_match_choices_do_not_expire_with_real_elapsed_time(self):
        db.delete_row(self.conn,'LockIn','lock-1')
        for who,other in [('owner','partner'),('partner','owner')]:
            db.insert_row(self.conn,'Match',{'id':who,'user_id':who,'candidate_id':other,'week':1,'slot':3,
                'revealed_at':'Wed:12','window_closes_at':'Wed:18'})
        for who in ('owner','partner'):
            r=self.request('/matches/'+who+'/actions',uid=who,method='POST',body={'action':'interest'})
            self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn',status='active')),1)

    def test_wall_clock_delays_and_payments_do_not_bypass_requirements(self):
        before=self.state()
        with mock.patch('accelerated_clock.position',side_effect=AssertionError('must not use elapsed clock')):
            self.assertEqual(self.state()['clock'],before['clock'])
        with mock.patch.dict('os.environ',{'PAYMENTS_ENABLED':'1'}):
            self.assertEqual(self.request(self.base+'/availability',method='PUT',body={'slots':[self.slot]}).status_code,403)
        self.assertEqual(db.fetch_all(self.conn,'Payment'),[])
        self.make_user('fourth')
        self.make_lockin('stranger','fourth','other-pair')
        other_clock=self.state('stranger')['clock']
        path=self.confirmed()
        for stage in ('date','debrief'):
            for who in ('owner','partner'): self.ready(path,who,stage)
        self.assertEqual(self.state('stranger')['clock'],other_clock)
