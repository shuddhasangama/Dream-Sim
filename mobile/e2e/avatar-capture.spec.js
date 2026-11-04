import {test,expect} from '@playwright/test';
async function mount(page,scenario='capture'){
 await page.goto('/');
 await page.evaluate(async scenario=>{
  const screen=await import('/src/screens/avatar.js');const root=document.createElement('main');root.className='container';document.body.replaceChildren(root);
  window.sent=[];window.pickSources=[];let data={enabled:true,state:'not_started',can_capture:true,options:[],consent_text:'Send only this selfie to OpenAI.',consent_version:'selfie-avatar-v1'};let busy=false;let server={...data};
  const takePhoto=async options=>{window.pickSources.push(options.source);if(scenario==='denied')throw Error('Permission denied');if(scenario==='cancel')throw Error('User cancelled');await new Promise(r=>setTimeout(r,50));const c=document.createElement('canvas');c.width=320;c.height=400;return {dataUrl:c.toDataURL('image/jpeg')};};
  function paint(){root.innerHTML=screen.render({data,safe:v=>String(v??''),busy});screen.bind(root,{data,session:{post:async(path,body)=>{window.sent.push({path,body});if(scenario==='upload-error'&&path.endsWith('/selfie'))throw Error('Photo save failed');if(path.endsWith('/generate')){server={...server,state:'queued',can_capture:false};if(scenario==='lost-response')throw Error('Connection lost');}return {...server};},get:async path=>{if(scenario==='offline')throw Error('Offline');if(path.endsWith('/face-match')){if(scenario==='face-error')throw Error('Face unavailable');return {};}return {...server};}},patch:next=>{data=next;},run:async fn=>{if(busy)return;busy=true;paint();try{await fn();}finally{busy=false;paint();}}},takePhoto);}
  paint();
 },scenario);
}
test('capture survives redraw; Generate appears only after consent and uploads once',async({page})=>{
 await mount(page);await expect(page.locator('#avatar-selfie')).toBeHidden();await expect(page.locator('#avatar-generate')).toBeHidden();await expect(page.locator('#avatar-photos')).toHaveCount(0);
 await page.locator('#avatar-camera').click();await expect(page.locator('#avatar-selfie')).toBeVisible();await expect(page.locator('#avatar-generate')).toBeHidden();expect(await page.evaluate(()=>window.sent)).toEqual([]);
 await page.locator('#avatar-consent').check();await expect(page.locator('#avatar-generate')).toBeVisible();await page.locator('#avatar-consent').uncheck();await expect(page.locator('#avatar-generate')).toBeHidden();await page.locator('#avatar-consent').check();await page.locator('#avatar-generate').click();
 await expect(page.locator('.avatar-flow')).toContainText('Your two avatars are queued.');expect((await page.evaluate(()=>window.sent)).map(x=>x.path)).toEqual(['/api/v1/profile/avatar/selfie','/api/v1/profile/avatar/generate']);expect(await page.evaluate(()=>window.pickSources)).toEqual(['CAMERA']);
});
test('refresh preserves selfie and consent with explicit feedback',async({page})=>{
 await mount(page);await page.locator('#avatar-camera').click();await page.locator('#avatar-consent').check();await page.locator('#avatar-refresh').click();await expect(page.locator('#avatar-selfie')).toBeVisible();await expect(page.locator('#avatar-consent')).toBeChecked();await expect(page.locator('#avatar-generate')).toBeVisible();await expect(page.locator('.avatar-flow')).toContainText('Status updated.');
});
test('failed upload keeps selfie and never requests paid generation',async({page})=>{
 await mount(page,'upload-error');await page.locator('#avatar-camera').click();await page.locator('#avatar-consent').check();await page.locator('#avatar-generate').click();await expect(page.locator('.avatar-flow')).toContainText('Photo save failed');await expect(page.locator('#avatar-selfie')).toBeVisible();expect((await page.evaluate(()=>window.sent)).map(x=>x.path)).toEqual(['/api/v1/profile/avatar/selfie']);
});
test('lost generation response reconciles queued state without replay',async({page})=>{
 await mount(page,'lost-response');await page.locator('#avatar-camera').click();await page.locator('#avatar-consent').check();await page.locator('#avatar-generate').click();await expect(page.locator('.avatar-flow')).toContainText('Your two avatars are queued.');await expect(page.locator('#avatar-generate')).toHaveCount(0);expect((await page.evaluate(()=>window.sent)).filter(x=>x.path.endsWith('/generate'))).toHaveLength(1);
});
test('refresh failure reports inline without clearing selfie',async({page})=>{
 await mount(page,'offline');await page.locator('#avatar-camera').click();await page.locator('#avatar-refresh').click();await expect(page.locator('.avatar-flow')).toContainText('Status could not be refreshed');await expect(page.locator('#avatar-selfie')).toBeVisible();
});
test('face endpoint failure does not block avatar refresh',async({page})=>{
 await mount(page,'face-error');await page.locator('#avatar-refresh').click();await expect(page.locator('.avatar-flow')).toContainText('Status updated.');await expect(page.locator('#avatar-camera')).toBeEnabled();
});
test('denied camera and cancellation keep capture usable',async({page})=>{
 await mount(page,'denied');await page.locator('#avatar-camera').click();await expect(page.locator('#avatar-note')).toContainText('permission is blocked');await expect(page.locator('#avatar-selfie')).toBeHidden();await expect(page.locator('#avatar-camera')).toBeEnabled();
 await mount(page,'cancel');await page.locator('#avatar-camera').click();await expect(page.locator('#avatar-note')).toContainText('cancelled');await expect(page.locator('#avatar-generate')).toBeHidden();expect(await page.evaluate(()=>window.sent)).toEqual([]);
});
