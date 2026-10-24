import test from 'node:test';
import assert from 'node:assert/strict';
import { restaurantPanel } from '../src/screens/restaurant.js';

test('Restaurant simulator is explicit and uncertain outcomes only offer reconciliation',()=>{
  const html=restaurantPanel({state:'unknown',message:'Check status',refund:'none',options:[]},String);
  assert.match(html,/No real reservation or payment/);
  assert.match(html,/data-action="reconcile"/);
  assert.doesNotMatch(html,/data-action="pay"|data-action="search"|data-action="cancel"/);
});
test('Both approvals unlock simulated deposit; disabled mode adds nothing',()=>{
  assert.equal(restaurantPanel(null,String),'');
  assert.doesNotMatch(restaurantPanel({state:'shortlist',message:'Choose',options:[],refund:'none',date_open:true},String),/data-action="pay"/);
  assert.match(restaurantPanel({state:'ready_to_pay',message:'Ready',options:[],refund:'none',date_open:true,can_pay:true},String),/data-action="pay"/);
});
