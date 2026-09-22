import {test,expect} from '@playwright/test';

test('shared-clock polling refreshes read screens, hides manual jumps, and preserves edited forms',async({page})=>{
  // Substitute only the local preview transport; no backend or real clock changes.
  await page.route('**/src/preview.js',async route=>{
    const response=await route.fetch();
    const source=(await response.text()).replace('export function previewTransport()', 'function baseTransport()');
    await route.fulfill({response,body:source+`
      export function previewTransport() {
        const base=baseTransport();
        return async (...args)=>{
          const result=await base(...args);
          if (args[0].endsWith('/journey/status') || args[0].endsWith('/week')) {
            result.data.data.clock={mode:'simulation',week:1,day:'Mon',hour:window.__testHour || 12};
            result.data.data.accelerated_test={enabled:true,step:1,finished:false};
          }
          return result;
        };
      }`});
  });
  await page.clock.install();
  await page.goto('/');
  await page.getByLabel('Phone number').fill('+15550001111');
  await page.getByRole('button',{name:'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill('123456');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('.accelerated-banner')).toContainText('Mon 12:00');
  await page.locator('.topnav').getByRole('button',{name:'Week',exact:true}).click();
  await expect(page.locator('[data-advance]')).toHaveCount(0);
  await page.evaluate(()=>{window.__testHour=13;});
  await page.clock.fastForward(15000);
  await expect(page.locator('.tw-now')).toContainText('Mon 13:00');
  await page.locator('.topnav').getByRole('button',{name:'Dashboard',exact:true}).click();
  await page.getByRole('button',{name:'Edit stats',exact:true}).click();
  await page.locator('input[name=weight_kg]').fill('69');
  await page.evaluate(()=>{window.__testHour=14;});
  await page.clock.fastForward(15000);
  await expect(page.locator('.accelerated-banner')).toContainText('unsaved screen is preserved');
  await expect(page.locator('input[name=weight_kg]')).toHaveValue('69');
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Refresh current step'}).click();
  await expect(page.locator('.accelerated-banner')).toContainText('Mon 14:00');
});
