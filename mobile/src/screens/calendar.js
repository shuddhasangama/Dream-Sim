// Date calendar (§2.4). Structured {day, meal_slot} objects throughout, per
// the spec's explicit instruction — never the old web app's "day|meal" form
// string. Every option list (valid_slots, alignment.options.*) comes from
// PlanningCalendar itself, never hardcoded here.

const MEAL_LABELS = { breakfast: 'Breakfast', lunch: 'Lunch', coffee: 'Coffee', dinner: 'Dinner' };

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Calendar</h1></section><section class="card"><p>Loading…</p></section>';
  const { alignment, overlap = [], valid_slots = [], my_slots = [], payment } = data;
  const mySet = new Set(my_slots.map((s) => `${s.day}|${s.meal_slot}`));

  return `<section class="intro"><span class="eyebrow">CALENDAR</span><h1>When to meet</h1></section>

    <section class="card">
      <h2>Budget, diet &amp; cuisine</h2>
      ${alignment.my_missing.length ? `<p class="warn">Still needed: ${alignment.my_missing.map(safe).join(', ')}</p>` : ''}
      ${alignment.partner_missing.length ? `<p class="hint">Waiting on your match for: ${alignment.partner_missing.map(safe).join(', ')}</p>` : ''}
      <form id="alignment-form">
        <div class="field"><label>Diet</label>
          <select name="diet">${alignment.options.diet.map((d) => `<option value="${safe(d)}" ${d === alignment.mine.diet ? 'selected' : ''}>${safe(d)}</option>`).join('')}</select>
        </div>
        <div class="field"><label>Budget</label><div class="chips">${alignment.options.budget.map((b) => `<label class="checkbox-row"><input type="checkbox" name="budget" value="${safe(b)}" ${asArray(alignment.mine.budget).includes(b) ? 'checked' : ''}> ${safe(b)}</label>`).join('')}</div></div>
        <div class="field"><label>Cuisine</label><div class="chips">${alignment.options.cuisine.map((c) => `<label class="checkbox-row"><input type="checkbox" name="cuisine" value="${safe(c)}" ${asArray(alignment.mine.cuisine).includes(c) ? 'checked' : ''}> ${safe(c)}</label>`).join('')}</div></div>
        <button class="secondary" type="submit">Save</button>
      </form>
    </section>

    <section class="card">
      <h2>Your availability</h2>
      <p class="hint">${data.partner_submitted ? 'Your match has submitted theirs too.' : "Waiting on your match to submit theirs."}</p>
      <form id="availability-form">
        ${valid_slots.map((s) => `<label class="checkbox-row"><input type="checkbox" name="slot" value="${safe(s.day)}|${safe(s.meal_slot)}" ${mySet.has(`${s.day}|${s.meal_slot}`) ? 'checked' : ''}> ${safe(s.day)} · ${safe(MEAL_LABELS[s.meal_slot] || s.meal_slot)}</label>`).join('')}
        <button class="secondary" type="submit">Save availability</button>
      </form>
    </section>

    ${data.current_plan_id ? `<section class="card guidance"><p>A time is already set.</p><button id="view-plan" class="primary" type="button">View date plan <span aria-hidden="true">→</span></button></section>`
      : data.editable && overlap.length ? `<section class="card"><h2>You're both free</h2>${overlap.map((s) => `<div class="slot"><span>${safe(s.day)} · ${safe(MEAL_LABELS[s.meal_slot] || s.meal_slot)}</span><button class="primary confirm-slot" data-day="${safe(s.day)}" data-meal="${safe(s.meal_slot)}" type="button" style="width:auto;margin:0;">Confirm</button></div>`).join('')}</section>`
      : `<section class="card"><p class="hint">No overlap yet — once you've both submitted availability, matching times show up here.</p></section>`}
    ${payment && payment.enforced && !payment.satisfied ? `<p class="warn">This is a beta simulation — no real payment is charged.</p>` : ''}`;
}

function asArray(v) { return Array.isArray(v) ? v : v ? [v] : []; }

export function bind(root, ctx) {
  const { session, run, patch, navigateTo } = ctx;
  const lockInId = encodeURIComponent(ctx.data.lock_in_id);

  root.querySelector('#alignment-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const body = {
        diet: form.get('diet'),
        budget: form.getAll('budget'),
        cuisine: form.getAll('cuisine'),
      };
      patch(await session.put(`/api/v1/lock-ins/${lockInId}/alignment`, body));
    });
  });

  root.querySelector('#availability-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      const slots = form.getAll('slot').map((v) => { const [day, meal_slot] = v.split('|'); return { day, meal_slot }; });
      patch(await session.put(`/api/v1/lock-ins/${lockInId}/availability`, { slots }));
    });
  });

  root.querySelectorAll('.confirm-slot').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    await session.post(`/api/v1/lock-ins/${lockInId}/date-plan`, { day: btn.dataset.day, meal_slot: btn.dataset.meal, cycle: ctx.data.cycle });
    patch(await session.get(`/api/v1/lock-ins/${lockInId}/calendar`));
    await ctx.refreshJourney();
  })));

  root.querySelector('#view-plan')?.addEventListener('click', () => navigateTo('plan'));
}
