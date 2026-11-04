import {test} from 'node:test';
import assert from 'node:assert/strict';
import {render} from '../src/faceMatch.js';
const safe=x=>String(x??'').replaceAll('<','&lt;');
test('face comparison success explicitly leaves liveness unchecked',()=>{
 const html=render({state:'matched',face_match_passed:true,match_percentage:99,message:'Face matched · Liveness not checked.',enabled:true},safe);
 assert.match(html,/99%/);assert.match(html,/Liveness not checked/);assert.doesNotMatch(html,/id="face-match-start"/);
});
test('missing source cannot request a paid comparison',()=>{
 const html=render({state:'not_started',can_request:false,reference_ready:false,selfie_ready:true,enabled:true,consent_text:'Separate consent'},safe);
 assert.match(html,/Complete DigiLocker/);assert.match(html,/id="face-match-start" disabled/);assert.match(html,/Separate consent/);
});
