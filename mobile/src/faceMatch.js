export function render(data,safe){
 if(!data)return '';
 return `<section class="card face-comparison"><h2>Selfie → Aadhaar</h2><p role="status">${safe(data.message)}</p>
 ${data.match_percentage!=null?`<p>Signzy match score: ${safe(data.match_percentage)}%</p>`:''}
 <p class="hint">Sandbox face comparison · Liveness not checked. This does not approve your account or block the other test journeys.</p>
 ${data.enabled&&data.state==='not_started'?`${!data.reference_ready?'<p>Complete DigiLocker with photo sharing first.</p>':''}${!data.selfie_ready?'<p>Capture and submit your latest selfie from Home → Your AI avatar.</p>':''}
 <label class="checkbox-row"><input type="checkbox" id="face-match-consent"> ${safe(data.consent_text)}</label><p id="face-match-note" role="status"></p><button type="button" id="face-match-start" ${data.can_request?'':'disabled'}>Compare selfie with Aadhaar</button>
 ${data.selfie_ready&&data.reference_ready&&!data.can_request?'<p>Submit your avatar generation to lock the current selfie before comparison.</p>':''}`:''}
 ${!data.enabled?'<p>Face comparison is being configured.</p>':''}<button type="button" id="face-match-refresh" class="secondary">Refresh face status</button></section>`;
}
export function bind(root,{session,run},data,refresh){
 root.querySelector('#face-match-refresh')?.addEventListener('click',()=>run(refresh));
 root.querySelector('#face-match-start')?.addEventListener('click',()=>{
  if(!root.querySelector('#face-match-consent').checked){root.querySelector('#face-match-note').textContent='Confirm Signzy consent first.';return;}
  run(async()=>{try{await session.post('/api/v1/profile/face-match',{consent:true,consent_version:data.consent_version});}finally{await refresh();}});
 });
}
