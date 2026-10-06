import * as personal from './personal.js';
let personalData=null, personalOwner=null;
// Home (design_handoff_app_ui_pulse/README.md, option "1a Pulse"): replaces
// the old Dashboard screen's presentation. Same data, same edit flows —
// Vision/Chemistry/Stats are still exactly screens/vision.js,
// screens/chemistry.js and statsFields.js's editableFieldsForm, just reached
// through three rings and one detail card instead of two collapsible
// accordions and a stat-rows list.
//
// ctx additions main.js provides beyond the usual buildCtx() shape (see
// main.js's own comments for why each lives there rather than here):
//   folds        — { vision: {open,data,error}, chemistry: {open,data,error} },
//                  eagerly loaded (main.js's load()) so the rings have a
//                  real percentage the moment Home first renders, not only
//                  after the person taps in.
//   dashboardStats/statsSummary — the existing Stats editor's own state.
//   weekSummary  — GET /api/v1/week's last response, fetched alongside
//                  profile/stats so the "Next up" card has a real source
//                  (mobile-journey-build-spec.md's own weekly schedule),
//                  never a client-side guess at what's next.
//   toggleFold(key) — flips folds[key].open without forcing a refetch
//                  (the data is already fresh from load()).

// The four fixed Vision pillars are look-and-feel copy for the ring/tiles
// ONLY — never business logic. The real list is always element_keys, from
// GET /api/v1/profile/vision's own response (folds.vision.data); this
// constant is nothing but the label a client shows before that request
// resolves at least once, the same fallback role DASHBOARD_STAT_ROWS plays
// for Stats below.
const VISION_PILLARS_FALLBACK = ['Intimacy', 'Kids', 'Cohabitate', 'Travel together'];

// Every stat row the web dashboard shows, in its exact order (unchanged
// from the old renderDashboard) — reused here for the Stats ring's fact
// tiles and CTA form.
export const DASHBOARD_STAT_ROWS = [
  ['age', 'Age', ''], ['height_cm', 'Height', ' cm'], ['weight_kg', 'Weight', ' kg'],
  ['waist_in', 'Waist', ' in'], ['income_band', 'Salary band', ''], ['diet', 'Diet', ''],
  ['education', 'Education', ''], ['nationality', 'Nationality', ''], ['profession', 'Profession', ''],
  ['religion', 'Religion', ''],
  ['has_children', 'Already has children', ''], ['children_count', 'Number of children', ''],
];

const stanceOf = (goal) => (Array.isArray(goal?.stance) ? goal.stance : goal?.stance ? [goal.stance] : []);

// ── ring math (exported: unit-testable without a DOM) ────────────────────

// A conic-gradient string for a 0–100 ring, `color` filled clockwise from
// 12 o'clock over `track` (round4-fixes-spec.md §3's "conic progress fill",
// same technique the REACH hero ring below reuses). A ring at 0% still
// shows a sliver so it never reads as "broken" rather than "just started".
export function ringGradient(pct, color, track) {
  const clamped = Math.min(100, Math.max(0, pct));
  const deg = Math.max(6, (clamped / 100) * 360);
  return `conic-gradient(${color} 0deg ${deg}deg, ${track} ${deg}deg 360deg)`;
}

// Vision: how many of the fixed pillars have a real answer. Travel together
// carries no sub-selection (onboarding.py/vision.py: it is "selected" on its
// own), so its bare presence in `goals` already counts as answered; every
// other pillar needs at least one stance/sub-selection.
export function visionProgress(visionData) {
  const elementKeys = visionData?.element_keys || VISION_PILLARS_FALLBACK;
  const goals = visionData?.goals || [];
  const byKey = new Map(goals.map((g) => [g.key, g]));
  const answered = elementKeys.filter((k) => byKey.has(k) && (k === 'Travel together' || stanceOf(byKey.get(k)).length > 0)).length;
  return { answered, total: elementKeys.length || 1, pct: Math.round((answered / (elementKeys.length || 1)) * 100) };
}

// Stats: the BGV-verified group, currently verified (round4-fixes-spec.md
// §4's `group`/`check` fields) — "5/5" is literal, not a mock number, since
// stats_edit.VERIFIED is exactly five fields.
export function statsProgress(statsSummary) {
  const verified = (statsSummary?.rows || []).filter((r) => r.group === 'verified');
  const done = verified.filter((r) => r.check === 'verified').length;
  return { answered: done, total: verified.length || 5, pct: Math.round((done / (verified.length || 5)) * 100) };
}

// Chemistry: activities with a bucket pick, out of every activity offered.
export function chemistryProgress(chemistryData) {
  const total = (chemistryData?.activity_options || []).length || 1;
  const done = Object.keys(chemistryData?.activities || {}).length;
  return { answered: done, total, pct: Math.round((done / total) * 100) };
}

// ── "Next up": the next moment from the real weekly schedule ─────────────
// grid.rows[].days[].moments already carries `past` (week_map.grid()'s own
// clock comparison) — the first non-past moment, in day/hour order, is
// "what's coming", exactly the same source Week's own accordion reads.
export function nextUpcoming(weekSummary) {
  const grid = weekSummary?.schedule?.grid;
  if (!grid) return null;
  const dayIndex = (d) => grid.days.findIndex((x) => x.day === d);
  const flat = [];
  grid.rows.forEach((row) => row.days.forEach((d) => (d.moments || []).forEach((m) => flat.push(m))));
  flat.sort((a, b) => (dayIndex(a.day) - dayIndex(b.day)) || (a.hour - b.hour));
  return flat.find((m) => !m.past) || null;
}

// ── rendering ──────────────────────────────────────────────────────────

const RING_DEFS = [
  { key: 'vision', label: 'Vision', color: 'var(--p-vision)', cta: 'Finish vision' },
  { key: 'stats', label: 'Stats', color: 'var(--p-success)', cta: 'Edit stats' },
  { key: 'chemistry', label: 'Chemistry', color: 'var(--p-grad2)', cta: 'Answer next' },
];

// Which ring's detail card is showing — module-level like reach.js's
// `moreFiltersOpen`, since every mutation re-renders the whole app and this
// is purely a client-side selection, not server state.
let selectedRing = 'vision';
export function _selectedRingForTest() { return selectedRing; }
// Called by main.js's openHomeRing() when a link elsewhere (a Guru tile, a
// stale next-action) points at 'vision'/'stats'/'chemistry' — Home is where
// all three actually live now, so the ring just gets pre-selected.
export function selectRing(key) { if (RING_DEFS.some((r) => r.key === key)) selectedRing = key; }

function ringTiles(key, ctx) {
  const { folds, statsSummary, safe } = ctx;
  if (key === 'vision') {
    const f = folds.vision;
    if (f.error) return { blocked: f.error };
    if (!f.data) return { blocked: 'This isn’t available right now.' };
    const { answered, total } = visionProgress(f.data);
    const elementKeys = f.data.element_keys || VISION_PILLARS_FALLBACK;
    const byKey = new Map((f.data.goals || []).map((g) => [g.key, g]));
    const tiles = elementKeys.slice(0, 4).map((k) => ({
      key: k, value: byKey.has(k) ? (stanceOf(byKey.get(k)).join(', ') || 'Set') : 'Not set',
    }));
    // vision.py: Intimacy plus any ONE more already satisfies every rule —
    // "2 of 4" is a real, complete Vision, not an unfinished one, so the
    // summary never frames the other two as owed ("of 4 possible", never
    // "of 4 set" or a bare fraction that reads like a completion score).
    return { tiles, summary: `${answered} of ${total} possible pillars` };
  }
  if (key === 'chemistry') {
    const f = folds.chemistry;
    if (f.error) return { blocked: f.error };
    if (!f.data) return { blocked: 'This isn’t available right now.' };
    const { answered, total } = chemistryProgress(f.data);
    const tiles = (f.data.activity_options || []).slice(0, 4).map((a) => ({ key: a, value: f.data.activities?.[a] || 'Not answered' }));
    return { tiles, summary: `${total - answered} prompts left` };
  }
  // stats
  const rows = statsSummary?.rows || [];
  const byKey = new Map(rows.map((r) => [r.key, r]));
  const verified = DASHBOARD_STAT_ROWS.filter(([k]) => byKey.get(k)?.group === 'verified').slice(0, 4);
  const tiles = verified.map(([k, label]) => ({ key: label, value: byKey.get(k)?.check === 'verified' ? `✓ ${safe(byKey.get(k).value ?? '')}` : String(byKey.get(k)?.value ?? '—') }));
  const { answered, total } = statsProgress(statsSummary);
  return { tiles, summary: answered === total ? 'All verified' : `${answered}/${total} verified` };
}

// The "Next up" card's real content: journey.next_action (guru.next_action())
// is already the app's one true "what's actually next for this person" —
// state-aware, including a waiting-on-partner state that has no clock time
// attached at all (e.g. signed but the other side hasn't yet). A schedule
// moment is only ever layered on for the eyebrow's small time hint, and
// only when it is honestly TODAY's — never a fabricated deadline for
// something that isn't actually clock-driven right now.
export function nextUpCard(journey, weekSummary) {
  const action = journey?.next_action;
  if (!action || (!action.headline && !action.body)) return null;
  const moment = nextUpcoming(weekSummary);
  const today = weekSummary?.clock?.day;
  const eyebrowTime = moment && (!today || moment.day === today) ? `${String(moment.hour).padStart(2, '0')}:00` : null;
  const dest = action.destination;
  return {
    title: action.headline || action.body,
    body: action.body || '',
    eyebrowTime,
    actionable: !!(dest && dest.eligible && dest.request),
    destinationKey: dest?.key,
  };
}

export function render(ctx) {
  if(personalOwner!==ctx.journey?.user?.user_id){personalData=null;personalOwner=ctx.journey?.user?.user_id;}
  const { journey, folds, dashboardStats, statsSummary, weekSummary, safe, busy } = ctx;
  const user = journey.user;
  const firstName = safe((user.display_name || 'there').trim().split(/\s+/)[0]);
  const indicator = journey.stage_indicator;
  const nextUp = nextUpCard(journey, weekSummary);

  const ringProgress = {
    vision: visionProgress(folds.vision.data),
    stats: statsProgress(statsSummary),
    chemistry: chemistryProgress(folds.chemistry.data),
  };
  const detail = ringTiles(selectedRing, ctx);
  const ringDef = RING_DEFS.find((r) => r.key === selectedRing);
  const editorOpen = selectedRing === 'stats' ? !!dashboardStats : !!folds[selectedRing]?.open;

  return `<section class="p-home-header">
      <div>
        ${journey.clock ? `<div class="p-eyebrow">WEEK ${safe(journey.clock.week)} · ${safe(String(journey.clock.day || '').toUpperCase())}</div>` : ''}
        <h1 class="p-hi">Hi, ${firstName}</h1>
      </div>
      <button type="button" id="p-avatar" class="p-avatar" aria-label="Profile and settings" ${busy ? 'disabled' : ''}>${safe((user.display_name || '?').trim()[0] || '?').toUpperCase()}</button>
    </section>

    ${indicator?.show ? `<div class="p-stage-stepper" role="list" aria-label="${safe(indicator.label)}">
      ${(indicator.stages || []).map((s) => `<div role="listitem" class="p-stage-col">
        <div class="p-stage-bar ${s.state === 'current' ? 'is-current' : ''}"></div>
        <span class="p-stage-label ${s.state === 'current' ? 'is-current' : ''}">${safe(s.label)}</span>
      </div>`).join('')}
    </div>` : ''}

    ${nextUp ? (nextUp.actionable ? `<button type="button" id="p-next-up" class="p-next-up" data-destination="${safe(nextUp.destinationKey || '')}">
        <div><div class="p-next-up-eyebrow">NEXT UP${nextUp.eyebrowTime ? ` · ${safe(nextUp.eyebrowTime)}` : ''}</div><div class="p-next-up-title">${safe(nextUp.title)}</div><p>${safe(nextUp.body)}</p></div>
        <span aria-hidden="true" class="p-next-up-arrow">→</span>
      </button>` : `<div class="p-next-up p-next-up-static">
        <div><div class="p-next-up-eyebrow">NEXT UP${nextUp.eyebrowTime ? ` · ${safe(nextUp.eyebrowTime)}` : ''}</div><div class="p-next-up-title">${safe(nextUp.title)}</div><p>${safe(nextUp.body)}</p></div>
      </div>`) : '<div class="p-card p-next-up-empty">Nothing due — enjoy your week</div>'}

    <div class="p-rings-row">
      ${RING_DEFS.map((r) => `<button type="button" class="p-ring-btn ${selectedRing === r.key ? 'is-selected' : ''}" data-ring="${r.key}">
        <div class="p-ring" style="background:${ringGradient(ringProgress[r.key].pct, r.color, 'var(--p-track)')}">
          <div class="p-ring-inner">${r.key === 'chemistry' ? safe(`${ringProgress[r.key].pct}%`) : safe(`${ringProgress[r.key].answered}/${ringProgress[r.key].total}`)}</div>
        </div>
        <span class="p-ring-label">${r.label}</span>
      </button>`).join('')}
    </div>

    <div class="p-detail-card">
      ${selectedRing === 'vision' ? `<p class="hint">${safe(folds.vision.data?.template_label || 'BYOB — your Vision')}</p>` : ''}
      <div class="p-detail-head"><span class="p-detail-title">${ringDef.label}</span><span class="p-detail-summary">${safe(detail.summary || '')}</span></div>
      ${detail.blocked ? `<p class="hint">${safe(detail.blocked)}</p>` : `<div class="p-fact-grid">${(detail.tiles || []).map((t) => `<div class="p-fact-tile"><div class="p-fact-key">${safe(t.key)}</div><div class="p-fact-value">${safe(t.value)}</div></div>`).join('')}</div>`}
      ${!detail.blocked ? (editorOpen ? '' : `<button type="button" class="p-outline-cta" data-open-editor="${selectedRing}">${ringDef.cta} <span aria-hidden="true">→</span></button>`) : ''}
    </div>

    <section class="card"><button type="button" id="identity-open" class="secondary">Private identity check</button>
    <button type="button" id="personal-open" class="secondary">Photo, ethnicity &amp; health preferences</button>
    ${personalData ? personal.render({...ctx,data:personalData}) : ''}</section>
    ${editorOpen ? `<div class="p-editor-panel" data-editor-body="${selectedRing}">
      ${selectedRing === 'stats' ? renderStatsEditor(ctx) : renderFoldBody(selectedRing, ctx)}
      <button type="button" class="secondary" id="p-close-editor" style="margin-top:10px;">${selectedRing === 'stats' && dashboardStats?._saved ? 'Done' : 'Close'}</button>
    </div>` : ''}`;
}

function renderStatsEditor(ctx) {
  const { dashboardStats, safe } = ctx;
  const { editableFieldsForm } = ctx.statsFields;
  return `${editableFieldsForm(dashboardStats, safe, 'dashboard-stats-form')}
    ${dashboardStats._saved ? '<p class="save-note">Saved.</p>' : ''}
    ${dashboardStats._error ? `<p class="warn">${safe(dashboardStats._error)}</p>` : ''}`;
}

function renderFoldBody(key, ctx) {
  const f = ctx.folds[key];
  if (f.error) return `<p class="warn">${ctx.safe(f.error)}</p>`;
  if (!f.data) return '<p class="hint">Loading…</p>';
  return ctx.screens[key].render({ ...ctx, data: f.data, patch: (next) => { f.data = next; } });
}

export function bind(root, ctx) {
  const { run, session, navigateTo, folds, dashboardStats } = ctx;

  root.querySelector('#personal-open')?.addEventListener('click',()=>run(async()=>{personalData=personalData?null:await session.get('/api/v1/profile/personal');}));
  root.querySelector('#identity-open')?.addEventListener('click',()=>ctx.navigateTo('identity'));
  if(personalData) personal.bind(root,{...ctx,data:personalData,patch:next=>{personalData=next;}});
  root.querySelector('#p-avatar')?.addEventListener('click', () => ctx.openAvatarSheet());
  root.querySelector('#p-next-up')?.addEventListener('click', (e) => navigateTo(e.currentTarget.dataset.destination));

  root.querySelectorAll('[data-ring]').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    selectedRing = btn.dataset.ring;
  })));

  root.querySelector('[data-open-editor]')?.addEventListener('click', () => run(async () => {
    const key = selectedRing;
    if (key === 'stats') { ctx.setDashboardStats(await session.get('/api/v1/profile/stats')); return; }
    ctx.toggleFold(key, true);
  }));
  root.querySelector('#p-close-editor')?.addEventListener('click', () => run(async () => {
    if (selectedRing === 'stats') { ctx.setDashboardStats(null); return; }
    ctx.toggleFold(selectedRing, false);
  }));

  const editorBody = root.querySelector(`[data-editor-body="${selectedRing}"]`);
  if (editorBody) {
    if (selectedRing === 'stats' && dashboardStats) bindStatsEditor(editorBody, ctx);
    else if (folds[selectedRing]?.data) ctx.screens[selectedRing].bind?.(editorBody, { ...ctx, data: folds[selectedRing].data, patch: (next) => { folds[selectedRing].data = next; } });
  }
}

function bindStatsEditor(root, ctx) {
  const { session, run, dashboardStats } = ctx;
  const { changedFields, fieldErrorsFromServer, fieldsEqual, withSubmittedValues } = ctx.statsFields;
  root.querySelector('#dashboard-stats-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const current = ctx.getDashboardStats();
      const { fields, errors, entered } = changedFields(e.target, current);
      if (errors) { ctx.setDashboardStats({ ...withSubmittedValues(current, entered), _saved: false, _error: null, _fieldErrors: errors }); return; }
      if (!Object.keys(fields).length) { ctx.setDashboardStats({ ...current, _saved: false, _error: 'Nothing changed yet — edit a field, then save.', _fieldErrors: null }); return; }
      console.info('[home] PATCH /api/v1/profile/stats request', { fields });
      try { await session.patch('/api/v1/profile/stats', { fields }); }
      catch (err) {
        console.error('[home] PATCH failed', err);
        const parsed = fieldErrorsFromServer(err.message, current);
        ctx.setDashboardStats({ ...withSubmittedValues(current, entered), _saved: false, _fieldErrors: parsed.byField, _error: parsed.general || (parsed.byField ? null : 'Could not save — try again.') });
        return;
      }
      let confirmed;
      try { confirmed = await session.get('/api/v1/profile/stats'); console.info('[home] confirmation GET response', confirmed); }
      catch (err) {
        console.error('[home] confirmation GET failed', err);
        ctx.setDashboardStats({ ...withSubmittedValues(current, fields), _saved: false, _error: 'Saved, but could not confirm — reload to check.' });
        return;
      }
      const byKey = Object.fromEntries((confirmed.rows || []).map((r) => [r.key, r.value]));
      const mismatched = Object.keys(fields).filter((k) => !fieldsEqual(byKey[k], fields[k]));
      if (mismatched.length) {
        console.error('[home] MISMATCH: server read-back does not match what was submitted', { submitted: fields, read_back: byKey, mismatched });
        ctx.setDashboardStats({ ...withSubmittedValues(confirmed, fields), _saved: false, _error: "That didn't actually save — the server's own copy doesn't match. Try again, or reload to see what's really there." });
        return;
      }
      ctx.setDashboardStats({ ...confirmed, _saved: true, _error: null, _fieldErrors: null });
      await ctx.refreshProfile();
    });
  });
}
