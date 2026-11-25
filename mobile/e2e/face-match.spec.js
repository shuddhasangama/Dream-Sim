import {test,expect} from '@playwright/test';
import {signUpWithCode} from './fixtures/auth.js';
// 14c61fd (2026-11-05) moved the face comparison from the avatar screen into the
// Verification screen ("3. Live face verification"), in its compact form: no
// separate "Selfie → Aadhaar" heading and no refresh button there (the screen
// refreshes itself; verification-progress.spec.js asserts the button is absent).
// What this test protects is unchanged: the face comparison is shown separately,
// cannot start before its prerequisites, consent is never pre-ticked, and it
// never blocks the rest of the journey.
// A member whose face check is still pending meets it in signup Step 4 (Verification);
// a verified member has no Verify surface.
async function openVerification(page){
 await page.getByRole('button',{name:'Sign up',exact:true}).click();await signUpWithCode(page);
 await page.getByRole('button',{name:'Family',exact:true}).click();await page.getByRole('button',{name:'Continue to Stats'}).click();
 await page.getByRole('button',{name:'Continue to Chemistry'}).click();
 await page.getByRole('button',{name:'Save chemistry',exact:true}).click();await expect(page.getByText('Saved.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Continue to Verification'}).click();await expect(page.getByRole('heading',{name:'Step 4 of 4 · Verification'})).toBeVisible();
}
test('avatar flow shows separate face comparison without blocking the test journey',async({page})=>{
 await page.goto('/');
 await openVerification(page);
 const fold=page.locator('#verification-face');
 if(!(await fold.evaluate(d=>d.open)))await fold.locator(':scope > summary').click();
 // a separate step of its own, which cannot start before DigiLocker identity is shared
 // (14c61fd/f0623e1: until then the step shows the prerequisite instead of the card)
 await expect(fold.locator(':scope > summary')).toContainText('Live face verification');
 await expect(fold).toContainText('Complete DigiLocker identity sharing first.');
 await expect(page.locator('#face-match-start')).toHaveCount(0);
 await expect(page.locator('#face-match-consent:checked')).toHaveCount(0);  // consent is never pre-ticked
 // never blocks the journey: the member can still step back through signup
 await page.getByRole('button',{name:'Previous step'}).click();await expect(page.getByRole('heading',{name:'Step 3 of 4 · Chemistry'})).toBeVisible();
});
