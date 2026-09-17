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
import { editableFieldsForm, collectFields } from './stats.js';

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>REACH</h1></section><section class="card"><p>Loading…</p></section>';
  const { counts, filters = [], sliders = [], ignored_count = 0, all_ignored } = data;
  const choices = filters.filter((f) => f.control === 'choice');
  const basicSliders = sliders.filter((s) => s.basic);
  const moreSliders = sliders.filter((s) => !s.basic);
  const basicChoices = choices.filter((f) => f.basic);
  const moreChoices = choices.filter((f) => !f.basic);
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

      <div>${basicSliders.map(sliderRow).join('')}${basicChoices.map(choiceRow(safe)).join('')}</div>

      ${moreSliders.length || moreChoices.length ? `<details class="more-filters"><summary>More filters</summary>
        <div>${moreSliders.map(sliderRow).join('')}${moreChoices.map(choiceRow(safe)).join('')}</div>
      </details>` : ''}

      <div class="hint" style="margin-top:12px;">Widening yours only helps where theirs already lets you in — both of you have to be open.</div>
    </section>

    <section class="card">
      <div class="section-label" style="margin:0;">Missing a filter you expected?</div>
      <div class="hint">A filter only appears once you've told us the matching stat — add it here without leaving REACH.</div>
      ${data._stats ? editableFieldsForm(data._stats, safe, 'inline-stats-form') : '<button id="edit-stats-toggle" class="secondary" type="button">Edit your stats</button>'}
    </section>

    <section class="card guru-card"><div class="guru-avatar">G</div><div>Nationality and religion are yours to explore — I'll never suggest widening them.</div></section>`;
}

function sliderRow(s) {
  const span = s.max - s.min;
  const pct = (v) => ((v - s.min) / span) * 100;
  const [lo, hi] = s.current || [s.min, s.max];
  return `<div class="filter${s.ignored ? ' is-any' : ''}" data-lever="${s.key}" data-min="${s.min}" data-max="${s.max}" data-step="${s.step}">
    <div class="filter-head">
      <span class="filter-name">${s.label}</span>
      <span class="filter-readout"><span class="sv-min">${lo}</span>–<span class="sv-max">${hi}</span> ${s.unit}</span>
      <label class="any-switch"><input type="checkbox" class="filter-any" data-filter="${s.key}" ${s.ignored ? 'checked' : ''}><span>Any</span></label>
    </div>
    <div class="slider-track-wrap">
      <div class="slider-track"></div>
      ${s.suggested ? `<div class="slider-suggested" style="left:${pct(s.suggested[0])}%;width:${pct(s.suggested[1]) - pct(s.suggested[0])}%"></div>` : ''}
      <div class="slider-selected" style="left:${pct(lo)}%;width:${Math.max(0, pct(hi) - pct(lo))}%"></div>
      ${s.self_value != null ? `<div class="slider-self" style="left:${pct(s.self_value)}%" title="You: ${s.self_value} ${s.unit}"></div>` : ''}
      <input type="range" class="range-min" min="${s.min}" max="${s.max}" step="${s.step}" value="${lo}">
      <input type="range" class="range-max" min="${s.min}" max="${s.max}" step="${s.step}" value="${hi}">
    </div>
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

export function bind(root, ctx) {
  const { session, run, patch, data } = ctx;

  root.querySelectorAll('.filter-any').forEach((box) => box.addEventListener('change', () => run(async () => {
    patch(await session.post('/api/v1/reach/ignore', { filter: box.dataset.filter, ignore: box.checked }));
  })));

  root.querySelector('#show-all')?.addEventListener('click', (e) => run(async () => {
    patch(await session.post('/api/v1/reach/show-all', { ignore: e.target.dataset.ignore === 'true' }));
  }));

  root.querySelector('#edit-stats-toggle')?.addEventListener('click', () => run(async () => {
    patch({ ...data, _stats: await session.get('/api/v1/profile/stats') });
  }));

  root.querySelector('#inline-stats-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      await session.patch('/api/v1/profile/stats', { fields: collectFields(e.target) });
      // A saved stat can unlock a new REACH lever (matching.py's
      // unlock_levers_for runs on every stats save) — reload the reach
      // state itself, not just the stats sub-form, so a newly-unlocked
      // filter shows up without a manual refresh. The inline editor
      // collapses back to its toggle; reopening it re-fetches fresh rows.
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
  });
}
