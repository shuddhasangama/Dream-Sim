# Prepared signup/verification release — 5 November 2026

Avatar setup opens directly in Verification after confirmed Aadhaar. The user captures a latest selfie, gives separate OpenAI consent, generates two options once, then selects one. The selection is saved to that account and used in its profile/match/comparison views. No Aadhaar/PAN photo is sent for generation. Live face comparison remains a separate step; its captured selfie can be reused if available. Court/FIR completion is not a prerequisite for generating or selecting an avatar.

The long-running BGV worker now gives avatars their own single processing thread and database connection. The legal/identity loop continues while image generation waits for OpenAI. Existing atomic claims and one-run ledger prevent paid retries. The --once diagnostic retains its sequential behavior. No new Railway variable or separate service is required. Both Dream-Sim and bgv-worker currently have DHASHU_AVATAR_ENABLED=1 and OPENAI_API_KEY configured.

## Release boundary

This release adds independent phone/OTP signup, resumable Vision → Stats → Chemistry → Verification, and automatic sandbox BGV assignment for Bangalore, Delhi and Mumbai. The Stats page is implemented with identity, optional claims, date preferences and optional health disclosure. Other metro cities remain catalogued but disabled. OTP verifies phone ownership; matching admission still requires the bound Aadhaar, live face and required legal/employment results. Avatar selection is not identity proof.

No Railway variable changes are needed with the currently audited configuration. DHASHU_DIGILOCKER_TESTERS is no longer used as a user-ID gate. Existing disabled accounts are not re-enabled. Signzy and Razorpay remain sandbox; this is production-style signup for the private tester distribution, not a switch to live billing or production Signzy.

No push, Railway deployment or Codemagic build was performed for this release.

## PowerShell: publish the prepared checkout to GitHub master

The primary dhashu-phase2 workspace has unrelated local changes. Use this prepared worktree; release changes are already committed. Do not run git add . in the primary workspace.

```powershell
Set-Location 'C:\DreamContractLocalBKP\ChatGPT\dhashu-waitlist-release'
git fetch origin master
git log --oneline origin/master..HEAD
git push origin HEAD:master
```

This is a normal fast-forward push, with no force and no local master checkout. A remote update causing divergence will be rejected. Stop and resolve it before deployment if the push fails.

## PowerShell: deploy both backend roles

Dream-Sim has the GitHub repository configured. bgv-worker currently has no repository source, so a GitHub push alone does not update that worker. Explicitly deploy both from the same committed checkout:

```powershell
$railway = "$env:APPDATA\npm\railway.cmd"
& $railway up --project c768517b-18ad-4855-8bad-521915324c10 --environment production --service Dream-Sim --detach
& $railway up --project c768517b-18ad-4855-8bad-521915324c10 --environment production --service bgv-worker --detach
```

Check that both deployments reach SUCCESS in Railway. Existing role variables are web for Dream-Sim and bgv-worker for bgv-worker. Existing credentials remain in Railway; none are embedded in these commands. The upload ignores outputs, private evidence and native files through .railwayignore.

## Codemagic and device acceptance (user managed)

After successful push and backend deployments, select master and the same release commit in Codemagic. Run ios-testflight for iOS; android-beta for a tester APK or android-play for a Play bundle. Distribute the resulting builds yourself.

On a testing account with an unused avatar allowance: sign in → complete Razorpay test checkout → connect/complete DigiLocker → confirm profile name and age update → open Your avatar (auto-expanded on first completion) → capture latest selfie → consent → generate two → choose one. Court/FIR can progress at the same time. Reopen the app to verify selection persists, and check profile/match/comparison display. Existing accounts that already used their one generation run do not get another run through deployment. A completed Razorpay transaction and native camera/browser-return flow still require device acceptance; automated tests do not substitute for those checks.

## Independent signup acceptance

Use Sign up with two separate real phone numbers. Receive and enter each SMS OTP, choose a Twogether plan, save Stats with an enabled launch city, save Chemistry and complete Verification. Close and reopen after Stats to verify resume. Confirm account separation, automatic Aadhaar name/age adoption, legal/face progress and saved avatar selection. New users are not admitted to matching merely by signing up. Actual SMS delivery, test checkout and native browser/camera return need device acceptance.
