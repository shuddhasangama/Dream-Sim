import * as faceMatch from '../faceMatch.js';
import {Camera,CameraSource} from '@capacitor/camera';
import {captureOptions} from './identity.js';
export async function load(session){const [avatar,face]=await Promise.all([session.get('/api/v1/profile/avatar'),session.get('/api/v1/profile/face-match')]);return {...avatar,face};}
export function render({data,safe,busy}){
 if(!data)return '<section class="card">Loading avatar…</section>';
 return `<section class="intro"><h1>Your avatar</h1><p>Two choices, one generation run. Made only from your latest selfie.</p></section><section class="card"><p role="status">${safe(data.message)}</p><p class="hint">AI avatar · Verification pending. Passive liveness is not connected yet.</p>
 ${!data.enabled?'<p>Avatar generation is being configured.</p>':''}
 ${data.can_capture?`<button type="button" id="avatar-camera" ${busy?'disabled':''}>Capture latest selfie</button><button type="button" id="avatar-photos" class="secondary" ${busy?'disabled':''}>Choose recent selfie from Photos</button><img id="avatar-selfie" class="profile-portrait" ${data._stagedSelfie?`src="${safe(data._stagedSelfie)}"`:'hidden'} alt="Review your private selfie"><p id="avatar-note" role="status">${safe(data._cameraNote||'')}</p><label class="checkbox-row"><input id="avatar-consent" type="checkbox"> ${safe(data.consent_text)}</label><button type="button" id="avatar-generate" ${data._stagedSelfie&&!busy?'':'disabled'}>Generate two avatars · one run only</button><p class="hint">GPT Image 2 · Low quality. Your Aadhaar and PAN photos are not sent to OpenAI. Camera capture alone does not prove liveness.</p>`:''}
 ${data.state==='draft'&&!data.can_capture?'':data.can_generate?'<p>Your latest saved selfie is ready. Capture it again to review it before generation.</p>':''}
 <div class="avatar-options">${(data.options||[]).map((src,i)=>`<div><img src="${safe(src)}" alt="Avatar option ${i+1}"><button type="button" data-avatar-accept="${i}">${data.selected===i?'Selected':'Choose avatar '+(i+1)}</button></div>`).join('')}</div>
 ${data.avatar?.photo?`<h2>Your selected avatar</h2><img class="profile-portrait" src="${safe(data.avatar.photo)}" alt="Your selected avatar"><p>Visible on your profile and to matches · Verification pending</p>`:''}
 <button type="button" id="avatar-refresh" class="secondary">Refresh avatar status</button>
 ${!['not_started','queued','submitting','deleted'].includes(data.state)?'<details><summary>Remove avatar and private images</summary><p>This removes your avatar from your profile and matches. It does not reset the one-run allowance or recall processing by OpenAI.</p><button type="button" id="avatar-delete" class="secondary">Remove my avatar images</button></details>':''}</section>${faceMatch.render(data.face,safe)}`;
}
export function captureError(error){
 const text=String(error?.message||error||'').toLowerCase();
 if(text.includes('cancel'))return 'Capture cancelled. No photo was uploaded.';
 if(text.includes('permission')||text.includes('denied')||text.includes('access'))return 'Camera or Photos permission is blocked. Enable Camera/Photos access for DhaShu in your device settings, then try again. You can also choose a recent selfie from Photos.';
 if(text.includes('not implemented')||text.includes('unavailable'))return 'Camera capture is unavailable. Choose a recent selfie from Photos to continue.';
 if(text.includes('large'))return 'The photo is too large. Choose a smaller JPEG selfie under 2 MB.';
 return 'The camera did not return a usable photo. Try again or choose a recent selfie from Photos. Nothing was uploaded.';
}
export function bind(root,{session,run,patch,data},takePhoto=options=>Camera.getPhoto(options)){
 let staged=data?._stagedSelfie||null;const refresh=async()=>patch(await load(session));
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
    patch({...data,_stagedSelfie:image.dataUrl,_cameraNote:'Review your latest selfie, then consent. Nothing has been uploaded yet.'});
   }catch(error){patch({...data,_stagedSelfie:null,_cameraNote:captureError(error)});}
  });
 }
 root.querySelector('#avatar-camera')?.addEventListener('click',()=>capture(captureOptions.source));
 root.querySelector('#avatar-photos')?.addEventListener('click',()=>capture(CameraSource.Photos));
 root.querySelector('#avatar-generate')?.addEventListener('click',()=>{
  if(!staged||!root.querySelector('#avatar-consent').checked){root.querySelector('#avatar-note').textContent='Review the selfie and confirm consent first.';return;}
  const image=staged;root.querySelector('#avatar-generate').disabled=true;
  run(async()=>{try{await session.post('/api/v1/profile/avatar/selfie',{image});await session.post('/api/v1/profile/avatar/generate',{consent:true,consent_version:data.consent_version});staged=null;}finally{await refresh();}});
 });
 root.querySelectorAll('[data-avatar-accept]').forEach(b=>b.addEventListener('click',()=>run(async()=>patch(await session.post('/api/v1/profile/avatar/accept',{index:Number(b.dataset.avatarAccept)})))));
 root.querySelector('#avatar-delete')?.addEventListener('click',()=>run(async()=>patch(await session.delete('/api/v1/profile/avatar'))));
}
