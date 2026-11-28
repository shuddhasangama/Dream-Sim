import test from 'node:test';
import assert from 'node:assert/strict';
import {render, bodyFrom, isPrompt, stillNeeded, CODE} from '../src/datePreferences.js';

const safe = (v) => String(v ?? '');
const state = {values: {diet: '', cuisine: [], budget: [], neighbourhoods: []}, missing: ['neighbourhoods', 'cuisine'],
  labels: {neighbourhoods: 'Neighbourhood', cuisine: 'Cuisine'}, diet_locked: false,
  options: {neighbourhoods: [{id: 'indiranagar', name: 'Indiranagar'}], diet: ['Vegan'], cuisine: ['Thai'], budget: ['₹']},
  _prompt: 'Before you accept a match, complete your date preferences: Neighbourhood, Cuisine.'};

test('client answer 3: the server refusal opens the prompt with its message', () => {
  assert.equal(CODE, 'date_preferences_required');
  assert.ok(isPrompt({status: 409, code: 'date_preferences_required'}));
  assert.ok(!isPrompt({status: 409, code: 'state_conflict'}));
  const html = render(state, safe);
  assert.match(html, /role="alert"[^>]*>Before you accept a match/);
  assert.match(html, /Neighbourhood · up to three · needed/);
  assert.match(html, /Cuisine · needed/);
  assert.deepEqual(stillNeeded(state), ['Neighbourhood', 'Cuisine']);
});

test('the form sends the four preferences, and a set diet only from Stats', () => {
  globalThis.FormData = class { constructor(f) { this.f = f; } getAll(k) { return this.f[k] || []; } get(k) { return (this.f[k] || [null])[0]; } };
  const form = {neighbourhoods: ['indiranagar'], cuisine: ['Thai'], budget: ['₹'], diet: ['Vegan']};
  assert.deepEqual(bodyFrom(form, state), {cuisine: ['Thai'], budget: ['₹'], neighbourhoods: ['indiranagar'], diet: 'Vegan'});
  assert.equal(bodyFrom(form, {...state, diet_locked: true}).diet, undefined);
  assert.match(render({...state, diet_locked: true}, safe), /Change your diet in Stats/);
});
