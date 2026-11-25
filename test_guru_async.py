"""perf-worker: the Guru AI reply on provider_jobs (DHASHU_ASYNC_GURU=1)."""
import json
import os
import unittest
from unittest import mock

import db
import guru_navigator as guru
import provider_jobs
import resilience
import test_guru_navigator

ON = {'DHASHU_ASYNC_GURU': '1'}


class GuruAsyncTests(unittest.TestCase):
    def setUp(self):
        self.f = test_guru_navigator.GuruNavigatorTests('test_mixed_intentions_shared_discussion_does_not_accept_date')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        for p in (mock.patch.dict(os.environ, ON), mock.patch('guru_provider.available', return_value=True)):
            p.start(); self.addCleanup(p.stop)
        self.topic = self.f.topic()
        self.f.req('private', {'action': 'ai_setting', 'enabled': True})

    def send(self, text='A question', rid='r1'):
        return self.f.req('private', {'action': 'message', 'topic': self.topic, 'text': text, 'request_id': rid})

    def jobs(self):
        return db.fetch_all(self.f.conn, 'ProviderJob', kind=guru.JOB_KIND)

    def work(self):
        while provider_jobs.work_one(self.f.conn, [guru.JOB_KIND]):
            pass

    def test_reply_is_enqueued_answered_by_the_worker_and_polled_by_the_owner(self):
        with mock.patch('guru_provider.reply', return_value='An AI answer') as reply:
            r = self.send()
            self.assertEqual(r.status_code, 200, r.json)
            reply.assert_not_called()                                    # the request never waits on OpenAI
            job_id = r.json['data']['pending_job']['job_id']
            self.assertEqual(r.json['data']['history'], [])
            self.assertFalse(self.f.request('/jobs/' + job_id).json['data']['done'])
            self.assertEqual(self.f.request('/jobs/' + job_id, uid='partner').status_code, 404)   # owner only
            self.work()
            reply.assert_called_once()
        status = self.f.request('/jobs/' + job_id).json['data']
        self.assertEqual((status['state'], status['done']), ('succeeded', True))
        state = self.f.req('state').json['data']
        self.assertIsNone(state['pending_job'])
        self.assertEqual([(h['role'], h['text'], h.get('mode')) for h in state['history']],
                         [('user', 'A question', None), ('guru', 'An AI answer', 'ai')])

    def test_job_rows_hold_no_personal_data(self):
        with mock.patch('guru_provider.reply', return_value='x'):
            self.send(text='My private worry about money')
        row = self.jobs()[0]
        blob = json.dumps(row, default=str)
        self.assertNotIn('private worry', blob)
        self.assertNotIn(self.topic, blob.replace(guru.JOB_KIND, ''))
        self.assertRegex(row['ref'], r'^[0-9a-f]{32}$')                 # an opaque token only

    def test_idempotent_send_and_job(self):
        with mock.patch('guru_provider.reply', return_value='Once') as reply:
            self.send(rid='same')
            self.assertEqual(self.send(rid='same').status_code, 200)      # same request id: no second job
            self.assertEqual(len(self.jobs()), 1)
            self.work()
            job = dict(self.jobs()[0]); job['state'] = 'running'
            guru._job_run(self.f.conn, job)                               # a duplicate delivery changes nothing
            self.assertEqual(reply.call_count, 1)
        self.assertEqual(len(self.f.req('state').json['data']['history']), 2)

    def test_provider_failure_or_open_breaker_falls_back_to_guided(self):
        with mock.patch('guru_provider.reply', return_value=None):       # refusal / breaker open -> None
            self.send()
            self.work()
        last = self.f.req('state').json['data']['history'][-1]
        self.assertEqual(last['mode'], 'guided')
        self.assertTrue(last['text'])

    def test_worker_uses_the_openai_circuit_breaker(self):
        os.environ['DHASHU_GURU_MODEL'] = 'test-model'; os.environ['OPENAI_API_KEY'] = 'sk-test'
        self.addCleanup(os.environ.pop, 'DHASHU_GURU_MODEL', None); self.addCleanup(os.environ.pop, 'OPENAI_API_KEY', None)
        calls = []
        def fake_call(name, fn, *args, **kw):
            calls.append(name)
            raise resilience.CircuitOpen(name)
        with mock.patch('guru_provider.resilience.call', side_effect=fake_call):
            self.send()
            self.work()
        self.assertEqual(calls, ['openai'])
        self.assertEqual(self.f.req('state').json['data']['history'][-1]['mode'], 'guided')

    def test_app_timeout_settles_in_guided_mode_and_the_late_job_is_a_no_op(self):
        with mock.patch('guru_provider.reply', return_value='Late AI answer') as reply:
            self.send()
            r = self.f.req('private', {'action': 'settle_pending'})
            self.assertEqual(r.status_code, 200)
            self.assertIsNone(r.json['data']['pending_job'])
            self.assertEqual(r.json['data']['history'][-1]['mode'], 'guided')
            self.work()                                                   # the job runs late
            reply.assert_not_called()
        self.assertEqual(len(self.f.req('state').json['data']['history']), 2)

    def test_dead_job_answers_in_guided_mode(self):
        with mock.patch('guru_provider.reply', side_effect=RuntimeError('boom')):
            self.send()
            for _ in range(3):
                provider_jobs.work_one(self.f.conn, [guru.JOB_KIND])
                self.f.conn.execute('UPDATE "ProviderJob" SET run_after = 0'); self.f.conn.commit()
        self.assertEqual(self.jobs()[0]['state'], 'dead')
        self.assertEqual(self.f.req('state').json['data']['history'][-1]['mode'], 'guided')

    def test_privacy_change_while_waiting_drops_the_answer(self):
        with mock.patch('guru_provider.reply', return_value='Should not be stored'):
            self.send()
            self.f.req('private', {'action': 'clear_history'})            # edits invalidate the in-flight answer
            self.work()
        self.assertEqual(self.f.req('state').json['data']['history'], [])

    def test_off_by_default_keeps_the_inline_path(self):
        with mock.patch.dict(os.environ, {'DHASHU_ASYNC_GURU': '0'}), mock.patch('guru_provider.reply', return_value='Inline') as reply:
            r = self.send()
        reply.assert_called_once()
        self.assertEqual(r.json['data']['history'][-1]['text'], 'Inline')
        self.assertIsNone(r.json['data']['pending_job'])
        self.assertEqual(self.jobs(), [])


if __name__ == '__main__':
    unittest.main()
