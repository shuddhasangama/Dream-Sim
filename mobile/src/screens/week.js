// Week & Match (§2.2) and Lock-in (§2.3). One screen, branching on the
// server's own `mode` — dating/locked_in/post_dating — exactly like the
// original web app's week.html did; the client never infers which of the
// three it's in from anything but that field.
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
  const { data, safe } = ctx;
  return `<section class="intro"><span class="eyebrow">WEEK</span><h1>Past the searching phase</h1></section>
    ${theWeek(ctx)}
    <section class="card guidance"><p>REACH and the weekly matches have sunset for you — Guru and Journey are where things continue from here.</p></section>`;
}

function lockedIn(ctx) {
  const { data, safe } = ctx;
  const li = data.lock_in;
  return `<section class="intro"><span class="eyebrow">WEEK · LOCKED IN</span><h1>You're locked in</h1></section>
    ${theWeek(ctx)}
    <section class="card">
      <div class="stat-row"><span>Status</span><strong>${safe(li?.status)}</strong></div>
      <div class="stat-row"><span>Since week</span><strong>${safe(li?.week)}</strong></div>
      <div class="stat-row"><span>Dates completed</span><strong>${safe(li?.dates_completed ?? 0)}</strong></div>
    </section>
    <section class="card guidance"><p>No one else can be matched to you while you're locked in — REACH is closed for now. Next is setting up when to meet.</p>
      <button id="to-calendar" class="primary" type="button">Open calendar <span aria-hidden="true">→</span></button></section>`;
}

function dating(ctx) {
  const { data, safe } = ctx;
  if (!data.prepared) {
    return `<section class="intro"><span class="eyebrow">WEEK ${safe(data.clock?.week)}</span><h1>This week hasn't started yet</h1></section>
      ${theWeek(ctx)}
      <section class="card"><p>Your matches for this week appear here as the week opens.</p></section>`;
  }
  const slots = data.matches || [];
  return `<section class="intro"><span class="eyebrow">WEEK ${safe(data.clock?.week)} · ${safe(data.clock?.day)} ${String(data.clock?.hour ?? 0).padStart(2, '0')}:00</span><h1>This week's matches</h1></section>
    ${theWeek(ctx)}
    ${slots.length ? slots.map((m) => matchSlot(m, safe, ctx.journey?.async_rehearsal?.enabled)).join('') : '<section class="card"><p>No matches this week — an honest zero, not a filter problem to fix.</p></section>'}`;
}

function matchSlot(m, safe, rehearsal=false) {
  if (m.status === 'not_yet_revealed') {
    return `<div class="card"><div class="muted">Match ${m.slot}</div><p>Reveals ${safe(m.revealed_at)}</p></div>`;
  }
  if (m.status === 'acted') {
    return `<div class="card"><div class="muted">Match ${m.slot}${m.candidate ? ' · ' + safe(m.candidate.display_name) : ''}</div><p>You said: ${safe(m.action)}</p></div>`;
  }
  if (m.status === 'no_response') {
    return `<div class="card"><div class="muted">Match ${m.slot}</div><p>Window closed with no response.</p></div>`;
  }
  if (m.status === 'closed') {
    return `<div class="card"><div class="muted">Match ${m.slot}</div><p>This window has closed.</p></div>`;
  }
  const c = m.candidate;
  const stats = c?.stats || {};
  return `<div class="candidate-card" data-match="${safe(m.id)}">
    <div class="muted">Match ${m.slot} · ${rehearsal ? 'stays open during this test journey' : `window closes ${safe(m.window_closes_at)}`}</div>
    ${c ? `<div class="candidate-name">${safe(c.display_name)}</div><div class="muted">${safe(c.city)}${c.bgv_status ? ' · ' + safe(c.bgv_status) : ''}</div>
    <div class="chips">${(c.visions || []).map((v) => `<span>${safe(v.key)}${v.stance ? ' · ' + safe(Array.isArray(v.stance) ? v.stance.join(', ') : v.stance) : ''}</span>`).join('')}</div>
    <div class="stat-grid">${Object.entries(stats).filter(([, v]) => v != null).map(([k, v]) => `<div>${safe(k.replace(/_/g, ' '))}: ${safe(v)}</div>`).join('')}</div>` : ''}
    ${m.their_interest ? '<p class="hint">They already expressed interest in you — expressing interest back will match you.</p>' : ''}
    ${m.allowed_actions?.includes('pass') ? '<textarea class="pass-reason" placeholder="Optional — why you\'re passing" maxlength="1000"></textarea>' : ''}
    <div class="action-row">
      ${m.allowed_actions?.includes('pass') ? `<button class="secondary act" data-match="${safe(m.id)}" data-action="pass" type="button">Pass</button>` : ''}
      ${m.allowed_actions?.includes('interest') ? `<button class="primary act" data-match="${safe(m.id)}" data-action="interest" type="button">Express interest</button>` : ''}
    </div>
  </div>`;
}

// "The week" (§3, spec item 8): the calendar grid from templates/
// _the_week.html, ported class-for-class (.tw-*) so it reads the same way
// on a phone as it does on the web. grid/legend come straight from the
// server's own week_map.py output (data.schedule); `explained` and
// `phase_copy` are pure derivations of data already on the wire —
// week_map.explained() is just "every moment with a `means`, day-sorted"
// (every moment in `grid` already carries its own `means`), and
// WEEK_PHASE_COPY below is week_map.py's own PHASE_COPY table, mirrored
// client-side the same way nav.js mirrors disclosure.py's labels — display
// text keyed by a server enum, not business logic of its own.
const WEEK_PHASE_COPY = {
  before_week_start: 'The week has not opened yet. Match 1 is revealed Monday midday.',
  match_1_open: 'Match 1 is live. You have until Tuesday midday.',
  match_2_open: 'Match 2 is live. You have until Wednesday midday.',
  match_3_open: "Match 3 is live — the last of this week. It closes Wednesday evening.",
  calendar_open: 'The calendar is open. Offer your weekend slots before Thursday midday.',
  calendar_closed: 'Slots are in. The overlap publishes Thursday evening, with the agreement to sign.',
  dates_live: 'Dates are live this weekend.',
  feedback_open: 'Feedback is open. It closes the week and shapes the next one.',
};

// round4-fixes-spec.md §7: the calendar explainer video. Never autoplays
// (no `autoplay`, `preload="metadata"` so opening it fetches at most the
// header), plays inline rather than forcing full screen on iOS, and lives in
// its own collapsible section, so it can never sit in front of the calendar.
// The source comes from config.js; until the file exists, the element's
// `error` event (bind() below) swaps it for a placeholder.
let videoOpen = false;

export function videoPlayerHtml(video, safe) {
  return `<video class="tw-video-player" controls preload="metadata" playsinline src="${safe(video.src)}"${video.poster ? ` poster="${safe(video.poster)}"` : ''}>
    <p class="hint">Your device can't play this video.</p></video>`;
}
const VIDEO_PLACEHOLDER = '<p class="hint tw-video-placeholder">The explainer video is on its way — it is not available yet.</p>';

function explainedMoments(grid) {
  const dayIndex = (d) => grid.days.findIndex((x) => x.day === d);
  const out = [];
  grid.rows.forEach((row) => row.days.forEach((d) => (d.moments || []).forEach((m) => { if (m.means) out.push(m); })));
  return out.sort((a, b) => (dayIndex(a.day) - dayIndex(b.day)) || (a.hour - b.hour));
}

function theWeek(ctx) {
  const { data, safe, journey, simulatedClockBuild } = ctx;
  const schedule = data.schedule;
  if (!schedule?.grid) return '';
  const { grid, legend = [] } = schedule;
  const nowText = data.clock ? `${safe(data.clock.day)} ${String(data.clock.hour ?? 0).padStart(2, '0')}:00` : '';
  const phaseCopy = journey?.async_rehearsal?.enabled ? 'Reference weekly timetable. This test journey advances through partner actions, not these deadlines.' : WEEK_PHASE_COPY[data.phase] || '';
  const explained = explainedMoments(grid);
  // §7.6/§7.8: the server's own simulated_clock is the primary gate —
  // never inferred from the build flag alone. The build flag is only ever
  // an ADDITIONAL restriction (both must be true), never a replacement.
  const simClock = journey?.simulated_clock && simulatedClockBuild && !journey?.accelerated_test?.enabled && !journey?.async_rehearsal?.enabled ? `<div class="demo-bar">
      <span class="demo-tag">SIMULATION</span>
      <span class="demo-clock">${safe(data.clock?.day)} ${String(data.clock?.hour ?? 0).padStart(2, '0')}:00 · Week ${safe(data.clock?.week)}</span>
      <div class="demo-steps">
        <button class="demo-step" type="button" data-advance="1">+1 hour</button>
        <button class="demo-step" type="button" data-advance="24">+1 day</button>
        <button class="demo-step" type="button" data-advance="168">+1 week</button>
      </div>
    </div>` : '';
  return `${simClock}<section class="card the-week">
    <div class="tw-head"><div class="section-label" style="margin:0;">The week</div><div class="tw-now">${nowText}</div></div>
    ${phaseCopy ? `<div class="hint tw-phase">${safe(phaseCopy)}</div>` : ''}
    <div class="tw-scroll">
      <table class="tw-grid">
        <caption class="visually-hidden">What happens on each day of the dating week</caption>
        <thead><tr><th scope="col"><span class="visually-hidden">Time of day</span></th>
          ${grid.days.map((d) => `<th scope="col" class="tw-day${d.is_today ? ' is-today' : ''}" title="${safe(d.day)}">${safe(d.day[0])}</th>`).join('')}
        </tr></thead>
        <tbody>
          ${grid.rows.map((row) => `<tr class="tw-band">
            <th scope="row" class="tw-band-label">${safe(row.label)}</th>
            ${row.days.map((cell) => `<td class="tw-cell${cell.is_today ? ' is-today' : ''}">
              ${(cell.moments || []).map((m) => `<span class="tw-chip tone-${safe(m.tone)}${m.past ? ' is-past' : ''}${m.personal ? ' is-personal' : ''}" title="${safe(m.full_label || m.label)} · ${safe(m.day)} ${safe(m.time || '')}${m.means ? ' — ' + safe(m.means) : ''}">${safe(m.label)}${m.personal ? '<span class="tw-personal-dot" aria-hidden="true"></span>' : ''}</span>`).join('')}
            </td>`).join('')}
          </tr>${row.key === grid.midday_after ? `<tr class="tw-midday" aria-hidden="true"><td colspan="${grid.days.length + 1}"><span>${safe(grid.midday_label)}</span></td></tr>` : ''}`).join('')}
        </tbody>
      </table>
    </div>
    <div class="tw-legend">${legend.map((e) => `<span class="tw-legend-item"><span class="tw-swatch tone-${safe(e.tone)}"></span>${safe(e.kind)}</span>`).join('')}</div>
    <details class="tw-video" ${videoOpen ? 'open' : ''}><summary>How the week works (short video)</summary>
      <div class="tw-video-body">${videoOpen ? videoPlayerHtml(CALENDAR_VIDEO, safe) : ''}</div></details>
    ${explained.length ? `<details class="tw-explain"><summary>What each one means</summary><dl>
      ${explained.map((m) => `<div class="tw-explain-row"><dt><span class="tw-chip tone-${safe(m.tone)}">${safe(m.label)}</span> ${m.full_label ? `<span class="tw-full">${safe(m.full_label)}</span> ` : ''}<span class="tw-when">${safe(m.day)} ${String(m.hour).padStart(2, '0')}:00</span></dt><dd>${safe(m.means)}</dd></div>`).join('')}
    </dl></details>` : ''}
  </section>`;
}

export function bind(root, ctx) {
  const { session, run, patch, navigateTo, refreshJourney } = ctx;

  // The player is mounted only when its section is opened (no request before
  // then) and unmounted on close. No re-render is needed for either, so
  // opening it never disturbs the calendar underneath.
  const videoBody = root.querySelector('.tw-video-body');
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
