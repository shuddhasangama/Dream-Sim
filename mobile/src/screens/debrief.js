// Date feedback (§2.5). Flag/decision options come from DateDebrief's own
// green_flag_options/red_flag_options/decision_options — never a hardcoded
// list. flagsValid() is the one bit of this screen worth unit-testing on
// its own (exactly two green flags, up to two red).

export function flagsValid(green, red) {
  return Array.isArray(green) && green.length === 2 && Array.isArray(red) && red.length <= 2;
}

const DECISION_COPY = {
  continue: { label: 'Continue dating', warn: null },
  relationship: { label: 'Go steady', warn: null },
  pass: { label: 'Pass', warn: "One No is Enough — this ends things and releases you both immediately, no explanation owed." },
};

export function render(ctx) {
  const { data, safe } = ctx;
  if (!data) return '<section class="intro"><h1>Debrief</h1></section><section class="card"><p>Loading…</p></section>';
  const f = data.my_feedback;
  const needsFlags = !flagsValid(f.green_flags, f.red_flags);

  if (!data.feedback_open) {
    return `<section class="intro"><span class="eyebrow">DEBRIEF</span><h1>Not open yet</h1></section><section class="card"><p>Feedback opens ${safe(data.opens_at)}.</p></section>`;
  }
  if (needsFlags) {
    return `<section class="intro"><span class="eyebrow">DEBRIEF</span><h1>How did it go?</h1></section>
      <section class="card"><form id="flags-form">
        <div class="field"><label>Pick exactly 2 green flags</label><div class="flag-grid" data-max="2">${(data.green_flag_options || []).map((g) => `<button type="button" class="flag" data-group="green" data-value="${safe(g)}">${safe(g)}</button>`).join('')}</div></div>
        <div class="field"><label>Up to 2 red flags — optional</label><div class="flag-grid red" data-max="2">${(data.red_flag_options || []).map((r) => `<button type="button" class="flag" data-group="red" data-value="${safe(r)}">${safe(r)}</button>`).join('')}</div></div>
        <label class="checkbox-row"><input type="checkbox" name="together_photo"> We took a selfie together</label>
        <label class="checkbox-row"><input type="checkbox" name="bill_photo"> We photographed the bill</label>
        <button class="primary" type="submit" disabled>Save feedback</button>
      </form></section>`;
  }
  if (!f.decision) {
    return `<section class="intro"><span class="eyebrow">DEBRIEF</span><h1>What's next?</h1></section>
      <section class="card"><p>Feedback saved. Now, what's next?</p>
        <form id="decision-form">
          <textarea name="reason" maxlength="2000" placeholder="Optional — only used if you pass"></textarea>
          <div class="action-row" style="flex-wrap:wrap;">
            ${(data.decision_options || []).map((d) => `<button type="submit" name="decision" value="${safe(d)}" class="${d === 'pass' ? 'secondary' : d === 'relationship' ? 'primary' : 'secondary'}">${safe(DECISION_COPY[d]?.label || d)}</button>`).join('')}
          </div>
          <p class="warn">${safe(DECISION_COPY.pass.warn)}</p>
        </form></section>`;
  }
  return `<section class="intro"><span class="eyebrow">DEBRIEF</span><h1>Saved</h1></section>
    <section class="card"><p>You said: ${safe(DECISION_COPY[f.decision]?.label || f.decision)}. ${data.partner_submitted ? '' : 'Waiting on your match.'}</p>
    ${data.resolution !== 'pending' ? `<p class="hint">Result: ${safe(data.resolution.replaceAll('_', ' '))}</p>` : ''}</section>`;
}

export function bind(root, ctx) {
  const { session, run, patch } = ctx;
  const planId = encodeURIComponent(ctx.data.plan_id);

  const picked = { green: new Set(), red: new Set() };
  const submitBtn = root.querySelector('#flags-form button[type="submit"]');
  const syncEnabled = () => { if (submitBtn) submitBtn.disabled = !flagsValid([...picked.green], [...picked.red]); };
  root.querySelectorAll('.flag').forEach((btn) => btn.addEventListener('click', () => {
    const group = picked[btn.dataset.group];
    const max = Number(btn.closest('.flag-grid').dataset.max);
    if (group.has(btn.dataset.value)) { group.delete(btn.dataset.value); btn.classList.remove('picked'); }
    else if (group.size < max) { group.add(btn.dataset.value); btn.classList.add('picked'); if (btn.dataset.group === 'red') btn.classList.add('red'); }
    syncEnabled();
  }));

  root.querySelector('#flags-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!flagsValid([...picked.green], [...picked.red])) return;
    run(async () => {
      const form = new FormData(e.target);
      patch(await session.put(`/api/v1/date-plans/${planId}/feedback/flags`, {
        green_flags: [...picked.green], red_flags: [...picked.red],
        together_photo: form.has('together_photo'), bill_photo: form.has('bill_photo'),
      }));
    });
  });

  root.querySelector('#decision-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const decision = e.submitter?.value;
    if (!decision) return;
    run(async () => {
      const reason = new FormData(e.target).get('reason')?.trim() || null;
      patch(await session.post(`/api/v1/date-plans/${planId}/feedback/decision`, { decision, reason: decision === 'pass' ? reason : null }));
    });
  });
}
