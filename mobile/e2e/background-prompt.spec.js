import {test,expect} from '@playwright/test';
// Ethnicity-restore fallback: the one-time "Please confirm your background details"
// card on Home (server decides via journey.background_prompt, behind
// DHASHU_ETHNICITY_PROMPT). Rendered the same way home-clean.spec.js renders Home.
async function mountHome(page,backgroundPrompt){
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await page.evaluate(async(show)=>{
  const home=await import('/src/screens/home.js'),stats=await import('/src/statsFields.js');
  const root=document.querySelector('#app');window.calls=[];
  const ctx={journey:{user:{user_id:'synthetic',display_name:'Example Person'},background_prompt:show},safe:x=>String(x??''),busy:false,
   folds:{vision:{data:{goals:[]}},chemistry:{data:{}}},statsSummary:{rows:[]},statsFields:stats,
   session:{get:async path=>{window.calls.push('GET '+path);return path.endsWith('/personal')?{categories:{},ethnicity_options:['Indian'],ethnicity:[],health:{}}:{rows:[]};},
            post:async path=>{window.calls.push('POST '+path);return {background_prompt:false};}},
   navigateTo:key=>window.destination=key,setDashboardStats:value=>{ctx.dashboardStats=value;},getDashboardStats:()=>ctx.dashboardStats,
   toggleFold:()=>{},screens:{},run:async fn=>{await fn();paint();}};
  const paint=()=>{root.innerHTML=home.render(ctx);home.bind(root,ctx);};paint();
 },backgroundPrompt);
}
test('the background prompt shows only when the server asks for it',async({page})=>{
 await mountHome(page,false);
 await expect(page.getByText('Please confirm your background details')).toHaveCount(0);
 await mountHome(page,true);
 await expect(page.getByRole('heading',{name:'Please confirm your background details'})).toBeVisible();
 await expect(page.getByText('It is optional')).toBeVisible();
});
test('Review opens the Stats editor where Background & health lives',async({page})=>{
 await mountHome(page,true);
 await page.getByRole('button',{name:'Review background'}).click();
 await expect(page.locator('#personal-form summary',{hasText:'Ethnicity / cultural background'})).toBeVisible();
 expect(await page.evaluate(()=>window.calls)).toEqual(expect.arrayContaining(['GET /api/v1/profile/stats','GET /api/v1/profile/personal']));
});
test('Not now dismisses it once, on the server, and the card goes away',async({page})=>{
 await mountHome(page,true);
 await page.getByRole('button',{name:'Not now'}).click();
 await expect(page.getByText('Please confirm your background details')).toHaveCount(0);
 expect(await page.evaluate(()=>window.calls.filter(c=>c.startsWith('POST')))).toEqual(['POST /api/v1/profile/background-prompt/dismiss']);
});
