import test from 'node:test';
import assert from 'node:assert/strict';
import { createNav, visibleTabs, labelFor } from '../src/nav.js';

test('nav starts on dashboard and pushes/pops', () => {
  let renders = 0;
  const nav = createNav(() => { renders++; });
  assert.deepEqual(nav.current, { key: 'dashboard' });
  nav.push('week');
  assert.deepEqual(nav.current, { key: 'week' });
  assert.equal(renders, 1);
  nav.push('matches', { matchId: 'm1' });
  assert.deepEqual(nav.current, { key: 'matches', params: { matchId: 'm1' } });
  assert.equal(nav.pop(), true);
  assert.deepEqual(nav.current, { key: 'week' });
  assert.equal(nav.pop(), true);
  assert.deepEqual(nav.current, { key: 'dashboard' });
});

test('pop on the root screen returns false and does not render', () => {
  let renders = 0;
  const nav = createNav(() => { renders++; });
  assert.equal(nav.pop(), false);
  assert.equal(renders, 0);
  assert.deepEqual(nav.current, { key: 'dashboard' });
});

test('resetTo replaces the whole stack', () => {
  const nav = createNav(() => {});
  nav.push('week');
  nav.push('matches');
  nav.resetTo('dashboard');
  assert.equal(nav.depth, 1);
  assert.deepEqual(nav.current, { key: 'dashboard' });
});

// §2.1: "REACH sunsets at lock-in — hide the entry point when journey/status
// says locked in." Exercised here as what it actually is: the server marking
// the reach surface ineligible, nothing client-side to keep in sync.
test('REACH tab disappears once the server marks it ineligible (locked in)', () => {
  const dating = [
    { key: 'dashboard', eligible: true, blocked_reason: null, api_available: true, request: null },
    { key: 'reach', eligible: true, blocked_reason: null, api_available: true, request: null },
    { key: 'week', eligible: true, blocked_reason: null, api_available: true, request: null },
  ];
  assert.deepEqual(visibleTabs(dating).map((t) => t.key), ['dashboard', 'reach', 'week']);

  const lockedIn = [
    { key: 'dashboard', eligible: true, blocked_reason: null, api_available: true, request: null },
    { key: 'reach', eligible: false, blocked_reason: 'REACH is closed while you are locked in or past Dating.', api_available: true, request: null },
    { key: 'week', eligible: true, blocked_reason: null, api_available: true, request: null },
  ];
  assert.deepEqual(visibleTabs(lockedIn).map((t) => t.key), ['dashboard', 'week']);
});

test('an unrecognized surface key is never rendered as a tab', () => {
  const surfaces = [{ key: 'something_new', eligible: true, blocked_reason: null, api_available: true, request: null }];
  assert.deepEqual(visibleTabs(surfaces), []);
});

test('a surface absent from the response entirely is treated as not eligible', () => {
  assert.deepEqual(visibleTabs([]), []);
  assert.deepEqual(visibleTabs(undefined), []);
});

test('labelFor falls back to the raw key for anything unrecognized', () => {
  assert.equal(labelFor('week'), 'Week');
  assert.equal(labelFor('some_future_surface'), 'some_future_surface');
});
