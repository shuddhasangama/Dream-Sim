// REACH — design_handoff_app_ui_pulse/README.md ("Pulse", option 1a):
// the same GET /api/v1/reach shape and the same set of mutations
// (ignore/set-range/show-all) reach.js has always used, now presented as
// a hero ring plus tap-to-loosen filter chips instead of one accordion
// row per filter. Every rule from the older row-based screen still
// applies structurally, not just by care:
//   - nationality/religion never appear as a "widen this" suggestion —
//     `deltas` (the auto-suggested widen list) is never rendered at all;
//     they only ever show up in `filters`, the person's own deliberate
//     choice.
//   - every mutation (widen/set-range/ignore/show-all) returns the FULL
//     fresh state already (the server's own _reach_state()), so a
//     successful call patches ctx directly instead of a second round-trip.
//   - a chip TAP toggles Any/Set — the exact behaviour the old Any-switch
//     checkbox had (matching.set_ignored() keeps the saved value either
//     way, "Nothing was deleted"). A chip's small "…" (sliders and the
//     Kids-style paired choice only — the two kinds that ever had a real
//     picker) opens a bottom sheet with that SAME picker markup, just
//     moved off the main screen per the spec's own instruction.
import { editableFieldsForm, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } from '../statsFields.js';

// Position of a value along a min..max track, as a percentage clamped to
// the track (round4-fixes-spec.md §3: 38 on the 21–80 age track is 28.8%).
export function trackPct(min, max, value) {
  const span = max - min;
  if (!(span > 0)) return 0;
  return Math.min(100, Math.max(0, ((value - min) / span) * 100));
}

// A conic-gradient string for the hero ring — same helper contract as
// home.js's ringGradient (0–100 in, a CSS background out), duplicated
// rather than imported so reach.js and home.js stay free of a mutual
// import for one three-line function.
export function reachRingGradient(mutual, fit, color, track) {
  const pct = fit > 0 ? (mutual / fit) * 100 : 0;
  const clamped = Math.min(100, Math.max(0, pct));
  const deg = mutual > 0 ? Math.max(6, (clamped / 100) * 360) : 0;
  return `conic-gradient(${color} 0deg ${deg}deg, ${track} ${deg}deg 360deg)`;
}

// round3-fixes-spec.md §4.2: two answers to one question are one merged
// control (matching.py's _OPPOSITES/`opposite` field) — a chip per
// filter, not per row of the API's own list. Sliders are their own group;
// `sensitive` (nationality/religion) chips carry no visible "yours" tag in
// Pulse's clean chip design, only an aria-label, matching the spec's plain
// chip look while keeping the information available to assistive tech.
function groupChoices(choices) {
  const byName = new Map(choices.map((f) => [f.name, f]));
  const seen = new Set();
  const groups = [];
  for (const f of choices) {
    if (seen.has(f.name)) continue;
    const opp = f.opposite ? byName.get(f.opposite) : null;
    seen.add(f.name);
    if (opp) { seen.add(opp.name); groups.push({ kind: 'paired', options: [f, opp] }); }
    else groups.push({ kind: 'single', filter: f });
  }
  return groups;
}

const PAIR_GROUP_LABELS = { wants_kids: 'Kids', no_kids_wanted: 'Kids', no_existing_children: 'Kids', has_existing_children: 'Kids' };

// One "unit" per chip: a slider, a single ignore-only choice, or a paired
// group — whatever kind, a chip only ever needs {chipKey, label, active,
// valueText, hasSheet}. `hasSheet` is true only for the two kinds that
// ever had a real picker beyond Any/Set (round3-fixes-spec.md §4.1's
// slider, §4.2's paired 3-way choice) — nothing is lost by NOT giving the
// rest a sheet, since Any/Set (the chip tap itself) is all they ever had.
function sliderUnit(s) {
  const [lo, hi] = s.current || [s.min, s.max];
  return { kind: 'slider', chipKey: s.key, label: s.label, active: !s.ignored,
    valueText: s.ignored ? 'Any' : `${lo}–${hi} ${s.unit}`, hasSheet: true, raw: s };
}
function singleUnit(f) {
  return { kind: 'single', chipKey: f.name, label: f.label, active: !f.ignored,
    valueText: f.ignored ? 'Any' : f.on_label, hasSheet: false, raw: f, sensitive: f.sensitive };
}
function pairedUnit(a, b) {
  const selected = !a.ignored ? a : (!b.ignored ? b : null);
  return { kind: 'paired', chipKey: `${a.name}|${b.name}`, label: PAIR_GROUP_LABELS[a.name] || a.label,
    active: !!selected, valueText: selected ? selected.on_label : 'Any', hasSheet: true, raw: [a, b] };
}

function chipUnits(data) {
  const { sliders = [], filters = [] } = data;
  const choiceGroups = groupChoices(filters.filter((f) => f.control === 'choice'));
  return [
    ...sliders.map(sliderUnit),
    ...choiceGroups.map((g) => (g.kind === 'paired' ? pairedUnit(...g.options) : singleUnit(g.filter))),
  ];
}

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Reach</h1></section><section class="card"><p>Loading…</p></section>';
  const { counts, ignored_count = 0, all_ignored } = data;
  const mutual = counts?.mutual_open ?? 0;
  const fit = counts?.fits_user_filters ?? 0;
  const units = chipUnits(data);

  return `<section class="intro"><span class="p-eyebrow">REACH · THIS WEEK</span></section>
    <div class="p-reach-hero">
      <div class="p-reach-ring" style="background:${reachRingGradient(mutual, fit, 'var(--p-success)', 'var(--p-track)')}">
        <div class="p-reach-ring-inner"><div><div class="p-reach-num">${safe(mutual)}</div><div class="p-reach-sub">open to you</div></div></div>
      </div>
      <div>
        <div class="p-reach-fit">of ${safe(fit)} who fit</div>
        <div class="p-reach-verified">${data.counting_unverified ? 'Counting everyone, verified or not' : 'Verified only'}</div>
      </div>
    </div>
    ${counts?.no_realistic_matches ? '<p class="warn">No realistic matches yet at your current filters.</p>' : ''}

    <div class="p-reach-hint"><span>Tap a filter to loosen it</span>
      <button type="button" class="p-text-link" id="show-all" data-ignore="${all_ignored ? 'false' : 'true'}">${all_ignored ? 'Put them back' : 'Any for everything'}</button>
    </div>
    ${ignored_count ? `<p class="hint">${safe(ignored_count)} set to Any. Nothing was deleted — tap one back and it returns as you left it.</p>` : ''}

    <div class="p-chip-row">${units.map((u) => chip(u, safe)).join('')}</div>

    <div class="p-card" style="margin-top:20px;">
      <div class="p-detail-title" style="font-size:15px;">Missing a filter you expected?</div>
      <div class="hint">A filter only appears once you've told us the matching stat — add it here without leaving REACH.</div>
      ${(data.locked_levers || []).length ? `<ul class="locked-levers">${data.locked_levers.map((l) => `<li>${safe(l.label)} <span class="hint">— add ${safe(l.needs)} to filter on it</span></li>`).join('')}</ul>` : ''}
      ${data._stats ? `${editableFieldsForm(data._stats, safe, 'inline-stats-form')}
        <button id="cancel-stats-edit" class="secondary" type="button" style="margin-top:8px;">Cancel</button>
        ${data._stats._saved ? '<p class="save-note">Saved.</p>' : ''}
        ${data._stats._error ? `<p class="warn">${safe(data._stats._error)}</p>` : ''}`
        : '<button id="edit-stats-toggle" class="p-outline-cta" type="button">Edit your stats</button>'}
    </div>

    ${sheetKey ? renderSheet(sheetKey, units, safe) : ''}

    <section class="card guru-card" style="margin-top:20px;"><div class="guru-avatar">G</div><div>Nationality and religion are yours to explore — I'll never suggest widening them.</div></section>`;
}

function chip(u, safe) {
  return `<div class="filter-chip ${u.active ? 'is-active' : ''}" data-chip="${safe(u.chipKey)}">
    <button type="button" class="chip-tap" data-toggle="${safe(u.chipKey)}" aria-label="${safe(u.label)}${u.sensitive ? ' (yours — never suggested)' : ''}, ${u.active ? safe(u.valueText) : 'Any'}">
      <span class="chip-label">${safe(u.label)}</span><span class="chip-value">${safe(u.valueText)}</span>
    </button>
    ${u.hasSheet ? `<button type="button" class="chip-more" data-open-sheet="${safe(u.chipKey)}" aria-label="Adjust ${safe(u.label)}">⋯</button>` : ''}
  </div>`;
}

// Which chip's sheet is open — module-level, like the old `moreFiltersOpen`
// (every mutation re-renders the whole app; this is purely a client-side
// selection, never server state).
let sheetKey = null;

function renderSheet(key, units, safe) {
  const unit = units.find((u) => u.chipKey === key);
  if (!unit) return '';
  const body = unit.kind === 'slider' ? sliderSheetBody(unit.raw) : pairedSheetBody(unit.raw, safe);
  return `<div class="p-chip-sheet-backdrop" data-close-sheet></div>
    <div class="p-chip-sheet" role="dialog" aria-label="Adjust ${safe(unit.label)}">
      <div class="p-sheet-handle" aria-hidden="true"></div>
      <div class="p-detail-title" style="margin-bottom:10px;">${safe(unit.label)}</div>
      ${body}
      <button type="button" class="secondary" data-close-sheet style="margin-top:14px;">Done</button>
    </div>`;
}

function sliderSheetBody(s) {
  const [lo, hi] = s.current || [s.min, s.max];
  return `<div class="filter${s.ignored ? ' is-any' : ''}" data-lever="${s.key}" data-min="${s.min}" data-max="${s.max}" data-step="${s.step}">
    <div class="filter-head">
      <span class="filter-readout"><span class="sv-min">${lo}</span>–<span class="sv-max">${hi}</span> ${s.unit}</span>
      <label class="any-switch"><input type="checkbox" class="filter-any" data-filter="${s.key}" ${s.ignored ? 'checked' : ''}><span>Any</span></label>
    </div>
    <div class="slider-track-wrap">
      <div class="slider-rail">
      <div class="slider-track"></div>
      ${s.suggested ? '<div class="slider-suggested"></div>' : ''}
      <div class="slider-selected"></div>
      ${s.self_value != null ? `<div class="slider-self" title="You: ${s.self_value} ${s.unit}"></div>` : ''}
      </div>
      <input type="range" class="range-min" aria-label="Minimum ${s.label}" min="${s.min}" max="${s.max}" step="${s.step}" value="${lo}">
      <input type="range" class="range-max" aria-label="Maximum ${s.label}" min="${s.min}" max="${s.max}" step="${s.step}" value="${hi}">
    </div>
    <div class="slider-scale" aria-label="${s.label} scale ${s.min} to ${s.max}"><span class="scale-min">${s.min}</span><span class="scale-max">${s.max}</span></div>
    <div class="filter-foot">
      <span>${s.self_value != null ? `You: ${s.self_value} ${s.unit}` : ''}${s.suggested ? ` · suggested ${s.suggested[0]}–${s.suggested[1]}` : ''}</span>
      <span class="filter-delta">${s.ignored ? (s.delta_if_ignored > 0 ? `−${s.delta_if_ignored} if you set a range` : '') : (s.delta_if_ignored > 0 ? `+${s.delta_if_ignored} on Any` : '')}</span>
    </div>
  </div>`;
}

// round3-fixes-spec.md §4.2's merged control — the same three-way radio
// (or, for the "existing children" pair, two independent checkboxes) as
// the old accordion row, just living in the sheet now.
function pairedSheetBody([a, b], safe) {
  const selected = !a.ignored ? a.name : (!b.ignored ? b.name : '');
  if (a.name === 'no_existing_children' || a.name === 'has_existing_children') {
    const choice = (f) => `<label class="paired-choice-option"><input type="checkbox" data-children-filter="${safe(f.name)}" value="${safe(f.name)}" ${!f.ignored ? 'checked' : ''}><span>${safe(f.on_label)}</span></label>`;
    return `<p class="muted">Children they already have. Future parenting preferences belong in Vision.</p>
      <div class="paired-choice-options" data-paired="${safe(a.name)}|${safe(b.name)}">${choice(b)}${choice(a)}</div>
      <p class="muted">Leave both unselected to include everyone.</p>`;
  }
  const groupName = `paired-${a.name}-${b.name}`;
  const option = (name, optLabel) => `<label class="paired-choice-option"><input type="radio" name="${safe(groupName)}" value="${safe(name)}" ${selected === name ? 'checked' : ''}><span>${safe(optLabel)}</span></label>`;
  return `<div class="paired-choice-options" data-paired="${safe(a.name)}|${safe(b.name)}">
    ${option(a.name, a.on_label)}${option(b.name, b.on_label)}${option('', 'Any')}
  </div>`;
}

export function bind(root, ctx) {
  const { session, run, patch, data } = ctx;
  const units = chipUnits(data);
  const unitByKey = new Map(units.map((u) => [u.chipKey, u]));

  root.querySelectorAll('[data-toggle]').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    const unit = unitByKey.get(btn.dataset.toggle);
    if (!unit) return;
    if (unit.kind === 'paired') {
      const [a, b] = unit.raw;
      if (unit.active) { patch(await session.post('/api/v1/reach/ignore', { filter: unit.raw.find((f) => !f.ignored).name, ignore: true })); }
      else { patch(await session.post('/api/v1/reach/ignore', { filter: a.name, ignore: false })); }
      return;
    }
    patch(await session.post('/api/v1/reach/ignore', { filter: unit.chipKey, ignore: unit.active }));
  })));

  root.querySelectorAll('[data-open-sheet]').forEach((btn) => btn.addEventListener('click', () => run(async () => { sheetKey = btn.dataset.openSheet; })));
  root.querySelectorAll('[data-close-sheet]').forEach((el) => el.addEventListener('click', () => run(async () => { sheetKey = null; })));

  // Inside the sheet: the same ignore/paired/slider wiring the old
  // accordion rows used, just scoped to whichever sheet is open.
  root.querySelectorAll('.p-chip-sheet .filter-any').forEach((box) => box.addEventListener('change', () => run(async () => {
    patch(await session.post('/api/v1/reach/ignore', { filter: box.dataset.filter, ignore: box.checked }));
  })));
  root.querySelectorAll('.p-chip-sheet [data-children-filter]').forEach((box) => box.addEventListener('change', () => run(async () => {
    patch(await session.post('/api/v1/reach/ignore', { filter: box.dataset.childrenFilter, ignore: !box.checked }));
  })));
  root.querySelectorAll('.p-chip-sheet [data-paired] input[type="radio"]').forEach((radio) => radio.addEventListener('change', () => run(async () => {
    const [nameA, nameB] = radio.closest('[data-paired]').dataset.paired.split('|');
    if (radio.value) patch(await session.post('/api/v1/reach/ignore', { filter: radio.value, ignore: false }));
    else {
      const held = (data.filters || []).find((f) => (f.name === nameA || f.name === nameB) && !f.ignored);
      patch(held ? await session.post('/api/v1/reach/ignore', { filter: held.name, ignore: true }) : data);
    }
  })));

  root.querySelector('#show-all')?.addEventListener('click', (e) => run(async () => {
    patch(await session.post('/api/v1/reach/show-all', { ignore: e.target.dataset.ignore === 'true' }));
  }));

  root.querySelector('#edit-stats-toggle')?.addEventListener('click', () => run(async () => {
    patch({ ...data, _stats: await session.get('/api/v1/profile/stats') });
  }));
  root.querySelector('#cancel-stats-edit')?.addEventListener('click', () => run(async () => patch({ ...data, _stats: null })));
  root.querySelector('#inline-stats-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const { fields, errors, entered } = changedFields(e.target, data._stats);
      if (errors) {
        patch({ ...data, _stats: { ...withSubmittedValues(data._stats, entered), _saved: false, _error: null, _fieldErrors: errors } });
        return;
      }
      if (!Object.keys(fields).length) {
        patch({ ...data, _stats: { ...data._stats, _saved: false, _error: 'Nothing changed yet — edit a field, then save.', _fieldErrors: null } });
        return;
      }
      console.info('[reach] PATCH /api/v1/profile/stats request', { fields });
      try {
        await session.patch('/api/v1/profile/stats', { fields });
      } catch (err) {
        console.error('[reach] PATCH failed', err);
        const parsed = fieldErrorsFromServer(err.message, data._stats);
        patch({ ...data, _stats: { ...withSubmittedValues(data._stats, entered), _saved: false, _fieldErrors: parsed.byField, _error: parsed.general || (parsed.byField ? null : 'Could not save — try again.') } });
        return;
      }
      let confirmed;
      try {
        confirmed = await session.get('/api/v1/profile/stats');
        console.info('[reach] confirmation GET response', confirmed);
      } catch (err) {
        console.error('[reach] confirmation GET failed', err);
        patch({ ...data, _stats: { ...withSubmittedValues(data._stats, fields), _saved: false, _error: 'Saved, but could not confirm — reload to check.' } });
        return;
      }
      const byKey = Object.fromEntries((confirmed.rows || []).map((r) => [r.key, r.value]));
      const mismatched = Object.keys(fields).filter((k) => !fieldsEqual(byKey[k], fields[k]));
      if (mismatched.length) {
        console.error('[reach] MISMATCH: server read-back does not match what was submitted', { submitted: fields, read_back: byKey, mismatched });
        patch({ ...data, _stats: { ...withSubmittedValues(confirmed, fields), _saved: false, _error: "That didn't actually save — the server's own copy doesn't match. Try again, or reload to see what's really there." } });
        return;
      }
      patch({ ...(await session.get('/api/v1/reach')), _stats: null });
    });
  });

  // Dual overlaid range inputs, sheet-only now: dragging redraws the bar
  // locally (no request per pixel); releasing (the "change" event) commits.
  root.querySelectorAll('.p-chip-sheet .filter[data-lever]').forEach((card) => {
    const minInput = card.querySelector('.range-min');
    const maxInput = card.querySelector('.range-max');
    const min = parseFloat(card.dataset.min), max = parseFloat(card.dataset.max);
    const redraw = () => {
      const lo = parseFloat(minInput.value), hi = parseFloat(maxInput.value);
      const loPct = ((lo - min) / (max - min)) * 100, hiPct = ((hi - min) / (max - min)) * 100;
      const selected = card.querySelector('.slider-selected');
      selected.style.left = loPct + '%';
      selected.style.width = Math.max(0, hiPct - loPct) + '%';
      card.querySelector('.sv-min').textContent = lo;
      card.querySelector('.sv-max').textContent = hi;
    };
    const clampAndDraw = (active) => {
      if (parseFloat(minInput.value) > parseFloat(maxInput.value)) {
        if (active === minInput) maxInput.value = minInput.value; else minInput.value = maxInput.value;
      }
      redraw();
    };
    minInput.addEventListener('pointerdown', () => { minInput.style.zIndex = 3; maxInput.style.zIndex = 2; });
    maxInput.addEventListener('pointerdown', () => { maxInput.style.zIndex = 3; minInput.style.zIndex = 2; });
    minInput.addEventListener('input', () => clampAndDraw(minInput));
    maxInput.addEventListener('input', () => clampAndDraw(maxInput));
    const commit = () => {
      if (card.classList.contains('is-any')) return;
      run(async () => {
        patch(await session.post('/api/v1/reach/set-range', { lever: card.dataset.lever, min: parseFloat(minInput.value), max: parseFloat(maxInput.value) }));
      });
    };
    minInput.addEventListener('change', commit);
    maxInput.addEventListener('change', commit);
    // Property assignments work under the installed app's strict CSP. Inline
    // style attributes in HTML strings were blocked outside Vite preview.
    redraw();
    const slider = data.sliders.find((s) => s.key === card.dataset.lever);
    const self = card.querySelector('.slider-self');
    if (self) self.style.left = trackPct(min, max, slider.self_value) + '%';
    const suggested = card.querySelector('.slider-suggested');
    if (suggested) {
      const left = trackPct(min, max, slider.suggested[0]);
      suggested.style.left = left + '%';
      suggested.style.width = (trackPct(min, max, slider.suggested[1]) - left) + '%';
    }
  });
}
