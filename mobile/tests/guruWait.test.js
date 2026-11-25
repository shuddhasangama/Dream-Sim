import test from 'node:test';
import assert from 'node:assert/strict';
import {waitForReply} from '../src/guruWait.js';
import {renderNavigator} from '../src/screens/guruNavigator.js';

// perf-worker: "Guru is thinking…", poll the job, timeout -> guided answer.
function fakeSession(statuses) {
  const calls = [];
  return {calls, get: async (path) => {
    calls.push('GET ' + path);
    if (path.startsWith('/api/v1/jobs/')) { const s = statuses.shift(); if (s instanceof Error) throw s; return s; }
    return {history: ['done']};
  }, post: async (path, body) => { calls.push('POST ' + path + ' ' + body.action); return {history: ['guided']}; }};
}
const clock = () => { let t = 0; return {now: () => t, sleep: async (ms) => { t += ms; }}; };

test('polls the owner job until done, then reloads the conversation', async () => {
  const s = fakeSession([{done: false}, {done: false}, {done: true}]);
  const out = await waitForReply(s, {job_id: 'j1'}, {...clock(), intervalMs: 1000, timeoutMs: 10000});
  assert.deepEqual(out, {history: ['done']});
  assert.deepEqual(s.calls, ['GET /api/v1/jobs/j1', 'GET /api/v1/jobs/j1', 'GET /api/v1/jobs/j1', 'GET /api/v1/guru/state']);
});

test('timeout settles in guided mode', async () => {
  const s = fakeSession(Array(50).fill({done: false}));
  const out = await waitForReply(s, {job_id: 'j1'}, {...clock(), intervalMs: 1000, timeoutMs: 5000});
  assert.deepEqual(out, {history: ['guided']});
  assert.equal(s.calls.at(-1), 'POST /api/v1/guru/private settle_pending');
  assert.equal(s.calls.filter((c) => c.startsWith('GET /api/v1/jobs/')).length, 5);
});

test('an unreadable status also settles (never waits forever)', async () => {
  const s = fakeSession([new Error('offline')]);
  const out = await waitForReply(s, {job_id: 'j/../x'}, {...clock()});
  assert.deepEqual(out, {history: ['guided']});
  assert.equal(s.calls[0], 'GET /api/v1/jobs/j%2F..%2Fx');           // the id is always URL-encoded
});

test('"Guru is thinking…" shows only while a reply is pending', () => {
  const base = {enabled: true, mode: 'ai', topics: [], history: [], memories: [], remember: false, shared_topics: [], discussions: []};
  const safe = (v) => String(v ?? '');
  assert.match(renderNavigator({...base, pending_job: {job_id: 'j1', until: 1}}, safe), /Guru is thinking…/);
  assert.doesNotMatch(renderNavigator({...base, pending_job: null}, safe), /Guru is thinking/);
});
