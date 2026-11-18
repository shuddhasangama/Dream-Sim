import test from 'node:test';
import assert from 'node:assert/strict';
import { render, load, bind, processing, canAutoRefresh } from '../src/screens/verification.js';
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
  assert.deepEqual(calls,['/api/v1/verification','/api/v1/verification/digilocker','/api/v1/verification/plan','/api/v1/verification/liveness','/api/v1/profile/liveness','/api/v1/profile/avatar','/api/v1/verification/payment']);
  assert.doesNotThrow(()=>bind({querySelector:()=>null},{session:{},run:()=>{},patch:()=>{}}));
});

test('compact checklist uses received identity, flags age difference and never invents clearance',()=>{
  const html=render({safe,data:{enabled:true,environment:'preproduction',bundle:{declared_age:34,consented:true,pan_state:'not_shared'},digilocker:{session:{state:'complete',identity:{name:'<private>',age:42,dob:'1984-01-01',document_address:'<address>'}}},results:[{operation:'fir_result',environment:'preproduction',state:'needs_review',message:'Review needed'}]}});
  assert.match(html,/Review age/);assert.match(html,/profile says 34/);assert.match(html,/PAN required:/);
  assert.doesNotMatch(html,/<private>|<address>|None found|Live face match/);
  assert.match(html,/Setup needed/);assert.match(html,/View document details/);
});

test('exact zero results show Verified and historical employer shows History found',()=>{
  const html=render({safe,data:{enabled:true,environment:'preproduction',bundle:{consented:true,employer_declared:true},results:[{operation:'current_employer',environment:'preproduction',state:'history_available',message:'Last recorded employer: Synthetic Ltd (2021 to 2022). Current employment is not established.'},{operation:'individual_result',environment:'preproduction',state:'verified',message:'Verified: completed exact search returned zero cases.'},{operation:'fir_result',environment:'preproduction',state:'verified',message:'Verified: completed exact search returned zero cases.'}]}});
  assert.match(html,/History found/);assert.match(html,/Last recorded employer/);assert.equal((html.match(/bgv-badge good">Verified/g)||[]).length,2);
  assert.doesNotMatch(html,/Final BGV review is pending/);
});


test('background work shows progress without refresh or duplicate avatar actions',()=>{
 const data={enabled:true,results:[{operation:'fir_search',state:'queued'}],digilocker:{enabled:true,session:{state:'retrieving'},consent_text:'Consent'},avatar:{enabled:true,state:'submitting',can_capture:true,options:[]},face:{enabled:true,state:'queued_get',operation:'liveness_secure',message:'Retrieving',can_complete:true}};
 const html=render({safe,data});
 assert.ok(html.indexOf('Connect DigiLocker')<html.indexOf('Verification checklist'));
 assert.match(html,/Aadhaar is required/);assert.match(html,/PAN is required for employment screening/);
 assert.match(html,/background/);assert.match(html,/Generating/);
 assert.doesNotMatch(html,/id="(?:bgv-refresh|face-match-refresh|avatar-refresh|avatar-camera|avatar-generate|face-hosted-complete)"/);
 assert.equal(processing(data),true);assert.equal(canAutoRefresh({...data,_verificationEditing:true}),false);
});

test('an unrelated avatar outage does not block verification reads',async()=>{
 const result=await load({get:async path=>{if(path.endsWith('/avatar'))throw {status:503};return {};}});
 assert.equal(result.avatar.state,'unavailable');
});

test('available identity-bound PAN allows scheduling without employer declaration',()=>{
 const html=render({safe,data:{enabled:true,bundle:{consented:true,pan_state:'not_shared',employer_declared:true,employment_identifier_available:true,mobile_available:false},results:[]}});
 assert.match(html,/Starting in the background/);assert.doesNotMatch(html,/PAN wasn|Mobile wasn/);
});


test('employment no longer asks for an employer and preserves owner-only result text',()=>{
 const html=render({safe,data:{enabled:true,bundle:{enabled:true,consented:true},digilocker:{session:{identity:{age:30}}},results:[{operation:'current_employer',state:'history_available',message:'Latest recorded employer: Example Ltd',received_at:'2026-11-15T06:00:00Z'}]}});
 assert.match(html,/Example Ltd/);assert.match(html,/Received/);
 assert.doesNotMatch(html,/name="employer"|Save employer/);
});

test('interrupted processing stops the spinner and exposes recovery guidance',()=>{
 const data={results:[{operation:'fir_result',state:'processing',recovery_required:true,message:'Support must reconcile'}]};
 assert.equal(processing(data),false);assert.match(render({safe,data}),/Support must reconcile/);
});

test('live face unlocks avatar while court work continues, in order',()=>{
 const base={enabled:true,bundle:{consented:true},digilocker:{session:{identity:{name:'Test',age:30}}},face:{operation:'liveness_secure',state:'matched'},avatar:{enabled:true,state:'not_started',can_capture:true,options:[]},results:[{operation:'fir_search',state:'queued'}]};
 const html=render({safe,data:base});
 assert.ok(html.indexOf('id="verification-face"')<html.indexOf('id="verification-avatar"'));
 assert.ok(html.indexOf('id="verification-avatar"')<html.indexOf('aria-label="Verification checklist"'));
 assert.match(html,/review your verified selfie/i);
 const locked=render({safe,data:{...base,face:{operation:'liveness_secure',state:'not_started'}}});
 assert.match(locked,/Complete live face verification first/);
 assert.doesNotMatch(locked,/id="avatar-generate"/);
});
