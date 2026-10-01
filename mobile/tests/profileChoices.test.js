import test from 'node:test';
import assert from 'node:assert/strict';
import {render} from '../src/screens/personal.js';
import {SIGNUP_STEPS} from '../src/signup.js';
test('personal screen explains consent, unknown status and displays saved values',()=>{
 const html=render({safe:String,data:{categories:{diabetes:'Diabetes'},health:{consent:true,categories:['diabetes'],note:'Discuss first'},openness:{mode:'specific',categories:['diabetes'],include_undisclosed:false},ethnicity:['South Asian'],ethnicity_options:['South Asian']}});
 assert.match(html,/name="share_health" type="checkbox" checked/);
 assert.match(html,/Discuss first/);
 assert.match(html,/their status is unknown/);
 assert.match(html,/Previously viewed information cannot be recalled/);
 assert.match(html,/value="specific" selected/);
 assert.deepEqual(SIGNUP_STEPS,['Vision','Stats','Chemistry','Profile']);
});
