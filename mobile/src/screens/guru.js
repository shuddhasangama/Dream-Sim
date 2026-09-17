// Guru entry (§5, spec item 12), ported from templates/guru.html: the
// coral "G" avatar in a bordered panel is the established Guru voice
// component — used everywhere else in the app (dashboard, REACH's
// nationality/religion note, week's lock-in note) and, until now, missing
// from Guru's own screen.
//
// §4 hard constraint 5: "Guru never nudges escalation — it reflects and
// structures; it does not suggest progressing, inviting home, or sharing
// contacts." That guarantee is enforced server-side by guru.next_action()
// itself — the same read model the dashboard's own "NEXT FOR YOU" card
// already renders — so this screen adds no escalation logic of its own;
// it just gives that same content its established voice and a dedicated
// home. (guru.html's "Also open" tile grid and its `cards`/`more` data
// aren't part of GET /api/v1/guidance's shape — that's a web-route-only
// addition — so this stays the single next action, as the web page's own
// lede already frames it: "One answer. Everything else is one link away.")

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Guru</h1></section><section class="card"><p>Loading…</p></section>';
  const dest = data.destination;
  return `<section class="intro"><span class="eyebrow">Guru</span><h1>What now?</h1>
    <p class="lede">One answer. Everything else is one link away, not spread across this screen.</p></section>
    <section class="card guru-card">
      <div class="guru-avatar">G</div>
      <div style="flex:1;">
        <div class="section-label" style="margin:0;">${safe(data.headline)}</div>
        <div style="margin-top:6px;">${safe(data.body)}</div>
        ${dest && dest.eligible && dest.request ? `<button id="guru-cta" class="primary" type="button" style="width:auto;padding:10px 16px;">${safe(data.cta || 'Continue')} <span aria-hidden="true">→</span></button>` : ''}
      </div>
    </section>`;
}

export function bind(root, ctx) {
  const { data, navigateTo } = ctx;
  root.querySelector('#guru-cta')?.addEventListener('click', () => navigateTo(data.destination.key));
}
