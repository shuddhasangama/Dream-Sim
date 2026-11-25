"""sec-session: refresh-token reuse revokes everything; OTP requests reveal nothing."""
import os
import time
import unittest
from unittest import mock

import auth_sessions as sessions
import test_auth


class SessionSecurityTests(unittest.TestCase):
    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_refresh_token_reuse_revokes_every_session_and_records_an_event(self):
        f = self.f
        first = f.login_mobile()
        other_device = sessions.issue(f.conn, 'owner')
        bystander = sessions.issue(f.conn, 'other')
        rotated = f.post('refresh', {'refresh_token': first['refresh_token']})
        self.assertEqual(rotated.status_code, 200)
        new = rotated.json['data'] if 'data' in rotated.json else rotated.json
        with self.assertLogs('dhashu.alert', level='WARNING') as logs:
            self.assertEqual(f.post('refresh', {'refresh_token': first['refresh_token']}).status_code, 401)  # replay
        self.assertTrue(any('security_event' in line for line in logs.output))
        for tokens in (new, other_device):                                  # thief's and owner's sessions all dead
            self.assertEqual(f.client.get('/api/v1/me', headers=f.bearer(tokens)).status_code, 401)
        self.assertEqual(f.post('refresh', {'refresh_token': new['refresh_token']}).status_code, 401)
        self.assertEqual(f.client.get('/api/v1/me', headers=f.bearer(bystander)).status_code, 200)  # other members untouched
        events = f.conn.execute('SELECT user_id, kind FROM SecurityEvent').fetchall()
        self.assertEqual([tuple(e) for e in events], [('owner', 'refresh_token_reuse')])

    def test_otp_request_bodies_and_timing_do_not_reveal_accounts(self):
        f = self.f
        def timed(number, ip):
            started = time.monotonic()
            response = f.post('request', {'channel': 'phone', 'destination': number}, environ_base={'REMOTE_ADDR': ip})
            return response, time.monotonic() - started
        slow_provider = lambda *a, **k: (time.sleep(0.2), 'SID')[1]
        f.start.side_effect = slow_provider
        with mock.patch.dict(os.environ, {'DHASHU_OTP_MIN_RESPONSE_MS': '400'}):
            known, known_s = timed('+919876543210', '10.9.0.1')
            unknown, unknown_s = timed('+919899999999', '10.9.0.2')
        self.assertEqual((known.status_code, unknown.status_code), (202, 202))
        strip = lambda body: {**body, 'data': {k: v for k, v in body['data'].items() if k != 'challenge_id'}}
        self.assertEqual(strip(known.json), strip(unknown.json))
        self.assertGreaterEqual(unknown_s, 0.38)                      # unknown waits as long as known
        self.assertGreaterEqual(known_s, 0.38)
        self.assertLess(abs(known_s - unknown_s), 0.15)


if __name__ == '__main__':
    unittest.main()
