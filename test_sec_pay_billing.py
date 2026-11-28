"""sec-pay (review fixes): billing serialises on the member's own row (no LOCK TABLE),
every provider event has a unique idempotency key, webhook failures raise the
payment_webhook_failure alert while duplicates stay a silent success, and payment
status checks can run on provider_jobs. SQLite + fake gateway; no network."""
import hashlib
import hmac
import inspect
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from flask import Flask

import billing_api
import billing_service as service
import db
import provider_jobs
import test_auth_postgres as pg
from api_contract import ApiError
from test_billing_service import BillingTests, FakeGateway


def signed(event):
    raw = json.dumps(event).encode()
    return raw, hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()


class MemberLockTests(BillingTests):
    def test_no_table_lock_only_the_members_own_row(self):
        self.assertNotRegex(inspect.getsource(service), r"""['"]LOCK TABLE""")   # no table-lock SQL
        locked = []
        with patch('db.lock_user_rows', side_effect=lambda conn, *ids: locked.append(ids)):
            row = self.purchase()
            raw, signature = signed(self.event(row))
            service.webhook(self.conn, raw, signature)
        self.assertTrue(locked)
        self.assertTrue(all(ids == ('a',) for ids in locked), locked)   # never another member, never empty

    def test_verification_payment_locks_the_member(self):
        import verification_payment
        self.assertNotIn('billing.transaction(conn)', inspect.getsource(verification_payment))


class EventIdempotencyTests(BillingTests):
    def entitlements(self):
        return db.fetch_all(self.conn, 'BillingEntitlement')

    def test_provider_event_id_is_the_unique_key_even_if_the_body_changes(self):
        row = self.purchase()
        event = self.event(row)
        first, first_sig = signed(event)
        self.assertIsNone(service.webhook(self.conn, first, first_sig, 'evt_RetryMe1'))
        # Razorpay retry of the same event, re-serialised with different bytes.
        second = json.dumps(event, indent=2).encode()
        second_sig = hmac.new(b'test-secret', second, hashlib.sha256).hexdigest()
        self.assertEqual(service.webhook(self.conn, second, second_sig, 'evt_RetryMe1'), 'duplicate')
        events = db.fetch_all(self.conn, 'BillingEvent')
        self.assertEqual([e['id'] for e in events], ['razorpay:evt_RetryMe1'])
        self.assertEqual(len(self.entitlements()), 1)

    def test_events_stored_before_the_change_are_still_duplicates(self):
        row = self.purchase()
        raw, signature = signed(self.event(row))
        service.webhook(self.conn, raw, signature)                      # no header: digest key (old format)
        self.assertEqual(service.webhook(self.conn, raw, signature, 'evt_After1'), 'duplicate')
        self.assertEqual(len(db.fetch_all(self.conn, 'BillingEvent')), 1)

    def test_malformed_event_ids_fall_back_to_the_signed_digest(self):
        row = self.purchase()
        raw, signature = signed(self.event(row))
        for bad in ('', 'evt bad', 'x' * 65, 'evt;drop', None):
            self.assertEqual(service.event_keys(raw, bad)[0], hashlib.sha256(raw).hexdigest())
        service.webhook(self.conn, raw, signature, '../../etc')
        self.assertEqual(db.fetch_all(self.conn, 'BillingEvent')[0]['id'], hashlib.sha256(raw).hexdigest())

    def test_distinct_events_for_one_purchase_both_apply(self):
        row = self.purchase()
        raw, signature = signed(self.event(row))
        service.webhook(self.conn, raw, signature, 'evt_One')
        refund = {'event': 'refund.processed', 'payload': {'refund': {'entity': {
            'id': 'rfnd_1', 'payment_id': 'pay_' + row['id'], 'amount': 100, 'status': 'processed'}}}}
        raw, signature = signed(refund)
        self.assertIsNone(service.webhook(self.conn, raw, signature, 'evt_Two'))
        self.assertEqual(service.get(self.conn, row['id'])['status'], 'refunded')


class WebhookAlertTests(BillingTests):
    def setUp(self):
        super().setUp()
        app = Flask('sec-pay-webhook-test')
        billing_api.register_web(app, lambda: self.conn, lambda: None)
        self.client = app.test_client()

    def post(self, raw, signature, event_id=None):
        headers = {'X-Razorpay-Signature': signature}
        if event_id:
            headers['X-Razorpay-Event-Id'] = event_id
        return self.client.post('/billing/webhooks/razorpay', data=raw, headers=headers)

    def fresh(self, event):
        return {**event, 'created_at': int(time.time())}

    def test_failures_alert_with_codes_only(self):
        with patch('alerts.emit') as emit:
            self.assertEqual(self.post(b'{"created_at":1}', 'f' * 64).status_code, 401)
            emit.assert_called_once_with('payment_webhook_failure', reason='invalid_signature', status=401)
            emit.reset_mock()
            unknown = self.fresh({'event': 'payment.captured', 'payload': {'payment': {'entity': {
                'id': 'pay_x', 'order_id': 'order_unknown', 'amount': 100, 'currency': 'INR', 'status': 'captured'}}}})
            raw, signature = signed(unknown)
            self.assertEqual(self.post(raw, signature).status_code, 503)
            emit.assert_called_once_with('payment_webhook_failure', reason='purchase_not_ready', status=503)
            emit.reset_mock()
            raw, signature = signed({'event': 'payment.captured', 'payload': {}, 'created_at': 1})
            self.assertEqual(self.post(raw, signature).status_code, 400)
            emit.assert_called_once_with('payment_webhook_failure', reason='stale_event', status=400)
        for call in emit.call_args_list:
            self.assertNotIn('pay_', json.dumps(call.kwargs))

    def test_duplicate_delivery_is_a_silent_success(self):
        row = self.purchase()
        raw, signature = signed(self.fresh(self.event(row)))
        with patch('alerts.emit') as emit:
            self.assertEqual(self.post(raw, signature, 'evt_Dup1').status_code, 200)
            self.assertEqual(self.post(raw, signature, 'evt_Dup1').status_code, 200)
            self.assertEqual(self.post(raw, signature).status_code, 200)
        emit.assert_not_called()
        self.assertEqual(len(db.fetch_all(self.conn, 'BillingEntitlement')), 1)

    def test_unexpected_error_alerts_and_is_not_swallowed(self):
        row = self.purchase()
        raw, signature = signed(self.fresh(self.event(row)))
        with patch('alerts.emit') as emit, patch.object(service, 'apply_payment', side_effect=RuntimeError('boom')):
            self.assertEqual(self.post(raw, signature).status_code, 500)
        emit.assert_called_once_with('payment_webhook_failure', reason='internal_error', status=500, error='RuntimeError')
        self.assertEqual(db.fetch_all(self.conn, 'BillingEvent'), [])     # not recorded: the retry will apply it


class ReconcileJobTests(BillingTests):
    def gateway_with_capture(self, row):
        captured = {'items': [{'id': 'pay_' + row['id'], 'order_id': row['provider_id'], 'status': 'captured',
                               'amount': 100, 'currency': 'INR'}]}
        FakeGateway.call = lambda self, *args: captured
        self.addCleanup(lambda: setattr(FakeGateway, 'call', lambda self, *args: {}))

    def test_async_check_records_a_job_and_the_worker_asks_the_provider(self):
        row = self.purchase()
        self.gateway_with_capture(row)
        with patch.dict(os.environ, {'DHASHU_ASYNC_BILLING': '1'}), \
                patch.object(service, 'reconcile', wraps=service.reconcile) as inline:
            first = service.request_reconcile(self.conn, 'a', row['id'])
            again = service.request_reconcile(self.conn, 'a', row['id'])
            inline.assert_not_called()                                   # no provider call in the request
            self.assertEqual(first['payment_status'], 'unpaid')
            self.assertEqual(first['job'], again['job'])                 # one job per purchase per window
            jobs = db.fetch_all(self.conn, 'ProviderJob', kind=service.RECONCILE_JOB)
            self.assertEqual([(j['user_id'], j['ref']) for j in jobs], [('a', row['id'])])
            self.assertTrue(provider_jobs.work_one(self.conn, [service.RECONCILE_JOB]))
        self.assertEqual(service.get(self.conn, row['id'])['payment_status'], 'captured')
        self.assertEqual(provider_jobs.status(self.conn, first['job'], 'a')['state'], 'succeeded')
        self.assertIsNone(provider_jobs.status(self.conn, first['job'], 'b'))   # owner-only

    def test_default_reconciles_inline_as_before(self):
        row = self.purchase()
        self.gateway_with_capture(row)
        result = service.request_reconcile(self.conn, 'a', row['id'])
        self.assertNotIn('job', result)
        self.assertEqual(result['payment_status'], 'captured')
        self.assertEqual(db.fetch_all(self.conn, 'ProviderJob'), [])

    def test_job_never_acts_for_another_member_or_environment(self):
        row = self.purchase()
        with patch.object(service, 'reconcile') as inline:
            service._reconcile_job(self.conn, {'user_id': 'b', 'ref': row['id']})
            with patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'live_pilot'}):
                service._reconcile_job(self.conn, {'user_id': 'a', 'ref': row['id']})
            service._reconcile_job(self.conn, {'user_id': 'a', 'ref': 'missing'})
        inline.assert_not_called()
        with self.assertRaises(ApiError):
            service.request_reconcile(self.conn, 'b', row['id'])           # not the owner

    def test_worker_registers_the_billing_job(self):
        import bgv_worker  # noqa: F401
        self.assertIn(service.RECONCILE_JOB, provider_jobs.HANDLERS)


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresMemberLockTests(unittest.TestCase):
    connect = pg.PostgresAuthenticationTests.connect
    cleanup = pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        for uid in ('payer_a', 'payer_b'):
            self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (%s,%s,%s)',
                              (uid, 'dating', 'verified'))
        p = patch.dict(os.environ, {'DHASHU_BILLING_MODE': 'sandbox', 'DHASHU_BILLING_TESTERS': 'payer_a,payer_b'})
        p.start(); self.addCleanup(p.stop)

    def test_one_members_billing_never_waits_for_another_member(self):
        first, second = self.connect(), self.connect()
        try:
            with service.transaction(first, 'payer_a'):
                result = {}

                def other_member():
                    start = time.monotonic()
                    result['quote'] = service.quote(second, 'payer_b', 'verification', None, 'web')
                    result['seconds'] = time.monotonic() - start
                t = threading.Thread(target=other_member); t.start(); t.join(timeout=5)
                self.assertFalse(t.is_alive(), "payer_b's quote waited on payer_a's billing lock")
                self.assertLess(result['seconds'], 2)
        finally:
            first.close(); second.close()

    def test_the_same_member_is_serialised(self):
        first, second = self.connect(), self.connect()
        try:
            order = []
            with service.transaction(first, 'payer_a'):
                def same_member():
                    service.quote(second, 'payer_a', 'verification', None, 'web')
                    order.append('second')
                t = threading.Thread(target=same_member); t.start(); t.join(timeout=1)
                self.assertTrue(t.is_alive(), "the member's second billing write did not wait")
                order.append('first')
            t.join(timeout=5)
            self.assertEqual(order, ['first', 'second'])
        finally:
            first.close(); second.close()


if __name__ == '__main__':
    unittest.main()
