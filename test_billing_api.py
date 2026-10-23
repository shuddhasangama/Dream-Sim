"""Browser authentication, CSRF, ownership and mobile billing boundaries."""
import os
from unittest import mock
import auth_sessions
import billing_service
import db
from test_billing_service import FakeGateway
from test_segment_efg_routes import RouteTestCase, app_module


class BillingApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        p=mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':True,'AUTH_PUBLIC_ORIGIN':'http://localhost'});p.start();self.addCleanup(p.stop)
        p=mock.patch.dict(os.environ,{'DHASHU_BILLING_MODE':'sandbox','DHASHU_BILLING_TESTERS':'owner,partner'});p.start();self.addCleanup(p.stop)
        p=mock.patch.object(billing_service,'Razorpay',FakeGateway);p.start();self.addCleanup(p.stop)
        self.tokens={}
        for uid in ('owner','partner'):
            self.make_user(uid)
            db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'auth_enabled':1,'created_at':'test'})
            self.tokens[uid]=auth_sessions.issue(self.conn,uid,kind='web')['access_token']
        self.login_browser('owner')

    def login_browser(self,uid):
        with self.client.session_transaction() as session:
            session.clear();session['auth_token']=self.tokens[uid]
        response=self.client.get('/api/v1/billing/config')
        self.assertEqual(response.status_code,200)
        self.csrf=response.json['data']['csrf']

    def post(self,path,body):
        return self.client.post('/api/v1/billing/'+path,json=body,headers={'X-Billing-CSRF':self.csrf,'Origin':app_module.app.config['AUTH_PUBLIC_ORIGIN']})

    def test_browser_flow_and_owner_isolation(self):
        q=self.post('quotes',{'product':'verification'})
        self.assertEqual(q.status_code,200)
        pid=q.json['data']['id']
        checkout=self.post('purchases/'+pid+'/checkout',{})
        self.assertEqual(checkout.status_code,200)
        self.assertIn('order_id',checkout.json['data']['checkout'])
        self.login_browser('partner')
        self.assertEqual(self.client.get('/api/v1/billing/purchases/'+pid).status_code,404)

    def test_csrf_and_native_sessions_cannot_choose_external_checkout(self):
        self.assertEqual(self.client.post('/api/v1/billing/quotes',json={'product':'verification'}).status_code,403)
        token=auth_sessions.issue(self.conn,'owner',kind='mobile')['access_token']
        response=self.client.get('/api/v1/billing/config',headers={'Authorization':'Bearer '+token})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json['error']['code'],'store_billing_required')

    def test_client_cannot_override_price_and_mock_confirmation_blocked(self):
        response=self.post('quotes',{'product':'verification','amount':1})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post('/pay/availability/confirm',headers={'Origin':app_module.app.config['AUTH_PUBLIC_ORIGIN']}).status_code,403)

    def test_bundle_unlocks_both_date_gates(self):
        import planning_service
        self.make_lockin('owner','partner')
        row=self.post('quotes',{'product':'date_mechanics','reference':'lock-1'}).json['data']
        self.post('purchases/'+row['id']+'/checkout',{})
        with billing_service.transaction(self.conn):
            billing_service.apply_payment(self.conn,billing_service.get(self.conn,row['id']),
                {'id':'pay_example','status':'captured','amount':100,'currency':'INR'})
        self.assertTrue(planning_service.paid(self.conn,'owner','availability','lock-1'))
        self.make_plan('lock-1',plan_id='plan-test',status='pending_signatures')
        self.assertTrue(planning_service.paid(self.conn,'owner','agreement','plan-test'))
        self.assertFalse(planning_service.paid(self.conn,'partner','availability','lock-1'))

    def test_page_renders_and_webhook_requires_signature(self):
        self.assertEqual(self.client.get('/billing').status_code,200)
        self.assertEqual(self.client.post('/billing/webhooks/razorpay',json={}).status_code,401)
