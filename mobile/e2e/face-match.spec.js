import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';
test('avatar flow shows separate face comparison without blocking the test journey',async({page})=>{
 await page.goto('/');await signInMember(page);
 await page.getByRole('button',{name:'Your AI avatar'}).click();await page.getByText('Face verification · Pending',{exact:true}).click();await expect(page.getByRole('heading',{name:'Selfie → Aadhaar'})).toBeVisible();await expect(page.locator('#face-match-start')).toBeDisabled();
 await expect(page.locator('.face-comparison')).toContainText('Liveness not checked');await page.getByRole('button',{name:'Refresh face status'}).click();
 await expect(page.locator('#face-match-consent')).not.toBeChecked();await page.locator('.p-tabbar').getByRole('button',{name:'Week',exact:true}).click();await expect(page.locator('.p-week-title')).toBeVisible();
});
