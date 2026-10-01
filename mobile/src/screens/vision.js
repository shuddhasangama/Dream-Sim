// Vision & Evolution (§2.6, round3-fixes-spec.md §7). `goals` are the real,
// current pillars (Intimacy / Travel together / Kids / Cohabitate) and their
// sub-selections; `pillar_options` is where every pillar's fixed sub-selection
// list comes from — never hardcoded here — and `detail_explanation` is the
// spec's own copy. All validation (Intimacy mandatory, two pillars minimum,
// Kids/Cohabitate need a sub-selection, Naturally needs Physical) lives on the
// server; this screen only offers choices and shows the server's own refusal.
//
// Add Detail (§7.2) is additive only: a pillar or sub-selection not already
// present. Declare a Change (§7.3) adds and/or removes sub-selections within
// one existing pillar, needs disclosure, and is only open while Reality Check
// is (`rc_open`) — when it is not, the reason is shown instead of a silently
// disabled form.

export function label(key) { return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' '); }

const stanceOf = (goal) => (Array.isArray(goal?.stance) ? goal.stance : goal?.stance ? [goal.stance] : []);

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Vision</h1></section><section class="card"><p>Loading…</p></section>';
  const { goals = [], element_keys = [], pillar_options = {}, detail_explanation = '', rc_open = false, changes = [] } = data;
  const byKey = new Map(goals.map((g) => [g.key, g]));
  const error = data._error ? `<p class="warn">${safe(data._error)}</p>` : '';
  const saved = data._saved ? '<p class="save-note">Saved.</p>' : '';

  // Additions: a pillar not selected yet, or a sub-selection not yet held.
  const addable = element_keys.flatMap((k) => {
    const opts = pillar_options[k] || [];
    if (!byKey.has(k)) return opts.length ? opts.map((o) => ({ pillar: k, sub: o })) : [{ pillar: k, sub: '' }];
    const held = stanceOf(byKey.get(k));
    return opts.filter((o) => !held.includes(o)).map((o) => ({ pillar: k, sub: o }));
  });
  const changeable = goals.filter((g) => (pillar_options[g.key] || []).length);

  return `<section class="intro"><span class="eyebrow">VISION</span><h1>Where you're headed</h1></section>

    <section class="card"><h2>Your Vision</h2>
    <div class="chips">${goals.map((g) => `<span>${safe(g.key)}${stanceOf(g).length ? ' · ' + safe(stanceOf(g).join(', ')) : ''}</span>`).join('') || '<p class="hint">Nothing chosen yet.</p>'}</div>
    <p class="hint" style="margin-top:10px;">${safe(detail_explanation)}</p></section>
    <section class="card"><h2>${safe(data.template_label || 'Choose your starting point')}</h2>
      <p>Templates set your pillars. Review the choices before saving. These preferences never imply consent to an activity.</p>
      <form id="vision-template-form">
      <label>Starting point<select name="template">${(data.presets || []).filter(p=>p.key!=='marriage').map(p=>`<option value="${safe(p.key)}" ${p.key===(data.template_key||'custom')?'selected':''}>${safe(p.label)} — ${safe(p.description)}</option>`).join('')}</select></label>
      <div id="template-preview"></div>
      <div id="custom-pillars" hidden>
      ${element_keys.map(k=>`<fieldset><legend><label><input type="checkbox" name="pillar" value="${safe(k)}" ${byKey.has(k)?'checked':''}> ${safe(k)}</label></legend>${(pillar_options[k]||[]).map(o=>`<label class="checkbox-row"><input type="checkbox" data-pillar-choice="${safe(k)}" value="${safe(o)}" ${stanceOf(byKey.get(k)||{}).includes(o)?'checked':''}> ${safe(o)}</label>`).join('')}</fieldset>`).join('')}
      <label>Future children<select name="kids_intent">${[['undecided','Undecided'],['open','Open to children'],['want','Want children'],['no','Do not want additional children']].map(([k,l])=>`<option value="${k}" ${data.kids_intent===k?'selected':''}>${l}</option>`).join('')}</select></label></div>
      <button class="primary" type="submit">Save Vision</button></form>
    </section>

    <details class="card vision-editor" data-vision-panel="add" ${ctx.onboarding || data._panels?.add ? 'open' : ''}><summary><strong>Add detail</strong></summary>
    <p class="hint">A pillar or choice you haven't set yet. This only ever adds — it never removes anything.</p>
    ${addable.length ? `<form id="detail-form">
      <div class="field"><label for="detail-choice">What to add</label>
        <select id="detail-choice" name="choice">${addable.map((a) => `<option value="${safe(a.pillar)}|${safe(a.sub)}">${safe(a.sub ? `${a.pillar} — ${a.sub}` : a.pillar)}</option>`).join('')}</select></div>
      <button class="primary" type="submit">Add</button>
    </form>` : '<p class="hint">Everything on offer is already part of your Vision.</p>'}</details>

    <details class="card vision-editor" data-vision-panel="change" ${ctx.onboarding || data._panels?.change ? 'open' : ''}><summary><strong>Declare a change</strong></summary>
    <p class="hint">A genuine change of mind within a pillar — adding or removing a choice. It must be disclosed to your partner and can't be made silently.</p>
    ${rc_open ? '' : '<p class="warn">Locked right now: changes can only be declared while Reality Check is open (Sunday 9pm to Monday 11am).</p>'}
    ${changeable.length ? `<form id="change-form">
      <div class="field"><label for="change-pillar">Pillar</label>
        <select id="change-pillar" name="pillar" ${rc_open ? '' : 'disabled'}>${changeable.map((g) => `<option value="${safe(g.key)}">${safe(g.key)}</option>`).join('')}</select></div>
      ${changeable.map((g) => `<fieldset class="change-options" data-pillar="${safe(g.key)}" ${g.key === changeable[0].key ? '' : 'hidden'}>
        ${(pillar_options[g.key] || []).map((o) => {
          const held = stanceOf(g).includes(o);
          return `<label class="checkbox-row"><input type="checkbox" name="${held ? 'remove' : 'add'}" value="${safe(o)}" ${rc_open ? '' : 'disabled'}> ${held ? 'Remove' : 'Add'} ${safe(o)}</label>`;
        }).join('')}</fieldset>`).join('')}
      <label class="checkbox-row"><input type="checkbox" name="disclosed_to_partner" required ${rc_open ? '' : 'disabled'}> I've disclosed this to my match</label>
      <button class="secondary" type="submit" ${rc_open ? '' : 'disabled'}>Declare change</button>
    </form>` : '<p class="hint">No pillar with choices to change yet.</p>'}
    </details>${error}${saved}
    ${changes.length ? `<section class="card"><h2>History</h2>${changes.map((c) => `<div class="clause">${safe(label(c.element_key))}: ${safe(c.from_value)} → ${safe(c.to_value)}</div>`).join('')}</section>` : ''}`;
}

async function reload(session) { return session.get('/api/v1/profile/vision'); }

export function bind(root, ctx) {
  const { session, run, data } = ctx;
  const patch = next=>ctx.patch({...next,_panels:data._panels});
  root.querySelectorAll('[data-vision-panel]').forEach(panel=>panel.addEventListener('toggle',()=>{
    data._panels={...data._panels,[panel.dataset.visionPanel]:panel.open};
  }));
  const templateForm=root.querySelector('#vision-template-form');
  const showTemplate=()=>{
    const item=(data.presets||[]).find(p=>p.key===templateForm.elements.template.value);
    root.querySelector('#custom-pillars').hidden=item?.key!=='custom';
    root.querySelector('#template-preview').textContent=item?.choices ? Object.entries(item.choices).map(([k,v])=>k+(v.length?': '+v.join(', '):'')).join(' · ') : 'Customise your pillars below.';
  };
  templateForm?.elements.template.addEventListener('change',showTemplate);
  if(templateForm) showTemplate();
  templateForm?.addEventListener('submit',e=>{e.preventDefault();run(async()=>{
    const form=new FormData(templateForm), pillars={};
    for(const k of form.getAll('pillar')) pillars[k]=[...templateForm.querySelectorAll('[data-pillar-choice]')].filter(el=>el.dataset.pillarChoice===k&&el.checked).map(el=>el.value);
    try { patch({...await session.put('/api/v1/profile/vision/template',{template:form.get('template'),pillars,kids_intent:form.get('kids_intent')}),_saved:true}); }
    catch(e){patch({...data,_error:e.message,_saved:false});}
  });});

  root.querySelector('#detail-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const [pillar, sub] = new FormData(e.target).get('choice').split('|');
      try {
        await session.post('/api/v1/profile/vision/details', { request_id: crypto.randomUUID(), pillar, ...(sub ? { sub_selection: sub } : {}) });
      } catch (err) {
        patch({ ...data, _saved: false, _error: err.message });
        return;
      }
      patch({ ...(await reload(session)), _saved: true });
    });
  });

  const pillarSelect = root.querySelector('#change-pillar');
  pillarSelect?.addEventListener('change', () => {
    root.querySelectorAll('.change-options').forEach((f) => { f.hidden = f.dataset.pillar !== pillarSelect.value; });
  });

  root.querySelector('#change-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const pillar = form.get('pillar');
      const scope = e.target.querySelector(`.change-options[data-pillar="${pillar}"]`);
      const pick = (name) => [...scope.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);
      try {
        await session.post('/api/v1/profile/vision/changes', {
          request_id: crypto.randomUUID(), pillar, add: pick('add'), remove: pick('remove'),
          disclosed_to_partner: form.has('disclosed_to_partner'),
        });
      } catch (err) {
        patch({ ...data, _saved: false, _error: err.message });
        return;
      }
      patch({ ...(await reload(session)), _saved: true });
    });
  });
}
