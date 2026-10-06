import {test,expect} from '@playwright/test';

async function mount(page,cancel=false){
 await page.goto('/');
 await page.evaluate(async(cancel)=>{
  const screen=await import('/src/screens/identity.js');
  const root=document.createElement('main');root.className='container';document.body.replaceChildren(root);
  window.sent=[];
  const data={enabled:true,status:'not_captured',consent_text:'I consent to private storage and BGV review.',consent_version:'identity-image-v1'};
  const ctx={data,safe:v=>String(v??''),session:{post:async(path,body)=>{window.sent.push({path,body});}},run:async fn=>fn()};
  root.innerHTML=screen.render(ctx);
  screen.bindPanel(root,ctx,data,async()=>{},async()=>{
   if(cancel)throw new Error('User cancelled');
   const canvas=document.createElement('canvas');canvas.width=320;canvas.height=400;
   return {dataUrl:canvas.toDataURL('image/jpeg')};
  });
 },cancel);
}
test('capture preview stays local until explicit consent and save',async({page})=>{
 await page.setViewportSize({width:375,height:812});await mount(page);
 await expect(page.getByRole('button',{name:'Save private image'})).toBeDisabled();
 await page.getByRole('button',{name:'Take a face photo'}).click();
 await expect(page.getByAltText('Review your identity image before uploading')).toBeVisible();
 expect(await page.evaluate(()=>window.sent)).toEqual([]);
 await page.getByRole('button',{name:'Save private image'}).click();
 expect(await page.evaluate(()=>window.sent)).toEqual([]);
 await page.getByRole('checkbox').check();
 await page.getByRole('button',{name:'Save private image'}).click();
 const sent=await page.evaluate(()=>window.sent);
 expect(sent).toHaveLength(1);expect(sent[0].body.consent).toBe(true);
 expect(sent[0].body.image).toContain('data:image/jpeg;base64,');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
test('cancelling camera does not upload or strand the capture control',async({page})=>{
 await mount(page,true);await page.getByRole('button',{name:'Take a face photo'}).click();
 await expect(page.getByRole('button',{name:'Take a face photo'})).toBeEnabled();
 await expect(page.getByRole('button',{name:'Save private image'})).toBeDisabled();
 expect(await page.evaluate(()=>window.sent)).toEqual([]);
});
