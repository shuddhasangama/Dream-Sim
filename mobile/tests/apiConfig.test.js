import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync, statSync} from 'node:fs';
import {join, relative, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  resolveApiConfig, buildApiOrigin, validateReleaseBaseUrl, validateDevBaseUrl,
  isPrivateHost, EMULATOR_DEFAULT, LOCAL_BACKEND, LOCAL_BACKEND_MODE, LOCAL_PROXY_PATHS,
} from '../src/apiConfig.js';
import {sameOriginTransport} from '../src/localTransport.js';
import {Session} from '../src/session.js';

const MOBILE = fileURLToPath(new URL('..', import.meta.url));
const REPO = join(MOBILE, '..');
// Assembled so this test file itself never contains the literal address.
const PROD_HOST = ['dream-sim-production', 'up', 'railway', 'app'].join('.');
const PROD = 'https://' + PROD_HOST;
const read = path => readFileSync(path, 'utf8');

// ── modes ────────────────────────────────────────────────────────────────
test('npm run dev (browser, development) defaults to the in-browser preview mock', () => {
  const cfg = resolveApiConfig({dev: true, native: false, mode: 'development', baseUrl: ''});
  assert.equal(cfg.kind, 'preview');
  assert.equal(cfg.baseUrl, '');
  assert.match(cfg.badge, /^PREVIEW\b/);
  assert.equal(cfg.release, false);
});

test('preview stays the default even if a base URL leaks into a browser dev build', () => {
  assert.equal(resolveApiConfig({dev: true, native: false, mode: 'development', baseUrl: PROD}).kind, 'preview');
});

test('npm run dev:local uses the same-origin proxy with a LOCAL badge', () => {
  const cfg = resolveApiConfig({dev: true, native: false, mode: LOCAL_BACKEND_MODE, baseUrl: ''});
  assert.deepEqual([cfg.kind, cfg.baseUrl, cfg.release], ['local-proxy', '', false]);
  assert.match(cfg.badge, /^LOCAL\b/);
  // Vite refuses a mode called "local" (it clashes with .env.*.local files).
  assert.notEqual(LOCAL_BACKEND_MODE, 'local');
  assert.match(readFileSync(new URL('../package.json', import.meta.url), 'utf8'), new RegExp(`"dev:local": "vite --host 127\\.0\\.0\\.1 --mode ${LOCAL_BACKEND_MODE}"`));
});

test('emulator build talks to 10.0.2.2:5000 by default with a LOCAL badge', () => {
  const cfg = resolveApiConfig({dev: false, native: true, mode: 'emulator', baseUrl: ''});
  assert.deepEqual([cfg.kind, cfg.baseUrl], ['remote', 'http://10.0.2.2:5000']);
  assert.equal(cfg.badge, 'LOCAL · 10.0.2.2:5000');
  assert.equal(EMULATOR_DEFAULT, 'http://10.0.2.2:5000');
});

test('release build uses exactly the configured https origin and shows no badge', () => {
  const cfg = resolveApiConfig({dev: false, native: true, mode: 'production', baseUrl: PROD});
  assert.deepEqual(cfg, {kind: 'remote', baseUrl: PROD, badge: null, release: true});
});

test('a release bundle opened in a plain browser is unsupported, never preview', () => {
  assert.equal(resolveApiConfig({dev: false, native: false, mode: 'production', baseUrl: PROD}).kind, 'unsupported');
});

test('every non-release mode shows a LOCAL or PREVIEW badge', () => {
  for (const input of [
    {dev: true, native: false, mode: 'development'}, {dev: true, native: false, mode: LOCAL_BACKEND_MODE},
    {dev: false, native: true, mode: 'emulator'}, {dev: true, native: true, mode: 'development'},
  ]) assert.match(resolveApiConfig({...input, baseUrl: ''}).badge, /^(LOCAL|PREVIEW)\b/, JSON.stringify(input));
});

test('dev native builds can never point at a real server', () => {
  assert.throws(() => resolveApiConfig({dev: false, native: true, mode: 'emulator', baseUrl: PROD}), /host must be one of/);
  assert.throws(() => validateDevBaseUrl('http://192.168.1.20:5000'), /host must be one of/);
  assert.equal(validateDevBaseUrl('http://localhost:5000/'), 'http://localhost:5000');
  assert.equal(validateDevBaseUrl('http://127.0.0.1:5000'), LOCAL_BACKEND);
});

// ── release guard ────────────────────────────────────────────────────────
test('release guard rejects missing, http, localhost, 10.0.2.2 and private addresses', () => {
  const rejected = {
    missing: [undefined, null, '', '   '],
    http: ['http://' + PROD_HOST, 'http://example.com', 'ftp://example.com'],
    local: ['https://localhost', 'https://localhost:5000', 'https://api.localhost', 'https://127.0.0.1', 'https://127.1.2.3',
      'https://[::1]', 'https://0.0.0.0', 'https://devbox', 'https://printer.local'],
    emulator: ['https://10.0.2.2', 'http://10.0.2.2:5000', 'https://10.0.2.2:5000'],
    private: ['https://10.1.2.3', 'https://172.16.0.1', 'https://172.31.255.255', 'https://192.168.1.5',
      'https://169.254.169.254', 'https://100.64.0.1', 'https://[fd00::1]', 'https://2130706433'],
    shape: [PROD + '/api', PROD + '?x=1', PROD + '#x', 'https://user:pw@' + PROD_HOST, 'not a url'],
  };
  for (const [group, values] of Object.entries(rejected)) {
    for (const value of values) assert.throws(() => validateReleaseBaseUrl(value), /Release build/, `${group}: ${value}`);
  }
});

test('release guard accepts a public https origin and normalises a trailing slash', () => {
  assert.equal(validateReleaseBaseUrl(PROD), PROD);
  assert.equal(validateReleaseBaseUrl(PROD + '/'), PROD);
  assert.equal(validateReleaseBaseUrl('https://api.example.com:8443'), 'https://api.example.com:8443');
  assert.equal(isPrivateHost('172.32.0.1'), false);
});

test('build time: production fails loudly without a safe URL; dev-only modes cannot be built', () => {
  assert.throws(() => buildApiOrigin({command: 'build', mode: 'production', baseUrl: undefined}), /VITE_API_BASE_URL is missing/);
  assert.throws(() => buildApiOrigin({command: 'build', mode: 'production', baseUrl: 'http://10.0.2.2:5000'}), /https/);
  assert.equal(buildApiOrigin({command: 'build', mode: 'production', baseUrl: PROD}), PROD);
  assert.equal(buildApiOrigin({command: 'build', mode: 'emulator', baseUrl: ''}), EMULATOR_DEFAULT);
  assert.throws(() => buildApiOrigin({command: 'build', mode: 'development'}), /dev server only/);
  assert.throws(() => buildApiOrigin({command: 'build', mode: LOCAL_BACKEND_MODE}), /dev server only/);
  assert.throws(() => buildApiOrigin({command: 'build', mode: 'staging', baseUrl: PROD}), /Unknown Vite mode/);
  assert.equal(buildApiOrigin({command: 'serve', mode: 'development'}), '');
  assert.equal(buildApiOrigin({command: 'serve', mode: LOCAL_BACKEND_MODE}), '');
});

// ── no hard-coded server address ─────────────────────────────────────────
const SKIP_DIRS = new Set(['node_modules', 'dist', '.gradle', 'build', 'test-results', 'playwright-report', 'artifacts', '.tools', '.git', 'ios']);
const SKIP_PATHS = [join('android', 'app', 'src', 'main', 'assets', 'public')]; // cap sync copy of dist (git-ignored)
const TEXT = /\.(js|mjs|cjs|ts|json|html|css|xml|gradle|properties|md|yaml|yml|txt|py|java|kt|plist|example)$/i;
function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const rel = relative(MOBILE, path);
    if (SKIP_PATHS.some(skip => rel === skip || rel.startsWith(skip + sep))) continue;
    if (statSync(path).isDirectory()) { if (!SKIP_DIRS.has(name)) yield* walk(path); }
    else if (TEXT.test(name) || name.startsWith('.env')) yield path;
  }
}

test('no mobile source file contains the production server address', () => {
  const offenders = [...walk(MOBILE)].filter(path => read(path).includes(PROD_HOST)).map(path => relative(MOBILE, path));
  assert.deepEqual(offenders, []);
});

test('the release config (codemagic.yaml) is the one place the production URL lives, in every workflow', () => {
  const yaml = read(join(REPO, 'codemagic.yaml'));
  const workflows = yaml.split(/\r?\n(?=  [a-z][\w-]*:\s*$)/m).filter(block => /^\s*name: DhaShu/m.test(block));
  assert.equal(workflows.length, 3);
  for (const block of workflows) {
    assert.match(block, new RegExp(`\\n        VITE_API_BASE_URL: "${PROD.replace(/\./g, '\\.')}"\\r?\\n`), block.split('\n')[0]);
  }
});

test('main.js takes its server only from apiConfig; index.html CSP uses the build placeholder', () => {
  const main = read(join(MOBILE, 'src', 'main.js'));
  assert.match(main, /const API = apiConfig\.baseUrl;/);
  assert.doesNotMatch(main, /https?:\/\/[a-z0-9.-]+\.(app|com|org|in|net)\b/i);
  const html = read(join(MOBILE, 'index.html'));
  assert.equal(html.split('__DHASHU_API_ORIGIN__').length - 1, 2);
  assert.doesNotMatch(html, /https?:\/\//);
  assert.match(read(join(MOBILE, 'vite.config.js')), /buildApiOrigin\(/);
});

test('main.js keeps previewTransport as the browser-dev default and the proxy opt-in', () => {
  const main = read(join(MOBILE, 'src', 'main.js'));
  assert.match(main, /const preview = apiConfig\.kind === 'preview';/);
  assert.match(main, /const transport = preview \? previewTransport\(\) : localProxy \? sameOriginTransport\(\) :/);
  assert.match(read(join(MOBILE, 'package.json')), /"dev": "vite --host 127\.0\.0\.1",/);
});

// ── local proxy transport + cookie session ───────────────────────────────
test('the local proxy covers the API and the backend sign-in pages only', () => {
  assert.deepEqual(LOCAL_PROXY_PATHS, ['/api', '/pool', '/login', '/logout', '/static']);
  assert.equal(LOCAL_BACKEND, 'http://127.0.0.1:5000');
});

test('sameOriginTransport sends relative, cookie-bearing requests and never an Authorization header', async () => {
  const calls = [];
  const send = sameOriginTransport(async (path, init) => { calls.push([path, init]); return {status: 200, json: async () => ({data: {ok: 1}, error: null})}; });
  const result = await send('/api/v1/me', 'POST', {a: 1}, 'access-token');
  assert.deepEqual(result, {status: 200, data: {data: {ok: 1}, error: null}});
  const [path, init] = calls[0];
  assert.equal(path, '/api/v1/me');
  assert.equal(init.credentials, 'same-origin');
  assert.equal(init.body, '{"a":1}');
  assert.equal('Authorization' in init.headers, false);
  for (const bad of ['//evil.example/x', PROD + '/api/v1/me', 'api/v1/me']) await assert.rejects(send(bad), /Same-origin/);
});

test('sameOriginTransport tolerates non-JSON bodies (e.g. a logout redirect)', async () => {
  const send = sameOriginTransport(async () => ({status: 0, json: async () => { throw new Error('opaque'); }}));
  assert.deepEqual(await send('/logout', 'POST'), {status: 0, data: null});
});

function cookieSession(handler) {
  const calls = []; let stored = null;
  const vault = {read: async () => stored, write: async v => { stored = v; }, clear: async () => { stored = null; }};
  const session = new Session(async (...args) => { calls.push(args); return handler(...args); }, vault, () => 0, {cookieAuth: true});
  return {session, calls, vault};
}
const ok = data => ({status: 200, data: {data, error: null}});

test('cookie session: restore asks /api/v1/me; 401 means signed out', async () => {
  const signedIn = cookieSession(() => ok({user_id: 'u_0001'}));
  assert.equal(await signedIn.session.restore(), true);
  assert.equal(signedIn.calls[0][0], '/api/v1/me');
  const signedOut = cookieSession(() => ({status: 401, data: {data: null, error: {message: 'Sign in'}}}));
  assert.equal(await signedOut.session.restore(), false);
});

test('cookie session: reads/writes carry no token and nothing is stored', async () => {
  const {session, calls, vault} = cookieSession(() => ok({fine: true}));
  assert.deepEqual(await session.get('/api/v1/journey/status'), {fine: true});
  await session.post('/api/v1/week/prepare', {});
  assert.equal(calls.every(call => call[3] === undefined), true);
  assert.equal(await vault.read(), null);
});

test('cookie session: logout uses the backend web logout', async () => {
  const {session, calls} = cookieSession(() => ({status: 302, data: null}));
  assert.equal(await session.logout(), true);
  assert.deepEqual(calls[0].slice(0, 2), ['/logout', 'POST']);
});

test('token sessions are unchanged by default (cookie mode is opt-in only)', async () => {
  const session = new Session(async () => ok({}), {read: async () => null, write: async () => {}, clear: async () => {}});
  assert.equal(session.cookieAuth, false);
  await assert.rejects(session.get('/api/v1/profile'), /Please sign in/);
  assert.equal(await session.restore(), false);
});

// ── Android: cleartext only in debug, only to this laptop ────────────────
test('release Android manifest stays https-only', () => {
  const manifest = read(join(MOBILE, 'android', 'app', 'src', 'main', 'AndroidManifest.xml'));
  assert.match(manifest, /android:usesCleartextTraffic="false"/);
  assert.doesNotMatch(manifest, /networkSecurityConfig/);
  for (const variant of ['release', 'main']) {
    assert.throws(() => statSync(join(MOBILE, 'android', 'app', 'src', variant, 'res', 'xml', 'network_security_config.xml')), /ENOENT/);
  }
});

test('debug-only network config permits cleartext solely to 10.0.2.2, localhost and 127.0.0.1', () => {
  const debug = join(MOBILE, 'android', 'app', 'src', 'debug');
  assert.match(read(join(debug, 'AndroidManifest.xml')), /android:networkSecurityConfig="@xml\/network_security_config"/);
  const nsc = read(join(debug, 'res', 'xml', 'network_security_config.xml'));
  assert.match(nsc, /<base-config cleartextTrafficPermitted="false"\s*\/>/);
  assert.equal(nsc.match(/cleartextTrafficPermitted="true"/g).length, 1);
  assert.deepEqual([...nsc.matchAll(/<domain includeSubdomains="false">([^<]+)<\/domain>/g)].map(m => m[1]).sort(), ['10.0.2.2', '127.0.0.1', 'localhost']);
  assert.doesNotMatch(nsc, /includeSubdomains="true"|<debug-overrides|trust-anchors/);
});
