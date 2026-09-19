// Guru entry (§5, spec item 12), ported from templates/guru.html: the
// coral "G" avatar in a bordered panel is the established Guru voice
// component — used everywhere else in the app (dashboard, REACH's
// nationality/religion note, week's lock-in note).
//
// §4 hard constraint 5: "Guru never nudges escalation — it reflects and
// structures; it does not suggest progressing, inviting home, or sharing
// contacts." That guarantee is enforced server-side — guru.next_action()
// for the single answer, guru_dating.dating_context()/pre_date_briefing()
// for the sections below, all informational, none of them an action this
// screen invents on its own.
//
// round3-fixes-spec.md §6 added the rest of GET /api/v1/guidance's shape
// this screen was previously ignoring: `dating_context` (§6.1 date prep,
// §6.2 consent + playbook, Dating-stage only — null outside it) and
// `also_open` (§6.3's "anything I can help you with?", the same list
// guru.html's "Also open" tiles show on web).

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Guru</h1></section><section class="card"><p>Loading…</p></section>';
  const dest = data.destination;
  const dc = data.dating_context;
  const prep = dc?.date_prep;
  const also = data.also_open || [];

  return `<section class="intro"><span class="eyebrow">Guru</span><h1>What now?</h1>
    <p class="lede">One answer first. Everything else is one tap away, not spread across this screen.</p></section>
    <section class="card guru-card">
      <div class="guru-avatar">G</div>
      <div style="flex:1;">
        <div class="section-label" style="margin:0;">${safe(data.headline)}</div>
        <div style="margin-top:6px;">${safe(data.body)}</div>
        ${dest && dest.eligible && dest.request ? `<button id="guru-cta" class="primary" type="button" style="width:auto;padding:10px 16px;">${safe(data.cta || 'Continue')} <span aria-hidden="true">→</span></button>` : ''}
      </div>
    </section>

    ${dc ? `<section class="card guru-card">
      <div class="guru-avatar">G</div>
      <div style="flex:1;">
        <div class="section-label" style="margin:0;">How this works</div>
        <p style="margin-top:6px;">${safe(dc.consent)}</p>
        <ul class="hint" style="margin-top:8px;padding-left:18px;">${dc.playbook.map((p) => `<li>${safe(p)}</li>`).join('')}</ul>
      </div>
    </section>` : ''}

    ${prep ? `<section class="card">
      <div class="section-label" style="margin:0;">Before you meet</div>
      ${prep.partner_greeting ? `<p class="hint" style="margin-top:8px;">They've said how they'd like to be greeted: <strong>${safe(prep.partner_greeting)}</strong>.</p>` : ''}
      <div class="section-label" style="margin-top:14px;font-size:11px;">Courtesies</div>
      <ul style="margin-top:6px;padding-left:18px;">${prep.courtesies.map((c) => `<li>${safe(c)}</li>`).join('')}</ul>
      <div class="section-label" style="margin-top:14px;font-size:11px;">Safety</div>
      <ul style="margin-top:6px;padding-left:18px;">${prep.safety.map((c) => `<li>${safe(c)}</li>`).join('')}</ul>
      <div class="section-label" style="margin-top:14px;font-size:11px;">Boundaries</div>
      <ul style="margin-top:6px;padding-left:18px;">${prep.boundaries.map((c) => `<li>${safe(c)}</li>`).join('')}</ul>
      <p class="hint" style="margin-top:10px;">${safe(prep.note)}</p>
    </section>` : ''}

    ${also.length ? `<section class="card">
      <div class="section-label" style="margin:0;">Anything else I can help with?</div>
      <div class="guru-cards" style="margin-top:10px;">${also.map((c) => `<button class="guru-tile" type="button" data-key="${safe(c.destination?.key || '')}" ${c.destination?.eligible ? '' : 'disabled'}>
        <span class="guru-tile-code">${safe(c.code)}</span>
        <span class="guru-tile-body">
          <span class="guru-tile-title">${safe(c.title)}</span>
          <span class="guru-tile-sub">${safe(c.subtitle)}</span>
        </span>
      </button>`).join('')}</div>
    </section>` : ''}`;
}

export function bind(root, ctx) {
  const { data, navigateTo } = ctx;
  root.querySelector('#guru-cta')?.addEventListener('click', () => navigateTo(data.destination.key));
  root.querySelectorAll('.guru-tile[data-key]').forEach((btn) => {
    if (btn.dataset.key) btn.addEventListener('click', () => navigateTo(btn.dataset.key));
  });
}
