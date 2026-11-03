import test from 'node:test';
import assert from 'node:assert/strict';
import { render, load, bind } from '../src/screens/verification.js';
const safe = v=>String(v??'').replaceAll('<','&lt;').replaceAll('>','&gt;');
test('verification labels sandbox and separates unavailable from mismatch',()=>{
  const html=render({safe,data:{enabled:true,environment:'preproduction',checks:{pan_simple:'Name and DOB'},
    consent_text:'Consent',results:[{operation:'individual_search',environment:'preproduction',state:'unavailable',message:'<private>'}]}});
  assert.match(html,/Sandbox testing/);
  assert.match(html,/Check unavailable/);
  assert.ok(!html.includes('<private>'));
  assert.match(html,/Verification checklist/);
  assert.doesNotMatch(html,/bgv-form|name="address"/);
});
test('disabled verification exposes no submission form',()=>{
  assert.ok(!render({safe,data:{enabled:false,checks:{},results:[]}}).includes('bgv-form'));
});
test('verification reads only own status and binds with root/context signature',async()=>{
  const calls=[];
  await load({get:async p=>calls.push(p)});
  assert.deepEqual(calls,['/api/v1/verification','/api/v1/verification/digilocker','/api/v1/verification/plan','/api/v1/verification/liveness']);
  assert.doesNotThrow(()=>bind({querySelector:()=>null},{session:{},run:()=>{},patch:()=>{}}));
});

test('compact checklist uses received identity, flags age difference and never invents clearance',()=>{
  const html=render({safe,data:{enabled:true,environment:'preproduction',bundle:{declared_age:34,consented:true,pan_state:'not_shared'},digilocker:{session:{state:'complete',identity:{name:'<private>',age:42,dob:'1984-01-01',document_address:'<address>'}}},results:[{operation:'fir_result',environment:'preproduction',state:'needs_review',message:'Review needed'}]}});
  assert.match(html,/Review age/);assert.match(html,/profile says 34/);assert.match(html,/PAN wasn/);
  assert.doesNotMatch(html,/<private>|<address>|None found|Live face match/);
  assert.match(html,/Setup needed/);assert.match(html,/View document details/);
});

test('exact zero results show Verified and historical employer shows History found',()=>{
  const html=render({safe,data:{enabled:true,environment:'preproduction',bundle:{consented:true,employer_declared:true},results:[{operation:'current_employer',environment:'preproduction',state:'history_available',message:'Last recorded employer: Synthetic Ltd (2021 to 2022). Current employment is not established.'},{operation:'individual_result',environment:'preproduction',state:'verified',message:'Verified: completed exact search returned zero cases.'},{operation:'fir_result',environment:'preproduction',state:'verified',message:'Verified: completed exact search returned zero cases.'}]}});
  assert.match(html,/History found/);assert.match(html,/Last recorded employer/);assert.equal((html.match(/bgv-badge good">Verified/g)||[]).length,2);
  assert.doesNotMatch(html,/Review needed|Final BGV review is pending/);
});
