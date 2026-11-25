import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';
async function openBackgroundAndHealth(page){
 await page.locator('[data-ring=stats]').click();await page.locator('[data-open-editor=stats]').click();
 for(const title of ['Ethnicity / cultural background','Health & accessibility']){
  const section=page.locator('#personal-form details').filter({has:page.locator('summary',{hasText:title})});
  if(!(await section.evaluate(d=>d.open)))await section.locator('summary').click();
 }
}
test('new Vision templates and optional personal profile persist in preview',async({page})=>{
 await page.goto('/');
 await signInMember(page);
 await page.locator('[data-open-editor=vision]').click();
 await expect(page.locator('#vision-template-form')).toHaveCount(0);
 await expect(page.locator('fieldset[disabled] input').first()).toBeDisabled();
 await page.locator('#p-close-editor').click();
 // d5325f9 (2026-11-05): ethnicity and health moved from the Bio panel into the
 // Stats editor ("Save background & health"), as collapsible sections (ab658cd).
 await openBackgroundAndHealth(page);
 await page.locator('input[name=ethnicity]').first().check();
 await page.locator('input[name=categories][value=diabetes]').check();
 await page.locator('input[name=share_health]').check();
 await page.locator('textarea[name=note]').fill('Happy to discuss what helps.');
 await page.getByRole('button',{name:'Save background & health'}).click();
 await expect(page.getByRole('status').filter({hasText:'Saved ✓'})).toHaveText('Saved ✓');
 await page.locator('#p-close-editor').click();await openBackgroundAndHealth(page);
 await expect(page.locator('input[name=categories][value=diabetes]')).toBeChecked();
 await expect(page.locator('input[name=share_health]')).toBeChecked();
});

// Owner decision (2026-11-25): the uploaded profile portrait is retired (the AI
// avatar replaces it). Its upload/crop/remove UI and PUT /api/v1/profile/photo are
// gone (the API answers 404: test_profile_choices.py, test_security_suite.py).
test('profile portrait upload is retired: no entry point anywhere a member edits their profile',async({page})=>{
 await page.goto('/');
 await signInMember(page);
 const portraitUi='#personal-open, #portrait-file, #portrait-editor, #portrait-canvas, #portrait-save, #portrait-remove';
 await expect(page.locator(portraitUi)).toHaveCount(0);
 await openBackgroundAndHealth(page);                                         // where the Bio moved
 await expect(page.locator(portraitUi)).toHaveCount(0);
 await expect(page.getByText('Your profile portrait')).toHaveCount(0);
 await expect(page.getByText('Choose a portrait')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Save background & health'})).toBeVisible();   // the rest still works
 await page.locator('#p-close-editor').click();
 await page.locator('#profile-settings').click();await expect(page.locator('.p-sheet')).toBeVisible();
 await expect(page.locator(portraitUi)).toHaveCount(0);
 // the AI avatar flow is untouched
 await page.keyboard.press('Escape');
 await expect(page.getByRole('button',{name:'Choose your avatar'})).toBeVisible();
});
