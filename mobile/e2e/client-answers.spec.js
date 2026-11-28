import {test,expect} from '@playwright/test';
import {signInMember, signUpWithCode} from './fixtures/auth.js';
// Client answers (DhaShu meeting, 27 Nov 2026), as a member sees them in the app.

async function signIn(page){await page.goto('/');await signInMember(page);}

test('answer 1: Travel together plan and pillars of your own on Custom',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Sign up',exact:true}).click();await signUpWithCode(page);
 await expect(page.getByRole('button',{name:'Travel together',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Customise your plan',exact:true}).click();
 await page.getByLabel('Name a pillar of your own').fill('Faith');
 await page.getByRole('button',{name:'Add pillar',exact:true}).click();
 await expect(page.locator('.signup-own-pillars')).toContainText('Faith');
 await page.getByLabel('Name a pillar of your own').fill('faith');
 await page.getByRole('button',{name:'Add pillar',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('already listed');
});

test('answer 4: Chemistry shows how many activities are sorted against the minimum of 4',async({page})=>{
 await signIn(page);
 await page.locator('[data-ring=chemistry]').click();await page.locator('[data-open-editor=chemistry]').click();
 await expect(page.locator('#activity-count')).toContainText(/Sorted \d+ of at least 4 activities/);
});

test('answer 6: height in cm and feet/inches, kept in step',async({page})=>{
 await signIn(page);
 await page.locator('[data-ring=stats]').click();await page.locator('[data-open-editor=stats]').click();
 const cm=page.locator('input[name=height_cm]').first();
 await expect(page.locator('input[name=height_ft]').first()).toBeVisible();
 await cm.fill('170');await cm.dispatchEvent('input');
 await expect(page.locator('input[name=height_ft]').first()).toHaveValue('5');
 await expect(page.locator('input[name=height_in]').first()).toHaveValue('7');
 await page.locator('input[name=height_ft]').first().fill('6');await page.locator('input[name=height_in]').first().fill('0');await page.locator('input[name=height_in]').first().dispatchEvent('input');
 await expect(cm).toHaveValue('183');
 await expect(page.getByText('140–210 cm (4′ 7″–6′ 10″)').first()).toBeVisible();
});

test('answer 8: Settings shows the support email',async({page})=>{
 await signIn(page);await page.locator('#profile-settings').click();
 await expect(page.locator('.support-line a')).toHaveAttribute('href','mailto:hello@dhashu.com');
});
