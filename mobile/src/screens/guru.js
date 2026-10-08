// Short, stage-specific guidance. Navigation always respects API eligibility.
let qa = null; // { question, answer, actionLabel, actionKey }
// GET /api/v1/reach's counts, fetched once per Guru visit the first time
// "Why so few matches?" is tapped — reach.js's own screen is the real
// source of truth; this is only ever read here for one sentence.
let reachCache = null;
let contextKey = null;

export function _resetForTest() { qa = null; reachCache = null; contextKey = null; }

const TOPICS = {
  values: ['What matters to you?', 'Review your Vision and the interests you would like to share. Your preferences are yours to choose.', 'vision'],
  matching: ['How matching works', 'Matching considers both people’s preferences. A Like expresses interest; only mutual interest creates a pair.', 'week'],
  match: ['Get to know this match', 'Compare your Vision, Stats and Chemistry. Look for what fits and what you would like to ask. You choose Like or Pass.', 'week'],
  planning: ['Plan your date together', 'Share your preferences and availability, then choose an overlapping slot. Your saved work stays while your partner responds.', 'calendar'],
  agreement: ['Know what you’re agreeing to', 'Read the date plan and terms before signing. Both partners must complete their own agreement. Signing does not imply consent to contact sharing or intimacy.', 'plan'],
  prepare: ['Prepare for your date', 'Check the time and public venue. Arrive on time, respect each other’s boundaries and choose something you both enjoy.', 'plan'],
  reflect: ['Reflect on your date', 'What felt good? What concerned you? Save your Debrief and choose what you want next. You do not need to decide together.', 'debrief'],
  build: ['Build on your last date', 'Think about what you enjoyed and what you would change. Ask your partner what they would enjoy next; another date is a choice for both of you.', null],
  next: ['Talk about what matters next', 'Choose the questions that matter to you, add your own and answer independently. Share answers only when you want to.', 'gate'],
  pace: ['Take your next step at your pace', 'You can take time, stay at this stage or decide not to continue. A next stage needs both people’s agreement.', 'gate'],
  sharing: ['Share at your pace', 'Phone, socials and home invitations are separate choices. Each request needs explicit consent. Accepting one never means accepting another; you can decline.', 'after_date'],
  support: ['Something doesn’t feel right?', 'You can decline a request, pause or end the connection. Use the reporting option where available. If you feel unsafe, leave and contact someone you trust.', null],
};
export function chipsFor(data) {
  const stage = data.topic_stage || (data.date_context?.phase === 'debrief' ? 'debrief' : data.date_context?.phase === 'before_date' ? 'before_date' : data.date_context ? 'planning' : 'matching');
  const ids = {
    matching: ['values', 'matching'],
    match_available: ['match', 'matching'],
    planning: ['planning', 'agreement', 'sharing'],
    repeat_planning: ['build', 'planning', 'sharing'],
    agreement: ['agreement', 'prepare', 'sharing'],
    before_date: ['prepare', 'agreement', 'sharing'],
    debrief: ['reflect', 'sharing'],
    post_debrief: ['build', 'pace', 'sharing'],
    relationship: ['next', 'pace', 'sharing'],
  }[stage] || ['values', 'pace'];
  return ids.map(id => ({id, label: TOPICS[id][0]}));
}

export function render(ctx) {
  const { data, safe, journey } = ctx;
  if (!data) return '<section class="intro"><h1>Guru</h1></section><section class="card"><p>Loading…</p></section>';
  const nextKey=JSON.stringify([journey?.user?.user_id,journey?.clock,data]);
  if(nextKey!==contextKey){qa=null;reachCache=null;contextKey=nextKey;}
  const firstName = safe((journey?.user?.display_name || 'there').trim().split(/\s+/)[0]);
  const chips = chipsFor(data);

  return `<section class="p-guru-header">
      <div class="guru-avatar">G</div>
      <div><div style="font-weight:800;">Guru</div><div class="p-guru-role">Relationship navigator</div></div>
    </section>
    <div class="p-guru-thread">
      ${!qa ? `<div class="p-bubble-guru"><span>${safe(data.headline || 'Your next step')} · ${safe(data.body || 'Choose a topic below.')}</span></div>` : ''}
      ${qa ? `<div class="p-bubble-user">${safe(qa.question)}</div>
        <div class="p-bubble-guru"><span>${safe(qa.answer)}</span>
          ${qa.actionLabel ? `<button type="button" class="p-bubble-action" data-goto>${safe(qa.actionLabel)} <span aria-hidden="true">→</span></button>` : ''}
        </div>` : ''}
    </div>
    <div class="p-quick-replies">${chips.map((c) => `<button type="button" class="p-quick-reply" data-chip="${safe(c.id)}">${safe(c.label)}</button>`).join('')}</div>
    <button type="button" class="secondary" data-chip="support">Something doesn’t feel right?</button>`;

}

// The one place every chip's question+answer+action gets decided — a plain
// function of (chip id, the SAME guidance response render() used, the
// journey surfaces needed to check an action's own eligibility, and a
// reach-counts fetcher) so it's testable without a DOM.
export async function answerFor(id, data, journeySurfaces, fetchReach) {
  const eligible = (key) => journeySurfaces?.find((s) => s.key === key)?.eligible;
  if (TOPICS[id]) {
    const [question, text, key] = TOPICS[id];
    const prompt = (data.date_context?.prompts || []).find(p =>
      id === 'build' ? p.title === 'Your last Debrief' : id === 'prepare' && p.title === 'Enjoy together');
    const target = journeySurfaces?.find(s => s.key === key);
    return {question, answer: text + (prompt ? ' ' + prompt.body : ''),
      actionLabel: target?.eligible && target?.request ? 'Open' : null, actionKey: key};
  }

  if (id === 'what_now') {
    const dest = data.destination;
    return { question: 'What now?', answer: data.body || data.headline || '',
      actionLabel: dest?.eligible && dest?.request ? (data.cta || 'Continue') : null, actionKey: dest?.key };
  }
  if (id === 'why_few_matches') {
    if (!reachCache) reachCache = await fetchReach();
    const mutual = reachCache?.counts?.mutual_open ?? 0, fit = reachCache?.counts?.fits_user_filters ?? 0;
    return { question: 'Why so few matches?', answer: `${mutual} of ${fit} who fit you are open to you. These are reciprocal filter counts, not guaranteed matches. Review your preferences only if you want to.`,
      actionLabel: eligible('reach') ? 'Open Reach' : null, actionKey: 'reach' };
  }
  if(data.date_context && ['date_prep','date_debrief','sharing'].includes(id)) {
    const item={date_prep:['Prepare for this date',data.date_context.prep,'calendar'],date_debrief:['Date Debrief',data.date_context.debrief||'Share what went well and any concerns, then choose what happens next.','debrief'],sharing:['Phone & socials',data.date_context.sharing,'after_date']}[id];
    const key=id==='date_prep'&&eligible('plan')?'plan':item[2];
    return {question:item[0],answer:item[1],actionLabel:eligible(key)&&journeySurfaces?.find(s=>s.key===key)?.request&&(id!=='date_debrief'||data.date_context.phase==='debrief')?'Open':null,actionKey:key};
  }
  const dc = data.dating_context;
  if (id === 'how_dating_works' && dc) {
    return { question: 'How Dating works', answer: [...(Array.isArray(dc.consent)?dc.consent:[dc.consent]),dc.playbook?.[0]].filter(Boolean).join(' '),
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
