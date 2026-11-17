import test from 'node:test';
import assert from 'node:assert/strict';
import {render} from '../src/screens/align.js';
test('date preferences screen has real controls without premature slot booking',()=>{
 const html=render({safe:String,data:{editable:true,alignment:{my_missing:[],partner_missing:[],mine:{},options:{diet:['Vegetarian'],budget:['500'],cuisine:['Indian']}},my_slots:[],overlap:[]}});
 assert.match(html,/alignment-form/);assert.match(html,/Vegetarian/);
 assert.doesNotMatch(html,/availability-form|confirm-slot/);
});
