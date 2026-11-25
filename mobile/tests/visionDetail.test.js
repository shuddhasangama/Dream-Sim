import test from 'node:test';
import assert from 'node:assert/strict';
import {render} from '../src/screens/vision.js';

// Owner decision (2026-11-25): Add detail / Declare a change only for items that
// HAVE detail, read from the server's pillar_options — never from a hardcoded list.
const safe = (v) => String(v ?? '');
const base = {
  goals: [{key: 'Intimacy', stance: ['Emotional']}, {key: 'Kids', stance: null}, {key: 'Cohabitate', stance: null}],
  element_keys: ['Intimacy', 'Kids', 'Cohabitate', 'Travel together'],
  pillar_options: {Intimacy: ['Emotional', 'Physical'], Kids: [], Cohabitate: [], 'Travel together': []},
  rc_open: true,
};
const html = (data) => render({data, safe});

test('only items with detail are offered in Add detail and Declare a change', () => {
  const out = html(base);
  assert.match(out, /data-vision-panel="add"/);
  assert.match(out, /data-vision-panel="change"/);
  assert.match(out, /value="Intimacy\|Physical"/);                       // the one detail not yet held
  for (const pillar of ['Kids', 'Cohabitate', 'Travel together']) {
    assert.doesNotMatch(out, new RegExp(`option value="${pillar}\\|`), pillar);   // no add action
    assert.doesNotMatch(out, new RegExp(`data-pillar="${pillar}"`), pillar);      // no change action
  }
  assert.match(out, /<option value="Intimacy">Intimacy<\/option>/);
});

test('both panels disappear when no item has detail', () => {
  const out = html({...base, pillar_options: {Intimacy: [], Kids: [], Cohabitate: [], 'Travel together': []}});
  assert.doesNotMatch(out, /data-vision-panel=/);
  assert.doesNotMatch(out, /Use Add detail or Declare a change/);
});

test('the rule follows the data: give Cohabitate detail and it gets both actions', () => {
  const out = html({...base, pillar_options: {...base.pillar_options, Cohabitate: ['Pets']}});
  assert.match(out, /value="Cohabitate\|Pets"/);
  assert.match(out, /data-pillar="Cohabitate"/);
});
