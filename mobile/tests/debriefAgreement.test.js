import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from '../src/screens/debrief.js';
import { chipsFor, answerFor } from '../src/screens/guru.js';
const safe=s=>String(s).replaceAll('<','&lt;');
test('mixed intentions show explicit choices instead of another date confirmation',()=>{
  const html=render({safe,data:{my_feedback:{},next_step:{needs_response:true,message:'Different next steps',options:['continue','discuss','end']}}});
  assert.match(html,/Yes, another date/);
  assert.match(html,/Date completed/);
  assert.doesNotMatch(html,/id="decision-form"/);
});
test('waiting partner cannot accept on the other person behalf',()=>{
  const html=render({safe,data:{my_feedback:{},next_step:{needs_response:false,message:'Waiting',options:['discuss','end']}}});
  assert.match(html,/Waiting for your partner/);
  assert.doesNotMatch(html,/Yes, another date/);
});
test('Guru routes discussion back to explicit debrief decision',async()=>{
  const data={topic_stage:'next_step_agreement'};
  assert.equal(chipsFor(data)[0].id,'intentions');
  const answer=await answerFor('intentions',data,[{key:'debrief',eligible:true,request:{path:'/date/debrief'}}]);
  assert.match(answer.answer,/Discussion does not accept another date/);
  assert.equal(answer.actionKey,'debrief');
});

import { render as renderPlan } from '../src/screens/plan.js';
test('old date is completed while next step is awaiting agreement',()=>{
 const html=renderPlan({safe,data:{id:'p',status:'confirmed'},journey:{current_date_plan:{id:'p',display_status:'completed_awaiting_agreement'}}});
 assert.match(html,/<h1>Date completed<\/h1>/);
});
