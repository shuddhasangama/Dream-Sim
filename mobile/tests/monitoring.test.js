import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, readdirSync, rmSync, statSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {mask, scrubEvent, startMonitoring} from '../src/monitoring.js';

const MOBILE = fileURLToPath(new URL('..', import.meta.url));

test('monitoring is off without a DSN', async () => {
  assert.equal(await startMonitoring({}), false);
});

test('events lose user, request data, tokens, emails and phone numbers', () => {
  const event = scrubEvent({
    user: {id: 'u_0001', email: 'a@b.com'},
    request: {url: 'https://api.example.com/api/v1/me?phone=%2B919876543210', headers: {Authorization: 'Bearer x'}, data: '{"p":1}'},
    message: 'failed for +91 98765 43210 owner@private.test',
    extra: {access_token: 'abc', note: 'mail owner@private.test'},
    breadcrumbs: [{message: 'tapped call 9876543210'}],
  });
  assert.equal(event.user, undefined);
  assert.deepEqual(event.request, {url: 'https://api.example.com/api/v1/me'});
  const text = JSON.stringify(event);
  for (const leak of ['9876543210', '98765', 'owner@private.test', 'a@b.com', 'Bearer', '"abc"']) assert.equal(text.includes(leak), false, leak);
  assert.equal(event.extra.access_token, '[filtered]');
  assert.equal(mask('x@y.io'), '[email]');
});

async function buildText(env) {
  const {build} = await import('vite');
  const outDir = mkdtempSync(join(tmpdir(), 'dhashu-mon-'));
  const saved = {...process.env};
  Object.assign(process.env, env);
  try {
    await build({root: MOBILE, configFile: join(MOBILE, 'vite.config.js'), mode: 'production', logLevel: 'silent', build: {outDir, emptyOutDir: true}});
  } finally {
    for (const key of Object.keys(env)) { if (key in saved) process.env[key] = saved[key]; else delete process.env[key]; }
  }
  const text = readdirSync(outDir, {recursive: true}).map(String).filter(f => statSync(join(outDir, f)).isFile() && f.endsWith('.js'))
    .map(f => readFileSync(join(outDir, f), 'utf8')).join('\n');
  rmSync(outDir, {recursive: true, force: true});
  return text;
}

test('release bundle without a DSN contains no Sentry code; with a DSN it does', {timeout: 120000}, async () => {
  const off = await buildText({VITE_API_BASE_URL: 'https://api.example.com'});
  assert.equal(/sentry/i.test(off), false);
  const on = await buildText({VITE_API_BASE_URL: 'https://api.example.com', VITE_SENTRY_DSN: 'https://public@o0.ingest.example.invalid/1'});
  assert.equal(/sentry/i.test(on), true);
});
