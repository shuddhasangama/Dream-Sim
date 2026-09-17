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
  await expect(page.getByRole('heading',{name:'Week',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'← Back'})).toBeVisible();

  await page.getByRole('button',{name:'← Back'}).click();
  await expect(page.getByRole('heading',{name:'Preview profile'})).toBeVisible();
  await expect(page.getByRole('button',{name:'← Back'})).toHaveCount(0);

  // The dashboard's own next-action CTA is a second way into the same
  // navigation, not a separate mechanism — it should land on the same screen.
  await page.getByRole('button',{name:'See this week'}).click();
  await expect(page.getByRole('heading',{name:'Week',exact:true})).toBeVisible();
});
