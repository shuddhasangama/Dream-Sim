// cq-playwright: the ONE place browser tests sign in, so a change to sign-in is
// fixed here, not in every spec.
//
// Since 2026-11-07 an existing member signs in with phone + password (66f26c8);
// since 2026-11-17 only Indian numbers (10 digits, country IN by default) are
// accepted (ab658cd). The preview mock accepts any password and the code 123456,
// and both routes end on the same signed-in Home as the old SMS login did.
// Both helpers start from the sign-in screen the spec has already opened.
export const MEMBER_PHONE = '9876543210';   // Indian mobile, 10 digits
export const MEMBER_PASSWORD = 'TwelveChars!';
export const PREVIEW_CODE = '123456';

// Existing member: phone + password -> Sign in.
export async function signInMember(page, {phone = MEMBER_PHONE, password = MEMBER_PASSWORD} = {}) {
  await page.getByLabel('Phone number', {exact: true}).fill(phone);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
}

// New member (the spec has already chosen "Sign up"): phone -> SMS code -> Sign in.
export async function signUpWithCode(page, {phone = MEMBER_PHONE, code = PREVIEW_CODE} = {}) {
  await page.getByLabel('Phone number', {exact: true}).fill(phone);
  await page.getByRole('button', {name: 'Send SMS code'}).click();
  await page.getByLabel('Verification code').fill(code);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
}

// Existing member signing in with a one-time code instead of the password
// ("First password / forgot password? Use a code" -> recovery code).
export async function openCodeSignIn(page, {phone = MEMBER_PHONE} = {}) {
  await page.getByRole('button', {name: 'First password / forgot password? Use a code'}).click();
  await page.getByLabel('Phone number', {exact: true}).fill(phone);
}
