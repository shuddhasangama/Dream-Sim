import test from 'node:test';
import assert from 'node:assert/strict';
import {render,bind} from '../src/digilocker.js';
const safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
test('DigiLocker requires explicit consent and explains sandbox',()=>{
  const html=render({enabled:true,environment:'preproduction',consent_text:'Consent',session:null},safe);
  assert.match(html,/checkbox/); assert.match(html,/required/); assert.match(html,/Sandbox test/);
  assert.equal(render({enabled:false},safe),'');
});
test('consent completion triggers retrieval, pending never displays identity approval',async()=>{
  const handlers={}; const calls=[];
  const form={elements:{completed:{checked:true}},addEventListener:(name,fn)=>handlers[name]=fn};
  const root={querySelector:id=>id==='#digilocker-complete'?form:null};
  const data={enabled:true,session:{id:'local-session',state:'pending',consent_url:'https://api.digitallocker.gov.in/'}};
  const html=render(data,safe); assert.match(html,/still processing/); assert.doesNotMatch(html,/<dl>/);
  bind(root,{data,session:{post:async(...args)=>{calls.push(args);return data;}},run:fn=>fn(),patch:()=>{}});
  await handlers.submit({preventDefault(){}});
  // Listener runs the supplied task; flush its microtask.
  await Promise.resolve();
  assert.deepEqual(calls,[['/api/v1/verification/digilocker/sessions/local-session/complete',{consent_completed:true}]]);
});
test('identity is escaped and document address is distinguished from current residence',()=>{
  const html=render({enabled:true,session:{state:'complete',identity:{name:'<img>',dob:'1990-01-01',age:36,age_as_of:'2026-11-02',document_address:'<address>'}}},safe);
  assert.ok(!html.includes('<img>')); assert.match(html,/&lt;img>/); assert.match(html,/does not confirm your current residence/);
  assert.doesNotMatch(html,/digilocker-complete/);
});
test('unconfirmed attempt shows cooldown and hides paid actions',()=>{
  const html=render({enabled:true,session:{state:'not_confirmed',cooling_down:true,cooldown_until:'2026-11-03T12:00:00Z',can_restart:false}},safe);
  assert.match(html,/attempt unsuccessful/); assert.match(html,/Cooldown ends/);
  assert.doesNotMatch(html,/id="digilocker-start"|id="digilocker-complete"/);
  const refreshed=render({enabled:true,consent_text:'Consent',session:{state:'not_confirmed',cooling_down:false,can_restart:true}},safe);
  assert.match(refreshed,/id="digilocker-start"/); assert.doesNotMatch(refreshed,/id="digilocker-complete"/);
});
