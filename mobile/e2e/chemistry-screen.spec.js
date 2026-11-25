import {test,expect} from '@playwright/test';
import {signInMember} from './fixtures/auth.js';
// vis-chem: one activity open at a time, every activity listed + "Add your own", the
// partner flag (never pre-ticked, visible when collapsed), one Save enabled only when
// something changed, a failed save keeps every edit, a warning before leaving with
// unsaved changes, and no overflow at 320 / 375 / 414 px.
async function openChemistry(page){
 await page.goto('/');await signInMember(page);
 await page.locator('[data-ring=chemistry]').click();await page.locator('[data-open-editor=chemistry]').click();
 await expect(page.locator('#activities-form')).toBeVisible();
}
const row=(page,name)=>page.locator('details.activity-row').filter({has:page.locator('.activity-name',{hasText:new RegExp('^'+name+'$')})});

test('one open at a time, every activity listed, partner flag shown when collapsed',async({page})=>{
 await openChemistry(page);
 const rows=page.locator('details.activity-row');
 expect(await rows.count()).toBeGreaterThanOrEqual(12);                       // every catalogue activity is always listed
 await expect(page.getByLabel(/Add your own activity/)).toBeVisible();
 await row(page,'Cooking').locator('summary').click();
 await expect(row(page,'Cooking')).toHaveAttribute('open','');
 await row(page,'Hiking').locator('summary').click();
 await expect(row(page,'Hiking')).toHaveAttribute('open','');
 await expect(row(page,'Cooking')).not.toHaveAttribute('open','');           // opening one closes the other
 expect(await row(page,'Hiking').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.top<innerHeight;})).toBe(true);
 // keyboard: the summary is focusable and Enter toggles it
 await row(page,'Cooking').locator('summary').focus();await page.keyboard.press('Enter');
 await expect(row(page,'Cooking')).toHaveAttribute('open','');
 // partner flag: never pre-ticked; shows on the collapsed row once ticked
 const flag=row(page,'Cooking').locator('input[name=partner_any]');
 await expect(flag).not.toBeChecked();
 await flag.check();
 await row(page,'Hiking').locator('summary').click();                       // Cooking collapses
 await expect(row(page,'Cooking').locator('[data-partner-flag]')).toBeVisible();
 await expect(row(page,'Cooking').locator('summary')).toContainText('Partner can be indifferent');
});

test('one Save, enabled only when changed; a failed save keeps every edit; Saved only when confirmed',async({page})=>{
 await openChemistry(page);
 const save=page.getByRole('button',{name:'Save chemistry'});
 await expect(save).toBeDisabled();
 await row(page,'Cooking').locator('summary').click();
 await row(page,'Cooking').locator('input[name=partner_any]').check();
 await expect(save).toBeEnabled();
 await row(page,'Cooking').locator('input[name=partner_any]').uncheck();
 await expect(save).toBeDisabled();                                            // back to the saved state
 // a custom activity without an answer -> the server refuses -> nothing is lost
 await row(page,'Cooking').locator('input[name=partner_any]').check();
 await page.locator('#custom-activity').fill('Chess');await page.getByRole('button',{name:'Add activity',exact:true}).click();
 await save.click();
 await expect(page.locator('#activities-form .warn')).toContainText('Choose your own answer');
 await expect(row(page,'Chess')).toHaveCount(1);
 await expect(row(page,'Cooking').locator('input[name=partner_any]')).toBeChecked();
 await expect(save).toBeEnabled();
 // answer it and save: Saved appears only after the server confirms
 await row(page,'Chess').locator('summary').click();
 await row(page,'Chess').locator('label.bucket-pick').filter({has:page.locator('input[value=good]')}).click();
 await save.click();
 await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
 await expect(save).toBeDisabled();
});

test('warns before leaving with unsaved changes',async({page})=>{
 await openChemistry(page);
 await row(page,'Hiking').locator('summary').click();
 await row(page,'Hiking').locator('label.bucket-pick').filter({has:page.locator('input[value=improve]')}).click();
 const dialogs=[];
 page.once('dialog',d=>{dialogs.push(d.message());d.dismiss();});
 await page.locator('[data-ring=vision]').click();
 expect(dialogs).toEqual(['You have unsaved changes. Leave without saving?']);
 await expect(page.locator('#activities-form')).toBeVisible();               // stayed, edits intact
 await expect(row(page,'Hiking').locator('input[value=improve]')).toBeChecked();
 page.once('dialog',d=>d.accept());
 await page.locator('[data-ring=vision]').click();
 await expect(page.locator('#activities-form')).toHaveCount(0);              // left on purpose
});

for(const width of [320,375,414])test(`Chemistry fits ${width}px with no overflow`,async({page})=>{
 await page.setViewportSize({width,height:800});await openChemistry(page);
 await row(page,'Cooking').locator('summary').click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.locator('body')).toHaveCSS('background-color','rgb(252, 251, 249)');
});
