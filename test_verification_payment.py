"""Sandbox payment binding, replay protection and identity gating without real IO."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import db
import verification_payment as service
from api_contract import ApiError

class Gateway:
    key='rzp_test_synthetic'
    link=None
    paid=False
    creates=0
    def call(self,method,path,body=None):
        if method=='POST':
            type(self).creates+=1
            type(self).link={'id':'plink_test','short_url':'https://rzp.io/i/test','amount':100,'currency':'INR','reference_id':body['reference_id'],'order_id':'order_test','status':'created','amount_paid':0}
            return self.link
        if path.startswith('payment_links/'):
            return {**self.link,**({'status':'paid','amount_paid':100,'payments':[{'status':'captured','amount':100,'payment_id':'pay_test'}]} if self.paid else {})}
        return {'id':'pay_test','status':'captured','amount':100,'currency':'INR','order_id':'order_test'}

class VerificationPaymentTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        env=patch.dict(os.environ,{'DATABASE_URL':'','DHASHU_BILLING_MODE':'sandbox','DHASHU_BILLING_TESTERS':''});env.start();self.addCleanup(env.stop)
        self.conn=db.get_connection(Path(temp.name)/'payments.db');db.init_db(self.conn);self.addCleanup(self.conn.close)
        for uid in ('a','b'):db.insert_row(self.conn,'User',{'id':uid,'journey_state':'onboarding','bgv_status':'declared'})
        gateway=patch.object(service,'Razorpay',Gateway);gateway.start();self.addCleanup(gateway.stop)
        Gateway.link=None;Gateway.paid=False;Gateway.creates=0
    def test_account_bound_capture_required_and_existing_link_reused(self):
        with self.assertRaises(ApiError):service.require_paid(self.conn,'a')
        first=service.start(self.conn,'a');again=service.start(self.conn,'a')
        self.assertEqual(first['purchase_id'],again['purchase_id']);self.assertEqual(Gateway.creates,1)
        self.assertFalse(service.complete(self.conn,'a')['can_begin'])
        Gateway.paid=True
        self.assertTrue(service.complete(self.conn,'a')['can_begin'])
        self.assertTrue(service.start(self.conn,'a')['can_begin']);self.assertEqual(Gateway.creates,1)
        self.assertFalse(service.view(self.conn,'b')['can_begin'])
        self.assertEqual(db.fetch_one(self.conn,'User',id='a')['bgv_status'],'declared')
    def test_foreign_or_wrong_price_provider_evidence_never_unlocks(self):
        service.start(self.conn,'a');Gateway.paid=True;Gateway.link['reference_id']='other'
        with self.assertRaises(ApiError):service.complete(self.conn,'a')
        self.assertFalse(service.view(self.conn,'a')['can_begin'])
    def test_uncertain_create_never_replayed_and_live_mode_blocked(self):
        with patch.object(Gateway,'call',side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):service.start(self.conn,'a')
        self.assertEqual(service.start(self.conn,'a')['state'],'outcome_unknown')
        self.assertEqual(Gateway.creates,0)
        with patch.dict(os.environ,{'DHASHU_BILLING_MODE':'live_pilot'}):
            with self.assertRaises(ApiError):service.start(self.conn,'a')
            self.assertFalse(service.view(self.conn,'a')['can_begin'])

