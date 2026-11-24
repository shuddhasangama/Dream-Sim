import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, readdirSync, rmSync, statSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {Session} from '../src/session.js';
import {DEV_PATHS, PICKER_TITLE, enableHarnessSession, loadUsers, loginAs, pickerHtml} from '../src/devLogin.js';

const MOBILE = fileURLToPath(new URL('..', import.meta.url));
const read = path => readFileSync(join(MOBILE, path), 'utf8');
const ok = data => ({status: 200, data: {data, error: null}});
const tokens = n => ({access_token: 'access-' + n, refresh_token: 'refresh-' + n, token_type: 'Bearer', expires_in: 900, session_id: 'harness_' + n, user_id: 'u_0001'});
const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
function setup(handler) {
  const calls = []; let stored = null;
  const vault = {read: async () => stored, write: async v => { stored = v; }, clear: async () => { stored = null; }};
  return {session: new Session(async (...args) => { calls.push(args); return handler(...args); }, vault, () => 0), calls, vault};
}

// ── session paths ─────────────────────────────────────────────────────────
test('sessions use the real refresh/logout endpoints unless the emulator harness swaps them', () => {
  const {session} = setup(() => ok({}));
  assert.deepEqual(session.paths, {refresh: '/api/v1/auth/refresh', logout: '/api/v1/auth/logout'});
  enableHarnessSession(session);
  assert.deepEqual(session.paths, {refresh: DEV_PATHS.refresh, logout: DEV_PATHS.logout});
});

test('loginAs posts the user id, keeps only the refresh token, and the session then uses bearer + dev refresh/logout', async () => {
  let n = 0;
  const {session, calls, vault} = setup(path => {
    if (path === DEV_PATHS.loginAs || path === DEV_PATHS.refresh) return ok(tokens(++n));
    return ok({fine: true});
  });
  enableHarnessSession(session);
  await loginAs(session, 'u_0001');
  assert.deepEqual(calls[0].slice(0, 3), [DEV_PATHS.loginAs, 'POST', {user_id: 'u_0001'}]);
  assert.equal(calls[0][3], undefined); // no token sent to login-as
  assert.equal(await vault.read(), 'refresh-1');
  await session.get('/api/v1/journey/status');
  assert.equal(calls[1][3], 'access-1');
  // restore() after an app restart rotates through the harness refresh endpoint
  const restored = new Session(session.send, vault, () => 0);
  enableHarnessSession(restored);
  assert.equal(await restored.restore(), true);
  assert.deepEqual(calls.at(-1).slice(0, 3), [DEV_PATHS.refresh, 'POST', {refresh_token: 'refresh-1'}]);
  assert.equal(await restored.logout(), true);
  assert.deepEqual(calls.at(-1).slice(0, 2), [DEV_PATHS.logout, 'POST']);
  assert.equal(await vault.read(), null);
});

test('loginAs refuses malformed ids before any request and surfaces server errors', async () => {
  const {session, calls} = setup(() => ({status: 404, data: {data: null, error: {message: 'Not found.'}}}));
  for (const bad of ['', 'x'.repeat(65), 'u 1', '../u', null, 7]) await assert.rejects(loginAs(session, bad), /Choose a local user/);
  assert.equal(calls.length, 0);
  await assert.rejects(loginAs(session, 'u_9999'), /Not found/);
  assert.equal(session.tokens, null);
});

test('loadUsers keeps only well-formed rows', async () => {
  const {session} = setup(() => ok({users: [{user_id: 'u_0001', journey_state: 'dating'}, {user_id: 5}, null, {user_id: 'u_0002'}]}));
  assert.deepEqual(await loadUsers(session), [{user_id: 'u_0001', journey_state: 'dating'}, {user_id: 'u_0002', journey_state: ''}]);
});

test('the picker escapes user ids and shows loading, empty and error states', () => {
  const html = pickerHtml({users: [{user_id: '<img src=x onerror=1>', journey_state: 'dating'}], error: ''}, safe);
  assert.match(html, new RegExp(PICKER_TITLE));
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /data-dev-user="&lt;img src=x onerror=1&gt;"/);
  assert.match(pickerHtml({users: null, error: ''}, safe), /Loading local users/);
  assert.match(pickerHtml({users: [], error: ''}, safe), /No users in the local database/);
  assert.match(pickerHtml({users: null, error: '<b>down</b>'}, safe), /&lt;b&gt;down&lt;\/b&gt;[\s\S]*dev-login-retry/);
});

// ── only the emulator build can reach it ─────────────────────────────────
test('main.js reaches devLogin only behind the emulator mode check; no dev paths elsewhere in src', () => {
  const main = read('src/main.js');
  assert.match(main, /if\(import\.meta\.env\.MODE==='emulator'\)\{devLogin=await import\('\.\/devLogin\.js'\);/);
  assert.equal(main.match(/import\('\.\/devLogin\.js'\)/g).length, 1);
  assert.doesNotMatch(main, /^import .*devLogin/m); // never a static import
  for (const line of main.split('\n').filter(l => /devLogin\.|loadDevUsers\(\)|devPicker[,)]/.test(l) && !/^\s*\/\//.test(l))) {
    if (/^async function loadDevUsers|^\s*(try|catch)\{?devPicker|^\s*onPick|^\s*onRetry/.test(line)) continue; // inside guarded blocks
    assert.match(line, /import\.meta\.env\.MODE[!=]=='emulator'/, line.trim().slice(0, 120));
  }
  for (const file of readdirSync(join(MOBILE, 'src'), {recursive: true})) {
    const path = join('src', String(file));
    if (statSync(join(MOBILE, path)).isFile() && !path.endsWith('devLogin.js') && /\.(js|html|css)$/.test(path)) {
      assert.doesNotMatch(read(path), /\/api\/v1\/dev/, path);
    }
  }
});

async function buildBundle(mode) {
  const {build} = await import('vite');
  const outDir = mkdtempSync(join(tmpdir(), `dhashu-${mode}-`));
  const previous = process.env.VITE_API_BASE_URL;
  // An example origin, never the real server: this only produces local files.
  if (mode === 'production') process.env.VITE_API_BASE_URL = 'https://api.example.com';
  try {
    await build({root: MOBILE, configFile: join(MOBILE, 'vite.config.js'), mode, logLevel: 'silent',
      build: {outDir, emptyOutDir: true}});
  } finally {
    if (previous === undefined) delete process.env.VITE_API_BASE_URL; else process.env.VITE_API_BASE_URL = previous;
  }
  const files = readdirSync(outDir, {recursive: true}).map(String).filter(f => statSync(join(outDir, f)).isFile());
  const text = files.filter(f => /\.(js|html|css|json)$/.test(f)).map(f => readFileSync(join(outDir, f), 'utf8')).join('\n');
  rmSync(outDir, {recursive: true, force: true});
  return {files, text};
}

const DEV_MARKERS = ['/api/v1/dev', PICKER_TITLE, 'data-dev-user', 'dev-login', 'Emulator dev build'];

test('release bundle contains neither the dev endpoints nor the picker code', {timeout: 120000}, async () => {
  const release = await buildBundle('production');
  assert.equal(release.files.some(f => /devLogin/i.test(f)), false, release.files.join(', '));
  for (const marker of DEV_MARKERS) assert.equal(release.text.includes(marker), false, marker);
});

test('emulator bundle does contain them (control for the release check)', {timeout: 120000}, async () => {
  const emulator = await buildBundle('emulator');
  assert.equal(emulator.files.some(f => /devLogin/.test(f)), true, emulator.files.join(', '));
  for (const marker of DEV_MARKERS) assert.equal(emulator.text.includes(marker), true, marker);
});
