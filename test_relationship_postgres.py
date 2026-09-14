"""PostgreSQL concurrent stage advancement and independent partner writes."""
import os,unittest,concurrent.futures
import db,journey,ceremony
import relationship_service as service
import road_service
import test_auth_postgres as pg
from clock import SimulationClock

@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'),'No isolated PostgreSQL configured')
class PostgresRelationshipTests(unittest.TestCase):
    connect=pg.PostgresAuthenticationTests.connect
    cleanup=pg.PostgresAuthenticationTests.cleanup
    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        self.conn.execute('UPDATE "User" SET bgv_status=%s WHERE id=%s',('verified','owner'))
        self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)',('partner','dating','verified'))
        journey.advance_stage(self.conn,'pair',True,True,today='2026-01-05',user_a_id='owner',user_b_id='partner')
        self.clock=SimulationClock.at(1,'Mon',12)
    def race(self,fn,users=('owner','partner')):
        def run(uid):
            c=self.connect()
            try:return fn(c,uid)
            finally:c.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,users))
    def test_simultaneous_stage_advance_is_exactly_once(self):
        for uid in ('owner','partner'):
            s=ceremony.new_state(uid,ceremony.STAGE_GATE,service.checkpoint_scope('pair','relationship'),'test')
            s=ceremony.sign(ceremony.ack_playbook(s),uid,list(ceremony.ack_keys(ceremony.STAGE_GATE)),'test')
            db.insert_row(self.conn,'Ceremony',ceremony.complete(ceremony.capture_face(s),'test'))
        self.race(lambda c,u:service.advance(c,u,'pair','relationship',self.clock,'2026-01-05'))
        self.assertEqual(db.fetch_one(self.conn,'Couple',id='pair')['stage'],'engaged')
        self.assertEqual(len(db.fetch_all(self.conn,'JourneyAction',kind='advance')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'Playbook')),2)
    def test_parallel_ideas_do_not_lose_partner_update(self):
        self.race(lambda c,u:service.idea(c,u,'pair',{'request_id':'idea','stage':'relationship','idea':u},self.clock))
        book=db.fetch_one(self.conn,'Playbook',couple_id='pair',stage='relationship')
        self.assertEqual(set(db.load_json_field(book['tier_custom_json'],[])),{'owner','partner'})
    def test_same_road_request_retried_concurrently_is_one_block(self):
        body={'request_id':'block','category':'free','days':['Mon'],'label':'Quiet time','start':'17:00','end':'20:00'}
        self.race(lambda c,u:road_service.block(c,u,'pair',body,self.clock),('owner','owner'))
        road=road_service.road(self.conn,'owner','pair')
        self.assertEqual(len(db.load_json_field(road['routine_json'],[])),1)
