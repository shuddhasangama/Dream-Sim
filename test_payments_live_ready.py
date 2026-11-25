"""dec-pay: real charges (live mode), server-owned amounts, startup refusal of unsafe
production settings, signed + fresh webhooks only. Razorpay is faked: no network."""
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest import mock

import billing_catalog
import test_billing_api
from api_contract import ApiError

LIVE_ENV = {'RAILWAY_ENVIRONMENT_NAME': 'production', 'DHASHU_BILLING_MODE': 'live', 'RAZORPAY_KEY_ID': 'rzp_live_abc123',
            'RAZORPAY_KEY_SECRET': 'secret-value', 'RAZORPAY_WEBHOOK_SECRET': 'w' * 32}


class CatalogTests(unittest.TestCase):
    def test_live_charges_the_catalogue_price_to_every_member(self):
        with mock.patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'live', 'DHASHU_BILLING_TESTERS': ''}):
            price = billing_catalog.price('anyone', 'verification')
            self.assertEqual((price['amount'], price['catalog_amount'], price['tax_treatment']), (199900, 199900, 'inclusive-total'))
            self.assertTrue(billing_catalog.real_billing('anyone'))
        with mock.patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'sandbox', 'DHASHU_BILLING_TESTERS': 'tester'}):
            self.assertEqual(billing_catalog.price('tester', 'verification')['amount'], 100)     # sandbox unchanged
            with self.assertRaises(ApiError):
                billing_catalog.price('anyone', 'verification')                                  # testers only
            self.assertFalse(billing_catalog.real_billing('anyone'))
        with mock.patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'disabled'}):
            self.assertFalse(billing_catalog.real_billing('anyone'))
            with self.assertRaises(ApiError):
                billing_catalog.price('anyone', 'verification')

    def test_live_gateway_requires_live_keys(self):
        import billing_razorpay
        with mock.patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'live', 'RAZORPAY_KEY_ID': 'rzp_test_x', 'RAZORPAY_KEY_SECRET': 's'}):
            with self.assertRaises(ApiError):
                billing_razorpay.Razorpay()
        with mock.patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'live', 'RAZORPAY_KEY_ID': 'rzp_live_x', 'RAZORPAY_KEY_SECRET': 's'}):
            billing_razorpay.Razorpay()


class StartupCheckTests(unittest.TestCase):
    def test_production_needs_live_keys_and_refuses_test_keys(self):
        self.assertIsNone(billing_catalog.startup_check(LIVE_ENV))
        self.assertIsNone(billing_catalog.startup_check({**LIVE_ENV, 'DHASHU_BILLING_MODE': 'disabled'}))
        self.assertIsNone(billing_catalog.startup_check({**LIVE_ENV, 'RAILWAY_ENVIRONMENT_NAME': 'staging', 'RAZORPAY_KEY_ID': 'rzp_test_x'}))
        for broken, word in (({'RAZORPAY_KEY_ID': 'rzp_test_x'}, 'TEST'), ({'RAZORPAY_KEY_ID': ''}, 'RAZORPAY_KEY_ID'),
                             ({'RAZORPAY_KEY_SECRET': ''}, 'RAZORPAY_KEY_SECRET'), ({'RAZORPAY_WEBHOOK_SECRET': 'short'}, 'RAZORPAY_WEBHOOK_SECRET'),
                             ({'DHASHU_BILLING_MODE': 'sandbox'}, 'sandbox')):
            with self.assertRaises(RuntimeError) as ctx:
                billing_catalog.startup_check({**LIVE_ENV, **broken})
            self.assertIn(word, str(ctx.exception))
            self.assertNotIn('secret-value', str(ctx.exception))                                 # names only, never values


class LiveRouteTests(unittest.TestCase):
    """The billing API fixture (composition, so its own tests are not re-run), in live
    mode with no testers list."""
    def setUp(self):
        self.f = test_billing_api.BillingApiTests('test_browser_flow_and_owner_isolation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        p = mock.patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'live', 'DHASHU_BILLING_TESTERS': '', 'RAZORPAY_WEBHOOK_SECRET': 'w' * 32})
        p.start(); self.addCleanup(p.stop)
        self.client, self.post = self.f.client, self.f.post

    def signed(self, event):
        raw = json.dumps(event).encode()
        return raw, hmac.new(b'w' * 32, raw, hashlib.sha256).hexdigest()

    def webhook(self, raw, signature=None):
        headers = {'Content-Type': 'application/json', **({'X-Razorpay-Signature': signature} if signature else {})}
        return self.client.post('/billing/webhooks/razorpay', data=raw, headers=headers)

    def test_every_member_buys_at_the_server_price_and_cannot_set_it(self):
        quote = self.post('quotes', {'product': 'verification'})
        self.assertEqual(quote.status_code, 200, quote.json)
        self.assertEqual(quote.json['data']['amount'], 199900)
        self.assertEqual(self.post('quotes', {'product': 'verification', 'amount': 100}).status_code, 400)
        checkout = self.post('purchases/' + quote.json['data']['id'] + '/checkout', {})
        self.assertEqual(checkout.status_code, 200)
        self.assertEqual(checkout.json['data']['checkout']['amount'], 199900)

    def test_the_simulated_gateway_is_refused_while_real_billing_is_on(self):
        self.assertEqual(self.client.post('/pay/availability/confirm', headers={'Origin': 'http://localhost'}).status_code, 403)

    def test_webhooks_must_be_signed_and_fresh(self):
        fresh = {'event': 'payment.authorized', 'payload': {}, 'created_at': int(time.time())}
        raw, signature = self.signed(fresh)
        self.assertEqual(self.webhook(raw).status_code, 401)                                     # unsigned
        self.assertEqual(self.webhook(raw, 'f' * 64).status_code, 401)                           # wrong signature
        self.assertEqual(self.webhook(raw, signature).status_code, 200)
        self.assertEqual(self.webhook(raw, signature).status_code, 200)                          # exact duplicate: no-op
        old, old_signature = self.signed({**fresh, 'created_at': int(time.time()) - 3 * 86400})
        r = self.webhook(old, old_signature)
        self.assertEqual((r.status_code, r.json['code']), (400, 'stale_event'))                 # replay of an old event
        missing, missing_signature = self.signed({'event': 'payment.authorized', 'payload': {}})
        self.assertEqual(self.webhook(missing, missing_signature).status_code, 400)


if __name__ == '__main__':
    unittest.main()
