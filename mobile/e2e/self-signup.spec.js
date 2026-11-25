import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/signup-options.json',import.meta.url),'utf8'));
test('fresh signup uses the three-city Stats form and resumes the saved step',async({page})=>{
 await page.goto('/');
 await page.evaluate(async fixture=>{
  const {createSignup}=await import('/src/signup.js');
  const root=document.querySelector('#app'),safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  let saved={modern:true,version:3,next_step:0,values:{},options:fixture.stats},vision={...fixture.vision,goals:[]},chemistry={activities:{},activity_options:['Cooking','Hiking','Tennis','Yoga'],buckets:[['good','★','Already good'],['improve','↑','Want to improve'],['maybe','?','Maybe'],['no','×','Not for me']]};
  window.signupRequests=[];
  const session={get:async path=>{if(path.endsWith('/signup/state'))return structuredClone(saved);if(path.endsWith('/profile/vision'))return structuredClone(vision);if(path.endsWith('/profile/chemistry'))return structuredClone(chemistry);if(path.endsWith('/profile/avatar'))return {enabled:true,state:'not_started',can_capture:true,options:[]};if(path.endsWith('/verification/digilocker'))return {enabled:true,consent_text:'Synthetic consent'};return {enabled:false,results:[]};},
   put:async(path,body)=>{window.signupRequests.push({path,body});if(path.endsWith('/vision/template')){vision={...vision,goals:Object.entries(body.pillars).map(([key,stance])=>({key,stance})),template_key:body.template,schema_version:2};saved.next_step=1;return vision;}if(path.endsWith('/signup/stats')){saved={...saved,next_step:2,values:{...body.fields,age:body.age,gender:body.gender,city:body.city,health:body.health}};return structuredClone(saved);}chemistry={...chemistry,...body};saved.next_step=3;return structuredClone(chemistry);}};
  let wizard;const paint=()=>{root.innerHTML=wizard.render();wizard.bind(root);};const run=async fn=>{await fn();paint();};
  window.restartSignup=async()=>{wizard=createSignup({session,run,safe,finish:async()=>{}});await wizard.begin();paint();};await window.restartSignup();
 },fixture);
 await page.getByRole('button',{name:'Family',exact:true}).click();await page.getByRole('button',{name:'Continue to Stats'}).click();
 await expect(page.locator('select[name=city] option')).toHaveText(['Choose your city','Bangalore','Delhi','Mumbai']);
 await expect(page.locator('[name=country],[name=children_count]')).toHaveCount(0);
 await page.locator('[name=age]').fill('35');   // 451efb5: age replaces name + date of birth (name comes from DigiLocker)
 await page.locator('[name=gender]').selectOption('female');await page.locator('[name=city]').selectOption('Delhi');
 await page.getByRole('button',{name:'Save and continue',exact:true}).click();
 // 056139e: a confirmed save now continues to the next step (only after the server's read-back).
 await expect(page.getByRole('heading',{name:'Step 3 of 4 · Chemistry'})).toBeVisible();
 await page.screenshot({path:'../outputs/self-signup-stats.png',fullPage:true});
 await page.evaluate(()=>window.restartSignup());await expect(page.getByRole('heading',{name:'Step 3 of 4 · Chemistry'})).toBeVisible();
 // 451efb5: each activity is a collapsible row; open it like a member before answering.
 for(const activity of ['Cooking','Hiking','Tennis','Yoga']){const row=page.locator('details.activity-row').filter({has:page.locator('.activity-name',{hasText:new RegExp('^'+activity+'$')})});if(!(await row.evaluate(d=>d.open)))await row.locator('summary').click();await page.locator('label.bucket-pick').filter({has:page.locator('input[name="act__'+activity+'"][value=good]')}).click();}
 await page.getByRole('button',{name:'Save chemistry',exact:true}).click();await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Continue to Verification'}).click();await expect(page.getByRole('heading',{name:'Step 4 of 4 · Verification'})).toBeVisible();
 await page.getByRole('button',{name:'Previous step'}).click();await page.getByRole('button',{name:'Previous step'}).click();await expect(page.locator('[name=city]')).toHaveValue('Delhi');await expect(page.locator('[name=age]')).toHaveValue('35');
 await page.setViewportSize({width:320,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
