// Guru — design_handoff_app_ui_pulse/README.md ("Pulse", option 1a): a
// conversational "what now?" with quick-reply chips instead of the old
// screen's fixed paragraphs/accordions. Every answer still comes from
// EXACTLY the same GET /api/v1/guidance response the old screen read
// (headline/body/cta/destination, Dating-only `dating_context`, and
// `also_open` — see journey_api.guidance()) — nothing here invents new
// server content, it only decides which quick reply surfaces which part
// of that same response, and in what order.
//
// §4 hard constraint 5 still holds structurally: Guru reflects and
// structures, never nudges escalation. Every answer below is either the
// server's own copy verbatim (dc.consent, dc.playbook, prep.*, a card's
// own subtitle) or a plain factual sentence built from counts already on
// the wire (`{mutual} of {fit} who fit...`) — nothing here suggests
// progressing a stage, inviting someone home, or sharing contacts.
//
// Non-Dating stages have no guru_dating.py content of their own (it is
// deliberately Dating-only) — so outside Dating the quick replies are
// "What now?" plus one chip per `also_open` entry, which is already
// whatever the server's own guru.cards() considers relevant at THIS
// stage. That is what makes the chip set "stage-aware" without this file
// hardcoding Relationship/Engaged/Married copy that doesn't exist yet.

// Which reflection is showing — module-level, like reach.js's sheet key:
// every mutation re-renders the whole app, and this is purely a client-
// side selection, never server state.
let qa = null; // { question, answer, actionLabel, actionKey }
// GET /api/v1/reach's counts, fetched once per Guru visit the first time
// "Why so few matches?" is tapped — reach.js's own screen is the real
// source of truth; this is only ever read here for one sentence.
let reachCache = null;

export function _resetForTest() { qa = null; reachCache = null; }

const STAGE_CHIPS = [
  { id: 'what_now', label: 'What now?' },
  { id: 'why_few_matches', label: 'Why so few matches?' },
  { id: 'how_dating_works', label: 'How Dating works' },
  { id: 'before_we_meet', label: 'Before we meet' },
];

function chipsFor(data) {
  if (data.dating_context) return STAGE_CHIPS;
  return [
    { id: 'what_now', label: 'What now?' },
    ...(data.also_open || []).map((c, i) => ({ id: `also_${i}`, label: c.title, card: c })),
  ];
}

export function render(ctx) {
  const { data, safe, journey } = ctx;
  if (!data) return '<section class="intro"><h1>Guru</h1></section><section class="card"><p>Loading…</p></section>';
  const firstName = safe((journey?.user?.display_name || 'there').trim().split(/\s+/)[0]);
  const chips = chipsFor(data);

  return `<section class="p-guru-header">
      <div class="guru-avatar">G</div>
      <div><div style="font-weight:800;">Guru</div><div class="p-guru-role">Relationship navigator</div></div>
    </section>
    <div class="p-guru-thread">
      <div class="p-bubble-guru"><span>Hi ${firstName}. What's on your mind?</span></div>
      ${qa ? `<div class="p-bubble-user">${safe(qa.question)}</div>
        <div class="p-bubble-guru"><span>${safe(qa.answer)}</span>
          ${qa.actionLabel ? `<button type="button" class="p-bubble-action" data-goto>${safe(qa.actionLabel)} <span aria-hidden="true">→</span></button>` : ''}
        </div>` : ''}
    </div>
    <div class="p-quick-replies">${chips.map((c) => `<button type="button" class="p-quick-reply" data-chip="${safe(c.id)}">${safe(c.label)}</button>`).join('')}</div>`;
}

// The one place every chip's question+answer+action gets decided — a plain
// function of (chip id, the SAME guidance response render() used, the
// journey surfaces needed to check an action's own eligibility, and a
// reach-counts fetcher) so it's testable without a DOM.
export async function answerFor(id, data, journeySurfaces, fetchReach) {
  const eligible = (key) => journeySurfaces?.find((s) => s.key === key)?.eligible;
  if (id === 'what_now') {
    const dest = data.destination;
    return { question: 'What now?', answer: data.body || data.headline || '',
      actionLabel: dest?.eligible && dest?.request ? (data.cta || 'Continue') : null, actionKey: dest?.key };
  }
  if (id === 'why_few_matches') {
    if (!reachCache) reachCache = await fetchReach();
    const mutual = reachCache?.counts?.mutual_open ?? 0, fit = reachCache?.counts?.fits_user_filters ?? 0;
    return { question: 'Why so few matches?', answer: `${mutual} of ${fit} who fit you are open to you. Loosen one filter.`,
      actionLabel: eligible('reach') ? 'Open Reach' : null, actionKey: 'reach' };
  }
  const dc = data.dating_context;
  if (id === 'how_dating_works' && dc) {
    return { question: 'How Dating works', answer: [dc.consent, dc.playbook?.[0]].filter(Boolean).join(' '),
      actionLabel: eligible('week') ? 'See the week' : null, actionKey: 'week' };
  }
  if (id === 'before_we_meet' && dc?.date_prep) {
    const prep = dc.date_prep;
    const rulesSurface = ['plan', 'calendar'].find(eligible);
    return { question: 'Before we meet', answer: [prep.courtesies?.[0], prep.note].filter(Boolean).join(' '),
      actionLabel: rulesSurface ? 'Rules of engagement' : null, actionKey: rulesSurface };
  }
  const card = (data.also_open || []).find((_, i) => `also_${i}` === id);
  if (card) {
    return { question: card.title, answer: card.subtitle || '',
      actionLabel: card.destination?.eligible && card.destination?.request ? `Open ${card.title}` : null, actionKey: card.destination?.key };
  }
  return null;
}

export function bind(root, ctx) {
  const { data, navigateTo, run, session, journey } = ctx;
  root.querySelectorAll('[data-chip]').forEach((btn) => btn.addEventListener('click', () => run(async () => {
    const next = await answerFor(btn.dataset.chip, data, journey?.surfaces, () => session.get('/api/v1/reach'));
    if (next) qa = next;
  })));
  root.querySelector('[data-goto]')?.addEventListener('click', () => { if (qa?.actionKey) navigateTo(qa.actionKey); });
}
