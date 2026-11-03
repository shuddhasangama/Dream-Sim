import * as digilocker from '../digilocker.js';
export async function load(session) {
  const [checks,identity,plan,liveness]=await Promise.all([session.get('/api/v1/verification'),digilocker.load(session),session.get('/api/v1/verification/plan'),session.get('/api/v1/verification/liveness')]);
  return {...checks,digilocker:identity,plan,liveness};
}
const labels={history_available:'History found',employment_mismatch:'Doesn’t match',not_confirmed:'Not confirmed',queued:'Confirming',processing:'Confirming',pending:'Processing',result_available:'Retrieving result',
  verified:'Verified',partially_verified:'Review needed',needs_review:'Review needed',unavailable:'Check unavailable',
  outcome_unknown:'Support review',reviewed_satisfied:'Reviewed',reviewed_needs_review:'Review needed',reviewed_not_satisfied:'Follow-up needed',waived:'Exception recorded'};
export function render({data,safe}) {
  if(!data)return '<section class="card">Loading verification…</section>';
  const s=data.digilocker?.session, identity=s?.identity, bundle=data.bundle||{};
  const ageMismatch=identity&&Number.isInteger(bundle.declared_age)&&bundle.declared_age!==identity.age;
  const results=(data.results||[]).filter(r=>!data.environment||r.environment===data.environment);
  function check(op,child,key) {
    const r=results.find(r=>r.operation===child)||results.find(r=>r.operation===op);
    const reviewed=data.plan?.checks?.find(c=>c.key===key||c.check_key===key);
    const state=reviewed?.state?.startsWith('reviewed_')?reviewed.state:r?.state;
    return {status:labels[state]||'Not started',tone:state==='verified'||state==='reviewed_satisfied'?'good':state==='needs_review'||state==='unavailable'||state==='employment_mismatch'?'attention':'waiting',
      text:r?.message||(identity&&bundle.consented?'Starting in the background':'Waiting for DigiLocker and consent')};
  }
  const employer=check('current_employer',null,'current_employer'),court=check('individual_search','individual_result','criminal_court'),fir=check('fir_search','fir_result','fir');
  if(!results.some(r=>r.operation==='current_employer')) {
    employer.status='Waiting for details';
    employer.text=bundle.pan_state==='not_shared'?'PAN wasn’t shared through DigiLocker':bundle.pan_state==='unavailable'?'PAN retrieval needs support review':bundle.pan_state!=='received'?'Waiting for a PAN document identifier':!bundle.mobile_available?'Mobile wasn’t available from DigiLocker':bundle.identity_name_match===false?'DigiLocker account name needs review':!bundle.employer_declared?'Add your declared employer below':'Starting in the background';
  }
  const row=(name,value,status,tone='waiting')=>`<div class="bgv-row"><div class="bgv-row-copy"><span class="bgv-label">${safe(name)}</span><div class="bgv-value">${safe(value)}</div></div><span class="bgv-badge ${tone}">${safe(status)}</span></div>`;
  return `<div class="bgv-compact"><header><span class="bgv-label">STAGE 1 · BEFORE YOU MEET</span><h1>Your verification</h1><p>Share once. Follow your checks here.</p></header>
    <section class="card bgv-checklist" aria-label="Verification checklist" aria-live="polite">
      ${row('Name',identity?.name||'Share from DigiLocker',identity?'Received':'Not started',identity?'good':'waiting')}
      ${row('Age / date of birth',identity?`${identity.age} · ${identity.dob}${ageMismatch?` (profile says ${bundle.declared_age})`:''}`:'From Aadhaar',ageMismatch?'Review age':identity?'Received':'Not started',ageMismatch?'attention':identity?'good':'waiting')}
      ${row('Document address',identity?'Received from Aadhaar':'From Aadhaar',identity?'Received':'Not started',identity?'good':'waiting')}
      ${row('Current employer',employer.text,employer.status,employer.tone)}
      ${row('Criminal court',court.text,court.status,court.tone)}
      ${row('FIR check',fir.text,fir.status,fir.tone)}
      ${row('Identity / live face',s?.reference_photo_available?'Document photo ready · selfie integration pending':'Waiting for document photo','Setup needed')}
    </section>
    ${identity?`<details class="bgv-details"><summary>View document details</summary><p>${safe(identity.document_address)}</p><p class="hint">Age is calculated from Aadhaar DOB. The document address does not confirm your current residence. Received details are not a comparison against your profile declarations.</p><p>PAN: ${safe(({received:'Identifier received from issued-document listing',pending:'Retrieving available documents',not_shared:'Not shared through DigiLocker',unavailable:'Retrieval needs support review',needs_review:'Document identifier needs review'})[bundle.pan_state]||'Not requested in this consent session')}</p></details>`:digilocker.render(data.digilocker,safe)}
    ${identity&&bundle.enabled&&(!bundle.consented||!bundle.employer_declared)?`<form id="bgv-bundle-form" class="card"><h2>${bundle.consented?'Current employer':'Continue background checks'}</h2><label>Declared current employer (optional for Court/FIR)<input name="employer" maxlength="200" autocomplete="organization"></label><label class="bgv-consent"><input type="checkbox" name="consent" required> ${safe(bundle.consent_text)}</label><button type="submit" class="primary">${bundle.consented?'Save employer and continue':'Start relevant checks'}</button><p class="hint">Employer screening waits for PAN, mobile and your employer declaration. Missing PAN does not block Court/FIR.</p></form>`:''}
    ${identity&&s.can_request_photo?`<details class="bgv-details"><summary>Share a fresh DigiLocker session including PAN</summary>${digilocker.render(data.digilocker,safe)}</details>`:''}
    ${results.filter(r=>r.can_check_again).map(r=>`<button type="button" class="secondary" data-bgv-poll="${safe(r.id)}">Check ${r.operation==='fir_result'?'FIR':'Court'} processing status again</button>`).join('')}
    <p class="hint">Face capture isn’t connected yet. No live face check has been performed.</p>
    <button type="button" id="bgv-refresh" class="secondary">Refresh status</button>
    <p class="hint">${data.environment==='preproduction'?'Sandbox testing · ':''}Each check has its own result. An exact search with zero cases verifies that check; overall account approval is separate.</p>
    ${!data.enabled?'<p>Verification checks are not enabled yet.</p>':''}</div>`;
}
export function bind(root,ctx) {
  const {session,run,patch}=ctx;
  const refresh=async()=>patch(await load(session));
  digilocker.bind(root,{session,run,data:ctx.data?.digilocker,patch:async()=>refresh()});
  root.querySelector('#bgv-refresh')?.addEventListener('click',()=>run(refresh));
  root.querySelectorAll?.('[data-bgv-poll]').forEach(button=>button.addEventListener('click',()=>run(async()=>{await session.post(`/api/v1/verification/${button.dataset.bgvPoll}/check-again`,{});await refresh();})));
  const form=root.querySelector('#bgv-bundle-form');
  form?.addEventListener('submit',event=>{
    event.preventDefault();
    const body={session_id:ctx.data.bundle.session_id,consent:form.elements.consent.checked,consent_version:ctx.data.bundle.consent_version,employer:form.elements.employer.value.trim()};
    run(async()=>{await session.post('/api/v1/verification/bundle',body);await refresh();});
  });
}
