import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const base=new URL('../../admin_dashboard/',import.meta.url);
test('metric list, account detail, refresh and back',async({page})=>{
 const requests=[];
 await page.route('**/admin-preview',r=>r.fulfill({contentType:'text/html',body:readFileSync(new URL('templates/dashboard.html',base),'utf8')}));
 await page.route('**/static/dashboard.*',r=>{const name=r.request().url().split('/').pop();return r.fulfill({contentType:name.endsWith('.js')?'text/javascript':'text/css',body:readFileSync(new URL('static/'+name,base),'utf8')});});
 await page.route('**/api/**',r=>{
 const u=new URL(r.request().url());requests.push(u.pathname+u.search);let data={generated_at:1794042000};
 if(u.pathname==='/api/session')data={email:'synthetic@example.test',role:'owner',sections:['overview','users','checks'],csrf:'synthetic'};
 else if(u.pathname.endsWith('/overview'))data={...data,metrics:[{label:'Phone verified',value:1,note:'Synthetic',filter:'phone_verified'}]};
 else if(u.pathname.endsWith('/users'))data={...data,rows:[{user_id:'synthetic-user',phone:'•••• 0001'}],has_more:false};
 else if(u.pathname==='/api/user-summary')data={...data,account:[{user_id:'synthetic-user',bgv_status:'declared'}],checks:[]};
 else if(u.pathname.endsWith('/checks'))data={...data,rows:[{operation:'criminal',environment:'preproduction',state:'completed',checks:1}]};
 else if(u.pathname==='/api/check-records')data={...data,rows:[{user_id:'synthetic-user',state:'completed'}],has_more:false};
 return r.fulfill({json:data});});
 await page.goto('/admin-preview');await page.getByRole('button',{name:'View Phone verified'}).click();expect(requests.some(x=>x.includes('filter=phone_verified'))).toBe(true);
 await page.getByRole('button',{name:'synthetic-user'}).click();await expect(page.getByRole('heading',{name:'User support summary'})).toBeVisible();
 await page.getByRole('button',{name:'Refresh report'}).click();await expect(page.getByRole('heading',{name:'Account',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'← Back to list'}).click();await page.getByRole('button',{name:'← Back to overview'}).click();
 await page.screenshot({path:'../outputs/password-login/dashboard-links.png',fullPage:true});
 await page.getByRole('button',{name:'Verification & errors',exact:true}).click();await page.getByRole('button',{name:'1',exact:true}).click();
 expect(requests.some(x=>x.includes('/api/check-records?'))).toBe(true);await expect(page.getByRole('button',{name:'synthetic-user'})).toBeVisible();
});
