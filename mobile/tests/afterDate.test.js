import test from 'node:test';
import assert from 'node:assert/strict';
import {render as gate} from '../src/screens/gate.js';
import {render as after} from '../src/screens/afterDate.js';
import {agreementPath,render as ceremony} from '../src/screens/ceremony.js';
import {withRealDateOnly} from '../src/screens/week.js';
const safe=v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;');
test('gate presents empty round as selection, not agreement; escapes custom prompts',()=>{
 const html=gate({safe,data:{gate:{status:'open',round:1},questions:[],asked:[{key:'x',prompt:'<script>',kind:'text'}],my_answers:{},report:{complete:false,headline:'Choose topics'},reflection:{},my_prerequisites:{}}});
 assert.match(html,/Choose up to three/);assert.match(html,/&lt;script>/);assert.doesNotMatch(html,/<script>/);assert.match(html,/data-gate="confirm" disabled/);
});
test('after date requires own agreement to accept contact and both to propose home visit',()=>{
 const html=after({safe,data:{contact_requests:[{id:'r',channel:'phone',sent_by_me:false,status:'pending'}],home_invites:[],contact_channels:['phone'],agreements:{}}});
 assert.match(html,/value="accepted" disabled/);assert.match(html,/<button class="secondary" disabled>Propose visit/);assert.doesNotMatch(html,/<pre/);
});
test('ceremony routes pair agreements and never claims partner has signed from own completion',()=>{
 assert.equal(agreementPath({lockInId:'a/b',kind:'contact_share'}),'/api/v1/lock-ins/a%2Fb/agreements/contact_share');
 const html=ceremony({safe,data:{complete:true,step:'done'}});
 assert.doesNotMatch(html,/Both signatures/);assert.match(html,/Waiting for your partner/);
});
test('week never invents sign or debrief without a saved plan',()=>{
 const result=withRealDateOnly({Thu:[{key:'sign'}],Sat:[{key:'debrief',tone:'debrief'}]},null);
 assert.deepEqual(result,{Thu:[],Sat:[]});
});

test('later checkpoints use the shared agreement screen and require partner completion',()=>{
 assert.equal(agreementPath({coupleId:'p/1',source:'relationship'}),'/api/v1/couples/p%2F1/checkpoints/relationship');
 const ctx={safe,params:{coupleId:'p'},data:{step:'done',my_complete:true,partner_complete:false,to_stage:'engaged',clauses:[]}};
 assert.match(ceremony(ctx),/id="advance-stage" class="primary" disabled/);
 assert.doesNotMatch(ceremony(ctx),/Both partners have completed/);
 assert.match(ceremony({...ctx,data:{...ctx.data,partner_complete:true}}),/Both partners have completed/);
});
