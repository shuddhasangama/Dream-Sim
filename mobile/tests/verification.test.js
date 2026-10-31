import test from 'node:test';
import assert from 'node:assert/strict';
import { render, load, bind } from '../src/screens/verification.js';
const safe = v=>String(v??'').replaceAll('<','&lt;').replaceAll('>','&gt;');
test('verification labels sandbox and separates unavailable from mismatch',()=>{
  const html=render({safe,data:{enabled:true,environment:'preproduction',checks:{pan_simple:'Name and DOB'},
    consent_text:'Consent',results:[{operation:'pan_simple',environment:'preproduction',state:'unavailable',message:'<private>'}]}});
  assert.match(html,/Sandbox testing/);
  assert.match(html,/Check unavailable/);
  assert.ok(!html.includes('<private>'));
  assert.match(html,/checkbox/);
});
test('disabled verification exposes no submission form',()=>{
  assert.ok(!render({safe,data:{enabled:false,checks:{},results:[]}}).includes('bgv-form'));
});
test('verification reads only own status and binds with root/context signature',async()=>{
  const calls=[];
  await load({get:async p=>calls.push(p)});
  assert.deepEqual(calls,['/api/v1/verification']);
  assert.doesNotThrow(()=>bind({querySelector:()=>null},{session:{},run:()=>{},patch:()=>{}}));
});
