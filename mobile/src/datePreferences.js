// Client answer 3 (2026-11-27): date preferences (neighbourhood, diet, cuisine, budget)
// are optional at signup and required before accepting a match or planning a date.
// When the server refuses with 409 'date_preferences_required', main.js opens this
// sheet with the server's own message; saving it returns the member to what they were
// doing to try again. GET/PUT /api/v1/profile/date-preferences.
export const CODE = 'date_preferences_required';

export function isPrompt(error) { return error?.code === CODE; }

export function render(state, safe) {
  const values = state.values || {}, options = state.options || {}, missing = new Set(state.missing || []);
  const needed = (k) => (missing.has(k) ? ' · needed' : '');
  const ticks = (name, list, chosen, label = (x) => x, value = (x) => x) => list.map((x) =>
    `<label class="checkbox-row"><input type="checkbox" name="${name}" value="${safe(value(x))}" ${(chosen || []).includes(value(x)) ? 'checked' : ''}> ${safe(label(x))}</label>`).join('');
  return `<main class="container"><section class="card date-preferences" aria-labelledby="date-prefs-title">
    <h1 id="date-prefs-title">Your date preferences</h1>
    ${state._prompt ? `<p role="alert" class="notice">${safe(state._prompt)}</p>` : ''}
    <p class="hint">Optional at sign-up. Needed before you accept a match or plan a date, so a venue suits you both.</p>
    ${state._error ? `<p role="alert" class="warn">${safe(state._error)}</p>` : ''}
    <form id="date-prefs-form">
      ${(options.neighbourhoods || []).length ? `<fieldset><legend>Neighbourhood · up to three${needed('neighbourhoods')}</legend>
        ${ticks('neighbourhoods', options.neighbourhoods, values.neighbourhoods, (p) => p.name, (p) => p.id)}</fieldset>` : ''}
      <label>Diet${needed('diet')}<select name="diet" ${state.diet_locked ? 'disabled' : ''}><option value="">Choose…</option>
        ${(options.diet || []).map((d) => `<option value="${safe(d)}" ${values.diet === d ? 'selected' : ''}>${safe(d)}</option>`).join('')}</select></label>
      ${state.diet_locked ? '<p class="hint">Change your diet in Stats.</p>' : ''}
      <fieldset><legend>Cuisine${needed('cuisine')}</legend>${ticks('cuisine', options.cuisine || [], values.cuisine)}</fieldset>
      <fieldset><legend>Budget per person${needed('budget')}</legend>${ticks('budget', options.budget || [], Array.isArray(values.budget) ? values.budget : values.budget ? [values.budget] : [])}</fieldset>
      <button class="primary" type="submit">Save date preferences</button>
      <button class="secondary" type="button" id="date-prefs-close">Not now</button>
    </form>
  </section></main>`;
}

// The PUT body from the form (diet only when the member may set it here).
export function bodyFrom(form, state) {
  const data = new FormData(form);
  const body = {cuisine: data.getAll('cuisine'), budget: data.getAll('budget')};
  if ((state.options?.neighbourhoods || []).length) body.neighbourhoods = data.getAll('neighbourhoods');
  if (!state.diet_locked && data.get('diet')) body.diet = data.get('diet');
  return body;
}

export function stillNeeded(state) {
  return (state.missing || []).map((k) => state.labels?.[k] || k);
}
