// Guru entry (§4 hard constraint 5: "Guru never nudges escalation — it
// reflects and structures; it does not suggest progressing, inviting home,
// or sharing contacts"). That guarantee is enforced server-side by
// guru.next_action() itself — the same read model the dashboard's own
// "NEXT FOR YOU" card already renders — so this screen adds no escalation
// logic of its own; it just gives that same content a dedicated home.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Guru</h1></section><section class="card"><p>Loading…</p></section>';
  const dest = data.destination;
  return `<section class="intro"><span class="eyebrow">GURU</span><h1>${safe(data.headline)}</h1></section>
    <section class="card guidance"><p>${safe(data.body)}</p>
    ${dest && dest.eligible && dest.request ? `<button id="guru-cta" class="primary" type="button">${safe(data.cta || 'Continue')} <span aria-hidden="true">→</span></button>` : ''}</section>`;
}

export function bind(root, ctx) {
  const { data, navigateTo } = ctx;
  root.querySelector('#guru-cta')?.addEventListener('click', () => navigateTo(data.destination.key));
}
