import test from 'node:test';
import assert from 'node:assert/strict';
import {needsSignup, createSignup} from '../src/signup.js';

test('pending onboarding and dating resume setup, established stages remain accessible',()=>{
 for(const journey_state of ['onboarding','dating']){
  assert.equal(needsSignup({journey_state,bgv_status:'pending'}),true);
  assert.equal(needsSignup({journey_state,bgv_status:'verified'}),false);
 }
 assert.equal(needsSignup({journey_state:'relationship',bgv_status:'pending'}),false);
 assert.equal(needsSignup(null),false);
});

test('server progress restores Stats and exposes verification without discarding dirty edits',async()=>{
 const signup=createSignup({session:{get:async path=>path==='/api/v1/signup/state'?{modern:true,next_step:1,values:{},options:{}}:{}},run:async f=>f(),safe:String,finish:async()=>{}});
 await signup.begin();
 const html=signup.render();
 assert.match(html,/Step 2 of 4/);
 assert.match(html,/signup-verification/);
});
