"""c-api-abuse: method allow-list, 413/415/422/429, CORS lock, enumeration
detection, structured events; normal journeys unaffected."""
import json
import os
from unittest import mock

import abuse_guard
from test_segment_efg_routes import RouteTestCase, app_module

LIMITS_ON = {'DHASHU_ABUSE_LIMITS': '1'}


class AbuseGuardTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        abuse_guard.reset(); self.addCleanup(abuse_guard.reset)
        self.make_user('owner'); self.client.post('/login/owner')

    def error_code(self, response):
        return (response.get_json() or {}).get('error', {}).get('code')

    def test_methods_outside_the_allow_list_get_405(self):
        for method in ('TRACE', 'CONNECT', 'PROPFIND'):
            response = self.client.open('/api/v1/me', method=method)
            self.assertEqual(response.status_code, 405, method)
            self.assertEqual(self.error_code(response), 'method_not_allowed', method)   # the guard, not Flask's default

    def test_body_limits_413_with_a_larger_limit_only_for_uploads(self):
        big = json.dumps({'fields': {'note': 'x' * (1024 * 1024 + 10)}})
        response = self.client.patch('/api/v1/profile/stats', data=big, content_type='application/json')
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.error_code(response), 'payload_too_large')
        photo = json.dumps({'photo': 'data:image/png;base64,' + 'A' * (2 * 1024 * 1024)})
        self.assertNotEqual(self.client.put('/api/v1/profile/photo', data=photo, content_type='application/json').status_code, 413)
        too_big = json.dumps({'photo': 'A' * (3 * 1024 * 1024 + 10)})
        self.assertEqual(self.client.put('/api/v1/profile/photo', data=too_big, content_type='application/json').status_code, 413)
        with mock.patch.dict(os.environ, {'DHASHU_MAX_BODY_BYTES': '100'}):
            self.assertEqual(self.client.post('/api/v1/week/prepare', json={'pad': 'x' * 200}).status_code, 413)

    def test_non_json_writes_get_415(self):
        response = self.client.post('/api/v1/week/prepare', data='a=b', content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.error_code(response), 'unsupported_media_type')
        self.assertNotEqual(self.client.post('/api/v1/week/prepare', json={}).status_code, 415)

    def test_wrong_types_422_when_switched_on(self):
        with mock.patch.dict(os.environ, {'DHASHU_VALIDATION_STATUS': '422'}):
            self.assertEqual(self.client.post('/api/v1/simulated-clock', json={'advance_hours': 'two'}).status_code, 422)

    def test_cors_is_locked_to_configured_app_origins(self):
        preflight = {'Origin': 'https://evil.example', 'Access-Control-Request-Method': 'POST'}
        self.assertEqual(self.client.options('/api/v1/me', headers=preflight).status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', self.client.get('/api/v1/me', headers={'Origin': 'https://evil.example'}).headers)
        with mock.patch.dict(os.environ, {'DHASHU_CORS_ORIGINS': 'capacitor://localhost, https://localhost'}):
            ok = self.client.options('/api/v1/me', headers={'Origin': 'capacitor://localhost', 'Access-Control-Request-Method': 'POST'})
            self.assertEqual(ok.status_code, 204)
            self.assertEqual(ok.headers['Access-Control-Allow-Origin'], 'capacitor://localhost')
            self.assertIn('Authorization', ok.headers['Access-Control-Allow-Headers'])
            self.assertEqual(self.client.get('/api/v1/me', headers={'Origin': 'https://localhost'}).headers['Access-Control-Allow-Origin'], 'https://localhost')
            self.assertEqual(self.client.options('/api/v1/me', headers=preflight).status_code, 403)

    def test_limits_are_off_by_default(self):
        with mock.patch.dict(os.environ, {'DHASHU_RATE_GLOBAL': '3'}):
            statuses = {self.client.get('/api/v1/health').status_code for _ in range(10)}
        self.assertEqual(statuses, {200})

    def test_global_and_category_limits_429_with_retry_after(self):
        with mock.patch.dict(os.environ, {**LIMITS_ON, 'DHASHU_RATE_GLOBAL': '5'}), self.assertLogs('dhashu.abuse', 'WARNING') as logs:
            statuses = [self.client.get('/api/v1/health').status_code for _ in range(7)]
            self.assertEqual(statuses, [200] * 5 + [429, 429])
            limited = self.client.get('/api/v1/health')
            self.assertEqual(self.error_code(limited), 'rate_limited')
            self.assertTrue(limited.headers['Retry-After'].isdigit())
        self.assertEqual(sum('"scope": "global"' in line for line in logs.output), 1)    # one event, not one per request
        abuse_guard.reset()
        with mock.patch.dict(os.environ, LIMITS_ON), mock.patch.dict(abuse_guard.CATEGORIES, {'search': (('/api/v1/discovery',), 2, 60)}):
            codes = [self.client.get('/api/v1/discovery').status_code for _ in range(3)]
        self.assertNotEqual(codes[0], 429)
        self.assertEqual(codes[2], 429)

    def test_enumeration_is_detected_alerted_once_and_blocked_when_limits_on(self):
        with self.assertLogs('dhashu.abuse', 'WARNING') as logs:
            for i in range(abuse_guard.ENUMERATION_LIMIT + 5):
                self.assertEqual(self.client.get(f'/api/v1/jobs/guess-{i}').status_code, 404)
        spikes = [json.loads(line.split(':', 2)[2]) for line in logs.output if 'abuse_spike' in line]
        self.assertEqual(len(spikes), 1)
        self.assertRegex(spikes[0]['client'], r'^[0-9a-f]{16}$')           # hashed, never the address
        self.assertNotIn('127.0.0.1', ''.join(logs.output))
        self.assertEqual(self.client.get('/api/v1/me').status_code, 200)    # detection alone never blocks
        with mock.patch.dict(os.environ, LIMITS_ON):
            self.assertEqual(self.client.get('/api/v1/me').status_code, 429)

    def test_normal_journey_requests_are_unaffected_with_limits_on(self):
        with mock.patch.dict(os.environ, LIMITS_ON):
            for path in ('/api/v1/health', '/api/v1/me', '/api/v1/dashboard'):
                self.assertNotIn(self.client.get(path).status_code, (405, 413, 415, 429), path)
            self.assertNotIn(self.client.post('/api/v1/week/prepare', json={}).status_code, (405, 413, 415, 429))

    def test_registered_in_the_app(self):
        self.assertIn('abuse_before', [f.__name__ for f in app_module.app.before_request_funcs[None]])


class GuardOnItsOwnTests(__import__('unittest').TestCase):
    """The guard alone, on a bare app whose route checks nothing itself: proves the
    backstop for any future route that forgets json_object()."""

    def setUp(self):
        from flask import Flask
        abuse_guard.reset(); self.addCleanup(abuse_guard.reset)
        app = Flask('guard-only')

        @app.route('/api/v1/raw', methods=['POST', 'TRACE', 'PROPFIND'])
        def raw():
            from flask import request
            return {'size': len(request.get_data())}

        abuse_guard.register(app)
        self.client = app.test_client()

    def test_backstops(self):
        self.assertEqual(self.client.open('/api/v1/raw', method='TRACE').status_code, 405)
        self.assertEqual(self.client.open('/api/v1/raw', method='PROPFIND').status_code, 405)
        self.assertEqual(self.client.post('/api/v1/raw', data='a=b', content_type='text/plain').status_code, 415)
        self.assertEqual(self.client.post('/api/v1/raw', data='x' * (1024 * 1024 + 1), content_type='application/json').status_code, 413)
        self.assertEqual(self.client.post('/api/v1/raw', json={'ok': 1}).status_code, 200)
