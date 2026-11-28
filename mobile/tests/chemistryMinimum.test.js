import test from 'node:test';
import assert from 'node:assert/strict';
import {render, activityMinimumError, countText, minimumFor, MIN_ACTIVITIES} from '../src/screens/chemistry.js';

const safe = (v) => String(v ?? '');
const buckets = [['good', '★', 'Already good'], ['maybe', '?', 'Maybe']];

test('client answer 4: at least four activities, own activities count', () => {
  assert.equal(MIN_ACTIVITIES, 4);
  assert.match(activityMinimumError({a: 'good', b: 'good', c: 'maybe'}), /at least 4 activities \(3\/4 so far\)/);
  assert.equal(activityMinimumError({a: 'good', b: 'good', c: 'maybe', 'My own': 'good'}), null);
  assert.equal(minimumFor({min_activities: 5}), 5);
  assert.equal(minimumFor({}), 4);
});

test('the screen shows how many are sorted against the minimum', () => {
  const html = render({safe, data: {activity_options: ['Cooking'], buckets, activities: {Cooking: 'good'}, partner_any: [],
    custom_activities: ['Kite flying'], min_activities: 4}});
  assert.match(html, /id="activity-count"/);
  assert.ok(html.includes(countText(1, 4)));
  assert.match(html, /Kite flying/);                       // own activities are listed with the catalogue
  assert.match(html, /Add your own activity/);
});
