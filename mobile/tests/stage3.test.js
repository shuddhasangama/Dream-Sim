import test from 'node:test';
import assert from 'node:assert/strict';
import { flagsValid } from '../src/screens/debrief.js';
import { legalAction } from '../src/screens/ceremony.js';

// §2.5: "Exactly two green flags and up to two red flags required before
// submitting."
test('flagsValid requires exactly two green flags', () => {
  assert.equal(flagsValid([], []), false);
  assert.equal(flagsValid(['a'], []), false);
  assert.equal(flagsValid(['a', 'b'], []), true);
  assert.equal(flagsValid(['a', 'b', 'c'], []), false);
});

test('flagsValid allows zero, one, or two red flags but never three', () => {
  assert.equal(flagsValid(['a', 'b'], []), true);
  assert.equal(flagsValid(['a', 'b'], ['x']), true);
  assert.equal(flagsValid(['a', 'b'], ['x', 'y']), true);
  assert.equal(flagsValid(['a', 'b'], ['x', 'y', 'z']), false);
});

// §2.4: "Ceremony is multi-step and order-enforced: playbook → sign → face."
// The client only ever offers the single action matching the server's
// current step.
test('ceremony legalAction matches the server-reported step, one at a time', () => {
  assert.equal(legalAction('playbook'), 'playbook');
  assert.equal(legalAction('sign'), 'sign');
  assert.equal(legalAction('face'), 'face');
});

test('ceremony legalAction is null once done — nothing left to advance', () => {
  assert.equal(legalAction('done'), null);
});

test('ceremony legalAction is null for an unrecognized step, never guesses', () => {
  assert.equal(legalAction('unknown_future_step'), null);
});
