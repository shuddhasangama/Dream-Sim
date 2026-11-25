// dec-web (owner decision: keep the old web version). The real Flask web pages,
// served by tools/e2e_server.py: sign in, the main pages, sign out.
import {test, expect} from '@playwright/test';
const BACKEND = 'http://127.0.0.1:5000';
const PAGES = ['/dashboard', '/week', '/reach', '/vision', '/stats', '/chemistry', '/guru', '/journey', '/verify'];

test('web: sign in, every main page loads with the security headers, sign out', async ({page}) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(BACKEND + '/pool');                                   // local sign-in list (simulation build)
  await page.request.post(BACKEND + '/login/test_owner');
  for (const path of PAGES) {
    const response = await page.goto(BACKEND + path);
    expect(response.status(), path).toBeLessThan(400);
    const body = await page.locator('body').innerText();
    expect(body, path).not.toMatch(/Traceback|Something broke/);
    const headers = response.headers();
    expect(headers['x-frame-options'], path).toBe('DENY');
    expect(headers['x-content-type-options'], path).toBe('nosniff');
    expect(headers['content-security-policy-report-only'] || headers['content-security-policy'], path).toMatch(/'nonce-/);
  }
  expect(errors).toEqual([]);                                           // no script errors on any page
  await page.request.post(BACKEND + '/logout');
  const after = await page.goto(BACKEND + '/dashboard');
  expect(new URL(after.url()).pathname).not.toBe('/dashboard');           // signed out: no member page
});
