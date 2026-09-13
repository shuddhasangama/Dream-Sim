"""Isolated date lifecycle tests, no external provider or database calls."""
import os
from unittest import mock
import auth_sessions
import db
import guru_dating
import date_cycle_service as service
import test_week_api
from test_segment_efg_routes import RouteTestCase, app_module


class DateCycleApiTests(RouteTestCase):
    request=test_week_api.WeekApiTests.request

    def setUp(self):
        super().setUp()
        p=mock.patch.dict(app_module.app.config, {'AUTH_ENABLED':True})
        p.start(); self.addCleanup(p.stop)
        self.headers={}
        for uid in ('owner','partner','stranger'):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'email':uid+'@test.example','auth_enabled':1,'created_at':'test'})
            self.headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
        self.make_lockin('owner','partner')
        self.make_plan('lock-1',plan_id='plan:lock-1',status='confirmed')
        self.path='/date-plans/plan:lock-1'
        self.set_clock(day='Sat',hour=21)

    def flags(self,who,path=None,**extra):
        return self.request((path or self.path)+'/feedback/flags',uid=who,method='PUT',body={'green_flags':guru_dating.GREEN_FLAGS[:2],'red_flags':[],**extra})

    def decision(self,who,choice='continue',path=None):
        return self.request((path or self.path)+'/feedback/decision',uid=who,method='POST',body={'decision':choice})

    def test_two_dates_preserve_history_and_stale_retries_do_not_touch_new_cycle(self):
        for who in ('owner','partner'):
            self.assertEqual(self.flags(who).status_code,200)
            self.assertEqual(self.decision(who).status_code,200)
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],1)
        self.assertEqual(db.fetch_one(self.conn,'DatePlan',id='plan:lock-1')['status'],'completed')
        # Prepare the next date through the actual JSON alignment/calendar boundary.
        base='/lock-ins/lock-1'
        for who in ('partner','owner'):
            options=self.request(base+'/calendar',uid=who).json['data']['alignment']['options']
            body={k: options[k][0] if k=='diet' else [options[k][0]] for k in options}
            self.assertEqual(self.request(base+'/alignment',uid=who,method='PUT',body=body).status_code,200)
            self.assertEqual(self.request(base+'/availability',uid=who,method='PUT',body={'slots':[{'day':'Sat','meal_slot':'dinner'}]}).status_code,200)
        slot={'day':'Sat','meal_slot':'dinner'}
        self.assertEqual(self.request(base+'/date-plan',method='POST',body=slot).status_code,409)
        response=self.request(base+'/date-plan',method='POST',body={**slot,'cycle':2})
        self.assertEqual(response.status_code,200,response.json)
        next_path='/date-plans/'+response.json['data']['id']
        # Sign both via the implemented agreement API (explicit local simulation).
        import ceremony
        with mock.patch.dict(os.environ,{'BETA_DATE_SIMULATION_ENABLED':'1'}),mock.patch.object(app_module.dateplan,'verify_face',return_value=True):
            for who in ('owner','partner'):
                for body in ({'step':'playbook'},{'step':'sign','signed_name':who,'acks':list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))},{'step':'face'}):
                    r=self.request(next_path+'/agreement/steps',uid=who,method='POST',body=body)
                    self.assertEqual(r.status_code,200,r.json)
        before=list(self.conn.iterdump())
        self.assertEqual(self.decision('owner').status_code,200)
        self.assertEqual(self.decision('owner','pass').status_code,409)
        self.assertEqual(self.request(self.path+'/no-show',method='POST',body={}).status_code,409)
        self.assertEqual(list(self.conn.iterdump()),before)
        self.set_clock(week=2,day='Sat',hour=21)
        for who in ('partner','owner'):
            self.assertEqual(self.flags(who,next_path).status_code,200)
            self.assertEqual(self.decision(who,path=next_path).status_code,200)
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],2)
        self.assertEqual(len(db.fetch_all(self.conn,'DatePlan')),2)
        self.assertEqual(len(db.fetch_all(self.conn,'DateResolution')),2)
        self.assertEqual(len(db.fetch_all(self.conn,'DateOutcome')),2)

    def test_either_actor_can_reject_without_forcing_the_other_to_confirm(self):
        self.flags('partner')
        self.assertEqual(self.decision('partner','pass').json['data']['resolution'],'rejected')
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['status'],'released')
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],0)
        self.assertEqual(self.decision('partner','pass').status_code,200)

    def test_early_feedback_invalid_flags_and_foreign_access_are_rejected(self):
        self.set_clock(day='Sat',hour=20)
        self.assertEqual(self.flags('owner').status_code,409)
        self.assertEqual(self.decision('owner').status_code,409)
        self.assertEqual(self.request(self.path+'/no-show',method='POST',body={}).status_code,409)
        self.assertEqual(self.flags('stranger').status_code,404)
        self.assertEqual(self.request(self.path+'/debrief',uid='stranger').status_code,404)
        self.assertEqual(db.fetch_all(self.conn,'DateFeedback'),[])

    def test_private_flags_and_mutual_consent(self):
        self.flags('owner',together_photo=True)
        result=self.request(self.path+'/debrief',uid='partner').json['data']
        self.assertEqual(result['my_feedback']['green_flags'],[])
        self.assertFalse(result['mutual_photo_consent']['together_photo'])
        self.flags('partner',together_photo=True)
        self.assertTrue(self.request(self.path+'/debrief').json['data']['mutual_photo_consent']['together_photo'])
        self.flags('owner',together_photo=False)
        self.assertFalse(self.request(self.path+'/debrief').json['data']['mutual_photo_consent']['together_photo'])

    def test_no_show_is_a_report_not_a_finding_and_does_not_count_date(self):
        r=self.request(self.path+'/no-show',method='POST',body={})
        self.assertEqual(r.status_code,200,r.json)
        self.assertFalse(r.json['data']['no_show_is_confirmed'])
        self.assertEqual(db.fetch_all(self.conn,'ComplianceEvent'),[])
        self.assertEqual(db.fetch_all(self.conn,'DateOutcome'),[])
        before=list(self.conn.iterdump())
        self.assertEqual(self.request(self.path+'/no-show',method='POST',body={}).status_code,200)
        self.assertEqual(list(self.conn.iterdump()),before)

    def test_late_cancellation_is_charged_once_and_cannot_cancel_started_date(self):
        self.set_clock(day='Sat',hour=18)
        with mock.patch.dict(os.environ,{'PAYMENTS_ENABLED':'1'}):
            for _ in range(2):
                self.assertEqual(self.request(self.path+'/cancel',method='POST',body={}).status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'ComplianceEvent')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'DateCharge')),1)
        self.assertEqual(db.fetch_all(self.conn,'DateCharge')[0]['status'],'pending')

    def test_early_cancel_has_no_fee_or_strike(self):
        self.set_clock(day='Thu',hour=12)
        self.assertEqual(self.request(self.path+'/cancel',method='POST',body={}).status_code,200)
        self.assertEqual(db.fetch_all(self.conn,'ComplianceEvent'),[])
        self.assertEqual(db.fetch_all(self.conn,'Payment'),[])

    def test_resolution_failure_rolls_back_partner_decision_and_count(self):
        for who in ('owner','partner'): self.flags(who)
        self.decision('owner')
        before=list(self.conn.iterdump())
        with mock.patch.object(service,'finish',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                service.decide(self.conn,'partner','plan:lock-1',{'decision':'continue'},app_module.get_clock(),app_module.WEEK_ONE_MONDAY)
        self.assertEqual(list(self.conn.iterdump()),before)

    def test_read_does_not_resolve_timeout(self):
        self.set_clock(week=2,day='Mon',hour=12)
        before=list(self.conn.iterdump())
        self.request(self.path+'/debrief')
        self.assertEqual(list(self.conn.iterdump()),before)
        self.assertEqual(self.flags('owner').status_code,409)
        self.assertEqual(self.request(self.path+'/feedback/reconcile',method='POST',body={}).json['data']['resolution'],'ghosted')
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],0)

    def test_both_relationship_opens_one_gate_without_advancing_stage(self):
        for who in ('partner','owner'):
            self.flags(who)
            self.assertEqual(self.decision(who,'relationship').status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'StageGate')),1)
        self.decision('owner','relationship')
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='lock-1')['dates_completed'],1)
        self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['journey_state'],'dating')
