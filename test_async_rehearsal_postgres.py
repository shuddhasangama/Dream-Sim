"""Readiness serialization on the existing disposable local PostgreSQL harness."""
import os
import unittest
from unittest import mock
import async_rehearsal
import db
import test_planning_postgres as planning_tests


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL configured')
class PostgresRehearsalTests(unittest.TestCase):
    connect=planning_tests.PostgresPlanningTests.connect
    cleanup=planning_tests.PostgresPlanningTests.cleanup
    run_pair=planning_tests.PostgresPlanningTests.run_pair
    confirm=planning_tests.PostgresPlanningTests.confirm

    def setUp(self):
        planning_tests.PostgresPlanningTests.setUp(self)
        patch=mock.patch.dict('os.environ',{'DHASHU_SIMULATED_CLOCK':'true','DHASHU_ASYNC_TEST':'true','DHASHU_TEST_START_WEEK':'1'})
        patch.start(); self.addCleanup(patch.stop)
        self.confirm(self.conn,'owner')
        self.conn.execute('UPDATE "DatePlan" SET status=%s WHERE id=%s',('confirmed','plan:pair'))

    def test_concurrent_partner_actions_and_retries(self):
        for step in ('date','debrief'):
            for _ in range(2):
                self.run_pair(lambda conn,uid:async_rehearsal.mark_ready(conn,uid,'plan:pair',step))
        self.assertEqual(len(db.fetch_all(self.conn,'RehearsalReady')),4)
        self.assertEqual(async_rehearsal.snapshot(self.conn,'owner')[1]['stage'],'debrief')
        self.assertEqual(db.fetch_all(self.conn,'DateFeedback'),[])
        self.assertEqual(db.fetch_all(self.conn,'DateOutcome'),[])

    def test_write_failure_rolls_back(self):
        import planning_service
        original=planning_service.sql
        def failed(conn,statement,values=()):
            result=original(conn,statement,values)
            if statement.startswith('INSERT INTO "RehearsalReady"'): raise RuntimeError('after insert')
            return result
        with mock.patch.object(planning_service,'sql',side_effect=failed):
            with self.assertRaises(RuntimeError): async_rehearsal.mark_ready(self.conn,'owner','plan:pair','date')
        self.assertEqual(db.fetch_all(self.conn,'RehearsalReady'),[])

    def test_concurrent_intro_start_is_idempotent_and_transfer_rolls_back(self):
        import week_service
        self.conn.execute('DELETE FROM "DatePlan"')
        self.conn.execute('DELETE FROM "Availability"')
        self.conn.execute('DELETE FROM "LockIn"')
        self.run_pair(lambda conn,uid:async_rehearsal.start_intro(conn,'owner'))
        self.assertEqual(len(db.fetch_all(self.conn,'RehearsalIntro')),1)
        self.conn.execute('UPDATE "RehearsalIntro" SET started_at=%s',('0',))
        self.run_pair(lambda conn,uid:async_rehearsal.save_draft(conn,'owner',[{'day':'Sat','meal_slot':'dinner'}]))
        before=db.fetch_one(self.conn,'RehearsalIntro',id='owner')['slots_json']
        with self.assertRaises(RuntimeError):
            with week_service.transition(self.conn):
                self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,1,%s,%s)',('new','owner','partner','test','active'))
                async_rehearsal.transfer_drafts(self.conn,'new',('owner','partner'),1)
                raise RuntimeError('injected after transfer')
        self.assertEqual(db.fetch_all(self.conn,'LockIn'),[])
        self.assertEqual(db.fetch_all(self.conn,'Availability'),[])
        self.assertEqual(db.fetch_one(self.conn,'RehearsalIntro',id='owner')['slots_json'],before)
