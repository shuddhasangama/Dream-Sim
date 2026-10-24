import test from 'node:test';
import assert from 'node:assert/strict';
import { render } from '../src/screens/calendar.js';

const base = {editable:true,alignment:{my_missing:[],partner_missing:[],mine:{},options:{diet:[],budget:[],cuisine:[]}},
  valid_slots:[],my_slots:[],overlap:[{day:'Sat',meal_slot:'dinner'}]};
const booking = {editable:true,ready:false,message:'Waiting for your match.',market:{city:'Bengaluru'},
  neighbourhoods:[{id:'indiranagar',name:'Indiranagar'}],mine:['indiranagar'],shared_neighbourhoods:[]};

test('Neighbourhood controls gate confirmation until both partners agree', () => {
  const html=render({safe:String,data:{...base,booking}});
  assert.match(html,/name="neighbourhood" value="indiranagar" checked/);
  assert.match(html,/confirm-slot[^>]*disabled/);
  assert.match(html,/does not reserve a table/);
  assert.doesNotMatch(render({safe:String,data:{...base,booking:{...booking,ready:true}}}),/confirm-slot[^>]*disabled/);
});
test('Flag-off calendar remains compatible and frozen choices have no form', () => {
  assert.doesNotMatch(render({safe:String,data:base}),/neighbourhood-form/);
  assert.doesNotMatch(render({safe:String,data:{...base,booking:{...booking,editable:false}}}),/neighbourhood-form/);
});
