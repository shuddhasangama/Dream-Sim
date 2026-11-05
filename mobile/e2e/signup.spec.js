import {test, expect} from '@playwright/test';

async function enter(page, signup=true) {
  await page.goto('/');
  if(signup) await page.getByRole('button',{name:'Sign up',exact:true}).click();
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
}

test('guided sign up verifies first, prefills and persists edits through all four steps', async({page})=>{
  const external=[];
  page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173')) external.push(r.url());});
  await enter(page);
  await expect(page.getByRole('heading',{name:'Step 1 of 4 · Vision'})).toBeVisible();
  await expect(page.locator('[data-signup-plan][aria-pressed=true]')).toHaveCount(0);
  await expect(page.getByText('Add detail',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Declare a change',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Family',exact:true}).click();
  await page.screenshot({path:'../outputs/signup-redesign-family.png',fullPage:true});
  await page.getByRole('button',{name:'Continue to Stats'}).click();
  await expect(page.locator('input[name="age"]')).toHaveValue('30');
  await page.locator('input[name="weight_kg"]').fill('68');
  await page.getByRole('button',{name:'Continue to Chemistry'}).click();
  await expect(page.getByRole('alert')).toContainText('Save your edits');
  await page.getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Continue to Chemistry'}).click();
  await expect(page.getByRole('heading',{name:'Step 3 of 4 · Chemistry'})).toBeVisible();
  await expect(page.locator('input[type=radio]:checked').first()).toBeChecked();
  await page.getByRole('button',{name:'Save chemistry'}).click();
  await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Continue to Verification'}).click();
  await expect(page.getByRole('heading',{name:'Step 4 of 4 · Verification'})).toBeVisible();
  await page.getByRole('button',{name:'Go to Home'}).click();
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();
  await page.locator('[data-ring=stats]').click();
  await page.locator('[data-open-editor=stats]').click();
  await expect(page.locator('input[name=weight_kg]')).toHaveValue('68');
  expect(external).toEqual([]);
});

test('walkthrough is available before login; login goes directly to dashboard',async({page})=>{
  await page.goto('/');
  await page.locator('.how-it-works summary').click();
  await expect(page.locator('.test-timetable tbody tr')).toHaveCount(11);
  const video=page.locator('.how-it-works video');
  await expect(video).toHaveAttribute('playsinline','');
  await video.evaluate(async v=>{await v.play();});
  await expect.poll(()=>video.evaluate(v=>v.currentTime)).toBeGreaterThan(0);
  await video.evaluate(v=>v.pause());
  await enter(page,false);
  await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();
  await expect(page.locator('.signup-intro')).toHaveCount(0);
});

test('invalid stats stay on the step and preserve the entered value for correction',async({page})=>{
  await enter(page);
  await page.getByRole('button',{name:'Family',exact:true}).click();
  await page.getByRole('button',{name:'Continue to Stats'}).click();
  await page.locator('input[name="age"]').fill('200');
  await page.getByRole('button',{name:'Save changes'}).click();
  await expect(page.locator('[data-error-for="age"]')).toBeVisible();
  await expect(page.locator('input[name="age"]')).toHaveValue('200');
  await page.getByRole('button',{name:'Continue to Chemistry'}).click();
  await expect(page.getByRole('heading',{name:'Step 2 of 4 · Stats'})).toBeVisible();
  await page.getByRole('button',{name:'Discard unsaved edits and reload this step'}).click();
  await expect(page.locator('input[name="age"]')).toHaveValue('30');
  await page.getByRole('button',{name:'Previous step'}).click();
  await expect(page.getByRole('heading',{name:'Step 1 of 4 · Vision'})).toBeVisible();
});

for(const [key,label,kids] of [['grow','Family',true],['two','We Two',false],['explore','Travel',false]])test(`signup offers ${label} with live pillar preview`,async({page})=>{
 await enter(page);await page.getByRole('button',{name:label,exact:true}).click();
 await expect(page.locator('[data-signup-plan="'+key+'"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('[data-signup-pillar="Kids"]')).toBeChecked({checked:kids});
 await expect(page.locator('[data-signup-pillar="Travel together"]')).toBeChecked();
 await page.getByRole('button',{name:'Continue to Stats'}).click();await expect(page.getByRole('heading',{name:'Step 2 of 4 · Stats'})).toBeVisible();
});
test('signup needs an explicit plan and custom choices have no history or duplicate travel toggle',async({page})=>{
 await enter(page);await expect(page.locator('#tester-login')).toHaveCount(0);await expect(page.locator('.verify-pill')).toHaveCount(0);
 await page.getByRole('button',{name:'Continue to Stats'}).click();await expect(page.getByRole('alert')).toContainText('Choose your Twogether Plan');
 await page.getByRole('button',{name:'Custom',exact:true}).click();await expect(page.locator('[data-signup-choice]:checked')).toHaveCount(0);await expect(page.getByText('Travel together (optional)',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Family',exact:true}).click();await page.getByRole('button',{name:'We Two',exact:true}).click();await expect(page.locator('[data-signup-pillar="Kids"]')).not.toBeChecked();
 await page.getByRole('button',{name:'Travel',exact:true}).click();await expect(page.locator('[data-signup-pillar="Cohabitate"]')).not.toBeChecked();
});
for(const width of [320,390])test(`focus panel aligns plans and pillars at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:844});await enter(page);
 await page.getByRole('button',{name:'Family',exact:true}).click();
 await page.getByRole('switch',{name:'Include Kids',exact:true}).uncheck();
 await expect(page.locator('[data-signup-plan="two"]')).toHaveAttribute('aria-pressed','true');
 await page.getByRole('switch',{name:'Include Kids',exact:true}).check();
 await expect(page.locator('[data-signup-plan="grow"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('[data-signup-choice]')).toHaveCount(4);
 await page.locator('[data-signup-choice][value="Pets"]').uncheck();
 await expect(page.locator('[data-signup-plan="grow"]')).toHaveAttribute('aria-pressed','true');
 await page.locator('[data-signup-focus="Intimacy"]').click();
 await expect(page.locator('[data-signup-choice]')).toHaveCount(2);
 const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,plans:[...document.querySelectorAll('[data-signup-plan]')].map(e=>Math.round(e.getBoundingClientRect().top)),tiles:[...document.querySelectorAll('.signup-pillar-tile')].map(e=>Math.round(e.getBoundingClientRect().top))}));
 expect(geometry.overflow).toBe(false);expect(new Set(geometry.plans).size).toBe(1);expect(new Set(geometry.tiles).size).toBe(2);
 await page.getByRole('button',{name:'Continue to Stats'}).click();await expect(page.getByRole('heading',{name:'Step 2 of 4 · Stats'})).toBeVisible();
});
