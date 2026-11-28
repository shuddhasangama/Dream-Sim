"""Per-member limits on every authenticated mutation (abuse_guard, sec-peruser)."""

from concurrent.futures import ThreadPoolExecutor
import os
import re
import sqlite3
from unittest import mock

import abuse_guard
import auth
from test_segment_efg_routes import RouteTestCase, app_module


class WriteLimitConfigurationTests(__import__('unittest').TestCase):
    def test_default_and_valid_limits(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(abuse_guard.member_write_limit(), 60)
        for raw, expected in [('1', 1), ('60', 60), ('1000', 1000)]:
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': raw}):
                self.assertEqual(abuse_guard.member_write_limit(), expected)

    def test_invalid_limits_fail_closed(self):
        for raw in ('', '0', '-1', 'abc', '1001', '١', '9' * 10000):
            with self.subTest(raw=raw[:8]), mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': raw}):
                with self.assertRaises(abuse_guard.LimitUnavailable):
                    abuse_guard.member_write_limit()

    def test_invalid_limit_refuses_startup(self):
        from flask import Flask
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': 'off'}):
            with self.assertRaises(abuse_guard.LimitUnavailable):
                abuse_guard.register_member_limits(Flask('limits-test'), current_user=lambda: None,
                                                   get_db=lambda: None)


class ApiWriteLimitTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.make_user('owner')
        self.make_user('other')
        self.login('owner')

    def test_repeated_writes_are_limited_and_window_resets(self):
        clock = [1000]
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '2'}), \
                mock.patch('auth_sessions.now', side_effect=lambda: clock[0]):
            first = self.client.post('/api/v1/week/prepare', json={})
            second = self.client.post('/api/v1/week/prepare', json={})
            blocked = self.client.post('/api/v1/week/prepare', json={})
            self.assertEqual([first.status_code, second.status_code, blocked.status_code],
                             [200, 200, 429])
            self.assertEqual(blocked.json['data'], None)
            self.assertEqual(blocked.json['error']['code'], 'rate_limited')
            self.assertEqual(blocked.headers['Retry-After'], '60')
            clock[0] += 61
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 200)

    def test_default_allows_normal_use_before_the_sixty_first_write(self):
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '60'}), \
                mock.patch('auth_sessions.now', return_value=2000):
            statuses = [self.client.post('/api/v1/week/prepare', json={}).status_code for _ in range(61)]
        self.assertEqual(statuses, [200] * 60 + [429])

    def test_member_group_and_request_ids_cannot_evict_another_bucket(self):
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '2'}), \
                mock.patch('auth_sessions.now', return_value=3000):
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 200)
            self.assertEqual(self.client.post('/api/v1/week/prepare?user_id=other', json={}).status_code, 200)
            self.assertEqual(self.client.post('/api/v1/week/prepare?user_id=other', json={}).status_code, 429)
            self.assertEqual(self.client.patch('/api/v1/profile/stats', json={}).status_code, 400)
            self.assertEqual(self.client.patch('/api/v1/profile/stats', json={}).status_code, 400)
            self.assertEqual(self.client.patch('/api/v1/profile/stats', json={}).status_code, 429)
            self.login('other')
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 200)
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 200)
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 429)
        keys = [row['id'] for row in self.conn.execute('SELECT id FROM "AuthThrottle"')]
        self.assertEqual(len(keys), 3)
        self.assertTrue(all(re.fullmatch(r'[a-f0-9]{64}', key) for key in keys))
        self.assertTrue(all('owner' not in key and 'other' not in key for key in keys))

    def test_every_write_method_is_counted(self):
        cases = [
            ('POST', '/api/v1/week/prepare', {}),
            ('PUT', '/api/v1/profile/bio', {}),
            ('PATCH', '/api/v1/profile/stats', {}),
            ('DELETE', '/api/v1/couples/unknown/road/routine/unknown', None),
        ]
        clock = [4000]
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '1'}), \
                mock.patch('auth_sessions.now', side_effect=lambda: clock[0]):
            for method, path, payload in cases:
                with self.subTest(method=method):
                    first = self.client.open(path, method=method, json=payload)
                    blocked = self.client.open(path, method=method, json=payload)
                    self.assertNotEqual(first.status_code, 429)
                    self.assertEqual(blocked.status_code, 429)
                    self.assertEqual(blocked.json['error']['code'], 'rate_limited')
                    clock[0] += 61

    def test_dynamic_ids_share_one_route_group(self):
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '2'}), \
                mock.patch('auth_sessions.now', return_value=5000):
            codes = [self.client.post(f'/api/v1/matches/guess-{i}/actions', json={}).status_code
                     for i in range(3)]
        self.assertEqual(codes, [400, 400, 429])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "AuthThrottle"').fetchone()[0], 1)

    def test_signed_out_and_expired_sessions_do_not_consume_a_bucket(self):
        with self.client.session_transaction() as session:
            session.clear()
        with mock.patch('auth_sessions.throttle', side_effect=AssertionError('throttle used')):
            for _ in range(3):
                response = self.client.post('/api/v1/week/prepare', json={})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json['error']['code'], 'authentication_required')
            with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True}), \
                    mock.patch.object(auth, 'resolve', return_value=None):
                with self.client.session_transaction() as session:
                    session['user_id'] = 'owner'
                response = self.client.post('/api/v1/week/prepare', json={},
                                            headers={'Authorization': 'Bearer expired-local-test-token'})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json['error']['code'], 'authentication_required')

    def test_reads_and_automated_callbacks_are_excluded(self):
        with mock.patch('auth_sessions.throttle', side_effect=AssertionError('throttle used')):
            self.assertEqual(self.client.get('/api/v1/me').status_code, 200)
            self.assertEqual(self.client.get('/api/v1/health').status_code, 200)
            self.assertEqual(self.client.post('/billing/webhooks/razorpay', json={}).status_code, 401)
            self.assertEqual(self.client.post('/public/signzy/digilocker/callback/' + 'x' * 32,
                                              json={}).status_code, 404)

    def test_invalid_configuration_and_database_failure_fail_closed(self):
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': 'bad'}):
            response = self.client.post('/api/v1/week/prepare', json={})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json['error']['code'], 'rate_limit_unavailable')
        with mock.patch('auth_sessions.throttle', side_effect=sqlite3.OperationalError('synthetic failure')):
            response = self.client.post('/api/v1/week/prepare', json={})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json['error']['code'], 'rate_limit_unavailable')
            self.assertNotIn('synthetic failure', response.get_data(as_text=True))

    def test_concurrent_requests_share_the_database_counter(self):
        def request_write(_index):
            client = app_module.app.test_client()
            with client.session_transaction() as session:
                session['user_id'] = 'owner'
            return client.patch('/api/v1/profile/stats', json={}).status_code

        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '2'}), \
                mock.patch('auth_sessions.now', return_value=6000):
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(request_write, range(6)))
        self.assertEqual(sorted(results), [400, 400, 429, 429, 429, 429])

    def test_domain_snapshot_still_detects_every_other_table_change(self):
        before = self.domain_snapshot()
        self.conn.execute('INSERT INTO "AuthThrottle" (id, attempts, expires_at) VALUES (?, 1, 1)',
                          ('synthetic-test-counter',))
        self.conn.commit()
        self.assertEqual(self.domain_snapshot(), before)
        self.conn.execute('UPDATE "User" SET journey_state = ? WHERE id = ?', ('relationship', 'owner'))
        self.conn.commit()
        self.assertNotEqual(self.domain_snapshot(), before)

    def test_web_form_writes_are_limited_per_member_too(self):
        # "every action": the web pages, not only /api/v1, share the member limit.
        clock = [7000]
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '2'}), \
                mock.patch('auth_sessions.now', side_effect=lambda: clock[0]):
            codes = [self.client.post('/chemistry/set', data={'key': '', 'value': ''}).status_code
                     for _ in range(3)]
            self.assertEqual(codes, [302, 302, 429])
            blocked = self.client.post('/chemistry/set', data={'key': '', 'value': ''})
            self.assertEqual(blocked.headers['Retry-After'], '60')
            self.assertNotIn('owner', blocked.get_data(as_text=True))
            # Another route group is a separate bucket; the window resets.
            self.assertNotEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 429)
            clock[0] += 61
            self.assertEqual(self.client.post('/chemistry/set', data={'key': '', 'value': ''}).status_code, 302)

    def test_limit_event_carries_the_client_key_never_the_member_id(self):
        with mock.patch.dict(os.environ, {'DHASHU_RATE_USER_WRITES': '1'}), \
                mock.patch('auth_sessions.now', return_value=8000), \
                self.assertLogs('dhashu.abuse', level='WARNING') as logs:
            self.client.post('/api/v1/week/prepare', json={})
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 429)
        line = '\n'.join(logs.output)
        self.assertIn('"scope": "member"', line)
        self.assertIn('"client": "', line)
        self.assertNotIn('owner', line)

    def test_normal_journey_burst_stays_under_the_default(self):
        # A member saving a whole form quickly (20 fields) and moving on is never limited.
        with mock.patch('auth_sessions.now', return_value=9000):
            codes = [self.client.post('/chemistry/set', data={'key': '', 'value': ''}).status_code
                     for _ in range(20)]
            codes += [self.client.post('/api/v1/week/prepare', json={}).status_code for _ in range(20)]
        self.assertNotIn(429, codes)
