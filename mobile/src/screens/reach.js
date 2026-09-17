// REACH (mobile-journey-build-spec.md §2.1). Every field rendered here comes
// straight from GET /api/v1/reach's own _reach_state() shape — counts,
// deltas, filters, sliders — nothing is a client-side guess at what REACH
// considers a match. Two rules enforced structurally, not just by care:
//   - nationality/religion never appear as a "widen this" suggestion (they
//     only ever show up in `filters`, which is the person's own deliberate
//     choice, never something this screen nudges) — see filterRows(), which
//     is the only thing that ever renders a sensitive lever at all.
//   - every mutation (widen/set-range/ignore) returns the FULL fresh state
//     already (app.py's _reach_state()), so a successful call patches ctx
//     directly instead of triggering a second round-trip GET.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>REACH</h1></section><section class="card"><p>Loading…</p></section>';
  const { counts, filters = [], sliders = [] } = data;
  return `<section class="intro"><span class="eyebrow">REACH</span><h1>Who's out there</h1></section>
    <section class="card">
      <div class="stat-row"><span>Open to you</span><strong>${safe(counts?.mutual_open ?? 0)}</strong></div>
      <div class="stat-row"><span>Fit your filters</span><strong>${safe(counts?.fits_user_filters ?? 0)}</strong></div>
      ${counts?.no_realistic_matches ? '<p class="warn">Nobody currently fits — try widening a filter below.</p>' : ''}
      ${data.counting_unverified ? '<p class="hint">Verification is still pending, so this count includes unverified profiles too.</p>' : ''}
    </section>
    <h2>Your ranges</h2>
    ${sliders.map(sliderRow).join('') || '<p class="hint">No range filters unlocked yet.</p>'}
    <h2>Your filters</h2>
    ${filters.map(filterRow).join('') || '<p class="hint">No filters set.</p>'}`;
}

function sliderRow(s) {
  const [lo, hi] = s.current || [];
  const suggested = s.suggested ? `Suggested ${s.suggested[0]}–${s.suggested[1]} ${s.unit}` : '';
  return `<div class="slot" data-slider="${s.key}">
    <div>
      <strong>${s.label}</strong>
      <div class="muted">${lo}–${hi} ${s.unit}${s.self_value != null ? ` · you: ${s.self_value} ${s.unit}` : ''}</div>
      ${suggested ? `<div class="muted">${suggested}</div>` : ''}
    </div>
    <button class="secondary widen" data-lever="${s.key}" type="button" style="width:auto;margin:0;">Widen</button>
  </div>`;
}

function filterRow(f) {
  const delta = f.delta_if_ignored;
  const deltaText = f.ignored
    ? (delta > 0 ? `Restoring this loses ${delta} ${delta === 1 ? 'person' : 'people'}` : '')
    : (delta > 0 ? `Setting to Any opens ${delta} more ${delta === 1 ? 'person' : 'people'}` : '');
  return `<div class="slot" data-filter="${f.name}">
    <div>
      <strong>${f.label}</strong>
      <div class="muted">${f.ignored ? 'Any' : f.on_label}${f.sensitive ? ' · you control this' : ''}</div>
      ${deltaText ? `<div class="muted">${deltaText}</div>` : ''}
    </div>
    <button class="secondary toggle-ignore" data-filter="${f.name}" data-ignore="${!f.ignored}" type="button" style="width:auto;margin:0;">${f.ignored ? 'Restore' : 'Set to Any'}</button>
  </div>`;
}

export function bind(root, ctx) {
  const { session, run, patch } = ctx;
  root.querySelectorAll('.widen').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    patch(await session.post('/api/v1/reach/widen', { lever: btn.dataset.lever }));
  })));
  root.querySelectorAll('.toggle-ignore').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    patch(await session.post('/api/v1/reach/ignore', { filter: btn.dataset.filter, ignore: btn.dataset.ignore === 'true' }));
  })));
}
