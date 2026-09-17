// Stats (§2.6, spec item 11), ported from templates/stats.html. Options
// and numeric ranges come straight from GET /api/v1/profile/stats's own
// options/ranges — never hardcoded. Field LABELS, UNITS and which fields
// are multi-select aren't in that JSON shape (onboarding.STAT_LABELS/
// STAT_UNITS/MULTI_VALUE_STATS are web-route-only additions) — mirrored
// here the same way nav.js mirrors disclosure.py's labels: presentational
// text keyed by a small, fixed set of field keys stats_edit.py already
// defines, never business logic of its own.

const STAT_LABELS = {
  age: 'Age', height_cm: 'Height', weight_kg: 'Weight', waist_in: 'Waist',
  education: 'Education', nationality: 'Nationality', profession: 'Profession',
  diet: 'Dietary preference', smoking: 'Smoking', drinking: 'Drinking',
  fitness_routine: 'Fitness routine', marital_history: 'Marital history',
  ethnicity: 'Ethnicity', religion: 'Religion', languages: 'Languages you speak',
  cuisine: 'Cuisine you enjoy', income_band: 'Salary band', budget: 'Restaurant budget',
};
const STAT_UNITS = { age: 'years', height_cm: 'cm', weight_kg: 'kg', waist_in: 'in' };
const MULTI_STATS = ['languages', 'cuisine', 'budget', 'ethnicity'];
const MULTI_CAPS = { ethnicity: 2 };

function label(key) { return STAT_LABELS[key] || key.replace(/_/g, ' '); }

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Your stats</h1></section><section class="card"><p>Loading…</p></section>';
  const { rows = [], options = {}, ranges = {}, changes = [] } = data;
  const open = rows.filter((r) => r.editable);
  const held = rows.filter((r) => !r.editable);
  const singleOpen = open.filter((r) => !MULTI_STATS.includes(r.key));
  const multiOpen = open.filter((r) => MULTI_STATS.includes(r.key));

  return `<section class="intro"><span class="eyebrow">Your file · Stats</span><h1>Your stats</h1></section>

    <form id="stats-form">
      <section class="card">
        <div class="section-label">Yours to change</div>
        ${!open.length ? '<div class="hint">Nothing is editable right now. These open again after the date.</div>' : ''}
        <div class="field-grid">${singleOpen.map((r) => `<label class="field-cell">
          <span class="field-label">${safe(label(r.key))}</span>
          ${options[r.key] ? `<select name="${safe(r.key)}"><option value="">Not set</option>${options[r.key].map((o) => `<option value="${safe(o)}" ${String(r.value) === o ? 'selected' : ''}>${safe(o)}</option>`).join('')}</select>`
            : `<input type="number" inputmode="numeric" name="${safe(r.key)}" value="${r.value ?? ''}" min="${ranges[r.key]?.[0] ?? ''}" max="${ranges[r.key]?.[1] ?? ''}" placeholder="${safe(STAT_UNITS[r.key] || '')}">`}
        </label>`).join('')}</div>

        ${multiOpen.map((r) => {
          const chosen = Array.isArray(r.value) ? r.value : (r.value ? [r.value] : []);
          const cap = MULTI_CAPS[r.key];
          return `<div class="multi-field">
            <div class="field-label">${safe(label(r.key))}${cap ? ` <span class="field-unit">pick up to ${cap}</span>` : ''}</div>
            <div class="chip-row" ${cap ? `data-cap="${cap}"` : ''}>${(options[r.key] || []).map((o) => `<label class="checkbox-row"><input type="checkbox" name="${safe(r.key)}" value="${safe(o)}" ${chosen.includes(o) ? 'checked' : ''}> ${safe(o)}</label>`).join('')}</div>
          </div>`;
        }).join('')}

        ${open.length ? '<button class="btn-save" type="submit">Save changes</button>' : ''}
      </section>
    </form>

    ${held.length ? `<form id="reverify-form"><section class="card">
      <div class="section-label">Verified — held</div>
      <div class="hint">These are vouched for, so they are not typed over. Tick anything that has genuinely changed and send it back to be re-checked.</div>
      <div class="field-grid">${held.map((r) => `<label class="field-cell held">
        <span class="field-label">${r.why === 'verified' ? `<input type="checkbox" name="field" value="${safe(r.key)}">` : ''}${safe(label(r.key))}</span>
        <span class="field-value">${r.value != null && r.value !== '' ? safe(r.value) : '—'}</span>
      </label>`).join('')}</div>
      ${held.some((r) => r.why === 'verified') ? '<button class="btn-save secondary" type="submit">Send ticked for re-checking</button>' : ''}
      <div class="micro" style="margin-top:8px;">${safe(held[0].reason || '')}</div>
    </section></form>` : ''}

    ${changes.length ? `<section class="card"><div class="section-label">What your partner has been shown</div>
      <div class="hint">Every change since you became exclusive. There is no undisclosed version of this.</div>
      <div class="stat-rows">${changes.map((c) => `<div class="stat-row"><span>${safe(label(c.field))}</span><span>${safe(c.from_value || '—')} → ${safe(c.to_value || '—')}</span></div>`).join('')}</div>
    </section>` : ''}`;
}

export function bind(root, ctx) {
  const { session, run, patch } = ctx;

  root.querySelector('#stats-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const fields = {};
      for (const [key, value] of form.entries()) {
        if (MULTI_STATS.includes(key)) { (fields[key] ??= []).push(value); }
        else fields[key] = value;
      }
      await session.patch('/api/v1/profile/stats', { fields });
      patch(await session.get('/api/v1/profile/stats'));
    });
  });

  root.querySelector('#reverify-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const fields = new FormData(e.target).getAll('field');
      if (!fields.length) return;
      await session.post('/api/v1/profile/stats/reverification', { fields });
      patch(await session.get('/api/v1/profile/stats'));
    });
  });
}
