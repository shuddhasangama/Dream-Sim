import {test,expect} from '@playwright/test';
async function mount(page,scenario='capture'){
 await page.goto('/');
 await page.evaluate(async scenario=>{
  const screen=await import('/src/screens/avatar.js');const root=document.createElement('main');root.className='container';document.body.replaceChildren(root);
  window.sent=[];window.pickSources=[];let data={enabled:true,state:'not_started',can_capture:true,options:[],consent_text:'Send only this selfie to OpenAI.',consent_version:'selfie-avatar-v1'};let busy=false;
  const takePhoto=async options=>{window.pickSources.push(options.source);if(scenario==='denied')throw Error('Permission denied');if(scenario==='cancel')throw Error('User cancelled');await new Promise(r=>setTimeout(r,50));const c=document.createElement('canvas');c.width=320;c.height=400;return {dataUrl:c.toDataURL('image/jpeg')};};
  function paint(){root.innerHTML=screen.render({data,safe:v=>String(v??''),busy});screen.bind(root,{data,session:{post:async(path,body)=>window.sent.push({path,body}),get:async()=>({...data,state:'queued',can_capture:false,options:[]})},patch:next=>{data=next;},run:async fn=>{if(busy)return;busy=true;paint();try{await fn();}finally{busy=false;paint();}}},takePhoto);}
  paint();
 },scenario);
}
test('empty preview is hidden; capture survives the busy redraw and stays private until consent',async({page})=>{
 await mount(page);await expect(page.locator('#avatar-selfie')).toBeHidden();await page.getByRole('button',{name:'Capture latest selfie'}).click();
 await expect(page.getByAltText('Review your private selfie')).toBeVisible();await expect(page.locator('#avatar-generate')).toBeEnabled();expect(await page.evaluate(()=>window.sent)).toEqual([]);
 await page.locator('#avatar-generate').click();await expect(page.locator('#avatar-note')).toContainText('consent first');expect(await page.evaluate(()=>window.sent)).toEqual([]);
 await page.locator('#avatar-consent').check();await page.locator('#avatar-generate').click();expect((await page.evaluate(()=>window.sent)).map(x=>x.path)).toEqual(['/api/v1/profile/avatar/selfie','/api/v1/profile/avatar/generate']);
});
test('Photos fallback stages a photo with the same explicit consent',async({page})=>{
 await mount(page);await page.getByRole('button',{name:'Choose recent selfie from Photos'}).click();await expect(page.locator('#avatar-selfie')).toBeVisible();expect(await page.evaluate(()=>window.pickSources)).toEqual(['PHOTOS']);expect(await page.evaluate(()=>window.sent)).toEqual([]);
});
test('denied camera and cancellation leave retry controls usable without a blank preview',async({page})=>{
 await mount(page,'denied');await page.locator('#avatar-camera').click();await expect(page.locator('#avatar-note')).toContainText('permission is blocked');await expect(page.locator('#avatar-selfie')).toBeHidden();await expect(page.locator('#avatar-photos')).toBeEnabled();
 await mount(page,'cancel');await page.locator('#avatar-camera').click();await expect(page.locator('#avatar-note')).toContainText('cancelled');await expect(page.locator('#avatar-generate')).toBeDisabled();expect(await page.evaluate(()=>window.sent)).toEqual([]);
});
