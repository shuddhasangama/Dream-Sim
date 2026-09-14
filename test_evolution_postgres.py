"""Isolated PostgreSQL retry and atomic append tests."""
import os,unittest,concurrent.futures
import db
import test_auth_postgres as pg
import after_date_service as service
import evolution_service
from clock import SimulationClock


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'),'No isolated PostgreSQL configured')
class PostgresEvolutionTests(unittest.TestCase):
    connect=pg.PostgresAuthenticationTests.connect
    cleanup=pg.PostgresAuthenticationTests.cleanup
    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        self.conn.execute('UPDATE "User" SET bgv_status=%s WHERE id=%s',('verified','owner'))
        self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)',('partner','dating','verified'))
        self.conn.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status,dates_completed) VALUES (%s,%s,%s,1,%s,%s,1)',('pair','owner','partner','test','active'))
        self.clock=SimulationClock.at(2,'Mon',12)
    def race(self,fn):
        def run(_):
            c=self.connect()
            try:return fn(c)
            finally:c.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,range(2)))
    def test_same_contact_request_is_one_row(self):
        result=self.race(lambda c:service.contact_request(c,'owner','pair','phone',self.clock))
        self.assertEqual(result[0],result[1])
        self.assertEqual(len(db.fetch_all(self.conn,'ContactRequest')),1)
    def test_next_level_open_is_atomic_under_retries(self):
        self.race(lambda c:service.next_level_action(c,'owner','pair',{},self.clock,True))
        self.assertEqual(len(db.fetch_all(self.conn,'NextLevelThread')),10)
    def test_vision_append_retries_do_not_fork_history(self):
        body={'request_id':'one','element_key':'children','detail_text':'Discuss'}
        self.race(lambda c:evolution_service.add_vision(c,'owner',body,self.clock))
        self.assertEqual(len(db.fetch_all(self.conn,'VisionEntry')),1)
