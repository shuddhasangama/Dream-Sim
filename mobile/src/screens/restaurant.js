// Simulation-only restaurant selection. All prices and states come from server.
export function restaurantPanel(r, safe) {
  if (!r) return '';
  const money = (amount, currency, exponent = 2) => safe(new Intl.NumberFormat(undefined, { style:'currency', currency }).format(amount / (10 ** exponent)));
  const action = (key, text) => `<button type="button" class="secondary restaurant-action" data-action="${key}">${text}</button>`;
  const searchable = ['not_started','empty','expired','changed','unavailable','cancelled','budget_limit_required'].includes(r.state) && r.refund !== 'failed' && r.date_open;
  return `<section class="card"><h2>Restaurant options</h2><p class="hint">Simulation · No real reservation or payment.</p><p role="status">${safe(r.message)}</p>
    ${r.selection_policy ? `<p class="hint">Compared by ${safe({lowest_total:'estimated total cost',lowest_upfront:'upfront payment',nearest:'distance'}[r.selection_policy] || r.selection_policy)}. Food prices are estimates. Tax and service-charge inclusion is unconfirmed.</p>` : ''}
    ${r.provider_failures && Object.keys(r.provider_failures).length ? '<p class="hint">Some providers were unavailable. Showing results from those that responded.</p>' : ''}
    ${searchable && r.needs_budget_cap ? `<label>Maximum food spend per person (${safe(r.currency)})<input id="restaurant-budget-cap" type="number" min="1" step="1"></label><p class="hint">Both partners will review the resulting quote before approval.</p>` : ''}
    ${searchable ? action('search','Find options') : ''}
    ${r.state === 'shortlist' ? r.options.map(q => `<article class="card"><h3>${safe(q.name)}</h3>
      ${q.provider_label ? `<p>Via ${safe(q.provider_label)}</p>` : ''}
      <p>${safe(q.neighbourhood)} · ${safe(q.distance_km)} km · ${safe(q.date_time)}</p>
      <p>${q.cuisines.map(safe).join(', ')} · ${q.diets.map(safe).join(', ')}</p>
      <p>Estimated food: ${money(q.estimate_per_person_minor,q.currency,q.currency_exponent)} per person.</p>
      ${Number.isInteger(q.estimated_total_minor) ? `<p>Estimated total for two: ${money(q.estimated_total_minor,q.currency,q.currency_exponent)} · Pay upfront: ${money(q.upfront_minor,q.currency,q.currency_exponent)}.</p>` : ''}
      <p>Table deposit: ${money(q.deposit_minor,q.currency,q.currency_exponent)} total; ${money(q.food_credit_minor,q.currency,q.currency_exponent)} redeemable against food. Booking fee: ${money(q.booking_fee_minor,q.currency,q.currency_exponent)}.</p>
      <p class="hint">DhaShu stage fees are separate. ${safe(q.cancellation)}</p>
      <p>${r.my_approval === q.quote_id ? '✓ You approved. ' : ''}${r.partner_approval === q.quote_id ? 'Your match approved this option.' : ''}</p>
      <button type="button" class="secondary restaurant-action" data-action="approve" data-quote="${safe(q.quote_id)}" ${r.my_approval === q.quote_id || !r.date_open ? 'disabled' : ''}>Approve this option</button></article>`).join('') : ''}
    ${r.selected && ['ready_to_pay','payment_failed'].includes(r.state) ? `<p>${safe(r.selected.name)} · Deposit ${money(r.selected.deposit_minor,r.selected.currency,r.selected.currency_exponent)} for the table. One partner pays the full deposit; no split payment is collected here.</p>` : ''}
    ${['ready_to_pay','payment_failed'].includes(r.state) && r.can_pay ? action('pay','Simulate deposit and reserve') : ''}
    ${r.state === 'ready_to_pay' && !r.can_pay && r.date_open ? '<p>Both partners need to sign the date playbook before the deposit step.</p>' : ''}
    ${r.state === 'unknown' ? action('reconcile','Check reservation status') : ''}
    ${r.reference ? `<p>Reference: ${safe(r.reference)}</p>` : ''}
    ${['confirmed','ready_to_pay','payment_failed','shortlist'].includes(r.state) ? action('cancel','Cancel restaurant selection / reservation') : ''}
    ${r.refund !== 'none' ? `<p>Simulated refund: ${safe(r.refund)}</p>` : ''}
    ${r.refund === 'failed' ? action('retry_refund','Retry simulated refund') : ''}
    <button type="button" class="secondary" id="restaurant-refresh">Refresh restaurant status</button>
  </section>`;
}

export function bindRestaurant(root, ctx) {
  root.querySelector('#restaurant-refresh')?.addEventListener('click', () => ctx.run(async () => {
    const restaurant = await ctx.session.get(`/api/v1/date-plans/${encodeURIComponent(ctx.data.id)}/restaurant`);
    ctx.patch({...ctx.data, restaurant});
  }));
  root.querySelectorAll('.restaurant-action').forEach(button => button.addEventListener('click', () => ctx.run(async () => {
    const path = `/api/v1/date-plans/${encodeURIComponent(ctx.data.id)}/restaurant`;
    const body = {action:button.dataset.action, revision:ctx.data.restaurant.revision};
    if (button.dataset.quote) body.quote_id = button.dataset.quote;
    const cap = root.querySelector('#restaurant-budget-cap');
    if (body.action === 'search' && cap?.value) body.max_per_person_minor = Math.round(Number(cap.value) * (10 ** ctx.data.restaurant.currency_exponent));
    const restaurant = await ctx.session.post(`${path}/actions`, body);
    ctx.patch({...ctx.data, restaurant});
  })));
}
