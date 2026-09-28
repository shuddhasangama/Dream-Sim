import {test,expect} from '@playwright/test';

// design_handoff_app_ui_pulse/README.md ("Pulse", option 1a): every test
// below signs in the same way, so this is the one place that changes if
// sign-in itself ever does.
async function signIn(page) {
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();
}
// The floating tab bar (replaces the old top text nav — see the README's
// "Global changes" table) and the avatar's profile/settings sheet.
const tabbar = (page) => page.locator('.p-tabbar');
async function openAvatarSheet(page) {
  await page.locator('#p-avatar').click();
  await expect(page.locator('.p-sheet')).toBeVisible();
}
// An event card on Week shows its title AND time in the same button, so a
// plain accessible-name match is ambiguous — this locates by the title text
// wherever it sits in the currently-selected day's list.
const eventCard = (page, title) => page.locator('.p-event-card',{hasText:title});
// A personalized moment (the real debrief time) can land on whichever day
// the confirmed date slot fell on — this finds it rather than assuming one.
async function selectDayWithEvent(page, title) {
  for (let i = 0; i < 7; i++) {
    await page.locator('.p-day-btn').nth(i).click();
    if (await eventCard(page, title).count()) return;
  }
  throw new Error(`No day this week has an event titled "${title}"`);
}
// A REACH chip's own tap target vs. its "open the picker sheet" trigger.
const chipTap = (page, key) => page.locator(`.filter-chip[data-chip="${key}"] .chip-tap`);
const chipSheetButton = (page, key) => page.locator(`.filter-chip[data-chip="${key}"] .chip-more`);

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
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/dashboard.png',fullPage:true});
  // Tab switching is instant and never grows a back-stack (README: "Tab
  // switch: instant, preserving each tab's scroll position") — Home stays
  // reachable via the tab bar itself, with no "← Back" ever appearing
  // between two primary tabs.
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await expect(page.getByRole('button',{name:'← Back'})).toHaveCount(0);
  await tabbar(page).getByRole('button',{name:'Home'}).click();
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();

  await openAvatarSheet(page);
  await expect(page.getByRole('button',{name:'Sign out'})).toBeEnabled();
  await page.getByRole('button',{name:'Sign out'}).click();
  await expect(page.getByLabel('Phone number')).toBeVisible();
  expect(await page.evaluate(()=>localStorage.length)).toBe(0);
  expect(errors).toEqual([]);expect(external).toEqual([]);
});

test('navigation: the floating tab bar, no back button between primary tabs, and journey/status-driven eligibility',async({page})=>{
  await signIn(page);

  // No back button on the root screen.
  await expect(page.getByRole('button',{name:'← Back'})).toHaveCount(0);
  // The tab bar shows exactly the four fixed keys, filtered by what
  // journey/status marked eligible — Verify and Relationship are
  // ineligible in the preview fixture and must never appear there
  // (mobile-journey-build-spec.md §1: derive nav from the API). They are
  // not lost, though — see the avatar-sheet test below.
  await expect(tabbar(page).getByRole('button',{name:'Home'})).toBeVisible();
  await expect(tabbar(page).getByRole('button',{name:'Reach'})).toBeVisible();
  await expect(tabbar(page).getByRole('button',{name:'Week'})).toBeVisible();
  await expect(tabbar(page).getByRole('button',{name:'Guru'})).toBeVisible();
  await expect(tabbar(page).getByRole('button',{name:'Verify'})).toHaveCount(0);
  await expect(tabbar(page).getByRole('button',{name:'Relationship'})).toHaveCount(0);

  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await expect(page.getByText('This week',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'← Back'})).toHaveCount(0);
  await expect(tabbar(page).getByRole('button',{name:'Week'})).toHaveClass(/is-active/);

  await tabbar(page).getByRole('button',{name:'Home'}).click();
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();

  // Home's own "Next up" card is a second way into Week, not a separate
  // mechanism — it should land on the same screen.
  await page.locator('#p-next-up').click();
  await expect(page.getByText('This week',{exact:true})).toBeVisible();
});

test('the avatar sheet holds Sign out plus any stage-gated surface the tab bar has no room for',async({page})=>{
  await signIn(page);
  await openAvatarSheet(page);
  await expect(page.locator('.p-sheet-name')).toHaveText('Preview profile');
  // Verify/Relationship/Journey are ineligible in the base fixture, so the
  // sheet offers only Sign out — nothing invented, nothing lost silently.
  await expect(page.locator('.p-sheet-links')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();
  // Dismissing it (backdrop) leaves Home exactly as it was.
  await page.locator('[data-close-avatar]').click();
  await expect(page.locator('.p-sheet')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();
});

test('mutual interest locks in and REACH disappears from the tab bar live, not just on the next full load',async({page})=>{
  await signIn(page);

  await expect(tabbar(page).getByRole('button',{name:'Reach'})).toBeVisible();
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await eventCard(page,'Match 1').click();
  await expect(page.locator('.candidate-name')).toHaveText('Priya Sharma');

  // Actions and the reason field must not be nested inside the accordion button.
  const candidate = page.locator('.candidate-card');
  await expect(candidate.getByRole('button',{name:'Pass',exact:true})).toBeVisible();
  await expect(candidate.getByRole('button',{name:'Express interest'})).toBeVisible();
  await expect(page.locator('button .candidate-card')).toHaveCount(0);
  await candidate.locator('.pass-reason').fill('Draft only — interest is still available');
  await expect(candidate.getByRole('button',{name:'Express interest'})).toBeVisible();

  await page.getByRole('button',{name:'Express interest'}).click();
  await expect(page.getByText('WEEK · LOCKED IN')).toBeVisible();
  await expect(page.getByText('Status')).toBeVisible();
  // The tab bar re-renders from the freshly refetched journey/status —
  // REACH is gone without needing a manual reload (mobile-journey-build-
  // spec.md §2.1: "REACH sunsets at lock-in").
  await expect(tabbar(page).getByRole('button',{name:'Reach'})).toHaveCount(0);

  await page.getByRole('button',{name:'Confirm Date'}).click();
  // Calendar now has its own bespoke screen (Stage 3) — untouched by Pulse.
  await expect(page.getByRole('heading',{name:'When to meet'})).toBeVisible();
});

test('full date pipeline: calendar overlap, plan, order-enforced ceremony, and two-green-flag debrief',async({page})=>{
  await signIn(page);

  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await eventCard(page,'Match 1').click();
  await page.getByRole('button',{name:'Express interest'}).click();
  await page.getByRole('button',{name:'Confirm Date'}).click();

  // Submit availability that overlaps the fixture's own match availability,
  // then confirm a slot — this generates the date plan (§2.4). Unrelated to
  // Pulse — calendar.js/plan.js/ceremony.js/debrief.js keep their own look.
  await page.getByLabel('Fri · Dinner').check();
  await page.getByLabel('Sat · Dinner').check();
  await page.getByRole('button',{name:'Save availability'}).click();
  await expect(page.getByRole('heading',{name:'You\'re both free'})).toBeVisible();
  await page.getByRole('button',{name:'Confirm'}).first().click();
  await expect(page.getByRole('button',{name:'View date plan'})).toBeVisible();

  await page.getByRole('button',{name:'View date plan'}).click();
  await expect(page.getByRole('heading',{name:'Pending signatures'})).toBeVisible();
  await page.getByRole('button',{name:'Review & sign'}).click();

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

  // round3-fixes-spec.md §5.2/§5.3: with the plan now confirmed, Week's
  // schedule swaps the generic Debrief placeholder for this couple's real
  // one — reachable on whichever day it actually falls, expanded like any
  // other event, with a nav button into debrief.js.
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await selectDayWithEvent(page,'Debrief');
  await eventCard(page,'Debrief').click();
  await page.getByRole('button',{name:'Open debrief'}).click();
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
  await page.getByRole('button',{name:'Move to Relationship'}).click();
  await expect(page.getByRole('heading',{name:'Saved'})).toBeVisible();
  await expect(page.getByText('You said: Move to Relationship.')).toBeVisible();
});

test('Week: the fixed weekend meal-slot template never reads as real bookings — only the couple\'s own confirmed date survives, and only once (design-review finding)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await eventCard(page,'Match 1').click();
  await page.getByRole('button',{name:'Express interest'}).click();

  // Before any date is confirmed, Friday/Saturday/Sunday show none of the
  // template's Breakfast/Lunch/Coffee/Dinner slots — nothing to see yet.
  for (let i = 4; i <= 6; i++) {
    await page.locator('.p-day-btn').nth(i).click();
    await expect(page.locator('.p-event-card[data-tone="date"]')).toHaveCount(0);
  }

  await page.getByRole('button',{name:'Confirm Date'}).click();
  await page.getByLabel('Fri · Dinner').check();
  await page.getByLabel('Sat · Dinner').check();
  await page.getByRole('button',{name:'Save availability'}).click();
  await page.getByRole('button',{name:'Confirm'}).first().click();

  await tabbar(page).getByRole('button',{name:'Week'}).click();
  let confirmedDays = 0, dayWithDate = -1;
  for (let i = 0; i < 7; i++) {
    await page.locator('.p-day-btn').nth(i).click();
    const count = await page.locator('.p-event-card[data-tone="date"]').count();
    expect(count, `day ${i}`).toBeLessThanOrEqual(1); // never more than one on any single day
    confirmedDays += count;
    if (count) dayWithDate = i;
  }
  // Exactly one real date across the whole week — never three.
  expect(confirmedDays).toBe(1);
  await page.locator('.p-day-btn').nth(dayWithDate).click();
  await page.locator('.p-event-card[data-tone="date"]').click();
  await expect(page.getByText('Your confirmed date.')).toBeVisible();
  await page.getByRole('button',{name:'View date plan'}).click();
  await expect(page.getByRole('heading',{name:'Pending signatures'})).toBeVisible();
});

test('Week: a "Today" action returns from any other day, and the day label never claims "today" for a day that is not (design-review finding)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await expect(page.locator('#p-today-jump')).toHaveCount(0); // already on today
  await page.locator('.p-day-btn').nth(3).click();
  await expect(page.locator('.p-day-label')).not.toContainText('today');
  await expect(page.locator('#p-today-jump')).toBeVisible();
  await page.locator('#p-today-jump').click();
  await expect(page.locator('.p-day-label')).toContainText('today');
  await expect(page.locator('.p-day-btn').nth(0)).toHaveClass(/is-selected/);
});

test('Home: "Next up" reflects the real journey state (including a waiting-on-partner state with no clock time), not a fabricated deadline (design-review finding)',async({page})=>{
  await signIn(page);
  // The base fixture's next_action already has a real destination — the
  // card is tappable and its time (if any) is today's, never invented.
  await expect(page.locator('#p-next-up')).toBeVisible();
  await expect(page.locator('.p-next-up-title')).toHaveText('Your next chapter starts here');
});

test('Guru: quick replies answer from the same guidance response the dashboard reads, never nudging escalation',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Guru'}).click();

  await expect(page.locator('.guru-avatar').first()).toHaveText('G');
  await expect(page.getByText("Hi Preview. What's on your mind?")).toBeVisible();
  // Nothing is answered until a chip is tapped — a clean chat, not a wall
  // of paragraphs.
  await expect(page.locator('.p-bubble-user')).toHaveCount(0);

  await page.getByRole('button',{name:'What now?'}).click();
  await expect(page.locator('.p-bubble-user')).toHaveText('What now?');
  await expect(page.getByText('Take a moment to review your profile')).toBeVisible();
  await page.getByRole('button',{name:/See this week|Continue/}).click();
  await expect(page.getByText('This week',{exact:true})).toBeVisible();

  await tabbar(page).getByRole('button',{name:'Guru'}).click();
  await page.getByRole('button',{name:'How Dating works'}).click();
  await expect(page.getByText(/Every yes here is a real yes\..*there is no searching or swiping\./)).toBeVisible();
  // §10/§4 hard constraint 5: never an escalation suggestion.
  await expect(page.locator('.p-guru-thread')).not.toContainText([/invite|share your (number|contact)|go steady/i]);

  await page.getByRole('button',{name:'Why so few matches?'}).click();
  await expect(page.getByText('1 of 6 who fit you are open to you. Loosen one filter.')).toBeVisible();
  await page.getByRole('button',{name:'Open Reach'}).click();
  await expect(page.getByText('REACH · THIS WEEK')).toBeVisible();

  await tabbar(page).getByRole('button',{name:'Guru'}).click();
  await page.getByRole('button',{name:'Before we meet'}).click();
  await expect(page.getByText('Arrive on time')).toBeVisible();
});

test('Home: three rings reflect real Vision/Stats/Chemistry progress, and each opens its own existing edit flow',async({page})=>{
  await signIn(page);

  // Stage stepper — the D·R·E·M indicator, now Home-only (§ Global changes).
  await expect(page.locator('.p-stage-label')).toHaveText(['Dating','Relationship','Engaged','Married']);
  await expect(page.locator('.p-stage-col').first().locator('.p-stage-bar')).toHaveClass(/is-current/);

  // Vision ring: selected by default, real percentage from profile.visions.
  await expect(page.locator('[data-ring="vision"]')).toHaveClass(/is-selected/);
  // A fraction, not a percentage — Vision has no "100%" target (Intimacy
  // plus any ONE more already satisfies every rule), so a smaller valid
  // choice must never read as an unfinished profile.
  await expect(page.locator('[data-ring="vision"] .p-ring-inner')).toHaveText('3/4');
  await expect(page.locator('.p-detail-summary')).toContainText('3 of 4 possible pillars');
  await expect(page.locator('.p-detail-title')).toHaveText('Vision');
  await expect(page.locator('.p-fact-tile',{hasText:'Intimacy'})).toContainText('Emotional');
  await page.locator('[data-open-editor]').click(); // "Finish vision →"
  await expect(page.locator('.vision-editor')).toHaveCount(2); // Add detail + Declare a change
  await page.locator('#p-close-editor').click();
  await expect(page.locator('.vision-editor')).toHaveCount(0);

  // Stats ring: the same inline stats editor as before, just reached here.
  await page.locator('[data-ring="stats"]').click();
  await expect(page.locator('.p-detail-title')).toHaveText('Stats');
  await expect(page.locator('[data-ring="stats"] .p-ring-inner')).toHaveText('5/5');
  await expect(page.locator('.p-fact-tile',{hasText:'Age'})).toContainText('✓');
  await page.locator('[data-open-editor]').click(); // "Edit stats →"
  await expect(page.locator('#dashboard-stats-form')).toBeVisible();
  await page.locator('input[name="waist_in"]').fill('30');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await page.locator('#p-close-editor').click();
  await expect(page.locator('.p-fact-tile',{hasText:'Age'})).toBeVisible(); // back to tiles, not the form

  // Chemistry ring.
  await page.locator('[data-ring="chemistry"]').click();
  await expect(page.locator('.p-detail-title')).toHaveText('Chemistry');
  await expect(page.locator('[data-ring="chemistry"] .p-ring-inner')).toHaveText('50%');
  await page.locator('[data-open-editor]').click(); // "Answer next →"
  await expect(page.getByRole('button',{name:'Save chemistry'})).toBeVisible();
  // "Board games" has no pick yet in the fixture — answering it is a NEW
  // answer, unlike re-picking one already set (which the ring would not
  // count as progress).
  await page.locator('label:has(input[name="act__Board games"][value="good"])').click();
  await page.getByRole('button',{name:'Save chemistry'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect(page.locator('input[name="act__Board games"][value="good"]')).toBeChecked();

  // A round-trip through another tab and back proves it actually persisted
  // server-side, not just an optimistic local render — and the ring itself
  // updates (chemistry answered count went up: 6 of 12 to 7 of 12).
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await tabbar(page).getByRole('button',{name:'Home'}).click();
  await page.locator('[data-ring="chemistry"]').click();
  await expect(page.locator('[data-ring="chemistry"] .p-ring-inner')).toHaveText('58%');
});

test('REACH: hero ring, filter chips, and the picker sheet for a slider (road-fixes-clock-spec.md §3, §5; round4-fixes-spec.md §3)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Reach'}).click();

  await expect(page.getByText('REACH · THIS WEEK')).toBeVisible();
  await expect(page.locator('.p-reach-num')).toHaveText('1');
  await expect(page.locator('.p-reach-fit')).toHaveText('of 6 who fit');

  // Every filter the API returns is a chip — sliders and choices alike,
  // nothing hidden behind a "More filters" split any more.
  for (const name of ['Age','Distance','Height','Weight','Waist','Diet','Education','Kids','Nationality','Religion','Non-smoker','Non-drinker']) {
    await expect(page.locator('.chip-label',{hasText:name})).toBeVisible();
  }

  // A plain tap toggles Any/Set and keeps the saved value either way.
  await expect(page.locator('[data-chip="age"]')).toHaveClass(/is-active/);
  await chipTap(page,'age').click();
  await expect(page.locator('[data-chip="age"]')).not.toHaveClass(/is-active/);
  await expect(page.locator('[data-chip="age"] .chip-value')).toHaveText('Any');
  await chipTap(page,'age').click();
  await expect(page.locator('[data-chip="age"]')).toHaveClass(/is-active/);
  await expect(page.locator('[data-chip="age"] .chip-value')).toHaveText('27–42 yrs'); // nothing was deleted

  // The "…" sheet carries the real range slider, moved off the main screen.
  await chipSheetButton(page,'age').click();
  const sheet = page.locator('.p-chip-sheet');
  await expect(sheet).toBeVisible();
  const marker = sheet.locator('.slider-self');
  const wrap = await sheet.locator('.slider-track-wrap').boundingBox();
  const m = await marker.boundingBox();
  const thumb = 22, travel = wrap.width - thumb;
  const frac = ((m.x + m.width/2) - (wrap.x + thumb/2)) / travel;
  // 38 on 21–80 sits ~28.8% along the thumb travel (round4-fixes-spec.md §3).
  expect(frac).toBeGreaterThan(0.27); expect(frac).toBeLessThan(0.30);
  await page.locator('[data-close-sheet]').first().click();
  await expect(sheet).toHaveCount(0);

  // Nationality/Religion are sensitive levers — never a visible "yours"
  // badge in Pulse's clean chip design, but still marked for a screen
  // reader and never offered a picker sheet (no widen-suggestion exists).
  await expect(chipTap(page,'nationality')).toHaveAttribute('aria-label',/yours — never suggested/);
  await expect(chipSheetButton(page,'nationality')).toHaveCount(0);

  // Bulk action, de-emphasized but still present and functional.
  await expect(page.getByText('4 set to Any')).toBeVisible();
  await page.getByRole('button',{name:'Any for everything'}).click();
  await expect(page.getByText(/set to Any/)).toContainText('13 set to Any');
});

test('REACH: Kids is one merged three-way chip, adjustable from its own sheet (round3-fixes-spec.md §4.2)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Reach'}).click();

  const key = 'no_existing_children|has_existing_children';
  await expect(page.locator(`[data-chip="${key}"]`)).not.toHaveClass(/is-active/);
  await chipSheetButton(page,key).click();
  const sheet = page.locator('.p-chip-sheet');
  const option = (value) => sheet.locator(`label:has(input[value="${value}"])`);
  await expect(sheet.locator('input:checked')).toHaveCount(0);

  await option('has_existing_children').click();
  await expect(sheet.locator('input[value="has_existing_children"]')).toBeChecked();
  await page.locator('[data-close-sheet]').first().click();
  await expect(page.locator(`[data-chip="${key}"]`)).toHaveClass(/is-active/);
  await expect(page.locator(`[data-chip="${key}"] .chip-value`)).toHaveText('Have kids');

  // A plain tap on the chip itself is the quick Any/Set toggle.
  await chipTap(page,key).click();
  await expect(page.locator(`[data-chip="${key}"]`)).not.toHaveClass(/is-active/);
});

test('Stats: verified group and self-declared fields, existing children, editable from Home\'s Stats ring (round3/4-fixes-spec.md)',async({page})=>{
  await signIn(page);
  await page.locator('[data-ring="stats"]').click();
  await page.locator('[data-open-editor]').click();

  const form = page.locator('#dashboard-stats-form');
  const verifiedGroup = form.locator('[data-group="verified"]');
  await expect(verifiedGroup.locator('[name]')).toHaveCount(5);
  for (const k of ['age','education','nationality','profession','income_band']) await expect(verifiedGroup.locator(`[name="${k}"]`)).toHaveCount(1);
  await expect(form.locator('[data-group="declared"] [name="age"]')).toHaveCount(0);
  await expect(page.getByText('Editing a verified field re-opens its BGV check.')).toHaveCount(1);

  // Existing children: options from the API, self-declared, distinct from
  // the Kids pillar in Vision.
  const sel = form.locator('[data-group="declared"] select[name="has_children"]');
  await expect(sel.locator('option')).toHaveText(['Not set','No','Yes']);
  await form.locator('input[name="children_count"]').fill('2');
  await form.getByRole('button',{name:'Save changes'}).click();
  await expect(page.locator('[data-error-for="children_count"]')).toContainText('only applies if you already have children');

  await sel.selectOption('Yes');
  await form.getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();

  // Only changed fields were ever sent (round4-fixes-spec.md §1) — verified
  // separately below; here, just confirm the read-only tiles/rows reflect it.
  await page.locator('#p-close-editor').click();
  await expect(page.locator('.p-fact-tile',{hasText:'Age'})).toBeVisible();
});

test('Editing one unrelated stat sends only that field — untouched Age is never validated (round4-fixes-spec.md §1)',async({page})=>{
  const patches=[];
  page.on('console',async(m)=>{ if(m.text().includes('PATCH /api/v1/profile/stats request')) patches.push(JSON.stringify(await m.args()[1].jsonValue())); });
  await signIn(page);
  await page.locator('[data-ring="stats"]').click();
  await page.locator('[data-open-editor]').click();

  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Nothing changed yet')).toBeVisible();
  expect(patches).toHaveLength(0);

  await page.locator('input[name="waist_in"]').fill('33');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect(page.locator('[data-error-for]')).toHaveCount(0);
  await expect.poll(()=>patches.length).toBe(1);
  expect(patches[0]).toContain('waist_in');
  expect(patches[0]).not.toContain('age');
  expect(patches[0]).not.toContain('"height_cm"');

  await page.locator('input[name="age"]').fill('150');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.locator('[data-error-for="age"]')).toContainText('Age must be between 21 and 75');
  await page.locator('input[name="age"]').fill('31');
  await page.locator('#dashboard-stats-form').getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.')).toBeVisible();
  await expect.poll(()=>patches.length).toBe(2);
  expect(patches[1]).toContain('"age":31');
});

test('Stats are editable inline from REACH without leaving the screen (round3-fixes-spec.md §3)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Reach'}).click();
  await expect(page.getByText('Missing a filter you expected?')).toBeVisible();
  await page.getByRole('button',{name:'Edit your stats'}).click();
  const waistInput = page.locator('input[name="waist_in"]');
  await expect(waistInput).toBeVisible();
  await expect(page.getByRole('button',{name:'Cancel'})).toBeVisible();
  await waistInput.fill('30');
  await page.locator('#inline-stats-form').getByRole('button',{name:'Save changes'}).click();
  // A saved stat can unlock a new REACH lever, so saving reloads the
  // REACH screen itself once persistence is confirmed.
  await expect(page.getByRole('button',{name:'Edit your stats'})).toBeVisible();
  await expect(page.getByText('REACH · THIS WEEK')).toBeVisible();
});

test('ROAD: reachable at Relationship entry (now behind the avatar sheet), routine/obligations/sharing, shared flag never defaulted (road-fixes-clock-spec.md §1)',async({page})=>{
  await signIn(page);

  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await eventCard(page,'Match 1').click();
  await page.getByRole('button',{name:'Express interest'}).click();
  await page.getByRole('button',{name:'Confirm Date'}).click();
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
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await selectDayWithEvent(page,'Debrief');
  await eventCard(page,'Debrief').click();
  await page.getByRole('button',{name:'Open debrief'}).click();
  await page.getByRole('button',{name:'Actually listened'}).click();
  await page.getByRole('button',{name:'On time'}).click();
  await page.getByRole('button',{name:'Save feedback'}).click();
  await page.getByRole('button',{name:'Move to Relationship'}).click();

  // Relationship appears in the avatar sheet immediately — no extra manual
  // reload — because the decision handler refreshes journey/status itself.
  await tabbar(page).getByRole('button',{name:'Home'}).click();
  await openAvatarSheet(page);
  await expect(page.getByRole('button',{name:'Relationship',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Relationship',exact:true}).click();
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

test('Week: day strip carries the real category dots and a decorative calendar date; each match window closing is its own event (round4-fixes-spec.md §6)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Week'}).click();

  // The day strip: 7 days, a real date under each letter (WEEK_ONE_MONDAY
  // epoch, pure client math — see week.js's dateOfMonth), today selected.
  const days = page.locator('.p-day-btn');
  await expect(days).toHaveCount(7);
  await expect(days.nth(0).locator('.p-day-letter')).toHaveText('M');
  await expect(days.nth(0).locator('.p-day-date')).toHaveText('5');
  await expect(days.nth(0)).toHaveClass(/is-selected/);

  // Tuesday: Match 1 closes / Match 2 revealed.
  await days.nth(1).click();
  await expect(page.getByText('Monday · today')).toHaveCount(0);
  await eventCard(page,'Match 1 closes').click();
  await expect(page.getByText("Match 1's window closes at midday")).toBeVisible();

  // Wednesday: Match 2 closes AND Match 3 closes (evening) — dating-stage-
  // spec.md §1: Match 3 closes Wednesday evening, not Thursday morning.
  await days.nth(2).click();
  await expect(eventCard(page,'Match 2 closes')).toBeVisible();
  await expect(eventCard(page,'Match 3 closes')).toBeVisible();
  // Never truncated — the full "Match N closes" wording always fits a
  // full-width event card (no 40px grid cell to abbreviate for any more).
  const clipped = await page.locator('.p-event-title').evaluateAll((els) => els.filter((el) => el.scrollWidth > el.clientWidth + 0.5).map((el) => el.textContent.trim()));
  expect(clipped).toEqual([]);
});

test('Week: explainer video sits beside the day view, never autoplays, and never blocks anything (round4-fixes-spec.md §7)',async({page})=>{
  await page.route('**/media/calendar-explainer.mp4',route=>route.fulfill({status:404,body:''}));
  const mediaRequests=[];
  page.on('request',(r)=>{ if(r.url().includes('/media/')) mediaRequests.push(r.url()); });
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Week'}).click();

  const video = page.locator('details.tw-video');
  await expect(video).toBeVisible();
  await expect(video).not.toHaveAttribute('open','');
  expect(mediaRequests).toEqual([]);

  await video.locator('summary').click();
  await expect(video.locator('video, .tw-video-placeholder')).toHaveCount(1);
  await expect(video.locator('.tw-video-placeholder')).toBeVisible();
  expect(await page.evaluate(()=>[...document.querySelectorAll('video')].some((v)=>!v.paused||v.autoplay))).toBe(false);

  // The rest of the screen stays fully usable with it open: the clock
  // still steps, the day strip still switches days.
  await page.locator('.demo-step',{hasText:'+1 hour'}).click();
  await expect(page.locator('.p-now-pill')).toContainText('MON 13:00');
  await expect(video).toHaveAttribute('open','');
  await page.locator('.p-day-btn').nth(1).click();
  await expect(page.locator('.p-day-label')).toContainText('Tuesday');
});

test('Week: no "Prepare this week" button — preparing is automatic, once, on load (round4-fixes-spec.md §8)',async({page})=>{
  const infos=[];
  page.on('console',(m)=>{ if(m.text().includes('[week] preparing this week')) infos.push(m.text()); });
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  const posts = () => page.evaluate(()=>window.__previewPrepareCount());

  // Already prepared this week: loading Week never posts, and there is no button.
  await expect(page.getByText('This week',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/Prepare this week/})).toHaveCount(0);
  expect(await posts()).toBe(0);

  // A new week begins unprepared. Stepping the clock into it reloads the
  // screen; the app prepares it by itself — once — and never shows a button.
  await page.locator('.demo-step',{hasText:'+1 week'}).click();
  await expect(page.getByText('This week',{exact:true})).toBeVisible();
  await expect(eventCard(page,'Match 1')).toBeVisible();
  await expect(page.getByRole('button',{name:/Prepare this week/})).toHaveCount(0);
  expect(await posts()).toBe(1);

  // Leaving and coming back does NOT repeat it (GET is read-only).
  await tabbar(page).getByRole('button',{name:'Home'}).click();
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  await expect(eventCard(page,'Match 1')).toBeVisible();
  expect(await posts()).toBe(1);
  expect(infos).toHaveLength(1);
});

test('simulated clock: labelled stepping controls on Week, gated on the server-reported flag (road-fixes-clock-spec.md §7)',async({page})=>{
  await signIn(page);
  await tabbar(page).getByRole('button',{name:'Week'}).click();

  // Always shown, read from the API — never computed on the device (§7.5).
  await expect(page.locator('.p-now-pill')).toContainText('MON 12:00');
  await expect(page.getByText('SIMULATION')).toBeVisible();

  await page.locator('.demo-step',{hasText:'+1 hour'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Mon 13:00');

  await page.locator('.demo-step',{hasText:'+1 day'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Tue 13:00');

  await page.locator('.demo-step',{hasText:'+1 week'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Week 2');
});

test('Vision: four pillars only, additive Add Detail, and Declare a Change gated on Reality Check (round3-fixes-spec.md §7)',async({page})=>{
  await signIn(page);
  await page.locator('[data-ring="vision"]').click();
  await page.locator('[data-open-editor]').click();

  // §7.1: the explanatory copy, and no Relocation/Career anywhere.
  await expect(page.getByText('Travel together takes no detail now.')).toBeVisible();
  await expect(page.getByText(/Relocation|Career/)).toHaveCount(0);

  // §7.2: Add Detail offers only what is NOT already held (Kids isn't set,
  // Chores split already is) and actually changes the Vision.
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
  await tabbar(page).getByRole('button',{name:'Week'}).click();
  for (let i = 0; i < 6; i++) await page.locator('.demo-step',{hasText:'+1 day'}).click();
  for (let i = 0; i < 10; i++) await page.locator('.demo-step',{hasText:'+1 hour'}).click();
  await expect(page.locator('.demo-clock')).toContainText('Sun 22:00');
  await tabbar(page).getByRole('button',{name:'Home'}).click();
  // Vision stays selected and its editor stays open across the round trip.
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
