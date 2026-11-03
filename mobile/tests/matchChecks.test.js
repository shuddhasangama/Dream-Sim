import test from 'node:test';
import assert from 'node:assert/strict';
import {render} from '../src/matchChecks.js';
const safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
test('nonshared summaries show no private checks',()=>{
 const html=render({shared:false,checks:[{label:'PRIVATE',status_label:'PRIVATE'}]},safe);
 assert.match(html,/not shared/);assert.doesNotMatch(html,/PRIVATE/);
});
test('match summary displays distinct statuses and checked dates safely',()=>{
 const html=render({shared:true,sandbox:true,checks:[{label:'Court',status_label:'Verified',checked_on:'2026-11-03'},{label:'Employment',status_label:'History found',checked_on:'2026-11-02'},{label:'<FIR>',status_label:'<status>'}]},safe);
 assert.match(html,/Checked on 2026-11-03/);assert.match(html,/History found/);assert.match(html,/Sandbox/);assert.doesNotMatch(html,/<FIR>|<status>/);assert.match(html,/Like or Pass/);
});
