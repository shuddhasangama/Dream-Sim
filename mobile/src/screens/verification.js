export async function load(session) { return session.get('/api/v1/verification'); }
const labels = {queued:'Waiting to start', processing:'Verification in progress', pending:'Provider processing',
  verified:'Selected fields verified', partially_verified:'Partially verified', needs_review:'Needs review',
  unavailable:'Check unavailable', outcome_unknown:'Awaiting support review'};

export function render({data, safe}) {
  if (!data) return '<section class="card">Loading verification…</section>';
  return `<section class="card"><h1>Verify your details</h1><p>Enter details → consent to the check → view your results.</p>
    ${data.environment==='preproduction'?'<p>Sandbox testing — results do not approve your account.</p>':''}
    <p>${safe(data.overall_approval)}</p>
    ${(data.results||[]).map(r=>`<article><h3>${safe(data.checks[r.operation])}</h3><p>${safe(labels[r.state]||r.state)} · ${safe(r.environment)}</p>
      <p>${safe(r.message||'Your request is saved.')}</p>${Object.entries(r.fields||{}).map(([k,v])=>`<p>${safe(k)}: ${safe(v.replaceAll('_',' '))}</p>`).join('')}</article>`).join('')}
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
  root.querySelector('#bgv-refresh')?.addEventListener('click',()=>run(async()=>patch(await load(session))));
  const form = root.querySelector('#bgv-form');
  if (!form) return;
  let requestId = crypto.randomUUID();
  const input = (name,label,type='text')=>`<label>${label}<input name="${name}" type="${type}" required autocomplete="off" maxlength="500"></label>`;
  function fields() {
    const operation = form.elements.operation.value;
    form.querySelector('#bgv-inputs').innerHTML = operation==='pan_simple'
      ? input('name','Legal name')+input('dob','Date of birth','date')+input('panNumber','PAN')
      : operation==='current_employer'?input('employer','Declared current employer')+input('panNumber','PAN')+input('mobile','Mobile')
      : operation==='individual_search'?input('name','Full name')+input('address','Address')
      :input('uan','UAN (12 digits)');
    form.elements.consent.checked = false;
    requestId = crypto.randomUUID();
  }
  fields(); form.elements.operation.addEventListener('change', fields);
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    const operation = values.operation;
    const inputs = operation==='pan_simple'?{panNumber:values.panNumber}
      :operation==='current_employer'?{panNumber:values.panNumber,mobile:values.mobile}
      :operation==='individual_search'?{name:values.name,address:values.address,matchType:'exact'}
      :{uan:values.uan,consentFlag:'Y',ttl:0};
    const declared = operation==='pan_simple'?{name:values.name,dob:values.dob}
      :operation==='current_employer'?{employer:values.employer}:{};
    run(async()=>patch(await session.post('/api/v1/verification',{request_id:requestId,operation,inputs,declared,
      consent:form.elements.consent.checked,consent_version:ctx.data.consent_version})));
  });
}
