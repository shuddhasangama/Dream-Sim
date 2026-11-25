// cq-playwright: two members through the whole journey against the real local
// backend — matched, two dates, gate, Relationship, Engaged, Married — then an
// exit, with the app itself checked in the browser along the way.
// Backend: tools/e2e_server.py (temporary SQLite, local harness sign-in).
import {test, expect, request as playwrightRequest} from '@playwright/test';

const BACKEND = 'http://127.0.0.1:5000';
const PAIR = ['test_owner', 'test_partner'];

class Member {
  constructor(api, id) { this.api = api; this.id = id; this.headers = {}; }
  async signIn() {
    const r = await this.api.post('/api/v1/dev/login-as', {data: {user_id: this.id}});
    expect(r.status(), await r.text()).toBe(200);
    this.headers = {Authorization: 'Bearer ' + (await r.json()).data.access_token};
  }
  async call(method, path, body, expected = 200) {
    const r = await this.api.fetch('/api/v1' + path, {method, headers: this.headers, data: body});
    const text = await r.text();
    expect(r.status(), `${method} ${path}: ${text.slice(0, 300)}`).toBe(expected);
    return text ? JSON.parse(text).data : null;
  }
  get(path, expected) { return this.call('GET', path, undefined, expected); }
  post(path, body = {}, expected) { return this.call('POST', path, body, expected); }
  put(path, body, expected) { return this.call('PUT', path, body, expected); }
  async sign(path, kind, acks) {
    for (const body of [{step: 'playbook'}, {step: 'sign', signed_name: this.id, acks: acks[kind]}, {step: 'face'}]) {
      await this.post(path, body);
    }
  }
}

async function clock(api, week, day, hour) {
  const r = await api.post('/api/v1/simulated-clock', {data: {week, day, hour}, headers: {}});
  expect([200, 201], await r.text()).toContain(r.status());
}

test('two members: matched -> two dates -> gate -> Relationship -> Engaged -> Married -> exit', async ({page}) => {
  const api = await playwrightRequest.newContext({baseURL: BACKEND});
  const constants = await (await api.get('/__e2e/constants')).json();
  const [owner, partner] = PAIR.map(id => new Member(api, id));
  const stranger = new Member(api, 'test_stranger');
  for (const m of [owner, partner, stranger]) await m.signIn();
  // the clock endpoint needs a signed-in caller
  const tick = (w, d, h) => owner.post('/simulated-clock', {week: w, day: d, hour: h});
  await tick(1, 'Mon', 12);

  // Matched and locked in.
  const matches = {};
  for (const m of [owner, partner]) {
    const week = await m.post('/week/prepare');
    expect(week.matches.length).toBe(1);
    matches[m.id] = week.matches[0].id;
  }
  for (const m of [owner, partner]) await m.post(`/matches/${matches[m.id]}/actions`, {action: 'interest'});
  const lid = (await owner.get('/lock-ins/current')).lock_in.id;
  const base = `/lock-ins/${lid}`;
  await stranger.get(base + '/calendar', 404);                       // not theirs

  // Two dates, each planned, signed, held and debriefed.
  for (const cycle of [1, 2]) {
    await tick(cycle, 'Mon', 12);
    for (const m of [owner, partner]) {
      const options = (await m.get(base + '/calendar')).alignment.options;
      const values = Object.fromEntries(Object.entries(options).map(([k, v]) => [k, k === 'diet' ? v[0] : [v[0]]]));
      await m.put(base + '/alignment', values);
      await m.put(base + '/availability', {slots: [{day: 'Sat', meal_slot: 'dinner'}]});
    }
    const plan = await owner.post(base + '/date-plan', {day: 'Sat', meal_slot: 'dinner', cycle});
    const path = `/date-plans/${plan.id}`;
    for (const m of [owner, partner]) await m.sign(path + '/agreement/steps', constants.kinds.date, constants.acks);
    await tick(cycle, 'Sat', 21);
    for (const m of [partner, owner]) {
      await m.put(path + '/feedback/flags', {green_flags: constants.green_flags, red_flags: []});
      await m.post(path + '/feedback/decision', {decision: 'continue'});
    }
    await owner.post(path + '/feedback/decision', {decision: 'continue'});
    expect((await owner.get('/lock-ins/current')).lock_in.dates_completed).toBe(cycle);
  }

  // The app shows the lock-in to the owner (real UI, same-origin proxy session).
  await page.request.post('/login/test_owner');
  await page.goto('/');
  await expect(page.locator('body')).not.toContainText('Something went wrong');

  // Gate into Relationship.
  await owner.get(base + '/after-date');
  for (const m of [owner, partner]) {
    await m.post('/profile/vision/details', {request_id: 'entry', pillar: 'Kids', sub_selection: 'Adoption'});
    await m.put('/profile/chemistry/entries/intimacy_pace', {value: 'slow'});
  }
  await tick(3, 'Mon', 12);
  for (const m of [owner, partner]) {
    for (const key of constants.chemistry_keys) {
      const value = key === 'physical_boundary' ? 'namaste' : key === 'intimacy_pace' ? 'slow' : 'yes';
      await m.put('/profile/chemistry/entries/' + key, {value});
    }
  }
  await owner.post(base + '/gate/raise');
  await owner.post(base + '/gate/ask', {round: 1, question_keys: ['exclusivity_check']});
  for (const m of [owner, partner]) await m.post(base + '/gate/answer', {round: 1, question_key: 'exclusivity_check', value: 'exclusive'});
  await tick(3, 'Wed', 12);
  for (const m of [owner, partner]) {
    await m.post(base + '/gate/confirm', {round: 1});
    await m.post(base + '/gate/exclusivity-ack', {round: 1, acknowledged: true});
  }
  for (const m of [owner, partner]) await m.sign(base + '/agreements/relationship_entry/steps', constants.kinds.relationship_entry, constants.acks);
  await owner.post(base + '/gate/enter-relationship', {round: 1});
  const cid = (await owner.get('/dashboard')).current_couple.id;
  const couple = `/couples/${cid}`;
  await stranger.get(couple, 404);

  // Shared road, then Engaged and Married.
  for (const m of [owner, partner]) {
    await m.post(couple + '/road/routine', {request_id: 'routine', category: 'free', days: ['Thu'], label: 'Time', start: '18:00', end: '20:00'});
    await m.put(couple + '/road/sharing', {slots: [{day: 'Thu', start: '18:00', end: '20:00'}]});
  }
  expect((await owner.get(couple + '/road')).overlap).toBeTruthy();
  for (const stage of ['relationship', 'engaged']) {
    const path = `${couple}/checkpoints/${stage}`;
    await owner.sign(path + '/steps', constants.kinds.stage_gate, constants.acks);
    await owner.post(path + '/advance', {}, 409);                    // partner has not signed yet
    await partner.sign(path + '/steps', constants.kinds.stage_gate, constants.acks);
    await owner.post(path + '/advance');
    await owner.post(path + '/advance');
  }
  for (const m of [owner, partner]) expect((await m.get('/me')).journey_state).toBe('married');

  // The app opens for the married member without errors.
  await page.goto('/');
  await expect(page.locator('body')).not.toContainText('Something went wrong');

  // Exit: interview acknowledged by both, private feedback, cool-off.
  const started = await owner.post(couple + '/exits', {stage: 'married'});
  const exitPath = `${couple}/exits/${started.id}`;
  await owner.post(exitPath + '/feedback', {declined: false, text: 'private'}, 409);   // interview first
  for (const m of [owner, partner]) await m.post(exitPath + '/interview', {acknowledged: true});
  await owner.post(exitPath + '/feedback', {declined: false, text: 'My private feedback'});
  const partnerView = await partner.get(exitPath);
  expect(JSON.stringify(partnerView)).not.toContain('My private feedback');        // never crosses to the partner
  await partner.post(exitPath + '/feedback', {declined: true});
  await owner.post(exitPath + '/reentry', {}, 409);                                  // cool-off still running
  await api.dispose();
});
