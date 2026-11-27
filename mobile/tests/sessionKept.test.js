// fix/avatar-signout: a 401 from one side panel must not sign the member out
// unless the session itself is refused. The backend says which: code
// 'authentication_required' = the session is refused (sign in again);
// 'app_session_required' = the API still accepts the session, one route needs
// the app's own sign-in (auth.py APP_SESSION_REQUIRED).
import test from 'node:test';
import assert from 'node:assert/strict';
import {Session, classify, APP_SESSION_REQUIRED} from '../src/session.js';
import {createResumeGuard} from '../src/resume.js';
import {resolveApiConfig} from '../src/apiConfig.js';
import {load as loadAvatar} from '../src/screens/avatar.js';

const token = n => ({access_token: 'access-' + n, refresh_token: 'refresh-' + n, expires_in: 900});
const ok = data => ({status: 200, data: {data, error: null}});
const refused = (code, message = 'Sign in to continue.') => ({status: 401, data: {data: null, error: {code, message}}});
function setup(send, options) {
  let value = null;
  const vault = {read: async () => value, write: async v => { value = v; }, clear: async () => { value = null; }};
  return {session: new Session(send, vault, () => 0, options), vault};
}

test('a side panel refusing a still-accepted session keeps the member signed in', async () => {
  const calls = [];
  const {session, vault} = setup(async (path, method, body, access) => {
    calls.push(path);
    return path === '/api/v1/profile/avatar' ? refused(APP_SESSION_REQUIRED, 'Sign in through the app.') : ok({user_id: 'u_1'});
  });
  await session.accept(token(1), 0);
  const error = await session.get('/api/v1/profile/avatar').catch(e => e);
  assert.equal(error.status, 403);
  assert.equal(error.sessionKept, true);
  assert.equal(error.message, 'Sign in through the app.');
  assert.notEqual(classify(error).kind, 'auth');                 // main.js run() does not sign out
  assert.equal(session.tokens.access_token, 'access-1');          // tokens and vault untouched
  assert.equal(await vault.read(), 'refresh-1');
  assert.deepEqual(await session.get('/api/v1/profile'), {user_id: 'u_1'});
  assert.deepEqual(calls, ['/api/v1/profile/avatar', '/api/v1/profile']);   // no replay, no extra calls
});

test('local browser (cookie) mode: the same route refusal keeps the session', async () => {
  const {session} = setup(async path => path === '/api/v1/profile/liveness' ? refused(APP_SESSION_REQUIRED) : ok({}), {cookieAuth: true});
  const error = await session.get('/api/v1/profile/liveness').catch(e => e);
  assert.equal(error.status, 403);
  assert.equal(classify(error).kind, 'error');
  const signedOut = await session.get('/api/v1/me').then(() => null);
  assert.equal(signedOut, null);
  const stillRefused = setup(async () => refused('authentication_required'), {cookieAuth: true}).session;
  assert.equal(classify(await stillRefused.get('/api/v1/profile').catch(e => e)).kind, 'auth');
});

for (const [why, response] of [
  ['refused session (no session / expired)', refused('authentication_required')],
  ['revoked session', refused('authentication_required', 'Sign in again.')],
  ['401 without a code (unknown) fails closed', {status: 401, data: {error: {message: 'Revoked'}}}],
]) {
  test(`release config: ${why} still signs out`, async () => {
    const config = resolveApiConfig({dev: false, native: true, mode: 'production', baseUrl: 'https://api.dhashu.example'});
    assert.equal(config.release, true);
    assert.equal(config.kind, 'remote');
    const {session, vault} = setup(async () => response, {cookieAuth: config.kind === 'local-proxy'});
    await session.accept(token(1), 0);
    const error = await session.get('/api/v1/profile/avatar').catch(e => e);
    assert.equal(error.status, 401);
    assert.equal(classify(error).kind, 'auth');                   // main.js run(): back to sign-in
    assert.equal(session.tokens, null);
    assert.equal(await vault.read(), null);
  });
}

test('release config: a locked account (refresh refused) on resume goes to sign-in', async () => {
  const {session} = setup(async path => path.endsWith('/refresh') ? refused('authentication_required', 'Account locked.') : ok({}));
  await session.accept({...token(1), expires_in: 1}, 0);         // expires inside the resume margin
  const events = [];
  const guard = createResumeGuard({session, isSignedIn: () => true, setCovered: v => events.push('cover:' + v),
    onResumed: async () => events.push('resumed'), onSignedOut: async () => events.push('signed-out')});
  assert.equal(await guard.handle(true), 'expired');
  assert.ok(events.includes('signed-out'));
  assert.ok(!events.includes('resumed'));
  assert.equal(session.tokens, null);
});

test('avatar screen: a kept-session refusal shows the panel as unavailable instead of signing out', async () => {
  const {session} = setup(async path => refused(APP_SESSION_REQUIRED, 'Sign in through the app.'));
  await session.accept(token(1), 0);
  const data = await loadAvatar(session);
  assert.equal(data.state, 'unavailable');
  assert.equal(data.enabled, false);
  assert.equal(data.message, 'Sign in through the app.');
  assert.equal(data._faceError, true);
  assert.equal(session.tokens.access_token, 'access-1');
});

test('avatar screen: a refused session still propagates the 401 (sign in again)', async () => {
  const {session} = setup(async () => refused('authentication_required'));
  await session.accept(token(1), 0);
  const error = await loadAvatar(session).catch(e => e);
  assert.equal(error.status, 401);
  assert.equal(session.tokens, null);
});

test('Sign out happens only when chosen: logout revokes, a kept refusal never does', async () => {
  const calls = [];
  const {session, vault} = setup(async (path, method, body, access) => {
    calls.push(path);
    if (path === '/api/v1/profile/avatar') return refused(APP_SESSION_REQUIRED);
    return ok({logged_out: true});
  });
  await session.accept(token(1), 0);
  await session.get('/api/v1/profile/avatar').catch(() => {});
  assert.ok(!calls.includes('/api/v1/auth/logout'));
  assert.equal(await vault.read(), 'refresh-1');
  assert.equal(await session.logout(), true);
  assert.equal(calls.at(-1), '/api/v1/auth/logout');
  assert.equal(session.tokens, null);
  assert.equal(await vault.read(), null);
});
