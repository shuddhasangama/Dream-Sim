// design_handoff_app_ui_pulse/README.md ("Pulse", option 1a) — Home's ring
// math and "Next up" derivation, pure enough to test without a DOM.
import test from 'node:test';
import assert from 'node:assert/strict';
import { ringGradient, visionProgress, statsProgress, chemistryProgress, nextUpcoming, nextUpCard } from '../src/screens/home.js';

test('ringGradient fills clockwise from 0deg, clamped, with a visible sliver at 0%', () => {
  assert.equal(ringGradient(0, '#fff', '#000'), 'conic-gradient(#fff 0deg 6deg, #000 6deg 360deg)');
  assert.equal(ringGradient(50, '#fff', '#000'), 'conic-gradient(#fff 0deg 180deg, #000 180deg 360deg)');
  assert.equal(ringGradient(100, '#fff', '#000'), 'conic-gradient(#fff 0deg 360deg, #000 360deg 360deg)');
  assert.equal(ringGradient(140, '#fff', '#000'), 'conic-gradient(#fff 0deg 360deg, #000 360deg 360deg)'); // clamped
});

test('visionProgress: Travel together needs only its bare presence; everything else needs a stance', () => {
  const data = { element_keys: ['Intimacy', 'Kids', 'Cohabitate', 'Travel together'],
    goals: [{ key: 'Intimacy', stance: ['Emotional'] }, { key: 'Travel together', stance: null }] };
  const p = visionProgress(data);
  assert.deepEqual(p, { answered: 2, total: 4, pct: 50 });
});
test('visionProgress: a pillar present but with no stance yet does not count as answered', () => {
  const data = { element_keys: ['Intimacy', 'Kids'], goals: [{ key: 'Kids', stance: null }] };
  assert.equal(visionProgress(data).answered, 0);
});
test('visionProgress falls back to the fixed 4-pillar shape before any GET has resolved', () => {
  assert.deepEqual(visionProgress(null), { answered: 0, total: 4, pct: 0 });
});

test('statsProgress counts the currently-verified subset of the verified group', () => {
  const rows = [
    { key: 'age', group: 'verified', check: 'verified' },
    { key: 'education', group: 'verified', check: 'in_review' },
    { key: 'nationality', group: 'verified', check: 'verified' },
    { key: 'profession', group: 'verified', check: 'verified' },
    { key: 'income_band', group: 'verified', check: 'verified' },
    { key: 'diet', group: 'declared', check: null },
  ];
  assert.deepEqual(statsProgress({ rows }), { answered: 4, total: 5, pct: 80 });
});
test('statsProgress never divides by zero before any GET has resolved', () => {
  assert.deepEqual(statsProgress(null), { answered: 0, total: 5, pct: 0 });
});

test('chemistryProgress counts activities with a bucket pick out of every activity offered', () => {
  const data = { activity_options: ['Cooking', 'Yoga', 'Tennis', 'Salsa', 'Reading'], activities: { Cooking: 'good', Yoga: 'improve' } };
  assert.deepEqual(chemistryProgress(data), { answered: 2, total: 5, pct: 40 });
});

test('nextUpcoming picks the first non-past moment in day/hour order', () => {
  const grid = {
    days: [{ day: 'Mon' }, { day: 'Tue' }, { day: 'Wed' }],
    rows: [
      { days: [{ day: 'Mon', moments: [{ day: 'Mon', hour: 12, label: 'Match 1', past: true }] }, { day: 'Tue', moments: [] }, { day: 'Wed', moments: [] }] },
      { days: [{ day: 'Mon', moments: [] }, { day: 'Tue', moments: [{ day: 'Tue', hour: 11, label: 'M1 closes', past: false }] }, { day: 'Wed', moments: [] }] },
    ],
  };
  assert.equal(nextUpcoming({ schedule: { grid } }).label, 'M1 closes');
});
test('nextUpcoming is null with no schedule yet, never throws', () => {
  assert.equal(nextUpcoming(null), null);
  assert.equal(nextUpcoming({}), null);
});

// A design-review finding (see conversation): the old "Next up" card was
// purely schedule-derived, so it could never reflect a real waiting-on-
// partner state that has no clock time at all. nextUpCard() sources its
// title from journey.next_action (already state-aware) and only ever
// layers a schedule time on top when one honestly applies today.
test('nextUpCard reads its title from journey.next_action, not the raw schedule', () => {
  const journey = { next_action: { headline: 'Waiting for your partner', body: 'They still need to sign.', destination: { key: 'plan', eligible: false, request: null } } };
  const card = nextUpCard(journey, null);
  assert.equal(card.title, 'Waiting for your partner');
  assert.equal(card.actionable, false);
  assert.equal(card.eyebrowTime, null);
});
test('nextUpCard is actionable only when the destination is genuinely reachable', () => {
  const journey = { next_action: { headline: 'See this week', destination: { key: 'week', eligible: true, request: { method: 'GET', path: '/x' } } } };
  const card = nextUpCard(journey, null);
  assert.equal(card.actionable, true);
  assert.equal(card.destinationKey, 'week');
});
test('nextUpCard only shows a time when the next schedule moment is honestly today\'s', () => {
  const grid = { days: [{ day: 'Mon' }], rows: [{ days: [{ day: 'Mon', moments: [{ day: 'Mon', hour: 18, label: 'Match 3 closes', past: false }] }] }] };
  const journey = { next_action: { headline: 'x', destination: {} } };
  const todaySame = nextUpCard(journey, { clock: { day: 'Mon' }, schedule: { grid } });
  assert.equal(todaySame.eyebrowTime, null);
  const todayDifferent = nextUpCard(journey, { clock: { day: 'Tue' }, schedule: { grid } });
  assert.equal(todayDifferent.eyebrowTime, null);
});
test('nextUpCard is null with nothing to say at all', () => {
  assert.equal(nextUpCard({ next_action: null }, null), null);
  assert.equal(nextUpCard({}, null), null);
});
