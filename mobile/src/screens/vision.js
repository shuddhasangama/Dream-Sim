// Vision & Evolution (§2.6). `goals` are the sign-up-time preferences
// (already shown on the dashboard); `element_keys`/`entries`/`changes` are
// the separate Relationship-stage detail vocabulary (evolution_api.py's
// /profile/vision) — a different, additive-only layer on top of the same
// goals, never a replacement for them (mobile-journey-build-spec.md §2.6:
// "Vision is additive-only... add granular detail, never delete").
//
// A declared reversal must be disclosed to the partner or the server
// returns 409 disclosure_required (evolution_service.add_vision) — the
// checkbox below is `required` so there's no path through this UI that
// submits an undisclosed change, on top of the server's own guard.

export function label(key) { return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' '); }

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Vision</h1></section><section class="card"><p>Loading…</p></section>';
  const { goals = [], element_keys = [], entries = [], changes = [] } = data;
  const byKey = new Map(element_keys.map((k) => [k, entries.filter((e) => e.element_key === k)]));

  return `<section class="intro"><span class="eyebrow">VISION</span><h1>Where you're headed</h1></section>

    <section class="card"><h2>Your goals</h2>
    <div class="chips">${goals.map((g) => `<span>${safe(g.key)}${g.stance ? ' · ' + safe(Array.isArray(g.stance) ? g.stance.join(', ') : g.stance) : ''}</span>`).join('') || '<p class="hint">Nothing chosen yet.</p>'}</div></section>

    <section class="card"><h2>Add detail</h2>
    <p class="hint">Granular detail beneath a goal — always allowed, never deletes anything.</p>
    <form id="detail-form">
      <div class="field"><label for="detail-element">Element</label>
        <select id="detail-element" name="element_key">${element_keys.map((k) => `<option value="${safe(k)}">${safe(label(k))}</option>`).join('')}</select></div>
      <div class="field"><label for="detail-text">Detail</label><textarea id="detail-text" name="detail_text" maxlength="2000" required></textarea></div>
      <button class="primary" type="submit">Add</button>
    </form>
    ${element_keys.map((k) => {
      const chain = byKey.get(k) || [];
      if (!chain.length) return '';
      return `<div class="clause"><strong>${safe(label(k))}</strong>${chain.map((e) => `<p>${safe(e.detail_text)}</p>`).join('')}</div>`;
    }).join('')}</section>

    <section class="card"><h2>Declare a change</h2>
    <p class="hint">A material reversal — must be disclosed to your match; it cannot be declared silently.</p>
    <form id="change-form">
      <div class="field"><label for="change-element">Element</label>
        <select id="change-element" name="element_key">${element_keys.map((k) => `<option value="${safe(k)}">${safe(label(k))}</option>`).join('')}</select></div>
      <div class="field"><label for="change-from">From</label><input id="change-from" name="from_value" maxlength="500" required></div>
      <div class="field"><label for="change-to">To</label><input id="change-to" name="to_value" maxlength="500" required></div>
      <label class="checkbox-row"><input type="checkbox" name="disclosed_to_partner" required> I've disclosed this to my match</label>
      <button class="secondary" type="submit">Declare change</button>
    </form>
    ${changes.length ? `<h2>History</h2>${changes.map((c) => `<div class="clause">${safe(label(c.element_key))}: ${safe(c.from_value)} → ${safe(c.to_value)}</div>`).join('')}` : ''}</section>`;
}

export function bind(root, ctx) {
  const { session, run, patch } = ctx;

  root.querySelector('#detail-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      patch(await session.post('/api/v1/profile/vision/details', {
        request_id: crypto.randomUUID(), element_key: form.get('element_key'), detail_text: form.get('detail_text').trim(),
      }));
      e.target.reset();
    });
  });

  root.querySelector('#change-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      patch(await session.post('/api/v1/profile/vision/changes', {
        request_id: crypto.randomUUID(), element_key: form.get('element_key'),
        from_value: form.get('from_value').trim(), to_value: form.get('to_value').trim(),
        disclosed_to_partner: form.has('disclosed_to_partner'),
      }));
      e.target.reset();
    });
  });
}
