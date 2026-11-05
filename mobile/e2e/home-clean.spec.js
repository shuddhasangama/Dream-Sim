import {test,expect} from '@playwright/test';
test('Home bounds avatar, keeps disclosures in Stats and allows changing an accepted option',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await page.evaluate(async()=>{
  const home=await import('/src/screens/home.js'),stats=await import('/src/statsFields.js');
  const root=document.querySelector('#app');
  const photo='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1536"><rect width="1024" height="1536" fill="#d9b87c"/></svg>');
  const ctx={journey:{user:{user_id:'synthetic',display_name:'Example Person'},own_avatar:{photo}},safe:x=>String(x??''),busy:false,folds:{vision:{data:{goals:[]}},chemistry:{data:{}}},statsSummary:{rows:[]},statsFields:stats,
   session:{get:async path=>path.endsWith('/personal')?{categories:{mobility:'Mobility'},ethnicity_options:['Indian'],ethnicity:[],health:{}}:{rows:[]}},
   navigateTo:key=>window.destination=key,setDashboardStats:value=>{ctx.dashboardStats=value;},run:async fn=>{await fn();paint();}};
  const paint=()=>{root.innerHTML=home.render(ctx);home.bind(root,ctx);};paint();window.avatarPhoto=photo;
 });
 const avatar=page.getByRole('button',{name:'Choose your avatar'});await expect(avatar).toBeVisible();
 const bounds=await avatar.boundingBox();expect(bounds.width).toBe(52);expect(bounds.height).toBe(52);
 const image=await avatar.locator('img').boundingBox();expect(image.width).toBe(52);expect(image.height).toBe(52);
 await expect(page.getByText('Private identity check',{exact:true})).toHaveCount(0);await expect(page.locator('#portrait-file')).toHaveCount(0);
 await expect(page.getByText('Ethnicity / cultural background',{exact:true})).toHaveCount(0);
 await page.screenshot({path:'../outputs/home-clean.png',fullPage:true});
 await avatar.click();expect(await page.evaluate(()=>window.destination)).toBe('avatar');
 await page.locator('[data-ring=stats]').click();await page.getByRole('button',{name:/Edit stats/}).click();
 await expect(page.getByRole('heading',{name:'Ethnicity / cultural background'})).toBeVisible();await expect(page.getByRole('heading',{name:'Health & accessibility'})).toBeVisible();await expect(page.locator('#portrait-file')).toHaveCount(0);
 await page.evaluate(async()=>{
  const flow=await import('/src/screens/avatar.js');const root=document.querySelector('#app');let data={enabled:true,state:'accepted',selected:0,options:[window.avatarPhoto,window.avatarPhoto],avatar:{photo:window.avatarPhoto}};
  const paint=()=>{root.innerHTML=flow.render({data,safe:x=>String(x??'')});flow.bind(root,{data,session:{post:async(path,body)=>({...data,selected:body.index})},run:async fn=>fn(),patch:next=>{data=next;window.selectedAvatar=next.selected;paint();}});};paint();
 });
 await expect(page.locator('[data-avatar-accept]')).toHaveCount(2);await page.locator('[data-avatar-accept="1"]').click();expect(await page.evaluate(()=>window.selectedAvatar)).toBe(1);
 await expect(page.locator('#avatar-generate')).toHaveCount(0);
});
