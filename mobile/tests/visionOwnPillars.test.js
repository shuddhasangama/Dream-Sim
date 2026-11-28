import test from 'node:test';
import assert from 'node:assert/strict';
import {addOwnPillar, inferPlan, render, empty, MAX_CUSTOM} from '../src/signupVision.js';

const safe = (v) => String(v ?? '');

test('client answer 1: Travel together label and own pillars on Custom', () => {
  const data = {signup_presets: [{key: 'grow'}], signup_pillar_options: {Intimacy: ['Emotional', 'Physical']}};
  assert.match(render({data, safe}), />Travel together</);
  let draft = addOwnPillar(empty(), '  Faith ');
  assert.deepEqual(draft.custom_pillars, ['Faith']);
  assert.equal(draft.plan, 'custom');
  assert.equal(inferPlan({Intimacy: ['Emotional'], 'Travel together': []}, ['Faith']), 'custom');
  assert.equal(inferPlan({Intimacy: ['Emotional'], 'Travel together': []}), 'explore');
  assert.throws(() => addOwnPillar(draft, 'faith'), /already listed/);
  assert.throws(() => addOwnPillar(draft, 'Kids'), /already listed/);
  for (const name of ['B', 'C', 'D']) draft = addOwnPillar(draft, name);
  assert.equal(draft.custom_pillars.length, MAX_CUSTOM);
  assert.throws(() => addOwnPillar(draft, 'E'), /up to 4/);
  assert.match(render({data: {...data, _signupVision: draft}, safe}), /Your own pillars[\s\S]*Faith/);
});
