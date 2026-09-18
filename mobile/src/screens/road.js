// ROAD (road-fixes-clock-spec.md §1, relationship-stage-spec.md §D2): set
// once at Relationship entry, carried forward — not a weekly form, and
// re-runnable if the couple chooses rather than gated behind a wizard.
// Reached from relationship.js with a couple id (no journey/status
// surface of its own, same pattern as ceremony.js), backed entirely by
// /api/v1/couples/{cid}/road's own GET/routine/obligations/sharing.
//
// This renders ONLY the ROAD slice of the couple-summary payload — never
// the playbook/differences/checkpoints/exits that live at the couple
// endpoint itself; that's its own build, flagged and left alone.
//
// Two fixed vocabularies aren't in the GET response (road_service.py's own
// validation constants, not exposed as options anywhere the JSON API
// returns) but are the spec's own stable prose, not personalised data —
// same class as nav.js's day names: DAYS (Mon..Sun), routine categories
// (work/fitness — "free" is added a different way, see below), and
// D2's own three travel modes (solo/partner_solo/together).
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const TRAVEL_MODES = [
  ['solo', 'Solo — private'],
  ['partner_solo', "Partner's own — visible only if shared"],
  ['together', 'Together'],
];

export async function load(session, params) {
  return session.get(`/api/v1/couples/${encodeURIComponent(params.coupleId)}/road`);
}

function slotKey(s) { return `${s.day}|${s.start}|${s.end}`; }

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>ROAD</h1></section><section class="card"><p>Loading…</p></section>';
  const { my_routine = [], my_obligations = [], partner_shared_obligations = [], my_availability = {}, my_shared_slots = [], partner_shared_slots = [], overlap = [] } = data;
  const sharedKeys = new Set(my_shared_slots.map(slotKey));

  return `<section class="intro"><span class="eyebrow">ROAD</span><h1>Routine, obligations, availability, dates</h1>
    <p class="lede">Set once here and carried forward into Engaged and Married — not a weekly form. Come back and change any of it whenever you both want to; nothing below is forced.</p></section>

    <section class="card"><h2>Routine</h2>
    <div class="hint">Work and fitness, together — the backdrop Availability is derived from.</div>
    ${my_routine.map((b) => `<div class="stat-row" data-routine="${safe(b.id)}"><span>${safe(b.label)} <span class="micro">${safe(b.category)}</span></span><span>${safe(b.days.join(', '))} · ${safe(b.start)}–${safe(b.end)} <button class="text-button remove-routine" data-id="${safe(b.id)}" type="button">Remove</button></span></div>`).join('') || '<p class="hint">Nothing on file yet.</p>'}
    <form id="routine-form" style="margin-top:12px;">
      <div class="row">
        <label class="checkbox-row"><input type="radio" name="category" value="work" checked> Work</label>
        <label class="checkbox-row"><input type="radio" name="category" value="fitness"> Fitness</label>
      </div>
      <div class="row">${DAYS.map((d) => `<label class="checkbox-row"><input type="checkbox" name="days" value="${d}"> ${d}</label>`).join('')}</div>
      <div class="field"><input type="text" name="label" placeholder="e.g. Office, Gym, Salsa" required></div>
      <div class="row"><input type="time" name="start" required><input type="time" name="end" required></div>
      <button class="secondary" type="submit">Add routine block</button>
    </form></section>

    <section class="card"><h2>Obligations</h2>
    <div class="hint">Travel, visiting family, anything one-time that overrides the routine.</div>
    ${my_obligations.map((o) => `<div class="stat-row" data-obligation="${safe(o.id)}"><span>${safe(o.title)} <span class="micro">${safe(o.type)}${o.travel_mode ? ' · ' + safe(o.travel_mode.replace('_', ' ')) : ''}${o.shared ? ' · shared' : ''}</span></span><span>${safe(o.starts_at)} → ${safe(o.ends_at)} <button class="text-button remove-obligation" data-id="${safe(o.id)}" type="button">Remove</button></span></div>`).join('') || '<p class="hint">None on file.</p>'}
    ${partner_shared_obligations.length ? `<div class="section-label">Shared with you</div>${partner_shared_obligations.map((o) => `<div class="stat-row"><span>${safe(o.title)} <span class="micro">${safe(o.type)}${o.travel_mode ? ' · ' + safe(o.travel_mode.replace('_', ' ')) : ''}</span></span><span>${safe(o.starts_at)} → ${safe(o.ends_at)}</span></div>`).join('')}` : ''}
    <form id="obligation-form" style="margin-top:12px;">
      <div class="field"><select name="type" id="obligation-type"><option value="obligation">Obligation</option><option value="travel">Travel</option></select></div>
      <div class="field"><input type="text" name="title" placeholder="e.g. Diwali trip to Goa, Visit parents" required></div>
      <div class="row"><input type="date" name="start_date" required><input type="date" name="end_date" required></div>
      <div class="field" id="travel-mode-field" hidden><select name="travel_mode">${TRAVEL_MODES.map(([v, l]) => `<option value="${v}">${safe(l)}</option>`).join('')}</select></div>
      <label class="checkbox-row"><input type="checkbox" name="shared"> Visible to your partner</label>
      <button class="secondary" type="submit">Add obligation</button>
    </form></section>

    <section class="card"><h2>Availability &amp; dates</h2>
    <div class="hint">Derived from your routine's gaps — private until you check a window below and share it. ${data.obligation_rule ? safe(data.obligation_rule) : ''}</div>
    ${overlap.length ? `<div class="section-label">When you could both go out</div><div class="row">${overlap.map((s) => `<span class="chip">${safe(s.day)} ${safe(s.start)}–${safe(s.end)}</span>`).join('')}</div>`
      : my_shared_slots.length ? '<p class="hint">No overlap yet — your match hasn\'t shared a window that lines up with yours.</p>' : ''}
    <form id="sharing-form" style="margin-top:12px;">
      <div class="section-label">Your available windows</div>
      ${DAYS.map((d) => (my_availability[d] || []).map((s) => `<label class="checkbox-row"><input type="checkbox" name="slot" value="${safe(slotKey(s))}" ${sharedKeys.has(slotKey(s)) ? 'checked' : ''}> ${d} ${safe(s.start)}–${safe(s.end)}</label>`).join('')).join('') || '<p class="hint">Nothing yet — add routine or free time below.</p>'}
      <button class="secondary" type="submit">Share checked windows</button>
    </form>
    <form id="free-time-form" style="margin-top:12px;">
      <div class="section-label">Add free time directly — no routine needed</div>
      <div class="row">${DAYS.map((d) => `<label class="checkbox-row"><input type="checkbox" name="days" value="${d}"> ${d}</label>`).join('')}</div>
      <div class="row"><input type="time" name="start" required><input type="time" name="end" required></div>
      <button class="secondary" type="submit">Add free time</button>
    </form></section>`;
}

export function bind(root, ctx) {
  const { session, run, patch, params } = ctx;
  const base = `/api/v1/couples/${encodeURIComponent(params.coupleId)}`;

  root.querySelector('#obligation-type')?.addEventListener('change', (e) => {
    root.querySelector('#travel-mode-field').hidden = e.target.value !== 'travel';
  });

  root.querySelector('#routine-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      patch(await session.post(`${base}/road/routine`, {
        request_id: crypto.randomUUID(), category: form.get('category'), days: form.getAll('days'),
        label: form.get('label').trim(), start: form.get('start'), end: form.get('end'),
      }));
    });
  });
  root.querySelectorAll('.remove-routine').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    patch(await session.delete(`${base}/road/routine/${encodeURIComponent(btn.dataset.id)}`));
  })));

  root.querySelector('#obligation-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const type = form.get('type');
      patch(await session.post(`${base}/road/obligations`, {
        request_id: crypto.randomUUID(), type, title: form.get('title').trim(),
        start_date: form.get('start_date'), end_date: form.get('end_date'),
        travel_mode: type === 'travel' ? form.get('travel_mode') : undefined,
        // Never defaulted — the person must tick this themselves (§1.5).
        shared: form.has('shared'),
      }));
    });
  });
  root.querySelectorAll('.remove-obligation').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    patch(await session.delete(`${base}/road/obligations/${encodeURIComponent(btn.dataset.id)}`));
  })));

  root.querySelector('#sharing-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const slots = new FormData(e.target).getAll('slot').map((v) => { const [day, start, end] = v.split('|'); return { day, start, end }; });
      patch(await session.put(`${base}/road/sharing`, { slots }));
    });
  });

  root.querySelector('#free-time-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      patch(await session.post(`${base}/road/routine`, {
        request_id: crypto.randomUUID(), category: 'free', days: form.getAll('days'),
        label: 'Free time', start: form.get('start'), end: form.get('end'),
      }));
    });
  });
}
