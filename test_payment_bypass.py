"""DHASHU_PAYMENT_BYPASS (owner decision 2026-11-27): while billing moves no real money,
one explicit setting unlocks every paid step, opens no checkout and charges nothing.
It is impossible in 'live' and 'live_pilot'."""
import os
import unittest
from unittest import mock

import billing_catalog as catalog
import billing_service
import db
import payments
import planning_service
import verification_payment
from api_contract import ApiError
import test_journey_api
import test_planning_api
from test_segment_efg_routes import app_module


def env(**values):
    clean = {k: v for k, v in os.environ.items() if k not in ('DHASHU_PAYMENT_BYPASS', 'DHASHU_FEES_WAIVED', 'DHASHU_BILLING_MODE')}
    clean.update(values)
    return mock.patch.dict(os.environ, clean, clear=True)


class BypassRuleTests(unittest.TestCase):
    def test_active_only_when_set_and_no_real_money_moves(self):
        cases = {('1', 'disabled'): True, ('1', 'sandbox'): True, ('true', None): True,
                 ('1', 'live'): False, ('1', 'live_pilot'): False, ('1', 'bogus'): False,
                 ('0', 'disabled'): False, (None, 'disabled'): False, ('maybe', 'disabled'): False}
        for (bypass, mode), expected in cases.items():
            values = {k: v for k, v in (('DHASHU_PAYMENT_BYPASS', bypass), ('DHASHU_BILLING_MODE', mode)) if v is not None}
            with env(**values):
                self.assertIs(catalog.payment_bypass(), expected, (bypass, mode))

    def test_sec_pay_name_is_only_an_alias_of_the_one_bypass(self):
        # sec-pay drafted DHASHU_FEES_WAIVED; it follows exactly the same rule, never a second one.
        for mode, expected in (('disabled', True), ('sandbox', True), ('live', False), ('live_pilot', False)):
            with env(DHASHU_FEES_WAIVED='1', DHASHU_BILLING_MODE=mode):
                self.assertIs(catalog.payment_bypass(), expected, mode)
        for mode in ('live', 'live_pilot'):
            with self.assertRaises(RuntimeError) as caught:
                catalog.startup_check({'DHASHU_FEES_WAIVED': '1', 'DHASHU_BILLING_MODE': mode})
            self.assertIn('DHASHU_FEES_WAIVED', str(caught.exception))
        with self.assertRaises(RuntimeError):
            catalog.validate_bypass({'DHASHU_FEES_WAIVED': 'maybe'})
        self.assertFalse(hasattr(catalog, 'fees_waived'))

    def test_startup_refuses_bypass_in_live_modes_in_every_environment(self):
        for mode in ('live', 'live_pilot'):
            for production in ({}, {'RAILWAY_ENVIRONMENT_NAME': 'production'}):
                with self.assertRaises(RuntimeError) as caught:
                    catalog.startup_check({'DHASHU_PAYMENT_BYPASS': '1', 'DHASHU_BILLING_MODE': mode, **production})
                self.assertIn('DHASHU_PAYMENT_BYPASS', str(caught.exception))
        with self.assertRaises(RuntimeError):
            catalog.startup_check({'DHASHU_PAYMENT_BYPASS': 'maybe'})

    def test_startup_allows_bypass_with_billing_disabled_in_production_and_logs_it(self):
        settings = {'DHASHU_PAYMENT_BYPASS': '1', 'DHASHU_BILLING_MODE': 'disabled', 'RAILWAY_ENVIRONMENT_NAME': 'production'}
        self.assertIsNone(catalog.startup_check(settings))
        self.assertIn('PAYMENT BYPASS ON', catalog.startup_notice(settings))
        self.assertIsNone(catalog.startup_notice({'DHASHU_BILLING_MODE': 'disabled'}))
        self.assertIsNone(catalog.startup_notice({'DHASHU_PAYMENT_BYPASS': '1', 'DHASHU_BILLING_MODE': 'live'}))

    def test_bypass_overrides_the_fee_switch_and_real_billing(self):
        with env(DHASHU_PAYMENT_BYPASS='1', PAYMENTS_ENABLED='1', DHASHU_BILLING_MODE='sandbox',
                 DHASHU_BILLING_TESTERS='owner'):
            # sec-pay: billing_service.fee_satisfied is the one fee authority.
            self.assertFalse(catalog.real_billing('owner'))
            self.assertTrue(billing_service.fee_satisfied(None, 'owner', payments.AVAILABILITY, 'lock-1'))
        with env(PAYMENTS_ENABLED='0'):                                # the retired switch opens nothing
            with mock.patch('billing_service.legacy_entitled', return_value=False):
                self.assertFalse(billing_service.fee_satisfied(None, 'owner', payments.AVAILABILITY, 'lock-1'))
        with env(DHASHU_PAYMENT_BYPASS='1', PAYMENTS_ENABLED='0', DHASHU_BILLING_MODE='live'):
            with mock.patch('billing_service.legacy_entitled', return_value=False):   # never in live
                self.assertFalse(billing_service.fee_satisfied(None, 'owner', payments.AVAILABILITY, 'lock-1'))

    def test_no_checkout_opens_and_nothing_is_charged(self):
        with env(DHASHU_PAYMENT_BYPASS='1', DHASHU_BILLING_MODE='sandbox', DHASHU_BILLING_TESTERS='owner'):
            with self.assertRaises(ApiError) as caught:
                catalog.price('owner', 'guru')
            self.assertEqual((caught.exception.code, caught.exception.status), ('payment_bypass', 409))
            for action in (verification_payment.start, verification_payment.complete,
                           verification_payment.confirm_provider_payment):
                with mock.patch.object(verification_payment, 'Razorpay') as gateway:
                    with self.assertRaises(ApiError) as caught:
                        action(None, 'owner')
                    self.assertEqual(caught.exception.code, 'payment_bypass')
                    gateway.assert_not_called()
            view = verification_payment.view(None, 'owner')
            self.assertEqual((view['required'], view['can_begin'], view['payment_bypass']), (False, True, True))
            self.assertIn('Test mode', view['message'])


class BypassRouteTests(unittest.TestCase):
    """The real date-planning fee gate (403 payment_required) opens under the bypass."""

    def setUp(self):
        self.f = test_planning_api.PlanningApiTests('test_payment_is_required_and_never_granted_by_api')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_paid_step_unlocked_with_no_payment_row_and_blocked_again_without_bypass(self):
        f = self.f
        with env(PAYMENTS_ENABLED='1'):
            self.assertEqual(f.request(f.base+'/availability', method='PUT', body={'slots': [f.slot]}).status_code, 403)
        with env(PAYMENTS_ENABLED='1', DHASHU_PAYMENT_BYPASS='1'):
            calendar = f.request(f.base+'/calendar').json['data']['payment']
            self.assertEqual((calendar['satisfied'], calendar['enforced']), (True, False))
            self.assertTrue(planning_service.paid(f.conn, 'owner', payments.AVAILABILITY, 'lock-1'))
            saved = f.request(f.base+'/availability', method='PUT', body={'slots': [f.slot]})
            self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(db.fetch_all(f.conn, 'Payment'), [])        # nothing charged, no simulated grant
        self.assertEqual(db.fetch_all(f.conn, 'BillingPurchase'), [])

    def test_verification_payment_route_reports_test_mode(self):
        with env(DHASHU_PAYMENT_BYPASS='1', DHASHU_BILLING_MODE='sandbox'):
            data = self.f.request('/verification/payment').json['data']
            self.assertEqual((data['can_begin'], data['payment_bypass']), (True, True))
            started = self.f.request('/verification/payment/start', method='POST', body={})
            self.assertEqual((started.status_code, started.json['error']['code']), (409, 'payment_bypass'))


class BypassDashboardTests(unittest.TestCase):
    def setUp(self):
        self.f = test_journey_api.JourneyApiTests('test_dashboard_and_status_are_same_own_read_model')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_dashboard_flag_drives_the_app_note(self):
        with env(DHASHU_PAYMENT_BYPASS='1'):
            self.assertIs(self.f.get('/dashboard').json['data']['payment_bypass'], True)
        with env():
            self.assertNotIn('payment_bypass', self.f.get('/dashboard').json['data'])
        with env(DHASHU_PAYMENT_BYPASS='1', DHASHU_BILLING_MODE='live'):
            self.assertNotIn('payment_bypass', self.f.get('/dashboard').json['data'])

    def test_web_pages_show_the_note(self):
        template = app_module.app.jinja_env.get_template('base.html')
        with app_module.app.test_request_context('/'):
            shown = template.render(session_user={'user_id': 'x'}, payment_bypass=True, brand_name='DhaShu')
            hidden = template.render(session_user={'user_id': 'x'}, payment_bypass=False, brand_name='DhaShu')
        self.assertIn('Test mode: payments off', shown)
        self.assertNotIn('Test mode: payments off', hidden)


if __name__ == '__main__':
    unittest.main()
