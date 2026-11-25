"""mon-sentry + mon-alerts: request ids, JSON request logs without personal data,
Sentry off without a DSN and scrubbed with one, alert events."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import alerts
import db
import observability
from test_segment_efg_routes import RouteTestCase, app_module


class RequestIdAndLogTests(RouteTestCase):
    def test_request_id_header_is_generated_or_kept_when_well_formed(self):
        generated = self.client.get('/api/v1/health').headers['X-Request-ID']
        self.assertRegex(generated, r'^[0-9a-f]{32}$')
        kept = self.client.get('/api/v1/health', headers={'X-Request-ID': 'support-ticket-1234'})
        self.assertEqual(kept.headers['X-Request-ID'], 'support-ticket-1234')
        for bad in ('../../etc', 'x' * 100, 'short', 'has space here'):
            self.assertNotEqual(self.client.get('/api/v1/health', headers={'X-Request-ID': bad}).headers['X-Request-ID'], bad)

    def test_api_error_body_carries_the_request_id(self):
        response = self.client.get('/api/v1/does-not-exist', headers={'X-Request-ID': 'trace-abcdef12'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['error']['reference'], 'trace-abcdef12')

    def test_one_json_line_per_request_with_route_rule_and_no_personal_data(self):
        self.make_user('owner'); self.client.post('/login/owner')
        with self.assertLogs('dhashu.request', level='INFO') as logs, mock.patch.dict(os.environ, {'DHASHU_LOG_FORMAT': 'json'}):
            self.client.get('/api/v1/matches/owner%3A1%3A1?email=a@b.com&phone=%2B919876543210',
                            headers={'X-Request-ID': 'trace-12345678'})
        line = json.loads(logs.records[-1].getMessage())
        self.assertEqual(set(line), {'level', 'ts', 'request_id', 'method', 'route', 'status', 'duration_ms'})
        self.assertEqual(line['request_id'], 'trace-12345678')
        self.assertEqual(line['route'], '/api/v1/matches/<match_id>')       # the rule, not the member's ids
        text = logs.output[-1]
        for leak in ('owner', 'a@b.com', '9876543210', 'email', 'phone'):
            self.assertNotIn(leak, text)

    def test_mask_hides_emails_and_phones(self):
        self.assertEqual(observability.mask('call +91 98765 43210 or mail a.b@c.in'), 'call [phone] or mail [email]')


class SentryTests(RouteTestCase):
    def tearDown(self):
        import sentry_sdk
        sentry_sdk.init()   # back to an inactive client
        super().tearDown() if hasattr(super(), 'tearDown') else None

    def test_off_without_dsn(self):
        with mock.patch.dict(os.environ, {'SENTRY_DSN': ''}):
            self.assertFalse(observability.init_sentry())

    def test_events_are_scrubbed_before_they_leave_the_process(self):
        import sentry_sdk
        from sentry_sdk.transport import Transport
        sent = []

        class FakeTransport(Transport):
            def __init__(self):
                super().__init__({'dsn': 'https://public@example.invalid/1'})
            def capture_envelope(self, envelope):
                sent.append(envelope)
        with mock.patch.dict(os.environ, {'SENTRY_DSN': 'https://public@example.invalid/1'}):
            self.assertTrue(observability.init_sentry(transport=FakeTransport()))

        def probe():
            raise RuntimeError('failed for member +919876543210 owner@private.test')
        self.make_user('owner'); self.client.post('/login/owner')
        app_module.app.config['PROPAGATE_EXCEPTIONS'] = False
        try:
            with mock.patch.dict(app_module.app.view_functions, {'api_v1.prepare_week': probe}):
                response = self.client.post('/api/v1/week/prepare?email=owner@private.test',
                                            json={'phone': '+919876543210', 'password': 'hunter2-secret'},
                                            headers={'Authorization': 'Bearer secret-token-value',
                                                     'X-Request-ID': 'trace-sentry01', 'Cookie': 'session=abc'})
            self.assertEqual(response.status_code, 500)
        finally:
            app_module.app.config['PROPAGATE_EXCEPTIONS'] = None
        sentry_sdk.flush(2)
        payload = json.dumps([item.payload.json for env in sent for item in env.items if item.payload.json])
        self.assertTrue(sent, 'no event captured')
        for leak in ('919876543210', '98765', 'owner@private.test', 'hunter2', 'secret-token-value', 'session=abc'):
            self.assertNotIn(leak, payload)
        self.assertIn('trace-sentry01', payload)


class AlertTests(unittest.TestCase):
    def setUp(self):
        alerts.reset(); self.addCleanup(alerts.reset)

    def test_emit_is_structured_and_rate_limited(self):
        clock = iter([0, 10, 400]).__next__
        with self.assertLogs('dhashu.alert', level='WARNING') as logs:
            self.assertTrue(alerts.emit('abuse_spike', clock=clock, count=12, detail={'nested': 'dropped'}))
            self.assertFalse(alerts.emit('abuse_spike', clock=clock, count=13))   # within cooldown
            self.assertTrue(alerts.emit('abuse_spike', clock=clock, count=14))
        first = json.loads(logs.records[0].getMessage())
        self.assertEqual(first, {'alert': 'abuse_spike', 'count': 12})           # non-scalar fields dropped

    def test_server_error_spike_threshold(self):
        with mock.patch.dict(os.environ, {'DHASHU_ALERT_5XX_PER_MINUTE': '3'}), self.assertLogs('dhashu.alert', level='WARNING') as logs:
            results = [alerts.record_server_error(clock=lambda: 100.0) for _ in range(3)]
        self.assertEqual(results, [False, False, True])
        self.assertIn('server_error_spike', logs.output[0])

    def test_otp_breaker_opening_alerts_twice_and_other_providers_once(self):
        import resilience
        resilience.reset_all(); self.addCleanup(resilience.reset_all)
        with self.assertLogs('dhashu.alert', level='WARNING') as logs:
            for _ in range(5):
                resilience.breaker('twilio').failure()
            for _ in range(5):
                resilience.breaker('openai').failure()
        events = [json.loads(r.getMessage())['alert'] for r in logs.records]
        self.assertEqual(events, ['circuit_open', 'otp_provider_down', 'circuit_open'])

    def test_stuck_verification_jobs(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        conn = db.get_connection(Path(tmp.name) / 'a.db'); self.addCleanup(conn.close)
        db.init_db(conn)
        conn.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (?,?,?)', ('u1', 'dating', 'declared'))
        conn.execute('''INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at)
                        VALUES ('old','u1','current_employer','preproduction','processing','x','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')''')
        conn.execute('''INSERT INTO "ProviderJob" (id,kind,user_id,ref,idempotency_key,state,attempts,max_attempts,run_after,created_at,updated_at)
                        VALUES ('j','digilocker_create','u1','s','k','running',1,1,0,0,0)''')
        conn.commit()
        with self.assertLogs('dhashu.alert', level='WARNING') as logs:
            self.assertEqual(alerts.check_stuck_jobs(conn), 2)
        self.assertIn('"count":2', logs.output[0])


if __name__ == '__main__':
    unittest.main()
