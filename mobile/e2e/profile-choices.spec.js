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

// The portrait upload (decode/crop/encode, save, remove) had its only entry point,
// Home's Bio panel (#personal-open), removed in d5325f9 when the AI avatar took
// over. Kept as-is until Saravanan decides: retire the portrait code, or give it
// an entry point again (see Group 5 report, "Decisions").
test('profile portrait upload, crop, save and remove',async({page})=>{
 await page.goto('/');
 await signInMember(page);
 await page.locator('#personal-open').click();
 // Exercise the actual image decode/crop/encode path with a tiny generated PNG.
 const bytes=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=600;c.height=800;c.getContext('2d').fillRect(0,0,600,800);return c.toDataURL().split(',')[1];});
 await page.locator('#portrait-file').setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:Buffer.from(bytes,'base64')});
 await expect(page.locator('#portrait-editor')).toBeVisible();
 await page.locator('#portrait-zoom').fill('1.2');
 await page.locator('textarea[name=note]').fill('Updated note');
 await page.getByRole('button',{name:'Save portrait'}).click();
 await expect(page.locator('#personal-photo-note')).toContainText('Save your profile preferences');
 await page.getByRole('button',{name:'Save Bio'}).click();
 await page.locator('#portrait-file').setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:Buffer.from(bytes,'base64')});
 await expect(page.locator('#portrait-editor')).toBeVisible();
 await page.getByRole('button',{name:'Save portrait'}).click();
 await expect(page.getByAltText('Your profile portrait')).toHaveAttribute('src',/^data:image\/jpeg/);
 await page.getByRole('button',{name:'Remove photo'}).click();
 await expect(page.getByAltText('Your profile portrait')).toHaveCount(0);
});
