"""Isolated PostgreSQL acceptance, including competing confirmations."""
from test_segment_efg_routes import DATE_PREFS
import concurrent.futures
import json
import os
import unittest
from unittest.mock import patch
import db
import discovery
from api_contract import ApiError
from clock import SimulationClock
import test_auth_postgres as pg
import test_discovery_release as release


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'Local test DSN required')
class PostgresDiscoveryTests(unittest.TestCase):
    connect=pg.PostgresAuthenticationTests.connect
    cleanup=pg.PostgresAuthenticationTests.cleanup
    expose=release.DiscoveryTests.expose
    mutual=release.DiscoveryTests.mutual

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        flag=patch.dict(os.environ,{'DHASHU_DAILY_DISCOVERY':'1'});flag.start();self.addCleanup(flag.stop)
        for uid,gender in [('owner','female'),('partner','male'),('stranger','male')]:
            db.insert_row(self.conn,'User',dict(id=uid,journey_state='dating',bgv_status='verified',
                stats_json=json.dumps({'age':30,'gender':gender,'city':'Bangalore','diet':'Vegetarian',**DATE_PREFS}),   # client answer 3
                vision_json=json.dumps([{'key':'Intimacy','stance':['Emotional']},{'key':'Travel together','stance':[]}]),
                preferences_json=json.dumps({'fixed':{'dealbreakers':[]},'adjustable':{}})))
            account=db.fetch_one(self.conn,'Account',user_id=uid) or dict(id=uid,user_id=uid,created_at='test')
            account.update(auth_enabled=1,verification_required=1,verified_email=1)
            db.insert_row(self.conn,'Account',account)
        discovery.configure_market(self.conn,'BLR',dict(discovery=True,verification=True,payments=True,restaurants=True,support=True,paused=False))

    def test_competing_confirmation_race(self):
        first=self.mutual();second=self.mutual('stranger')
        clock=SimulationClock.at(1,'Mon',12)
        discovery.confirm(self.conn,'partner',first['id'],clock)
        discovery.confirm(self.conn,'stranger',second['id'],clock)
        def confirm(pid):
            conn=self.connect()
            try:
                try:return discovery.confirm(conn,'owner',pid,clock)['confirmed']
                except ApiError:return False
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(confirm,[first['id'],second['id']])),[False,True])
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryAllocation',user_id='owner')),1)


for name in ('test_views_are_not_holds_and_private_interest',
             'test_three_person_incompatible_choices_do_not_allocate',
             'test_own_reset_cannot_reverse_other_pass_or_block',
             'test_two_confirmations_required_and_city_pause_rechecked',
             'test_verified_visibility_and_unverified_cannot_like',
             'test_expired_proposal_and_changed_filter_cannot_confirm',
             'test_catalogue_review_conflict_preserves_answers_and_counts_once'):
    setattr(PostgresDiscoveryTests,name,getattr(release.DiscoveryTests,name))
