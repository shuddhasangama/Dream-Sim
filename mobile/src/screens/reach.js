// REACH (mobile-journey-build-spec.md §2.1), ported from templates/reach.html
// and static/app.js — one row per filter, name + Any switch + (for a range)
// a real draggable slider, never a name shown twice in two different
// controls. Every field comes straight from GET /api/v1/reach's own
// _reach_state() shape — counts, filters, sliders — nothing here is a
// client-side guess at what REACH considers a match.
//
// Two rules enforced structurally, not just by care:
//   - nationality/religion never appear as a "widen this" suggestion —
//     `deltas` (the auto-suggested widen list) is never rendered at all;
//     they only ever show up in `filters`, the person's own deliberate
//     choice, marked "yours" (sensitive) rather than nudged.
//   - every mutation (widen/set-range/ignore/show-all) returns the FULL
//     fresh state already (the server's own _reach_state()), so a
//     successful call patches ctx directly instead of a second round-trip.
//
// road-fixes-clock-spec.md §6: a missing stat is what keeps a filter out
// of this screen in the first place (matching.unlock_levers_for runs on
// every stats save, so filling one in is what actually adds the row) —
// but /api/v1/reach has no "here's what's locked and why" field to key an
// inline prompt off, so this offers stats editing unconditionally rather
// than pretending to know which filter a person is missing. `_stats` is a
// transient slice of GET /api/v1/profile/stats folded into this screen's
// own data, fetched lazily so opening REACH never pays for a request it
// might not need.
import { editableFieldsForm, changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } from '../statsFields.js';

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>REACH</h1></section><section class="card"><p>Loading…</p></section>';
  const { counts, filters = [], sliders = [], ignored_count = 0, all_ignored } = data;
  const choiceGroups = groupChoices(filters.filter((f) => f.control === 'choice'));
  const basicSliders = sliders.filter((s) => s.basic);
  const moreSliders = sliders.filter((s) => !s.basic);
  const basicChoices = choiceGroups.filter((g) => g.basic);
  const moreChoices = choiceGroups.filter((g) => !g.basic);
  const mutual = counts?.mutual_open ?? 0;

  return `<section class="intro"><span class="eyebrow">REACH · Reciprocity this week</span><h1>See who opens up.</h1></section>
    <section class="card reach-summary">
      <div><span class="reach-number">${safe(mutual)}</span> ${mutual === 1 ? 'person' : 'people'}</div>
      <div class="micro">of ${safe(counts?.fits_user_filters ?? 0)} who fit what you want are also open to you</div>
      <div class="micro">${data.counting_unverified
        ? 'Counting everyone here — verified and not yet verified — so you can see the place. Once you are verified this narrows to people you could actually be matched with.'
        : 'Counting verified people only. These are the ones the weekly matcher can actually pair you with.'}</div>
      ${counts?.no_realistic_matches ? '<div class="micro" style="color:var(--coral-1);margin-top:8px;">No realistic matches yet at your current filters — the one for you may not have signed up yet.</div>' : ''}
    </section>

    <section class="card">
      <div class="filter-bar">
        <div class="section-label" style="margin:0;">Your filters</div>
        <button class="secondary btn-showall" id="show-all" data-ignore="${all_ignored ? 'false' : 'true'}" type="button">${all_ignored ? 'Put them back' : 'Any for everything'}</button>
      </div>
      <div class="hint">${ignored_count
        ? `${safe(ignored_count)} set to Any. Nothing was deleted — switch one back and it returns as you left it.`
        : 'Set anything to <strong>Any</strong> and it stops narrowing your pool.'}</div>

      <div>${basicSliders.map(sliderRow).join('')}${basicChoices.map(choiceGroupRow(safe)).join('')}</div>

      ${moreSliders.length || moreChoices.length ? `<details class="more-filters" ${moreFiltersOpen ? 'open' : ''}><summary>More filters</summary>
        <div>${moreSliders.map(sliderRow).join('')}${moreChoices.map(choiceGroupRow(safe)).join('')}</div>
      </details>` : ''}

      <div class="hint" style="margin-top:12px;">Widening yours only helps where theirs already lets you in — both of you have to be open.</div>
    </section>

    <section class="card">
      <div class="section-label" style="margin:0;">Missing a filter you expected?</div>
      <div class="hint">A filter only appears once you've told us the matching stat — add it here without leaving REACH.</div>
      ${(data.locked_levers || []).length ? `<ul class="locked-levers">${data.locked_levers.map((l) => `<li>${safe(l.label)} <span class="hint">— add ${safe(l.needs)} to filter on it</span></li>`).join('')}</ul>` : ''}
      ${data._stats ? `${editableFieldsForm(data._stats, safe, 'inline-stats-form')}
        <button id="cancel-stats-edit" class="secondary" type="button" style="margin-top:8px;">Cancel</button>
        ${data._stats._saved ? '<p class="save-note">Saved.</p>' : ''}
        ${data._stats._error ? `<p class="warn">${safe(data._stats._error)}</p>` : ''}`
        : '<button id="edit-stats-toggle" class="secondary" type="button">Edit your stats</button>'}
    </section>

    <section class="card guru-card"><div class="guru-avatar">G</div><div>Nationality and religion are yours to explore — I'll never suggest widening them.</div></section>`;
}

// Every change re-renders the whole screen, which would snap "More filters"
// shut under the person's finger after each choice inside it — so its open
// state is remembered across renders.
let moreFiltersOpen = false;

// Position of a value along a min..max track, as a percentage clamped to
// the track (round4-fixes-spec.md §3: 38 on the 21–80 age track is 28.8%).
export function trackPct(min, max, value) {
  const span = max - min;
  if (!(span > 0)) return 0;
  return Math.min(100, Math.max(0, ((value - min) / span) * 100));
}

function sliderRow(s) {
  const [lo, hi] = s.current || [s.min, s.max];
  return `<div class="filter${s.ignored ? ' is-any' : ''}" data-lever="${s.key}" data-min="${s.min}" data-max="${s.max}" data-step="${s.step}">
    <div class="filter-head">
      <span class="filter-name">${s.label}</span>
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

function choiceRow(safe) {
  return (f) => `<div class="filter is-choice${f.ignored ? ' is-any' : ''}" data-filter="${f.name}">
    <div class="filter-head">
      <span class="filter-name">${safe(f.label)}${f.sensitive ? ' <span class="sensitive-tag">yours</span>' : ''}</span>
      <span class="filter-readout">${f.ignored ? 'Any' : safe(f.on_label)}</span>
      <label class="any-switch"><input type="checkbox" class="filter-any" data-filter="${safe(f.name)}" ${f.ignored ? 'checked' : ''}><span>Any</span></label>
    </div>
    <div class="filter-foot">
      <span></span>
      <span class="filter-delta">${f.ignored ? (f.delta_if_ignored > 0 ? `−${f.delta_if_ignored} if switched back on` : '') : (f.delta_if_ignored > 0 ? `+${f.delta_if_ignored} on Any` : '')}</span>
    </div>
  </div>`;
}

// round3-fixes-spec.md §4.2: "Wants kids" and "Does not want kids" as two
// separate Any-switch rows was duplicative — they are two answers to one
// question (matching.py's _OPPOSITES). Which filter names pair up comes
// from each filter's own `opposite` field, not a hardcoded list here, so
// this generalizes to any future opposite pair the API adds.
function groupChoices(choices) {
  const byName = new Map(choices.map((f) => [f.name, f]));
  const seen = new Set();
  const groups = [];
  for (const f of choices) {
    if (seen.has(f.name)) continue;
    const opp = f.opposite ? byName.get(f.opposite) : null;
    seen.add(f.name);
    if (opp) {
      seen.add(opp.name);
      groups.push({ kind: 'paired', options: [f, opp], basic: f.basic });
    } else {
      groups.push({ kind: 'single', filter: f, basic: f.basic });
    }
  }
  return groups;
}

function choiceGroupRow(safe) {
  return (group) => (group.kind === 'paired' ? pairedChoiceRow(safe, group.options) : choiceRow(safe)(group.filter));
}

// Presentational only, same as nav.js's own SURFACE_LABELS — the API
// names which two filters pair up (via `opposite`), not what to call the
// merged row. A pair this map doesn't know falls back to the first
// filter's own label rather than showing nothing.
const PAIR_GROUP_LABELS = { wants_kids: 'Kids', no_kids_wanted: 'Kids', no_existing_children: 'Kids', has_existing_children: 'Kids' };

function pairedChoiceRow(safe, [a, b]) {
  const selected = !a.ignored ? a.name : (!b.ignored ? b.name : '');
  if (a.name === 'no_existing_children' || a.name === 'has_existing_children') {
    const choice = f => `<label class="paired-choice-option"><input type="checkbox" data-children-filter="${safe(f.name)}" value="${safe(f.name)}" ${!f.ignored ? 'checked' : ''}><span>${safe(f.on_label)}</span></label>`;
    return `<div class="filter is-choice" data-paired="${safe(a.name)}|${safe(b.name)}"><div class="filter-head"><span class="filter-name">Kids</span></div><p class="muted">Children they already have. Future parenting preferences belong in Vision.</p><div class="paired-choice-options">${choice(b)}${choice(a)}</div><p class="muted">Leave both unselected to include everyone.</p></div>`;
  }
  const groupName = `paired-${a.name}-${b.name}`;
  const option = (name, optLabel) => `<label class="paired-choice-option"><input type="radio" name="${safe(groupName)}" value="${safe(name)}" ${selected === name ? 'checked' : ''}><span>${safe(optLabel)}</span></label>`;
  return `<div class="filter is-choice${!selected ? ' is-any' : ''}" data-paired="${safe(a.name)}|${safe(b.name)}">
    <div class="filter-head">
      <span class="filter-name">${safe(PAIR_GROUP_LABELS[a.name] || a.label)}${a.sensitive || b.sensitive ? ' <span class="sensitive-tag">yours</span>' : ''}</span>
    </div>
    <div class="paired-choice-options">
      ${option(a.name, a.on_label)}${option(b.name, b.on_label)}${option('', 'Any')}
    </div>
  </div>`;
}

export function bind(root, ctx) {
  const { session, run, patch, data } = ctx;

  root.querySelector('details.more-filters')?.addEventListener('toggle', (e) => { moreFiltersOpen = e.target.open; });

  root.querySelectorAll('.filter-any').forEach((box) => box.addEventListener('change', () => run(async () => {
    patch(await session.post('/api/v1/reach/ignore', { filter: box.dataset.filter, ignore: box.checked }));
  })));

  // round3-fixes-spec.md §4.2: the merged kids control still just calls
  // /api/v1/reach/ignore — the same endpoint the individual Any-switches
  // use — since matching.set_ignored() already clears the opposite tag
  // server-side when one of a pair is turned on.
  root.querySelectorAll('[data-children-filter]').forEach(box=>box.addEventListener('change',()=>run(async()=>{
    patch(await session.post('/api/v1/reach/ignore',{filter:box.dataset.childrenFilter,ignore:!box.checked}));
  })));
  root.querySelectorAll('[data-paired] input[type="radio"]').forEach((radio) => radio.addEventListener('change', () => run(async () => {
    const [nameA, nameB] = radio.closest('[data-paired]').dataset.paired.split('|');
    if (radio.value) {
      patch(await session.post('/api/v1/reach/ignore', { filter: radio.value, ignore: false }));
    } else {
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
      // Same "don't trust a 200, re-read it back" discipline as
      // chemistry.js (round3-fixes-spec.md §1/§3): confirm the saved
      // values independently before treating this as done.
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
      // A saved stat can unlock a new REACH lever (matching.py's
      // unlock_levers_for runs on every stats save) — reload the reach
      // state itself, not just the stats sub-form, so a newly-unlocked
      // filter shows up without a manual refresh.
      patch({ ...(await session.get('/api/v1/reach')), _stats: null });
    });
  });

  // Dual overlaid range inputs: dragging redraws the bar locally (no
  // request per pixel); releasing (the "change" event) commits the range.
  root.querySelectorAll('.filter[data-lever]').forEach((card) => {
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
    const slider=data.sliders.find(s=>s.key===card.dataset.lever);
    const self=card.querySelector('.slider-self');
    if(self) self.style.left=trackPct(min,max,slider.self_value)+'%';
    const suggested=card.querySelector('.slider-suggested');
    if(suggested) {
      const left=trackPct(min,max,slider.suggested[0]);
      suggested.style.left=left+'%';
      suggested.style.width=(trackPct(min,max,slider.suggested[1])-left)+'%';
    }
  });
}
