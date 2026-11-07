# Member password login and dashboard count details

Prepared in C:\DreamContractLocalBKP\ChatGPT\dhashu-waitlist-release. No accounts are deleted or reassigned. Admin login remains password + authenticator; member passwords are separate.

## Release order

1. In Windows PowerShell:

```powershell
Set-Location 'C:\DreamContractLocalBKP\ChatGPT\dhashu-waitlist-release'
git fetch origin master
git log --oneline origin/master..HEAD
git push origin HEAD:master
$railway = "$env:APPDATA\npm\railway.cmd"
& $railway up --project c768517b-18ad-4855-8bad-521915324c10 --environment production --service Dream-Sim --detach
```

2. Wait for Dream-Sim to become healthy. Startup applies additive PasswordGrant and MemberEmailChallenge tables. No manual database edits needed. Keep AUTH_ENABLED and Twilio Verify configured for initial phone verification and recovery.
3. The GitHub-connected dhashu-admin service should redeploy from master. Check it is successful. If it does not redeploy automatically:

```powershell
& $railway up --project c768517b-18ad-4855-8bad-521915324c10 --environment production --service dhashu-admin --detach
```

No bgv-worker deployment is required for this change. Keep DHASHU_ACTIVITY_ENABLED=1 on Dream-Sim. Do not change OTP-bypass, simulated-clock, BGV or billing settings for this release.
4. Build the updated master commit in Codemagic for iOS/Android; distribute through TestFlight/your Android test track. Use a new build number. Old builds can still use OTP; password UI needs this new build.
5. Hard-refresh the admin website. Click any Overview numeric count, journey-stage count or recorded signup milestone to see its filtered accounts. Click an account for support details. Refresh preserves the selected filter or account; Back returns to the list/overview. Verification counts open request records (not unique people). Owner marketing city/payment counts open matching accounts. Marketing-only admins cannot access individual accounts.

## Phone/password testing

- New user: Sign up -> SMS OTP -> set/confirm a password (12–128 characters) -> Vision/Stats/Chemistry/Verification.
- Existing user: Log in -> First password / forgot password? Use a code -> phone including +91 -> SMS OTP -> set password. Signed-in users can also open Settings -> Set/reset login password. A recent provider-approved OTP is required; tester bypass is insufficient.
- Password setup/reset grants expire after 10 minutes and are one-use. If expired, Request a new verification code returns to recovery.
- Sign out -> phone + password -> sign in without sending SMS.
- App reopening continues to use the existing secure refresh-token flow. This release does not change session lifetimes or impose one-device-only login.
- Reset password using a fresh code -> all previous member sessions are revoked. The successful reset creates a replacement session on the current device. Lost reset responses require code recovery again.
- Wrong passwords, disabled accounts and email login attempts are rejected. Rate limits are shared in the database. Password values are hashed with scrypt and never stored in the mobile vault.
- The member web /signin page also accepts the password set in the phone app. Web code sign-in remains available; password setup/reset UI is in the updated phone app.

## Phone-only authentication

Member login, first password setup and recovery use the registered phone only. No email is requested, linked or used to sign in or reset a password. Existing email data is retained but cannot authenticate. No new Railway variables or email service setup are needed; DHASHU_EMAIL_LOGIN_ENABLED is no longer used and may be removed if previously added.

Recovery: enter registered phone -> receive SMS OTP -> choose a new password (12–128 characters). The app keeps valid sessions signed in through its existing refresh-token flow. SMS is needed for initial signup, first password setup or recovery, not normal password login.

Existing longer passwords remain valid. Rebuild the mobile app from the updated commit even if you already built the preceding version: it has the 12-character minimum and phone-only screens. Deploy Dream-Sim before distributing that build.

## Communication addresses

| Address | Purpose |
| --- | --- |
| hello@dhashu.com | Future member-facing communications; not needed for phone-only login/reset |
| operations@dhashu.com | Internal operations |
| partners@dhashu.com | Signzy, Brand Meadows, Razorpay and other vendors |
| office@shuddhasangama.org | Existing private dashboard owner login |

The private dashboard retains its own email identifier, password and authenticator. No sender mailbox, DNS or provider configuration was changed. Sending future member emails from hello@dhashu.com will require configuring/verifying that sender with the selected email provider; it does not affect this release.

## Safeguards and validation

Passwords are scrypt-hashed. Setup/reset requires a fresh provider-approved SMS OTP, with a ten-minute one-use grant; tester bypass cannot set a password. Successful reset revokes old member sessions. Login attempts and SMS requests remain rate limited. No automatic identity approval or phone-account reassignment is introduced. Dashboard reporting stays read-only, masked, paginated and role-restricted.

Automated tests mock provider calls: no real SMS or email is sent. Test SMS delivery and the installed iPhone/Android flow after deployment. Dashboard counts and filters from the previous commit remain included.
