import {Browser} from '@capacitor/browser';
let listener=null;
export function render(data,safe,busy=false){
 if(!data?.required)return '';
 if(data.can_begin)return '<section class="card verification-payment"><h2>Verification test payment</h2><p role="status">Confirmed · ₹0 real money deducted.</p></section>';
 return `<section class="card verification-payment"><h2>Begin verification</h2><p>${safe(data.message||'Test checkout status is unavailable. Check for updates.')}</p>
 ${data.enabled&&['not_started','expired','cancelled'].includes(data.state)?`<button type="button" id="verification-pay-start" class="primary" ${busy?'disabled':''}>Begin verification · test payment</button>`:''}
 ${data.checkout_url?`<button type="button" id="verification-pay-open" class="primary" ${busy?'disabled':''}>Continue test payment</button><button type="button" class="secondary" id="verification-pay-check" ${busy?'disabled':''}>I’ve paid · Check confirmation</button>`:''}
 ${['creating','outcome_unknown'].includes(data.state)?'<p role="status">Checkout is being confirmed. Do not start another payment.</p>':''}</section>`;
}
export function bind(root,{session,run},data,refresh,browser=Browser){
 const complete=async()=>{await session.post('/api/v1/verification/payment/complete',{});await refresh();};
 const open=async next=>{
  if(!next.checkout_url)return;
  const url=new URL(next.checkout_url);
  if(url.protocol!=='https:'||!['rzp.io','rzp.in'].includes(url.hostname)||url.username||url.password)throw Error('Invalid test checkout link.');
  if(listener){await listener.remove();listener=null;}
  listener=await browser.addListener('browserFinished',()=>{const previous=listener;listener=null;previous?.remove();run(complete);});
  await browser.open({url:url.href});
 };
 root.querySelector('#verification-pay-start')?.addEventListener('click',()=>run(async()=>{const next=await session.post('/api/v1/verification/payment/start',{});await refresh();await open(next);}));
 root.querySelector('#verification-pay-open')?.addEventListener('click',()=>run(()=>open(data)));
 root.querySelector('#verification-pay-check')?.addEventListener('click',()=>run(complete));
}
