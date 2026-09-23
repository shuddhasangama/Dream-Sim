import {test,expect} from '@playwright/test';

test('rehearsal waits, notices partner actions on an unchanged clock, and preserves edits',async({page})=>{
  await page.route('**/src/preview.js',async route=>{
    const response=await route.fetch();
    const source=(await response.text()).replace('export function previewTransport()', 'function baseTransport()');
    await route.fulfill({response,body:source+`
      export function previewTransport() {
        const base=baseTransport();
        return async (...args)=>{
          if (args[0].includes('/rehearsal/')) {
            window.__ready=true;
            return {status:200,data:{error:null,data:{enabled:true}}};
          }
          const result=await base(...args);
          if (args[0].endsWith('/journey/status')) {
            result.data.data.async_rehearsal={enabled:true,stage:'ready_for_date',
              message:window.__peer?'Your partner is ready.':window.__ready?'Waiting for your partner.':'Ready when you are.',
              request:window.__ready?null:{path:'/api/v1/rehearsal/date-plans/test/ready',body:{step:'date'},label:'Ready for simulated date'}};
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
  await expect(page.locator('.rehearsal-banner')).toContainText('at your own pace');
  await page.getByRole('button',{name:'Ready for simulated date',exact:true}).click();
  await expect(page.locator('.rehearsal-banner')).toContainText('Waiting for your partner');
  await page.locator('.topnav').getByRole('button',{name:'Week',exact:true}).click();
  await expect(page.locator('[data-advance]')).toHaveCount(0);
  await page.evaluate(()=>{window.__peer=true;});
  await page.clock.fastForward(15000);
  await expect(page.locator('.rehearsal-banner')).toContainText('Your partner is ready');
  await page.locator('.topnav').getByRole('button',{name:'Dashboard',exact:true}).click();
  await page.getByRole('button',{name:'Edit stats',exact:true}).click();
  await page.locator('input[name=weight_kg]').fill('69');
  await page.evaluate(()=>{window.__peer=false;});
  await page.clock.fastForward(15000);
  await expect(page.locator('.rehearsal-banner')).toContainText('unsaved screen is preserved');
  await expect(page.locator('input[name=weight_kg]')).toHaveValue('69');
});
