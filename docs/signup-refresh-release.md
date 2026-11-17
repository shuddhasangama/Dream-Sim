# Signup and first-week release — 17 November 2026

## Changes
- Configured country picker: India +91 enabled; other listed countries disabled. Frontend and backend require exactly 10 Indian national digits.
- Public signup continues creating accounts only after successful OTP validation. A failed signup SMS now returns an actionable error rather than displaying the code-entry screen. Logs include only numeric provider HTTP status/error code, never provider messages, phone numbers or credentials.
- REACH can be opened during onboarding after Stats is saved, and returned from without losing the signup step. It shows potential compatibility, not reservations. Verification and completed onboarding remain necessary for dates.
- Monday/Tuesday empty batches can be checked again. Wednesday–Sunday new entrants wait until the next week. Existing scheduled Wednesday offers remain valid.
- Real matching reserves reciprocal, one-to-one slots atomically, with up to three sequential weekly opportunities. Existing batches and isolated rehearsal assignments stay intact. Allocation is deterministic, not registration-order FCFS.
- Date preferences now have a working mobile screen without prematurely exposing slot booking.
- Ethnicity and health sections collapse; signup ethnicity also collapses. Removed duplicate top safe-area padding; increased bottom clearance.
- Production default clock uses Asia/Kolkata. Legacy missing preference sections no longer crash candidate filtering.

## Deploy
Work from `C:\DreamContractLocalBKP\ChatGPT\dhashu-employment-release`, not the older dhashu-phase2 checkout.
Review `git status` and `git diff` before staging. No commit or deployment has been performed by this change.
Backend changes need Railway deployment; mobile changes need a new Codemagic Android/iOS build and tester update. No new database migration is required.
Keep valid Twilio credentials. Do not bulk-delete Railway variables. Disable simulation/test-pair settings only when moving the test environment to real weekly operation; check each service/environment intentionally.

## Read-only Railway audit
Run inside the Dream-Sim service container:
```sh
cd /app
PYTHONPATH=/app /app/.venv/bin/python tools/signup_diagnostics.py
```
A real delivery test is still required after deployment. Ask a tester to request one signup code and compare its time with Dream-Sim logs and Twilio Verify/Debugger logs. An accepted request does not prove handset delivery.

## Full user reset — separate from deployment
This is destructive and includes the formerly protected three accounts. Take a database backup and pause signup access/background jobs before running. Do not let a worker recreate records during the reset.
The helper aborts on unexpected user counts, live billing or provider bookings requiring reconciliation, and unsafe dependencies. It does not delete provider-side records, external files or backups, nor unrelated infrastructure/admin configuration.
First run the read-only audit for the CURRENT user count. Replace N below with that count (do not assume it is still 3):
```sh
cd /app
PYTHONPATH=/app /app/.venv/bin/python tools/purge_other_users.py --all-users --expected-users N
```
Review the table counts, then run the identical command with `--apply`:
```sh
PYTHONPATH=/app /app/.venv/bin/python tools/purge_other_users.py --all-users --expected-users N --apply
PYTHONPATH=/app /app/.venv/bin/python tools/signup_diagnostics.py
```
Confirm Users: 0 and Accounts: 0; resume services. Sign out on all test devices and start signup again. This script does not fix a Twilio account restriction or carrier delivery problem.

## Acceptance checks
1. India is selected; 9/11-digit input is rejected; other countries cannot be selected.
2. Fresh phone signup receives OTP; delivery failure displays an error. Valid OTP creates one account; repeat signup resumes it.
3. Stop at Vision/Stats, reopen and resume; verification remains accessible.
4. Save Stats, open REACH, change a filter and return to signup.
5. Complete two compatible verified profiles Monday/Tuesday: reciprocal offers; third user cannot occupy the same slot with either person.
6. Join Wednesday or later: REACH works, no new date offer that week. Existing Wednesday offers work.
7. Date preferences open and save instead of the fallback screen. Slot selection remains in the calendar.
8. Check collapsible sections and safe-area spacing on iPhone and Android.

## Limits
Live Railway state, Twilio account restrictions and actual SMS delivery have not been inspected from this workspace. No live users have been deleted. Mobile device visual checks remain part of tester acceptance.

## Git promotion commands (PowerShell)
```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-employment-release
git status --short
git add app.py auth.py auth_delivery.py clock.py matching.py week_service.py phone_country.py phone_countries.json mobile/src/main.js mobile/src/phoneCountry.js mobile/src/bone.css mobile/src/signup.js mobile/src/signupStats.js mobile/src/screens/align.js mobile/src/screens/calendar.js mobile/src/screens/personal.js mobile/src/screens/reach.js mobile/tests/align.test.js mobile/tests/phoneCountry.test.js mobile/tests/signupResume.test.js test_auth.py test_auth_delivery.py test_self_signup.py test_phone_country.py test_signup_matching.py test_week_postgres.py test_purge_other_users.py tools/purge_other_users.py tools/signup_diagnostics.py docs/signup-refresh-release.md
git diff --cached --stat
git commit -m "Fix public signup diagnostics and first-week matching UX"
git fetch origin
git log --oneline HEAD..origin/master
```
If the last command shows no remote-only commits, push with `git push origin HEAD:master`. If it lists commits, integrate/review those changes first; do not force-push.
Wait for Dream-Sim to deploy the new commit. Then build Android/iOS from the same master commit in Codemagic. A Railway-only deploy will not update the installed country picker or mobile screens.
