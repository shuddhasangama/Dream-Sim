import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePhone,countries,countryOptions} from '../src/phoneCountry.js';
test('India requires exactly ten digits',()=>{
 assert.equal(normalizePhone('9876543210'),'+919876543210');
 assert.equal(normalizePhone('+91 98765 43210'),'+919876543210');
 for(const v of ['987654321','98765432101','919876543210','','98765abcde']) assert.throws(()=>normalizePhone(v));
});
test('only India is enabled and other options are visible',()=>{
 assert.deepEqual(countries.filter(c=>c.enabled).map(c=>c.code),['IN']);
 assert.throws(()=>normalizePhone('4155552671','US'));
 assert.match(countryOptions(),/disabled/);
 assert.match(countryOptions(),/Coming soon/);
});
