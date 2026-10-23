"""Payment safety regressions: isolated SQLite and fake provider, no real charges."""
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import db
import billing_catalog as catalog
import billing_service as service
from api_contract import ApiError


class FakeGateway:
    key='rzp_test_fake'
    calls=0
    def create_order(self,row):
        type(self).calls+=1
        return {'id':'order_'+row['id']}
    def create_subscription(self,row):
        type(self).calls+=1
        return {'id':'sub_'+row['id']}
    def call(self,*args):
        return {}


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=patch.dict(os.environ,{'DATABASE_URL':'','DHASHU_BILLING_MODE':'sandbox',
            'DHASHU_BILLING_TESTERS':'a,b','RAZORPAY_WEBHOOK_SECRET':'test-secret'},clear=False)
        p.start();self.addCleanup(p.stop)
        self.conn=db.get_connection(Path(self.temp.name)/'billing.db')
        self.addCleanup(self.conn.close);db.init_db(self.conn)
        for uid in ('a','b','outsider'):
            db.insert_row(self.conn,'User',{'id':uid,'journey_state':'dating','bgv_status':'verified'})
        p=patch.object(service,'Razorpay',FakeGateway);p.start();self.addCleanup(p.stop)
        FakeGateway.calls=0

    def purchase(self,product='verification'):
        q=service.quote(self.conn,'a',product,None,'web')
        service.checkout(self.conn,'a',q['id'],accept_recurring=True)
        return service.get(self.conn,q['id'])

    def event(self,row,kind='payment.captured',**extra):
        payment={'id':'pay_'+row['id'],'order_id':row['provider_id'],'status':'captured',
                 'amount':100,'currency':'INR',**extra}
        event={'event':kind,'payload':{'payment':{'entity':payment}}}
        if row['product']=='guru':
            event['payload']['subscription']={'entity':{'id':row['provider_id'],'current_end':int(time.time())+3600}}
        return event

    def send(self,event):
        raw=json.dumps(event).encode()
        signature=hmac.new(b'test-secret',raw,hashlib.sha256).hexdigest()
        service.webhook(self.conn,raw,signature)

    def test_catalog_and_routing(self):
        self.assertEqual(catalog.PRODUCTS['engagement_marriage']['amount'],199900)
        self.assertEqual(catalog.price('a','guru')['amount'],100)
        self.assertEqual(catalog.price('a','guru')['catalog_amount'],19900)
        for channel in ('ios','android'):
            with self.assertRaises(ApiError):catalog.route(channel)
        with self.assertRaises(ApiError):catalog.price('outsider','guru')

    def test_duplicate_checkout_and_competing_quotes(self):
        row=self.purchase()
        service.checkout(self.conn,'a',row['id'])
        self.assertEqual(FakeGateway.calls,1)
        quote=service.quote(self.conn,'a','verification',None,'web')
        with self.assertRaises(ApiError):service.checkout(self.conn,'a',quote['id'])
        self.assertEqual(FakeGateway.calls,1)

    def test_signed_capture_grants_once_and_wrong_amount_does_not(self):
        row=self.purchase()
        with self.assertRaises(ApiError):self.send(self.event(row,amount=199900))
        self.assertFalse(service.entitled(self.conn,'a','verification','a'))
        self.send(self.event(row));self.send(self.event(row))
        self.assertEqual(len(db.fetch_all(self.conn,'BillingEntitlement')),1)
        self.assertTrue(service.entitled(self.conn,'a','verification','a'))

    def test_unauthorized_signature_and_ownership(self):
        row=self.purchase()
        with self.assertRaises(ApiError):service.webhook(self.conn,b'{}','wrong')
        with self.assertRaises(ApiError):service.get(self.conn,row['id'],'b')
        with self.assertRaises(ApiError):service.quote(self.conn,'a','verification','b','web')
        with self.assertRaises(ApiError):service.quote(self.conn,'a','date_mechanics','missing','web')

    def test_uncertain_create_is_never_retried(self):
        q=service.quote(self.conn,'a','verification',None,'web')
        with patch.object(FakeGateway,'create_order',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):service.checkout(self.conn,'a',q['id'])
        self.assertEqual(service.checkout(self.conn,'a',q['id'])['status'],'reconciling')
        self.assertEqual(FakeGateway.calls,0)

    def test_refund_revokes_and_late_capture_cannot_restore(self):
        row=self.purchase();self.send(self.event(row))
        event={'event':'refund.processed','payload':{'refund':{'entity':{
            'id':'rfnd_1','payment_id':'pay_'+row['id'],'amount':100,'status':'processed'}}}}
        self.send(event);self.send(self.event(row))
        self.assertFalse(service.entitled(self.conn,'a','verification','a'))
        self.assertEqual(service.get(self.conn,row['id'])['status'],'refunded')

    def test_subscription_only_charged_event_grants_and_expiry_enforced(self):
        row=self.purchase('guru')
        self.send(self.event(row,'subscription.activated'))
        self.assertFalse(service.entitled(self.conn,'a','guru','a'))
        self.send(self.event(row,'subscription.charged'))
        self.assertTrue(service.entitled(self.conn,'a','guru','a'))
        self.send(self.event(row,'subscription.cancelled'))
        self.assertTrue(service.entitled(self.conn,'a','guru','a'))
        with patch.object(service.time,'time',return_value=time.time()+7200):
            self.assertFalse(service.entitled(self.conn,'a','guru','a'))

    def test_environment_separation(self):
        row=self.purchase();self.send(self.event(row))
        with patch.dict(os.environ,{'DHASHU_BILLING_MODE':'live_pilot'}):
            self.assertFalse(service.entitled(self.conn,'a','verification','a'))
            with self.assertRaises(ApiError):service.reconcile(self.conn,'a',row['id'])

    def test_expired_quote(self):
        q=service.quote(self.conn,'a','verification',None,'web')
        with patch.object(service.time,'time',return_value=time.time()+1800):
            with self.assertRaises(ApiError):service.checkout(self.conn,'a',q['id'])

    def test_reconciled_refund_does_not_leave_access_active(self):
        row=self.purchase();self.send(self.event(row))
        with service.transaction(self.conn):
            service.apply_payment(self.conn,service.get(self.conn,row['id']),{
                'id':'pay_'+row['id'],'status':'captured','amount':100,'currency':'INR','amount_refunded':100})
        self.assertFalse(service.entitled(self.conn,'a','verification','a'))

    def test_gateway_rejects_live_credentials_in_sandbox(self):
        from billing_razorpay import Razorpay
        with patch.dict(os.environ,{'RAZORPAY_KEY_ID':'rzp_live_example','RAZORPAY_KEY_SECRET':'secret'}):
            with self.assertRaises(ApiError):Razorpay()

    def test_subscription_reconciliation_uses_paid_invoice(self):
        row=self.purchase('guru')
        end=int(time.time())+3600
        responses=[{'status':'active'}, {'items':[{'id':'inv_example','subscription_id':row['provider_id'],
            'status':'paid','payment_id':'pay_example','billing_end':end}]},
            {'id':'pay_example','invoice_id':'inv_example','status':'captured','amount':100,'currency':'INR'}]
        with patch.object(FakeGateway,'call',side_effect=responses):
            result=service.reconcile(self.conn,'a',row['id'])
        self.assertEqual(result['paid_until'],end)
        self.assertTrue(service.entitled(self.conn,'a','guru','a'))


if __name__=='__main__':unittest.main()
