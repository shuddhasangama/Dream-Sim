import {test,expect} from '@playwright/test';
async function mount(page,mode){
 await page.goto('/');
 await page.evaluate(async mode=>{
  const {render}=await import('/src/screens/verification.js');
  const safe=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const identity={name:'Synthetic Private Name',age:36,dob:'1990-01-01',document_address:'SYNTHETIC PRIVATE ADDRESS'};
  const active=mode!=='start';
  const data={enabled:true,environment:'preproduction',bundle:{consented:true,employer_declared:true,pan_state:active?'received':'pending'},digilocker:{enabled:true,environment:'preproduction',consent_text:'I agree to share my Aadhaar details and available PAN records for verification.',session:active?{state:'complete',identity,reference_photo_available:true}:null},
   results:active?[{operation:'current_employer',state:'processing',environment:'preproduction',message:'Confirming available employment records'},{operation:'individual_result',state:'verified',environment:'preproduction',message:'Exact search completed: zero cases.'},{operation:'fir_result',state:'processing',environment:'preproduction',message:'Retrieving FIR result'}]:[],
   face:{enabled:true,operation:'liveness_secure',state:active?'matched':'not_started',reference_ready:active,can_request:false,message:active?'Liveness and Aadhaar face match passed.':'Complete DigiLocker first.'},
   avatar:{enabled:true,state:active?'submitting':'not_started',can_capture:!active,options:[]},_verificationFolds:[]};
  document.querySelector('#app').innerHTML=render({safe,data});
 },mode);
}
test('DigiLocker leads; live capture and avatar are minimizable',async({page})=>{
 await mount(page,'start');
 expect(await page.locator('#digilocker-start').evaluate(e=>e.getBoundingClientRect().top)).toBeLessThan(await page.locator('.bgv-checklist').evaluate(e=>e.getBoundingClientRect().top));
 await expect(page.getByText('Aadhaar is required. PAN is optional; salaried employment checks use PAN.')).toBeVisible();
 await expect(page.locator('#face-match-refresh,#avatar-refresh')).toHaveCount(0);
 await expect(page.locator('#verification-face')).not.toHaveAttribute('open','');
 await page.locator('#verification-face>summary').click();await expect(page.locator('#verification-face')).toHaveAttribute('open','');
 await page.screenshot({path:'../outputs/verification-redesign-start.png',fullPage:true});
});
test('processing jobs suppress duplicate buttons and private identity stays collapsed',async({page})=>{
 await mount(page,'working');
 await expect(page.getByText(/Checks are running in the background/)).toBeVisible();
 await expect(page.locator('#bgv-refresh,#face-match-refresh,#avatar-refresh,#avatar-generate,#avatar-camera')).toHaveCount(0);
 await expect(page.getByText('Synthetic Private Name',{exact:true})).not.toBeVisible();
 await page.locator('#verification-avatar>summary').click();
 await expect(page.getByText('Generating your two avatars…',{exact:true})).toBeVisible();
 await page.setViewportSize({width:320,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'../outputs/verification-redesign-working.png',fullPage:true});
});
test('signup status polling makes reads only and never replaces an earlier signup step',async({page})=>{
 await page.goto('/');
 const result=await page.evaluate(async()=>{
  const {createSignup}=await import('/src/signup.js');
  const calls=[];
  const plan={Intimacy:['Emotional','Physical'],'Travel together':[]};
  const vision={goals:Object.entries(plan).map(([key,stance])=>({key,stance})),schema_version:2,template_key:'explore',signup_presets:[{key:'explore',choices:plan,kids_intent:'undecided'}],signup_pillar_options:{Intimacy:['Emotional','Physical']}};
  const session={get:async path=>{calls.push(['GET',path]);return path.endsWith('/vision')?vision:path.endsWith('/stats')?{rows:[]}:path.endsWith('/chemistry')?{activities:{},activity_options:[],buckets:[]}:path.endsWith('/avatar')?{state:'submitting',options:[]}:{};},put:async(path)=>{calls.push(['PUT',path]);return vision;}};
  const root=document.querySelector('#app');let wizard;
  const safe=x=>String(x??'');const paint=()=>{root.innerHTML=wizard.render();wizard.bind(root);};
  const run=async action=>{await action();paint();};
  wizard=createSignup({session,safe,run,finish:async()=>{}});await wizard.begin();paint();
  calls.length=0;const initial=await wizard.refreshStatus();const initialCalls=calls.length;
  root.querySelector('[data-signup-plan=explore]').click();await new Promise(r=>setTimeout(r,0));
  for(let i=0;i<3;i++){root.querySelector('#signup-next').click();await new Promise(r=>setTimeout(r,0));}
  calls.length=0;const updated=await wizard.refreshStatus();
  return {initial,initialCalls,updated,calls};
 });
 expect(result.initial).toBe(false);expect(result.initialCalls).toBe(0);expect(result.updated).toBe(true);
 expect(result.calls.length).toBeGreaterThan(0);expect(result.calls.every(([method])=>method==='GET')).toBe(true);
});
