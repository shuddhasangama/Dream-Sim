// design_handoff_app_ui_pulse/README.md ("Pulse", option 1a) — Guru's
// quick-reply answers: every one is either the server's own guidance
// response verbatim or a plain sentence built from counts already on the
// wire — never an escalation suggestion (§4 hard constraint 5).
import test from 'node:test';
import assert from 'node:assert/strict';
import { answerFor, _resetForTest } from '../src/screens/guru.js';

test.beforeEach(() => _resetForTest());

const surfaces = [
  { key: 'week', eligible: true }, { key: 'reach', eligible: true },
  { key: 'plan', eligible: false }, { key: 'calendar', eligible: false },
];

test('"What now?" answers with the guidance response body, action only if the destination is actually reachable', async () => {
  const data = { headline: 'h', body: 'Take a moment.', cta: 'See this week',
    destination: { key: 'week', eligible: true, request: { method: 'GET', path: '/x' } } };
  const r = await answerFor('what_now', data, surfaces, async () => ({}));
  assert.equal(r.answer, 'Take a moment.');
  assert.deepEqual([r.actionLabel, r.actionKey], ['See this week', 'week']);
});
test('"What now?" offers no action when the destination is not reachable', async () => {
  const data = { body: 'x', destination: { key: 'gate', eligible: false, request: null } };
  const r = await answerFor('what_now', data, surfaces, async () => ({}));
  assert.equal(r.actionLabel, null);
});

test('"Why so few matches?" states the real counts and fetches reach exactly once', async () => {
  let calls = 0;
  const fetchReach = async () => { calls += 1; return { counts: { mutual_open: 2, fits_user_filters: 9 } }; };
  const data = {};
  const first = await answerFor('why_few_matches', data, surfaces, fetchReach);
  assert.equal(first.answer, '2 of 9 who fit you are open to you. These are reciprocal filter counts, not guaranteed matches. Review your preferences only if you want to.');
  assert.deepEqual([first.actionLabel, first.actionKey], ['Open Reach', 'reach']);
  await answerFor('why_few_matches', data, surfaces, fetchReach);
  assert.equal(calls, 1, 'memoized — one Guru visit, one /reach read');
});

test('"How Dating works" is null outside Dating (no dating_context) — the chip never appears for another stage', async () => {
  assert.equal(await answerFor('how_dating_works', {}, surfaces, async () => ({})), null);
});
test('"How Dating works" uses the consent explainer plus the first playbook step, verbatim', async () => {
  const data = { dating_context: { consent: 'Every yes is real.', playbook: ['Matches are drawn for you.', 'second'] } };
  const r = await answerFor('how_dating_works', data, surfaces, async () => ({}));
  assert.equal(r.answer, 'Every yes is real. Matches are drawn for you.');
  assert.equal(r.actionKey, 'week');
});

test('"Before we meet" falls back from plan to calendar, and drops the action when neither is reachable', async () => {
  const data = { dating_context: { date_prep: { courtesies: ['Arrive on time'], note: 'Contact stays in-app.' } } };
  const r = await answerFor('before_we_meet', data, surfaces, async () => ({}));
  assert.equal(r.actionLabel, null); // both plan and calendar are ineligible in this fixture
  const reachable = [{ key: 'plan', eligible: true }];
  const r2 = await answerFor('before_we_meet', data, reachable, async () => ({}));
  assert.equal(r2.actionKey, 'plan');
  assert.match(r2.answer, /Arrive on time/);
});

test('an also_open card becomes its own chip answer, one-to-one', async () => {
  const data = { also_open: [{ title: 'Vibes', subtitle: 'What keeps this alive', destination: { key: 'vibes', eligible: false, request: null } }] };
  const r = await answerFor('also_0', data, surfaces, async () => ({}));
  assert.equal(r.question, 'Vibes');
  assert.equal(r.answer, 'What keeps this alive');
  assert.equal(r.actionLabel, null); // ineligible destination — still readable, just not actionable
});

test('an unknown chip id answers nothing rather than guessing', async () => {
  assert.equal(await answerFor('not_a_real_chip', {}, surfaces, async () => ({})), null);
});
