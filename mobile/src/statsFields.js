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
  // round4-fixes-spec.md §5: children a person ALREADY has — not the Kids
  // pillar (which is about wanting them).
  has_children: 'Already has children', children_count: 'Number of children',
};
const STAT_UNITS = { age: 'years', height_cm: 'cm', weight_kg: 'kg', waist_in: 'in', children_count: 'children' };
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
  const multiOpen = open.filter((r) => MULTI_STATS.includes(r.key));
  // round4-fixes-spec.md §4: the BGV-verified fields (the server's own
  // `group`, not a list kept here) sit together under one "Verified"
  // treatment, apart from self-declared ones, and share ONE short
  // re-verification line instead of a warning under each field.
  const verified = open.filter((r) => r.group === 'verified' && !MULTI_STATS.includes(r.key));
  const declared = open.filter((r) => r.group !== 'verified' && !MULTI_STATS.includes(r.key));
  if (!open.length) return '<div class="hint">Nothing is editable right now. These open again after the date.</div>';
  const err = (key) => (data._fieldErrors?.[key] ? `<span class="warn field-error" role="alert" data-error-for="${safe(key)}">${safe(data._fieldErrors[key])}</span>` : '');
  const cell = (r) => `<label class="field-cell">
      <span class="field-label">${safe(label(r.key))}</span>
      ${options[r.key] ? `<select name="${safe(r.key)}"><option value="">Not set</option>${options[r.key].map((o) => `<option value="${safe(o)}" ${String(r.value) === o ? 'selected' : ''}>${safe(o)}</option>`).join('')}</select>`
        : `<input type="number" inputmode="numeric" name="${safe(r.key)}" value="${r.value ?? ''}" min="${ranges[r.key]?.[0] ?? ''}" max="${ranges[r.key]?.[1] ?? ''}" placeholder="${safe(STAT_UNITS[r.key] || '')}">`}
      ${err(r.key)}
    </label>`;
  const reverifyNote = verified.map((r) => r.warning).find(Boolean);
  return `<form id="${formId}" novalidate>
    ${verified.length ? `<fieldset class="stats-group is-verified" data-group="verified">
      <legend><span class="verified-mark" aria-hidden="true">✓</span> Verified</legend>
      ${reverifyNote ? `<p class="group-note">${safe(reverifyNote)}</p>` : ''}
      <div class="field-grid">${verified.map(cell).join('')}</div>
    </fieldset>` : ''}
    ${declared.length ? `<fieldset class="stats-group" data-group="declared">
      <legend>Self-declared</legend>
      <div class="field-grid">${declared.map(cell).join('')}</div>
    </fieldset>` : ''}

    ${multiOpen.map((r) => {
      const chosen = Array.isArray(r.value) ? r.value : (r.value ? [r.value] : []);
      const cap = MULTI_CAPS[r.key];
      return `<div class="multi-field">
        <div class="field-label">${safe(label(r.key))}${cap ? ` <span class="field-unit">pick up to ${cap}</span>` : ''}</div>
        <div class="chip-row" ${cap ? `data-cap="${cap}"` : ''}>${(options[r.key] || []).map((o) => `<label class="checkbox-row"><input type="checkbox" name="${safe(r.key)}" value="${safe(o)}" ${chosen.includes(o) ? 'checked' : ''}> ${safe(o)}</label>`).join('')}</div>
        ${err(r.key)}
      </div>`;
    }).join('')}
    <button class="btn-save" type="submit">Save changes</button>
  </form>`;
}

// Read-only Stats display: verified fields together under one shared
// "Verified" treatment, self-declared ones apart. `rows` is
// GET /api/v1/profile/stats's rows (each carries the server's own `group`);
// `order` keeps the dashboard's existing field order/labels/units. Fields
// with no value are omitted.
export function groupedStatRows(rows, order, safe) {
  const byKey = new Map((rows || []).map((r) => [r.key, r]));
  const shown = order.filter(([k]) => byKey.get(k)?.value != null && byKey.get(k).value !== '');
  const line = ([k, name, unit]) => {
    const v = byKey.get(k).value;
    return `<div class="stat-row"><span>${safe(name)}</span><span>${safe(Array.isArray(v) ? v.join(', ') : v)}${unit}</span></div>`;
  };
  const verified = shown.filter(([k]) => byKey.get(k).group === 'verified');
  const declared = shown.filter(([k]) => byKey.get(k).group !== 'verified');
  return `${verified.length ? `<div class="stats-group is-verified" data-group="verified"><div class="group-title"><span class="verified-mark" aria-hidden="true">✓</span> Verified</div><div class="stat-rows">${verified.map(line).join('')}</div></div>` : ''}
    ${declared.length ? `<div class="stats-group" data-group="declared"><div class="group-title">Self-declared</div><div class="stat-rows">${declared.map(line).join('')}</div></div>` : ''}`;
}

// FormData → {field: value|values[]} for editableFieldsForm's own inputs.
function readForm(form) {
  const fields = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (MULTI_STATS.includes(key)) { (fields[key] ??= []).push(value); }
    else fields[key] = value;
  }
  return fields;
}

// round4-fixes-spec.md §1: send ONLY what the person changed, correctly
// typed. The old code PATCHed every input — untouched Age included — and
// FormData hands numbers back as strings ("38"), which the API's strict
// whole-number check refuses. That blocked every save, whatever was edited.
// Returns {fields, errors}: `fields` holds only changed values (numeric
// stats as real integers, multi-selects as arrays, cleared → null), and
// `errors` maps a field key to an inline message when an edited value
// can't be sent as-is. Untouched fields are never validated at all.
export function changedFields(form, statsData) {
  const submitted = readForm(form);
  const { rows = [], ranges = {} } = statsData;
  const fields = {}, errors = {};
  for (const r of rows.filter((x) => x.editable)) {
    const multi = MULTI_STATS.includes(r.key);
    if (!(r.key in submitted) && !multi) continue;        // input not rendered
    let value = multi ? (submitted[r.key] || []) : submitted[r.key];
    if (multi) { if (!value.length) value = null; }
    else if (typeof value === 'string') value = value.trim() === '' ? null : value.trim();
    if (value !== null && !multi && ranges[r.key]) {
      const n = Number(value);
      const [lo, hi] = ranges[r.key];
      if (!Number.isFinite(n) || !Number.isInteger(n)) { errors[r.key] = `${label(r.key)} must be a whole number.`; continue; }
      if (n < lo || n > hi) { errors[r.key] = `${label(r.key)} must be between ${lo} and ${hi}.`; continue; }
      value = n;
    }
    if (multi && MULTI_CAPS[r.key] && value && value.length > MULTI_CAPS[r.key]) {
      errors[r.key] = `${label(r.key)}: pick at most ${MULTI_CAPS[r.key]}.`; continue;
    }
    // Compare with what the SERVER last confirmed (`orig`, kept by
    // withSubmittedValues), not with a value we re-rendered after a failed
    // save — otherwise a rejected entry looks "unchanged" on the retry and
    // is silently never sent.
    if (fieldsEqual(value, 'orig' in r ? r.orig : r.value)) continue;   // untouched
    fields[r.key] = value;
  }
  return { fields, errors: Object.keys(errors).length ? errors : null, entered: submitted };
}

// A server refusal names its field(s) in prose ("age has to be between…");
// attach each part to the matching field so it shows next to that input.
// Anything that matches no field stays a general message.
export function fieldErrorsFromServer(message, statsData) {
  const keys = (statsData.rows || []).filter((r) => r.editable).map((r) => r.key);
  const byField = {}, rest = [];
  for (const part of String(message || '').split('; ')) {
    const low = part.toLowerCase();
    const key = keys.find((k) => low.includes(k) || low.includes(k.replace(/_/g, ' ')) || low.includes(label(k).toLowerCase()));
    if (key) byField[key] = part; else rest.push(part);
  }
  return { byField: Object.keys(byField).length ? byField : null, general: rest.join('; ') || null };
}

// Overlay just-submitted field values onto a stats payload's rows, so a
// failed save can re-render with what the person actually picked instead
// of reverting to the last-confirmed server values (the same "preserve
// the user's selections on failure" requirement chemistry.js's PUT/GET
// pair already applies).
export function withSubmittedValues(statsData, fields) {
  return { ...statsData, rows: (statsData.rows || []).map((r) => (r.key in fields ? { ...r, orig: 'orig' in r ? r.orig : r.value, value: fields[r.key] } : r)) };
}

// Shallow, order-independent value equality — good enough for stats
// values, which are strings, numbers or flat arrays of strings.
export function fieldsEqual(a, b) {
  const blank = (v) => v == null || v === '';
  const av = Array.isArray(a) ? a : (blank(a) ? [] : [a]);
  const bv = Array.isArray(b) ? b : (blank(b) ? [] : [b]);
  if (av.length !== bv.length) return false;
  const as = [...av].map(String).sort(), bs = [...bv].map(String).sort();
  return as.every((v, i) => v === bs[i]);
}
