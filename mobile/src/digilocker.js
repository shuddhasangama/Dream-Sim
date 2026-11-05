// Consent confirmation is a retrieval trigger, never a client-side verification.
import { Browser } from '@capacitor/browser';
export async function load(session) {
  return session.get('/api/v1/verification/digilocker');
}
export function render(data, safe, compact=false) {
  if (!data?.enabled) return '';
  const s = data.session;
  const labels = {creating:'Creating your consent link', awaiting_consent:'Complete DigiLocker consent',
    retrieving:'Retrieving your details', pending:'DigiLocker is still processing your consent',
    complete:'Details received from DigiLocker', expired:'Your consent link has expired',
    not_confirmed:'Verification attempt unsuccessful: DigiLocker consent or data was not confirmed. This does not mean your identity failed.',
    needs_review:'Your result needs review. Contact support.', unavailable:'DigiLocker is unavailable. Contact support.',
    outcome_unknown:'The provider response could not be confirmed. Contact support before starting again.'};
  return `<section class="card"><h2>Connect DigiLocker</h2>
    ${data.environment==='preproduction'?'<p class="hint">Sandbox test · does not approve your account.</p>':''}
    ${compact?'<p>Aadhaar is required. PAN is optional; salaried employment checks use PAN.</p><p class="hint">Enter Aadhaar and OTP only on DigiLocker.</p>':'<p>Share Aadhaar details and available PAN records. Enter Aadhaar and OTP only on DigiLocker. If you have Aadhaar but no DigiLocker account, set one up in DigiLocker first. If you do not have Aadhaar, contact support; installing DigiLocker does not issue Aadhaar.</p>'}
    ${!s || s.state==='expired' || s.can_request_photo || s.can_restart ? `<form id="digilocker-start"><label><input type="checkbox" name="consent" required> ${compact?'I agree to share Aadhaar details and available PAN records.':safe(data.consent_text)}</label>${compact?`<details><summary>Sharing details</summary><p>${safe(data.consent_text)}</p></details>`:''}<button class="primary" type="submit">${s?.can_request_photo?'Create a new document-sharing link':'Create DigiLocker link'}</button></form>` : `<p role="status">${safe(labels[s.state]||'Refresh your status')}</p>`}
    ${s?.consent_url?`<button type="button" id="digilocker-open" class="primary">Open DigiLocker to complete OTP and consent</button>
      <p>Complete OTP and document sharing in DigiLocker, then return here. Closing the browser or only receiving an OTP does not complete consent.</p>
      <p>Confirm only when finished. Each consent link permits one retrieval attempt. An unconfirmed attempt requires a ${safe(data.cooldown_minutes||30)}-minute cooldown before starting again.</p>
      <form id="digilocker-complete"><label><input type="checkbox" name="completed" required> I completed DigiLocker OTP and consent for this link.</label><button class="primary" type="submit">Retrieve my details</button></form>`:''}
    ${s?.identity?`<dl><dt>Name</dt><dd>${safe(s.identity.name)}</dd><dt>Date of birth</dt><dd>${safe(s.identity.dob)}</dd>
      <dt>Age as of ${safe(s.identity.age_as_of)}</dt><dd>${safe(s.identity.age)}</dd><dt>Document address</dt><dd>${safe(s.identity.document_address)}</dd></dl>
      <p class="hint">Age is calculated from the document date of birth. The document address does not confirm your current residence.</p>`:''}
    ${s?.state==='complete'?`<p>Document photo: ${s.reference_photo_available?'reference received securely':'not available from this consent session'}. Liveness and face comparison are separate checks.</p>`:''}
    ${s?.cooling_down && s.state!=='complete'?`<p role="status">No further retrieval will be sent for this link. Cooldown ends: ${safe(new Date(s.cooldown_until).toLocaleString())}. Refresh status after that time.</p>`:''}
    ${compact?'':'<button type="button" id="digilocker-refresh" class="secondary">Refresh DigiLocker status</button>'}</section>`;
}
export function bind(root, {session, run, data, patch}) {
  // Keep an idempotency key across a failed network response while this form remains mounted.
  const form=root.querySelector('#digilocker-start');
  root.querySelector('#digilocker-open')?.addEventListener('click',()=>run(async()=>{
    const url=new URL(data.session.consent_url);
    if (url.protocol!=='https:' || !['api.digitallocker.gov.in','digilocker.meripehchaan.gov.in','digilocker.signzy.tech'].includes(url.hostname)) throw new Error('Invalid DigiLocker link. Refresh and contact support.');
    await Browser.open({url:url.href});
  }));
  let id=crypto.randomUUID();
  form?.addEventListener('submit',event=>{
    event.preventDefault();
    run(async()=>await patch(await session.post('/api/v1/verification/digilocker/sessions',{
      request_id:id, consent:form.elements.consent.checked, consent_version:data.consent_version})));
  });
  const complete=root.querySelector('#digilocker-complete');
  complete?.addEventListener('submit',event=>{
    event.preventDefault();
    run(async()=>await patch(await session.post(`/api/v1/verification/digilocker/sessions/${data.session.id}/complete`,{
      consent_completed:complete.elements.completed.checked})));
  });
  root.querySelector('#digilocker-refresh')?.addEventListener('click',()=>run(async()=>await patch(await load(session))));
}
