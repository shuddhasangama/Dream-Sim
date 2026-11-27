// fix/avatar-signout: tapping the round avatar on Home must open the avatar
// screen and keep the member signed in. Runs the EMULATOR build (vite --mode
// emulator, the same bundle `npm run sync:emulator` ships) against the real
// local backend (tools/e2e_server.py, local harness), signed in through
// "Pick a local user". Capacitor's native bridge is replaced by a shim: its
// CapacitorHttp.request calls go through Node to the backend (no CORS, same
// headers the app sends on a device) and SessionVault keeps the refresh token
// in memory.
import {test, expect, request as playwrightRequest} from '@playwright/test';

const BACKEND = 'http://127.0.0.1:5000';
const EMULATOR_APP = 'http://127.0.0.1:5175';

async function nativeShim(page, calls) {
  const api = await playwrightRequest.newContext({baseURL: BACKEND});
  await page.exposeFunction('__nativeHttp', async ({url, method, data, headers}) => {
    const path = new URL(url).pathname;
    const r = await api.fetch(url, {method, headers, data: data === undefined ? undefined : data});
    calls.push({method, path, status: r.status(), bearer: String(headers?.Authorization || '').startsWith('Bearer ')});
    const text = await r.text();
    return {status: r.status(), headers: {}, url, data: text ? JSON.parse(text) : null};
  });
  await page.addInitScript(() => {
    let vault = null;
    window.Capacitor = {
      PluginHeaders: [
        {name: 'CapacitorHttp', methods: [{name: 'request', rtype: 'promise'}]},
        {name: 'SessionVault', methods: ['read', 'write', 'clear'].map(name => ({name, rtype: 'promise'}))},
      ],
      nativePromise: async (plugin, method, options) => {
        if (plugin === 'CapacitorHttp' && method === 'request') return window.__nativeHttp(options);
        if (plugin === 'SessionVault') {
          if (method === 'read') return {value: vault};
          if (method === 'write') { vault = options.value; return {}; }
          if (method === 'clear') { vault = null; return {}; }
        }
        throw new Error(`shim: ${plugin}.${method} not available`);
      },
      nativeCallback: () => { throw new Error('shim: callbacks not available'); },
    };
    window.CapacitorCustomPlatform = {name: 'android', plugins: {}};
  });
  return api;
}

async function pickLocalUser(page, userId) {
  await page.goto(EMULATOR_APP + '/');
  await expect(page.getByText('Pick a local user')).toBeVisible();
  await expect(page.getByText('LOCAL · 127.0.0.1:5000')).toBeVisible();
  await page.locator(`[data-dev-user="${userId}"]`).click();
  await expect(page.locator('#p-avatar')).toBeVisible();
}

test('emulator build: tapping the Home avatar opens the avatar screen and keeps the member signed in', async ({page}) => {
  const calls = [];
  const api = await nativeShim(page, calls);
  await pickLocalUser(page, 'test_owner');
  const loginsBefore = calls.filter(c => c.path === '/api/v1/dev/login-as').length;
  expect(loginsBefore).toBe(1);

  await page.locator('#p-avatar').click();
  await expect(page.locator('.avatar-flow')).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Your avatar'})).toBeVisible();
  // Still signed in: no picker, no session-ended message, no new dev login.
  await expect(page.getByText('Pick a local user')).toHaveCount(0);
  await expect(page.getByText('Please sign in')).toHaveCount(0);
  const avatarCalls = calls.filter(c => ['/api/v1/profile/avatar', '/api/v1/profile/liveness'].includes(c.path));
  expect(avatarCalls.map(c => `${c.path} ${c.status}`)).toEqual(expect.arrayContaining(
    ['/api/v1/profile/avatar 200', '/api/v1/profile/liveness 200']));
  expect(avatarCalls.every(c => c.bearer)).toBe(true);
  expect(calls.filter(c => c.status === 401)).toEqual([]);
  expect(calls.filter(c => c.path === '/api/v1/dev/login-as').length).toBe(loginsBefore);

  // Back to Home: still the same member, data still loads.
  await page.locator('.p-tabbar [data-nav="dashboard"]').click();
  await expect(page.locator('#p-avatar')).toBeVisible();
  await api.dispose();
});

test('emulator build: Sign out signs out only when chosen', async ({page}) => {
  const calls = [];
  const api = await nativeShim(page, calls);
  await pickLocalUser(page, 'test_partner');
  await page.locator('#p-avatar').click();
  await expect(page.locator('.avatar-flow')).toBeVisible();
  await page.locator('.p-tabbar [data-nav="dashboard"]').click();
  await expect(page.locator('#p-avatar')).toBeVisible();
  await expect(page.getByText('Pick a local user')).toHaveCount(0);

  await page.locator('#profile-settings').click();
  await page.locator('#logout').click();
  await expect(page.getByText('You have signed out.')).toBeVisible();
  await expect(page.getByText('Pick a local user')).toBeVisible();
  expect(calls.some(c => c.path === '/api/v1/dev/logout' && c.status === 200)).toBe(true);
  await api.dispose();
});

test('backend: avatar and liveness answer 200 for a valid harness session and 401 without one', async () => {
  const api = await playwrightRequest.newContext({baseURL: BACKEND});
  const login = await api.post('/api/v1/dev/login-as', {data: {user_id: 'test_stranger'}});
  expect(login.status()).toBe(200);
  const {access_token} = (await login.json()).data;
  for (const path of ['/api/v1/profile/avatar', '/api/v1/profile/liveness']) {
    const ok = await api.get(path, {headers: {Authorization: 'Bearer ' + access_token}});
    expect(ok.status(), `${path}: ${await ok.text()}`).toBe(200);
    const none = await api.get(path);
    expect(none.status(), path).toBe(401);
    const bogus = await api.get(path, {headers: {Authorization: 'Bearer ' + 'x'.repeat(43)}});
    expect(bogus.status(), path).toBe(401);
  }
  // A revoked session is refused on these routes too.
  const logout = await api.post('/api/v1/dev/logout', {headers: {Authorization: 'Bearer ' + access_token}});
  expect(logout.status()).toBe(200);
  for (const path of ['/api/v1/profile/avatar', '/api/v1/profile/liveness']) {
    const revoked = await api.get(path, {headers: {Authorization: 'Bearer ' + access_token}});
    expect(revoked.status(), path).toBe(401);
  }
  await api.dispose();
});

test('local browser build: a side panel refusing the session shows it unavailable and keeps the member signed in', async ({page}) => {
  // npm run dev:local signs in with the backend's own cookie session, which the
  // app-only avatar routes refuse (code app_session_required). Not a refused session.
  const refusals = [];
  page.on('response', r => { if (r.url().includes('/api/v1/profile/avatar') || r.url().includes('/api/v1/profile/liveness')) refusals.push(r.status()); });
  await page.request.post('/login/test_owner');
  await page.goto('/');
  await expect(page.locator('#p-avatar')).toBeVisible();
  await page.locator('#p-avatar').click();
  await expect(page.locator('.avatar-flow')).toBeVisible();
  await expect(page.locator('.avatar-flow [role="status"]').first()).toHaveText('Sign in through the app.');
  expect(refusals).toContain(401);
  await expect(page.getByText('Your session ended')).toHaveCount(0);
  await page.locator('.p-tabbar [data-nav="dashboard"]').click();
  await expect(page.locator('#p-avatar')).toBeVisible();          // still signed in
});
