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

- New user: Sign up -> SMS OTP -> set/confirm a password (15–128 characters) -> Vision/Stats/Chemistry/Verification.
- Existing user: Log in -> First password / forgot password? Use a code -> phone including +91 -> SMS OTP -> set password. Signed-in users can also open Settings -> Set/reset login password. A recent provider-approved OTP is required; tester bypass is insufficient.
- Password setup/reset grants expire after 10 minutes and are one-use. If expired, Request a new verification code returns to recovery.
- Sign out -> phone + password -> sign in without sending SMS.
- App reopening continues to use the existing secure refresh-token flow. This release does not change session lifetimes or impose one-device-only login.
- Reset password using a fresh code -> all previous member sessions are revoked. The successful reset creates a replacement session on the current device. Lost reset responses require code recovery again.
- Wrong password, disabled accounts and unverified email are rejected. Rate limits are shared in the database. Password values are hashed with scrypt and never stored in the mobile vault.
- The member web /signin page also accepts the password set in the phone app. Web code sign-in remains available; password setup/reset UI is in the updated phone app.

## Optional verified email login and recovery

Phone/password works without any new Railway credentials or variables. Existing verified account emails also work as login identifiers.

To let members add a new email:
1. In Twilio Console, configure the existing Verify service's email channel with its SendGrid integration/sender. Merely owning office@shuddhasangama.org does not configure member email delivery.
2. Only once ready, set DHASHU_EMAIL_LOGIN_ENABLED=1 on Dream-Sim and apply the change. No need to add it to admin or bgv-worker. Default is off; the email enrollment panel is hidden while off.
3. In the phone app, Settings -> Email login & recovery -> enter email and current member password -> Send email code -> verify the delivered code.
4. Sign out and test email + password. Then test Use a code with that verified email, and set a replacement password.

If email delivery is not configured, leave the flag off. Phone/password login and SMS recovery still work. No live SMS or email was sent during local automated testing. Actual provider delivery and installed iPhone/Android behavior must be checked after release.

## Safeguards and limitations

No password is emailed, no automatic identity approval is added, and no member phone mapping changes. Password reset requires provider OTP approval even if a contact is already marked verified. Email enrollment requires the current password plus a code delivered to the new email, and is bound to the requesting session. It cannot claim another account's email. Dashboard access remains role-restricted, audited, masked, read-only and paginated.
