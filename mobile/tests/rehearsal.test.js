import test from 'node:test';
import assert from 'node:assert/strict';
import {renderRehearsal,progressKey} from '../src/rehearsal.js';
const safe=s=>String(s).replaceAll('<','&lt;');
test('rehearsal UI is absent unless enabled and only offers server action',()=>{
  assert.equal(renderRehearsal(null,safe),'');
  const waiting=renderRehearsal({enabled:true,message:'Waiting <partner>'},safe);
  assert.ok(waiting.includes('&lt;partner>'));
  assert.ok(!waiting.includes('id="rehearsal-ready"'));
  const ready=renderRehearsal({enabled:true,message:'Ready',request:{label:'Ready for Debrief'}},safe);
  assert.ok(ready.includes('Ready for Debrief'));
});
test('partner progress is detected even without a clock change',()=>{
  const a={clock:{week:39,day:'Thu',hour:18},async_rehearsal:{partner_ready:false}};
  assert.notEqual(progressKey(a),progressKey({...a,async_rehearsal:{partner_ready:true}}));
  assert.notEqual(progressKey(a),progressKey({...a,async_rehearsal:null}));
});
