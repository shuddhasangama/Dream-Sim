import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, classify } from '../src/session.js';

// §3 of mobile-journey-build-spec.md: each status needs distinct, specific
// client behaviour. Tested here as pure data so nothing depends on a DOM.

test('401 classifies as auth, never a retry', () => {
  const c = classify(new ApiError('Your session could not be renewed. Please sign in again.', 401));
  assert.equal(c.kind, 'auth');
  assert.equal(c.retry, false);
  assert.match(c.message, /sign in again/);
});

test('409 classifies as conflict with fixed copy, not the server message, and never a retry', () => {
  const c = classify(new ApiError('duplicate submission', 409));
  assert.equal(c.kind, 'conflict');
  assert.equal(c.retry, false);
  assert.equal(c.message, 'This has already been handled.');
});

test('400 classifies as validation and surfaces the server message verbatim', () => {
  const c = classify(new ApiError('min must not exceed max.', 400));
  assert.equal(c.kind, 'validation');
  assert.equal(c.message, 'min must not exceed max.');
});

test('a network failure (status 0, session.js\'s own default) classifies as retryable', () => {
  const c = classify(new ApiError('Connection unavailable. Check your internet and try again.'));
  assert.equal(c.kind, 'network');
  assert.equal(c.retry, true);
});

test('an unmapped status still produces a usable message, never throws', () => {
  const c = classify(new ApiError('Request could not be completed.', 500));
  assert.equal(c.kind, 'error');
  assert.equal(c.message, 'Request could not be completed.');
});
