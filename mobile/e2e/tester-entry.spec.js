import {test,expect} from '@playwright/test';
for (const signup of [false,true]) {
  test(`OTP-free tester entry: ${signup?'guided signup':'dashboard'}`,async({page})=>{
    await page.route('**/src/preview.js',async route=>{
      const response=await route.fetch();
      const source=(await response.text()).replace("if (path.endsWith('/auth/verify')) {", "if (path.endsWith('/auth/tester')) { active=true; return ok({access_token:'preview-access',refresh_token:'preview-refresh',expires_in:900}); } if (path.endsWith('/auth/verify')) {");
      await route.fulfill({response,body:source});
    });
    await page.goto('/');
    if(signup) await page.getByRole('button',{name:'Sign up',exact:true}).click();
    await page.getByLabel('Phone number').fill('+15550001111');
    await page.getByRole('button',{name:'Continue as tester without SMS'}).click();
    await expect(page.getByLabel('Verification code')).toHaveCount(0);
    if(signup) await expect(page.getByRole('heading',{name:'Step 1 of 3 · Vision'})).toBeVisible();
    else await expect(page.locator('.topnav').getByRole('button',{name:'Dashboard',exact:true})).toBeVisible();
  });
}
