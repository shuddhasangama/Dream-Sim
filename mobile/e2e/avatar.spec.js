import {test,expect} from '@playwright/test';
test('Home opens the private avatar flow, explains selfie-only generation and preserves it on refresh',async({page})=>{
 await page.goto('/');await page.getByLabel('Phone number').fill('+15550001111');await page.getByRole('button',{name:'Send SMS code'}).click();await page.getByLabel('Verification code').fill('123456');await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.getByRole('button',{name:'Your AI avatar'}).click();await expect(page.getByRole('heading',{name:'Your avatar',exact:true})).toBeVisible();
 await expect(page.getByText('GPT Image 2 · Low quality',{exact:true})).toBeVisible();await expect(page.locator('#avatar-generate')).toBeHidden();
 await page.getByRole('button',{name:'Refresh avatar status'}).click();await expect(page.getByRole('button',{name:'Capture latest selfie'})).toBeVisible();
});
