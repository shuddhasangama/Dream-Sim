import { Camera, CameraDirection, CameraResultType, CameraSource } from '@capacitor/camera';

export const captureOptions = {
  source: CameraSource.Camera, direction: CameraDirection.Front,
  resultType: CameraResultType.DataUrl, quality: 80, width: 1200, height: 1200,
  allowEditing: false, saveToGallery: false, correctOrientation: true, webUseInput: true,
};

const labels = {not_captured:'Not captured', captured:'Saved — awaiting submission',
  submitted:'Awaiting provider review', verified:'Identity check approved',
  rejected:'Provider could not approve this image', expired:'A new check is needed', deleted:'Image deleted'};

export async function load(session) { return session.get('/api/v1/identity-capture'); }

export function panel(data, safe) {
  if (!data?.enabled) return '<p>Identity-image capture is not enabled yet.</p>';
  const canCapture = ['not_captured','deleted','rejected','expired'].includes(data.status);
  return `<section class="card"><h2>Face photo</h2>
    <p role="status">${safe(data.test_approved ? 'Capture complete — approved for testing' : labels[data.status] || 'Check status')}</p>
    <p>Private photo for your identity check.</p>
    ${canCapture ? `<p>Face the camera in good light. Keep your full face visible.</p>
      <button id="identity-camera" type="button">Take a face photo</button>
      <img id="identity-preview" class="profile-portrait" hidden alt="Review your identity image before uploading">
      <p id="identity-note" role="status"></p>
      <form id="identity-form"><label class="checkbox-row"><input type="checkbox" name="consent" required> I agree to store this photo for BGV review.</label><details><summary>How your photo is used</summary><p>${safe(data.consent_text)}</p></details>
      <button id="identity-upload" class="primary" type="submit" disabled>Save private image</button></form>` : ''}
    ${data.test_approved ? '<p>You can continue testing now. BGV authentication is still pending.</p>' : ''}
    ${data.status === 'captured' && !data.test_approved ? '<p>Your image has not been sent automatically. DhaShu must submit it to the verification provider.</p>' : ''}
    ${data.verified ? '<p>Your approved check can be reused for later agreements while it remains valid. Each agreement still needs your own signature.</p>' : ''}
    <button id="identity-refresh" type="button">Refresh status</button>
    ${data.capture_id && data.status !== 'deleted' ? `<details><summary>Delete identity image</summary>
      <p>This removes DhaShu’s stored image and stops reuse of this check. It does not erase existing agreements or recall provider exports.</p>
      <button id="identity-delete" type="button">Delete my identity image</button></details>` : ''}
    </section>`;
}

export function render({data,safe}) {
  return '<section class="intro"><h1>Identity check</h1></section>' + (data ? panel(data,safe) : '<p>Loading…</p>');
}

export function bindPanel(root, {session, run}, data, reload, takePhoto = () => Camera.getPhoto(captureOptions)) {
  let staged = null;
  root.querySelector('#identity-camera')?.addEventListener('click', async () => {
    const button=root.querySelector('#identity-camera');
    const note=root.querySelector('#identity-note');
    staged=null;
    root.querySelector('#identity-upload').disabled=true;
    root.querySelector('#identity-preview').hidden=true;
    root.querySelector('[name="consent"]').checked=false;
    button.disabled=true;
    note.textContent='';
    try {
      const image=await takePhoto();
      if (!button.isConnected) return;
      if (!image.dataUrl || image.dataUrl.length>2_800_000) throw new Error('Use a smaller image and try again.');
      staged=image.dataUrl;
      const preview=root.querySelector('#identity-preview');
      preview.src=staged;preview.hidden=false;
      root.querySelector('#identity-upload').disabled=false;
      button.textContent='Retake photo';
      note.textContent='Review your photo, then consent and save. Nothing has been uploaded yet.';
      root.dispatchEvent(new Event('input',{bubbles:true}));
    } catch {
      if (button.isConnected) note.textContent='No photo saved. If camera access was denied, allow it in your phone settings and try again.';
    } finally { if(button.isConnected) button.disabled=false; }
  });
  root.querySelector('#identity-form')?.addEventListener('submit', e => {
    e.preventDefault();
    if(!staged || !new FormData(e.target).has('consent')) return;
    const payload={image:staged,consent:true,consent_version:data.consent_version};
    // Keep the image in memory only; the global render can replace this DOM.
    staged=null;
    run(async()=>{await session.post('/api/v1/identity-capture',payload);await reload();});
  });
  root.querySelector('#identity-refresh')?.addEventListener('click',()=>run(reload));
  root.querySelector('#identity-delete')?.addEventListener('click',()=>run(async()=>{
    await session.delete('/api/v1/identity-capture');await reload();
  }));
}

export function bind(root,ctx) { bindPanel(root,ctx,ctx.data,async()=>ctx.patch(await load(ctx.session))); }
