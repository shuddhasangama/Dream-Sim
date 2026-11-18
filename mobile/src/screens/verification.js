import * as faceMatch from '../faceMatch.js';
import * as digilocker from '../digilocker.js';
import * as avatarScreen from './avatar.js';
import * as verificationPayment from '../verificationPayment.js';
export async function load(session) {
  const [checks,identity,plan,liveness,face,avatar,payment]=await Promise.all([session.get('/api/v1/verification'),digilocker.load(session),session.get('/api/v1/verification/plan'),session.get('/api/v1/verification/liveness'),faceMatch.load(session),session.get('/api/v1/profile/avatar').catch(error=>{if(error?.status===401)throw error;return {enabled:false,state:'unavailable',message:'Avatar status unavailable. Check for updates to try again.'};}),session.get('/api/v1/verification/payment').catch(error=>{if(error?.status===401)throw error;return {required:true,enabled:false,can_begin:false,state:'unavailable'};})]);
  return {...checks,digilocker:identity,plan,liveness,face,payment,avatar:avatar?{...avatar,...(avatar.verified_selfie_preview&&avatar.can_capture?{_stagedSelfie:avatar.verified_selfie_preview}:{}),face}:null};
}
const FACE_WORK=['queued_create','creating','queued_get','retrieving'];
const DOCUMENT_WORK=['creating','retrieving'];
const CHECK_WORK=['queued','processing','result_available'];
export function processing(data){return (DOCUMENT_WORK.includes(data?.digilocker?.session?.state)&&!data?.digilocker?.session?.recovery_required)||FACE_WORK.includes(data?.face?.state)||['queued','submitting'].includes(data?.avatar?.state)||(data?.results||[]).some(r=>CHECK_WORK.includes(r.state)&&!r.recovery_required);}
export function canAutoRefresh(data){return !data?.avatar?._stagedSelfie&&!data?._verificationEditing;}
const labels={record_available:'Record received',history_available:'History found',employment_mismatch:'Doesn’t match',not_confirmed:'Not confirmed',queued:'Confirming',processing:'Confirming',pending:'Awaiting provider',result_available:'Retrieving result',
  verified:'Verified',partially_verified:'Review needed',needs_review:'Review needed',unavailable:'Check unavailable',
  outcome_unknown:'Support review',reviewed_satisfied:'Reviewed',reviewed_needs_review:'Review needed',reviewed_not_satisfied:'Follow-up needed',waived:'Exception recorded'};
export function render({data,safe,busy=false}) {
  if(!data)return '<section class="card">Loading verification…</section>';
  const s=data.digilocker?.session, identity=s?.identity, bundle=data.bundle||{};
  const faceReady=data.face?.operation==='liveness_secure' && data.face?.state==='matched';
  const ageMismatch=identity&&Number.isInteger(bundle.declared_age)&&bundle.declared_age!==identity.age;
  const results=(data.results||[]).filter(r=>!data.environment||r.environment===data.environment);
  function check(op,child,key) {
    const r=results.find(r=>r.operation===child)||results.find(r=>r.operation===op);
    const reviewed=data.plan?.checks?.find(c=>c.key===key||c.check_key===key);
    const state=reviewed?.state?.startsWith('reviewed_')?reviewed.state:r?.state;
    return {status:labels[state]||'Not started',running:CHECK_WORK.includes(state)&&!r?.recovery_required,verified_at:r?.verified_at,received_at:r?.received_at,tone:state==='verified'||state==='reviewed_satisfied'?'good':state==='needs_review'||state==='unavailable'||state==='employment_mismatch'?'attention':'waiting',
      text:r?.message||(identity&&bundle.consented?'Starting in the background':'Waiting for DigiLocker and consent')};
  }
  const employer=check('current_employer',null,'current_employer'),court=check('individual_search','individual_result','criminal_court'),fir=check('fir_search','fir_result','fir');
  if(!results.some(r=>r.operation==='current_employer')) {
    employer.status=bundle.employment_blocker?'Action needed':'Waiting to start';
    employer.text=bundle.employment_blocker || (!bundle.employment_identifier_available?'PAN required: add your issued PAN document in DigiLocker and share it':'Starting in the background');
  }
  const dateText=(value)=>{const d=new Date(value);return value&&!Number.isNaN(d.getTime())?d.toLocaleString():null;};
  const dated=(value,info)=>{const verified=dateText(info?.verified_at),received=dateText(info?.received_at);return `${value}${verified?` · Verified ${verified}`:received?` · Received ${received}`:''}`;};
  const row=(name,value,status,tone='waiting',running=false)=>`<div class="bgv-row"><div class="bgv-row-copy"><span class="bgv-label">${safe(name)}</span><div class="bgv-value">${safe(value)}</div></div><span class="bgv-badge ${tone}">${running?'<span class="bgv-progress-dot" aria-hidden="true"></span>':''}${safe(status)}</span></div>`;
  return `<div class="bgv-compact"><header><span class="bgv-label">STAGE 1 · BEFORE YOU MEET</span><h1>Your verification</h1><p>Complete the next available step. Background checks continue while you create your avatar.</p></header>
    ${sequence(data,safe)}
    ${verificationPayment.render(data.payment,safe,busy)}
    ${identity?`<section class="card bgv-document-complete"><h2>DigiLocker <span class="bgv-badge good">Details received</span></h2><p class="hint">Aadhaar shared · PAN ${bundle.pan_state==='received'?'received':bundle.pan_state==='pending'?'being retrieved':'required for employment'}</p></section>`:data.payment?.required&&!data.payment.can_begin?'<p class="hint">Complete test payment to connect DigiLocker.</p>':digilocker.render(data.digilocker,safe,true)}
    <details class="card verification-fold" id="verification-face" ${(data._verificationFolds?.includes('verification-face')||identity&&!faceReady)?'open':''}><summary>3. Live face verification <span class="bgv-badge ${data.face?.state==='matched'?'good':data.face?.state==='not_matched'?'attention':'waiting'}">${FACE_WORK.includes(data.face?.state)?'Processing':data.face?.state==='matched'?'Complete':data.face?.state==='awaiting_capture'?'Continue capture':data.face?.state==='pending'?'Awaiting result':data.face?.state==='not_matched'?'Doesn’t match':['unknown','outcome_unknown','unavailable'].includes(data.face?.state)?'Needs attention':'To do'}</span></summary>
      ${identity?faceMatch.render(data.face,safe,true):'<p class="hint">Complete DigiLocker identity sharing first.</p>'}
    </details>
    <details class="card verification-fold" id="verification-avatar" ${(data._verificationFolds?.includes('verification-avatar')||(!data._verificationFolds&&faceReady&&['not_started','draft'].includes(data.avatar?.state)))?'open':''}><summary>4. Your avatar <span class="bgv-badge ${data.avatar?.state==='accepted'?'good':'waiting'}">${({queued:'Queued',submitting:'Generating',ready:'Choose one',accepted:'Complete'})[data.avatar?.state]||'To do'}</span></summary>
      <div id="verification-avatar-body">${!faceReady&&!['queued','submitting','ready','accepted'].includes(data.avatar?.state)?'<p>Complete live face verification first. Then review your verified selfie and consent to avatar generation.</p>':data.avatar?avatarScreen.render({data:data.avatar,safe,busy,embedded:true}):'<p>Avatar status unavailable.</p>'}</div>
    </details>
    ${!['queued','submitting','ready','accepted'].includes(data.avatar?.state)?'<p class="hint">After live face verification, your verified selfie is ready for two avatar choices. Confirm avatar consent and start generation while employment, court and FIR checks continue.</p>':''}
    <p class="bgv-live-status" role="status">${data._statusError?safe(data._statusError):processing(data)?'<span class="bgv-progress-dot" aria-hidden="true"></span> Checks are running in the background. Status updates automatically.':'Follow each check below.'}</p>
    <section class="card bgv-checklist" aria-label="Verification checklist" aria-live="polite"><h2>5. Background check progress</h2><p class="hint">These checks run automatically after identity sharing and consent. Historical employment records require review; they do not establish current employment.</p>
      ${row('Name',identity?dated('Received securely · revealed to matches later',s?.field_verifications?.name):'Share from DigiLocker',identity?'Received':'Not started',identity?'good':'waiting')}
      ${row('Age / date of birth',identity?dated(`${identity.age} · ${identity.dob}${ageMismatch?` (profile says ${bundle.declared_age})`:''}`,s?.field_verifications?.dob):'From Aadhaar',ageMismatch?'Review age':identity?'Received':'Not started',ageMismatch?'attention':identity?'good':'waiting')}
      ${row('Document address',identity?dated('Received from Aadhaar',s?.field_verifications?.document_address):'From Aadhaar',identity?'Received':'Not started',identity?'good':'waiting')}
      ${row('Employment record',dated(employer.text,employer),employer.status,employer.tone,employer.running)}
      ${row('Criminal court',dated(court.text,court),court.status,court.tone,court.running)}
      ${row('FIR check',dated(fir.text,fir),fir.status,fir.tone,fir.running)}
      ${row('Identity / live face',dated(data.face?.message||(s?.reference_photo_available?'Document photo ready · Face comparison available':'Waiting for document photo'),{verified_at:data.face?.state==='matched'?data.face?.checked_at:null}),data.face?.state==='matched'?(data.face.operation==='liveness_secure'?'Live face checked':'Face matched'):data.face?.state==='not_matched'?'Doesn’t match':data.face?.state==='unknown'?'Check unavailable':data.face?'Pending':'Setup needed',data.face?.state==='not_matched'?'attention':data.face?.state==='matched'?'good':'waiting')}
    </section><p class="hint">${identity?'Your name and age have been updated from DigiLocker. Age is calculated from the confirmed Aadhaar DOB.':'Your name and age will update automatically from confirmed DigiLocker details.'} Your name is revealed later in the matching journey.</p>
    ${identity?`<details class="bgv-details"><summary>View document details</summary><p>${safe(identity.name)}</p><p>${safe(identity.document_address)}</p><p class="hint">Age is calculated from Aadhaar DOB. The document address does not confirm your current residence. Received details are not a comparison against your profile declarations.</p><p>PAN: ${safe(({received:'Identifier received from issued-document listing',pending:'Retrieving available documents',not_shared:'Not shared through DigiLocker',unavailable:'Retrieval needs support review',needs_review:'Document identifier needs review'})[bundle.pan_state]||'Not requested in this consent session')}</p></details>`:''}
    ${identity&&bundle.enabled&&!bundle.consented?`<form id="bgv-bundle-form" class="card"><h2>Continue background checks</h2><label class="bgv-consent"><input type="checkbox" name="consent" required> ${safe(bundle.consent_text)}</label><button type="submit" class="primary">Start relevant checks</button><p class="hint">Employment screening requires your issued PAN document from DigiLocker. Aadhaar alone does not supply PAN; an employer name is not required.</p></form>`:''}
    ${identity&&s.can_request_photo?`<details class="bgv-details"><summary>Share a fresh DigiLocker session including PAN</summary>${digilocker.render(data.digilocker,safe,true)}</details>`:''}
    ${results.filter(r=>r.can_check_again&&r.state==='pending').map(r=>`<button type="button" class="secondary" data-bgv-poll="${safe(r.id)}">Retrieve ${r.operation==='fir_result'?'FIR':'Court'} result</button>`).join('')}
    ${!processing(data)||data._statusError?`<button type="button" id="bgv-refresh" class="secondary" ${busy?'disabled':''}>Check for updates</button>`:''}
    <p class="hint">${data.environment==='preproduction'?'Sandbox testing · ':''}Each check has its own result. A completed exact search with zero results means no records were returned by that search, not comprehensive criminal clearance. Overall account approval is separate.</p>
    <section class="card"><h2>6. Final review</h2><p>Each required check must be verified or explicitly reviewed by support before account approval. Employment history alone is not current-employer confirmation. Any possible court or FIR match needs review.</p></section>
    ${!data.enabled?'<p>Verification checks are not enabled yet.</p>':''}</div>`;
}
export function bind(root,ctx) {
  const {session,run,patch}=ctx;
  if(ctx.busy)root.querySelectorAll?.('button,input,select,textarea').forEach(el=>{el.disabled=true;});
  const refresh=async()=>{
    const next=await load(session);
    const folds=[...root.querySelectorAll?.('.verification-fold[open]')||[]].map(e=>e.id);
    if(ctx.data?.face?.state!=='matched'&&next.face?.state==='matched'&&next.avatar?.can_capture&&!folds.includes('verification-avatar'))folds.push('verification-avatar');
    patch({...next,...(next.avatar?.can_capture&&ctx.data?.avatar?._stagedSelfie?{avatar:{...next.avatar,_stagedSelfie:ctx.data.avatar._stagedSelfie,_avatarConsent:ctx.data.avatar._avatarConsent}}:{}),_verificationFolds:folds});
  };
  verificationPayment.bind(root,{session,run},ctx.data?.payment,refresh);
  root.querySelectorAll?.('.verification-fold').forEach(section=>section.addEventListener('toggle',()=>{ctx.data._verificationFolds=[...root.querySelectorAll('.verification-fold[open]')].map(e=>e.id);}));
  const avatarRoot=root.querySelector('#verification-avatar-body');
  if(avatarRoot&&ctx.data?.avatar)avatarScreen.bind(avatarRoot,{session,run,embedded:true,data:ctx.data.avatar,patch:avatar=>{
    patch({...ctx.data,avatar:{...avatar,face:ctx.data.face},_verificationFolds:[...root.querySelectorAll('.verification-fold[open]')].map(e=>e.id)});
  }});
  faceMatch.bind(root,{session,run},ctx.data?.face,refresh);
  digilocker.bind(root,{session,run,data:ctx.data?.digilocker,patch:async()=>refresh()});
  root.querySelector('#bgv-refresh')?.addEventListener('click',()=>run(refresh));
  root.querySelectorAll?.('[data-bgv-poll]').forEach(button=>button.addEventListener('click',()=>run(async()=>{await session.post(`/api/v1/verification/${button.dataset.bgvPoll}/check-again`,{});await refresh();})));
  root.querySelectorAll?.('form input,form select,form textarea').forEach(input=>input.addEventListener('input',()=>{ctx.data._verificationEditing=true;}));
  const form=root.querySelector('#bgv-bundle-form');
  form?.addEventListener('submit',event=>{
    event.preventDefault();
    const body={session_id:ctx.data.bundle.session_id,consent:form.elements.consent.checked,consent_version:ctx.data.bundle.consent_version};
    run(async()=>{await session.post('/api/v1/verification/bundle',body);await refresh();});
  });
}

export function sequence(data,safe){
 const identity=!!data.digilocker?.session?.identity;
 const paid=!data.payment?.required||data.payment.can_begin;
 const live=data.face?.operation==='liveness_secure'&&data.face.state==='matched';
 const avatarDone=data.avatar?.state==='accepted';
 const avatarRunning=['queued','submitting'].includes(data.avatar?.state);
 const steps=[['1. Verification payment',paid?'Complete':'Next: complete payment'],['2. Identity and PAN',identity?'Identity received · review PAN status':paid?'Next: connect DigiLocker':'Locked · complete payment'],['3. Live face verification',live?'Complete':identity?'Next: verify your face':'Locked · share identity'],['4. Your avatar',avatarDone?'Complete':avatarRunning?'Generating in background':live?'Next: review selfie and generate':'Locked · complete live face verification'],['5. Background checks',identity&&data.bundle?.consented?'Automatic · see individual results':'Locked · identity and consent required']];
 const next=!paid?'Complete verification payment.':!identity?'Connect DigiLocker and share Aadhaar plus your issued PAN document.':!live?'Complete live face verification.':!avatarDone&&!avatarRunning?'Review your verified selfie, confirm avatar consent and start generation.':'Your background checks and avatar progress appear below. Resolve any item marked Review needed.';
 return `<section class="card verification-sequence"><h2>Your next step</h2><p role="status">${safe(next)}</p><ol style="list-style:none;padding:0">${steps.map(([name,state])=>`<li style="margin:12px 0;${state.startsWith('Locked')?'color:#777;':state==='Complete'?'color:#111;font-weight:700;':''}">${state==='Complete'?'✓ ':''}${safe(name)} — ${safe(state)}</li>`).join('')}</ol><p class="hint">PAN comes from a separate issued PAN document in DigiLocker, not from Aadhaar. Missing PAN blocks employment screening, not court or FIR processing.</p></section>`;
}
