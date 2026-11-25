import {test,expect} from '@playwright/test';
import {signUpWithCode} from './fixtures/auth.js';
// 451efb5 (2026-11-23): each activity is a collapsible row, one open at a time.
// Open a row the way a member does (tap its name) before using its controls.
async function openActivity(page,name){
 const row=page.locator('details.activity-row').filter({has:page.locator('.activity-name',{hasText:new RegExp('^'+name+'$')})});
 if(!(await row.evaluate(d=>d.open)))await row.locator('summary').click();
}
test('own Chemistry answers and partner indifference survive saving; four custom limit',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Sign up',exact:true}).click();
 await signUpWithCode(page);
 await page.getByRole('button',{name:'Family',exact:true}).click();await page.getByRole('button',{name:'Continue to Stats'}).click();await page.getByRole('button',{name:'Continue to Chemistry'}).click();
 await openActivity(page,'Hiking');await page.locator('input[name=partner_any][value=Hiking]').check();
 for(const name of ['Marathon running','Singing','Chess','Gardening']){
  await page.locator('#custom-activity').fill(name);await page.getByRole('button',{name:'Add activity',exact:true}).click();
  await openActivity(page,name);await page.locator('label.bucket-pick').filter({has:page.locator('input[name="act__'+name+'"][value=good]')}).click();
 }
 await expect(page.locator('#add-activity')).toBeDisabled();
 await openActivity(page,'Marathon running');await page.locator('input[name=partner_any][value="Marathon running"]').check();
 await page.getByRole('button',{name:'Save chemistry',exact:true}).click();await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'../outputs/chemistry-updated-signup.png',fullPage:true});
 await page.getByRole('button',{name:'Continue to Verification'}).click();await expect(page.getByRole('heading',{name:'Step 4 of 4 · Verification'})).toBeVisible();
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'../outputs/verification-current-signup.png',fullPage:true});
 await page.evaluate(async()=>{
  const {render}=await import('/src/screens/verification.js');
  const safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  document.querySelector('.bgv-compact').outerHTML=render({safe,data:{enabled:true,environment:'preproduction',results:[],bundle:{enabled:true},digilocker:{enabled:true,environment:'preproduction',session:null,consent_text:'I agree to share my Aadhaar details, photo and available PAN records through Signzy for verification.'},face:{enabled:true,operation:'liveness_secure',state:'not_started',reference_ready:false,can_request:false,message:'Complete DigiLocker with photo sharing first.'}}});
 });
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'../outputs/verification-enabled-start.png',fullPage:true});
 await page.getByRole('button',{name:'Previous step'}).click();await expect(page.locator('input[name=partner_any][value=Hiking]')).toBeChecked();
 await expect(page.locator('input[name="act__Marathon running"][value=good]')).toBeChecked();
 await openActivity(page,'Gardening');await page.getByRole('button',{name:'Remove Gardening',exact:true}).click();await expect(page.locator('#add-activity')).toBeEnabled();
 await page.setViewportSize({width:320,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
