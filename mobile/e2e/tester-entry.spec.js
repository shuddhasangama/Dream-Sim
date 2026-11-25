import {test,expect} from '@playwright/test';
for(const signup of [false,true])test(`entry requires OTP: ${signup?'signup':'login'}`,async({page})=>{
 await page.goto('/');if(signup)await page.getByRole('button',{name:'Sign up',exact:true}).click();
 if(signup)await expect(page.getByRole('button',{name:'Send SMS code'})).toBeVisible();else{await expect(page.getByLabel('Password',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();}await expect(page.locator('#tester-login')).toHaveCount(0);await expect(page.getByText('Continue as tester without SMS',{exact:true})).toHaveCount(0);
 await expect(page.locator('.signup-intro')).toHaveCount(0);await expect(page.getByText('Declare a change',{exact:true})).toHaveCount(0);
});
