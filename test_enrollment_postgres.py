"""Local PostgreSQL enrollment races and continuous API-only journey."""
import concurrent.futures
import os
import tempfile
from pathlib import Path
import unittest
from unittest import mock
import db
import enrollment_service as service
import test_auth_postgres as pg
from test_enrollment_api import sections
import test_api_only_journey as e2e
from test_segment_efg_routes import RouteTestCase, app_module
from api_contract import ApiError


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'),'No isolated PostgreSQL configured')
class PostgresEnrollmentTests(unittest.TestCase):
    connect=pg.PostgresAuthenticationTests.connect
    cleanup=pg.PostgresAuthenticationTests.cleanup
    setUp=pg.PostgresAuthenticationTests.setUp
    def race(self,fn):
        def run(index):
            conn=self.connect()
            try:
                try:return fn(conn,index)
                except (ValueError,ApiError) as exc:return type(exc).__name__
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,range(2)))
    def test_contact_collision_serializes_invites(self):
        result=self.race(lambda c,i:service.invite(c,'new@example.test',apply=True))
        self.assertEqual(sum(isinstance(r,dict) for r in result),1)
        self.assertEqual(len(db.fetch_all(self.conn,'EnrollmentDraft')),1)
    def test_parallel_drafts_detect_stale_revision(self):
        uid=service.invite(self.conn,'new@example.test',apply=True)['user_id']
        self.conn.execute('UPDATE "Account" SET verified_email=1 WHERE user_id=%s',(uid,))
        data=sections();keys=['vision','activities']
        result=self.race(lambda c,i:service.write(c,uid,0,keys[i],data[keys[i]]))
        self.assertEqual(sum(isinstance(r,dict) for r in result),1)
        self.assertEqual(db.fetch_one(self.conn,'EnrollmentDraft',id=uid)['revision'],1)
    def test_duplicate_completion_is_one_atomic_pending_profile(self):
        uid=service.invite(self.conn,'new@example.test',apply=True)['user_id']
        self.conn.execute('UPDATE "Account" SET verified_email=1 WHERE user_id=%s',(uid,))
        for rev,(key,value) in enumerate(sections().items()):service.write(self.conn,uid,rev,key,value)
        result=self.race(lambda c,i:service.write(c,uid,3))
        self.assertEqual(result[0],result[1])
        self.assertEqual(result[0]['revision'],4)
        self.assertEqual(db.fetch_one(self.conn,'User',id=uid)['bgv_status'],'pending')


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'),'No isolated PostgreSQL configured')
class PostgresApiOnlyJourneyTests(unittest.TestCase):
    connect=pg.PostgresAuthenticationTests.connect
    cleanup=pg.PostgresAuthenticationTests.cleanup
    setup_profiles=e2e.ApiOnlyJourneyTests.setup_profiles
    call=e2e.ApiOnlyJourneyTests.call
    post=e2e.ApiOnlyJourneyTests.post
    sign=e2e.ApiOnlyJourneyTests.sign
    set_clock=RouteTestCase.set_clock
    test_two_dates_gate_road_married_and_revoked_tokens=e2e.ApiOnlyJourneyTests.test_two_dates_gate_road_married_and_revoked_tokens
    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        self.conn.execute('DELETE FROM "Account"')
        self.conn.execute('DELETE FROM "User"')
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        for p in (mock.patch.object(db,'get_connection',lambda *a,**k:self.connect()),
                mock.patch.object(app_module,'SIM_STATE_PATH',Path(tmp.name)/'clock.json'),
                mock.patch.dict(os.environ,{'PAYMENTS_ENABLED':'0','DEMO_MODE':'1','DHASHU_SIMULATED_CLOCK':'true'})):
            p.start();self.addCleanup(p.stop)
        self.client=app_module.app.test_client()
        self.setup_profiles()
