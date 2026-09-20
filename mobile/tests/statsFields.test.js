// round4-fixes-spec.md §1 — only changed fields are sent, correctly typed.
import test from 'node:test';
import assert from 'node:assert/strict';
import { changedFields, fieldErrorsFromServer, fieldsEqual } from '../src/statsFields.js';

// Minimal FormData stand-in: changedFields only calls new FormData(form).entries().
globalThis.FormData = class { constructor(form) { this.pairs = form.pairs; } entries() { return this.pairs[Symbol.iterator](); } };

const stats = {
  rows: [
    { key: 'age', value: 38, editable: true }, { key: 'height_cm', value: 170, editable: true },
    { key: 'diet', value: 'Vegetarian', editable: true }, { key: 'languages', value: ['English'], editable: true },
  ],
  ranges: { age: [21, 75], height_cm: [140, 210] },
};
const form = (pairs) => ({ pairs });
const untouched = [['age', '38'], ['height_cm', '170'], ['diet', 'Vegetarian'], ['languages', 'English']];
const with_ = (k, v) => untouched.map(([a, b]) => (a === k ? [a, v] : [a, b]));

test('nothing edited → nothing sent (a string "38" is never re-submitted)', () => {
  const r = changedFields(form(untouched), stats);
  assert.deepEqual(r.fields, {}); assert.equal(r.errors, null);
});
test('one unrelated field changed → only that field, Age untouched', () => {
  const r = changedFields(form(with_('diet', 'Vegan')), stats);
  assert.deepEqual(r.fields, { diet: 'Vegan' });
});
test('an edited numeric field is a real integer, not a string', () => {
  const r = changedFields(form(with_('age', '40')), stats);
  assert.deepEqual(r.fields, { age: 40 }); assert.equal(typeof r.fields.age, 'number');
});
test('out-of-range / non-integer edit is an inline error naming the field', () => {
  assert.match(changedFields(form(with_('age', '99')), stats).errors.age, /Age must be between 21 and 75/);
  assert.match(changedFields(form(with_('height_cm', '170.5')), stats).errors.height_cm, /Height must be a whole number/);
});
test('clearing a field sends null; multi-select changes send the array', () => {
  assert.deepEqual(changedFields(form(with_('height_cm', '')), stats).fields, { height_cm: null });
  const multi = untouched.filter(([k]) => k !== 'languages').concat([['languages', 'English'], ['languages', 'Hindi']]);
  assert.deepEqual(changedFields(form(multi), stats).fields, { languages: ['English', 'Hindi'] });
});
test('server refusal is attached to its own field', () => {
  const r = fieldErrorsFromServer('age has to be between 21 and 75.; Something else', stats);
  assert.match(r.byField.age, /between 21 and 75/); assert.equal(r.general, 'Something else');
});
test('fieldsEqual treats blank and null alike', () => { assert.ok(fieldsEqual('', null)); assert.ok(!fieldsEqual('1', null)); });

test('a rejected entry is still "changed" on retry (compares to the server value, not the re-rendered one)', async () => {
  const { withSubmittedValues } = await import('../src/statsFields.js');
  const failed = withSubmittedValues(stats, { height_cm: '180' });          // re-render after a refused save
  const retry = changedFields(form(with_('height_cm', '180')), failed);
  assert.deepEqual(retry.fields, { height_cm: 180 });
  const reverted = changedFields(form(untouched), failed);                  // user backs out → nothing to send
  assert.deepEqual(reverted.fields, {});
});
