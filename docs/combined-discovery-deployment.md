# Combined signup and discovery release — 23 November 2026

## Location and scope

Use `C:\DreamContractLocalBKP\ChatGPT\dhashu-discovery-release`, branch `codex/combined-discovery-release`. Do not deploy from the older, modified `dhashu-phase2` folder.

This release is prepared locally, not pushed or deployed. It uses the existing Dream-Sim repository and existing Railway services. No new repository, service, database, MSG91 key or admin account is needed. No users are deleted.

| Area | Included |
|---|---|
| Signup | Age only, 18–120 whole years; no manual name/DOB; gender and city retained. Older installed clients can still submit the previous form. |
| Verified identity | DigiLocker remains the source of name/DOB and verified age. Declared age/gender are retained separately. Age differences are recorded and explained to the owner. Gender remains self-declared; this release does not claim it is document-verified. |
| Vision | Together wording; explicit pillars; Emotional required, Physical optional; no hidden Cohabitate detail requirement. Historical detail is retained. |
| Chemistry | 28 curated activities, popularity ordering, labelled expandable answers, suggestions and owner-only alias review. Conflicting old answers are archived rather than lost. |
| REACH | Verified viewers see verified profiles; unverified viewers can preview both. Daily previews expose age, city, pillars and verification label, not names, photos or BGV evidence. |
| Daily discovery | Two profiles/day, private interests/passes, mutual proposals, two confirmations before exclusive allocation, own-pass reconsideration and blocking. |
| City controls | Owner-only readiness switches in the existing MFA admin dashboard. No minimum registration threshold. Bangalore, Delhi and Mumbai start discovery-enabled; other cities remain disabled. |
| UI | Conditional children count, numeric range hints/error summary, focused REACH errors, reduced duplicated top safe-area spacing. |

## Important behavior before activation

- `DHASHU_DAILY_DISCOVERY=0` is the default. Signup, Vision and Chemistry changes work with it off. Legacy matching remains active until you deliberately enable the new flow.
- The new matching mode replaces the old numbered-match actions. Older app builds cannot use the new actions; distribute the updated app first.
- Defaults: two new profiles/day, reset midnight IST; interest lasts seven days; proposals expire after 24 hours. Views and one-sided confirmations do not hold anyone. Both confirmations atomically create one exclusive allocation.
- Wednesday onward, new pairings target the following weekend. Actual shared availability and restaurant booking are separate subsequent steps; confirming a pairing does not confirm a restaurant table.
- A city opens dates only when Discovery, Verification, Payments, Restaurants and Support are enabled and Paused is off. These are operator attestations of readiness, not automatic checks of vendor contracts.
- A pause stops new allocations; existing pairings/bookings are retained. Paid verification is blocked in discovery-only cities until verification and payment readiness are enabled.
- Existing date-cycle history remains excluded from pre-date reconsideration. A reset cannot undo another person's pass, a block or a past date.
- Profiles are not automatically recycled after exposure. A member can explicitly reconsider their own pre-date pass; a profile already shown today becomes eligible for a later daily batch, without creating an extra daily slot. No date or match is guaranteed in a small pool.
- The existing allocation transaction serializes writes conservatively. A large-population load test and a real-device pilot remain necessary before a broad public launch.

## 1. Commit and push — Windows PowerShell

Run in a local PowerShell window, not Railway:

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-discovery-release
git branch --show-current
git status --short
git diff --check
git add -A
git commit -m "Add age signup, curated chemistry and controlled daily discovery"
git fetch origin
git merge origin/master
git push origin HEAD:master
git rev-parse --short HEAD
```

The branch should be `codex/combined-discovery-release`. Review the listed files before committing. Generated previews, database fixtures and logs are inside ignored `data/`.

If Git reports a merge conflict, stop before pushing and resolve it; do not use force-push. Save the final commit ID to compare with Railway and Codemagic.

## 2. Railway — backend first

1. Verify a current production database backup, then use the existing `faithful-miracle / production` project.
2. In **Dream-Sim → Variables**, set `DHASHU_DAILY_DISCOVERY=0` during rollout. Keep existing MSG91, Signzy, database and payment variables.
3. Deploy the new `master` commit to Dream-Sim. Also deploy the same commit to **dhashu-admin** and **bgv-worker** if their automatic deployment did not run. Preserve each service's existing process role and start command.
4. Confirm all three deployments are healthy and show the expected commit.
5. In the **Dream-Sim Railway console**, run this idempotent schema check:

```bash
cd /app
/app/.venv/bin/python - <<'PY'
import db
conn = db.get_connection()
try:
    db.init_db(conn)
    for table in ('ActivityAlias', 'ActivitySuggestion', 'DiscoveryMarket',
                  'DiscoveryExposure', 'DiscoveryDecision', 'DiscoveryProposal',
                  'DiscoveryAllocation', 'DiscoveryEvent', 'DiscoveryBlock'):
        db.fetch_all(conn, table)
    print('Release schema ready. No users deleted; no provider calls sent.')
finally:
    conn.close()
PY
```

Take/verify a production database backup before the deployment. New schema objects are additive; this release does not drop or rewrite existing account or booking tables.

## 3. Codemagic — Android and iOS

1. Start each existing workflow using **master**, after the GitHub push.
2. Check the workflow commit matches Railway's commit. Existing workflows already use `PROJECT_BUILD_NUMBER` for native build numbering.
3. Publish the successful builds to your existing Android testing track and TestFlight.
4. Install the new builds on test devices. A Railway deployment alone cannot update the installed signup UI.
5. Check age-only signup, every Vision plan, Chemistry save/reload, REACH, OTP and interrupted-verification recovery. Use consenting testers; automated local tests do not send real OTP/BGV requests.

## 4. Admin readiness and new matching activation

1. Sign in to the existing admin dashboard with your password and Google Authenticator.
2. Open **Activity review** to map suggestions to a curated name. Do not merge broad categories such as Athletics into Running without reviewing the meaning.
3. Open **City readiness**. Set each city's switches independently. Leave other cities disabled.
4. Keep Restaurants off if reservations/support are not operational. A green switch is your confirmation that the corresponding service is genuinely ready.
5. After the updated mobile build and a small pilot are ready, set **Dream-Sim** `DHASHU_DAILY_DISCOVERY=1` and deploy that variable change. No need to change this flag on the worker.
6. Test two-sided interest, two confirmations, the three-person no-mutual-interest case, own-pass reset and a city pause. Confirm that existing bookings remain intact.

## Recovery

- To stop new pairings while retaining new discovery: use **City readiness → Paused**. This is the preferred operational pause.
- To return to legacy matching: set `DHASHU_DAILY_DISCOVERY=0` on Dream-Sim and redeploy. Existing active LockIns remain; proposals and histories are retained. Legacy behavior then applies, so review users with pending daily proposals before switching modes.
- Do not delete tables, reset users, or rotate OTP/provider credentials as part of this release.
- No public App Store launch is performed by these steps; testing-track distribution and final store release remain separate decisions.

## Validation and remaining launch checks

Local validation: 228 backend regression tests passed, followed by 12 discovery tests after the final reset fix; 140 mobile tests passed; eight PostgreSQL tests passed, including competing confirmations. The Vite production build and four phone-width renders also passed. The PostgreSQL test instance is local and isolated from Railway.

Not performed here: production deployment, live SMS/BGV/payment/restaurant calls, a real-device end-to-end pilot, or a scale/security certification. Dependency installation reports existing npm advisories; dependency remediation is not bundled into this feature release.
