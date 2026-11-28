import test from 'node:test';
import assert from 'node:assert/strict';
import {ftInToCm, cmToFtIn, heightLabel, ftInRange, readHeight, ftInInputs} from '../src/heightUnits.js';
import {changedFields, editableFieldsForm} from '../src/statsFields.js';

const safe = (v) => String(v ?? '');

test('client answer 6: same numbers as height_units.py', () => {
  assert.equal(ftInToCm(5, 7), 170);
  assert.deepEqual(cmToFtIn(170), [5, 7]);
  assert.equal(heightLabel(170), '170 cm (5′ 7″)');
  assert.equal(heightLabel(null), '');
  assert.deepEqual(ftInRange(140, 210), [[4, 7], [6, 10]]);
});

test('validation is the same in both units', () => {
  assert.deepEqual(readHeight({cm: '170'}), {cm: 170, error: null});
  assert.deepEqual(readHeight({ft: '5', inch: '7'}), {cm: 170, error: null});
  for (const bad of [{cm: '139'}, {cm: '211'}, {cm: '170.5'}, {ft: '4', inch: '6'}, {ft: '6', inch: '11'}, {ft: '5', inch: '12'}])
    assert.ok(readHeight(bad).error, JSON.stringify(bad));
  assert.match(readHeight({cm: '211'}).error, /4′ 7″–6′ 10″/);
  assert.deepEqual(readHeight({}), {cm: null, error: null});
});

test('the stats editor offers feet/inches and sends one cm value', () => {
  const data = {rows: [{key: 'height_cm', editable: true, value: 170}], options: {}, ranges: {height_cm: [140, 210]}};
  const html = editableFieldsForm(data, safe, 'f');
  assert.match(html, /name="height_ft"/);
  assert.match(html, /name="height_in"/);
  assert.ok(html.includes('140–210 cm (4′ 7″–6′ 10″)'));
  assert.match(ftInInputs(170, safe), /value="5"[\s\S]*value="7"/);
  const form = (values) => ({names: Object.keys(values), __values: values});
  const read = (values) => changedFields(Object.assign(form(values), {[Symbol.iterator]: undefined}), data);
  // FormData stand-in: changedFields reads FormData(form); emulate with a real-ish object
  globalThis.FormData = class { constructor(f) { this.f = f; } entries() { return Object.entries(this.f.__values); } };
  assert.deepEqual(read({height_cm: '170', height_ft: '6', height_in: '0'}).fields, {height_cm: 183});   // ft/in changed
  assert.deepEqual(read({height_cm: '172', height_ft: '5', height_in: '7'}).fields, {height_cm: 172});   // cm changed
  assert.deepEqual(read({height_cm: '170', height_ft: '5', height_in: '7'}).fields, {});                 // untouched
  assert.ok(read({height_cm: '', height_ft: '7', height_in: '2'}).errors.height_cm);                     // 218 cm: refused
});
