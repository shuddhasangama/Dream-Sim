import {test,expect} from '@playwright/test';
async function mount(page,pending=false){
 await page.goto('/');
 await page.evaluate(async pending=>{
  const face=await import('/src/faceMatch.js');const root=document.createElement('main');document.body.replaceChildren(root);
  let data={enabled:true,operation:'liveness_secure',state:'not_started',can_request:true,reference_ready:true,consent_version:'hosted-liveness-aadhaar-v1',consent_text:'Signzy captures and compares with Aadhaar.'};
  let busy=false;window.calls=[];window.opened=[];window.listenerRemoved=0;
  const session={get:async()=>{if(data.state==='queued_create')data={...data,state:'awaiting_capture',session_id:'flow-123',capture_url:'https://liveliness-preproduction.signzy.app/consumer/test/token/private',can_complete:true};else if(data.state==='queued_get')data={...data,state:pending?'pending':'matched',capture_url:null,can_complete:false,liveness:pending?'pending':'passed',match_percentage:pending?null:99,combined_passed:!pending,message:pending?'Capture is not complete yet.':'Liveness and Aadhaar face match passed.'};return {...data};},post:async(path,body)=>{window.calls.push({path,body});data={...data,state:path.endsWith('/complete')?'queued_get':'queued_create'};return {...data};}};
  const browser={addListener:async(name,callback)=>{window.returnFromSignzy=callback;return {remove:async()=>window.listenerRemoved++};},open:async value=>window.opened.push(value.url)};
  const refresh=async()=>{data=await session.get();};
  function paint(){root.innerHTML=face.render(data,x=>String(x??''));face.bind(root,{session,run:async action=>{if(busy)return;busy=true;paint();try{await action();}finally{busy=false;paint();}}},data,refresh,browser,async()=>{});}
  paint();
 },pending);
}

test('consent creates one hosted link; closing browser triggers bound get and saves passed result',async({page})=>{
 await mount(page);await page.locator('#face-match-start').click();await expect(page.locator('#face-match-note')).toContainText('consent');expect(await page.evaluate(()=>window.calls)).toEqual([]);
 await page.locator('#face-match-consent').check();await page.locator('#face-match-start').click();await expect.poll(()=>page.evaluate(()=>window.opened.length)).toBe(1);
 expect((await page.evaluate(()=>window.calls)).map(x=>x.path)).toEqual(['/api/v1/profile/liveness']);
 await page.evaluate(()=>window.returnFromSignzy());await expect(page.locator('.face-comparison')).toContainText('99%');await expect(page.locator('.face-comparison')).toContainText('Liveness: passed');
 const sent=await page.evaluate(()=>window.calls);expect(sent[1]).toEqual({path:'/api/v1/profile/liveness/complete',body:{session_id:'flow-123'}});expect(await page.evaluate(()=>window.listenerRemoved)).toBe(1);
 await page.locator('#face-match-refresh').click();expect((await page.evaluate(()=>window.calls)).length).toBe(2);
});

test('manual finish works after an interrupted return and pending response never shows verified',async({page})=>{
 await mount(page,true);await page.locator('#face-match-consent').check();await page.locator('#face-match-start').click();await expect(page.locator('#face-hosted-complete')).toBeVisible();await page.locator('#face-hosted-complete').click();await expect(page.locator('.face-comparison')).toContainText('Capture is not complete');await expect(page.locator('.face-comparison')).not.toContainText('Liveness: passed');expect((await page.evaluate(()=>window.calls)).length).toBe(2);
});

test('verified Signzy selfie loads into private avatar preview without generation',async({page})=>{
 await page.goto('/');const state=await page.evaluate(async()=>{
  const avatar=await import('/src/screens/avatar.js');const c=document.createElement('canvas');c.width=160;c.height=200;const image=c.toDataURL('image/jpeg');
  const data=await avatar.load({get:async path=>path.endsWith('/avatar')?{state:'not_started',enabled:true,can_capture:true,verified_selfie_preview:image,options:[]}:{operation:'liveness_secure',state:'matched'}});
  return {hasPreview:data._stagedSelfie===image,consent:data._avatarConsent===true};
 });expect(state).toEqual({hasPreview:true,consent:false});
});
