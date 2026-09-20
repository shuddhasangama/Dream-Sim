// round4-fixes-spec.md §8 — week/prepare is automatic internal setup: run only
// when the server offers it, and a 409 is "already handled", never a retry.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ensurePrepared } from '../src/screens/week.js';

const fakeSession = (post) => ({ calls: [], async post(path, body) { this.calls.push(['POST', path, body]); return post(path, body); },
  async get(path) { this.calls.push(['GET', path]); return { prepared: true, from: 'get' }; } });

test('nothing to do when the server offers no prepare_request', async () => {
  const s = fakeSession(() => { throw new Error('must not post'); });
  const data = { prepared: true, prepare_request: null };
  assert.equal(await ensurePrepared(s, data), data);
  assert.deepEqual(s.calls, []);
});
test('posts exactly the server-provided request once and returns its result', async () => {
  const s = fakeSession(() => ({ prepared: true, from: 'post' }));
  const out = await ensurePrepared(s, { prepared: false, prepare_request: { method: 'POST', path: '/api/v1/week/prepare', body: {} } });
  assert.deepEqual(s.calls, [['POST', '/api/v1/week/prepare', {}]]);
  assert.equal(out.from, 'post');
});
test('a 409 is already-handled: re-read, do not retry the POST', async () => {
  const s = fakeSession(() => { throw Object.assign(new Error('conflict'), { status: 409 }); });
  const out = await ensurePrepared(s, { prepare_request: { path: '/api/v1/week/prepare', body: {} } });
  assert.equal(s.calls.filter((c) => c[0] === 'POST').length, 1);
  assert.deepEqual(s.calls[1], ['GET', '/api/v1/week']);
  assert.equal(out.from, 'get');
});
test('any other failure still surfaces', async () => {
  const s = fakeSession(() => { throw Object.assign(new Error('boom'), { status: 500 }); });
  await assert.rejects(() => ensurePrepared(s, { prepare_request: { path: '/x', body: {} } }), /boom/);
});
