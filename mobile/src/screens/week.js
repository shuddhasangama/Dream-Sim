// Week & Match (§2.2) and Lock-in (§2.3). One screen, branching on the
// server's own `mode` — dating/locked_in/post_dating — exactly like the
// original web app's week.html did; the client never infers which of the
// three it's in from anything but that field.
//
// §2.2's atomicity rule: GET is read-only. week/prepare only ever runs from
// an explicit tap on the button below, never automatically on load or
// re-render, so a repeated GET (e.g. from going back and forth) can never
// duplicate a transition.
//
// Lock-in has no partner-picking endpoint by design (§2.3) — this screen
// only ever expresses interest/pass on a slot the server already revealed.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Week</h1></section><section class="card"><p>Loading…</p></section>';
  if (data.mode === 'post_dating') return postDating(data, safe);
  if (data.mode === 'locked_in') return lockedIn(ctx);
  return dating(ctx);
}

function postDating(data) {
  return `<section class="intro"><span class="eyebrow">WEEK</span><h1>Past the searching phase</h1></section>
    <section class="card guidance"><p>REACH and the weekly matches have sunset for you — Guru and Journey are where things continue from here.</p></section>`;
}

function lockedIn(ctx) {
  const { data, safe } = ctx;
  const li = data.lock_in;
  return `<section class="intro"><span class="eyebrow">WEEK · LOCKED IN</span><h1>You're locked in</h1></section>
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
      <section class="card"><p>Set up this week's matches to see who's revealed.</p>
      <button id="prepare" class="primary" type="button">Prepare this week <span aria-hidden="true">→</span></button></section>`;
  }
  const slots = data.matches || [];
  return `<section class="intro"><span class="eyebrow">WEEK ${safe(data.clock?.week)} · ${safe(data.clock?.day)} ${String(data.clock?.hour ?? 0).padStart(2, '0')}:00</span><h1>This week's matches</h1></section>
    ${slots.length ? slots.map((m) => matchSlot(m, safe)).join('') : '<section class="card"><p>No matches this week — an honest zero, not a filter problem to fix.</p></section>'}
    ${scheduleGrid(data.schedule, safe)}`;
}

function matchSlot(m, safe) {
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
    <div class="muted">Match ${m.slot} · window closes ${safe(m.window_closes_at)}</div>
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

function scheduleGrid(schedule, safe) {
  if (!schedule?.grid?.rows?.length) return '';
  return `<h2>This week</h2><div class="week-grid">${schedule.grid.rows.map((row) => `
    <div class="week-day">${safe(row.label)}</div>
    <div>${row.days.flatMap((d) => d.moments || []).map((mo) => `<span class="moment tone-${safe(mo.tone)}">${safe(mo.day)} ${safe(mo.time || mo.hour)} · ${safe(mo.label)}</span>`).join('')}</div>
  `).join('')}</div>`;
}

export function bind(root, ctx) {
  const { session, run, patch, navigateTo, refreshJourney } = ctx;
  root.querySelector('#prepare')?.addEventListener('click', () => run(async () => {
    patch(await session.post('/api/v1/week/prepare', {}));
  }));
  root.querySelector('#to-calendar')?.addEventListener('click', () => navigateTo('calendar'));
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
