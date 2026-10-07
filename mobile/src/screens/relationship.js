// Relationship overview and shared agreement entry for later checkpoints.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Relationship</h1></section><section class="card"><p>Loading…</p></section>';
  const couple = data.couple;
  return `<section class="intro"><span class="eyebrow">Relationship</span><h1>Stage: ${safe(couple?.stage || 'relationship')}</h1>
    <p class="lede">Together since ${safe(couple?.start_date || 'this week')}. ROAD — your routine, obligations, availability and dates — is set once here and carries forward.</p></section>
    <section class="card guru-card"><div class="guru-avatar">G</div><div>Set up ROAD when you're ready. It's a one-time setup, not a weekly form — you can revisit it any time, but nothing here is forced.</div>
    <button id="open-road" class="primary" type="button" style="width:auto;padding:10px 16px;margin-top:12px;">Open ROAD <span aria-hidden="true">→</span></button></section>
    ${data.next_stage ? `<section class="card"><h2>Next stage</h2><p>When you both choose to, review the agreement for ${safe(data.next_stage)}.</p><button id="open-checkpoint" class="secondary">Review next-stage agreement</button></section>` : ''}`;
}

export function bind(root, ctx) {
  const { data, navigateTo } = ctx;
  root.querySelector('#open-checkpoint')?.addEventListener('click',()=>navigateTo('ceremony',{coupleId:data.couple.id,source:data.couple.stage,returnTo:'relationship'}));
  root.querySelector('#open-road')?.addEventListener('click', () => navigateTo('road', { coupleId: data.couple.id }));
}
