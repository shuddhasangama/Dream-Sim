// Private and shared spaces have distinct forms and explicit sharing labels.
export function renderNavigator(n, safe) {
  if (!n?.enabled) return '';
  const drafts=n._drafts || {};
  const button=(action,label)=>`<button type="button" class="secondary" data-private-action="${action}">${label}</button>`;
  return `<section class="card"><h2>Talk with Guru</h2><p class="hint">${n.mode==='ai'?'AI-assisted conversation.':'Guided prompts.'} Your last 50 exchanges stay private from your partner. Only messages you submit in a shared conversation go to your partner.</p>
    <form id="guru-private-form"><label for="guru-topic">Explore</label><select id="guru-topic" name="topic">${n.topics.map(t=>`<option value="${safe(t.id)}" ${drafts.topic===t.id?'selected':''}>${safe(t.label)}</option>`).join('')}</select>
    <div class="guru-history" aria-label="Private conversation">${n.history.map(m=>`<div class="${m.role==='user'?'p-bubble-user':'p-bubble-guru'}"><strong>${m.role==='user'?'You':m.mode==='ai'?'Guru · AI':'Guru · guided'}</strong><p>${safe(m.text)}</p></div>`).join('')}</div>
    <label for="guru-message">Your thoughts</label><textarea id="guru-message" name="text" maxlength="800" required placeholder="What would you like to explore?">${safe(drafts.text||'')}</textarea><button class="primary">Send privately</button></form>
    ${n.ai_available?`<details><summary>Optional AI responses</summary><p class="hint">When enabled, your message, last 10 exchanges, saved memories and current stage are sent to OpenAI. We disable response storage; provider safety logs may still retain content. Turning this off stops future sends; it cannot recall earlier requests.</p><label class="checkbox-row"><input id="guru-ai" type="checkbox" ${n.ai_consent?'checked':''}> Allow OpenAI-assisted replies</label></details>`:''}
    <details><summary>Private memory & history</summary><p class="hint">Save only what you want to revisit. These notes stay private from your partner. If you enable AI responses, saved memories may be sent to OpenAI. Turning memory off deletes saved memories; history has its own delete button.</p>
      <label class="checkbox-row"><input id="guru-remember" type="checkbox" ${n.remember?'checked':''}> Enable saved memory</label>
      ${n.remember?`${n.memories.map(m=>`<form class="guru-memory-form" data-memory-id="${safe(m.id)}"><input name="text" maxlength="240" value="${safe(m.text)}" aria-label="Saved memory" required><button class="secondary">Save</button><button type="button" class="secondary" data-delete-memory="${safe(m.id)}">Delete</button></form>`).join('')}
      <form class="guru-memory-form"><input name="text" maxlength="240" placeholder="A preference or note to remember" aria-label="New memory" required><button class="secondary">Save memory</button></form>`:''}
      ${button('clear_history','Delete private history')}${button('delete_private','Delete all private Guru data')}
      <p class="hint">Deletes apply to live app storage. Existing database backups follow the operator’s retention policy.</p>
    </details></section>
    <section class="card"><h2>Talk together</h2><p class="hint">Invite your partner. Respond when ready. Private Guru notes never enter this space. This is a guided conversation, not counselling.</p>
    ${n.shared_topics.length?`<form id="guru-invite"><select name="topic" aria-label="Shared topic">${n.shared_topics.map(t=>`<option value="${safe(t.id)}">${safe(t.label)}</option>`).join('')}</select><button class="secondary">Invite partner</button></form>`:'<p>Shared conversations open when you have an eligible partner and topic.</p>'}
    <button type="button" class="secondary" id="guru-refresh">Refresh conversations</button>
    ${n.discussions.map(d=>discussion(d,safe)).join('')}</section>`;
}

function discussion(d,safe) {
  const act=(a,label)=>`<button type="button" class="secondary" data-shared-action="${a}">${label}</button>`;
  const status={invited:d.invited_by_me?'Invitation sent. Waiting for your partner.':'Your partner invited you. Join only if you want to.',active:d.my_confirmed?'Your confirmation is saved. Waiting for your partner.':d.both_responded?'Both perspectives are shared. Propose a next step together.':'Share your perspective when ready.',paused:'Paused. Both partners must choose Resume.',agreed:'Both confirmed this next step.',closed:'Conversation closed. Shared content was removed.'}[d.status];
  return `<article class="guru-discussion" data-discussion="${safe(d.id)}" data-revision="${d.revision}"><h3>${safe(d.title)}</h3><p role="status">${safe(status)}</p>
    ${d.status==='invited'&&!d.invited_by_me?act('accept','Join conversation'):''}
    ${['active','paused','agreed'].includes(d.status)?`<div class="guru-perspectives"><div><h4>You</h4><p>${safe(d.my_perspective||'Not shared yet')}</p></div><div><h4>Your partner</h4><p>${safe(d.partner_perspective||'Waiting for their perspective')}</p></div></div>`:''}
    ${d.status==='active'?`<p class="hint"><strong>Guru asks:</strong> ${safe(d.prompt||'What would you like each other to understand?')}</p><form data-shared-form="perspective"><label>Your perspective — shared with your partner</label><textarea name="text" maxlength="800" required placeholder="What happened, how you felt, and what you need">${safe(d.my_perspective)}</textarea><button class="secondary">Share perspective</button></form>
      ${d.both_responded?`<form data-shared-form="propose"><label>A next step to consider</label><textarea name="text" maxlength="800" required placeholder="Something you both feel comfortable trying">${safe(d.proposal)}</textarea><button class="secondary">Propose next step</button></form>`:''}${act('pause','Pause')}`:''}
    ${d.proposal?`<h4>Proposed next step</h4><p>${safe(d.proposal)}</p><p>${d.my_confirmed?'✓ You confirmed':'You have not confirmed'} · ${d.partner_confirmed?'✓ Partner confirmed':'Partner has not confirmed'}</p>${d.status==='active'&&!d.my_confirmed?act('confirm','I agree to this step'):''}<p class="hint">This does not change your relationship stage, payments or consent permissions.</p>`:''}
    ${d.status==='paused'?act('resume','Resume'):''}
    ${d.status!=='closed'?act('leave','Leave & remove shared content'):''}
    </article>`;
}

export function bindNavigator(root,ctx) {
  const {session,run,patch,data}=ctx;
  const update=(next)=>patch({...data,navigator:{...next,_drafts:{topic:data.navigator?._drafts?.topic}}});
  const form=root.querySelector('#guru-private-form');
  form?.addEventListener('input',()=>{const f=new FormData(form);data.navigator._drafts={topic:f.get('topic'),text:f.get('text')};});
  const privateAction=(body)=>run(async()=>update(await session.post('/api/v1/guru/private',body)));
  root.querySelector('#guru-private-form')?.addEventListener('submit',e=>{
    e.preventDefault();const f=new FormData(e.target);
    privateAction({action:'message',topic:f.get('topic'),text:f.get('text'),request_id:crypto.randomUUID()});
  });
  root.querySelectorAll('[data-private-action]').forEach(btn=>btn.addEventListener('click',()=>{
    if(window.confirm('Delete this private Guru data?')) privateAction({action:btn.dataset.privateAction});
  }));
  root.querySelector('#guru-ai')?.addEventListener('change',e=>privateAction({action:'ai_setting',enabled:e.target.checked}));
  root.querySelector('#guru-remember')?.addEventListener('change',e=>privateAction({action:'memory_setting',enabled:e.target.checked}));
  root.querySelectorAll('.guru-memory-form').forEach(form=>form.addEventListener('submit',e=>{
    e.preventDefault();privateAction({action:'save_memory',text:new FormData(form).get('text'),...(form.dataset.memoryId?{memory_id:form.dataset.memoryId}:{})});
  }));
  root.querySelectorAll('[data-delete-memory]').forEach(btn=>btn.addEventListener('click',()=>privateAction({action:'delete_memory',memory_id:btn.dataset.deleteMemory})));
  root.querySelector('#guru-refresh')?.addEventListener('click',()=>run(async()=>update(await session.get('/api/v1/guru/state'))));
  root.querySelector('#guru-invite')?.addEventListener('submit',e=>{
    e.preventDefault();const topic=new FormData(e.target).get('topic');
    run(async()=>update(await session.post('/api/v1/guru/discussions',{topic})));
  });
  root.querySelectorAll('[data-discussion]').forEach(article=>{
    const send=(action,text)=>{
      const body={action,revision:Number(article.dataset.revision),...(text!==undefined?{text}:{})};
      run(async()=>update(await session.post(`/api/v1/guru/discussions/${article.dataset.discussion}`,body)));
    };
    article.querySelectorAll('[data-shared-action]').forEach(btn=>btn.addEventListener('click',()=>{
      if(btn.dataset.sharedAction==='leave'&&!window.confirm('Leave and remove this conversation for both of you?'))return;
      send(btn.dataset.sharedAction);
    }));
    article.querySelectorAll('[data-shared-form]').forEach(form=>form.addEventListener('submit',e=>{
      e.preventDefault();send(form.dataset.sharedForm,new FormData(form).get('text'));
    }));
  });
}
