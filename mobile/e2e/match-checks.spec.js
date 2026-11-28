import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';
async function signIn(page){await page.goto('/');await signInMember(page);await expect(page.getByRole('heading',{name:'Hi, Preview'})).toBeVisible();}
const tab=(page,name)=>page.locator('.p-tabbar').getByRole('button',{name,exact:true});
test('match card has dates, category, statuses and existing decisions',async({page})=>{
 await signIn(page);await tab(page,'Week').click();await page.locator('.p-event-card').filter({hasText:'Match 1'}).getByRole('button').first().click();
 await expect(page.locator('.match-checks')).toBeVisible();await expect(page.locator('.match-checks')).toContainText('Checked on 2026-11-03');await expect(page.locator('.match-checks')).toContainText('History found');await expect(page.getByText('Employment category: Freelancer',{exact:false})).toBeVisible();
 await expect(page.getByRole('button',{name:'Like',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Pass',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'../outputs/match-checks-card-preview.png',fullPage:true});
 await page.getByRole('button',{name:'Pass',exact:true}).click();await expect(page.getByText(/Your decision: Pass/)).toBeVisible();
});
test('client answer 5: REACH filters are Stats-only',async({page})=>{
 await signIn(page);await tab(page,'Reach').click();
 await expect(page.locator('.reach-stats-only')).toHaveText('REACH filters use your Stats only.');
 await expect(page.locator('details.reach-extra-filters')).toHaveCount(0);
 await expect(page.locator('#reach-work-verification')).toHaveCount(0);
 await expect(page.locator('#health-reach-form')).toHaveCount(0);
});
test('Stats category and sharing are explicit opt-in choices',async({page})=>{
 await signIn(page);await page.locator('[data-ring=stats]').click();await page.locator('[data-open-editor=stats]').click();await expect(page.locator('select[name=share_verification_summary]')).toHaveValue('');await page.locator('select[name=employment_category]').selectOption('Business owner');await page.locator('select[name=share_verification_summary]').selectOption('Yes');await page.getByRole('button',{name:'Save changes',exact:true}).click();if(await page.locator('#p-close-editor').count())await page.locator('#p-close-editor').click();await page.locator('[data-open-editor=stats]').click();await expect(page.locator('select[name=employment_category]')).toHaveValue('Business owner');await expect(page.locator('select[name=share_verification_summary]')).toHaveValue('Yes');
});
