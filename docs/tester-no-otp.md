# Optional OTP-free tester entry

Disabled by default. Shared Android/iOS UI offers **Continue as tester without SMS** below normal SMS sign-in. Enter the phone already associated with the test Account. Log in opens Dashboard; Sign up reviews existing Vision, Stats and Chemistry. No SMS or access code is used. To act as the other test partner, log out and enter that partner's associated phone. Progress remains attached to each profile; this does not change rehearsal timing.

## Deploy in order

1. Deploy this backend code to Railway and build/distribute the updated Android and iOS apps from the same commit.
2. Keep AUTH_ENABLED and existing Twilio settings. Do not disable authentication globally.
3. In Dream-Sim service variables set DHASHU_TESTER_USER_IDS to a comma-separated list of the specific synthetic profile IDs you authorize, for example test_blr_20260921_m01,test_blr_20260921_f01. Check these IDs exist and have enabled Accounts with the intended phone associations. The list is an explicit operator designation, not an automatic synthetic-data check.
4. Set DHASHU_TESTER_NO_OTP=true and deploy the variable changes.
5. Test an allowed profile, normal SMS login, logout, and a profile outside the list (must be denied by the tester endpoint).

No database migration or new Twilio registration is required. The allowlist grants access to the whole selected profile to anyone who knows its phone number, including through direct API calls. Store tester lists do not protect the API. Use only disposable synthetic profiles; never include real private profiles. This is a testing entry method, not phone verification. Phone/email verification and BGV flags are unchanged.

## Revert

Set DHASHU_TESTER_NO_OTP=false and deploy. Existing tester access and refresh tokens then fail, while OTP sessions continue normally. Removing a user ID similarly blocks its tester sessions. Tokens are not permanently revoked merely by removing a flag/list entry: re-enabling it can re-enable still-unexpired tokens. Use auth_admin.py disable for permanent account/session revocation when retiring a tester. Normal logout also revokes the current session.

The button remains visible while disabled and reports that OTP-free access is unavailable; SMS sign-in remains available. Old app versions continue to use OTP. Native device validation and live deployment are separate from local tests.
