import test from 'node:test';
import assert from 'node:assert/strict';
import { label } from '../src/screens/vision.js';

// element_key is a server-supplied raw string (children, cohabitation, ...) —
// label() only formats it for display, it never invents new keys.
test('vision label title-cases a raw element_key for display', () => {
  assert.equal(label('children'), 'Children');
  assert.equal(label('career'), 'Career');
});

test('vision label turns underscores into spaces', () => {
  assert.equal(label('household_and_shared_space'), 'Household and shared space');
});
