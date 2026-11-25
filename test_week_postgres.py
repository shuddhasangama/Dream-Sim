"""Real PostgreSQL races for Week, on the isolated localhost fixture only."""
import concurrent.futures
import os
import unittest

import db
import week_service
from api_contract import ApiError
from clock import SimulationClock
import test_auth_postgres as pg


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresWeekTests(unittest.TestCase):
    connect = pg.PostgresAuthenticationTests.connect
    cleanup = pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        self.conn.execute('UPDATE "User" SET bgv_status = %s WHERE id = %s',('verified','owner'))
        for uid in ('partner','stranger'):
            self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)',(uid,'dating','verified'))
        self.clock = SimulationClock.at(1,'Mon',12)

    def match(self, uid, other, slot=1):
        mid=f'{uid}:1:{slot}'
        self.conn.execute('''INSERT INTO "Match" (id,user_id,candidate_id,week,slot,revealed_at,window_closes_at)
                             VALUES (%s,%s,%s,1,%s,%s,%s)''',
                          (mid,uid,other,slot,str(self.clock),str(SimulationClock.at(1,'Tue',12))))
        return mid

    def decide(self, args):
        uid, mid = args
        conn = self.connect()
        try:
            try:
                return week_service.decide(conn,uid,mid,'interest',None,self.clock)
            except ApiError as exc:
                return exc.code
        finally:
            conn.close()

    def test_simultaneous_reciprocal_decisions_create_one_pair(self):
        a=self.match('owner','partner')
        b=self.match('partner','owner')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            results=list(ex.map(self.decide,[('owner',a),('partner',b)]))
        self.assertTrue(all(isinstance(r,dict) for r in results),results)
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)
        self.assertTrue(self.decide(('owner',a))['replayed'])

    def test_forced_interleaving_of_mutual_likes_still_creates_exactly_one_pair(self):
        """perf-rowlock: make both transactions reach the decision at the same moment.
        Without row locks neither would see the other's uncommitted like (0 pairs);
        with them the second waits for the first and sees the committed like."""
        import threading
        from unittest import mock
        a=self.match('owner','partner')
        b=self.match('partner','owner')
        barrier=threading.Barrier(2)
        real=week_service.eligible_user
        def meet_then_check(conn,uid):
            try:
                barrier.wait(timeout=1)   # with row locks only one thread gets here at a time
            except threading.BrokenBarrierError:
                pass
            return real(conn,uid)
        with mock.patch.object(week_service,'eligible_user',meet_then_check):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                results=list(ex.map(self.decide,[('owner',a),('partner',b)]))
        self.assertTrue(all(isinstance(r,dict) for r in results),results)
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)

    def test_row_locks_do_not_block_unrelated_members(self):
        """perf-rowlock: a transaction holding one member must not block another member."""
        import threading
        self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)',('loner','dating','verified'))
        holder=self.connect()
        try:
            with holder.transaction():
                week_service.lock_users(holder,'owner','partner')
                done=threading.Event()
                def other():
                    conn=self.connect()
                    try:
                        with conn.transaction():
                            week_service.lock_users(conn,'stranger','loner')
                        done.set()
                    finally:
                        conn.close()
                t=threading.Thread(target=other);t.start();t.join(timeout=3)
                self.assertTrue(done.is_set(),"unrelated members were blocked by another pair's lock")
        finally:
            holder.close()

    def test_competing_pairs_cannot_lock_the_same_person_twice(self):
        a=self.match('owner','partner')
        b=self.match('partner','owner')
        c=self.match('owner','stranger',2)
        d=self.match('stranger','owner')
        self.decide(('partner',b))
        self.decide(('stranger',d))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            results=list(ex.map(self.decide,[('owner',a),('owner',c)]))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1,results)
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)

    def test_concurrent_preparation_adopts_legacy_rows_once(self):
        self.match('owner','partner')
        def prepare(_):
            conn=self.connect()
            try:
                return week_service.prepare(conn,'owner',self.clock)
            finally:
                conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            results=list(ex.map(prepare,range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(len(db.fetch_all(self.conn,'MatchBatch')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'Match')),1)

    def test_concurrent_fresh_preparation_is_reciprocal_per_slot(self):
        import json
        from unittest.mock import patch
        for uid,gender in [('owner','male'),('partner','female'),('stranger','male')]:
            self.conn.execute('UPDATE "User" SET journey_state=%s,stats_json=%s WHERE id=%s',('dating',json.dumps({'city':'Bengaluru','gender':gender}),uid))
            if uid!='owner':
                self.conn.execute('INSERT INTO "Account" (id,user_id,created_at,auth_enabled,verified_phone) VALUES (%s,%s,0,1,1)',(uid,uid))
        self.conn.execute('UPDATE "Account" SET verified_phone=1')
        def prepare(uid):
            conn=self.connect()
            try:return week_service.prepare(conn,uid,self.clock)
            finally:conn.close()
        with patch('async_rehearsal.enabled',return_value=False), patch('fixed_test_pairs.configured',return_value={}):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                list(ex.map(prepare,['owner','partner','stranger']))
        rows=db.fetch_all(self.conn,'Match')
        self.assertTrue(rows)
        for row in rows:
            reciprocal=[r for r in rows if r['user_id']==row['candidate_id'] and r['candidate_id']==row['user_id'] and r['slot']==row['slot']]
            self.assertEqual(len(reciprocal),1)
            competing=[r for r in rows if r['candidate_id']==row['candidate_id'] and r['slot']==row['slot']]
            self.assertEqual(len(competing),1)
