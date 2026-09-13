"""Date-plan and signature races against a disposable localhost PostgreSQL."""
import concurrent.futures
import json
import os
import unittest
from unittest import mock
import ceremony
import db
import planning_service as service
import test_auth_postgres as pg
from api_contract import ApiError


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL configured')
class PostgresPlanningTests(unittest.TestCase):
    connect = pg.PostgresAuthenticationTests.connect
    cleanup = pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        patch = mock.patch.dict(os.environ, {'PAYMENTS_ENABLED': '0'})
        patch.start()
        self.addCleanup(patch.stop)
        self.conn.execute('UPDATE "User" SET bgv_status=%s WHERE id=%s', ('verified', 'owner'))
        self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)', ('partner','dating','verified'))
        stats=json.dumps({'budget':['₹1,500–2,500'], 'diet':'Vegetarian', 'cuisine':['Thai']})
        self.conn.execute('UPDATE "User" SET stats_json=%s', (stats,))
        self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,1,%s,%s)', ('pair','owner','partner','test','active'))
        for who in ('owner','partner'):
            self.conn.execute('INSERT INTO "Availability" (id,lockin_id,user_id,day,meal_slot) VALUES (%s,%s,%s,%s,%s)', (who,'pair',who,'Sat','dinner'))

    def run_pair(self, fn):
        def worker(who):
            conn=self.connect()
            try:
                return fn(conn,who)
            finally:
                conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(worker, ['owner','partner']))

    def confirm(self, conn, who):
        return service.confirm(conn,who,'pair','Sat','dinner',lambda *args:'2026-09-19T19:30')

    def test_simultaneous_confirmation_creates_exactly_one_plan(self):
        result=self.run_pair(self.confirm)
        self.assertEqual(result[0]['id'], result[1]['id'])
        self.assertEqual(len(db.fetch_all(self.conn,'DatePlan')),1)

    def test_simultaneous_completions_confirm_both_signatures(self):
        self.confirm(self.conn,'owner')
        for who in ('owner','partner'):
            service.agreement(self.conn,who,'plan:pair',{'step':'playbook'},'test',lambda _:True)
            service.agreement(self.conn,who,'plan:pair',{'step':'sign','signed_name':who,'acks':list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))},'test',lambda _:True)
        self.run_pair(lambda conn,who:service.agreement(conn,who,'plan:pair',{'step':'face'},'test',lambda _:True))
        self.assertEqual(len(db.fetch_all(self.conn,'Signature')),2)
        self.assertEqual(db.fetch_one(self.conn,'DatePlan',id='plan:pair')['status'],'confirmed')

    def test_failed_signature_mirror_rolls_back_ceremony(self):
        self.confirm(self.conn,'owner')
        service.agreement(self.conn,'owner','plan:pair',{'step':'playbook'},'test',lambda _:True)
        service.agreement(self.conn,'owner','plan:pair',{'step':'sign','signed_name':'Name','acks':list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))},'test',lambda _:True)
        with mock.patch.object(service,'persist_signature',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                service.agreement(self.conn,'owner','plan:pair',{'step':'face'},'test',lambda _:True)
        state=service.agreement_state(self.conn,'owner','plan:pair','test')
        self.assertEqual(ceremony.next_step(state),'face')
        self.assertEqual(db.fetch_all(self.conn,'Signature'),[])

    def test_availability_change_racing_confirmation_has_consistent_result(self):
        def action(conn,who):
            try:
                if who == 'owner':
                    self.confirm(conn,who)
                    return 'confirmed'
                service.availability(conn,who,'pair',[])
                return 'cleared'
            except ApiError as exc:
                return exc.code
        results=self.run_pair(action)
        plans=db.fetch_all(self.conn,'DatePlan')
        if plans:
            self.assertEqual(results,['confirmed','state_conflict'])
            self.assertTrue(service.slots(self.conn,'pair','partner'))
        else:
            self.assertEqual(results,['overlap_required','cleared'])
