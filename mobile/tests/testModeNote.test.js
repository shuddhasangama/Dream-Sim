// DHASHU_PAYMENT_BYPASS: Home shows "Test mode: payments off" only when the server says so.
import test from 'node:test';
import assert from 'node:assert/strict';
import { testModeNote } from '../src/screens/home.js';

test('the test-mode note shows only when the dashboard reports payment_bypass:true', () => {
  assert.match(testModeNote({ payment_bypass: true }), /Test mode: payments off/);
  assert.match(testModeNote({ payment_bypass: true }), /role="note"/);
  for (const journey of [{}, { payment_bypass: false }, { payment_bypass: 'true' }, null, undefined]) {
    assert.equal(testModeNote(journey), '');
  }
});
