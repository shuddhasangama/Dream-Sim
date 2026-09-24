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

test('personal intro starts once, advances to minute twelve and saves pre-match slots',async({page})=>{
  await page.route('**/src/preview.js',async route=>{
    const response=await route.fetch();
    const source=(await response.text()).replace('export function previewTransport()', 'function baseTransport()');
    await route.fulfill({response,body:source+`
      export function previewTransport() {
        const base=baseTransport();
        return async (...args)=>{
          if (args[0].endsWith('/rehearsal/start')) {
            window.__starts=(window.__starts||0)+1;
            window.__introStart ??= Date.now();
            return {status:200,data:{error:null,data:{enabled:true}}};
          }
          if (args[0].endsWith('/rehearsal/availability')) {
            window.__slots=args[2].slots;
            return {status:200,data:{error:null,data:{enabled:true}}};
          }
          const result=await base(...args);
          if (args[0].endsWith('/journey/status')) {
            const step=Math.min(4,Math.floor((Date.now()-(window.__introStart??Date.now()))/180000));
            const checkpoints=[['Mon',10],['Mon',12],['Tue',12],['Wed',12],['Wed',18]];
            result.data.data.clock={week:39,day:checkpoints[step][0],hour:checkpoints[step][1]};
            result.data.data.async_rehearsal={enabled:true,intro_step:step,
              next_jump_in_seconds:step<4?180:null,
              message:step<4?'Advancing through match checkpoints.':'Availability is open. The clock waits here.',
              ...(!window.__introStart?{start_request:{path:'/api/v1/rehearsal/start',body:{}}}:{}),
              ...(step===4?{draft_availability:{path:'/api/v1/rehearsal/availability',valid_slots:[{day:'Sat',meal_slot:'dinner'}],my_slots:window.__slots||[]}}:{})};
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
  await expect(page.locator('.rehearsal-banner')).toContainText('Next checkpoint');
  await expect(page.locator('#rehearsal-slots')).toHaveCount(0);
  await page.clock.fastForward(720000);
  await expect(page.locator('#rehearsal-slots')).toBeVisible();
  await page.getByLabel('Sat · dinner').check();
  await page.clock.fastForward(15000);
  await expect(page.getByLabel('Sat · dinner')).toBeChecked();
  await page.getByRole('button',{name:'Save availability',exact:true}).click();
  await expect(page.getByLabel('Sat · dinner')).toBeChecked();
  await page.getByRole('button',{name:'Refresh progress'}).click();
  await expect(page.getByLabel('Sat · dinner')).toBeChecked();
  expect(await page.evaluate(()=>window.__starts)).toBe(1);
  expect(await page.evaluate(()=>window.__slots)).toEqual([{day:'Sat',meal_slot:'dinner'}]);
});
