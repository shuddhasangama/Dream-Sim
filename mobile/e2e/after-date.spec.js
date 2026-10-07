import {test,expect} from '@playwright/test';
const base={lock_in_id:'pair/one',gate:{status:'open',round:1,my_confirmed:false,partner_confirmed:false},questions:[{key:'relationship_meaning',text:'What does a relationship mean to you?',kind:'text'}],asked:[],my_answers:{},report:{headline:'Choose topics.',complete:false,lines:[]},reflection:{test_mode:true,my_ready:false,partner_ready:false},my_prerequisites:{met:false,vision_met:true,chemistry_missing:['intimacy_pace'],stats_missing:[]}};
async function mount(page,module,data){
 await page.goto('/');
 await page.evaluate(async({module,data})=>{
  const screen=await import(`/src/screens/${module}.js`);
  const root=document.createElement('main');root.className='container';root.style.maxWidth='460px';document.body.replaceChildren(root);
  window.sent=[];
  const ctx={data,safe:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),journey:{current_lock_in:{partner_name:'Your match',name_hidden:true,partner_summary:{city:'Bangalore',age:33}},current_date_plan:{datetime:'2026-10-03T19:30',status:'confirmed'},milestones:['first_date']},params:{},refreshJourney:async()=>{},navigateTo:(...args)=>window.sent.push({navigation:args}),session:{post:async(path,body)=>{window.sent.push({path,body});return data;}},patch:()=>{},run:async(fn)=>{try{await fn();}catch(e){window.failure=e.message;}}};
  root.innerHTML=screen.render(ctx);screen.bind(root,ctx);
 },{module,data});
}
for(const width of [375,414,430])test(`relationship questions usable at ${width}px and enlarged layout`,async({page})=>{
 await page.setViewportSize({width,height:896});await mount(page,'gate',base);
 await page.getByLabel('What does a relationship mean to you?').check();
 await page.getByLabel('Your own question').fill('How do we balance family time?');
 await page.getByRole('button',{name:'Save topics'}).click();
 expect(await page.evaluate(()=>window.sent[0])).toEqual({path:'/api/v1/lock-ins/pair%2Fone/gate/ask',body:{round:1,question_keys:['relationship_meaning'],custom_question:'How do we balance family time?'}});
 await expect(page.getByRole('button',{name:'Finish reflection (test)'})).toBeDisabled();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 if(width===414)await page.screenshot({path:'test-results/relationship-414.png',fullPage:true});
 await page.evaluate(()=>document.body.style.zoom='2');
 await page.getByRole('button',{name:'Complete profile',exact:true}).scrollIntoViewIfNeeded();
 await page.getByRole('button',{name:'Complete profile',exact:true}).click();
 expect(await page.evaluate(()=>window.sent.at(-1))).toEqual({navigation:['dashboard']});
});
test('contact acceptance sends chosen handle to owned request',async({page})=>{
 await mount(page,'afterDate',{lock_in_id:'pair/one',contact_channels:['instagram'],contact_requests:[{id:'r/one',channel:'instagram',status:'pending',sent_by_me:false}],agreements:{contact_share:{mine:true,partner:false}},home_invites:[],expectation_flags:[],next_level:{questions:[],answers:[]}});
 await page.getByLabel('Your handle or profile URL').fill('@myprofile');
 await page.getByRole('button',{name:'Accept sharing',exact:true}).click();
 expect(await page.evaluate(()=>window.sent[0])).toEqual({path:'/api/v1/lock-ins/pair%2Fone/contact-requests/r%2Fone/response',body:{response:'accepted',contact_value:'@myprofile'}});
 await expect(page.getByRole('button',{name:'Propose visit'})).toBeDisabled();
});

for(const width of [320,414])test(`adjacent answers and compact calendar at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:896});
 await mount(page,'gate',{...base,my_questions_submitted:true,asked:[{key:'relationship_meaning',prompt:'What does a relationship mean to you?',kind:'text',origin:'both'}],my_answers:{relationship_meaning:'Time together'},my_sharing:{relationship_meaning:true},partner_answers:{relationship_meaning:'Being considerate'},partner_answered:['relationship_meaning'],report:{complete:true},reflection:{test_mode:true,my_ready:false}});
 await expect(page.getByText('Chosen by both',{exact:true})).toBeVisible();
 await expect(page.getByText('Being considerate',{exact:true})).toBeVisible();
 const columns=page.locator('.answer-columns');
 const left=await columns.locator('form').boundingBox(),right=await columns.locator(':scope > div').boundingBox();
 expect(right.x).toBeGreaterThan(left.x);
 expect(Math.abs(left.y-right.y)).toBeLessThan(3);
 await page.getByRole('button',{name:'Save answer',exact:true}).click();
 expect(await page.evaluate(()=>window.sent[0].body)).toMatchObject({share_with_partner:true,value:'Time together'});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 if(width===414)await page.screenshot({path:'test-results/adjacent-answers-414.png',fullPage:true});
 await mount(page,'calendar',{lock_in_id:'p',editable:true,alignment:{my_missing:[],partner_missing:[],mine:{},options:{diet:[],budget:[],cuisine:[]}},valid_slots:[{day:'Fri',meal_slot:'dinner'},{day:'Sat',meal_slot:'lunch'},{day:'Sun',meal_slot:'coffee'}],my_slots:[]});
 await expect(page.getByRole('group',{name:'Your weekend availability'})).toBeVisible();
 await page.getByLabel('Sat Lunch',{exact:true}).check();
 await expect(page.getByLabel('Sat Lunch',{exact:true})).toBeChecked();
 expect((await page.locator('.weekend-grid').boundingBox()).height).toBeLessThan(300);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 if(width===414)await page.screenshot({path:'test-results/calendar-414.png',fullPage:true});
});
