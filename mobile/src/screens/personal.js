// Optional disclosures are never inferred from a photo or a missing answer.
export function render({data,safe}) {
 if(!data) return '<p>Loading profile…</p>';
 const h=data.health||{}, p=data.openness||{};
 const options=(name,selected)=>(Object.entries(data.categories||{}).map(([k,v])=>`<label class="checkbox-row"><input type="checkbox" name="${name}" value="${k}" ${selected.includes(k)?'checked':''}> ${safe(v)}</label>`).join(''));
 return `<h2>Your profile portrait</h2><p>Use a clear head-and-shoulders photo with simple lighting and background. No identity document is needed. Photos do not confer verification.</p>
 ${data.photo?`<img class="profile-portrait" src="${safe(data.photo)}" alt="Your profile portrait">`:''}
 <label for="portrait-file">Choose a portrait</label><input id="portrait-file" type="file" accept="image/jpeg,image/png,image/webp">
 <p id="personal-photo-note" role="status"></p><div id="portrait-editor" hidden><canvas id="portrait-canvas" width="480" height="600" class="profile-portrait"></canvas>
 <label>Zoom<input id="portrait-zoom" type="range" min="1" max="3" step="0.01" value="1"></label>
 <label>Horizontal position<input id="portrait-x" type="range" min="0" max="1" step="0.01" value="0.5"></label>
 <label>Vertical position<input id="portrait-y" type="range" min="0" max="1" step="0.01" value="0.5"></label>
 <button type="button" id="portrait-save">Save portrait</button></div>
 ${data.photo?'<button type="button" id="portrait-remove">Remove photo</button>':''}
 <form id="personal-form"><h2>Ethnicity / cultural background</h2><p>Optional, up to two. Separate from nationality; shown on your match profile.</p>
 ${(data.ethnicity_options||[]).map(v=>`<label class="checkbox-row"><input type="checkbox" name="ethnicity" value="${safe(v)}" ${(data.ethnicity||[]).includes(v)?'checked':''}> ${safe(v)}</label>`).join('')}
 <h2>Health &amp; accessibility</h2><p>Optional and self-declared. Share only what you are comfortable showing to potential matches. This is not a medical assessment. An unanswered profile does not mean no conditions.</p>
 ${options('categories',h.categories||[])}
 <label>What would you like a potential partner to know? <textarea name="note" maxlength="500">${safe(h.note||'')}</textarea></label>
 <label class="checkbox-row"><input name="share_health" type="checkbox" ${h.consent?'checked':''}> I consent to displaying these details to potential matches and using the selected categories for matching.</label>
 <p class="hint">To withdraw, clear the categories and note, untick consent, and save. Previously viewed information cannot be recalled.</p>
 <h2>My openness to a partner's disclosures</h2><p>These preferences are private. They apply to future matching, not existing pairs.</p>
 <label>Partner disclosure preference<select name="openness"><option value="any" ${p.mode!=='specific'?'selected':''}>Open to any / no filter</option><option value="specific" ${p.mode==='specific'?'selected':''}>Open to selected categories</option></select></label>
 ${options('open_categories',p.categories||[])}
 <label class="checkbox-row"><input type="checkbox" name="include_undisclosed" ${p.include_undisclosed!==false?'checked':''}> Include people who have not disclosed (their status is unknown)</label>
 <p class="hint">With selected categories, all categories someone shares must be included. An empty selection excludes all disclosed categories; it does not establish anyone's health status.</p>
 <button type="submit" class="primary">Save profile preferences</button></form>
 ${data._saved?'<p role="status">Saved ✓</p>':''}${data._error?`<p role="alert" class="warn">${safe(data._error)}</p>`:''}`;
}
export function bind(root,ctx) {
 const {session,run,patch,data}=ctx;
 let formDirty=false;
 for(const event of ['input','change']) root.querySelector('#personal-form')?.addEventListener(event,()=>{formDirty=true;});
 root.querySelector('#personal-form')?.addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);run(async()=>{
 try{patch({...await session.put('/api/v1/profile/personal',{ethnicity:f.getAll('ethnicity'),categories:f.getAll('categories'),note:f.get('note'),share_health:f.has('share_health'),openness:f.get('openness'),open_categories:f.getAll('open_categories'),include_undisclosed:f.has('include_undisclosed')}),_saved:true});}
 catch(e){patch({...data,health:{consent:f.has('share_health'),categories:f.getAll('categories'),note:f.get('note')},ethnicity:f.getAll('ethnicity'),openness:{mode:f.get('openness'),categories:f.getAll('open_categories'),include_undisclosed:f.has('include_undisclosed')},_saved:false,_error:e.message});}
 });});
 let img=null;
 const canvas=root.querySelector('#portrait-canvas');
 const draw=()=>{if(!img)return;const z=+root.querySelector('#portrait-zoom').value;const scale=Math.max(480/img.width,600/img.height)*z;
 const w=480/scale,h=600/scale,x=(img.width-w)*+root.querySelector('#portrait-x').value,y=(img.height-h)*+root.querySelector('#portrait-y').value;
 canvas.getContext('2d').drawImage(img,x,y,w,h,0,0,480,600);};
 for(const id of ['portrait-zoom','portrait-x','portrait-y']) root.querySelector('#'+id)?.addEventListener('input',draw);
 root.querySelector('#portrait-file')?.addEventListener('change',async e=>{
 const file=e.target.files[0];if(!file)return;
 if(file.size>10000000){run(async()=>patch({...data,_error:'Choose an image under 10 MB.'}));return;}
 const reader=new FileReader();reader.onload=()=>{img=new Image();img.onload=()=>{root.querySelector('#portrait-editor').hidden=false;draw();};img.onerror=()=>run(async()=>patch({...data,_error:'Use a JPEG, PNG or WebP photo.'}));img.src=reader.result;};reader.readAsDataURL(file);
 });
 const save=photo=>{if(formDirty){root.querySelector('#personal-photo-note').textContent='Save your profile preferences before changing your photo.';return;} return run(async()=>{try{patch({...await session.put('/api/v1/profile/photo',{photo}),_saved:true});}catch(e){patch({...data,_error:e.message});}});};
 root.querySelector('#portrait-save')?.addEventListener('click',()=>save(canvas.toDataURL('image/jpeg',0.85)));
 root.querySelector('#portrait-remove')?.addEventListener('click',()=>save(null));
}
