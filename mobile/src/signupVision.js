// Initial setup: versioned server vocabulary, separate from profile evolution.
const PLANS=[['grow','Family'],['two','Together'],['explore','Travel together'],['custom','Customise your plan']];
// Client answer 1: Custom lets the member add up to four pillars of their own.
export const MAX_CUSTOM=4;
const PILLARS=['Intimacy','Kids','Cohabitate','Travel together'];
const LABELS={'Travel together':'Travel','Chores split':'Chores','Expenses sharing':'Expenses'};
const ICONS={grow:'<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-8h6v8"/>',two:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',explore:'<path d="m22 2-7 20-4-9-9-4 20-7ZM11 13 22 2"/>',custom:'<path d="M3 6h18M3 18h18"/><circle cx="8" cy="6" r="3"/><circle cx="16" cy="18" r="3"/>'};
export const empty=()=>({plan:null,pillars:{Intimacy:['Emotional']},kids_intent:'undecided',focus:'Intimacy',custom_pillars:[]});
export function inferPlan(pillars,custom=[]){
 if(custom.length)return 'custom';
 const keys=Object.keys(pillars).sort().join('|');
 if(keys===[...PILLARS].sort().join('|'))return 'grow';
 if(keys===['Intimacy','Cohabitate','Travel together'].sort().join('|'))return 'two';
 if(keys===['Intimacy','Travel together'].sort().join('|'))return 'explore';
 return 'custom';
}
function align(next){
 next.plan=inferPlan(next.pillars,next.custom_pillars||[]);
 next.kids_intent='Kids' in next.pillars?'want':next.plan==='two'?'no':'undecided';
 return next;
}
export function choose(data,key){
 const item=(data.signup_presets||[]).find(p=>p.key===key);
 if(!item)throw Error('The updated signup choices are unavailable.');
 return {plan:key,pillars:key==='custom'?{Intimacy:['Emotional']}:structuredClone(item.choices),kids_intent:item.kids_intent,focus:'Intimacy',custom_pillars:[]};
}
export function render({data,safe}){
 const draft=data?._signupVision||empty(),focus='Intimacy';
 const available=!!data?.signup_presets;
 const active=Object.hasOwn(draft.pillars,focus);
 return `<section class="card signup-vision"><h1>Your Together plan</h1><p class="hint">Choose a starting point. Make it yours.</p>
 <div class="signup-plans" role="group" aria-label="Together Plan">${PLANS.map(([key,name])=>`<button type="button" data-signup-plan="${key}" aria-pressed="${draft.plan===key}" ${available?'':'disabled'}><svg class="plan-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">${ICONS[key]}</svg><span>${name}</span><span class="plan-selection" aria-hidden="true">${draft.plan===key?"●":"○"}</span></button>`).join('')}</div>
 ${available?`<form id="signup-vision-form"><h2 class="pillars-heading">Your pillars</h2><p class="hint">Your plan includes these pillars. Adjust the optional ones.</p><div class="signup-focus-grid">${PILLARS.map(key=>{
  const included=Object.hasOwn(draft.pillars,key),detailed=key==='Intimacy';
  return `<div class="signup-pillar-tile ${focus===key?'is-focused':''}"><div class="signup-pillar-heading">
   ${detailed?`<button type="button" class="signup-focus-title" data-signup-focus="${safe(key)}" aria-expanded="${focus===key}" aria-controls="signup-pillar-detail">${safe(LABELS[key]||key)}</button>`:`<span>${safe(LABELS[key]||key)}</span>`}
   ${key==='Intimacy'?'':`<label class="signup-switch"><input type="checkbox" role="switch" data-signup-pillar="${safe(key)}" aria-label="Include ${safe(LABELS[key]||key)}" ${included?'checked':''}><span aria-hidden="true"></span></label>`}
   </div><small>${key==='Intimacy'?'Required':included?'Included':'Optional'}</small></div>`;
 }).join('')}</div>
 <section id="signup-pillar-detail" aria-label="${safe(focus)} choices"><h2>${focus==='Intimacy'?'Closeness that matters':'Sharing a home'}</h2>
 ${!active?'<p class="hint">Switch on Cohabitate to choose your priorities.</p>':''}
 <div class="signup-focus-choices">${(data.signup_pillar_options?.[focus]||[]).map(value=>`<label><input type="checkbox" data-signup-choice="${safe(focus)}" value="${safe(value)}" ${value==='Emotional'||active&&draft.pillars[focus].includes(value)?'checked':''} ${value==='Emotional'||!active?'disabled':''}><span>${safe(LABELS[value]||value)}</span></label>`).join('')}</div></section></form>`:'<p role="alert">The updated signup is not available on this server yet.</p>'}
 ${draft.plan==='custom'?ownPillars(draft,safe):''}
 ${data?._error?`<p class="warn" role="alert">${safe(data._error)}</p>`:''}</section>`;
}
export function ownPillars(draft,safe){
 const own=draft.custom_pillars||[];
 return `<section class="signup-own-pillars" aria-label="Your own pillars"><h2>Your own pillars</h2>
  <ul>${own.map(name=>`<li>${safe(name)} <button type="button" class="text-button" data-remove-own-pillar="${safe(name)}">Remove</button></li>`).join('')}</ul>
  ${own.length<MAX_CUSTOM?`<div><input id="own-pillar" maxlength="40" placeholder="For example, Faith" aria-label="Name a pillar of your own"><button type="button" id="add-own-pillar">Add pillar</button></div>`:''}
  <p class="hint">Up to ${MAX_CUSTOM} pillars of your own, alongside the four above.</p></section>`;
}
export function addOwnPillar(draft,name){
 const clean=String(name||'').trim().replace(/\s+/g,' ');
 const taken=[...PILLARS,'Travel',...(draft.custom_pillars||[])].map(x=>x.toLocaleLowerCase());
 if(!clean||clean.length>40)throw Error('Name your pillar in 1 to 40 characters.');
 if(taken.includes(clean.toLocaleLowerCase()))throw Error('Choose a pillar that is not already listed.');
 if((draft.custom_pillars||[]).length>=MAX_CUSTOM)throw Error(`Add up to ${MAX_CUSTOM} pillars of your own.`);
 return {...structuredClone(draft),plan:'custom',custom_pillars:[...(draft.custom_pillars||[]),clean]};
}
export function bind(root,{data,run,patch}){
 const update=next=>run(async()=>patch({...data,_signupVision:next,_signupDirty:true,_error:''}));
 root.querySelector('#add-own-pillar')?.addEventListener('click',()=>{let next;try{next=addOwnPillar(data._signupVision||empty(),root.querySelector('#own-pillar').value);}catch(e){run(async()=>patch({...data,_error:e.message}));return;}update(next);});
 root.querySelectorAll('[data-remove-own-pillar]').forEach(button=>button.addEventListener('click',()=>{const next=structuredClone(data._signupVision||empty());next.custom_pillars=(next.custom_pillars||[]).filter(x=>x!==button.dataset.removeOwnPillar);update(next);}));
 root.querySelectorAll('[data-signup-plan]').forEach(button=>button.addEventListener('click',()=>update(choose(data,button.dataset.signupPlan))));
 root.querySelectorAll('[data-signup-focus]').forEach(button=>button.addEventListener('click',()=>update({...structuredClone(data._signupVision||empty()),focus:button.dataset.signupFocus})));
 root.querySelectorAll('[data-signup-pillar]').forEach(input=>input.addEventListener('change',()=>{
  const next=structuredClone(data._signupVision||empty()),key=input.dataset.signupPillar;
  if(input.checked)next.pillars[key]=[];else delete next.pillars[key];
  next.focus='Intimacy';update(align(next));
 }));
 root.querySelectorAll('[data-signup-choice]').forEach(input=>input.addEventListener('change',()=>{
  const next=structuredClone(data._signupVision||empty()),key=input.dataset.signupChoice;
  next.pillars[key]=[...root.querySelectorAll('[data-signup-choice]')].filter(el=>el.dataset.signupChoice===key&&el.checked).map(el=>el.value);
  update(align(next));
 }));
}
export async function save(session,data){
 const draft=data._signupVision;
 if(draft?.pillars?.Intimacy&&!draft.pillars.Intimacy.includes('Emotional'))draft.pillars.Intimacy.unshift('Emotional');
 if(!draft?.plan)throw Error('Choose your Together Plan to continue.');
 const result=await session.put('/api/v1/profile/vision/template',{schema_version:2,template:draft.plan,pillars:draft.pillars,kids_intent:draft.kids_intent,...(draft.plan==='custom'?{custom_pillars:draft.custom_pillars||[]}:{})});
 const saved=Object.fromEntries((result.goals||[]).map(g=>[g.key,g.stance||[]]));
 if(result.schema_version!==2||result.template_key!==draft.plan||Object.keys(saved).length!==Object.keys(draft.pillars).length||Object.entries(draft.pillars).some(([key,values])=>!saved[key]||values.length!==saved[key].length||values.some(v=>!saved[key].includes(v))))throw Error('Could not confirm your saved plan. Please try again.');
 return result;
}
