// Optional disclosures are never inferred from a photo or a missing answer.
// The uploaded profile portrait was retired on 2026-11-25 (the AI avatar replaces it).
export function render({data,safe,statsOnly=false}) {
 if(!data) return '<p>Loading profile…</p>';
 const h=data.health||{}, p=data.openness||{};
 const options=(name,selected)=>(Object.entries(data.categories||{}).map(([k,v])=>`<label class="checkbox-row"><input type="checkbox" name="${name}" value="${k}" ${selected.includes(k)?'checked':''}> ${safe(v)}</label>`).join(''));
 return `${statsOnly?'':'<h1>Your Bio</h1>'}<form id="personal-form"><details><summary><strong>Ethnicity / cultural background</strong> · ${safe((data.ethnicity||[]).join(", ")||"Optional")}</summary><p>Optional, up to two. Separate from nationality; shown on your match profile.</p>
 ${(data.ethnicity_options||[]).map(v=>`<label class="checkbox-row"><input type="checkbox" name="ethnicity" value="${safe(v)}" ${(data.ethnicity||[]).includes(v)?'checked':''}> ${safe(v)}</label>`).join('')}
 </details><details><summary><strong>Health &amp; accessibility</strong></summary>
 ${h.consent?'<button type="button" id="health-withdraw">Withdraw health disclosure</button>':''}
 <p>Optional and self-declared. Share only what you are comfortable showing to potential matches. This is not a medical assessment. An unanswered profile does not mean no conditions.</p>
 ${options('categories',h.categories||[])}
 <label>What would you like a potential partner to know? <textarea name="note" maxlength="500">${safe(h.note||'')}</textarea></label>
 <label class="checkbox-row"><input name="share_health" type="checkbox" ${h.consent?'checked':''}> I consent to displaying these details to potential matches and using the selected categories for matching.</label>
 <p class="hint">You can withdraw disclosure at any time. Previously viewed information cannot be recalled.</p>
 <p>Partner preferences are managed privately in REACH.</p>
 </details><button type="submit" class="primary">${statsOnly?'Save background & health':'Save Bio'}</button></form>
 ${data._saved?'<p role="status">Saved ✓</p>':''}${data._error?`<p role="alert" class="warn">${safe(data._error)}</p>`:''}`;
}
export function bind(root,ctx) {
 const {session,run,patch,data}=ctx;
 root.querySelector('#health-withdraw')?.addEventListener('click',()=>run(async()=>patch({...await session.post('/api/v1/profile/bio/withdraw',{}),_saved:true})));
 root.querySelector('#personal-form')?.addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);run(async()=>{
 try{patch({...await session.put('/api/v1/profile/bio',{ethnicity:f.getAll('ethnicity'),categories:f.getAll('categories'),note:f.get('note'),share_health:f.has('share_health')}),_saved:true});}
 catch(e){patch({...data,health:{consent:f.has('share_health'),categories:f.getAll('categories'),note:f.get('note')},ethnicity:f.getAll('ethnicity'),openness:data.openness,_saved:false,_error:e.message});}
 });});
}
