import test from 'node:test';
import assert from 'node:assert/strict';
import {render} from '../src/screens/personal.js';
import {healthForm} from '../../static/health-reach.js';
import {SIGNUP_STEPS} from '../src/signup.js';
test('personal screen explains consent, unknown status and displays saved values',()=>{
 const html=render({safe:String,data:{categories:{diabetes:'Diabetes'},health:{consent:true,categories:['diabetes'],note:'Discuss first'},openness:{mode:'specific',categories:['diabetes'],include_undisclosed:false},ethnicity:['South Asian'],ethnicity_options:['South Asian']}});
 assert.match(html,/name="share_health" type="checkbox" checked/);
 assert.match(html,/Discuss first/);
 assert.match(html,/An unanswered profile does not mean no conditions/);
 assert.match(html,/Your Bio/);
 assert.doesNotMatch(html,/name="openness"/);
 assert.match(html,/Withdraw health disclosure/);
 assert.match(html,/Previously viewed information cannot be recalled/);

 assert.deepEqual(SIGNUP_STEPS,['Vision','Stats','Chemistry','Bio']);
});

test('REACH contains private health preferences with saved selections',()=>{
 const html=healthForm({categories:{diabetes:'Diabetes'},preferences:{mode:'specific',categories:['diabetes'],include_undisclosed:false}},String);
 assert.match(html,/value="specific" selected/);
 assert.match(html,/value="diabetes" checked/);
 assert.match(html,/Notes are never used for filtering/);
 assert.doesNotMatch(html,/name="include_undisclosed" checked/);
});
