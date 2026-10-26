import { pairContext } from './pairContext.js';
import { restaurantPanel, bindRestaurant } from './restaurant.js';
// Date plan (§2.4). Reached generically via journey/status's own "plan"
// surface — once a date exists, journey_api.py already routes it here, so
// no custom loader is needed, unlike ceremony.js.

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Date plan</h1></section><section class="card"><p>Loading…</p></section>';
  return `<section class="intro"><span class="eyebrow">DATE PLAN</span><h1>${safe((ctx.journey?.current_date_plan?.id === data.id && ctx.journey.current_date_plan.display_status === 'completed_awaiting_agreement') || data.status === 'completed' ? 'Date completed' : data.status === 'cancelled' ? 'Date cancelled' : data.readiness?.label || (data.status === 'confirmed' ? 'Confirmed' : 'Pending signatures'))}</h1></section>
    ${pairContext(ctx)}
    ${restaurantPanel(data.restaurant, safe)}
    ${data.booking ? `<section class="card"><h2>Agreed date preferences</h2><p>${data.booking.neighbourhoods.map(p => safe(p.name)).join(', ')}</p><p>${data.booking.cuisines.map(safe).join(', ')} · ${data.booking.budget_bands.map(safe).join(', ')} per person</p><p class="hint">Restaurant booking is pending. No table has been reserved.</p></section>` : ''}
    <section class="card">
      <div class="stat-row"><span>When</span><strong>${safe(data.datetime)}</strong></div>
      <div class="stat-row"><span>Meal</span><strong>${safe(data.meal)}</strong></div>
      ${data.venue ? `<div class="stat-row"><span>Venue</span><strong>${safe(data.venue)}</strong></div>` : ''}
      ${data.cuisine ? `<div class="stat-row"><span>Cuisine</span><strong>${safe(data.cuisine)}</strong></div>` : ''}
      ${data.budget_estimate ? `<div class="stat-row"><span>Budget</span><strong>${safe(data.budget_estimate)}</strong></div>` : ''}
      <div class="stat-row"><span>Bill split</span><strong>${safe(data.bill_split)}</strong></div>
    </section>
    <section class="card guidance">
      <div class="stat-row"><span>You signed</span><strong>${data.my_signed ? 'Yes' : 'Not yet'}</strong></div>
      <div class="stat-row"><span>Your match signed</span><strong>${data.partner_signed ? 'Yes' : 'Not yet'}</strong></div>
      ${data.face_simulation_available ? `<p class="hint">Face verification runs as a beta simulation — never a live biometric check.</p>` : ''}
      <button id="to-ceremony" class="primary" type="button">${data.my_signed ? 'Review signed playbook' : 'Read and sign'} <span aria-hidden="true">→</span></button>
    </section>`;
}

export function bind(root, ctx) {
  bindRestaurant(root, ctx);
  const { navigateTo } = ctx;
  root.querySelector('#to-ceremony')?.addEventListener('click', () => navigateTo('ceremony', { planId: ctx.data.id }));
}
