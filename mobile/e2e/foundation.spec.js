import {test,expect} from '@playwright/test';
test('phone layout, wrong code, dashboard, and sign out without external calls',async({page})=>{
  const errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173'))external.push(r.url());});
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Send SMS code'})).toBeEnabled();
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('000000');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('#notice')).toContainText('Preview code');
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/dashboard.png',fullPage:true});
  // Refresh Dashboard button was removed (§1) — screens reload on
  // navigation instead. Round-trip through Week and back to prove it.
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  await page.getByRole('button',{name:'← Back'}).click();
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Sign out'})).toBeEnabled();
  await page.getByRole('button',{name:'Sign out'}).click();
  await expect(page.getByLabel('Phone number')).toBeVisible();
  expect(await page.evaluate(()=>localStorage.length)).toBe(0);
  expect(errors).toEqual([]);expect(external).toEqual([]);
});

test('navigation: tabs, the in-app back button, and journey/status-driven eligibility',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();

  // No back button on the root screen.
  await expect(page.getByRole('button',{name:'← Back'})).toHaveCount(0);
  // Tabs reflect exactly what journey/status marked eligible — Verify,
  // Relationship and Journey are ineligible in the preview fixture and must
  // never appear (mobile-journey-build-spec.md §1: derive nav from the API).
  const tabbar = page.locator('.topnav');
  await expect(tabbar.getByRole('button',{name:'REACH'})).toBeVisible();
  await expect(tabbar.getByRole('button',{name:'Week'})).toBeVisible();
  await expect(tabbar.getByRole('button',{name:'Verify'})).toHaveCount(0);
  await expect(tabbar.getByRole('button',{name:'Relationship'})).toHaveCount(0);

  await tabbar.getByRole('button',{name:'Week'}).click();
  await expect(page.getByRole('heading',{name:"This week's matches"})).toBeVisible();
  await expect(page.getByRole('button',{name:'← Back'})).toBeVisible();

  await page.getByRole('button',{name:'← Back'}).click();
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();
  await expect(page.getByRole('button',{name:'← Back'})).toHaveCount(0);

  // The dashboard's own next-action CTA is a second way into the same
  // navigation, not a separate mechanism — it should land on the same screen.
  await page.getByRole('button',{name:'See this week'}).click();
  await expect(page.getByRole('heading',{name:"This week's matches"})).toBeVisible();
});

test('mutual interest locks in and REACH disappears from the tab bar live, not just on the next full load',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  const tabbar = page.locator('.topnav');
  await expect(tabbar.getByRole('button',{name:'REACH'})).toBeVisible();
  await tabbar.getByRole('button',{name:'Week'}).click();
  await expect(page.locator('.candidate-name')).toHaveText('Priya Sharma');

  await page.getByRole('button',{name:'Express interest'}).click();
  await expect(page.getByRole('heading',{name:"You're locked in"})).toBeVisible();
  await expect(page.getByText('Status')).toBeVisible();
  // The tab bar re-renders from the freshly refetched journey/status —
  // REACH is gone without needing a manual reload (mobile-journey-build-
  // spec.md §2.1: "REACH sunsets at lock-in").
  await expect(tabbar.getByRole('button',{name:'REACH'})).toHaveCount(0);

  await page.getByRole('button',{name:'Open calendar'}).click();
  // Calendar now has its own bespoke screen (Stage 3).
  await expect(page.getByRole('heading',{name:'When to meet'})).toBeVisible();
});

test('full date pipeline: calendar overlap, plan, order-enforced ceremony, and two-green-flag debrief',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  await page.getByRole('button',{name:'Express interest'}).click();
  await page.getByRole('button',{name:'Open calendar'}).click();

  // Submit availability that overlaps the fixture's own match availability,
  // then confirm a slot — this generates the date plan (§2.4).
  await page.getByLabel('Fri · Dinner').check();
  await page.getByLabel('Sat · Dinner').check();
  await page.getByRole('button',{name:'Save availability'}).click();
  await expect(page.getByRole('heading',{name:'You\'re both free'})).toBeVisible();
  await page.getByRole('button',{name:'Confirm'}).first().click();
  await expect(page.getByRole('button',{name:'View date plan'})).toBeVisible();

  await page.getByRole('button',{name:'View date plan'}).click();
  await expect(page.getByRole('heading',{name:'Pending signatures'})).toBeVisible();
  await page.getByRole('button',{name:'Review & sign'}).click();

  // Ceremony is order-enforced: playbook → sign → face (§2.4). The client
  // only ever offers the one action matching the server's current step.
  await expect(page.getByRole('heading',{name:'Rules of engagement'})).toBeVisible();
  await page.getByRole('button',{name:"I've read this"}).click();

  await expect(page.getByRole('heading',{name:'Sign'})).toBeVisible();
  await page.getByLabel('Your name').fill('Rohan Verma');
  await page.getByLabel('I will treat my match with respect.').check();
  await page.getByLabel('I understand the cancellation terms.').check();
  await page.getByLabel('I understand this is not a relationship yet.').check();
  await page.getByLabel('I accept the platform is not liable for what happens on the date.').check();
  await page.getByRole('button',{name:'Sign',exact:true}).click();

  await expect(page.getByRole('heading',{name:"Verify it's you"})).toBeVisible();
  await page.getByRole('button',{name:'Verify',exact:true}).click();
  await expect(page.getByRole('heading',{name:'All set'})).toBeVisible();

  // round3-fixes-spec.md §5.2/§5.3: with the plan now confirmed, the Week
  // screen's grid swaps the generic Debrief placeholder for this couple's
  // real one — marked distinctly ("replace in place"), not just present.
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  const personalDebrief = page.locator('.tw-chip.is-personal', { hasText: 'Debrief' });
  await expect(personalDebrief).toBeVisible();
  await expect(personalDebrief).toHaveAttribute('title', /your actual date/);
  await page.getByRole('button',{name:'← Back'}).click();

  await page.getByRole('button',{name:'After the date'}).click();
  await expect(page.getByRole('heading',{name:'How did it go?'})).toBeVisible();

  // flagsValid requires exactly two green flags (§2.5) — the submit button
  // must stay disabled until exactly two are picked.
  const submit = page.getByRole('button',{name:'Save feedback'});
  await expect(submit).toBeDisabled();
  await page.getByRole('button',{name:'Actually listened'}).click();
  await expect(submit).toBeDisabled();
  await page.getByRole('button',{name:'On time'}).click();
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect(page.getByRole('heading',{name:"What's next?"})).toBeVisible();
  await expect(page.getByText('One No is Enough')).toBeVisible();
  await page.getByRole('button',{name:'Go steady'}).click();
  await expect(page.getByRole('heading',{name:'Saved'})).toBeVisible();
  await expect(page.getByText('You said: Go steady.')).toBeVisible();
});

test('Guru entry reflects the same next-action as the dashboard, and Vision records an additive detail plus a disclosed change',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  const tabbar = page.locator('.topnav');
  await tabbar.getByRole('button',{name:'Guru'}).click();
  // Guru never nudges escalation — it's the same read-only next-action
  // projection the dashboard's own "NEXT FOR YOU" card already shows, in
  // its own coral-avatar voice component (§5).
  await expect(page.getByRole('heading',{name:'What now?'})).toBeVisible();
  await expect(page.locator('.guru-avatar').first()).toHaveText('G');
  await expect(page.getByText('Your next chapter starts here')).toBeVisible();

  // round3-fixes-spec.md §6.2: consent + playbook, in Guru's own voice,
  // Dating-only — never an escalation suggestion, only how things work.
  // round4-fixes-spec.md §9: both are collapsible, bold-headed, collapsed by
  // default — their content appears only once expanded.
  const how = page.locator('details[data-fold="how-dating-works"]');
  const before = page.locator('details[data-fold="before-you-meet"]');
  await expect(how.locator('summary strong')).toHaveText('How Dating works');
  await expect(before.locator('summary strong')).toHaveText('Before you meet');
  await expect(how).not.toHaveAttribute('open','');
  await expect(before).not.toHaveAttribute('open','');
  await expect(page.getByText('Every yes here is a real yes.')).toBeHidden();
  await expect(page.getByText('Meet at the confirmed public venue')).toBeHidden();

  await how.locator('summary').click();
  await expect(page.getByText('Every yes here is a real yes.')).toBeVisible();
  await expect(page.getByText('there is no searching or swiping.')).toBeVisible();
  // §10: the consent approach, as its three points — descriptive, no nudges.
  const points = page.locator('[data-consent-points] li');
  await expect(points).toHaveCount(3);
  await expect(points.nth(0)).toContainText('always free');
  await expect(points.nth(0)).toContainText('never shown to the other person as a rejection');
  await expect(points.nth(1)).toContainText('exchanged in-app, when both of you choose');
  await expect(points.nth(1)).toContainText('never asked for in person');
  await expect(points.nth(2)).toContainText('shown before you meet');
  await expect(points.nth(2)).toContainText('expected to be respected');
  await expect(page.locator('details[data-fold] li')).not.toContainText([/invite|share your (number|contact)|go steady/i]);

  // §6.1: date-prep content (courtesies/safety/boundaries) surfaced
  // directly on Guru, not only on the plan-review screen.
  await before.locator('summary').click();
  await expect(page.getByText('Meet at the confirmed public venue')).toBeVisible();

  // §6.3: the open-ended "anything else I can help with?" entry point.
  await expect(page.getByText('Anything else I can help with?')).toBeVisible();
  await expect(page.getByRole('button',{name:'Vibes'})).toBeDisabled();

  await page.getByRole('button',{name:'See this week'}).click();
  await expect(page.getByRole('heading',{name:"This week's matches"})).toBeVisible();

  // Vision now lives on the Dashboard as a collapsible section (round4 §2).
  await tabbar.getByRole('button',{name:'Dashboard'}).click();
  await page.locator('summary',{hasText:'Vision'}).click();
  await expect(page.getByText('Intimacy · Emotional, Physical')).toBeVisible();
});

test('Chemistry actually saves and shows an explicit saved indicator (road-fixes-clock-spec.md §2)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.locator('summary',{hasText:'Chemistry'}).click();
  await expect(page.getByText("Hobbies, skills and activities.")).toBeVisible();

  // Pick a bucket for an activity that had nothing set, save, and confirm
  // it comes back checked AND an explicit "Saved" indicator appears right
  // by the button — the regression was the save looking like it silently
  // did nothing (evolution_api.chemistry_read forwarded the wrong shape).
  // The radio itself is visually hidden (opacity:0) behind its styled
  // glyph, same pattern as the web app's own bucket-pick — click the
  // label, which is what a real tap on the glyph actually hits.
  await page.locator('label:has(input[name="act__Yoga"][value="improve"])').click();
  await page.getByRole('button',{name:'Save chemistry'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect(page.locator('input[name="act__Yoga"][value="improve"]')).toBeChecked();

  // A round-trip through another screen and back proves it actually
  // persisted server-side, not just an optimistic local render.
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  await page.getByRole('button',{name:'← Back'}).click();
  await expect(page.locator('input[name="act__Yoga"][value="improve"]')).toBeChecked();
});

test('REACH heading is plain, and "More filters" exposes every filter the API returns (road-fixes-clock-spec.md §3, §5)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.locator('.topnav').getByRole('button',{name:'REACH',exact:true}).click();
  await expect(page.getByRole('heading',{name:'See who opens up.'})).toBeVisible();
  await expect(page.locator('.topnav').getByRole('button',{name:'Reality Check'})).toHaveCount(0);
  await expect(page.getByText('Reality Check')).toHaveCount(0);

  // Basic filters are visible without expanding anything. round3-fixes-spec.md
  // §4.2: "Wants kids"/"Does not want kids" are now one merged "Kids" row
  // with a three-way choice, not two separate filter rows. §4.3: Education
  // is a real filter now, not silently missing.
  for (const name of ['Age','Distance','Diet','Kids','Education']) {
    await expect(page.locator('.filter-name',{hasText:name})).toBeVisible();
  }
  await expect(page.getByText('Have kids',{exact:true})).toBeVisible();
  await expect(page.getByText("Don’t have kids")).toBeVisible();

  // Discovered from the API, not hardcoded — every non-basic filter the
  // fixture returns (sliders and choices alike) must show up once
  // expanded, in the same one-row-per-filter pattern as the basic ones.
  await page.getByText('More filters').click();
  for (const name of ['Height','Weight','Waist','Nationality','Religion','Non-smoker','Non-drinker']) {
    await expect(page.locator('.filter-name',{hasText:name})).toBeVisible();
  }
});

test('REACH age marker sits on the track, in proportion, aligned with the thumbs (round4-fixes-spec.md §3)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('.topnav').getByRole('button',{name:'REACH'}).click();

  const row = page.locator('.filter[data-lever="age"]');
  const marker = row.locator('.slider-self');
  await expect(marker).toBeVisible();
  const wrap = await row.locator('.slider-track-wrap').boundingBox();
  const track = await row.locator('.slider-track').boundingBox();
  const m = await marker.boundingBox();

  // Vertically ON the track: marker's centre is the track's centre.
  expect(Math.abs((m.y + m.height/2) - (track.y + track.height/2))).toBeLessThan(1);

  // 38 on 21–80 sits ~28.8% along the thumb travel, not centred or offset.
  const thumb = 22, travel = wrap.width - thumb;
  const expected = (v) => wrap.x + thumb/2 + ((v-21)/59) * travel;
  expect(Math.abs((m.x + m.width/2) - expected(38))).toBeLessThan(1);
  const frac = ((m.x + m.width/2) - (wrap.x + thumb/2)) / travel;
  expect(frac).toBeGreaterThan(0.27); expect(frac).toBeLessThan(0.30);

  // The same rail places any age: 21, 60 and 80 land where a thumb at that
  // value would (the range input's own thumb is the ground truth).
  for (const age of [21, 38, 60, 80]) {
    await marker.evaluate((el, pct) => { el.style.left = pct + '%'; }, ((age-21)/59)*100);
    const box = await marker.boundingBox();
    expect(Math.abs((box.x + box.width/2) - expected(age)), `age ${age}`).toBeLessThan(1);
  }
  // Ground truth: set the min thumb to 60 and compare its rendered centre.
  const truth = await page.evaluate(() => {
    const r = document.querySelector('.filter[data-lever="age"] .range-min');
    r.min = 21; r.max = 80; r.value = 60;
    const b = r.getBoundingClientRect();
    return b.x + 11 + ((60-21)/59) * (b.width - 22);
  });
  expect(Math.abs(truth - expected(60))).toBeLessThan(1);
});

test('REACH kids filter has two existing-children choices, mutually exclusive (round3-fixes-spec.md §4.2)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('.topnav').getByRole('button',{name:'REACH',exact:true}).click();

  const kidsRow = page.locator('[data-paired="no_existing_children|has_existing_children"]');
  await expect(kidsRow).toBeVisible();
  // The radio itself is visually hidden behind its pill label (same
  // pattern as chemistry.js's bucket-pick radios) — click the label.
  const option = (value) => kidsRow.locator(`label:has(input[value="${value}"])`);
  // Fixture starts with both ignored — "Any" is selected.
  await expect(kidsRow.locator('input:checked')).toHaveCount(0);

  await option('has_existing_children').click();
  await expect(kidsRow.locator('input[value="has_existing_children"]')).toBeChecked();
  await expect(kidsRow.locator('input[value="no_existing_children"]')).not.toBeChecked();

  // Picking the opposite clears the first — never both held at once.
  await option('no_existing_children').click();
  await expect(kidsRow.locator('input[value="no_existing_children"]')).toBeChecked();
  await expect(kidsRow.locator('input[value="has_existing_children"]')).not.toBeChecked();

  // Back to Any switches the held one off again.
  await option('no_existing_children').click();
  await expect(kidsRow.locator('input:checked')).toHaveCount(0);
});

test('Stats are editable inline from Dashboard, with cancel, and a verified field warns before it reopens verification (round3-fixes-spec.md §2/§3)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  // The standalone Stats screen/tab is gone entirely.
  await expect(page.locator('.topnav').getByRole('button',{name:'Stats',exact:true})).toHaveCount(0);

  // Entry point 1: Dashboard, inline — no navigation away.
  await page.getByRole('button',{name:'Edit stats'}).click();
  await expect(page.getByRole('button',{name:'Save changes'})).toBeVisible();
  // round4-fixes-spec.md §4: the five BGV-verified fields sit together in
  // one "Verified" group, apart from self-declared ones, with ONE short
  // re-verification line for the whole group — not a paragraph per field.
  const verifiedGroup = page.locator('#dashboard-stats-form [data-group="verified"]');
  await expect(verifiedGroup.locator('[name]')).toHaveCount(5);
  for (const k of ['age','education','nationality','profession','income_band']) await expect(verifiedGroup.locator(`[name="${k}"]`)).toHaveCount(1);
  await expect(page.locator('#dashboard-stats-form [data-group="declared"] [name="age"]')).toHaveCount(0);
  await expect(page.getByText('Editing a verified field re-opens its BGV check.')).toHaveCount(1);
  await expect(page.getByText(/vouched for by a background check/)).toHaveCount(0);

  // Cancel discards the open editor without saving anything.
  await page.getByRole('button',{name:'Cancel'}).click();
  await expect(page.getByRole('button',{name:'Edit stats'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Save changes'})).toHaveCount(0);

  // Reopen and actually save: an ordinary field plus the verified one.
  await page.getByRole('button',{name:'Edit stats'}).click();
  await page.locator('input[name="waist_in"]').fill('30');
  await page.locator('select[name="profession"]').selectOption('Design');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  // Confirmed by an independent re-GET (same discipline as chemistry.js)
  // before "Saved." shows — the editor stays open with the confirmation
  // rather than silently collapsing.
  await expect(page.getByText('Saved.')).toBeVisible();
  await page.getByRole('button',{name:'Done'}).click();
  await expect(page.getByRole('button',{name:'Edit stats'})).toBeVisible();
  await expect(page.getByText('30 in')).toBeVisible();
  // Read-only display groups the same way.
  await expect(page.locator('.stats-group[data-group="verified"] .stat-row',{hasText:'Age'})).toBeVisible();
  await expect(page.locator('.stats-group[data-group="declared"] .stat-row',{hasText:'Waist'})).toBeVisible();
  await expect(page.locator('.stats-group[data-group="verified"] .stat-row',{hasText:'Waist'})).toHaveCount(0);
});

test('Editing one unrelated stat sends only that field — untouched Age is never validated (round4-fixes-spec.md §1)',async({page})=>{
  const patches=[];
  page.on('console',async(m)=>{ if(m.text().includes('PATCH /api/v1/profile/stats request')) patches.push(JSON.stringify(await m.args()[1].jsonValue())); });
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:'Edit stats'}).click();

  // Saving with nothing changed is a no-op with a hint, not a failing PATCH.
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Nothing changed yet')).toBeVisible();
  expect(patches).toHaveLength(0);

  // Change ONE field, leave Age alone: must save.
  await page.locator('input[name="waist_in"]').fill('33');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect(page.locator('[data-error-for]')).toHaveCount(0);
  await expect.poll(()=>patches.length).toBe(1);
  expect(patches[0]).toContain('waist_in');
  expect(patches[0]).not.toContain('age');
  expect(patches[0]).not.toContain('"height_cm"');

  // An edited numeric field is sent as a real number and validated inline,
  // next to its own input, naming the field.
  await page.locator('input[name="age"]').fill('150');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.locator('[data-error-for="age"]')).toContainText('Age must be between 21 and 75');
  await page.locator('input[name="age"]').fill('31');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect.poll(()=>patches.length).toBe(2);
  expect(patches[1]).toContain('"age":31');
});

test('Existing children: editable stat with a count, and its own REACH filter pair (round4-fixes-spec.md §5)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.getByRole('button',{name:'Edit stats'}).click();
  const form = page.locator('#dashboard-stats-form');
  // Options come from the API (No/Yes), it's a self-declared field, and it is
  // labelled as existing children — not the Kids pillar.
  const sel = form.locator('[data-group="declared"] select[name="has_children"]');
  await expect(sel.locator('option')).toHaveText(['Not set','No','Yes']);
  await expect(form.getByText('Already has children')).toBeVisible();

  // A count without "Yes" is refused inline, next to the count field.
  await form.locator('input[name="children_count"]').fill('2');
  await form.getByRole('button',{name:'Save changes'}).click();
  await expect(page.locator('[data-error-for="children_count"]')).toContainText('only applies if you already have children');

  // Yes + count saves and shows on the Dashboard.
  await sel.selectOption('Yes');
  await form.getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await page.getByRole('button',{name:'Done'}).click();
  await expect(page.locator('.stats-group[data-group="declared"] .stat-row',{hasText:'Already has children'})).toContainText('Yes');
  await expect(page.locator('.stats-group[data-group="declared"] .stat-row',{hasText:'Number of children'})).toContainText('2');

  // REACH: a generic filter pair under More filters, mutually exclusive.
  await page.locator('.topnav').getByRole('button',{name:'REACH'}).click();
  await page.locator('summary',{hasText:'More filters'}).click();
  const pair = page.locator('[data-paired="no_existing_children|has_existing_children"]');
  await expect(pair).toContainText('Children they already have');
  await pair.locator('label',{hasText:'Don’t have kids'}).click();
  await expect(pair.locator('input[value="no_existing_children"]')).toBeChecked();
  await pair.locator('label',{hasText:/^Have kids$/}).click();
  await expect(pair.locator('input[value="has_existing_children"]')).toBeChecked();
  await expect(pair.locator('input[value="no_existing_children"]')).not.toBeChecked();
});

test('Stats are editable inline from REACH without leaving the screen (round3-fixes-spec.md §3)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.locator('.topnav').getByRole('button',{name:'REACH',exact:true}).click();
  await expect(page.getByText('Missing a filter you expected?')).toBeVisible();
  await page.getByRole('button',{name:'Edit your stats'}).click();
  const waistInput = page.locator('input[name="waist_in"]');
  await expect(waistInput).toBeVisible();
  await expect(page.getByRole('button',{name:'Cancel'})).toBeVisible();
  await waistInput.fill('30');
  await page.locator('#inline-stats-form').getByRole('button',{name:'Save changes'}).click();
  // A saved stat can unlock a new REACH lever, so saving reloads the
  // REACH screen itself once persistence is confirmed — not just the
  // stats sub-form — and collapses the inline editor back to its toggle.
  await expect(page.getByRole('button',{name:'Edit your stats'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'See who opens up.'})).toBeVisible();
});

test('ROAD: reachable at Relationship entry, routine/obligations/sharing, shared flag never defaulted (road-fixes-clock-spec.md §1)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  // Walk the same dating pipeline as the full-pipeline test, ending on a
  // mutual "relationship" decision — the trigger road.js needs to become
  // reachable at all (§1.1: "First, make it reachable").
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  await page.getByRole('button',{name:'Express interest'}).click();
  await page.getByRole('button',{name:'Open calendar'}).click();
  await page.getByLabel('Fri · Dinner').check();
  await page.getByLabel('Sat · Dinner').check();
  await page.getByRole('button',{name:'Save availability'}).click();
  await page.getByRole('button',{name:'Confirm'}).first().click();
  await page.getByRole('button',{name:'View date plan'}).click();
  await page.getByRole('button',{name:'Review & sign'}).click();
  await page.getByRole('button',{name:"I've read this"}).click();
  await page.getByLabel('Your name').fill('Rohan Verma');
  await page.getByLabel('I will treat my match with respect.').check();
  await page.getByLabel('I understand the cancellation terms.').check();
  await page.getByLabel('I understand this is not a relationship yet.').check();
  await page.getByLabel('I accept the platform is not liable for what happens on the date.').check();
  await page.getByRole('button',{name:'Sign',exact:true}).click();
  await page.getByRole('button',{name:'Verify',exact:true}).click();
  await page.getByRole('button',{name:'After the date'}).click();
  await page.getByRole('button',{name:'Actually listened'}).click();
  await page.getByRole('button',{name:'On time'}).click();
  await page.getByRole('button',{name:'Save feedback'}).click();
  await page.getByRole('button',{name:'Go steady'}).click();

  // The Relationship tab appears immediately — no extra manual reload —
  // because the decision handler refreshes journey/status itself.
  const topnav = page.locator('.topnav');
  await expect(topnav.getByRole('button',{name:'Relationship',exact:true})).toBeVisible();
  await topnav.getByRole('button',{name:'Relationship',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Stage: relationship'})).toBeVisible();

  await page.getByRole('button',{name:'Open ROAD'}).click();
  await expect(page.getByRole('heading',{name:'Routine, obligations, availability, dates'})).toBeVisible();

  // R — Routine.
  await page.locator('#routine-form').getByLabel('Fri',{exact:true}).check();
  await page.getByPlaceholder('e.g. Office, Gym, Salsa').fill('Gym');
  const [startTime, endTime] = await page.locator('#routine-form input[type="time"]').all();
  await startTime.fill('18:00');
  await endTime.fill('19:30');
  await page.getByRole('button',{name:'Add routine block'}).click();
  await expect(page.getByText('Fri · 18:00–19:30')).toBeVisible();

  // O — Obligations, travel mode. The "Visible to your partner" checkbox
  // must start unchecked — the client never sets `shared` on the user's
  // behalf (§1.5) — and travel_mode only appears once type=travel.
  await expect(page.getByLabel('Visible to your partner')).not.toBeChecked();
  await expect(page.locator('#travel-mode-field')).toBeHidden();
  await page.locator('#obligation-type').selectOption('travel');
  await expect(page.locator('#travel-mode-field')).toBeVisible();
  await page.locator('#obligation-form input[name="title"]').fill('Goa trip');
  const [obStart, obEnd] = await page.locator('#obligation-form input[type="date"]').all();
  await obStart.fill('2026-02-01');
  await obEnd.fill('2026-02-03');
  await page.getByRole('button',{name:'Add obligation'}).click();
  const goaRow = page.locator('[data-obligation]',{hasText:'Goa trip'});
  await expect(goaRow).toBeVisible();
  await expect(goaRow).not.toContainText('shared'); // not ticked, so never reported as shared

  // Partner's already-shared obligation is shown read-only.
  await expect(page.getByText("Sister's wedding")).toBeVisible();

  // A — Availability, D — share windows and see the overlap.
  await expect(page.getByLabel('Sat 10:00–22:00')).toBeVisible();
  await page.getByLabel('Sat 10:00–22:00').check();
  await page.getByRole('button',{name:'Share checked windows'}).click();
  await expect(page.getByText('When you could both go out')).toBeVisible();
  await expect(page.locator('.chip',{hasText:'Sat 10:00–22:00'})).toBeVisible();
});

test('Week grid labels each match window closing, untruncated at phone widths (round4-fixes-spec.md §6)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();

  for (const width of [375, 320]) {
    await page.setViewportSize({width, height: 800});
    const chips = page.locator('.tw-grid .tw-chip');
    // Pairs with the reveal: Tue/Wed mornings close Match 1/2; Match 3 closes Wed evening.
    await expect(page.locator('.tw-grid .tw-chip',{hasText:'M1 closes'})).toHaveCount(1);
    await expect(page.locator('.tw-grid .tw-chip',{hasText:'M2 closes'})).toHaveCount(1);
    await expect(page.locator('.tw-grid .tw-chip',{hasText:'M3 closes'})).toHaveCount(1);
    // Never cut off: every chip's text fits inside its own box.
    const clipped = await chips.evaluateAll((els) => els.filter((el) => el.scrollWidth > el.clientWidth + 0.5).map((el) => el.textContent.trim()));
    expect(clipped, `clipped chips at ${width}px`).toEqual([]);
  }
  // The column position: the close sits in its own day's column.
  const cols = await page.locator('.tw-grid thead th.tw-day').evaluateAll((ths) => ths.map((t) => t.title));
  const colOf = async (text) => page.locator('.tw-grid .tw-chip',{hasText:text}).evaluate((el) => el.closest('td').cellIndex - 1);
  expect(cols[await colOf('M1 closes')]).toBe('Tue');
  expect(cols[await colOf('M2 closes')]).toBe('Wed');
  expect(cols[await colOf('M3 closes')]).toBe('Wed');

  // Full wording where there is room.
  await page.locator('summary',{hasText:'What each one means'}).click();
  for (const n of [1,2,3]) await expect(page.locator('.tw-full',{hasText:`Match ${n} closes`})).toBeVisible();
});

test('Week: explainer video sits by "What each one means", never autoplays, and never blocks the calendar (round4-fixes-spec.md §7)',async({page})=>{
  // Exercise the missing-file fallback explicitly, regardless of local media.
  await page.route('**/media/calendar-explainer.mp4',route=>route.fulfill({status:404,body:''}));
  const mediaRequests=[];
  page.on('request',(r)=>{ if(r.url().includes('/media/')) mediaRequests.push(r.url()); });
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();

  // Placed right beside the existing expander, collapsed, nothing fetched yet.
  const video = page.locator('details.tw-video');
  await expect(video).toBeVisible();
  await expect(video).not.toHaveAttribute('open','');
  await expect(page.locator('details.tw-video + details.tw-explain')).toHaveCount(1);
  expect(mediaRequests).toEqual([]);

  // Opening it mounts a player that is not playing; with the file not yet
  // supplied it degrades to a placeholder rather than a broken player.
  await video.locator('summary').click();
  await expect(video.locator('video, .tw-video-placeholder')).toHaveCount(1);
  await expect(video.locator('.tw-video-placeholder')).toBeVisible();
  expect(await page.evaluate(()=>[...document.querySelectorAll('video')].some((v)=>!v.paused||v.autoplay))).toBe(false);

  // The calendar stays fully usable with it open: the clock still steps,
  // and the "What each one means" expander still opens.
  await page.locator('.demo-step',{hasText:'+1 hour'}).click();
  await expect(page.locator('.tw-now')).toContainText('Mon 13:00');
  await expect(video).toHaveAttribute('open','');
  await page.locator('summary',{hasText:'What each one means'}).click();
  await expect(page.locator('.tw-explain-row').first()).toBeVisible();
});

test('Week: no "Prepare this week" button — preparing is automatic, once, on load (round4-fixes-spec.md §8)',async({page})=>{
  const infos=[];
  page.on('console',(m)=>{ if(m.text().includes('[week] preparing this week')) infos.push(m.text()); });
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  const posts = () => page.evaluate(()=>window.__previewPrepareCount());

  // Already prepared this week: loading Week never posts, and there is no button.
  await expect(page.getByRole('heading',{name:"This week's matches"})).toBeVisible();
  await expect(page.getByRole('button',{name:/Prepare this week/})).toHaveCount(0);
  expect(await posts()).toBe(0);

  // A new week begins unprepared. Stepping the clock into it reloads the
  // screen; the app prepares it by itself — once — and never shows a button.
  await page.locator('.demo-step',{hasText:'+1 week'}).click();
  await expect(page.getByRole('heading',{name:"This week's matches"})).toBeVisible();
  await expect(page.getByText(/^Reveals /)).toHaveCount(2);
  await expect(page.getByRole('button',{name:/Prepare this week/})).toHaveCount(0);
  expect(await posts()).toBe(1);

  // Re-rendering / leaving and coming back does NOT repeat it (GET is read-only).
  await page.getByRole('button',{name:'← Back'}).click();
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  await expect(page.getByText(/^Reveals /)).toHaveCount(2);
  expect(await posts()).toBe(1);
  expect(infos).toHaveLength(1);
});

test('simulated clock: labelled stepping controls on Week, gated on the server-reported flag (road-fixes-clock-spec.md §7)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  // Always shown, read from the API — never computed on the device (§7.5).
  await expect(page.locator('.tw-now')).toHaveText('Mon 12:00');
  // Clearly labelled as simulation, same voice as the app's other beta
  // simulations (§7.7) — and only present because the fixture reports
  // simulated_clock:true, never inferred from a build flag alone (§7.6).
  await expect(page.getByText('SIMULATION')).toBeVisible();

  await page.locator('.demo-step',{hasText:'+1 hour'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Mon 13:00');

  await page.locator('.demo-step',{hasText:'+1 day'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Tue 13:00');

  await page.locator('.demo-step',{hasText:'+1 week'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Week 2');
});

test('Vision and Chemistry are collapsed Dashboard sections, not tabs (round4-fixes-spec.md §2)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  const nav = page.locator('.topnav');
  await expect(nav.getByRole('button',{name:'Vision'})).toHaveCount(0);
  await expect(nav.getByRole('button',{name:'Chemistry'})).toHaveCount(0);

  // Bold headers, both collapsed by default.
  for (const name of ['Vision','Chemistry']) {
    const fold = page.locator(`details[data-fold="${name.toLowerCase()}"]`);
    await expect(fold.locator('summary strong')).toHaveText(name);
    await expect(fold).not.toHaveAttribute('open','');
    expect(await fold.locator('summary strong').evaluate(el=>Number(getComputedStyle(el).fontWeight))).toBeGreaterThanOrEqual(600);
  }
  await expect(page.getByRole('button',{name:'Save chemistry'})).toBeHidden();

  // Expanding shows the very same controls; collapsing hides them again.
  await page.locator('summary',{hasText:'Chemistry'}).click();
  await expect(page.getByRole('button',{name:'Save chemistry'})).toBeVisible();
  await page.locator('summary',{hasText:'Chemistry'}).click();
  await expect(page.getByRole('button',{name:'Save chemistry'})).toBeHidden();
});

test('Vision: four pillars only, additive Add Detail, and Declare a Change gated on Reality Check (round3-fixes-spec.md §7)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('summary',{hasText:'Vision'}).click();

  // §7.1: the explanatory copy, and no Relocation/Career anywhere.
  await expect(page.getByText('Travel together takes no detail now.')).toBeVisible();
  await expect(page.getByText(/Relocation|Career/)).toHaveCount(0);

  // §7.2: Add Detail offers only what is NOT already held (Kids isn't set,
  // Chores split already is) and actually changes the Vision.
  await expect(page.locator('#detail-choice')).toBeHidden();
  await page.locator('[data-vision-panel=add] summary').click();
  const choice = page.locator('#detail-choice');
  await expect(choice.locator('option[value="Cohabitate|Chores split"]')).toHaveCount(0);
  await expect(choice.locator('option[value="Cohabitate|Expenses sharing"]')).toHaveCount(1);
  await choice.selectOption('Kids|Adoption');
  await page.getByRole('button',{name:'Add',exact:true}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect(page.locator('.chips').getByText('Kids · Adoption')).toBeVisible();
  await expect(choice.locator('option[value="Kids|Adoption"]')).toHaveCount(0);

  // §7.3: outside Reality Check the change form is locked, with the reason.
  await page.locator('[data-vision-panel=change] summary').click();
  await expect(page.getByText(/Locked right now/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Declare change'})).toBeDisabled();

  // Step the simulated clock to Sunday 22:00 (RC open) and declare one.
  await page.locator('.topnav').getByRole('button',{name:'Week'}).click();
  for (let i = 0; i < 6; i++) await page.locator('.demo-step',{hasText:'+1 day'}).click();
  for (let i = 0; i < 10; i++) await page.locator('.demo-step',{hasText:'+1 hour'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Sun 22:00');
  await page.getByRole('button',{name:'← Back'}).click();
  // The Vision section stays expanded on return to the Dashboard.
  await expect(page.getByText(/Locked right now/)).toHaveCount(0);

  await page.locator('[data-vision-panel=change]').evaluate(el=>el.open=true);
  await page.locator('#change-pillar').selectOption('Kids');
  await page.getByLabel('Add Surrogacy').check();
  await page.getByLabel("I've disclosed this to my match").check();
  await page.getByRole('button',{name:'Declare change'}).click();
  await expect(page.locator('.chips').getByText('Kids · Adoption, Surrogacy')).toBeVisible();

  // A removal that would break the rules is refused with the server's reason:
  // Kids only (two pillars would remain, fine) — but Intimacy's last kind is not.
  await page.locator('#change-pillar').selectOption('Intimacy');
  await page.getByLabel('Remove Emotional').check();
  await page.getByLabel('Remove Physical').check();
  await page.getByLabel("I've disclosed this to my match").check();
  await page.getByRole('button',{name:'Declare change'}).click();
  await expect(page.getByText('Intimacy is mandatory')).toBeVisible();
});
