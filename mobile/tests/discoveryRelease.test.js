import test from 'node:test';
import assert from 'node:assert/strict';
import {render as vision,empty} from '../src/signupVision.js';
import {render as chemistry} from '../src/screens/chemistry.js';
import {render as week} from '../src/screens/week.js';
import {editableFieldsForm} from '../src/statsFields.js';

test('Emotional is mandatory and Cohabitate details are hidden even with a legacy server catalogue',()=>{
 const html=vision({safe:String,data:{_signupVision:empty(),signup_presets:[],signup_pillar_options:{Intimacy:['Emotional','Physical'],Cohabitate:['Pets']}}});
 assert.match(html,/Your Together plan/);
 assert.match(html,/value="Emotional" checked disabled/);
 assert.doesNotMatch(html,/value="Pets"/);
 assert.match(html,/data-signup-pillar="Cohabitate"/);
});
test('Chemistry displays labels, collapsed answers and independent partner preference',()=>{
 const html=chemistry({safe:String,data:{activity_options:['Running'],activities:{Running:'good'},buckets:[['good','★','Already good at it']]}});
 assert.match(html,/<details class="activity-row" name="chemistry-activity">/);
 assert.match(html,/data-activity-answer> · Already good at it/);
 assert.match(html,/name="partner_any"/);
});
test('Discovery exposes unverified status without allowing interest',()=>{
 const html=week({safe:String,data:{mode:'discovery',message:'Complete verification',quota:2,date_ready:false,proposals:[],passed:[],profiles:[{id:'u',age:29,city:'Delhi',verification:'Unverified',pillars:['Intimacy']}]}});
 assert.match(html,/Unverified/);
 assert.match(html,/data-discovery-action="interest" disabled/);
 assert.doesNotMatch(html,/Match 1/);
});
test('A submitted pairing confirmation is disabled until both respond',()=>{
 const html=week({safe:String,data:{mode:'discovery',quota:2,message:'Review',profiles:[],proposals:[{id:'p',confirmed:true,expires_at:2000000000,profile:{age:30,city:'Mumbai',verification:'Verified',pillars:[]}}]}});
 assert.match(html,/data-proposal="p" disabled/);
 assert.match(html,/Waiting for confirmation/);
});
test('Children count is conditional and numeric errors have an adjacent summary',()=>{
 const html=editableFieldsForm({rows:[{key:'has_children',value:'No',editable:true},{key:'children_count',value:2,editable:true},{key:'height_cm',value:999,editable:true}],ranges:{height_cm:[140,210]},_fieldErrors:{height_cm:'Out of range'}},String,'test');
 assert.match(html,/data-children-count hidden/);
 assert.match(html,/140–210 cm/);
 assert.match(html,/Please correct Height/);
});
