import {test,expect} from '@playwright/test';
test('account-bound test payment leads verification and browser return checks provider confirmation',async({page})=>{
 await page.goto('/');
 await page.evaluate(async()=>{
  const screen=await import('/src/screens/verification.js'),payment=await import('/src/verificationPayment.js');
  const root=document.querySelector('#app'),safe=x=>String(x??'');
  let data={enabled:true,payment:{required:true,enabled:true,can_begin:false,state:'not_started',message:'Test payment only — ₹0 real money deducted. Razorpay shows a simulated ₹1 payment.'},digilocker:{enabled:true,consent_text:'I agree to share Aadhaar details and available PAN records.'},results:[]};
  window.paymentCalls=[];window.paymentOpened=[];
  const session={post:async path=>{window.paymentCalls.push(path);if(path.endsWith('/start'))data.payment={...data.payment,state:'pending',checkout_url:'https://rzp.io/i/synthetic-test-link'};else data.payment={...data.payment,can_begin:true,state:'paid',checkout_url:null};return data.payment;}};
  const browser={open:async x=>window.paymentOpened.push(x.url),addListener:async(name,fn)=>{window.paymentReturn=fn;return {remove:async()=>{}};}};
  let busy=false;
  const paint=()=>{root.innerHTML=screen.render({data,safe,busy});payment.bind(root,{session,run:async fn=>{if(busy)return;busy=true;paint();try{await fn();}finally{busy=false;paint();}}},data.payment,async()=>paint(),browser);};paint();
 });
 await expect(page.locator('#digilocker-start')).toHaveCount(0);
 await page.screenshot({path:'../outputs/verification-payment-top.png',fullPage:true});
 await page.getByRole('button',{name:'Begin verification · test payment',exact:true}).click();
 expect(await page.evaluate(()=>window.paymentOpened)).toEqual(['https://rzp.io/i/synthetic-test-link']);
 await expect(page.locator('#digilocker-start')).toHaveCount(0);
 await page.evaluate(()=>window.paymentReturn());
 await expect(page.locator('#digilocker-start')).toBeVisible();
 await expect(page.getByText('Confirmed · ₹0 real money deducted.',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>window.paymentCalls)).toEqual(['/api/v1/verification/payment/start','/api/v1/verification/payment/complete']);
 await page.screenshot({path:'../outputs/verification-payment-confirmed.png',fullPage:true});
});
