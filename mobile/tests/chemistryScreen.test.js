import test from 'node:test';
import assert from 'node:assert/strict';
import {render, snapshot} from '../src/screens/chemistry.js';
import * as leaveGuard from '../src/leaveGuard.js';

const safe = (v) => String(v ?? '');
const buckets = [['good', '★', 'Already good'], ['improve', '↑', 'Want to improve']];
const base = {activity_options: ['Cooking', 'Hiking'], buckets, activities: {Cooking: 'good'}, partner_any: [], custom_activities: []};

test('snapshot ignores order and compares content', () => {
  assert.equal(snapshot({activities: {b: '1', a: '2'}, partner_any: ['y', 'x']}), snapshot({activities: {a: '2', b: '1'}, partner_any: ['x', 'y']}));
  assert.notEqual(snapshot(base), snapshot({...base, partner_any: ['Cooking']}));
});

test('one Save, enabled only when something changed since the server confirmed it', () => {
  assert.match(render({data: base, safe}), /id="save-chemistry" disabled/);
  const edited = {...base, _baseline: snapshot(base), activities: {Cooking: 'good', Hiking: 'improve'}};
  assert.doesNotMatch(render({data: edited, safe}), /id="save-chemistry" disabled/);
  const failed = {...edited, _error: 'Could not save'};                        // edits kept after a failed save
  assert.doesNotMatch(render({data: failed, safe}), /id="save-chemistry" disabled/);
  assert.match(render({data: failed, safe}), /value="improve" checked/);
});

test('every activity is listed, with its answer and the partner flag shown when collapsed', () => {
  const html = render({data: {...base, partner_any: ['Cooking']}, safe});
  for (const name of ['Cooking', 'Hiking']) assert.match(html, new RegExp(`<span class="activity-name">${name}</span>`));
  assert.match(html, /Cooking<\/span><small data-activity-answer> · Already good<\/small><small data-partner-flag > · Partner can be indifferent/);
  assert.match(html, /Hiking<\/span><small data-activity-answer> · Choose your answer<\/small><small data-partner-flag hidden>/);
  assert.doesNotMatch(render({data: base, safe}), /name="partner_any" value="Cooking" checked/);   // never pre-ticked
});

test('leave guard asks only when there are unsaved changes', () => {
  const asked = [];
  leaveGuard.setAsk((m) => { asked.push(m); return false; });
  leaveGuard.arm(() => false);
  assert.equal(leaveGuard.confirmLeave(), true);
  leaveGuard.arm(() => true);
  assert.equal(leaveGuard.confirmLeave(), false);                               // the member stays
  leaveGuard.setAsk(() => true);
  assert.equal(leaveGuard.confirmLeave(), true);                                // the member leaves
  assert.equal(leaveGuard.dirty(), false);                                       // and the guard is released
  assert.deepEqual(asked, [leaveGuard.MESSAGE]);
});
