"""MSG91 is the primary OTP provider (owner decision 2026-11-27).

The real auth_delivery adapter runs; only the HTTPS opener is mocked, so no SMS is
sent. Covers: default provider, Twilio never required, sign-up / sign-in / resend
through MSG91, provider failure, the circuit breaker + otp_provider_down alert, the
5-per-number-per-day limit, the global breaker and the timing padding.
"""
import io
import json
import os
import time
import unittest
import urllib.error
from unittest import mock
from urllib.parse import parse_qs, urlparse

from flask import Flask

import alerts
import auth
import auth_delivery
import resilience
import test_auth

REAL_START, REAL_CHECK, REAL_CONFIGURED = auth_delivery.start, auth_delivery.check, auth_delivery.configured
MSG91_ENV = {'MSG91_AUTH_KEY': 'test-msg91-key', 'MSG91_TEMPLATE_ID': 'b' * 24}
TWILIO_NAMES = ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID', 'DHASHU_SMS_PROVIDER')


def msg91_only_env(**extra):
    """Environment with MSG91 settings and no Twilio settings or provider override."""
    env = {k: v for k, v in os.environ.items() if k not in TWILIO_NAMES}
    env.update(MSG91_ENV, **extra)
    return mock.patch.dict(os.environ, env, clear=True)


def reply(payload):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


class Msg91DefaultTests(unittest.TestCase):
    def test_msg91_is_the_default_provider(self):
        with msg91_only_env():
            self.assertEqual(auth_delivery.provider(), 'msg91')
            self.assertTrue(auth_delivery.configured())
        with msg91_only_env(DHASHU_SMS_PROVIDER='  '):
            self.assertEqual(auth_delivery.provider(), 'msg91')

    def test_twilio_settings_alone_do_not_configure_sign_in(self):
        twilio = {'TWILIO_ACCOUNT_SID': 'AC' + 'a' * 32, 'TWILIO_VERIFY_SERVICE_SID': 'VA' + 'b' * 32,
                  'TWILIO_AUTH_TOKEN': 'x'}
        with msg91_only_env(MSG91_AUTH_KEY='', **twilio):
            self.assertFalse(auth_delivery.configured())          # no silent fallback to Twilio
        with msg91_only_env(MSG91_TEMPLATE_ID='not-a-template'):
            self.assertFalse(auth_delivery.configured())
        with msg91_only_env(DHASHU_SMS_PROVIDER='twilio', **twilio):
            self.assertTrue(auth_delivery.configured())           # optional, explicit fallback

    def _register(self):
        app = Flask('msg91-startup')
        app.secret_key = 's' * 40
        auth.register_auth(app, lambda: None)
        return app

    def test_startup_needs_msg91_and_never_twilio(self):
        secure = {'AUTH_ENABLED': '1', 'AUTH_PUBLIC_ORIGIN': 'https://beta.example.test', 'SECRET_KEY': 's' * 40}
        with msg91_only_env(**secure):
            self.assertTrue(self._register().config['AUTH_ENABLED'])
        with msg91_only_env(MSG91_AUTH_KEY='', **secure):
            with self.assertRaises(RuntimeError) as caught:
                self._register()
        self.assertIn('MSG91_AUTH_KEY', str(caught.exception))
        self.assertNotIn('Twilio Verify configuration', str(caught.exception))

    def test_send_goes_to_msg91_and_twilio_is_never_called(self):
        with msg91_only_env(), mock.patch.object(auth_delivery, '_post') as twilio, \
                mock.patch.object(auth_delivery.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = reply({'type': 'success', 'request_id': 'req-1'})
            sid = auth_delivery.start('phone', '+919876543210')
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(urlparse(request.full_url).netloc, 'control.msg91.com')
            self.assertEqual(request.get_header('Authkey'), 'test-msg91-key')
            self.assertEqual(parse_qs(urlparse(request.full_url).query)['template_id'], ['b' * 24])
            self.assertEqual(sid, 'msg91:919876543210:req-1')
            twilio.assert_not_called()


class Msg91BreakerTests(unittest.TestCase):
    def setUp(self):
        resilience.reset_all(); self.addCleanup(resilience.reset_all)
        alerts.reset(); self.addCleanup(alerts.reset)

    def test_msg91_outage_opens_the_breaker_fails_fast_and_alerts(self):
        calls = []

        class Opener:
            def open(inner, request, timeout=None):
                calls.append(1)
                raise urllib.error.HTTPError(request.full_url, 500, 'down', {}, io.BytesIO(b'{}'))

        with msg91_only_env(), mock.patch('urllib.request.build_opener', return_value=Opener()), \
                self.assertLogs('dhashu.alert', level='WARNING') as logs:
            for _ in range(7):
                with self.assertRaises(auth_delivery.DeliveryUnavailable):
                    auth_delivery.start('phone', '+919876543210')
        self.assertEqual(len(calls), 5)                      # then fail fast without calling MSG91
        self.assertEqual(resilience.snapshot()['msg91'], 'open')
        events = [json.loads(r.getMessage()) for r in logs.records]
        self.assertIn(('circuit_open', 'msg91'), [(e['alert'], e.get('provider')) for e in events])
        self.assertIn(('otp_provider_down', 'msg91'), [(e['alert'], e.get('provider')) for e in events])


class Msg91RouteTests(unittest.TestCase):
    """Sign-up, sign-in and resend through the real MSG91 adapter (HTTP mocked)."""

    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        for name, real in (('start', REAL_START), ('check', REAL_CHECK), ('configured', REAL_CONFIGURED)):
            patcher = mock.patch.object(auth_delivery, name, real); patcher.start(); self.addCleanup(patcher.stop)
        env = msg91_only_env(DHASHU_OTP_MIN_RESPONSE_MS='0'); env.start(); self.addCleanup(env.stop)
        resilience.reset_all(); self.addCleanup(resilience.reset_all)
        alerts.reset(); self.addCleanup(alerts.reset)
        opener = mock.patch.object(auth_delivery.urllib.request, 'build_opener'); self.factory = opener.start()
        self.addCleanup(opener.stop)
        self.sent = []

        def open_(request, timeout=None):
            url = urlparse(request.full_url)
            query = parse_qs(url.query)
            if url.path.endswith('/otp/verify'):
                ok = query['otp'] == ['123456']
                return reply({'type': 'success', 'message': 'OTP verified success'} if ok
                             else {'type': 'error', 'message': 'OTP not match'})
            self.sent.append(query['mobile'][0])
            return reply({'type': 'success', 'request_id': 'req%d' % len(self.sent)})
        self.factory.return_value.open.side_effect = open_

    def advance(self, seconds):
        import auth_sessions
        return mock.patch('auth_sessions.now', return_value=auth_sessions.now() + seconds)

    def request(self, path, number, ip):
        return self.f.post(path, {'channel': 'phone', 'destination': number}, environ_base={'REMOTE_ADDR': ip})

    def verify(self, challenge, code):
        return self.f.post('verify', {'challenge_id': challenge, 'code': code})

    def test_sign_up_through_msg91_creates_the_account_only_after_the_code(self):
        response = self.request('signup/request', '+919812345678', '10.9.0.1')
        self.assertEqual(response.status_code, 202, response.json)
        self.assertEqual(self.sent, ['919812345678'])
        challenge = response.json['data']['challenge_id']
        self.assertEqual(self.verify(challenge, '000000').status_code, 401)   # wrong code
        done = self.verify(challenge, '123456')
        self.assertEqual(done.status_code, 200, done.json)
        self.assertIn('access_token', done.json['data'])

    def test_sign_in_and_resend_both_send_through_msg91(self):
        first = self.request('request', '+919876543210', '10.9.1.1')
        self.assertEqual(first.status_code, 202)
        with self.advance(61):                                                # resend after the cooldown
            again = self.request('request', '+919876543210', '10.9.1.2')
            self.assertEqual(again.status_code, 202)
            self.assertEqual(self.sent, ['919876543210', '919876543210'])
            self.assertEqual(self.verify(first.json['data']['challenge_id'], '123456').status_code, 401)  # replaced
            self.assertEqual(self.verify(again.json['data']['challenge_id'], '123456').status_code, 200)

    def test_msg91_failure_is_a_controlled_error_and_creates_no_account(self):
        self.factory.return_value.open.side_effect = urllib.error.HTTPError('u', 401, 'bad key', {}, io.BytesIO(b'{}'))
        response = self.request('signup/request', '+919812340000', '10.9.2.1')
        self.assertEqual((response.status_code, response.json['error']['code']), (503, 'otp_delivery_failed'))
        import db
        self.assertFalse([r for r in db.fetch_all(self.f.conn, 'Account') if r['phone'] == '919812340000'])

    def test_msg91_breaker_open_stops_sending(self):
        self.factory.return_value.open.side_effect = urllib.error.HTTPError('u', 500, 'down', {}, io.BytesIO(b'{}'))
        statuses = [self.request('signup/request', '+91981234%04d' % i, '10.9.3.%d' % i).status_code for i in range(7)]
        self.assertEqual(statuses, [503] * 7)
        self.assertEqual(self.factory.return_value.open.call_count, 5)
        self.assertEqual(resilience.snapshot()['msg91'], 'open')

    def test_five_codes_per_number_per_day_with_msg91(self):
        statuses = []
        for i in range(7):
            with self.advance(61 * i):
                statuses.append(self.request('request', '+919876543210', '10.9.4.%d' % i).status_code)
        self.assertEqual(statuses, [202] * 5 + [429, 429])
        self.assertEqual(len(self.sent), 5)                                   # no SMS past the limit

    def test_global_breaker_pauses_msg91_sends_and_alerts_once(self):
        with mock.patch.dict(os.environ, {'DHASHU_OTP_GLOBAL_PER_HOUR': '2'}), \
                self.assertLogs('dhashu.alert', level='WARNING') as logs:
            self.assertEqual(self.request('request', '+919876543210', '10.9.5.1').status_code, 202)
            self.assertEqual(self.request('signup/request', '+919811111111', '10.9.5.2').status_code, 202)
            paused = self.request('request', '+919876543211', '10.9.5.3')
        self.assertEqual((paused.status_code, paused.json['error']['code']), (503, 'otp_paused'))
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(sum('otp_global_breaker' in line for line in logs.output), 1)

    def test_timing_padding_applies_with_msg91(self):
        with mock.patch.dict(os.environ, {'DHASHU_OTP_MIN_RESPONSE_MS': '250'}):
            for number, ip in (('+919876543210', '10.9.6.1'), ('+919800000001', '10.9.6.2')):  # known / unknown
                started = time.monotonic()
                self.assertEqual(self.request('request', number, ip).status_code, 202)
                self.assertGreaterEqual(time.monotonic() - started, 0.25)


if __name__ == '__main__':
    unittest.main()
