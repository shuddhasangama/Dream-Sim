// round4-fixes-spec.md §3 — the "you" marker is proportional along the track.
import test from 'node:test';
import assert from 'node:assert/strict';
import { trackPct } from '../src/screens/reach.js';

test('age marker on the 21–80 track: ends, middle, and 38 ≈ 28.8%', () => {
  assert.equal(trackPct(21, 80, 21), 0);
  assert.equal(trackPct(21, 80, 80), 100);
  assert.ok(Math.abs(trackPct(21, 80, 38) - 28.81) < 0.01);
  assert.ok(Math.abs(trackPct(21, 80, 60) - 66.10) < 0.01);
});
test('out-of-range and degenerate tracks are clamped, never off the track', () => {
  assert.equal(trackPct(21, 80, 10), 0);
  assert.equal(trackPct(21, 80, 99), 100);
  assert.equal(trackPct(5, 5, 5), 0);
});
