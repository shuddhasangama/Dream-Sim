"""Real PostgreSQL races for exactly-once date resolution."""
import concurrent.futures
from datetime import date
import os
import unittest
from unittest import mock
import db
import date_cycle_service as service
import guru_dating
import test_auth_postgres as pg
from clock import SimulationClock
from api_contract import ApiError


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'),'No isolated PostgreSQL configured')
class PostgresDateCycleTests(unittest.TestCase):
    connect=pg.PostgresAuthenticationTests.connect
    cleanup=pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        self.conn.execute('UPDATE "User" SET bgv_status=%s WHERE id=%s',('verified','owner'))
        self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)',('partner','dating','verified'))
        self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,1,%s,%s)',('pair','owner','partner','test','active'))
        self.conn.execute('INSERT INTO "DatePlan" (id,lockin_id,datetime,meal,bill_split,status) VALUES (%s,%s,%s,%s,%s,%s)',('plan','pair','2026-01-10T19:30','dinner','pay-your-own','confirmed'))
        self.clock=SimulationClock.at(1,'Sat',21)
        self.epoch=date(2026,1,5)

    def flags(self):
        for who in ('owner','partner'):
            service.flags(self.conn,who,'plan',{'green_flags':guru_dating.GREEN_FLAGS[:2],'red_flags':[]},self.clock,self.epoch)

    def race(self,action,users=('owner','partner')):
        def worker(who):
            conn=self.connect()
            try:
                try:
                    action(conn,who)
                    return 'ok'
                except ApiError as exc:return exc.code
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(worker,users))

    def test_simultaneous_continue_counts_once_and_keeps_history(self):
        self.flags()
        result=self.race(lambda c,u:service.decide(c,u,'plan',{'decision':'continue'},self.clock,self.epoch))
        self.assertEqual(result,['ok','ok'])
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='pair')['dates_completed'],1)
        self.assertEqual(len(db.fetch_all(self.conn,'DateResolution')),1)
        self.assertEqual(db.fetch_one(self.conn,'DatePlan',id='plan')['status'],'completed')

    def test_duplicate_last_partner_submission_resolves_once(self):
        self.flags()
        service.decide(self.conn,'owner','plan',{'decision':'continue'},self.clock,self.epoch)
        result=self.race(lambda c,u:service.decide(c,u,'plan',{'decision':'continue'},self.clock,self.epoch),('partner','partner'))
        self.assertEqual(result,['ok','ok'])
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='pair')['dates_completed'],1)

    def test_competing_cancellations_assess_one_charge(self):
        self.clock=SimulationClock.at(1,'Sat',18)
        with mock.patch.dict(os.environ,{'PAYMENTS_ENABLED':'1'}):
            result=self.race(lambda c,u:service.cancel(c,u,'plan',self.clock,self.epoch))
        self.assertEqual(sorted(result),['ok','state_conflict'])
        self.assertEqual(len(db.fetch_all(self.conn,'DateCharge')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'ComplianceEvent')),1)

    def test_competing_no_show_reports_cannot_increment_completed_dates(self):
        result=self.race(lambda c,u: service.no_show(c,u,'plan',self.clock,self.epoch))
        self.assertEqual(sorted(result),['ok','state_conflict'])
        self.assertEqual(db.fetch_one(self.conn,'LockIn',id='pair')['dates_completed'],0)
        self.assertEqual(db.fetch_all(self.conn,'ComplianceEvent'),[])
