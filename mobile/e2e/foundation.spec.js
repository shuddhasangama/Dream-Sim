import {test,expect} from '@playwright/test';
test('phone layout, wrong code, dashboard, refresh and sign out without external calls',async({page})=>{
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
  await page.getByRole('button',{name:'Refresh dashboard'}).click();
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
  const tabbar = page.locator('.tabbar');
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

  const tabbar = page.locator('.tabbar');
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

  await page.locator('.tabbar').getByRole('button',{name:'Week'}).click();
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

  const tabbar = page.locator('.tabbar');
  await tabbar.getByRole('button',{name:'Guru'}).click();
  // Guru never nudges escalation — it's the same read-only next-action
  // projection the dashboard's own "NEXT FOR YOU" card already shows.
  await expect(page.getByRole('heading',{name:'Your next chapter starts here'})).toBeVisible();
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
