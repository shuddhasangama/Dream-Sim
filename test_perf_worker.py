"""perf-worker: background provider jobs (idempotent, leased, retried, dead-lettered)
and DigiLocker consent links created by the worker instead of inside the request."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import db
import provider_jobs as jobs
import test_auth_postgres as pg
from test_digilocker_signup import DigiLockerSignupTests


class JobLifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.conn = db.get_connection(Path(tmp.name) / 'j.db'); self.addCleanup(self.conn.close)
        db.init_db(self.conn)
        self.ran, self.dead = [], []
        handlers = dict(jobs.HANDLERS)
        self.addCleanup(lambda: (jobs.HANDLERS.clear(), jobs.HANDLERS.update(handlers)))
        jobs.register_kind('probe', lambda conn, job: self.ran.append(job['ref']),
                           on_dead=lambda conn, job: self.dead.append(job['ref']), max_attempts=3, lease=30)
        jobs.register_kind('flaky', self.fail_run, on_dead=lambda conn, job: self.dead.append(job['ref']), max_attempts=2, lease=30)

    def fail_run(self, conn, job):
        raise TimeoutError('provider slow')

    def enqueue(self, kind='probe', ref='r1', key='k1', user='u1'):
        with jobs.auth_sessions.transaction(self.conn):
            return jobs.enqueue(self.conn, kind, user, ref, key)

    def row(self, job_id):
        return db.fetch_one(self.conn, 'ProviderJob', id=job_id)

    def test_enqueue_is_idempotent(self):
        first = self.enqueue(); second = self.enqueue(ref='other')
        self.assertEqual(first, second)
        self.assertEqual(len(db.fetch_all(self.conn, 'ProviderJob')), 1)
        with self.assertRaises(ValueError):
            self.enqueue(kind='unknown', key='k2')

    def test_success_runs_once(self):
        job_id = self.enqueue()
        self.assertTrue(jobs.work_one(self.conn))
        self.assertFalse(jobs.work_one(self.conn))          # nothing left
        self.assertEqual(self.ran, ['r1'])
        self.assertEqual((self.row(job_id)['state'], self.row(job_id)['attempts']), ('succeeded', 1))

    def test_failure_retries_with_backoff_then_dead_letters(self):
        job_id = self.enqueue(kind='flaky', ref='f1', key='kf')
        t0 = int(time.time()) + 10
        with mock.patch.object(jobs, 'now', return_value=t0):
            self.assertTrue(jobs.work_one(self.conn))
        row = self.row(job_id)
        self.assertEqual((row['state'], row['attempts'], row['run_after'], row['last_error']), ('queued', 1, t0 + 5, 'TimeoutError'))
        with mock.patch.object(jobs, 'now', return_value=t0 + 1):
            self.assertFalse(jobs.work_one(self.conn))      # not due yet (backoff)
        with mock.patch.object(jobs, 'now', return_value=t0 + 5):
            self.assertTrue(jobs.work_one(self.conn))
        self.assertEqual(self.row(job_id)['state'], 'dead')
        self.assertEqual(self.dead, ['f1'])
        self.assertEqual([jobs.backoff(n) for n in (1, 2, 3, 9)], [5, 10, 20, 300])

    def test_expired_lease_requeues_then_dead_letters(self):
        job_id = self.enqueue()
        t0 = int(time.time()) + 10
        with mock.patch.object(jobs, 'now', return_value=t0):
            job = jobs.claim(self.conn)                    # worker "dies" holding it
        self.assertEqual(job['id'], job_id)
        with mock.patch.object(jobs, 'now', return_value=t0 + 31):
            self.assertIsNone(jobs.claim(self.conn))        # requeued with backoff
        self.assertEqual(self.row(job_id)['state'], 'queued')
        self.conn.execute('UPDATE "ProviderJob" SET attempts = max_attempts, state = ?, lease_until = ? WHERE id = ?', ('running', t0, job_id))
        self.conn.commit()
        with mock.patch.object(jobs, 'now', return_value=t0 + 100):
            jobs.claim(self.conn)
        self.assertEqual(self.row(job_id)['state'], 'dead')
        self.assertEqual(self.dead, ['r1'])

    def test_status_is_owner_only_and_exposes_no_reference(self):
        job_id = self.enqueue(ref='secret-session-id')
        view = jobs.status(self.conn, job_id, 'u1')
        self.assertEqual(set(view), {'id', 'kind', 'state', 'done', 'attempts'})
        self.assertNotIn('secret-session-id', str(view))
        self.assertIsNone(jobs.status(self.conn, job_id, 'u2'))
        self.assertIsNone(jobs.status(self.conn, 'x' * 100, 'u1'))


class JobRouteTests(unittest.TestCase):
    def test_route_is_owner_only(self):
        from test_segment_efg_routes import RouteTestCase
        case = RouteTestCase('run'); case.setUp(); self.addCleanup(case.doCleanups); self.addCleanup(case._stop)
        case.make_user('owner'); case.make_user('other')
        handlers = dict(jobs.HANDLERS); self.addCleanup(lambda: (jobs.HANDLERS.clear(), jobs.HANDLERS.update(handlers)))
        jobs.register_kind('probe', lambda conn, job: None)
        with jobs.auth_sessions.transaction(case.conn):
            job_id = jobs.enqueue(case.conn, 'probe', 'owner', 'ref', 'route-key')
        self.assertEqual(case.client.post('/login/owner').status_code, 302)
        response = case.client.get('/api/v1/jobs/' + job_id)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data']['state'], 'queued')
        case.client.post('/logout'); case.client.post('/login/other')
        self.assertEqual(case.client.get('/api/v1/jobs/' + job_id).status_code, 404)


class AsyncDigiLockerTests(unittest.TestCase):
    """The member's request returns at once; the worker makes the provider call.
    Reuses the DigiLocker test fixture without re-running its (synchronous) tests."""
    def setUp(self):
        self.fixture = DigiLockerSignupTests('test_full_flow_idempotent_and_minimal_encrypted_identity')
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.conn, self.body = self.fixture.conn, self.fixture.body
        p = mock.patch.dict(os.environ, {'DHASHU_ASYNC_DIGILOCKER': '1'}); p.start(); self.addCleanup(p.stop)
        import digilocker_signup
        self.service = digilocker_signup

    def slow_provider(self, delay=1.5):
        import io, json
        calls, timeouts = [], []

        def opener(*args, **kwargs):
            class Opener:
                def open(inner, request, timeout=None):
                    calls.append(1); timeouts.append(timeout); time.sleep(delay)
                    response = io.BytesIO(json.dumps({'result': {'requestId': 'request_12345678',
                        'url': 'https://api.digitallocker.gov.in/public/oauth2/1/authorize?state=request_12345678'}}).encode())
                    response.code = 200
                    return response
            return Opener()
        patcher = mock.patch('urllib.request.build_opener', side_effect=opener); patcher.start(); self.addCleanup(patcher.stop)
        return calls, timeouts

    def test_request_returns_immediately_and_worker_creates_the_link(self):
        calls, timeouts = self.slow_provider()
        start = time.monotonic()
        self.service.create(self.conn, 'u1', self.body)
        self.assertLess(time.monotonic() - start, 0.5)        # no provider wait in the request
        self.assertEqual(calls, [])
        self.assertEqual(self.service.view(self.conn, 'u1')['session']['state'], 'creating')
        self.service.create(self.conn, 'u1', self.body)        # retried request: still one job
        self.assertEqual(len(db.fetch_all(self.conn, 'ProviderJob')), 1)
        self.assertTrue(jobs.work_one(self.conn))
        self.assertEqual((calls, timeouts), ([1], [10]))       # one call, 10 s provider timeout
        self.assertEqual(self.service.view(self.conn, 'u1')['session']['state'], 'awaiting_consent')
        self.assertFalse(jobs.work_one(self.conn))              # never replayed
        self.assertEqual(calls, [1])

    def test_worker_death_mid_call_leaves_a_clear_state_and_no_replay(self):
        calls, _ = self.slow_provider(delay=0)
        self.service.create(self.conn, 'u1', self.body)
        t0 = int(time.time())
        with mock.patch.object(jobs, 'now', return_value=t0):
            job = jobs.claim(self.conn)                         # worker dies before running it
        self.assertIsNotNone(job)
        with mock.patch.object(jobs, 'now', return_value=t0 + 61):
            self.assertFalse(jobs.work_one(self.conn))          # lease expired: max_attempts=1 => dead
        self.assertEqual(calls, [])
        self.assertEqual(self.service.view(self.conn, 'u1')['session']['state'], 'outcome_unknown')

    def test_default_stays_synchronous(self):
        os.environ['DHASHU_ASYNC_DIGILOCKER'] = '0'
        calls, timeouts = self.slow_provider(delay=0)
        self.service.create(self.conn, 'u1', self.body)
        self.assertEqual((calls, timeouts), ([1], [20]))       # unchanged in-request behaviour
        self.assertEqual(db.fetch_all(self.conn, 'ProviderJob'), [])


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class PostgresJobClaimTests(unittest.TestCase):
    connect = pg.PostgresAuthenticationTests.connect
    cleanup = pg.PostgresAuthenticationTests.cleanup

    def setUp(self):
        pg.PostgresAuthenticationTests.setUp(self)
        handlers = dict(jobs.HANDLERS); self.addCleanup(lambda: (jobs.HANDLERS.clear(), jobs.HANDLERS.update(handlers)))
        jobs.register_kind('probe', lambda conn, job: None, lease=30)
        with jobs.auth_sessions.transaction(self.conn):
            pass
        for i in range(10):
            conn = self.connect()
            try:
                with jobs.auth_sessions.transaction(conn):
                    jobs.enqueue(conn, 'probe', 'owner', f'r{i}', f'key-{i}')
            finally:
                conn.close()

    def test_two_workers_never_claim_the_same_job(self):
        claimed, lock = [], threading.Lock()

        def worker():
            conn = self.connect()
            try:
                while True:
                    job = jobs.claim(conn, ['probe'])
                    if not job:
                        return
                    with lock:
                        claimed.append(job['id'])
            finally:
                conn.close()
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=20)
        self.assertEqual(len(claimed), 10)
        self.assertEqual(len(set(claimed)), 10)


if __name__ == '__main__':
    unittest.main()
