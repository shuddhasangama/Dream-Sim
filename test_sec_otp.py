"""sec-otp: country allow-list, 5 codes per number per day, global hourly breaker."""
import os
import unittest
from unittest import mock

import auth_delivery
from test_auth import AuthenticationTests


class OtpPolicyTests(unittest.TestCase):
    def setUp(self):
        self.f = AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        import alerts
        alerts.reset(); self.addCleanup(alerts.reset)

    def request(self, destination, ip):
        return self.f.post('request', {'channel': 'phone', 'destination': destination},
                           environ_base={'REMOTE_ADDR': ip})

    def advance(self, seconds):
        import auth_sessions
        real = auth_sessions.now()
        return mock.patch('auth_sessions.now', return_value=real + seconds)

    def test_five_codes_per_number_per_day_for_known_and_unknown_numbers(self):
        for number in ('+919876543210', '+919800000000'):          # known account / unknown number
            statuses = []
            for i in range(7):
                with self.advance(61 * i):                         # past the 60 s per-number pacing
                    statuses.append(self.request(number, f'10.1.{i}.{len(number)}').status_code)
            self.assertEqual(statuses, [202] * 5 + [429, 429], number)

    def test_global_breaker_pauses_everyone_and_alerts_once(self):
        with mock.patch.dict(os.environ, {'DHASHU_OTP_GLOBAL_PER_HOUR': '2'}), self.assertLogs('dhashu.alert', level='WARNING') as logs:
            first = self.request('+919876543210', '10.2.0.1')
            self.assertEqual(first.status_code, 202)
            # the second real send reaches the limit
            second = self.f.post('signup/request', {'channel': 'phone', 'destination': '+919811111111'},
                                 environ_base={'REMOTE_ADDR': '10.2.0.2'})
            self.assertEqual(second.status_code, 202)
            for number, ip in (('+919876543211', '10.2.0.3'), ('+919822222222', '10.2.0.4')):  # known, unknown
                paused = self.request(number, ip)
                self.assertEqual(paused.status_code, 503)
                self.assertEqual(paused.json['error']['code'], 'otp_paused')
        self.assertEqual(sum('otp_global_breaker' in line for line in logs.output), 1)
        self.assertLessEqual(self.f.start.call_count, 2)

    def test_country_allow_list(self):
        with mock.patch.dict(os.environ, {'DHASHU_OTP_COUNTRIES': '44'}):
            response = self.request('+919876543210', '10.3.0.1')
        self.assertEqual((response.status_code, response.json['error']['code']), (400, 'country_unavailable'))
        self.f.start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
