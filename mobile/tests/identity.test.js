import test from 'node:test';
import assert from 'node:assert/strict';
import {panel,captureOptions} from '../src/screens/identity.js';
import {render as ceremony} from '../src/screens/ceremony.js';
const safe=value=>String(value??'').replaceAll('<','&lt;').replaceAll('"','&quot;');
test('a pending identity image cannot be used as an approved face step',()=>{
  const html=ceremony({safe,data:{step:'face',face_simulation_available:true,identity:{enabled:true,status:'submitted',verified:false,capture_id:'c'}}});
  assert.doesNotMatch(html,/id="do-face"/);
  assert.match(html,/signature is saved/);
  assert.doesNotMatch(html,/beta simulation/);
});
test('approved identity is reusable but each agreement still needs consent',()=>{
  const html=ceremony({safe,data:{step:'face',identity:{enabled:true,status:'verified',verified:true,capture_id:'c'}}});
  assert.match(html,/id="do-face"/);
  assert.match(html,/Each agreement still needs your own signature/);
  assert.doesNotMatch(html,/identity-camera/);
});
test('capture requires review and explicit consent and does not save to gallery',()=>{
  const html=panel({enabled:true,status:'not_captured',consent_text:'<script>'},safe);
  assert.match(html,/name="consent" required/);
  assert.match(html,/id="identity-upload"[^>]*disabled/);
  assert.match(html,/&lt;script>/);
  assert.equal(captureOptions.saveToGallery,false);
  assert.equal(captureOptions.allowEditing,false);
  assert.equal(captureOptions.source,'CAMERA');
});

test('test-approved capture offers Continue without claiming BGV verification',()=>{
  const html=ceremony({safe,data:{step:'face',identity:{enabled:true,status:'captured',verified:false,test_approved:true,can_complete:true,capture_id:'c'}}});
  assert.match(html,/id="do-face"/);
  assert.match(html,/Continue/);
  assert.match(html,/BGV authentication is still pending/);
  assert.doesNotMatch(html,/Return here once/);
});
