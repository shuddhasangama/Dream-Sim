import test from 'node:test';
import assert from 'node:assert/strict';
import {render as signup,neighbourhoodFields} from '../src/signupStats.js';
import {render as calendar} from '../src/screens/calendar.js';
test('Basics required and date preferences precede remaining sections',()=>{
 const html=signup({safe:String,data:{values:{},options:{}}});
 const labels=['Basics · required','Date preferences · optional','Work &amp; education','Background &amp; family','Lifestyle','Health &amp; accessibility'];
 for(let i=1;i<labels.length;i++)assert.ok(html.indexOf(labels[i])>html.indexOf(labels[i-1]));
 for(const field of ['name','dob','gender','city'])assert.match(html,new RegExp(`name="${field}"[^>]*required`));
});
test('Neighbourhoods come only from selected city and restore checked choices',()=>{
 const opts={neighbourhoods_by_city:{Bangalore:[{id:'indiranagar',name:'Indiranagar'}],Delhi:[{id:'saket',name:'Saket'}]}};
 const html=neighbourhoodFields('Bangalore',['indiranagar'],opts,String);
 assert.match(html,/value="indiranagar" checked/);assert.doesNotMatch(html,/Saket/);
 assert.match(neighbourhoodFields('',[],opts,String),/Choose your city/);
});
test('Calendar asks review before slots and exposes next step after save',()=>{
 const data={editable:true,preferences_reviewed:false,alignment:{my_missing:[],partner_missing:[],mine:{},options:{diet:[],budget:[],cuisine:[]}}};
 assert.doesNotMatch(calendar({safe:String,data}),/id="availability-form"/);
 assert.match(calendar({safe:String,data:{...data,preferences_reviewed:true}}),/id="availability-form"/);
 assert.match(calendar({safe:String,preferencesOnly:true,data:{...data,preferences_reviewed:true}}),/id="choose-availability"/);
});
