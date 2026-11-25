"""c-resilience: circuit breakers, database timeouts, clean 503s, graceful worker
shutdown, and outage tests proving other routes keep answering."""
import io
import os
import threading
import time
import unittest
import urllib.error
from unittest import mock

import db
import resilience
from test_segment_efg_routes import RouteTestCase


class BreakerTests(unittest.TestCase):
    def make(self, **kw):
        self.now = [0.0]
        return resilience.CircuitBreaker('t', failures=3, reset=30, clock=lambda: self.now[0], **kw)

    def test_opens_after_consecutive_failures_and_recovers_through_one_trial(self):
        b = self.make()
        for _ in range(2):
            self.assertTrue(b.allow()); b.failure()
        self.assertEqual(b.state, 'closed')
        b.failure()
        self.assertEqual(b.state, 'open')
        self.assertFalse(b.allow())
        self.now[0] = 30
        self.assertTrue(b.allow())                  # one trial in half-open
        self.assertFalse(b.allow())                 # only one at a time
        b.failure()
        self.assertEqual(b.state, 'open')           # trial failed: open again
        self.now[0] = 61
        self.assertTrue(b.allow()); b.success()
        self.assertEqual((b.state, b.failures), ('closed', 0))

    def test_client_errors_are_not_outages(self):
        resilience.reset_all()
        def bad_request():
            raise urllib.error.HTTPError('u', 400, 'bad', {}, io.BytesIO(b''))
        def outage():
            raise urllib.error.HTTPError('u', 503, 'down', {}, io.BytesIO(b''))
        for _ in range(10):
            with self.assertRaises(urllib.error.HTTPError):
                resilience.call('x', bad_request)
        self.assertEqual(resilience.snapshot()['x'], 'closed')
        for _ in range(5):
            with self.assertRaises(urllib.error.HTTPError):
                resilience.call('x', outage)
        with self.assertRaises(resilience.CircuitOpen):
            resilience.call('x', lambda: 'never called')
        self.assertIsInstance(resilience.CircuitOpen('x'), ConnectionError)

    def test_thread_safe_under_concurrent_failures(self):
        b = self.make()
        def hammer():
            for _ in range(200):
                if b.allow():
                    b.failure()
        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(b.state, 'open')


class ProviderOutageTests(unittest.TestCase):
    def test_guru_timeouts_fall_back_and_stop_calling_the_provider(self):
        import guru_provider
        calls = []
        def slow(*a, **k):
            calls.append(1); raise TimeoutError()
        with mock.patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic', 'DHASHU_GURU_AI_ENABLED': '1', 'DHASHU_GURU_MODEL': 'synthetic-model'}), \
                mock.patch.object(guru_provider, 'urlopen', slow):
            for _ in range(8):
                self.assertIsNone(guru_provider.reply('hello', 'topic', [], [], {}))
        self.assertEqual(len(calls), 5)               # breaker opened: no more waiting on a dead provider
        self.assertEqual(resilience.snapshot()['openai'], 'open')

    def test_twilio_500s_open_the_breaker_and_fail_fast(self):
        import auth_delivery
        calls = []
        class Opener:
            def open(inner, request, timeout=None):
                calls.append(1); raise urllib.error.HTTPError('u', 500, 'down', {}, io.BytesIO(b'{}'))
        with mock.patch.object(auth_delivery, '_twilio_configured', return_value=True), \
                mock.patch.dict(os.environ, {'TWILIO_VERIFY_SERVICE_SID': 'VA' + '0' * 32, 'TWILIO_ACCOUNT_SID': 'AC' + '0' * 32, 'TWILIO_AUTH_TOKEN': 'x'}), \
                mock.patch('urllib.request.build_opener', return_value=Opener()):
            for _ in range(7):
                with self.assertRaises(auth_delivery.DeliveryUnavailable):
                    auth_delivery._post('Verifications', {'To': '+919876543210', 'Channel': 'sms'})
        self.assertEqual(len(calls), 5)

    def test_signzy_open_circuit_is_reported_as_not_sent(self):
        from signzy.client import Client, Config
        for _ in range(5):
            resilience.breaker('signzy').failure()
        with mock.patch('urllib.request.build_opener') as opener:
            summary = Client(Config(token='synthetic')).execute('current_employer',
                {'panNumber': 'AAAAA0000A', 'mobile': '9000000000'}, consent_confirmed=True, evidence_sink=lambda _: None)
        opener.return_value.open.assert_not_called()
        self.assertEqual(summary['outcome'], 'not_sent_provider_circuit_open')
        self.assertFalse(summary['retry_automatically'])


class BusyDatabaseTests(RouteTestCase):
    def test_pool_exhaustion_is_a_clean_retryable_503_and_other_routes_answer(self):
        from psycopg_pool import PoolTimeout
        self.make_user('owner')
        self.assertEqual(self.client.post('/login/owner').status_code, 302)
        with mock.patch.object(db, 'acquire', side_effect=PoolTimeout('pool exhausted at 10.0.0.5')):
            response = self.client.get('/api/v1/me')
            liveness = self.client.get('/api/v1/health')          # needs no database
            page = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['error']['code'], 'service_busy')
        self.assertEqual(response.headers['Retry-After'], '2')
        self.assertNotIn('10.0.0.5', response.get_data(as_text=True))
        self.assertEqual(liveness.status_code, 200)
        self.assertEqual(page.status_code, 503)
        self.assertEqual(self.client.get('/api/v1/me').status_code, 200)   # recovers at once

    def test_busy_errors_are_not_written_to_the_database(self):
        from psycopg import errors as pg_errors
        self.make_user('owner'); self.client.post('/login/owner')
        with mock.patch('errors.record') as record, \
                mock.patch.object(db, 'acquire', side_effect=pg_errors.QueryCanceled('canceling statement due to statement timeout')):
            self.assertEqual(self.client.get('/api/v1/me').status_code, 503)
        record.assert_not_called()


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresTimeoutTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        dsn = Path(os.environ['AUTH_TEST_POSTGRES_DSN_FILE']).read_text(encoding='ascii').strip()
        env = mock.patch.dict(os.environ, {'DATABASE_URL': dsn, 'DHASHU_DB_POOL': '1', 'DHASHU_DB_POOL_MAX': '2',
                                           'DHASHU_DB_STATEMENT_TIMEOUT_MS': '300', 'DHASHU_DB_LOCK_TIMEOUT_MS': '200'})
        env.start(); self.addCleanup(env.stop)
        db.close_pools(); self.addCleanup(db.close_pools)

    def test_slow_query_is_cancelled_and_the_connection_stays_usable(self):
        from psycopg import errors as pg_errors
        for conn in (db.get_connection(), db.acquire()):
            self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'], '300ms')
            self.assertEqual(conn.execute('SHOW lock_timeout').fetchone()['lock_timeout'], '200ms')
            start = time.monotonic()
            with self.assertRaises(pg_errors.QueryCanceled):
                conn.execute('SELECT pg_sleep(3)')
            self.assertLess(time.monotonic() - start, 2)
            conn.rollback()
            self.assertEqual(conn.execute('SELECT 1 AS one').fetchone()['one'], 1)
            conn.commit()
            (db.release(conn) if conn is not None else None)

    def test_url_options_like_search_path_are_kept(self):
        from urllib.parse import quote
        base = os.environ['DATABASE_URL']
        with mock.patch.dict(os.environ, {'DATABASE_URL': base + ('&' if '?' in base else '?') + 'options=' + quote('-csearch_path=pg_catalog')}):
            conn = db.get_connection()
            try:
                self.assertEqual(conn.execute('SHOW search_path').fetchone()['search_path'], 'pg_catalog')
                self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'], '300ms')
            finally:
                conn.close()


class WorkerShutdownTests(unittest.TestCase):
    def test_stop_ends_the_loop_between_iterations(self):
        import bgv_worker
        stop, steps = threading.Event(), []
        def step():
            steps.append(1)
            if len(steps) == 3:
                stop.set()              # e.g. SIGTERM arrives mid-iteration
            return True
        t = threading.Thread(target=bgv_worker.loop, args=(stop, step, 0.01)); t.start(); t.join(timeout=3)
        self.assertFalse(t.is_alive())
        self.assertEqual(len(steps), 3)  # the in-flight iteration finished; no new one started

    def test_idle_wait_wakes_immediately_on_stop(self):
        import bgv_worker
        stop = threading.Event()
        t = threading.Thread(target=bgv_worker.loop, args=(stop, lambda: False, 60)); t.start()
        time.sleep(0.1); start = time.monotonic(); stop.set(); t.join(timeout=3)
        self.assertFalse(t.is_alive())
        self.assertLess(time.monotonic() - start, 1)


if __name__ == '__main__':
    unittest.main()
