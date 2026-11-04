import {Camera} from '@capacitor/camera';
import {captureOptions} from './identity.js';
export async function load(session){return session.get('/api/v1/profile/avatar');}
export function render({data,safe}){
 if(!data)return '<section class="card">Loading avatar…</section>';
 return `<section class="intro"><h1>Your avatar</h1><p>Two choices, one generation run. Made only from your latest selfie.</p></section><section class="card"><p role="status">${safe(data.message)}</p><p class="hint">AI avatar · Verification pending. Face verification is not connected yet.</p>
 ${!data.enabled?'<p>Avatar generation is being configured.</p>':''}
 ${data.can_capture?`<button type="button" id="avatar-camera">Capture latest selfie</button><img id="avatar-selfie" class="profile-portrait" hidden alt="Review your private selfie"><p id="avatar-note" role="status"></p><label class="checkbox-row"><input id="avatar-consent" type="checkbox"> ${safe(data.consent_text)}</label><button type="button" id="avatar-generate" disabled>Generate two avatars · one run only</button><p class="hint">GPT Image 2 · Low quality. Your Aadhaar and PAN photos are not sent to OpenAI. Camera capture alone does not prove liveness.</p>`:''}
 ${data.state==='draft'&&!data.can_capture?'':data.can_generate?'<p>Your latest saved selfie is ready. Capture it again to review it before generation.</p>':''}
 <div class="avatar-options">${(data.options||[]).map((src,i)=>`<div><img src="${safe(src)}" alt="Avatar option ${i+1}"><button type="button" data-avatar-accept="${i}">${data.selected===i?'Selected':'Choose avatar '+(i+1)}</button></div>`).join('')}</div>
 ${data.avatar?.photo?`<h2>Your selected avatar</h2><img class="profile-portrait" src="${safe(data.avatar.photo)}" alt="Your selected avatar"><p>Visible on your profile and to matches · Verification pending</p>`:''}
 <button type="button" id="avatar-refresh" class="secondary">Refresh avatar status</button>
 ${!['not_started','queued','submitting','deleted'].includes(data.state)?'<details><summary>Remove avatar and private images</summary><p>This removes your avatar from your profile and matches. It does not reset the one-run allowance or recall processing by OpenAI.</p><button type="button" id="avatar-delete" class="secondary">Remove my avatar images</button></details>':''}</section>`;
}
export function bind(root,{session,run,patch,data}){
 let staged=null;const refresh=async()=>patch(await load(session));
 root.querySelector('#avatar-refresh')?.addEventListener('click',()=>run(refresh));
 root.querySelector('#avatar-camera')?.addEventListener('click',async()=>{
  const button=root.querySelector('#avatar-camera'),note=root.querySelector('#avatar-note');button.disabled=true;
  staged=null;root.querySelector('#avatar-generate').disabled=true;root.querySelector('#avatar-consent').checked=false;
  try{const image=await Camera.getPhoto(captureOptions);if(!button.isConnected)return;
   if(!image.dataUrl||image.dataUrl.length>2_800_000)throw Error();staged=image.dataUrl;
   const preview=root.querySelector('#avatar-selfie');preview.src=staged;preview.hidden=false;root.querySelector('#avatar-generate').disabled=false;
   note.textContent='Review your latest selfie, then consent. Nothing has been sent yet.';
  }catch{if(button.isConnected)note.textContent='No photo saved. Check camera permission and try again.';}finally{if(button.isConnected)button.disabled=false;}
 });
 root.querySelector('#avatar-generate')?.addEventListener('click',()=>{
  if(!staged||!root.querySelector('#avatar-consent').checked){root.querySelector('#avatar-note').textContent='Review the selfie and confirm consent first.';return;}
  const image=staged;root.querySelector('#avatar-generate').disabled=true;
  run(async()=>{try{await session.post('/api/v1/profile/avatar/selfie',{image});await session.post('/api/v1/profile/avatar/generate',{consent:true,consent_version:data.consent_version});staged=null;}finally{await refresh();}});
 });
 root.querySelectorAll('[data-avatar-accept]').forEach(b=>b.addEventListener('click',()=>run(async()=>patch(await session.post('/api/v1/profile/avatar/accept',{index:Number(b.dataset.avatarAccept)})))));
 root.querySelector('#avatar-delete')?.addEventListener('click',()=>run(async()=>patch(await session.delete('/api/v1/profile/avatar'))));
}
