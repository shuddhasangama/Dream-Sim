// Initial selection only. Existing-profile evolution belongs to screens/vision.js.
const PLANS=[['grow','Family'],['two','We Two'],['explore','Travel'],['custom','Custom']];
const PILLARS=['Intimacy','Kids','Cohabitate','Travel together'];
export const empty=()=>({plan:null,pillars:{},kids_intent:'undecided'});
export function choose(data,key){
 const item=(data.presets||[]).find(p=>p.key===key);
 const pillars=key==='custom'?{Intimacy:[]}:structuredClone(item?.choices||{});
 if(['grow','two'].includes(key))pillars['Travel together']=[];
 return {plan:key,pillars,kids_intent:item?.kids_intent||'undecided'};
}
export function render({data,safe}){
 const draft=data?._signupVision||empty();
 return `<section class="card signup-vision"><h1>Select your Twogether Plan</h1>
 <div class="signup-plans" role="group" aria-label="Twogether Plan">${PLANS.map(([key,name])=>`<button type="button" data-signup-plan="${key}" aria-pressed="${draft.plan===key}">${name}</button>`).join('')}</div>
 ${draft.plan?`<form id="signup-vision-form"><div class="signup-pillars">${PILLARS.map(key=>{
  const enabled=Object.hasOwn(draft.pillars,key);
  return `<fieldset><legend><label><input type="checkbox" data-signup-pillar="${safe(key)}" ${enabled?'checked':''} ${key==='Intimacy'?'disabled':''}> ${key==='Travel together'?'Travel':safe(key)}${key==='Intimacy'?' <small>Required</small>':''}</label></legend>
  ${(data.pillar_options?.[key]||[]).map(value=>`<label class="checkbox-row"><input type="checkbox" data-signup-choice="${safe(key)}" value="${safe(value)}" ${enabled&&draft.pillars[key].includes(value)?'checked':''} ${enabled?'':'disabled'}> ${safe(value==='Chores split'?'Chores':value==='Expenses sharing'?'Expenses':value)}</label>`).join('')}
  </fieldset>`;
 }).join('')}</div></form>`:'<p class="hint">Choose a plan to see its pillars. You can switch plans or customise your choices.</p>'}
 ${data?._error?`<p class="warn" role="alert">${safe(data._error)}</p>`:''}</section>`;
}
export function bind(root,{data,run,patch}){
 const update=next=>run(async()=>patch({...data,_signupVision:next,_signupDirty:true,_error:''}));
 root.querySelectorAll('[data-signup-plan]').forEach(button=>button.addEventListener('click',()=>update(choose(data,button.dataset.signupPlan))));
 root.querySelectorAll('[data-signup-pillar]').forEach(input=>input.addEventListener('change',()=>{
  const next=structuredClone(data._signupVision||empty());const key=input.dataset.signupPillar;
  if(input.checked)next.pillars[key]=[];else delete next.pillars[key];
  next.plan='custom';next.kids_intent='Kids' in next.pillars?'want':'undecided';update(next);
 }));
 root.querySelectorAll('[data-signup-choice]').forEach(input=>input.addEventListener('change',()=>{
  const next=structuredClone(data._signupVision||empty());const key=input.dataset.signupChoice;
  next.pillars[key]=[...root.querySelectorAll('[data-signup-choice]')].filter(x=>x.dataset.signupChoice===key&&x.checked).map(x=>x.value);
  next.plan='custom';update(next);
 }));
}
export async function save(session,data){
 const draft=data._signupVision;
 if(!draft?.plan)throw Error('Choose your Twogether Plan to continue.');
 const result=await session.put('/api/v1/profile/vision/template',{template:draft.plan,pillars:draft.pillars,kids_intent:draft.kids_intent,travel:'Travel together' in draft.pillars});
 const saved=Object.fromEntries((result.goals||[]).map(g=>[g.key,g.stance||[]]));
 if(Object.keys(saved).length!==Object.keys(draft.pillars).length||Object.entries(draft.pillars).some(([key,values])=>!saved[key]||values.length!==saved[key].length||values.some(value=>!saved[key].includes(value))))throw Error('Could not confirm your saved plan. Please try again.');
 return result;
}
