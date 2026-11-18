# Verification sequence and PAN-required employment

18 November 2026. Combine with signup-sections-release.md. No new database migration or environment variables.

## User flow
1. Payment if required.
2. DigiLocker Aadhaar identity, screening consent, and issued PAN document. PAN is extracted from the issued-document listing, not Aadhaar. Missing or mismatched PAN blocks employment only.
3. Hosted live-face verification. Avatar capture/generation is blocked on the backend until the hosted result matches the current DigiLocker session when hosted verification is enabled.
4. Review verified selfie, explicitly consent to OpenAI processing, then generate avatars. Generation has its own worker and does not wait for court/FIR checks. No automatic generation without consent.
5. Automatic employment, criminal court and FIR checks. Status and receipt/check dates remain separate. Completed controls use a black tick in the sequence; prerequisites use grey locked text.
6. Final review. Historical employment is not current employment confirmation. Source-bound support approval can satisfy the salaried employment admission requirement; history alone never automatically passes it.

## Employment diagnosis
Live output supplied for su_17a00beb7cba: issued PAN received, consent present, no employment request. This rules out missing PAN in that snapshot but does not establish a root cause. Inspect worker commit and logs, active identity-plan binding and provider pauses. New status output exposes identity-plan mismatch. Scheduling logs blocked API errors.
The existing employment_history adapter is retained. Its app-facing operation ID remains current_employer for compatibility. Phone-only fallback is removed; existing queued phone-only requests are stopped before provider IO.

## Deployment
Use the dhashu-employment-release checkout. Commit this and the pending signup/neighbourhood release together; fetch and rebase origin/master, then push HEAD:master (never force push).
Railway Dream-Sim AND bgv-worker must deploy the same commit, database and existing encryption key. Deploy the admin service too if it shares this repository and source configuration. Build both platforms in Codemagic from master after Railway succeeds.
Do not delete users, reset requests, or rerun all provider checks.

## Targeted employment check (Railway shell, after deployment)
Read-only:

    cd /app
    PYTHONPATH=/app /app/.venv/bin/python tools/check_employment_user.py --phone +919986006296

Submit only a missing/queued employment request using existing recorded consent (may consume provider credits):

    PYTHONPATH=/app /app/.venv/bin/python tools/check_employment_user.py --phone +919986006296 --run

No completed, failed, processing or uncertain request is replayed. Provider pause and policy checks remain enforced. If a worker claims the request concurrently, inspect its later status. No PAN or private response is printed. The scheduler may recover a missing document-listing prerequisite, but does not initiate court/FIR work in targeted mode.

## Acceptance
- No PAN: employment explains how to share PAN; court/FIR continue.
- Name mismatch: PAN not used; support review shown.
- Face not passed/current identity changed: avatar action blocked.
- Face passed: avatar opens; explicit consent required; court/FIR can still process.
- Completed exact court/FIR zero results: display source outcome, never comprehensive criminal clearance.
- Historical employer: history found, current employer unconfirmed; explicit source-bound support review for admission.
- Targeted command never selects a different user's provider request.

## Exact combined Git commands (Windows PowerShell)

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-employment-release

git add app.py avatar_service.py bgv_app.py bgv_bundle.py booking_coordination.py employment_lookup.py guru.py launch_cities.py launch_neighbourhoods.json neighbourhood_catalog.py planning_api.py planning_service.py self_signup.py mobile/src/digilocker.js mobile/src/screens/calendar.js mobile/src/screens/verification.js mobile/src/signupStats.js mobile/tests/verification.test.js mobile/tests/signupSections.test.js test_avatar_service.py test_employment_lookup.py test_planning_api.py test_self_signup.py tools/check_employment_user.py docs/signup-sections-release.md docs/verification-sequence-release.md

git diff --cached --stat
git diff --cached --check
git commit -m "Improve signup preferences and sequence PAN-based verification"
git fetch origin
git rebase origin/master
```

Stop if rebase reports conflicts. Otherwise:

```powershell
git push origin HEAD:master
git rev-parse --short HEAD
```

Verify that commit in Railway Dream-Sim and bgv-worker, then build master in Codemagic for iOS and Android. No schema or purge commands.

Validation: 54 targeted backend tests; 135 mobile tests; production mobile build; disposable PostgreSQL run 37 passed, 4 skipped. This PostgreSQL command includes SQLite-backed unit tests as well; it does not mean all 37 exercised PostgreSQL. No live provider request or deployment was performed locally.
