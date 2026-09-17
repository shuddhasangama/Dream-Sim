// Date plan (§2.4). Reached generically via journey/status's own "plan"
// surface — once a date exists, journey_api.py already routes it here, so
// no custom loader is needed, unlike ceremony.js.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Date plan</h1></section><section class="card"><p>Loading…</p></section>';
  const sel = data.my_selections || {};
  return `<section class="intro"><span class="eyebrow">DATE PLAN</span><h1>${safe(data.status === 'confirmed' ? 'Confirmed' : 'Pending signatures')}</h1></section>
    <section class="card">
      <div class="stat-row"><span>When</span><strong>${safe(data.datetime)}</strong></div>
      <div class="stat-row"><span>Meal</span><strong>${safe(data.meal)}</strong></div>
      ${data.venue ? `<div class="stat-row"><span>Venue</span><strong>${safe(data.venue)}</strong></div>` : ''}
      ${data.cuisine ? `<div class="stat-row"><span>Cuisine</span><strong>${safe(data.cuisine)}</strong></div>` : ''}
      ${data.budget_estimate ? `<div class="stat-row"><span>Budget</span><strong>${safe(data.budget_estimate)}</strong></div>` : ''}
      <div class="stat-row"><span>Bill split</span><strong>${safe(data.bill_split)}</strong></div>
    </section>
    <section class="card">
      <h2>Your selections</h2>
      <form id="selections-form">
        <div class="field"><label for="dietary">Anything about diet the host should know?</label><textarea id="dietary" name="dietary" maxlength="1000">${safe(sel.dietary || '')}</textarea></div>
        <div class="field"><label for="dress">Dress code note</label><textarea id="dress" name="dress" maxlength="1000">${safe(sel.dress || '')}</textarea></div>
        <button class="secondary" type="submit">Save</button>
      </form>
    </section>
    <section class="card guidance">
      <div class="stat-row"><span>You signed</span><strong>${data.my_signed ? 'Yes' : 'Not yet'}</strong></div>
      <div class="stat-row"><span>Your match signed</span><strong>${data.partner_signed ? 'Yes' : 'Not yet'}</strong></div>
      ${data.face_simulation_available ? `<p class="hint">Face verification runs as a beta simulation — never a live biometric check.</p>` : ''}
      ${!data.my_signed ? `<button id="to-ceremony" class="primary" type="button">Review &amp; sign <span aria-hidden="true">→</span></button>` : ''}
    </section>`;
}

export function bind(root, ctx) {
  const { session, run, patch, navigateTo } = ctx;
  const planId = encodeURIComponent(ctx.data.id);

  root.querySelector('#selections-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      patch(await session.put(`/api/v1/date-plans/${planId}/selections`, {
        dietary: form.get('dietary')?.trim() || null,
        dress: form.get('dress')?.trim() || null,
      }));
    });
  });

  root.querySelector('#to-ceremony')?.addEventListener('click', () => navigateTo('ceremony', { planId: ctx.data.id }));
}
