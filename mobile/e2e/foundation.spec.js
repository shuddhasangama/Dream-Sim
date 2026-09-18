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
  await expect(page.locator('.guru-avatar')).toHaveText('G');
  await expect(page.getByText('Your next chapter starts here')).toBeVisible();
  await page.getByRole('button',{name:'See this week'}).click();
  await expect(page.getByRole('heading',{name:"This week's matches"})).toBeVisible();

  await tabbar.getByRole('button',{name:'Vision'}).click();
  await expect(page.getByRole('heading',{name:"Where you're headed"})).toBeVisible();
  await expect(page.getByText('Intimacy · Emotional')).toBeVisible();

  // Adding detail is always allowed — no disclosure gate.
  await page.getByLabel('Detail').fill('Would like at least one child, open to timing');
  await page.getByRole('button',{name:'Add',exact:true}).click();
  await expect(page.getByText('Would like at least one child, open to timing')).toBeVisible();

  // Declaring a change is disclosure-gated client-side (required checkbox) —
  // §2.6/evolution_service.add_vision: an undisclosed reversal is refused.
  await page.getByLabel('From').fill('Wanted kids');
  await page.getByLabel('To',{exact:true}).fill('Not sure about kids anymore');
  await page.getByRole('button',{name:'Declare change'}).click();
  await expect(page.getByRole('heading',{name:'History'})).toHaveCount(0);

  await page.getByLabel("I've disclosed this to my match").check();
  await page.getByRole('button',{name:'Declare change'}).click();
  await expect(page.getByRole('heading',{name:'History'})).toBeVisible();
  await expect(page.getByText('Children: Wanted kids → Not sure about kids anymore')).toBeVisible();
});

test('Chemistry actually saves and shows an explicit saved indicator (road-fixes-clock-spec.md §2)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  await page.locator('.topnav').getByRole('button',{name:'Chemistry'}).click();
  await expect(page.getByRole('heading',{name:"What you'd actually do together"})).toBeVisible();

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
  await page.locator('.topnav').getByRole('button',{name:'Dashboard'}).click();
  await page.locator('.topnav').getByRole('button',{name:'Chemistry'}).click();
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

  // Basic filters are visible without expanding anything.
  for (const name of ['Age','Distance','Diet','Wants kids','Does not want kids']) {
    await expect(page.locator('.filter-name',{hasText:name})).toBeVisible();
  }

  // Discovered from the API, not hardcoded — every non-basic filter the
  // fixture returns (sliders and choices alike) must show up once
  // expanded, in the same one-row-per-filter pattern as the basic ones.
  await page.getByText('More filters').click();
  for (const name of ['Height','Weight','Waist','Nationality','Religion','Non-smoker','Non-drinker']) {
    await expect(page.locator('.filter-name',{hasText:name})).toBeVisible();
  }
});

test('Stats are editable from Dashboard and inline from REACH (road-fixes-clock-spec.md §6)',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();

  // Entry point 1: Dashboard.
  await page.getByRole('button',{name:'Edit stats'}).click();
  await expect(page.getByRole('heading',{name:'Your stats'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Save changes'})).toBeVisible();
  // Verified fields are held, never directly editable — re-checking is
  // clearly flagged as dropping them out of "verified" in the meantime.
  await expect(page.getByText('Verified — held')).toBeVisible();
  await expect(page.getByText('drops it out of "verified"')).toBeVisible();

  // Entry point 2: inline from REACH, without navigating away.
  await page.locator('.topnav').getByRole('button',{name:'REACH',exact:true}).click();
  await expect(page.getByText('Missing a filter you expected?')).toBeVisible();
  await page.getByRole('button',{name:'Edit your stats'}).click();
  const waistInput = page.locator('input[name="waist_in"]');
  await expect(waistInput).toBeVisible();
  await waistInput.fill('30');
  await page.locator('#inline-stats-form').getByRole('button',{name:'Save changes'}).click();
  // Saving collapses the inline editor back to its toggle and reloads
  // the REACH screen itself (a saved stat can unlock a new lever).
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
