// Optional server-driven rehearsal UI, shared by Android and iOS.
export function renderRehearsal(state, safe) {
  if (!state?.enabled) return '';
  return `<aside class="card rehearsal-banner"><strong>Test journey · at your own pace</strong>
    <p>${safe(state.message)}</p><p class="hint">Your progress stays saved while your partner is away. No automatic reset.</p>
    ${state.request ? `<button id="rehearsal-ready" type="button" class="primary">${safe(state.request.label)}</button>` : ''}
    <button id="refresh-clock" type="button" class="secondary">Refresh progress</button></aside>`;
}

export function progressKey(journey) {
  // Partner readiness can change while the displayed clock stays the same.
  return JSON.stringify([journey?.clock, journey?.async_rehearsal, journey?.current_date_plan,
    journey?.current_lock_in, journey?.milestones]);
}
