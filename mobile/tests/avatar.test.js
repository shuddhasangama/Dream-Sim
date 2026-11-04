import {test} from 'node:test';
import assert from 'node:assert/strict';
import {render,bind} from '../src/screens/avatar.js';
const safe=x=>String(x??'').replaceAll('<','&lt;');
test('loading avatar screen binds without dereferencing missing data',()=>{
 assert.doesNotThrow(()=>bind({querySelector:()=>null,querySelectorAll:()=>[]},{session:{},run:()=>{},patch:()=>{},data:null}));
});
test('avatar explains selfie-only consent and permanent two-option limit',()=>{
 const html=render({data:{enabled:true,can_capture:true,options:[],state:'not_started',message:'Capture',consent_text:'Only my selfie'},safe});
 assert.match(html,/One generation run/);assert.match(html,/Generate 2 avatars/);assert.match(html,/GPT Image 2/);assert.doesNotMatch(html,/avatar-photos/);
});
test('ready avatar options are individually selectable without another generation button',()=>{
 const html=render({data:{enabled:true,state:'ready',options:['data:image/jpeg;base64,one','data:image/jpeg;base64,two'],selected:1,avatar:{}},safe});
 assert.match(html,/data-avatar-accept="0"/);assert.match(html,/data-avatar-accept="1"/);assert.match(html,/Selected/);assert.doesNotMatch(html,/id="avatar-generate"/);
});
