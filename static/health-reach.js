export function healthForm(h, safe) {
 if(!h) return '';
 const p=h.preferences||{};
 return `<details class="card"><summary>Health &amp; accessibility preferences · ${h.ignored?'Paused by Show all':p.mode==='specific'?'Selected categories':'No filter'}</summary>
 <p>Private preferences. Applies mutually to future matches. Your own disclosure is in Bio.</p>
 <p>Broad sensory preferences include hearing and vision needs; non-visible includes neurodivergence and mental health; cancer includes current and past cancer. Selecting a narrow category does not accept an unspecified broad disclosure. Trauma remains separate.</p><form id="health-reach-form"><label>Preference<select name="mode"><option value="any" ${p.mode!=='specific'?'selected':''}>No filter</option><option value="specific" ${p.mode==='specific'?'selected':''}>Open to selected categories</option></select></label>
 ${Object.entries(h.categories).map(([k,v])=>`<label class="checkbox-row"><input type="checkbox" name="categories" value="${safe(k)}" ${(p.categories||[]).includes(k)?'checked':''}>${safe(v)}</label>`).join('')}
 <label><input type="checkbox" name="include_undisclosed" ${p.include_undisclosed!==false?'checked':''}>Include people who have not shared (unknown)</label>
 <p>For selected categories, every category a person shares must be included. No filter includes everyone regardless of disclosure. Notes are never used for filtering. Show all pauses this filter without deleting your choices; restoring filters restores it. Saving here reactivates your choice.</p>
 <button type="submit">Save preferences</button><p id="health-reach-error" role="alert"></p></form></details>`;
}
