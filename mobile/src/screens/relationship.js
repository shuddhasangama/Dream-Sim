// Relationship entry (road-fixes-clock-spec.md §1). journey/status points
// the 'relationship'/'journey' surfaces at the full couple-summary
// endpoint (/api/v1/couples/{cid}) — playbook, differences, checkpoints,
// exits. Rendering all of that is its own build; this screen reads only
// what it needs (the couple's own id/stage) and hands off to road.js for
// the one slice this task actually asks for. Reached generically via
// journey.surfaces, same as any other surface — no custom load() needed
// since the server already gives a real GET path for it.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Relationship</h1></section><section class="card"><p>Loading…</p></section>';
  const couple = data.couple;
  return `<section class="intro"><span class="eyebrow">Relationship</span><h1>Stage: ${safe(couple?.stage || 'relationship')}</h1>
    <p class="lede">Together since ${safe(couple?.start_date || 'this week')}. ROAD — your routine, obligations, availability and dates — is set once here and carries forward.</p></section>
    <section class="card guru-card"><div class="guru-avatar">G</div><div>Set up ROAD when you're ready. It's a one-time setup, not a weekly form — you can revisit it any time, but nothing here is forced.</div>
    <button id="open-road" class="primary" type="button" style="width:auto;padding:10px 16px;margin-top:12px;">Open ROAD <span aria-hidden="true">→</span></button></section>`;
}

export function bind(root, ctx) {
  const { data, navigateTo } = ctx;
  root.querySelector('#open-road')?.addEventListener('click', () => navigateTo('road', { coupleId: data.couple.id }));
}
