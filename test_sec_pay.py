"""Regression tests for the removed simulated-payment path and fee policy."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from unittest import mock
import unittest

import db
import payments
import planning_service
from test_segment_efg_routes import RouteTestCase, app_module
from tools import e2e_server


class FakePaymentRegressionTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("payer"))
        self.make_user("partner")
        self.lock = self.make_lockin("payer", "partner")

    def test_legacy_payment_pages_and_confirmations_are_not_routes(self):
        for purpose in payments.PURPOSES:
            self.assertEqual(self.client.get(f"/pay/{purpose}").status_code, 404)
            for _ in range(2):
                self.assertEqual(self.client.post(f"/pay/{purpose}/confirm").status_code, 404)
        for purpose in ("", "unknown", "x%27%20OR%201%3D1", "x" * 500):
            self.assertEqual(self.client.get(f"/pay/{purpose}").status_code, 404)
            self.assertEqual(self.client.post(f"/pay/{purpose}/confirm").status_code, 404)
        self.assertEqual(db.fetch_all(self.conn, "Payment"), [])

    def test_removed_routes_are_404_without_login_or_for_another_member(self):
        with self.client.session_transaction() as session:
            session.clear()
        for path in ("/pay/guru", "/pay/guru/confirm"):
            response = self.client.get(path) if path.endswith("guru") else self.client.post(path)
            self.assertEqual(response.status_code, 404)
        self.login("partner")
        self.assertEqual(self.client.post("/pay/availability/confirm").status_code, 404)
        self.assertEqual(db.fetch_all(self.conn, "Payment"), [])

    def test_concurrent_fake_confirmations_cannot_write_a_payment(self):
        def attempt(_):
            return app_module.app.test_client().post('/pay/guru/confirm').status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(attempt, range(8))),[404]*8)
        self.assertEqual(db.fetch_all(self.conn,"Payment"),[])

    def test_legacy_paid_row_and_old_off_switch_cannot_unlock_availability(self):
        db.insert_row(self.conn, "Payment", {
            "id": "legacy-paid", "user_id": "payer", "purpose": payments.AVAILABILITY,
            "scope_id": self.lock, "amount_inr": 499, "status": "paid",
            "reference": "unverified", "created_at": "test",
        })
        with mock.patch.dict("os.environ", {
            "DHASHU_FEES_WAIVED": "0", "PAYMENTS_ENABLED": "0",
        }):
            self.assertFalse(planning_service.paid(
                self.conn, "payer", payments.AVAILABILITY, self.lock))

    def test_explicit_waiver_unlocks_without_a_payment_row(self):
        with mock.patch.dict("os.environ", {
            "DHASHU_FEES_WAIVED": "1", "PAYMENTS_ENABLED": "1",
        }):
            self.assertTrue(planning_service.paid(
                self.conn, "payer", payments.AVAILABILITY, self.lock))

    def test_guru_web_gate_uses_only_waiver_or_verified_entitlement(self):
        with mock.patch.dict("os.environ", {"DHASHU_FEES_WAIVED": "0", "PAYMENTS_ENABLED": "0"}):
            for path in ("/guru", "/guru/everything"):
                self.assertEqual(self.client.get(path).status_code, 403)
            with mock.patch("billing_service.legacy_entitled", return_value=True):
                self.assertEqual(self.client.get("/guru").status_code, 200)
        self.assertEqual(self.client.get("/guru").status_code, 200)


class LocalE2EPaymentPolicyTests(unittest.TestCase):
    def test_local_server_uses_explicit_waiver_and_removes_provider_keys(self):
        with mock.patch.dict(os.environ, {'PAYMENTS_ENABLED': '0', 'RAZORPAY_KEY_ID': 'test-only'}, clear=True):
            self.assertEqual(e2e_server.prepare_environment('/tmp/sec-pay-test'),
                             Path('/tmp/sec-pay-test/e2e.db'))
            self.assertEqual(os.environ['DHASHU_FEES_WAIVED'], '1')
            self.assertEqual(os.environ['DHASHU_BILLING_MODE'], 'sandbox')
            self.assertNotIn('RAZORPAY_KEY_ID', os.environ)

    def test_local_server_refuses_production_marker_before_mutating_environment(self):
        with mock.patch.dict(os.environ, {'RAILWAY_ENVIRONMENT': 'production', 'RAZORPAY_KEY_ID': 'test-only'}, clear=True):
            with self.assertRaises(SystemExit):
                e2e_server.prepare_environment('/tmp/sec-pay-test')
            self.assertEqual(os.environ['RAZORPAY_KEY_ID'], 'test-only')
