// Week & Match (§2.2) and Lock-in (§2.3) — presentation redesigned per
// design_handoff_app_ui_pulse/README.md ("Pulse", option 1a): a day strip
// plus one day's events at a time, instead of the full 7×4 grid. The DATA
// is exactly the same server read model (GET /api/v1/week's own `schedule.
// grid`/`matches`/`mode`) — this file only reshapes how it's drawn.
//
// §2.2's atomicity rule: GET is read-only, and render() never changes state.
// round4-fixes-spec.md §8: POST /week/prepare is internal setup (it freezes
// this week's match set; no input, idempotent), not a decision for the
// person — so there is no button for it. ensurePrepared() below runs it once
// when the screen is LOADED (and after the demo clock steps), never from
// render(), and only when the server's own `prepare_request` says it is
// both needed and allowed.
//
// Lock-in has no partner-picking endpoint by design (§2.3) — this screen
// only ever expresses interest/pass on a slot the server already revealed.

import { CALENDAR_VIDEO } from '../config.js';

// Called by main.js right after GET /api/v1/week on a screen load. The
// server only sends `prepare_request` when the week is unprepared, the user
// is a verified Dating user who is not locked in, and the week has started —
// so no client-side rule decides eligibility. 409 means someone else got
// there first (or the state moved: locked in, week not open) — "already
// handled", never a retry: the fresh GET is the answer.
export async function ensurePrepared(session, data) {
  const req = data?.prepare_request;
  if (!req) return data;
  console.info('[week] preparing this week (automatic, once per load)', req);
  try {
    return await session.post(req.path, req.body ?? {});
  } catch (err) {
    if (err?.status === 409) return session.get('/api/v1/week');
    throw err;
  }
}

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Week</h1></section><section class="card"><p>Loading…</p></section>';
  if (data.mode === 'post_dating') return postDating(ctx);
  if (data.mode === 'locked_in') return lockedIn(ctx);
  return dating(ctx);
}

function postDating(ctx) {
  return `<section class="intro"><span class="p-eyebrow">WEEK</span></section>
    ${weekHeader(ctx)}
    <section class="p-card" style="margin-top:20px;"><p style="margin:0;">REACH and the weekly matches have sunset for you — Guru and Journey are where things continue from here.</p></section>`;
}

function lockedIn(ctx) {
  const { data, safe } = ctx;
  const li = data.lock_in;
  return `<section class="intro"><span class="p-eyebrow">WEEK · LOCKED IN</span></section>
    ${confirmDateAvailable(ctx) ? '<section class="p-card guidance"><h2>Confirm Date</h2><p>Save your availability, then confirm a slot when you are both free.</p><button id="to-calendar" class="primary" type="button">Confirm Date →</button></section>' : ''}
    ${weekHeader(ctx)}
    <section class="p-card" style="margin-top:20px;">
      <div class="stat-row"><span>Status</span><strong>${safe(li?.status)}</strong></div>
      <div class="stat-row"><span>Since week</span><strong>${safe(li?.week)}</strong></div>
      <div class="stat-row"><span>Dates completed</span><strong>${safe(li?.dates_completed ?? 0)}</strong></div>
    </section>
    <section class="p-card" style="margin-top:14px;"><p style="margin:0;">No one else can be matched to you while you're locked in — REACH is closed for now.</p></section>`;
}

export function confirmDateAvailable(ctx) {
  const day = ctx.data?.clock?.day;
  return !ctx.data?.date_plan && ['Mon','Tue','Wed','Thu'].includes(day)
    && !(ctx.journey?.async_rehearsal?.intro_step < 4)
    && !!ctx.journey?.surfaces?.find(s => s.key === 'calendar' && s.eligible && s.request);
}

function dating(ctx) {
  const { data } = ctx;
  if (!data.prepared) {
    return `<section class="intro"><span class="p-eyebrow">WEEK ${ctx.safe(data.clock?.week)}</span></section>
      ${weekHeader(ctx)}
      <p class="hint" style="margin-top:16px;">Your matches for this week appear here as the week opens.</p>`;
  }
  return weekHeader(ctx);
}

// ── day math ─────────────────────────────────────────────────────────────
// A decorative calendar date under each day letter — pure client-side
// arithmetic against clock.py's own WEEK_ONE_MONDAY epoch (a fixed Monday),
// so it needs no new endpoint: week+weekday alone already determine it,
// exactly the way app.py's week_to_date() derives a real date server-side.
const DAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DAY_FULL_NAMES = { Mon: 'Monday', Tue: 'Tuesday', Wed: 'Wednesday', Thu: 'Thursday', Fri: 'Friday', Sat: 'Saturday', Sun: 'Sunday' };
const WEEK_ONE_MONDAY_UTC = Date.UTC(2026, 0, 5);
export function dateOfMonth(week, day) {
  const dayIdx = DAY_ORDER.indexOf(day);
  if (dayIdx < 0 || !Number.isFinite(week)) return null;
  return new Date(WEEK_ONE_MONDAY_UTC + ((week - 1) * 7 + dayIdx) * 86400000).getUTCDate();
}

// Every category colour dot — day-strip and event list both key off the
// same `tone` the grid already carries (week_map.MOMENTS's own `tone`),
// mapped to the spec's six named categories; `muted` (Rank) gets a plain
// neutral dot rather than inventing a seventh category.
const CATEGORY_COLOR = {
  match: '#FF5A7A', reality: '#3CC6C0', calendar: '#A58BFF',
  publish: '#3DDC97', date: '#F5B54A', debrief: '#E889B5', muted: '#8A86A3',
};

// Every moment, flattened per day (not just the ones with a `means`, unlike
// the old "What each one means" list — the day strip's dots and the event
// list both need EVERY moment), sorted by hour within the day.
export function momentsByDay(grid) {
  const byDay = Object.fromEntries(grid.days.map((d) => [d.day, []]));
  grid.rows.forEach((row) => row.days.forEach((d) => (d.moments || []).forEach((m) => byDay[d.day]?.push(m))));
  Object.values(byDay).forEach((list) => list.sort((a, b) => a.hour - b.hour));
  return byDay;
}

// week_map.MOMENTS' `tone: 'date'` entries (Breakfast/Lunch/Coffee/Dinner on
// Fri/Sat/Sun) are a FIXED, always-present template — "a confirmed slot can
// fall anywhere across the weekend" — never three real bookings. The old
// 7×4 grid showed them as small same-size chips alongside everything else,
// which read as decorative; a full-width event card gives every one of
// them the same visual weight as a real, scheduled thing, which could
// easily be misread as "three date bookings this weekend." Only the ONE
// that matches this couple's own confirmed plan (by day + hour, the only
// fields current_date_plan actually carries) is real — the rest are
// dropped rather than shown as though they were.
export function confirmedDateMoment(datePlan) {
  if (!datePlan?.datetime) return null;
  const [datePart, timePart] = datePlan.datetime.split('T');
  if (!datePart || !timePart) return null;
  const dayIdx = (new Date(datePart + 'T00:00:00Z').getUTCDay() + 6) % 7; // Mon=0
  return { day: DAY_ORDER[dayIdx], hour: parseInt(timePart.slice(0, 2), 10) };
}

// Drops every generic weekend meal-slot moment except the one (if any)
// that is this couple's own real confirmed date — marked `personal` so it
// gets the same "this one's actually yours" treatment as the debrief
// moment already has.
export function withRealDateOnly(byDay, datePlan) {
  const real = confirmedDateMoment(datePlan);
  const out = {};
  for (const [day, moments] of Object.entries(byDay)) {
    out[day] = moments
      .filter((m) => m.tone !== 'date' || (real && real.day === day && real.hour === m.hour))
      .map((m) => (m.tone === 'date' ? { ...m, personal: true, means: m.means || 'Your confirmed date.' } : m));
  }
  return out;
}

const MATCH_KEY_TO_SLOT = { match_1: 1, match_2: 2, match_3: 3 };
// A moment that corresponds to an existing screen worth opening from here —
// the surface key it maps to, and the label that screen's own tab already
// uses for its CTA (calendar.js/plan.js), so nothing new is invented.
const NAV_FOR_MOMENT = {
  slots: { surface: 'calendar', label: 'Confirm Date' },
  calendar_closes: { surface: 'plan', label: 'View plan' },
  sign: { surface: 'plan', label: 'Review & sign' },
  debrief: { surface: 'debrief', label: 'Open debrief' },
  // The one surviving "date" moment (withRealDateOnly above) is this
  // couple's own confirmed date — its own plan is one tap away too.
  date_fri: { surface: 'plan', label: 'View date plan' },
  date_fri_eve: { surface: 'plan', label: 'View date plan' },
  date_sat_m: { surface: 'plan', label: 'View date plan' },
  date_sat_a: { surface: 'plan', label: 'View date plan' },
  date_sat_e: { surface: 'plan', label: 'View date plan' },
  date_sun_m: { surface: 'plan', label: 'View date plan' },
  date_sun_a: { surface: 'plan', label: 'View date plan' },
  date_sun_e: { surface: 'plan', label: 'View date plan' },
};

// Which event is expanded inline — module-level like reach.js's sheet key,
// since every mutation re-renders the whole app and this is purely a
// client-side selection.
let expandedKey = null;
// Which day is selected — null means "today" (grid.days[].is_today), so a
// fresh load always defaults there without this module remembering a
// specific index across an unrelated week.
let selectedDay = null;
// Every OTHER state change (the clock stepping, an event expanding) re-
// renders the whole screen, which would otherwise snap the video section
// shut under the person's finger — its open state is remembered the same
// way reach.js remembers "More filters"/the sheet.
let videoOpen = false;

function weekHeader(ctx) {
  const { data, safe, journey, simulatedClockBuild, navigateTo } = ctx;
  const schedule = data.schedule;
  if (!schedule?.grid) return '';
  const { grid } = schedule;
  const byDay = withRealDateOnly(momentsByDay(grid), data.date_plan);
  const todayIdx = grid.days.findIndex((d) => d.is_today);
  const matchBySlot = Object.fromEntries((data.matches || []).map((m) => [m.slot, m]));
  // A currently-open match's own reveal day can be a day BEHIND today's
  // (Match 1 opens Monday and stays actionable through Tuesday's midday),
  // so the day this screen opens on defaults there instead of "today" when
  // the person hasn't picked a day yet this visit — otherwise reaching an
  // actionable match would mean already knowing which day to tap first.
  const openMatchDayIdx = (() => {
    const openMatch = (data.matches || []).find((m) => m.status === 'open');
    if (!openMatch) return -1;
    const key = `match_${openMatch.slot}`;
    return grid.days.findIndex((d) => (byDay[d.day] || []).some((m) => m.key === key));
  })();
  const selectedIdx = selectedDay != null ? selectedDay : (openMatchDayIdx >= 0 ? openMatchDayIdx : (todayIdx >= 0 ? todayIdx : 0));
  const selected = grid.days[selectedIdx];
  const events = byDay[selected.day] || [];

  const simClock = journey?.simulated_clock && simulatedClockBuild && !journey?.accelerated_test?.enabled && !journey?.async_rehearsal?.enabled ? `<div class="demo-bar">
      <span class="demo-tag">SIMULATION</span>
      <span class="demo-clock">${safe(data.clock?.day)} ${String(data.clock?.hour ?? 0).padStart(2, '0')}:00 · Week ${safe(data.clock?.week)}</span>
      <div class="demo-steps">
        <button class="demo-step" type="button" data-advance="1">+1 hour</button>
        <button class="demo-step" type="button" data-advance="24">+1 day</button>
        <button class="demo-step" type="button" data-advance="168">+1 week</button>
      </div>
    </div>` : '';
  const rehearsalCopy = journey?.async_rehearsal?.enabled
    ? '<p class="hint" style="margin-top:8px;">Test clock: 3-minute steps until Wednesday 18:00, then partner actions. Revealed matches stay open.</p>' : '';

  return `${simClock}${data.fixed_test_pair ? '<p class="hint">One assigned partner for this test. Both choose Express interest to open availability; otherwise your introduction continues to minute 12.</p>' : rehearsalCopy}
    <div class="p-week-header">
      <span class="p-week-title">This week</span>
      <span class="p-now-pill">NOW · ${safe(String(data.clock?.day || '').toUpperCase())} ${String(data.clock?.hour ?? 0).padStart(2, '0')}:00</span>
    </div>

    <div class="p-day-strip">${grid.days.map((d, i) => {
      const dateNum = dateOfMonth(data.clock?.week, d.day);
      const dots = (byDay[d.day] || []).slice(0, 4);
      return `<button type="button" class="p-day-btn ${i === selectedIdx ? 'is-selected' : (d.is_today ? 'is-today' : '')}" data-day="${i}">
        <span class="p-day-letter">${safe(d.day[0])}</span>
        <span class="p-day-date">${dateNum != null ? safe(dateNum) : safe(d.day)}</span>
        <span class="p-day-dots">${dots.map((m) => `<span class="p-day-dot" style="background:${CATEGORY_COLOR[m.tone] || CATEGORY_COLOR.muted}"></span>`).join('')}</span>
      </button>`;
    }).join('')}</div>

    <div class="p-day-label-row">
      <span class="p-day-label">${safe(DAY_FULL_NAMES[selected.day] || selected.day)}${selected.is_today ? ' · today' : ''}</span>
      ${!selected.is_today ? '<button type="button" class="p-text-link" id="p-today-jump">Today</button>' : ''}
    </div>
    <div class="p-event-list">${events.length ? events.map((m) => eventCard(m, selected.day, matchBySlot, ctx)).join('') : '<p class="hint">Nothing scheduled this day.</p>'}</div>

    <details class="tw-video" ${videoOpen ? 'open' : ''}><summary>How the week works (short video)</summary>
      <div class="tw-video-body" data-video-body>${videoOpen ? videoPlayerHtml(CALENDAR_VIDEO, safe) : ''}</div></details>`;
}

function eventCard(m, day, matchBySlot, ctx) {
  const { safe } = ctx;
  const key = `${day}:${m.key || m.label}`;
  const open = expandedKey === key;
  const slot = MATCH_KEY_TO_SLOT[m.key];
  const match = slot ? matchBySlot[slot] : null;
  const navHere = m.key === 'calendar_closes' && !ctx.data.date_plan
    ? {surface:'calendar', label:'Confirm Date'} : NAV_FOR_MOMENT[m.key];
  const navEligible = navHere && ctx.journey?.surfaces?.find((s) => s.key === navHere.surface)?.eligible
    && (navHere.surface !== 'calendar' || confirmDateAvailable(ctx));
  const hasDetail = !!(m.means || (match && match.status !== 'not_yet_revealed') || navEligible);

  const row = `<div class="p-event-row">
      <span class="p-event-dot" style="background:${CATEGORY_COLOR[m.tone] || CATEGORY_COLOR.muted}"></span>
      <span class="p-event-title">${safe(m.full_label || m.label)}</span>
      ${ctx.data.activity_status?.[m.key] ? `<span class="activity-complete">✓ ${safe(ctx.data.activity_status[m.key])}</span>` : ''}
      <span class="p-event-time">${String(m.hour).padStart(2, '0')}:00</span>
    </div>`;
  const detail = open ? `<div class="p-event-detail">
      ${m.means ? `<p class="hint" style="margin:0 0 10px;">${safe(m.means)}</p>` : ''}
      ${match && match.status !== 'not_yet_revealed' ? matchSlot(match, safe, ctx.journey?.async_rehearsal?.enabled, ctx.folds?.chemistry?.data?.activities) : ''}
      ${navEligible ? `<button type="button" class="p-outline-cta" data-week-nav="${safe(navHere.surface)}">${safe(navHere.label)} <span aria-hidden="true">→</span></button>` : ''}
    </div>` : '';

  return hasDetail
    ? `<div class="p-event-card" data-tone="${safe(m.tone)}"><button type="button" class="p-event-toggle" data-event="${safe(key)}" aria-expanded="${open}">${row}</button>${detail}</div>`
    : `<div class="p-event-card" data-tone="${safe(m.tone)}" style="cursor:default;">${row}</div>`;
}

function matchSlot(m, safe, rehearsal = false, myActivities = {}) {
  if (m.status === 'acted') return `<p class="hint" style="margin:0;">${m.candidate ? safe(m.candidate.display_name) + ' — ' : ''}You said: ${safe(m.action)}</p>`;
  if (m.status === 'no_response') return '<p class="hint" style="margin:0;">Window closed with no response.</p>';
  if (m.status === 'closed') return '<p class="hint" style="margin:0;">This window has closed.</p>';
  const c = m.candidate;
  return `<div class="candidate-card" data-match="${safe(m.id)}" style="margin-top:0;">
    <div class="muted">${rehearsal ? 'Stays open during this test journey' : `Window closes ${safe(m.window_closes_at)}`}</div>
    ${c ? `<div class="candidate-name">${safe(c.display_name)}</div><div class="muted">${safe(c.city)}${c.bgv_status ? ' · ' + safe(c.bgv_status) : ''}</div>
    ${c.photo ? `<img class="profile-portrait" src="${safe(c.photo)}" alt="Profile portrait">` : ''}
    <div class="match-panels">
    <details><summary>Vision</summary><p>${safe(c.vision_template||'Individual Vision')}</p>
    <div class="chips">${(c.visions || []).map(v=>`<span>${safe(v.key)} · ${safe(Array.isArray(v.stance)?v.stance.join(', '):v.stance||'')}</span>`).join('')}</div>
    <p>Future children: ${safe(({want:'Want children',no:'Do not want additional children',open:'Open to children',undecided:'Undecided'})[c.kids_intent]||'Undecided')}</p></details>
    <details><summary>Stats</summary><div class="stat-grid">${Object.entries(c.stats || {}).filter(([,v])=>v!=null).map(([k,v])=>`<div>${safe(k.replaceAll('_',' '))}: ${safe(v)} <small>${c.verified_fields?.includes(k)?'✓ Verified':'Self-declared'}</small></div>`).join('')}</div>
    <p>Ethnicity: ${safe((c.ethnicity||[]).join(', ')||'Not shared')} · self-declared</p>
    ${c.health?.consent ? `<h3>Shared health &amp; accessibility</h3><p>${safe((c.health.categories||[]).map(k=>c.health_labels?.[k]||k).join(', '))}</p><p>${safe(c.health.note||'')}</p><p class="hint">Self-declared; not medically verified.</p>` : '<p class="hint">Health/accessibility not shared. This does not indicate absence of a condition.</p>'}</details>
    <details><summary>Chemistry</summary><p>Shared interests: ${safe(Object.entries(c.activities||{}).filter(([k,v])=>['good','improve'].includes(v)&&['good','improve'].includes(myActivities[k])).map(([k])=>k).join(', ')||'None recorded yet')}</p>${Object.entries(c.activities||{}).filter(([,v])=>v!=='no').map(([k,v])=>`<p>${safe(k)} · ${safe(({good:'Enjoys / skilled',improve:'Developing',maybe:'Open to trying'})[v]||v)}</p>`).join('')||'<p>Interests not shared yet.</p>'}
    <details><summary>Not for me</summary>${Object.entries(c.activities||{}).filter(([,v])=>v==='no').map(([k])=>`<p>${safe(k)}</p>`).join('')||'<p>None shared.</p>'}</details></details></div>` : ''}
    ${m.their_interest ? '<p class="hint">They already expressed interest in you — expressing interest back will match you.</p>' : ''}
    ${m.allowed_actions?.includes('pass') ? '<textarea class="pass-reason" placeholder="Optional — why you\'re passing" maxlength="1000"></textarea>' : ''}
    <div class="action-row">
      ${m.allowed_actions?.includes('pass') ? `<button class="secondary act" data-match="${safe(m.id)}" data-action="pass" type="button">Pass</button>` : ''}
      ${m.allowed_actions?.includes('interest') ? `<button class="primary act" data-match="${safe(m.id)}" data-action="interest" type="button">Express interest</button>` : ''}
    </div>
  </div>`;
}

// round4-fixes-spec.md §7: the calendar explainer video. Never autoplays
// (no `autoplay`, `preload="metadata"` so opening it fetches at most the
// header), plays inline rather than forcing full screen on iOS. The source
// comes from config.js; until the file exists, the element's `error` event
// (bind() below) swaps it for a placeholder.
export function videoPlayerHtml(video, safe) {
  return `<video class="tw-video-player" controls preload="metadata" playsinline src="${safe(video.src)}"${video.poster ? ` poster="${safe(video.poster)}"` : ''}>
    <p class="hint">Your device can't play this video.</p></video>`;
}
const VIDEO_PLACEHOLDER = '<p class="hint tw-video-placeholder">The explainer video is on its way — it is not available yet.</p>';

export function bind(root, ctx) {
  const { session, run, patch, navigateTo, refreshJourney, journey } = ctx;

  root.querySelectorAll('.p-day-btn').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    selectedDay = Number(btn.dataset.day);
  })));
  // Always the real "today", never the openMatchDayIdx smart default —
  // a "Today" action that didn't land on today would defeat its own point.
  root.querySelector('#p-today-jump')?.addEventListener('click', () => run(async () => {
    const idx = ctx.data?.schedule?.grid?.days?.findIndex((d) => d.is_today);
    selectedDay = idx != null && idx >= 0 ? idx : null;
  }));
  root.querySelectorAll('[data-event]').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    expandedKey = expandedKey === btn.dataset.event ? null : btn.dataset.event;
  })));
  root.querySelectorAll('[data-week-nav]').forEach((btn) => btn.addEventListener('click', () => navigateTo(btn.dataset.weekNav)));

  const videoBody = root.querySelector('[data-video-body]');
  const watchForMissingFile = () => {
    const player = videoBody?.querySelector('video');
    player?.addEventListener('error', () => { videoBody.innerHTML = VIDEO_PLACEHOLDER; }, { once: true });
  };
  watchForMissingFile();
  root.querySelector('details.tw-video')?.addEventListener('toggle', (e) => {
    videoOpen = e.target.open;
    if (!videoBody) return;
    if (videoOpen && !videoBody.querySelector('video, .tw-video-placeholder')) { videoBody.innerHTML = videoPlayerHtml(CALENDAR_VIDEO, ctx.safe); watchForMissingFile(); }
    else if (!videoOpen) { videoBody.querySelector('video')?.pause(); videoBody.innerHTML = ''; }
  });

  root.querySelector('#to-calendar')?.addEventListener('click', () => navigateTo('calendar'));
  root.querySelectorAll('.demo-step').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    await session.post('/api/v1/simulated-clock', { advance_hours: Number(btn.dataset.advance) });
    // The clock moving can change everything about this screen — reveal
    // timing, phase, prepared state — so reload both the week and the
    // shared journey/status rather than patching a field by hand.
    patch(await ensurePrepared(session, await session.get('/api/v1/week')));
    await refreshJourney();
  })));
  root.querySelectorAll('.act').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    const matchId = btn.dataset.match;
    const action = btn.dataset.action;
    const card = btn.closest('[data-match]');
    const reason = action === 'pass' ? card.querySelector('.pass-reason')?.value.trim() || null : undefined;
    const body = action === 'pass' ? { action, pass_reason: reason } : { action };
    // `replayed:true` on the response means this exact decision was already
    // recorded (§3 idempotency) — either way the reload below shows the
    // real current state, so there's nothing further to special-case here.
    await session.post(`/api/v1/matches/${encodeURIComponent(matchId)}/actions`, body);
    // The action endpoint returns only the decision, not the whole week —
    // reload the week (and journey/status, for lock-in/tab changes) rather
    // than hand-patch a single slot, since mutual interest can restructure
    // the entire list (§2.3: lock-in clears every other candidate).
    patch(await session.get('/api/v1/week'));
    await refreshJourney();
  })));
}
