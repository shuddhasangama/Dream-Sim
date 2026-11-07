import {test,expect} from '@playwright/test';
test('OTP then password setup then signup',async({page})=>{
 await page.goto('/?passwordFlow=1');await page.getByRole('button',{name:'Sign up',exact:true}).click();
 await page.getByLabel('Phone number',{exact:true}).fill('+15550001111');await page.getByRole('button',{name:'Send SMS code'}).click();
 await page.getByLabel('Verification code').fill('123456');await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Set your password'})).toBeVisible();
 await page.getByLabel('Password',{exact:true}).fill('TwelveChars!');await page.getByLabel('Confirm password').fill('TwelveChars!');
 await page.screenshot({path:'../outputs/password-login/setup.png',fullPage:true});await page.getByRole('button',{name:'Save password and continue'}).click();
 await expect(page.getByRole('heading',{name:'Step 1 of 4 · Vision'})).toBeVisible();
});
test('password login and explicit recovery',async({page})=>{
 await page.goto('/');await page.getByLabel('Phone number').fill('+15550001111');await page.getByLabel('Password',{exact:true}).fill('TwelveChars!');
 await page.screenshot({path:'../outputs/password-login/signin.png',fullPage:true});await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.locator('#profile-settings')).toBeVisible();await page.locator('#profile-settings').click();await expect(page.locator('#set-member-password')).toBeVisible();
 await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('button',{name:'First password / forgot password? Use a code'}).click();
 await expect(page.getByRole('button',{name:'Send recovery code'})).toBeVisible();
 await expect(page.getByLabel(/email/i)).toHaveCount(0);
});
