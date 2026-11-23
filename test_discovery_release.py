"""Release acceptance: private discovery, mutual allocation and editable catalogue."""
import concurrent.futures
import json
import os
from unittest.mock import patch
import db
import discovery
import activity_catalog
import onboarding
import vision_plans
from api_contract import ApiError
from test_week_api import WeekApiTests
from test_self_signup import SelfSignupTests


class AgeSignupTests(SelfSignupTests):
    def test_age_only_signup_and_invalid_ages(self):
        uid,headers=self.signup()
        body=self.stats();body.pop('name');body.pop('dob');body['age']=29
        result=self.client.put('/api/v1/signup/stats',headers=headers,json=body)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['data']['values']['age'],29)
        self.assertEqual(result.json['data']['values']['name'],'')
        for age in [17,121,18.5,True,'29',None]:
            body['age']=age
            self.assertEqual(self.client.put('/api/v1/signup/stats',headers=headers,json=body).status_code,400,age)
        stats=db.load_json_field(db.fetch_one(self.conn,'User',id=uid)['stats_json'],{})
        self.assertEqual(stats['declared_age'],29)
        self.assertEqual(stats['declared_gender'],'female')


class DiscoveryTests(WeekApiTests):
    # Do not inherit the legacy API acceptance cases: this is the opt-in mode.
    def setUp(self):
        super().setUp()
        flag=patch.dict(os.environ,{'DHASHU_DAILY_DISCOVERY':'1'});flag.start();self.addCleanup(flag.stop)
        for uid,gender in [('owner','female'),('partner','male'),('stranger','male')]:
            row=db.fetch_one(self.conn,'User',id=uid)
            row['stats_json']=json.dumps({'age':30,'gender':gender,'city':'Bangalore'})
            row['vision_json']=json.dumps([{'key':'Intimacy','stance':['Emotional']},{'key':'Travel together','stance':[]}])
            db.insert_row(self.conn,'User',row)
        discovery.configure_market(self.conn,'BLR',dict(discovery=True,verification=True,payments=True,restaurants=True,support=True,paused=False))

    def expose(self):
        for uid in ('owner','partner','stranger'):discovery.prepare(self.conn,uid,1)

    def mutual(self,other='partner'):
        self.expose()
        discovery.act(self.conn,'owner',other,'interest',1)
        discovery.act(self.conn,other,'owner','interest',1)
        return next(r for r in db.fetch_all(self.conn,'DiscoveryProposal') if other in (r['user_a'],r['user_b']))

    def test_api_is_authenticated_and_get_does_not_allocate(self):
        before=len(db.fetch_all(self.conn,'DiscoveryExposure'))
        result=self.request('/week')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['data']['mode'],'discovery')
        self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryExposure')),before)
        result=self.request('/discovery/prepare',method='POST',body={})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(len(result.json['data']['profiles']),2)
        self.assertEqual(self.client.get('/api/v1/discovery').status_code,401)

    def test_wednesday_allocates_following_weekend(self):
        from clock import SimulationClock
        clock=SimulationClock.at(1,'Wed',12)
        self.assertEqual(discovery.cycle_for(clock),2)
        for uid in ('owner','partner'):discovery.prepare(self.conn,uid,2)
        discovery.act(self.conn,'owner','partner','interest',2)
        discovery.act(self.conn,'partner','owner','interest',2)
        row=db.fetch_all(self.conn,'DiscoveryProposal')[0]
        discovery.confirm(self.conn,'owner',row['id'],clock)
        discovery.confirm(self.conn,'partner',row['id'],clock)
        self.assertEqual(db.fetch_all(self.conn,'LockIn')[0]['week'],2)

    def test_views_are_not_holds_and_private_interest(self):
        self.expose()
        self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryExposure',user_id='owner')),2)
        discovery.prepare(self.conn,'owner',1)
        self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryExposure',user_id='owner')),2)
        discovery.act(self.conn,'partner','owner','interest',1)
        snapshot=discovery.snapshot(self.conn,'owner',1)
        self.assertEqual(snapshot['proposals'],[])
        self.assertTrue(all(p['action']=='none' for p in snapshot['profiles']))
        self.assertEqual(db.fetch_all(self.conn,'LockIn'),[])
        self.assertNotIn('name',snapshot['profiles'][0])

    def test_three_person_incompatible_choices_do_not_allocate(self):
        self.expose()
        discovery.act(self.conn,'partner','owner','pass',1)
        discovery.act(self.conn,'stranger','owner','interest',1)
        discovery.act(self.conn,'owner','stranger','pass',1)
        with self.assertRaises(ApiError):discovery.act(self.conn,'owner','partner','interest',1)
        self.assertEqual(db.fetch_all(self.conn,'DiscoveryProposal'),[])
        self.assertEqual(db.fetch_all(self.conn,'LockIn'),[])

    def test_own_reset_cannot_reverse_other_pass_or_block(self):
        self.expose()
        discovery.act(self.conn,'owner','partner','pass',1)
        discovery.act(self.conn,'partner','owner','pass',1)
        discovery.act(self.conn,'owner','partner','reset',1)
        self.assertTrue(discovery.excluded(self.conn,'owner','partner'))
        discovery.act(self.conn,'owner','stranger','block',1)
        with self.assertRaises(ApiError):discovery.act(self.conn,'owner','stranger','reset',1)

    def test_reset_same_second_waits_for_next_day_without_duplicate_exposure(self):
        with patch('discovery.time.time',return_value=1795430000):
            self.expose()
            discovery.act(self.conn,'owner','partner','pass',1)
            discovery.act(self.conn,'owner','partner','reset',1)
            discovery.prepare(self.conn,'owner',1)
            self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryExposure',user_id='owner')),2)
            with patch('discovery.day',return_value='2026-11-24'):
                discovery.prepare(self.conn,'owner',1)
                self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryExposure',user_id='owner')),3)

    def test_two_confirmations_required_and_city_pause_rechecked(self):
        proposal=self.mutual()
        from clock import SimulationClock
        clock=SimulationClock.at(1,'Mon',12)
        self.assertFalse(discovery.confirm(self.conn,'owner',proposal['id'],clock)['confirmed'])
        self.assertEqual(db.fetch_all(self.conn,'LockIn'),[])
        discovery.configure_market(self.conn,'BLR',dict(discovery=True,verification=True,payments=True,restaurants=True,support=True,paused=True))
        with self.assertRaises(ApiError):discovery.confirm(self.conn,'partner',proposal['id'],clock)
        discovery.configure_market(self.conn,'BLR',dict(discovery=True,verification=True,payments=True,restaurants=True,support=True,paused=False))
        self.assertTrue(discovery.confirm(self.conn,'partner',proposal['id'],clock)['confirmed'])
        discovery.configure_market(self.conn,'BLR',dict(discovery=True,verification=True,payments=True,restaurants=True,support=True,paused=True))
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn',status='active')),1)

    def test_competing_confirmation_race_only_one_allocation(self):
        first=self.mutual();second=self.mutual('stranger')
        from clock import SimulationClock
        clock=SimulationClock.at(1,'Mon',12)
        discovery.confirm(self.conn,'partner',first['id'],clock)
        discovery.confirm(self.conn,'stranger',second['id'],clock)
        path=self.conn.execute('PRAGMA database_list').fetchone()[2]
        def confirm(pid):
            conn=db.get_connection(path)
            try:
                try:return discovery.confirm(conn,'owner',pid,clock)['confirmed']
                except ApiError:return False
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(confirm,[first['id'],second['id']])),[False,True])
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'DiscoveryAllocation',user_id='owner')),1)

    def test_verified_visibility_and_unverified_cannot_like(self):
        row=db.fetch_one(self.conn,'User',id='partner');row['bgv_status']='declared';db.insert_row(self.conn,'User',row)
        self.expose()
        self.assertNotIn('partner',[p['id'] for p in discovery.snapshot(self.conn,'owner',1)['profiles']])
        self.assertIn('owner',[p['id'] for p in discovery.snapshot(self.conn,'partner',1)['profiles']])
        with self.assertRaises(ApiError):discovery.act(self.conn,'partner','owner','interest',1)

    def test_expired_proposal_and_changed_filter_cannot_confirm(self):
        proposal=self.mutual()
        from clock import SimulationClock
        with patch('discovery.time.time',return_value=proposal['expires_at']+1):
            with self.assertRaises(ApiError):discovery.confirm(self.conn,'owner',proposal['id'],SimulationClock.at(1,'Mon',12))
        row=db.fetch_one(self.conn,'User',id='owner');row['preferences_json']=json.dumps({'adjustable':{'age':[50,70]}});db.insert_row(self.conn,'User',row)
        with self.assertRaises(ApiError):discovery.confirm(self.conn,'owner',proposal['id'],SimulationClock.at(1,'Mon',12))

    def test_catalogue_review_conflict_preserves_answers_and_counts_once(self):
        row=db.fetch_one(self.conn,'User',id='owner')
        row['skills_json']=json.dumps({'activities':{'Running':'good','Sprinting':'no'},'custom_activities':['Sprinting'],'partner_any':['Sprinting']})
        db.insert_row(self.conn,'User',row)
        activity_catalog.queue(self.conn,['Sprinting'])
        activity_catalog.review(self.conn,'Sprinting','Running','operator')
        skills=db.load_json_field(db.fetch_one(self.conn,'User',id='owner')['skills_json'],{})
        self.assertEqual(skills['activities'],{'Running':'good'})
        self.assertEqual(skills['activity_alias_archive'],{'Sprinting':'no'})
        self.assertEqual(skills['partner_any'],[])
        self.assertEqual(activity_catalog.ordered(self.conn)[0],'Running')
        self.assertEqual(len(onboarding.ACTIVITIES),28)

    def test_all_vision_presets_allow_empty_cohabitate_but_require_emotional(self):
        for preset in vision_plans.PRESETS:
            if preset['choices']:vision_plans.validate(preset['choices'])
        with self.assertRaises(ApiError):vision_plans.validate({'Intimacy':['Physical'],'Cohabitate':[]})
        vision_plans.validate({'Intimacy':['Emotional','Physical'],'Cohabitate':[]})


# Only inherit setup helpers, not legacy-mode test methods.
for name in dir(WeekApiTests):
    if name.startswith('test_') and name not in DiscoveryTests.__dict__:
        setattr(DiscoveryTests,name,None)
