import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmDateAvailable, render as week} from '../src/screens/week.js';
import {render as boundary} from '../src/screens/boundaries.js';
import {render as debrief} from '../src/screens/debrief.js';

test('Confirm Date is unavailable after Thursday, after plan creation, or while introduction runs', () => {
  const ctx={data:{clock:{day:'Thu'}},journey:{surfaces:[{key:'calendar',eligible:true,request:{path:'/calendar'}}]}};
  assert.equal(confirmDateAvailable(ctx),true);
  for(const day of ['Fri','Sat','Sun']) assert.equal(confirmDateAvailable({...ctx,data:{clock:{day}}}),false);
  assert.equal(confirmDateAvailable({...ctx,data:{...ctx.data,date_plan:{status:'confirmed'}}}),false);
  assert.equal(confirmDateAvailable({...ctx,journey:{...ctx.journey,async_rehearsal:{intro_step:2}}}),false);
});

test('Boundaries shows selectable greeting preferences rather than a raw plan', () => {
  const html=boundary({safe:String,data:{answers:{physical_boundary:'namaste'},options:{physical_boundary:['namaste','handshake']}}});
  assert.match(html,/value="namaste" selected/);
  assert.match(html,/Update saved preference/);
  assert.doesNotMatch(html,/lockin_id|<pre/);
});

test('Week shows persisted completion and puts the planning action before the schedule', () => {
  const ctx={safe:String,data:{mode:'locked_in',clock:{week:39,day:'Thu',hour:12},lock_in:{status:'active',week:39},
    activity_status:{calendar_closes:'Completed'},schedule:{grid:{days:[{day:'Thu',is_today:true}],rows:[{days:[{day:'Thu',moments:[{key:'calendar_closes',label:'Publish',hour:12,tone:'publish'}]}]}]}}},
    journey:{surfaces:[{key:'calendar',eligible:true,request:{path:'/calendar'}}]}};
  const html=week(ctx);
  assert.match(html,/✓ Completed/);
  assert.ok(html.indexOf('id="to-calendar"') < html.indexOf('p-week-header'));
  assert.doesNotMatch(week({...ctx,data:{...ctx.data,date_plan:{status:'confirmed'}}}),/id="to-calendar"/);
  assert.doesNotMatch(week({...ctx,data:{...ctx.data,activity_status:{}}}),/✓ Completed/);
});

test('Debrief distinguishes another date from a mutual Relationship choice', () => {
  const html=debrief({safe:String,data:{feedback_open:true,my_feedback:{green_flags:['a','b'],red_flags:[]},decision_options:['continue','relationship','pass']}});
  assert.match(html,/Another date together/);
  assert.match(html,/Move to Relationship/);
  assert.match(html,/both partners must choose it/);
  assert.match(html,/value="continue"/);
  assert.match(html,/value="relationship"/);
});
