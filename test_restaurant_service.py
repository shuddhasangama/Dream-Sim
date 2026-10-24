import json
import os
import unittest
from unittest import mock

import db
import restaurant_service as service
from restaurant_provider import distance_km
from test_booking_coordination import BookingTests


class RestaurantTests(unittest.TestCase):
    def setUp(self):
        self.fixture = BookingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        flag = mock.patch.dict(os.environ, {'DHASHU_RESTAURANT_MODE':'simulation','DHASHU_RESTAURANT_SCENARIO':'success'})
        flag.start()
        self.addCleanup(flag.stop)
        self.fixture.prepare()
        self.pid = self.fixture.confirm().json['data']['id']
        self.conn = self.fixture.conn
        self.conn.execute("UPDATE DatePlan SET status='confirmed'")
        self.conn.commit()
        self.path = '/date-plans/'+self.pid+'/restaurant'

    def view(self, uid='owner'):
        return self.fixture.request(self.path,uid=uid).json['data']

    def action(self, action, uid='owner', **extra):
        return self.fixture.request(self.path+'/actions',uid=uid,method='POST',body={
            'action':action,'revision':self.view(uid)['revision'], **extra})

    def ready(self):
        r=self.action('search')
        self.assertEqual(r.status_code,200,r.json)
        q=r.json['data']['options'][0]['quote_id']
        self.assertEqual(self.action('approve',quote_id=q).status_code,200)
        self.assertEqual(self.action('approve','partner',quote_id=q).json['data']['state'],'ready_to_pay')

    def test_success_cancel_and_no_real_payment(self):
        self.ready()
        result=self.action('pay').json['data']
        self.assertEqual(result['state'],'confirmed')
        self.assertTrue(result['reference'].startswith('SIM-'))
        self.assertEqual(db.fetch_all(self.conn,'BillingPurchase'),[])
        self.assertEqual(db.fetch_all(self.conn,'BillingEntitlement'),[])
        self.assertEqual(self.action('pay').status_code,409)
        self.assertEqual(self.action('cancel','partner').json['data']['refund'],'processed')
        self.assertTrue(db.fetch_all(self.conn,'RestaurantEvent'))

    def test_conflicting_approvals_cannot_pay(self):
        options=self.action('search').json['data']['options']
        self.assertEqual(len(options),3)
        self.assertTrue(all(o['distance_km']<=3 for o in options))
        self.action('approve',quote_id=options[0]['quote_id'])
        self.action('approve','partner',quote_id=options[1]['quote_id'])
        self.assertEqual(self.view()['state'],'shortlist')
        self.assertEqual(self.action('pay').status_code,409)
        self.assertEqual(self.action('approve',quote_id='wrong').status_code,400)

    def test_expired_and_changed_quotes_clear_approvals(self):
        self.ready()
        with mock.patch('restaurant_service.now',return_value=self.view()['expires_at']+1):
            self.assertEqual(self.action('pay').json['data']['state'],'expired')
        self.ready()
        with mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_SCENARIO':'price_changed'}):
            self.assertEqual(self.action('pay').json['data']['state'],'changed')
        self.assertIsNone(self.view()['my_approval'])

    def test_timeout_reconciles_before_retry_or_cancel(self):
        self.ready()
        with mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_SCENARIO':'timeout'}):
            self.assertEqual(self.action('pay').json['data']['state'],'unknown')
        for action in ('pay','cancel','search'):
            self.assertEqual(self.action(action).status_code,409)
        self.assertEqual(self.action('reconcile').json['data']['state'],'confirmed')

    def test_failure_scenarios_and_refund_recovery(self):
        with mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_SCENARIO':'empty'}):
            self.assertEqual(self.action('search').json['data']['state'],'empty')
        self.ready()
        with mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_SCENARIO':'unavailable'}):
            self.assertEqual(self.action('pay').json['data']['state'],'unavailable')
        self.ready()
        with mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_SCENARIO':'payment_failed'}):
            self.assertEqual(self.action('pay').json['data']['state'],'payment_failed')
        self.assertEqual(self.action('pay').json['data']['state'],'confirmed')
        with mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_SCENARIO':'refund_failed'}):
            self.assertEqual(self.action('cancel').json['data']['refund'],'failed')
        self.assertEqual(self.action('search').status_code,409)
        self.assertEqual(self.action('retry_refund').json['data']['refund'],'processed')

    def test_foreign_user_and_stale_revision(self):
        self.assertEqual(self.fixture.request(self.path,uid='stranger').status_code,404)
        self.assertEqual(self.fixture.request(self.path+'/actions',uid='stranger',method='POST',body={'action':'search','revision':0}).status_code,404)
        self.action('search')
        self.assertEqual(self.action('search',revision=0).status_code,409)
        before=list(self.conn.iterdump())
        self.view()
        self.assertEqual(before,list(self.conn.iterdump()))

    def test_closed_date_blocks_new_payment_but_allows_cancellation(self):
        self.ready()
        self.action('pay')
        self.conn.execute("UPDATE DatePlan SET status='cancelled'")
        self.conn.commit()
        self.assertEqual(self.action('search').status_code,409)
        self.assertEqual(self.action('cancel').json['data']['state'],'cancelled')

    def test_two_area_limit(self):
        # New pair cycle, with no frozen plan.
        self.conn.execute('DELETE FROM DatePlan')
        self.conn.commit()
        self.assertEqual(self.fixture.choose(places=['indiranagar','jayanagar','koramangala']).status_code,400)

    def test_browser_csrf_and_render(self):
        from test_segment_efg_routes import app_module
        with mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':False}):
            self.fixture.login('owner')
            url='/restaurant/'+self.pid
            self.assertEqual(self.fixture.client.get(url).status_code,200)
            self.assertEqual(self.fixture.client.post(url,data={'action':'search','revision':'0'}).status_code,403)
            with self.fixture.client.session_transaction() as sess:
                token=sess['restaurant_csrf']
            self.assertEqual(self.fixture.client.post(url,data={'action':'search','revision':'0','csrf':token}).status_code,302)
            self.assertIn(b'Demo restaurant',self.fixture.client.get(url).data)

    def test_distance_and_filters(self):
        self.assertAlmostEqual(distance_km({'lat':0,'lon':0},{'lat':0,'lon':0}),0)
        with mock.patch('restaurant_provider.SimulatedProvider.search',return_value=[{
            'id':'far','lat':0,'lon':0,'available':True,'currency':'INR',
            'cuisines':['Thai'],'diets':['Vegetarian'],'estimate_per_person_minor':1}]):
            self.assertEqual(self.action('search').json['data']['state'],'empty')

    def test_open_budget_requires_cap_and_malformed_actions_are_rejected(self):
        saved=db.fetch_one(self.conn,'BookingSnapshot',dateplan_id=self.pid)
        data=json.loads(saved['payload_json'])
        data['budget_per_person_minor']={'min':450000,'max':None}
        self.conn.execute('UPDATE BookingSnapshot SET payload_json=? WHERE id=?',(json.dumps(data),self.pid))
        self.conn.commit()
        self.assertEqual(self.action('search').json['data']['state'],'budget_limit_required')
        self.assertEqual(self.action('search',max_per_person_minor=400000).status_code,400)
        self.assertEqual(self.action('search',max_per_person_minor=800000).json['data']['state'],'shortlist')
        self.assertEqual(self.action([]).status_code,400)

    def test_playbook_required_and_resolved_date_cannot_book(self):
        self.ready()
        self.conn.execute("UPDATE DatePlan SET status='pending_signatures'")
        self.conn.commit()
        self.assertEqual(self.action('pay').status_code,409)

    def test_multiple_platforms_compare_cost_and_keep_selected_provider(self):
        import restaurant_registry as registry
        from restaurant_provider import SimulatedProvider
        class HigherFee(SimulatedProvider):
            def search(self,*args):
                return [{**q,'booking_fee_minor':10000} for q in super().search(*args)]
        settings={'selection_policy':'lowest_total','providers':[
            {'id':'higher','label':'Higher fee demo','adapter':'higher','enabled':True,'markets':['IN-BLR'],'priority':1},
            {'id':'lower','label':'Lower fee demo','adapter':'simulation','enabled':True,'markets':['IN-BLR'],'priority':2}]}
        spec={**registry.ADAPTERS['simulation'],'factory':HigherFee}
        with mock.patch.dict(registry.ADAPTERS,{'higher':spec}), mock.patch.object(registry,'config',return_value=settings):
            q=self.action('search').json['data']['options'][0]
            self.assertEqual(q['provider_id'],'lower')
            self.action('approve',quote_id=q['quote_id'])
            self.action('approve','partner',quote_id=q['quote_id'])
            self.assertEqual(self.action('pay').json['data']['state'],'confirmed')
            row=json.loads(db.fetch_one(self.conn,'RestaurantBooking',id=self.pid)['payload_json'])
            self.assertEqual(row['provider'],'lower')
            self.assertEqual(self.action('cancel').json['data']['refund'],'processed')
