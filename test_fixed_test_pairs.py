"""Synthetic pair isolation, rollback, verification and delayed-partner progression."""
import os
import time
from unittest import mock

import auth_sessions
import async_rehearsal
import clock
import db
import fixed_test_pairs as fixed
import signup_verification
import week_service
from test_segment_efg_routes import RouteTestCase, app_module


class FixedPairTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.a, self.b = fixed.PREFIX+'f06', fixed.PREFIX+'m06'
        patch = mock.patch.dict(os.environ, {
            'DHASHU_ASYNC_TEST':'true', 'DHASHU_FIXED_TEST_PAIRS':'06',
            'DHASHU_TESTER_NO_OTP':'true', 'DHASHU_TESTER_USER_IDS':f'{self.a},{self.b}',
            'DHASHU_TEST_START_WEEK':'39'})
        patch.start(); self.addCleanup(patch.stop)
        for uid in (self.a, self.b, 'outsider'):
            self.make_user(uid)
            db.insert_row(self.conn, 'Account', {'id':uid, 'user_id':uid,
                'email':uid+'@test.example', 'auth_enabled':1,
                'verification_required':1, 'verified_email':0, 'verified_phone':0,
                'created_at':'test'})

    def assign(self):
        with week_service.transition(self.conn):
            return fixed.assign(self.conn, self.a, 39)

    def test_assign_reciprocal_once_and_preserve_decisions(self):
        self.assertIn('ASSIGNED', self.assign())
        self.assertEqual(len(db.fetch_all(self.conn, 'Match')), 2)
        week_service.decide(self.conn, self.a, f'fixed:{self.a}:39:1', 'interest', None,
                            clock.SimulationClock.at(39,'Mon',12))
        before = list(self.conn.iterdump())
        self.assertIn('ALREADY', self.assign())
        self.assertEqual(before, list(self.conn.iterdump()))

    def test_mutual_interest_skips_intro_but_one_sided_does_not(self):
        self.assign()
        with mock.patch.object(async_rehearsal.time, 'time', return_value=1000):
            for uid in (self.a, self.b):
                async_rehearsal.start_intro(self.conn, uid)
        with mock.patch.object(async_rehearsal.time, 'time', return_value=1181):
            when = clock.SimulationClock.at(39,'Mon',12)
            week_service.decide(self.conn,self.a,f'fixed:{self.a}:39:1','interest',None,when)
            self.assertEqual(async_rehearsal.intro(self.conn,self.a)[1],1)
            week_service.decide(self.conn,self.b,f'fixed:{self.b}:39:1','interest',None,when)
            for uid in (self.a,self.b):
                self.assertTrue(async_rehearsal.intro_complete(self.conn,uid))
                point, meta = async_rehearsal.snapshot(self.conn,uid)
                self.assertEqual(str(point),'Wed:18')
                self.assertEqual(meta['stage'],'availability')
            before = list(self.conn.iterdump())
            self.assertIn('PRESERVED', self.assign())
            self.assertEqual(before,list(self.conn.iterdump()))

    def test_test_waiver_does_not_fake_verification_and_switches_off(self):
        a=db.fetch_one(self.conn,'Account',user_id=self.a)
        self.assertFalse(signup_verification.is_satisfied(a))
        self.assertTrue(signup_verification.matching_satisfied(a))
        self.assertFalse(signup_verification.matching_satisfied(db.fetch_one(self.conn,'Account',user_id='outsider')))
        for key in ('DHASHU_ASYNC_TEST','DHASHU_TESTER_NO_OTP','DHASHU_SIMULATED_CLOCK'):
            with mock.patch.dict(os.environ,{key:'false'}):
                self.assertFalse(signup_verification.matching_satisfied(a))
        with mock.patch.dict(os.environ,{'DHASHU_TESTER_USER_IDS':''}):
            self.assertFalse(signup_verification.matching_satisfied(a))
        self.assertEqual(a,db.fetch_one(self.conn,'Account',user_id=self.a))

    def test_recorded_incoming_decision_prevents_reassignment(self):
        db.insert_row(self.conn,'Match',{'id':'old','user_id':'outsider','candidate_id':self.a,
            'week':39,'slot':1,'revealed_at':'Mon:12','window_closes_at':'Tue:12','action':'interest'})
        before=list(self.conn.iterdump())
        with self.assertRaisesRegex(ValueError,'Recorded decision'):
            self.assign()
        self.assertEqual(before,list(self.conn.iterdump()))

    def test_disabled_partner_and_foreign_active_pair_are_preserved(self):
        self.conn.execute('UPDATE Account SET auth_enabled=0 WHERE user_id=?',(self.b,)); self.conn.commit()
        with self.assertRaisesRegex(ValueError,'enabled'):
            self.assign()
        self.conn.execute('UPDATE Account SET auth_enabled=1 WHERE user_id=?',(self.b,)); self.conn.commit()
        self.make_lockin(self.a,'outsider')
        with self.assertRaisesRegex(ValueError,'another user'):
            self.assign()

    def test_dry_run_transaction_rolls_back_and_prepare_keeps_one(self):
        before=list(self.conn.iterdump())
        with self.assertRaisesRegex(RuntimeError,'dry'):
            with week_service.transition(self.conn):
                fixed.assign(self.conn,self.a,39)
                raise RuntimeError('dry')
        self.assertEqual(before,list(self.conn.iterdump()))
        self.assign()
        rows=week_service.prepare(self.conn,self.a,clock.SimulationClock.at(39,'Mon',10))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['candidate_id'],self.b)
        self.assertFalse(fixed.permits('outsider',self.a))
        with mock.patch.dict(os.environ,{'DHASHU_FIXED_TEST_PAIRS':''}):
            self.assertTrue(fixed.permits('outsider',self.a))

    def test_api_advertises_interest_to_approved_unverified_tester(self):
        self.assign()
        with app_module.app.test_request_context('/'):
            with mock.patch.object(app_module,'get_clock',return_value=clock.SimulationClock.at(39,'Mon',12)):
                user=app_module.load_user(self.a)
                row=db.fetch_one(self.conn,'Match',user_id=self.a,week=39)
                self.assertIn('interest',app_module._api_match_view(user,row)['allowed_actions'])
