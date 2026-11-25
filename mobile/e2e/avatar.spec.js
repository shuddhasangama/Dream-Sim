import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';
test('Home opens the private avatar flow, explains selfie-only generation and preserves it on refresh',async({page})=>{
 await page.goto('/');await signInMember(page);
 await page.getByRole('button',{name:'Choose your avatar'}).click();await expect(page.getByRole('heading',{name:'Your avatar',exact:true})).toBeVisible();
 await expect(page.getByText('GPT Image 2 · Low quality',{exact:true})).toBeVisible();await expect(page.locator('#avatar-generate')).toBeHidden();
 await page.getByRole('button',{name:'Refresh avatar status'}).click();await expect(page.getByRole('button',{name:'Capture latest selfie'})).toBeVisible();
});
