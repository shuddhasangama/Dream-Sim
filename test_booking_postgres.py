"""Phase 3 races on a disposable PostgreSQL cluster, never Railway."""
import concurrent.futures
import json
import os
import unittest
from unittest import mock

import booking_coordination as booking
import db
import planning_service as planning
import test_auth_postgres as pg
from api_contract import ApiError


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL configured')
class BookingPostgresTests(unittest.TestCase):
    connect = pg.PostgresAuthenticationTests.connect
    cleanup = pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        flag = mock.patch.dict(os.environ, {'DHASHU_BOOKING_COORDINATION_ENABLED':'1', 'PAYMENTS_ENABLED':'0', 'DHASHU_ASYNC_TEST':'false'})
        flag.start()
        self.addCleanup(flag.stop)
        self.conn.execute('UPDATE "User" SET bgv_status=%s WHERE id=%s', ('verified', 'owner'))
        self.conn.execute('INSERT INTO "User" (id, journey_state, bgv_status) VALUES (%s,%s,%s)', ('partner','dating','verified'))
        import date_alignment
        stats = {'city':'Bengaluru','diet':'Vegetarian','cuisine':['Thai'],'budget':[date_alignment.options_for('budget','Bengaluru')[0]]}
        self.conn.execute('UPDATE "User" SET stats_json=%s', (json.dumps(stats),))
        self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,1,%s,%s)', ('pair','owner','partner','test','active'))
        for who in ('owner','partner'):
            self.conn.execute('INSERT INTO "Availability" (id,lockin_id,user_id,day,meal_slot) VALUES (%s,%s,%s,%s,%s)', (who,'pair',who,'Sat','dinner'))
            current=booking.view(self.conn,who,'pair')
            booking.update(self.conn,who,'pair',{'scope':current['scope'],'revision':0,'neighbourhoods':['indiranagar']})

    def parallel(self, fn):
        def worker(who):
            conn=self.connect()
            try:
                return fn(conn,who)
            finally:
                conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker,['owner','partner']))

    def test_both_confirm_creates_one_snapshot_and_plan(self):
        result=self.parallel(lambda c,u: planning.confirm(c,u,'pair','Sat','dinner',lambda *a:'2026-10-24T19:30'))
        self.assertEqual(result[0]['id'],result[1]['id'])
        self.assertEqual(len(db.fetch_all(self.conn,'DatePlan')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'BookingSnapshot')),1)

    def test_concurrent_edits_reject_stale_revision(self):
        state=booking.view(self.conn,'owner','pair')
        def change(conn, who):
            try:
                booking.update(conn,'owner','pair',{'scope':state['scope'],'revision':state['revision'],
                    'neighbourhoods':['jayanagar' if who=='owner' else 'koramangala']})
                return 'saved'
            except ApiError as exc:
                return exc.code
        self.assertCountEqual(self.parallel(change), ['saved','state_conflict'])
