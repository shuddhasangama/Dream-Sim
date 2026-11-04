import {Browser} from '@capacitor/browser';
let returnListener=null;
export async function load(session){
 try{return await session.get('/api/v1/profile/liveness');}
 catch(error){if(![404,503].includes(error?.status))throw error;return session.get('/api/v1/profile/face-match');}
}
export function render(data,safe){
 if(!data)return '';
 if(data.operation==='liveness_secure')return `<section class="card face-comparison"><h2>Live face verification</h2><p role="status">${safe(data.message)}</p>
 ${data.match_percentage!=null?`<p>Face match: ${safe(data.match_percentage)}% · Liveness: ${safe(data.liveness)}</p>`:''}
 ${data.enabled&&data.state==='not_started'?`${!data.reference_ready?'<p>Complete DigiLocker photo sharing first.</p>':''}<label class="checkbox-row"><input type="checkbox" id="face-match-consent"> I agree to live capture and comparison with my Aadhaar photo.</label><details><summary>How this check works</summary><p>${safe(data.consent_text)}</p></details><button type="button" id="face-match-start" ${data.can_request?'':'disabled'}>Start face verification</button>`:''}
 ${data.capture_url?'<button type="button" id="face-hosted-open">Open Signzy capture</button>':''}
 ${data.can_complete?'<button type="button" id="face-hosted-complete">I’ve finished · Check result</button>':''}
 <p id="face-match-note" role="status"></p><button type="button" id="face-match-refresh" class="secondary">Refresh face status</button><p class="hint">Sandbox check · Overall account approval is separate.</p></section>`;
 return `<section class="card face-comparison"><h2>Selfie → Aadhaar</h2><p role="status">${safe(data.message)}</p>
 ${data.match_percentage!=null?`<p>Signzy match score: ${safe(data.match_percentage)}%</p>`:''}
 <p class="hint">Sandbox face comparison · Liveness not checked. This does not approve your account or block the other test journeys.</p>
 ${data.enabled&&data.state==='not_started'?`${!data.reference_ready?'<p>Complete DigiLocker with photo sharing first.</p>':''}${!data.selfie_ready?'<p>Capture and submit your latest selfie from Home → Your AI avatar.</p>':''}
 <label class="checkbox-row"><input type="checkbox" id="face-match-consent"> ${safe(data.consent_text)}</label><p id="face-match-note" role="status"></p><button type="button" id="face-match-start" ${data.can_request?'':'disabled'}>Compare selfie with Aadhaar</button>
 ${data.selfie_ready&&data.reference_ready&&!data.can_request?'<p>Submit your avatar generation to lock the current selfie before comparison.</p>':''}`:''}
 ${!data.enabled?'<p>Face comparison is being configured.</p>':''}<button type="button" id="face-match-refresh" class="secondary">Refresh face status</button></section>`;
}
export async function waitForStatus(session,current,pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))){
 let next=current;
 for(let i=0;i<12&&['queued_create','creating','queued_get','retrieving'].includes(next.state);i++){
  await pause(700);next=await session.get('/api/v1/profile/liveness');
 }
 return next;
}
export function bind(root,{session,run},data,refresh,browser=Browser,pause){
 if(data?.operation==='liveness_secure'){
  const complete=async flow=>{const next=await session.post('/api/v1/profile/liveness/complete',{session_id:flow});await waitForStatus(session,next,pause);await refresh();};
  const open=async face=>{
   if(!face.capture_url)return;
   const url=new URL(face.capture_url);
   if(url.protocol!=='https:'||url.hostname!=='liveliness-preproduction.signzy.app'||url.username||url.password)throw Error('Invalid Signzy capture link.');
   if(returnListener){await returnListener.remove();returnListener=null;}
   returnListener=await browser.addListener('browserFinished',()=>{
    const listener=returnListener;returnListener=null;listener?.remove();
    run(()=>complete(face.session_id));
   });
   await browser.open({url:url.href});
  };
  root.querySelector('#face-match-refresh')?.addEventListener('click',()=>run(async()=>{await waitForStatus(session,data,pause);await refresh();}));
  root.querySelector('#face-match-start')?.addEventListener('click',()=>{
   if(!root.querySelector('#face-match-consent')?.checked){root.querySelector('#face-match-note').textContent='Confirm Signzy consent first.';return;}
   run(async()=>{const next=await session.post('/api/v1/profile/liveness',{consent:true,consent_version:data.consent_version});const ready=await waitForStatus(session,next,pause);await refresh();await open(ready);});
  });
  root.querySelector('#face-hosted-open')?.addEventListener('click',()=>run(()=>open(data)));
  root.querySelector('#face-hosted-complete')?.addEventListener('click',()=>run(()=>complete(data.session_id)));
  return;
 }
 root.querySelector('#face-match-refresh')?.addEventListener('click',()=>run(refresh));
 root.querySelector('#face-match-start')?.addEventListener('click',()=>{
  if(!root.querySelector('#face-match-consent').checked){root.querySelector('#face-match-note').textContent='Confirm Signzy consent first.';return;}
  run(async()=>{try{await session.post('/api/v1/profile/face-match',{consent:true,consent_version:data.consent_version});}finally{await refresh();}});
 });
}
