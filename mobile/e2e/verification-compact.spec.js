import {test,expect} from '@playwright/test';
const fixture={enabled:true,environment:'preproduction',bundle:{enabled:true,consented:true,employer_declared:true,pan_state:'received',mobile_available:true,declared_age:34},digilocker:{enabled:true,session:{state:'complete',reference_photo_available:true,identity:{name:'Arjun Mehta',age:42,dob:'1984-01-01',document_address:'SYNTHETIC DOCUMENT ADDRESS'}}},results:[{operation:'current_employer',environment:'preproduction',state:'processing',message:'Confirming your declared employer'},{operation:'individual_result',environment:'preproduction',state:'needs_review',message:'Result received for review'},{operation:'fir_search',environment:'preproduction',state:'queued',message:'Checking available records'}]};
async function preview(page,data=fixture){
 await page.goto('/');await page.getByLabel('Phone number').waitFor();
 await page.evaluate(async data=>{
  const {render}=await import('/src/screens/verification.js');
  const safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  document.querySelector('#app').innerHTML=render({data,safe});
 },data);
}
test('compact verification fits a narrow screen and keeps private address collapsed',async({page})=>{
 await preview(page);
 await expect(page.locator('.bgv-row')).toHaveCount(7);
 await expect(page.getByText('SYNTHETIC DOCUMENT ADDRESS')).not.toBeVisible();
 await expect(page.getByText('Review age',{exact:true})).toBeVisible();
 await expect(page.getByText('Setup needed',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'../outputs/bgv-compact-preview.png',fullPage:true});
 await page.getByText('View document details',{exact:true}).click();
 await expect(page.getByText('SYNTHETIC DOCUMENT ADDRESS')).toBeVisible();
 await page.setViewportSize({width:320,height:740});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('legacy Aadhaar identity asks for screening consent without manual PAN entry',async({page})=>{
 await preview(page,{...fixture,bundle:{enabled:true,consented:false,employer_declared:false,pan_state:'not_requested',consent_text:'Synthetic screening consent'},results:[]});
 await expect(page.getByRole('button',{name:'Start relevant checks'})).toBeVisible();
 await expect(page.locator('input[name=panNumber],input[name=address]')).toHaveCount(0);
 await expect(page.locator('input[name=consent]')).not.toBeChecked();
});

test('exact checks and source employment history have distinct outcomes',async({page})=>{
 await preview(page,{...fixture,results:[{operation:'current_employer',environment:'preproduction',state:'history_available',message:'Last recorded employer: Synthetic Ltd (20 May 2021 to 23 May 2022; 1 year, 3 days). This historical record does not establish your current employment status.'},{operation:'individual_result',environment:'preproduction',state:'verified',message:'Verified: completed exact search returned zero cases.'},{operation:'fir_result',environment:'preproduction',state:'needs_review',message:'Exact search returned 2 case candidate(s). Review is required before this check can be verified.'}]});
 await expect(page.getByText('History found',{exact:true})).toBeVisible();
 await expect(page.getByText('Verified',{exact:true})).toBeVisible();
 await expect(page.getByText(/1 year, 3 days/)).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'../outputs/bgv-exact-history-preview.png',fullPage:true});
});
