import {test, expect} from '@playwright/test';

async function enter(page, signup=true) {
  await page.goto('/');
  if(signup) await page.getByRole('button',{name:'Sign up',exact:true}).click();
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
}

test('guided sign up verifies first, prefills and persists edits through all three steps', async({page})=>{
  const external=[];
  page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173')) external.push(r.url());});
  await enter(page);
  await expect(page.getByRole('heading',{name:'Step 1 of 3 · Vision'})).toBeVisible();
  await expect(page.getByText('Intimacy · Emotional, Physical')).toBeVisible();
  await page.locator('#detail-choice').selectOption({index:0});
  await page.getByRole('button',{name:'Add',exact:true}).click();
  await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Continue to Stats'}).click();
  await expect(page.locator('input[name="age"]')).toHaveValue('30');
  await page.locator('input[name="weight_kg"]').fill('68');
  await page.getByRole('button',{name:'Continue to Chemistry'}).click();
  await expect(page.getByRole('alert')).toContainText('Save your edits');
  await page.getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Continue to Chemistry'}).click();
  await expect(page.getByRole('heading',{name:'Step 3 of 3 · Chemistry'})).toBeVisible();
  await expect(page.locator('input[type=radio]:checked').first()).toBeChecked();
  await page.getByRole('button',{name:'Save chemistry'}).click();
  await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Finish sign up'}).click();
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();
  await expect(page.getByText('68 kg',{exact:true})).toBeVisible();
  expect(external).toEqual([]);
});

test('login goes directly to dashboard; video and timetable work on Home',async({page})=>{
  await enter(page,false);
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();
  await expect(page.locator('.signup-intro')).toHaveCount(0);
  await page.locator('.how-it-works summary').click();
  await expect(page.locator('.test-timetable tbody tr')).toHaveCount(11);
  const video=page.locator('.how-it-works video');
  await expect(video).toHaveAttribute('playsinline','');
  await video.evaluate(async v=>{await v.play();});
  await expect.poll(()=>video.evaluate(v=>v.currentTime)).toBeGreaterThan(0);
  await video.evaluate(v=>v.pause());
});

test('invalid stats stay on the step and preserve the entered value for correction',async({page})=>{
  await enter(page);
  await page.getByRole('button',{name:'Continue to Stats'}).click();
  await page.locator('input[name="age"]').fill('200');
  await page.getByRole('button',{name:'Save changes'}).click();
  await expect(page.locator('[data-error-for="age"]')).toBeVisible();
  await expect(page.locator('input[name="age"]')).toHaveValue('200');
  await page.getByRole('button',{name:'Continue to Chemistry'}).click();
  await expect(page.getByRole('heading',{name:'Step 2 of 3 · Stats'})).toBeVisible();
  await page.getByRole('button',{name:'Discard unsaved edits and reload this step'}).click();
  await expect(page.locator('input[name="age"]')).toHaveValue('30');
  await page.getByRole('button',{name:'Previous step'}).click();
  await expect(page.getByRole('heading',{name:'Step 1 of 3 · Vision'})).toBeVisible();
});
