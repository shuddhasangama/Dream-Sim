// Stats field metadata + the "yours to change" editor, shared by Dashboard's
// inline editor and REACH's inline editor (round3-fixes-spec.md §2/§3) —
// there is no standalone Stats screen any more, so this is the one place
// the field list/labels/multi-select/warning handling live, rather than
// two copies drifting apart. Options and numeric ranges come from
// GET /api/v1/profile/stats's own options/ranges — never hardcoded here.
// LABELS, UNITS and which fields are multi-select aren't in that JSON shape
// (onboarding.STAT_LABELS/STAT_UNITS/MULTI_VALUE_STATS are web-route-only
// additions) — mirrored here the same way nav.js mirrors disclosure.py's
// labels: presentational text keyed by a small, fixed set of field keys
// stats_edit.py already defines, never business logic of its own.

export const STAT_LABELS = {
  age: 'Age', height_cm: 'Height', weight_kg: 'Weight', waist_in: 'Waist',
  education: 'Education', nationality: 'Nationality', profession: 'Profession',
  diet: 'Dietary preference', smoking: 'Smoking', drinking: 'Drinking',
  fitness_routine: 'Fitness routine', marital_history: 'Marital history',
  ethnicity: 'Ethnicity', religion: 'Religion', languages: 'Languages you speak',
  cuisine: 'Cuisine you enjoy', income_band: 'Salary band', budget: 'Restaurant budget',
};
const STAT_UNITS = { age: 'years', height_cm: 'cm', weight_kg: 'kg', waist_in: 'in' };
export const MULTI_STATS = ['languages', 'cuisine', 'budget', 'ethnicity'];
const MULTI_CAPS = { ethnicity: 2 };

export function label(key) { return STAT_LABELS[key] || key.replace(/_/g, ' '); }

// The "yours to change" editor alone — reused by both entry points, which
// only ever need the open fields, never the held/verified section.
// round3-fixes-spec.md §3: a field can now be editable AND carry a
// `warning` (a previously-verified field — editing it re-opens
// verification) — shown right under the input, before the person saves.
export function editableFieldsForm(data, safe, formId) {
  const { rows = [], options = {}, ranges = {} } = data;
  const open = rows.filter((r) => r.editable);
  const singleOpen = open.filter((r) => !MULTI_STATS.includes(r.key));
  const multiOpen = open.filter((r) => MULTI_STATS.includes(r.key));
  if (!open.length) return '<div class="hint">Nothing is editable right now. These open again after the date.</div>';
  return `<form id="${formId}">
    <div class="field-grid">${singleOpen.map((r) => `<label class="field-cell">
      <span class="field-label">${safe(label(r.key))}</span>
      ${options[r.key] ? `<select name="${safe(r.key)}"><option value="">Not set</option>${options[r.key].map((o) => `<option value="${safe(o)}" ${String(r.value) === o ? 'selected' : ''}>${safe(o)}</option>`).join('')}</select>`
        : `<input type="number" inputmode="numeric" name="${safe(r.key)}" value="${r.value ?? ''}" min="${ranges[r.key]?.[0] ?? ''}" max="${ranges[r.key]?.[1] ?? ''}" placeholder="${safe(STAT_UNITS[r.key] || '')}">`}
      ${r.warning ? `<span class="warn">${safe(r.warning)}</span>` : ''}
    </label>`).join('')}</div>

    ${multiOpen.map((r) => {
      const chosen = Array.isArray(r.value) ? r.value : (r.value ? [r.value] : []);
      const cap = MULTI_CAPS[r.key];
      return `<div class="multi-field">
        <div class="field-label">${safe(label(r.key))}${cap ? ` <span class="field-unit">pick up to ${cap}</span>` : ''}</div>
        <div class="chip-row" ${cap ? `data-cap="${cap}"` : ''}>${(options[r.key] || []).map((o) => `<label class="checkbox-row"><input type="checkbox" name="${safe(r.key)}" value="${safe(o)}" ${chosen.includes(o) ? 'checked' : ''}> ${safe(o)}</label>`).join('')}</div>
      </div>`;
    }).join('')}
    <button class="btn-save" type="submit">Save changes</button>
  </form>`;
}

// FormData → {field: value|values[]} for editableFieldsForm's own inputs.
export function collectFields(form) {
  const fields = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (MULTI_STATS.includes(key)) { (fields[key] ??= []).push(value); }
    else fields[key] = value;
  }
  return fields;
}

// Overlay just-submitted field values onto a stats payload's rows, so a
// failed save can re-render with what the person actually picked instead
// of reverting to the last-confirmed server values (the same "preserve
// the user's selections on failure" requirement chemistry.js's PUT/GET
// pair already applies).
export function withSubmittedValues(statsData, fields) {
  return { ...statsData, rows: (statsData.rows || []).map((r) => (r.key in fields ? { ...r, value: fields[r.key] } : r)) };
}

// Shallow, order-independent value equality — good enough for stats
// values, which are strings, numbers or flat arrays of strings.
export function fieldsEqual(a, b) {
  const av = Array.isArray(a) ? a : (a == null ? [] : [a]);
  const bv = Array.isArray(b) ? b : (b == null ? [] : [b]);
  if (av.length !== bv.length) return false;
  const as = [...av].map(String).sort(), bs = [...bv].map(String).sort();
  return as.every((v, i) => v === bs[i]);
}
