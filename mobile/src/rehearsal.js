// Optional server-driven rehearsal UI, shared by Android and iOS.
export function renderRehearsal(state, safe, clock) {
  if (!state?.enabled) return '';
  const draft=state.draft_availability;
  const selected=new Set((draft?.my_slots||[]).map(s=>`${s.day}|${s.meal_slot}`));
  const slots=draft ? `<form id="rehearsal-slots"><h2>Your weekend availability</h2><p>Save your slots now. Planning still requires mutual interest and a shared slot.</p>
    ${draft.valid_slots.map(s=>`<label class="checkbox-row"><input type="checkbox" name="slot" value="${safe(s.day)}|${safe(s.meal_slot)}" ${selected.has(`${s.day}|${s.meal_slot}`)?'checked':''}> ${safe(s.day)} · ${safe(s.meal_slot)}</label>`).join('')}
    <button type="submit" class="primary">Save availability</button></form>` : '';
  return `<aside class="card rehearsal-banner"><strong>Test journey · at your own pace</strong>
    ${clock ? `<p><strong>${safe(clock.day)} ${String(clock.hour).padStart(2,'0')}:00 · Week ${safe(clock.week)}</strong></p>` : ''}
    <p>${safe(state.message)}</p>${state.next_jump_in_seconds != null ? `<p class="hint">Next checkpoint in approximately ${Math.ceil(state.next_jump_in_seconds/60)} minute(s). Availability opens after 12 minutes; then the clock waits.</p>` : ''}${slots}<p class="hint">Your progress stays saved while your partner is away. No automatic reset.</p>
    ${state.request ? `<button id="rehearsal-ready" type="button" class="primary">${safe(state.request.label)}</button>` : ''}
    <button id="refresh-clock" type="button" class="secondary">Refresh progress</button></aside>`;
}

export function progressKey(journey) {
  // Partner readiness can change while the displayed clock stays the same.
  return JSON.stringify([journey?.clock, journey?.async_rehearsal, journey?.current_date_plan,
    journey?.current_lock_in, journey?.milestones]);
}
