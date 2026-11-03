import * as digilocker from '../digilocker.js';
export async function load(session) {
  const [checks,identity,plan,liveness]=await Promise.all([session.get('/api/v1/verification'),digilocker.load(session),session.get('/api/v1/verification/plan'),session.get('/api/v1/verification/liveness')]);
  return {...checks,digilocker:identity,plan,liveness};
}
const labels = {queued:'Waiting to start', processing:'Verification in progress', pending:'Provider processing',
  verified:'Selected fields verified', partially_verified:'Partially verified', needs_review:'Needs review',
  unavailable:'Check unavailable', outcome_unknown:'Awaiting support review', result_available:'Search ready for result retrieval',
  blocked:'Waiting for setup',not_started:'Not started',not_confirmed:'Verification attempt not confirmed',reviewed_satisfied:'Requirements met after review',
  reviewed_needs_review:'Review in progress',reviewed_not_satisfied:'Needs follow-up',waived:'Exception recorded'};

export function render({data, safe}) {
  if (!data) return '<section class="card">Loading verification…</section>';
  return `${data.plan?.assigned?`<section class="card"><h2>Your verification plan</h2><p>${safe(data.plan.country)} · ${safe(data.plan.city)} · ${safe(data.plan.environment)}</p>
    ${data.plan.checks.map(c=>`<p>${safe(c.label)} · Phase ${safe(c.phase)} · ${safe(labels[c.state]||c.state)}${c.message?`<br>${safe(c.message)}`:''}</p>`).join('')}</section>`:''}
    ${digilocker.render(data.digilocker,safe)}
    ${data.liveness?`<section class="card"><h2>Liveness Secure</h2><p>${safe(data.liveness.message)}</p><p>Document photo reference: ${data.liveness.reference_photo_available?'received':'not received yet'}</p><p>Selfie capture will be available after the vendor upload integration is connected.</p></section>`:''}
    <section class="card"><h1>Verify your details</h1><p>Enter details → consent to the check → view your results.</p>
    ${data.environment==='preproduction'?'<p>Sandbox testing — results do not approve your account.</p>':''}
    <p>${safe(data.overall_approval)}</p>
    ${(data.results||[]).map(r=>`<article><h3>${safe(data.checks[r.operation]||data.result_labels?.[r.operation]||'Verification result')}</h3><p>${safe(labels[r.state]||r.state)} · ${safe(r.environment)}</p>
      <p>${safe(r.message||'Your request is saved.')}</p>${Object.entries(r.fields||{}).map(([k,v])=>`<p>${safe(k)}: ${safe(v.replaceAll('_',' '))}</p>`).join('')}
      ${r.can_fetch_result?`<button type="button" data-bgv-result="${safe(r.id)}">Retrieve linked result</button>`:''}
      ${r.can_check_again?`<button type="button" data-bgv-poll="${safe(r.id)}">Check pending result again</button>`:''}</article>`).join('')}
    <button id="bgv-refresh" type="button">Refresh status</button></section>
    ${data.enabled?`<form id="bgv-form" class="card"><h2>Request a check</h2>
    <label>Check<select name="operation">${Object.entries(data.checks).map(([k,v])=>`<option value="${safe(k)}">${safe(v)}</option>`).join('')}</select></label>
    <div id="bgv-inputs"></div>
    <label><input type="checkbox" name="consent" required> ${safe(data.consent_text)}</label>
    <p>Submit only your own details. Original declarations are kept separately from provider results.</p>
    <button type="submit">Submit for verification</button></form>`:'<section class="card">Verification checks are not enabled yet.</section>'}`;
}

export function bind(root, ctx) {
  const {session, run, patch} = ctx;
  digilocker.bind(root,{session,run,data:ctx.data?.digilocker,patch:next=>patch({...ctx.data,digilocker:next})});
  root.querySelector('#bgv-refresh')?.addEventListener('click',()=>run(async()=>patch(await load(session))));
  root.querySelectorAll?.('[data-bgv-result]').forEach(button=>{
    const id=crypto.randomUUID();
    button.addEventListener('click',()=>run(async()=>patch({...ctx.data,...await session.post(`/api/v1/verification/${button.dataset.bgvResult}/result`,{request_id:id})})));
  });
  root.querySelectorAll?.('[data-bgv-poll]').forEach(button=>button.addEventListener('click',()=>run(async()=>patch({...ctx.data,...await session.post(`/api/v1/verification/${button.dataset.bgvPoll}/check-again`,{})}))));
  const form = root.querySelector('#bgv-form');
  if (!form) return;
  let requestId = crypto.randomUUID();
  const input = (name,label,type='text')=>`<label>${label}<input name="${name}" type="${type}" required autocomplete="off" maxlength="500"></label>`;
  function fields() {
    const operation = form.elements.operation.value;
    form.querySelector('#bgv-inputs').innerHTML = operation==='current_employer'
      ? input('employer','Declared current employer')+input('panNumber','PAN required by employer check')+input('mobile','Mobile')
      :input('name','Full name')+input('address','Address');
    form.elements.consent.checked = false;
    requestId = crypto.randomUUID();
  }
  fields(); form.elements.operation.addEventListener('change', fields);
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    const operation = values.operation;
    const inputs = operation==='current_employer'?{panNumber:values.panNumber,mobile:values.mobile}
      :operation==='individual_search'?{name:values.name,address:values.address,matchType:'possible',caseCategory:'criminal'}
      :{name:values.name,address:values.address,matchType:'possible'};
    const declared = operation==='current_employer'?{employer:values.employer}:{};
    run(async()=>patch({...ctx.data,...await session.post('/api/v1/verification',{request_id:requestId,operation,inputs,declared,
      consent:form.elements.consent.checked,consent_version:ctx.data.consent_version})}));
  });
}
