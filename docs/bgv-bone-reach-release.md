# Direct-app BGV pilot, Bone theme and REACH cycle freeze

Release prepared 3 November 2026. The user explicitly authorized deployment and
selected **m06**, internal account `test_blr_20260921_m06`, for real Signzy sandbox
tests. No provider calls should run merely to smoke-test the deployment.

## Included

- Phase 1 BGV app endpoints, encrypted policy/case/evidence and review records,
  DigiLocker photo consent and one-retrieval-per-session cooldown (30 minutes).
- Separate Railway web/worker roles through service_entrypoint.py. Web startup
  prepares the sandbox policy for the exact configured account, idempotently.
  No profile reset, phone ownership grant, match deletion or overall BGV approval.
- m06-only DigiLocker allowlist. With policy enforcement enabled, other accounts
  without an assigned case cannot submit the queued employer/court/FIR checks.
- Bone mobile presentation from the supplied HTML: ivory background, white cards,
  serif headings, local Outfit/Gloock/IBM Plex Mono fonts, logo and icon navigation,
  green/red/neutral status treatments. No external font calls or CSP relaxation.
- REACH freezes at the first persisted match reveal, without requiring mutual
  interest. Later daily slots keep the freeze between reveals. Empty/exhausted
  batches reopen it; three explicit own or received passes are resolved only once
  their scheduled reveal days have arrived. Active pairing keeps it closed across
  planning, date and pending debrief, including a new simulation week. Returning
  to the pool releases the pair; continuing to date together keeps the lock.
- Like/Pass use match eligibility, not REACH edit availability. API read/write
  guards, navigation eligibility and personal matching preferences share the
  cycle lock. The app notices eligibility changes even on an unchanged clock.

The actual saved reveal/window timestamps remain authoritative: this does not
move the existing Mon/Tue/Wed cadence or reset the current simulated clock. A
normal expired review is not recorded as an explicit pass. Rehearsal mode still
keeps unanswered matches open; it does not gain an expiry-based bypass.

## Operator configuration

Set these only for the controlled preproduction pilot, preserving existing tester,
clock, identity-capture and payment settings:

```
DHASHU_PROCESS_ROLE=web
DHASHU_BGV_APP_ENABLED=1
DHASHU_BGV_POLICY_ENABLED=1
DHASHU_BGV_BOOTSTRAP_USER_ID=test_blr_20260921_m06
DHASHU_DIGILOCKER_ENABLED=1
DHASHU_DIGILOCKER_TESTERS=test_blr_20260921_m06
DHASHU_DIGILOCKER_COOLDOWN_MINUTES=30
SIGNZY_ENV=preproduction
SIGNZY_PRODUCTION_ENABLED=0
```

Use the existing Signzy sandbox API key, callback configuration and one stable
SIGNZY_RECEIPT_ENCRYPTION_KEY. Back up the key privately; never commit it. API and
worker share it and the same Postgres database. Worker has
DHASHU_PROCESS_ROLE=bgv-worker and the same policy enforcement. Deploy the API and
verify its bootstrap message before starting the worker. No public worker domain
is required. Inspect queued requests before enabling worker execution; uncertain
provider calls are never automatically retried.

The first bootstrap assigns only the explicit IN/BLR sandbox policy to m06. A
different existing case stops deployment for operator review instead of replacing
evidence. Other users' public profiles and current matching eligibility remain
unchanged by BGV setup. The requested REACH rule applies to everyone.

## Tester acceptance

1. Install the new Android/TestFlight build; sign in to the existing m06 account
   with Continue as tester without SMS. Browser preview remains simulated.
2. Open profile/settings from the Home avatar, then Verify. The sandbox label and
   m06's phase checklist must be visible. Verify another tester cannot start BGV.
3. Use your own consenting identity. DigiLocker supplies real name/DOB/address and
   photo reference privately; it does not overwrite m06's simulated public profile.
4. Complete OTP and sharing outside the app, return manually and confirm once.
   Verify persistence after restart; an unconfirmed attempt must show cooldown.
5. Employer/court/FIR checks submit into the worker queue. Result buttons retrieve
   only the matching account's stored provider ID. Empty results require review.
6. Liveness stays a setup placeholder pending the vendor-approved upload/capture
   contract. Do not claim live liveness based on ordinary camera capture.
7. At first match reveal, REACH must disappear while Like/Pass remain usable.
   Direct API filter writes must return 403. Passing an early slot must not reopen
   it before later daily candidates. Three resolved passes/no available candidates
   reopen it; planning/date/debrief keep it closed while the pair remains active.

Fresh vendor/device acceptance remains a human test, particularly OTP and consent.
Automated responses are synthetic; a successful build is not proof of a passed BGV.
The iOS workflow uploads successful builds to TestFlight, not the public App Store.
