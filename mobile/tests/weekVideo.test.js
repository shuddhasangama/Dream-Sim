// round4-fixes-spec.md §7 — the explainer player: never autoplays, source is configurable.
import test from 'node:test';
import assert from 'node:assert/strict';
import { videoPlayerHtml } from '../src/screens/week.js';
import { CALENDAR_VIDEO } from '../src/config.js';

const safe = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

test('the player has controls, does not autoplay, and only preloads metadata', () => {
  const html = videoPlayerHtml({ src: '/media/x.mp4', poster: '' }, safe);
  assert.match(html, /<video[^>]*\bcontrols\b/);
  assert.match(html, /preload="metadata"/);
  assert.match(html, /\bplaysinline\b/);
  assert.doesNotMatch(html, /autoplay/i);
  assert.doesNotMatch(html, /\bloop\b/);
  assert.doesNotMatch(html, /poster=/);
});
test('the source and poster come from config, and are escaped', () => {
  const html = videoPlayerHtml({ src: '/v/"><script>.mp4', poster: '/p.jpg' }, safe);
  assert.match(html, /poster="\/p\.jpg"/);
  assert.doesNotMatch(html, /<script>/);
  assert.equal(typeof CALENDAR_VIDEO.src, 'string');
  assert.ok(CALENDAR_VIDEO.src.length > 0);
});
