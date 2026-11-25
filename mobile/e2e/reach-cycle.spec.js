import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';

test('REACH closes on server eligibility change without needing a mutual pair or clock change',async({page})=>{
  await page.route('**/src/preview.js',async route=>{
    const response=await route.fetch();
    const source=(await response.text()).replace('export function previewTransport()', 'function baseTransport()');
    await route.fulfill({response,body:source+`
      export function previewTransport(){
        const base=baseTransport();
        return async (...args)=>{
          const result=await base(...args);
          if(args[0].endsWith('/journey/status') && window.__reachPaused){
            const surface=result.data.data.surfaces.find(s=>s.key==='reach');
            surface.eligible=false;surface.request=null;surface.blocked_reason='Match review is in progress.';
          }
          return result;
        };
      }`});
  });
  await page.clock.install();await page.goto('/');
  await signInMember(page);
  await page.locator('.p-tabbar').getByRole('button',{name:'Reach',exact:true}).click();
  await expect(page.locator('.reach-review-heading')).toBeVisible();   // REACH screen (056139e header)
  await page.evaluate(()=>{window.__reachPaused=true;});
  await page.clock.fastForward(15000);
  await expect(page.locator('.p-tabbar').getByRole('button',{name:'Reach',exact:true})).toHaveCount(0);
  await expect(page.locator('.p-hi')).toBeVisible();
  await expect(page.locator('#notice')).toContainText('Unsaved filters were not applied');
});

test('Bone palette and bundled typography fit a small phone without external font requests',async({page})=>{
  const requests=[];page.on('request',r=>requests.push(r.url()));
  await page.setViewportSize({width:320,height:740});await page.goto('/');
  await expect(page.locator('.brand-name')).toHaveText('DhaShu');
  // 056139e (2026-11-23, Brand Meadows): background #FCFBF9 and Newsreader headings,
  // both still bundled (the no-Google-Fonts check below is unchanged).
  await expect(page.locator('body')).toHaveCSS('background-color','rgb(252, 251, 249)');
  await expect(page.locator('h1').first()).toHaveCSS('font-family',/Newsreader/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(requests.some(url=>/fonts\.googleapis|fonts\.gstatic/.test(url))).toBeFalsy();
  await page.screenshot({path:'test-results/bone-signin-320.png',fullPage:true});
});
