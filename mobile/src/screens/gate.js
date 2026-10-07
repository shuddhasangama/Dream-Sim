import { pairContext } from './pairContext.js';
const preferred=['relationship_meaning','exclusivity_check','timeline_expectation','open_question','disagreement_handling','money_talk'];
export function nextStep(d) {
 if(!d.gate)return 'Start your conversation.';
 if(d.gate.status!=='open')return 'Return Home for your next step.';
 if(!d.my_questions_submitted)return 'Choose up to three topics.';
 if((d.asked||[]).some(q=>!d.my_answers?.[q.key]))return 'Answer the open questions below.';
 if(!d.report?.complete)return 'Your answers are saved. Waiting for your partner.';
 if(d.reflection?.test_mode&&!d.reflection.my_ready)return 'Review your answers, then finish reflection.';
 if(!d.may_confirm)return 'Waiting for both partners to finish reflection.';
 if(!d.gate.my_confirmed)return 'Choose whether to move to Relationship.';
 if(!d.gate.partner_confirmed)return 'Waiting for your partner’s choice.';
 if(!d.my_prerequisites?.met)return 'Complete the missing profile details below.';
 if(!d.gate.my_exclusivity_ack)return 'Acknowledge exclusivity below.';
 if(!d.gate.my_entry_complete)return 'Read and sign your relationship agreement.';
 if(!d.partner_prerequisites_met||!d.gate.partner_entry_complete||!d.gate.partner_exclusivity_ack)return 'Your steps are done. Waiting for your partner.';
 return 'You are both ready. Select Enter Relationship.';
}
export function render(ctx) {
 const {data:d,safe:s}=ctx;
 if(!d)return '<h1>Relationship conversation</h1><p>Loading…</p>';
 const button=(action,label,disabled=false)=>`<button class="secondary" type="button" data-gate="${action}" ${disabled?'disabled':''}>${label}</button>`;
 let html=`<h1>Relationship conversation</h1>${pairContext(ctx)}<section class="card guidance"><h2>Next step</h2><p role="status">${s(nextStep(d))}</p><button class="secondary" id="gate-refresh">Refresh progress</button></section>`;
 if(!d.gate)return html+button('raise','Start the conversation');
 if(d.gate.status!=='open')return html+`<p class="activity-complete">${d.gate.status==='progressed'?'✓ Relationship started':'Conversation closed'}</p>`;
 html+=`<section class="card"><h2>${d.my_questions_submitted?'✓ Topics chosen':'Choose topics'}</h2>`;
 if(!d.my_questions_submitted) {
  const qs=d.questions||[];
  const option=q=>`<label class="checkbox-row"><input type="checkbox" name="question" value="${s(q.key)}">${s(q.text)}${d.asked?.some(a=>a.key===q.key)?' · Partner chose this':''}</label>`;
  html+=`<form id="gate-ask"><p>Choose up to three, including an optional question of your own.</p>${qs.filter(q=>preferred.includes(q.key)).map(option).join('')}<details><summary>More topics</summary>${qs.filter(q=>!preferred.includes(q.key)&&!q.key.startsWith('custom_')).map(option).join('')}</details><label>Your own question<textarea name="custom" maxlength="300"></textarea></label><button class="secondary">Save topics</button></form>`;
 }
 html+='</section>';
 if(d.asked?.length)html+=`<section class="card"><h2>Answer together</h2>${d.asked.map(q=>{
  const value=d.my_answers?.[q.key]||'', partner=d.partner_answers?.[q.key];
  const frozen=d.gate.my_confirmed||d.gate.partner_confirmed;
  const answered=d.partner_answered?.includes(q.key);
  return `<article class="conversation-question"><h3>${s(q.prompt)}</h3><p class="question-origin">${s(({you:'Chosen by you',partner:'Chosen by your partner',both:'Chosen by both'})[q.origin]||'Shared topic')}</p><div class="answer-columns"><form data-answer="${s(q.key)}"><h4>You ${value?'✓':''}</h4><label><span class="sr-only">Your answer</span>${q.kind==='scale'?`<select name="value" required ${frozen?'disabled':''}><option value="">Choose…</option>${(q.options||[]).map(o=>`<option value="${s(o)}" ${value===o?'selected':''}>${s(o.replaceAll('_',' '))}</option>`).join('')}</select>`:`<textarea name="value" required maxlength="4000" ${frozen?'disabled':''}>${s(value)}</textarea>`}</label><label class="checkbox-row"><input type="checkbox" name="share" ${d.my_sharing?.[q.key]?'checked':''} ${frozen?'disabled':''}>Share this answer once we both answer</label><button class="secondary" ${frozen?'disabled':''}>Save answer</button></form><div><h4>Your partner ${answered?'✓':''}</h4><p>${partner?s(partner.replaceAll('_',' ')):answered?'Answer saved privately.':'Waiting for an answer.'}</p></div></div></article>`;
 }).join('')}</section>`;
 html+=`<section class="card"><h2>${d.gate.my_confirmed?'✓ ':''}Reflect and choose</h2><p>${d.report?.complete?'Both answers are saved. Review them before choosing.':'Reflection opens once all answers are saved.'}</p>${d.reflection?.test_mode?button('reflection-ready',d.reflection.my_ready?'✓ Reflection complete':'Finish reflection (test)',!d.report?.complete||d.reflection.my_ready):`<p>${s(d.reflection?.note||'')}</p>`}<p>You: ${d.gate.my_confirmed?'✓ Confirmed':'Not confirmed'} · Partner: ${d.gate.partner_confirmed?'✓ Confirmed':'Waiting'}</p>${button('confirm','Move to Relationship',!d.may_confirm||d.gate.my_confirmed)}${button('decline','Stay in Dating')}</section>`;
 const pre=d.my_prerequisites||{};
 html+=`<section class="card"><h2>Readiness and agreement</h2><p>Your profile: ${pre.met?'✓ Complete':'Needs attention'} · Partner: ${d.partner_prerequisites_met?'✓ Complete':'Waiting'}</p>${!pre.met?`<p>${s([...(pre.vision_met?[]:['Vision']),...(pre.stats_missing||[]),...(pre.chemistry_missing||[])].map(k=>k.replaceAll('_',' ')).join(', '))}</p><button class="secondary" data-profile="dashboard">Complete profile</button>`:''}<button class="secondary" data-profile="boundaries">Review boundaries</button>${button('exclusivity-ack',d.gate.my_exclusivity_ack?'✓ Exclusivity acknowledged':'Acknowledge exclusivity',d.gate.my_exclusivity_ack)}<button class="secondary" id="entry-agreement" ${d.gate.my_confirmed&&d.gate.partner_confirmed?'':'disabled'}>${d.gate.my_entry_complete?'✓ Review signed agreement':'Read and sign agreement'}</button><p>Partner agreement: ${d.gate.partner_entry_complete?'✓ Complete':'Waiting'}</p>${button('enter-relationship','Enter Relationship',!d.gate.my_confirmed||!d.gate.partner_confirmed||!pre.met||!d.partner_prerequisites_met||!d.gate.my_entry_complete||!d.gate.partner_entry_complete||!d.gate.my_exclusivity_ack||!d.gate.partner_exclusivity_ack)}</section>`;
 return html;
}
export function bind(root,ctx){
 const base=`/api/v1/lock-ins/${encodeURIComponent(ctx.data.lock_in_id)}/gate`;
 root.querySelector('#gate-refresh')?.addEventListener('click',()=>ctx.run(async()=>{ctx.patch(await ctx.session.get(base));await ctx.refreshJourney();}));
 const act=async(action,body={})=>{const result=await ctx.session.post(`${base}/${action}`,{...(action==='raise'?{}:{round:ctx.data.gate.round}),...body});await ctx.refreshJourney();if(result.advanced)ctx.patch({...ctx.data,gate:{...ctx.data.gate,status:'progressed'}});else ctx.patch(result);};
 root.querySelectorAll('[data-gate]').forEach(b=>b.addEventListener('click',()=>ctx.run(()=>act(b.dataset.gate,b.dataset.gate==='exclusivity-ack'?{acknowledged:true}:{}))));
 root.querySelector('#gate-ask')?.addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target),custom=f.get('custom').trim();ctx.run(()=>act('ask',{question_keys:f.getAll('question'),...(custom?{custom_question:custom}:{})}));});
 root.querySelectorAll('[data-answer]').forEach(f=>f.addEventListener('submit',e=>{e.preventDefault();const form=new FormData(f);ctx.run(()=>act('answer',{question_key:f.dataset.answer,value:form.get('value').trim(),share_with_partner:form.has('share')}));}));
 root.querySelector('#entry-agreement')?.addEventListener('click',()=>ctx.navigateTo('ceremony',{lockInId:ctx.data.lock_in_id,kind:'relationship_entry',returnTo:'gate'}));
 root.querySelectorAll('[data-profile]').forEach(b=>b.addEventListener('click',()=>ctx.navigateTo(b.dataset.profile)));
}
