import test from 'node:test';
import assert from 'node:assert/strict';
import {Session} from '../src/session.js';
import {createResumeGuard} from '../src/resume.js';

// feat-resume: the session is checked before any private screen is shown again.
const token = n => ({access_token: 'access-' + n, refresh_token: 'refresh-' + n, expires_in: 900});
const ok = data => ({status: 200, data: {data, error: null}});
function setup(send, now) {
  let value = null;
  const vault = {read: async () => value, write: async v => { value = v; }, clear: async () => { value = null; }};
  return {session: new Session(send, vault, now), vault};
}

test('resume with a fresh access token does not touch the network', async () => {
  let calls = 0; let time = 0;
  const {session} = setup(async () => { calls++; return ok({}); }, () => time);
  await session.accept(token(1), 0); time = 60_000;
  assert.equal(await session.resume(), true);
  assert.equal(calls, 0);
});

test('resume with an access token that expired while away refreshes first', async () => {
  const paths = []; let time = 0;
  const {session, vault} = setup(async path => { paths.push(path); return ok(token(2)); }, () => time);
  await session.accept(token(1), 0); time = 2 * 3600_000;            // two hours in the background
  assert.equal(await session.resume(), true);
  assert.deepEqual(paths, ['/api/v1/auth/refresh']);
  assert.equal(session.tokens.access_token, 'access-2');
  assert.equal(await vault.read(), 'refresh-2');
});

test('resume when the refresh is refused (revoked, locked, expired) signs out', async () => {
  let time = 0;
  const {session, vault} = setup(async () => ({status: 401, data: {error: {message: 'Revoked'}}}), () => time);
  await session.accept(token(1), 0); time = 2 * 3600_000;
  assert.equal(await session.resume(), false);
  assert.equal(session.tokens, null);
  assert.equal(await vault.read(), null);
});

test('resume without a session is simply signed out', async () => {
  const {session} = setup(async () => ok({}), () => 0);
  assert.equal(await session.resume(), false);
});

function guard({resume, signedIn = true}) {
  const log = [];
  let covered = false;
  const g = createResumeGuard({
    session: {resume: async () => { log.push('check'); return resume(); }},
    isSignedIn: () => signedIn,
    setCovered: v => { covered = v; log.push(v ? 'cover' : 'uncover'); },
    onResumed: async () => { log.push('reload:' + (covered ? 'covered' : 'VISIBLE')); },
    onSignedOut: async () => { log.push('signin:' + (covered ? 'covered' : 'VISIBLE')); },
  });
  return {g, log, covered: () => covered};
}

test('guard: background covers; return checks, then reloads while still covered, then shows', async () => {
  const {g, log, covered} = guard({resume: async () => true});
  assert.equal(await g.handle(false), 'covered');
  assert.equal(await g.handle(true), 'resumed');
  assert.deepEqual(log, ['cover', 'cover', 'check', 'reload:covered', 'uncover']);
  assert.equal(covered(), false);
});

test('guard: an expired session goes to sign-in and the private screen is never re-shown', async () => {
  const {g, log} = guard({resume: async () => false});
  await g.handle(false);
  assert.equal(await g.handle(true), 'expired');
  assert.deepEqual(log, ['cover', 'cover', 'check', 'signin:covered', 'uncover']);
  assert.ok(!log.some(e => e.startsWith('reload')));
});

test('guard: a check that throws (offline) is treated as signed out, never as signed in', async () => {
  const {g, log} = guard({resume: async () => { throw new Error('offline'); }});
  assert.equal(await g.handle(true), 'expired');
  assert.ok(log.includes('signin:covered'));
});

test('guard: rapid flips run one check at a time', async () => {
  let inFlight = 0; let max = 0;
  const {g} = guard({resume: async () => { inFlight++; max = Math.max(max, inFlight); await new Promise(r => setTimeout(r, 5)); inFlight--; return true; }});
  await Promise.all([g.handle(true), g.handle(false), g.handle(true), g.handle(true)]);
  assert.equal(max, 1);
});

test('guard: signed-out screens are not covered or checked', async () => {
  const {g, log} = guard({resume: async () => true, signedIn: false});
  assert.equal(await g.handle(false), 'covered');
  assert.equal(await g.handle(true), 'signed-out');
  assert.deepEqual(log, ['uncover']);
});
