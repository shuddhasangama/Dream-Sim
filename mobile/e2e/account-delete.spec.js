import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';
// feat-delete: Settings -> Delete account -> confirm -> signed out -> sign in within the
// grace period -> "scheduled for deletion on <date>" -> Cancel deletion -> Home again.
test('delete account from Settings, then cancel within the grace period',async({page})=>{
 await page.goto('/');await signInMember(page);
 await page.locator('#profile-settings').click();
 await page.getByRole('button',{name:'Delete account',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Delete your account'})).toBeVisible();
 await expect(page.getByText('After 30 days everything is deleted')).toBeVisible();
 // "Keep my account" leaves without doing anything
 await page.getByRole('button',{name:'Keep my account'}).click();
 await expect(page.locator('#profile-settings')).toBeVisible();
 await page.locator('#profile-settings').click();await page.getByRole('button',{name:'Delete account',exact:true}).click();
 // confirm with a code: a wrong code is refused and nothing happens
 await page.getByRole('button',{name:'Use a code instead'}).click();
 await page.getByLabel('Code sent to your phone').fill('000000');
 await page.getByRole('button',{name:'Delete my account'}).click();
 await expect(page.getByRole('alert')).toContainText('not accepted');
 await page.getByLabel('Code sent to your phone').fill('123456');
 await page.getByRole('button',{name:'Delete my account'}).click();
 await expect(page.locator('#notice')).toContainText('signed out everywhere');
 await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();
 // signing in again within the grace period shows the date and Cancel deletion
 await signInMember(page);
 await expect(page.getByRole('heading',{name:'Your account is scheduled for deletion'})).toBeVisible();
 await expect(page.getByText(/scheduled for deletion on \d{1,2} \w+ \d{4}/)).toBeVisible();
 await expect(page.locator('.p-tabbar')).toHaveCount(0);                     // nothing else is reachable
 await page.getByRole('button',{name:'Cancel deletion'}).click();
 await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();
});
for(const width of [320,390])test(`delete screens fit ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:780});await page.goto('/');await signInMember(page);
 await page.locator('#profile-settings').click();await page.getByRole('button',{name:'Delete account',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
