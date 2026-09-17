// Agreement ceremony (§2.4): playbook → sign → face, order-enforced. No
// journey/status surface exists for this screen (its path always needs a
// specific plan id), so it defines its own load() — main.js's loadScreen()
// calls this instead of the generic surface lookup.
//
// The client only ever offers the ONE action matching `data.step` — never a
// picker of "which step to do" — so there is no path through this UI that
// submits a step out of order, on top of the server's own validation.

const STEP_ORDER = ['playbook', 'sign', 'face', 'done'];

// The one action this screen will ever offer for a given server-reported
// step — null once done, since there's nothing left to advance. Exported so
// the step-order guarantee ("never offer a step other than the current
// one") is testable without a DOM: render() below never branches on
// anything but this same `data.step`, so there is structurally no path to
// showing two steps' forms at once, let alone the wrong one.
export function legalAction(step) {
  return STEP_ORDER.includes(step) && step !== 'done' ? step : null;
}

export async function load(session, params) {
  return session.get(`/api/v1/date-plans/${encodeURIComponent(params.planId)}/agreement`);
}

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Agreement</h1></section><section class="card"><p>Loading…</p></section>';
  const stepIndex = STEP_ORDER.indexOf(data.step);
  const track = `<div class="step-track">${STEP_ORDER.map((s, i) => `<div class="step-node ${i < stepIndex || data.complete ? 'done' : i === stepIndex ? 'current' : ''}">${safe(s)}</div>`).join('')}</div>`;

  if (data.complete || data.step === 'done') {
    return `<section class="intro"><span class="eyebrow">AGREEMENT</span><h1>All set</h1></section>${track}
      <section class="card guidance"><p>Both signatures and verification are complete. This plan is confirmed.</p>
      <button id="to-debrief" class="primary" type="button">After the date <span aria-hidden="true">→</span></button></section>`;
  }
  if (data.step === 'playbook') {
    return `<section class="intro"><span class="eyebrow">AGREEMENT · 1 of 3</span><h1>Rules of engagement</h1></section>${track}
      <section class="card">${(data.clauses || []).map((c) => `<div class="clause">${safe(c.text || c.label || c.term || JSON.stringify(c))}</div>`).join('') || '<p class="hint">Nothing further to review — continue when ready.</p>'}</section>
      <button id="do-playbook" class="primary" type="button">I've read this <span aria-hidden="true">→</span></button>`;
  }
  if (data.step === 'sign') {
    return `<section class="intro"><span class="eyebrow">AGREEMENT · 2 of 3</span><h1>Sign</h1></section>${track}
      <section class="card"><form id="sign-form">
        <div class="field"><label for="signed_name">Your name</label><input id="signed_name" name="signed_name" required maxlength="200"></div>
        ${(data.acknowledgements || []).map((a) => `<label class="checkbox-row"><input type="checkbox" name="ack" value="${safe(a.key)}" required> ${safe(a.label)}</label><p class="hint" style="margin:-6px 0 10px 26px;">${safe(a.term)}</p>`).join('')}
        <button class="primary" type="submit">Sign</button>
      </form></section>`;
  }
  if (data.step === 'face') {
    return `<section class="intro"><span class="eyebrow">AGREEMENT · 3 of 3</span><h1>Verify it's you</h1></section>${track}
      <section class="card"><p>${data.face_simulation_available ? "This is a beta simulation — it doesn't run a real biometric check." : 'Verification is not available in this build yet.'}</p>
      <button id="do-face" class="primary" type="button" ${data.face_simulation_available ? '' : 'disabled'}>Verify <span aria-hidden="true">→</span></button></section>`;
  }
  return `<section class="intro"><h1>Agreement</h1></section>${track}`;
}

export function bind(root, ctx) {
  const { session, run, patch, params, navigateTo } = ctx;
  const planId = encodeURIComponent(params.planId);
  const reload = async () => patch(await session.get(`/api/v1/date-plans/${planId}/agreement`));

  root.querySelector('#to-debrief')?.addEventListener('click', () => navigateTo('debrief'));

  root.querySelector('#do-playbook')?.addEventListener('click', () => run(async () => {
    await session.post(`/api/v1/date-plans/${planId}/agreement/steps`, { step: 'playbook' });
    await reload();
  }));

  root.querySelector('#sign-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    run(async () => {
      const form = new FormData(e.target);
      await session.post(`/api/v1/date-plans/${planId}/agreement/steps`, {
        step: 'sign', signed_name: form.get('signed_name').trim(), acks: form.getAll('ack'),
      });
      await reload();
    });
  });

  root.querySelector('#do-face')?.addEventListener('click', () => run(async () => {
    await session.post(`/api/v1/date-plans/${planId}/agreement/steps`, { step: 'face' });
    await reload();
  }));
}
