import test from 'node:test';
import assert from 'node:assert/strict';
import {renderConfirm, renderScheduled, dueDate, confirm} from '../src/accountDeletion.js';

const safe = (v) => String(v ?? '').replaceAll('<', '&lt;');

test('confirm screen: password first, code on request, server grace days, errors escaped', () => {
  const html = renderConfirm({grace_days: 30}, safe);
  assert.match(html, /After 30 days everything is deleted/);
  assert.match(html, /id="delete-password-form"/);
  assert.match(html, /Use a code instead/);
  assert.match(renderConfirm({grace_days: 7, challenge_id: 'c1'}, safe), /id="delete-code-form"/);
  assert.match(renderConfirm({grace_days: 7, challenge_id: 'c1'}, safe), /After 7 days/);
  assert.match(renderConfirm({_error: '<b>no</b>'}, safe), /&lt;b>no/);
});

test('scheduled screen shows the date and only cancel / sign out', () => {
  const html = renderScheduled({due_at: Date.UTC(2026, 11, 25) / 1000}, safe);
  assert.match(html, /scheduled for deletion on <strong>25 December 2026<\/strong>/);
  assert.match(html, /id="delete-cancel"/);
  assert.match(html, /id="logout"/);
  assert.equal(dueDate(0), '1 January 1970');
});

test('confirmation is one request to the deletion endpoint', async () => {
  const calls = [];
  await confirm({post: async (p, b) => { calls.push([p, b]); return {}; }}, {password: 'x'});
  assert.deepEqual(calls, [['/api/v1/account/deletion', {password: 'x'}]]);
});
