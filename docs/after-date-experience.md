# After-date experience: release and tester checks

This update needs **Railway plus new Android and iOS builds**. The screens are bundled in the apps; a Railway variable cannot replace the installed JavaScript.

## What changed

- Dedicated consent, home-visit and Relationship conversation screens replace raw JSON.
- Guru exposes eligible after-date activities even while the account is in Dating. It explicitly describes itself as stage-based guidance, not a free-text AI chat. Its responses do not infer agreement from written answers.
- Each partner can select up to three topics, including one custom question. Both answer the shared topics independently. Custom question text is shared; Relationship answers remain private. The separate optional closeness conversation explains its reciprocal answer-sharing rule before submission.
- Empty question sets are incomplete. Confirmation requires answers, reflection, mutual intent, exclusivity acknowledgements, both entry agreements and both profiles' prerequisites.
- In the existing asynchronous beta only, each partner can explicitly finish reflection. Both acknowledgements are required; editing an answer or adding topics resets them. This also permits the later health-openness question to open in the rehearsal, avoiding a frozen-clock prerequisite loop. Normal operation keeps the timed intervals.
- Contact details are released only after acceptance and both contact agreements. Instagram/LinkedIn acceptance collects the recipient's chosen handle. Home visits disclose expectations, require acknowledgement and remain cancellable without penalty. There is no automatic trusted-contact notification or real biometric check.
- Home and Week explain next steps. Week hides generic signing and Debrief placeholders when no relevant plan exists, and shows the actual saved date/time rather than matching it to an inaccurate meal-template hour.
- Partner context follows the existing name-disclosure policy. Before meeting, the app explains why the name is hidden and shows the partner's city, age, profession and Vision summary.
- Prerequisite errors retain their actual explanation instead of all becoming “already handled.”
- Phone layouts accommodate wrapping, safe areas, scrolling and enlarged content. Browser checks do not replace a real-device iOS pinch-zoom check.

No live data, phone assignments, matches, signatures or tester accounts have been reset.

## 1. Commit and push from Windows PowerShell

Run from the repository, not from Railway. These are the files changed for this task; review `git diff` before committing.

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
git status --short
git diff --check
if ($LASTEXITCODE -ne 0) { throw "Fix whitespace errors before continuing." }
git add -u
git add docs/after-date-experience.md mobile/src/screens/afterDate.js mobile/src/screens/gate.js mobile/src/screens/pairContext.js mobile/tests/afterDate.test.js mobile/e2e/after-date.spec.js test_after_date_experience.py
git diff --cached --stat
git commit -m "Complete after-date consent and relationship experience"
if ($LASTEXITCODE -ne 0) { throw "Commit failed; stop here." }
git push origin master
if ($LASTEXITCODE -ne 0) { throw "Push failed; stop here." }
git log -1 --oneline
```

Leave `mobile/android/.idea/` untracked. Do not use `git add .`.

## 2. Railway backend first

1. Open the existing **Dream-Sim** service, **Deployments**.
2. Wait for the GitHub-triggered deployment of the commit above to succeed. If automatic deployment is disabled, deploy that commit manually.
3. Keep existing authentication, tester allowlists, phone associations, fixed pairs, start week and clock variables. This change introduces no new variables.
4. For the current asynchronous rehearsal, these existing settings must remain enabled:

| Variable | Rehearsal value |
|---|---|
| `DHASHU_SIMULATED_CLOCK` | `true` |
| `DHASHU_ASYNC_TEST` | `true` |
| `BETA_DATE_SIMULATION_ENABLED` | `1` |

Keep your existing payment-test settings unchanged. These settings simulate the clock and face step; they do not implement live verification.

5. In **Dream-Sim → Console**, run this against the newly deployed code:

```bash
python -c "import db; c=db.get_connection(); db.init_db(c); print(db.reconcile_columns(c)); c.close()"
```

Normal output after initialization is `{'added': [], 'needs_migration': []}`. The additive schema changes are `StageGate.reflection_ready_a`, `StageGate.reflection_ready_b`, `GateAsk.custom_question` and `ContactRequest.shared_contact`. Existing rows are preserved. If the command errors or reports `needs_migration`, stop and inspect the output before distributing the apps.

Do not rerun a user reset or pairing script for this release.

## 3. Build and distribute Android

1. Codemagic: branch **master**, workflow **android-play / DhaShu Android Play Bundle**.
2. Confirm its commit matches the Railway deployment.
3. Download `app-release.aab` after a successful build.
4. Play Console: **DhaShu → Internal testing → Create new release**, upload the AAB, review and publish it to the existing tester group.
5. Testers update DhaShu through their existing testing link/Play Store account.

The workflow already builds the web assets and runs `cap sync android`. No separate local sync or APK build is required.

## 4. Build and distribute iOS

1. Codemagic: branch **master**, workflow **ios-testflight / DhaShu iOS TestFlight**.
2. Confirm the same commit and let the workflow build/upload the IPA.
3. App Store Connect: **DhaShu → TestFlight**; wait for processing, complete any requested build information, and assign the new build to the existing tester group. The current YAML does not automatically submit it for TestFlight testing.
4. Testers open **TestFlight → DhaShu → Update**.

Keep Codemagic's existing `DHASHU_SIMULATED_CLOCK: "false"` build setting: that hides manual clock-jump controls. It does not disable the server-driven asynchronous rehearsal.

## 5. Two-phone smoke test (no reset)

Use your existing f06/m06 accounts wherever their saved journey currently stands:

1. Home/Week should explain the next activity and whose action is needed. A saved date should show its actual time and partner context.
2. After a completed date, open Guru and choose the sharing/after-date activity. Confirm there is a form, not JSON.
3. Contact sharing: complete each person's agreement separately; request a channel; have the other person accept. Check details stay hidden before acceptance and both agreements.
4. Optional home visit: finish the required agreements, propose a visit, then use the recipient phone to review expectations and respond. Each acknowledges separately. Verify cancellation is available.
5. Relationship conversation: choose topics and optionally add a custom question. Answer on one phone, close it, then answer on the other. The first person's answers must remain saved and private.
6. Both tap **I have reflected (test)**. Complete any listed profile prerequisites under Home and **Review boundaries & expectations**. Neither person's confirmation or agreement should be filled in automatically.
7. Both confirm intent, acknowledge exclusivity, and complete their own entry agreements. **Enter Relationship** enables only when both are ready.
8. On the iPhone Plus, test portrait/landscape, keyboard entry and pinch zoom. All final buttons must remain reachable by scrolling. Report the device/iOS version and screen if not.

Manual **Refresh partner progress** is available in both new screens, including when the simulated clock stays at the same time.

## Local verification commands

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
python -m pytest -q
cd mobile
npm test
npx playwright test
npm run build
```

The backend tests use isolated test databases; the browser tests use local preview/component fixtures. They do not contact Railway, Twilio or a live BGV provider.

## Reverting

Revert this release commit and redeploy the backend and both mobile workflows. Leave the additive database columns and saved user records in place; do not drop columns or reset journeys. Turning off the existing asynchronous-test flag restores ordinary timing, but changes test behavior for all users sharing that environment.

## Verification completed for this change

- Python: 1,440 passed, 30 skipped, 761 subtests passed.
- Mobile unit tests: 85 passed.
- Playwright: 36 passed; the four new after-date component checks were repeated after button styling changed and passed.
- Production web asset build: successful.
- Whitespace check: clean (Git may emit normal LF/CRLF conversion warnings).

Native signed Android/iOS builds, Railway rollout, real-device pinch zoom and third-party delivery were not executed by this local test run.
