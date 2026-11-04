import * as faceMatch from '../faceMatch.js';
import {Camera} from '@capacitor/camera';
import {captureOptions} from './identity.js';
export async function load(session){
 const [avatar,face]=await Promise.allSettled([session.get('/api/v1/profile/avatar'),session.get('/api/v1/profile/face-match')]);
 if(avatar.status==='rejected')throw avatar.reason;
 if(face.status==='rejected'&&face.reason?.status===401)throw face.reason;
 return {...avatar.value,face:face.status==='fulfilled'?face.value:null,_faceError:face.status==='rejected'};
}
export function statusText(data){return ({not_started:'Capture your latest selfie to begin.',draft:'Review your selfie and consent to continue.',queued:'Your two avatars are queued.',submitting:'Generating your two avatars…',ready:'Choose your avatar.',accepted:'Your avatar is on your profile.',unknown:'Generation could not be confirmed. Contact support; another run is blocked.',deleted:'Images removed. Your generation allowance is unchanged.',expired:'Your private images have expired.'})[data.state]||data.message||'Check your avatar status.';}

export function render({data,safe,busy}){
 if(!data)return '<section class="card">Loading avatar…</section>';
 return `<section class="intro"><h1>Your avatar</h1><p>One selfie. Two choices. One generation run.</p></section><section class="card avatar-flow"><p role="status">${safe(data._requestNote||statusText(data))}</p>
 ${!data.enabled?'<p>Avatar generation is being configured.</p>':''}
 ${data.can_capture?`<button type="button" id="avatar-camera" ${busy?'disabled':''}>${data._stagedSelfie?'Retake selfie':'Capture latest selfie'}</button><img id="avatar-selfie" class="profile-portrait" ${data._stagedSelfie?`src="${safe(data._stagedSelfie)}"`:'hidden'} alt="Review your private selfie"><p id="avatar-note" role="status">${safe(data._cameraNote||'')}</p>
 ${data._stagedSelfie?`<label class="checkbox-row"><input id="avatar-consent" type="checkbox" ${data._avatarConsent?'checked':''} ${busy?'disabled':''}> I agree to send this selfie to OpenAI to generate two avatars.</label><details><summary>How your photo is used</summary><p>${safe(data.consent_text)}</p></details>`:''}
 <button type="button" id="avatar-generate" ${data._stagedSelfie&&data._avatarConsent?'':'hidden'} ${busy?'disabled':''}>Generate 2 avatars</button><p class="hint">GPT Image 2 · Low quality</p>`:''}
 ${!data._stagedSelfie&&data.can_generate?'<p>Your latest saved selfie is ready. Capture it again to review it before generation.</p>':''}
 <div class="avatar-options">${(data.options||[]).map((src,i)=>`<div><img src="${safe(src)}" alt="Avatar option ${i+1}"><button type="button" data-avatar-accept="${i}">${data.selected===i?'Selected':'Choose avatar '+(i+1)}</button></div>`).join('')}</div>
 ${data.avatar?.photo?`<h2>Your selected avatar</h2><img class="profile-portrait" src="${safe(data.avatar.photo)}" alt="Your selected avatar"><p>Visible on your profile and to matches · Verification pending</p>`:''}
 <button type="button" id="avatar-refresh" class="secondary" ${busy?'disabled':''}>${busy?'Checking…':'Refresh avatar status'}</button>
 ${!['not_started','queued','submitting','deleted'].includes(data.state)?'<details><summary>Remove avatar and private images</summary><p>This removes your avatar from your profile and matches. It does not reset the one-run allowance or recall processing by OpenAI.</p><button type="button" id="avatar-delete" class="secondary">Remove my avatar images</button></details>':''}</section><details class="card"><summary>Face verification · ${safe(data.face?.state==='matched'?'Matched':'Pending')}</summary>${data._faceError?'<p>Face status unavailable. Refresh to try again.</p>':faceMatch.render(data.face,safe)}</details>`;
}
export function captureError(error){
 const text=String(error?.message||error||'').toLowerCase();
 if(text.includes('cancel'))return 'Capture cancelled. No photo was uploaded.';
 if(text.includes('permission')||text.includes('denied')||text.includes('access'))return 'Camera permission is blocked. Enable Camera access for DhaShu in your iPhone settings, then try again.';
 if(text.includes('not implemented')||text.includes('unavailable'))return 'Camera capture is unavailable. Close and reopen the app, then try again.';
 if(text.includes('large'))return 'The photo is too large. Retake your selfie and try again.';
 return 'The camera did not return a usable photo. Try capturing again. Nothing was uploaded.';
}
export function bind(root,{session,run,patch,data},takePhoto=options=>Camera.getPhoto(options)){
 let staged=data?._stagedSelfie||null;
 const refresh=async()=>{
  try{
   const next=await load(session);
   patch({...next,...(next.can_capture&&staged?{_stagedSelfie:staged,_avatarConsent:!!data._avatarConsent}:{}),_requestNote:'Status updated. '+statusText(next)});
  }catch(error){if(error?.status===401)throw error;patch({...data,_requestNote:'Status could not be refreshed. Check your connection and try again.'});}
 };
 faceMatch.bind(root,{session,run},data?.face,refresh);
 root.querySelector('#avatar-refresh')?.addEventListener('click',()=>run(refresh));
 function capture(source){
  // Global busy state suppresses app-resume polling and navigation while the
  // native picker is open. Stage the result in screen memory, not a stale DOM.
  run(async()=>{
   try{
    const image=await takePhoto({...captureOptions,source});
    if(!image.dataUrl)throw Error('No usable image');
    if(image.dataUrl.length>2_800_000)throw Error('Photo too large');
    patch({...data,_stagedSelfie:image.dataUrl,_avatarConsent:false,_requestNote:'',_cameraNote:'Review your selfie, then give consent.'});
   }catch(error){patch({...data,_stagedSelfie:null,_cameraNote:captureError(error)});}
  });
 }
 root.querySelector('#avatar-camera')?.addEventListener('click',()=>capture(captureOptions.source));
 root.querySelector('#avatar-consent')?.addEventListener('change',event=>{
  data._avatarConsent=event.target.checked;
  root.querySelector('#avatar-generate').hidden=!event.target.checked||!staged;
 });
 root.querySelector('#avatar-generate')?.addEventListener('click',()=>{
  if(!staged||!root.querySelector('#avatar-consent')?.checked){root.querySelector('#avatar-note').textContent='Review the selfie and confirm consent first.';return;}
  const image=staged;root.querySelector('#avatar-generate').disabled=true;
  run(async()=>{
   try{
    await session.post('/api/v1/profile/avatar/selfie',{image});
    const next=await session.post('/api/v1/profile/avatar/generate',{consent:true,consent_version:data.consent_version});
    staged=null;patch({...next,face:data.face,_requestNote:statusText(next)});
   }catch(error){
    if(error?.status===401)throw error;
    // A lost response must be reconciled with server state, never replayed.
    try{
     const next=await load(session);
     patch({...next,...(next.can_capture?{_stagedSelfie:image,_avatarConsent:true}:{}),_requestNote:next.can_capture?'Could not start generation. '+(error.message||'Please try again.'):statusText(next)});
    }catch{patch({...data,_stagedSelfie:null,_avatarConsent:false,_requestNote:'Submission could not be confirmed. Refresh status before continuing.'});}
   }
  });
 });
 root.querySelectorAll('[data-avatar-accept]').forEach(b=>b.addEventListener('click',()=>run(async()=>patch(await session.post('/api/v1/profile/avatar/accept',{index:Number(b.dataset.avatarAccept)})))));
 root.querySelector('#avatar-delete')?.addEventListener('click',()=>run(async()=>patch(await session.delete('/api/v1/profile/avatar'))));
}
