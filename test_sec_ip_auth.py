"""sec-ip through the real auth endpoints, behind a simulated Railway proxy."""
import os
import unittest
from unittest import mock

import client_ip
import test_auth

PROXY = '100.64.0.7'


class SecIpAuthTests(unittest.TestCase):
    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        client_ip.reset(); self.addCleanup(client_ip.reset)
        p = mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': 'railway', 'DHASHU_SHARED_IP_ALERT': '1000'})
        p.start(); self.addCleanup(p.stop)

    def ask(self, number, visitor, spoof=None):
        chain = (spoof + ', ' if spoof else '') + visitor
        return self.f.post('request', {'channel': 'phone', 'destination': number},
                           environ_base={'REMOTE_ADDR': PROXY}, headers={'X-Forwarded-For': chain})

    def test_one_hundred_visitors_each_get_their_own_limit(self):
        statuses = [self.ask(f'+9198{n:08d}', f'198.51.{n // 250}.{n % 250 + 1}').status_code for n in range(100)]
        self.assertEqual(statuses, [202] * 100)          # before sec-ip: the 21st visitor got 429 (one shared bucket)

    def test_one_attacker_is_still_limited_to_20_per_10_minutes_even_when_spoofing(self):
        statuses = [self.ask(f'+9197{n:08d}', '203.0.113.66', spoof=f'10.9.{n}.1').status_code for n in range(22)]
        self.assertEqual(statuses[:20], [202] * 20)
        self.assertEqual(statuses[20:], [429, 429])

    def test_full_sign_in_journey_behind_the_proxy(self):
        headers = {'X-Forwarded-For': '198.51.100.20'}
        r = self.f.post('request', {'channel': 'phone', 'destination': '+919876543210'},
                        environ_base={'REMOTE_ADDR': PROXY}, headers=headers)
        self.assertEqual(r.status_code, 202)
        tokens = self.f.post('verify', {'challenge_id': r.json['data']['challenge_id'], 'code': '123456'},
                             environ_base={'REMOTE_ADDR': PROXY}, headers=headers)
        self.assertEqual(tokens.status_code, 200)
        self.assertEqual(self.f.client.get('/api/v1/me', headers=self.f.bearer(tokens.json['data'])).status_code, 200)
        refreshed = self.f.post('refresh', {'refresh_token': tokens.json['data']['refresh_token']},
                                environ_base={'REMOTE_ADDR': PROXY}, headers=headers)
        self.assertEqual(refreshed.status_code, 200)

    def test_shared_ip_bucket_alert_from_the_real_endpoint(self):
        with mock.patch.dict(os.environ, {'DHASHU_SHARED_IP_ALERT': '3'}), mock.patch('alerts.emit') as emit:
            for n in range(5):
                self.ask(f'+9196{n:08d}', '203.0.113.77')
        self.assertIn('shared_ip_bucket', [c.args[0] for c in emit.call_args_list])


if __name__ == '__main__':
    unittest.main()
